"""Download the explicitly sourced photo list without altering its image bytes."""
import hashlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/review_photo_sources.json'
MANIFEST = ROOT / 'data/test/review_candidates.json'


def validate_sources(rows):
    ids = [r['image_id'] for r in rows]
    assert len(ids) == len(set(ids)), 'Duplicate image IDs'
    for row in rows:
        for field in ('source_url', 'source_title', 'label_basis', 'image_url'):
            assert isinstance(row[field], str) and row[field].strip(), (row['image_id'], field)
        assert row['source_url'].startswith('https://')
        assert row['image_url'].startswith('https://')
        assert row['labels'] or row['evaluation_role'] == 'unlabelled_demo'


def download(row):
    row = dict(row)
    path = ROOT / 'data/test/review_photos' / (row['image_id'] + '.jpg')
    try:
        if path.exists():
            payload = path.read_bytes()
        else:
            with urlopen(Request(row['image_url'], headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
                payload = response.read(10_000_001)
        assert len(payload) <= 10_000_000, 'Photo exceeds 10 MB'
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            row['width'], row['height'] = image.size
            assert image.format == 'JPEG', 'Expected JPEG; preserve extension correctly before proceeding'
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(payload)
        row.update(file=str(path.relative_to(ROOT)), sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
        return row, None
    except Exception as error:
        return None, {'image_id': row['image_id'], 'image_url': row['image_url'], 'error': str(error)}


def check_files(rows):
    validate_sources(rows)
    hashes = set()
    catalog_hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'data/catalog').glob('*/*')}
    for row in rows:
        payload = (ROOT / row['file']).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        assert digest == row['sha256'], row['image_id']
        assert digest not in hashes, ('Duplicate test photo', row['image_id'])
        assert digest not in catalog_hashes, ('Catalogue duplicate', row['image_id'])
        hashes.add(digest)
        with Image.open(io.BytesIO(payload)) as image:
            assert image.size == (row['width'], row['height'])
    assert sum(r['bytes'] for r in rows) < 100_000_000


if __name__ == '__main__':
    if '--check' in sys.argv:
        rows = json.loads(MANIFEST.read_text())
        check_files(rows)
        print(f"Verified {len(rows)} photo files and source records")
    else:
        rows = json.loads(SOURCE.read_text())
        validate_sources(rows)
        results = list(ThreadPoolExecutor(max_workers=6).map(download, rows))
        photos = [r for r, error in results if r]
        errors = [error for r, error in results if error]
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(photos, indent=2, ensure_ascii=False) + '\n')
        (ROOT / 'out/review_download_failures.json').write_text(json.dumps(errors, indent=2) + '\n')
        check_files(photos)
        print(json.dumps({'downloaded': len(photos), 'failed': len(errors), 'bytes': sum(r['bytes'] for r in photos)}))
        if errors:
            sys.exit(1)
