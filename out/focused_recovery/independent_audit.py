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



import re
import base64

QUESTION_FEATURES=['body_layout','handle_control','bin_mechanism','display_layout','cyclone_filter','identifier','relationship']
BODY_FEATURES={'body_layout','filter','cyclone','cyclone_assembly','display','handle'}
GENERIC={'DYSON','HEPA','FILTRO','ANIMAL'}

def literal(value):return re.sub(r'\s+',' ',value.strip()).upper()
def specific(value):return bool(set(re.findall(r'[A-Z0-9]+',literal(value)))-GENERIC)
def iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return intersection/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)
def eligible(target):
    return not(target.get('role')=='accessory' or target.get('accessory_only')) and bool({f.get('feature','').lower().replace(' ','_') for f in target.get('observations',[]) if f.get('visible') is True}&BODY_FEATURES)

def check_predicates(value,plan,subset=None):
    assert isinstance(value,dict) and isinstance(value.get('observations'),list)
    questions={q['question_id']:q for q in plan['questions']}
    expected=set(questions) if subset is None else set(subset)
    records=value['observations'];ids=[o['question_id'] for o in records]
    assert len(ids)==len(set(ids)) and set(ids)==expected
    targets={t['object_id']:t for t in plan['targets']}
    def state(row,target=None):
        assert row['state'] in ('present','absent','not_visible') and type(row['region_fully_visible']) is bool
        text(row['detail'])
        if row['state']=='not_visible':assert row['box_2d'] is None and not row['region_fully_visible']
        else:
            box(row['box_2d'],target)
            if row['state']=='absent':assert row['region_fully_visible']
    for o in records:
        question=questions[o['question_id']];name=question['object_id']
        assert o['object_id']==name
        state(o,targets[name]['box_2d']);assert isinstance(o['literal_text'],str) and type(o['needs_check']) is bool
        assert o['state']=='present' or not o['literal_text']
        aliases=[] if question['feature']=='relationship' else plan['focus_refs'][name]
        refs=o['references'];assert isinstance(refs,list) and len(refs)==len(aliases) and {r['reference'] for r in refs}==set(aliases)
        for r in refs:
            assert r['panel'] in plan['panels'][r['reference']];state(r)
            assert r['relation_to_query'] in ('same','different','not_comparable')
            assert r['relation_to_query']=='not_comparable' or 'not_visible' not in (o['state'],r['state'])
        if question['feature']=='relationship':
            related=o.get('related_object_id');assert related is None or related in targets and related!=name
            assert o.get('relationship','unresolved') in ('connected_component','independent_machine','unresolved')
            assert o.get('relationship')!='connected_component' or related is not None
    return value

def required_checks(plan,observations):
    result=[]
    for o in observations['observations']:
        feature=o['question_id'].split('__')[-1]
        needed=o['needs_check'] or o['state']=='absent' or any(r['state']=='absent' for r in o['references'])
        if feature=='identifier' and o['state']=='present' and specific(o['literal_text']):needed=True
        if feature in ('body_layout','bin_mechanism'):
            relations={r['reference']:r['relation_to_query'] for r in o['references']}
            for group in plan['ambiguity_sets']:
                if set(group)<=set(relations) and {'same','different'}<=set(relations[a] for a in group):needed=True
        old=plan['baseline'].get(o['object_id'])
        if old:
            checks={c['reference']:c for c in old['reference_checks']}
            for r in o['references']:
                relations={c['relation'] for c in checks[r['reference']]['comparisons'] if c['feature']==feature and c['relation']!='unobserved'}
                new={'same':'support','different':'conflict'}.get(r['relation_to_query'])
                if relations and new and new not in relations:needed=True
        if needed:result.append(o['question_id'])
    return result

def agrees(o,c):
    if not c or o['state']!=c['state'] or o['state']=='not_visible' or iou(o['box_2d'],c['box_2d'])<.5:return False
    if o['question_id'].endswith('__identifier') and literal(o['literal_text'])!=literal(c['literal_text']):return False
    theirs={r['reference']:r for r in c['references']}
    for r in o['references']:
        if r['reference'] not in theirs:return False
        q=theirs[r['reference']]
        if r['state']!=q['state'] or r['relation_to_query']!=q['relation_to_query']:return False
        if r['state']!='not_visible' and (r['panel']!=q['panel'] or iou(r['box_2d'],q['box_2d'])<.5):return False
    return True

