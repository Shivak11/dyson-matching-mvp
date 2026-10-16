"""Finish the unchanged Gemini protocol with an explicitly enlarged output limit."""
import argparse
import copy
import fcntl
from pathlib import Path
import shutil
import time
import json

import run_pipeline_v2 as v2
from run_pipeline_v2_continuation import ledger, spent
from pipeline_api import Client, positive

ROOT = v2.ROOT
FULL = Path('out/pipeline_v2_full')
PREVIOUS = Path('out/pipeline_v2_continuation')
PREVIOUS_CONFIG = Path('data/pipeline_v2_continuation_config.json')
NEW = Path('out/pipeline_v2_recovery')
CONFIG = Path('data/pipeline_v2_recovery_config.json')
DECISION = Path('data/pipeline_v2_recovery_decision.json')
FAILED = 'v2standard:identify:P051'


class RecoveryClient(Client):
    def generate(self, job_id, *args, **kwargs):
        if not isinstance(job_id, str) or not job_id.startswith('v2full:'):
            raise ValueError('Unexpected Gemini logical job ID')
        return super().generate('v2long:'+job_id[len('v2full:'):], *args, **kwargs)

    def record_validation_failure(self, job_id, error):
        if not isinstance(job_id, str) or not job_id.startswith('v2full:'):
            raise ValueError('Unexpected Gemini logical job ID')
        return super().record_validation_failure('v2long:'+job_id[len('v2full:'):], error)


def build_config(previous, root=ROOT):
    """Activate only under the shared run lock after the recorded terminal stop."""
    root = Path(root)
    from run_pipeline_v2_continuation import verify_config as verify_previous
    verify_previous(previous, root)
    decision = v2.read(root/DECISION, {})
    required = {'failed_logical_job_id':FAILED, 'previous_max_output_tokens':16384,
                'new_max_output_tokens':32768, 'stage_ceiling_inr':600,
                'requested_model':'google/gemini-3.7-flash', 'provider_only':['google-ai-studio'],
                'thinking_level':'high', 'automatic_fallback':False}
    if any(decision.get(key) != value for key, value in required.items()) or not decision.get('owner_instruction'):
        raise ValueError('Missing or incompatible output-limit recovery authorisation')
    if v2.read(root/PREVIOUS/'inflight.json', {}):
        raise ValueError('Previous requests remain in flight')
    records = ledger(root/PREVIOUS/'calls.jsonl')
    if not records:
        raise ValueError('Missing failed request')
    failed = records[-1]
    choices = failed.get('provider_response', {}).get('choices', [])
    receipt = v2.read(root/PREVIOUS/'run_receipt.json', {})
    if (failed.get('logical_job_id') != FAILED or failed.get('status') != 'error'
        or failed.get('http_status') != 200 or failed.get('error') != 'Incomplete provider result: length'
        or len(choices) != 1 or choices[0].get('finish_reason') != 'length'
        or choices[0].get('native_finish_reason') != 'MAX_TOKENS'
        or receipt.get('status') != 'stopped' or receipt.get('inflight_count') != 0
        or receipt.get('error') != failed['job_id']+': '+failed['error']):
        raise ValueError('Recovery requires the settled specific P051 output-limit failure')
    latest = {row.get('logical_job_id', row['job_id']):row for row in records}
    if any(row.get('status') != 'ok' and name != FAILED for name,row in latest.items()):
        raise ValueError('Another unresolved failed request cannot be reset')
    if abs(spent(records)-receipt['continuation_accounted_usd']) > 1e-10:
        raise ValueError('Previous stop receipt does not match settled costs')
    config = copy.deepcopy(previous)
    config['study_id'] += '-output-limit-recovery'
    config['models']['flash37high']['max_output_tokens'] = 32768
    config['phase_route'] = {**previous['phase_route'], 'logical_job_prefix':'v2long:',
                             'max_output_tokens':32768, 'partial_old_responses_reused':False}
    config['recovery_decision'] = decision
    config['previous_ledgers'].append({'file':str(PREVIOUS/'calls.jsonl'),
         'sha256':v2.sha(root/PREVIOUS/'calls.jsonl'), 'accounted_cost_usd':spent(records)})
    guard = sum(source['accounted_cost_usd'] for source in config['previous_ledgers'])*config['budget']['usd_inr']
    config['budget'].update(stage_max_inr=600-guard,
                            prior_accounted_inr=config['prior_stage_accounted_inr']+guard)
    if config['budget']['stage_max_inr'] <= 0:
        raise ValueError('No authorised recovery budget remains')
    completed = set(v2.read(root/FULL/'completed_photos.json', []))
    if receipt.get('completed_count') != len(completed):
        raise ValueError('Previous completion receipt does not match saved results')
    config['phase_photo_ids'] = [row['image_id'] for row in v2.read(root/'data/test/test_manifest.json', [])
                                 if row['image_id'] not in completed]
    files = [(root/PREVIOUS/name) for name in ('run_receipt.json','blocker.json','scoreboard.json')
             if (root/PREVIOUS/name).exists()]
    files += [(root/FULL/name) for name in ('run_receipt.json','blocker.json','scoreboard.json','summary.json',
              'results.json','detections.json','completed_photos.json','STOP') if (root/FULL/name).exists()]
    partial = root/FULL/'photos'
    if partial.exists():
        files += [file for directory in partial.iterdir() if directory.is_dir() and directory.name not in completed
                  for file in directory.rglob('*') if file.is_file()]
    config['prior_phase_evidence'] = {str(file.relative_to(root)):v2.sha(file) for file in files}
    for file in (PREVIOUS_CONFIG, DECISION, Path('tools/run_pipeline_v2_recovery.py'), PREVIOUS/'calls.jsonl'):
        config['frozen_files'][str(file)] = v2.sha(root/file)
    if (root/PREVIOUS/'frozen_config.json').exists():
        config['frozen_files'][str(PREVIOUS/'frozen_config.json')] = v2.sha(root/PREVIOUS/'frozen_config.json')
    verify_config(config, root)
    return config


