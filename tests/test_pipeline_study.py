import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from summarize_pipeline_study import cost_tables
class StudyTests(unittest.TestCase):
    def test_shared_cost_once_and_audit_events_excluded(self):
        c={'models':{'a':{'model':'a-route'},'b':{'model':'b-route'}},'reporting_usd_inr':100,'budget':{'usd_inr':100,'stage_max_inr':400}}
        def call(job,cost,basis='provider_reported_cost',status='ok'):
            return {'job_id':job,'estimated_cost_usd':cost,'cost_basis':basis,'status':status,'elapsed_seconds':1}
        calls=[call('detect:P001',.01),call('embed:P001_01',.001),call('embed:dyson_x_0',.001),call('check:a:visual:P001_01',.02),call('check:b:visual:P001_01',.03),call('check:b:visual:P001_01',0,'validation_only_no_new_request','validation_error'),call('check:b:visual:P001_01',0,'offline_validation_recovery')]
        results=[{'model':m,'variant':'visual','image_id':'P001'} for m in ['a','b','a+b']]
        out=cost_tables(c,calls,results,{'P001'})
        combo=next(x for x in out['models'] if x['model']=='a+b')
        self.assertAlmostEqual(combo['cost_per_original_photo_inr'],6.1)
        self.assertAlmostEqual(out['stage_cost_inr'],6.2)
        self.assertEqual(out['api_call_count'],5)
        self.assertEqual(out['validation_failure_count'],1)
        self.assertEqual(out['offline_recovery_count'],1)
        self.assertAlmostEqual(out['one_time_reference_embeddings_inr'],.1)
if __name__=='__main__':unittest.main()
