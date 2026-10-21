"""Direct regressions for durable queues, save recovery and burst responses."""
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import app_server
from test_webapp import fixture_root, image_file, HTTPFixture


class CountingEngine:
    def __init__(self, root, ledger_root, store):
        self.calls = []
        self.lock = threading.Lock()

    def run(self, job, stage):
        with self.lock:
            self.calls.append(job['id'])
        return []


def wait_until(predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.02)
    return False


class DurableQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=CountingEngine)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def start_workers(self):
        self.app.remaining_workers = len(self.app.workers)
        for worker in self.app.workers:
            worker.start()

    def test_failed_enqueue_checkpoint_does_not_lose_database_job(self):
        job = self.app.store.create_jobs({'images': [image_file()], 'request_id': 'lost-ack'})[0]
        with patch('app_server.cloud_runtime.checkpoint', side_effect=RuntimeError('temporary save failure')):
            with self.assertRaises(RuntimeError):
                self.app.enqueue([job])
        self.assertTrue(self.app.queue.empty())
        self.start_workers()
        self.assertTrue(wait_until(lambda: self.app.store.job(job['id'])['exports_available']))
        self.assertEqual(self.app.engine.calls, [job['id']])

    def test_transient_claim_failure_is_retried_without_a_queue_hint(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        claim = self.app.store.claim_job
        failures = [True]

        def flaky_claim(key):
            if failures:
                failures.pop()
                raise RuntimeError('temporary database failure')
            return claim(key)

        with patch.object(self.app.store, 'claim_job', side_effect=flaky_claim):
            self.start_workers()
            self.assertTrue(wait_until(lambda: self.app.store.job(job['id'])['exports_available']))
        self.assertEqual(self.app.engine.calls, [job['id']])
        self.assertTrue(all(worker.is_alive() for worker in self.app.workers))

    def test_claim_must_be_checkpointed_before_inference(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        with patch('app_server.cloud_runtime.checkpoint', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):
                self.app.process_job(job['id'])
        self.assertEqual(self.app.store.job(job['id'])['status'], 'queued')
        self.assertEqual(self.app.engine.calls, [])
        self.app.process_job(job['id'])
        self.assertEqual(self.app.engine.calls, [job['id']])

    def test_terminal_save_failure_recovers_without_repeating_inference(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        save = self.app._save_prediction
        failures = [True]

        def flaky_save(key):
            if failures:
                failures.pop()
                raise RuntimeError('temporary final save failure')
            return save(key)

        with patch.object(self.app, '_save_prediction', side_effect=flaky_save):
            self.app.process_job(job['id'])
            self.assertEqual(self.app.public_jobs(job['id'])[0]['status'], 'completed')
            self.assertFalse(self.app.store.job(job['id'])['exports_available'])
            self.start_workers()
            self.assertTrue(wait_until(lambda: self.app.store.job(job['id'])['exports_available']))
        self.assertEqual(self.app.engine.calls, [job['id']])
        self.assertTrue(all(worker.is_alive() for worker in self.app.workers))

    def test_terminal_database_update_recovers_without_repeating_inference(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        update = self.app.store.update_job
        failures = [True]

        def flaky_update(key, **changes):
            if failures and changes.get('status') == 'completed':
                failures.pop()
                raise RuntimeError('temporary database failure')
            return update(key, **changes)

        with patch.object(self.app.store, 'update_job', side_effect=flaky_update):
            self.app.process_job(job['id'])
            self.assertEqual(self.app.store.job(job['id'])['status'], 'running')
            self.start_workers()
            self.assertTrue(wait_until(lambda: self.app.store.job(job['id'])['exports_available']))
        self.assertEqual(self.app.engine.calls, [job['id']])

    def test_two_final_checkpoint_failures_keep_both_workers_and_finish_three_jobs(self):
        jobs = self.app.store.create_jobs({'images': [image_file(name) for name in ('a.png', 'b.png', 'c.png')]})
        failures = [True, True]
        failed_ids = set()

        def checkpoint():
            fresh = [job['id'] for job in self.app.store.jobs() if job['status'] == 'completed' and job['id'] not in failed_ids]
            if failures and fresh:
                failed_ids.add(fresh[0])
                failures.pop()
                raise RuntimeError('temporary final checkpoint failure')

        with patch('app_server.cloud_runtime.checkpoint', side_effect=checkpoint):
            self.start_workers()
            self.assertTrue(wait_until(lambda: all(self.app.store.job(job['id'])['exports_available'] for job in jobs)
                                      and not self.app.pending_saves, seconds=6))
        self.assertEqual(failures, [])
        self.assertCountEqual(self.app.engine.calls, [job['id'] for job in jobs])
        self.assertTrue(all(worker.is_alive() for worker in self.app.workers))

    def test_checkpoint_failure_after_sealing_does_not_fail_reads_or_repeat_engine(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        self.app.process_job(job['id'])
        with patch('app_server.cloud_runtime.checkpoint', side_effect=RuntimeError('temporary upload failure')):
            result = self.app._seal_prediction(job['id'])
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(self.app.public_jobs(job['id'])[0]['status'], 'completed')
        with self.app.save_lock:
            self.app.pending_saves[job['id']]['next'] = 0
        self.app._retry_saves()
        self.assertNotIn(job['id'], self.app.pending_saves)
        self.assertEqual(self.app.engine.calls, [job['id']])

    def test_save_retry_is_bounded_and_never_reexecutes_inference(self):
        job = self.app.store.create_jobs({'images': [image_file()]})[0]
        with patch.object(self.app, '_save_prediction', side_effect=RuntimeError('save failed')) as save:
            self.app.process_job(job['id'])
            for _ in range(5):
                self.app.pending_saves[job['id']]['next'] = 0
                self.app._retry_saves()
            self.assertEqual(save.call_count, 3)
        self.assertEqual(self.app.engine.calls, [job['id']])

    def test_restart_preserves_queued_and_resumes_only_unambiguous_running_jobs(self):
        jobs = self.app.store.create_jobs({'images': [image_file('queued.png'), image_file('safe.png'), image_file('ambiguous.png')]})
        queued, safe, ambiguous = [job['id'] for job in jobs]
        self.app.store.claim_job(safe)
        self.app.store.claim_job(ambiguous)
        folder = self.app.ledger_root / ambiguous
        folder.mkdir()
        (folder / 'inflight.json').write_text(json.dumps({'pending': {'reserved_cost_usd': .1}}))
        self.app.close()
        self.app = app_server.build_app(self.root, start_worker=False, inference_factory=CountingEngine)
        self.assertEqual(self.app.store.job(queued)['status'], 'queued')
        self.assertEqual(self.app.store.job(safe)['status'], 'queued')
        self.assertEqual(self.app.store.job(ambiguous)['status'], 'interrupted')
        self.start_workers()
        self.assertTrue(wait_until(lambda: all(self.app.store.job(key)['exports_available'] for key in (queued, safe))))
        self.assertCountEqual(self.app.engine.calls, [queued, safe])


class HTTPResilienceTests(HTTPFixture, unittest.TestCase):
    def test_failed_ack_cached_resubmission_reconciles_the_durable_queue(self):
        self.app.engine = CountingEngine(self.root, self.app.ledger_root, self.app.store)
        payload = {'images': [image_file()], 'request_id': 'retry-lost-ack'}
        headers = {'X-CSRF-Token': self.app.csrf_token}
        with patch('app_server.api_configured', return_value=True):
            with patch('app_server.cloud_runtime.checkpoint', side_effect=RuntimeError('storage unavailable')):
                self.assertEqual(self.request('/api/jobs', payload, headers=headers)[0], 500)
            code, _, raw = self.request('/api/jobs', payload, headers=headers)
            self.assertEqual(code, 202)
            job = json.loads(raw)['jobs'][0]
            self.assertFalse(self.app.queue.empty())
            self.app.process_job(self.app.queue.get_nowait())
            code, _, raw = self.request('/api/jobs', payload, headers=headers)
            self.assertEqual(code, 202)
            self.assertEqual(json.loads(raw)['jobs'][0]['id'], job['id'])
            self.assertEqual(len(self.app.store.jobs()), 1)
            self.assertEqual(self.app.engine.calls, [job['id']])

    def test_failed_retry_ack_reconciles_the_existing_unstarted_job(self):
        original = self.app.store.create_jobs({'images': [image_file()]})[0]
        self.app.store.update_job(original['id'], status='failed')
        payload = {'request_id': 'retry-save-outage'}
        path = '/api/jobs/' + original['id'] + '/retry'
        headers = {'X-CSRF-Token': self.app.csrf_token}
        with patch('app_server.api_configured', return_value=True):
            with patch('app_server.cloud_runtime.checkpoint', side_effect=RuntimeError('storage unavailable')):
                self.assertEqual(self.request(path, payload, headers=headers)[0], 500)
            code, _, raw = self.request(path, payload, headers=headers)
        self.assertEqual(code, 202)
        retried = json.loads(raw)['jobs'][0]
        self.assertNotEqual(retried['id'], original['id'])
        self.assertEqual(len(self.app.store.jobs()), 2)
        self.assertEqual(self.app.queue.get_nowait(), retried['id'])

    def test_six_client_bursts_receive_responses(self):
        self.assertEqual(self.server.request_queue_size, 128)
        for iteration in range(3):
            barrier = threading.Barrier(6)
            payload = {'images': [image_file()], 'request_id': 'burst-' + str(iteration)}

            def request():
                barrier.wait(timeout=3)
                return self.request('/api/jobs', payload, headers={'X-CSRF-Token': self.app.csrf_token})

            with patch('app_server.api_configured', return_value=True), ThreadPoolExecutor(max_workers=6) as pool:
                responses = list(pool.map(lambda _: request(), range(6)))
            self.assertEqual([row[0] for row in responses], [202] * 6)
            self.assertEqual(len({json.loads(row[2])['jobs'][0]['id'] for row in responses}), 1)
            self.assertEqual(len(self.app.store.jobs()), iteration + 1)


if __name__ == '__main__':
    unittest.main()