def focused_decisions(raw,plan,observations,checks,facts,threshold):
    check_predicates(observations,plan)
    check_predicates(checks,plan,[o['question_id'] for o in checks['observations']])
    by_q={o['question_id']:o for o in observations['observations']};by_check={o['question_id']:o for o in checks['observations']}
    mandatory=set(required_checks(plan,observations));by_fact={f['id']:f for f in facts['facts']};refs=facts['references']
    items=raw['results'];assert len(items)==len(plan['active_ids']) and {r['object_id'] for r in items}==set(plan['active_ids'])
    merged=[];all_reasons={}
    for item in items:
        name=item['object_id'];focused=plan['focus_refs'][name];updates=item['reference_check_updates'];reasons=[]
        assert len(updates)==len(focused) and {c['reference'] for c in updates}==set(focused)
        for check in updates:
            for c in check['comparisons']:
                q=c['question_id'];o=by_q[q];assert o['object_id']==name and q.split('__')[-1]==c['feature']
                r=next(r for r in o['references'] if r['reference']==check['reference'])
                assert c['relation']=={'same':'support','different':'conflict','not_comparable':'unobserved'}[r['relation_to_query']]
                assert c['query_visible']==(o['state']!='not_visible') and c['query_box_2d']==o['box_2d']
                assert c['panel']==r['panel'] and c['reference_visible']==(r['state']!='not_visible') and c['reference_box_2d']==r['box_2d']
                if c['relation']!='unobserved' and q in mandatory and not agrees(o,by_check.get(q)):
                    reasons.append('A consequential or disputed predicate lacks independent agreement: '+q)
        d=item['decision'];selected=d['reference'];assert selected is None or selected in focused
        if selected is not None:
            positive=set()
            for c in next(c for c in updates if c['reference']==selected)['comparisons']:
                o=by_q[c['question_id']];r=next(r for r in o['references'] if r['reference']==selected)
                if c['relation']=='support' and o['state']=='present' and r['state']=='present':positive.add(c['feature'])
            if len(positive)<2:reasons.append('Two distinct positively visible supporting feature types are required.')
        verified=set();seen=set()
        assert isinstance(item['distinctions'],list)
        for distinction in item['distinctions']:
            rival=distinction['rival'];q=distinction['question_id'];fact_ids=distinction['fact_ids']
            assert rival in plan['plausible_refs'][name] and rival!=selected and rival not in seen;seen.add(rival)
            assert isinstance(fact_ids,list) and fact_ids and len(fact_ids)==len(set(fact_ids)) and set(fact_ids)<=set(by_fact)
            o=by_q[q];assert o['object_id']==name;feature=q.split('__')[-1]
            selected_o=next((r for r in o['references'] if r['reference']==selected),None)
            rival_o=next((r for r in o['references'] if r['reference']==rival),None)
            sources=[by_fact[f] for f in fact_ids]
            explicit=any(f.get('feature')==feature and rival in f.get('distinguishes',{}).get(selected,[]) and f['kind'] in ('distinction','distinctive','model_identifier') for f in sources)
            shared=any(feature in f.get('non_unique_features',[]) and {selected,rival}<=set(f['references']) for f in by_fact.values())
            images=all(any(f['kind']=='reference_image' and alias in f['references'] and panel in f.get('panels',[]) for f in sources) for alias,panel in [(selected,distinction.get('selected_panel')),(rival,distinction.get('rival_panel'))])
            geometry=bool(selected_o and rival_o and selected_o['state']!='not_visible' and rival_o['state']!='not_visible' and selected_o['relation_to_query']=='same' and rival_o['relation_to_query']=='different' and distinction.get('selected_panel')==selected_o['panel'] and distinction.get('rival_panel')==rival_o['panel'] and images)
            permitted=bool(o['state']!='not_visible' and selected_o and selected_o['relation_to_query']=='same' and (explicit or geometry))
            if feature in ('relationship','head_architecture') or shared and not(feature=='identifier' and explicit):permitted=False
            if feature=='identifier':
                reading=literal(by_check.get(q,{}).get('literal_text',''));code=re.sub('[^A-Z0-9]','',reading)
                permitted=bool(permitted and explicit and agrees(o,by_check.get(q)) and specific(reading) and not any(code==re.sub('[^A-Z0-9]','',literal(c['part_code'])) for c in facts.get('compatibility',[])) and any(reading in {literal(v) for v in f.get('literal_texts',[])} for f in sources if f['kind']=='model_identifier'))
            if q in mandatory and not agrees(o,by_check.get(q)):permitted=False
            if permitted:verified.add(rival)
        if selected is not None:
            missing=set(plan['plausible_refs'][name])-{selected}-verified
            if missing:reasons.append('No verified visible distinction from plausible rivals: '+','.join(sorted(missing)))
        old=copy.deepcopy(plan['baseline'][name]);update_map={c['reference']:c for c in updates}
        old.update(decision=copy.deepcopy(d),reference_checks=[copy.deepcopy(update_map.get(c['reference'],c)) for c in old['reference_checks']],other_brand_evidence=[],focused_raw=copy.deepcopy(item),carried_reference_ids=[c['reference'] for c in old['reference_checks'] if c['reference'] not in focused])
        merged.append(old);all_reasons[name]=list(dict.fromkeys(reasons))
    targets={t['object_id']:t for t in plan['targets']}
    parsed=compare({'results':merged},[targets[name] for name in plan['active_ids']],refs,threshold)
    for name,row in parsed.items():
        row['focus_gate_reasons']=all_reasons[name]
        if all_reasons[name]:row['decision'].update(status='not_sure',product=None);row['decision']['missing_evidence']+=all_reasons[name]
    return parsed

