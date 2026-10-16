"""Complete only the stopped P019 control with the authorised larger output cap."""
import argparse
from contextlib import contextmanager
import copy
import fcntl
import json
from pathlib import Path
import shutil
import time

import run_failure_recovery as runner
from pipeline_api import Client, digest, encoded, parse_generation, positive
from run_slow_comparison import verify_history

ROOT=runner.ROOT
OLD=runner.OUT
OLD_CONFIG=runner.CONFIG
NEW=Path('out/failure_recovery_completion')
CONFIG=Path('data/failure_control_completion_config.json')
DECISION=Path('data/failure_control_recovery_decision.json')
INVENTORY='v3:inventory:P019'
FAILED='v3:compare:P019'
RETRY='v3long:compare:P019'
OUTPUTS=('results.json','detections.json','completed_photos.json')


def spent(records):
    return sum(positive(row['estimated_cost_usd'],'recorded cost',True) for row in records)


def stopped_phase(previous,root=ROOT):
    root=Path(root)
    if encoded(previous)!=encoded(runner.read(root/OLD/'frozen_config.json',{})):
        raise ValueError('Old configuration differs from its activated copy')
    if runner.read(root/OLD/'inflight.json',{}):raise ValueError('Old request remains in flight')
    records=runner.ledger(root/OLD/'calls.jsonl')
    if not records:raise ValueError('Missing stopped P019 request')
    failed=records[-1];choices=failed.get('provider_response',{}).get('choices',[])
    receipt=runner.read(root/OLD/'run_receipt.json',{})
    if (failed.get('logical_job_id')!=FAILED or failed.get('status')!='error' or failed.get('http_status')!=200
        or failed.get('error')!='Incomplete provider result: length' or len(choices)!=1
        or choices[0].get('finish_reason')!='length' or choices[0].get('native_finish_reason')!='MAX_TOKENS'
        or failed.get('config_sha256')!=digest(encoded(previous)) or receipt.get('status')!='stopped'
        or receipt.get('inflight_count')!=0 or receipt.get('error')!=failed['job_id']+': '+failed['error']):
        raise ValueError('Only the settled P019 output-limit failure permits completion')
    latest={row.get('logical_job_id',row['job_id']):row for row in records}
    if any(row['status']!='ok' and job!=FAILED for job,row in latest.items()):
        raise ValueError('Another failed request cannot be reset')
    completed=runner.read(root/OLD/'completed_photos.json',[])
    if (len(completed)!=22 or len(set(completed))!=22 or set(completed)!=set(previous['scope']['photo_ids'])-{'P019'}
        or receipt.get('completed_count')!=22 or not {'P006','P014'}<=set(completed)
        or abs(receipt.get('costs',{}).get('new_accounted_usd',-1)-spent(records))>1e-10):
        raise ValueError('The stopped phase must preserve exactly 22 completed photos')
    score=runner.read(root/OLD/'scoreboard.json',{})
    controls={row['image_id']:row for row in score.get('transitions',[]) if row.get('cohort')=='control'}
    if any(not controls.get(name,{}).get('new_correct') or not controls[name].get('completed') for name in ('P006','P014')):
        raise ValueError('The two completed controls must remain correct')
    return records


