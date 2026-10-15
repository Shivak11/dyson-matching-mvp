"""Run the owner-requested model settings while preserving earlier evidence and spend."""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import time
import run_pipeline as pipeline
from pipeline_api import Client
from summarize_pipeline_study import make_study

ROOT = pipeline.ROOT
OUT = pipeline.OUT
NEW = OUT / 'high_reasoning'


def verify_previous(config, out=OUT):
    previous = config['previous_stage']
    if pipeline.sha(out/'calls.jsonl') != previous['calls_sha256']:
        raise ValueError('Earlier spending changed; recalculate the remaining allowance')
    if pipeline.read(out/'inflight.json', {}):
        raise ValueError('Earlier requests remain in flight')
    calls = [json.loads(line) for line in (out/'calls.jsonl').read_text().splitlines()]
    spent = sum(row['estimated_cost_usd'] for row in calls)
    guard = spent * config['budget']['usd_inr']
    if abs(guard - previous['guard_accounted_inr']) > 1e-8:
        raise ValueError('Earlier cost does not match the frozen allowance')
    if abs(config['budget']['stage_max_inr'] + guard - previous['stage_ceiling_inr']) > 1e-8:
        raise ValueError('Revised allowance changes the authorised stage ceiling')
    if abs(config['budget']['prior_accounted_inr'] - guard - previous['prior_accounted_inr']) > 1e-8:
        raise ValueError('Revised allowance omits earlier total spending')
    return calls


def saved_inputs(config):
    for file, key in [('data/test/test_manifest.json','test_manifest_sha256'), ('data/reference_pack.json','reference_pack_sha256'), ('data/telling_details.json','telling_details_sha256')]:
        if pipeline.sha(ROOT/file) != config[key]:
            raise ValueError('Frozen input changed: '+file)
    inputs = pipeline.read(OUT/'inputs.json', {})
    detections = pipeline.read(OUT/'detections.json', {})
    shortlists = pipeline.read(OUT/'shortlists.json', {})
    for image_id in config['premium_subset_ids']:
        photo = inputs['photos'][image_id]
        if pipeline.sha(ROOT/photo['file']) != photo['sha256']:
            raise ValueError('Prepared photo changed: '+image_id)
        for obj in detections[image_id]:
            if pipeline.sha(ROOT/obj['crop_file']) != obj['crop_sha256'] or obj['instance_id'] not in shortlists:
                raise ValueError('Saved crop or shortlist unavailable: '+obj['instance_id'])
    for refs in inputs['references'].values():
        for ref in refs:
            if pipeline.sha(ROOT/ref['file']) != ref['sha256']:
                raise ValueError('Prepared reference changed: '+ref['id'])
    return inputs, detections


def combined_study(config, old_calls):
    pipeline.summarise(config, pipeline.read(ROOT/'data/test/test_manifest.json', []))
    calls = old_calls + [json.loads(line) for line in (NEW/'calls.jsonl').read_text().splitlines()] if (NEW/'calls.jsonl').exists() else old_calls
    reporting = copy.deepcopy(config)
    reporting['budget']['stage_max_inr'] = config['previous_stage']['stage_ceiling_inr']
    study = make_study(reporting, pipeline.read(ROOT/'data/test/test_manifest.json', []), pipeline.read(OUT/'results.json', []), pipeline.read(OUT/'detections.json', {}), calls)
    pipeline.save(OUT/'study.json', study)
    return study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--model', action='append')
    parser.add_argument('--limit', type=int, help='Preflight on the first N fixed-subset photos.')
    parser.add_argument('--workers', type=int, choices=range(1,9), default=3)
    args = parser.parse_args()
    config = pipeline.read(ROOT/'data/pipeline_high_reasoning_config.json', {})
    selected = args.model or config['requested_models']
    if not selected or any(m not in config['requested_models'] for m in selected):
        parser.error('Use only the owner-requested settings in this comparison')
    ids = config['premium_subset_ids'][:args.limit] if args.limit else config['premium_subset_ids']
    pipeline.RUNTIME_CONCURRENCY = args.workers
    with (OUT/'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        old_calls = verify_previous(config)
        inputs, _ = saved_inputs(config)
        if args.run:
            client = Client(config, ROOT, NEW)
            (OUT/'STOP').unlink(missing_ok=True)
            try:
                pipeline.check(config, client, inputs['photos'], inputs['references'], ids, selected, ['telling_details'])
            except Exception as error:
                pipeline.save(NEW/'blocker.json', {'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()), 'error':str(error), 'attempted':'Requested models with existing inputs, saved usage and no automatic retries.'})
                raise
            finally:
                (OUT/'STOP').write_text('Original run paused after model-setting revision. Use run_high_reasoning.py to retain the combined spending limit.\n')
        study = combined_study(config, old_calls)
        print(json.dumps({'stage_cost_inr':study['costs']['stage_cost_inr'], 'guard_accounted_inr':study['costs']['guard_accounted_inr'], 'stage_ceiling_inr':study['costs']['stage_ceiling_inr']}))

if __name__ == '__main__':
    main()
