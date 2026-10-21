"""Checkpoint compression retains the archive contents and storage bounds."""
import io
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from webapp import cloud_runtime


class CheckpointCompressionTests(unittest.TestCase):
    def test_snapshot_uses_fast_gzip_and_restores_identical_bytes(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as restored:
            root = Path(folder)
            (root / 'var/media').mkdir(parents=True)
            (root / 'var/runtime/job').mkdir(parents=True)
            (root / 'var/media/photo.jpg').write_bytes(b'\xff\xd8' + bytes(range(256)) * 4 + b'\xff\xd9')
            (root / 'var/runtime/job/ledger.json').write_bytes(b'{"charged_cost_usd":0.12}')
            with sqlite3.connect(root / 'var/app.sqlite3') as database:
                database.execute('CREATE TABLE saved (value TEXT)')
                database.execute("INSERT INTO saved VALUES ('retained')")
            with patch.object(cloud_runtime.tarfile, 'open', wraps=tarfile.open) as opened:
                snapshot = cloud_runtime.snapshot(root)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(opened.call_args.kwargs['mode'], 'w:gz')
            self.assertEqual(opened.call_args.kwargs['compresslevel'], 1)
            with tarfile.open(fileobj=io.BytesIO(snapshot), mode='r:gz') as archive:
                captured = {member.name: archive.extractfile(member).read() for member in archive}
            self.assertEqual(set(captured), {'var/app.sqlite3', 'var/media/photo.jpg',
                                            'var/runtime/job/ledger.json'})
            cloud_runtime.restore(restored, snapshot)
            for name, content in captured.items():
                self.assertEqual((Path(restored) / name).read_bytes(), content)
            for name in ('var/media/photo.jpg', 'var/runtime/job/ledger.json'):
                self.assertEqual(captured[name], (root / name).read_bytes())
            with sqlite3.connect(Path(restored) / 'var/app.sqlite3') as database:
                self.assertEqual(database.execute('SELECT value FROM saved').fetchone(), ('retained',))

    def test_snapshot_and_restore_keep_all_storage_limits(self):
        self.assertEqual(cloud_runtime.MAX_ARCHIVE_BYTES, 100 * 1024 * 1024)
        self.assertEqual(cloud_runtime.MAX_EXPANDED_BYTES, 250 * 1024 * 1024)
        self.assertEqual(cloud_runtime.MAX_FILES, 10000)
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as restored:
            root = Path(folder)
            (root / 'var/media').mkdir(parents=True)
            (root / 'var/media/photo.jpg').write_bytes(bytes(range(256)))
            snapshot = cloud_runtime.snapshot(root)
            for limit, value, message in (
                ('MAX_ARCHIVE_BYTES', 1, 'archive exceeds'),
                ('MAX_EXPANDED_BYTES', 1, 'storage limit'),
                ('MAX_FILES', 0, 'storage limit'),
            ):
                with self.subTest(operation='snapshot', limit=limit), patch.object(cloud_runtime, limit, value):
                    with self.assertRaisesRegex(RuntimeError, message):
                        cloud_runtime.snapshot(root)
            for limit, value, message in (
                ('MAX_ARCHIVE_BYTES', 1, 'archive exceeds'),
                ('MAX_EXPANDED_BYTES', 1, 'expands beyond'),
                ('MAX_FILES', 0, 'unsupported entry'),
            ):
                with self.subTest(operation='restore', limit=limit), patch.object(cloud_runtime, limit, value):
                    with self.assertRaisesRegex(RuntimeError, message):
                        cloud_runtime.restore(restored, snapshot)
                    self.assertFalse((Path(restored) / 'var/media/photo.jpg').exists())


if __name__ == '__main__':
    unittest.main()