def verify_config(config, root=ROOT):
    root = Path(root)
    previous = v2.read(root/PREVIOUS_CONFIG, {})
    if config['stage_ceiling_inr'] != 600 or config['budget']['total_max_inr'] != 2000:
        raise ValueError('Recovery changes authorised ceilings')
    sources = config['previous_ledgers']
    files = [source['file'] for source in sources]
    if len(files) != 6 or len(set(files)) != 6 or sources[:-1] != previous['previous_ledgers'] or files[-1] != str(PREVIOUS/'calls.jsonl'):
        raise ValueError('Recovery must carry all six previous ledgers exactly once')
    for file, digest in previous['frozen_files'].items():
        if config['frozen_files'].get(file) != digest:
            raise ValueError('Recovery replaced a previous frozen input hash')
    for file, digest in config['frozen_files'].items():
        if v2.sha(root/file) != digest:
            raise ValueError('Frozen file changed: '+file)
    models = copy.deepcopy(previous['models'])
    if models['flash37high']['max_output_tokens'] != 16384:
        raise ValueError('Unexpected previous output limit')
    models['flash37high']['max_output_tokens'] = 32768
    if (config['models'] != models or config['rate_limit_policy'] != previous['rate_limit_policy']
        or config['confidence_threshold'] != previous['confidence_threshold']):
        raise ValueError('Recovery changes model settings or decision rules')
    return v2.verify_history(config, root=root)


def snapshot_prior_stop(config, root=ROOT):
    root = Path(root)
    directory = root/NEW/'prior_phase_snapshot'
    for name, digest in config['prior_phase_evidence'].items():
        destination = directory/name
        if not destination.exists():
            if v2.sha(root/name) != digest:
                raise ValueError('Previous phase evidence changed before snapshot')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root/name, destination)
        if v2.sha(destination) != digest:
            raise ValueError('Previous phase snapshot changed')


def recovery_costs(config, root=ROOT):
    root = Path(root)
    history = {source['file']:source['accounted_cost_usd'] for source in config['previous_ledgers']}
    full_cost, standard_cost = history[str(FULL/'calls.jsonl')], history[str(PREVIOUS/'calls.jsonl')]
    calls = ledger(root/NEW/'calls.jsonl')
    new_cost = spent(calls)
    settled = {row['job_id'] for row in calls}
    reserve = sum(positive(row['reserved_cost_usd'], 'pending reserve', True)
                  for job,row in v2.read(root/NEW/'inflight.json', {}).items() if job not in settled)
    corrected = full_cost+standard_cost+new_cost+reserve
    combined = sum(history.values())+new_cost+reserve
    guard_rate, report_rate = config['budget']['usd_inr'], config['reporting_usd_inr']
    completed = len(v2.read(root/FULL/'completed_photos.json', []))
    preflight = history['out/pipeline_v2/calls.jsonl']
    return {'new_settled_usd':full_cost+standard_cost+new_cost, 'pending_reserve_usd':reserve,
            'new_accounted_usd':corrected, 'new_cost_inr':corrected*report_rate,
            'new_guard_inr':corrected*guard_rate, 'corrected_full_settled_usd':full_cost,
            'continuation_settled_usd':standard_cost, 'recovery_settled_usd':new_cost,
            'technical_preflight_usd':preflight,
            'revision_including_preflight_cost_inr':(corrected+preflight)*report_rate,
            'stage_ceiling_inr':600, 'combined_stage_guard_inr':combined*guard_rate,
            'combined_stage_cost_inr':combined*report_rate, 'remaining_guard_inr':600-combined*guard_rate,
            'new_cost_per_completed_photo_inr':corrected*report_rate/completed if completed else None,
            'completed_original_photos':completed, 'shared_v1_preprocessing_cost_included_in_new_cost':False}


