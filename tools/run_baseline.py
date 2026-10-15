"""Run the frozen whole-photo baseline; --run makes metered API calls."""
import argparse
import base64
import concurrent.futures
import csv
import fcntl
import hashlib
import io
import json
import math
import os
import shlex
import signal
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'out/baseline'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_score(response):
    if 'choices' in response:
        candidate, = response['choices']
        if candidate.get('finish_reason') != 'stop':
            raise ValueError('Incomplete provider result: ' + str(candidate.get('finish_reason')))
        text = candidate['message']['content']
    else:
        candidate, = response['candidates']
        if candidate.get('finishReason') != 'STOP':
            raise ValueError('Incomplete provider result: ' + str(candidate.get('finishReason')))
        text = ''.join(p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought'))
    result = json.loads(text)
    score = result['similarity_score']
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError('Similarity score must be a finite number from 0 to 100')
    if not isinstance(result.get('reason'), str) or not result['reason'].strip():
        raise ValueError('Missing reason')
    return result, text


def usage_cost(usage, pricing):
    if 'cost' in usage:
        cost = usage['cost']
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            raise ValueError('Invalid reported cost')
        return cost
    if 'prompt_tokens' in usage:
        usage = {'promptTokenCount': usage['prompt_tokens'], 'candidatesTokenCount': usage['completion_tokens']}
    prompt = usage['promptTokenCount']
    cached = usage.get('cachedContentTokenCount', 0)
    output = usage.get('candidatesTokenCount', 0) + usage.get('thoughtsTokenCount', 0)
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in (prompt, cached, output)) or cached > prompt:
        raise ValueError('Invalid usage counters')
    return ((prompt - cached) * pricing['input_usd_per_million'] + cached * pricing['cached_input_usd_per_million'] + output * pricing['output_including_thinking_usd_per_million']) / 1_000_000


def budget_allows(spent, count, reservation, limit):
    return spent >= 0 and count >= 0 and spent + count * reservation <= limit + 1e-12


def decide(scores, order, threshold):
    ranked = sorted(order, key=lambda product: (-scores[product], order.index(product)))
    top = ranked[0]
    if scores[top] < threshold:
        return {'status': 'not_in_catalogue', 'product': None, 'score': scores[top], 'top_two': ranked[:2]}
    if scores[top] == scores[ranked[1]]:
        return {'status': 'not_sure', 'product': None, 'score': scores[top], 'top_two': ranked[:2]}
    return {'status': 'match', 'product': top, 'score': scores[top], 'top_two': ranked[:2]}


def api_key_for(name):
    if os.environ.get(name):
        return os.environ[name]
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            field, separator, value = line.partition('=')
            if separator and field.strip().removeprefix('export ') == name:
                parts = shlex.split(value, comments=True)
                if len(parts) == 1:
                    return parts[0]
    raise RuntimeError(name + ' is unavailable')


def payload(query, reference, config):
    if config.get('provider') == 'openrouter':
        def image(part):
            data = part['inlineData']
            return {'type': 'image_url', 'image_url': {'url': 'data:' + data['mimeType'] + ';base64,' + data['data']}}
        return {'model': config['model'], 'messages': [{'role': 'system', 'content': config['json_instruction']}, {'role': 'user', 'content': [{'type': 'text', 'text': config['prompt']}, {'type': 'text', 'text': 'Image A:'}, image(query), {'type': 'text', 'text': 'Image B:'}, image(reference)]}], 'max_tokens': config['max_output_tokens'], 'reasoning': {'enabled': config['reasoning_enabled']}, 'response_format': {'type': 'json_object'}, 'provider': config['openrouter_provider'], 'usage': {'include': True}}
    schema = {'type': 'object', 'properties': {'similarity_score': {'type': 'number', 'minimum': 0, 'maximum': 100}, 'reason': {'type': 'string'}}, 'required': ['similarity_score', 'reason'], 'additionalProperties': False}
    return {'contents': [{'role': 'user', 'parts': [{'text': config['prompt']}, {'text': 'Image A:'}, query, {'text': 'Image B:'}, reference]}], 'generationConfig': {'thinkingConfig': {'thinkingLevel': config['thinking_level']}, 'maxOutputTokens': config['max_output_tokens'], 'responseFormat': {'text': {'mimeType': 'APPLICATION_JSON', 'schema': schema}}}}


