import copy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import focused_protocol as focus
import test_failure_protocol as old


class FocusedProtocolTests(unittest.TestCase):
    def fixture(self,selected='R01',rival='R05'):
        helper=old.FailureProtocolTests();refs=helper.refs();target=helper.target()
        target['observations'][0]['feature']='body_layout'
        raw=helper.raw(selected);item=raw['results'][0];item['decision']['top_two']=[selected,rival]
        for check in item['reference_checks']:
            if check['reference']==selected:continue
            comparison=helper.comparison(check['reference']);comparison['relation']='conflict'
            check.update(outcome='visible_conflict',comparisons=[comparison])
        facts={'references':refs,'facts':[{'id':'IMAGE_'+alias,'kind':'reference_image','feature':'body_layout',
            'references':[alias],'panels':ref['panels'],'source_urls':['https://manufacturer.test/'+alias],
            'statement':'The saved manufacturer panels show this family structure.'} for alias,ref in refs.items()],
            'ambiguity_sets':[['R04','R08'],['R02','R03']],
            'compatibility':[{'part_code':'972213-02','references':['R02','R08'],'body_identity':False}],
        }
        facts['facts'].append({'id':'SHARED','kind':'shared','references':['R04','R08'],
            'source_urls':['https://manufacturer.test/shared'],'statement':'These controls and filter cues are shared.',
            'non_unique_features':['handle_control','display_layout','cyclone_filter','identifier']})
        baseline={'o1':{'raw':item}};rankings={'o1':[selected,rival]}
        plan=focus.plan_focus([target],baseline,rankings,facts)
        observations=[]
        for question in plan['questions']:
            feature=question['feature'];hidden=feature=='identifier'
            observations.append({'object_id':'o1','question_id':question['question_id'],
                'state':'not_visible' if hidden else 'present','box_2d':None if hidden else [110,110,400,400],
                'region_fully_visible':not hidden,'detail':'Visible structural region.' if not hidden else 'No readable model text.',
                'literal_text':'','needs_check':False,'references':[] if feature=='relationship' else [
                    {'reference':alias,'panel':alias+'-P1','state':'not_visible' if hidden else 'present',
                     'box_2d':None if hidden else [100,100,400,400],'region_fully_visible':not hidden,
                     'relation_to_query':'not_comparable' if hidden else 'same' if alias==selected else 'different',
                     'detail':'Corresponding manufacturer structure.'} for alias in plan['focus_refs']['o1']]})
        observed={'observations':observations}
        final=self.final(plan,observed,selected)
        return target,baseline,rankings,facts,plan,observed,final

    def final(self,plan,observed,selected,features=('body_layout','handle_control'),distinction='body_layout'):
        by_question={record['question_id']:record for record in observed['observations']};updates=[]
        for alias in plan['focus_refs']['o1']:
            comparisons=[]
            for feature in features if alias==selected else [distinction]:
                question='o1__'+feature;observation=by_question[question]
                ref=next(ref for ref in observation['references'] if ref['reference']==alias)
                comparisons.append({'feature':feature,'question_id':question,
                    'relation':{'same':'support','different':'conflict','not_comparable':'unobserved'}[ref['relation_to_query']],
                    'query_visible':observation['state']!='not_visible','query_box_2d':observation['box_2d'],
                    'panel':ref['panel'],'reference_visible':ref['state']!='not_visible','reference_box_2d':ref['box_2d'],
                    'detail':'The corresponding observed structures match or differ.'})
            updates.append({'reference':alias,'outcome':'supported' if alias==selected else
                            'visible_conflict' if any(c['relation']=='conflict' for c in comparisons) else 'insufficient_evidence',
                            'evidence':'Observed structural comparison.','comparisons':comparisons})
        decision=copy.deepcopy(plan['baseline']['o1']['decision']);decision.update(status='same_family',reference=selected,confidence=95)
        distinctions=[{'rival':alias,'question_id':'o1__'+distinction,'selected_panel':selected+'-P1','rival_panel':alias+'-P1',
                       'fact_ids':['IMAGE_'+selected,'IMAGE_'+alias]} for alias in plan['focus_refs']['o1'] if alias!=selected]
        return {'results':[{'object_id':'o1','decision':decision,'reference_check_updates':updates,'distinctions':distinctions}]}

    def parse(self,data,checks=None):
        target,baseline,ranks,facts,plan,observed,final=data
        return focus.validate_final(final,plan,observed,checks,facts,facts['references'])['o1']

    def test_structural_contrast_uses_three_visible_regions_and_preserves_nine_checks(self):
        data=self.fixture();before=copy.deepcopy(data);result=self.parse(data)
        self.assertEqual(data,before);self.assertEqual(result['decision']['status'],'match')
        self.assertEqual(result['focus_gate_reasons'],[])
        self.assertEqual(len(result['raw']['reference_checks']),9);self.assertEqual(len(result['candidate_checks']),6)
        self.assertEqual(len(result['raw']['carried_reference_ids']),7)
        self.assertEqual(result['raw']['focused_raw'],data[-1]['results'][0])

    def test_shared_controls_cannot_distinguish_the_documented_pair(self):
        data=list(self.fixture('R04','R08'));data[-1]=self.final(data[4],data[5],'R04',('handle_control','cyclone_filter'),'handle_control')
        result=self.parse(data)
        self.assertEqual(result['decision']['status'],'not_sure');self.assertTrue(result['focus_gate_reasons'])
        self.assertEqual(result['raw']['decision']['reference'],'R04');self.assertEqual(result['raw']['decision']['confidence'],95)
        data[-1]=self.final(data[4],data[5],'R04',('body_layout','bin_mechanism'),'bin_mechanism')
        self.assertEqual(self.parse(data,copy.deepcopy(data[5]))['decision']['status'],'match')

    def test_nonexclusive_positive_fact_and_missing_reference_pixels_do_not_establish_uniqueness(self):
        data=list(self.fixture());facts=data[3]
        facts['facts'].append({'id':'POSITIVE','kind':'positive','feature':'body_layout','references':['R01'],
            'source_urls':['https://manufacturer.test/positive'],'statement':'This family has this body feature.'})
        data[-1]['results'][0]['distinctions'][0]['fact_ids']=['POSITIVE']
        self.assertEqual(self.parse(data)['decision']['status'],'not_sure')
        data=self.fixture();observation=data[5]['observations'][0]
        rival=next(ref for ref in observation['references'] if ref['reference']=='R05')
        rival.update(state='not_visible',box_2d=None,region_fully_visible=False,relation_to_query='not_comparable')
        data[-1].update(self.final(data[4],data[5],'R01'))
        self.assertEqual(self.parse(data)['decision']['status'],'not_sure')

    def test_absence_requires_full_visibility_and_independent_agreement(self):
        data=list(self.fixture());observation=data[5]['observations'][0];observation['state']='absent'
        selected=next(ref for ref in observation['references'] if ref['reference']=='R01');selected['state']='absent'
        data[-1]=self.final(data[4],data[5],'R01',('body_layout','handle_control','bin_mechanism'))
        self.assertEqual(self.parse(data)['decision']['status'],'not_sure')
        checks={'observations':[copy.deepcopy(observation)]}
        self.assertEqual(self.parse(data,checks)['decision']['status'],'match')
        checks['observations'][0]['state']='present'
        self.assertEqual(self.parse(data,checks)['decision']['status'],'not_sure')
        observation['region_fully_visible']=False
        with self.assertRaises(ValueError):focus.validate_predicates(data[5],data[4])

    def test_changed_old_relation_requests_a_blind_check(self):
        target,baseline,ranks,facts,plan,observed,final=self.fixture()
        old_comparison=baseline['o1']['raw']['reference_checks'][0]['comparisons'][0]
        old_comparison['relation']='conflict'
        baseline['o1']['raw']['reference_checks'][0]['outcome']='insufficient_evidence'
        replanned=focus.plan_focus([target],baseline,ranks,facts,observations=observed)
        self.assertIn('o1__body_layout',replanned['check_question_ids'])

    def test_checker_is_blind_to_prior_identity_explanation_answers_and_proposed_text(self):
        target,baseline,ranks,facts,plan,observed,final=self.fixture()
        first=focus.predicate_prompt(plan,['o1__identifier'])
        altered=copy.deepcopy(plan);altered['baseline']['o1']['decision'].update(reference='R09',confidence=1,evidence=['private guess'])
        altered['targets'][0]['observations'][0]['detail']='private proposed text'
        altered['targets'][0]['readable_identifier']='private literal'
        altered['observations']=observed;altered['source_title']='private title';altered['source_url']='https://private.test'
        self.assertEqual(first,focus.predicate_prompt(altered,['o1__identifier']))
        for secret in ['private guess','private proposed text','private literal','private title','https://private.test','manufacturer.test','dyson_']:
            self.assertNotIn(secret,first)
        final_prompt=focus.final_prompt(plan,observed,None,facts)
        self.assertNotIn('https://manufacturer.test',final_prompt)
        self.assertNotIn('reference_checks',final_prompt)

    def test_ambiguity_expansion_retains_a_fourth_plausible_candidate(self):
        target,baseline,ranks,facts,_,_,_=self.fixture('R04','R02')
        plan=focus.plan_focus([target],baseline,{'o1':['R04','R02']},facts)
        self.assertEqual(set(plan['plausible_refs']['o1']),{'R04','R08','R02','R03'})
        self.assertEqual(len(plan['focus_refs']['o1']),3);self.assertEqual(plan['overflow_ids'],['o1'])
        with self.assertRaises(ValueError):focus.plan_focus([target],baseline,{'o1':['unknown']},facts)

    def test_unfocused_plausible_rival_prevents_acceptance(self):
        data=list(self.fixture());plan=data[4]
        plan['plausible_refs']['o1'].append('R07')
        result=self.parse(data)
        self.assertEqual(result['decision']['status'],'not_sure')
        self.assertIn('R07',' '.join(result['focus_gate_reasons']))

    def test_part_codes_and_generic_text_are_not_body_identifiers(self):
        for literal in ['HEPA','DYSON HEPA','972213-02','972213 02','MODEL-A']:
            data=list(self.fixture());facts=data[3];plan=data[4];observed=data[5]
            question=next(item for item in observed['observations'] if item['question_id']=='o1__identifier')
            question.update(state='present',box_2d=[110,110,400,400],region_fully_visible=True,literal_text=literal)
            for ref in question['references']:
                ref.update(state='present',box_2d=[100,100,400,400],region_fully_visible=True,
                           relation_to_query='same' if ref['reference']=='R01' else 'different')
            facts['facts'].append({'id':'MODEL_ID','kind':'model_identifier','feature':'identifier','references':['R01'],
                'source_urls':['https://manufacturer.test/identifier'],'statement':'This exact model identifier distinguishes this family.',
                'distinguishes':{'R01':['R05']},'literal_texts':[literal]})
            data[-1]=self.final(plan,observed,'R01',('body_layout','identifier'),'identifier')
            data[-1]['results'][0]['distinctions'][0]['fact_ids']=['MODEL_ID']
            checks={'observations':[copy.deepcopy(question)]}
            self.assertEqual(self.parse(data,checks)['decision']['status'],'match' if literal=='MODEL-A' else 'not_sure')
            if literal=='MODEL-A':
                checks['observations'][0]['literal_text']='MODEL-B'
                self.assertEqual(self.parse(data,checks)['decision']['status'],'not_sure')

    def test_tool_eligibility_and_independent_partial_targets_are_preserved(self):
        helper=old.FailureProtocolTests();target,baseline,ranks,facts,plan,observed,final=self.fixture()
        tool=helper.target('tool','partial_machine');tool['observations']=[{'feature':feature,'visible':True} for feature in ['dust_bin','control','cleaner_head']]
        partial=helper.target('partial','partial_machine');partial['observations'][0]['feature']='filter'
        self.assertFalse(focus.eligible_target(tool));self.assertTrue(focus.eligible_target(partial))
        second=copy.deepcopy(baseline['o1']);second['raw']['object_id']='partial'
        plan=focus.plan_focus([target,tool,partial],{**baseline,'partial':second},{'o1':['R01','R05'],'partial':['R01','R05']},facts)
        self.assertEqual(plan['active_ids'],['o1','partial']);self.assertEqual(plan['passive_ids'],['tool'])
        self.assertEqual([target['object_id'] for target in plan['targets']],['o1','tool','partial'])
        self.assertEqual(plan['targets'][0]['observations'],target['observations'])
        passive=focus.plan_focus([tool],{}, {},facts)
        self.assertEqual(passive['active_ids'],[])
        with self.assertRaises(ValueError):focus.plan_focus([target],baseline,ranks,facts,ocr={'native':'forbidden'})

    def test_predicate_regions_visibility_text_and_coverage_are_strict(self):
        target,baseline,ranks,facts,plan,observed,final=self.fixture()
        for variant in ['nan','outside','reference','hidden','hidden_text','panel','object','duplicate','missing','relation','unknown']:
            raw=copy.deepcopy(observed);item=raw['observations'][0]
            if variant=='nan':item['box_2d']=[110,110,math.nan,400]
            if variant=='outside':item['box_2d']=[0,0,50,50]
            if variant=='reference':item['references'][0]['box_2d']=[0,0,1001,1000]
            if variant=='hidden':item.update(state='not_visible',region_fully_visible=False)
            if variant=='hidden_text':raw['observations'][5]['literal_text']='unseen'
            if variant=='panel':item['references'][0]['panel']='R09-P1'
            if variant=='object':item['object_id']='other'
            if variant=='duplicate':raw['observations'].append(copy.deepcopy(item))
            if variant=='missing':raw['observations'].pop()
            if variant=='relation':item['references'][0]['relation_to_query']='guess'
            if variant=='unknown':item['question_id']='o1__unknown'
            with self.subTest(variant=variant),self.assertRaises(ValueError):focus.validate_predicates(raw,plan)
        question='o1__body_layout';subset={'observations':[observed['observations'][0]]}
        self.assertEqual(focus.validate_predicates(subset,plan,[question]),subset)
        with self.assertRaises(ValueError):focus.validate_predicates(subset,plan,[question,question])

    def test_relationships_cannot_invent_parents_or_remove_independent_targets(self):
        target,baseline,ranks,facts,plan,observed,final=self.fixture()
        relationship=observed['observations'][-1]
        relationship.update(relationship='connected_component',related_object_id='missing')
        with self.assertRaises(ValueError):focus.validate_predicates(observed,plan)
        relationship.update(relationship='independent_machine',related_object_id=None)
        self.assertEqual(focus.validate_predicates(observed,plan)['observations'][-1]['relationship'],'independent_machine')
        self.assertEqual(plan['active_ids'],['o1'])

    def test_final_citations_geometry_scope_and_two_feature_support_are_strict(self):
        for variant in ['fact','comparison','panel','duplicate','missing','one_feature','region','unknown_object']:
            data=list(self.fixture());item=data[-1]['results'][0]
            if variant=='fact':item['distinctions'][0]['fact_ids']=['UNKNOWN']
            if variant=='comparison':item['reference_check_updates'][0]['comparisons'][0]['question_id']='o1__identifier'
            if variant=='panel':item['reference_check_updates'][0]['comparisons'][0]['panel']='R09-P1'
            if variant=='duplicate':item['reference_check_updates'].append(copy.deepcopy(item['reference_check_updates'][0]))
            if variant=='missing':item['reference_check_updates'].pop()
            if variant=='one_feature':item['reference_check_updates'][0]['comparisons'].pop()
            if variant=='region':item['reference_check_updates'][0]['comparisons'][0]['query_box_2d']=[110,110,500,500]
            if variant=='unknown_object':item['object_id']='missing'
            if variant=='one_feature':self.assertEqual(self.parse(data)['decision']['status'],'not_sure')
            else:
                with self.subTest(variant=variant),self.assertRaises(ValueError):self.parse(data)

    def test_unknown_old_checks_do_not_expand_beyond_the_closest_candidates(self):
        target,baseline,ranks,facts,plan,observed,final=self.fixture()
        for check in baseline['o1']['raw']['reference_checks']:
            check.update(outcome='insufficient_evidence',comparisons=[])
        plan=focus.plan_focus([target],baseline,ranks,facts)
        self.assertEqual(plan['focus_refs']['o1'],['R01','R05'])
        self.assertEqual(len(plan['baseline']['o1']['reference_checks']),9)
        self.assertEqual(plan['overflow_ids'],[])

    def test_two_confirmed_absences_are_not_two_positive_supports(self):
        data=list(self.fixture())
        for observation in data[5]['observations'][:2]:
            observation['state']='absent'
            next(ref for ref in observation['references'] if ref['reference']=='R01')['state']='absent'
        data[-1]=self.final(data[4],data[5],'R01')
        result=self.parse(data,copy.deepcopy(data[5]))
        self.assertEqual(result['decision']['status'],'not_sure')
        self.assertIn('positively visible',' '.join(result['focus_gate_reasons']))

    def test_independent_agreement_requires_substantial_query_and_reference_overlap(self):
        for variant in ['query','reference','panel']:
            data=list(self.fixture());observation=data[5]['observations'][0];observation['needs_check']=True
            check=copy.deepcopy(observation)
            if variant=='query':check['box_2d']=[399,399,700,700]
            if variant=='reference':check['references'][0]['box_2d']=[399,399,700,700]
            if variant=='panel':check['references'][0]['panel']='R01-P2'
            with self.subTest(variant=variant):
                self.assertEqual(self.parse(data,{'observations':[check]})['decision']['status'],'not_sure')
        self.assertFalse(focus._overlap([0,0,500,500],[499,499,999,999]))
        self.assertTrue(focus._overlap([0,0,500,500],[0,0,500,500]))

    def test_canonical_prompts_do_not_depend_on_object_key_order(self):
        target,baseline,ranks,facts,plan,observed,final=self.fixture()
        def reorder(value):
            if isinstance(value,dict):return {key:reorder(value[key]) for key in reversed(value)}
            if isinstance(value,list):return [reorder(item) for item in value]
            return value
        self.assertEqual(focus.predicate_prompt(plan),focus.predicate_prompt(reorder(plan)))
        self.assertEqual(focus.final_prompt(plan,observed,None,facts),focus.final_prompt(reorder(plan),reorder(observed),None,reorder(facts)))
        bad=copy.deepcopy(facts);bad['facts'][0]['source_urls']=[]
        with self.assertRaises(ValueError):focus.plan_focus([target],baseline,ranks,bad)


if __name__=='__main__':unittest.main()
