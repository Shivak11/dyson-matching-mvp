"""Repair one saved unresolved advisory-alternative list without a paid request."""
import argparse
import copy
import fcntl
import json
import re
from pathlib import Path
import time

import run_pipeline_v2 as v2
import run_pipeline_v2_recovery as recovery
from pipeline_api import Client, digest, encoded

ROOT = v2.ROOT
POLICY = Path('data/pipeline_v2_alternative_repair_decision.json')
RECEIPTS = recovery.NEW/'validation_repairs'


def receipt_file(job_id):
    return RECEIPTS/(job_id.replace(':','_')+'.json')
NORMALISATION = ('Remove only known non-catalogue reference IDs outside the supplied candidates '
                 'from top_two in not_sure answers with null product. Keep remaining order, '
                 'preserve substantive answer fields and retain removed IDs as unverified alternatives.')


def normalise_batch(raw, targets, candidate_map, non_catalogue_ids, threshold=90):
    normalised = copy.deepcopy(raw)
    if not isinstance(normalised, dict) or not isinstance(normalised.get('results'), list):
        raise ValueError('Invalid matching batch')
    changed = False
    for item in normalised['results']:
        if not isinstance(item,dict) or item.get('object_id') not in candidate_map or not isinstance(item.get('decision'),dict):
            raise ValueError('Invalid matching object')
        candidates = candidate_map[item['object_id']]
        decision = item['decision']
        alternatives = decision['top_two']
        if (not isinstance(alternatives, list) or len(alternatives)>2
            or any(not isinstance(value, str) or not value.strip() for value in alternatives)
            or len(set(alternatives)) != len(alternatives)):
            raise ValueError('Malformed advisory alternatives cannot be repaired')
        removed = [value for value in alternatives if value not in candidates]
        if not removed: continue
        if decision['status'] != 'not_sure' or decision['product'] is not None:
            raise ValueError('Resolved answers cannot be repaired')
        if any(value not in non_catalogue_ids for value in removed):
            raise ValueError('Unknown or unsupplied catalogue alternative cannot be removed')
        for key in ('format_repairs','unverified_alternatives'):
            if key in item and (not isinstance(item[key], list) or any(not isinstance(value,str) for value in item[key])):
                raise ValueError('Malformed repair metadata')
        decision['top_two'] = [value for value in alternatives if value in candidates]
        item.setdefault('format_repairs', []).append('Known non-catalogue advisory alternatives removed from top_two: '+', '.join(removed)+'.')
        item.setdefault('unverified_alternatives', []).extend(removed)
        changed = True
    if not changed:
        raise ValueError('No permitted advisory alternative repair exists')
    v2.validate_batch(normalised, targets, candidate_map, threshold)
    return normalised


def load_context(job_id, config, root=ROOT):
    parts = job_id.split(':')
    if (not re.fullmatch(r'v2long:(identify|refine):P[0-9]{3}',job_id)
        or parts[2] not in config['phase_photo_ids']):
        raise ValueError('Only unfinished-phase identify or refine jobs are supported')
    directory = Path(root)/recovery.FULL/'photos'/parts[2]
    observation = v2.read(directory/'observations.json', {})
    machines = v2.validate_observation(observation)['machines']
    prepared = directory/'prepared.json' if parts[1]=='identify' else directory/'refinement_inputs.json'
    candidate_map = v2.read(prepared, {})['initial_candidates' if parts[1]=='identify' else 'expanded_candidates']
    targets = machines if parts[1]=='identify' else [target for target in machines if target['object_id'] in candidate_map]
    if not candidate_map or set(candidate_map) != {target['object_id'] for target in targets}:
        raise ValueError('Saved candidate context does not match the physical machines')
    for candidates in candidate_map.values():
        if (not isinstance(candidates,list) or not candidates or any(not isinstance(value,str) for value in candidates)
            or len(set(candidates))!=len(candidates) or any(value not in config['catalogue_order'] for value in candidates)):
            raise ValueError('Invalid saved candidate map')
    cards = v2.read(Path(root)/'data/reference_cards_v2.json', {})['products']
    negatives = {key for key,card in cards.items() if card['in_catalog'] is False}
    return targets, candidate_map, negatives, {str(file.relative_to(root)):v2.sha(file)
                                             for file in (directory/'observations.json',prepared)}