def prepare(config):
    manifest_bytes = (ROOT / 'data/test/test_manifest.json').read_bytes()
    assert digest(manifest_bytes) == config['test_manifest_sha256'], 'Test answer key changed'
    rows = json.loads(manifest_bytes)
    parts, inputs = {}, []
    input_dir = ROOT / config.get('input_dir', str((OUT / 'inputs').relative_to(ROOT)))
    input_dir.mkdir(parents=True, exist_ok=True)
    originals = [(r['image_id'], r['file'], r['sha256']) for r in rows]
    originals += [('R' + str(i + 1), ref['file'], ref['sha256']) for i, ref in enumerate(config['catalogue_references'].values())]
    for name, file, expected in originals:
        raw = (ROOT / file).read_bytes()
        assert digest(raw) == expected, ('Input file changed', name)
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert('RGBA')
            background = Image.new('RGBA', image.size, 'white')
            background.alpha_composite(image)
            image = background.convert('RGB')
            image.thumbnail((config['query_max_dimension'], config['query_max_dimension']))
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=config['query_jpeg_quality'])
            data = buffer.getvalue()
        target = input_dir / (name + '.jpg')
        if target.exists():
            assert target.read_bytes() == data, ('Prepared input changed', name)
        else:
            target.write_bytes(data)
        parts[name] = {'inlineData': {'mimeType': 'image/jpeg', 'data': base64.b64encode(data).decode()}}
        inputs.append({'id': name, 'file': str(target.relative_to(ROOT)), 'original_sha256': expected, 'prepared_sha256': digest(data), 'width': image.width, 'height': image.height})
    (OUT / 'input_manifest.json').write_text(json.dumps(inputs, indent=2) + '\n')
    return rows, parts


def ledger_rows(config_sha):
    path = OUT / 'calls.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    assert all(row['config_sha256'] == config_sha for row in rows), 'Config changed after metered calls'
    return rows


