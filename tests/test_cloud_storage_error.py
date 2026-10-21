"""Storage failures retain accounting and use an accurate public message."""
import json
import tempfile
import unittest
from unittest.mock import patch

import app_server
from webapp import cloud_runtime
from test_webapp import fixture_root, image_file


class StorageErrorTests(unittest.TestCase):
    def run_failure(self, error):
        with tempfile.TemporaryDirectory() as folder:
            root = fixture_root(folder)
            app = app_server.build_app(root, start_worker=False)
            try:
                job = app.store.create_jobs({'images': [image_file()]})[0]
                ledger = app.ledger_root / job['id']
                ledger.mkdir()
                calls = {'job_id': 'inventory', 'status': 'ok', 'estimated_cost_usd': .06,
                         'cost_basis': 'provider_reported_cost'}
                pending = {'comparison': {'job_id': 'comparison', 'reserved_cost_usd': .22}}
                calls_bytes = json.dumps(calls) + '\n'
                pending_bytes = json.dumps(pending)
                (ledger / 'calls.jsonl').write_text(calls_bytes)
                (ledger / 'inflight.json').write_text(pending_bytes)
                with patch.object(app.engine, 'run', side_effect=error) as run:
                    app.process_job(job['id'])
                self.assertEqual(run.call_count, 1)
                result = app.store.job(job['id'])
                self.assertEqual(result['status'], 'failed')
                self.assertAlmostEqual(result['cost_inr'], 28)
                self.assertEqual((ledger / 'calls.jsonl').read_text(), calls_bytes)
                self.assertEqual((ledger / 'inflight.json').read_text(), pending_bytes)
                self.assertTrue(app.store.media(job['image_url'].rsplit('/', 1)[1])[0].exists())
                self.assertNotIn('private diagnostic', result['error'])
                self.assertTrue(result['exports_available'])
                return result['error']
            finally:
                app.close()

    def test_storage_error_is_not_reported_as_model_failure(self):
        message = self.run_failure(cloud_runtime.CloudStateError('private diagnostic'))
        self.assertIn('data could not be saved', message)
        self.assertIn('spending records were kept', message)
        self.assertNotIn('The model request failed', message)

    def test_provider_error_keeps_model_failure_message(self):
        message = self.run_failure(RuntimeError('private diagnostic'))
        self.assertIn('The model request failed', message)
        self.assertNotIn('Saved-state storage', message)


if __name__ == '__main__':
    unittest.main()
