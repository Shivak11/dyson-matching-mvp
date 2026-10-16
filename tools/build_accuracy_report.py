"""Build a portable HTML report from the preserved, independently audited results."""
import base64
import html
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def name(value):
    names = {key: row['name'] for key, row in read('data/reference_cards_v2.json')['products'].items()}
    return names.get(str(value).removeprefix('NONCAT_'), str(value).replace('_', ' '))


def esc(value):
    return html.escape(str(value), quote=True)


def thumbnail(file):
    with Image.open(ROOT / file) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
        image.thumbnail((640, 440))
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=78)
    return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()


def build():
    baseline = read('out/baseline-qwen/summary.json')
    revised = read('out/pipeline_v2_recovery/scoreboard.json')
    group = revised['all_photos']['groups'][0]
    comparison = read('out/pipeline/slow_comparison/scoreboard.json')
    failures = read('out/failure_recovery_completion/scoreboard.json')
    ocr = read('out/targeted_ocr/interpretation.json')
    manifest = read('data/test/test_manifest.json')
    assert len(manifest) == 58 and group['metrics']['correct_total'] == 37
    assert group['metrics']['confidently_wrong_count'] == 5
    results = {row['image_id']: row for row in group['per_photo']}
    detections = read('out/pipeline_v2_full/detections.json')
    changes = {row['image_id']: row for row in failures['summary']['groups'][0]['per_photo']}
    rows = []
    for photo in manifest:
        pid = photo['image_id']
        multi = len(photo['labels']) > 1
        result = results.get(pid, {})
        outcome = 'Multiple models' if multi else ('Correct' if result.get('correct') else 'Not sure' if result.get('status') == 'not_sure' else 'Confidently wrong')
        answer = 'V12 Detect Slim and V15 Detect' if multi else name(result.get('product')) if result.get('product') else 'Not in catalogue' if result.get('status') == 'not_in_catalogue' else 'Not sure'
        boxes = ''.join(f'<rect x="{b[1]}" y="{b[0]}" width="{b[3]-b[1]}" height="{b[2]-b[0]}"/>' for machine in detections.get(pid, []) if (b := machine.get('box_2d')))
        evidence = ''.join(f'<li>{esc(text)}</li>' for text in result.get('evidence', []))
        missing = ''.join(f'<li>{esc(text)}</li>' for text in result.get('missing_evidence', []))
        later = changes.get(pid)
        later_text = ''
        if later:
            decision = name(later.get('product')) if later.get('product') else 'Not sure' if later.get('status') == 'not_sure' else 'Not in catalogue'
            later_text = f'<p><strong>Selected-failure round:</strong> {esc(decision)}. {"Correct" if later.get("correct") else "Not sure" if later.get("status")=="not_sure" else "Confidently wrong"}.</p>'
        css = 'wrong' if outcome == 'Confidently wrong' else 'unsure' if outcome == 'Not sure' else 'correct'
        rows.append(f'''<article class="photo" data-outcome="{esc(outcome)}"><div class="picture"><img loading="lazy" src="{thumbnail(photo['file'])}" alt="Test photograph {pid}"><svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Detected machine regions">{boxes}</svg></div>
        <div><h3>{pid} · <span class="{css}">{outcome}</span></h3><p><strong>Source label:</strong> {esc(', '.join(name(v) for v in photo['labels']))}</p><p><strong>Gemini answer:</strong> {esc(answer)}</p>{'<p>The model set is correct; per-box identity was not source-labelled.</p>' if multi else ''}
        <details><summary>Evidence and source</summary><ul>{evidence}</ul>{'<p>Missing details:</p><ul>'+missing+'</ul>' if missing else ''}{later_text}<p><a href="{esc(photo['source_url'])}">{esc(photo['source_title'])}</a></p><p>{esc(photo['label_basis'])}</p></details></div></article>''')
    study = read('out/pipeline/study.json')
    qwen = next(r for r in study['fixed_subset']['groups'] if r['model'] == 'qwen38max' and r['variant'] == 'telling_details')
    qwen_cost = next(r for r in study['fixed_subset_costs']['models'] if r['model'] == 'qwen38max')
    assert qwen['complete_photo_count'] == 16
    model_rows = ''.join(f'<tr><th>{esc({"flash37high":"Gemini 3.7 Flash high","solhigh":"GPT-6.1 Sol high","flash37high+solhigh":"Agreement between both"}[r["model"]])}</th><td>{r["correct"]}/15</td><td class="wrong">{r["confidently_wrong"]}</td><td>{r["not_sure"]}</td><td>₹{r["cost_per_completed_original_photo_inr"]:.2f}</td></tr>' for r in comparison['scoreboard'])
    model_rows += f'<tr><th>Qwen 3.8 Max</th><td>{qwen["metrics"]["correct_total"]}/15</td><td class="wrong">{qwen["metrics"]["confidently_wrong_count"]}</td><td>{qwen["metrics"]["not_sure_count"]}</td><td>₹{qwen_cost["cost_per_original_photo_inr"]:.2f}</td></tr>'
    document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dyson photo matching results</title><style>
    :root{color-scheme:light;--ink:#20251f;--muted:#596358;--line:#d9ddd6;--blue:#244dda;--wrong:#a62723;--paper:#f5f6f2}*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1160px;margin:auto;padding:42px 28px}h1{font-size:38px;line-height:1.15;letter-spacing:-1px;margin:0 0 14px}h2{font-size:24px;margin:32px 0 14px}h3{font-size:18px;margin:0 0 8px}p{margin:10px 0}a{color:var(--blue)}table{border-collapse:collapse;width:100%;background:white;font-size:15px}td,th{text-align:left;padding:13px;border-bottom:1px solid var(--line)}th{font-weight:600}.table-scroll{overflow-x:auto}.wrong{color:var(--wrong);font-weight:650}.correct{color:#176341}.unsure{color:#805a17}.numbers{display:flex;gap:32px;margin:24px 0;flex-wrap:wrap}.numbers strong{font-size:42px;line-height:1;display:block}.numbers span{display:block;margin-top:8px}.photo{display:grid;grid-template-columns:320px 1fr;gap:24px;background:white;border:1px solid var(--line);padding:18px;margin:14px 0;break-inside:avoid}.picture{position:relative;align-self:start}.picture img{width:100%;display:block}.picture svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.picture rect{stroke:#2457d7;stroke-width:4;fill:none;vector-effect:non-scaling-stroke}details{margin:10px 0}summary{cursor:pointer;color:var(--blue);min-height:32px}button,select{font:inherit;padding:9px 14px;border:1px solid #969d92;background:white;border-radius:5px;cursor:pointer}button:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #6385fb;outline-offset:3px}.controls{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}.note{color:var(--muted);font-size:14px}ul{padding-left:20px}footer{margin-top:24px;color:var(--muted)}@media(max-width:650px){main{padding:24px 18px}h1{font-size:30px}.photo{grid-template-columns:1fr}.numbers{gap:24px}.numbers strong{font-size:34px}}@media print{body{background:white}main{padding:0}.controls,button{display:none}h1{font-size:26px}h2{font-size:20px;margin-top:20px}.numbers strong{font-size:30px}.photo{grid-template-columns:230px 1fr}a{color:inherit}}
    </style></head><body><main><div class="controls"><h1>Dyson photo matching results</h1><button id="print-report">Print report</button></div>
    <p>Gemini correctly resolved 37 of 57 single-model photographs. Five answers were confidently wrong and 15 were not sure.</p><div class="numbers"><div><strong>64.9%</strong><span>Correct overall</span></div><div class="wrong"><strong>5</strong><span>Confidently wrong</span></div><div><strong>15</strong><span>Not sure</span></div><div><strong>₹5.21</strong><span>Per photo, revised Gemini run</span></div></div>
    <h2>Whole-photo scoring and the revised pipeline</h2><div class="table-scroll"><table><thead><tr><th>Approach</th><th>Correct</th><th>Confidently wrong</th><th>Not sure</th><th>Cost/photo</th></tr></thead><tbody><tr><th>Whole photo, one reference; Qwen 3.7 Flash, threshold 90</th><td>23/57</td><td class="wrong">12</td><td>5</td><td>₹0.05</td></tr><tr><th>Object grouping and manufacturer evidence; Gemini 3.7 Flash high</th><td>37/57</td><td class="wrong">5</td><td>15</td><td>₹5.21</td></tr></tbody></table></div>
    <p>The baseline reproduces the client's scoring method with Qwen after the Gemini Argon baseline was stopped for cost. This comparison changes both the model and the method. The Gemini run correctly matched 28 catalogue photos and rejected nine outside-catalogue photos. It also returned the correct V12/V15 set in the separate two-model photograph.</p>
    <p class="note">The revised run cost is divided by all 58 photographs. It excludes earlier shared detection and embedding work; including that work is about ₹5.36/photo. These are public development photographs with source-derived labels. Client-store holdout accuracy has not been measured.</p>
    <h2>Models on the same 15 photographs</h2><div class="table-scroll"><table><thead><tr><th>Model</th><th>Correct</th><th>Confidently wrong</th><th>Not sure</th><th>Cost/photo</th></tr></thead><tbody>MODEL_ROWS</tbody></table></div>
    <p>Requiring agreement removed the wrong answer in this small comparison, while leaving nine photographs unresolved. On these same 15 photos, the later Gemini workflow returned 10 correct, two confidently wrong and three not sure, regressing from the earlier 11 correct, one wrong and three not sure. Gemini, Sol and their agreement returned the correct model set in the additional two-model photograph. Costs include shared pipeline work and retained failed-call reserves where recorded.</p>
    <p>In the earlier paired Qwen 3.7 Flash test, adding telling-details cards changed nine correct, four confidently wrong and two not sure to eight correct, two confidently wrong and five not sure. The cards reduced wrong confident answers while increasing unresolved photos; this is not evidence of a universal accuracy gain.</p><h2>What the recovery rounds changed</h2><p>Comparing aligned manufacturer views recovered six of the original 20 failures, introduced one confidently wrong answer and left 13 not sure. Two of three previously correct controls stayed correct; one became not sure. This was a selected-failure experiment, not a fresh full-set score. Its cost was about ₹8.40 per selected photo, including the separate control retry.</p>
    <p>OpenRouter's Mistral OCR checked P054 and the 13 remaining unsure photos. It found no usable model or part identifiers and recovered no identities. Reported cost was ₹0.19/photo; an additional parser-fee reserve remains in the spending ledger.</p>
    <p>P054 remains a recorded failure: the source identifies Gen5detect, while the aligned-reference round returned V16 at 95. The shared controls, screen and filter were insufficient to distinguish them. The app therefore shows supporting and missing details beside its qualitative confidence. That confidence is a model assessment, not a measured probability.</p>
    <h2>Every test photograph</h2><div class="controls"><p>Original full-set Gemini decisions are preserved below; recovery-round changes appear inside each photo's details.</p><label>Show <select id="filter"><option>All photographs</option><option>Confidently wrong</option><option>Not sure</option><option>Correct</option><option>Multiple models</option></select></label></div><section id="photos">PHOTOS</section><footer>Results recorded on 15–16 October 2026. Catalogue: six Dyson model families, with V11, Gen5detect and Shark examples outside the catalogue. Three candidate frames without a visible machine were dropped during native image review.</footer></main><script>document.querySelector('#print-report').addEventListener('click',()=>window.print());document.querySelector('#filter').addEventListener('change',e=>{for(const row of document.querySelectorAll('.photo'))row.hidden=e.target.value!=='All photographs'&&row.dataset.outcome!==e.target.value;});</script></body></html>'''
    document = document.replace('MODEL_ROWS', model_rows).replace('PHOTOS', '\n'.join(rows))
    assert document.count('<article class="photo"') == 58
    destination = ROOT / 'web/report.html'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(document)
    print(f'{destination}: 58 photos; 37 correct, 5 confidently wrong, 15 unsure; preserved source results')
    return destination


if __name__ == '__main__':
    build()
