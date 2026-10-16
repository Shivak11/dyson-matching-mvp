#!/usr/bin/env python3
"""Independently audit saved failure-cohort evidence without paid calls or project writes."""
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path('/Users/shivakakkar/Python Projects/dyson-matching-mvp/.worktrees/test-set')
FEATURES={'body_layout','handle_control','bin_mechanism','display_layout','cyclone_filter','identifier','head_architecture'}


def read(path,default=None):
    return json.loads(path.read_text()) if path.exists() else default


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def ledger(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def logical(row):
    return row.get('logical_job_id',row['job_id'])


def physical(rows):
    return [r for r in rows if 'reserved_cost_usd' in r and r.get('cost_basis') not in ('offline_validation_recovery','offline_usage_bound_recovery')]


def box(value,target=None):
    assert isinstance(value,list) and len(value)==4
    assert all(not isinstance(x,bool) and isinstance(x,(int,float)) and math.isfinite(x) for x in value)
    y1,x1,y2,x2=value
    assert 0<=y1<y2<=1000 and 0<=x1<x2<=1000
    if target is not None:
        assert target[0]<=y1<y2<=target[2] and target[1]<=x1<x2<=target[3]


def intersects(a,b):
    return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])


def text(value,empty=False):
    assert isinstance(value,str) and (empty or value.strip())


def provider_json(row):
    choice,=row['provider_response']['choices']
    assert choice['finish_reason']=='stop' and choice.get('native_finish_reason')=='STOP'
    raw=json.loads(choice['message']['content'])
    assert isinstance(raw,dict) and encoded(raw)==encoded(row['result'])
    return raw


def inventory(raw):
    objects=copy.deepcopy(raw['objects'])
    assert isinstance(objects,list) and len(objects)<=20
    names=[o['object_id'] for o in objects]
    assert len(names)==len(set(names))
    by_id={o['object_id']:o for o in objects}
    for obj in objects:
        text(obj['object_id']);box(obj['box_2d'])
        assert obj['role'] in ('machine','partial_machine','accessory')
        assert obj['visibility'] in ('whole_machine','main_body','part_only')
        text(obj['readable_identifier'],True)
        obj.setdefault('parent_id',None)
        parent=obj['parent_id']
        assert obj['role']=='accessory' or parent is None
        if parent is not None:
            assert parent!=obj['object_id'] and parent in by_id and by_id[parent]['role']!='accessory'
        assert isinstance(obj['observations'],list) and len(obj['observations'])<=4
        for feature in obj['observations']:
            text(feature['feature']);text(feature['detail']);assert type(feature['visible']) is bool
            if feature['visible']:
                box(feature['box_2d']);assert intersects(feature['box_2d'],obj['box_2d'])
            else:
                assert feature.get('box_2d') is None;feature['box_2d']=None
    machines=[o for o in objects if o['role']!='accessory']
    if not machines and objects:
        bounds=[min(o['box_2d'][0] for o in objects),min(o['box_2d'][1] for o in objects),max(o['box_2d'][2] for o in objects),max(o['box_2d'][3] for o in objects)]
        machines=[{**objects[0],'role':'partial_machine','parent_id':None,'visibility':'part_only',
                   'box_2d':bounds,'accessory_only':True,'observations':[f for o in objects for f in o['observations']][:4],'readable_identifier':''}]
    return {'objects':objects,'machines':machines}


def compare(raw,targets,references,threshold):
    """Reproduce mapping and evidence gates without importing the product parser."""
    objects=copy.deepcopy(raw['results'])
    ids=[o['object_id'] for o in objects]
    assert len(ids)==len(set(ids)) and set(ids)=={t['object_id'] for t in targets}
    output={}
    for item in objects:
        target=next(t for t in targets if t['object_id']==item['object_id'])
        assert not target.get('accessory_only') and target['role']!='accessory'
        d=item['decision'];status=d['status'];selected=d['reference'];confidence=d['confidence']
        assert status in ('same_family','other_brand','not_sure')
        assert selected in references if status=='same_family' else selected is None
        assert type(confidence) is int and 0<=confidence<=100
        alternatives=d['top_two']
        assert isinstance(alternatives,list) and len(alternatives)<=2 and len(alternatives)==len(set(alternatives))
        assert all(a in references for a in alternatives)
        for field in ('evidence','missing_evidence','contradictions'):
            assert isinstance(d[field],list)
            for value in d[field]:text(value)
        text(d['retake'],True)
        checks=item['reference_checks']
        assert isinstance(checks,list) and len(checks)==9 and sorted(c['reference'] for c in checks)==sorted(references)
        supports={};conflicts={};mapped_checks=[]
        for check in checks:
            alias=check['reference'];outcome=check['outcome'];comparisons=check['comparisons']
            assert outcome in ('supported','visible_conflict','insufficient_evidence')
            text(check['evidence']);assert isinstance(comparisons,list) and len(comparisons)<=4
            supports[alias]=set();conflicts[alias]=0
            for c in comparisons:
                assert c['feature'] in FEATURES and c['relation'] in ('support','conflict','unobserved')
                assert c['panel'] in references[alias]['panels'];text(c['detail'])
                for side in ('query','reference'):
                    assert type(c[side+'_visible']) is bool
                    if c[side+'_visible']:box(c[side+'_box_2d'],target['box_2d'] if side=='query' else None)
                    else:assert c[side+'_box_2d'] is None
                if c['relation']!='unobserved':assert c['query_visible'] and c['reference_visible']
                if c['relation']=='support':supports[alias].add(c['feature'])
                if c['relation']=='conflict':conflicts[alias]+=1
            if outcome=='visible_conflict':assert conflicts[alias]>0
            verified=outcome=='supported' and len(supports[alias])>=2 and not conflicts[alias]
            if references[alias]['in_catalog']:
                mapped_checks.append({'product':references[alias]['product'],'outcome':'confirmed' if verified else 'contradicted' if outcome=='visible_conflict' else 'insufficient_evidence','evidence':check['evidence']})
        other=item['other_brand_evidence'];assert isinstance(other,list) and len(other)<=2
        for evidence in other:text(evidence['text']);box(evidence['query_box_2d'],target['box_2d'])
        reasons=[];mapped_status='not_sure';product=None
        if status=='same_family':
            if len(supports[selected])<2:reasons.append('Two distinct visible diagnostic feature types are required.')
            if conflicts[selected]:reasons.append('The selected reference has a visible conflicting feature.')
            if [c['reference'] for c in checks if c['outcome']=='supported']!=[selected]:reasons.append('Reference checks do not identify exactly one supported family.')
            if not d['evidence']:reasons.append('The family decision lacks supporting evidence.')
            if confidence<threshold:reasons.append('Confidence is below the automatic acceptance threshold.')
            if not reasons:
                mapped_status='match' if references[selected]['in_catalog'] else 'not_in_catalogue'
                product=references[selected]['product'] if mapped_status=='match' else None
        elif status=='other_brand':reasons.append('Outside-reference brand evidence is unverified in this fixed reference experiment.')
        mapped={**d,'status':mapped_status,'product':product,'top_two':[references[a]['product'] for a in alternatives],'missing_evidence':d['missing_evidence']+reasons}
        mapped.pop('reference')
        output[item['object_id']]={'raw':item,'decision':mapped,'candidate_checks':mapped_checks,'top_two':mapped['top_two'],
                                 'gate_reasons':reasons,'matched_reference':selected,'matched_product':references[selected]['product'] if selected else None}
    return output


