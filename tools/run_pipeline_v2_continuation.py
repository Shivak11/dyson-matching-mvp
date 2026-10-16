"""Continue the Gemini experiment through the recorded standard endpoint."""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import shutil
import time

import run_pipeline_v2 as v2
from pipeline_api import Client, positive

ROOT = v2.ROOT
FULL = Path('out/pipeline_v2_full')
NEW = Path('out/pipeline_v2_continuation')
CONFIG = Path('data/pipeline_v2_continuation_config.json')
FULL_CONFIG = Path('data/pipeline_v2_full_config.json')
AMENDMENT = Path('data/pipeline_v2_budget_amendment.json')
ROUTE = Path('data/pipeline_v2_route_decision.json')
MANUAL_STOP = 'Manual pause after repeated Vertex Flex 429 responses.'


class StandardClient(Client):
    def generate(self, job_id, *args, **kwargs):
        if not job_id.startswith('v2full:'):
            raise ValueError('Unexpected Gemini logical job ID')
        return super().generate('v2standard:'+job_id[len('v2full:'):], *args, **kwargs)

    def record_validation_failure(self, job_id, error):
        if not job_id.startswith('v2full:'):
            raise ValueError('Unexpected Gemini logical job ID')
        return super().record_validation_failure('v2standard:'+job_id[len('v2full:'):], error)


def ledger(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def spent(records):
    return sum(positive(row['estimated_cost_usd'], 'recorded cost', True) for row in records)


def build_config(full_config, root=ROOT):
    """Call only while holding the shared run lock, after the recorded old stop."""
    root = Path(root)
    amendment = v2.read(root/AMENDMENT, {})
    required = {'stage_ceiling_before_inr': 400, 'additional_authorized_inr': 200,
                'stage_ceiling_after_inr': 600, 'overall_ceiling_inr': 2000,
                'model_and_request_settings_unchanged': True}
    if any(amendment.get(key) != value for key, value in required.items()) or not amendment.get('owner_instruction'):
        raise ValueError('Missing or incompatible budget authorisation')
    if full_config['stage_ceiling_inr'] != 400 or full_config['budget']['total_max_inr'] != 2000:
        raise ValueError('Unexpected previous budget')
    for file, digest in full_config['frozen_files'].items():
        if v2.sha(root/file) != digest:
            raise ValueError('Frozen file changed: '+file)
    v2.verify_history(full_config, root=root)
    route = v2.read(root/ROUTE, {})
    model = full_config['models']['flash37high']
    if (route.get('new_route') != ['google-ai-studio'] or route.get('previous_route') != model['provider_only']
        or route.get('requested_model') != model['model'] or route.get('automatic_fallback') is not False
        or route.get('advertised_dated_model') != 'google/gemini-3.7-flash-20260813'
        or route.get('input_usd_per_million') != model['input_usd_per_million']
        or route.get('output_usd_per_million') != model['output_usd_per_million']):
        raise ValueError('Missing or incompatible manual provider decision')
    receipt = v2.read(root/FULL/'run_receipt.json', {})
    budget_stop = str(receipt.get('error', '')).startswith('Pipeline budget stop before request:')
    stop = root/FULL/'STOP'
    manual_stop = receipt.get('error') == 'Pipeline STOP file is present' and stop.exists() and stop.read_text().startswith(MANUAL_STOP)
    if receipt.get('status') != 'stopped' or not (budget_stop or manual_stop):
        raise ValueError('Continuation requires a settled budget stop or the recorded manual route stop')
    if v2.read(root/FULL/'inflight.json', {}) or receipt.get('inflight_count') != 0:
        raise ValueError('Earlier requests remain in flight')
    path = root/FULL/'calls.jsonl'
    records = ledger(path)
    if not records or any(row.get('status') != 'ok' and not
                          (manual_stop and Client._is_rate_limit(row) and not row.get('retry_exhausted'))
                          for row in records):
        raise ValueError('Continuation cannot reset another failed request or exhausted retry policy')
    if abs(spent(records)-receipt['new_accounted_usd']) > 1e-10:
        raise ValueError('Previous stop receipt does not match settled costs')
    config = copy.deepcopy(full_config)
    config['study_id'] += '-budget-continuation'
    config['stage_ceiling_inr'] = 600
    config['models']['flash37high']['provider_only'] = route['new_route']
    config['phase_route'] = {**route, 'logical_job_prefix':'v2standard:',
                             'partial_old_responses_reused':False}
    config['previous_ledgers'].append({'file':str(FULL/'calls.jsonl'), 'sha256':v2.sha(path),
                                       'accounted_cost_usd':spent(records)})
    previous = sum(source['accounted_cost_usd'] for source in config['previous_ledgers'])
    guard = previous*config['budget']['usd_inr']
    config['budget'].update(stage_max_inr=600-guard,
                            prior_accounted_inr=config['prior_stage_accounted_inr']+guard)
    if config['budget']['stage_max_inr'] <= 0:
        raise ValueError('No continuation allowance remains')
    files = [root/FULL/name for name in ('run_receipt.json','blocker.json','scoreboard.json',
                                         'results.json','detections.json','completed_photos.json','summary.json','STOP')
             if (root/FULL/name).exists()]
    completed = set(v2.read(root/FULL/'completed_photos.json', []))
    partial = root/FULL/'photos'
    if partial.exists():
        files += [file for directory in partial.iterdir() if directory.is_dir() and directory.name not in completed
                  for file in directory.rglob('*') if file.is_file()]
    config['prior_phase_evidence'] = {str(file.relative_to(root/FULL)):v2.sha(file) for file in files}
    if manual_stop:
        config['frozen_files'][str(FULL/'STOP')] = v2.sha(stop)
    for file in (FULL_CONFIG, AMENDMENT, ROUTE):
        config['frozen_files'][str(file)] = v2.sha(root/file)
    source = root/'tools/run_pipeline_v2_continuation.py'
    if source.exists():
        config['frozen_files'][str(source.relative_to(root))] = v2.sha(source)
    plates_file = root/FULL/'reference_plates.json'
    if plates_file.exists():
        config['frozen_files'][str(plates_file.relative_to(root))] = v2.sha(plates_file)
        for plate in v2.read(plates_file, {}).values():
            if v2.sha(root/plate['file']) != plate['sha256']:
                raise ValueError('Prepared manufacturer reference changed')
            config['frozen_files'][plate['file']] = plate['sha256']
    verify_config(config, root)
    return config


def verify_config(config, root=ROOT):
    root = Path(root)
    if config['stage_ceiling_inr'] != 600 or config['budget']['total_max_inr'] != 2000:
        raise ValueError('Continuation changes authorised ceilings')
    files = [source['file'] for source in config['previous_ledgers']]
    if len(files) != 5 or len(set(files)) != 5 or files[-1] != str(FULL/'calls.jsonl'):
        raise ValueError('Continuation must carry all five prior ledgers exactly once')
    for file, digest in config['frozen_files'].items():
        if v2.sha(root/file) != digest:
            raise ValueError('Frozen file changed: '+file)
    original = v2.read(root/FULL_CONFIG, {})
    models = copy.deepcopy(original['models'])
    models['flash37high']['provider_only'] = ['google-ai-studio']
    if config['models'] != models or config['rate_limit_policy'] != original['rate_limit_policy'] or config['confidence_threshold'] != original['confidence_threshold']:
        raise ValueError('Continuation changes model settings or decision rules')
    return v2.verify_history(config, root=root)


def snapshot_prior_stop(config, root=ROOT):
    root = Path(root)
    directory = root/NEW/'prior_phase_snapshot'
    directory.mkdir(parents=True, exist_ok=True)
    for name, digest in config['prior_phase_evidence'].items():
        destination = directory/name
        if not destination.exists():
            if v2.sha(root/FULL/name) != digest:
                raise ValueError('Previous stop evidence changed before snapshot')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root/FULL/name, destination)
        if v2.sha(destination) != digest:
            raise ValueError('Previous stop snapshot changed')


