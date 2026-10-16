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


def annotations(response):
    choice,=response['choices'];assert choice['finish_reason']=='stop'
    files=[a['file'] for a in choice['message'].get('annotations',[]) if a.get('type')=='file' and isinstance(a.get('file'),dict)]
    assert len(files)==1 and isinstance(files[0]['hash'],str) and files[0]['hash']
    parts=files[0]['content'];assert isinstance(parts,list) and all(isinstance(p,dict) for p in parts)
    assert all(isinstance(p.get('text'),str) for p in parts if p.get('type')=='text')
    texts=[p['text'] for p in parts if p.get('type')=='text']
    return {'literal_texts':texts,'no_text_extracted':not any(t.strip() for t in texts),'annotation_file_hash':files[0]['hash'],
            'engine':'mistral-ocr','evidence_source':'OpenRouter server file-parser annotations; downstream answer excluded'}

def content_texts(texts):
    result=[]
    for block in texts:
        value=re.sub(r'</?file(?:\s+[^>]*)?>','',block)
        value=re.sub(r'!\[[^\]]*\]\([^)]*\)','',value)
        for line in value.splitlines():
            line=line.strip()
            if not line or re.fullmatch(r'[\s|:-]*',line):continue
            result.append(line)
    return result


def candidates(texts):
    text='\n'.join(texts)
    parts=sorted(set(re.findall(r'(?<!\d)\d{6}-\d{2}(?!\d)',text)))
    models=sorted(set(m.group(0) for m in re.finditer(r'(?i)\b(?:gen\s*5\s*detect|wash\s*g1|v(?:8|11|12|15|16)(?:\s+(?:detect\s+slim|detect|piston\s+animal))?|CY23|shark\s+stratos)\b',text)))
    return {'possible_model_strings':models,'possible_part_codes':parts,'manufacturer_verified':False,'body_identity_accepted':False}

