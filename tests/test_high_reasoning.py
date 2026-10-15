import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_high_reasoning import verify_previous
from run_pipeline import sha

class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        (self.out/'calls.jsonl').write_text(json.dumps({'estimated_cost_usd':.94})+'\n')
        (self.out/'inflight.json').write_text('{}')
        self.config={'budget':{'usd_inr':100,'stage_max_inr':306,'prior_accounted_inr':136.68},'previous_stage':{'calls_sha256':sha(self.out/'calls.jsonl'),'guard_accounted_inr':94,'stage_ceiling_inr':400,'prior_accounted_inr':42.68}}
    def test_spend_and_remaining_allowance(self):
        self.assertEqual(len(verify_previous(self.config,self.out)),1)
    def test_old_ledger_change_and_unresolved_call_stop(self):
        (self.out/'inflight.json').write_text('{"job":{}}')
        with self.assertRaisesRegex(ValueError,'in flight'):verify_previous(self.config,self.out)
        (self.out/'inflight.json').write_text('{}')
        with (self.out/'calls.jsonl').open('a') as f:f.write('{}\n')
        with self.assertRaisesRegex(ValueError,'spending changed'):verify_previous(self.config,self.out)
    def test_omitted_or_increased_spending_stops(self):
        for key in ['stage_max_inr','prior_accounted_inr']:
            changed=copy.deepcopy(self.config);changed['budget'][key]+=1
            with self.assertRaises(ValueError):verify_previous(changed,self.out)

if __name__=='__main__':unittest.main()