def continuation_costs(config, root=ROOT):
    root = Path(root)
    full_cost = spent(ledger(root/FULL/'calls.jsonl'))
    calls = ledger(root/NEW/'calls.jsonl')
    new_cost = spent(calls)
    settled_jobs = {row['job_id'] for row in calls}
    reserve = sum(positive(row['reserved_cost_usd'], 'pending reserve', True)
                  for job,row in v2.read(root/NEW/'inflight.json', {}).items() if job not in settled_jobs)
    previous = sum(source['accounted_cost_usd'] for source in config['previous_ledgers'])
    guard_rate, report_rate = config['budget']['usd_inr'], config['reporting_usd_inr']
    corrected = full_cost+new_cost+reserve
    combined = previous+new_cost+reserve
    completed = len(v2.read(root/FULL/'completed_photos.json', []))
    preflight = next(source['accounted_cost_usd'] for source in config['previous_ledgers']
                     if source['file']=='out/pipeline_v2/calls.jsonl')
    return {'new_settled_usd':full_cost+new_cost, 'pending_reserve_usd':reserve,
            'new_accounted_usd':corrected, 'new_cost_inr':corrected*report_rate,
            'new_guard_inr':corrected*guard_rate,
            'corrected_full_settled_usd':full_cost, 'continuation_settled_usd':new_cost,
            'technical_preflight_usd':preflight,
            'revision_including_preflight_cost_inr':(corrected+preflight)*report_rate,
            'stage_ceiling_inr':600, 'combined_stage_guard_inr':combined*guard_rate,
            'combined_stage_cost_inr':combined*report_rate,
            'remaining_guard_inr':600-combined*guard_rate,
            'new_cost_per_completed_photo_inr':corrected*report_rate/completed if completed else None,
            'completed_original_photos':completed,
            'shared_v1_preprocessing_cost_included_in_new_cost':False}


