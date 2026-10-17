"""SQLite metadata and opaque, validated filesystem media for the local app."""
import base64
import binascii
import io
import hashlib
import json
import os
import re
import sqlite3
import uuid
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageOps

from .predictions import PIPELINE_VERSION, TERMINAL, csv_bytes, envelope
from .transport import encoded, digest

MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000
MIMES = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')


class ConflictError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, name, limit=16000, required=False):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value or (required and not value.strip()):
        raise ValueError('Enter a valid ' + name + '.')
    return value.strip()


def source_url(value):
    value = text(value, 'manufacturer source URL', 2000, True)
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Enter an http or https manufacturer source URL.')
    return value


def filename(value):
    value = text(value, 'filename', 180, True)
    if '/' in value or '\\' in value or any(ord(c) < 32 for c in value) or value in ('.', '..'):
        raise ValueError('Use a filename without folders or control characters.')
    return value


def validate_upload(item, pdf=False):
    if not isinstance(item, dict):
        raise ValueError('Each file needs a filename and data URL.')
    name = filename(item.get('filename'))
    data = item.get('data_url')
    if not isinstance(data, str) or len(data) > MAX_FILE_BYTES * 4 // 3 + 100:
        raise ValueError('Each file must be 12 MiB or smaller.')
    match = re.fullmatch(r'data:([a-z]+/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=\r\n]*)', data)
    if not match:
        raise ValueError('Upload a base64 image or PDF data URL.')
    try:
        raw = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('The uploaded file could not be decoded.') from None
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError('Each file must contain data and be 12 MiB or smaller.')
    if pdf:
        if match[1] != 'application/pdf' or not raw.startswith(b'%PDF-') or b'%%EOF' not in raw[-2048:]:
            raise ValueError('Upload a valid original PDF document.')
        return {'filename': name, 'mime': 'application/pdf', 'raw': raw, 'provider': None, 'kind': 'pdf'}
    if match[1] not in MIMES.values():
        raise ValueError('Use JPEG, PNG or WebP images.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in MIMES or MIMES[image.format] != match[1]:
                    raise ValueError('Image bytes do not match the declared file type.')
                if image.width * image.height > MAX_PIXELS or image.width <= 0 or image.height <= 0:
                    raise ValueError('Images must be 40 megapixels or smaller.')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Use a single-frame image.')
                image.verify()
            with Image.open(io.BytesIO(raw)) as original:
                image = ImageOps.exif_transpose(original)
                image.load()
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    background = Image.new('RGBA', rgba.size, 'white')
                    image = Image.alpha_composite(background, rgba).convert('RGB')
                else:
                    image = image.convert('RGB')
                image.thumbnail((2048, 2048))
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=92)
    except ValueError:
        raise
    except Exception:
        raise ValueError('This image is damaged or cannot be opened.') from None
    return {'filename': name, 'mime': match[1], 'raw': raw, 'provider': output.getvalue(), 'kind': 'image'}


