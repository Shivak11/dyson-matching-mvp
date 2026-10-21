"""Offline cumulative-view storage, joint requests and evidence boundaries."""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os

from test_webapp import fixture_root, image_file, HTTPFixture
from test_webapp_inference import FakeClient, target, response
from webapp.store import Store, ConflictError
from webapp.inference import Inference, validate_batch, BudgetError, RUNTIME_CAP_INR
from webapp.predictions import hosted_job, hosted_prediction


class MultipleViewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.store = Store(self.root, self.root / 'var')
        self.parent = self.store.create_jobs({'images': [image_file('private-answer-1.png', 'red')]})[0]
        self.parent = self.store.update_job(self.parent['id'], status='completed', matches=[{'object_id': 'o1'}])
        self.snapshot = self.store.job(self.parent['id'], internal=True)['_snapshot']

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, parent=None, color='blue', request_id='step-two'):
        return {'images': [image_file('private-answer-2.png', color)], 'parent_job_id': (parent or self.parent)['id'],
                'same_product': True, 'expected_product_id': None, 'request_id': request_id}

    def child(self):
        return self.store.create_jobs(self.payload())[0]

    def complete(self, job, **changes):
        return self.store.update_job(job['id'], status='completed', matches=[{'object_id': 'o1'}], **changes)

    def test_chain_is_immutable_frozen_and_capped_at_three(self):
        before = copy.deepcopy(self.parent)
        self.store.edit_product({'name': 'Changed after first photo'}, 'dyson_v15_detect')
        child = self.child()
        self.assertEqual(child['mode'], 'identify')
        self.assertEqual(child['image_url'], self.parent['image_url'])
        self.assertEqual(child['root_job_id'], self.parent['id'])
        self.assertEqual(child['view_count'], 2)
        self.assertEqual(self.store.job(child['id'], internal=True)['_snapshot'], self.snapshot)
        self.complete(child)
        third = self.store.create_jobs(self.payload(child, 'green', 'step-three'))[0]
        self.assertEqual([view['view_id'] for view in third['views']], ['view_1', 'view_2', 'view_3'])
        self.assertEqual(third['parent_job_id'], child['id'])
        self.complete(third)
        with self.assertRaisesRegex(ValueError, 'three'):
            self.store.create_jobs(self.payload(third, 'black', 'step-four'))
        self.assertEqual(self.store.job(self.parent['id']), before)
        reopened = Store(self.root, self.root / 'var')
        self.assertEqual(len(reopened.job(third['id'], internal=True)['_views']), 3)
        self.assertNotIn('_views', reopened.job(third['id']))

    def test_invalid_parent_modes_assertions_counts_and_duplicate_content(self):
        for changes in ({'same_product': False}, {'same_product': 1}, {'parent_job_id': 'missing'},
                        {'expected_product_id': 'dyson_v15_detect'}, {'images': []},
                        {'images': [image_file('x.png', 'red')]},
                        {'images': [image_file('x.png', 'blue'), image_file('y.png', 'green')]}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, KeyError)):
                self.store.create_jobs(self.payload() | changes)
        for changes in ({'status': 'running'}, {'mode': 'verify'}, {'matches': []},
                        {'matches': [{'object_id': 'o1'}, {'object_id': 'o2'}]}):
            self.store.update_job(self.parent['id'], **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.child()
            self.store.update_job(self.parent['id'], **self.parent)

    def test_idempotency_and_grouped_retry_keep_all_views_and_frozen_catalogue(self):
        child = self.child()
        cached, created = self.store.create_jobs(self.payload(), with_created=True)
        self.assertFalse(created)
        self.assertEqual(cached[0]['id'], child['id'])
        with self.assertRaises(ConflictError):
            self.store.create_jobs(self.payload(color='green'))
        self.complete(child)
        self.store.edit_product({'name': 'Changed after group'}, 'dyson_v15_detect')
        retry = self.store.retry(child['id'], 'retry-group')[0]
        self.assertEqual(retry['views'], child['views'])
        self.assertEqual(retry['parent_job_id'], child['parent_job_id'])
        self.assertEqual(self.store.job(retry['id'], internal=True)['_snapshot'], self.snapshot)
        claimed = self.store.claim_job(retry['id'])
        self.assertEqual(len(claimed['_views']), 2)

    def joint_response(self, status='consistent'):
        raw = response(self.snapshot)
        result = raw['results'][0]['result']
        result['decisive_region'] = None
        result['cross_view_consistency'] = {'status': status, 'evidence': 'Body and bin arrangements are compatible across views.'}
        for index, check in enumerate(result['feature_checks']):
            check['query_view'] = 'view_' + str(index + 1)
            check['detail'] = 'Valid visible feature in ' + check['query_view']
        return raw

    def run_fixture(self, child, inventories, comparison=None):
        script = [inventories] + ([comparison] if comparison is not None else [])
        clients = []
        def factory(*args, **options):
            client = FakeClient(*args, **options)
            client.responses = copy.deepcopy(script)
            clients.append(client)
            return client
        job = self.store.job(child['id'], internal=True)
        results = Inference(self.root, self.root / 'var/runtime', self.store, factory).run(job, lambda stage: None)
        return results, clients[0]

    def inventory(self, count=2):
        return {'views': [{'view_id': 'view_' + str(index + 1), 'objects': [target()]} for index in range(count)]}

    def test_joint_requests_include_all_views_with_neutral_labels_and_same_limits(self):
        child = self.child()
        results, client = self.run_fixture(child, self.inventory(), self.joint_response())
        self.assertEqual(results[0]['product_id'], 'dyson_v15_detect')
        self.assertEqual(results[0]['confidence'], 'High')
        self.assertEqual({row['view_id'] for row in results[0]['view_evidence']}, {'view_1', 'view_2'})
        self.assertEqual(len(client.seen), 2)
        for call in client.seen:
            self.assertEqual([label for label, _ in call['images'][:2]], ['View 1', 'View 2'])
            self.assertNotEqual(call['images'][0][1], call['images'][1][1])
            self.assertNotIn('private-answer', call['prompt'])
        self.assertEqual(client.options['request_interval_seconds'], 15)
        self.assertEqual(client.config['models']['flash37high']['thinking_level'], 'high')
        self.assertEqual(client.config['models']['flash37high']['provider_only'], ['google-ai-studio'])
        self.assertEqual(client.config['budget']['total_max_inr'], RUNTIME_CAP_INR)
        self.complete(child)
        third = self.store.create_jobs(self.payload(child, 'green', 'step-three'))[0]
        _, client = self.run_fixture(third, self.inventory(3), self.joint_response())
        for call in client.seen:
            self.assertEqual([label for label, _ in call['images'][:3]], ['View 1', 'View 2', 'View 3'])

    def test_per_view_regions_and_consistency_gate_without_changing_single_view(self):
        targets = {'view_1': target(), 'view_2': target()}
        raw = self.joint_response()
        item = validate_batch(raw, [target()], self.snapshot, view_targets=targets)['o1']
        self.assertEqual(item['decision']['status'], 'match')
        for state in ('conflicting', 'insufficient_evidence'):
            raw = self.joint_response(state)
            item = validate_batch(raw, [target()], self.snapshot, view_targets=targets)['o1']
            self.assertEqual(item['decision']['status'], 'not_sure')
        for bad in ('unknown', None):
            raw = self.joint_response()
            raw['results'][0]['result']['feature_checks'][0]['query_view'] = bad
            with self.assertRaises(ValueError):
                validate_batch(raw, [target()], self.snapshot, view_targets=targets)
        raw = self.joint_response()
        targets['view_2']['box_2d'] = [400, 400, 900, 900]
        item = validate_batch(raw, [target()], self.snapshot, view_targets=targets)['o1']
        self.assertEqual(item['decision']['status'], 'not_sure')
        self.assertEqual(len(item['unverified_feature_checks']), 1)
        self.assertEqual(validate_batch(response(self.snapshot), [target()], self.snapshot)['o1']['decision']['status'], 'match')

    def test_multiple_or_empty_view_remains_unsure_without_borrowing_features(self):
        for objects in ([], [target(), dict(target(), object_id='o2')]):
            with self.subTest(objects=objects):
                child = self.store.create_jobs(self.payload(request_id=None))[0]
                inventory = self.inventory()
                inventory['views'][1]['objects'] = objects
                results, client = self.run_fixture(child, inventory)
                self.assertEqual(results[0]['status'], 'not_sure')
                self.assertEqual(results[0]['view_evidence'], [])
                self.assertEqual(len(client.seen), 1)

    def test_grouped_exports_and_hosted_allowlist_preserve_sealed_parent(self):
        self.store.seal_prediction(self.parent['id'], {'cost_inr': 0})
        sealed = {kind: self.store.prediction_export(self.parent['id'], kind) for kind in ('json', 'csv')}
        child = self.child()
        matches, _ = self.run_fixture(child, self.inventory(), self.joint_response())
        self.store.update_job(child['id'], status='completed', matches=matches)
        details = {'cost_inr': 2, 'requested_model': 'PRIVATE_MODEL', 'config_sha256': 'SECRET', 'requests': [{'model': 'PRIVATE_MODEL'}]}
        self.store.seal_prediction(child['id'], details)
        job = self.store.job(child['id'])
        job['views'][0]['sha256'] = 'PRIVATE_HASH'
        public = hosted_job(job)
        self.assertEqual(public['view_count'], 2)
        self.assertNotIn('PRIVATE', json.dumps(public))
        exported = json.loads(self.store.prediction_export(child['id'], 'json'))
        self.assertTrue(all(len(view['sha256']) == 64 for view in exported['views']))
        exported['views'][0]['sha256'] = 'PRIVATE_HASH'
        for kind in ('json', 'csv'):
            content = hosted_prediction(exported, kind)
            self.assertNotIn(b'PRIVATE', content)
            if kind == 'csv':
                rows = list(csv.DictReader(io.StringIO(content.decode())))
                self.assertEqual(rows[0]['view_count'], '2')
                self.assertEqual(len(json.loads(rows[0]['views'])), 2)
            self.assertEqual(self.store.prediction_export(self.parent['id'], kind), sealed[kind])
        self.assertEqual(json.loads(hosted_prediction(exported, 'json'))['matches'][0]['view_boxes'], matches[0]['view_boxes'])

    def test_grouped_path_stops_at_existing_reservation_guard_before_transport(self):
        child = self.child()
        ledgers = self.root / 'var/runtime'
        old = ledgers / 'previous'
        old.mkdir(parents=True)
        (old / 'inflight.json').write_text(json.dumps({'reserved': {'reserved_cost_usd': (RUNTIME_CAP_INR - 1) / 100}}))
        clients = []
        def factory(*args, **options):
            client = FakeClient(*args, **options)
            clients.append(client)
            return client
        with self.assertRaises(BudgetError):
            Inference(self.root, ledgers, self.store, factory).run(self.store.job(child['id'], internal=True), lambda stage: None)
        self.assertEqual(clients[0].seen, [])


class MultipleViewsHTTPTests(HTTPFixture, unittest.TestCase):
    def test_hosted_create_and_cached_repeat_keep_grouping_and_hide_private_hashes(self):
        parent = self.app.store.create_jobs({'images': [image_file('one.png', 'red')]})[0]
        self.app.store.update_job(parent['id'], status='completed', matches=[{'object_id': 'o1'}])
        headers = {'X-CSRF-Token': self.app.csrf_token, 'X-Container-Token': 'test-container', 'Origin': self.base}
        payload = {'request_id': 'joint-http', 'parent_job_id': parent['id'], 'same_product': True,
                   'expected_product_id': None, 'images': [image_file('two.png', 'blue')]}
        with patch.dict(os.environ, {'CLOUD_CONTAINER_TOKEN': 'test-container'}), \
             patch('app_server.cloud_runtime.enabled', return_value=True), \
             patch('app_server.cloud_runtime.checkpoint'), patch('app_server.api_configured', return_value=True):
            code, _, raw = self.request('/api/jobs', payload, headers=headers)
            self.assertEqual(code, 202, raw)
            child = json.loads(raw)['jobs'][0]
            self.assertEqual(child['view_count'], 2)
            self.assertEqual(child['parent_job_id'], parent['id'])
            self.assertEqual(self.app.queue.qsize(), 1)
            repeated = json.loads(self.request('/api/jobs', payload, headers=headers)[2])['jobs'][0]
            self.assertEqual(repeated['id'], child['id'])
            self.assertEqual(self.app.queue.qsize(), 1)
            self.assertEqual(self.request('/api/jobs', payload | {'same_product': False}, headers=headers)[0], 409)
            self.assertNotIn('_media_id', raw.decode())
            self.assertNotIn('sha256', raw.decode())


if __name__ == '__main__':
    unittest.main()