def independent_plan(saved,initial,facts):
    targets=initial['inventory']['machines'];projected=[{k:copy.deepcopy(t[k]) for k in ('object_id','box_2d','role','visibility','observations','accessory_only') if k in t} for t in targets]
    assert saved['targets']==projected and saved['active_ids']==[t['object_id'] for t in targets if eligible(t)]
    assert saved['passive_ids']==[t['object_id'] for t in targets if not eligible(t)]
    assert saved['panels']=={a:r['panels'] for a,r in facts['references'].items()} and saved['ambiguity_sets']==facts['ambiguity_sets']
    assert {q['question_id'] for q in saved['questions']}=={name+'__'+feature for name in saved['active_ids'] for feature in QUESTION_FEATURES}
    for t in targets:
        name=t['object_id'];baseline=initial['comparison'].get(name,{}).get('raw')
        assert saved['baseline'][name]==baseline
        if name not in saved['active_ids']:continue
        d=baseline['decision'];seeds=([d['reference']] if d['reference'] else [])+d['top_two']+d['top_two'][:2]
        candidates=list(dict.fromkeys(seeds+[c['reference'] for c in baseline['reference_checks'] if c['outcome']=='supported'])) or list(facts['references'])
        while True:
            expanded=candidates[:]
            for group in facts['ambiguity_sets']:
                if set(group)&set(expanded):expanded+= [a for a in group if a not in expanded]
            if expanded==candidates:break
            candidates=expanded
        assert saved['plausible_refs'][name]==candidates and saved['focus_refs'][name]==candidates[:3]
    assert saved['overflow_ids']==[name for name,aliases in saved['plausible_refs'].items() if len(aliases)>3]
    assert saved['check_question_ids']==[]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args();root=args.root.resolve();out=root/'out/focused_recovery';errors=[];notes=[]
    def check(value,message):
        if not value:errors.append(message)
    def attempt(label,fn):
        try:return fn()
        except Exception as exc:errors.append(label+': '+type(exc).__name__+': '+str(exc));return None
    config=read(root/'data/focused_recovery_config.json');assert config,'Focused configuration is not activated'
    cfg_sha=sha(encoded(config));check(read(out/'frozen_config.json',config)==config,'Transport freeze differs')
    changes=[name for name,h in config['frozen_files'].items() if not (root/name).exists() or sha((root/name).read_bytes())!=h]
    check(not changes,'A frozen source, input or historical result changed')
    previous=read(root/'data/failure_control_completion_config.json')
    check(all(config['frozen_files'].get(n)==h for n,h in previous['frozen_files'].items()),'An inherited expected hash was replaced or omitted')
    check(len(config['previous_ledgers'])==9 and len({x['file'] for x in config['previous_ledgers']})==9,'Historical ledgers are not counted exactly once')
    prior=0;history=[]
    for h in config['previous_ledgers']:
        records=ledger(root/h['file']);prior+=sum(r['estimated_cost_usd'] for r in records);history+=records
        check(sha((root/h['file']).read_bytes())==h['sha256'] and abs(sum(r['estimated_cost_usd'] for r in records)-h['accounted_cost_usd'])<1e-10,'Historical hash or cost changed: '+h['file'])
        check(not read((root/h['file']).with_name('inflight.json'),{}),'Historical inflight reservation remains')
    check(abs(prior-7.777909361)<1e-10,'Nine-ledger spending differs from the admitted baseline')
    check(config['stage_ceiling_inr']==1000 and config['budget']['total_max_inr']==2000 and config['budget']['usd_inr']==100,'Authorised monetary ceilings changed')
    check(abs(config['budget']['stage_max_inr']+prior*100-1000)<1e-8 and abs(config['budget']['prior_accounted_inr']-prior*100-42.68)<1e-8,'Budget omitted prior spending')
    calls=ledger(out/'calls.jsonl');paid=physical(calls);latest={logical(r):r for r in calls}
    duplicates=[j for j,n in Counter(r['job_id'] for r in physical(history+calls)).items() if n>1];check(not duplicates,'A physical job is duplicated')
    pending=read(out/'inflight.json',{});settled={r['job_id'] for r in calls};pending={j:r for j,r in pending.items() if j not in settled}
    spent=sum(r['estimated_cost_usd'] for r in calls);reserve=sum(r['reserved_cost_usd'] for r in pending.values());accounted=spent+reserve
    check(len(pending)<=1,'More than one request is pending')
    check((prior+accounted)*100<=1000+1e-8 and config['budget']['prior_accounted_inr']+accounted*100<=2000+1e-8,'Authorised budget exceeded')
    check(not [j for j,r in latest.items() if r['status']!='ok' and not(r.get('http_status')==429 and not r.get('retry_exhausted'))],'A terminal error or validation failure is unresolved')
    check(not [r for r in calls if r.get('cost_basis') in ('offline_validation_recovery','offline_usage_bound_recovery')],'Unreviewed offline recovery exists')
    scope=config['scope'];facts=read(root/'data/focused_manufacturer_facts.json');manifest={p['image_id']:p for p in read(root/'data/test/test_manifest.json')}
    admission=read(out/'admission_audit.json');prior_rows={p['image_id']:p for p in admission['scores']['aligned_reference']['all_selected']['per_photo']}
    expected_fail=[p['image_id'] for p in admission['scores']['aligned_reference']['failures']['per_photo'] if not p['correct']]
    check(scope=={'failure_ids':expected_fail,'control_ids':['P006','P014','P019'],'photo_ids':expected_fail+['P006','P014','P019']} and len(expected_fail)==14,'Selected development scope changed')
    plans={};initials={};active=[];passive=[]
    for image_id in scope['photo_ids']:
        directory=out/'photos'/image_id;plan=read(directory/'plan.json');initial=read(directory/'initial.json')
        def verify_initial():
            source=root/config['photo_inputs'][image_id]['source_directory'];assert source==root/('out/failure_recovery_completion/photos' if image_id=='P019' else 'out/failure_recovery/photos')/image_id
            assert initial=={'inventory':read(source/'inventory.json'),'comparison':read(source/'comparison.json',{})}
            independent_plan(plan,initial,facts)
            info=config['photo_inputs'][image_id]
            assert info['query_file']==manifest[image_id]['file'] and info['query_sha256']==sha((root/info['query_file']).read_bytes())
            assert info['target_ids']==[t['object_id'] for t in initial['inventory']['machines']]
            assert info['active_ids']==info['eligible_ids']==plan['active_ids']
        attempt(image_id+' initial provenance and trigger',verify_initial)
        plans[image_id]=plan;initials[image_id]=initial;(active if plan['active_ids'] else passive).append(image_id)
    check(active==config['body_ids'] and passive==config['tool_only_ids'] and len(active)==7 and len(passive)==10,'Runtime trigger population changed')
    for name,m in config['models'].items():
        check(m['provider']=='openrouter' and m['provider_only'] and m['input_token_bound']>0 and m['max_output_tokens']>0,'Invalid OpenRouter model binding: '+name)
    limits={'predicates':(20000,16384,.75,3.75),'checker':(16000,8192,2,10),'final':(28000,16384,.75,3.75),'ocr':(6000,128,.03,.13)}
    reservations={}
    for name,(i,o,p,c) in limits.items():
        m=config['models'][name];check((m['input_token_bound'],m['max_output_tokens'],m['input_usd_per_million'],m['output_usd_per_million'])==(i,o,p,c),'Model cap or rates changed: '+name)
        reservations[name]=(i*p+o*c)/1e6+(2*m['maximum_parser_fee_usd'] if name=='ocr' else 0)
    maximum=7*sum(reservations.values())*100
    check(abs(maximum-config['maximum_planned_guard_inr'])<1e-8 and abs(maximum-205.097648)<1e-8 and maximum<=config['budget']['stage_max_inr'],'Planned upper bound is incorrect')
    usage_checks=0
    for r in paid:
        def verify_usage():
            nonlocal usage_checks
            _,stage,image_id=logical(r).split(':');assert stage in reservations and image_id in active
            m=config['models'][stage];assert r['config_sha256']==cfg_sha and r['requested_model']==m['model'] and r['provider_route']=='openrouter'
            assert abs(r['reserved_cost_usd']-reservations[stage])<1e-12 and r['estimated_cost_usd']<=r['reserved_cost_usd']+1e-12
            if r.get('cost_basis')=='reserved_upper_bound_usage_unavailable':assert r['estimated_cost_usd']==r['reserved_cost_usd'];return
            u=r['usage_metadata'];assert u==r['provider_response']['usage'];p=u['prompt_tokens'];c=u['completion_tokens'];cached=u.get('prompt_tokens_details',{}).get('cached_tokens',0)
            assert all(type(v) is int and v>=0 for v in (p,c,cached)) and cached<=p and p<=m['input_token_bound'] and c<=m['max_output_tokens'] and u.get('total_tokens',p+c)==p+c
            token_cost=((p-cached)*m['input_usd_per_million']+cached*m.get('cached_input_usd_per_million',m['input_usd_per_million'])+c*m['output_usd_per_million'])/1e6
            cost=u.get('cost',token_cost)
            if stage=='ocr':
                assert abs(r['downstream_accounted_cost_usd']-cost)<1e-10 and r['ocr_parser_fee_reserve_usd']==m['maximum_parser_fee_usd']
                assert abs(r['estimated_cost_usd']-cost-m['maximum_parser_fee_usd'])<1e-10
            else:assert abs(token_cost-cost)<1e-9 and abs(r['estimated_cost_usd']-cost)<1e-10
            if r['status']=='ok':
                assert r['provider_response']['choices'][0]['finish_reason']=='stop' and r['model_version']==m['model']
                if stage in ('predicates','final'):assert r['provider']=='Google AI Studio'
                elif stage=='checker':assert r['provider']=='OpenAI'
                else:assert 'alibaba' in r['provider'].lower()
            usage_checks+=1
        attempt(r['job_id']+' cost and identity',verify_usage)
    ordered=sorted(physical(history[-100:])+paid,key=lambda r:r.get('request_started_unix',0))
    new_ids={r['job_id'] for r in paid};gaps=[];retry_checks=0
    for a,b in zip(ordered,ordered[1:]):
        if b['job_id'] not in new_ids:continue
        gap=b['request_started_unix']-a['request_finished_unix'];gaps.append(gap);check(gap>=15-.002,'Requests overlap or violate response-to-start pacing')
    for r in paid:
        if r.get('http_status')==429:
            _,n=r['job_id'].rsplit(':attempt:',1);base=[60,120,240][min(int(n)-1,2)]
            check(r['retry_delay_seconds']>=max(base,r.get('retry_after_seconds',0)),'Retry delay is shorter than policy');retry_checks+=1
    successes={logical(r):r for r in paid if r['status']=='ok'}
    completed=read(out/'completed_photos.json',[]);results=read(out/'results.json',[]);detections=read(out/'detections.json',{})
    check(len(completed)==len(set(completed)) and set(completed)<=set(scope['photo_ids']),'Invalid completed photo list')
    request_checks=0;gate_checks=0;crop_checks=0;ocr_checks=0
    sys.path.insert(0,str(root/'tools'))
    from pipeline_api import Client
    from focused_protocol import predicate_prompt,final_prompt
    from openrouter_ocr import read_crop
    panels=read(root/'out/failure_recovery/reference_panels.json')
    class Capture:
        def __init__(self):self.config=config
        def _call(self,job,operation,model,payload,url,reservation,parse):return sha(url.encode()+b'\n'+encoded(payload)),payload,reservation
    def capture_generation(stage,prompt,images):return Client.generate(Capture(),'unused',stage,prompt,images)
    def expected_images(image_id,plan,observations=None):
        nonlocal crop_checks
        directory=out/'photos'/image_id;source=root/config['photo_inputs'][image_id]['query_file'];records=[];images=[]
        def add(label,coords,filename,maximum=1024):
            nonlocal crop_checks
            from PIL import Image,ImageOps
            with Image.open(source) as original:w,h=ImageOps.exif_transpose(original).size
            bounds=crop_bounds(coords,w,h,.04);data,size=image_bytes(source,bounds,maximum)
            p=directory/filename;assert p.read_bytes()==data
            records.append({'label':label,'file':str(p.relative_to(root)),'pixel_box':bounds,'sha256':sha(data)});images.append((label,p));crop_checks+=1
        add('WHOLE SCENE',[0,0,1000,1000],'scene.jpg',1536)
        for target in plan['targets']:
            if target['object_id'] not in plan['active_ids']:continue
            name=target['object_id'];add('TARGET '+name,target['box_2d'],name+'_body.jpg')
            features=[f for f in target.get('observations',[]) if f.get('visible') and f['feature'] not in ('cleaner_head','wand')]
            for n,f in enumerate(features[:3]):add('TARGET '+name+' DETAIL '+str(n),f['box_2d'],name+'_detail_'+str(n)+'.jpg')
        if observations:
            for n,o in enumerate(observations['observations']):
                if o['state']=='present' and o['needs_check'] and o['box_2d']:add('QUESTION '+o['question_id'],o['box_2d'],'focus_'+str(n)+'.jpg')
        aliases={a for values in plan['focus_refs'].values() for a in values}
        images += [(p['panel_id'],root/p['file']) for p in panels['images'] if p['panel_id'].split('-')[0] in aliases]
        return images,records
    def verify_request(job,prompt,images,stage):
        nonlocal request_checks
        expected,payload,reservation=capture_generation(stage,prompt,images)
        for r in paid+[v for v in pending.values()]:
            if logical(r)==job:assert r['request_sha256']==expected and abs(r['reserved_cost_usd']-reservation)<1e-12
        context=json.loads(prompt.rsplit('\n',1)[-1]);assert not {'baseline','decision','confidence','source_url','source_title','label_basis'}&set(context)
        if stage!='final':assert set(context)=={'targets','questions','references'} and all(set(t)<= {'object_id','box_2d','role','visibility'} for t in context['targets'])
        request_checks+=sum(logical(r)==job for r in paid)
        return payload
    for image_id in scope['photo_ids']:
        directory=out/'photos'/image_id;plan=plans[image_id];initial=initials[image_id]
        if not plan['active_ids']:
            if image_id in completed:
                def verify_passive():
                    assert not [r for r in paid if logical(r).endswith(':'+image_id)]
                    assert all(not specific(t.get('readable_identifier','')) for t in initial['inventory']['machines'])
                    info=read(directory/'compatibility.json');assert info['new_paid_calls']==0 and not info['body_identified'] and info['exact_verified_part_code'] is None and info['manufacturer_sets']==facts['compatibility']
                attempt(image_id+' shared component skip',verify_passive)
            continue
        first='v4:predicates:'+image_id
        if not any(logical(r)==first for r in paid+list(pending.values())):continue
        def verify_photo():
            nonlocal gate_checks,ocr_checks
            images,records=expected_images(image_id,plan)
            assert read(directory/'predicate_images.json')==records
            verify_request(first,predicate_prompt(plan),images,'predicates')
            if first not in successes:return
            o=provider_json(successes[first]);check_predicates(o,plan);assert o==read(directory/'observations.json')
            question_ids=required_checks(plan,o);assert question_ids==read(directory/'checker_questions.json')
            images,records=expected_images(image_id,plan,o);assert records==read(directory/'focused_images.json')
            checks={'observations':[]};job='v4:checker:'+image_id
            if question_ids:
                verify_request(job,predicate_prompt(plan,question_ids),images,'checker')
                if job not in successes:return
                checks=provider_json(successes[job]);check_predicates(checks,plan,question_ids);assert checks==read(directory/'independent_checks.json')
            else:assert not [r for r in paid if logical(r)==job]
            expected_text=next((v for v in o['observations'] if v['question_id'].endswith('__identifier') and v['state']=='present' and (v['needs_check'] or re.search(r'(?i)\b(?:V\d{1,2}|GEN\s*5|CY\d+|SV\d+|\d{6}-\d{2})\b',v['literal_text']))),None)
            ocr=read(directory/'ocr.json',[]);job='v4:ocr:'+image_id
            if expected_text:
                if not any(logical(r)==job for r in paid+list(pending.values())):return
                expected_hash,payload,reservation=read_crop(Capture(),job,directory/'text_region.jpg')
                assert payload['plugins']==[{'id':'file-parser','pdf':{'engine':'mistral-ocr'}}]
                file_data=payload['messages'][0]['content'][1]['file']['file_data'];pdf=base64.b64decode(file_data.split(',',1)[1]);assert (directory/'text_region.jpg').read_bytes() in pdf and b'/Count 1' in pdf
                for r in paid+list(pending.values()):
                    if logical(r)==job:assert r['request_sha256']==expected_hash and abs(r['reserved_cost_usd']-reservation)<1e-12
                if job not in successes:return
                response=successes[job]['provider_response'];assert response['choices'][0]['finish_reason']=='stop'
                annotations=response['choices'][0]['message']['annotations'];files=[a['file'] for a in annotations if a.get('type')=='file' and isinstance(a.get('file'),dict)]
                assert len(files)==1;extracted=[p['text'] for p in files[0]['content'] if p.get('type')=='text' and isinstance(p.get('text'),str)];assert extracted
                literal_result={'literal_texts':extracted,'annotation_file_hash':files[0]['hash'],'engine':'mistral-ocr','evidence_source':'server file-parser annotations; downstream answer excluded'}
                assert successes[job]['result']==literal_result and len(ocr)==1 and ocr[0]['object_id']==expected_text['object_id'] and ocr[0]['query_box_2d']==expected_text['box_2d']
                assert all(ocr[0][k]==v for k,v in literal_result.items());ocr_checks+=1
            else:assert not ocr and not [r for r in paid if logical(r)==job]
            final_facts={**facts,'ocr_evidence':ocr};job='v4:final:'+image_id
            if any(logical(r)==job for r in paid+list(pending.values())):verify_request(job,final_prompt(plan,o,checks,final_facts),images,'final')
            if job not in successes:return
            raw=provider_json(successes[job]);parsed=focused_decisions(raw,plan,o,checks,final_facts,90)
            assert encoded(parsed)==encoded(read(directory/'comparison.json'))
            for name,row in parsed.items():
                for variant in ('focused_recovery','focused_raw'):
                    match,=[r for r in results if r['image_id']==image_id and r['instance_id']==image_id+'_'+name and r['variant']==variant]
                    assert encoded(match['raw'])==encoded(row['raw']) and encoded(match['candidate_checks'])==encoded(row['candidate_checks'])
                    assert encoded(match['decision'])==encoded(row['decision'] if variant=='focused_recovery' else raw_decision(row['raw'],facts['references']))
                gate_checks+=1
        attempt(image_id+' request, pixels and independent final gate',verify_photo)
    for image_id in completed:
        targets=initials[image_id]['inventory']['machines'];expected=[{**t,'instance_id':image_id+'_'+t['object_id']} for t in targets]
        check(detections.get(image_id)==expected,'Completed target coverage changed: '+image_id)
        for variant in ('focused_recovery','focused_raw'):
            rows=[r for r in results if r['image_id']==image_id and r['variant']==variant]
            check(aggregate(image_id,rows,detections)['complete'],'A completed physical target is missing: '+image_id+':'+variant)
    scores={};family_scores={}
    for variant in ('focused_recovery','focused_raw'):
        rows=[r for r in results if r['variant']==variant]
        check(len(rows)==len({(r['image_id'],r['instance_id']) for r in rows}),'Duplicate result instance: '+variant)
        scores[variant]={name:score(ids,manifest,rows,detections,completed,set(config['catalogue_order'])) for name,ids in [('failures',scope['failure_ids']),('controls',scope['control_ids']),('all_selected',scope['photo_ids'])]}
        family_scores[variant]={name:reference_family_score(ids,manifest,rows,detections,completed) for name,ids in [('failures',scope['failure_ids']),('controls',scope['control_ids'])]}
    final={p['image_id']:p for p in scores['focused_recovery']['all_selected']['per_photo']};transitions=[];outcomes=Counter()
    for image_id in scope['photo_ids']:
        a=prior_rows[image_id];b=final[image_id]
        outcome='not_run' if not b['completed'] else 'recovered_correct' if b['correct'] else ('still_unsure' if a['status']=='not_sure' else 'wrong_to_unsure') if b['status']=='not_sure' else 'new_wrong' if a['status']=='not_sure' else 'still_wrong'
        transitions.append({'image_id':image_id,'old_status':a['status'],'old_correct':a['correct'],'new_status':b['run_status'],'new_correct':b['correct'],'outcome':outcome})
        if image_id in scope['failure_ids']:outcomes[outcome]+=1
    control_regressions=[i for i in scope['control_ids'] if final[i]['completed'] and not final[i]['correct']]
    if args.require_complete:
        check(set(completed)==set(scope['photo_ids']) and len(completed)==17,'The selected17-photo cohort is incomplete')
        check(not pending and all(r['status']=='ok' for r in latest.values()),'A request remains pending or failed')
        check(gate_checks==sum(len(plans[i]['active_ids']) for i in active),'A completed body final gate was not independently reconstructed')
        receipt=read(out/'run_receipt.json',{});check(receipt.get('status')=='completed' and receipt.get('completed_count')==17 and receipt.get('inflight_count')==0,'Final run receipt is incomplete')
    previous_live=None
    def previous_audit():
        proc=subprocess.run([sys.executable,str(root/'out/failure_recovery_completion/independent_audit.py'),'--root',str(root),'--require-complete'],capture_output=True,text=True)
        r=json.loads(proc.stdout);assert proc.returncode==0 and r['audit_status']=='PASS' and r['combined_completed_photo_count']==23
        return {'status':'PASS','completed':23,'old58':r['integrity']['old58_live_audit'],'frozen_changes':r['integrity']['frozen_changes']}
    previous_live=attempt('Fresh prior strict audit',previous_audit)
    check(iou([0,0,500,500],[499,499,999,999])<.5 and iou([0,0,500,500],[0,0,500,500])==1,'Independent overlap self-check failed')
    report={'audit_status':'FAIL' if errors else 'PASS' if args.require_complete else 'IN_PROGRESS_CHECKS_PASS','errors':errors,'notes':notes,
      'completed_photo_count':len(completed),'selected_photo_count':17,'scores':scores,'exact_reference_family_scores':family_scores,'failure_outcomes':dict(outcomes),'transitions':transitions,'control_regressions_vs_original_correct_controls':control_regressions,
      'integrity':{'audit_source_sha256':sha(Path(__file__).read_bytes()),'config_sha256':cfg_sha,'frozen_file_count':len(config['frozen_files']),'frozen_changes':changes,'fresh_previous_phase':previous_live,
        'all_ten_ledgers_physical_jobs':len(physical(history+calls)),'duplicate_physical_job_ids':duplicates,'requests_reconstructed':request_checks,'independent_final_gates':gate_checks,'original_pixel_crops_checked':crop_checks,'server_ocr_annotations_checked':ocr_checks},
      'transport':{'physical_paid_calls':len(paid),'pending':list(pending),'usage_cost_checks':usage_checks,'recorded_429_retries':retry_checks,'minimum_finish_to_start_gap_seconds':min(gaps) if gaps else None},
      'costs':{'prior_nine_ledgers_accounted_usd':prior,'new_settled_usd':spent,'new_pending_reserve_usd':reserve,'new_accounted_usd':accounted,'new_reporting_inr':accounted*config['reporting_usd_inr'],'new_guard_inr':accounted*100,
         'combined_stage_guard_inr':(prior+accounted)*100,'remaining_guard_inr':1000-(prior+accounted)*100,'overall_guard_inr':config['budget']['prior_accounted_inr']+accounted*100,'stage_ceiling_inr':1000,'overall_ceiling_inr':2000,'maximum_planned_guard_inr':maximum},
      'scope':{'development_failures':14,'controls':3,'new_full58_accuracy_tested':False,'new_images_used':False,'training_used':False,'ocr_route':'OpenRouter only'}}
    print(json.dumps(report,indent=2));return 1 if errors else 0

if __name__=='__main__':raise SystemExit(main())
