import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import repair_v2_alternatives as repair
from pipeline_api import Client, digest, encoded
from run_pipeline import save, read, sha


class AlternativeRepairTests(unittest.TestCase):
    candidates = {'o1':['dyson_v16_piston_animal','dyson_v8_absolute','dyson_big_ball']}
    targets = [{'object_id':'o1','box_2d':[0,0,1000,1000]}]
    negatives = {'dyson_gen5detect','dyson_v11','shark_stratos'}

    def raw(self):
        return {'results':[{'object_id':'o1','decision':{'status':'not_sure','product':None,'confidence':40,
                 'top_two':['dyson_v16_piston_animal','dyson_gen5detect'],'evidence':['Visible upper body.'],
                 'missing_evidence':['Handle outside the frame.'],'contradictions':['Other bin layout.'],
                 'retake':'Show the body and controls.'},'candidate_checks':[
                 {'product':name,'outcome':'insufficient_evidence','evidence':'Controls outside frame.'}
                 for name in self.candidates['o1']],'decisive_region':[10,10,500,500],
                 'refinement_reason':'Inspect controls.'}]}

    def normalise(self, raw):
        return repair.normalise_batch(raw,self.targets,self.candidates,self.negatives,90)

    def test_current_case_keeps_every_substantive_field_and_original(self):
        raw=self.raw();before=copy.deepcopy(raw);out=self.normalise(raw)
        self.assertEqual(raw,before)
        self.assertEqual(out['results'][0]['decision']['top_two'],['dyson_v16_piston_animal'])
        self.assertEqual(out['results'][0]['unverified_alternatives'],['dyson_gen5detect'])
        expected=copy.deepcopy(before);expected['results'][0]['decision']['top_two']=['dyson_v16_piston_animal']
        cleaned=copy.deepcopy(out)
        cleaned['results'][0].pop('format_repairs');cleaned['results'][0].pop('unverified_alternatives')
        self.assertEqual(cleaned,expected)
        self.assertEqual(out['results'][0]['decision']['status'],'not_sure')
        self.assertEqual(out['results'][0]['decision']['confidence'],40)

    def test_removed_guesses_are_never_replaced(self):
        raw=self.raw();raw['results'][0]['decision']['top_two']=['dyson_v11','dyson_gen5detect']
        self.assertEqual(self.normalise(raw)['results'][0]['decision']['top_two'],[])

    def test_resolved_answers_unknown_ids_and_unsupplied_catalogue_ids_rejected(self):
        for status,product in [('match','dyson_v16_piston_animal'),('not_in_catalogue',None),('not_sure','dyson_v16_piston_animal')]:
            raw=self.raw();raw['results'][0]['decision'].update(status=status,product=product)
            with self.subTest(status=status),self.assertRaises(ValueError):self.normalise(raw)
        for name in ['unknown_product','dyson_v12_detect_slim']:
            raw=self.raw();raw['results'][0]['decision']['top_two'][1]=name
            with self.subTest(name=name),self.assertRaises(ValueError):self.normalise(raw)

    def test_malformed_duplicates_and_excess_alternatives_rejected(self):
        for values in [None,'dyson_gen5detect',[None],[''],['a','dyson_gen5detect','dyson_v11'],
                       ['dyson_gen5detect','dyson_gen5detect'],[['dyson_gen5detect']]]:
            raw=self.raw();raw['results'][0]['decision']['top_two']=values
            with self.subTest(values=values),self.assertRaises(ValueError):self.normalise(raw)

    def test_other_validation_defects_cannot_be_hidden_by_repair(self):
        for key,value in [('confidence',-1),('evidence','bad'),('top_two',['dyson_v16_piston_animal'])]:
            raw=self.raw();raw['results'][0]['decision'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.normalise(raw)
        raw=self.raw();raw['results'][0]['candidate_checks'].pop()
        with self.assertRaises(ValueError):self.normalise(raw)
        raw=self.raw();raw['results'][0]['decisive_region']=[0,0,0,1]
        with self.assertRaises(ValueError):self.normalise(raw)
        raw=self.raw();raw['results']*=2
        with self.assertRaises(ValueError):self.normalise(raw)

    def fixture(self,root):
        config={'budget':{'stage_max_inr':100,'total_max_inr':2000,'prior_accounted_inr':500,'usd_inr':100},
                'rate_limit_policy':{'rate_limit_retries':3,'request_interval_seconds':15,'max_retry_delay_seconds':300},
                'catalogue_order':self.candidates['o1'],'confidence_threshold':90,'prior_phase_evidence':{},
                'phase_photo_ids':['P051','P052']}
        save(root/repair.recovery.CONFIG,config)
        raw=self.raw();job='v2long:identify:P051'
        original={'job_id':job+':attempt:1','logical_job_id':job,'status':'ok',
                  'config_sha256':digest(encoded(config)),'request_sha256':'unchanged-request',
                  'requested_model':'google/gemini-3.7-flash','result':raw,'estimated_cost_usd':.10566,
                  'cost_basis':'provider_reported_cost','provider_response':{'choices':[{'finish_reason':'stop',
                  'message':{'content':json.dumps(raw)}}]}}
        directory=root/repair.recovery.NEW;directory.mkdir(parents=True)
        (directory/'calls.jsonl').write_text(json.dumps(original)+'\n')
        client=Client(config,root,directory,**config['rate_limit_policy'])
        client.record_validation_failure(job,'Invalid top two')
        save(root/repair.POLICY,{'job_id':job,'job_prefix':'v2long:','allowed_stages':['identify','refine'],'allowed_error':'Invalid top two','allowed_status':'not_sure',
             'new_paid_requests':0,'known_non_catalogue_ids':sorted(self.negatives),'invent_guesses':False,
             'use_existing_offline_validation_recovery':True})
        return config,job,original

    def test_existing_offline_recovery_preserves_provider_original_and_never_calls_api(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config,job,original=self.fixture(root)
            calls=root/repair.recovery.NEW/'calls.jsonl';before=calls.read_bytes()
            context=(self.targets,self.candidates,self.negatives,{})
            with patch.object(repair.recovery,'verify_config') as verify,patch.object(repair,'load_context',return_value=context),patch('pipeline_api.urllib.request.urlopen') as network:
                receipt=repair.repair(job,apply=True,root=root)
                network.assert_not_called();verify.assert_called_once_with(config,root)
            self.assertTrue(calls.read_bytes().startswith(before))
            records=repair.recovery.ledger(calls)
            self.assertEqual(records[0],original)
            self.assertEqual(len(records),3)
            recovered=records[-1]
            self.assertEqual(recovered['cost_basis'],'offline_validation_recovery')
            self.assertEqual(recovered['estimated_cost_usd'],0)
            self.assertEqual(recovered['provider_response'],original['provider_response'])
            self.assertEqual(recovered['result']['results'][0]['decision']['top_two'],['dyson_v16_piston_animal'])
            self.assertEqual(receipt['original_record_sha256'],digest(encoded(original)))
            self.assertEqual(receipt['normalised_result_sha256'],digest(encoded(recovered['result'])))
            self.assertEqual(receipt['validation_failure_sha256'],recovered['recovery']['validation_failure_sha256'])
            self.assertEqual(receipt['policy_sha256'],sha(root/repair.POLICY))
            self.assertEqual(receipt['paid_requests'],0)
            self.assertEqual(read(root/repair.receipt_file(job),{})['removed_ids'],{'o1':['dyson_gen5detect']})
            after=calls.read_bytes()
            with patch.object(repair.recovery,'verify_config'),self.assertRaises(ValueError):repair.repair(job,apply=True,root=root)
            self.assertEqual(calls.read_bytes(),after)

    def test_other_latest_errors_and_inflight_requests_block(self):
        for variant in ['error','pending']:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as d:
                root=Path(d);_,job,_=self.fixture(root)
                if variant=='error':
                    path=root/repair.recovery.NEW/'calls.jsonl';rows=repair.recovery.ledger(path)
                    rows[-1]['error']='Invalid confidence';path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                else:save(root/repair.recovery.NEW/'inflight.json',{'pending':{}})
                with patch.object(repair.recovery,'verify_config'),self.assertRaises(ValueError):repair.repair(job,apply=True,root=root)
                self.assertFalse((root/repair.receipt_file(job)).exists())

    def test_context_selects_identify_and_refine_candidates_from_saved_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);directory=root/repair.recovery.FULL/'photos/P051'
            obj={'object_id':'o1','role':'partial_machine','parent_id':None,'box_2d':[0,0,1000,1000],
                 'visibility':'part_only','observations':[],'readable_identifier':''}
            save(directory/'observations.json',{'objects':[obj]})
            save(directory/'prepared.json',{'initial_candidates':self.candidates})
            save(directory/'refinement_inputs.json',{'expanded_candidates':self.candidates})
            save(root/'data/reference_cards_v2.json',{'products':{name:{'in_catalog':False} for name in self.negatives}})
            for stage in ['identify','refine']:
                targets,candidates,negatives,hashes=repair.load_context('v2long:'+stage+':P051',{'catalogue_order':self.candidates['o1'],'phase_photo_ids':['P051']},root)
                self.assertEqual(targets,[obj]);self.assertEqual(candidates,self.candidates);self.assertEqual(negatives,self.negatives)
                self.assertEqual(len(hashes),2)
            for job in ['v2long:identify:P052','v2long:observe:P051','v2standard:identify:P051']:
                with self.assertRaises(ValueError):repair.load_context(job,{'phase_photo_ids':['P051']},root)
            self.assertNotEqual(repair.receipt_file('v2long:identify:P051'),repair.receipt_file('v2long:refine:P051'))


if __name__=='__main__':unittest.main()
