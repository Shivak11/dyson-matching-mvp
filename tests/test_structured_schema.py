"""Provider shapes are strict, stage-specific and passed through real inference."""
import tempfile
import unittest
from pathlib import Path

from test_webapp import fixture_root, image_file
from test_webapp_inference import FakeClient, response, target
from webapp.inference import Inference, FEATURES
from webapp.schemas import inventory_schema, comparison_schema
from webapp.store import Store


class StructuredSchemaTests(unittest.TestCase):
    def assert_closed(self, schema):
        if schema.get('type') == 'object':
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(schema['required']), set(schema['properties']))
            for value in schema['properties'].values():
                self.assert_closed(value)
        if schema.get('type') == 'array':
            self.assert_closed(schema['items'])
        for option in schema.get('anyOf', []):
            self.assert_closed(option)

    def test_every_nested_object_is_closed_and_all_fields_are_required(self):
        for schema in (inventory_schema(), inventory_schema(['view_1', 'view_2']),
                       comparison_schema(['o1'], ['p1', 'p2']),
                       comparison_schema(['o1'], ['p1'], ['view_1', 'view_2'])):
            self.assert_closed(schema)

    def test_inventory_bounds_and_nullable_hidden_feature_coordinates(self):
        objects = inventory_schema()['properties']['objects']
        self.assertEqual(objects['maxItems'], 20)
        machine = objects['items']['properties']
        self.assertEqual(machine['role']['enum'], ['machine', 'partial_machine', 'accessory'])
        observation = machine['observations']['items']['properties']
        self.assertEqual(set(observation['feature']['enum']), FEATURES)
        box, null = observation['box_2d']['anyOf']
        self.assertEqual(null, {'type': 'null'})
        self.assertEqual((box['minItems'], box['maxItems']), (4, 4))
        self.assertEqual(box['items'], {'type': 'number', 'minimum': 0, 'maximum': 1000})

    def test_comparison_requires_exact_detail_key_and_candidate_constraints(self):
        rows = comparison_schema(['o1', 'o2'], ['p1', 'p2'])['properties']['results']
        self.assertEqual((rows['minItems'], rows['maxItems']), (2, 2))
        row = rows['items']['properties']
        self.assertEqual(row['object_id']['enum'], ['o1', 'o2'])
        result = row['result']['properties']
        feature = result['feature_checks']['items']['properties']
        self.assertIn('detail', feature)
        self.assertNotIn('detail: short visible diagnostic comparison', feature)
        self.assertEqual(feature['detail'], {'type': 'string', 'minLength': 1})
        self.assertEqual(feature['product']['enum'], ['p1', 'p2'])
        self.assertEqual(feature['reference_view']['enum'], ['plate'])
        self.assertEqual(result['candidate_checks']['minItems'], 2)
        self.assertEqual(result['decision']['properties']['confidence']['type'], 'integer')
        self.assertNotIn('cross_view_consistency', result)

    def test_joint_schema_limits_views_and_requires_consistency(self):
        views = ['view_1', 'view_2', 'view_3']
        inventory = inventory_schema(views)['properties']['views']
        self.assertEqual((inventory['minItems'], inventory['maxItems']), (3, 3))
        self.assertEqual(inventory['items']['properties']['view_id']['enum'], views)
        result = comparison_schema(['o1'], ['p1'], views)['properties']['results']['items']['properties']['result']['properties']
        self.assertEqual(result['feature_checks']['items']['properties']['query_view']['enum'], views)
        self.assertEqual(result['decisive_view']['anyOf'][0]['enum'], views)
        self.assertEqual(result['cross_view_consistency']['properties']['status']['enum'],
                         ['consistent', 'conflicting', 'insufficient_evidence'])
        refined = comparison_schema(['o1'], ['p1'], available_originals=['p1'])
        feature = refined['properties']['results']['items']['properties']['result']['properties']['feature_checks']['items']['properties']
        self.assertEqual(feature['reference_view']['enum'], ['plate', 'original_detail'])

    def test_inference_passes_schema_for_each_single_photo_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture_root(directory)
            store = Store(root, root / 'var')
            job = store.create_jobs({'images': [image_file()]})[0]
            job = store.job(job['id'], internal=True)
            created = []

            class SchemaClient(FakeClient):
                def generate(self, job_id, model, prompt, images, schema=None):
                    self.schemas.append(schema)
                    return super().generate(job_id, model, prompt, images)

            def factory(*args, **options):
                client = SchemaClient(*args, **options)
                client.schemas = []
                client.responses = [{'objects': [target()]}, response(job['_snapshot'])]
                created.append(client)
                return client

            matches = Inference(root, root / 'var/runtime', store, factory).run(job, lambda stage: None)
            self.assertEqual(matches[0]['product_id'], 'dyson_v15_detect')
            self.assertEqual(created[0].schemas[0], inventory_schema())
            self.assertEqual(created[0].schemas[1], comparison_schema(['o1'], [row['id'] for row in job['_snapshot']]))


if __name__ == '__main__':
    unittest.main()
