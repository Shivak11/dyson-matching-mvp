"""Offline isolation, frozen-protocol parity and immutable download checks."""
import ast
import copy
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_server
from test_webapp import FakeEngine, HTTPFixture, fixture_root, image_file
from test_webapp_inference import FakeClient, response, target
from webapp import inference, protocol, transport
from webapp.predictions import collect_run_details
from webapp.store import ConflictError, Store

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'ed4eb5f91a466d8d495af87ee0dbedfa788762c4'


def node(source, name, owner=None):
    tree = ast.parse(source)
    body = next(item.body for item in tree.body if isinstance(item, ast.ClassDef) and item.name == owner) if owner else tree.body
    return next(item for item in body if (getattr(item, 'name', None) == name or
                isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name) and item.targets[0].id == name))


def old_source(path):
    return subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT, text=True)


def compiled_function(source, name, namespace, owner=None):
    module = ast.Module(body=[copy.deepcopy(node(source, name, owner))], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<frozen-development-source>', 'exec'), namespace)
    return namespace[name]


class ProtocolParityTests(unittest.TestCase):
    def test_extracted_prompts_and_gates_keep_source_bytes(self):
        current = (ROOT / 'webapp/protocol.py').read_text()
        mappings = {'tools/run_pipeline.py': ('pixel_box', 'validate_result', 'gate_decision'),
                    'tools/evidence_v2.py': ('OBSERVE_PROMPT', 'RESULT_FORMAT', '_box', 'validate_observation',
                                             'validate_match_result', 'needs_refinement'),
                    'tools/failure_protocol.py': ('inventory_prompt', 'validate_inventory')}
        for path, names in mappings.items():
            original = old_source(path)
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(ast.get_source_segment(current, node(current, name)),
                                     ast.get_source_segment(original, node(original, name)))
        original = old_source('webapp/inference.py')
        current = (ROOT / 'webapp/inference.py').read_text()
        for name, owner in [('catalogue_projection', None), ('comparison_prompt', None), ('valid_box', None),
                            ('validate_batch', None), ('_references', 'Inference'), ('run', 'Inference')]:
            with self.subTest(name=name):
                self.assertEqual(ast.get_source_segment(current, node(current, name, owner)),
                                 ast.get_source_segment(original, node(original, name, owner)))
        original = old_source('webapp/store.py')
        current = (ROOT / 'webapp/store.py').read_text()
        self.assertEqual(ast.get_source_segment(current, node(current, 'validate_upload')),
                         ast.get_source_segment(original, node(original, 'validate_upload')))

    def test_openrouter_payload_reservation_and_pacing_code_are_unchanged(self):
        original = old_source('tools/pipeline_api.py')
        current = (ROOT / 'webapp/transport.py').read_text()
        for name in ('_call', '_atomic_json', '_append', '_index_record', '_is_rate_limit', '_recoverable',
                     '_refresh_failure', '_wait', '_retry_delay', '_retry_after', 'record_validation_failure'):
            self.assertEqual(ast.dump(node(current, name, 'Client'), include_attributes=False),
                             ast.dump(node(original, name, 'Client'), include_attributes=False), name)
        with tempfile.TemporaryDirectory() as folder:
            root = fixture_root(folder)
            model = json.loads((root / 'runtime_config.json').read_text())['model']
            model['input_token_bound'] = 128000
            calls = []

            class Capture:
                config = {'models': {'flash37high': model}}

                def _call(self, *args):
                    calls.append(args[:-1])

            legacy = compiled_function(original, 'generate', dict(vars(transport)), 'Client')
            image = root / 'var/catalogue-seed/dyson_big_ball.png'
            legacy(Capture(), 'run:stage', 'flash37high', protocol.inventory_prompt(), [('Fresh scene', image)])
            transport.Client.generate(Capture(), 'run:stage', 'flash37high', protocol.inventory_prompt(), [('Fresh scene', image)])
            self.assertEqual(calls[0], calls[1])
            self.assertEqual(calls[1][4], 'https://openrouter.ai/api/v1/chat/completions')
            self.assertEqual(calls[1][3]['provider']['only'], ['google-ai-studio'])

    def test_original_and_extracted_fresh_runs_have_identical_requests_and_images(self):
        original = old_source('webapp/inference.py')
        old_run = compiled_function(original, 'run', dict(vars(inference)), 'Inference')
        with tempfile.TemporaryDirectory() as folder:
            root = fixture_root(folder)
            store = Store(root, root / 'var')
            created = store.create_jobs({'images': [image_file()], 'expected_product_id': 'dyson_v15_detect'})[0]
            job = store.job(created['id'], internal=True)
            snapshot = job['_snapshot']
            machine2 = dict(target(), object_id='o2', box_2d=[500, 500, 1000, 1000])
            machine2['observations'] = [dict(target()['observations'][0], box_2d=[600, 600, 700, 700])]
            multiple = response(snapshot)
            multiple['results'].append(copy.deepcopy(multiple['results'][0]))
            multiple['results'][1]['object_id'] = 'o2'
            for check in multiple['results'][1]['result']['feature_checks']:
                check['query_box_2d'] = [600, 600, 700, 700]
            multiple['results'][1]['result']['decisive_region'] = [600, 600, 700, 700]
            for script in ([{'objects': [target()]}, response(snapshot)],
                           [{'objects': [target()]}, response(snapshot, status='not_sure'), response(snapshot)],
                           [{'objects': [target(), machine2]}, multiple]):
                captured = []

                class CaptureClient(FakeClient):
                    def generate(self, job_id, model, prompt, images):
                        captured.append({'model': model, 'prompt': prompt,
                                         'images': [(label, hashlib.sha256(path.read_bytes()).hexdigest()) for label, path in images]})
                        return copy.deepcopy(self.responses.pop(0))

                def factory(*args, **kwargs):
                    client = CaptureClient(*args, **kwargs)
                    client.responses = copy.deepcopy(script)
                    return client

                engine = inference.Inference(root, root / 'var/runtime', store, factory)
                old_matches = old_run(engine, job, lambda stage: None)
                old_requests = copy.deepcopy(captured)
                captured.clear()
                new_matches = engine.run(job, lambda stage: None)
                self.assertEqual(old_requests, captured)
                self.assertEqual(old_matches, new_matches)
                self.assertEqual(engine._client(job['id']).config['models']['flash37high']['input_token_bound'], 128000)


class PrivatePredictionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def job(self, name='fresh.png', expected=None):
        return self.app.store.create_jobs({'images': [image_file(name)], 'expected_product_id': expected})[0]

    def completed(self, name='fresh.png', expected=None):
        job = self.job(name, expected)
        self.app.engine.count = 1
        self.app.process_job(job['id'])
        return self.app.store.job(job['id'])

    def test_terminal_bytes_are_stable_after_catalogue_config_and_restart(self):
        job = self.completed(expected='dyson_v15_detect')
        before = {kind: self.app.store.prediction_export(job['id'], kind) for kind in ('json', 'csv')}
        saved = json.loads(before['json'])
        self.assertEqual(saved['schema_version'], 1)
        self.assertEqual(saved['mode'], 'verify')
        self.assertEqual(saved['claimed_product']['id'], 'dyson_v15_detect')
        self.assertEqual(saved['photograph']['sha256'], hashlib.sha256(base64_bytes(image_file())).hexdigest())
        self.assertEqual(len(list(csv.DictReader(io.StringIO(before['csv'].decode())))), 1)
        self.app.store.edit_product({'name': 'Edited later'}, 'dyson_v15_detect')
        (self.root / 'runtime_config.json').write_text('{"model":{"model":"changed-later"}}')
        self.app.close()
        shutil.rmtree(self.root / 'var/catalogue-seed')
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)
        for kind, content in before.items():
            self.assertEqual(self.app.store.prediction_export(job['id'], kind), content)
        self.assertEqual(self.app.engine.count, 0)

    def test_terminal_statuses_seal_and_retry_uses_a_separate_record(self):
        failed = self.job()
        self.app.process_job(failed['id'])
        before = self.app.store.prediction_export(failed['id'], 'json')
        retry = self.app.store.retry(failed['id'], 'new-explicit-retry')[0]
        self.assertNotEqual(retry['id'], failed['id'])
        self.assertFalse(retry['exports_available'])
        self.assertEqual(self.app.store.prediction_export(failed['id'], 'json'), before)
        self.app.close()
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)
        interrupted = self.app.public_jobs(retry['id'])[0]
        self.assertEqual(interrupted['status'], 'interrupted')
        self.assertTrue(interrupted['exports_available'])
        self.assertIsNone(interrupted['run_details']['started_at'])
        self.assertIsNone(interrupted['run_details']['elapsed_seconds'])

    def test_pending_and_unknown_exports_do_not_run_or_create_predictions(self):
        pending = self.job()
        with self.assertRaises(ConflictError):
            self.app.store.prediction_export(pending['id'], 'json')
        with self.assertRaises(KeyError):
            self.app.store.prediction_export('unknown', 'json')
        self.assertEqual(self.app.engine.count, 0)
        self.assertIsNone(self.app.store.job(pending['id'])['run_details'])

    def test_recorded_timing_and_queue_are_saved_separately(self):
        job = self.completed()
        details = job['run_details']
        self.assertEqual(details['pipeline_version'], 'fresh-photo-v1')
        self.assertIsNotNone(details['started_at'])
        self.assertIsNotNone(details['completed_at'])
        self.assertGreaterEqual(details['elapsed_seconds'], 0)
        self.assertGreaterEqual(details['queued_seconds'], 0)
        self.assertEqual(details['requests'], [])

    def test_whitelisted_ledger_distinguishes_actual_requested_and_reserved(self):
        job = self.job()
        folder = self.app.ledger_root / job['id']
        folder.mkdir()
        frozen = {'models': {'flash37high': json.loads((self.root / 'runtime_config.json').read_text())['model']}}
        (folder / 'frozen_config.json').write_text(json.dumps(frozen))
        calls = [dict(job_id='one', operation='generate', status='ok', model_version='google/gemini-3.7-flash-actual',
                      provider='Google AI Studio', elapsed_seconds=1.5, estimated_cost_usd=.01, reserved_cost_usd=.05,
                      cost_basis='provider_reported_cost', provider_response={'secret': 'PRIVATE_RESPONSE'},
                      headers={'Authorization': 'PRIVATE_HEADER'}, error='/private/server/SECRET_PATH', prompt='PRIVATE_PROMPT'),
                 dict(job_id='two', operation='generate', status='error', estimated_cost_usd=.02, reserved_cost_usd=.02,
                      cost_basis='reserved_upper_bound_usage_unavailable'),
                 dict(job_id='one', status='validation_error', estimated_cost_usd=0)]
        (folder / 'calls.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in calls))
        (folder / 'inflight.json').write_text(json.dumps({'one': {'reserved_cost_usd': .05}, 'unknown': {'reserved_cost_usd': .03}}))
        stored = self.app.store.job(job['id'], internal=True)
        details = collect_run_details(stored, stored['_snapshot'], folder, 6)
        self.assertEqual(details['requested_provider'], 'google-ai-studio')
        self.assertEqual(details['requested_model'], 'google/gemini-3.7-flash')
        self.assertEqual(len(details['requests']), 3)
        self.assertEqual(details['requests'][0]['model'], 'google/gemini-3.7-flash-actual')
        self.assertEqual(details['requests'][0]['provider'], 'Google AI Studio')
        self.assertEqual(details['requests'][0]['cost_usd'], .01)
        self.assertIsNone(details['requests'][1]['cost_usd'])
        self.assertIsNone(details['requests'][2]['cost_usd'])
        self.assertEqual(details['requests'][2]['reserved_cost_usd'], .03)
        self.assertEqual(inference.ledger_accounting(self.app.ledger_root)['spent_inr'], 6)
        serialized = json.dumps(details)
        for forbidden in ('PRIVATE_', 'SECRET_PATH', 'provider_response', 'Authorization', 'headers', 'prompt', str(self.root)):
            self.assertNotIn(forbidden, serialized)

    def test_legacy_jobs_reconstruct_only_their_own_material(self):
        job = self.job()
        with self.app.store.connect() as connection:
            data = dict(job, status='completed')
            data.pop('run_details')
            data.pop('exports_available')
            connection.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), job['id']))
        (self.root / 'runtime_config.json').write_text('{"model":{"model":"CURRENT_CONFIG_MUST_NOT_APPEAR"}}')
        public = self.app.public_jobs(job['id'])[0]
        self.assertTrue(public['exports_available'])
        self.assertEqual(public['run_details']['pipeline_version'], 'legacy-local-app')
        self.assertIsNone(public['run_details']['config_sha256'])
        self.assertIsNone(public['run_details']['requested_model'])
        self.assertIsNone(public['run_details']['elapsed_seconds'])
        self.assertNotIn('CURRENT_CONFIG_MUST_NOT_APPEAR', self.app.store.prediction_export(job['id'], 'json').decode())

    def test_saved_legacy_charge_is_retained_when_its_ledger_is_unavailable(self):
        job = self.job()
        self.app.store.update_job(job['id'], status='completed', cost_inr=2.5)
        self.app.close()
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)
        saved = self.app.public_jobs(job['id'])[0]
        self.assertEqual(saved['cost_inr'], 2.5)
        self.assertEqual(saved['run_details']['cost_basis'], 'saved_job_cost_without_request_ledger')
        self.assertTrue(self.app.bootstrap()['settings']['accounting_error'])
        self.assertIsNone(self.app.bootstrap()['settings']['runtime_remaining_inr'])
        client = inference.Inference(self.root, self.app.ledger_root, self.app.store, lambda *args, **kwargs: self.fail('No model request is allowed'))
        with self.assertRaises(ValueError):
            client._client(job['id'])
        self.assertEqual(json.loads(self.app.store.prediction_export(job['id'], 'json'))['run_details']['cost_inr'], 2.5)

    def test_per_object_csv_escapes_formulas_and_omits_private_fields(self):
        job = self.job('=HYPERLINK("private").png')
        matches = []
        for index, state in enumerate(('match', 'not_sure', 'not_in_catalog')):
            matches.append({'object_id': 'o' + str(index), 'box_2d': [0, 0, 1000, 1000], 'status': state,
                            'product_id': 'fixture', 'product_name': ' +SUM(1,2)', 'confidence': 'High',
                            'verification': 'confirmed', 'evidence': ['Observed bin.'], 'missing_evidence': ['Read the label.'],
                            'retake_guidance': ['Photograph the label.'], 'alternatives': [{'id': 'other', 'name': 'Other', 'secret': 'PRIVATE_ALT'}],
                            'reference_image_url': '/private/server/path', 'source_url': 'PRIVATE_SOURCE', 'prompt': 'PRIVATE_PROMPT',
                            'raw': {'headers': 'PRIVATE_HEADERS', 'image': 'PRIVATE_IMAGE'}})
        self.app.store.update_job(job['id'], status='completed', matches=matches)
        saved = self.app.public_jobs(job['id'])[0]
        raw_json = self.app.store.prediction_export(job['id'], 'json')
        rows = list(csv.DictReader(io.StringIO(self.app.store.prediction_export(job['id'], 'csv').decode())))
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]['filename'].startswith("'="))
        self.assertTrue(rows[0]['model_family'].startswith("' +"))
        self.assertEqual(json.loads(rows[0]['retake_guidance']), ['Photograph the label.'])
        self.assertEqual({row['decision_status'] for row in rows}, {'match', 'not_sure', 'not_in_catalog'})
        for forbidden in ('PRIVATE_', '/private/server', 'source_url', 'reference_image_url', 'prompt', 'headers'):
            self.assertNotIn(forbidden, raw_json.decode())
        self.assertTrue(saved['exports_available'])

    def test_retake_guidance_uses_unchanged_retake_and_missing_evidence(self):
        snapshot = self.app.store.job(self.job()['id'], internal=True)['_snapshot']
        raw = response(snapshot, status='not_sure')['results'][0]['result']
        raw['decision']['retake'] = 'Photograph the printed model label.'
        shown = inference.display_match(target(), raw, snapshot)
        self.assertEqual(shown['retake_guidance'], ['Photograph the printed model label.', 'Inspect the body detail.'])

    def test_existing_owned_directories_and_database_become_private(self):
        self.app.close()
        for path in (self.root / 'var', self.root / 'var/runtime', self.root / 'var/media', self.root / 'var/jobs'):
            path.chmod(0o755)
        (self.root / 'var/app.sqlite3').chmod(0o644)
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)
        for path in (self.root / 'var', self.root / 'var/runtime', self.root / 'var/media', self.root / 'var/jobs'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / 'var/app.sqlite3').stat().st_mode & 0o777, 0o600)
        job = self.job()
        internal = self.app.store.job(job['id'], internal=True)
        self.assertEqual(self.app.store.media(internal['_media_id'])[0].stat().st_mode & 0o777, 0o600)

    def test_export_failure_preserves_prediction_and_later_jobs(self):
        first, second = self.app.store.create_jobs({'images': [image_file('one.png'), image_file('two.png')]})
        self.app.engine.count = 1
        with patch.object(self.app.store, 'seal_prediction', side_effect=OSError('PRIVATE_DISK_DETAIL')):
            self.app.process_job(first['id'])
        failed_export = self.app.store.job(first['id'])
        self.assertEqual(failed_export['status'], 'completed')
        self.assertFalse(failed_export['exports_available'])
        self.assertIn('reopen the app', failed_export['export_error'])
        self.assertNotIn('PRIVATE', failed_export['export_error'])
        self.app.process_job(second['id'])
        self.assertTrue(self.app.store.job(second['id'])['exports_available'])
        self.assertTrue(self.app.public_jobs(first['id'])[0]['exports_available'])
        self.assertEqual(self.app.engine.count, 3)

    def test_truncated_ledger_blocks_spending_without_hiding_history_or_saved_exports(self):
        completed = self.completed()
        saved = self.app.store.prediction_export(completed['id'], 'json')
        pending = self.job()
        broken = self.app.ledger_root / 'damaged-job'
        broken.mkdir()
        (broken / 'calls.jsonl').write_text('{"job_id":')
        clients = []
        self.app.engine = inference.Inference(self.root, self.app.ledger_root, self.app.store,
                                             lambda *args, **kwargs: clients.append(args))
        self.app.process_job(pending['id'])
        stopped = self.app.store.job(pending['id'])
        self.assertEqual(stopped['status'], 'failed')
        self.assertFalse(stopped['exports_available'])
        self.assertTrue(stopped['export_error'])
        self.assertEqual(clients, [])
        self.assertEqual(self.app.store.prediction_export(completed['id'], 'json'), saved)
        bootstrap = self.app.bootstrap()
        self.assertEqual(len(bootstrap['jobs']), 2)
        self.assertTrue(bootstrap['settings']['accounting_error'])
        self.assertIsNone(bootstrap['settings']['runtime_spent_inr'])
        self.assertIsNone(bootstrap['settings']['runtime_remaining_inr'])
        self.app.close()
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=FakeEngine)
        self.assertEqual(len(self.app.bootstrap()['jobs']), 2)
        self.assertEqual((broken / 'calls.jsonl').read_text(), '{"job_id":')

    def test_seed_rejects_escape_and_existing_database_needs_no_seed(self):
        self.app.close()
        shutil.rmtree(self.root / 'var/catalogue-seed')
        reopened = Store(self.root, self.root / 'var')
        self.assertEqual(len(reopened.products()), 9)
        other = self.root / 'other-root'
        other.mkdir()
        fixture_root(other)
        path = other / 'var/catalogue-seed/reference_cards.json'
        cards = json.loads(path.read_text())
        next(iter(cards['products'].values()))['images'][0]['file'] = '../../../runtime_config.json'
        path.write_text(json.dumps(cards))
        with self.assertRaises(ValueError):
            Store(other, other / 'var')

    def test_code_only_import_and_fresh_inference_need_no_research_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            clean = fixture_root(folder)
            shutil.copy2(ROOT / 'app_server.py', clean / 'app_server.py')
            shutil.copytree(ROOT / 'webapp', clean / 'webapp', ignore=shutil.ignore_patterns('__pycache__'))
            script = '''import json, sys
from pathlib import Path
from webapp.store import Store
from webapp.inference import Inference
import app_server
root=Path.cwd()
assert not (root/'data').exists() and not (root/'out').exists() and not (root/'tools').exists()
store=Store(root,root/'var')
image=json.loads(sys.argv[1])
job=store.create_jobs({'images':[image]})[0]
class Client:
    def __init__(self, config, root, out, **options): self.config=config
    def generate(self,*args): return {'objects':[]}
engine=Inference(root,root/'var/runtime',store,Client)
assert engine.run(store.job(job['id'],internal=True),lambda stage:None)==[]
assert not any(name in sys.modules for name in ('run_baseline','run_pipeline','pipeline_api','failure_protocol','evidence_v2'))
print('clean runtime import and fresh inference passed')
'''
            result = subprocess.run([sys.executable, '-c', script, json.dumps(image_file())], cwd=clean, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('fresh inference passed', result.stdout)


def base64_bytes(image):
    import base64
    return base64.b64decode(image['data_url'].split(',', 1)[1])


class ExportHTTPTests(HTTPFixture, unittest.TestCase):
    def test_removed_historical_routes_and_bootstrap(self):
        self.assertNotIn('evaluation', json.loads(self.request('/api/bootstrap')[2]))
        for path in ('/api/evaluation', '/report', '/web/report.html', '/media/eval-P001'):
            self.assertEqual(self.request(path)[0], 404)
        policy = self.request('/')[1]['Content-Security-Policy']
        self.assertIn("script-src 'self';", policy)
        self.assertNotIn('sha256-', policy)

    def test_export_attachments_security_and_unavailable_status(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        path = '/api/jobs/' + job['id'] + '/export.json'
        self.assertEqual(self.request(path)[0], 409)
        self.assertEqual(self.request('/api/jobs/unknown/export.json')[0], 404)
        self.assertEqual(self.app.engine.count, 0)
        self.app.engine.count = 1
        self.app.process_job(job['id'])
        for kind in ('json', 'csv'):
            download = path.rsplit('.', 1)[0] + '.' + kind
            code, headers, raw = self.request(download)
            self.assertEqual(code, 200)
            self.assertIn('attachment;', headers['Content-Disposition'])
            self.assertEqual(headers['X-Content-SHA256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(self.request(download)[2], raw)
            self.assertEqual(self.request(download, headers={'Origin': 'https://other.example'})[0], 403)
            self.assertEqual(self.request(download, headers={'Host': 'other.example'})[0], 403)
            self.assertEqual(self.request(download, headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)


if __name__ == '__main__':
    unittest.main()
