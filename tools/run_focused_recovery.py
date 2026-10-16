"""Run the separately frozen focused recovery experiment through OpenRouter."""
import argparse
import copy
import fcntl
import json
import re
import subprocess
import sys
from pathlib import Path
import time

from run_pipeline import ROOT, read as read_optional, save, sha
from openrouter_ocr import OCRClient as Client
from run_slow_comparison import verify_history
from run_failure_recovery import ledger, query_crop, generate, raw_rows
from openrouter_ocr import read_crop
from evaluate_pipeline import evaluate
from focused_protocol import (eligible_target, plan_focus, predicate_prompt, validate_predicates,
                              final_prompt, validate_final)

OUT=Path('out/focused_recovery')
CONFIG=Path('data/focused_recovery_config.json')
FACTS=Path('data/focused_manufacturer_facts.json')
PREVIOUS=Path('data/failure_control_completion_config.json')
COMPLETED=Path('out/failure_recovery_completion')
OLD=Path('out/failure_recovery')


def read(path,default=...):
    return json.loads(Path(path).read_text()) if default is ... else read_optional(path,default)


def stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())


def source_directory(image_id,root=ROOT):
    recent=Path(root)/COMPLETED/'photos'/image_id
    return recent if (recent/'inventory.json').exists() else Path(root)/OLD/'photos'/image_id


def inputs(image_id,root=ROOT):
    directory=source_directory(image_id,root)
    inventory=read(directory/'inventory.json')
    compared=read(directory/'comparison.json',{})
    rankings={key:value['raw']['decision']['top_two'] for key,value in compared.items()}
    return inventory,compared,rankings


def reservation(model):
    return (model['input_token_bound']*model['input_usd_per_million']+
            model['max_output_tokens']*model['output_usd_per_million'])/1e6


def verify_config(config,root=ROOT):
    root=Path(root)
    for name,expected in config['frozen_files'].items():
        if sha(root/name)!=expected:raise ValueError('Frozen focused input changed: '+name)
    if len(config['previous_ledgers'])!=9 or len({x['file'] for x in config['previous_ledgers']})!=9:
        raise ValueError('Nine previous ledgers must be counted once')
    if any(m['provider']!='openrouter' for m in config['models'].values()):
        raise ValueError('Every model, including text reading, must use OpenRouter')
    return verify_history(config,root)


