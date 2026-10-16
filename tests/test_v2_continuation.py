import copy
import fcntl
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import run_pipeline_v2_continuation as continuation
from pipeline_api import Client
from run_pipeline import save, read, sha


class ContinuationTests(unittest.TestCase):
    def fixture(self, root):
        model = {'model':'google/gemini-3.7-flash','provider':'openrouter',
                 'input_usd_per_million':.75,'output_usd_per_million':3.75,
                 'max_output_tokens':16384,'input_token_bound':28000,'thinking_level':'high',
                 'provider_only':['google-vertex/global/flex'],'request_timeout_seconds':480}
        prior = []
        for file, cost in [('out/pipeline/calls.jsonl',.5),
                           ('out/pipeline/high_reasoning/calls.jsonl',.6),
                           ('out/pipeline/slow_comparison/calls.jsonl',.7),
                           ('out/pipeline_v2/calls.jsonl',.02)]:
            p=root/file;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps({'job_id':file,'status':'ok','estimated_cost_usd':cost})+'\n')
            save(p.with_name('inflight.json'),{})
            prior.append({'file':file,'sha256':sha(p),'accounted_cost_usd':cost})
        guard=sum(row['accounted_cost_usd'] for row in prior)*100
        config={'study_id':'full','stage_ceiling_inr':400,'prior_stage_accounted_inr':42.68,
                'budget':{'stage_max_inr':400-guard,'total_max_inr':2000,
                          'prior_accounted_inr':42.68+guard,'usd_inr':100},
                'reporting_usd_inr':95,'models':{'flash37high':model},
                'previous_ledgers':prior,'frozen_files':{},'confidence_threshold':90,
                'rate_limit_policy':{'rate_limit_retries':3,'request_interval_seconds':15,'max_retry_delay_seconds':300}}
        save(root/continuation.FULL_CONFIG,config)
        amendment={'stage_ceiling_before_inr':400,'additional_authorized_inr':200,
                   'stage_ceiling_after_inr':600,'overall_ceiling_inr':2000,
                   'model_and_request_settings_unchanged':True,'owner_instruction':'increase the spending i authorize by 200 bucks more'}
        save(root/continuation.AMENDMENT,amendment)
        save(root/continuation.ROUTE,{'new_route':['google-ai-studio'],
             'previous_route':['google-vertex/global/flex'],'requested_model':model['model'],
             'automatic_fallback':False,'advertised_dated_model':'google/gemini-3.7-flash-20260813',
             'input_usd_per_million':.75,'output_usd_per_million':3.75})
        client=Client(config,root,root/continuation.FULL,**config['rate_limit_policy'])
        reply={'choices':[{'finish_reason':'stop','message':{'content':'{"observed":true}'}}],
               'usage':{'prompt_tokens':10,'completion_tokens':20,'cost':.001},'model':model['model']}
        with patch('pipeline_api.api_key_for',return_value='test'), patch('pipeline_api.urllib.request.urlopen',return_value=io.StringIO(json.dumps(reply))):
            client.generate('v2full:observe:P002','flash37high','unchanged prompt',[])
        save(root/continuation.FULL/'run_receipt.json',{'status':'stopped',
             'error':'Pipeline budget stop before request: v2full:identify:P002:attempt:1',
             'inflight_count':0,'new_accounted_usd':.001})
        save(root/continuation.FULL/'blocker.json',{'error':'budget stop'})
        save(root/continuation.FULL/'scoreboard.json',{'old':'scoreboard'})
        save(root/continuation.FULL/'summary.json',{'old':'summary'})
        save(root/continuation.FULL/'completed_photos.json',['P001'])
        (root/'out/pipeline/run.lock').touch()
        return config

    def test_new_cap_carries_all_spending_without_changing_requests(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);full=self.fixture(root);before=copy.deepcopy(full)
            config=continuation.build_config(full,root)
            self.assertEqual(full,before)
            expected_models=copy.deepcopy(full['models'])
            expected_models['flash37high']['provider_only']=['google-ai-studio']
            self.assertEqual(config['models'],expected_models)
            self.assertEqual(config['rate_limit_policy'],full['rate_limit_policy'])
            self.assertEqual(config['confidence_threshold'],90)
            self.assertEqual(config['stage_ceiling_inr'],600)
            self.assertAlmostEqual(config['budget']['stage_max_inr'],417.9)
            self.assertAlmostEqual(config['budget']['prior_accounted_inr'],224.78)
            self.assertEqual(len(config['previous_ledgers']),5)
            self.assertEqual(config['budget']['total_max_inr'],2000)
            self.assertEqual(continuation.verify_config(config,root)[-1]['result'],{'observed':True})

    def test_changed_route_uses_fresh_ids_then_own_cache_without_rebilling(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);full=self.fixture(root);config=continuation.build_config(full,root)
            before=(root/continuation.FULL/'calls.jsonl').read_bytes()
            client=continuation.StandardClient(config,root,root/continuation.NEW,**config['rate_limit_policy'])
            reply={'choices':[{'finish_reason':'stop','message':{'content':'{"new_route":true}'}}],
                   'usage':{'prompt_tokens':10,'completion_tokens':20,'cost':.001}}
            with patch('pipeline_api.api_key_for',return_value='test'), patch('pipeline_api.urllib.request.urlopen',return_value=io.StringIO(json.dumps(reply))) as network:
                self.assertEqual(client.generate('v2full:observe:P002','flash37high','unchanged prompt',[]),{'new_route':True})
                self.assertEqual(network.call_count,1)
                payload=json.loads(network.call_args.args[0].data)
                self.assertEqual(payload['provider']['only'],['google-ai-studio'])
            self.assertEqual(client.accounted_cost_usd,.001)
            self.assertEqual(client.reused_jobs,set())
            calls=continuation.ledger(root/continuation.NEW/'calls.jsonl')
            self.assertEqual(calls[0]['logical_job_id'],'v2standard:observe:P002')
            old=continuation.ledger(root/continuation.FULL/'calls.jsonl')[0]
            self.assertNotEqual(calls[0]['request_sha256'],old['request_sha256'])
            resumed=continuation.StandardClient(config,root,root/continuation.NEW,**config['rate_limit_policy'])
            with patch('pipeline_api.urllib.request.urlopen') as network:
                self.assertEqual(resumed.generate('v2full:observe:P002','flash37high','unchanged prompt',[]),{'new_route':True})
                network.assert_not_called()
            self.assertEqual(resumed.accounted_cost_usd,.001)
            self.assertEqual(len(continuation.ledger(root/continuation.NEW/'calls.jsonl')),1)
            self.assertEqual((root/continuation.FULL/'calls.jsonl').read_bytes(),before)
            with self.assertRaises(ValueError):resumed.generate('v2full:observe:P002','flash37high','changed prompt',[])

    def test_frozen_ledger_change_and_nonbudget_failure_block_activation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);full=self.fixture(root);config=continuation.build_config(full,root)
            p=root/continuation.FULL/'calls.jsonl';p.write_text(p.read_text()+'\n')
            with self.assertRaises(ValueError):continuation.verify_config(config,root)
        for failure in ('HTTP Error 429: exhausted','Timeout','validation error'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);full=self.fixture(root)
                receipt=read(root/continuation.FULL/'run_receipt.json',{})
                receipt['error']=failure;save(root/continuation.FULL/'run_receipt.json',receipt)
                with self.assertRaises(ValueError):continuation.build_config(full,root)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);full=self.fixture(root)
            save(root/continuation.FULL/'inflight.json',{'pending':{'reserved_cost_usd':.08}})
            with self.assertRaises(ValueError):continuation.build_config(full,root)

    def test_recorded_manual_stop_admits_recoverable_429_and_preserves_partial_stages(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);full=self.fixture(root)
            stop=root/continuation.FULL/'STOP';stop.write_text(continuation.MANUAL_STOP+' Let the request settle.')
            receipt=read(root/continuation.FULL/'run_receipt.json',{})
            receipt.update(error='Pipeline STOP file is present',new_accounted_usd=.021)
            save(root/continuation.FULL/'run_receipt.json',receipt)
            p=root/continuation.FULL/'calls.jsonl'
            with p.open('a') as target:target.write(json.dumps({'job_id':'failed','status':'error','http_status':429,'estimated_cost_usd':.02,'retry_exhausted':False})+'\n')
            partial=root/continuation.FULL/'photos/P002/observations.json';save(partial,{'old':'partial'})
            config=continuation.build_config(full,root)
            continuation.snapshot_prior_stop(config,root)
            copy=root/continuation.NEW/'prior_phase_snapshot/photos/P002/observations.json'
            self.assertEqual(copy.read_bytes(),partial.read_bytes())
            self.assertEqual((root/continuation.NEW/'prior_phase_snapshot/STOP').read_bytes(),stop.read_bytes())
            self.assertEqual(read(root/continuation.NEW/'prior_phase_snapshot/summary.json',{}),{'old':'summary'})
            self.assertTrue(stop.exists())
            self.assertAlmostEqual(config['previous_ledgers'][-1]['accounted_cost_usd'],.021)
            lines=continuation.ledger(p);lines[-1]['retry_exhausted']=True
            p.write_text(''.join(json.dumps(row)+'\n' for row in lines))
            with self.assertRaises(ValueError):continuation.build_config(full,root)

    def test_cap_increase_requires_exact_amendment_and_no_duplicate_ledgers(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);full=self.fixture(root);config=continuation.build_config(full,root)
            wrong=copy.deepcopy(config);wrong['previous_ledgers'][0]=wrong['previous_ledgers'][-1]
            with self.assertRaises(ValueError):continuation.verify_config(wrong,root)
            wrong=copy.deepcopy(config);wrong['stage_ceiling_inr']=601
            with self.assertRaises(ValueError):continuation.verify_config(wrong,root)
            amendment=read(root/continuation.AMENDMENT,{})
            amendment['additional_authorized_inr']=300;save(root/continuation.AMENDMENT,amendment)
            with self.assertRaises(ValueError):continuation.build_config(full,root)

    def test_snapshots_and_costs_preserve_old_outputs_and_count_each_charge_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);full=self.fixture(root);config=continuation.build_config(full,root)
            old=(root/continuation.FULL/'run_receipt.json').read_bytes()
            continuation.snapshot_prior_stop(config,root)
            self.assertEqual((root/continuation.NEW/'prior_phase_snapshot/run_receipt.json').read_bytes(),old)
            save(root/continuation.FULL/'run_receipt.json',{'status':'completed'})
            continuation.snapshot_prior_stop(config,root)
            p=root/continuation.NEW/'calls.jsonl';p.write_text(json.dumps({'job_id':'new','estimated_cost_usd':.01})+'\n')
            save(root/continuation.NEW/'inflight.json',{'new':{'reserved_cost_usd':9},'unsettled':{'reserved_cost_usd':.02}})
            costs=continuation.continuation_costs(config,root)
            self.assertAlmostEqual(costs['new_accounted_usd'],.031)
            self.assertAlmostEqual(costs['combined_stage_guard_inr'],185.1)
            self.assertAlmostEqual(costs['remaining_guard_inr'],414.9)
            self.assertAlmostEqual(costs['technical_preflight_usd'],.02)
            self.assertAlmostEqual(costs['revision_including_preflight_cost_inr'],.051*95)
            self.assertEqual(costs['stage_ceiling_inr'],600)
            self.assertEqual(read(root/continuation.NEW/'prior_phase_snapshot/scoreboard.json',{}),{'old':'scoreboard'})
            save(root/continuation.NEW/'prior_phase_snapshot/run_receipt.json',{})
            with self.assertRaises(ValueError):continuation.snapshot_prior_stop(config,root)

    def test_shared_lock_blocks_activation_while_prior_process_runs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            with (root/'out/pipeline/run.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(continuation,'ROOT',root), patch.object(sys,'argv',['continuation','--run']), patch.object(continuation,'StandardClient') as client:
                    with self.assertRaises(BlockingIOError):continuation.main()
                    client.assert_not_called()
            self.assertFalse((root/continuation.CONFIG).exists())

    def test_completed_rows_preserved_and_partial_photo_only_is_resumed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            old_result={'image_id':'P001','variant':'evidence_final','saved':'unchanged'}
            save(root/continuation.FULL/'results.json',[old_result])
            save(root/'data/test/test_manifest.json',[{'image_id':'P001'},{'image_id':'P002'},{'image_id':'P003'}])
            save(root/'data/reference_cards_v2.json',{'products':{}})
            old_ledger=(root/continuation.FULL/'calls.jsonl').read_bytes()
            old_config=(root/continuation.FULL_CONFIG).read_bytes()
            with patch.object(continuation,'ROOT',root), patch.object(sys,'argv',['continuation','--run','--limit','1']), \
                 patch.object(continuation.v2,'run_photo',return_value=({'machines':[]},[],[])) as run, \
                 patch.object(continuation,'score',return_value={'costs':{}}):
                continuation.main()
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args.args[2]['image_id'],'P002')
            self.assertIn(old_result,read(root/continuation.FULL/'results.json',[]))
            self.assertEqual(read(root/continuation.FULL/'completed_photos.json',[]),['P001','P002'])
            self.assertEqual((root/continuation.FULL/'calls.jsonl').read_bytes(),old_ledger)
            self.assertEqual((root/continuation.FULL_CONFIG).read_bytes(),old_config)
            self.assertEqual(read(root/continuation.NEW/'prior_phase_snapshot/run_receipt.json',{})['status'],'stopped')
            self.assertEqual(read(root/continuation.NEW/'run_receipt.json',{})['status'],'completed')


if __name__=='__main__':unittest.main()


class ValidationJobMappingTests(unittest.TestCase):
    def test_domain_validation_failure_uses_new_paid_job_id(self):
        from run_pipeline_v2_continuation import StandardClient
        from pipeline_api import Client
        from run_pipeline_v2 import generate_validated
        client=StandardClient.__new__(StandardClient)
        def invalid(raw):raise ValueError('Missing machine')
        with patch.object(StandardClient,'generate',return_value={}), patch.object(Client,'record_validation_failure') as record:
            with self.assertRaises(ValueError):generate_validated(client,'v2full:identify:P022','prompt',[],invalid)
        record.assert_called_once_with('v2standard:identify:P022','Missing machine')
