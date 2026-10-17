"""Offline validation, aggregate reservation, route, pacing and crop checks."""
import base64
import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from test_webapp import fixture_root, image_file
from webapp.store import Store
from webapp.inference import (Inference, BudgetError, catalogue_projection, comparison_prompt,
                              validate_batch, display_match, ledger_accounting, settings,
                              RUNTIME_CAP_INR, STAGE_CAP_INR, HISTORICAL_STAGE_GUARD_INR)


def target():
    return {'object_id': 'o1', 'role': 'machine', 'parent_id': None, 'visibility': 'main_body',
            'box_2d': [0, 0, 1000, 1000], 'readable_identifier': '',
            'observations': [{'feature': 'body_layout', 'visible': True, 'detail': 'Motor and bin are visible.',
                              'box_2d': [100, 100, 500, 500]}]}


def response(snapshot, product='dyson_v15_detect', status='match'):
    return {'results': [{'object_id': 'o1', 'result': {
        'decision': {'status': status, 'product': product if status == 'match' else None, 'confidence': 95 if status == 'match' else 0,
                     'top_two': [product], 'evidence': ['Visible bin layout and trigger match the reference.'] if status == 'match' else [],
                     'missing_evidence': [] if status == 'match' else ['Inspect the body detail.'], 'contradictions': [], 'retake': ''},
        'candidate_checks': [{'product': row['id'], 'outcome': 'confirmed' if row['id'] == product and status == 'match' else 'insufficient_evidence',
                              'evidence': 'Body detail matches.' if row['id'] == product else 'The identifying detail is hidden.'} for row in snapshot],
        'decisive_region': [100, 100, 200, 200], 'refinement_reason': '',
        'feature_checks': [{'product': product, 'feature': feature, 'query_visible': True, 'query_box_2d': [100, 100, 200, 200],
                            'reference_visible': True, 'reference_box_2d': [0, 0, 1000, 1000], 'detail': 'Visible diagnostic comparison.'}
                           for feature in ('body_layout', 'handle_control')] if status == 'match' else []}}]}


