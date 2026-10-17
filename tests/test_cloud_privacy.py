"""Hosted responses expose product results without private execution records."""
import csv
import io
import json
import os
import unittest
from unittest.mock import patch

from test_webapp import HTTPFixture, image_file


class HostedPrivacyTests(HTTPFixture, unittest.TestCase):
    def test_all_response_paths_redact_without_changing_sealed_exports(self):
        marker = 'private-execution-marker'
        details = {'requested_model': marker, 'requested_provider': marker,
                   'reasoning_effort': marker, 'pipeline_version': marker,
                   'config_sha256': 'a' * 64, 'catalogue_sha256': 'b' * 64,
                   'requests': [{'model': marker, 'provider': marker}],
                   'started_at': '2026-10-17T05:00:00+00:00',
                   'completed_at': '2026-10-17T05:00:02+00:00',
                   'elapsed_seconds': 2, 'queued_seconds': 1, 'cost_inr': 0}
        original = self.app.store.create_jobs({'images': [image_file('saved.png')]})[0]
        match = {'object_id': 'o1', 'box_2d': [0, 0, 1000, 1000], 'status': 'match',
                 'product_id': 'dyson_v8_absolute', 'product_name': 'Dyson V8 Absolute',
                 'confidence': 'High', 'evidence': ['Visible body and bin details.'],
                 'missing_evidence': [], 'retake_guidance': [], 'verification': 'confirmed',
                 'alternatives': [{'id': 'dyson_v11', 'name': 'Dyson V11', 'private': marker}],
                 'reference_image_url': '/media/manufacturer-v8',
                 'source_url': 'https://manufacturer.example/v8',
                 'reference_images': [{'id': 'manufacturer-v8', 'url': '/media/manufacturer-v8',
                                       'filename': 'v8.png', 'private': marker}],
                 'private': marker}
        self.app.store.update_job(original['id'], status='completed', stage=marker,
                                  matches=[match], private=marker)
        self.app.store.seal_prediction(original['id'], details)
        sealed = {kind: self.app.store.prediction_export(original['id'], kind) for kind in ('json', 'csv')}
        self.assertIn(marker.encode(), sealed['json'])
        runtime = self.app.bootstrap()['settings']
        runtime['api_configured'] = True
        headers = {'X-CSRF-Token': self.app.csrf_token, 'X-Container-Token': 'test-container',
                   'Origin': self.base}
        forbidden = {'requested_model', 'requested_provider', 'reasoning_effort', 'pipeline_version',
                     'config_sha256', 'catalogue_sha256', 'requests', 'private', 'model_label',
                     'request_pause_seconds', 'stage_remaining_inr', 'api_configured'}

        def public(value):
            self.assertNotIn(marker, json.dumps(value))
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value), forbidden.intersection(value))
                for item in value.values():
                    public(item)
            elif isinstance(value, list):
                for item in value:
                    public(item)

        def request(path, payload=None):
            code, response_headers, raw = self.request(path, payload, headers=headers)
            self.assertIn(code, (200, 202), raw)
            value = json.loads(raw)
            public(value)
            return value, response_headers, raw

        with patch.dict(os.environ, {'CLOUD_CONTAINER_TOKEN': 'test-container'}), \
             patch('app_server.cloud_runtime.enabled', return_value=True), \
             patch('app_server.cloud_runtime.checkpoint'), \
             patch('app_server.api_configured', return_value=True), \
             patch('app_server.settings', return_value=runtime):
            bootstrap, _, _ = request('/api/bootstrap')
            self.assertTrue(bootstrap['settings']['service_ready'])
            self.assertEqual(bootstrap['settings']['runtime_remaining_inr'], runtime['runtime_remaining_inr'])
            request('/api/jobs')
            detail, _, _ = request('/api/jobs/' + original['id'])
            self.assertEqual(detail['matches'][0]['confidence'], 'High')
            self.assertEqual(detail['matches'][0]['status'], 'match')
            self.assertEqual(detail['matches'][0]['reference_image_url'], '/media/manufacturer-v8')
            self.assertEqual(detail['matches'][0]['source_url'], 'https://manufacturer.example/v8')
            self.assertEqual(detail['matches'][0]['reference_images'], [
                {'id': 'manufacturer-v8', 'url': '/media/manufacturer-v8', 'filename': 'v8.png'}])
            self.assertEqual(detail['run_details']['elapsed_seconds'], 2)
            self.assertEqual(detail['run_details']['cost_inr'], 0)
            for kind in ('json', 'csv'):
                code, response_headers, raw = self.request('/api/jobs/' + original['id'] + '/export.' + kind, headers=headers)
                self.assertEqual(code, 200)
                self.assertNotIn('X-Content-SHA256', response_headers)
                self.assertNotIn(marker.encode(), raw)
                self.assertNotIn(b'sha256', raw)
                if kind == 'json':
                    public(json.loads(raw))
                else:
                    rows = list(csv.DictReader(io.StringIO(raw.decode())))
                    self.assertEqual(rows[0]['model_family'], 'Dyson V8 Absolute')
                    self.assertEqual(rows[0]['elapsed_seconds'], '2')
                    public(rows)
            payload = {'request_id': 'hosted-upload', 'images': [image_file('new.png')]}
            created, _, _ = request('/api/jobs', payload)
            key = created['jobs'][0]['id']
            self.app.store.update_job(key, status='running', stage=marker, private=marker, run_details=details)
            cached, _, _ = request('/api/jobs', payload)
            self.assertEqual(cached['jobs'][0]['stage'], 'Processing photograph')
            request('/api/jobs/' + key)
            request('/api/bootstrap')
            request('/api/jobs')
            retry_payload = {'request_id': 'hosted-retry'}
            retry, _, _ = request('/api/jobs/' + original['id'] + '/retry', retry_payload)
            self.app.store.update_job(retry['jobs'][0]['id'], stage=marker, private=marker, run_details=details)
            request('/api/jobs/' + original['id'] + '/retry', retry_payload)
            with patch('app_server.api_configured', return_value=False):
                code, _, raw = self.request('/api/jobs', {'request_id': 'unavailable', 'images': [image_file()]}, headers=headers)
                self.assertEqual(code, 503)
                self.assertNotIn(b'OPENROUTER', raw)
            runtime['accounting_error'] = marker
            code, _, raw = self.request('/api/jobs', {'request_id': 'accounting', 'images': [image_file()]}, headers=headers)
            self.assertEqual(code, 409)
            public(json.loads(raw))
            public(request('/api/bootstrap')[0])
            runtime['accounting_error'] = None
            self.assertEqual(self.app.queue.qsize(), 2)
            self.assertEqual(self.app.engine.count, 0)
        for kind in ('json', 'csv'):
            self.assertEqual(self.app.store.prediction_export(original['id'], kind), sealed[kind])
            self.assertEqual(self.request('/api/jobs/' + original['id'] + '/export.' + kind)[2], sealed[kind])
        self.assertEqual(self.app.public_jobs(original['id'])[0]['run_details']['requested_model'], marker)
        self.assertEqual(self.app.bootstrap()['settings']['model_label'], runtime['model_label'])