def prepare(root=ROOT):
    root=Path(root)
    if (root/CONFIG).exists():raise ValueError('Focused configuration already frozen')
    check=subprocess.run([sys.executable,str(root/COMPLETED/'independent_audit.py'),'--root',str(root),'--require-complete'],capture_output=True,text=True)
    if check.returncode:raise ValueError('Fresh prior-phase audit failed: '+check.stdout[-2000:])
    audit=json.loads(check.stdout)
    save(root/OUT/'admission_audit.json',audit)
    if audit.get('audit_status')!='PASS' or audit.get('combined_completed_photo_count')!=23:
        raise ValueError('A completed audited prior experiment is required')
    previous=read(root/PREVIOUS);facts=read(root/FACTS)
    failures=[p['image_id'] for p in audit['scores']['aligned_reference']['failures']['per_photo'] if not p['correct']]
    controls=previous['scope']['control_ids'];ids=failures+controls
    if len(failures)!=14 or len(ids)!=len(set(ids)):raise ValueError('Unexpected next cohort')
    history=copy.deepcopy(previous['previous_ledgers'])
    old_ledger=root/COMPLETED/'calls.jsonl'
    history.append({'file':str(old_ledger.relative_to(root)),'sha256':sha(old_ledger),
                    'accounted_cost_usd':sum(x['estimated_cost_usd'] for x in ledger(old_ledger))})
    prior=sum(x['accounted_cost_usd'] for x in history)*100
    flash=copy.deepcopy(previous['models']['inventory'])
    flash.update(input_token_bound=20000,max_output_tokens=16384,request_timeout_seconds=600)
    final=copy.deepcopy(flash);final['input_token_bound']=28000
    sol=copy.deepcopy(read(root/'data/pipeline_slow_comparison_config.json')['models']['solhigh'])
    sol.update(input_token_bound=16000,max_output_tokens=8192,cached_input_usd_per_million=.1)
    ocr={'provider':'openrouter','model':'qwen/qwen3.7-flash','provider_only':['alibaba'],
         'input_token_bound':6000,'max_output_tokens':128,'input_usd_per_million':.03,
         'output_usd_per_million':.13,'cached_input_usd_per_million':.006,
         'maximum_parser_fee_usd':.01,'request_timeout_seconds':240}
    models={'predicates':flash,'checker':sol,'final':final,'ocr':ocr}
    manifest={p['image_id']:p for p in read(root/'data/test/test_manifest.json')}
    photo_inputs={};body_ids=[];tool_ids=[]
    for image_id in ids:
        inventory,baseline,rankings=inputs(image_id,root)
        plan=plan_focus(inventory['machines'],baseline,rankings,facts)
        directory=root/OUT/'photos'/image_id
        save(directory/'plan.json',plan)
        save(directory/'initial.json',{'inventory':inventory,'comparison':baseline})
        source=source_directory(image_id,root)
        photo_inputs[image_id]={'source_directory':str(source.relative_to(root)),
            'query_file':manifest[image_id]['file'],'query_sha256':sha(root/manifest[image_id]['file']),
            'target_ids':[t['object_id'] for t in inventory['machines']],
            'eligible_ids':[t['object_id'] for t in inventory['machines'] if eligible_target(t)],
            'active_ids':plan['active_ids']}
        (body_ids if plan['active_ids'] else tool_ids).append(image_id)
    maximum=len(body_ids)*(sum(reservation(m) for m in models.values())+2*ocr['maximum_parser_fee_usd'])*100
    if maximum>1000-prior+1e-8:raise ValueError('Planned worst case exceeds remaining allowance')
    frozen=copy.deepcopy(previous['frozen_files'])
    paths=[PREVIOUS,FACTS,Path('tools/run_focused_recovery.py'),Path('tools/focused_protocol.py'),
           Path('tests/test_focused_recovery.py'),Path('tests/test_focused_protocol.py'),Path('tools/openrouter_ocr.py'),
           Path('tests/test_openrouter_ocr.py'),OUT/'admission_audit.json',Path('PLAN.md')]
    paths += [p.relative_to(root) for p in (root/COMPLETED).rglob('*') if p.is_file()]
    paths += [p.relative_to(root) for p in (root/OUT/'photos').rglob('*.json')]
    for name in paths:
        current=sha(root/name)
        if str(name) in frozen and frozen[str(name)]!=current:raise ValueError('Inherited input changed')
        frozen[str(name)]=current
    config={'study_id':'focused-recovery-v4','scope':{'failure_ids':failures,'control_ids':controls,'photo_ids':ids},
      'photo_inputs':photo_inputs,'body_ids':body_ids,'tool_only_ids':tool_ids,'models':models,
      'confidence_threshold':90,'catalogue_order':previous['catalogue_order'],'previous_ledgers':history,
      'stage_ceiling_inr':1000,'prior_stage_accounted_inr':previous['prior_stage_accounted_inr'],
      'budget':{'usd_inr':100,'stage_max_inr':1000-prior,'total_max_inr':2000,
                'prior_accounted_inr':prior+previous['prior_stage_accounted_inr']},
      'reporting_usd_inr':previous['reporting_usd_inr'],'rate_limit_policy':previous['rate_limit_policy'],
      'maximum_planned_guard_inr':maximum,'frozen_files':frozen,
      'ocr_route':'conditional OpenRouter Mistral file-parser, with independently blinded Sol visual checks; no native/local OCR',
      'full58_retested':False,'new_photographs':False}
    save(root/CONFIG,config);verify_config(config,root)
    return config


def image_inputs(image_id,plan,config,root=ROOT,observations=None):
    root=Path(root);directory=root/OUT/'photos'/image_id;source=root/config['photo_inputs'][image_id]['query_file']
    records=[];images=[]
    def crop(label,box,name,maximum=1024):
        record=query_crop(source,box,directory/name,root,maximum)
        records.append({'label':label,**record});images.append((label,root/record['file']))
    crop('WHOLE SCENE',[0,0,1000,1000],'scene.jpg',1536)
    for target in plan['targets']:
        if target['object_id'] not in plan['active_ids']:continue
        key=target['object_id'];crop('TARGET '+key,target['box_2d'],key+'_body.jpg')
        visible=[f for f in target.get('observations',[]) if f.get('visible') and f['feature'] not in ('cleaner_head','wand')]
        for index,f in enumerate(visible[:3]):
            crop('TARGET '+key+' DETAIL '+str(index),f['box_2d'],key+'_detail_'+str(index)+'.jpg')
    if observations:
        for index,o in enumerate(observations['observations']):
            if o['state']=='present' and o.get('needs_check') and o['box_2d']:
                crop('QUESTION '+o['question_id'],o['box_2d'],'focus_'+str(index)+'.jpg')
    panels=read(root/OLD/'reference_panels.json');aliases=set(a for group in plan['focus_refs'].values() for a in group)
    for panel in panels['images']:
        if panel['panel_id'].split('-')[0] in aliases:
            images.append((panel['panel_id'],root/panel['file']))
    return images,records


