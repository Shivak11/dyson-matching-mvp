"""Read P054 and the remaining unsure photos with OpenRouter Mistral OCR only."""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from run_pipeline import ROOT,save,sha
from run_failure_recovery import ledger,query_crop
from run_slow_comparison import verify_history
from openrouter_ocr import OCRClient,read_crop

OUT=Path('out/targeted_ocr')
CONFIG=Path('data/targeted_ocr_config.json')
PREVIOUS=Path('data/focused_recovery_config.json')
PRIOR=Path('out/failure_recovery_completion')
FOCUSED=Path('out/focused_recovery')


def read(path,default=...):
    path=Path(path)
    return json.loads(path.read_text()) if path.exists() or default is ... else default


def stamp():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())


def parse_annotations(response,model):
    choice,=response['choices']
    if choice.get('finish_reason')!='stop':raise ValueError('Incomplete OCR processing response')
    if response.get('usage',{}).get('prompt_tokens',model['input_token_bound']+1)>model['input_token_bound']:
        raise ValueError('OCR input exceeds its reserved bound')
    files=[a['file'] for a in choice['message'].get('annotations',[]) if a.get('type')=='file' and isinstance(a.get('file'),dict)]
    if len(files)!=1 or not isinstance(files[0].get('hash'),str) or not files[0]['hash']:
        raise ValueError('Independent server file-parser annotation is missing')
    content=files[0].get('content')
    if not isinstance(content,list) or any(not isinstance(p,dict) for p in content):raise ValueError('Invalid server OCR content')
    texts=[p['text'] for p in content if p.get('type')=='text' and isinstance(p.get('text'),str)]
    return {'literal_texts':texts,'no_text_extracted':not any(t.strip() for t in texts),
       'annotation_file_hash':files[0]['hash'],'engine':'mistral-ocr',
       'evidence_source':'OpenRouter server file-parser annotations; downstream answer excluded'}


def extract(client,job,jpeg):
    class Request:
        config=client.config
        def _call(self,*args):return args
    args=read_crop(Request(),job,jpeg)
    return client._call(*args[:-1],lambda response:parse_annotations(response,client.config['models']['ocr']))


def text_candidates(texts):
    text='\n'.join(texts)
    codes=sorted(set(re.findall(r'(?<!\d)\d{6}-\d{2}(?!\d)',text)))
    models=sorted(set(m.group(0) for m in re.finditer(r'(?i)\b(?:gen\s*5\s*detect|wash\s*g1|v(?:8|11|12|15|16)(?:\s+(?:detect\s+slim|detect|piston\s+animal))?|CY23|shark\s+stratos)\b',text)))
    return {'possible_model_strings':models,'possible_part_codes':codes,'manufacturer_verified':False,'body_identity_accepted':False}


def verify(config,root=ROOT):
    root=Path(root)
    if len(config['previous_ledgers'])!=10 or len({x['file'] for x in config['previous_ledgers']})!=10:
        raise ValueError('Ten historical ledgers must be counted once')
    for name,expected in config['frozen_files'].items():
        if sha(root/name)!=expected:raise ValueError('Frozen OCR input changed: '+name)
    if config['models']['ocr']['provider']!='openrouter':raise ValueError('OCR must use OpenRouter')
    return verify_history(config,root)


def prepare(root=ROOT):
    root=Path(root)
    if (root/CONFIG).exists():raise ValueError('Targeted OCR inputs already frozen')
    def audit(path,expected_status):
        proc=subprocess.run([sys.executable,str(root/path),'--root',str(root)]+(['--require-complete'] if expected_status=='PASS' else []),capture_output=True,text=True)
        value=json.loads(proc.stdout)
        if value['audit_status']!=expected_status:raise ValueError('Historical audit state changed')
        return value
    completed=audit(PRIOR/'independent_audit.py','PASS')
    stopped=audit(FOCUSED/'independent_audit.py','FAIL')
    if stopped['errors']!=['A terminal error or validation failure is unresolved'] or stopped['completed_photo_count']!=0 or stopped['transport']['pending']:
        raise ValueError('The stopped focused phase has a different blocker')
    previous=read(root/PREVIOUS);history=copy.deepcopy(previous['previous_ledgers'])
    calls=root/FOCUSED/'calls.jsonl'
    if len(ledger(calls))!=1 or ledger(calls)[0]['error']!='Incomplete provider result: length':raise ValueError('Expected one preserved preflight truncation')
    history.append({'file':str(calls.relative_to(root)),'sha256':sha(calls),
                    'accounted_cost_usd':sum(r['estimated_cost_usd'] for r in ledger(calls))})
    cases=[p['image_id'] for p in completed['scores']['aligned_reference']['failures']['per_photo'] if not p['correct']]
    if len(cases)!=14 or 'P054' not in cases:raise ValueError('Unexpected selected OCR cohort')
    ids=['P054']+[i for i in cases if i!='P054'];items={}
    for image_id in ids:
        initial=read(root/FOCUSED/'photos'/image_id/'initial.json')
        targets=initial['inventory']['machines']
        if len(targets)!=1:raise ValueError('The frozen OCR cohort needs one physical target per photo')
        original=previous['photo_inputs'][image_id]
        items[image_id]={'query_file':original['query_file'],'query_sha256':original['query_sha256'],
                        'object_id':targets[0]['object_id'],'query_box_2d':targets[0]['box_2d']}
    save(root/OUT/'admission_audits.json',{'prior_complete':completed,'focused_stopped':stopped})
    prior=sum(x['accounted_cost_usd'] for x in history)*100
    model=copy.deepcopy(previous['models']['ocr'])
    reserve=(model['input_token_bound']*model['input_usd_per_million']+model['max_output_tokens']*model['output_usd_per_million'])/1e6+2*model['maximum_parser_fee_usd']
    if 14*reserve*100>1000-prior:raise ValueError('Selected OCR requests exceed remaining budget')
    frozen=copy.deepcopy(previous['frozen_files'])
    paths=[PREVIOUS,Path('tools/run_targeted_ocr.py'),Path('tests/test_targeted_ocr.py'),Path('docs/plan-targeted-ocr.md'),OUT/'admission_audits.json']
    paths += [p.relative_to(root) for p in (root/FOCUSED).rglob('*') if p.is_file()]
    for name in paths:
        current=sha(root/name)
        if str(name) in frozen and frozen[str(name)]!=current:raise ValueError('An inherited frozen input changed')
        frozen[str(name)]=current
    config={'study_id':'targeted-openrouter-mistral-ocr','scope':ids,'photo_inputs':items,'models':{'ocr':model},
      'previous_ledgers':history,'stage_ceiling_inr':1000,'prior_stage_accounted_inr':42.68,
      'budget':{'usd_inr':100,'stage_max_inr':1000-prior,'total_max_inr':2000,'prior_accounted_inr':prior+42.68},
      'reporting_usd_inr':previous['reporting_usd_inr'],'rate_limit_policy':previous['rate_limit_policy'],
      'frozen_files':frozen,'maximum_first_attempts_guard_inr':14*reserve*100,'full58_retested':False}
    save(root/CONFIG,config);verify(config,root);return config