def repair(job_id, *, apply=False, root=ROOT):
    root = Path(root)
    config = v2.read(root/recovery.CONFIG, {})
    recovery.verify_config(config, root)
    for name, expected in config['prior_phase_evidence'].items():
        if v2.sha(root/recovery.NEW/'prior_phase_snapshot'/name) != expected:
            raise ValueError('Previous phase snapshot changed')
    if v2.read(root/recovery.NEW/'inflight.json', {}):
        raise ValueError('A request remains in flight')
    path = root/recovery.NEW/'calls.jsonl'
    records = recovery.ledger(path)
    matching = [(index,row) for index,row in enumerate(records,1) if row.get('logical_job_id',row['job_id'])==job_id]
    if not matching or matching[-1][1]['status']!='validation_error' or matching[-1][1].get('error')!='Invalid top two':
        raise ValueError('Only the latest exact Invalid top two validation failure can be repaired')
    original = [(index,row) for index,row in matching if row['status']=='ok' and row['cost_basis']!='offline_validation_recovery']
    if len(original)!=1:
        raise ValueError('Expected one original paid successful response')
    line, original = original[0]
    failure = matching[-1][1]
    if records[-1] != failure:
        raise ValueError('A later ledger event prevents this bounded repair')
    policy = v2.read(root/POLICY, {})
    targets, candidates, negatives, context_hashes = load_context(job_id, config, root)
    if (policy.get('job_prefix')!='v2long:' or not job_id.startswith(policy['job_prefix'])
        or job_id.split(':')[1] not in policy.get('allowed_stages', [])
        or job_id.split(':')[2] not in config['phase_photo_ids'] or policy.get('allowed_error')!='Invalid top two'
        or policy.get('allowed_status')!='not_sure' or policy.get('new_paid_requests')!=0
        or set(policy.get('known_non_catalogue_ids', []))!=negatives
        or policy.get('invent_guesses') is not False
        or policy.get('use_existing_offline_validation_recovery') is not True):
        raise ValueError('Repair does not match the recorded normalisation policy')
    def validator(raw):
        return normalise_batch(raw, targets, candidates, negatives, config['confidence_threshold'])
    normalised = validator(original['result'])
    receipt = {'job_id':job_id,'helper_source_sha256':v2.sha(Path(__file__)),
               'policy_file':str(POLICY),'policy_sha256':v2.sha(root/POLICY),
               'original_response_line':line,'original_record_sha256':digest(encoded(original)),
               'validation_failure_sha256':digest(encoded(failure)),
               'original_provider_response_sha256':digest(encoded(original['provider_response'])),
               'request_sha256':original['request_sha256'],'config_sha256':original['config_sha256'],
               'normalisation_policy':NORMALISATION,'context_sha256':context_hashes,
               'removed_ids':{item['object_id']:item['unverified_alternatives'] for item in normalised['results'] if item.get('unverified_alternatives')},
               'normalised_result_sha256':digest(encoded(normalised)),
               'paid_requests':0,'additional_cost_usd':0}
    if apply:
        receipt_path = root/receipt_file(job_id)
        if receipt_path.exists():
            raise ValueError('Immutable validation repair receipt already exists')
        before = path.read_bytes()
        client = Client(config, root, root/recovery.NEW, **config['rate_limit_policy'])
        recovered = client.recover_validation(job_id, validator)
        if recovered != normalised or not path.read_bytes().startswith(before):
            raise RuntimeError('Offline recovery did not preserve the original ledger prefix')
        receipt['recovery_record_sha256'] = digest(encoded(recovery.ledger(path)[-1]))
        receipt['recorded_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        receipt_path.parent.mkdir(parents=True,exist_ok=True)
        with receipt_path.open('x') as target:
            json.dump(receipt,target,indent=2,ensure_ascii=False);target.write('\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair',action='store_true')
    parser.add_argument('--job',required=True)
    args = parser.parse_args()
    with (ROOT/'out/pipeline/run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(repair(args.job,apply=args.repair,root=ROOT)),flush=True)


if __name__=='__main__':main()