def build_config(previous,root=ROOT):
    root=Path(root);runner.verify_config(previous,root);records=stopped_phase(previous,root)
    decision=runner.read(root/DECISION,{})
    required={'failed_logical_job_id':FAILED,'previous_max_output_tokens':32768,'new_max_output_tokens':65536,
              'previous_request_timeout_seconds':480,'new_request_timeout_seconds':900,
              'requested_model':'google/gemini-3.7-flash','provider_only':['google-ai-studio'],'thinking_level':'high',
              'stage_ceiling_inr':1000,'overall_ceiling_inr':2000,'automatic_fallback':False,
              'reuse_exact_inventory':True,'previous_completed_count':22,'reservation_usd':.28326}
    if any(decision.get(key)!=value for key,value in required.items()) or not decision.get('owner_instruction'):
        raise ValueError('Missing or incompatible control-completion authorisation')
    if decision.get('original_failure_sha256',digest(encoded(records[-1])))!=digest(encoded(records[-1])):
        raise ValueError('The authorised original failure changed')
    model=previous['models']['comparison']
    if (model['max_output_tokens']!=32768 or model['request_timeout_seconds']!=480
        or model['provider']!='openrouter' or model['model']!=required['requested_model']
        or model['provider_only']!=required['provider_only'] or model['thinking_level']!='high'
        or previous['stage_ceiling_inr']!=1000 or previous['budget']['total_max_inr']!=2000):
        raise ValueError('Previous model or authorised ceilings differ')
    config=copy.deepcopy(previous);config['study_id']+='-control-completion'
    config['models']['comparison'].update(max_output_tokens=65536,request_timeout_seconds=900)
    config['previous_ledgers'].append({'file':str(OLD/'calls.jsonl'),'sha256':runner.sha(root/OLD/'calls.jsonl'),
                                       'accounted_cost_usd':spent(records)})
    if len(config['previous_ledgers'])!=8 or len({row['file'] for row in config['previous_ledgers']})!=8:
        raise ValueError('All eight historical ledgers must be carried once')
    guard=sum(row['accounted_cost_usd'] for row in config['previous_ledgers'])*config['budget']['usd_inr']
    if abs(guard-decision.get('prior_stage_guard_inr',-1))>1e-8:raise ValueError('Settled guard spending changed')
    config['budget'].update(stage_max_inr=1000-guard,prior_accounted_inr=config['prior_stage_accounted_inr']+guard)
    if config['budget']['stage_max_inr']<.28326*config['budget']['usd_inr']:
        raise ValueError('Insufficient allowance for the authorised reservation')
    config['completion_photo_ids']=['P019'];config['completion_decision']=decision
    files=[root/OLD_CONFIG,root/DECISION,root/'tools/finish_failure_control.py',root/'tests/test_failure_control.py']
    files += [path for path in (root/OLD).rglob('*') if path.is_file()]
    for path in files:
        name=str(path.relative_to(root));actual=runner.sha(path)
        if name in config['frozen_files'] and config['frozen_files'][name]!=actual:
            raise ValueError('An inherited expected hash cannot be replaced: '+name)
        config['frozen_files'][name]=actual
    return config


def verify_config(config,root=ROOT):
    root=Path(root);expected=build_config(runner.read(root/OLD_CONFIG,{}),root)
    if encoded(config)!=encoded(expected):raise ValueError('Frozen completion configuration changed')
    for name,expected_hash in config['frozen_files'].items():
        if runner.sha(root/name)!=expected_hash:raise ValueError('Frozen completion input changed: '+name)
    return verify_history(config,root)


class Capture:
    """Use the unchanged request builder without a transport or ledger."""
    def __init__(self,config):self.config=config
    def _call(self,job,operation,model,payload,url,reservation,parse):
        return {'request_sha256':digest(url.encode()+b'\n'+encoded(payload)),
                'payload':payload,'reservation_usd':reservation,'timeout_seconds':model.get('request_timeout_seconds',180)}


def capture(config,job,model,prompt,images,schema=None):
    return Client.generate(Capture(config),job,model,prompt,images,schema)