class Store:
    def __init__(self, root, data_dir):
        self.root = Path(root).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data_dir.chmod(0o700)
        for folder in ('media', 'jobs'):
            (self.data_dir / folder).mkdir(exist_ok=True, mode=0o700)
            (self.data_dir / folder).chmod(0o700)
        self.db = self.data_dir / 'app.sqlite3'
        descriptor = os.open(self.db, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self.db.chmod(0o600)
        with self.connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS media (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime TEXT NOT NULL,
                    original_path TEXT NOT NULL, provider_path TEXT, kind TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, job_ids TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL,
                    snapshot TEXT NOT NULL, media_id TEXT NOT NULL REFERENCES media(id));
                CREATE TABLE IF NOT EXISTS prediction_exports (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(id), json_bytes BLOB NOT NULL, csv_bytes BLOB NOT NULL);
            """)
        self.seed()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _save_media(self, connection, item):
        key = uuid.uuid4().hex
        suffix = '.pdf' if item['kind'] == 'pdf' else {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}[item['mime']]
        original = 'media/' + key + suffix
        provider = 'media/' + key + '.provider.jpg' if item['provider'] is not None else None
        (self.data_dir / original).write_bytes(item['raw'])
        (self.data_dir / original).chmod(0o600)
        if provider:
            (self.data_dir / provider).write_bytes(item['provider'])
            (self.data_dir / provider).chmod(0o600)
        connection.execute('INSERT INTO media VALUES (?,?,?,?,?,?)',
                           (key, item['filename'], item['mime'], original, provider, item['kind']))
        return key

    def media(self, key, provider=False):
        if not ID.fullmatch(key):
            raise KeyError('Image not found.')
        with self.connect() as connection:
            row = connection.execute('SELECT * FROM media WHERE id=?', (key,)).fetchone()
        if row is None:
            raise KeyError('Image not found.')
        relative = row['provider_path'] if provider else row['original_path']
        if not relative:
            raise KeyError('Image not found.')
        path = (self.data_dir / relative).resolve()
        if not path.is_relative_to(self.data_dir / 'media') or not path.is_file():
            raise KeyError('Image not found.')
        return path, 'image/jpeg' if provider else row['mime'], row['filename']

    def seed(self):
        with self.connect() as connection:
            if connection.execute('SELECT COUNT(*) FROM products').fetchone()[0]:
                return
            seed = (self.root / 'var/catalogue-seed').resolve()
            cards = json.loads((seed / 'reference_cards.json').read_text())['products']
            for key, card in cards.items():
                images = []
                for reference in card['images']:
                    path = (seed / reference['file']).resolve()
                    if not path.is_relative_to(seed):
                        raise ValueError('Invalid manufacturer reference path.')
                    raw = path.read_bytes()
                    with Image.open(io.BytesIO(raw)) as image:
                        mime = MIMES[image.format]
                    item = validate_upload({'filename': path.name, 'data_url': 'data:' + mime + ';base64,' + base64.b64encode(raw).decode()})
                    images.append(self._save_media(connection, item))
                passages = '\n\n'.join(source['supporting_passage'] for source in card['sources'])
                brochure_id = None
                if card.get('brochure_file'):
                    path = (seed / card['brochure_file']).resolve()
                    if not path.is_relative_to(seed):
                        raise ValueError('Invalid manufacturer document path.')
                    item = validate_upload({'filename': path.name, 'data_url': 'data:application/pdf;base64,' + base64.b64encode(path.read_bytes()).decode()}, pdf=True)
                    brochure_id = self._save_media(connection, item)
                data = {'id': key, 'name': card['name'], 'manufacturer': 'Shark' if key.startswith('shark_') else 'Dyson',
                        'in_catalog': card['in_catalog'], 'source_url': card['sources'][0]['url'],
                        'brochure_details': passages, 'sources': card['sources'],
                        'visible_features': card.get('visible_features', []), 'variant_limits': card.get('variant_limits', []),
                        'image_ids': images, 'brochure_id': brochure_id}
                connection.execute('INSERT INTO products VALUES (?,?)', (key, json.dumps(data)))

    def _product(self, connection, data):
        images = []
        for key in data['image_ids']:
            row = connection.execute('SELECT filename FROM media WHERE id=?', (key,)).fetchone()
            images.append({'id': key, 'url': '/media/' + key, 'filename': row['filename']})
        brochure = connection.execute('SELECT filename FROM media WHERE id=?', (data['brochure_id'],)).fetchone() if data.get('brochure_id') else None
        return {key: data[key] for key in ('id', 'name', 'manufacturer', 'in_catalog', 'source_url', 'brochure_details')} | {
            'images': images, 'image_url': images[0]['url'] if images else None,
            'brochure_url': '/media/' + data['brochure_id'] if data.get('brochure_id') else None,
            'brochure_filename': brochure['filename'] if brochure else None}

    def products(self):
        with self.connect() as connection:
            return [self._product(connection, json.loads(row['data'])) for row in connection.execute('SELECT data FROM products ORDER BY rowid')]

    def product(self, key):
        with self.connect() as connection:
            row = connection.execute('SELECT data FROM products WHERE id=?', (key,)).fetchone()
            if row is None:
                raise KeyError('Product not found.')
            return self._product(connection, json.loads(row['data']))

    def edit_product(self, payload, key=None):
        if not isinstance(payload, dict):
            raise ValueError('Enter product details.')
        allowed = {'name', 'manufacturer', 'source_url', 'brochure_details', 'images', 'brochure'}
        if set(payload) - allowed:
            raise ValueError('Unknown product field.')
        validated = {}
        for field, limit in [('name', 180), ('manufacturer', 180), ('brochure_details', 16000)]:
            if field in payload or key is None:
                validated[field] = text(payload.get(field, ''), field.replace('_', ' '), limit, field == 'name')
        if 'source_url' in payload or key is None:
            validated['source_url'] = source_url(payload.get('source_url'))
        images = payload.get('images', [])
        if not isinstance(images, list) or len(images) > 10 or (key is None and not images):
            raise ValueError('Add one to ten manufacturer images.')
        image_items = [validate_upload(item) for item in images]
        brochure = payload.get('brochure')
        brochure_item = validate_upload(brochure, pdf=True) if brochure is not None else None
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if key is not None:
                row = connection.execute('SELECT data FROM products WHERE id=?', (key,)).fetchone()
                if row is None:
                    raise KeyError('Product not found.')
                data = json.loads(row['data'])
            else:
                data = {'id': uuid.uuid4().hex, 'in_catalog': True, 'image_ids': [], 'brochure_id': None,
                        'visible_features': [], 'variant_limits': [], 'sources': []}
            data.update(validated)
            data['image_ids'] += [self._save_media(connection, item) for item in image_items]
            if brochure_item:
                data['brochure_id'] = self._save_media(connection, brochure_item)
            connection.execute('INSERT INTO products VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                               (data['id'], json.dumps(data)))
            return self._product(connection, data)

    def _snapshot(self, connection):
        products = []
        for row in connection.execute('SELECT data FROM products ORDER BY rowid'):
            data = json.loads(row['data'])
            data['image_records'] = [dict(connection.execute('SELECT id,filename FROM media WHERE id=?', (key,)).fetchone()) for key in data['image_ids']]
            products.append(data)
        return products

    def _request(self, payload, retry_of=None):
        key = payload.get('request_id')
        if key is None:
            return None, None
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise ValueError('Use a valid request ID.')
        fingerprint = hashlib.sha256(json.dumps({'kind': 'retry' if retry_of else 'upload', 'original_job': retry_of, 'payload': payload}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return key, fingerprint

    def _cached(self, connection, key, fingerprint):
        if key is None:
            return None
        row = connection.execute('SELECT fingerprint,job_ids FROM requests WHERE id=?', (key,)).fetchone()
        if row is None:
            return None
        if row['fingerprint'] != fingerprint:
            raise ConflictError('This request ID was already used with different content. Start a new selection or retry.')
        return [json.loads(connection.execute('SELECT data FROM jobs WHERE id=?', (job,)).fetchone()['data']) for job in json.loads(row['job_ids'])]

    def cached_jobs(self, payload, retry_of=None):
        key, fingerprint = self._request(payload, retry_of)
        with self.connect() as connection:
            return self._cached(connection, key, fingerprint)

    def _save_request(self, connection, key, fingerprint, jobs):
        if key is not None:
            connection.execute('INSERT INTO requests VALUES (?,?,?)', (key, fingerprint, json.dumps([job['id'] for job in jobs])))

    def create_jobs(self, payload, *, with_created=False):
        if not isinstance(payload, dict) or set(payload) - {'images', 'expected_product_id', 'request_id', 'parent_job_id', 'same_product'}:
            raise ValueError('Enter images and an optional expected product.')
        request_id, fingerprint = self._request(payload)
        images = payload.get('images')
        if not isinstance(images, list) or not 1 <= len(images) <= 5:
            raise ValueError('Upload one to five store images.')
        grouped = 'parent_job_id' in payload or 'same_product' in payload
        if grouped and (len(images) != 1 or payload.get('same_product') is not True or payload.get('expected_product_id') is not None):
            raise ValueError('Add one new photo of the same product in Identify mode.')
        items = [validate_upload(item) for item in images]
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            cached = self._cached(connection, request_id, fingerprint)
            if cached is not None:
                return (cached, False) if with_created else cached
            if grouped:
                parent_key = payload.get('parent_job_id')
                if not isinstance(parent_key, str) or not ID.fullmatch(parent_key):
                    raise ValueError('Choose a completed Identify result with one machine.')
                parent_row = connection.execute('SELECT * FROM jobs WHERE id=?', (parent_key,)).fetchone()
                parent = json.loads(parent_row['data']) if parent_row else None
                if not parent or parent['status'] != 'completed' or parent['mode'] != 'identify' or len(parent.get('matches', [])) != 1:
                    raise ValueError('Choose a completed Identify result with one machine.')
                prior = self._views(connection, parent_row)
                if len(prior) >= 3:
                    raise ValueError('A product can have at most three views.')
                for view in prior:
                    saved = connection.execute('SELECT original_path,provider_path FROM media WHERE id=?', (view['media_id'],)).fetchone()
                    if (digest((self.data_dir / saved['original_path']).read_bytes()) == digest(items[0]['raw']) or
                            digest((self.data_dir / saved['provider_path']).read_bytes()) == digest(items[0]['provider'])):
                        raise ValueError('Choose a different photo of this product.')
                media_id = self._save_media(connection, items[0])
                views = prior + [{'media_id': media_id, 'filename': items[0]['filename']}]
                jobs = [self._insert_job(connection, prior[0]['media_id'], prior[0]['filename'],
                        json.loads(parent_row['snapshot']), None, views=views, parent_job_id=parent_key,
                        root_job_id=parent.get('root_job_id', parent_key))]
                self._save_request(connection, request_id, fingerprint, jobs)
                return (jobs, True) if with_created else jobs
            snapshot = self._snapshot(connection)
            expected = payload.get('expected_product_id')
            if expected is not None and (not isinstance(expected, str) or expected not in {p['id'] for p in snapshot if p['in_catalog']}):
                raise ValueError('Choose an expected model from the catalogue.')
            jobs = [self._insert_job(connection, self._save_media(connection, item), item['filename'], snapshot, expected) for item in items]
            self._save_request(connection, request_id, fingerprint, jobs)
        return (jobs, True) if with_created else jobs

    def _views(self, connection, row):
        data = json.loads(row['data'])
        views = data.get('views') or [{'image_url': '/media/' + row['media_id']}]
        saved = []
        for view in views:
            url = view.get('image_url', '')
            key = url.removeprefix('/media/')
            if not url.startswith('/media/') or not ID.fullmatch(key):
                raise ValueError('Invalid saved product view.')
            media = connection.execute('SELECT id,filename FROM media WHERE id=?', (key,)).fetchone()
            if media is None:
                raise ValueError('A saved product view is unavailable.')
            saved.append({'media_id': media['id'], 'filename': media['filename']})
        return saved

    def _insert_job(self, connection, media_id, name, snapshot, expected, *, views=None, parent_job_id=None, root_job_id=None):
        key = uuid.uuid4().hex
        product = next((p for p in snapshot if p['id'] == expected), None)
        job = {'id': key, 'filename': name, 'image_url': '/media/' + media_id,
               'created_at': now(), 'status': 'queued', 'stage': 'Waiting to run',
               'mode': 'verify' if expected else 'identify', 'expected_product_id': expected,
               'expected_product_name': product['name'] if product else None,
               'cost_inr': 0.0, 'error': None, 'matches': [], 'exports_available': False, 'run_details': None, 'export_error': None}
        if views:
            job.update(view_count=len(views), parent_job_id=parent_job_id, root_job_id=root_job_id,
                       views=[{'view_id': 'view_' + str(index + 1), 'filename': view['filename'],
                               'image_url': '/media/' + view['media_id']} for index, view in enumerate(views)])
        connection.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                           (key, job['created_at'], json.dumps(job), json.dumps(snapshot), media_id))
        return job

    def jobs(self):
        with self.connect() as connection:
            return [json.loads(row['data']) for row in connection.execute('SELECT data FROM jobs ORDER BY created_at DESC, rowid DESC')]

    def job(self, key, internal=False):
        with self.connect() as connection:
            row = connection.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
            views = self._views(connection, row) if row is not None and internal else None
        if row is None:
            raise KeyError('Run not found.')
        data = json.loads(row['data'])
        if internal:
            data['_snapshot'] = json.loads(row['snapshot'])
            data['_media_id'] = row['media_id']
            data['_views'] = views
        return data

    def update_job(self, key, **changes):
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT data FROM jobs WHERE id=?', (key,)).fetchone()
            if row is None:
                raise KeyError('Run not found.')
            data = json.loads(row['data'])
            data.update(changes)
            connection.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data, allow_nan=False), key))
        return data

    def seal_prediction(self, key, run_details):
        """Save both download bodies in the same transaction, once per terminal job."""
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
            if row is None:
                raise KeyError('Run not found.')
            data = json.loads(row['data'])
            if data['status'] not in TERMINAL or connection.execute('SELECT 1 FROM prediction_exports WHERE job_id=?', (key,)).fetchone():
                return data
            media = connection.execute('SELECT original_path FROM media WHERE id=?', (row['media_id'],)).fetchone()
            path = (self.data_dir / media['original_path']).resolve()
            if not path.is_relative_to(self.data_dir / 'media'):
                raise ValueError('Invalid saved photograph path.')
            for match in data['matches']:
                match.setdefault('retake_guidance', list(match.get('missing_evidence', [])))
            data.update(run_details=run_details, exports_available=True, export_error=None)
            value = envelope(data, digest(path.read_bytes()), now())
            if data.get('view_count', 1) > 1:
                value['views'] = [dict(view) for view in data['views']]
                for view, saved in zip(value['views'], self._views(connection, row)):
                    media = connection.execute('SELECT original_path FROM media WHERE id=?', (saved['media_id'],)).fetchone()
                    original = (self.data_dir / media['original_path']).resolve()
                    if not original.is_relative_to(self.data_dir / 'media'):
                        raise ValueError('Invalid saved product view path.')
                    view['sha256'] = digest(original.read_bytes())
            connection.execute('INSERT INTO prediction_exports VALUES (?,?,?)',
                               (key, encoded(value) + b'\n', csv_bytes(value)))
            connection.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data, allow_nan=False), key))
        return data

    def prediction_export(self, key, kind):
        if kind not in ('json', 'csv'):
            raise KeyError('Export not found.')
        with self.connect() as connection:
            job = connection.execute('SELECT data FROM jobs WHERE id=?', (key,)).fetchone()
            if job is None:
                raise KeyError('Run not found.')
            row = connection.execute('SELECT json_bytes,csv_bytes FROM prediction_exports WHERE job_id=?', (key,)).fetchone()
        if row is None:
            raise ConflictError(json.loads(job['data']).get('export_error') or 'Wait for this run to finish before downloading its prediction.')
        return bytes(row[kind + '_bytes'])

    def retry(self, key, request_id=None, *, with_created=False):
        request_key, fingerprint = self._request({'request_id': request_id}, key)
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            cached = self._cached(connection, request_key, fingerprint)
            if cached is not None:
                return (cached, False) if with_created else cached
            row = connection.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
            if row is None:
                raise KeyError('Run not found.')
            job = json.loads(row['data'])
            if job['status'] in ('queued', 'running'):
                raise ValueError('Wait for this run to finish before retrying.')
            # Grouped retries retain the same views and catalogue; standalone retries use current material.
            grouped = job.get('view_count', 1) > 1
            jobs = [self._insert_job(connection, row['media_id'], job['filename'],
                    json.loads(row['snapshot']) if grouped else self._snapshot(connection), job['expected_product_id'],
                    views=self._views(connection, row) if grouped else None,
                    parent_job_id=job.get('parent_job_id'), root_job_id=job.get('root_job_id'))]
            self._save_request(connection, request_key, fingerprint, jobs)
            return (jobs, True) if with_created else jobs

    def claim_job(self, key):
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
            if row is None:
                raise KeyError('Run not found.')
            job = json.loads(row['data'])
            if job['status'] != 'queued':
                return None
            job.update(status='running', stage='Preparing manufacturer references', started_at=now(),
                       run_details={'pipeline_version': PIPELINE_VERSION})
            connection.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(job), key))
            job['_snapshot'], job['_media_id'] = json.loads(row['snapshot']), row['media_id']
            job['_views'] = self._views(connection, row)
            return job

    def interrupt_unfinished(self):
        for job in self.jobs():
            if job['status'] in ('queued', 'running'):
                self.update_job(job['id'], status='interrupted', stage='Run interrupted',
                                completed_at=now(),
                                error='The app restarted before this run finished. Start a deliberate retry to run it again.')
