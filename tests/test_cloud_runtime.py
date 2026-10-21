"""Focused checks for bounded cloud state and paid-request persistence."""
import io
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import nullcontext
import json
import urllib.error
from unittest.mock import patch

import app_server
from webapp import cloud_runtime
from webapp.transport import Client


class CloudRuntimeTests(unittest.TestCase):
    def test_state_transport_identifies_the_app(self):
        with patch.dict(os.environ, {'CLOUD_STATE_URL': 'https://demo.example/__state', 'CLOUD_STATE_TOKEN': 'test-token'}), \
                patch('webapp.cloud_runtime.urllib.request.urlopen') as network:
            cloud_runtime._request('GET')
        request = network.call_args.args[0]
        self.assertEqual(request.get_header('User-agent'), 'MultiplierPhotoDemo/1.0')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')

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
                    patch.object(cloud_runtime.time, 'sleep'), \
                    patch('webapp.transport.api_key_for', return_value='test-placeholder'), \
                    patch('webapp.transport.urllib.request.urlopen') as provider:
                with self.assertRaisesRegex(RuntimeError, 'Cloud state could not be saved'):
                    client._paid_call('call', 'call', 'generate', model, b'{}', 'sha',
                        'https://provider.example', .01, lambda result: result, 30)
                provider.assert_not_called()
                self.assertIn('call', client.pending)

    def test_transient_state_put_retries_same_snapshot_with_bounded_backoff(self):
        unavailable = urllib.error.HTTPError('https://private.invalid', 503, 'Unavailable', {}, None)
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', Path('/unused')), \
                patch.object(cloud_runtime, 'snapshot', return_value=b'one-immutable-snapshot') as snapshot, \
                patch.object(cloud_runtime, '_request', side_effect=[unavailable, OSError('network'), nullcontext(SimpleNamespace(status=200))]) as write, \
                patch.object(cloud_runtime.time, 'sleep') as wait:
            cloud_runtime.checkpoint()
        snapshot.assert_called_once()
        self.assertEqual(write.call_count, 3)
        self.assertTrue(all(call.args == ('PUT', b'one-immutable-snapshot') for call in write.call_args_list))
        self.assertEqual([call.args[0] for call in wait.call_args_list], [1, 2])
        self.assertTrue(all(0 < call.kwargs['timeout'] <= 15 for call in write.call_args_list))

    def test_state_retry_uses_remaining_deadline_instead_of_three_long_timeouts(self):
        clock = [0.0]
        timeouts = []
        def write(method, data, *, timeout):
            timeouts.append(timeout)
            clock[0] += timeout
            raise TimeoutError('storage timeout')
        def wait(delay):
            clock[0] += delay
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', Path('/unused')), \
                patch.object(cloud_runtime, 'snapshot', return_value=b'snapshot'), \
                patch.object(cloud_runtime, '_request', side_effect=write), \
                patch.object(cloud_runtime.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(cloud_runtime.time, 'sleep', side_effect=wait):
            with self.assertRaises(cloud_runtime.CloudStateError):
                cloud_runtime.checkpoint()
        self.assertEqual(timeouts, [15, 14])
        self.assertEqual(clock[0], 30)

    def test_state_retry_stops_after_three_attempts_and_retains_safe_reason(self):
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', Path('/unused')), \
                patch.object(cloud_runtime, 'snapshot', return_value=b'snapshot'), \
                patch.object(cloud_runtime, '_request', side_effect=urllib.error.URLError('private token must not appear')) as write, \
                patch.object(cloud_runtime.time, 'sleep') as wait:
            with self.assertRaises(cloud_runtime.CloudStateError) as raised:
                cloud_runtime.checkpoint()
        self.assertEqual(write.call_count, 3)
        self.assertEqual(wait.call_count, 2)
        self.assertIn('URLError', str(raised.exception))
        self.assertNotIn('private token', str(raised.exception))

    def test_permanent_state_errors_and_snapshot_failures_are_not_retried(self):
        for code in (400, 401, 403, 413):
            with self.subTest(code=code), patch.dict(os.environ, {'CLOUD_MODE': '1'}), \
                    patch.object(cloud_runtime, '_root', Path('/unused')), \
                    patch.object(cloud_runtime, 'snapshot', return_value=b'snapshot'), \
                    patch.object(cloud_runtime, '_request', side_effect=urllib.error.HTTPError('', code, '', {}, None)) as write, \
                    patch.object(cloud_runtime.time, 'sleep') as wait:
                with self.assertRaisesRegex(cloud_runtime.CloudStateError, 'HTTP ' + str(code)):
                    cloud_runtime.checkpoint()
                self.assertEqual(write.call_count, 1)
                wait.assert_not_called()
        with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', Path('/unused')), \
                patch.object(cloud_runtime, 'snapshot', side_effect=RuntimeError('Storage bounds exceeded')), \
                patch.object(cloud_runtime, '_request') as write, patch.object(cloud_runtime.time, 'sleep') as wait:
            with self.assertRaisesRegex(cloud_runtime.CloudStateError, 'snapshot failed'):
                cloud_runtime.checkpoint()
            write.assert_not_called()
            wait.assert_not_called()

    def test_recovered_reservation_checkpoint_precedes_exactly_one_paid_call(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            client = Client({'budget': {'usd_inr': 100, 'stage_max_inr': 10, 'total_max_inr': 10,
                                       'prior_accounted_inr': 0}, 'models': {}}, root, root / 'var/runtime/job')
            model = {'model': 'test', 'provider': 'openrouter', 'input_usd_per_million': 1,
                     'output_usd_per_million': 1, 'input_token_bound': 1000}
            def provider(request, timeout):
                self.assertEqual(write.call_count, 3)
                self.assertTrue(client.pending)
                return io.BytesIO(json.dumps({'usage': {'cost': .001}, 'ok': True}).encode())
            with patch.dict(os.environ, {'CLOUD_MODE': '1'}), patch.object(cloud_runtime, '_root', root), \
                    patch.object(cloud_runtime, '_request', side_effect=[OSError('offline'), OSError('offline'),
                        nullcontext(SimpleNamespace(status=200)), nullcontext(SimpleNamespace(status=200))]) as write, \
                    patch.object(cloud_runtime.time, 'sleep'), patch('webapp.transport.api_key_for', return_value='test'), \
                    patch('webapp.transport.urllib.request.urlopen', side_effect=provider) as paid:
                result = client._paid_call('call', 'call', 'generate', model, b'{}', 'sha',
                                          'https://provider.example', .01, lambda value: value, 30)
            self.assertTrue(result['ok'])
            self.assertEqual(paid.call_count, 1)
            self.assertEqual(write.call_count, 4)
            self.assertEqual(client.pending, {})

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