def checker_questions(plan,observations,baseline,rankings,facts):
    return plan_focus(plan['targets'],baseline,rankings,facts,observations=observations)['check_question_ids']


def passive_rows(image_id,targets,catalogue):
    return [{'image_id':image_id,'instance_id':image_id+'_'+t['object_id'],'model':'focused_v4',
             'variant':'focused_recovery','candidates':catalogue,'comparison_skipped':True,
             'decision':{'status':'not_sure','product':None,'confidence':0,'top_two':[],
               'evidence':[],'missing_evidence':['Only a component or insufficient identifying body evidence is available.'],
               'contradictions':[],'retake':''},'compatibility_only':True}
            for t in targets]


def run_photo(client,config,image_id,root=ROOT):
    root=Path(root);directory=root/OUT/'photos'/image_id;facts=read(root/FACTS)
    plan=read(directory/'plan.json');initial=read(directory/'initial.json')
    targets=initial['inventory']['machines']
    passive=[t for t in targets if t['object_id'] not in plan['active_ids']]
    rows=passive_rows(image_id,passive,config['catalogue_order'])
    if not plan['active_ids']:
        save(directory/'compatibility.json',{'exact_verified_part_code':None,'body_identified':False,
            'reason':'No plausible non-generic identifier in the saved candidate-free inventory; shared accessory compatibility cannot identify an unseen body.',
            'manufacturer_sets':facts['compatibility'],'new_paid_calls':0})
        return targets,rows
    images,records=image_inputs(image_id,plan,config,root)
    save(directory/'predicate_images.json',records)
    observations=generate(client,'v4:predicates:'+image_id,'predicates',predicate_prompt(plan),images,
                          lambda raw:validate_predicates(raw,plan))
    save(directory/'observations.json',observations)
    rankings={key:value['raw']['decision']['top_two'] for key,value in initial['comparison'].items()}
    questions=checker_questions(plan,observations,initial['comparison'],rankings,facts)
    save(directory/'checker_questions.json',questions)
    # The checker receives only fixed questions and pixels, never the first model's answers.
    checks={'observations':[]}
    images,records=image_inputs(image_id,plan,config,root,observations)
    save(directory/'focused_images.json',records)
    if questions:
        checks=generate(client,'v4:checker:'+image_id,'checker',predicate_prompt(plan,questions),images,
                        lambda raw:validate_predicates(raw,plan,question_ids=questions))
        save(directory/'independent_checks.json',checks)
    ocr=[]
    for observation in observations['observations']:
        if (observation['question_id'].endswith('__identifier') and observation['state']=='present'
            and (observation['needs_check'] or re.search(r'(?i)\b(?:V\d{1,2}|GEN\s*5|CY\d+|SV\d+|\d{6}-\d{2})\b',observation['literal_text']))):
            crop=query_crop(root/config['photo_inputs'][image_id]['query_file'],observation['box_2d'],directory/'text_region.jpg',root,1536)
            literal=read_crop(client,'v4:ocr:'+image_id,root/crop['file'])
            ocr.append({'object_id':observation['object_id'],'query_box_2d':observation['box_2d'],
                        'location_kind':'submitted original-image crop, not individual character boxes','crop':crop,**literal})
            break
    save(directory/'ocr.json',ocr)
    facts={**facts,'ocr_evidence':ocr}
    compared=generate(client,'v4:final:'+image_id,'final',final_prompt(plan,observations,checks,facts),images,
        lambda raw:validate_final(raw,plan,observations,checks,facts,facts['references'],config['confidence_threshold']))
    save(directory/'comparison.json',compared)
    rows += [{'image_id':image_id,'instance_id':image_id+'_'+key,'model':'focused_v4','variant':'focused_recovery',
              'candidates':config['catalogue_order'],**value} for key,value in compared.items()]
    if {r['instance_id'] for r in rows}!={image_id+'_'+t['object_id'] for t in targets}:
        raise ValueError('Focused results lost an independent physical target')
    return targets,rows


