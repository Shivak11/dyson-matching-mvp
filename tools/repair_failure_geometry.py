"""Suppress scene-valid comparisons outside their target without another paid request."""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import re
import time

import run_failure_recovery as runner
from failure_protocol import validate_comparison
from pipeline_api import Client, digest, encoded, parse_generation, positive

ROOT = runner.ROOT
ERROR = 'Query region must stay inside its physical target'
POLICY = ('For a scene-valid query comparison outside its physical target, preserve the full original '
          'and locator as unverified metadata, then set query_visible=false, query_box_2d=null and '
          'relation=unobserved. Downgrade visible_conflict only when its final valid conflict is removed. '
          'Preserve raw decisions and text; validate again with the actual physical targets.')


def normalise(raw, targets, references, threshold=90):
    # Validate every other schema/geometry condition before suppressing target-containment evidence.
    validate_comparison(raw,[{**target,'box_2d':[0,0,1000,1000]} for target in targets],references,threshold)
    normalised=copy.deepcopy(raw)
    by_id={target['object_id']:target for target in targets}
    changed=False
    for item in normalised['results']:
        target=by_id[item['object_id']]['box_2d']
        archived=item.get('unverified_comparisons',[])
        if not isinstance(archived,list):raise ValueError('Invalid unverified comparison metadata')
        for check in item['reference_checks']:
            removed_conflict=False
            for index,comparison in enumerate(check['comparisons']):
                box=comparison['query_box_2d']
                if not comparison['query_visible'] or (target[0]<=box[0]<box[2]<=target[2] and target[1]<=box[1]<box[3]<=target[3]):
                    continue
                archived.append({'object_id':item['object_id'],'reference':check['reference'],
                                 'comparison_index':index,'comparison':copy.deepcopy(comparison)})
                removed_conflict=removed_conflict or comparison['relation']=='conflict'
                comparison.update(query_visible=False,query_box_2d=None,relation='unobserved')
                changed=True
            if check['outcome']=='visible_conflict' and removed_conflict and not any(comparison['relation']=='conflict' for comparison in check['comparisons']):
                check['outcome']='insufficient_evidence'
        if archived:item['unverified_comparisons']=archived
    if not changed:raise ValueError('No permitted target-containment suppression exists')
    validate_comparison(normalised,targets,references,threshold)
    return normalised


def load_context(job, config, root=ROOT):
    if not isinstance(job,str) or not re.fullmatch(r'v3:compare:P[0-9]{3}',job) or job.split(':')[2] not in config['scope']['photo_ids']:
        raise ValueError('Job is outside the frozen comparison cohort')
    root=Path(root);image_id=job.split(':')[2]
    inventory_path=root/runner.OUT/'photos'/image_id/'inventory.json'
    saved=runner.read(inventory_path,{})
    inventory=runner.validate_inventory(saved)
    if encoded(inventory['machines'])!=encoded(saved.get('machines')):
        raise ValueError('Saved physical targets differ from the validated inventory')
    panels_path=root/runner.OUT/'reference_panels.json'
    references=runner.read(panels_path,{})['references']
    context={str(inventory_path.relative_to(root)):digest(encoded(saved)),
             str(panels_path.relative_to(root)):digest(encoded(runner.read(panels_path,{})))}
    return inventory['machines'],references,context


def _repair_locked(job, *, apply=False, root=ROOT):
    root=Path(root);config=runner.read(root/runner.CONFIG,{})
    runner.verify_config(config,root)
    if encoded(config)!=encoded(runner.read(root/runner.OUT/'frozen_config.json',{})):
        raise ValueError('Configuration differs from its activated frozen copy')
    targets,references,context=load_context(job,config,root)
    directory=root/runner.OUT
    if runner.read(directory/'inflight.json',{}):raise ValueError('A request remains in flight')
    path=directory/'calls.jsonl';records=runner.ledger(path)
    matching=[(line,row) for line,row in enumerate(records,1) if row.get('logical_job_id',row['job_id'])==job]
    if not matching or matching[-1][1]['status']!='validation_error' or matching[-1][1].get('error')!=ERROR or matching[-1][1]!=records[-1]:
        raise ValueError('Only the latest exact target-containment validation failure can be repaired')
    originals=[(line,row) for line,row in matching if row['status']=='ok' and row['cost_basis']=='provider_reported_cost']
    if len(originals)!=1:raise ValueError('Expected one complete physical paid response')
    line,original=originals[0];failure=matching[-1][1]
    if (original['config_sha256']!=digest(encoded(config)) or failure['config_sha256']!=original['config_sha256']
        or failure['request_sha256']!=original['request_sha256'] or original.get('http_status')!=200
        or original['requested_model']!=config['models']['comparison']['model']):
        raise ValueError('Original response or request configuration changed')
    response=original['provider_response'];choice,=response['choices']
    if choice.get('native_finish_reason')!='STOP':raise ValueError('Provider response is incomplete')
    raw=parse_generation(response,'openrouter')
    if encoded(raw)!=encoded(original['result']):raise ValueError('Saved raw JSON differs from the provider response')
    current=sum(positive(row['estimated_cost_usd'],'recorded cost',True) for row in records)*config['budget']['usd_inr']
    previous=sum(row['accounted_cost_usd'] for row in config['previous_ledgers'])*config['budget']['usd_inr']
    if current+previous>config['stage_ceiling_inr']+1e-8 or current+config['budget']['prior_accounted_inr']>config['budget']['total_max_inr']+1e-8:
        raise ValueError('Accounted spending exceeds the authorised ceiling')
    normalised=normalise(raw,targets,references,config['confidence_threshold'])
    changes=[entry for item in normalised['results'] for entry in item.get('unverified_comparisons',[])]
    receipt={'job_id':job,'helper_source_sha256':runner.sha(Path(__file__)),'policy':POLICY,
             'original_response_line':line,'original_record_sha256':digest(encoded(original)),
             'validation_failure_sha256':digest(encoded(failure)),
             'provider_response_sha256':digest(encoded(response)),'request_sha256':original['request_sha256'],
             'config_sha256':original['config_sha256'],'canonical_context_sha256':context,'hash_kind':'canonical_json',
             'normalised_result_sha256':digest(encoded(normalised)),'transformations':changes,
             'paid_requests':0,'additional_cost_usd':0}
    if apply:
        receipt_path=directory/'geometry_repairs'/(job.replace(':','_')+'.json')
        if receipt_path.exists():raise ValueError('Immutable geometry repair receipt already exists')
        before=path.read_bytes()
        client=Client(config,root,directory,**config['rate_limit_policy'])
        recovered=client.recover_validation(job,lambda saved:normalise(saved,targets,references,config['confidence_threshold']))
        if recovered!=normalised or not path.read_bytes().startswith(before):raise RuntimeError('Offline recovery changed original ledger data')
        receipt['recovery_record_sha256']=digest(encoded(runner.ledger(path)[-1]))
        receipt['recorded_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        receipt_path.parent.mkdir(parents=True,exist_ok=True)
        with receipt_path.open('x') as destination:
            json.dump(receipt,destination,indent=2);destination.write('\n')
    return receipt


def repair(job, *, apply=False, root=ROOT):
    root=Path(root)
    with (root/'out/pipeline/run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _repair_locked(job,apply=apply,root=root)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',required=True);parser.add_argument('--repair',action='store_true')
    args=parser.parse_args()
    print(json.dumps(repair(args.job,apply=args.repair,root=ROOT)),flush=True)


if __name__=='__main__':main()
