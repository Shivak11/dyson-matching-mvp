"""Offline storage, HTTP boundary and persisted queue checks."""
import base64
import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app_server
from webapp.store import Store, validate_upload

ROOT = Path(__file__).resolve().parents[1]


def image_file(name='store.png', color='white', exif=False):
    output = io.BytesIO()
    image = Image.new('RGB', (40, 60), color)
    if exif:
        tags = Image.Exif()
        tags[270] = 'private metadata'
        image.save(output, 'PNG', exif=tags)
    else:
        image.save(output, 'PNG')
    return {'filename': name, 'data_url': 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()}


def fixture_root(folder):
    root = Path(folder)
    seed = root / 'var/catalogue-seed'
    seed.mkdir(parents=True)
    ids = ('dyson_big_ball', 'dyson_v8_absolute', 'dyson_v12_detect_slim', 'dyson_v15_detect',
           'dyson_v16_piston_animal', 'dyson_washg1', 'dyson_v11', 'dyson_gen5detect', 'shark_stratos')
    cards = {'products': {}}
    for index, key in enumerate(ids):
        name = key + '.png'
        raw = base64.b64decode(image_file(name)['data_url'].split(',', 1)[1])
        (seed / name).write_bytes(raw)
        cards['products'][key] = {'name': key.replace('_', ' ').title(), 'in_catalog': index < 6,
            'images': [{'file': name, 'view': 'Manufacturer view'}],
            'sources': [{'url': 'https://manufacturer.example/' + key, 'supporting_passage': 'Manufacturer details for ' + key}],
            'visible_features': [], 'variant_limits': []}
    (seed / 'reference_cards.json').write_text(json.dumps(cards))
    model = {'model': 'google/gemini-3.7-flash', 'provider': 'openrouter', 'input_usd_per_million': .75,
        'output_usd_per_million': 3.75, 'cached_input_usd_per_million': .075, 'max_output_tokens': 32768,
        'input_token_bound': 28000, 'thinking_level': 'high', 'request_timeout_seconds': 480,
        'provider_only': ['google-ai-studio']}
    (root / 'runtime_config.json').write_text(json.dumps({'model': model}))
    (root / 'web').mkdir()
    (root / 'web/index.html').write_text('<html><body>Local test</body></html>')
    return root


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.store = Store(self.root, self.root / 'var')

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_persists_six_products_and_three_lookalikes(self):
        products = self.store.products()
        self.assertEqual(sum(product['in_catalog'] for product in products), 6)
        self.assertEqual(len(products), 9)
        first = products[0]
        self.store.edit_product({'name': 'Changed manufacturer name'}, first['id'])
        reopened = Store(self.root, self.root / 'var')
        self.assertEqual(reopened.product(first['id'])['name'], 'Changed manufacturer name')
        self.assertIn('brochure_details', first)
        self.assertNotIn('visible_features', first)

    def test_seed_preserves_original_manufacturer_document(self):
        with tempfile.TemporaryDirectory() as folder:
            root = fixture_root(folder)
            seed = root / 'var/catalogue-seed'
            raw = b'%PDF-1.4\nmanufacturer test document\n%%EOF\n'
            name = 'Dyson V8 user manual.pdf'
            (seed / name).write_bytes(raw)
            cards_path = seed / 'reference_cards.json'
            cards = json.loads(cards_path.read_text())
            cards['products']['dyson_v8_absolute']['brochure_file'] = name
            cards_path.write_text(json.dumps(cards))
            store = Store(root, root / 'var')
            product = store.product('dyson_v8_absolute')
            self.assertEqual(product['brochure_filename'], name)
            key = product['brochure_url'].rsplit('/', 1)[1]
            self.assertEqual(store.media(key)[0].read_bytes(), raw)

    def test_seed_rejects_document_path_outside_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = fixture_root(folder)
            cards_path = root / 'var/catalogue-seed/reference_cards.json'
            cards = json.loads(cards_path.read_text())
            cards['products']['dyson_v8_absolute']['brochure_file'] = '../outside.pdf'
            cards_path.write_text(json.dumps(cards))
            with self.assertRaisesRegex(ValueError, 'document path'):
                Store(root, root / 'var')

    def test_snapshot_is_fixed_when_catalogue_changes(self):
        job = self.store.create_jobs({'images': [image_file()], 'expected_product_id': 'dyson_v15_detect'})[0]
        snapshot = self.store.job(job['id'], internal=True)['_snapshot']
        old = next(row for row in snapshot if row['id'] == 'dyson_v15_detect')['brochure_details']
        self.store.edit_product({'brochure_details': 'Additional manufacturer passage'}, 'dyson_v15_detect')
        stored = self.store.job(job['id'], internal=True)
        self.assertEqual(next(row for row in stored['_snapshot'] if row['id'] == 'dyson_v15_detect')['brochure_details'], old)
        self.assertEqual(job['mode'], 'verify')
        self.assertFalse(any(key.startswith('_') for key in self.store.job(job['id'])))

    def test_invalid_batch_creates_no_jobs_or_media(self):
        with self.store.connect() as connection:
            before = connection.execute('SELECT COUNT(*) FROM media').fetchone()[0]
        bad = {'filename': 'broken.png', 'data_url': 'data:image/png;base64,YmFk'}
        with self.assertRaises(ValueError):
            self.store.create_jobs({'images': [image_file(), bad]})
        self.assertEqual(self.store.jobs(), [])
        with self.store.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM media').fetchone()[0], before)

    def test_original_preserved_provider_view_has_no_exif(self):
        item = image_file(exif=True)
        job = self.store.create_jobs({'images': [item]})[0]
        key = self.store.job(job['id'], internal=True)['_media_id']
        original = self.store.media(key)[0]
        self.assertEqual(original.read_bytes(), base64.b64decode(item['data_url'].split(',', 1)[1]))
        with Image.open(self.store.media(key, provider=True)[0]) as image:
            self.assertFalse(image.getexif())
            self.assertEqual(image.mode, 'RGB')

    def test_upload_validation_blocks_paths_types_limits(self):
        for name in ('../private.png', 'folder\\private.png', 'bad\nname.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_upload(image_file(name))
        wrong = image_file()
        wrong['data_url'] = wrong['data_url'].replace('image/png', 'image/jpeg')
        with self.assertRaises(ValueError):
            validate_upload(wrong)
        with patch('webapp.store.MAX_PIXELS', 2000), self.assertRaises(ValueError):
            validate_upload(image_file())
        with self.assertRaises(ValueError):
            self.store.create_jobs({'images': [image_file()], 'expected_product_id': 'shark_stratos'})
        with self.assertRaises(KeyError):
            self.store.media('../../.env')

    def test_product_add_append_and_optional_pdf(self):
        pdf = b'%PDF-1.4\noriginal manufacturer document\n%%EOF\n'
        product = self.store.edit_product({'name': 'Manufacturer product', 'manufacturer': 'Manufacturer',
                    'source_url': 'https://manufacturer.example/product', 'brochure_details': 'Manufacturer specification.',
                    'images': [image_file('official.png')], 'brochure': {'filename': 'brochure.pdf',
                    'data_url': 'data:application/pdf;base64,' + base64.b64encode(pdf).decode()}})
        changed = self.store.edit_product({'images': [image_file('extra.png')]}, product['id'])
        self.assertEqual(len(changed['images']), 2)
        self.assertEqual(changed['image_url'], product['image_url'])
        key = product['brochure_url'].split('/')[-1]
        self.assertEqual(self.store.media(key)[0].read_bytes(), pdf)
        self.assertTrue(product['in_catalog'])
        with self.assertRaises(ValueError):
            self.store.edit_product({'source_url': 'javascript:alert(1)'}, product['id'])

    def test_request_id_persists_and_conflicts_on_changed_payload(self):
        payload = {'images': [image_file()], 'request_id': 'persistent-request'}
        first, created = self.store.create_jobs(payload, with_created=True)
        self.assertTrue(created)
        reopened = Store(self.root, self.root / 'var')
        second, created = reopened.create_jobs(payload, with_created=True)
        self.assertFalse(created)
        self.assertEqual(first[0]['id'], second[0]['id'])
        changed = {'images': [image_file('other-name.png')], 'request_id': 'persistent-request'}
        with self.assertRaises(ValueError):
            reopened.create_jobs(changed)
        self.assertEqual(len(reopened.jobs()), 1)

    def test_retry_retains_old_history_and_new_snapshot(self):
        first = self.store.create_jobs({'images': [image_file()]})[0]
        with self.assertRaises(ValueError):
            self.store.retry(first['id'])
        self.store.update_job(first['id'], status='failed', error='Request failed', cost_inr=2.0)
        self.store.edit_product({'name': 'Changed name'}, 'dyson_v15_detect')
        second = self.store.retry(first['id'])[0]
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['image_url'], second['image_url'])
        self.assertEqual(self.store.job(first['id'])['cost_inr'], 2.0)
        self.assertEqual(len(self.store.jobs()), 2)