def report(config,root=ROOT):
    root=Path(root);out=root/OUT
    manifest=[p for p in read(root/'data/test/test_manifest.json') if p['image_id'] in config['scope']['photo_ids']]
    results=read(out/'results.json',[]);detections=read(out/'detections.json',{})
    complete=read(out/'completed_photos.json',[])
    calls=ledger(out/'calls.jsonl');pending=read(out/'inflight.json',{})
    settled={r['job_id'] for r in calls};spent=sum(r['estimated_cost_usd'] for r in calls)
    reserve=sum(r['reserved_cost_usd'] for k,r in pending.items() if k not in settled)
    prior=sum(p['accounted_cost_usd'] for p in config['previous_ledgers'])
    summaries={name:evaluate([p for p in manifest if p['image_id'] in ids],[r for r in results if r['image_id'] in ids],config['catalogue_order'],{k:v for k,v in detections.items() if k in ids})
      for name,ids in [('failures',config['scope']['failure_ids']),('controls',config['scope']['control_ids']),('all_selected',config['scope']['photo_ids'])]}
    result={'scope':config['scope'],'summaries':summaries,'completed_count':len(complete),'completed_ids':complete,
      'full58_accuracy_retested':False,'costs':{'new_accounted_usd':spent+reserve,'new_reporting_inr':(spent+reserve)*config['reporting_usd_inr'],
        'new_guard_inr':(spent+reserve)*100,'new_pending_reserve_usd':reserve,
        'combined_stage_guard_inr':(prior+spent+reserve)*100,'remaining_guard_inr':1000-(prior+spent+reserve)*100,
        'overall_guard_inr':config['budget']['prior_accounted_inr']+(spent+reserve)*100}}
    save(out/'scoreboard.json',result);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--run',action='store_true');parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    if args.prepare and args.run:parser.error('Preparation is separate from paid execution')
    if args.preflight and not args.run:parser.error('Preflight requires --run')
    with (ROOT/'out/pipeline/run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config=prepare() if args.prepare else read(ROOT/CONFIG,{})
        old=verify_config(config)
        if args.prepare:print(json.dumps({'status':'prepared','body_ids':config['body_ids'],'tool_only_ids':config['tool_only_ids'],
             'maximum_guard_inr':config['maximum_planned_guard_inr'],'remaining_guard_inr':config['budget']['stage_max_inr']}));return
        if not args.run:print(json.dumps(report(config)['costs']));return
        if (ROOT/OUT/'STOP').exists():raise ValueError('Focused STOP marker is present')
        client=Client(config,ROOT,ROOT/OUT,**config['rate_limit_policy'])
        historical_finish=max((r.get('request_finished_unix',0) for r in old),default=0)
        if historical_finish:
            elapsed=max(0,time.time()-historical_finish)
            client.last_request_finished_at=max(client.last_request_finished_at or float('-inf'),time.monotonic()-elapsed)
        results=read(ROOT/OUT/'results.json',[]);detections=read(ROOT/OUT/'detections.json',{})
        completed=read(ROOT/OUT/'completed_photos.json',[]);error=None;started=stamp()
        selected=config['scope']['photo_ids']
        if args.preflight:selected=config['body_ids'][:1]
        try:
            for image_id in selected:
                if image_id in completed:continue
                targets,rows=run_photo(client,config,image_id)
                detections[image_id]=[{**t,'instance_id':image_id+'_'+t['object_id']} for t in targets]
                results=[r for r in results if r['image_id']!=image_id]+raw_rows(rows,read(ROOT/FACTS)['references'])+rows
                for r in results:
                    if r['variant']=='reference_raw':r['variant']='focused_raw'
                save(ROOT/OUT/'results.json',results);save(ROOT/OUT/'detections.json',detections)
                completed.append(image_id);save(ROOT/OUT/'completed_photos.json',completed)
                report(config)
                print(json.dumps({'photo':image_id,'completed':len(completed),'decisions':[r['decision'] for r in rows]}),flush=True)
        except Exception as exc:
            error=str(exc);save(ROOT/OUT/'blocker.json',{'error':error,'attempted':'Frozen focused observations, conditional blinded OpenRouter Sol check, unchanged comparison gate plus uniqueness; one paced worker and no fallback.'})
        finally:
            board=report(config)
            save(ROOT/OUT/'run_receipt.json',{'status':'stopped' if error else 'preflight_completed' if args.preflight else 'completed',
               'started_utc':started,'settled_utc':stamp(),'completed_count':len(completed),'selected_ids':selected,
               'workers':1,'inflight_count':len(client.pending),'error':error,'costs':board['costs']})
        if error:raise SystemExit('Stopped: '+error)


if __name__=='__main__':main()
