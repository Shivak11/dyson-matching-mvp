"""Offline checks for the frozen baseline's score, billing and decision boundaries."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('baseline', Path(__file__).resolve().parents[1] / 'tools/run_baseline.py')
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((b.ROOT / 'data/baseline_config.json').read_text())

    def test_rejections_threshold_boundary_and_ties(self):
        order = ['a', 'b', 'c']
        self.assertEqual(b.decide({'a': 79.9, 'b': 20, 'c': 30}, order, 80)['status'], 'not_in_catalogue')
        self.assertEqual(b.decide({'a': 80, 'b': 79, 'c': 20}, order, 80)['product'], 'a')
        tied = b.decide({'a': 90, 'b': 90, 'c': 20}, order, 90)
        self.assertEqual((tied['status'], tied['top_two']), ('not_sure', ['a', 'b']))

    def test_invalid_scores_and_truncation_fail(self):
        for score in [-1, 101, True, '90', float('nan')]:
            response = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps({'similarity_score': score, 'reason': 'Visible shape'})}]}}]}
            with self.assertRaises(ValueError):
                b.parse_score(response)
        with self.assertRaises(ValueError):
            b.parse_score({'candidates': [{'finishReason': 'MAX_TOKENS'}]})

    def test_cost_includes_thinking_and_cache_discount(self):
        usage = {'promptTokenCount': 1000, 'cachedContentTokenCount': 200, 'candidatesTokenCount': 100, 'thoughtsTokenCount': 400}
        self.assertAlmostEqual(b.usage_cost(usage, self.config['pricing']), 0.00662)
        with self.assertRaises(ValueError):
            b.usage_cost({'promptTokenCount': 10, 'cachedContentTokenCount': 11}, self.config['pricing'])

    def test_budget_reserves_all_inflight_requests(self):
        self.assertTrue(b.budget_allows(5.75, 4, 0.06048, 6))
        self.assertFalse(b.budget_allows(5.8, 4, 0.06048, 6))

    def test_payload_contains_only_two_images_and_fixed_text(self):
        request = b.payload({'inlineData': {'data': 'QUERY'}}, {'inlineData': {'data': 'REFERENCE'}}, self.config)
        parts = request['contents'][0]['parts']
        self.assertEqual(sum('inlineData' in part for part in parts), 2)
        self.assertEqual([part['text'] for part in parts if 'text' in part], [self.config['prompt'], 'Image A:', 'Image B:'])
        self.assertEqual(request['generationConfig']['responseFormat']['text']['mimeType'], 'APPLICATION_JSON')
        self.assertNotIn('source_url', json.dumps(request))
        self.assertNotIn('dyson_v8_absolute', json.dumps(request))

    def test_summary_scores_wrong_high_confidence_and_rejections(self):
        rows = [{'image_id': 'P001', 'labels': ['a'], 'evaluation_role': 'labelled_single'}, {'image_id': 'P002', 'labels': ['NONCAT_x'], 'evaluation_role': 'labelled_single'}]
        config = dict(self.config, catalogue_order=['a', 'b'], thresholds=[90])
        calls = [{'image_id': i, 'catalogue_id': p, 'status': 'ok', 'config_sha256': 'fixed', 'result': {'similarity_score': score}, 'estimated_cost_usd': 0.01} for i, p, score in [('P001', 'a', 80), ('P001', 'b', 95), ('P002', 'a', 30), ('P002', 'b', 20)]]
        with tempfile.TemporaryDirectory() as d, patch.object(b, 'OUT', Path(d)), patch.object(b, 'ledger_rows', return_value=calls), patch('builtins.print'):
            b.summarize(config, 'fixed', rows)
            result = json.loads((Path(d) / 'summary.json').read_text())['thresholds']['90']
            self.assertEqual(result['correct_total'], 1)
            self.assertEqual(result['confidently_wrong_count'], 1)
            self.assertEqual(result['correct_non_catalogue_rejections'], 1)
            self.assertEqual(result['verification_pair_counts'], {'true_accept': 0, 'false_accept': 1, 'true_reject': 2, 'false_reject': 1})
            with patch.object(b, 'ledger_rows', return_value=calls[:-1]), self.assertRaises(AssertionError):
                b.summarize(config, 'fixed', rows)

    def test_resume_rejects_changed_configuration(self):
        with tempfile.TemporaryDirectory() as d, patch.object(b, 'OUT', Path(d)):
            (Path(d) / 'calls.jsonl').write_text(json.dumps({'config_sha256': 'old'}) + '\n')
            with self.assertRaises(AssertionError):
                b.ledger_rows('new')

class OpenRouterTests(unittest.TestCase):
    def test_json_response_and_reported_cost(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"similarity_score": 85, "reason": "Visible product shape"}'}}]}
        self.assertEqual(b.parse_score(response)[0]['similarity_score'], 85)
        self.assertAlmostEqual(b.usage_cost({'cost': 0.000123}, {}), 0.000123)
        with self.assertRaises(ValueError):
            b.usage_cost({'cost': -1}, {})

    def test_openrouter_payload_preserves_two_images_without_labels(self):
        config = json.loads((b.ROOT / 'data/baseline_qwen_config.json').read_text())
        request = b.payload({'inlineData': {'mimeType': 'image/jpeg', 'data': 'QUERY'}}, {'inlineData': {'mimeType': 'image/jpeg', 'data': 'REFERENCE'}}, config)
        content = request['messages'][1]['content']
        self.assertEqual([p['image_url']['url'] for p in content if p['type'] == 'image_url'], ['data:image/jpeg;base64,QUERY', 'data:image/jpeg;base64,REFERENCE'])
        self.assertEqual(request['provider']['max_price'], {'prompt': 0.035, 'completion': 0.15})
        self.assertEqual(request['response_format'], {'type': 'json_object'})
        self.assertNotIn('source_url', json.dumps(request))

    def test_ignored_local_env_reads_only_named_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(b, 'ROOT', Path(directory)), patch.dict(b.os.environ, {}, clear=True):
            (Path(directory) / '.env').write_text('OTHER_KEY=unrelated\nOPENROUTER_API_KEY="unit-test-value" # comment\n')
            self.assertEqual(b.api_key_for('OPENROUTER_API_KEY'), 'unit-test-value')
            with self.assertRaises(RuntimeError):
                b.api_key_for('MISSING_KEY')


if __name__ == '__main__':
    unittest.main()