def comparison_proof(previous,config,prompt,images,failed):
    old=capture(previous,FAILED,'comparison',prompt,images)
    new=capture(config,RETRY,'comparison',prompt,images)
    changed=copy.deepcopy(old['payload']);changed['max_tokens']=65536
    if (old['request_sha256']!=failed['request_sha256'] or old['payload']['max_tokens']!=32768
        or new['payload']!=changed or abs(new['reservation_usd']-.28326)>1e-12):
        raise ValueError('Comparison differs beyond the authorised output cap')
    return {'old_logical_job_id':FAILED,'new_logical_job_id':RETRY,
            'old_request_sha256':old['request_sha256'],'new_request_sha256':new['request_sha256'],
            'payload_changed_fields':{'max_tokens':{'old':32768,'new':65536}},
            'old_timeout_seconds':old['timeout_seconds'],'new_timeout_seconds':new['timeout_seconds'],
            'reservation_usd':new['reservation_usd'],'original_failed_record_sha256':digest(encoded(failed))}


def proof(path,value):
    if path.exists():
        if runner.read(path,{})!=value:raise ValueError('Saved completion proof changed: '+str(path))
    else:runner.save(path,value)


class CompletionClient(Client):
    def __init__(self,config,root,out,**kwargs):
        self.previous=runner.read(Path(root)/OLD_CONFIG,{})
        self.old_records=runner.ledger(Path(root)/OLD/'calls.jsonl')
        super().__init__(config,root,out,**kwargs)
        finished=[row['request_finished_unix'] for row in self.old_records+runner.ledger(self.calls_path)
                  if isinstance(row.get('request_finished_unix'),(int,float))]
        if finished:self.last_request_finished_at=time.monotonic()-max(0,time.time()-max(finished))

    def generate(self,job,model,prompt,images,schema=None):
        if job==INVENTORY and model=='inventory' and schema is None:
            originals=[row for row in self.old_records if row.get('logical_job_id',row['job_id'])==INVENTORY
                       and row['status']=='ok' and row.get('cost_basis')=='provider_reported_cost']
            if len(originals)!=1:raise ValueError('Exactly one original complete inventory is required')
            original=originals[0];request=capture(self.previous,job,model,prompt,images)
            if original['config_sha256']!=digest(encoded(self.previous)) or request['request_sha256']!=original['request_sha256']:
                raise ValueError('Cached inventory request changed')
            raw=parse_generation(original['provider_response'],'openrouter')
            if (original.get('http_status')!=200 or original['provider_response']['choices'][0].get('native_finish_reason')!='STOP'
                or encoded(raw)!=encoded(original['result'])
                or encoded(runner.validate_inventory(raw))!=encoded(runner.read(self.root/OLD/'photos/P019/inventory.json',{}))):
                raise ValueError('Original complete inventory changed')
            proof(self.out/'inventory_reuse_proof.json',{'job_id':job,'request_sha256':request['request_sha256'],
                  'original_record_sha256':digest(encoded(original)),'original_config_sha256':original['config_sha256'],
                  'original_raw_sha256':digest(encoded(raw)),'paid_requests':0,'additional_cost_usd':0})
            return raw
        if job!=FAILED or model!='comparison' or schema is not None:raise ValueError('Only P019 comparison is authorised')
        compared=comparison_proof(self.previous,self.config,prompt,images,self.old_records[-1])
        proof(self.out/'comparison_payload_proof.json',compared)
        return super().generate(RETRY,model,prompt,images,schema)

    def record_validation_failure(self,job,error):
        if job!=FAILED:raise ValueError('Only P019 comparison validation can be recorded')
        return super().record_validation_failure(RETRY,error)


@contextmanager
def completion_output():
    previous=runner.OUT;runner.OUT=NEW
    try:yield
    finally:runner.OUT=previous