class FakeClient:
    def __init__(self, config, root, out, **options):
        self.config = config
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.options = options
        self.last_request_finished_at = None
        self.responses = []
        self.seen = []
        self.invalid = []

    def generate(self, job_id, model, prompt, images):
        self.seen.append({'prompt': prompt, 'images': images, 'job_id': job_id})
        with (self.out / 'calls.jsonl').open('a') as output:
            output.write(json.dumps({'job_id': job_id, 'status': 'ok', 'estimated_cost_usd': 0.01,
                                     'request_finished_unix': time.time()}) + '\n')
        return copy.deepcopy(self.responses.pop(0))

    def record_validation_failure(self, job_id, error):
        self.invalid.append((job_id, error))


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.store = Store(self.root, self.root / 'var')
        self.ledgers = self.root / 'var/runtime'
        self.ledgers.mkdir()
        self.job = self.store.create_jobs({'images': [image_file('PRIVATE-TEST-LABEL-P054.png')], 'expected_product_id': 'dyson_v15_detect'})[0]
        self.job = self.store.job(self.job['id'], internal=True)
        self.snapshot = self.job['_snapshot']
        self.script = []
        self.created = []

    def tearDown(self):
        self.temp.cleanup()

    def client_factory(self, *args, **options):
        client = FakeClient(*args, **options)
        client.responses = copy.deepcopy(self.script)
        self.created.append(client)
        return client

    def engine(self):
        return Inference(self.root, self.ledgers, self.store, self.client_factory)

    def test_manufacturer_projection_excludes_labels_filenames_and_old_outputs(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot[0].update(filename='PRIVATE-FILENAME', source_title='PRIVATE-SOURCE-LABEL', prior_answer='PRIVATE-PRIOR-ANSWER')
        projection = catalogue_projection(snapshot)
        prompt = comparison_prompt([target()], snapshot, 'dyson_v15_detect')
        for secret in ('PRIVATE-FILENAME', 'PRIVATE-SOURCE-LABEL', 'PRIVATE-PRIOR-ANSWER', 'image_records', 'image_ids'):
            self.assertNotIn(secret, prompt)
        self.assertEqual(len(projection), 9)
        self.assertIn(snapshot[0]['brochure_details'], json.dumps(projection))
        self.assertIn('expected_product', prompt)
        self.assertNotIn('all six', prompt.lower())

    def test_complete_evidence_uses_two_calls_no_refinement(self):
        self.script = [{'objects': [target()]}, response(self.snapshot)]
        matches = self.engine().run(self.job, lambda stage: None)
        self.assertEqual(len(self.created[0].seen), 2)
        self.assertEqual(matches[0]['product_id'], 'dyson_v15_detect')
        self.assertEqual(matches[0]['confidence'], 'High')
        self.assertEqual(matches[0]['verification'], 'confirmed')
        self.assertTrue(matches[0]['reference_images'])
        self.assertTrue(matches[0]['source_url'].startswith('https://'))
        self.assertNotIn('PRIVATE-TEST-LABEL', ''.join(row['prompt'] for row in self.created[0].seen))
        self.assertEqual(self.created[0].options['request_interval_seconds'], 15)
        self.assertEqual(self.created[0].options['rate_limit_retries'], 2)
        self.assertEqual(self.created[0].config['models']['flash37high']['provider_only'], ['google-ai-studio'])

    def test_negative_family_is_identified_and_expected_model_rejected(self):
        item = validate_batch(response(self.snapshot, 'dyson_gen5detect'), [target()], self.snapshot)['o1']
        result = display_match(target(), item, self.snapshot, 'dyson_v15_detect')
        self.assertEqual(result['status'], 'not_in_catalog')
        self.assertEqual(result['product_id'], 'dyson_gen5detect')
        self.assertEqual(result['verification'], 'rejected')

    def test_flat_comparison_uses_the_same_evidence_validation(self):
        raw = response(self.snapshot)
        nested = validate_batch(raw, [target()], self.snapshot)['o1']
        flat = {'results': [{'object_id': 'o1', **raw['results'][0]['result']}]}
        accepted = validate_batch(flat, [target()], self.snapshot)['o1']
        self.assertEqual(accepted['decision'], nested['decision'])
        self.assertEqual(accepted['feature_checks'], nested['feature_checks'])
        flat['results'][0]['decision']['confidence'] = 0.95
        with self.assertRaises(ValueError):
            validate_batch(flat, [target()], self.snapshot)

    def test_shared_controls_lcd_filter_cannot_resolve_v16(self):
        raw = response(self.snapshot, 'dyson_v16_piston_animal')
        checks = raw['results'][0]['result']['feature_checks']
        checks[0]['feature'] = 'handle_control'
        checks[1]['feature'] = 'display_layout'
        item = validate_batch(raw, [target()], self.snapshot)['o1']
        self.assertEqual(item['decision']['status'], 'not_sure')
        self.assertIsNone(item['decision']['product'])
        self.assertIn('body', item['decision']['missing_evidence'][-1])

    def test_invisible_placeholder_coordinates_are_removed_without_adding_support(self):
        raw = response(self.snapshot)
        checks = raw['results'][0]['result']['feature_checks']
        hidden = copy.deepcopy(checks[0])
        hidden.update(feature='identifier', reference_visible=False,
                      reference_box_2d=[0, 0, 1000, 1000])
        checks.append(hidden)
        before = copy.deepcopy(raw)
        item = validate_batch(raw, [target()], self.snapshot)['o1']
        self.assertEqual(item['decision']['status'], 'match')
        self.assertIsNone(item['feature_checks'][-1]['reference_box_2d'])
        self.assertEqual(len(item['decision']['evidence']), 1)
        self.assertTrue(item['format_repairs'])
        self.assertEqual(raw, before)
        checks[1]['reference_visible'] = False
        item = validate_batch(raw, [target()], self.snapshot)['o1']
        self.assertEqual(item['decision']['status'], 'not_sure')
        self.assertIsNone(item['decision']['product'])

    def test_invalid_schema_duplicates_and_foreign_feature_regions_fail(self):
        for modify in ('fraction', 'duplicate', 'foreign'):
            raw = response(self.snapshot)
            if modify == 'fraction':
                raw['results'][0]['result']['decision']['confidence'] = 0.95
            elif modify == 'duplicate':
                raw['results'] += copy.deepcopy(raw['results'])
            else:
                raw['results'][0]['result']['feature_checks'][0]['query_box_2d'] = [0, 0, 1001, 1000]
            with self.subTest(modify=modify), self.assertRaises(ValueError):
                validate_batch(raw, [target()], self.snapshot)

    def test_recorded_geometry_overrun_excludes_only_unverified_detail(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/app_geometry_overrun.json').read_text())
        before = copy.deepcopy(fixture['response'])
        item = validate_batch(fixture['response'], fixture['targets'], fixture['candidates'])['o1']
        self.assertEqual(item['decision']['product'], 'dyson_v8_absolute')
        self.assertEqual(item['decision']['status'], 'match')
        self.assertEqual(len(item['unverified_feature_checks']), 1)
        self.assertEqual(len(item['decision']['evidence']), 2)
        self.assertFalse(item['feature_checks'][2]['query_visible'])
        self.assertIn('excluded', item['decision']['missing_evidence'][-1])
        self.assertEqual(fixture['response'], before)

    def test_foreign_body_support_cannot_establish_identity(self):
        machine = target()
        machine['box_2d'] = [100, 100, 900, 900]
        raw = response(self.snapshot)
        raw['results'][0]['result']['feature_checks'][0]['query_box_2d'] = [0, 0, 90, 90]
        item = validate_batch(raw, [machine], self.snapshot)['o1']
        self.assertEqual(item['decision']['status'], 'not_sure')
        self.assertIsNone(item['decision']['product'])

    def test_failed_validation_records_failure_and_does_not_retry_success(self):
        self.script = [{'objects': [target()]}, {'results': []}]
        with self.assertRaises(ValueError):
            self.engine().run(self.job, lambda stage: None)
        self.assertEqual(len(self.created[0].seen), 2)
        self.assertEqual(len(self.created[0].invalid), 1)
        self.assertEqual(ledger_accounting(self.ledgers)['spent_inr'], 2)

    def test_one_targeted_refinement_crops_original_pixels(self):
        image = Image.new('RGB', (3000, 6000), 'white')
        output = io.BytesIO()
        image.save(output, 'PNG')
        uploaded = {'filename': 'high-resolution.png', 'data_url': 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()}
        new_job = self.store.create_jobs({'images': [uploaded]})[0]
        job = self.store.job(new_job['id'], internal=True)
        self.script = [{'objects': [target()]}, response(self.snapshot, status='not_sure'), response(self.snapshot)]
        result = self.engine().run(job, lambda stage: None)
        self.assertEqual(len(self.created[0].seen), 3)
        detail = next(path for label, path in self.created[0].seen[-1]['images'] if label.startswith('Same-photo detail'))
        with Image.open(detail) as crop:
            self.assertEqual(crop.size, (300, 600))
        with Image.open(self.store.media(job['_media_id'], provider=True)[0]) as provider:
            self.assertEqual(max(provider.size), 2048)
        self.assertEqual(result[0]['status'], 'match')

    def test_finite_float_boxes_survive_inventory_comparison_and_native_crop(self):
        image = Image.new('RGB', (3000, 6000), 'white')
        output = io.BytesIO()
        image.save(output, 'PNG')
        uploaded = {'filename': 'float-region.png', 'data_url': 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()}
        new_job = self.store.create_jobs({'images': [uploaded]})[0]
        job = self.store.job(new_job['id'], internal=True)
        observed = target()
        observed['box_2d'] = [0.0, 0.0, 1000.0, 1000.0]
        observed['observations'][0]['box_2d'] = [100.25, 100.5, 500.75, 500.5]
        initial = response(self.snapshot, status='not_sure')
        initial['results'][0]['result']['decisive_region'] = [100.25, 100.5, 200.75, 200.5]
        refined = response(self.snapshot)
        refined['results'][0]['result']['decisive_region'] = [100.25, 100.5, 200.75, 200.5]
        for check in refined['results'][0]['result']['feature_checks']:
            check['query_box_2d'] = [100.25, 100.5, 200.75, 200.5]
            check['reference_box_2d'] = [0.25, 0.5, 999.75, 999.5]
        self.script = [{'objects': [observed]}, initial, refined]
        matches = self.engine().run(job, lambda stage: None)
        self.assertEqual(matches[0]['status'], 'match')
        detail = next(path for label, path in self.created[0].seen[-1]['images'] if label.startswith('Same-photo detail'))
        with Image.open(detail) as crop:
            self.assertEqual(crop.size, (301, 604))
        bad = copy.deepcopy(refined)
        bad['results'][0]['result']['feature_checks'][0]['query_box_2d'][0] = float('nan')
        with self.assertRaises(ValueError):
            validate_batch(bad, [observed], self.snapshot)

    def test_refinement_adds_two_native_manufacturer_views_from_disputed_families(self):
        image = Image.new('RGB', (1200, 2400), 'white')
        output = io.BytesIO()
        image.save(output, 'PNG')
        uploaded = {'filename': 'manufacturer-original.png', 'data_url': 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()}
        product = self.store.edit_product({'name': 'New manufacturer family', 'source_url': 'https://manufacturer.example/family',
                    'images': [uploaded], 'brochure_details': 'Manufacturer-supplied details.'})
        new_job = self.store.create_jobs({'images': [image_file()]})[0]
        job = self.store.job(new_job['id'], internal=True)
        snapshot = job['_snapshot']
        initial = response(snapshot, product['id'], status='not_sure')
        initial['results'][0]['result']['decision']['top_two'] = [product['id'], 'dyson_v15_detect']
        self.script = [{'objects': [target()]}, initial, response(snapshot, product['id'])]
        matches = self.engine().run(job, lambda stage: None)
        supplied = [(label, path) for label, path in self.created[0].seen[-1]['images'] if label.startswith('Original manufacturer detail ')]
        self.assertEqual(len(supplied), 2)
        self.assertEqual(supplied[0][0], 'Original manufacturer detail ' + product['id'])
        with Image.open(supplied[0][1]) as detail:
            self.assertEqual(detail.size, (768, 1536))
        original = self.store.media(product['images'][0]['id'])[0]
        self.assertEqual(original.read_bytes(), output.getvalue())
        self.assertEqual(matches[0]['product_id'], product['id'])
        raw = response(snapshot, product['id'])
        raw['results'][0]['result']['feature_checks'][0]['reference_view'] = 'original_detail'
        with self.assertRaises(ValueError):
            validate_batch(raw, [target()], snapshot)
        self.assertEqual(validate_batch(raw, [target()], snapshot, [product['id']])['o1']['decision']['status'], 'match')

    def test_empty_or_accessory_inventory_does_not_pay_for_family_comparison(self):
        self.script = [{'objects': []}]
        self.assertEqual(self.engine().run(self.job, lambda stage: None), [])
        self.assertEqual(len(self.created[0].seen), 1)
        other = self.store.create_jobs({'images': [image_file()]})[0]
        accessory = target()
        accessory.update(role='accessory', visibility='part_only')
        self.script = [{'objects': [accessory]}]
        result = self.engine().run(self.store.job(other['id'], internal=True), lambda stage: None)
        self.assertEqual(result[0]['status'], 'not_sure')
        self.assertEqual(len(self.created[-1].seen), 1)

    def test_cumulative_budget_and_last_finish_are_carried_between_jobs(self):
        folder = self.ledgers / 'old-job'
        folder.mkdir()
        finished = time.time() - 3
        (folder / 'calls.jsonl').write_text(json.dumps({'job_id': 'old-request', 'status': 'ok', 'estimated_cost_usd': .2, 'request_finished_unix': finished}) + '\n')
        (folder / 'inflight.json').write_text(json.dumps({'unknown': {'reserved_cost_usd': .1}}))
        client = self.engine()._client(self.job['id'])
        self.assertAlmostEqual(client.config['budget']['prior_accounted_inr'], 30)
        self.assertAlmostEqual(client.config['budget']['stage_max_inr'],
                               min(RUNTIME_CAP_INR, STAGE_CAP_INR - HISTORICAL_STAGE_GUARD_INR) - 30)
        self.assertLess(abs((time.monotonic() - client.last_request_finished_at) - 3), 1)
        self.assertAlmostEqual(settings(self.ledgers)['stage_remaining_inr'],
                               STAGE_CAP_INR - HISTORICAL_STAGE_GUARD_INR - 30)

    def test_budget_stops_before_a_new_paid_request(self):
        folder = self.ledgers / 'old-job'
        folder.mkdir()
        limit = min(RUNTIME_CAP_INR, STAGE_CAP_INR - HISTORICAL_STAGE_GUARD_INR)
        (folder / 'inflight.json').write_text(json.dumps({'unknown': {'reserved_cost_usd': (limit - 1) / 100}}))
        self.script = [{'objects': []}]
        with self.assertRaises(BudgetError):
            self.engine().run(self.job, lambda stage: None)
        self.assertEqual(self.created[0].seen, [])
        self.assertAlmostEqual(ledger_accounting(self.ledgers)['spent_inr'], limit - 1)

    def test_oversized_context_stops_before_transport(self):
        self.job['_snapshot'][0]['brochure_details'] = 'Manufacturer text. ' * 20000
        self.script = [{'objects': [target()]}, response(self.snapshot)]
        with self.assertRaises(ValueError):
            self.engine().run(self.job, lambda stage: None)
        self.assertEqual(len(self.created[0].seen), 1)

    def test_accounting_retains_unknowns_without_double_count_and_rejects_nonfinite(self):
        folder = self.ledgers / 'old-job'
        folder.mkdir()
        (folder / 'calls.jsonl').write_text(json.dumps({'job_id': 'done', 'status': 'error', 'estimated_cost_usd': .05}) + '\n' + json.dumps({'job_id': 'done', 'status': 'validation_error', 'estimated_cost_usd': 0}) + '\n')
        (folder / 'inflight.json').write_text(json.dumps({'done': {'reserved_cost_usd': .1}, 'pending': {'reserved_cost_usd': .2}}))
        self.assertAlmostEqual(ledger_accounting(self.ledgers)['spent_inr'], 25)
        (folder / 'calls.jsonl').write_text('{"job_id":"bad","status":"ok","estimated_cost_usd":NaN}\n')
        with self.assertRaises(ValueError):
            ledger_accounting(self.ledgers)


if __name__ == '__main__':
    unittest.main()
