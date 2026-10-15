"""Resume the fixed Gemini/Sol comparison with paced, recorded HTTP 429 retries."""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import time

import run_pipeline as pipeline
from run_high_reasoning import saved_inputs
from pipeline_api import Client, positive
from summarize_pipeline_study import make_study

ROOT = pipeline.ROOT
OUT = pipeline.OUT
NEW = OUT / 'slow_comparison'
CONFIG = ROOT / 'data/pipeline_slow_comparison_config.json'


def verify_history(config, root=ROOT):
    calls = []
    for source in config['previous_ledgers']:
        path = root / source['file']
        if pipeline.sha(path) != source['sha256']:
            raise ValueError('Earlier ledger changed: ' + source['file'])
        if pipeline.read(path.with_name('inflight.json'), {}):
            raise ValueError('Earlier requests remain in flight')
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        spent = sum(positive(row['estimated_cost_usd'], 'recorded cost', True) for row in rows)
        if abs(spent - source['accounted_cost_usd']) > 1e-10:
            raise ValueError('Earlier cost does not match its frozen allowance')
        calls.extend(rows)
    guard = sum(row['estimated_cost_usd'] for row in calls) * config['budget']['usd_inr']
    if abs(config['budget']['stage_max_inr'] + guard - config['stage_ceiling_inr']) > 1e-8:
        raise ValueError('Revised allowance changes the authorised stage ceiling')
    if abs(config['budget']['prior_accounted_inr'] - guard - config['prior_stage_accounted_inr']) > 1e-8:
        raise ValueError('Revised allowance omits earlier total spending')
    return calls


def combined_study(config, old_calls, out=OUT, new=NEW):
    if pipeline.read(new / 'inflight.json', {}):
        raise ValueError('New requests remain unresolved; wait for settled spending')
    pipeline.summarise(config, pipeline.read(ROOT / 'data/test/test_manifest.json', []))
    path = new / 'calls.jsonl'
    calls = old_calls + ([json.loads(line) for line in path.read_text().splitlines()] if path.exists() else [])
    reporting = copy.deepcopy(config)
    reporting['budget']['stage_max_inr'] = config['stage_ceiling_inr']
    study = make_study(reporting, pipeline.read(ROOT / 'data/test/test_manifest.json', []), pipeline.read(out / 'results.json', []), pipeline.read(out / 'detections.json', {}), calls)
    pipeline.save(out / 'study.json', study)
    pipeline.save(new / 'study.json', study)
    return study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--model', action='append', choices=['flash37high', 'solhigh'])
    parser.add_argument('--limit', type=int, help='Preflight on the first N fixed-subset photos.')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    config = pipeline.read(CONFIG, {})
    selected = args.model or config['requested_models']
    ids = config['premium_subset_ids'][:args.limit] if args.limit else config['premium_subset_ids']
    pipeline.RUNTIME_CONCURRENCY = 1
    NEW.mkdir(parents=True, exist_ok=True)
    started = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with (OUT / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_calls = verify_history(config)
        inputs, _ = saved_inputs(config)
        client, failure = None, None
        if args.run:
            client = Client(config, ROOT, NEW, reuse_records=old_calls, **config['rate_limit_policy'])
            stop = OUT / 'STOP'
            previous_stop = stop.read_text() if stop.exists() else None
            stop.unlink(missing_ok=True)
            try:
                pipeline.check(config, client, inputs['photos'], inputs['references'], ids, selected, ['telling_details'])
            except Exception as error:
                failure = str(error)
                pipeline.save(NEW / 'blocker.json', {'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'error': failure, 'attempted': 'One worker, paced requests and bounded HTTP 429 retries; no fallback.'})
            finally:
                stop.write_text(previous_stop or 'Original run paused. Use run_slow_comparison.py for the current comparison.\n')
                pipeline.save(NEW / 'run_receipt.json', {'started_at_utc': started, 'settled_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'status': 'stopped' if failure else 'completed', 'models': selected, 'photo_ids': ids, 'reused_jobs': sorted(client.reused_jobs), 'rate_limit_policy': config['rate_limit_policy'], 'workers': 1, 'new_ledger_accounted_usd': client.accounted_cost_usd, 'inflight_count': len(client.pending), 'error': failure})
        study = combined_study(config, old_calls)
        print(json.dumps({'status': 'stopped' if failure else 'completed', 'stage_cost_inr': study['costs']['stage_cost_inr'], 'guard_accounted_inr': study['costs']['guard_accounted_inr'], 'stage_ceiling_inr': study['costs']['stage_ceiling_inr']}), flush=True)
        if failure:
            raise SystemExit('Stopped: ' + failure)


if __name__ == '__main__':
    main()
