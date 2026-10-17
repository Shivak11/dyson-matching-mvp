"""Private, bounded state checkpoints for the single-container demonstration."""
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

LOCK = threading.RLock()
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 250 * 1024 * 1024
MAX_FILES = 10000
_root = None


def enabled():
    return os.environ.get('CLOUD_MODE') == '1'


def _request(method, data=None):
    url = os.environ.get('CLOUD_STATE_URL', '')
    token = os.environ.get('CLOUD_STATE_TOKEN', '')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path != '/__state' or parsed.query or parsed.fragment or parsed.username or not token:
        raise RuntimeError('Cloud state configuration is incomplete.')
    request = urllib.request.Request(url, data=data, method=method,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/gzip',
                 'User-Agent': 'MultiplierPhotoDemo/1.0'})
    return urllib.request.urlopen(request, timeout=90)


def _allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '\\' in name or any(part in ('..', '.') for part in name.split('/')):
        return False
    parts = path.parts
    if len(parts) < 2 or parts[0] != 'var':
        return False
    if any(part.endswith(('.tmp', '.lock', '-wal', '-shm')) for part in parts):
        return False
    return parts == ('var', 'app.sqlite3') or (parts[1] in ('media', 'jobs', 'runtime') and len(parts) >= 3)


def restore(root, archive):
    """Validate the complete archive before replacing any runtime file."""
    root = Path(root).resolve()
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise RuntimeError('Cloud state archive exceeds the demo limit.')
    with tempfile.TemporaryDirectory(prefix='dyson-restore-') as temporary:
        staging = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as source:
            total = 0
            seen = set()
            for number, member in enumerate(source):
                if number >= MAX_FILES or not member.isfile() or not _allowed(member.name) or member.name in seen:
                    raise RuntimeError('Cloud state archive contains an unsupported entry.')
                seen.add(member.name)
                total += member.size
                if member.size < 0 or total > MAX_EXPANDED_BYTES:
                    raise RuntimeError('Cloud state archive expands beyond the demo limit.')
                target = staging / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as content, target.open('wb') as output:
                    shutil.copyfileobj(content, output)
                target.chmod(0o600)
        for name in seen:
            target = root / name
            # Existing image layers and seed files cannot redirect state extraction.
            if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != root and parent.is_relative_to(root)):
                raise RuntimeError('Cloud state destination contains a symbolic link.')
        for name in seen:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.replace(staging / name, target)


def configure(root):
    global _root
    if not enabled():
        return
    if not os.environ.get('CLOUD_CONTAINER_TOKEN'):
        raise RuntimeError('Cloud gateway configuration is incomplete.')
    with LOCK:
        _root = Path(root).resolve()
        try:
            with _request('GET') as response:
                archive = response.read(MAX_ARCHIVE_BYTES + 1)
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code == 404:
                return
            raise RuntimeError('Cloud state could not be restored.') from None
        restore(_root, archive)


def snapshot(root):
    """Take a SQLite backup rather than copying a live WAL database."""
    root = Path(root).resolve()
    with LOCK, tempfile.TemporaryDirectory(prefix='dyson-checkpoint-') as temporary:
        backup = Path(temporary) / 'app.sqlite3'
        database = root / 'var/app.sqlite3'
        if database.exists():
            with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
                source.backup(target)
        output = io.BytesIO()
        total = 0
        count = 0
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            for path in sorted((root / 'var').rglob('*')):
                name = path.relative_to(root).as_posix()
                if path.is_symlink():
                    raise RuntimeError('Cloud state contains an unsupported symbolic link.')
                if not path.is_file() or not _allowed(name):
                    continue
                source = backup if path == database else path
                total += source.stat().st_size
                count += 1
                if total > MAX_EXPANDED_BYTES or count > MAX_FILES:
                    raise RuntimeError('Cloud state exceeds the demo storage limit.')
                archive.add(source, arcname=name, recursive=False)
        if output.tell() > MAX_ARCHIVE_BYTES:
            raise RuntimeError('Cloud state archive exceeds the demo limit.')
        return output.getvalue()


def checkpoint():
    if not enabled():
        return
    with LOCK:
        if _root is None:
            raise RuntimeError('Cloud state has not been configured.')
        try:
            with _request('PUT', snapshot(_root)) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError('Cloud state could not be saved.')
        except Exception:
            raise RuntimeError('Cloud state could not be saved. No further paid request can start until storage is available.') from None