def score(config, rows):
    scoreboard = v2.score(config, rows)
    scoreboard['costs'] = continuation_costs(config, ROOT)
    v2.save(ROOT/FULL/'scoreboard.json', scoreboard)
    v2.save(ROOT/NEW/'scoreboard.json', scoreboard)
    return scoreboard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    with (ROOT/'out/pipeline/run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        config = v2.read(ROOT/CONFIG, {})
        if not config:
            if not args.run:
                raise ValueError('Run configuration is not frozen; --run is required to activate continuation')
            config = build_config(v2.read(ROOT/FULL_CONFIG, {}), ROOT)
            snapshot_prior_stop(config, ROOT)
            v2.save(ROOT/CONFIG, config)
        verify_config(config, ROOT)
        snapshot_prior_stop(config, ROOT)
        rows = v2.read(ROOT/'data/test/test_manifest.json', [])
        if not args.run:
            print(json.dumps({'status':'offline','costs':score(config, rows)['costs']})); return
        client = StandardClient(config, ROOT, ROOT/NEW, **config['rate_limit_policy'])
        cards = v2.read(ROOT/'data/reference_cards_v2.json', {})['products']
        plates = v2.read(ROOT/FULL/'reference_plates.json', {})
        old_detections = v2.read(ROOT/'out/pipeline/detections.json', {})
        shortlists = v2.read(ROOT/'out/pipeline/shortlists.json', {})
        results = v2.read(ROOT/FULL/'results.json', [])
        detections = v2.read(ROOT/FULL/'detections.json', {})
        completed = v2.read(ROOT/FULL/'completed_photos.json', [])
        remaining = [photo for photo in rows if photo['image_id'] not in completed]
        selected = remaining[:args.limit] if args.limit else remaining
        failure = None
        started = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            for photo in selected:
                image_id = photo['image_id']
                if image_id in completed: continue
                observation, initial, final = v2.run_photo(client, config, photo, cards, plates, old_detections, shortlists)
                detections[image_id] = [{**target,'instance_id':image_id+'_'+target['object_id']} for target in observation['machines']]
                if not initial:
                    decision = {'status':'not_sure','product':None,'confidence':0,'top_two':[],'evidence':[],
                                'missing_evidence':['No physical cleaner was located.'],'contradictions':[],
                                'retake':'Photograph the cleaner body, bin and controls.'}
                    initial = [{'image_id':image_id,'instance_id':image_id+'_none','detection_missed':True,
                                'model':'flash37high_v2','variant':'evidence_initial','candidates':[],
                                'candidate_checks':[],'decision':decision}]
                    final = [{**initial[0],'variant':'evidence_final'}]
                results = [row for row in results if row['image_id'] != image_id]+initial+final
                v2.save(ROOT/FULL/'detections.json', detections); v2.save(ROOT/FULL/'results.json', results)
                completed.append(image_id); v2.save(ROOT/FULL/'completed_photos.json', completed)
                print(json.dumps({'photo':image_id,'completed':len(completed),'machines':len(observation['machines']),
                                  'final':[row['decision'] for row in final],
                                  'continuation_guard_inr':client.accounted_cost_usd*config['budget']['usd_inr']}), flush=True)
        except Exception as error:
            failure = str(error)
            v2.save(ROOT/NEW/'blocker.json', {'error':failure,'completed_photos':completed,
                    'new_accounted_usd':client.accounted_cost_usd,
                    'attempted':'Same Gemini model and matching protocol, one worker, 15-second gaps and recorded bounded 429 retries; fixed standard endpoint.'})
        finally:
            verify_config(config, ROOT)
            receipt = {'started_utc':started,'settled_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                       'status':'stopped' if failure else 'completed','completed_count':len(completed),
                       'requested_count':len(selected),'workers':1,'rate_limit_policy':config['rate_limit_policy'],
                       'continuation_accounted_usd':client.accounted_cost_usd,'reused_jobs':sorted(client.reused_jobs),
                       'ledger':str(NEW/'calls.jsonl'),'inflight_count':len(client.pending),'error':failure,
                       'phase_route':config['phase_route']}
            v2.save(ROOT/NEW/'run_receipt.json', receipt)
            v2.save(ROOT/FULL/'run_receipt.json', receipt)
            scoreboard = score(config, rows)
            print(json.dumps({'status':receipt['status'],'costs':scoreboard['costs']}), flush=True)
        if failure: raise SystemExit('Stopped: '+failure)


if __name__ == '__main__': main()
