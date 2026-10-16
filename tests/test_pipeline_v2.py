import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_pipeline_v2 as v2

class V2RunnerTests(unittest.TestCase):
    def test_original_crop_preserves_pixels_and_never_upscales(self):
        with tempfile.TemporaryDirectory() as d, patch.object(v2,'ROOT',Path(d)):
            root=Path(d); source=root/'original.png'
            Image.new('RGB',(3200,1600),'red').save(source)
            crop=v2.crop_original(source,[250,250,750,750],root/'crop.jpg',maximum=4000)
            self.assertEqual(crop['pixel_box'],(704,352,2496,1248))
            self.assertEqual((crop['width'],crop['height']),(1792,896))
            with Image.open(root/'crop.jpg') as saved:
                self.assertEqual(saved.size,(1792,896))
            with self.assertRaises(ValueError):v2.crop_original(source,[0,0,0,50],root/'bad.jpg')

    def test_matching_uses_embedding_crop_with_greatest_overlap(self):
        boxes={'P1':[{'instance_id':'left','box_2d':[0,0,1000,400]}, {'instance_id':'right','box_2d':[0,600,1000,1000]}]}
        shortlists={'left':[{'product':'a','similarity':.9}],'right':[{'product':'b','similarity':.8}]}
        self.assertEqual(v2.saved_ranking('P1',{'box_2d':[0,650,1000,1000]},boxes,shortlists,['a','b'])[0]['product'],'b')
        self.assertEqual(v2.saved_ranking('P2',{}, {'P2':[]},{},['a','b']),[{'product':'a','similarity':None},{'product':'b','similarity':None}])

    def test_decisive_region_cannot_select_another_machine(self):
        raw={'results':[{'object_id':'one'}]}
        validated={'decision':{'status':'match'},'decisive_region':[800,800,900,900]}
        with patch.object(v2,'validate_match_result',return_value=validated):
            result=v2.validate_batch(raw,[{'object_id':'one','box_2d':[100,100,300,300]}],{'one':['a']},90)
        self.assertEqual(result['one']['decisive_region'],[100,100,300,300])
        self.assertTrue(result['one']['evidence_conflict'])

    def test_batch_rejects_missing_duplicate_and_extra_machines(self):
        target=[{'object_id':'one'},{'object_id':'two'}]
        for ids in [['one'],['one','one'],['one','two','three']]:
            with self.assertRaises(ValueError):v2.validate_batch({'results':[{'object_id':i} for i in ids]},target,{},90)

    def test_validation_failure_is_recorded_without_second_paid_call(self):
        class Client:
            def __init__(self):self.calls=0;self.events=[]
            def generate(self,*a):self.calls+=1;return {'wrong':'shape'}
            def record_validation_failure(self,*a):self.events.append(a)
        client=Client()
        def invalid(raw):raise ValueError('Missing results')
        with self.assertRaises(ValueError):v2.generate_validated(client,'job','prompt',[],invalid)
        self.assertEqual(client.calls,1)
        self.assertEqual(client.events,[('job','Missing results')])

    def test_empty_freeze_manifest_is_rejected(self):
        with self.assertRaises(ValueError):v2.verify_frozen({'frozen_files':{}})

    def test_frozen_file_change_stops_before_history_or_api(self):
        with tempfile.TemporaryDirectory() as d, patch.object(v2,'ROOT',Path(d)):
            root=Path(d);(root/'old.json').write_text('{}')
            config={'frozen_files':{'old.json':v2.sha(root/'old.json')}}
            with patch.object(v2,'verify_history',return_value=[]) as history:
                v2.verify_frozen(config)
                (root/'old.json').write_text('{"changed":true}')
                with self.assertRaises(ValueError):v2.verify_frozen(config)
                self.assertEqual(history.call_count,1)

if __name__=='__main__':unittest.main()
