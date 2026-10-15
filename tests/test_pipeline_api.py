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

    def rate_error(self, status=429, retry_after=None):
        headers = {} if retry_after is None else {'Retry-After': retry_after}
        return api.urllib.error.HTTPError('https://example.invalid', status, 'Rate limit', headers, io.BytesIO(b'{"error":"temporarily unavailable"}'))

    def fake_clock(self):
        clock = {'now': 100.0, 'sleeps': []}
        def sleep(seconds):
            clock['sleeps'].append(seconds)
            clock['now'] += seconds
        for mocked in (patch.object(api.time, 'monotonic', side_effect=lambda: clock['now']), patch.object(api.time, 'sleep', side_effect=sleep), patch.object(api.random, 'uniform', return_value=0)):
            mocked.start()
            self.addCleanup(mocked.stop)
        return clock

    def test_rate_limit_attempts_are_metered_and_restart_uses_logical_cache(self):
        clock = self.fake_clock()
        client = api.Client(self.config, self.root, self.root / 'slow', rate_limit_retries=2, request_interval_seconds=15)
        with patch.object(api.urllib.request, 'urlopen', side_effect=[self.rate_error(), self.response(reply())]) as network:
            self.assertEqual(self.generate(client=client), {'status': 'ok'})
            restored = api.Client(self.config, self.root, self.root / 'slow', rate_limit_retries=2, request_interval_seconds=15)
            self.assertEqual(self.generate(client=restored), {'status': 'ok'})
            self.assertEqual(network.call_count, 2)
        rows = [json.loads(line) for line in client.calls_path.read_text().splitlines()]
        self.assertEqual([row['job_id'] for row in rows], ['first:attempt:1', 'first:attempt:2'])
        self.assertEqual([row['logical_job_id'] for row in rows], ['first', 'first'])
        self.assertEqual([row['http_status'] for row in rows], [429, 200])
        self.assertAlmostEqual(restored.accounted_cost_usd, 0.004)
        self.assertEqual(json.loads(client.pending_path.read_text()), {})
        self.assertEqual(sum(clock['sleeps']), 60)
        self.assertLessEqual(max(clock['sleeps']), 30)
        self.assertFalse(restored.failure)

    def test_prior_success_reuses_exact_request_without_new_ledger_cost(self):
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply())):
            self.generate()
        original = self.client.calls_path.read_bytes()
        client = api.Client(self.config, self.root, self.root / 'reuse', reuse_records=self.rows())
        with patch.object(api.urllib.request, 'urlopen') as network:
            self.assertEqual(self.generate(client=client), {'status': 'ok'})
            with self.assertRaisesRegex(ValueError, 'Request changed'):
                self.generate(prompt='Changed', client=client)
            network.assert_not_called()
        self.assertEqual(client.reused_jobs, {'first'})
        self.assertEqual(client.accounted_cost_usd, 0)
        self.assertFalse(client.calls_path.exists())
        self.assertEqual(self.client.calls_path.read_bytes(), original)

    def test_prior_rate_limit_gets_one_new_attempt_without_changing_history(self):
        self.fake_clock()
        with patch.object(api.urllib.request, 'urlopen', side_effect=self.rate_error()):
            with self.assertRaises(RuntimeError):
                self.generate()
        original = self.client.calls_path.read_bytes()
        historical = self.rows()
        historical[0].pop('http_status')
        historical[0]['error'] = 'HTTP Error 429: Too Many Requests'
        client = api.Client(self.config, self.root, self.root / 'new-attempt', reuse_records=historical)
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply())) as network:
            self.generate(client=client)
            self.assertEqual(network.call_count, 1)
        row, = [json.loads(line) for line in client.calls_path.read_text().splitlines()]
        self.assertEqual(row['job_id'], 'first:attempt:1')
        self.assertAlmostEqual(client.accounted_cost_usd, 0.001)
        self.assertEqual(self.client.calls_path.read_bytes(), original)

    def test_reused_domain_validation_failure_is_zero_cost_and_stops(self):
        with patch.object(api.urllib.request, 'urlopen', return_value=self.response(reply())):
            self.generate()
        original = self.client.calls_path.read_bytes()
        client = api.Client(self.config, self.root, self.root / 'reused-invalid', reuse_records=self.rows())
        self.generate(client=client)
        client.record_validation_failure('first', 'Invalid domain fields')
        self.assertEqual(client.accounted_cost_usd, 0)
        self.assertTrue(client.failure)
        row, = [json.loads(line) for line in client.calls_path.read_text().splitlines()]
        self.assertEqual(row['status'], 'validation_error')
        self.assertEqual(row['config_sha256'], client.config_sha256)
        self.assertEqual(row['reused_record_sha256'], api.digest(api.encoded(self.rows()[0])))
        restored = api.Client(self.config, self.root, client.out, reuse_records=self.rows())
        with patch.object(api.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(RuntimeError, 'Previously failed'):
                self.generate(client=restored)
            network.assert_not_called()
        self.assertEqual(self.client.calls_path.read_bytes(), original)

    def test_default_rate_limit_is_never_retried(self):
        with patch.object(api.urllib.request, 'urlopen', side_effect=self.rate_error()) as network:
            with self.assertRaises(RuntimeError):
                self.generate()
            with self.assertRaisesRegex(RuntimeError, 'Previously failed'):
                self.generate()
            self.assertEqual(network.call_count, 1)
        self.assertEqual(self.rows()[0]['job_id'], 'first')
        self.assertTrue(self.client.failure)

    def test_non429_and_parse_failures_are_never_retried_under_slow_policy(self):
        for index, error in enumerate((self.rate_error(500), TimeoutError('timeout'), self.response({'choices': []}))):
            client = api.Client(self.config, self.root, self.root / ('terminal-' + str(index)), rate_limit_retries=3)
            arguments = {'side_effect': error} if isinstance(error, Exception) else {'return_value': error}
            with patch.object(api.urllib.request, 'urlopen', **arguments) as network:
                with self.assertRaises(RuntimeError):
                    self.generate(client=client)
                with self.assertRaisesRegex(RuntimeError, 'stopped'):
                    self.generate(job='other', client=client)
                self.assertEqual(network.call_count, 1)
            self.assertTrue(client.failure)

    def test_retry_cap_and_failed_attempt_cost_survive_restart(self):
        clock = self.fake_clock()
        client = api.Client(self.config, self.root, self.root / 'exhaust', rate_limit_retries=2)
        with patch.object(api.urllib.request, 'urlopen', side_effect=[self.rate_error(), self.rate_error(), self.rate_error()]) as network:
            with self.assertRaises(RuntimeError):
                self.generate(client=client)
            self.assertEqual(network.call_count, 3)
        self.assertEqual(sum(clock['sleeps']), 180)
        restored = api.Client(self.config, self.root, self.root / 'exhaust', rate_limit_retries=2)
        self.assertAlmostEqual(restored.accounted_cost_usd, 0.009)
        self.assertTrue(restored.failure)
        with patch.object(api.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(RuntimeError, 'Previously failed'):
                self.generate(client=restored)
            with self.assertRaisesRegex(RuntimeError, 'stopped'):
                self.generate(job='other', client=restored)
            network.assert_not_called()

    def test_budget_stops_before_second_attempt_and_keeps_failed_reserve(self):
        self.fake_clock()
        client = api.Client(self.config, self.root, self.root / 'retry-budget', rate_limit_retries=3)
        client.cap_usd = 0.005
        with patch.object(api.urllib.request, 'urlopen', side_effect=self.rate_error()) as network:
            with self.assertRaisesRegex(RuntimeError, 'budget stop'):
                self.generate(client=client)
            self.assertEqual(network.call_count, 1)
        self.assertEqual(client.accounted_cost_usd, 0.003)
        self.assertEqual(json.loads(client.pending_path.read_text()), {})

    def test_retry_after_and_pacing_use_chunked_waits(self):
        clock = self.fake_clock()
        client = api.Client(self.config, self.root, self.root / 'paced', rate_limit_retries=1, request_interval_seconds=15)
        starts = []
        outcomes = [self.rate_error(retry_after='75'), self.response(reply()), self.response(reply())]
        def network(request, timeout):
            starts.append(clock['now'])
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        with patch.object(api.urllib.request, 'urlopen', side_effect=network):
            self.generate(client=client)
            self.generate(job='second', client=client)
        self.assertEqual(starts, [100, 175, 190])
        self.assertLessEqual(max(clock['sleeps']), 30)
        with patch.object(api.time, 'time', return_value=0):
            self.assertEqual(api.Client._retry_after('Thu, 01 Jan 1970 00:02:00 GMT'), 120)
        for invalid in ('nan', 'inf', '-1', 'bad header', 'x' * 257):
            self.assertIsNone(api.Client._retry_after(invalid))

    def test_finish_to_start_pause_survives_restart(self):
        clock = self.fake_clock()
        client = api.Client(self.config, self.root, self.root / 'finish-paced', rate_limit_retries=1, request_interval_seconds=15)
        starts = []
        def network(request, timeout):
            starts.append(clock['now'])
            clock['now'] += 10
            return self.response(reply())
        with patch.object(api.time, 'time', side_effect=lambda: clock['now']), patch.object(api.urllib.request, 'urlopen', side_effect=network):
            self.generate(client=client)
            restored = api.Client(self.config, self.root, client.out, rate_limit_retries=1, request_interval_seconds=15)
            self.generate(job='second', client=restored)
        self.assertEqual(starts, [100, 125])
        self.assertEqual(sum(clock['sleeps']), 15)
        self.assertEqual(client.logical_records['first']['request_finished_unix'], 110)

    def test_unrecovered_non429_history_blocks_slow_policy(self):
        with patch.object(api.urllib.request, 'urlopen', side_effect=self.rate_error(500)):
            with self.assertRaises(RuntimeError):
                self.generate()
        client = api.Client(self.config, self.root, self.root / 'blocked-history', reuse_records=self.rows(), rate_limit_retries=3)
        with patch.object(api.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(RuntimeError, 'stopped'):
                self.generate(job='other', client=client)
            network.assert_not_called()

    def test_retry_after_over_maximum_stops_without_truncating_wait(self):
        clock = self.fake_clock()
        client = api.Client(self.config, self.root, self.root / 'long-wait', rate_limit_retries=3, max_retry_delay_seconds=300)
        with patch.object(api.urllib.request, 'urlopen', side_effect=self.rate_error(retry_after='301')) as network:
            with self.assertRaises(RuntimeError):
                self.generate(client=client)
            self.assertEqual(network.call_count, 1)
        self.assertFalse(clock['sleeps'])
        self.assertTrue(client.failure)
        self.assertTrue(client.logical_records['first']['retry_exhausted'])
        self.assertEqual(client.logical_records['first']['retry_delay_seconds'], 301)

    def test_stop_during_backoff_prevents_another_request(self):
        clock = self.fake_clock()
        client = api.Client(self.config, self.root, self.root / 'stop-wait', rate_limit_retries=3)
        def stop_sleep(seconds):
            clock['now'] += seconds
            (client.out / 'STOP').touch()
        with patch.object(api.time, 'sleep', side_effect=stop_sleep), patch.object(api.urllib.request, 'urlopen', side_effect=self.rate_error()) as network:
            with self.assertRaisesRegex(RuntimeError, 'STOP file'):
                self.generate(client=client)
            self.assertEqual(network.call_count, 1)
        self.assertEqual(json.loads(client.pending_path.read_text()), {})

    def test_invalid_retry_controls_fail_before_network(self):
        invalid = [('rate_limit_retries', value) for value in (-1, True, 1.5, '3')]
        invalid += [('request_interval_seconds', value) for value in (-1, True, float('inf'))]
        invalid += [('max_retry_delay_seconds', value) for value in (-1, True, float('nan'))]
        with patch.object(api.urllib.request, 'urlopen') as network:
            for index, (field, value) in enumerate(invalid):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    api.Client(self.config, self.root, self.root / ('bad-control-' + str(index)), **{field: value})
            network.assert_not_called()

    def test_shape_reservation_persistence_and_cache(self):
        def network(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload['response_format'], {'type': 'json_object'})
            self.assertEqual(payload['provider']['max_price'], {'prompt': 1, 'completion': 2})
            self.assertFalse(payload['provider']['allow_fallbacks'])
            self.assertNotIn('only', payload['provider'])
            self.assertEqual(timeout, 180)
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

    def test_explicit_provider_max_effort_and_timeout(self):
        config = copy.deepcopy(self.config)
        config['models']['test'].update(provider_only=['Google AI Studio'], thinking_level='max', request_timeout_seconds=600)
        client = api.Client(config, self.root, self.root / 'pinned')
        def network(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload['provider']['only'], ['Google AI Studio'])
            self.assertFalse(payload['provider']['allow_fallbacks'])
            self.assertEqual(payload['reasoning'], {'effort': 'max'})
            self.assertEqual(timeout, 600)
            return self.response(reply())
        with patch.object(api.urllib.request, 'urlopen', side_effect=network) as network:
            self.generate(client=client)
            self.assertEqual(network.call_count, 1)

    def test_invalid_optional_controls_fail_before_network(self):
        invalid = [('request_timeout_seconds', value) for value in (0, -1, True, None, '600', float('nan'), float('inf'))]
        invalid += [('provider_only', value) for value in ([], None, 'Google', [''], ['  '], [True], ['Google', 1])]
        with patch.object(api.urllib.request, 'urlopen') as network:
            for index, (key, value) in enumerate(invalid):
                with self.subTest(key=key, value=value):
                    config = copy.deepcopy(self.config)
                    config['models']['test'][key] = value
                    with self.assertRaises(ValueError):
                        client = api.Client(config, self.root, self.root / ('invalid-' + str(index)))
                        self.generate(client=client)
            network.assert_not_called()

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

    def test_default_parallel_success_does_not_block_active_requests(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def network(request, timeout):
            if json.loads(request.data)['messages'][1]['content'][0]['text'] == 'Wait':
                entered.set()
                release.wait(2)
            return self.response(reply())
        def waiting():
            try:
                self.generate(job='waiting', prompt='Wait')
            except Exception as error:
                errors.append(error)
        with patch.object(api.urllib.request, 'urlopen', side_effect=network) as network:
            thread = threading.Thread(target=waiting)
            thread.start()
            self.assertTrue(entered.wait(2))
            self.generate(job='second')
            self.assertFalse(self.client.failure)
            self.generate(job='third')
            release.set()
            thread.join(3)
            self.assertFalse(errors)
            self.assertEqual(network.call_count, 3)

    def test_crash_reservation_blocks_resume(self):
        self.client._atomic_json(self.client.pending_path, {'lost': {'config_sha256': self.client.config_sha256, 'reserved_cost_usd': 0.003}})
        restored = api.Client(self.config, self.root, self.root / 'out')
        self.assertEqual(restored.accounted_cost_usd, 0.003)
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            self.generate(client=restored)

    def test_native_request_and_thinking_usage(self):
        config = copy.deepcopy(self.config)
        config['models']['test'].update(provider='gemini', thinking_level='low', request_timeout_seconds=420)
        client = api.Client(config, self.root, self.root / 'native')
        response = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"status":"ok"}'}]}}], 'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 100, 'thoughtsTokenCount': 100}}
        def network(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload['generationConfig']['responseFormat']['text']['mimeType'], 'APPLICATION_JSON')
            self.assertEqual(payload['generationConfig']['thinkingConfig']['thinkingLevel'], 'LOW')
            self.assertEqual(timeout, 420)
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
