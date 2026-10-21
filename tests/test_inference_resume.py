"""Completed stages are reused; ambiguous paid work is never repeated."""
import io
import json
import tempfile
import unittest
from unittest.mock import patch

import app_server
from test_webapp import fixture_root, image_file
from test_webapp_inference import target, response
from webapp.inference import (Inference, BudgetError, can_resume_job, ledger_accounting,
                             RUNTIME_CAP_INR, STAGE_CAP_INR, HISTORICAL_STAGE_GUARD_INR)
from webapp.store import Store
from webapp.transport import Client


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = fixture_root(self.temp.name)
        self.store = Store(self.root, self.root / 'var')
        row = self.store.create_jobs({'images': [image_file()]})[0]
        self.job = self.store.job(row['id'], internal=True)
        self.ledgers = self.root / 'var/runtime'
        self.engine = Inference(self.root, self.ledgers, self.store)
        self.key = patch('webapp.transport.api_key_for', return_value='invented-test-only')
        self.key.start()
        self.addCleanup(self.key.stop)

    def provider_reply(self, result):
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(result)}}], 'usage': {'cost': .001}}).encode())

    def pause_after_inventory(self):
        def stage(name):
            if name == 'Comparing manufacturer references':
                raise SystemExit('Simulated process exit after durable inventory')
        with patch('webapp.transport.urllib.request.urlopen', return_value=self.provider_reply({'objects': [target()]})) as network:
            with self.assertRaises(SystemExit):
                self.engine.run(self.job, stage)
        self.assertEqual(network.call_count, 1)

    def test_resume_keeps_frozen_config_and_reuses_inventory_without_second_charge(self):
        self.pause_after_inventory()
        folder = self.ledgers / self.job['id']
        frozen = (folder / 'frozen_config.json').read_bytes()
        self.assertTrue(can_resume_job(self.ledgers, self.job['id']))
        compared = response(self.job['_snapshot'])
        result = compared['results'][0]['result']
        result['evidence_conflict'] = False
        for check in result['feature_checks']:
            check['reference_view'] = 'plate'
        with patch.object(Client, '_wait'), patch('webapp.transport.urllib.request.urlopen', return_value=self.provider_reply(compared)) as network:
            matches = Inference(self.root, self.ledgers, self.store).run(self.job, lambda stage: None)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(matches[0]['product_id'], 'dyson_v15_detect')
        self.assertEqual((folder / 'frozen_config.json').read_bytes(), frozen)
        records = [json.loads(x) for x in (folder / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertAlmostEqual(ledger_accounting(self.ledgers)['spent_inr'], .2)

    def test_unstarted_job_is_recoverable_but_unsafe_ids_are_not(self):
        self.assertTrue(can_resume_job(self.ledgers, self.job['id']))
        self.assertFalse(can_resume_job(self.ledgers, '../outside'))

    def test_app_startup_requeues_and_finishes_after_durable_inventory(self):
        self.store.claim_job(self.job['id'])
        self.pause_after_inventory()
        compared = response(self.job['_snapshot'])
        compared['results'][0]['result']['evidence_conflict'] = False
        for check in compared['results'][0]['result']['feature_checks']:
            check['reference_view'] = 'plate'
        app = app_server.build_app(self.root, start_worker=False)
        self.addCleanup(app.close)
        self.assertEqual(app.store.job(self.job['id'])['status'], 'queued')
        with patch.object(Client, '_wait'), patch('webapp.transport.urllib.request.urlopen', return_value=self.provider_reply(compared)) as network:
            app.process_job(self.job['id'])
        saved = app.store.job(self.job['id'])
        self.assertEqual(saved['status'], 'completed')
        self.assertTrue(saved['exports_available'])
        self.assertEqual(network.call_count, 1)
        self.assertAlmostEqual(saved['cost_inr'], .2)

    def test_cached_inventory_does_not_bypass_current_budget_for_next_call(self):
        self.pause_after_inventory()
        other = self.ledgers / 'other'
        other.mkdir()
        limit = min(RUNTIME_CAP_INR, STAGE_CAP_INR - HISTORICAL_STAGE_GUARD_INR)
        (other / 'inflight.json').write_text(json.dumps({'unknown': {'reserved_cost_usd': (limit - .2) / 100}}))
        with patch('webapp.transport.urllib.request.urlopen') as network:
            with self.assertRaises(BudgetError):
                self.engine.run(self.job, lambda stage: None)
        network.assert_not_called()
        self.assertAlmostEqual(ledger_accounting(self.ledgers)['spent_inr'], limit - .1)

    def test_unresolved_request_or_failed_validation_blocks_automatic_resume(self):
        self.pause_after_inventory()
        folder = self.ledgers / self.job['id']
        config = json.loads((folder / 'frozen_config.json').read_text())
        records = [json.loads(x) for x in (folder / 'calls.jsonl').read_text().splitlines()]
        pending = {self.job['id'] + ':comparison': {'config_sha256': records[0]['config_sha256'], 'reserved_cost_usd': .01}}
        (folder / 'inflight.json').write_text(json.dumps(pending))
        self.assertFalse(can_resume_job(self.ledgers, self.job['id']))
        (folder / 'inflight.json').write_text('{}')
        (folder / 'error.json').write_text('{"type":"ValueError"}')
        self.assertFalse(can_resume_job(self.ledgers, self.job['id']))
        (folder / 'error.json').unlink()
        with (folder / 'calls.jsonl').open('a') as out:
            out.write(json.dumps({**records[0], 'status': 'validation_error'}) + '\n')
        self.assertFalse(can_resume_job(self.ledgers, self.job['id']))

    def test_settled_pending_is_safe_but_config_drift_is_not(self):
        self.pause_after_inventory()
        folder = self.ledgers / self.job['id']
        row = json.loads((folder / 'calls.jsonl').read_text())
        (folder / 'inflight.json').write_text(json.dumps({row['job_id']: row}))
        self.assertTrue(can_resume_job(self.ledgers, self.job['id']))
        cfg = json.loads((folder / 'frozen_config.json').read_text())
        cfg['models']['flash37high']['thinking_level'] = 'low'
        (folder / 'frozen_config.json').write_text(json.dumps(cfg))
        self.assertFalse(can_resume_job(self.ledgers, self.job['id']))

    def test_corrupt_or_mismatched_ledger_is_not_resumable(self):
        self.pause_after_inventory()
        folder = self.ledgers / self.job['id']
        original = (folder / 'calls.jsonl').read_text()
        for broken in ('not-json', '[]\n', original.replace('"status":"ok"', '"status":"error"')):
            (folder / 'calls.jsonl').write_text(broken)
            self.assertFalse(can_resume_job(self.ledgers, self.job['id']))
        (folder / 'calls.jsonl').write_text(original)
        cfg = json.loads((folder / 'frozen_config.json').read_text())
        cfg['budget']['total_max_inr'] = 999999
        (folder / 'frozen_config.json').write_text(json.dumps(cfg))
        self.assertFalse(can_resume_job(self.ledgers, self.job['id']))
