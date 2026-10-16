import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_failure_recovery as run
from run_pipeline import save, sha
from pipeline_api import Client


def fixture(root):
    source=root/'data/catalog/example.png';source.parent.mkdir(parents=True)
    Image.new('RGBA',(100,200),(20,30,40,255)).save(source)
    references={f'R{i:02d}':{'product':'family_'+str(i),'in_catalog':i<=6,
        'panels':[{'panel_id':f'R{i:02d}-P1','source_file':'data/catalog/example.png',
                   'source_sha256':sha(source),'box_2d':[0,0,500,1000],'description':'Body'}]}
        for i in range(1,10)}
    save(root/run.VIEWS,{'references':references})
    save(root/'data/reference_cards_v2.json',{'products':{entry['product']:{'in_catalog':entry['in_catalog'],
         'images':[{'file':'data/catalog/example.png','sha256':sha(source)}]} for entry in references.values()}})
    return references


class FailureRecoveryTests(unittest.TestCase):
    def test_render_uses_manufacturer_pixels_and_neutral_panel_ids(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root)
            refs,images=run.render_references(root)
            self.assertEqual(len(images),9);self.assertEqual(len(refs),9)
            for item in images:
                self.assertEqual(list(item['source_pixel_box']),[0,0,100,100])
                self.assertEqual(sha(root/item['file']),item['sha256'])
                self.assertEqual((item['width'],item['height']),(100,100))
                self.assertEqual(Path(item['file']).stem,item['panel_id'])

    def test_reference_mapping_and_source_boundaries(self):
        for failure in ['source','hash','duplicate','flag','panel']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
                root=Path(d);refs=fixture(root)
                if failure=='source':refs['R01']['panels'][0]['source_file']='data/test/query.jpg'
                if failure=='hash':refs['R01']['panels'][0]['source_sha256']='changed'
                if failure=='duplicate':refs['R02']['product']=refs['R01']['product']
                if failure=='flag':refs['R01']['in_catalog']=1
                if failure=='panel':refs['R02']['panels'][0]['panel_id']='R01-P1'
                save(root/run.VIEWS,{'references':refs})
                with self.assertRaises(ValueError):run.render_references(root)

    def test_shared_accessory_stays_unsure_without_a_comparison_call(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'query.jpg';Image.new('RGB',(100,100),'grey').save(source)
            inventory={'machines':[{'object_id':'o1','accessory_only':True}], 'objects':[]}
            class Fake:
                def __init__(self):self.jobs=[]
                def generate(self,job,model,prompt,images):self.jobs.append((job,model));return {}
            client=Fake()
            with patch.object(run,'validate_inventory',return_value=inventory):
                targets,rows=run.run_photo(client,{'catalogue_order':['a']},{'image_id':'P012','file':'query.jpg'},{},root)
            self.assertEqual(client.jobs,[('v3:inventory:P012','inventory')])
            self.assertEqual(rows[0]['decision']['status'],'not_sure')
            self.assertTrue(rows[0]['comparison_skipped'])
            self.assertEqual(len(targets),1)

    def test_crop_retains_pixels_bounds_and_relative_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'original.png';Image.new('RGB',(2000,1000),'red').save(source)
            out=root/'crop.jpg';result=run.query_crop(source,[100,100,900,900],out,root)
            self.assertEqual(result['file'],'crop.jpg')
            self.assertEqual(result['sha256'],sha(out))
            with Image.open(out) as image:self.assertLessEqual(max(image.size),1536)
            self.assertGreater(result['pixel_box'][2]-result['pixel_box'][0],1500)

    def test_new_allowance_carries_all_seven_ledgers_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);frozen=root/'frozen.txt';frozen.write_text('unchanged')
            history=[]
            for index in range(7):
                file=Path('old')/str(index)/'calls.jsonl';(root/file).parent.mkdir(parents=True)
                (root/file).write_text(json.dumps({'estimated_cost_usd':.5})+'\n')
                history.append({'file':str(file),'sha256':sha(root/file),'accounted_cost_usd':.5})
            config={'frozen_files':{'frozen.txt':sha(frozen)},'previous_ledgers':history,'stage_ceiling_inr':1000,
                    'prior_stage_accounted_inr':42.68,'budget':{'usd_inr':100,'stage_max_inr':650,'prior_accounted_inr':392.68}}
            self.assertEqual(len(run.verify_config(config,root)),7)
            wrong=copy.deepcopy(config);wrong['budget']['stage_max_inr']+=.01
            with self.assertRaises(ValueError):run.verify_config(wrong,root)
            frozen.write_text('changed')
            with self.assertRaises(ValueError):run.verify_config(config,root)

    def test_current_reservations_and_budget_stop_are_the_shared_transport(self):
        models={'inventory':{'input_token_bound':20000,'max_output_tokens':16384},
                'comparison':{'input_token_bound':50000,'max_output_tokens':32768}}
        reservations={key:(value['input_token_bound']*.75+value['max_output_tokens']*3.75)/1e6 for key,value in models.items()}
        self.assertAlmostEqual(reservations['inventory'],.07644)
        self.assertAlmostEqual(reservations['comparison'],.16038)
        self.assertLess(23*reservations['inventory']*100+13*reservations['comparison']*100,425.1550139)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config={'budget':{'usd_inr':100,'stage_max_inr':1,'total_max_inr':2000,'prior_accounted_inr':100},'models':{}}
            client=Client(config,root,root/'out')
            with patch('pipeline_api.urllib.request.urlopen') as network:
                with self.assertRaisesRegex(RuntimeError,'budget stop'):
                    client._paid_call('new','new','generate',{'provider':'openrouter','model':'m'},b'{}','sha','url',.16038,lambda x:x,1)
                network.assert_not_called()

    def test_unrun_failure_is_not_reported_as_a_model_abstention(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); out=root/run.OUT;out.mkdir(parents=True)
            manifest=[{'image_id':name,'evaluation_role':'labelled_single','labels':['a']} for name in ['P001','P002']]
            save(root/'data/test/test_manifest.json',manifest)
            save(root/'out/pipeline_v2_recovery/independent_audit.json',{'final':{'per_photo':[
                {'image_id':'P001','status':'match','correct':False},{'image_id':'P002','status':'match','correct':True}]}})
            decision={'status':'match','product':'a','confidence':95,'top_two':['a'],'evidence':['Body evidence.'],
                      'missing_evidence':[],'contradictions':[],'retake':''}
            save(out/'results.json',[{'image_id':'P002','instance_id':'P002_o1','model':'m','variant':'aligned_reference',
                                     'candidates':['a'],'decision':decision}])
            save(out/'detections.json',{'P002':[{'instance_id':'P002_o1'}]})
            save(out/'completed_photos.json',['P002'])
            config={'scope':{'photo_ids':['P001','P002'],'failure_ids':['P001'],'control_ids':['P002']},
                    'catalogue_order':['a'],'previous_ledgers':[{'accounted_cost_usd':1}],
                    'budget':{'usd_inr':100},'reporting_usd_inr':95,'stage_ceiling_inr':1000}
            report=run.report(config,root)
            self.assertEqual(report['transitions'][0]['new_status'],'not_run')
            self.assertEqual(report['failure_outcomes']['not_run'],1)
            self.assertEqual(report['failure_outcomes']['wrong_to_unsure'],0)
            self.assertEqual(report['control_regressions'],[])

    def test_raw_guess_remains_visible_when_gate_rejects_it(self):
        refs={'R01':{'product':'a','in_catalog':True},'R07':{'product':'outside','in_catalog':False}}
        native={'status':'same_family','reference':'R01','confidence':95,'top_two':['R01','R07'],
                'evidence':['Claimed feature.'],'missing_evidence':[],'contradictions':[],'retake':''}
        row={'image_id':'P001','variant':'aligned_reference','raw':{'decision':native},
             'decision':{'status':'not_sure','product':None,'confidence':95,'top_two':[]}}
        before=copy.deepcopy(row);initial,=run.raw_rows([row],refs)
        self.assertEqual(row,before)
        self.assertEqual(initial['variant'],'reference_raw')
        self.assertEqual(initial['decision']['status'],'match')
        self.assertEqual(initial['decision']['product'],'a')
        self.assertEqual(initial['decision']['top_two'],['a','outside'])
        self.assertEqual(row['decision']['status'],'not_sure')

    def test_validation_failure_is_recorded_without_another_paid_request(self):
        class Fake:
            def __init__(self):self.failures=[];self.calls=0
            def generate(self,*args):self.calls+=1;return {'bad':True}
            def record_validation_failure(self,job,error):self.failures.append((job,error))
        client=Fake()
        def reject(raw):raise ValueError('Invalid response')
        with self.assertRaisesRegex(ValueError,'Invalid response'):run.generate(client,'job','model','prompt',[],reject)
        self.assertEqual(client.calls,1);self.assertEqual(client.failures,[('job','Invalid response')])


if __name__=='__main__':unittest.main()
