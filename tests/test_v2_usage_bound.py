import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import repair_v2_usage_bound as repair
import test_v2_recovery as recovery_fixtures
from run_pipeline import save, read, sha
from pipeline_api import digest, encoded


class UsageBoundRepairTests(unittest.TestCase):
    def fixture(self,root):
        previous=recovery_fixtures.RecoveryTests().fixture(root)
        config=repair.recovery.build_config(previous,root)
        config['catalogue_order']=['a','b']
        repair.recovery.snapshot_prior_stop(config,root)
        save(root/repair.recovery.CONFIG,config)
        obj={'object_id':'o1','role':'machine','parent_id':None,'box_2d':[0,0,1000,1000],
             'visibility':'whole_machine','observations':[],'readable_identifier':''}
        directory=root/repair.recovery.FULL/'photos/P058'
        save(directory/'observations.json',{'objects':[obj]})
        save(directory/'refinement_inputs.json',{'expanded_candidates':{'o1':['a','b']}})
        save(root/'data/reference_cards_v2.json',{'products':{'outside':{'in_catalog':False}}})
        raw={'results':[{'object_id':'o1','decision':{'status':'not_sure','product':None,'confidence':40,
             'top_two':['a'],'evidence':['Visible body.'],'missing_evidence':['Model text unreadable.'],
             'contradictions':[],'retake':'Show the model label.'},'candidate_checks':[
             {'product':name,'outcome':'insufficient_evidence','evidence':'No distinguishing detail.'} for name in ['a','b']],
             'decisive_region':[10,10,500,500]}]}
        usage={'prompt_tokens':37957,'completion_tokens':5744,
               'prompt_tokens_details':{'cached_tokens':0},'cost':.05000775,
               'cost_details':{'upstream_inference_prompt_cost':.02846775,
                               'upstream_inference_completions_cost':.02154,'upstream_inference_cost':.05000775}}
        response={'choices':[{'finish_reason':'stop','native_finish_reason':'STOP','message':{'content':json.dumps(raw)}}],'usage':usage}
        row={'job_id':repair.JOB+':attempt:1','logical_job_id':repair.JOB,'status':'error','http_status':200,
             'error':repair.ERROR,'cost_basis':'provider_reported_cost','estimated_cost_usd':.05000775,
             'reserved_cost_usd':.14388,'config_sha256':digest(encoded(config)),'request_sha256':'original-request',
             'requested_model':'google/gemini-3.7-flash','provider_response':response,'usage_metadata':copy.deepcopy(usage),'result':raw}
        self.write_record(root,row)
        return config,row

    def write_record(self,root,row):
        path=root/repair.recovery.NEW/'calls.jsonl'
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(row)+'\n')
        save(path.with_name('inflight.json'),{})

    def test_success_appends_zero_cost_without_rebilling_or_modifying_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,original=self.fixture(root)
            path=root/repair.recovery.NEW/'calls.jsonl';before=path.read_bytes()
            with patch('pipeline_api.urllib.request.urlopen') as network:
                receipt=repair.repair(apply=True,root=root)
                network.assert_not_called()
            records=repair.recovery.ledger(path)
            self.assertTrue(path.read_bytes().startswith(before));self.assertEqual(records[0],original)
            self.assertEqual(len(records),2);event=records[-1]
            self.assertEqual(event['status'],'ok');self.assertNotIn('error',event)
            self.assertEqual(event['cost_basis'],'offline_usage_bound_recovery')
            self.assertEqual(event['estimated_cost_usd'],0)
            self.assertEqual(event['provider_response'],original['provider_response'])
            self.assertEqual(event['result'],original['result'])
            self.assertAlmostEqual(repair.recovery.spent(records),.05000775)
            self.assertEqual(event['recovery']['original_record_sha256'],digest(encoded(original)))
            self.assertEqual(receipt['recovery_record_sha256'],digest(encoded(event)))
            self.assertEqual(receipt['paid_requests'],0)
            self.assertEqual(read(root/repair.RECEIPT,{})['request_sha256'],'original-request')
            with self.assertRaises(ValueError):repair.repair(apply=True,root=root)
            self.assertEqual(len(repair.recovery.ledger(path)),2)

    def test_dry_run_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);path=root/repair.recovery.NEW/'calls.jsonl';before=path.read_bytes()
            receipt=repair.repair(root=root)
            self.assertEqual(receipt['published_input_cost_usd'],.02846775)
            self.assertEqual(receipt['published_output_cost_usd'],.02154)
            self.assertEqual(path.read_bytes(),before);self.assertFalse((root/repair.RECEIPT).exists())

    def test_wrong_job_error_and_partial_output_are_rejected(self):
        for change in ['job','error','http','finish','native','body']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d);_,row=self.fixture(root)
                if change=='job':row['logical_job_id']='v2long:refine:P059'
                if change=='error':row['error']='Timeout'
                if change=='http':row['http_status']=429
                if change=='finish':row['provider_response']['choices'][0]['finish_reason']='length'
                if change=='native':row['provider_response']['choices'][0]['native_finish_reason']='MAX_TOKENS'
                if change=='body':row['provider_response']['choices'][0]['message']['content']='{"incomplete"'
                self.write_record(root,row)
                with self.assertRaises((ValueError,json.JSONDecodeError)):repair.repair(apply=True,root=root)
                self.assertEqual(len(repair.recovery.ledger(root/repair.recovery.NEW/'calls.jsonl')),1)

    def test_mismatched_saved_json_and_malformed_domain_are_rejected(self):
        for change in ['saved_json','domain']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d);_,row=self.fixture(root)
                if change=='saved_json':row['result']['results'][0]['decision']['confidence']=41
                else:
                    row['result']['results'][0]['candidate_checks'].pop()
                    row['provider_response']['choices'][0]['message']['content']=json.dumps(row['result'])
                self.write_record(root,row)
                with self.assertRaises(ValueError):repair.repair(apply=True,root=root)

    def test_cost_mismatch_and_over_reservation_are_rejected(self):
        for change in ['usage','recorded','reserve','over_reserve','details']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d);_,row=self.fixture(root);usage=row['provider_response']['usage']
                if change=='usage':usage['cost']+=.001
                if change=='recorded':row['estimated_cost_usd']+=.001
                if change=='reserve':row['reserved_cost_usd']+=.01
                if change=='details':usage['cost_details']['upstream_inference_prompt_cost']+=.001
                if change=='over_reserve':
                    usage.update(prompt_tokens=200000,completion_tokens=32768,cost=.27288)
                    usage['cost_details']={};row['estimated_cost_usd']=.27288
                row['usage_metadata']=copy.deepcopy(usage)
                self.write_record(root,row)
                with self.assertRaises(ValueError):repair.repair(apply=True,root=root)

    def test_changed_frozen_evidence_and_pending_request_are_rejected(self):
        for change in ['frozen','snapshot','pending']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d);config,_=self.fixture(root)
                if change=='frozen':(root/'tools/frozen.py').write_text('changed')
                if change=='snapshot':
                    name=next(iter(config['prior_phase_evidence']))
                    (root/repair.recovery.NEW/'prior_phase_snapshot'/name).write_text('changed')
                if change=='pending':save(root/repair.recovery.NEW/'inflight.json',{'pending':{}})
                with self.assertRaises(ValueError):repair.repair(apply=True,root=root)
                self.assertFalse((root/repair.RECEIPT).exists())

    def test_stage_budget_breach_is_rejected_without_repair(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,row=self.fixture(root);path=root/repair.recovery.NEW/'calls.jsonl'
            earlier={**row,'job_id':'v2long:observe:P058:attempt:1','logical_job_id':'v2long:observe:P058',
                     'status':'ok','estimated_cost_usd':50}
            path.write_text(json.dumps(earlier)+'\n'+json.dumps(row)+'\n')
            with self.assertRaises(ValueError):repair.repair(apply=True,root=root)
            self.assertEqual(len(repair.recovery.ledger(path)),2)


if __name__=='__main__':unittest.main()