def run(config, config_sha, rows, parts, limit):
    openrouter = config.get('provider') == 'openrouter'
    api_key = api_key_for('OPENROUTER_API_KEY' if openrouter else 'GEMINI_API_KEY')
    old = ledger_rows(config_sha)
    completed = {(r['image_id'], r['catalogue_id']) for r in old if r['status'] == 'ok'}
    jobs = [(row['image_id'], product, 'R' + str(i + 1)) for row in rows for i, product in enumerate(config['catalogue_order']) if (row['image_id'], product) not in completed]
    if limit:
        jobs = jobs[:limit]
    pricing, budget = config['pricing'], config['budget']
    reservation = (budget['per_request_input_token_bound'] * pricing['input_usd_per_million'] + config['max_output_tokens'] * pricing['output_including_thinking_usd_per_million']) / 1_000_000
    cap = min(budget['baseline_max_inr'], budget['total_authorised_inr'] - budget.get('previous_budget_accounted_inr', 0)) / budget['conservative_usd_inr']
    spent = sum(row['estimated_cost_usd'] for row in old)
    stop_requested = False

    def stop_after_batch(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, stop_after_batch)

    def call(job):
        image_id, product, reference = job
        record = {'image_id': image_id, 'catalogue_id': product, 'config_sha256': config_sha, 'requested_model': config['model'], 'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        body = json.dumps(payload(parts[image_id], parts[reference], config), separators=(',', ':')).encode()
        record['request_sha256'] = digest(body)
        start, response = time.monotonic(), None
        try:
            url = 'https://openrouter.ai/api/v1/chat/completions' if openrouter else 'https://generativelanguage.googleapis.com/v1beta/models/' + config['model'] + ':generateContent'
            headers = {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + api_key} if openrouter else {'x-goog-api-key': api_key})}
            request = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=180) as reply:
                response = json.load(reply)
            record['usage_metadata'] = response.get('usage', {}) if openrouter else response.get('usageMetadata', {})
            record['model_version'] = response.get('model') if openrouter else response.get('modelVersion')
            record['provider'] = response.get('provider')
            record['response_id'] = response.get('id') if openrouter else response.get('responseId')
            result, text = parse_score(response)
            record.update(status='ok', result=result, response_text=text)
            if record['usage_metadata'].get('prompt_tokens' if openrouter else 'promptTokenCount', 0) > budget['per_request_input_token_bound']:
                raise ValueError('Input token count exceeds reserved bound')
        except Exception as error:
            message = str(error)
            if isinstance(error, urllib.error.HTTPError):
                message += ' ' + error.read(3000).decode(errors='replace')
            record.update(status='error', error=message.replace(api_key, '[REDACTED]'))
            if response is not None:
                record['provider_response'] = response
        record['elapsed_seconds'] = time.monotonic() - start
        try:
            record['estimated_cost_usd'] = usage_cost(record['usage_metadata'], pricing)
            record['cost_basis'] = 'openrouter_reported_cost' if openrouter and 'cost' in record['usage_metadata'] else 'reported_tokens_and_published_standard_rates'
        except (KeyError, ValueError):
            record['estimated_cost_usd'] = reservation
            record['cost_basis'] = 'reserved_upper_bound_usage_unavailable'
        return record

    for start in range(0, len(jobs), budget['concurrency']):
        if stop_requested or (OUT / 'STOP').exists():
            raise RuntimeError('Stopped on user instruction after saving in-flight responses')
        batch = jobs[start:start + budget['concurrency']]
        if not budget_allows(spent, len(batch), reservation, cap):
            raise RuntimeError('Baseline budget stop before scheduling another batch')
        failures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = [executor.submit(call, job) for job in batch]
            for future in concurrent.futures.as_completed(futures):
                record = future.result()
                with (OUT / 'calls.jsonl').open('a') as log:
                    log.write(json.dumps(record, ensure_ascii=False) + '\n')
                    log.flush()
                    os.fsync(log.fileno())
                spent += record['estimated_cost_usd']
                if record['status'] == 'error':
                    failures.append(record['error'])
                else:
                    completed.add((record['image_id'], record['catalogue_id']))
        count = len(completed)
        print(json.dumps({'completed_pairs': count, 'total_pairs': len(rows) * len(config['catalogue_order']), 'estimated_cost_usd': round(spent, 6), 'failed_this_batch': len(failures)}), flush=True)
        if failures:
            raise RuntimeError('Provider/response failure; no further batches scheduled: ' + failures[0])


