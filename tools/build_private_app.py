#!/usr/bin/env python3
"""Build an allowlisted code archive; prepare manufacturer inputs locally only."""
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_FILES = ('app_server.py', 'requirements.txt', 'web/index.html', 'web/app.js', 'web/style.css')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_files(source):
    source = Path(source).resolve()
    files = [source / name for name in FIXED_FILES]
    files += sorted((source / 'webapp').glob('*.py'))
    if not files or not (source / 'webapp/__init__.py').is_file():
        raise ValueError('The runtime package is missing.')
    for path in files:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError('Runtime source must be a contained regular file: ' + path.name)
    return files


def prepare_inputs(source, destination):
    """Copy manufacturer material and the selected model entry without test data."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    cards_file = source / 'data/reference_cards_v2.json'
    model_file = source / 'data/pipeline_v2_recovery_config.json'
    cards = json.loads(cards_file.read_text())
    model = json.loads(model_file.read_text())['models']['flash37high']
    seed = destination / 'var/catalogue-seed'
    seed.mkdir(parents=True, exist_ok=True, mode=0o700)
    copied = []
    for card in cards['products'].values():
        for image in card['images']:
            relative = Path(image['file'])
            original = (source / relative).resolve()
            target = (seed / relative).resolve()
            if relative.is_absolute() or not original.is_relative_to(source / 'data/catalog') or not target.is_relative_to(seed):
                raise ValueError('Manufacturer images must stay inside the catalogue folders.')
            if original.is_symlink() or not original.is_file():
                raise ValueError('A manufacturer reference is missing.')
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(original, target)
            target.chmod(0o600)
            copied.append(target)
    seed_file = seed / 'reference_cards.json'
    seed_file.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + '\n')
    seed_file.chmod(0o600)
    config_file = destination / 'runtime_config.json'
    config_file.write_text(json.dumps({'model': model}, ensure_ascii=False, indent=2) + '\n')
    config_file.chmod(0o600)
    return {'manufacturer_images': len(copied), 'seed_sha256': digest(seed_file), 'runtime_config_sha256': digest(config_file)}


def build(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source.is_relative_to(destination):
        raise ValueError('Choose a separate output folder.')
    files = runtime_files(source)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Refuse a reused output containing data; never silently package a dirty folder.
    if any(destination.iterdir()):
        raise ValueError('Use an empty output folder; existing files were kept.')
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(path, target)
    archive = destination.with_name(destination.name + '-code.zip')
    names = []
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for path in files:
            name = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            zipped.writestr(info, path.read_bytes())
            names.append(name)
    receipt = {'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
               'code_files': {str(p.relative_to(source)): digest(p) for p in files},
               'archive_sha256': digest(archive), 'archive_files': names,
               'data_in_archive': False, 'credentials_in_archive': False}
    destination.with_name(destination.name + '-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-catalogue', action='store_true', help='Prepare manufacturer-only inputs locally after creating the code-only archive.')
    parser.add_argument('--inputs-only', action='store_true', help='Prepare inputs in an existing local runtime without copying code.')
    args = parser.parse_args()
    if args.inputs_only:
        if not args.prepare_catalogue:
            parser.error('--inputs-only requires --prepare-catalogue')
        receipt = prepare_inputs(args.source, args.output)
    else:
        receipt = build(args.source, args.output)
        if args.prepare_catalogue:
            receipt['local_inputs'] = prepare_inputs(args.source, args.output)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
