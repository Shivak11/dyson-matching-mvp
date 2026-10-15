"""Apply recorded native presence reviews and render the reviewed photo list."""
import hashlib
import json
import math
from collections import Counter

from PIL import Image, ImageDraw, ImageFont, ImageOps
from collect_review_photos import ROOT, check_files

NAMES = {
    'dyson_v8_absolute': 'V8 Absolute',
    'dyson_v12_detect_slim': 'V12 Detect Slim',
    'dyson_v15_detect': 'V15 Detect',
    'dyson_v16_piston_animal': 'V16 Piston Animal',
    'dyson_big_ball': 'Big Ball',
    'dyson_wash_g1': 'WashG1',
    'NONCAT_dyson_v11': 'V11 (outside catalogue)',
    'NONCAT_dyson_gen5detect': 'Gen5detect (outside catalogue)',
    'NONCAT_shark_stratos': 'Shark Stratos (outside catalogue)',
}


def finalize():
    candidates = json.loads((ROOT / 'data/test/review_candidates.json').read_text())
    reviews = json.loads((ROOT / 'data/test/presence_review.json').read_text())
    check_files(candidates)
    assert len(reviews) == len(candidates)
    by_id = {r['image_id']: r for r in reviews}
    assert set(by_id) == {r['image_id'] for r in candidates}
    labelled, demos, excluded = [], [], []
    for row in candidates:
        review = by_id[row['image_id']]
        assert isinstance(review['product_visible'], bool)
        assert review['review_method'] == 'native_image_viewing'
        row = dict(row, presence_review=review)
        row['label'] = row['labels'][0] if len(row['labels']) == 1 else 'multi_product' if row['labels'] else 'unlabelled_display'
        if not review['product_visible']:
            excluded.append(row)
        elif row['evaluation_role'] == 'unlabelled_demo':
            demos.append(row)
        else:
            labelled.append(row)
    assert 30 <= len(labelled) <= 60
    assert set(NAMES) == {label for row in labelled for label in row['labels']}
    for name, rows in [('test_manifest.json', labelled), ('demo_manifest.json', demos), ('excluded_photos.json', excluded)]:
        (ROOT / 'data/test' / name).write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n')
    counts = Counter(row['labels'][0] for row in labelled if len(row['labels']) == 1)
    summary = {'downloaded': len(candidates), 'labelled_photos': len(labelled), 'single_product_photos': sum(counts.values()),
               'labelled_multi_product_photos': sum(len(r['labels']) > 1 for r in labelled), 'unlabelled_demo_photos': len(demos),
               'dropped_no_product_visible': len(excluded), 'single_product_counts': dict(counts),
               'labelled_source_groups': len({r['source_group'] for r in labelled}),
               'downloaded_photo_bytes': sum(r['bytes'] for r in candidates), 'paid_matching_calls': 0}
    tile_w, tile_h, columns, header = 300, 252, 6, 82
    rows = labelled + demos
    sheet = Image.new('RGB', (columns * tile_w, header + math.ceil(len(rows) / columns) * tile_h), 'white')
    draw = ImageDraw.Draw(sheet)
    font_path = '/System/Library/Fonts/Supplemental/Arial.ttf'
    font = ImageFont.truetype(font_path, 17)
    heading = ImageFont.truetype(font_path, 27)
    draw.text((14, 10), 'Dyson test photos', fill='black', font=heading)
    draw.text((14, 48), f"{len(labelled)} labelled photos; {len(demos)} unlabelled demo; {len(excluded)} photos excluded because no machine was visible.", fill='black', font=font)
    for i, row in enumerate(rows):
        x, y = i % columns * tile_w, header + i // columns * tile_h
        with Image.open(ROOT / row['file']) as source:
            image = ImageOps.contain(ImageOps.exif_transpose(source).convert('RGB'), (tile_w - 12, 198))
        sheet.paste(image, (x + (tile_w - image.width) // 2, y + (198 - image.height) // 2))
        names = ' + '.join(NAMES[label] for label in row['labels']) if row['labels'] else 'Display scene; demo only'
        draw.text((x + 7, y + 204), row['image_id'], fill='black', font=font)
        draw.text((x + 7, y + 226), names, fill='black', font=font)
    output = ROOT / 'out/test_contact_sheet.jpg'
    sheet.save(output, quality=92)
    summary['contact_sheet_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary['contact_sheet_size'] = list(sheet.size)
    (ROOT / 'out/test_set_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    finalize()