class FakeEngine:
    def __init__(self, *args):
        self.count = 0

    def run(self, job, stage):
        self.count += 1
        stage('Comparing manufacturer references')
        if self.count == 1:
            raise RuntimeError('private key must never leave the backend')
        return []


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_failure_does_not_disable_later_jobs_or_expose_errors(self):
        jobs = self.app.store.create_jobs({'images': [image_file('one.png'), image_file('two.png')]})
        for job in jobs:
            self.app.process_job(job['id'])
        self.assertEqual(self.app.store.job(jobs[0]['id'])['status'], 'failed')
        self.assertNotIn('private key', self.app.store.job(jobs[0]['id'])['error'])
        self.assertEqual(self.app.store.job(jobs[1]['id'])['status'], 'completed')

    def test_restart_interrupts_without_automatic_paid_resume(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        self.app.close()
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)
        self.assertEqual(self.app.store.job(job['id'])['status'], 'interrupted')
        self.assertTrue(self.app.queue.empty())
        self.assertEqual(self.app.engine.count, 0)

    def test_duplicate_queued_key_does_not_execute_again(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        self.app.process_job(job['id'])
        self.app.process_job(job['id'])
        self.assertEqual(self.app.engine.count, 1)
        self.assertEqual(self.app.store.job(job['id'])['status'], 'failed')
        diagnostic = json.loads((self.app.ledger_root / job['id'] / 'error.json').read_text())
        self.assertEqual(diagnostic['type'], 'RuntimeError')

    def test_public_job_includes_current_inflight_reservation(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        folder = self.app.ledger_root / job['id']
        folder.mkdir()
        (folder / 'inflight.json').write_text(json.dumps({'active-request': {'reserved_cost_usd': .25}}))
        self.assertEqual(self.app.store.job(job['id'])['cost_inr'], 0)
        self.assertEqual(self.app.public_jobs(job['id'])[0]['cost_inr'], 25)
        self.assertEqual(self.app.bootstrap()['jobs'][0]['cost_inr'], 25)


    def test_process_lock_prevents_two_workers_even_with_other_data_dir(self):
        with self.assertRaises(RuntimeError):
            app_server.build_app(self.root, self.root / 'other-data', start_worker=False)


class HTTPFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)
        self.server = app_server.make_server(self.app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, method=None, headers=None):
        values = {'Content-Type': 'application/json', **(headers or {})}
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                                         method=method, headers=values)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.headers, error.read()

