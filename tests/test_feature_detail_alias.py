"""Only the observed description-key alias is repaired; evidence gates stay intact."""
import copy
import unittest

from test_webapp_inference import response, target
from webapp.inference import validate_batch


ALIAS = 'detail: short visible diagnostic comparison'


class FeatureDetailAliasTests(unittest.TestCase):
    snapshot = [{'id': 'dyson_v15_detect'}]

    def aliased_response(self):
        raw = response(self.snapshot)
        for check in raw['results'][0]['result']['feature_checks']:
            check[ALIAS] = check.pop('detail')
        return raw

    def test_exact_alias_repairs_without_mutating_raw_or_adding_evidence(self):
        raw = self.aliased_response()
        before = copy.deepcopy(raw)
        item = validate_batch(raw, [target()], self.snapshot)['o1']
        self.assertEqual(item['decision']['status'], 'match')
        self.assertEqual(item['decision']['product'], 'dyson_v15_detect')
        self.assertEqual(item['decision']['evidence'], ['Visible diagnostic comparison.'])
        self.assertEqual(len(item['format_repairs']), 2)
        self.assertTrue(all(ALIAS in repair for repair in item['format_repairs']))
        self.assertEqual(raw, before)

    def test_canonical_detail_is_authoritative_even_when_alias_conflicts(self):
        raw = self.aliased_response()
        check = raw['results'][0]['result']['feature_checks'][0]
        check['detail'] = 'Canonical visible body comparison.'
        check[ALIAS] = 'Conflicting alias description.'
        item = validate_batch(raw, [target()], self.snapshot)['o1']
        self.assertEqual(item['feature_checks'][0]['detail'], check['detail'])
        self.assertNotIn(check[ALIAS], item['decision']['evidence'])
        for invalid in (None, False, 1, '', '   '):
            with self.subTest(canonical=invalid), self.assertRaises(ValueError):
                check['detail'] = invalid
                validate_batch(raw, [target()], self.snapshot)

    def test_missing_malformed_or_unrecognised_alias_is_not_rescued(self):
        for value in (None, False, 1, [], {}, '', '   '):
            raw = self.aliased_response()
            raw['results'][0]['result']['feature_checks'][0][ALIAS] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_batch(raw, [target()], self.snapshot)
        for key in (None, 'detail: visible comparison', ALIAS + ' '):
            raw = self.aliased_response()
            check = raw['results'][0]['result']['feature_checks'][0]
            value = check.pop(ALIAS)
            if key is not None:
                check[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_batch(raw, [target()], self.snapshot)

    def test_alias_does_not_weaken_region_feature_or_match_schema_gates(self):
        for mutation in ('invalid_box', 'unknown_product', 'unknown_feature', 'fractional_confidence'):
            raw = self.aliased_response()
            item = raw['results'][0]['result']
            if mutation == 'invalid_box':
                item['feature_checks'][0]['query_box_2d'] = [0, 0, 1001, 1000]
            elif mutation == 'unknown_product':
                item['feature_checks'][0]['product'] = 'unknown'
            elif mutation == 'unknown_feature':
                item['feature_checks'][0]['feature'] = 'unknown'
            else:
                item['decision']['confidence'] = 0.95
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_batch(raw, [target()], self.snapshot)
        raw = self.aliased_response()
        raw['results'][0]['result']['feature_checks'][0]['query_box_2d'] = [0, 0, 90, 90]
        machine = target()
        machine['box_2d'] = [100, 100, 900, 900]
        item = validate_batch(raw, [machine], self.snapshot)['o1']
        self.assertEqual(item['decision']['status'], 'not_sure')
        self.assertIsNone(item['decision']['product'])
        self.assertEqual(len(item['unverified_feature_checks']), 1)


if __name__ == '__main__':
    unittest.main()