def geometry_base(raw,targets):
    """Discard only otherwise valid whole-scene regions outside their target."""
    result=copy.deepcopy(raw);removed=[]
    by_id={t['object_id']:t for t in targets}
    for item in result['results']:
        target=by_id[item['object_id']]['box_2d']
        for check in item['reference_checks']:
            original_conflicts=sum(c['relation']=='conflict' for c in check['comparisons'])
            removed_conflicts=0
            for index,c in enumerate(check['comparisons']):
                assert c['relation'] in ('support','conflict','unobserved'), 'An invalid relation cannot be normalised'
                if c['query_visible'] is not True:continue
                b=c['query_box_2d'];box(b)
                if not(target[0]<=b[0]<b[2]<=target[2] and target[1]<=b[1]<b[3]<=target[3]):
                    removed.append({'object_id':item['object_id'],'reference':check['reference'],'comparison_index':index,'comparison':copy.deepcopy(c)})
                    removed_conflicts+=c['relation']=='conflict'
                    c.update(query_visible=False,query_box_2d=None,relation='unobserved')
            if check['outcome']=='visible_conflict' and original_conflicts and removed_conflicts and not any(c['relation']=='conflict' for c in check['comparisons']):
                check['outcome']='insufficient_evidence'
    assert removed, 'No permitted query-containment suppression exists'
    return result,removed


def raw_decision(raw,references):
    d=copy.deepcopy(raw['decision']);alias=d.pop('reference')
    if d['status']=='same_family':
        d['status']='match' if references[alias]['in_catalog'] else 'not_in_catalogue'
        d['product']=references[alias]['product'] if d['status']=='match' else None
    else:d.update(status='not_in_catalogue' if d['status']=='other_brand' else 'not_sure',product=None)
    d['top_two']=[references[a]['product'] for a in d['top_two']]
    return d


def aggregate(image_id,rows,detections):
    observed=detections.get(image_id)
    saved=[r for r in rows if r['image_id']==image_id]
    expected={o['instance_id'] for o in observed} if observed is not None else set()
    ids=[r['instance_id'] for r in saved if not r.get('detection_missed')]
    complete=observed is not None and bool(saved) and set(ids)==expected and len(ids)==len(set(ids))
    answer={'status':'not_sure','product':None,'confidence':0,'complete':complete}
    if not complete or not observed or any(r.get('detection_missed') for r in saved):return answer
    decisions=[r['decision'] for r in saved];statuses={d['status'] for d in decisions}
    products={d['product'] for d in decisions if d['status']=='match'}
    if statuses=={'not_in_catalogue'} or statuses=={'match'} and len(products)==1:
        answer.update(status=decisions[0]['status'],product=decisions[0]['product'],confidence=min(d['confidence'] for d in decisions))
    return answer


def score(ids,manifest,rows,detections,completed,catalogue):
    per_photo=[]
    for image_id in ids:
        d=aggregate(image_id,rows,detections);label=manifest[image_id]['labels'][0]
        done=image_id in completed
        correct=done and (d['status']=='match' and d['product']==label or d['status']=='not_in_catalogue' and label not in catalogue)
        per_photo.append({**d,'image_id':image_id,'source_label':label,'completed':done,'correct':correct,'run_status':d['status'] if done else 'not_run'})
    wrong=[d for d in per_photo if d['completed'] and d['status']!='not_sure' and not d['correct']]
    metrics={'denominator':len(ids),'correct':sum(d['correct'] for d in per_photo),'wrong':len(wrong),
             'confidently_wrong':sum(d['confidence']>=90 for d in wrong),
             'unsure':sum(d['completed'] and d['status']=='not_sure' for d in per_photo),'not_run':sum(not d['completed'] for d in per_photo)}
    metrics['accuracy_all_selected']=metrics['correct']/len(ids)
    return {'metrics':metrics,'per_photo':per_photo}


def reference_family_score(ids,manifest,rows,detections,completed):
    per_photo=[]
    for image_id in ids:
        source_label=manifest[image_id]['labels'][0]
        expected=source_label[len('NONCAT_'):] if source_label.startswith('NONCAT_') else source_label
        saved=[r for r in rows if r['image_id']==image_id]
        coverage=aggregate(image_id,rows,detections)['complete']
        products={r.get('matched_product') for r in saved}
        resolved=(image_id in completed and coverage and bool(saved) and bool(detections.get(image_id))
                  and all(not r.get('detection_missed') and r['decision']['status']!='not_sure' for r in saved)
                  and None not in products and len(products)==1)
        per_photo.append({'image_id':image_id,'source_label':source_label,'expected_reference_family':expected,
                          'predicted_reference_families':sorted(p for p in products if p is not None),
                          'completed':image_id in completed,'resolved_known_reference_family':resolved,
                          'exact_reference_family_correct':resolved and products=={expected}})
    return {'denominator':len(ids),'exact_correct':sum(p['exact_reference_family_correct'] for p in per_photo),
            'wrong_resolved_family':sum(p['resolved_known_reference_family'] and not p['exact_reference_family_correct'] for p in per_photo),
            'unresolved_or_unrun':sum(not p['resolved_known_reference_family'] for p in per_photo),'per_photo':per_photo}


