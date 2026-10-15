import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_pipeline import pixel_box,cosine,rank_products,validate_result,gate_decision,CHECK_PROMPT,include_expected

class PipelineTests(unittest.TestCase):
    def test_padding_and_clamping(self):
        self.assertEqual(pixel_box([100,200,900,800],100,200,.1),(14,4,86,196))
        self.assertEqual(pixel_box([0,0,1000,1000],100,200,.1),(0,0,100,200))
        for box in ([0,10,0,20],[-1,0,100,100],[0,0,math.nan,1],[False,0,1,1]):
            with self.assertRaises(ValueError): pixel_box(box,100,100,.1)
    def test_product_max_retrieval(self):
        refs={'a':[{'id':'a1'},{'id':'a2'}],'b':[{'id':'b1'}]}
        v={'a1':[0,1],'a2':[1,0],'b1':[.6,.8]}
        self.assertEqual(rank_products([1,0],refs,v,1)[0]['product'],'a')
        self.assertAlmostEqual(cosine([1,2],[2,4]),1)
        with self.assertRaises(ValueError):cosine([0,0],[1,1])
    def result(self):
        return {'decision':{'status':'match','product':'a','confidence':89,'top_two':['a','b'],'evidence':['visible bin arrangement'],'missing_evidence':[],'contradictions':[],'retake':''},'candidate_checks':[{'product':'a','outcome':'confirmed','evidence':'bin'},{'product':'b','outcome':'contradicted','evidence':'body'}]}
    def test_validation_and_fixed_gate(self):
        raw=self.result();validate_result(raw,['a','b']);out=gate_decision(raw,90)
        self.assertEqual(out['decision']['status'],'not_sure'); self.assertEqual(raw['decision']['status'],'match')
        raw['decision']['confidence']=90
        self.assertEqual(gate_decision(raw,90)['decision']['status'],'match')
    def test_reject_invalid_candidate_and_nan(self):
        for field,value in [('product','z'),('confidence',math.nan),('confidence',True),('top_two',['a','a'])]:
            x=self.result();x['decision'][field]=value
            with self.assertRaises(ValueError): validate_result(x,['a','b'])
        x=self.result();x['candidate_checks'][0]['outcome']='insufficient_evidence'
        with self.assertRaises(ValueError):validate_result(x,['a','b'])
    def test_null_alternatives_for_outside_preserve_answer(self):
        raw=self.result();raw['decision'].update(status='not_in_catalogue',product=None,top_two=None)
        out=validate_result(raw,['a','b'])
        self.assertEqual(out['decision']['top_two'],[])
        self.assertIsNone(raw['decision']['top_two'])
        raw['decision']['top_two']=[None,None]
        self.assertEqual(validate_result(raw,['a','b'])['decision']['top_two'],[])
    def test_missing_optional_explanation_fields_preserve_decision(self):
        raw=self.result();del raw['decision']['contradictions'];del raw['decision']['retake']
        out=validate_result(raw,['a','b'])
        self.assertEqual(out['decision']['product'],'a')
        self.assertEqual(out['decision']['contradictions'],[])
        self.assertEqual(out['decision']['retake'],'')
        self.assertEqual(len(out['format_repairs']),2)
    def test_candidate_not_sure_alias_and_outside_uncertainty(self):
        raw=self.result();raw['decision'].update(status='not_in_catalogue',product=None,confidence=100)
        raw['candidate_checks'][0]['outcome']='not_sure'
        parsed=validate_result(raw,['a','b'])
        self.assertEqual(parsed['candidate_checks'][0]['outcome'],'insufficient_evidence')
        self.assertEqual(raw['candidate_checks'][0]['outcome'],'not_sure')
        self.assertEqual(gate_decision(parsed,90)['decision']['status'],'not_sure')
    def test_conflicting_confirmations_cannot_be_accepted(self):
        raw=self.result();raw['decision']['confidence']=99
        raw['candidate_checks'][1]['outcome']='confirmed'
        self.assertEqual(gate_decision(raw,90)['decision']['status'],'not_sure')
        raw['decision'].update(status='not_in_catalogue',product=None)
        self.assertEqual(gate_decision(raw,90)['decision']['status'],'not_sure')
    def test_expected_product_is_supplied_without_changing_retrieval(self):
        refs={'a':[{'id':'a1'}],'b':[{'id':'b1'}]};vectors={'a1':[1,0],'b1':[0,1]}
        retrieved=rank_products([1,0],refs,vectors,1)
        supplied=include_expected(retrieved,'b',[1,0],refs,vectors)
        self.assertEqual([x['product'] for x in supplied],['a','b'])
        self.assertEqual([x['product'] for x in retrieved],['a'])
        self.assertEqual(include_expected(retrieved,None,None,refs,{}),retrieved)
    def test_prompt_keeps_uncertainty_and_no_label_input(self):
        self.assertIn('Failure to match the shortlist is not enough',CHECK_PROMPT)
        self.assertNotIn('source_label',CHECK_PROMPT)

if __name__=='__main__':unittest.main()
