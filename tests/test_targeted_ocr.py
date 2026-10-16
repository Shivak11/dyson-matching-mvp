import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_targeted_ocr as target


class TargetedOCRTests(unittest.TestCase):
    def response(self,content=None):
        return {'usage':{'prompt_tokens':20},'choices':[{'finish_reason':'stop','message':{'content':'untrusted V99 model answer',
          'annotations':[{'type':'file','file':{'hash':'x','content':content if content is not None else []}}]}}]}

    def test_empty_ocr_annotation_is_valid_but_missing_annotation_is_not(self):
        value=self.response();parsed=target.parse_annotations(value,{'input_token_bound':6000})
        self.assertTrue(parsed['no_text_extracted']);self.assertEqual(parsed['literal_texts'],[])
        value['choices'][0]['message']['annotations']=[]
        with self.assertRaises(ValueError):target.parse_annotations(value,{'input_token_bound':6000})

    def test_only_literal_server_text_is_retained(self):
        parsed=target.parse_annotations(self.response([{'type':'text','text':'FILTRO'}]),{'input_token_bound':6000})
        self.assertEqual(parsed['literal_texts'],['FILTRO']);self.assertNotIn('V99',str(parsed))
        self.assertFalse(parsed['no_text_extracted'])

    def test_incomplete_or_over_bound_responses_are_rejected(self):
        for change in ['finish','bound']:
            value=self.response()
            if change=='finish':value['choices'][0]['finish_reason']='length'
            else:value['usage']['prompt_tokens']=6001
            with self.assertRaises(ValueError):target.parse_annotations(value,{'input_token_bound':6000})

    def test_text_candidates_are_unverified_and_do_not_accept_body_identity(self):
        value=target.text_candidates(['dyson HEPA FILTRO','V12 Detect Slim and 972213-02'])
        self.assertEqual(value['possible_part_codes'],['972213-02'])
        self.assertEqual(value['possible_model_strings'],['V12 Detect Slim'])
        self.assertFalse(value['manufacturer_verified']);self.assertFalse(value['body_identity_accepted'])
        self.assertEqual(target.text_candidates(['Dyson HEPA'])['possible_model_strings'],[])

    def test_neutral_request_contains_no_test_metadata_or_prior_guess(self):
        model={'provider':'openrouter','model':'qwen/qwen3.7-flash','provider_only':['alibaba'],
          'input_token_bound':6000,'max_output_tokens':128,'input_usd_per_million':.03,'output_usd_per_million':.13,'maximum_parser_fee_usd':.01}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source-with-private-title.jpg';Image.new('RGB',(30,20),'white').save(p)
            client=Mock(config={'models':{'ocr':model}})
            target.extract(client,'ocr14:P054',p)
            args=client._call.call_args.args;payload=args[3]
            self.assertEqual(payload['plugins'],[{'id':'file-parser','pdf':{'engine':'mistral-ocr'}}])
            self.assertEqual(payload['messages'][0]['content'][1]['file']['filename'],'region.pdf')
            self.assertNotIn('private-title',json.dumps(payload));self.assertNotIn('P054',json.dumps(payload))
            self.assertAlmostEqual(args[5],.02019664)

    def test_exact_ten_ledger_population_is_required(self):
        with self.assertRaisesRegex(ValueError,'Ten historical ledgers'):
            target.verify({'previous_ledgers':[{'file':'same'}]*10})


if __name__=='__main__':unittest.main()
