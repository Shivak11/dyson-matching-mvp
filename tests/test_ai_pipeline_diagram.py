"""Check the smaller catalogue and joint-photo diagram against the real pipeline."""
import json
from pathlib import Path
import re
import struct
import unittest
import xml.etree.ElementTree as ET

from test_architecture_diagram import pinned_model_guards


ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / 'docs/architecture/ai-pipeline.svg'


class AIPipelineDiagramTests(unittest.TestCase):
    def test_pipeline_facts(self):
        document = ET.fromstring(SVG.read_text())
        facts = json.loads(document.find('{http://www.w3.org/2000/svg}metadata').text)
        inference = (ROOT / 'webapp/inference.py').read_text()
        guards = pinned_model_guards()
        self.assertEqual(facts['model'], guards['model'])
        self.assertEqual(facts['provider'], guards['provider'])
        self.assertEqual(facts['reasoning'], guards['thinking_level'])
        dimensions = re.search(r'ImageOps.contain\(image.convert\(\x27RGB\x27\), \((\d+), (\d+)\)\)', inference)
        self.assertEqual((facts['reference_tile_size'],) * 2, tuple(map(int, dimensions.groups())))
        self.assertEqual(facts['reference_columns'], int(re.search(r'width = 640 \* min\((\d+), len\(panels\)\)', inference).group(1)))
        store = (ROOT / 'webapp/store.py').read_text()
        self.assertEqual(facts['product_views'], int(re.search(r'if len\(prior\) >= (\d+)', store).group(1)))
        self.assertEqual(facts['image_tool'], 'Pillow')
        self.assertIn('from PIL import Image, ImageOps', inference)
        joint = inference[inference.index('    def _run_multiple('):]
        self.assertEqual(facts['inventory_all_views'], "generate('Finding product across views', prompt, images," in joint)
        self.assertEqual(facts['comparison_all_views_and_references'], "generate('Comparing product views together', prompt, images + references," in joint)
        transport = (ROOT / 'webapp/transport.py').read_text()
        self.assertEqual(facts['strict_json_schema'], "'type': 'json_schema'" in transport and "'strict': True" in transport)
        visible = ' '.join(node.text or '' for node in document.findall('{http://www.w3.org/2000/svg}text'))
        self.assertIn('Both Gemini steps receive all 3 photos together.', visible)
        self.assertIn('brochure details as supplied text', visible)
        self.assertIn('Python checks JSON', visible)

    def test_png_dimensions(self):
        png = SVG.with_suffix('.png').read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', png[16:24]), (2880, 1820))


if __name__ == '__main__':
    unittest.main()
