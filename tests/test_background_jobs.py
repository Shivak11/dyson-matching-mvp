"""Offline concurrency, pacing, reservation and process-lock checks."""
import fcntl
import tempfile
import threading
import unittest

import app_server
from webapp.request_coordinator import RequestCoordinator
from test_webapp import fixture_root, image_file


class BlockingEngine:
    def __init__(self, root, ledger_root, store):
        self.lock = threading.Lock()
        self.count = 0
        self.started = [threading.Event(), threading.Event()]
        self.release = [threading.Event(), threading.Event()]

    def run(self, job, stage):
        with self.lock:
            index = self.count
            self.count += 1
        self.started[index].set()
        if not self.release[index].wait(10):
            raise RuntimeError('Test did not release background work.')
        return []


class BackgroundTests(unittest.TestCase):
    def test_two_jobs_overlap_and_last_worker_retains_process_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = fixture_root(folder)
            app = app_server.build_app(root, inference_factory=BlockingEngine)
            try:
                jobs = app.store.create_jobs({'images': [image_file('one.png'), image_file('two.png')]})
                app.enqueue(jobs)
                self.assertTrue(all(event.wait(3) for event in app.engine.started))
                self.assertTrue(all(app.store.job(job['id'])['status'] == 'running' for job in jobs))
                app.engine.release[0].set()
                app.close()
                self.assertFalse(app.lock_file.closed)
                with (root / 'var/worker.lock').open('a+') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                app.engine.release[1].set()
                for worker in app.workers:
                    worker.join(timeout=3)
                self.assertTrue(all(not worker.is_alive() for worker in app.workers))
                self.assertTrue(app.lock_file.closed)
                self.assertTrue(all(app.store.job(job['id'])['status'] == 'completed' for job in jobs))
            finally:
                for event in app.engine.release:
                    event.set()
                app.close()

    def test_launches_are_spaced_from_last_launch(self):
        current = [0.0]
        waits = []

        def wait(delay):
            waits.append(delay)
            current[0] += delay

        coordinator = RequestCoordinator(lambda: 0, lambda: 100,
                                         wait=wait, clock=lambda: current[0])
        with coordinator.admission():
            coordinator.started()
        current[0] = 3
        with coordinator.admission():
            coordinator.started()
        self.assertEqual(waits, [12])
        self.assertEqual(coordinator.last_started, 15)

    def test_budget_check_and_persisted_reservation_are_atomic(self):
        account = {'spent': 0}
        coordinator = RequestCoordinator(lambda: account['spent'], lambda: 10, interval_seconds=0)
        barrier = threading.Barrier(2)
        outcomes = []

        def reserve():
            barrier.wait(timeout=3)
            try:
                with coordinator.admission():
                    coordinator.check_budget(.08)
                    account['spent'] += 8
                    coordinator.started()
                outcomes.append('admitted')
            except RuntimeError:
                outcomes.append('blocked')

        workers = [threading.Thread(target=reserve) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(sorted(outcomes), ['admitted', 'blocked'])
        self.assertEqual(account['spent'], 8)


if __name__ == '__main__':
    unittest.main()
