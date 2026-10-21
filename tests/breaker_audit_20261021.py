"""Report-only local breaker audit. Never uses credentials, real photos or external sockets.

Run from the repository with PYTHONPATH=.:tests using the bundled Python runtime.
Every scenario is run twice, with independent invented state, by this module's main.
Some assertions confirm reproduced defects; a green audit does not mean no findings.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import app_server
from test_webapp import fixture_root, image_file
from test_webapp_inference import target, response
from webapp import cloud_runtime, transport
from webapp.inference import ledger_accounting, validate_batch
from webapp.request_coordinator import RequestCoordinator
from webapp.store import Store, ConflictError

EVIDENCE = []
EXTERNAL_ATTEMPTS = []
HTTP_EXCHANGES = []
MOCK_EXCHANGES = []
EXPECTED_HEAD = '9ceb1734eb73617e16d5e4934c3485c4e75a1be2'
OUTPUT = Path(__file__).resolve().parents[1] / 'var/breaker-20261021'
SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
          'required': ['ok'], 'additionalProperties': False}
CONFIG = {'models': {'fake': {'provider': 'openrouter', 'model': 'google/test-only',
    'input_usd_per_million': 1, 'output_usd_per_million': 2,
    'max_output_tokens': 1000, 'input_token_bound': 1000,
    'provider_only': ['google-ai-studio']}},
    'budget': {'stage_max_inr': 100, 'total_max_inr': 100,
               'prior_accounted_inr': 0, 'usd_inr': 100}}


def provider_reply(text='{"ok":true}', finish='stop', cost=.001):
    MOCK_EXCHANGES.append({'kind': 'invented-provider', 'finish': finish})
    return io.BytesIO(json.dumps({'choices': [{'finish_reason': finish,
        'message': {'content': text}}], 'usage': {'cost': cost}}).encode())


class EmptyEngine:
    def __init__(self, *args):
        self.calls = 0

    def run(self, job, stage):
        self.calls += 1
        return []


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dyson-breaker-')
        self.addCleanup(self.tmp.cleanup)
        self.root = fixture_root(self.tmp.name)
        self.photo = self.root / 'invented.png'
        import base64
        self.photo.write_bytes(base64.b64decode(image_file()['data_url'].split(',')[1]))
        self.patches = [patch.dict(os.environ, {'CLOUD_MODE': '0',
            'OPENROUTER_API_KEY': 'invented-test-only', 'CLOUD_CONTAINER_TOKEN': 'invented-test-only'}),
            patch.object(transport, 'api_key_for', return_value='invented-test-only'),
            patch.object(app_server, 'api_key_for', return_value='invented-test-only')]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def record(self, **details):
        EVIDENCE.append({'scenario': self._testMethodName, **details})

    def client(self, name='one', coordinator=None):
        return transport.Client(CONFIG, self.root, self.root / 'var/runtime' / name,
                                request_coordinator=coordinator)

    def call(self, client, name='invented-call'):
        return client.generate(name, 'fake', 'Check the invented photo.',
                               [('Invented view', self.photo)], schema=SCHEMA)

    @contextmanager
    def http(self):
        app = app_server.build_app(self.root, start_worker=False, inference_factory=EmptyEngine)
        server = app_server.make_server(app, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = 'http://127.0.0.1:' + str(server.server_address[1])
        def request(path, payload):
            HTTP_EXCHANGES.append({'path': path, 'host': '127.0.0.1'})
            req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json', 'X-CSRF-Token': app.csrf_token,
                         'Origin': base})
            try:
                with urllib.request.urlopen(req, timeout=4) as reply:
                    return reply.status, json.load(reply)
            except urllib.error.HTTPError as error:
                with error:
                    return error.code, json.load(error)
        with patch.object(app_server, 'api_configured', return_value=True):
            try:
                yield app, request
            finally:
                server.shutdown(); server.server_close(); worker.join(3)

    def test_01_http_six_simultaneous_identical_submissions(self):
        with self.http() as (app, request):
            payload = {'images': [image_file()], 'request_id': 'supervisor-double-tap'}
            results, errors, barrier = [], [], threading.Barrier(6)
            def submit():
                try:
                    barrier.wait(3); results.append(request('/api/jobs', payload))
                except Exception as error:
                    errors.append({'type': type(error).__name__, 'message': str(error)})
            threads = [threading.Thread(target=submit) for _ in range(6)]
            for t in threads: t.start()
            for t in threads: t.join(5)
            if errors:
                self.record(outcome='burst-transport-failure', completed=len(results), errors=errors,
                            live_threads=sum(t.is_alive() for t in threads))
            self.assertEqual(len(results), 6)
            self.assertTrue(all(code == 202 for code, _ in results))
            self.assertEqual(len({r['jobs'][0]['id'] for _, r in results}), 1)
            self.assertEqual(app.queue.qsize(), 1)
            changed = copy.deepcopy(payload)
            changed['images'] = [image_file('other.png', 'blue')]
            self.assertEqual(request('/api/jobs', changed)[0], 409)
            self.record(outcome='guard-held', submissions=6, queue=1, changed_payload_status=409)

    def test_02_http_upload_checkpoint_loss_then_repeat(self):
        with self.http() as (app, request):
            payload = {'images': [image_file()], 'request_id': 'resubmit-after-storage-error'}
            with patch.object(cloud_runtime, 'checkpoint', side_effect=cloud_runtime.CloudStateError('invented temporary storage outage')):
                first, _ = request('/api/jobs', payload)
            second, reply = request('/api/jobs', payload)
            self.assertEqual((first, second), (500, 202))
            self.assertEqual(app.queue.qsize(), 0)
            self.assertEqual(reply['jobs'][0]['status'], 'queued')
            self.assertEqual(len(app.store.jobs()), 1)
            self.record(outcome='reproduced', finding='BRK-001', first_status=first,
                        repeated_status=second, saved_status='queued', queue=0)

    def test_03_http_retry_checkpoint_loss_then_repeat(self):
        with self.http() as (app, request):
            original = app.store.create_jobs({'images': [image_file()]})[0]
            app.store.update_job(original['id'], status='failed')
            path = '/api/jobs/' + original['id'] + '/retry'
            payload = {'request_id': 'retry-after-storage-error'}
            with patch.object(cloud_runtime, 'checkpoint', side_effect=cloud_runtime.CloudStateError('invented storage outage')):
                first, _ = request(path, payload)
            second, reply = request(path, payload)
            self.assertEqual((first, second), (500, 202))
            self.assertEqual(app.queue.qsize(), 0)
            self.assertEqual(reply['jobs'][0]['status'], 'queued')
            self.record(outcome='reproduced', finding='BRK-001', route='retry',
                        first_status=first, repeated_status=second, queue=0)

    def test_04_two_final_seal_failures_remove_both_workers(self):
        app = app_server.build_app(self.root, inference_factory=EmptyEngine)
        jobs = app.store.create_jobs({'images': [image_file('a.png'), image_file('b.png'), image_file('c.png')]})
        errors = []
        def hook(args): errors.append(str(args.exc_value))
        try:
            with patch.object(threading, 'excepthook', side_effect=hook), patch.object(cloud_runtime, 'checkpoint', side_effect=cloud_runtime.CloudStateError('invented final seal outage')):
                for job in jobs: app.queue.put(job['id'])
                for worker in app.workers: worker.join(3)
            self.assertTrue(all(not w.is_alive() for w in app.workers))
            statuses = [app.store.job(j['id'])['status'] for j in jobs]
            self.assertEqual(statuses.count('completed'), 2)
            self.assertEqual(statuses.count('queued'), 1)
            self.assertEqual(app.remaining_workers, 0)
            self.assertEqual(len(errors), 2)
            self.record(outcome='reproduced', finding='BRK-002', statuses=statuses,
                        worker_errors=errors, workers_alive=0, queue=app.queue.qsize())
        finally:
            app.close()

    def test_05_claim_write_failure_terminates_worker(self):
        app = app_server.build_app(self.root, inference_factory=EmptyEngine)
        job = app.store.create_jobs({'images': [image_file()]})[0]
        errors = []
        try:
            with patch.object(threading, 'excepthook', side_effect=lambda args: errors.append(str(args.exc_value))), patch.object(app.store, 'claim_job', side_effect=OSError('invented SQLite write failure')):
                app.queue.put(job['id'])
                deadline = time.monotonic() + 3
                while not errors and time.monotonic() < deadline: time.sleep(.01)
            self.assertEqual(len(errors), 1)
            self.assertEqual(sum(w.is_alive() for w in app.workers), 1)
            self.assertEqual(app.store.job(job['id'])['status'], 'queued')
            self.assertEqual(app.queue.qsize(), 0)
            self.record(outcome='reproduced', finding='BRK-003', errors=errors,
                        status='queued', queue=0, workers_alive=1)
        finally: app.close()

    def test_06_truncated_provider_json_records_actual_cost(self):
        client = self.client()
        with patch.object(transport.urllib.request, 'urlopen', return_value=provider_reply('{"ok":')) as network:
            with self.assertRaises(RuntimeError): self.call(client)
        row = json.loads(client.calls_path.read_text())
        self.assertEqual(row['estimated_cost_usd'], .001)
        self.assertEqual(row['status'], 'error')
        self.assertEqual(client.pending, {})
        self.assertEqual(network.call_count, 1)
        self.record(outcome='guard-held', status=row['status'], actual_usd=row['estimated_cost_usd'])

    def test_07_token_truncation_and_unexpected_field_rejected(self):
        outcomes = []
        for name, content, finish in [('length', '{"ok":true}', 'length'), ('extra', '{"ok":true,"detail_wrong":"x"}', 'stop')]:
            client = self.client(name)
            with patch.object(transport.urllib.request, 'urlopen', return_value=provider_reply(content, finish)):
                with self.assertRaises(RuntimeError): self.call(client)
            row = json.loads(client.calls_path.read_text())
            self.assertEqual(row['estimated_cost_usd'], .001)
            outcomes.append({'case': name, 'status': row['status']})
        self.record(outcome='guard-held', cases=outcomes)

    def test_08_temporary_reservation_write_failure_recovers_once(self):
        client = self.client()
        writes, provider_count = [], []
        def state(method, data, **kwargs):
            writes.append(data)
            if len(writes) <= 2: raise OSError('invented unavailable store')
            return nullcontext(SimpleNamespace(status=200))
        def provider(req, timeout):
            provider_count.append(1)
            self.assertEqual(len(writes), 3)
            return provider_reply()
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', self.root), patch.object(cloud_runtime, '_request', side_effect=state), patch.object(cloud_runtime.time, 'sleep'), patch.object(transport.urllib.request, 'urlopen', side_effect=provider):
            self.assertEqual(self.call(client), {'ok': True})
        self.assertEqual(len(provider_count), 1)
        self.assertEqual(writes[0], writes[1]); self.assertEqual(writes[1], writes[2])
        self.record(outcome='guard-held', state_attempts=len(writes), provider_calls=1)

    def test_09_persistent_reservation_failure_never_calls_provider(self):
        client = self.client()
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', self.root), patch.object(cloud_runtime, '_request', side_effect=OSError('invented outage')), patch.object(cloud_runtime.time, 'sleep'), patch.object(transport.urllib.request, 'urlopen') as network:
            with self.assertRaises(cloud_runtime.CloudStateError): self.call(client)
            self.assertEqual(network.call_count, 0)
        reopened = self.client()
        with patch.object(transport.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(RuntimeError, 'unresolved'): self.call(reopened)
            self.assertEqual(network.call_count, 0)
        self.assertAlmostEqual(ledger_accounting(self.root / 'var/runtime')['spent_inr'], .3)
        self.record(outcome='guard-held', provider_calls=0, retained_upper_bound_inr=.3)

    def test_10_temporary_settlement_write_failure_keeps_single_charge(self):
        client = self.client()
        writes = []
        def state(method, data, **kwargs):
            writes.append(data)
            if len(writes) in (2, 3): raise OSError('invented settlement outage')
            return nullcontext(SimpleNamespace(status=200))
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', self.root), patch.object(cloud_runtime, '_request', side_effect=state), patch.object(cloud_runtime.time, 'sleep'), patch.object(transport.urllib.request, 'urlopen', side_effect=lambda *a, **k: provider_reply()) as network:
            self.assertEqual(self.call(client), {'ok': True})
        self.assertEqual(network.call_count, 1)
        self.assertEqual(len(writes), 4)
        self.assertAlmostEqual(ledger_accounting(self.root / 'var/runtime')['spent_inr'], .1)
        self.record(outcome='guard-held', state_attempts=4, provider_calls=1, charged_inr=.1)

    def test_11_persistent_settlement_failure_restore_retains_reservation(self):
        client, durable = self.client(), []
        def state(method, data, **kwargs):
            if not durable: durable.append(data); return nullcontext(SimpleNamespace(status=200))
            raise OSError('invented persistent settlement outage')
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', self.root), patch.object(cloud_runtime, '_request', side_effect=state), patch.object(cloud_runtime.time, 'sleep'), patch.object(transport.urllib.request, 'urlopen', side_effect=lambda *a, **k: provider_reply()) as network:
            with self.assertRaises(cloud_runtime.CloudStateError): self.call(client)
        self.assertEqual(network.call_count, 1)
        self.assertAlmostEqual(ledger_accounting(self.root / 'var/runtime')['spent_inr'], .1)
        with tempfile.TemporaryDirectory() as folder:
            cloud_runtime.restore(folder, durable[0])
            accounting = ledger_accounting(Path(folder) / 'var/runtime')
            self.assertAlmostEqual(accounting['spent_inr'], .3)
            reopened = transport.Client(CONFIG, folder, Path(folder) / 'var/runtime/one')
            with patch.object(transport.urllib.request, 'urlopen') as network:
                with self.assertRaisesRegex(RuntimeError, 'unresolved'): self.call(reopened)
                self.assertEqual(network.call_count, 0)
        self.record(outcome='guard-held', actual_local_inr=.1, durable_upper_bound_inr=.3, duplicate_calls=0)

    def test_12_three_clients_max_two_calls_overlap(self):
        runtime, active, maximum = self.root / 'var/runtime', [0], [0]
        coordinator = RequestCoordinator(lambda: ledger_accounting(runtime)['spent_inr'], lambda: 100, interval_seconds=0)
        clients = [self.client(str(i), coordinator) for i in range(3)]
        lock, release, both = threading.Lock(), threading.Event(), threading.Event()
        errors = []
        def provider(*args, **kwargs):
            with lock:
                active[0] += 1; maximum[0] = max(maximum[0], active[0])
                if active[0] == 2: both.set()
            if not release.wait(3): raise RuntimeError('test release absent')
            with lock: active[0] -= 1
            return provider_reply()
        def invoke(c):
            try: self.call(c)
            except Exception as e: errors.append(str(e))
        with patch.object(transport.urllib.request, 'urlopen', side_effect=provider) as network:
            threads = [threading.Thread(target=invoke, args=(c,)) for c in clients]
            for t in threads: t.start()
            try:
                self.assertTrue(both.wait(3)); self.assertEqual(network.call_count, 2)
            finally:
                release.set()
                for t in threads: t.join(4)
        self.assertEqual(errors, []); self.assertEqual(maximum[0], 2)
        self.assertEqual(network.call_count, 3)
        self.record(outcome='guard-held', max_concurrent=2, total_calls=3)

    def test_13_simultaneous_budget_admission_blocks_second(self):
        runtime = self.root / 'var/runtime'
        coordinator = RequestCoordinator(lambda: ledger_accounting(runtime)['spent_inr'], lambda: .5, interval_seconds=0)
        clients = [self.client(str(i), coordinator) for i in range(2)]
        started, release, denied = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def provider(*args, **kwargs):
            started.set(); release.wait(3); return provider_reply()
        def invoke(c):
            try: self.call(c)
            except Exception as e: errors.append(str(e)); denied.set()
        with patch.object(transport.urllib.request, 'urlopen', side_effect=provider) as network:
            threads = [threading.Thread(target=invoke, args=(c,)) for c in clients]
            threads[0].start(); self.assertTrue(started.wait(3)); threads[1].start()
            try: self.assertTrue(denied.wait(3)); self.assertEqual(network.call_count, 1)
            finally:
                release.set()
                for t in threads: t.join(4)
        self.assertEqual(len(errors), 1); self.assertIn('remaining allowance', errors[0])
        self.record(outcome='guard-held', admitted_calls=1, denied_calls=1, cap_inr=.5)

    def test_14_actual_client_launch_pacing_and_settlement_lock(self):
        clock, waits, launches = [0.0], [], []
        def wait(n): waits.append(n); clock[0] += n
        coordinator = RequestCoordinator(lambda: 0, lambda: 100, interval_seconds=15, clock=lambda: clock[0], wait=wait)
        clients = [self.client(str(i), coordinator) for i in range(2)]
        def provider(*args, **kwargs): launches.append(clock[0]); return provider_reply()
        with patch.object(transport.urllib.request, 'urlopen', side_effect=provider):
            self.call(clients[0]); clock[0] = 4; self.call(clients[1])
        self.assertEqual(launches, [0, 15]); self.assertEqual(waits, [11])
        self.record(outcome='guard-held', launches=launches, waits=waits)

    def test_15_restart_interrupts_jobs_retains_paid_and_pending(self):
        app = app_server.build_app(self.root, start_worker=False, inference_factory=EmptyEngine)
        job = app.store.create_jobs({'images': [image_file()]})[0]
        app.store.claim_job(job['id'])
        folder = app.ledger_root / job['id']; folder.mkdir()
        (folder / 'calls.jsonl').write_text(json.dumps({'job_id': 'finished', 'status': 'ok', 'estimated_cost_usd': .1}) + '\n')
        (folder / 'inflight.json').write_text(json.dumps({'unknown': {'reserved_cost_usd': .2}}))
        app.close()
        reopened = app_server.build_app(self.root, start_worker=False, inference_factory=EmptyEngine)
        try:
            self.assertEqual(reopened.store.job(job['id'])['status'], 'interrupted')
            self.assertTrue(reopened.queue.empty()); self.assertEqual(reopened.engine.calls, 0)
            self.assertAlmostEqual(reopened.store.job(job['id'])['cost_inr'], 30)
            self.record(outcome='guard-held', status='interrupted', charged_upper_bound_inr=30, automatic_calls=0)
        finally: reopened.close()

    def test_16_joint_conflicts_do_not_increase_certainty(self):
        store = Store(self.root, self.root / 'var')
        parent = store.create_jobs({'images': [image_file('one.png', 'red')]})[0]
        snapshot = store.job(parent['id'], internal=True)['_snapshot']
        raw = response(snapshot)
        result = raw['results'][0]['result']
        result['decisive_region'] = None
        result['cross_view_consistency'] = {'status': 'conflicting', 'evidence': 'One photo has a trigger and the other has a different body.'}
        for i, check in enumerate(result['feature_checks']): check['query_view'] = 'view_' + str(i + 1)
        checked = validate_batch(raw, [target()], snapshot, view_targets={'view_1': target(), 'view_2': target()})
        self.assertEqual(checked['o1']['decision']['status'], 'not_sure')
        raw = response(snapshot); item = raw['results'][0]['result']; item['decisive_region'] = None
        item['cross_view_consistency'] = {'status': 'consistent', 'evidence': 'Body matches.'}
        for check in item['feature_checks']: check['query_view'] = 'view_3'
        with self.assertRaisesRegex(ValueError, 'supplied view'):
            validate_batch(raw, [target()], snapshot, view_targets={'view_1': target(), 'view_2': target()})
        self.record(outcome='guard-held', contradictory_status='not_sure', unsupplied_view='rejected')

    def test_17_joint_frozen_lineage_and_three_view_limit(self):
        store = Store(self.root, self.root / 'var')
        parent = store.create_jobs({'images': [image_file('first.png', 'red')]})[0]
        store.update_job(parent['id'], status='completed', matches=[{'object_id': 'o1'}])
        original = store.job(parent['id'], internal=True)['_snapshot']
        store.edit_product({'name': 'Changed while supervisor adds view'}, 'dyson_v15_detect')
        def add(parent, colour, key):
            return store.create_jobs({'images': [image_file(key + '.png', colour)], 'parent_job_id': parent['id'],
                                      'same_product': True, 'request_id': key})[0]
        second = add(parent, 'blue', 'second')
        store.update_job(second['id'], status='completed', matches=[{'object_id': 'o1'}])
        third = add(second, 'green', 'third')
        store.update_job(third['id'], status='completed', matches=[{'object_id': 'o1'}])
        self.assertEqual(store.job(third['id'], internal=True)['_snapshot'], original)
        self.assertEqual(third['root_job_id'], parent['id'])
        with self.assertRaisesRegex(ValueError, 'three'): add(third, 'white', 'fourth')
        with self.assertRaisesRegex(ValueError, 'different photo'): add(parent, 'red', 'duplicate')
        self.record(outcome='guard-held', preserved_snapshot=True, fourth_view='rejected', duplicate='rejected')

    def test_18_compound_429_then_malformed_strict_response(self):
        client = transport.Client(CONFIG, self.root, self.root / 'var/runtime/retry', rate_limit_retries=1)
        attempt = [0]
        def provider(*args, **kwargs):
            attempt[0] += 1
            if attempt[0] == 1:
                MOCK_EXCHANGES.append({'kind': 'invented-provider', 'http': 429})
                raise urllib.error.HTTPError('https://invented.invalid', 429, 'Invented rate limit', {'Retry-After': '0'}, io.BytesIO(b'{}'))
            return provider_reply('{"ok":"wrong-type"}')
        with patch.object(client, '_wait'), patch.object(client, '_retry_delay', return_value=0), patch.object(transport.urllib.request, 'urlopen', side_effect=provider):
            with self.assertRaises(RuntimeError): self.call(client)
        records = [json.loads(line) for line in client.calls_path.read_text().splitlines()]
        self.assertEqual(len(records), 2); self.assertEqual(records[0]['http_status'], 429)
        self.assertEqual(records[1]['status'], 'error'); self.assertEqual(client.pending, {})
        self.assertAlmostEqual(client.accounted_cost_usd, .004)
        self.record(outcome='guard-held', attempts=2, accounted_inr=.4, statuses=[r['status'] for r in records])


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source_paths = ['app_server.py', 'webapp', 'cloudflare/src']
    subprocess.check_call(['git', 'diff', '--exit-code', EXPECTED_HEAD, '--', *source_paths],
                          cwd=OUTPUT.parents[1])
    source_hashes = {str(path.relative_to(OUTPUT.parents[1])): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in [OUTPUT.parents[1] / 'app_server.py',
                                  *sorted((OUTPUT.parents[1] / 'webapp').glob('*.py'))]}
    original_connect = socket.socket.connect
    def guarded_connect(sock, address):
        if not isinstance(address, tuple) or address[0] not in ('127.0.0.1', 'localhost', '::1'):
            EXTERNAL_ATTEMPTS.append(repr(address)); raise AssertionError('External network blocked by breaker harness')
        return original_connect(sock, address)
    suite = unittest.TestSuite()
    burst = '--burst' in sys.argv
    names = ['test_01_http_six_simultaneous_identical_submissions'] if burst else unittest.defaultTestLoader.getTestCaseNames(Audit)
    repetitions = 10 if burst else 2
    for repeat in range(repetitions):
        for name in names: suite.addTest(Audit(name))
    with patch.object(socket.socket, 'connect', guarded_connect):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {'target_head': EXPECTED_HEAD, 'scenario_count': len(names), 'executions': result.testsRun,
               'source_sha256': source_hashes,
               'failures': len(result.failures), 'errors': len(result.errors),
               'http_exchanges': len(HTTP_EXCHANGES), 'mock_provider_exchanges': len(MOCK_EXCHANGES),
               'real_model_calls': 0, 'production_calls': 0, 'external_socket_attempts': EXTERNAL_ATTEMPTS,
               'evidence': EVIDENCE}
    (OUTPUT / ('burst-results.json' if burst else 'results.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__': main()
