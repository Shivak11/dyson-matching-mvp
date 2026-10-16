import copy
import math
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from evidence_v2 import (OBSERVE_PROMPT, build_match_prompt, build_refine_prompt,
                         needs_refinement, select_candidate_ids,
                         validate_match_result, validate_observation)


class EvidenceProtocolTests(unittest.TestCase):
    def obj(self, name='o1', role='machine', parent=None):
        return {'object_id': name, 'role': role, 'parent_id': parent,
                'box_2d': [100, 100, 900, 900],
                'visibility': 'whole_machine' if role == 'machine' else 'part_only',
                'observations': [{'feature': 'bin', 'visible': True,
                                  'detail': 'A transparent bin is visible.',
                                  'box_2d': [200, 200, 400, 500]}],
                'readable_identifier': ''}

    def result(self):
        return {'decision': {'status': 'match', 'product': 'a', 'confidence': 96,
                             'top_two': ['a', 'b'], 'evidence': ['Visible release control.'],
                             'missing_evidence': [], 'contradictions': [], 'retake': ''},
                'candidate_checks': [{'product': 'a', 'outcome': 'confirmed', 'evidence': 'Release control.'},
                                     {'product': 'b', 'outcome': 'contradicted', 'evidence': 'Different body.'}],
                'decisive_region': [200, 200, 400, 500], 'refinement_reason': ''}

    def test_connected_accessory_does_not_cancel_machine(self):
        raw = {'objects': [self.obj(), self.obj('o2', 'accessory', 'o1')]}
        out = validate_observation(raw)
        self.assertEqual([o['object_id'] for o in out['machines']], ['o1'])
        self.assertEqual(len(out['objects']), 2)
        self.assertEqual(raw['objects'][1]['role'], 'accessory')

    def test_detached_clear_accessory_excluded_and_second_partial_retained(self):
        out = validate_observation({'objects': [self.obj(), self.obj('o2', 'accessory'),
                                               self.obj('o3', 'partial_machine')]})
        self.assertEqual([o['object_id'] for o in out['machines']], ['o1', 'o3'])

    def test_accessory_only_frame_retained_without_inventing_identifier(self):
        raw = {'objects': [self.obj('o1', 'accessory'), self.obj('o2', 'accessory')]}
        raw['objects'][0]['readable_identifier'] = 'Tool identifier'
        raw['objects'][1]['box_2d'] = [0, 0, 200, 200]
        raw['objects'][1]['observations'][0]['box_2d'] = [20, 20, 100, 100]
        out = validate_observation(raw)
        self.assertEqual(len(out['machines']), 1)
        target = out['machines'][0]
        self.assertEqual(target['role'], 'partial_machine')
        self.assertTrue(target['accessory_only'])
        self.assertEqual(target['box_2d'], [0, 0, 900, 900])
        self.assertEqual(target['readable_identifier'], '')
        self.assertEqual(raw['objects'][0]['role'], 'accessory')

    def test_invalid_parents_cycles_and_independent_child_rejected(self):
        cases = [[self.obj('o1', 'accessory', 'missing')],
                 [self.obj('o1', 'accessory', 'o1')],
                 [self.obj('o1', 'accessory', 'o2'), self.obj('o2', 'accessory', 'o1')],
                 [self.obj(), self.obj('o2', 'partial_machine', 'o1')],
                 [self.obj('o1', 'accessory', False)]]
        for objects in cases:
            with self.subTest(objects=objects), self.assertRaises(ValueError):
                validate_observation({'objects': objects})

    def test_bad_ids_roles_boxes_and_details_rejected(self):
        changes = [('object_id', '../escape'), ('role', 'unknown'),
                   ('box_2d', None), ('box_2d', [0, 0, math.nan, 2]),
                   ('visibility', 'unknown'), ('readable_identifier', False)]
        for key, value in changes:
            obj = self.obj(); obj[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_observation({'objects': [obj]})
        with self.assertRaises(ValueError):
            validate_observation({'objects': [self.obj(), self.obj()]})
        obj = self.obj(); obj['observations'][0]['visible'] = 'false'
        with self.assertRaises(ValueError): validate_observation({'objects': [obj]})
        obj = self.obj(); obj['observations'] *= 5
        with self.assertRaises(ValueError): validate_observation({'objects': [obj]})

    def test_feature_cannot_belong_to_another_machine(self):
        obj=self.obj();obj['box_2d']=[100,100,300,300]
        obj['observations'][0]['box_2d']=[800,800,900,900]
        with self.assertRaises(ValueError):validate_observation({'objects':[obj]})

    def test_fractional_confidence_is_not_silently_demoted_or_rescaled(self):
        raw=self.result();raw['decision']['confidence']=.95
        with self.assertRaises(ValueError):validate_match_result(raw,['a','b'])
        raw['decision']['confidence']=95
        self.assertEqual(validate_match_result(raw,['a','b'])['decision']['status'],'match')
        self.assertIn('integer percentage from 0 to 100',build_match_prompt({},['a','b'],{'a':{},'b':{}}))

    def test_hidden_feature_has_no_visible_region(self):
        obj = self.obj(); observation = obj['observations'][0]
        observation.update(visible=False, detail='Controls are outside the frame.', box_2d=None)
        out = validate_observation({'objects': [obj]})
        self.assertIsNone(out['machines'][0]['observations'][0]['box_2d'])
        observation['box_2d'] = [0, 0, 100, 100]
        with self.assertRaises(ValueError): validate_observation({'objects': [obj]})
        self.assertEqual(validate_observation({'objects': []})['machines'], [])

    def test_all_six_expansion_and_expected_inclusion(self):
        ranking = [{'product': p} for p in 'abc']
        self.assertEqual(select_candidate_ids(ranking, list('abcdef')), list('abc'))
        self.assertEqual(select_candidate_ids(ranking, list('abcdef'), 'f'), list('abcf'))
        self.assertEqual(select_candidate_ids(ranking, list('abcdef'), 'f', True), list('abcfde'))
        self.assertEqual(select_candidate_ids([], list('abcdef')), list('abcdef'))
        self.assertEqual(ranking, [{'product': p} for p in 'abc'])
        for ranking, expected in [([{'product': 'a'}, {'product': 'a'}], None),
                                  ([{'product': 'z'}], None), ([], 'z')]:
            with self.assertRaises(ValueError): select_candidate_ids(ranking, list('abcdef'), expected)

    def test_empty_and_non_string_candidate_ids_rejected(self):
        for catalogue in ([], [''], ['   '], [False], [1], [[]]):
            with self.subTest(catalogue=catalogue), self.assertRaises(ValueError):
                select_candidate_ids([], catalogue)
        for product in ('', '  ', False, 1, []):
            with self.subTest(product=product), self.assertRaises(ValueError):
                select_candidate_ids([{'product': product}], ['a'])
            with self.subTest(expected=product), self.assertRaises(ValueError):
                select_candidate_ids([], ['a'], product)

    def test_prompt_projects_cards_without_mutating_source(self):
        card = {'name': 'A', 'in_catalog': True, 'visible_features': ['Visible control.'],
                'variant_limits': ['Colour varies.'], 'sources': ['private-evidence-url'],
                'images': [{'file': 'source.jpg', 'sha256': 'digest'}]}
        cards = {'a': card, 'outside': {**card, 'in_catalog': False}}
        before = copy.deepcopy(cards)
        prompt = build_match_prompt(self.obj(), ['a'], cards)
        context = json.loads(prompt.rsplit('\n', 1)[1])
        allowed = {'name', 'in_catalog', 'visible_features', 'variant_limits'}
        self.assertEqual(set(context['manufacturer_cards']['a']), allowed)
        self.assertEqual(set(context['non_catalogue_comparisons']['outside']), allowed)
        self.assertNotIn('private-evidence-url', prompt)
        self.assertNotIn('sha256', prompt)
        self.assertEqual(cards, before)

    def test_high_confidence_outside_always_refines(self):
        raw = self.result(); raw['decision'].update(status='not_in_catalogue', product=None, confidence=100)
        raw['candidate_checks'][0]['outcome'] = 'contradicted'
        out = validate_match_result(raw, ['a', 'b'])
        self.assertEqual(out['decision']['status'], 'not_in_catalogue')
        self.assertTrue(needs_refinement(out, [{'product': 'a'}]))

    def test_uncertainty_contradiction_retrieval_conflict_and_low_confidence_refine(self):
        for change in ({'status': 'not_sure', 'product': None},
                       {'confidence': 89}, {'contradictions': ['The release control conflicts.']}):
            raw = self.result(); raw['decision'].update(change)
            self.assertTrue(needs_refinement(validate_match_result(raw, ['a', 'b']), [{'product': 'a'}]))
        self.assertTrue(needs_refinement(self.result(), [{'product': 'b'}]))
        raw = self.result(); raw['evidence_conflict'] = True
        self.assertTrue(needs_refinement(validate_match_result(raw, ['a', 'b']), [{'product': 'a'}]))
        self.assertFalse(needs_refinement(self.result(), [{'product': 'a'}]))

    def test_strict_match_checks_and_decisive_crop_bounds(self):
        raw = self.result(); before = copy.deepcopy(raw)
        self.assertEqual(validate_match_result(raw, ['a', 'b'])['decision']['product'], 'a')
        self.assertEqual(raw, before)
        for region in ([0, 0, 0, 1000], [False, 0, 100, 100], [-1, 0, 100, 100], 'region'):
            raw = self.result(); raw['decisive_region'] = region
            with self.assertRaises(ValueError): validate_match_result(raw, ['a', 'b'])
        raw = self.result(); raw['decisive_region'] = None
        self.assertIsNone(validate_match_result(raw, ['a', 'b'])['decisive_region'])
        raw = self.result(); raw['candidate_checks'].pop()
        with self.assertRaises(ValueError): validate_match_result(raw, ['a', 'b'])
        raw = self.result(); raw['candidate_checks'][1]['outcome'] = 'confirmed'
        self.assertEqual(validate_match_result(raw, ['a', 'b'])['decision']['status'], 'not_sure')

    def test_prompts_keep_candidate_free_observation_and_grounded_refinement(self):
        self.assertNotIn('Dyson', OBSERVE_PROMPT)
        cards = {p: {'name': p, 'visible_features': ['Supported feature.']} for p in 'ab'}
        prompt = build_match_prompt(self.obj(), list('ab'), cards, 'a')
        self.assertIn('verification hypothesis', prompt)
        self.assertIn('"expected_product":"a"', prompt)
        self.assertIn('per-target result record', prompt)
        self.assertNotIn('source_label', prompt)
        refined = build_refine_prompt(self.obj(), list('ab'), cards, self.result())
        self.assertIn('original-resolution', refined)
        self.assertIn('All six catalogue families', refined)
        self.assertIn('shared accessory cannot identify', refined)


if __name__ == '__main__': unittest.main()
