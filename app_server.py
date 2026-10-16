#!/usr/bin/env python3
"""Loopback-only local app, SQLite catalogue and one paid OpenRouter worker."""
import argparse
import fcntl
import hmac
import hashlib
import base64
import json
import queue
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from webapp.store import Store, ID, ConflictError
from webapp.inference import Inference, BudgetError, settings, ledger_accounting, api_configured, api_key_for

ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 65 * 1024 * 1024
EVALUATION_SUMMARY = {'singles': 57, 'correct': 37, 'confidently_wrong': 5, 'unsure': 15, 'multi_photo_count': 1}


class App:
    def __init__(self, root=ROOT, data_dir=None, *, start_worker=True, inference_factory=Inference):
        self.root = Path(root).resolve()
        self.runtime = self.root / 'var'
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_file = (self.runtime / 'worker.lock').open('a+')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            raise RuntimeError('Another local app is already running for this repository.') from None
        self.ledger_root = self.runtime / 'runtime'
        self.ledger_root.mkdir(exist_ok=True, mode=0o700)
        try:
            self.store = Store(self.root, data_dir or self.runtime)
            self.store.interrupt_unfinished()
            for job in self.store.jobs():
                cost = ledger_accounting(self.ledger_root)['per_job'].get(job['id'], 0.0)
                if cost != job['cost_inr']:
                    self.store.update_job(job['id'], cost_inr=cost)
            self.engine = inference_factory(self.root, self.ledger_root, self.store)
        except Exception:
            self.lock_file.close()
            raise
        self.csrf_token = secrets.token_urlsafe(32)
        self.queue = queue.Queue()
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self._work, name='openrouter-single-worker', daemon=True)
        if start_worker:
            self.worker.start()

    def close(self):
        self.stop.set()
        self.queue.put(None)
        if self.worker.is_alive():
            self.worker.join(timeout=1)
        # Keep the process lock during an active network request, even after the HTTP listener closes.
        if not self.worker.is_alive():
            self.lock_file.close()

    def _cost(self, key):
        return ledger_accounting(self.ledger_root)['per_job'].get(key, 0.0)

    def _work(self):
        try:
            while not self.stop.is_set():
                key = self.queue.get()
                if key is None or self.stop.is_set():
                    return
                self.process_job(key)
        finally:
            if self.stop.is_set():
                self.lock_file.close()

    def process_job(self, key):
        job = self.store.claim_job(key)
        if job is None:
            return
        try:
            matches = self.engine.run(job, lambda stage: self.store.update_job(key, stage=stage, cost_inr=self._cost(key)))
            self.store.update_job(key, status='completed', stage='Complete', matches=matches, cost_inr=self._cost(key), error=None)
        except Exception as error:
            diagnostic = str(error)[:6000]
            try:
                diagnostic = diagnostic.replace(api_key_for('OPENROUTER_API_KEY'), '[REDACTED]')
            except Exception:
                pass
            folder = self.ledger_root / key
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            (folder / 'error.json').write_text(json.dumps({'type': type(error).__name__, 'message': diagnostic}))
            if isinstance(error, BudgetError):
                message = 'The remaining spending allowance cannot cover another request. This upload and any charges were kept.'
            elif isinstance(error, ValueError):
                message = 'The result could not be validated. This upload and any charges were kept. Retry as a new run if needed.'
            else:
                message = 'The model request failed. This upload and any charges were kept. Retry as a new run if needed.'
            self.store.update_job(key, status='failed', stage='Run stopped', error=message, cost_inr=self._cost(key))

    def enqueue(self, jobs, created=True):
        if created:
            for job in jobs:
                self.queue.put(job['id'])
        return {'jobs': jobs}

    def bootstrap(self):
        return {'csrf_token': self.csrf_token, 'catalogue': self.store.products(), 'jobs': self.store.jobs(),
                'settings': settings(self.ledger_root), 'evaluation': EVALUATION_SUMMARY}

    def evaluation(self):
        manifest = json.loads((self.root / 'data/test/test_manifest.json').read_text())
        scoreboard = json.loads((self.root / 'out/pipeline_v2_recovery/scoreboard.json').read_text())['all_photos']['groups'][0]
        outcomes = {row['image_id']: row for row in scoreboard['per_photo']}
        saved = json.loads((self.root / 'out/pipeline_v2_full/results.json').read_text())
        detections = json.loads((self.root / 'out/pipeline_v2_full/detections.json').read_text())
        original_cards = json.loads((self.root / 'data/reference_cards_v2.json').read_text())['products']
        original_images = {product['id']: product['images'][:len(original_cards[product['id']]['images'])] for product in self.store.products() if product['id'] in original_cards}
        media = {key: images[0]['url'] if images else None for key, images in original_images.items()}
        photos = []
        for photo in manifest:
            key = photo['image_id']
            matches = []
            for row in saved:
                if row['image_id'] != key or row['variant'] != 'evidence_final':
                    continue
                decision = row['decision']
                product_id = decision['product']
                product = original_cards.get(product_id)
                status = decision['status'].replace('not_in_catalogue', 'not_in_catalog')
                target = next((target for target in detections.get(key, []) if target['object_id'] == row['object_id']), {})
                matches.append({'object_id': row['object_id'], 'box_2d': target.get('box_2d'), 'status': status,
                    'product_id': product_id, 'product_name': product['name'] if product else None,
                    'confidence': 'High' if status != 'not_sure' and decision.get('confidence', 0) >= 90 else 'Low',
                    'evidence': decision['evidence'], 'missing_evidence': decision['missing_evidence'],
                    'alternatives': [{'id': candidate, 'name': original_cards[candidate]['name']} for candidate in decision['top_two'] if candidate in original_cards],
                    'reference_image_url': media.get(product_id), 'verification': None,
                    'reference_images': original_images.get(product_id, []),
                    'source_url': product['sources'][0]['url'] if product else None})
            result = outcomes.get(key)
            outcome = 'multi_photo' if photo.get('evaluation_role') == 'labelled_multi' else 'unsure' if result and result['status'] == 'not_sure' else 'correct' if result and result.get('correct') else 'wrong'
            photos.append({'id': key, 'filename': key + Path(photo['file']).suffix,
                           'image_url': '/media/eval-' + key, 'source_title': photo['source_title'],
                           'source_url': photo['source_url'], 'source_labels': photo.get('labels', []),
                           'outcome': outcome, 'matches': matches})
        summary = {'original': EVALUATION_SUMMARY,
                   'selected_failure_wave': {'selected_failures': 20, 'correct': 6, 'confidently_wrong': 1, 'unsure': 13, 'controls': 3},
                   'multi_photo_scope': 'Photo identity set only; the source does not assign model identity to a box.'}
        return {'summary': summary, 'photos': photos}

    def media(self, key):
        if re.fullmatch(r'eval-P[0-9]{3}', key):
            wanted = key[5:]
            manifest = json.loads((self.root / 'data/test/test_manifest.json').read_text())
            photo = next((row for row in manifest if row['image_id'] == wanted), None)
            if not photo:
                raise KeyError('Image not found.')
            path = (self.root / photo['file']).resolve()
            if not path.is_relative_to(self.root / 'data/test/review_photos') or not path.is_file():
                raise KeyError('Image not found.')
            mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}.get(path.suffix.lower())
            if not mime:
                raise KeyError('Image not found.')
            return path, mime, wanted + path.suffix
        return self.store.media(key)


