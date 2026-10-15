"""Offline tests for pipeline request construction, persistence and cost limits."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import pipeline_api as api


def reply(result=None, cost=0.001):
    return {'model': 'test-model', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result or {'status': 'ok'})}}], 'usage': {'cost': cost, 'prompt_tokens': 10, 'completion_tokens': 10}}


class PipelineApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photo = self.root / 'photo.jpg'
        self.photo.write_bytes(b'image-for-mocked-transport')
        self.config = {'models': {'test': {'provider': 'openrouter', 'model': 'test-model', 'input_usd_per_million': 1, 'output_usd_per_million': 2, 'max_output_tokens': 1000, 'input_token_bound': 1000}}, 'embedding': {'model': 'gemini-embedding-2', 'dimensions': 3072, 'usd_per_image': 0.00012}, 'budget': {'stage_max_inr': 400, 'total_max_inr': 2000, 'prior_accounted_inr': 42.68, 'usd_inr': 100}}
        self.client = api.Client(self.config, self.root, self.root / 'out')
        self.key = patch.object(api, 'api_key_for', return_value='test-secret')
        self.key.start()
        self.addCleanup(self.key.stop)

    def generate(self, job='first', prompt='Return JSON', client=None):
        return (client or self.client).generate(job, 'test', prompt, [('Scene', self.photo)])

    def response(self, value):
        return io.BytesIO(json.dumps(value).encode())

    def rows(self):
        return [json.loads(line) for line in self.client.calls_path.read_text().splitlines()]

    def test_shape_reservation_persistence_and_cache(self):
        def network(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload['response_format'], {'type': 'json_object'})
            self.assertEqual(payload['provider']['max_price'], {'prompt': 1, 'completion': 2})
            self.assertFalse(payload['provider']['allow_fallbacks'])
            self.assertEqual(payload['reasoning'], {'enabled': False})
            self.assertEqual(len(payload['messages'][1]['content']), 3)
            pending = json.loads(self.client.pending_path.read_text())
            self.assertEqual(pending['first']['reserved_cost_usd'], 0.003)
            self.assertNotIn('test-secret', self.client.pending_path.read_text())
            return self.response(reply())
        with patch.object(api.urllib.request, 'urlopen', side_effect=network) as network:
            self.assertEqual(self.generate(), {'status': 'ok'})
            restored = api.Client(self.config, self.root, self.root / 'out')
            self.assertEqual(self.generate(client=restored), {'status': 'ok'})
            self.assertEqual(network.call_count, 1)
        self.assertEqual(self.client.accounted_cost_usd, 0.001)
        self.assertEqual(json.loads(self.client.pending_path.read_text()), {})
        self.assertEqual(self.rows()[0]['provider_response']['model'], 'test-model')

    def test_request_and_config_mismatch_stop(self):
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply())):
            self.generate()
        with self.assertRaisesRegex(ValueError, 'Request changed'):
            self.generate(prompt='Changed prompt')
        self.config['budget']['stage_max_inr'] = 300
        with self.assertRaisesRegex(ValueError, 'Config changed'):
            api.Client(self.config, self.root, self.root / 'out')

    def test_parse_error_keeps_reported_cost_and_stops(self):
        response = reply(cost=0.002)
        response['choices'][0]['message']['content'] = 'invalid JSON'
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(response)) as network:
            with self.assertRaises(RuntimeError):
                self.generate()
            with self.assertRaisesRegex(RuntimeError, 'Previously failed'):
                self.generate()
            with self.assertRaisesRegex(RuntimeError, 'stopped'):
                self.generate(job='second')
            self.assertEqual(network.call_count, 1)
        self.assertEqual(self.client.accounted_cost_usd, 0.002)
        self.assertEqual(self.rows()[0]['status'], 'error')

    def test_network_error_keeps_unknown_reserve_and_redacts(self):
        with patch.object(api.urllib.request, 'urlopen', side_effect=OSError('bad test-secret')):
            with self.assertRaisesRegex(RuntimeError, 'REDACTED'):
                self.generate()
        self.assertEqual(self.client.accounted_cost_usd, 0.003)
        self.assertNotIn('test-secret', self.client.calls_path.read_text())

    def test_budget_accounts_for_threads_inflight(self):
        self.client.cap_usd = 0.004
        entered, release = threading.Event(), threading.Event()
        errors = []
        def network(request, timeout):
            entered.set()
            release.wait(2)
            return self.response(reply())
        def first():
            try:
                self.generate()
            except Exception as error:
                errors.append(error)
        with patch.object(api.urllib.request, 'urlopen', side_effect=network) as network:
            thread = threading.Thread(target=first)
            thread.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaisesRegex(RuntimeError, 'budget stop'):
                self.generate(job='second')
            release.set()
            thread.join(3)
            self.assertFalse(errors)
            self.assertEqual(network.call_count, 1)

    def test_crash_reservation_blocks_resume(self):
        self.client._atomic_json(self.client.pending_path, {'lost': {'config_sha256': self.client.config_sha256, 'reserved_cost_usd': 0.003}})
        restored = api.Client(self.config, self.root, self.root / 'out')
        self.assertEqual(restored.accounted_cost_usd, 0.003)
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            self.generate(client=restored)

    def test_native_request_and_thinking_usage(self):
        config = copy.deepcopy(self.config)
        config['models']['test'].update(provider='gemini', thinking_level='low')
        client = api.Client(config, self.root, self.root / 'native')
        response = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"status":"ok"}'}]}}], 'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 100, 'thoughtsTokenCount': 100}}
        def network(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload['generationConfig']['responseFormat']['text']['mimeType'], 'APPLICATION_JSON')
            self.assertEqual(payload['generationConfig']['thinkingConfig']['thinkingLevel'], 'LOW')
            return self.response(response)
        with patch.object(api.urllib.request, 'urlopen', side_effect=network):
            self.generate(client=client)
        self.assertAlmostEqual(client.accounted_cost_usd, 0.0005)

    def test_embedding_single_image_and_validation(self):
        def network(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload['outputDimensionality'], 3072)
            self.assertEqual(len(payload['content']['parts']), 1)
            self.assertIn('inlineData', payload['content']['parts'][0])
            return self.response({'embedding': {'values': [1.0] + [0] * 3071}})
        with patch.object(api.urllib.request, 'urlopen', side_effect=network):
            self.assertEqual(len(self.client.embed('embedding', self.photo)), 3072)
        self.assertEqual(self.client.accounted_cost_usd, 0.00012)
        self.assertEqual(self.rows()[0]['cost_basis'], 'published_per_image_estimate')
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response({'embedding': {'values': [0] * 3072}})):
            with self.assertRaisesRegex(RuntimeError, 'Invalid embedding'):
                self.client.embed('zero', self.photo)
        self.assertEqual(self.client.accounted_cost_usd, 0.00024)

    def test_domain_failure_preserves_cost_on_restart(self):
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply())):
            self.generate()
        self.client.record_validation_failure('first', 'Missing decision')
        restored = api.Client(self.config, self.root, self.root / 'out')
        self.assertEqual(restored.accounted_cost_usd, 0.001)
        with self.assertRaisesRegex(RuntimeError, 'Previously failed'):
            self.generate(client=restored)
        self.assertEqual(len(self.rows()), 2)

    def test_offline_recovery_keeps_cost_and_original_response(self):
        raw = {'decision': {'status': 'not_in_catalogue', 'top_two': None}}
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply(raw))):
            self.generate()
        self.client.record_validation_failure('first', 'top_two is null')
        def validate(result):
            self.assertEqual(result['decision']['status'], 'not_in_catalogue')
            result['decision']['top_two'] = []
            return result
        restored = api.Client(self.config, self.root, self.root / 'out')
        with patch.object(api.urllib.request, 'urlopen', side_effect=AssertionError('Must stay offline')) as network:
            fixed = restored.recover_validation('first', validate)
            self.assertEqual(self.generate(client=restored), fixed)
            network.assert_not_called()
        self.assertEqual(fixed['decision']['top_two'], [])
        self.assertEqual(self.rows()[0]['result'], raw)
        self.assertEqual(self.rows()[-1]['estimated_cost_usd'], 0)
        self.assertEqual(self.rows()[-1]['recovery']['original_response_line'], 1)
        self.assertFalse(restored.failure)
        self.assertEqual(api.Client(self.config, self.root, self.root / 'out').accounted_cost_usd, 0.001)

    def test_offline_recovery_rejects_network_failure_and_failed_validator(self):
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply())):
            self.generate()
        self.client.record_validation_failure('first', 'invalid domain fields')
        def invalid(result):
            raise ValueError('Still invalid')
        with self.assertRaisesRegex(ValueError, 'Still invalid'):
            self.client.recover_validation('first', invalid)
        self.assertEqual(len(self.rows()), 2)
        self.assertTrue(self.client.failure)
        separate = api.Client(self.config, self.root, self.root / 'network-failure')
        with patch.object(api.urllib.request, 'urlopen', side_effect=OSError('offline')):
            with self.assertRaises(RuntimeError):
                self.generate(client=separate)
        with self.assertRaisesRegex(ValueError, 'Only domain-validation'):
            separate.recover_validation('first', lambda result: result)

    def test_actual_cost_over_reservation_is_recorded_then_stops(self):
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply(cost=0.01))):
            with self.assertRaisesRegex(RuntimeError, 'exceeded'):
                self.generate()
        self.assertEqual(self.client.accounted_cost_usd, 0.01)


if __name__ == '__main__':
    unittest.main()