def summarize(config, config_sha, rows):
    calls = ledger_rows(config_sha)
    good = [r for r in calls if r['status'] == 'ok']
    by_pair = {(r['image_id'], r['catalogue_id']): r for r in good}
    expected_pairs = {(r['image_id'], p) for r in rows for p in config['catalogue_order']}
    assert set(by_pair) == expected_pairs and len(good) == len(expected_pairs), 'Run incomplete or duplicate successful comparisons'
    singles = [r for r in rows if r['evaluation_role'] == 'labelled_single']
    score_rows, metrics = [], {}
    for row in rows:
        scores = {p: by_pair[row['image_id'], p]['result']['similarity_score'] for p in config['catalogue_order']}
        score_rows.append({'image_id': row['image_id'], 'source_labels': row['labels'], 'evaluation_role': row['evaluation_role'], 'scores': scores, 'decisions': {str(t): decide(scores, config['catalogue_order'], t) for t in config['thresholds']}})
    for threshold in config['thresholds']:
        results = []
        for row in score_rows:
            if row['evaluation_role'] != 'labelled_single':
                continue
            decision = row['decisions'][str(threshold)]
            truth = set(row['source_labels']) & set(config['catalogue_order'])
            correct = (decision['status'] == 'match' and decision['product'] in truth) or (decision['status'] == 'not_in_catalogue' and not truth)
            results.append(dict(decision, image_id=row['image_id'], source_label=row['source_labels'][0], in_catalogue=bool(truth), correct=bool(correct)))
        accepted = [r for r in results if r['status'] == 'match']
        wrong = [r for r in accepted if not r['correct']]
        pair_counts = {'true_accept': 0, 'false_accept': 0, 'true_reject': 0, 'false_reject': 0}
        for row in score_rows:
            for product, score in row['scores'].items():
                positive, accept = product in row['source_labels'], score >= threshold
                key = ('true_accept' if accept else 'false_reject') if positive else ('false_accept' if accept else 'true_reject')
                pair_counts[key] += 1
        metrics[str(threshold)] = {'single_photo_count': len(results), 'correct_total': sum(r['correct'] for r in results), 'correct_catalogue_matches': sum(r['correct'] and r['in_catalogue'] for r in results), 'catalogue_photo_count': sum(r['in_catalogue'] for r in results), 'correct_non_catalogue_rejections': sum(r['correct'] and not r['in_catalogue'] for r in results), 'non_catalogue_photo_count': sum(not r['in_catalogue'] for r in results), 'accepted_count': len(accepted), 'wrong_accepted_count': len(wrong), 'not_sure_count': sum(r['status'] == 'not_sure' for r in results), 'not_in_catalogue_count': sum(r['status'] == 'not_in_catalogue' for r in results), 'confidently_wrong_count': sum(r['score'] >= config['confidently_wrong_score_min'] for r in wrong), 'wrong_answers': wrong, 'per_photo': results, 'verification_pair_counts': pair_counts}
    total_cost = sum(r['estimated_cost_usd'] for r in calls)
    summary = {'study': config['study_id'], 'model': config['model'], 'config_sha256': config_sha, 'labelled_photos': len(rows), 'single_photos': len(singles), 'multi_photos': len(rows) - len(singles), 'successful_calls': len(good), 'failed_calls': len(calls) - len(good), 'model_versions': sorted({r.get('model_version') or 'unreported' for r in good}), 'estimated_cost_usd': total_cost, 'estimated_cost_inr': total_cost * config['exchange_rate']['usd_inr'], 'estimated_cost_inr_per_original_photo': total_cost * config['exchange_rate']['usd_inr'] / len(rows), 'mean_successful_pair_cost_inr': statistics.mean(r['estimated_cost_usd'] for r in good) * config['exchange_rate']['usd_inr'], 'thresholds': metrics, 'multi_product_results': [r for r in score_rows if r['evaluation_role'] != 'labelled_single']}
    (OUT / 'scores.json').write_text(json.dumps(score_rows, indent=2) + '\n')
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    with (OUT / 'scores.csv').open('w', newline='') as target:
        writer = csv.writer(target, lineterminator='\n')
        writer.writerow(['image_id', 'source_labels'] + config['catalogue_order'])
        writer.writerows([r['image_id'], '|'.join(r['source_labels']), *[r['scores'][p] for p in config['catalogue_order']]] for r in score_rows)
    print(json.dumps({k: v for k, v in summary.items() if k not in ('thresholds', 'multi_product_results')}, indent=2))
    for threshold, result in metrics.items():
        print(json.dumps({'threshold': threshold, **{k: v for k, v in result.items() if k not in ('per_photo', 'wrong_answers')}}, indent=2))


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--config', default='data/baseline_qwen_config.json')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--summarize', action='store_true')
    args = parser.parse_args()
    config_bytes = (ROOT / args.config).read_bytes()
    config, config_sha = json.loads(config_bytes), digest(config_bytes)
    OUT = ROOT / config.get('output_dir', 'out/baseline')
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows, parts = prepare(config)
        if args.run:
            try:
                run(config, config_sha, rows, parts, args.limit)
            except Exception as error:
                (OUT / 'BLOCKER.md').write_text('Baseline stopped.\n\n' + str(error) + '\n\nSaved call records include any returned usage. No automatic retry or model substitution was attempted.\n')
                raise
        if args.summarize:
            summarize(config, config_sha, rows)
        if not args.run and not args.summarize:
            print(f'Prepared {len(rows)} whole photos and six reference images; no metered call made')


if __name__ == '__main__':
    main()