def exact_pdf(jpeg):
    from PIL import Image
    data=jpeg.read_bytes()
    with Image.open(jpeg) as im:assert im.format=='JPEG' and im.mode=='RGB';w,h=im.size
    stream=f'q {w} 0 0 {h} 0 0 cm /Im0 Do Q'.encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
      f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>'.encode(),
      f'<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n'.encode()+data+b'\nendstream',
      f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream']
    document=bytearray(b'%PDF-1.4\n');offsets=[0]
    for n,obj in enumerate(objects,1):offsets.append(len(document));document.extend(f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n')
    index=len(document);document.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:document.extend(f'{offset:010} 00000 n \n'.encode())
    document.extend(f'trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{index}\n%%EOF\n'.encode());return bytes(document)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--require-complete',action='store_true');args=parser.parse_args()
    root=args.root.resolve();out=root/'out/targeted_ocr';errors=[];notes=[]
    def check(condition,message):
        if not condition:errors.append(message)
    def attempt(name,fn):
        try:return fn()
        except Exception as exc:errors.append(name+': '+type(exc).__name__+': '+str(exc));return None
    check(content_texts(['<file name=\"region.pdf\">','| ![img-0.jpeg](img-0.jpeg) | |','| --- | :--: |','</file>'])==[], 'Wrapper/table removal self-check failed')
    check(content_texts(['| 972213-02 | ![img-0.jpeg](img-0.jpeg) |'])==['| 972213-02 |  |'], 'Content preservation self-check failed')
    check(content_texts(['UOSho'])==['UOSho'], 'Literal fragment preservation self-check failed')
    config=read(root/'data/targeted_ocr_config.json')
    if not config:
        print(json.dumps({'audit_status':'AWAITING_ACTIVATION','errors':['Configuration is not frozen'] if args.require_complete else []},indent=2));return int(args.require_complete)
    config_sha=sha(encoded(config));frozen_changes=[p for p,h in config['frozen_files'].items() if not (root/p).exists() or sha((root/p).read_bytes())!=h]
    check(not frozen_changes,'A frozen source, input or historical result changed')
    previous=read(root/'data/focused_recovery_config.json');check(all(config['frozen_files'].get(p)==h for p,h in previous['frozen_files'].items()),'An inherited expected hash changed or was omitted')
    check(read(out/'frozen_config.json',config)==config,'Transport configuration differs')
    checks=read(out/'admission_audits.json');completed_audit=checks['prior_complete'];stopped_audit=checks['focused_stopped']
    old_failures=completed_audit['scores']['aligned_reference']['failures']['per_photo']
    expected=[p['image_id'] for p in old_failures if not p['correct']];expected=['P054']+[p for p in expected if p!='P054']
    check(config['scope']==expected and len(expected)==14 and not set(expected)&{'P006','P014','P019'},'OCR scope differs from one wrong case and13 unsure photos')
    check(sum(p['status']=='not_sure' for p in old_failures if not p['correct'])==13,'The admitted prior uncertainty population changed')
    histories=config['previous_ledgers'];prior=0;old_calls=[]
    check(len(histories)==10 and len({p['file'] for p in histories})==10,'Ten previous ledgers are not counted once')
    for item in histories:
        path=root/item['file'];rows=ledger(path);cost=sum(r['estimated_cost_usd'] for r in rows);old_calls+=rows;prior+=cost
        check(sha(path.read_bytes())==item['sha256'] and abs(cost-item['accounted_cost_usd'])<1e-10,'Historical ledger hash or cost differs: '+item['file'])
        check(not read(path.with_name('inflight.json'),{}),'Historical request remains pending')
    check(abs(prior-7.851389111)<1e-10,'Prior spending differs from the ten-ledger admission')
    check(config['budget']['usd_inr']==100 and config['stage_ceiling_inr']==1000 and config['budget']['total_max_inr']==2000,'Authorised ceilings changed')
    check(abs(config['budget']['stage_max_inr']-(1000-prior*100))<1e-8 and abs(config['budget']['prior_accounted_inr']-prior*100-42.68)<1e-8,'Prior spending was omitted from budget')
    check(config['models']=={'ocr':previous['models']['ocr']},'OCR binding changed from the approved frozen route')
    model=config['models']['ocr'];check(model['provider']=='openrouter' and model['provider_only']==['alibaba'] and model['model']=='qwen/qwen3.7-flash','OCR transport or receipt model changed')
    reservation=(model['input_token_bound']*model['input_usd_per_million']+model['max_output_tokens']*model['output_usd_per_million'])/1e6+2*model['maximum_parser_fee_usd']
    check(abs(reservation-.02019664)<1e-12 and abs(config['maximum_first_attempts_guard_inr']-14*reservation*100)<1e-8,'OCR reservation changed')
    check(config.get('full58_retested') is False,'OCR subset is described as a full58 test')
    for image_id in expected:
        info=config['photo_inputs'][image_id];old=read(root/'out/focused_recovery/photos'/image_id/'initial.json');target,=old['inventory']['machines'];query=previous['photo_inputs'][image_id]
        check(info=={'query_file':query['query_file'],'query_sha256':query['query_sha256'],'object_id':target['object_id'],'query_box_2d':target['box_2d']},'Submitted physical target changed: '+image_id)
        check(sha((root/info['query_file']).read_bytes())==info['query_sha256'],'Original image changed: '+image_id)
    calls=ledger(out/'calls.jsonl');paid=physical(calls);latest={logical(r):r for r in calls};paid_ids={r['job_id'] for r in paid}
    duplicate_jobs=[j for j,n in Counter(r['job_id'] for r in physical(old_calls+calls)).items() if n>1];check(not duplicate_jobs,'A physical paid job is duplicated')
    check(len(calls)==len(paid),'An unreviewed offline or validation event exists')
    check(all(logical(r).startswith('ocr14:') and logical(r)[6:] in expected and r['operation']=='ocr' for r in paid),'An out-of-scope or non-OCR call exists')
    check(all(r['config_sha256']==config_sha for r in calls),'New ledger configuration differs')
    pending=read(out/'inflight.json',{});settled={r['job_id'] for r in calls};pending={j:r for j,r in pending.items() if j not in settled}
    check(len(pending)<=1,'More than one request is pending')
    spent=sum(r['estimated_cost_usd'] for r in calls);pending_reserve=sum(r['reserved_cost_usd'] for r in pending.values());accounted=spent+pending_reserve
    check((prior+accounted)*100<=1000+1e-8 and config['budget']['prior_accounted_inr']+accounted*100<=2000+1e-8,'Budget exceeded')
    check(not [r for r in latest.values() if r['status']!='ok' and not(r.get('http_status')==429 and not r.get('retry_exhausted'))],'A terminal OCR failure is unresolved')
    usage_checks=0;extra_fee=0;provider_total=0
    for r in paid:
        def verify_usage():
            nonlocal usage_checks,extra_fee,provider_total
            assert r['requested_model']==model['model'] and r['provider_route']=='openrouter' and abs(r['reserved_cost_usd']-reservation)<1e-12 and r['estimated_cost_usd']<=reservation+1e-12
            if r['cost_basis']=='reserved_upper_bound_usage_unavailable':assert r['estimated_cost_usd']==reservation;return
            usage=r['usage_metadata'];assert usage==r['provider_response']['usage'];i=usage['prompt_tokens'];o=usage['completion_tokens'];cached=usage.get('prompt_tokens_details',{}).get('cached_tokens',0)
            assert all(type(x) is int and x>=0 for x in (i,o,cached)) and cached<=i<=model['input_token_bound'] and o<=model['max_output_tokens']
            token_cost=((i-cached)*model['input_usd_per_million']+cached*model['cached_input_usd_per_million']+o*model['output_usd_per_million'])/1e6
            charge=usage.get('cost',token_cost);assert isinstance(charge,(int,float)) and math.isfinite(charge) and charge>=0
            assert abs(r['downstream_accounted_cost_usd']-charge)<1e-10 and r['ocr_parser_fee_reserve_usd']==model['maximum_parser_fee_usd']
            assert r['downstream_cost_basis']==('provider_reported_cost' if 'cost' in usage else 'reported_tokens_and_configured_rates') and r['cost_basis']==r['downstream_cost_basis']+'_plus_unreconciled_ocr_fee_reserve'
            assert abs(r['estimated_cost_usd']-charge-model['maximum_parser_fee_usd'])<1e-10
            if 'cost' not in usage:assert abs(charge-token_cost)<1e-10
            else:assert charge+1e-10>=token_cost and charge<=token_cost+model['maximum_parser_fee_usd']+1e-8
            if r['status']=='ok':assert r['model_version']==model['model'] and 'alibaba' in r['provider'].lower()
            extra_fee+=r['ocr_parser_fee_reserve_usd'];provider_total+=charge;usage_checks+=1
        attempt(r['job_id']+' metering',verify_usage)
    ordered=sorted(physical(old_calls)+paid,key=lambda r:r.get('request_started_unix',0));gaps=[];retry_checks=0
    for a,b in zip(ordered,ordered[1:]):
        if b['job_id'] not in paid_ids:continue
        gap=b['request_started_unix']-a['request_finished_unix'];gaps.append(gap);check(gap>=15-.002,'Pacing or overlap violation')
        if logical(a)==logical(b) and a.get('http_status')==429:check(gap>=a['retry_delay_seconds']-.002,'Recorded retry backoff was not observed')
    for r in paid:
        if r.get('http_status')==429:
            n=int(r['job_id'].rsplit(':attempt:',1)[1]);base=[60,120,240][min(n-1,2)]
            check(r['retry_delay_seconds']>=max(base,r.get('retry_after_seconds',0)),'429 backoff is too short');retry_checks+=1
    results=read(out/'results.json',[]);result_ids=[r['image_id'] for r in results]
    check(len(result_ids)==len(set(result_ids)) and set(result_ids)<=set(expected),'Result population differs')
    successes={logical(r):r for r in paid if r['status']=='ok'}
    sys.path.insert(0,str(root/'tools'))
    from openrouter_ocr import read_crop
    class Capture:
        config={'models':{'ocr':model}}
        def _call(self,job,operation,used_model,payload,url,bound,parse):return sha(url.encode()+b'\n'+encoded(payload)),payload,bound
    request_checks=0;pixel_checks=0;annotation_checks=0
    all_current=paid+list(pending.values())
    for image_id in expected:
        job='ocr14:'+image_id;directory=out/'photos'/image_id;info=config['photo_inputs'][image_id]
        if not any(logical(r)==job for r in all_current):continue
        def verify_photo():
            nonlocal request_checks,pixel_checks,annotation_checks
            from PIL import Image,ImageOps
            source=root/info['query_file'];crop=directory/'object.jpg'
            with Image.open(source) as im:w,h=ImageOps.exif_transpose(im).size
            bounds=crop_bounds(info['query_box_2d'],w,h,.04);data,size=image_bytes(source,bounds,1536)
            assert crop.read_bytes()==data
            record={'file':str(crop.relative_to(root)),'pixel_box':bounds,'sha256':sha(data)};assert record==read(directory/'crop.json');pixel_checks+=1
            expected_sha,payload,bound=read_crop(Capture(),job,crop)
            assert payload['model']==model['model'] and payload['plugins']==[{'id':'file-parser','pdf':{'engine':'mistral-ocr'}}]
            assert payload['reasoning']=={'enabled':False} and payload['provider']['only']==['alibaba'] and payload['provider']['allow_fallbacks'] is False
            message,=payload['messages'];assert message['role']=='user';receipt,file=message['content']
            assert receipt=={'type':'text','text':'Return JSON {"processed":true}. Do not identify products or add text. The file-parser annotations will be retained separately.'}
            assert file['type']=='file' and file['file']['filename']=='region.pdf'
            assert base64.b64decode(file['file']['file_data'].split(',',1)[1])==exact_pdf(crop)
            for r in all_current:
                if logical(r)==job:assert r['request_sha256']==expected_sha and abs(r['reserved_cost_usd']-bound)<1e-12
            request_checks+=sum(logical(r)==job for r in paid)
            if job not in successes:return
            physical=successes[job];ocr=annotations(physical['provider_response']);assert ocr==physical['result']
            candidate=candidates(ocr['literal_texts'])
            result={'image_id':image_id,'object_id':info['object_id'],'query_box_2d':info['query_box_2d'],'location_kind':'submitted original-image crop; no per-character boxes','crop':record,'ocr':ocr,'candidates':candidate}
            assert result==read(directory/'ocr.json')
            saved,=[r for r in results if r['image_id']==image_id];assert saved==result;annotation_checks+=1
        attempt(image_id+' original pixels, request and parser annotation',verify_photo)
    with_text=sum(not r['ocr']['no_text_extracted'] for r in results);specific_count=sum(bool(r['candidates']['possible_model_strings'] or r['candidates']['possible_part_codes']) for r in results)
    actual_text_count=sum(bool(content_texts(r['ocr']['literal_texts'])) for r in results)
    wrapper_only=[r['image_id'] for r in results if not r['ocr']['no_text_extracted'] and not content_texts(r['ocr']['literal_texts'])]
    if wrapper_only:notes.append('The frozen photos_with_text field includes transport wrappers; use photos_with_actual_content_text for interpretation.')
    board=read(out/'scoreboard.json',{});board_current=bool(board and board.get('completed_count')==len(results) and abs(board.get('costs',{}).get('new_accounted_usd',-1)-accounted)<1e-10)
    if board_current:
        check(board['selected_count']==14 and board['completed_ids']==result_ids and board['photos_with_text']==with_text and board['photos_with_specific_candidate']==specific_count,'Saved extraction counts differ')
        check(board['accepted_body_identities']==0 and board['full58_matching_accuracy_retested'] is False,'Unverified OCR text was accepted as identity or full58 accuracy')
        costs={'new_accounted_usd':accounted,'new_reporting_inr':accounted*config['reporting_usd_inr'],'new_guard_inr':accounted*100,'pending_reserve_usd':pending_reserve,
          'retained_parser_fee_reserve_usd':sum(r.get('ocr_parser_fee_reserve_usd',0) for r in calls),'combined_stage_guard_inr':(prior+accounted)*100,'remaining_guard_inr':1000-(prior+accounted)*100,'overall_guard_inr':config['budget']['prior_accounted_inr']+accounted*100}
        check(set(board['costs'])==set(costs) and all(abs(board['costs'][k]-v)<1e-8 for k,v in costs.items()),'Saved financial summary differs')
    elif paid:notes.append('The saved scoreboard is stale while a request is active.')
    fresh_audits={}
    for name,path,wanted in [('completed23','out/failure_recovery_completion/independent_audit.py','PASS'),('focused_stop','out/focused_recovery/independent_audit.py','FAIL')]:
        def verify_prior():
            proc=subprocess.run([sys.executable,str(root/path),'--root',str(root)]+(['--require-complete'] if wanted=='PASS' else []),capture_output=True,text=True)
            value=json.loads(proc.stdout);assert value['audit_status']==wanted
            if wanted=='PASS':assert proc.returncode==0 and value['combined_completed_photo_count']==23
            else:
                assert proc.returncode==1 and value['errors']==['A terminal error or validation failure is unresolved'] and value['completed_photo_count']==0 and not value['transport']['pending']
                old,=ledger(root/'out/focused_recovery/calls.jsonl');choice,=old['provider_response']['choices']
                assert old['error']=='Incomplete provider result: length' and old['http_status']==200 and choice['finish_reason']=='length' and choice['native_finish_reason']=='MAX_TOKENS' and abs(old['estimated_cost_usd']-.07347975)<1e-12
            return {'audit_status':value['audit_status'],'errors':value['errors'],'source_sha256':sha((root/path).read_bytes()),'frozen_changes':value['integrity']['frozen_changes']}
        fresh_audits[name]=attempt('Fresh '+name+' audit',verify_prior)
    if args.require_complete:
        check(len(results)==14 and set(result_ids)==set(expected),'OCR cohort is incomplete')
        check(not pending and all(r['status']=='ok' for r in latest.values()),'A request remains pending or failed')
        check(annotation_checks==14 and request_checks==len(paid),'An extraction or request was not independently verified')
        check(board_current,'The final scoreboard is absent or stale')
        receipt=read(out/'run_receipt.json',{})
        check(receipt.get('status')=='completed' and receipt.get('completed_count')==14 and receipt.get('workers')==1 and receipt.get('inflight_count')==0 and receipt.get('error') is None,'Final receipt is incomplete')
        check(receipt.get('costs')==board.get('costs'),'Receipt and scoreboard costs differ')
    report={'audit_status':'FAIL' if errors else 'PASS' if args.require_complete else 'IN_PROGRESS_CHECKS_PASS','errors':errors,'notes':notes,'completed_count':len(results),'selected_count':14,
      'ocr_counts':{'photos_with_nonempty_annotation_text':with_text,'photos_with_actual_content_text':actual_text_count,'transport_wrapper_only_photo_ids':wrapper_only,'photos_without_actual_content_text':len(results)-actual_text_count,'photos_with_specific_candidate':specific_count,'manufacturer_verified_body_identities':0,'not_run':14-len(results)},
      'per_photo':[{'image_id':r['image_id'],'literal_texts':r['ocr']['literal_texts'],'content_texts_excluding_transport_wrappers':content_texts(r['ocr']['literal_texts']),'candidates':r['candidates']} for r in results],
      'integrity':{'audit_source_sha256':sha(Path(__file__).read_bytes()),'config_sha256':config_sha,'frozen_file_count':len(config['frozen_files']),'frozen_changes':frozen_changes,'fresh_prior_audits':fresh_audits,
        'all_eleven_ledgers_physical_jobs':len(physical(old_calls+calls)),'duplicate_physical_jobs':duplicate_jobs,'requests_reconstructed':request_checks,'original_pixel_crops_checked':pixel_checks,'server_annotations_checked':annotation_checks},
      'transport':{'physical_calls':len(paid),'usage_cost_checks':usage_checks,'pending':list(pending),'recorded429':retry_checks,'minimum_finish_to_start_gap_seconds':min(gaps) if gaps else None},
      'costs':{'prior_ten_ledgers_accounted_usd':prior,'new_settled_usd':spent,'pending_reserve_usd':pending_reserve,'new_accounted_usd':accounted,'reported_or_token_derived_cost_usd':provider_total,'extra_parser_fee_reserve_usd':extra_fee,
        'new_reporting_inr':accounted*config['reporting_usd_inr'],'new_guard_inr':accounted*100,'combined_stage_guard_inr':(prior+accounted)*100,'remaining_guard_inr':1000-(prior+accounted)*100,'overall_guard_inr':config['budget']['prior_accounted_inr']+accounted*100,
        'stage_ceiling_inr':1000,'overall_ceiling_inr':2000,'maximum_first_attempts_guard_inr':14*reservation*100},'scope':{'all58_tested':False,'controls_tested':False,'source_labels_changed':False,'body_identity_recovery_claimed':False,'ocr_route':'OpenRouter Mistral server file-parser only'}}
    print(json.dumps(report,indent=2));return 1 if errors else 0

if __name__=='__main__':raise SystemExit(main())
