import copy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from failure_protocol import inventory_prompt,validate_inventory,build_comparison_prompt,validate_comparison
from evaluate_pipeline import evaluate


class FailureProtocolTests(unittest.TestCase):
    def refs(self):
        products=['dyson_big_ball','dyson_v8_absolute','dyson_v12_detect_slim','dyson_v15_detect',
                  'dyson_v16_piston_animal','dyson_wash_g1','dyson_v11','dyson_gen5detect','shark_stratos']
        return {f'R{i:02}':{'product':product,'in_catalog':i<=6,'panels':[f'R{i:02}-P1',f'R{i:02}-P2'],
                           'name':'PRIVATE MODEL NAME','source_url':'private-source','old_answer':'old-secret'}
                for i,product in enumerate(products,1)}

    def target(self,name='o1',role='machine'):
        return {'object_id':name,'role':role,'parent_id':None,'box_2d':[100,100,900,900],
                'visibility':'whole_machine' if role=='machine' else 'part_only','readable_identifier':'',
                'observations':[{'feature':'body','visible':True,'box_2d':[110,110,800,800],'detail':'Visible bin and body.'}]}

    def comparison(self,alias='R01',feature='body_layout'):
        return {'feature':feature,'relation':'support','query_visible':True,'query_box_2d':[110,110,400,400],
                'panel':alias+'-P1','reference_visible':True,'reference_box_2d':[100,100,400,400],
                'detail':'Corresponding bin and motor layout are visible.'}

    def raw(self,alias='R01'):
        checks=[{'reference':name,'outcome':'insufficient_evidence','evidence':'No exclusive visible distinction.',
                 'comparisons':[]} for name in self.refs()]
        check=next(check for check in checks if check['reference']==alias)
        check.update(outcome='supported',evidence='Visible body layout and controls distinguish this family.',
                     comparisons=[self.comparison(alias),self.comparison(alias,'handle_control')])
        return {'results':[{'object_id':'o1','decision':{'status':'same_family','reference':alias,'confidence':95,
                'top_two':[alias,'R02' if alias!='R02' else 'R01'],'evidence':['Body layout and control arrangement match.'],
                'missing_evidence':[],'contradictions':[],'retake':''},'reference_checks':checks,'other_brand_evidence':[]}]}

    def validate(self,raw):
        return validate_comparison(raw,[self.target()],self.refs())['o1']

    def test_inventory_keeps_accessories_unassigned_and_true_partial_machines(self):
        body=self.target();tool=self.target('tool','accessory');second=self.target('second','partial_machine')
        out=validate_inventory({'objects':[body,tool,second]})
        self.assertEqual([item['object_id'] for item in out['machines']],['o1','second'])
        self.assertIsNone(out['objects'][1]['parent_id'])
        only=validate_inventory({'objects':[tool]})
        self.assertTrue(only['machines'][0]['accessory_only'])
        self.assertIn('separate body, motor, bin or handle',inventory_prompt())
        self.assertIn('unassigned accessory',inventory_prompt())
        hidden=self.target();hidden['observations'][0].update(visible=False,box_2d=None)
        validate_inventory({'objects':[hidden]})
        hidden['observations'][0]['box_2d']=[100,100,200,200]
        with self.assertRaises(ValueError):validate_inventory({'objects':[hidden]})

    def test_catalogue_and_known_outside_mapping_preserve_raw_and_alternatives(self):
        for alias,status,product in [('R01','match','dyson_big_ball'),('R08','not_in_catalogue',None)]:
            raw=self.raw(alias);before=copy.deepcopy(raw);out=self.validate(raw)
            self.assertEqual(raw,before);self.assertEqual(out['raw'],raw['results'][0])
            self.assertEqual(out['decision']['status'],status);self.assertEqual(out['decision']['product'],product)
            self.assertEqual(out['matched_product'],self.refs()[alias]['product'])
            self.assertEqual(out['top_two'][0],self.refs()[alias]['product'])
            self.assertEqual(out['decision']['confidence'],95)
            self.assertEqual(len(out['candidate_checks']),6)
            self.assertEqual(len(out['raw']['reference_checks']),9)

    def test_two_distinct_visible_diagnostic_feature_types_are_required(self):
        for variant in ['one','duplicate','conflict','ambiguous']:
            raw=self.raw();checks=raw['results'][0]['reference_checks'];chosen=checks[0]
            if variant=='one':chosen['comparisons'].pop()
            if variant=='duplicate':chosen['comparisons'][1]['feature']='body_layout'
            if variant=='conflict':chosen['comparisons'][1]['relation']='conflict'
            if variant=='ambiguous':checks[1]['outcome']='supported'
            out=self.validate(raw)
            self.assertEqual(out['decision']['status'],'not_sure')
            self.assertTrue(out['gate_reasons'])
        raw=self.raw();raw['results'][0]['reference_checks'][0]['comparisons'][0]['feature']='colour'
        with self.assertRaises(ValueError):self.validate(raw)

    def test_hidden_feature_cannot_supply_support_or_conflict(self):
        for relation in ['support','conflict']:
            raw=self.raw();comparison=raw['results'][0]['reference_checks'][0]['comparisons'][0]
            comparison.update(relation=relation,query_visible=False,query_box_2d=None)
            with self.assertRaises(ValueError):self.validate(raw)
        raw=self.raw();check=raw['results'][0]['reference_checks'][0]
        check.update(outcome='visible_conflict',comparisons=[])
        with self.assertRaises(ValueError):self.validate(raw)
        raw=self.raw();comparison=raw['results'][0]['reference_checks'][0]['comparisons'][0]
        comparison.update(relation='unobserved',query_visible=False,query_box_2d=None)
        self.assertEqual(self.validate(raw)['decision']['status'],'not_sure')

    def test_all_nine_checks_and_all_objects_are_mandatory(self):
        for variant in ['missing','duplicate','unknown']:
            raw=self.raw();checks=raw['results'][0]['reference_checks']
            if variant=='missing':checks.pop()
            if variant=='duplicate':checks[-1]=copy.deepcopy(checks[0])
            if variant=='unknown':checks[-1]['reference']='R10'
            with self.subTest(variant=variant),self.assertRaises(ValueError):self.validate(raw)
        for ids in [[],['o1','o1'],['o1','o2']]:
            raw=self.raw();item=raw['results'][0]
            raw['results']=[{**copy.deepcopy(item),'object_id':name} for name in ids]
            with self.assertRaises(ValueError):self.validate(raw)
        raw=self.raw();raw['results'].append({**copy.deepcopy(raw['results'][0]),'object_id':'o2'})
        out=validate_comparison(raw,[self.target(),self.target('o2')],self.refs())
        self.assertEqual(set(out),{'o1','o2'})

    def test_bad_regions_and_other_family_panels_are_rejected(self):
        for side,box in [('query',[-1,0,100,100]),('query',[0,0,50,50]),
                         ('query',[100,100,100,200]),('reference',[0,0,1001,1000]),
                         ('reference',[False,0,100,100]),('reference',[0,0,math.nan,100])]:
            raw=self.raw();raw['results'][0]['reference_checks'][0]['comparisons'][0][side+'_box_2d']=box
            with self.subTest(side=side,box=box),self.assertRaises(ValueError):self.validate(raw)
        raw=self.raw();raw['results'][0]['reference_checks'][0]['comparisons'][0]['panel']='R02-P1'
        with self.assertRaises(ValueError):self.validate(raw)

    def test_confidence_threshold_and_integer_units(self):
        raw=self.raw();raw['results'][0]['decision']['confidence']=89
        self.assertEqual(self.validate(raw)['decision']['status'],'not_sure')
        raw['results'][0]['decision']['confidence']=90
        self.assertEqual(self.validate(raw)['decision']['status'],'match')
        for value in [True,95.0,.95,-1,101]:
            raw=self.raw();raw['results'][0]['decision']['confidence']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.validate(raw)

    def test_alias_selection_and_alternatives_are_strict(self):
        for key,value in [('reference','dyson_big_ball'),('reference',None),('top_two',['R01','R01']),
                          ('top_two',['R01','R10']),('top_two',['R01','R02','R03'])]:
            raw=self.raw();raw['results'][0]['decision'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.validate(raw)
        refs=self.refs();refs.pop('R09')
        with self.assertRaises(ValueError):validate_comparison(self.raw(),[self.target()],refs)

    def test_unregistered_other_brand_remains_advisory_with_literal_reading(self):
        raw=self.raw();item=raw['results'][0]
        item['decision'].update(status='other_brand',reference=None)
        item['reference_checks'][0].update(outcome='insufficient_evidence',comparisons=[])
        self.assertEqual(self.validate(raw)['decision']['status'],'not_sure')
        for text,expected in [('HEPA','not_sure'),('V12 Detect Slim','not_sure'),('Tineco','not_sure'),
                              ('Hoover','not_sure'),('Dyson','not_sure'),('Shark','not_sure')]:
            item['other_brand_evidence']=[{'text':text,'query_box_2d':[100,100,200,200]}]
            self.assertEqual(self.validate(raw)['decision']['status'],expected)
        item['other_brand_evidence'][0]['query_box_2d']=[0,0,10,10]
        with self.assertRaises(ValueError):self.validate(raw)

    def test_known_outside_reference_and_catalogue_checks_work_with_existing_evaluator(self):
        references=self.refs()
        catalogue=[entry['product'] for entry in references.values() if entry['in_catalog']]
        rows=[];results=[];detections={}
        for image_id,alias in [('catalogue','R01'),('negative','R09')]:
            raw=self.raw(alias);raw['results'][0]['decision']['confidence']=90
            mapped=self.validate(raw)
            self.assertEqual(len(mapped['raw']['reference_checks']),9)
            self.assertEqual({check['product'] for check in mapped['candidate_checks']},set(catalogue))
            rows.append({'image_id':image_id,'labels':[references[alias]['product']],
                         'evaluation_role':'labelled_single'})
            instance=image_id+'_o1'
            results.append({'image_id':image_id,'instance_id':instance,'model':'neutral',
                            'variant':'comparison','candidates':catalogue,'supplied_candidates':catalogue,**mapped})
            detections[image_id]=[{'instance_id':instance}]
        group=evaluate(rows,results,catalogue,detections)['groups'][0]
        self.assertEqual(group['metrics']['correct_total'],2)
        self.assertEqual(group['metrics']['correct_non_catalogue_rejections'],1)
        self.assertEqual(group['metrics']['confidently_wrong_count'],0)
        self.assertEqual(group['verification']['evaluated_pair_count'],12)
        outside=next(row for row in group['per_photo'] if row['image_id']=='negative')
        self.assertEqual(outside['status'],'not_in_catalogue')
        self.assertEqual(outside['confidence'],90)

    def test_prompt_projects_neutral_inputs_without_model_names_or_old_answers(self):
        target=self.target();target.update(product='dyson_v8_absolute',source_label='source-secret',old_answer='answer-secret')
        target['observations'][0]['source']='observation-source-secret'
        prompt=build_comparison_prompt([target],self.refs())
        for text in ['dyson_','shark_stratos','PRIVATE MODEL NAME','private-source','old-secret','source-secret','answer-secret','observation-source-secret']:
            self.assertNotIn(text,prompt)
        context=json.loads(prompt.rsplit('\n',1)[1])
        self.assertEqual(set(context['references']),set(self.refs()))
        self.assertEqual(context['references']['R01'],{'panels':['R01-P1','R01-P2']})
        self.assertIn('WHOLE SCENE',prompt);self.assertIn('PANEL',prompt)

    def test_embedded_json_is_canonical_across_key_order_and_does_not_mutate(self):
        refs=self.refs();target=self.target();before=copy.deepcopy((refs,target))
        first=build_comparison_prompt([target],refs)
        def reorder(value):
            if isinstance(value,dict):return {key:reorder(value[key]) for key in reversed(value)}
            if isinstance(value,list):return [reorder(item) for item in value]
            return value
        second=build_comparison_prompt([reorder(target)],reorder(refs))
        self.assertEqual(first,second);self.assertEqual((refs,target),before)
        with self.assertRaises(ValueError):build_comparison_prompt([{**target,'accessory_only':True}],refs)


if __name__=='__main__':unittest.main()