def build_app(root=ROOT, data_dir=None, **options):
    return App(root, data_dir, **options)


class Handler(BaseHTTPRequestHandler):
    server_version = 'DysonLocal/1'

    def log_message(self, format, *args):
        # Uploaded names, query strings and errors never enter access logs.
        return

    @property
    def app(self):
        return self.server.app

    def _security(self, mutate=False):
        port = self.server.server_address[1]
        host = self.headers.get('Host', '')
        valid_hosts = {'127.0.0.1:' + str(port), 'localhost:' + str(port)}
        if port == 80:
            valid_hosts |= {'127.0.0.1', 'localhost'}
        if host not in valid_hosts:
            self.send_json(403, {'error': 'Open this app through its local address.'})
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin != 'http://' + host:
            self.send_json(403, {'error': 'Use the app from the same local browser address.'})
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send_json(403, {'error': 'Cross-site requests are not allowed.'})
            return False
        if mutate and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), self.app.csrf_token):
            self.send_json(403, {'error': 'Refresh this page before submitting changes.'})
            return False
        return True

    def _headers(self, status, mime, size, script_hashes=()):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(size))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        scripts = ' '.join(["'self'", *script_hashes])
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src " + scripts + "; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")

    def send_json(self, status, data):
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self._headers(status, 'application/json; charset=utf-8', len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def file(self, path, mime, name=None):
        if not path.is_file():
            raise KeyError('File not found.')
        content = path.read_bytes()
        hashes = []
        if path == self.app.root / 'web/report.html':
            for script in re.findall(rb'<script(?:\s[^>]*)?>(.*?)</script>', content, re.DOTALL):
                hashes.append("'sha256-" + base64.b64encode(hashlib.sha256(script).digest()).decode() + "'")
        self._headers(200, mime, len(content), hashes)
        if name and mime == 'application/pdf':
            self.send_header('Content-Disposition', 'inline; filename="brochure.pdf"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if not self._security():
            return
        try:
            path = urlsplit(self.path).path
            if unquote(path) != path:
                raise KeyError('Page not found.')
            if path == '/api/bootstrap':
                self.send_json(200, self.app.bootstrap())
            elif path == '/api/catalogue':
                self.send_json(200, {'products': self.app.store.products()})
            elif re.fullmatch(r'/api/catalogue/[A-Za-z0-9_-]{1,80}', path):
                self.send_json(200, self.app.store.product(path.rsplit('/', 1)[1]))
            elif path == '/api/jobs':
                self.send_json(200, {'jobs': self.app.store.jobs()})
            elif re.fullmatch(r'/api/jobs/[A-Za-z0-9_-]{1,80}', path):
                self.send_json(200, self.app.store.job(path.rsplit('/', 1)[1]))
            elif path == '/api/evaluation':
                self.send_json(200, self.app.evaluation())
            elif re.fullmatch(r'/media/[A-Za-z0-9_-]{1,80}', path):
                self.file(*self.app.media(path.rsplit('/', 1)[1]))
            elif path in ('/', '/web/index.html', '/web/app.js', '/web/style.css', '/report'):
                filename = 'report.html' if path == '/report' else 'index.html' if path == '/' else path.rsplit('/', 1)[1]
                mime = {'html': 'text/html; charset=utf-8', 'css': 'text/css; charset=utf-8', 'js': 'text/javascript; charset=utf-8'}[filename.rsplit('.', 1)[1]]
                self.file(self.app.root / 'web' / filename, mime)
            elif path == '/favicon.ico':
                self._headers(204, 'image/x-icon', 0)
                self.end_headers()
            else:
                raise KeyError('Page not found.')
        except KeyError:
            self.send_json(404, {'error': 'The requested item was not found.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_json(500, {'error': 'The saved data could not be read. Check the local app before continuing.'})

    def _body(self):
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip() != 'application/json':
            raise ValueError('Send this request as JSON.')
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked uploads are not supported.')
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            raise ValueError('A valid request length is required.') from None
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError('Upload requests must be 65 MiB or smaller.')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('The upload ended before the whole request arrived.')
        try:
            return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid number')))
        except (ValueError, UnicodeError):
            raise ValueError('The request contains invalid JSON.') from None

    def _mutate(self, method):
        if not self._security(mutate=True):
            return
        try:
            path = urlsplit(self.path).path
            body = self._body()
            if method == 'POST' and path == '/api/catalogue':
                self.send_json(201, self.app.store.edit_product(body))
            elif method == 'PATCH' and re.fullmatch(r'/api/catalogue/[A-Za-z0-9_-]{1,80}', path):
                self.send_json(200, self.app.store.edit_product(body, path.rsplit('/', 1)[1]))
            elif method == 'POST' and path == '/api/jobs':
                if not isinstance(body, dict) or not isinstance(body.get('request_id'), str) or not ID.fullmatch(body['request_id']):
                    raise ValueError('A request ID is required before running a photo.')
                cached = self.app.store.cached_jobs(body)
                if cached is not None:
                    self.send_json(202, {'jobs': cached})
                    return
                if not api_configured():
                    self.send_json(503, {'error': 'Add OPENROUTER_API_KEY to the local .env before running a photo.'})
                    return
                if settings(self.app.ledger_root)['runtime_remaining_inr'] <= 0:
                    self.send_json(409, {'error': 'The app spending limit has been reached.'})
                    return
                self.send_json(202, self.app.enqueue(*self.app.store.create_jobs(body, with_created=True)))
            elif method == 'POST' and re.fullmatch(r'/api/jobs/[A-Za-z0-9_-]{1,80}/retry', path):
                if not isinstance(body, dict) or set(body) != {'request_id'} or not isinstance(body['request_id'], str) or not ID.fullmatch(body['request_id']):
                    raise ValueError('A new request ID is required for a deliberate retry.')
                original_id = path.split('/')[3]
                cached = self.app.store.cached_jobs(body, original_id)
                if cached is not None:
                    self.send_json(202, {'jobs': cached})
                    return
                if not api_configured():
                    self.send_json(503, {'error': 'Add OPENROUTER_API_KEY to the local .env before retrying a photo.'})
                    return
                if settings(self.app.ledger_root)['runtime_remaining_inr'] <= 0:
                    self.send_json(409, {'error': 'The app spending limit has been reached.'})
                    return
                self.send_json(202, self.app.enqueue(*self.app.store.retry(original_id, body['request_id'], with_created=True)))
            else:
                self.send_json(404, {'error': 'The requested action was not found.'})
        except ConflictError as error:
            self.send_json(409, {'error': str(error)})
        except ValueError as error:
            self.send_json(400, {'error': str(error)})
        except KeyError:
            self.send_json(404, {'error': 'The requested item was not found.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_json(500, {'error': 'This change could not be saved. Check the local app before trying again.'})

    def do_POST(self):
        self._mutate('POST')

    def do_PATCH(self):
        self._mutate('PATCH')

    def do_OPTIONS(self):
        self.send_json(403, {'error': 'Cross-origin requests are not allowed.'})


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self):
        super().server_close()
        if hasattr(self, 'app'):
            self.app.close()


def make_server(app=None, port=8766, *, root=ROOT, data_dir=None, **options):
    created = app is None
    app = app or build_app(root, data_dir, **options)
    try:
        server = LocalServer(('127.0.0.1', port), Handler)
    except Exception:
        if created:
            app.close()
        raise
    server.app = app
    return server


def main():
    parser = argparse.ArgumentParser(description='Run the local Dyson matching app.')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    server = make_server(port=args.port, data_dir=args.data_dir)
    print('Local app: http://127.0.0.1:' + str(args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
