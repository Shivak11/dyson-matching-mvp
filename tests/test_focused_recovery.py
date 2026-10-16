import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_focused_recovery as focus
from run_pipeline import save,sha


class FocusedRunnerTests(unittest.TestCase):
    def test_request_reservations_fit_remaining_guard(self):
        models=[dict(input_token_bound=i,max_output_tokens=o,input_usd_per_million=p,output_usd_per_million=c)
                for i,o,p,c in [(20000,16384,.75,3.75),(16000,8192,2,10),(28000,16384,.75,3.75)]]
        maximum=7*sum(focus.reservation(m) for m in models)*100
        self.assertAlmostEqual(maximum,190.960)
        self.assertLess(maximum,222.2090639)

    def test_completion_source_wins_only_with_saved_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);recent=root/focus.COMPLETED/'photos/P019'
            recent.mkdir(parents=True)
            self.assertEqual(focus.source_directory('P019',root),root/focus.OLD/'photos/P019')
            save(recent/'inventory.json',{'machines':[]})
            self.assertEqual(focus.source_directory('P019',root),recent)

    def test_verify_rejects_changed_frozen_input(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'x').write_text('before')
            config={'frozen_files':{'x':sha(root/'x')}}
            (root/'x').write_text('after')
            with self.assertRaisesRegex(ValueError,'Frozen focused input changed'):focus.verify_config(config,root)

    def test_history_is_nine_distinct_ledgers(self):
        config={'frozen_files':{},'previous_ledgers':[{'file':'repeated'}]*9,'models':{}}
        with self.assertRaisesRegex(ValueError,'Nine previous ledgers'):focus.verify_config(config)

    def test_all_text_and_vision_providers_must_be_openrouter(self):
        config={'frozen_files':{},'previous_ledgers':[{'file':str(i)} for i in range(9)],
                'models':{'checker':{'provider':'native'}}}
        with self.assertRaisesRegex(ValueError,'Every model'):focus.verify_config(config)

    def test_tool_only_cases_keep_every_independent_target_without_paid_calls(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);directory=root/focus.OUT/'photos/one'
            targets=[{'object_id':'a'},{'object_id':'b'}]
            save(directory/'plan.json',{'active_ids':[]})
            save(directory/'initial.json',{'inventory':{'machines':targets}})
            save(root/focus.FACTS,{'compatibility':[{'part_code':'123','body_identity':False}]})
            client=Mock();returned,rows=focus.run_photo(client,{'catalogue_order':['cat']},'one',root)
            self.assertEqual(returned,targets)
            self.assertEqual({r['instance_id'] for r in rows},{'one_a','one_b'})
            self.assertTrue(all(r['decision']['status']=='not_sure' for r in rows))
            client.generate.assert_not_called()
            self.assertFalse(json.loads((directory/'compatibility.json').read_text())['body_identified'])

    def test_new_namespace_keeps_old_failure_costs_without_importing_failure_state(self):
        for last,expected in [(900,990),(995,995)]:
            with self.subTest(last=last),tempfile.TemporaryDirectory() as d:
                root=Path(d);(root/'out/pipeline').mkdir(parents=True)
                config={'rate_limit_policy':{'request_interval_seconds':15},'scope':{'photo_ids':[]}}
                save(root/focus.CONFIG,config)
                old=[{'status':'error','request_finished_unix':1990,'estimated_cost_usd':.1}]
                client=Mock(last_request_finished_at=last,pending={})
                with patch.object(focus,'ROOT',root),patch.object(sys,'argv',['run','--run']), \
                     patch.object(focus,'verify_config',return_value=old), \
                     patch.object(focus,'Client',return_value=client) as factory, \
                     patch.object(focus,'report',return_value={'costs':{}}), \
                     patch.object(focus.time,'time',return_value=2000), \
                     patch.object(focus.time,'monotonic',return_value=1000):
                    focus.main()
                self.assertNotIn('reuse_records',factory.call_args.kwargs)
                self.assertEqual(client.last_request_finished_at,expected)

    def test_checker_question_selection_cannot_pass_answers_to_prompt(self):
        plan={'targets':[{'object_id':'a'}]};baseline={'old':'answer'};ranks={'a':['R01']};facts={'facts':[]}
        with patch.object(focus,'plan_focus',return_value={'check_question_ids':['a__identifier']}) as planner:
            answer=focus.checker_questions(plan,{'observations':[]},baseline,ranks,facts)
        self.assertEqual(answer,['a__identifier'])
        self.assertEqual(planner.call_args.args[0],plan['targets'])


if __name__=='__main__':unittest.main()
