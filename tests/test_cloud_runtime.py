"""Focused checks for bounded cloud state and paid-request persistence."""
import io
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app_server
from webapp import cloud_runtime
from webapp.transport import Client


class CloudRuntimeTests(unittest.TestCase):
    def test_restore_rejects_traversal_and_links_before_writing(self):
        for name, link in [('var/media/../../escape', False), ('var/media/link', True)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                output = io.BytesIO()
                with tarfile.open(fileobj=output, mode='w:gz') as archive:
                    good = tarfile.TarInfo('var/media/good.jpg')
                    good.size = 4
                    archive.addfile(good, io.BytesIO(b'good'))
                    bad = tarfile.TarInfo(name)
                    if link:
                        bad.type = tarfile.SYMTYPE
                        bad.linkname = '/tmp/escape'
                    archive.addfile(bad)
                with self.assertRaises(RuntimeError):
                    cloud_runtime.restore(folder, output.getvalue())
                self.assertFalse((Path(folder) / 'var/media/good.jpg').exists())

    def test_snapshot_restores_committed_sqlite_wal_and_runtime_files(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as restored:
            root = Path(folder)
            (root / 'var/runtime/job').mkdir(parents=True)
            (root / 'var/runtime/job/inflight.json').write_text('{"call": {"reserved_cost_usd": 0.1}}')
            (root / 'var/worker.lock').touch()
            (root / 'var/runtime/job/ignore.tmp').write_text('partial')
            with sqlite3.connect(root / 'var/app.sqlite3') as connection:
                connection.execute('PRAGMA journal_mode=WAL')
                connection.execute('CREATE TABLE test (value TEXT)')
                connection.execute("INSERT INTO test VALUES ('saved')")
                connection.commit()
                archive = cloud_runtime.snapshot(root)
            cloud_runtime.restore(restored, archive)
            with sqlite3.connect(Path(restored) / 'var/app.sqlite3') as connection:
                self.assertEqual(connection.execute('SELECT value FROM test').fetchone()[0], 'saved')
            self.assertTrue((Path(restored) / 'var/runtime/job/inflight.json').is_file())
            self.assertFalse((Path(restored) / 'var/worker.lock').exists())
            self.assertFalse((Path(restored) / 'var/runtime/job/ignore.tmp').exists())

    def test_failed_reservation_checkpoint_prevents_paid_network_call(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = {'budget': {'usd_inr': 100, 'stage_max_inr': 10,
                'total_max_inr': 10, 'prior_accounted_inr': 0}, 'models': {}}
            client = Client(config, root, root / 'var/runtime/job')
            model = {'model': 'test', 'provider': 'openrouter'}
            with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', root), \
                    patch.object(cloud_runtime, '_request', side_effect=OSError('offline')), \
                    patch('webapp.transport.api_key_for', return_value='test-placeholder'), \
                    patch('webapp.transport.urllib.request.urlopen') as provider:
                with self.assertRaisesRegex(RuntimeError, 'Cloud state could not be saved'):
                    client._paid_call('call', 'call', 'generate', model, b'{}', 'sha',
                        'https://provider.example', .01, lambda result: result, 30)
                provider.assert_not_called()
                self.assertIn('call', client.pending)

    def test_cloud_gateway_token_is_required_before_local_host_checks(self):
        handler = object.__new__(app_server.Handler)
        handler.headers = {'Host': 'localhost:8080'}
        handler.server = SimpleNamespace(server_address=('0.0.0.0', 8080))
        replies = []
        handler.send_json = lambda status, body: replies.append(status)
        with patch.dict(os.environ, {'CLOUD_MODE': '1', 'CLOUD_CONTAINER_TOKEN': 'test-token'}):
            self.assertFalse(handler._security())
            self.assertEqual(replies, [403])
            handler.headers['X-Container-Token'] = 'test-token'
            self.assertTrue(handler._security())


if __name__ == '__main__':
    unittest.main()
