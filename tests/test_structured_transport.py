"""Strict provider schemas and local shape checks preserve metered requests."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from webapp import transport


class StructuredTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photo = self.root / 'photo.jpg'
        self.photo.write_bytes(b'fake-provider-image')
        self.config = {'models': {'test': {'provider': 'openrouter', 'model': 'test-model',
            'input_usd_per_million': 1, 'output_usd_per_million': 2,
            'max_output_tokens': 1000, 'input_token_bound': 1000,
            'provider_only': ['google-ai-studio']}},
            'budget': {'stage_max_inr': 100, 'total_max_inr': 100, 'prior_accounted_inr': 0, 'usd_inr': 100}}
        self.schema = {'type': 'object', 'properties': {'detail': {'type': 'string', 'minLength': 1}},
                       'required': ['detail'], 'additionalProperties': False}
        self.client = transport.Client(self.config, self.root, self.root / 'out')
        self.key = patch.object(transport, 'api_key_for', return_value='test-only')
        self.key.start()
        self.addCleanup(self.key.stop)

    def response(self, content):
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(content)}}],
                                      'usage': {'cost': .001, 'prompt_tokens': 10, 'completion_tokens': 10}}).encode())

    def test_schema_is_strict_and_provider_must_support_parameters(self):
        def network(request, timeout):
            payload = json.loads(request.data)
            shape = payload['response_format']
            self.assertEqual(shape['type'], 'json_schema')
            self.assertTrue(shape['json_schema']['strict'])
            self.assertEqual(shape['json_schema']['schema'], self.schema)
            self.assertTrue(payload['provider']['require_parameters'])
            self.assertEqual(payload['provider']['only'], ['google-ai-studio'])
            self.assertFalse(payload['provider']['allow_fallbacks'])
            return self.response({'detail': 'Visible body'})
        with patch.object(transport.urllib.request, 'urlopen', side_effect=network):
            result = self.client.generate('strict', 'test', 'Return detail', [('Scene', self.photo)], schema=self.schema)
        self.assertEqual(result, {'detail': 'Visible body'})

    def test_malformed_shape_fails_locally_and_keeps_actual_usage(self):
        with patch.object(transport.urllib.request, 'urlopen', return_value=self.response({'detail: wrong': 'text'})):
            with self.assertRaisesRegex(RuntimeError, 'schema'):
                self.client.generate('wrong', 'test', 'Return detail', [('Scene', self.photo)], schema=self.schema)
        row = json.loads(self.client.calls_path.read_text())
        self.assertEqual(row['status'], 'error')
        self.assertEqual(row['estimated_cost_usd'], .001)
        self.assertEqual(json.loads(self.client.pending_path.read_text()), {})

    def test_gemini_nullable_payload_retains_closed_objects_and_local_checks(self):
        from webapp.schemas import inventory_schema, comparison_schema
        original = inventory_schema()
        adapted = transport.provider_schema(original, {'model': 'google/gemini-3.7-flash'})
        machine = adapted['properties']['objects']['items']
        self.assertEqual(machine['properties']['parent_id'], {'type': ['string', 'null']})
        self.assertEqual(machine['properties']['observations']['items']['properties']['box_2d']['type'], ['array', 'null'])
        self.assertFalse(machine['additionalProperties'])
        self.assertEqual(set(machine['required']), set(machine['properties']))
        self.assertIn('pattern', original['properties']['objects']['items']['properties']['object_id'])
        self.assertNotIn('maxItems', adapted['properties']['objects'])
        self.assertNotIn('minimum', machine['properties']['box_2d']['items'])
        with self.assertRaises(ValueError):
            transport.validate_shape([0, 0, 1001, 1000], original['properties']['objects']['items']['properties']['box_2d'])
        with self.assertRaises(ValueError):
            transport.validate_shape([0, 0, 1000], original['properties']['objects']['items']['properties']['box_2d'])
        decision = transport.provider_schema(comparison_schema(['o1'], ['v8']), {'model': 'google/test'})['properties']['results']['items']['properties']['result']['properties']['decision']
        self.assertEqual(decision['properties']['product']['enum'], ['v8', None])
        for invalid in ('', 'bad id'):
            with self.assertRaises(ValueError):
                transport.validate_shape(invalid, original['properties']['objects']['items']['properties']['object_id'])
        with self.assertRaises(ValueError):
            transport.validate_shape('', original['properties']['objects']['items']['properties']['parent_id'])
        self.assertEqual(transport.provider_schema(original, {'model': 'other/model'}), original)

    def test_no_schema_retains_existing_json_mode(self):
        def network(request, timeout):
            self.assertEqual(json.loads(request.data)['response_format'], {'type': 'json_object'})
            return self.response({'detail': 'Visible'})
        with patch.object(transport.urllib.request, 'urlopen', side_effect=network):
            self.client.generate('old', 'test', 'Return detail', [('Scene', self.photo)])

    def test_one_reservation_and_one_settlement_checkpoint_per_call(self):
        with patch.object(transport.cloud_runtime, 'checkpoint') as checkpoint:
            def network(request, timeout):
                self.assertEqual(checkpoint.call_count, 1)
                self.assertTrue(self.client.pending)
                return self.response({'detail': 'Visible'})
            with patch.object(transport.urllib.request, 'urlopen', side_effect=network):
                self.client.generate('checkpoints', 'test', 'Return detail', [('Scene', self.photo)])
            self.assertEqual(checkpoint.call_count, 2)
        self.assertEqual(json.loads(self.client.pending_path.read_text()), {})
        self.assertEqual(json.loads(self.client.calls_path.read_text())['status'], 'ok')

    def test_actual_clients_overlap_under_shared_request_limit(self):
        from webapp.inference import ledger_accounting
        from webapp.request_coordinator import RequestCoordinator
        root = self.root / 'runtime'
        coordinator = RequestCoordinator(lambda: ledger_accounting(root)['spent_inr'], lambda: 10, interval_seconds=0)
        clients = [transport.Client(self.config, self.root, root / str(i), request_coordinator=coordinator) for i in range(2)]
        reached = threading.Barrier(2)
        errors = []
        def network(request, timeout):
            reached.wait(timeout=3)
            return self.response({'detail': 'Visible'})
        def run(index):
            try:
                clients[index].generate('call', 'test', 'Return detail', [('Scene', self.photo)])
            except Exception as error:
                errors.append(error)
        with patch.object(transport.urllib.request, 'urlopen', side_effect=network) as calls:
            threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=4)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(calls.call_count, 2)
        self.assertAlmostEqual(ledger_accounting(root)['spent_inr'], .2)

    def test_actual_clients_cannot_race_past_shared_budget(self):
        from webapp.inference import ledger_accounting
        from webapp.request_coordinator import RequestCoordinator
        root = self.root / 'runtime'
        coordinator = RequestCoordinator(lambda: ledger_accounting(root)['spent_inr'], lambda: .4, interval_seconds=0)
        clients = [transport.Client(self.config, self.root, root / str(i), request_coordinator=coordinator) for i in range(2)]
        started, blocked, release = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def network(request, timeout):
            started.set()
            if not release.wait(3): raise RuntimeError('Test release missing')
            return self.response({'detail': 'Visible'})
        def run(index):
            try:
                clients[index].generate('call', 'test', 'Return detail', [('Scene', self.photo)])
            except Exception as error:
                errors.append(str(error)); blocked.set()
        with patch.object(transport.urllib.request, 'urlopen', side_effect=network) as calls:
            threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
            try:
                threads[0].start(); self.assertTrue(started.wait(3))
                threads[1].start(); self.assertTrue(blocked.wait(3))
                self.assertEqual(calls.call_count, 1)
            finally:
                release.set()
                for thread in threads:
                    if thread.ident is not None: thread.join(timeout=4)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(errors), 1)
        self.assertIn('remaining allowance', errors[0])
        self.assertAlmostEqual(ledger_accounting(root)['spent_inr'], .1)
