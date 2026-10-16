import copy
import fcntl
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_pipeline_v2_recovery as recovery
from run_pipeline import save, read, sha


class RecoveryTests(unittest.TestCase):
    def fixture(self, root):
        model = {'model':'google/gemini-3.7-flash','provider':'openrouter','input_usd_per_million':.75,
                 'output_usd_per_million':3.75,'max_output_tokens':16384,'input_token_bound':28000,
                 'thinking_level':'high','provider_only':['google-vertex/global/flex'],'request_timeout_seconds':480}
        sources = []
        paths = ['out/pipeline/calls.jsonl','out/pipeline/high_reasoning/calls.jsonl',
                 'out/pipeline/slow_comparison/calls.jsonl','out/pipeline_v2/calls.jsonl',
                 'out/pipeline_v2_full/calls.jsonl']
        for name,cost in zip(paths,[.942440986,1.06160775,.547499125,.01996275,.67253175]):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'job_id':name,'status':'ok','estimated_cost_usd':cost})+'\n')
            save(path.with_name('inflight.json'),{})
            sources.append({'file':name,'sha256':sha(path),'accounted_cost_usd':cost})
        full={'models':{'flash37high':model},'rate_limit_policy':{'rate_limit_retries':3,
              'request_interval_seconds':15,'max_retry_delay_seconds':300},'confidence_threshold':90}
        save(root/'data/pipeline_v2_full_config.json',full)
        sentinel=root/'tools/frozen.py';sentinel.parent.mkdir(parents=True,exist_ok=True);sentinel.write_text('original')
        previous={'study_id':'standard','stage_ceiling_inr':600,'prior_stage_accounted_inr':42.68,
                  'models':{'flash37high':{**model,'provider_only':['google-ai-studio']}},
                  'budget':{'stage_max_inr':600-sum(s['accounted_cost_usd'] for s in sources)*100,
                            'prior_accounted_inr':42.68+sum(s['accounted_cost_usd'] for s in sources)*100,
                            'total_max_inr':2000,'usd_inr':100},'reporting_usd_inr':95.15703439035285,
                  'previous_ledgers':sources,'confidence_threshold':90,
                  'rate_limit_policy':full['rate_limit_policy'],'phase_route':{'new_route':['google-ai-studio'],
                  'logical_job_prefix':'v2standard:'},'frozen_files':{'tools/frozen.py':sha(sentinel),
                  'data/pipeline_v2_full_config.json':sha(root/'data/pipeline_v2_full_config.json')}}
        save(root/recovery.PREVIOUS_CONFIG,previous)
        records=[{'job_id':'v2standard:observe:P051:attempt:1','logical_job_id':'v2standard:observe:P051',
                  'status':'ok','estimated_cost_usd':1.5863295},
                 {'job_id':'v2standard:identify:P051:attempt:1','logical_job_id':recovery.FAILED,
                  'status':'error','http_status':200,'error':'Incomplete provider result: length',
                  'estimated_cost_usd':.06693675,'provider_response':{'choices':[{'finish_reason':'length',
                  'native_finish_reason':'MAX_TOKENS'}]}}]
        path=root/recovery.PREVIOUS/'calls.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(json.dumps(row)+'\n' for row in records))
        save(path.with_name('inflight.json'),{})
        receipt={'status':'stopped','inflight_count':0,'completed_count':49,
                 'continuation_accounted_usd':1.65326625,
                 'error':'v2standard:identify:P051:attempt:1: Incomplete provider result: length'}
        save(root/recovery.PREVIOUS/'run_receipt.json',receipt)
        save(root/recovery.PREVIOUS/'blocker.json',{'old':'failure'})
        save(root/recovery.PREVIOUS/'scoreboard.json',{'old':'standard scoreboard'})
        save(root/recovery.PREVIOUS/'frozen_config.json',previous)
        for name,value in [('run_receipt.json',receipt),('blocker.json',{'old':'full failure'}),
                           ('scoreboard.json',{'old':'full scoreboard'}),('summary.json',{'old':'summary'}),
                           ('detections.json',{}),('completed_photos.json',[f'P{i:03}' for i in range(1,51) if i!=44]),
                           ('results.json',[{'image_id':f'P{i:03}','old':'untouched'} for i in range(1,51) if i!=44])]:
            save(root/recovery.FULL/name,value)
        (root/recovery.FULL/'STOP').write_text('Keep old phase stopped')
        save(root/recovery.FULL/'photos/P051/observations.json',{'old':'partial'})
        save(root/'data/test/test_manifest.json',[{'image_id':f'P{i:03}'} for i in range(1,60) if i!=44])
        decision={'owner_instruction':'continue the calls lets finish the 58','failed_logical_job_id':recovery.FAILED,
                  'previous_max_output_tokens':16384,'new_max_output_tokens':32768,'stage_ceiling_inr':600,
                  'requested_model':model['model'],'provider_only':['google-ai-studio'],
                  'thinking_level':'high','automatic_fallback':False}
        save(root/recovery.DECISION,decision)
        shutil.copy2(recovery.__file__,root/'tools/run_pipeline_v2_recovery.py')
        return previous

    def test_six_ledgers_and_remaining_budget_preserve_every_prior_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=self.fixture(root);before=copy.deepcopy(previous)
            config=recovery.build_config(previous,root)
            self.assertEqual(previous,before)
            self.assertEqual(len(config['previous_ledgers']),6)
            self.assertEqual(config['previous_ledgers'][:-1],previous['previous_ledgers'])
            self.assertAlmostEqual(config['budget']['stage_max_inr'],110.2691389)
            self.assertAlmostEqual(config['budget']['prior_accounted_inr'],532.4108611)
            self.assertEqual(config['models']['flash37high']['max_output_tokens'],32768)
            self.assertEqual(config['models']['flash37high']['provider_only'],['google-ai-studio'])
            self.assertEqual(config['phase_photo_ids'],[f'P{i:03}' for i in range(51,60)])
            for name,digest in previous['frozen_files'].items():self.assertEqual(config['frozen_files'][name],digest)
            self.assertIn('tools/run_pipeline_v2_recovery.py',config['frozen_files'])
            recovery.verify_config(config,root)

    def test_only_settled_specific_max_tokens_failure_is_admitted(self):
        for change in ['wrong_job','wrong_finish','wrong_native','wrong_http','pending','completed','other_failure']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d);previous=self.fixture(root)
                records=recovery.ledger(root/recovery.PREVIOUS/'calls.jsonl')
                last=records[-1]
                if change=='wrong_job':last['logical_job_id']='v2standard:identify:P052'
                if change=='wrong_finish':last['provider_response']['choices'][0]['finish_reason']='stop'
                if change=='wrong_native':last['provider_response']['choices'][0]['native_finish_reason']='STOP'
                if change=='wrong_http':last['http_status']=429
                if change=='other_failure':last['error']='Timeout'
                if change=='pending':save(root/recovery.PREVIOUS/'inflight.json',{'x':{}})
                if change=='completed':
                    receipt=read(root/recovery.PREVIOUS/'run_receipt.json',{});receipt['status']='completed'
                    save(root/recovery.PREVIOUS/'run_receipt.json',receipt)
                (root/recovery.PREVIOUS/'calls.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records))
                with self.assertRaises(ValueError):recovery.build_config(previous,root)

    def test_changed_decision_model_and_caps_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=self.fixture(root);config=recovery.build_config(previous,root)
            for key,value in [('stage_ceiling_inr',601),('previous_ledgers',config['previous_ledgers'][:-1])]:
                bad=copy.deepcopy(config);bad[key]=value
                with self.assertRaises(ValueError):recovery.verify_config(bad,root)
            bad=copy.deepcopy(config);bad['models']['flash37high']['max_output_tokens']=65536
            with self.assertRaises(ValueError):recovery.verify_config(bad,root)
            decision=read(root/recovery.DECISION,{});decision['new_max_output_tokens']=65536
            save(root/recovery.DECISION,decision)
            with self.assertRaises(ValueError):recovery.build_config(previous,root)

    def test_source_changes_and_recomputed_old_hash_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=self.fixture(root);config=recovery.build_config(previous,root)
            file=root/'tools/frozen.py';file.write_text('changed')
            with self.assertRaises(ValueError):recovery.verify_config(config,root)
            bad=copy.deepcopy(config);bad['frozen_files']['tools/frozen.py']=sha(file)
            with self.assertRaises(ValueError):recovery.verify_config(bad,root)
            file.write_text('original')
            new=root/'tools/run_pipeline_v2_recovery.py';new.write_text('changed recovery')
            with self.assertRaises(ValueError):recovery.verify_config(config,root)

    def test_prior_partial_and_progress_snapshots_are_immutable(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=self.fixture(root);config=recovery.build_config(previous,root)
            recovery.snapshot_prior_stop(config,root)
            snapshot=root/recovery.NEW/'prior_phase_snapshot'
            for name,digest in config['prior_phase_evidence'].items():self.assertEqual(sha(snapshot/name),digest)
            partial=snapshot/recovery.FULL/'photos/P051/observations.json'
            self.assertEqual(read(partial,{}),{'old':'partial'})
            save(root/recovery.FULL/'photos/P051/observations.json',{'new':'current'})
            recovery.snapshot_prior_stop(config,root)
            self.assertEqual(read(partial,{}),{'old':'partial'})
            save(partial,{'corrupt':True})
            with self.assertRaises(ValueError):recovery.snapshot_prior_stop(config,root)

    def test_long_namespace_validation_mapping_and_enlarged_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=self.fixture(root);config=recovery.build_config(previous,root)
            client=recovery.RecoveryClient(config,root,root/recovery.NEW,**config['rate_limit_policy'])
            reply={'choices':[{'finish_reason':'stop','message':{'content':'{"wrong":true}'}}],
                   'usage':{'prompt_tokens':10,'completion_tokens':20,'cost':.001}}
            with patch('pipeline_api.api_key_for',return_value='test'),patch('pipeline_api.urllib.request.urlopen',return_value=io.StringIO(json.dumps(reply))) as network:
                raw=client.generate('v2full:observe:P051','flash37high','same prompt',[])
                self.assertEqual(raw,{'wrong':True})
                payload=json.loads(network.call_args.args[0].data)
                self.assertEqual(payload['max_tokens'],32768)
                self.assertEqual(payload['provider']['only'],['google-ai-studio'])
            client.record_validation_failure('v2full:observe:P051','Missing objects')
            records=recovery.ledger(root/recovery.NEW/'calls.jsonl')
            self.assertAlmostEqual(records[0]['reserved_cost_usd'],.14388)
            self.assertEqual(records[0]['logical_job_id'],'v2long:observe:P051')
            self.assertEqual(records[1]['status'],'validation_error')
            self.assertEqual(records[1]['logical_job_id'],'v2long:observe:P051')
            self.assertEqual(records[1]['estimated_cost_usd'],0)
            self.assertFalse(client.reuse_records)
            for name in ['v2standard:observe:P051',None]:
                with self.assertRaises(ValueError):client.generate(name,'flash37high','prompt',[])
                with self.assertRaises(ValueError):client.record_validation_failure(name,'error')

    def test_costs_include_three_revision_phases_and_all_six_history_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=self.fixture(root);config=recovery.build_config(previous,root)
            path=root/recovery.NEW/'calls.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'job_id':'settled','estimated_cost_usd':.05})+'\n')
            save(root/recovery.NEW/'inflight.json',{'settled':{'reserved_cost_usd':999},'pending':{'reserved_cost_usd':.02}})
            costs=recovery.recovery_costs(config,root)
            self.assertAlmostEqual(costs['new_accounted_usd'],.67253175+1.65326625+.07)
            self.assertAlmostEqual(costs['combined_stage_guard_inr'],496.7308611)
            self.assertAlmostEqual(costs['remaining_guard_inr'],103.2691389)
            self.assertAlmostEqual(costs['technical_preflight_usd'],.01996275)
            self.assertEqual(costs['stage_ceiling_inr'],600)

    def test_preflight_then_resume_skips_all49_and_records9_requested(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            save(root/'data/reference_cards_v2.json',{'products':{}})
            old_results=read(root/recovery.FULL/'results.json',[])
            old_ledger=(root/recovery.PREVIOUS/'calls.jsonl').read_bytes()
            old_config=(root/recovery.PREVIOUS_CONFIG).read_bytes()
            with patch.object(recovery,'ROOT',root),patch.object(recovery.v2,'run_photo',return_value=({'machines':[]},[],[])) as run,patch.object(recovery,'score',return_value={'costs':{}}),patch('builtins.print'):
                with patch.object(sys,'argv',['recovery','--run','--limit','1']):recovery.main()
                self.assertEqual(run.call_count,1)
                self.assertEqual(run.call_args.args[2]['image_id'],'P051')
                with patch.object(sys,'argv',['recovery','--run']):recovery.main()
                self.assertEqual(run.call_count,9)
            final=read(root/recovery.FULL/'results.json',[])
            for result in old_results:self.assertIn(result,final)
            receipt=read(root/recovery.NEW/'run_receipt.json',{})
            self.assertEqual(receipt['completed_count'],58)
            self.assertEqual(receipt['requested_count'],9)
            self.assertEqual(receipt['selected_count'],8)
            self.assertEqual(receipt['status'],'completed')
            self.assertEqual((root/recovery.PREVIOUS/'calls.jsonl').read_bytes(),old_ledger)
            self.assertEqual((root/recovery.PREVIOUS_CONFIG).read_bytes(),old_config)
            self.assertTrue((root/recovery.FULL/'STOP').exists())

    def test_shared_lock_blocks_activation_before_any_new_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            with (root/'out/pipeline/run.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(recovery,'ROOT',root),patch.object(sys,'argv',['recovery','--run']),patch.object(recovery,'RecoveryClient') as client:
                    with self.assertRaises(BlockingIOError):recovery.main()
                    client.assert_not_called()
            self.assertFalse((root/recovery.CONFIG).exists())


if __name__=='__main__':unittest.main()