def image_bytes(source,bounds,maximum,reference=False):
    from PIL import Image,ImageOps
    with Image.open(source) as raw:
        im=ImageOps.exif_transpose(raw).convert('RGBA' if reference else 'RGB').crop(bounds)
        im.thumbnail((maximum,maximum))
        if reference:
            bg=Image.new('RGBA',im.size,'white');bg.alpha_composite(im);im=bg.convert('RGB')
        b=io.BytesIO();im.save(b,format='JPEG',quality=95)
        return b.getvalue(),im.size


def crop_bounds(value,width,height,padding):
    box(value);y1,x1,y2,x2=value;dx=(x2-x1)*padding;dy=(y2-y1)*padding
    return [max(0,math.floor((x1-dx)*width/1000)),max(0,math.floor((y1-dy)*height/1000)),min(width,math.ceil((x2+dx)*width/1000)),min(height,math.ceil((y2+dy)*height/1000))]


def self_checks():
    refs={f'R{i:02}':{'product':str(i),'in_catalog':i<=6,'panels':[f'R{i:02}-P1']} for i in range(1,10)}
    target={'object_id':'o1','role':'machine','box_2d':[0,0,1000,1000]}
    feature=lambda name:{'feature':name,'relation':'support','query_visible':True,'query_box_2d':[0,0,500,500],
                         'panel':'R01-P1','reference_visible':True,'reference_box_2d':[0,0,500,500],'detail':'Visible detail.'}
    checks=[{'reference':a,'outcome':'insufficient_evidence','evidence':'No visible distinction.','comparisons':[]} for a in refs]
    checks[0].update(outcome='supported',comparisons=[feature('body_layout'),feature('handle_control')])
    raw={'results':[{'object_id':'o1','decision':{'status':'same_family','reference':'R01','confidence':95,'top_two':['R01'],
          'evidence':['Visible body.'],'missing_evidence':[],'contradictions':[],'retake':''},'reference_checks':checks,'other_brand_evidence':[]}]}
    assert compare(raw,[target],refs,90)['o1']['decision']['status']=='match'
    for variant in ('low','duplicate','ambiguous','other_brand'):
        x=copy.deepcopy(raw)
        if variant=='low':x['results'][0]['decision']['confidence']=89
        if variant=='duplicate':x['results'][0]['reference_checks'][0]['comparisons'][1]['feature']='body_layout'
        if variant=='ambiguous':x['results'][0]['reference_checks'][1]['outcome']='supported'
        if variant=='other_brand':x['results'][0]['decision'].update(status='other_brand',reference=None)
        assert compare(x,[target],refs,90)['o1']['decision']['status']=='not_sure'
    x=copy.deepcopy(raw);x['results'][0]['reference_checks'][0]['comparisons'][0].update(query_visible=False,query_box_2d=None)
    try:compare(x,[target],refs,90)
    except AssertionError:pass
    else:raise AssertionError('Control accepted hidden support')
    row={'image_id':'one','instance_id':'one_o1','decision':{'status':'match','product':'1','confidence':95}}
    assert aggregate('one',[row],{'one':[{'instance_id':'one_o1'}]})['status']=='match'
    assert aggregate('one',[row],{'one':[{'instance_id':'one_o1'},{'instance_id':'one_o2'}]})['status']=='not_sure'
    narrow={**target,'box_2d':[0,0,900,900]}
    bad=copy.deepcopy(raw);bad['results'][0]['reference_checks'][0]['comparisons'][0]['query_box_2d']=[0,0,500,901]
    normalised,removed=geometry_base(bad,[narrow])
    assert len(removed)==1 and normalised['results'][0]['decision']==bad['results'][0]['decision']
    assert compare(normalised,[narrow],refs,90)['o1']['decision']['status']=='not_sure'
    conflict=lambda outside:{**feature('handle_control'),'relation':'conflict','panel':'R02-P1','query_box_2d':[0,0,500,901 if outside else 500]}
    for keep_other in (True,False):
        bad=copy.deepcopy(raw);bad['results'][0]['reference_checks'][1].update(outcome='visible_conflict',comparisons=[conflict(True)]+([conflict(False)] if keep_other else []))
        normalised,removed=geometry_base(bad,[narrow])
        assert normalised['results'][0]['reference_checks'][1]['outcome']==('visible_conflict' if keep_other else 'insufficient_evidence')
        assert compare(normalised,[narrow],refs,90)['o1']['decision']['status']=='match'
    bad=copy.deepcopy(raw);bad['results'][0]['reference_checks'][1].update(outcome='visible_conflict',comparisons=[conflict(True)])
    bad['results'][0]['reference_checks'][2].update(outcome='visible_conflict',comparisons=[])
    normalised,_=geometry_base(bad,[narrow])
    try:compare(normalised,[narrow],refs,90)
    except AssertionError:pass
    else:raise AssertionError('Control hid an unrelated invalid conflict')
    for variant in ('relation','out_of_scene'):
        bad=copy.deepcopy(raw);c=bad['results'][0]['reference_checks'][0]['comparisons'][0]
        c['query_box_2d']=[0,0,500,901 if variant=='relation' else 1001]
        if variant=='relation':c['relation']='invalid_relation'
        try:geometry_base(bad,[narrow])
        except AssertionError:pass
        else:raise AssertionError('Control normalised an unapproved defect')
    return 14


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args();root=args.root.resolve();out=root/'out/failure_recovery'
    controls_checked=self_checks();errors=[];notes=[]
    def check(condition,message):
        if not condition:errors.append(message)
    def attempt(label,fn):
        try:return fn()
        except Exception as e:errors.append(label+': '+str(e));return None
    config=read(root/'data/failure_recovery_config.json');scope=config['scope'];config_sha=sha(encoded(config))
    catalogue=set(config['catalogue_order']);panels=read(out/'reference_panels.json');refs=panels['references']
    manifest={p['image_id']:p for p in read(root/'data/test/test_manifest.json')}
    results=read(out/'results.json',[]);detections=read(out/'detections.json',{});completed=read(out/'completed_photos.json',[])
    baseline=read(root/'out/pipeline_v2_recovery/independent_audit.json');old={p['image_id']:p for p in baseline['final']['per_photo']}
    check(config==read(out/'frozen_config.json'),'Active configuration differs from the transport freeze')
    check(config['stage_ceiling_inr']==1000 and config['budget']['total_max_inr']==2000 and config['budget']['usd_inr']==100,'Authorised ceilings or guard FX differ')
    check(config['reporting_usd_inr']==95.15703439035285,'Reporting FX changed')
    check(len(scope['failure_ids'])==20 and set(scope['failure_ids'])=={p for p,d in old.items() if not d['correct']},'Failure cohort differs from the frozen20 failures')
    check(scope['control_ids']==['P006','P014','P019'] and all(old[p]['correct'] for p in scope['control_ids']),'Frozen sanity controls changed')
    check(len(scope['photo_ids'])==23 and len(set(scope['photo_ids']))==23 and set(scope['photo_ids'])==set(scope['failure_ids']+scope['control_ids']),'Selected cohort changed')
    check(scope==read(root/'data/failure_recovery_scope.json'),'Scope file differs from configuration')
    check(len(completed)==len(set(completed)) and set(completed)<=set(scope['photo_ids']),'Invalid completed-photo population')
    check(all(manifest[p]['evaluation_role']=='labelled_single' for p in scope['photo_ids']),'Selected denominator is not23single-family photos')
    check(set(refs)=={f'R{i:02}' for i in range(1,10)} and len({r['product'] for r in refs.values()})==9,'Neutral reference mapping changed')
    check({r['product'] for r in refs.values() if r['in_catalog']}==catalogue,'Reference catalogue mapping differs')
    check({r['product'] for r in refs.values() if not r['in_catalog']}=={'dyson_v11','dyson_gen5detect','shark_stratos'},'Negative reference mapping differs')
    frozen_changes=[p for p,h in config['frozen_files'].items() if not (root/p).exists() or sha((root/p).read_bytes())!=h]
    check(not frozen_changes,'Frozen project inputs changed')
    check(len(config['frozen_files'])==969,'The frozen input population differs from the activated969 files')
    required_freeze={'tools/run_failure_recovery.py','tools/failure_protocol.py','tests/test_failure_recovery.py','tests/test_failure_protocol.py',
                     'data/reference_views_v3.json','data/failure_recovery_scope.json','data/pipeline_budget_amendment_additional_400.json',
                     'data/pipeline_v2_recovery_config.json','out/failure_recovery/reference_panels.json'}|{p['file'] for p in panels['images']}
    check(required_freeze<=set(config['frozen_files']),'Required new-phase code, reference or authorisation input is not frozen')
    previous_config=read(root/'data/pipeline_v2_recovery_config.json')
    expected_models={}
    for key,bound,cap in [('inventory',20000,16384),('comparison',50000,32768)]:
        model=copy.deepcopy(previous_config['models']['flash37high']);model.update(input_token_bound=bound,max_output_tokens=cap);expected_models[key]=model
    check(config['models']==expected_models and config['confidence_threshold']==90,'Authorised model settings or acceptance threshold differ')
    check(config['rate_limit_policy']==previous_config['rate_limit_policy'],'Recorded pacing or retry policy changed')
    check(all(config['frozen_files'].get(p)==h for p,h in previous_config['frozen_files'].items()),'An inherited old freeze hash was overwritten')
    check(config['frozen_files'].get('data/pipeline_v2_recovery_config.json')==sha((root/'data/pipeline_v2_recovery_config.json').read_bytes()),'Historical recovery configuration is not frozen')
    history=config['previous_ledgers'];old_calls=[];prior=0;old_pending=[]
    check(len(history)==7 and len({p['file'] for p in history})==7,'Seven historical ledgers are not counted exactly once')
    for source in history:
        p=root/source['file'];rows=ledger(p);old_calls+=rows;cost=sum(r['estimated_cost_usd'] for r in rows);prior+=cost
        check(sha(p.read_bytes())==source['sha256'],'Old ledger changed: '+source['file'])
        check(abs(cost-source['accounted_cost_usd'])<1e-10,'Old ledger cost differs: '+source['file'])
        if read(p.with_name('inflight.json'),{}):old_pending.append(source['file'])
    check(not old_pending,'Old requests remain pending')
    check(abs(prior-5.748449861)<1e-10,'Historical accounted total changed')
    check(abs(prior*100+config['budget']['stage_max_inr']-1000)<1e-8,'Remaining stage allowance omits historical spending')
    check(abs(config['budget']['prior_accounted_inr']-prior*100-config['prior_stage_accounted_inr'])<1e-8,'Overall allowance omits prior spending')
    calls=ledger(out/'calls.jsonl');paid=physical(calls);all_paid=physical(old_calls+calls)
    duplicate_paid=[j for j,n in Counter(r['job_id'] for r in all_paid).items() if n>1]
    check(not duplicate_paid,'A physical paid job is repeated across eight ledgers')
    check(all(r['config_sha256']==config_sha for r in calls),'New ledger configuration identity differs')
    check(all(logical(r).startswith('v3:') for r in calls),'New ledger reused a historical logical namespace')
    check(all(r.get('cost_basis')!='offline_usage_bound_recovery' for r in calls),'An unapproved input-bound repair exists in the new phase')
    geometry_events=[r for r in calls if r.get('cost_basis')=='offline_validation_recovery']
    geometry_records={logical(r):r for r in geometry_events};geometry_normalised={};geometry_proofs={}
    check(len(geometry_events)==len(geometry_records),'Repeated geometry recovery for one logical request')
    for job,recovery in geometry_records.items():
        def verify_geometry_recovery():
            prefix,stage,image_id=job.split(':');assert prefix=='v3' and stage=='compare' and image_id in scope['photo_ids']
            receipt=read(out/'geometry_repairs'/(job.replace(':','_')+'.json'),{})
            assert receipt and receipt['job_id']==job
            provenance=recovery['recovery'];line=receipt['original_response_line']
            assert type(line) is int and 1<=line<=len(calls)
            original=calls[line-1]
            originals=[r for r in calls if logical(r)==job and r['status']=='ok' and r.get('cost_basis')=='provider_reported_cost']
            assert len(originals)==1 and original==originals[0]
            failures=[r for r in calls if logical(r)==job and r['status']=='validation_error' and sha(encoded(r))==receipt['validation_failure_sha256']]
            assert len(failures)==1 and failures[0]['error']=='Query region must stay inside its physical target'
            assert calls.index(original)<calls.index(failures[0]) and calls.index(failures[0])+1==calls.index(recovery)
            assert sha(encoded(original))==receipt['original_record_sha256']==provenance['original_record_sha256']
            assert provenance['original_response_line']==line and provenance['validation_failure_sha256']==receipt['validation_failure_sha256']
            assert provenance['reason']==failures[0]['error']
            assert recovery['status']=='ok' and recovery['estimated_cost_usd']==0 and failures[0]['estimated_cost_usd']==0
            assert failures[0]['cost_basis']=='validation_only_no_new_request'
            for key,value in original.items():
                if key not in ('result','estimated_cost_usd','cost_basis'):assert encoded(recovery[key])==encoded(value),'Geometry recovery changed request/provider metadata: '+key
            assert set(recovery)==set(original)|{'recovery','recovered_at_utc'}
            assert sha(encoded(recovery))==receipt['recovery_record_sha256']
            assert sha(encoded(original['provider_response']))==receipt['provider_response_sha256']
            assert original['config_sha256']==config_sha==receipt['config_sha256'] and original['request_sha256']==receipt['request_sha256']
            assert sha((root/'tools/repair_failure_geometry.py').read_bytes())==receipt['helper_source_sha256']
            assert receipt['paid_requests']==0 and receipt['additional_cost_usd']==0
            policy=('For a scene-valid query comparison outside its physical target, preserve the full original '
                    'and locator as unverified metadata, then set query_visible=false, query_box_2d=null and '
                    'relation=unobserved. Downgrade visible_conflict only when its final valid conflict is removed. '
                    'Preserve raw decisions and text; validate again with the actual physical targets.')
            assert receipt['policy']==policy and receipt['hash_kind']=='canonical_json'
            expected_context={str((out/'photos'/image_id/'inventory.json').relative_to(root)),str((out/'reference_panels.json').relative_to(root))}
            assert set(receipt['canonical_context_sha256'])==expected_context
            assert all(sha(encoded(read(root/name)))==expected for name,expected in receipt['canonical_context_sha256'].items())
            targets=read(out/'photos'/image_id/'inventory.json')['machines'];raw=provider_json(original)
            compare(raw,[{**t,'box_2d':[0,0,1000,1000]} for t in targets],refs,config['confidence_threshold'])
            normalised,removed=geometry_base(raw,targets)
            for item in normalised['results']:
                archived=item.get('unverified_comparisons',[]);assert isinstance(archived,list)
                additions=[entry for entry in removed if entry['object_id']==item['object_id']]
                if archived or additions:item['unverified_comparisons']=archived+additions
            assert encoded(normalised)==encoded(recovery['result']),'Independent geometry suppression differs from recovered result'
            assert sha(encoded(normalised))==receipt['normalised_result_sha256']
            assert receipt['transformations']==[entry for item in normalised['results'] for entry in item.get('unverified_comparisons',[])]
            compare(normalised,targets,refs,config['confidence_threshold'])
            geometry_normalised[job]=normalised
            geometry_proofs[job]={'receipt_sha256':sha(encoded(receipt)),'helper_source_sha256':receipt['helper_source_sha256'],
                                  'original_record_sha256':receipt['original_record_sha256'],'validation_failure_sha256':receipt['validation_failure_sha256'],
                                  'new_suppression_count':len(removed),'suppressed_comparisons':removed,'additional_cost_usd':0}
        attempt(job+' geometry recovery',verify_geometry_recovery)
    latest={logical(r):r for r in calls}
    physical_successes={logical(r):r for r in paid if r['status']=='ok'}
    successful={j:physical_successes[j] for j,r in latest.items() if r['status']=='ok' and j in physical_successes}
    check(not [j for j,r in latest.items() if r['status']!='ok' and (r.get('http_status')!=429 or r.get('retry_exhausted'))],'An unrecovered non-429 failure, validation error or exhausted429 request exists')
    pending=read(out/'inflight.json',{});settled={r['job_id'] for r in calls};unresolved={j:r for j,r in pending.items() if j not in settled}
    check(len(unresolved)<=1,'More than one new request is in flight')
    for job,reservation in unresolved.items():
        def validate_reserve():
            assert reservation['config_sha256']==config_sha
            prefix,stage,image_id=logical(reservation).split(':');assert prefix=='v3' and image_id in scope['photo_ids'] and stage in ('inventory','compare')
            model=config['models']['inventory' if stage=='inventory' else 'comparison']
            expected=(model['input_token_bound']*model['input_usd_per_million']+model['max_output_tokens']*model['output_usd_per_million'])/1e6
            assert abs(reservation['reserved_cost_usd']-expected)<1e-12
        attempt(job+' pending reservation',validate_reserve)
    spent=sum(r['estimated_cost_usd'] for r in calls);reserve=sum(r['reserved_cost_usd'] for r in unresolved.values());accounted=spent+reserve
    check(all(isinstance(r['estimated_cost_usd'],(int,float)) and not isinstance(r['estimated_cost_usd'],bool) and math.isfinite(r['estimated_cost_usd']) and r['estimated_cost_usd']>=0 for r in calls),'Invalid recorded cost')
    check(accounted*100<=config['budget']['stage_max_inr']+1e-8,'New phase exceeded its remaining monetary allowance')
    check(config['budget']['prior_accounted_inr']+accounted*100<=2000+1e-8,'Overall authorised budget exceeded')
    usage_checks=0
    for row in paid:
        def validate_cost():
            nonlocal usage_checks
            prefix,stage,image_id=logical(row).split(':');assert prefix=='v3' and image_id in scope['photo_ids'] and stage in ('inventory','compare')
            model=config['models']['inventory' if stage=='inventory' else 'comparison']
            expected=(model['input_token_bound']*model['input_usd_per_million']+model['max_output_tokens']*model['output_usd_per_million'])/1e6
            assert abs(row['reserved_cost_usd']-expected)<1e-12 and row['estimated_cost_usd']<=expected+1e-12
            if row['status']=='ok':
                assert row['requested_model']==row['model_version']=='google/gemini-3.7-flash'
                assert row['provider']=='Google AI Studio' and row['provider_route']=='openrouter'
                assert row['provider_response']['service_tier']=='default'
                provider_json(row);usage=row['usage_metadata'];assert usage==row['provider_response']['usage']
                p,c=usage['prompt_tokens'],usage['completion_tokens'];cached=usage.get('prompt_tokens_details',{}).get('cached_tokens',0)
                assert all(type(v) is int and v>=0 for v in (p,c,cached)) and cached<=p
                assert p<=model['input_token_bound'] and c<=model['max_output_tokens'] and usage['total_tokens']==p+c
                actual=((p-cached)*model['input_usd_per_million']+cached*model['cached_input_usd_per_million']+c*model['output_usd_per_million'])/1e6
                assert abs(actual-row['estimated_cost_usd'])<1e-10 and abs(actual-usage['cost'])<1e-10
                details=usage.get('cost_details',{})
                for k,v in [('upstream_inference_prompt_cost',actual-c*model['output_usd_per_million']/1e6),('upstream_inference_completions_cost',c*model['output_usd_per_million']/1e6),('upstream_inference_cost',actual)]:
                    if k in details:assert abs(details[k]-v)<1e-10
                usage_checks+=1
            elif row.get('cost_basis')=='reserved_upper_bound_usage_unavailable':assert row['estimated_cost_usd']==row['reserved_cost_usd']
        attempt(row['job_id']+' cost',validate_cost)
    ordered=sorted(paid,key=lambda r:r['request_started_unix'])
    gaps=[b['request_started_unix']-a['request_finished_unix'] for a,b in zip(ordered,ordered[1:])]
    check(all(g>=15-.002 for g in gaps),'Response-to-request pacing fell below15seconds')
    if ordered:
        old_finished=max(r.get('request_finished_unix',0) for r in physical(old_calls))
        check(ordered[0]['request_started_unix']-old_finished>=15-.002,'First new-phase request did not respect historical pacing')
    attempts=Counter(logical(r) for r in paid);retry_checks=[]
    for job,n in attempts.items():
        check(n<=4,'429 attempt limit exceeded: '+job)
        seq=[r for r in ordered if logical(r)==job]
        for index,(a,b) in enumerate(zip(seq,seq[1:]),1):
            gap=b['request_started_unix']-a['request_finished_unix'];required=max(60*2**(index-1),a.get('retry_after_seconds',0))
            check(a.get('http_status')==429 and a['request_sha256']==b['request_sha256'] and gap>=required-.002,'Retry changed request or violated backoff: '+job)
            retry_checks.append({'logical_job_id':job,'gap_seconds':gap,'required_seconds':required})
    from PIL import Image,ImageOps
    reference_pixel_checks=0
    for panel in panels['images']:
        def verify_panel():
            nonlocal reference_pixel_checks
            source=root/panel['source_file'];destination=root/panel['file']
            assert sha(source.read_bytes())==panel['source_sha256'] and sha(destination.read_bytes())==panel['sha256']
            rendered,size=image_bytes(source,panel['source_pixel_box'],768,True)
            assert rendered==destination.read_bytes() and list(size)==[panel['width'],panel['height']]
            reference_pixel_checks+=1
        attempt(panel['panel_id']+' pixels',verify_panel)
    sys.path.insert(0,str(root/'tools'))
    from pipeline_api import Client
    from failure_protocol import inventory_prompt,build_comparison_prompt
    class Capture:
        def __init__(self):self.config=config
        def _call(self,job,operation,model,payload,url,reservation,parse):return sha(url.encode()+b'\n'+encoded(payload)),payload
    capture=Capture();request_checks=0;inventory_checks=0;decision_checks=0;crop_checks=0
    def check_query(path,source,region,maximum,record=None):
        nonlocal crop_checks
        with Image.open(source) as raw:width,height=ImageOps.exif_transpose(raw).size
        bounds=crop_bounds(region,width,height,.04);image,size=image_bytes(source,bounds,maximum)
        assert image==path.read_bytes(),'Query image differs from original source pixels'
        if record:assert record['pixel_box']==bounds and record['sha256']==sha(image) and root/record['file']==path
        crop_checks+=1
    for job,row in successful.items():
        def audit_request():
            nonlocal request_checks,inventory_checks,decision_checks
            prefix,stage,image_id=job.split(':');directory=out/'photos'/image_id
            raw=provider_json(row);source=root/manifest[image_id]['file'];scene=directory/'scene.jpg'
            check_query(scene,source,[0,0,1000,1000],2048)
            if stage=='inventory':
                derived=inventory(raw);assert encoded(derived)==encoded(read(directory/'inventory.json'))
                prompt=inventory_prompt();images=[('WHOLE SCENE',scene)];key='inventory';inventory_checks+=1
            else:
                inv=read(directory/'inventory.json');targets=inv['machines'];crops=read(directory/'query_crops.json')
                assert targets and not any(t.get('accessory_only') for t in targets)
                images=[('WHOLE SCENE',scene)];key='comparison'
                for target in targets:
                    name=target['object_id'];records=crops[name];body=directory/(name+'_body.jpg')
                    assert len(records)==1+sum(f['visible'] for f in target['observations'])
                    check_query(body,source,target['box_2d'],1536,records[0]);images.append(('TARGET '+name,body));index=1
                    for number,feature in enumerate(target['observations']):
                        if feature['visible']:
                            detail=directory/(name+'_detail_'+str(number)+'.jpg');check_query(detail,source,feature['box_2d'],1536,records[index]);index+=1
                            images.append(('TARGET '+name+' DETAIL '+str(number),detail))
                images += [(p['panel_id'],root/p['file']) for p in panels['images']]
                prompt=build_comparison_prompt(targets,refs)
                processed=geometry_normalised.get(job,raw)
                derived=compare(processed,targets,refs,config['confidence_threshold']);assert encoded(derived)==encoded(read(directory/'comparison.json'))
                decision_checks+=len(derived)
                context=json.loads(prompt.rsplit('\n',1)[1]);assert all(set(v)=={'panels'} for v in context['references'].values())
            request_hash,payload=Client.generate(capture,job,key,prompt,images)
            assert request_hash==row['request_sha256'],'Saved request hash differs from exact reconstructed payload'
            assert payload['provider']['only']==['google-ai-studio'] and payload['provider']['allow_fallbacks'] is False and payload['reasoning']=={'effort':'high'}
            text_parts=[p['text'] for p in payload['messages'][1]['content'] if p['type']=='text']
            for forbidden in ('"source_label"','"source_url"','"source_title"','"label_basis"','"labels"','dyson_v16_piston_animal','dyson_gen5detect','shark_stratos'):
                assert all(forbidden not in p for p in text_parts),'Source or product metadata entered inference text'
            request_checks+=1
        attempt(job+' request',audit_request)
    skipped=[]
    for image_id in completed:
        def audit_completed():
            directory=out/'photos'/image_id;inv=read(directory/'inventory.json');targets=inv['machines']
            assert 'v3:inventory:'+image_id in successful
            assert encoded(detections[image_id])==encoded([{**t,'instance_id':image_id+'_'+t['object_id']} for t in targets])
            skip=not targets or all(t.get('accessory_only') for t in targets)
            if skip:
                assert 'v3:compare:'+image_id not in latest and not (directory/'comparison.json').exists()
                skipped.append(image_id)
            else:assert 'v3:compare:'+image_id in successful
            for variant in ('reference_raw','aligned_reference'):
                rows=[r for r in results if r['image_id']==image_id and r['variant']==variant]
                assert aggregate(image_id,rows,detections)['complete']
                for r in rows:
                    if skip:assert r['decision']['status']=='not_sure' and r.get('comparison_skipped') is True
                    else:
                        name=r['raw']['object_id'];assert r['instance_id']==image_id+'_'+name
                        parsed=read(directory/'comparison.json')[name]
                        expected=raw_decision(parsed['raw'],refs) if variant=='reference_raw' else parsed['decision']
                        assert encoded(r['decision'])==encoded(expected)
                        assert encoded(r['raw'])==encoded(parsed['raw']) and encoded(r['candidate_checks'])==encoded(parsed['candidate_checks'])
                        assert len(r['candidate_checks'])==6 and {c['product'] for c in r['candidate_checks']}==catalogue
        attempt(image_id+' completed output',audit_completed)
    scores={};exact_family_scores={}
    for variant in ('reference_raw','aligned_reference'):
        rows=[r for r in results if r['variant']==variant]
        check(len(rows)==len({(r['image_id'],r['instance_id']) for r in rows}),'Duplicate variant instance: '+variant)
        scores[variant]={cohort:score(ids,manifest,rows,detections,completed,catalogue) for cohort,ids in [('failures',scope['failure_ids']),('controls',scope['control_ids']),('all_selected',scope['photo_ids'])]}
        family_cohorts=[('failures',scope['failure_ids']),('controls',scope['control_ids']),('non_catalogue_failures',[p for p in scope['failure_ids'] if manifest[p]['labels'][0].startswith('NONCAT_')])]
        exact_family_scores[variant]={cohort:reference_family_score(ids,manifest,rows,detections,completed) for cohort,ids in family_cohorts}
    final={r['image_id']:r for r in scores['aligned_reference']['all_selected']['per_photo']}
    transitions=[];outcomes=Counter();regressions=[]
    for image_id in scope['photo_ids']:
        a,b=old[image_id],final[image_id]
        cohort='failure' if image_id in scope['failure_ids'] else 'control'
        key='not_run' if not b['completed'] else 'recovered_correct' if b['correct'] else ('still_unsure' if a['status']=='not_sure' else 'wrong_to_unsure') if b['status']=='not_sure' else 'new_wrong' if a['status']=='not_sure' else 'still_wrong'
        if cohort=='failure':outcomes[key]+=1
        elif b['completed'] and not b['correct']:regressions.append(image_id)
        transitions.append({'image_id':image_id,'cohort':cohort,'old_status':a['status'],'old_correct':a['correct'],'new_status':b['run_status'],'new_correct':b['correct'],'completed':b['completed']})
    outcomes={k:outcomes[k] for k in ('recovered_correct','still_wrong','new_wrong','wrong_to_unsure','still_unsure','not_run')}
    board=read(out/'scoreboard.json',{});board_current=bool(board and board.get('completed_count')==len(completed) and abs(board.get('costs',{}).get('new_accounted_usd',-1)-accounted)<1e-10)
    if board_current:
        check(board['transitions']==transitions,'Saved baseline transitions differ')
        check(board['failure_outcomes']==outcomes and board['control_regressions']==regressions,'Saved failure recovery or control regression counts differ')
        check(board.get('full_set_accuracy_retested') is False,'Selected-cohort result is described as a full-set retest')
        groups={g['variant']:g for g in board['summary']['groups']}
        for variant in scores:
            if variant not in groups:check(not completed,'Saved summary variant missing');continue
            m=scores[variant]['all_selected']['metrics'];saved=groups[variant]['metrics']
            for key,value in [('single_photo_count',23),('correct_total',m['correct']),('confidently_wrong_count',m['confidently_wrong']),('not_sure_count',m['unsure']+m['not_run']),('resolved_count',23-m['unsure']-m['not_run'])]:
                check(saved[key]==value,'Saved summary metric differs: '+variant+':'+key)
    else:notes.append('Saved scoreboard is absent or stale while the run is active.')
    if args.require_complete:
        check(set(completed)==set(scope['photo_ids']),'Not all23selected photos completed')
        check(not unresolved and not [j for j,r in latest.items() if r['status']!='ok'],'Pending or failed new-phase requests remain')
        check(request_checks==len(successful),'Not all successful requests were reconstructed')
        check(set(geometry_records)==set(geometry_normalised),'A geometry recovery was not independently reproduced')
        check(board_current,'Final scoreboard is absent or stale')
        receipt=read(out/'run_receipt.json',{})
        check(receipt.get('status')=='completed' and receipt.get('completed_count')==23 and receipt.get('inflight_count')==0,'Final run receipt is incomplete')
    old_live_audit=None
    if args.require_complete:
        def verify_old_live():
            proc=subprocess.run([sys.executable,str(root/'out/pipeline_v2_recovery/independent_audit.py'),'--root',str(root),'--require-complete'],capture_output=True,text=True)
            value=json.loads(proc.stdout)
            assert proc.returncode==0 and value['audit_status']=='PASS' and value['completed_photo_count']==58
            return {'exit_code':proc.returncode,'status':value['audit_status'],'completed_photo_count':58,'frozen_file_count':value['integrity']['frozen_file_count'],'frozen_changes':value['integrity']['frozen_changes']}
        old_live_audit=attempt('Fresh preserved58-photo audit',verify_old_live)
    try:head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    except Exception:head=None
    source_hashes={p:sha((root/p).read_bytes()) for p in ('tools/run_failure_recovery.py','tools/failure_protocol.py','tests/test_failure_recovery.py','tests/test_failure_protocol.py')}
    for p in ('tools/repair_failure_geometry.py','tests/test_failure_geometry.py'):
        if (root/p).exists():source_hashes[p]=sha((root/p).read_bytes())
    test_log=Path('/tmp/dyson-failure-all-tests.log')
    geometry_test_log=Path('/tmp/dyson-failure-geometry-tests.log')
    report={'audit_status':'FAIL' if errors else 'PASS' if args.require_complete else 'IN_PROGRESS_CHECKS_PASS','errors':errors,'notes':notes,
            'completed_photo_count':len(completed),'selected_photo_count':23,'scores':scores,'exact_reference_family_scores':exact_family_scores,'failure_outcomes':outcomes,'transitions':transitions,'control_regressions':regressions,
            'accessory_or_no_machine_comparison_skips':sorted(skipped),
            'integrity':{'self_checks':controls_checked,'config_sha256':config_sha,'audit_source_sha256':sha(Path(__file__).read_bytes()),'source_hashes':source_hashes,
                         'test_log_sha256':sha(test_log.read_bytes()) if test_log.exists() else None,'geometry_test_log_sha256':sha(geometry_test_log.read_bytes()) if geometry_test_log.exists() else None,'git_head_at_audit':head,'frozen_file_count':len(config['frozen_files']),'frozen_changes':frozen_changes,
                         'old_full58_audit_status':baseline['audit_status'],'old_full58_completed':baseline['completed_photo_count'],'old_inherited_frozen_file_count':len(previous_config['frozen_files']),'fresh_old_full58_audit':old_live_audit,
                         'all_eight_ledgers_physical_jobs':len(all_paid),'duplicate_physical_job_ids':duplicate_paid,'new_requests_reconstructed':request_checks,'independent_inventory_checks':inventory_checks,
                         'independent_physical_decisions_checked':decision_checks,'manufacturer_panels_reconstructed':reference_pixel_checks,'query_images_reconstructed':crop_checks,
                         'geometry_recovery_count':len(geometry_records),'geometry_recovery_additional_cost_usd':sum(r['estimated_cost_usd'] for r in geometry_events),'geometry_recovery_proofs':geometry_proofs},
            'transport':{'new_physical_calls':len(paid),'logical_successes':len(successful),'pending':list(unresolved),'usage_cost_checks':usage_checks,'retries':retry_checks,
                         'minimum_finish_to_start_gap_seconds':min(gaps) if gaps else None,'returned_providers':dict(Counter(r.get('provider') for r in paid if r['status']=='ok')),
                         'returned_models':dict(Counter(r.get('model_version') for r in paid if r['status']=='ok')),
                         'maximum_input_tokens':{stage:max((r.get('usage_metadata',{}).get('prompt_tokens',0) for r in paid if logical(r).split(':')[1]==stage),default=0) for stage in ('inventory','compare')}},
            'costs':{'historical_seven_ledgers_accounted_usd':prior,'new_settled_usd':spent,'new_unresolved_reserve_usd':reserve,'new_accounted_usd':accounted,'new_reporting_inr':accounted*config['reporting_usd_inr'],
                     'new_guard_inr':accounted*100,'combined_stage_guard_inr':(prior+accounted)*100,'stage_ceiling_inr':1000,'remaining_stage_guard_inr':1000-(prior+accounted)*100,
                     'combined_stage_reporting_inr':(prior+accounted)*config['reporting_usd_inr'],'overall_guard_inr':config['budget']['prior_accounted_inr']+accounted*100,'overall_ceiling_inr':2000,
                     'new_reporting_cost_per_completed_photo_inr':accounted*config['reporting_usd_inr']/len(completed) if completed else None},
            'scope':{'selected_failure_development_evaluation':True,'full58_accuracy_retested':False,'client_store_holdout_tested':False,'new_retake_photos_tested':False,'known_product_live_arm_tested':False,
                     'confidence_is_calibrated_probability':False,'image_semantic_truth_independently_proved':False}}
    print(json.dumps(report,indent=2));return 1 if errors else 0


if __name__=='__main__':raise SystemExit(main())
