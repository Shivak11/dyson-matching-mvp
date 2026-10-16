import copy
import fcntl
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import repair_failure_geometry as repairer
import test_failure_protocol as fixtures
from pipeline_api import Client, digest, encoded


class FailureGeometryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.FailureProtocolTests()
        self.targets=[self.fixture.target()]
        self.refs=self.fixture.refs()

    def raw(self, supports=2):
        raw=self.fixture.raw()
        check=raw['results'][0]['reference_checks'][0]
        features=['body_layout','handle_control','bin_mechanism','cyclone_filter']
        check['comparisons']=[self.fixture.comparison(feature=feature) for feature in features[:supports]]
        check['comparisons'][0]['query_box_2d']=[110,110,400,902]
        return raw

    def test_suppression_retains_original_and_never_changes_raw_decision(self):
        raw=self.raw(4);before=copy.deepcopy(raw)
        normalised=repairer.normalise(raw,self.targets,self.refs)
        self.assertEqual(raw,before)
        item=normalised['results'][0];original=raw['results'][0]
        self.assertEqual(item['decision'],original['decision'])
        archived=item['unverified_comparisons'][0]
        self.assertEqual(archived,{'object_id':'o1','reference':'R01','comparison_index':0,
                                  'comparison':original['reference_checks'][0]['comparisons'][0]})
        expected=copy.deepcopy(original['reference_checks'][0]['comparisons'][0])
        expected.update(query_visible=False,query_box_2d=None,relation='unobserved')
        self.assertEqual(item['reference_checks'][0]['comparisons'][0],expected)
        self.assertEqual(repairer.validate_comparison(normalised,self.targets,self.refs)['o1']['decision']['status'],'match')

    def test_one_remaining_distinct_support_demotes_without_changing_identity(self):
        raw=self.raw();normalised=repairer.normalise(raw,self.targets,self.refs)
        mapped=repairer.validate_comparison(normalised,self.targets,self.refs)['o1']
        self.assertEqual(mapped['decision']['status'],'not_sure')
        self.assertEqual(normalised['results'][0]['decision'],raw['results'][0]['decision'])
        self.assertEqual(mapped['raw']['decision']['confidence'],95)

    def test_visible_conflict_is_downgraded_only_when_its_last_conflict_is_removed(self):
        for another in [False,True]:
            raw=self.raw(4);check=raw['results'][0]['reference_checks'][1]
            conflict=self.fixture.comparison('R02');conflict.update(relation='conflict',query_box_2d=[110,110,400,902])
            check.update(outcome='visible_conflict',comparisons=[conflict],evidence='Visible control differs.')
            if another:
                valid=self.fixture.comparison('R02','handle_control');valid['relation']='conflict'
                check['comparisons'].append(valid)
            normalised=repairer.normalise(raw,self.targets,self.refs)
            changed=normalised['results'][0]['reference_checks'][1]
            self.assertEqual(changed['outcome'],'visible_conflict' if another else 'insufficient_evidence')
            self.assertEqual(changed['evidence'],check['evidence'])

    def test_other_geometry_and_domain_defects_are_rejected_without_mutation(self):
        variants=[('out_of_scene',[110,110,400,1001]),('negative',[-1,110,400,902]),
                  ('nonfinite',[110,110,math.nan,902]),('bool',[True,110,400,902]),
                  ('empty',[110,110,110,902]),('malformed',[110,110,902])]
        for name,box in variants:
            raw=self.raw();raw['results'][0]['reference_checks'][0]['comparisons'][0]['query_box_2d']=box
            before=copy.deepcopy(raw)
            with self.subTest(name=name),self.assertRaises(ValueError):repairer.normalise(raw,self.targets,self.refs)
            self.assertEqual(repr(raw),repr(before))
        for variant in ['reference_box','panel','unknown_reference','unknown_object','confidence','hidden_support','other_brand_region']:
            raw=self.raw();item=raw['results'][0];comparison=item['reference_checks'][0]['comparisons'][0]
            if variant=='reference_box':comparison['reference_box_2d']=[0,0,1001,1000]
            if variant=='panel':comparison['panel']='R02-P1'
            if variant=='unknown_reference':item['reference_checks'][-1]['reference']='R10'
            if variant=='unknown_object':item['object_id']='o2'
            if variant=='confidence':item['decision']['confidence']=.95
            if variant=='hidden_support':comparison.update(reference_visible=False,reference_box_2d=None)
            if variant=='other_brand_region':item['other_brand_evidence']=[{'text':'Printed text','query_box_2d':[0,0,50,50]}]
            with self.subTest(variant=variant),self.assertRaises(ValueError):repairer.normalise(raw,self.targets,self.refs)
        with self.assertRaises(ValueError):repairer.normalise(self.fixture.raw(),self.targets,self.refs)

    def saved_phase(self,root):
        root=Path(root)
        (root/'out/pipeline').mkdir(parents=True)
        sentinel=root/'frozen.txt';sentinel.write_text('Frozen evidence.\n')
        previous=[]
        for index in range(7):
            path=root/f'out/old{index}/calls.jsonl';path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'estimated_cost_usd':.5})+'\n')
            previous.append({'file':str(path.relative_to(root)),'sha256':repairer.runner.sha(path),'accounted_cost_usd':.5})
        config={'frozen_files':{'frozen.txt':repairer.runner.sha(sentinel)},'previous_ledgers':previous,
                'stage_ceiling_inr':1000,'prior_stage_accounted_inr':42.68,
                'budget':{'usd_inr':100,'stage_max_inr':650,'prior_accounted_inr':392.68,'total_max_inr':2000},
                'models':{'comparison':{'model':'google/gemini-3.7-flash'}},
                'rate_limit_policy':{'rate_limit_retries':3,'request_interval_seconds':15,'max_retry_delay_seconds':300},
                'scope':{'photo_ids':['P013']},'confidence_threshold':90}
        repairer.runner.save(root/repairer.runner.CONFIG,config)
        directory=root/repairer.runner.OUT
        repairer.runner.save(directory/'frozen_config.json',config)
        inventory=repairer.runner.validate_inventory({'objects':self.targets})
        repairer.runner.save(directory/'photos/P013/inventory.json',inventory)
        repairer.runner.save(directory/'reference_panels.json',{'references':self.refs})
        raw=self.raw(4)
        response={'choices':[{'finish_reason':'stop','native_finish_reason':'STOP',
                               'message':{'content':json.dumps(raw)}}]}
        original={'job_id':'v3:compare:P013:attempt:1','logical_job_id':'v3:compare:P013','status':'ok',
                  'estimated_cost_usd':.10441875,'cost_basis':'provider_reported_cost',
                  'config_sha256':digest(encoded(config)),'request_sha256':'request-hash',
                  'requested_model':config['models']['comparison']['model'],'http_status':200,
                  'provider_response':response,'result':raw}
        ledger=directory/'calls.jsonl';ledger.write_bytes(encoded(original)+b'\n')
        Client(config,root,directory,**config['rate_limit_policy']).record_validation_failure('v3:compare:P013',repairer.ERROR)
        return config,directory,ledger

    def test_offline_apply_preserves_ledger_prefix_and_cost_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);config,directory,path=self.saved_phase(root)
            before=path.read_bytes();old=repairer.runner.ledger(path)
            with patch.object(Client,'generate',side_effect=AssertionError('No API calls permitted')):
                dry=repairer.repair('v3:compare:P013',root=root)
                self.assertEqual(path.read_bytes(),before)
                self.assertFalse((directory/'geometry_repairs').exists())
                receipt=repairer.repair('v3:compare:P013',apply=True,root=root)
            rows=repairer.runner.ledger(path)
            self.assertTrue(path.read_bytes().startswith(before));self.assertEqual(len(rows),3)
            self.assertEqual(rows[-1]['cost_basis'],'offline_validation_recovery')
            self.assertEqual(sum(row['estimated_cost_usd'] for row in rows),sum(row['estimated_cost_usd'] for row in old))
            self.assertEqual(rows[-1]['provider_response'],rows[0]['provider_response'])
            self.assertEqual(rows[-1]['recovery']['original_record_sha256'],receipt['original_record_sha256'])
            self.assertEqual(rows[-1]['recovery']['validation_failure_sha256'],receipt['validation_failure_sha256'])
            self.assertEqual(receipt['normalised_result_sha256'],digest(encoded(rows[-1]['result'])))
            self.assertEqual(receipt['normalised_result_sha256'],dry['normalised_result_sha256'])
            self.assertEqual(receipt['paid_requests'],0);self.assertEqual(receipt['additional_cost_usd'],0)
            self.assertEqual(receipt['hash_kind'],'canonical_json')
            self.assertEqual(json.loads((directory/'geometry_repairs/v3_compare_P013.json').read_text()),receipt)
            with self.assertRaises(ValueError):repairer.repair('v3:compare:P013',apply=True,root=root)
            self.assertEqual(len(repairer.runner.ledger(path)),3)

    def test_canonical_context_survives_key_reordering_but_rejects_changed_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);config,directory,path=self.saved_phase(root)
            first=repairer.repair('v3:compare:P013',root=root)
            inventory=directory/'photos/P013/inventory.json';saved=json.loads(inventory.read_text())
            inventory.write_bytes(encoded(saved))
            second=repairer.repair('v3:compare:P013',root=root)
            self.assertEqual(first['canonical_context_sha256'],second['canonical_context_sha256'])
            saved['machines'][0]['box_2d']=[100,100,800,800]
            inventory.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError,'validated inventory'):repairer.repair('v3:compare:P013',root=root)

    def test_scope_pending_frozen_config_and_lock_guards(self):
        for variant in ['observe','outside','pending','frozen','config','lock']:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);config,directory,path=self.saved_phase(root)
                job='v3:compare:P013';lock=None
                if variant=='observe':job='v3:inventory:P013'
                if variant=='outside':job='v3:compare:P014'
                if variant=='pending':repairer.runner.save(directory/'inflight.json',{'unfinished':{}})
                if variant=='frozen':(root/'frozen.txt').write_text('Changed.')
                if variant=='config':repairer.runner.save(directory/'frozen_config.json',{})
                if variant=='lock':
                    lock=(root/'out/pipeline/run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                before=path.read_bytes()
                try:
                    with self.assertRaises((ValueError,BlockingIOError)):repairer.repair(job,apply=True,root=root)
                finally:
                    if lock:lock.close()
                self.assertEqual(path.read_bytes(),before)

    def test_wrong_failure_or_changed_paid_response_cannot_be_repaired(self):
        for variant in ['error','request','partial','raw','model','duplicate','budget']:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);config,directory,path=self.saved_phase(root)
                rows=repairer.runner.ledger(path)
                if variant=='error':rows[-1]['error']='Other validation error'
                if variant=='request':rows[-1]['request_sha256']='different'
                if variant=='partial':rows[0]['provider_response']['choices'][0]['finish_reason']='length'
                if variant=='raw':rows[0]['result']['results'][0]['decision']['confidence']=94
                if variant=='model':rows[0]['requested_model']='another-model'
                if variant=='duplicate':rows.insert(1,copy.deepcopy(rows[0]))
                if variant=='budget':rows[0]['estimated_cost_usd']=7
                path.write_bytes(b''.join(encoded(row)+b'\n' for row in rows));before=path.read_bytes()
                with self.assertRaises(ValueError):repairer.repair('v3:compare:P013',apply=True,root=root)
                self.assertEqual(path.read_bytes(),before)

    def test_actual_p013_saved_response_without_labels_or_api(self):
        root=repairer.ROOT;directory=root/repairer.runner.OUT
        ledger=directory/'calls.jsonl'
        if not ledger.exists():self.skipTest('Saved P013 paid response unavailable')
        rows=[row for row in repairer.runner.ledger(ledger) if row.get('logical_job_id')=='v3:compare:P013' and row.get('cost_basis')=='provider_reported_cost']
        if len(rows)!=1:self.skipTest('Exactly one original P013 paid response unavailable')
        config=repairer.runner.read(root/repairer.runner.CONFIG,{})
        targets,refs,context=repairer.load_context('v3:compare:P013',config,root)
        raw=rows[0]['result'];normalised=repairer.normalise(raw,targets,refs)
        self.assertEqual(normalised['results'][0]['decision'],raw['results'][0]['decision'])
        self.assertEqual(len(normalised['results'][0]['unverified_comparisons']),2)
        self.assertEqual(repairer.validate_comparison(normalised,targets,refs)['o1']['decision']['status'],'match')
        self.assertEqual(repairer.validate_comparison(normalised,targets,refs)['o1']['decision']['confidence'],95)


if __name__=='__main__':unittest.main()