def report(config,root=ROOT):
    out=Path(root)/OUT;calls=ledger(out/'calls.jsonl');settled={r['job_id'] for r in calls}
    pending={k:v for k,v in read(out/'inflight.json',{}).items() if k not in settled}
    results=read(out/'results.json',[]);spent=sum(r['estimated_cost_usd'] for r in calls)
    reserve=sum(r['reserved_cost_usd'] for r in pending.values());prior=sum(x['accounted_cost_usd'] for x in config['previous_ledgers'])
    board={'selected_count':len(config['scope']),'completed_count':len(results),'completed_ids':[r['image_id'] for r in results],
      'photos_with_text':sum(not r['ocr']['no_text_extracted'] for r in results),
      'photos_with_specific_candidate':sum(bool(r['candidates']['possible_model_strings'] or r['candidates']['possible_part_codes']) for r in results),
      'accepted_body_identities':0,'full58_matching_accuracy_retested':False,
      'costs':{'new_accounted_usd':spent+reserve,'new_reporting_inr':(spent+reserve)*config['reporting_usd_inr'],
        'new_guard_inr':(spent+reserve)*100,'pending_reserve_usd':reserve,
        'retained_parser_fee_reserve_usd':sum(r.get('ocr_parser_fee_reserve_usd',0) for r in calls),
        'combined_stage_guard_inr':(prior+spent+reserve)*100,'remaining_guard_inr':1000-(prior+spent+reserve)*100,
        'overall_guard_inr':config['budget']['prior_accounted_inr']+(spent+reserve)*100}}
    save(out/'scoreboard.json',board);return board


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--preflight',action='store_true')
    args=p.parse_args()
    if args.prepare and args.run:p.error('Preparation is separate from paid calls')
    if args.preflight and not args.run:p.error('Preflight needs --run')
    with (ROOT/'out/pipeline/run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config=prepare() if args.prepare else read(ROOT/CONFIG)
        history=verify(config)
        if args.prepare:print(json.dumps({'status':'prepared','scope':config['scope'],'maximum_guard_inr':config['maximum_first_attempts_guard_inr']}));return
        if not args.run:print(json.dumps(report(config)));return
        client=OCRClient(config,ROOT,ROOT/OUT,**config['rate_limit_policy'])
        latest=max((r.get('request_finished_unix',0) for r in history),default=0)
        if latest:client.last_request_finished_at=max(client.last_request_finished_at or float('-inf'),time.monotonic()-max(0,time.time()-latest))
        results=read(ROOT/OUT/'results.json',[]);completed={r['image_id'] for r in results};error=None;started=stamp()
        try:
            for image_id in config['scope'][:1] if args.preflight else config['scope']:
                if image_id in completed:continue
                item=config['photo_inputs'][image_id];directory=ROOT/OUT/'photos'/image_id
                crop=query_crop(ROOT/item['query_file'],item['query_box_2d'],directory/'object.jpg',ROOT,1536)
                save(directory/'crop.json',crop)
                extracted=extract(client,'ocr14:'+image_id,ROOT/crop['file'])
                result={'image_id':image_id,'object_id':item['object_id'],'query_box_2d':item['query_box_2d'],
                     'location_kind':'submitted original-image crop; no per-character boxes','crop':crop,
                     'ocr':extracted,'candidates':text_candidates(extracted['literal_texts'])}
                save(directory/'ocr.json',result);results.append(result);save(ROOT/OUT/'results.json',results)
                report(config);print(json.dumps({'photo':image_id,'completed':len(results),'no_text':extracted['no_text_extracted'],
                                                'candidates':result['candidates']}),flush=True)
        except Exception as exc:
            error=str(exc);save(ROOT/OUT/'blocker.json',{'error':error,'attempted':'One paced OpenRouter Mistral file-parser request per selected original object crop; no fallback or native/local OCR.'})
        finally:
            score=report(config)
            save(ROOT/OUT/'run_receipt.json',{'status':'stopped' if error else 'preflight_completed' if args.preflight else 'completed',
              'started_utc':started,'settled_utc':stamp(),'completed_count':len(results),'workers':1,
              'inflight_count':len(client.pending),'error':error,'costs':score['costs']})
        if error:raise SystemExit('Stopped: '+error)


if __name__=='__main__':main()
