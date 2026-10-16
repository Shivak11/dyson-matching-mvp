import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('private_packaging', Path(__file__).resolve().parents[1] / 'tools/build_private_app.py')
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class PrivatePackagingTests(unittest.TestCase):
    def fixture(self, root):
        for name in (*packaging.FIXED_FILES, 'webapp/__init__.py', 'webapp/inference.py'):
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('# runtime\n')
        for name in ('.env', 'var/app.sqlite3', 'data/test/answers.json', 'out/predictions.json', 'web/report.html', 'data/catalog/photo.jpg'):
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('SENSITIVE_SENTINEL')

    def test_archive_allowlist_excludes_runtime_and_research(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'source'; root.mkdir(); self.fixture(root)
            target = Path(d) / 'delivery'
            with patch.object(packaging.subprocess, 'check_output', return_value='a' * 40):
                receipt = packaging.build(root, target)
            with zipfile.ZipFile(target.with_name('delivery-code.zip')) as z:
                self.assertEqual(set(z.namelist()), set(packaging.FIXED_FILES) | {'webapp/__init__.py', 'webapp/inference.py'})
                self.assertTrue(all(b'SENSITIVE_SENTINEL' not in z.read(n) for n in z.namelist()))
            self.assertFalse(receipt['data_in_archive'])
            with self.assertRaises(ValueError):
                packaging.build(root, target)
            self.assertEqual((root / '.env').read_text(), 'SENSITIVE_SENTINEL')

    def test_local_seed_has_only_manufacturer_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'source'; source.mkdir(); self.fixture(source)
            cards = {'products': {'family': {'images': [{'file': 'data/catalog/photo.jpg'}]}}}
            (source / 'data/reference_cards_v2.json').write_text(json.dumps(cards))
            model = {'provider': 'openrouter', 'model': 'fixed-model', 'threshold': 90}
            (source / 'data/pipeline_v2_recovery_config.json').write_text(json.dumps({'models': {'flash37high': model}, 'frozen_files': ['DO_NOT_COPY']}))
            destination = Path(d) / 'local'
            result = packaging.prepare_inputs(source, destination)
            self.assertEqual(result['manufacturer_images'], 1)
            self.assertEqual(json.loads((destination / 'runtime_config.json').read_text()), {'model': model})
            self.assertEqual(json.loads((destination / 'var/catalogue-seed/reference_cards.json').read_text()), cards)
            self.assertFalse((destination / 'data/test').exists())
            self.assertFalse((destination / '.env').exists())
            cards['products']['family']['images'][0]['file'] = '../outside.jpg'
            (source / 'data/reference_cards_v2.json').write_text(json.dumps(cards))
            with self.assertRaises(ValueError):
                packaging.prepare_inputs(source, destination)

    def test_symlink_runtime_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'source'; source.mkdir(); self.fixture(source)
            (source / 'app_server.py').unlink()
            (source / 'app_server.py').symlink_to(source / '.env')
            with self.assertRaises(ValueError):
                packaging.runtime_files(source)
