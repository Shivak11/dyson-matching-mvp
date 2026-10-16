import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import resume_v2_recovery as replay


class ReplayTests(unittest.TestCase):
    def record(self):
        raw='{"objects":[{"role":"machine","object_id":"o1","box_2d":[0,0,1000,1000]}]}'
        original=json.loads(raw)
        saved=json.loads(json.dumps(original,sort_keys=True))
        return {'status':'ok','cost_basis':'provider_reported_cost','result':saved,
                'provider_response':{'choices':[{'message':{'content':raw}}]}}

    def test_original_order_is_restored_without_changing_values(self):
        record=self.record();before=copy.deepcopy(record)
        result=replay.provider_order(record['result'],record)
        self.assertEqual(result,record['result'])
        self.assertEqual(list(result['objects'][0]),['role','object_id','box_2d'])
        self.assertNotEqual(json.dumps(result),json.dumps(record['result']))
        self.assertEqual(record,before)

    def test_changed_saved_or_provider_values_are_rejected(self):
        record=self.record()
        with self.assertRaises(ValueError):replay.provider_order({'changed':True},record)
        record['provider_response']['choices'][0]['message']['content']='{"objects":[]}'
        with self.assertRaises(ValueError):replay.provider_order(record['result'],record)
        record=self.record();record['result']={'value':True};record['provider_response']['choices'][0]['message']['content']='{"value":1}'
        with self.assertRaises(ValueError):replay.provider_order(record['result'],record)
        record=self.record();record['status']='validation_error'
        with self.assertRaises(ValueError):replay.provider_order(record['result'],record)

    def test_offline_normalised_result_stays_as_saved(self):
        record=self.record();record.update(cost_basis='offline_validation_recovery',result={'normalised':True})
        result=replay.provider_order(record['result'],record)
        self.assertIs(result,record['result'])

    def test_client_replays_generation_after_the_existing_request_check(self):
        client=replay.ReplayClient.__new__(replay.ReplayClient)
        record=self.record();client.logical_records={'v2long:observe:P051':record}
        with patch.object(replay.BASE_CLIENT,'generate',return_value=record['result']) as generate:
            result=client.generate('v2full:observe:P051','flash37high','prompt',[])
            generate.assert_called_once_with('v2full:observe:P051','flash37high','prompt',[])
        self.assertEqual(list(result['objects'][0]),['role','object_id','box_2d'])

    def test_receipt_is_bound_to_source_and_frozen_configuration(self):
        config={'budget':{'stage_max_inr':100,'total_max_inr':2000,'prior_accounted_inr':500,'usd_inr':100}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out'
            client=replay.ReplayClient(config,root,out)
            path=out/'replay_adapter_receipt.json';before=path.read_bytes()
            receipt=json.loads(before)
            self.assertEqual(receipt['adapter_source_sha256'],replay.recovery.v2.sha(Path(replay.__file__)))
            self.assertEqual(receipt['config_sha256'],client.config_sha256)
            replay.ReplayClient(config,root,out)
            self.assertEqual(path.read_bytes(),before)
            receipt['adapter_source_sha256']='changed';path.write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):replay.ReplayClient(config,root,out)

    def test_runner_binds_only_the_client_and_restores_it_after_failure(self):
        old=replay.recovery.RecoveryClient
        def fail():
            self.assertIs(replay.recovery.RecoveryClient,replay.ReplayClient)
            raise ValueError('test failure')
        with patch.object(replay.recovery,'main',side_effect=fail):
            with self.assertRaises(ValueError):replay.main()
        self.assertIs(replay.recovery.RecoveryClient,old)


if __name__=='__main__':unittest.main()
