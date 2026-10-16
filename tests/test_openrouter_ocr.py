from pathlib import Path
import io
import json
import tempfile
import unittest
from unittest.mock import Mock,patch
from PIL import Image
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from openrouter_ocr import one_page_pdf,extract_annotations,read_crop,OCRClient


class OpenRouterOCRTests(unittest.TestCase):
    def image(self,root):
        path=Path(root)/'crop.jpg';Image.new('RGB',(23,41),'white').save(path);return path

    def test_pdf_embeds_the_exact_jpeg_bytes_as_one_page(self):
        with tempfile.TemporaryDirectory() as root:
            path=self.image(root);pdf=one_page_pdf(path)
            self.assertIn(path.read_bytes(),pdf)
            self.assertIn(b'/Count 1',pdf)
            self.assertIn(b'/MediaBox [0 0 23 41]',pdf)
            self.assertTrue(pdf.endswith(b'%%EOF\n'))

    def test_only_server_annotations_are_evidence(self):
        response={'usage':{'prompt_tokens':10},'choices':[{'finish_reason':'stop','message':{'content':'{"invented_model":"V99"}',
          'annotations':[{'type':'file','file':{'hash':'x','content':[{'type':'text','text':'HEPA FILTER'}]}}]}}]}
        result=extract_annotations(response,{'input_token_bound':100})
        self.assertEqual(result['literal_texts'],['HEPA FILTER'])
        self.assertNotIn('V99',str(result))
        del response['choices'][0]['message']['annotations']
        with self.assertRaisesRegex(ValueError,'independent file-parser'):extract_annotations(response,{'input_token_bound':100})

    def test_provider_charge_and_unreconciled_parser_fee_both_remain_accounted(self):
        client=OCRClient.__new__(OCRClient);client.config={'models':{'ocr':{'maximum_parser_fee_usd':.01}}}
        record={'operation':'ocr','status':'ok','cost_basis':'provider_reported_cost','estimated_cost_usd':.0021,'reserved_cost_usd':.02019664}
        with patch('pipeline_api.Client._append') as append:client._append(record)
        self.assertAlmostEqual(record['estimated_cost_usd'],.0121)
        self.assertAlmostEqual(record['downstream_accounted_cost_usd'],.0021)
        self.assertEqual(record['ocr_parser_fee_reserve_usd'],.01)
        self.assertEqual(record['status'],'ok')
        append.assert_called_once_with(record)

    def test_token_only_usage_keeps_parser_fee_in_ledger_and_resumed_spending(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);out=root/'out';path=self.image(root)
            config={'budget':{'usd_inr':100,'stage_max_inr':10,'total_max_inr':10,'prior_accounted_inr':0},
              'models':{'ocr':{'provider':'openrouter','model':'qwen/qwen3.7-flash','input_token_bound':6000,
                'max_output_tokens':128,'input_usd_per_million':.03,'output_usd_per_million':.13,
                'provider_only':['alibaba'],'maximum_parser_fee_usd':.01}}}
            response={'usage':{'prompt_tokens':10,'completion_tokens':4},'choices':[{'finish_reason':'stop',
              'message':{'content':'{"processed":true}','annotations':[{'type':'file','file':{'hash':'x',
                'content':[{'type':'text','text':'HEPA'}]}}]}}]}
            reply=io.BytesIO(json.dumps(response).encode());reply.status=200
            client=OCRClient(config,root,out)
            with patch('pipeline_api.api_key_for',return_value='fixture-only'), \
                 patch('urllib.request.urlopen',return_value=reply):read_crop(client,'ocr',path)
            saved=json.loads((out/'calls.jsonl').read_text())
            self.assertAlmostEqual(saved['estimated_cost_usd'],.01+.00000082)
            self.assertAlmostEqual(client.spent_usd,saved['estimated_cost_usd'])
            resumed=OCRClient(config,root,out)
            self.assertAlmostEqual(resumed.spent_usd,client.spent_usd)
            self.assertEqual(resumed.pending,{})

    def test_route_is_explicit_server_mistral_and_fee_is_reserved(self):
        with tempfile.TemporaryDirectory() as root:
            client=Mock(config={'models':{'ocr':{'provider':'openrouter','model':'qwen/qwen3.7-flash','input_token_bound':6000,
              'max_output_tokens':128,'input_usd_per_million':.03,'output_usd_per_million':.13,
              'provider_only':['alibaba'],'maximum_parser_fee_usd':.01}}})
            read_crop(client,'ocr',self.image(root))
            args=client._call.call_args.args
            self.assertEqual(args[3]['plugins'],[{'id':'file-parser','pdf':{'engine':'mistral-ocr'}}])
            self.assertAlmostEqual(args[5],.02019664)
            self.assertFalse(args[3]['provider']['allow_fallbacks'])


if __name__=='__main__':unittest.main()