class HTTPTests(HTTPFixture, unittest.TestCase):
    def test_bootstrap_host_origin_and_csrf(self):
        code, headers, raw = self.request('/api/bootstrap')
        data = json.loads(raw)
        self.assertEqual(code, 200)
        self.assertEqual(len(data['catalogue']), 9)
        self.assertEqual(data['settings']['runtime_remaining_inr'], 300)
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.request('/api/bootstrap', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/bootstrap', headers={'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/jobs', {'images': [image_file()]})[0], 403)
        self.assertEqual(self.request('/api/jobs', {'images': [image_file()]}, headers={
            'X-CSRF-Token': data['csrf_token'], 'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_catalogue_job_and_media_routes(self):
        token = json.loads(self.request('/api/bootstrap')[2])['csrf_token']
        headers = {'X-CSRF-Token': token, 'Origin': self.base}
        with patch('app_server.api_configured', return_value=True):
            code, _, raw = self.request('/api/jobs', {'images': [image_file()], 'request_id': 'upload-one'}, headers=headers)
        self.assertEqual(code, 202)
        job = json.loads(raw)['jobs'][0]
        self.assertEqual(self.request(job['image_url'])[0], 200)
        self.assertEqual(json.loads(self.request('/api/jobs/' + job['id'])[2])['status'], 'queued')
        self.assertEqual(self.request('/api/catalogue/dyson_v15_detect', {'name': 'New name'}, method='PATCH', headers=headers)[0], 200)
        for path in ('/.env', '/media/../../.env', '/media/%2e%2e', '/web/../.env', '/media/unknown'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/report')[0], 404)

    def test_idempotent_upload_and_retry_do_not_duplicate_paid_queue_entries(self):
        headers = {'X-CSRF-Token': self.app.csrf_token}
        payload = {'images': [image_file()], 'request_id': 'same-upload'}
        with patch('app_server.api_configured', return_value=True):
            first = json.loads(self.request('/api/jobs', payload, headers=headers)[2])['jobs'][0]
            repeated = json.loads(self.request('/api/jobs', payload, headers=headers)[2])['jobs'][0]
            self.assertEqual(first['id'], repeated['id'])
            self.assertEqual(self.app.queue.qsize(), 1)
            changed = {'images': [image_file('changed.png')], 'request_id': 'same-upload'}
            self.assertEqual(self.request('/api/jobs', changed, headers=headers)[0], 409)
            self.app.process_job(first['id'])
            self.app.process_job(first['id'])
            self.assertEqual(self.app.engine.count, 1)
            retry_path = '/api/jobs/' + first['id'] + '/retry'
            retry_body = {'request_id': 'same-retry'}
            retry = json.loads(self.request(retry_path, retry_body, headers=headers)[2])['jobs'][0]
            retry_again = json.loads(self.request(retry_path, retry_body, headers=headers)[2])['jobs'][0]
            self.assertEqual(retry['id'], retry_again['id'])
            self.assertEqual(self.app.queue.qsize(), 2)
            self.assertEqual(len(self.app.store.jobs()), 2)


    def test_invalid_batch_and_retry_while_queued(self):
        headers = {'X-CSRF-Token': self.app.csrf_token}
        with patch('app_server.api_configured', return_value=True):
            bad = {'filename': 'bad.png', 'data_url': 'data:image/png;base64,YmFk'}
            self.assertEqual(self.request('/api/jobs', {'images': [image_file(), bad], 'request_id': 'upload-bad'}, headers=headers)[0], 400)
            self.assertFalse(self.app.store.jobs())
            raw = self.request('/api/jobs', {'images': [image_file()], 'request_id': 'upload-one'}, headers=headers)[2]
            job = json.loads(raw)['jobs'][0]
            self.assertEqual(self.request('/api/jobs/' + job['id'] + '/retry', {'request_id': 'retry-one'}, headers=headers)[0], 400)


if __name__ == '__main__':
    unittest.main()