def score(config, rows):
    scoreboard = v2.score(config, rows)
    scoreboard['costs'] = recovery_costs(config, ROOT)
    v2.save(ROOT/FULL/'scoreboard.json', scoreboard)
    v2.save(ROOT/NEW/'scoreboard.json', scoreboard)
    return scoreboard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1: parser.error('--limit must be positive')
    with (ROOT/'out/pipeline/run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        config = v2.read(ROOT/CONFIG, {})
        if not config:
            if not args.run: raise ValueError('Use --run to activate the separately frozen recovery')
            config = build_config(v2.read(ROOT/PREVIOUS_CONFIG, {}), ROOT)
            snapshot_prior_stop(config, ROOT)
            v2.save(ROOT/CONFIG, config)
        verify_config(config, ROOT)
        snapshot_prior_stop(config, ROOT)
        rows = v2.read(ROOT/'data/test/test_manifest.json', [])
        if not args.run:
            print(json.dumps({'status':'offline','costs':score(config, rows)['costs']})); return
        client = RecoveryClient(config, ROOT, ROOT/NEW, **config['rate_limit_policy'])
        finished = [row['request_finished_unix'] for row in ledger(ROOT/PREVIOUS/'calls.jsonl')+ledger(ROOT/NEW/'calls.jsonl')
                    if isinstance(row.get('request_finished_unix'), (int,float))]
        if finished:
            client.last_request_finished_at = time.monotonic()-max(0,time.time()-max(finished))
        cards = v2.read(ROOT/'data/reference_cards_v2.json', {})['products']
        plates = v2.read(ROOT/FULL/'reference_plates.json', {})
        old_detections = v2.read(ROOT/'out/pipeline/detections.json', {})
        shortlists = v2.read(ROOT/'out/pipeline/shortlists.json', {})
        results, detections = v2.read(ROOT/FULL/'results.json', []), v2.read(ROOT/FULL/'detections.json', {})
        completed = v2.read(ROOT/FULL/'completed_photos.json', [])
        remaining = [row for row in rows if row['image_id'] not in completed and row['image_id'] in config['phase_photo_ids']]
        selected = remaining[:args.limit] if args.limit else remaining
        started, failure = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), None
        try:
            for photo in selected:
                image_id = photo['image_id']
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
                v2.save(ROOT/FULL/'detections.json', detections);v2.save(ROOT/FULL/'results.json', results)
                completed.append(image_id);v2.save(ROOT/FULL/'completed_photos.json', completed)
                print(json.dumps({'photo':image_id,'completed':len(completed),'final':[row['decision'] for row in final],
                                  'recovery_guard_inr':client.accounted_cost_usd*config['budget']['usd_inr']}), flush=True)
        except Exception as error:
            failure = str(error)
            v2.save(ROOT/NEW/'blocker.json', {'error':failure,'completed_photos':completed,
                    'new_accounted_usd':client.accounted_cost_usd,
                    'attempted':'Same Gemini high reasoning and standard endpoint; enlarged output bound, one worker and recorded 429 retry policy.'})
        finally:
            verify_config(config, ROOT)
            receipt = {'started_utc':started,'settled_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                       'status':'stopped' if failure else 'completed','completed_count':len(completed),
                       'requested_count':len(config['phase_photo_ids']),'selected_count':len(selected),
                       'workers':1,'rate_limit_policy':config['rate_limit_policy'],
                       'recovery_accounted_usd':client.accounted_cost_usd,'reused_jobs':sorted(client.reused_jobs),
                       'ledger':str(NEW/'calls.jsonl'),'inflight_count':len(client.pending),'error':failure,
                       'phase_route':config['phase_route']}
            v2.save(ROOT/NEW/'run_receipt.json', receipt);v2.save(ROOT/FULL/'run_receipt.json', receipt)
            print(json.dumps({'status':receipt['status'],'costs':score(config, rows)['costs']}), flush=True)
        if failure: raise SystemExit('Stopped: '+failure)


if __name__ == '__main__': main()