def preserve_outputs(root=ROOT):
    root=Path(root);directory=root/NEW
    for name in OUTPUTS:
        source=root/OLD/name;snapshot=directory/'prior_outputs'/name;destination=directory/name
        snapshot.parent.mkdir(parents=True,exist_ok=True)
        if not snapshot.exists():shutil.copy2(source,snapshot)
        if snapshot.read_bytes()!=source.read_bytes():raise ValueError('Prior output snapshot changed')
        if not destination.exists():shutil.copy2(source,destination)
    old_results=runner.read(root/OLD/'results.json',[]);results=runner.read(directory/'results.json',[])
    old_completed=runner.read(root/OLD/'completed_photos.json',[]);completed=runner.read(directory/'completed_photos.json',[])
    old_detections=runner.read(root/OLD/'detections.json',{});detections=runner.read(directory/'detections.json',{})
    if (results[:len(old_results)]!=old_results or any(row.get('image_id')!='P019' for row in results[len(old_results):])
        or completed not in (old_completed,old_completed+['P019'])
        or any(detections.get(key)!=value for key,value in old_detections.items())
        or set(detections)-set(old_detections)-{'P019'}):
        raise ValueError('Completed old photo rows changed')
    return results,detections,completed


def execute(config,root=ROOT):
    root=Path(root);verify_config(config,root)
    if (root/NEW/'STOP').exists():raise RuntimeError('Completion STOP file is present')
    if runner.read(root/NEW/'inflight.json',{}):raise ValueError('A completion request remains in flight')
    results,detections,completed=preserve_outputs(root)
    client=CompletionClient(config,root,root/NEW,**config['rate_limit_policy'])
    panels=runner.read(root/OLD/'reference_panels.json',{})
    photo=next(row for row in runner.read(root/'data/test/test_manifest.json',[]) if row['image_id']=='P019')
    failure=None;started=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    with completion_output():
        try:
            if 'P019' not in completed:
                targets,rows=runner.run_photo(client,config,photo,panels,root)
                detections['P019']=[{**target,'instance_id':'P019_'+target['object_id']} for target in targets]
                results=[row for row in results if row['image_id']!='P019']+runner.raw_rows(rows,panels['references'])+rows
                runner.save(root/NEW/'detections.json',detections);runner.save(root/NEW/'results.json',results)
                completed.append('P019');runner.save(root/NEW/'completed_photos.json',completed)
        except Exception as error:
            failure=str(error);runner.save(root/NEW/'blocker.json',{'error':failure,'attempted':'One authorised P019 comparison with the unchanged protocol and larger output cap.'})
        finally:
            score=runner.report(config,root)
            retry=score['costs']['new_accounted_usd'];old=config['previous_ledgers'][-1]['accounted_cost_usd']
            score['costs'].update(completion_retry_accounted_usd=retry,whole_v3_and_retry_accounted_usd=old+retry,
                whole_v3_and_retry_reporting_inr=(old+retry)*config['reporting_usd_inr'],
                whole_v3_and_retry_guard_inr=(old+retry)*config['budget']['usd_inr'])
            runner.save(root/NEW/'scoreboard.json',score)
            receipt={'started_utc':started,'settled_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                     'status':'stopped' if failure else 'completed','completed_count':len(completed),
                     'selected_photo_ids':['P019'],'all_photo_ids':config['scope']['photo_ids'],'error':failure,
                     'inflight_count':len(client.pending),'workers':1,'costs':score['costs'],
                     'config_sha256':digest(encoded(config)),'helper_source_sha256':runner.sha(Path(__file__))}
            runner.save(root/NEW/'run_receipt.json',receipt)
    verify_config(config,root);preserve_outputs(root)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    args=parser.parse_args()
    with (ROOT/'out/pipeline/run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.prepare:
            if (ROOT/CONFIG).exists():raise ValueError('The completion configuration already exists')
            config=build_config(runner.read(ROOT/OLD_CONFIG,{}));runner.save(ROOT/CONFIG,config)
            print(json.dumps({'status':'prepared','budget':config['budget']}));return
        config=runner.read(ROOT/CONFIG,{})
        if not config:raise ValueError('Prepare and freeze the completion configuration before execution')
        verify_config(config)
        if not args.run:print(json.dumps({'status':'offline','budget':config['budget']}));return
        receipt=execute(config);print(json.dumps(receipt),flush=True)
        if receipt['error']:raise SystemExit('Stopped: '+receipt['error'])


if __name__=='__main__':main()
