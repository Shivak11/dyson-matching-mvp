"""Keep the deployed architecture picture consistent with the current source."""
import ast
import inspect
import json
from pathlib import Path
import re
import struct
import unittest
import xml.etree.ElementTree as ET

from webapp import cloud_runtime
from webapp.inference import PAUSE_SECONDS
from webapp.request_coordinator import RequestCoordinator


ROOT = Path(__file__).resolve().parents[1]
DIAGRAM = ROOT / 'docs/architecture/system-diagram.svg'


def read(path):
    return (ROOT / path).read_text()


def pinned_model_guards():
    tree = ast.parse(read('webapp/inference.py'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'pinned_model')
    values = {}
    for node in ast.walk(function):
        if (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotEq)
                and isinstance(node.left, ast.Subscript) and isinstance(node.left.value, ast.Name)
                and node.left.value.id == 'model'):
            values[ast.literal_eval(node.left.slice)] = ast.literal_eval(node.comparators[0])
    return values


class ArchitectureDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svg = DIAGRAM.read_text()
        cls.document = ET.fromstring(cls.svg)
        cls.facts = json.loads(cls.document.find('{http://www.w3.org/2000/svg}metadata').text)
        cls.config = json.loads(read('cloudflare/wrangler.jsonc'))

    def test_deployment_and_storage_facts(self):
        facts, config = self.facts, self.config
        self.assertEqual(facts['release_image_sha256'], config['containers'][0]['image'].split('@sha256:')[1], 'Redraw the deployed image subtitle.')
        receipt = json.loads(read('docs/evidence/budget-addition-20261021.json'))
        self.assertEqual(facts['verified_date'], receipt['verified_at'].split('T')[0])
        self.assertEqual(facts['worker'], config['name'])
        self.assertEqual(facts['durable_object'], config['durable_objects']['bindings'][0]['class_name'])
        self.assertEqual(facts['container_instances'], config['containers'][0]['max_instances'])
        self.assertEqual(facts['request_logging'], config['observability']['enabled'], 'Redraw the dashed request-logging card.')
        self.assertEqual(facts['r2_bucket'], config['r2_buckets'][0]['bucket_name'])
        worker = read('cloudflare/worker.js')
        self.assertEqual(facts['port'], int(re.search(r'defaultPort = (\d+)', worker).group(1)))
        self.assertEqual(facts['checkpoint_key'], re.search(r"env.STATE.get\('([^']+)'\)", worker).group(1))
        self.assertEqual(facts['private_lifecycle_events'], "await storage.put('lifecycle-events'" in worker)
        self.assertTrue(cloud_runtime._allowed(facts['working_database']))
        self.assertIn("self.db = self.data_dir / 'app.sqlite3'", read('webapp/store.py'))
        for folder in facts['working_files']:
            self.assertTrue(cloud_runtime._allowed(folder + '/example.json'), 'Redraw the files included in a checkpoint.')

    def test_model_and_background_facts(self):
        facts, guards = self.facts, pinned_model_guards()
        self.assertEqual(facts['model'], guards['model'])
        self.assertEqual(facts['provider'], guards['provider'])
        self.assertEqual(facts['reasoning'], guards['thinking_level'])
        self.assertEqual(facts['provider_route'], guards['provider_only'])
        app = read('app_server.py')
        self.assertEqual(facts['background_workers'], int(re.search(r'for index in range\((\d+)\)', app).group(1)), 'Redraw the background-worker card.')
        self.assertEqual(facts['max_inflight'], inspect.signature(RequestCoordinator).parameters['max_inflight'].default)
        self.assertEqual(facts['launch_gap_seconds'], PAUSE_SECONDS)
        self.assertEqual(facts['max_product_views'], int(re.search(r'if len\(prior\) >= (\d+)', read('webapp/store.py')).group(1)))
        transport = read('webapp/transport.py')
        self.assertEqual(facts['strict_json_schema'], "'type': 'json_schema'" in transport and "'strict': True" in transport)
        self.assertEqual(facts['provider_fallback'], "'allow_fallbacks': True" in transport)
        self.assertIn("'allow_fallbacks': False", transport)
        inference = read('webapp/inference.py')
        joint = inference[inference.index('    def _run_multiple('):]
        self.assertEqual(facts['joint_views'], "generate('Comparing product views together', prompt, images + references" in joint)
        self.assertIn('self.store.recover_unfinished', app)
        self.assertIn('source.backup(target)', read('webapp/cloud_runtime.py'))

    def test_trace_and_visible_labels(self):
        facts = self.facts
        receipt = json.loads(read('docs/evidence/worker-repair/hosted-observation.json'))
        self.assertEqual(facts['trace_job'], receipt['job_id'])
        self.assertEqual(receipt['status'], 'completed')
        self.assertIn(facts['trace_photo'], read('docs/timeout-repair-20261021.md'))
        self.assertIn(facts['trace_job'], read('docs/breaker-repair-20261021.md'))
        visible = ' '.join(node.text or '' for node in self.document.findall('{http://www.w3.org/2000/svg}text'))
        for label in [facts['trace_photo'], facts['durable_object'], 'Gemini 3.7 Flash', 'OpenRouter',
                      str(facts['background_workers']) + ' background workers',
                      str(facts['max_inflight']) + ' model calls maximum.',
                      'Launch at least ' + str(facts['launch_gap_seconds']) + 's apart.',
                      facts['release_image_sha256'][:12], '21 October 2026']:
            self.assertIn(label, visible)
        self.assertEqual(self.document.attrib['viewBox'], '0 0 1440 1510')

    def test_png_is_twice_the_svg_size(self):
        png = (DIAGRAM.with_suffix('.png')).read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', png[16:24]), (2880, 3020), 'Render the PNG again at 2x.')


if __name__ == '__main__':
    unittest.main()
