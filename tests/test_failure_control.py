import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import finish_failure_control as control
import test_failure_protocol as fixtures
from pipeline_api import Client, digest, encoded


class FailureControlTests(unittest.TestCase):
    def fixture(self,root):
        root=Path(root);(root/'out/pipeline').mkdir(parents=True)
        sentinel=root/'frozen.txt';sentinel.write_text('Original evidence.\n')
        history=[]
        for index in range(7):
            path=root/f'out/old{index}/calls.jsonl';path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'estimated_cost_usd':.5})+'\n')
            history.append({'file':str(path.relative_to(root)),'sha256':control.runner.sha(path),'accounted_cost_usd':.5})
        model={'model':'google/gemini-3.7-flash','provider':'openrouter','provider_only':['google-ai-studio'],
               'input_usd_per_million':.75,'output_usd_per_million':3.75,'max_output_tokens':32768,
               'input_token_bound':50000,'thinking_level':'high','request_timeout_seconds':480}
        helper=fixtures.FailureProtocolTests();references=helper.refs();raw=helper.raw()
        inventory={'objects':[helper.target()]}
        failures=[f'P{index:03}' for index in range(101,121)];controls=['P006','P014','P019'];ids=failures+controls
        config={'study_id':'failure-v3','models':{'comparison':model,'inventory':{**model,'max_output_tokens':16384,'input_token_bound':20000}},
                'frozen_files':{'frozen.txt':control.runner.sha(sentinel)},'previous_ledgers':history,
                'stage_ceiling_inr':1000,'prior_stage_accounted_inr':42.68,
                'budget':{'usd_inr':100,'stage_max_inr':650,'prior_accounted_inr':392.68,'total_max_inr':2000},
                'rate_limit_policy':{'rate_limit_retries':3,'request_interval_seconds':15,'max_retry_delay_seconds':300},
                'scope':{'failure_ids':failures,'control_ids':controls,'photo_ids':ids,'preflight_id':'P022'},
                'confidence_threshold':90,'catalogue_order':[value['product'] for value in references.values() if value['in_catalog']],
                'reporting_usd_inr':95}
        control.runner.save(root/control.OLD_CONFIG,config)
        control.runner.save(root/control.OLD/'frozen_config.json',config)
        source=root/'query.jpg';Image.new('RGB',(180,260),'grey').save(source)
        panel=root/'panel.jpg';Image.new('RGB',(80,80),'silver').save(panel)
        panels={'references':references,'images':[{'panel_id':panel_id,'file':'panel.jpg'}
                 for value in references.values() for panel_id in value['panels']]}
        control.runner.save(root/control.OLD/'reference_panels.json',panels)
        photos=[{'image_id':name,'file':'query.jpg','evaluation_role':'labelled_single','labels':[config['catalogue_order'][0]]} for name in ids]
        control.runner.save(root/'data/test/test_manifest.json',photos)
        captures={}
        class Recorder:
            def generate(self,job,model,prompt,images):
                captures[job]=(prompt,images,control.capture(config,job,model,prompt,images))
                return inventory if model=='inventory' else raw
        control.runner.run_photo(Recorder(),config,photos[-1],panels,root)
        (root/control.OLD/'photos/P019/comparison.json').unlink()
        records=[]
        for job,cost,status in [(control.INVENTORY,.00650175,'ok'),(control.FAILED,.14911875,'error')]:
            result=inventory if status=='ok' else raw
            response={'choices':[{'finish_reason':'stop' if status=='ok' else 'length',
                                   'native_finish_reason':'STOP' if status=='ok' else 'MAX_TOKENS',
                                   'message':{'content':json.dumps(result) if status=='ok' else '{"incomplete":'}}]}
            record={'job_id':job+':attempt:1','logical_job_id':job,'status':status,'http_status':200,
                    'estimated_cost_usd':cost,'cost_basis':'provider_reported_cost','config_sha256':digest(encoded(config)),
                    'request_sha256':captures[job][2]['request_sha256'],'requested_model':model['model'],
                    'provider_response':response,'request_finished_unix':time.time()-100}
            if status=='ok':record['result']=inventory
            else:record['error']='Incomplete provider result: length'
            records.append(record)
        (root/control.OLD/'calls.jsonl').write_bytes(b''.join(encoded(row)+b'\n' for row in records))
        completed=ids[:-1]
        decision={'status':'match','product':config['catalogue_order'][0],'confidence':95,'top_two':[config['catalogue_order'][0]],
                  'evidence':['Visible body features.'],'missing_evidence':[],'contradictions':[],'retake':''}
        results=[{'image_id':name,'instance_id':name+'_o1','model':'flash37high_v3','variant':'aligned_reference',
                  'candidates':config['catalogue_order'],'decision':decision} for name in completed]
        detections={name:[{'instance_id':name+'_o1'}] for name in completed}
        for name,value in [('results.json',results),('detections.json',detections),('completed_photos.json',completed)]:
            control.runner.save(root/control.OLD/name,value)
        control.runner.save(root/'out/pipeline_v2_recovery/independent_audit.json',{'final':{'per_photo':[
            {'image_id':name,'status':'match' if name in controls else 'not_sure','correct':name in controls} for name in ids]}})
        score=control.runner.report(config,root)
        control.runner.save(root/control.OLD/'run_receipt.json',{'status':'stopped','inflight_count':0,'completed_count':22,
             'error':records[-1]['job_id']+': '+records[-1]['error'],'costs':score['costs']})
        instruction={'failed_logical_job_id':control.FAILED,'previous_max_output_tokens':32768,'new_max_output_tokens':65536,
             'previous_request_timeout_seconds':480,'new_request_timeout_seconds':900,'requested_model':model['model'],
             'provider_only':['google-ai-studio'],'thinking_level':'high','stage_ceiling_inr':1000,'overall_ceiling_inr':2000,
             'automatic_fallback':False,'reuse_exact_inventory':True,'previous_completed_count':22,'reservation_usd':.28326,
             'owner_instruction':'Finish the final control with the recorded larger cap.',
             'prior_stage_guard_inr':(3.5+control.spent(records))*100}
        control.runner.save(root/control.DECISION,instruction)
        for name in ['tools/finish_failure_control.py','tests/test_failure_control.py']:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Frozen source fixture.\n')
        return config,captures,raw

    def response(self,raw,finish='stop'):
        class Reply:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.data
        reply=Reply();reply.data=json.dumps({'choices':[{'finish_reason':finish,
            'native_finish_reason':'STOP' if finish=='stop' else 'MAX_TOKENS','message':{'content':json.dumps(raw)}}],
            'usage':{'prompt_tokens':100,'completion_tokens':100,'cost':.005}}).encode()
        return reply

    def test_budget_carries_eight_ledgers_and_only_two_model_settings_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);previous,_,_=self.fixture(root);config=control.build_config(previous,root)
            self.assertEqual(config['previous_ledgers'][:-1],previous['previous_ledgers'])
            self.assertEqual(len(control.verify_config(config,root)),9)
            guard=sum(row['accounted_cost_usd'] for row in config['previous_ledgers'])*100
            self.assertAlmostEqual(config['budget']['stage_max_inr'],1000-guard)
            self.assertAlmostEqual(config['budget']['prior_accounted_inr'],42.68+guard)
            expected=copy.deepcopy(previous['models']);expected['comparison'].update(max_output_tokens=65536,request_timeout_seconds=900)
            self.assertEqual(config['models'],expected);self.assertEqual(config['scope'],previous['scope'])
            for name,sha in previous['frozen_files'].items():self.assertEqual(config['frozen_files'][name],sha)
            self.assertNotIn(str(control.CONFIG),config['frozen_files'])
            self.assertFalse(any(name.startswith(str(control.NEW)+'/') for name in config['frozen_files']))

    def test_only_payload_cap_changes_and_old_request_is_reproduced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);previous,captures,_=self.fixture(root);config=control.build_config(previous,root)
            prompt,images,_=captures[control.FAILED];failed=control.runner.ledger(root/control.OLD/'calls.jsonl')[-1]
            proof=control.comparison_proof(previous,config,prompt,images,failed)
            self.assertEqual(proof['payload_changed_fields'],{'max_tokens':{'old':32768,'new':65536}})
            self.assertEqual(proof['old_request_sha256'],failed['request_sha256'])
            self.assertNotEqual(proof['old_request_sha256'],proof['new_request_sha256'])
            self.assertEqual(proof['new_timeout_seconds'],900);self.assertAlmostEqual(proof['reservation_usd'],.28326)
            wrong=copy.deepcopy(config);wrong['models']['comparison']['thinking_level']='low'
            with self.assertRaises(ValueError):control.comparison_proof(previous,wrong,prompt,images,failed)
            with self.assertRaises(ValueError):control.comparison_proof(previous,config,prompt+'changed',images,failed)

    def test_complete_retry_reuses_inventory_preserves_old_bytes_and_resumes_without_billing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);previous,_,raw=self.fixture(root);config=control.build_config(previous,root)
            before={str(path.relative_to(root)):path.read_bytes() for path in (root/control.OLD).rglob('*') if path.is_file()}
            with patch('pipeline_api.api_key_for',return_value='test-key'),patch('pipeline_api.urllib.request.urlopen',return_value=self.response(raw)) as network:
                receipt=control.execute(config,root)
                self.assertEqual(receipt['completed_count'],23);self.assertEqual(receipt['status'],'completed')
                request=network.call_args.args[0];self.assertEqual(json.loads(request.data)['max_tokens'],65536)
                self.assertEqual(network.call_args.kwargs['timeout'],900);self.assertEqual(network.call_count,1)
                for name in control.OUTPUTS:shutil.copy2(root/control.NEW/'prior_outputs'/name,root/control.NEW/name)
                resumed=control.execute(config,root)
                self.assertEqual(resumed['completed_count'],23);self.assertEqual(network.call_count,1)
            self.assertEqual(len(control.runner.ledger(root/control.NEW/'calls.jsonl')),1)
            row=control.runner.ledger(root/control.NEW/'calls.jsonl')[0]
            self.assertEqual(row['logical_job_id'],control.RETRY);self.assertEqual(row['estimated_cost_usd'],.005)
            self.assertEqual(control.runner.OUT,control.OLD)
            self.assertEqual(before,{name:(root/name).read_bytes() for name in before})
            reuse=control.runner.read(root/control.NEW/'inventory_reuse_proof.json',{})
            self.assertEqual(reuse['paid_requests'],0);self.assertEqual(reuse['job_id'],control.INVENTORY)
            self.assertAlmostEqual(receipt['costs']['whole_v3_and_retry_accounted_usd'],.00650175+.14911875+.005)
            for name in control.OUTPUTS:self.assertEqual((root/control.NEW/'prior_outputs'/name).read_bytes(),(root/control.OLD/name).read_bytes())

    def test_incomplete_retry_stops_and_cannot_be_reset_for_a_second_paid_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);previous,_,raw=self.fixture(root);config=control.build_config(previous,root)
            with patch('pipeline_api.api_key_for',return_value='test-key'),patch('pipeline_api.urllib.request.urlopen',return_value=self.response(raw,'length')) as network:
                receipt=control.execute(config,root);self.assertEqual(receipt['status'],'stopped')
                self.assertEqual(receipt['completed_count'],22);self.assertIn('length',receipt['error'])
                resumed=control.execute(config,root);self.assertEqual(resumed['status'],'stopped')
                self.assertEqual(network.call_count,1)
            self.assertEqual(len(control.runner.ledger(root/control.NEW/'calls.jsonl')),1)

    def test_exact_inventory_and_scope_are_enforced_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);previous,captures,_=self.fixture(root);config=control.build_config(previous,root)
            client=control.CompletionClient(config,root,root/control.NEW,**config['rate_limit_policy'])
            prompt,images,_=captures[control.INVENTORY]
            with patch('pipeline_api.urllib.request.urlopen') as network:
                self.assertIn('objects',client.generate(control.INVENTORY,'inventory',prompt,images))
                for job,model,changed_prompt in [('v3:inventory:P006','inventory',prompt),(control.FAILED,'inventory',prompt),
                                                  (control.INVENTORY,'inventory',prompt+'changed')]:
                    with self.assertRaises(ValueError):client.generate(job,model,changed_prompt,images)
                network.assert_not_called()
            rows=control.runner.ledger(root/control.OLD/'calls.jsonl');rows[0]['provider_response']['choices'][0]['finish_reason']='length'
            (root/control.OLD/'calls.jsonl').write_bytes(b''.join(encoded(row)+b'\n' for row in rows))
            client.old_records=rows
            with self.assertRaises(ValueError):client.generate(control.INVENTORY,'inventory',prompt,images)

    def test_changed_or_incomplete_history_and_scope_are_rejected(self):
        for variant in ['pending','missing','other_error','wrong_stop','receipt','completed','controls','frozen','decision','duplicate']:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);previous,_,_=self.fixture(root)
                if variant=='pending':control.runner.save(root/control.OLD/'inflight.json',{'pending':{}})
                if variant=='missing':(root/control.OLD/'calls.jsonl').unlink()
                if variant in ['other_error','wrong_stop']:
                    rows=control.runner.ledger(root/control.OLD/'calls.jsonl')
                    if variant=='other_error':rows.insert(0,{**rows[0],'logical_job_id':'v3:inventory:P006','status':'error'})
                    if variant=='wrong_stop':rows[-1]['provider_response']['choices'][0]['finish_reason']='stop'
                    (root/control.OLD/'calls.jsonl').write_bytes(b''.join(encoded(row)+b'\n' for row in rows))
                if variant=='receipt':control.runner.save(root/control.OLD/'run_receipt.json',{})
                if variant=='completed':control.runner.save(root/control.OLD/'completed_photos.json',[])
                if variant=='controls':control.runner.save(root/control.OLD/'scoreboard.json',{})
                if variant=='frozen':(root/'frozen.txt').write_text('Changed.')
                if variant=='decision':control.runner.save(root/control.DECISION,{})
                if variant=='duplicate':previous['previous_ledgers'][-1]=copy.deepcopy(previous['previous_ledgers'][0])
                with self.assertRaises((ValueError,FileNotFoundError)):control.build_config(previous,root)

    def test_mutated_completion_or_old_snapshot_and_stop_file_block_calls(self):
        for variant in ['config','old_output','new_prefix','stop','pending']:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);previous,_,_=self.fixture(root);config=control.build_config(previous,root)
                if variant=='config':config['models']['comparison']['max_output_tokens']=131072
                if variant=='old_output':(root/control.OLD/'photos/P019/inventory.json').write_text('{}')
                if variant=='new_prefix':
                    control.preserve_outputs(root);control.runner.save(root/control.NEW/'results.json',[])
                if variant=='stop':control.runner.save(root/control.NEW/'STOP',{})
                if variant=='pending':control.runner.save(root/control.NEW/'inflight.json',{'pending':{}})
                with patch('pipeline_api.urllib.request.urlopen') as network:
                    with self.assertRaises((ValueError,RuntimeError)):control.execute(config,root)
                    network.assert_not_called()


if __name__=='__main__':unittest.main()
