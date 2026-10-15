"""Offline budget and immutable-history checks for the authorised retry run."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_slow_comparison as slow
from run_pipeline import sha


class SlowComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = {'budget': {'usd_inr': 100, 'stage_max_inr': 200, 'prior_accounted_inr': 242.68}, 'stage_ceiling_inr': 400, 'prior_stage_accounted_inr': 42.68, 'previous_ledgers': []}
        for folder, cost in [('old', .94), ('revised', 1.06)]:
            out = self.root / folder
            out.mkdir()
            path = out / 'calls.jsonl'
            path.write_text(json.dumps({'estimated_cost_usd': cost}) + '\n')
            (out / 'inflight.json').write_text('{}')
            self.config['previous_ledgers'].append({'file': str(path.relative_to(self.root)), 'sha256': sha(path), 'accounted_cost_usd': cost})

    def test_two_histories_counted_once(self):
        rows = slow.verify_history(self.config, self.root)
        self.assertAlmostEqual(sum(r['estimated_cost_usd'] for r in rows), 2)
        self.assertEqual(len(rows), 2)

    def test_modified_history_or_unsettled_spend_stops(self):
        path = self.root / 'revised/calls.jsonl'
        path.write_text(path.read_text() + '{}\n')
        with self.assertRaisesRegex(ValueError, 'ledger changed'):
            slow.verify_history(self.config, self.root)
        self.config['previous_ledgers'][1]['sha256'] = sha(path)
        (self.root / 'revised/inflight.json').write_text('{"pending":{}}')
        with self.assertRaisesRegex(ValueError, 'in flight'):
            slow.verify_history(self.config, self.root)

    def test_cannot_increase_cap_or_omit_prior_spending(self):
        for key in ['stage_max_inr', 'prior_accounted_inr']:
            changed = copy.deepcopy(self.config)
            changed['budget'][key] += 1
            with self.assertRaises(ValueError):
                slow.verify_history(changed, self.root)

    def test_report_refuses_unsettled_requests(self):
        (self.root / 'inflight.json').write_text('{"pending":{}}')
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            slow.combined_study({}, [], new=self.root)

    def test_requested_settings_and_identical_gemini(self):
        root = Path(__file__).resolve().parents[1]
        old = json.loads((root / 'data/pipeline_high_reasoning_config.json').read_text())
        config = json.loads((root / 'data/pipeline_slow_comparison_config.json').read_text())
        self.assertEqual(config['requested_models'], ['flash37high', 'solhigh'])
        self.assertEqual(config['models']['flash37high'], old['models']['flash37high'])
        self.assertEqual(config['models']['solhigh']['thinking_level'], 'high')
        self.assertEqual(config['premium_subset_ids'], old['premium_subset_ids'])
        for key in ['reference_pack_sha256', 'telling_details_sha256', 'test_manifest_sha256', 'confidence_threshold']:
            self.assertEqual(config[key], old[key])
        self.assertEqual(config['rate_limit_policy']['request_interval_seconds'], 15)


if __name__ == '__main__':
    unittest.main()
