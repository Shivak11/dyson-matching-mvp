#!/usr/bin/env python3
"""Read saved Dyson evidence without model calls or project writes."""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
DEFAULT_ROOT = Path('/Users/shivakakkar/Python Projects/dyson-matching-mvp/.worktrees/test-set')


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_ledger(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def logical(row):
    return row.get('logical_job_id', row['job_id'])


def physical(rows):
    return [r for r in rows if 'reserved_cost_usd' in r and r.get('cost_basis') not in ('offline_validation_recovery','offline_usage_bound_recovery')]


def box_ok(box):
    return (isinstance(box, list) and len(box) == 4
            and all(not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x) for x in box)
            and 0 <= box[0] < box[2] <= 1000 and 0 <= box[1] < box[3] <= 1000)


def intersects(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def response_json(row):
    response = row['provider_response']
    assert len(response['choices']) == 1, 'Expected exactly one returned choice'
    choice = response['choices'][0]
    assert choice['finish_reason'] == 'stop', 'Provider did not finish the response'
    raw = json.loads(choice['message']['content'])
    assert raw == row['result'], 'Ledger result differs from provider response'
    assert isinstance(raw, dict)
    return raw


def verify_usage_bound_original(row, model):
    """Check the one completed P058 response rejected by the input estimate."""
    assert row['job_id']=='v2long:refine:P058:attempt:1'
    assert row['status']=='error' and row['error']=='Reported input tokens exceed reserved bound'
    assert row['http_status']==200 and row['cost_basis']=='provider_reported_cost'
    assert row['provider']=='Google AI Studio' and row['requested_model']==model['model'] and row['model_version']==model['model']
    raw=response_json(row)
    usage=row['usage_metadata']
    assert usage==row['provider_response']['usage'], 'Usage differs from original provider response'
    for key in ('prompt_tokens','completion_tokens','total_tokens'):
        assert isinstance(usage[key],int) and not isinstance(usage[key],bool) and usage[key]>=0
    assert usage['prompt_tokens']==37957 and usage['completion_tokens']==5744
    assert usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens']
    assert usage['prompt_tokens']>model['input_token_bound'] and usage['completion_tokens']<=model['max_output_tokens']
    assert usage.get('prompt_tokens_details',{}).get('cached_tokens',0)==0
    prompt_cost=usage['prompt_tokens']*model['input_usd_per_million']/1_000_000
    completion_cost=usage['completion_tokens']*model['output_usd_per_million']/1_000_000
    calculated=prompt_cost+completion_cost
    assert abs(calculated-.05000775)<1e-12
    assert abs(usage['cost']-calculated)<1e-12 and abs(row['estimated_cost_usd']-calculated)<1e-12
    assert abs(usage['cost_details']['upstream_inference_prompt_cost']-prompt_cost)<1e-12
    assert abs(usage['cost_details']['upstream_inference_completions_cost']-completion_cost)<1e-12
    assert abs(usage['cost_details']['upstream_inference_cost']-calculated)<1e-12
    assert calculated<=row['reserved_cost_usd'] and abs(row['reserved_cost_usd']-.14388)<1e-12
    return raw


def observation_result(raw):
    objects = copy.deepcopy(raw['objects'])
    by_id = {obj['object_id']: obj for obj in objects}
    assert len(objects) == len(by_id), 'Duplicate observed object ID'
    for obj in objects:
        assert obj['role'] in ('machine', 'partial_machine', 'accessory')
        assert box_ok(obj['box_2d']), 'Invalid machine box'
        obj.setdefault('parent_id', None)
        parent = obj['parent_id']
        assert obj['role'] == 'accessory' or parent is None
        if parent is not None:
            assert parent in by_id and parent != obj['object_id'] and by_id[parent]['role'] != 'accessory'
        for feature in obj['observations']:
            if feature['visible']:
                assert box_ok(feature['box_2d']) and intersects(feature['box_2d'], obj['box_2d'])
            else:
                assert feature.get('box_2d') is None
                feature['box_2d'] = None
    machines = [obj for obj in objects if obj['role'] != 'accessory']
    if not machines and objects:
        union = [min(o['box_2d'][0] for o in objects), min(o['box_2d'][1] for o in objects),
                 max(o['box_2d'][2] for o in objects), max(o['box_2d'][3] for o in objects)]
        machines = [{**objects[0], 'role': 'partial_machine', 'parent_id': None,
                     'visibility': 'part_only', 'box_2d': union, 'accessory_only': True,
                     'observations': [f for o in objects for f in o['observations']][:4], 'readable_identifier': ''}]
    return {'objects': objects, 'machines': machines}


def gate(raw, candidates, threshold):
    """Reproduce decision rules independently of product validators and scorer."""
    result = copy.deepcopy(raw)
    decision = result['decision']
    assert decision['status'] in ('match', 'not_sure', 'not_in_catalogue')
    for key in ('top_two', 'missing_evidence', 'contradictions'):
        if decision.get(key) is None:
            decision[key] = []
    if decision.get('retake') is None:
        decision['retake'] = ''
    if decision['status'] == 'not_in_catalogue':
        decision['top_two'] = [v for v in decision['top_two'] if v is not None]
    confidence = decision['confidence']
    assert not isinstance(confidence, bool) and isinstance(confidence, (int, float)) and math.isfinite(confidence)
    assert 0 <= confidence <= 100 and confidence == int(confidence), 'Confidence unit/scale error'
    assert decision['product'] in candidates if decision['status'] == 'match' else decision['product'] is None
    assert isinstance(decision.get('evidence'),list) and all(isinstance(v,str) for v in decision['evidence'])
    assert all(isinstance(decision[key],list) and all(isinstance(v,str) for v in decision[key]) for key in ('missing_evidence','contradictions'))
    assert isinstance(decision['retake'],str)
    assert isinstance(decision['top_two'],list) and len(decision['top_two'])<=2
    assert all(isinstance(p,str) and p.strip() for p in decision['top_two'])
    assert len(set(decision['top_two']))==len(decision['top_two']) and all(p in candidates for p in decision['top_two']), 'Invalid advisory catalogue alternatives'
    assert result.get('decisive_region') is None or box_ok(result['decisive_region'])
    assert 'refinement_reason' not in result or isinstance(result['refinement_reason'],str)
    assert 'evidence_conflict' not in result or isinstance(result['evidence_conflict'],bool)
    checks = result['candidate_checks']
    assert len(checks) == len(candidates) and sorted(x['product'] for x in checks) == sorted(candidates)
    for check in checks:
        if check['outcome'] == 'not_sure':
            check['outcome'] = 'insufficient_evidence'
        assert check['outcome'] in ('confirmed', 'contradicted', 'insufficient_evidence')
        assert isinstance(check['evidence'], str) and check['evidence'].strip()
    confirmed = [c['product'] for c in checks if c['outcome'] == 'confirmed']
    inconsistent = (decision['status'] == 'match' and confirmed != [decision['product']]
                    or decision['status'] == 'not_in_catalogue' and any(c['outcome'] != 'contradicted' for c in checks))
    low = decision['status'] == 'match' and confidence < threshold
    if inconsistent or low:
        decision['raw_status'], decision['raw_product'] = decision['status'], decision['product']
        decision['status'], decision['product'] = 'not_sure', None
        decision['missing_evidence'].append('Candidate checks conflict with the final answer.' if inconsistent
                                             else 'Evidence strength below the frozen automatic-match threshold.')
        decision['retake'] = decision['retake'] or 'Photograph the motor, dust bin, controls and any model label clearly.'
    return result


def normalise_advisory(raw, candidates, negatives):
    """Independently reproduce the sole authorised repair, without product code."""
    result=copy.deepcopy(raw)
    assert isinstance(result,dict) and isinstance(result.get('results'),list)
    objects=[item.get('object_id') for item in result['results']]
    assert len(objects)==len(set(objects)) and set(objects)==set(candidates)
    removals={}
    for item in result['results']:
        decision=item['decision']
        alternatives=decision['top_two']
        assert isinstance(alternatives,list) and len(alternatives)<=2
        assert all(isinstance(v,str) and v.strip() for v in alternatives)
        assert len(alternatives)==len(set(alternatives))
        removed=[value for value in alternatives if value not in candidates[item['object_id']]]
        if not removed:
            continue
        assert decision['status']=='not_sure' and decision['product'] is None
        assert set(removed)<=set(negatives), 'Repair would remove an unknown or unsupplied catalogue ID'
        for key in ('format_repairs','unverified_alternatives'):
            assert key not in item or isinstance(item[key],list) and all(isinstance(v,str) for v in item[key])
        decision['top_two']=[value for value in alternatives if value in candidates[item['object_id']]]
        item.setdefault('format_repairs',[]).append('Known non-catalogue advisory alternatives removed from top_two: '+', '.join(removed)+'.')
        item.setdefault('unverified_alternatives',[]).extend(removed)
        removals[item['object_id']]=removed
    assert removals, 'No bounded advisory repair exists'
    return result,removals


def requires_refinement(result, ranking, threshold):
    d = result['decision']
    return (d['status'] != 'match' or d['confidence'] < threshold or bool(d.get('raw_status'))
            or bool(d.get('contradictions')) or bool(result.get('evidence_conflict'))
            or bool(ranking and d['product'] != ranking[0]['product']))


def aggregate(image_id, rows, detections):
    objects = detections.get(image_id)
    saved = [r for r in rows if r['image_id'] == image_id]
    ids = [r['instance_id'] for r in saved if not r.get('detection_missed')]
    expected = {o['instance_id'] for o in objects} if objects is not None else set()
    complete = objects is not None and bool(saved) and set(ids) == expected and len(ids) == len(set(ids))
    decision = {'status': 'not_sure', 'product': None, 'confidence': 0}
    if not complete or not objects or any(r.get('detection_missed') for r in saved):
        return {**decision, 'complete': complete}
    answers = [r['decision'] for r in saved]
    statuses = {r['status'] for r in answers}
    products = {r['product'] for r in answers if r['status'] == 'match'}
    if statuses == {'not_in_catalogue'} or statuses == {'match'} and len(products) == 1:
        decision = {'status': answers[0]['status'], 'product': answers[0]['product'],
                    'confidence': min(r['confidence'] for r in answers)}
    return {**decision, 'complete': complete}


def score(manifest, rows, detections, catalogue):
    singles, multis = [], []
    for photo in manifest:
        image_id = photo['image_id']
        if photo['evaluation_role'] == 'labelled_single':
            d = aggregate(image_id, rows, detections)
            label = photo['labels'][0]
            correct = d['status'] == 'match' and d['product'] == label or d['status'] == 'not_in_catalogue' and label not in catalogue
            singles.append({**d, 'image_id': image_id, 'source_label': label, 'correct': correct})
        elif photo['evaluation_role'] == 'labelled_multi':
            answers = [r for r in rows if r['image_id'] == image_id]
            coverage = aggregate(image_id, rows, detections)['complete']
            predicted = sorted({r['decision']['product'] for r in answers if r['decision']['status'] == 'match'})
            expected = sorted(set(photo['labels']) & set(catalogue))
            unresolved = not coverage or not detections.get(image_id) or any(r.get('detection_missed') or r['decision']['status'] == 'not_sure' for r in answers)
            outside = sum(r['decision']['status'] == 'not_in_catalogue' for r in answers)
            multis.append({'image_id': image_id, 'expected_identity_set': expected, 'predicted_identity_set': predicted,
                           'correct_resolved_identity_set': predicted == expected and not unresolved and not outside,
                           'unresolved': unresolved, 'outside_instance_count': outside, 'result_complete': coverage})
    wrong = [r for r in singles if r['status'] != 'not_sure' and not r['correct']]
    metrics = {'single_photo_count': len(singles), 'correct_total': sum(r['correct'] for r in singles),
               'wrong_total': len(wrong), 'confidently_wrong_count': sum(r['confidence'] >= 90 for r in wrong),
               'not_sure_count': sum(r['status'] == 'not_sure' for r in singles),
               'resolved_count': sum(r['status'] != 'not_sure' for r in singles)}
    metrics['accuracy'] = metrics['correct_total'] / len(singles) if singles else None
    return {'metrics': metrics, 'per_photo': singles, 'multi_photo_results': multis}


def self_check():
    raw = {'decision':{'status':'match','product':'a','confidence':95,'top_two':['a','b'],
                       'evidence':['Visible feature.'],'missing_evidence':[],'contradictions':[],'retake':''},
           'candidate_checks':[{'product':'a','outcome':'confirmed','evidence':'Visible detail.'},
                               {'product':'b','outcome':'contradicted','evidence':'Incompatible detail.'}]}
    assert gate(raw,['a','b'],90)['decision']['status']=='match'
    low=copy.deepcopy(raw);low['decision']['confidence']=80
    assert gate(low,['a','b'],90)['decision']['status']=='not_sure'
    fraction=copy.deepcopy(raw);fraction['decision']['confidence']=.95
    try:
        gate(fraction,['a','b'],90)
    except AssertionError:
        pass
    else:
        raise AssertionError('Control failed to reject fractional confidence')
    outside=copy.deepcopy(raw);outside['decision'].update(status='not_in_catalogue',product=None)
    assert gate(outside,['a','b'],90)['decision']['status']=='not_sure'
    row={'image_id':'one','instance_id':'one_o1','decision':raw['decision']}
    assert aggregate('one',[row],{'one':[{'instance_id':'one_o1'}]})['status']=='match'
    assert aggregate('one',[row],{'one':[{'instance_id':'one_o1'},{'instance_id':'one_o2'}]})['status']=='not_sure'
    assert aggregate('one',[row],{})['status']=='not_sure'
    unresolved=copy.deepcopy(raw);unresolved.update(object_id='o1');unresolved['decision'].update(status='not_sure',product=None,confidence=40,top_two=['a','negative'])
    batch={'results':[unresolved]};before=copy.deepcopy(batch)
    repaired,removed=normalise_advisory(batch,{'o1':['a','b']},{'negative'})
    assert batch==before and removed=={'o1':['negative']}
    assert repaired['results'][0]['decision']=={**unresolved['decision'],'top_two':['a']}
    assert gate(repaired['results'][0],['a','b'],90)['decision']['status']=='not_sure'
    for status,product,alternative in [('match','a','negative'),('not_sure',None,'unknown'),('not_in_catalogue',None,'negative')]:
        invalid=copy.deepcopy(batch);invalid['results'][0]['decision'].update(status=status,product=product,top_two=['a',alternative])
        try:
            normalise_advisory(invalid,{'o1':['a','b']},{'negative'})
        except AssertionError:
            pass
        else:
            raise AssertionError('Control allowed an unauthorised repair')
    return 11


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    self_checks = self_check()
    root = args.root.resolve()
    out = root / 'out/pipeline_v2_full'
    full_config = read(root/'data/pipeline_v2_full_config.json')
    standard_config = read(root/'data/pipeline_v2_continuation_config.json')
    config = read(root/'data/pipeline_v2_recovery_config.json')
    standard = root/'out/pipeline_v2_continuation'
    continuation = root/'out/pipeline_v2_recovery'
    standard_snapshot = standard/'prior_phase_snapshot'
    snapshot = continuation/'prior_phase_snapshot'
    recovery_full_snapshot=snapshot/'out/pipeline_v2_full'
    manifest = read(root/'data/test/test_manifest.json')
    completed = read(out/'completed_photos.json', [])
    detections = read(out/'detections.json', {})
    results = read(out/'results.json', [])
    catalogue = config['catalogue_order']
    errors, notes = [], []
    def check(condition, message):
        if not condition:
            errors.append(message)
    def attempt(label, fn):
        try:
            return fn()
        except Exception as exc:
            errors.append(label + ': ' + str(exc))
            return None

    frozen_changes = [p for p,h in config['frozen_files'].items() if not (root/p).exists() or digest((root/p).read_bytes()) != h]
    check(not frozen_changes, 'Frozen files changed')
    snapshot_changes = [name for name,h in config['prior_phase_evidence'].items() if not (snapshot/name).exists() or digest((snapshot/name).read_bytes())!=h]
    check(not snapshot_changes,'Prior phase snapshot changed')
    previous_completed = read(recovery_full_snapshot/'completed_photos.json',[])
    previous_results = read(recovery_full_snapshot/'results.json',[])
    previous_detections = read(recovery_full_snapshot/'detections.json',{})
    check([r for r in results if r['image_id'] in previous_completed]==previous_results,'Previously completed results changed')
    check(all(detections.get(image_id)==previous_detections[image_id] for image_id in previous_completed),'Previously completed detections changed')
    check(config['models']['flash37high']['provider_only']==['google-ai-studio'],'Incorrect continuation route')
    check(config['phase_route']['automatic_fallback'] is False and config['phase_route']['partial_old_responses_reused'] is False,'Continuation fallback/reuse policy changed')
    same_models=copy.deepcopy(standard_config['models']);same_models['flash37high']['max_output_tokens']=32768
    check(config['models']==same_models,'Recovery changes more than the authorised output cap')
    old_ledgers = []
    prior_spend = 0
    unresolved_old = {}
    for source in config['previous_ledgers']:
        path = root/source['file']
        check(digest(path.read_bytes()) == source['sha256'], 'Old ledger hash mismatch: ' + source['file'])
        rows = read_ledger(path)
        spend = sum(r['estimated_cost_usd'] for r in rows)
        prior_spend += spend
        check(abs(spend-source['accounted_cost_usd']) < 1e-10, 'Old ledger cost mismatch: ' + source['file'])
        old_ledgers.append((source['file'], rows))
        pending = read(path.with_name('inflight.json'), {})
        if pending:
            unresolved_old[source['file']] = list(pending)
    check(not unresolved_old, 'Old requests remain unresolved')
    check(abs(prior_spend*config['budget']['usd_inr'] + config['budget']['stage_max_inr'] - config['stage_ceiling_inr']) < 1e-8, 'Original stage allowance changed')
    check(abs(config['budget']['prior_accounted_inr'] - prior_spend*config['budget']['usd_inr'] - config['prior_stage_accounted_inr']) < 1e-8, 'Prior overall spend omitted')
    full_calls = read_ledger(out/'calls.jsonl')
    full_spend = sum(r['estimated_cost_usd'] for r in full_calls)
    standard_calls = read_ledger(standard/'calls.jsonl')
    standard_spend = sum(r['estimated_cost_usd'] for r in standard_calls)
    prior_corrected_spend = full_spend+standard_spend
    new_calls = read_ledger(continuation/'calls.jsonl')
    all_calls = [r for _,rows in old_ledgers for r in rows] + new_calls
    check(all(not isinstance(r['estimated_cost_usd'],bool) and isinstance(r['estimated_cost_usd'],(int,float)) and math.isfinite(r['estimated_cost_usd']) and r['estimated_cost_usd']>=0 for r in all_calls),'Invalid recorded cost')
    paid = physical(all_calls)
    ids = [r['job_id'] for r in paid]
    duplicate_jobs = [job for job,n in Counter(ids).items() if n > 1]
    check(not duplicate_jobs, 'Repeated physical paid job ID')
    new_paid = physical(new_calls)
    check(all(logical(r).startswith('v2long:') for r in new_calls),'Continuation reused a prior logical namespace')
    corrected_paid = physical(full_calls+standard_calls+new_calls)
    new_by_logical = {logical(r): r for r in corrected_paid if r['status'] == 'ok'}
    offline_recoveries={logical(r):r for r in new_calls if r.get('cost_basis')=='offline_validation_recovery'}
    recovery_events=[r for r in new_calls if r.get('cost_basis')=='offline_validation_recovery']
    check(len(recovery_events)==len(offline_recoveries),'Repeated offline recovery for one logical request')
    repair_policy_path=root/'data/pipeline_v2_alternative_repair_decision.json'
    repair_policy=read(repair_policy_path,{})
    repair_helper=root/'tools/repair_v2_alternatives.py'
    repair_originals={}
    repair_receipts={}
    independently_normalised_jobs=set()
    independently_gated_usage_jobs=set()
    for job,recovery in offline_recoveries.items():
        parts=job.split(':')
        check(len(parts)==3 and parts[0]=='v2long' and parts[1] in ('identify','refine') and parts[2] in config['phase_photo_ids'],'Offline repair outside the unfinished recovery phase')
        check(repair_policy.get('job_prefix')=='v2long:' and parts[1] in repair_policy.get('allowed_stages',[]) and repair_policy.get('allowed_status')=='not_sure' and repair_policy.get('allowed_error')=='Invalid top two','Offline repair policy scope differs')
        check(repair_policy.get('new_paid_requests')==0 and repair_policy.get('invent_guesses') is False and repair_policy.get('source_labels_unchanged') is True and repair_policy.get('use_existing_offline_validation_recovery') is True,'Offline repair policy changed substantive scope')
        provenance=recovery.get('recovery',{})
        line=provenance.get('original_response_line',0)
        original=new_calls[line-1] if isinstance(line,int) and 1<=line<=len(new_calls) else {}
        failures=[r for r in new_calls if logical(r)==job and r.get('status')=='validation_error' and digest(encoded(r))==provenance.get('validation_failure_sha256')]
        original_count=sum(logical(r)==job and r.get('status')=='ok' and r.get('cost_basis')!='offline_validation_recovery' for r in new_calls)
        check(original_count==1,'Offline recovery does not have exactly one original successful response')
        check(bool(original) and original.get('cost_basis')!='offline_validation_recovery' and original.get('status')=='ok','Recovery original response locator is invalid')
        check(bool(original) and digest(encoded(original))==provenance.get('original_record_sha256'),'Recovery original response hash differs')
        check(len(failures)==1 and failures[0].get('error')=='Invalid top two','Recovery does not bind the specific validation failure')
        check(recovery.get('status')=='ok' and recovery.get('estimated_cost_usd')==0,'Offline recovery is not zero cost')
        check(provenance.get('reason')=='Invalid top two','Offline recovery reason changed')
        if failures:
            check(new_calls.index(original)<new_calls.index(failures[0]) and new_calls.index(failures[0])+1==new_calls.index(recovery),'Offline recovery event order differs')
            check(failures[0].get('estimated_cost_usd')==0 and failures[0].get('cost_basis')=='validation_only_no_new_request','Validation failure incurred an extra charge')
        if original:
            for key,value in original.items():
                if key not in ('result','estimated_cost_usd','cost_basis'):
                    check(recovery.get(key)==value,'Recovery changed original request/response metadata: '+key)
            check(set(recovery)==set(original)|{'recovered_at_utc','recovery'},'Offline recovery added unexpected record fields')
            repair_originals[job]=original
        receipt_path=continuation/'validation_repairs'/(job.replace(':','_')+'.json')
        receipt=read(receipt_path,{})
        check(bool(receipt),'Offline recovery has no immutable repair receipt')
        if receipt:
            check(receipt.get('job_id')==job and receipt.get('original_response_line')==line and receipt.get('original_record_sha256')==provenance.get('original_record_sha256') and receipt.get('validation_failure_sha256')==provenance.get('validation_failure_sha256'),'Repair receipt lineage differs')
            check(receipt.get('helper_source_sha256')==digest(repair_helper.read_bytes()) and receipt.get('policy_file')=='data/pipeline_v2_alternative_repair_decision.json' and receipt.get('policy_sha256')==digest(repair_policy_path.read_bytes()),'Repair source or policy hash differs')
            check(receipt.get('paid_requests')==0 and receipt.get('additional_cost_usd')==0,'Repair receipt claims a paid request')
            check(receipt.get('normalised_result_sha256')==digest(encoded(recovery['result'])) and receipt.get('recovery_record_sha256')==digest(encoded(recovery)),'Repair receipt result or recovery hash differs')
            if original:
                check(receipt.get('request_sha256')==original.get('request_sha256') and receipt.get('config_sha256')==original.get('config_sha256') and receipt.get('original_provider_response_sha256')==digest(encoded(original['provider_response'])),'Repair receipt changed provider evidence')
            check(all((root/name).exists() and digest((root/name).read_bytes())==expected for name,expected in receipt.get('context_sha256',{}).items()),'Repair candidate or observation context changed')
            repair_receipts[job]=receipt
    usage_events=[r for r in new_calls if r.get('cost_basis')=='offline_usage_bound_recovery']
    usage_recoveries={logical(r):r for r in usage_events}
    check(len(usage_events)==len(usage_recoveries),'Repeated input-bound recovery for one logical request')
    usage_recovery_originals={}
    usage_repair_receipt={}
    for job,recovery_event in usage_recoveries.items():
        def audit_usage_recovery():
            nonlocal usage_repair_receipt
            assert job=='v2long:refine:P058', 'Unexpected input-bound recovery'
            receipt=read(continuation/'usage_bound_repair_P058.json',{})
            assert receipt and receipt['job_id']==job
            provenance=recovery_event['recovery']
            line=receipt['original_record_line']
            assert isinstance(line,int) and not isinstance(line,bool) and 1<=line<=len(new_calls)
            original=new_calls[line-1]
            assert sum(logical(r)==job and r.get('cost_basis') not in ('offline_usage_bound_recovery','offline_validation_recovery') for r in new_calls)==1
            assert new_calls.index(original)+1==new_calls.index(recovery_event), 'Input-bound recovery is not adjacent to its original error'
            raw=verify_usage_bound_original(original,config['models']['flash37high'])
            assert digest(encoded(original))==receipt['original_record_sha256']==provenance['original_record_sha256']
            assert digest(encoded(original['provider_response']))==receipt['provider_response_sha256']==provenance['provider_response_sha256']
            assert digest(encoded(raw))==receipt['result_sha256']
            assert encoded(recovery_event['result'])==encoded(raw), 'Input-bound recovery changed a substantive result'
            assert recovery_event['status']=='ok' and recovery_event['estimated_cost_usd']==0 and 'error' not in recovery_event
            for key,value in original.items():
                if key not in ('error','status','estimated_cost_usd','cost_basis'):
                    assert encoded(recovery_event[key])==encoded(value), 'Input-bound recovery changed original metadata: '+key
            assert set(recovery_event)==(set(original)-{'error'})|{'recovery','recovered_at_utc'}
            assert digest(encoded(recovery_event))==receipt['recovery_record_sha256']
            assert receipt['helper_source_sha256']==digest((root/'tools/repair_v2_usage_bound.py').read_bytes())==provenance['helper_source_sha256']
            for key in ('request_sha256','config_sha256'):
                assert receipt[key]==original[key]==provenance[key]
            assert receipt['config_sha256']==digest(encoded(config))
            assert receipt['original_error']==original['error']==provenance['original_error']
            policy=('Accept only the complete saved P058 refinement after its exact input-token-bound error. '
                    'Require unchanged provider JSON, full frozen domain validation and verified published-price '
                    'usage within the original monetary reservation and authorised budgets. Make no paid request.')
            assert receipt['policy']==provenance['reason']==policy
            assert receipt['paid_requests']==0 and receipt['additional_cost_usd']==0
            assert abs(receipt['original_actual_cost_usd']-.05000775)<1e-12 and abs(receipt['original_reserved_cost_usd']-.14388)<1e-12
            assert abs(receipt['published_input_cost_usd']-.02846775)<1e-12 and abs(receipt['published_output_cost_usd']-.02154)<1e-12
            expected_context={'out/pipeline_v2_full/photos/P058/observations.json','out/pipeline_v2_full/photos/P058/refinement_inputs.json'}
            assert set(receipt['context_sha256'])==expected_context and receipt['context_sha256']==provenance['context_sha256']
            assert all(digest((root/name).read_bytes())==expected for name,expected in receipt['context_sha256'].items())
            usage_repair_receipt=receipt
            return original
        verified=attempt('P058 offline input-bound recovery',audit_usage_recovery)
        if verified is not None:
            usage_recovery_originals[job]=verified
    config_hash = digest(encoded(config))
    adapter_receipt=read(continuation/'replay_adapter_receipt.json',{})
    adapter_source=root/'tools/resume_v2_recovery.py'
    check(bool(adapter_receipt),'Replay adapter receipt is missing')
    if adapter_receipt:
        check(adapter_receipt.get('adapter_source_sha256')==digest(adapter_source.read_bytes()),'Replay adapter source hash differs')
        check(adapter_receipt.get('config_sha256')==config_hash,'Replay adapter configuration hash differs')
        check(adapter_receipt.get('model_settings_unchanged') is True and adapter_receipt.get('paid_replays') is False,'Replay adapter changed the recorded execution policy')
        check(adapter_receipt.get('policy')=='Replay original provider JSON key order only after structural equality; retain offline-normalised results as saved.','Replay adapter policy differs')
    check(all(r['config_sha256'] == config_hash for r in new_calls), 'New call config hash mismatch')
    pending = read(continuation/'inflight.json', {})
    settled_ids = {r['job_id'] for r in new_calls}
    unresolved = {job:r for job,r in pending.items() if job not in settled_ids}
    new_spend = sum(r['estimated_cost_usd'] for r in new_calls)
    reserved = sum(r['reserved_cost_usd'] for r in unresolved.values())
    accounted = new_spend + reserved
    check(accounted*config['budget']['usd_inr'] <= config['budget']['stage_max_inr']+1e-8, 'New spending exceeded remaining allowance')
    settled_cost_checks = 0
    for row in corrected_paid:
        if row.get('usage_metadata', {}).get('cost') is not None:
            check(abs(row['usage_metadata']['cost']-row['estimated_cost_usd']) < 1e-12, 'Provider cost mismatch: ' + row['job_id'])
            settled_cost_checks += 1
        check(row['estimated_cost_usd'] <= row['reserved_cost_usd']+1e-12, 'Paid request exceeded reservation: ' + row['job_id'])
        if row['status'] == 'ok':
            check(row.get('requested_model') == config['models']['flash37high']['model'], 'Unexpected requested model')
            check(row.get('model_version') == config['models']['flash37high']['model'], 'Unexpected returned model')
            check(row.get('usage_metadata', {}).get('prompt_tokens', 0) <= config['models']['flash37high']['input_token_bound'], 'Input bound exceeded')
    ordered = sorted(corrected_paid, key=lambda r:r['request_started_unix'])
    gaps = [b['request_started_unix']-a['request_finished_unix'] for a,b in zip(ordered, ordered[1:])]
    check(all(gap >= config['rate_limit_policy']['request_interval_seconds']-.002 for gap in gaps), 'Request pacing shorter than policy')
    check(all(r['request_finished_unix'] >= r['request_started_unix'] for r in ordered), 'Invalid request timing')
    attempts = Counter(logical(r) for r in corrected_paid)
    check(all(n <= 1+config['rate_limit_policy']['rate_limit_retries'] for n in attempts.values()), 'Retry count exceeded policy')
    retry_gaps = []
    for job in attempts:
        sequence = [r for r in ordered if logical(r) == job]
        for index,(first,second) in enumerate(zip(sequence,sequence[1:]),1):
            gap = second['request_started_unix']-first['request_finished_unix']
            minimum = max(60*2**(index-1),first.get('retry_after_seconds',0))
            retry_gaps.append({'job':job,'seconds':gap,'required_minimum':minimum})
            check(first.get('http_status') == 429 and gap >= minimum-.002,'Retry did not respect rate-limit backoff: '+job)
    for row in corrected_paid:
        if row.get('cost_basis') == 'reserved_upper_bound_usage_unavailable':
            check(abs(row['estimated_cost_usd']-row['reserved_cost_usd']) < 1e-12,'Unknown-usage cost omits full reservation: '+row['job_id'])
    check(all(r['config_sha256']==config_hash for r in unresolved.values()),'Pending request config mismatch')
    expected_failure='v2standard:identify:P051:attempt:1'
    non_429_errors=[r for r in corrected_paid if r['status']!='ok' and r.get('http_status')!=429]
    expected_non_429_failures=[expected_failure]+[r['job_id'] for r in usage_recovery_originals.values()]
    check([r['job_id'] for r in non_429_errors]==expected_non_429_failures,'Unexpected or unrecovered non-rate-limit paid failure exists')
    length_failure=next((r for r in standard_calls if r['job_id']==expected_failure),{})
    choices=length_failure.get('provider_response',{}).get('choices',[])
    check(length_failure.get('status')=='error' and length_failure.get('http_status')==200 and 'result' not in length_failure,'Expected truncated response was accepted or changed')
    check(len(choices)==1 and choices[0].get('finish_reason')=='length' and choices[0].get('native_finish_reason')=='MAX_TOKENS','Expected truncation metadata changed')
    check(abs(length_failure.get('estimated_cost_usd',0)-.06693675)<1e-12,'Expected truncation cost changed')

    initial_rows = [r for r in results if r['variant'] == 'evidence_initial']
    final_rows = [r for r in results if r['variant'] == 'evidence_final']
    initial_score = score(manifest, initial_rows, detections, catalogue)
    final_score = score(manifest, final_rows, detections, catalogue)
    check(len(completed) == len(set(completed)), 'Completed photo list contains duplicates')
    check(set(completed) <= {r['image_id'] for r in manifest}, 'Unknown completed photo')
    for variant,rows in [('initial',initial_rows),('final',final_rows)]:
        keys = [(r['image_id'],r['instance_id']) for r in rows]
        check(len(keys) == len(set(keys)), 'Duplicate ' + variant + ' result')
        for image_id in completed:
            check(aggregate(image_id,rows,detections)['complete'], 'Missing completed ' + variant + ' instances: ' + image_id)

    # Payload construction uses the actual transport method without initialising a client.
    # Scoring, confidence gating and response parsing above do not import product logic.
    sys.path.insert(0, str(root/'tools'))
    from pipeline_api import Client
    from run_pipeline_v2 import batch_prompt
    from evidence_v2 import OBSERVE_PROMPT
    class Capture:
        def __init__(self,phase_config): self.config = phase_config
        def _call(self, job, operation, model, payload, url, reservation, parse):
            return digest(url.encode()+b'\n'+encoded(payload)), payload
    captures = {'v2full':Capture(full_config),'v2standard':Capture(standard_config),'v2long':Capture(config)}
    cards = read(root/'data/reference_cards_v2.json')['products']
    plates = read(out/'reference_plates.json', {})
    request_checks, raw_checks, observation_checks = 0, 0, 0
    phase_counts=Counter()
    request_hash_checked_jobs=set()
    requests_to_audit=dict(new_by_logical)
    requests_to_audit[logical(length_failure)]=length_failure
    requests_to_audit.update(usage_recovery_originals)
    for failed in corrected_paid:
        if failed.get('http_status')==429:
            recovered=new_by_logical.get(logical(failed))
            check(bool(recovered) and recovered['request_sha256']==failed['request_sha256'],'Recovered retry changed request: '+failed['job_id'])
    def phase_path(file,prefix):
        path=root/file
        if path.is_relative_to(out):
            relative=path.relative_to(out)
            if prefix=='v2full' and (standard_snapshot/relative).exists():
                return standard_snapshot/relative
            if prefix in ('v2full','v2standard') and (recovery_full_snapshot/relative).exists():
                return recovery_full_snapshot/relative
        return path
    for job,row in requests_to_audit.items():
        def audit_row():
            nonlocal request_checks, raw_checks, observation_checks
            prefix,stage,image_id = job.split(':')
            phase_config={'v2full':full_config,'v2standard':standard_config,'v2long':config}[prefix]
            assert row['config_sha256']==digest(encoded(phase_config)), 'Phase configuration hash mismatch'
            directory = phase_path(Path('out/pipeline_v2_full/photos')/image_id,prefix)
            truncated=row['job_id']==expected_failure
            raw = None if truncated else response_json(row)
            if stage == 'observe':
                prompt, images = OBSERVE_PROMPT, [('WHOLE SCENE', directory/'scene.jpg')]
                saved = read(directory/'observations.json')
                if saved is not None:
                    derived = observation_result(raw)
                    assert derived == saved, 'Observed machines differ from raw response'
                    observation_checks += 1
            else:
                observation = read(directory/'observations.json')
                prepared = read(directory/'prepared.json')
                targets = observation['machines']
                candidates = prepared['initial_candidates']
                if stage == 'identify':
                    images = [('WHOLE SCENE',directory/'scene.jpg')] + [('TARGET '+key,phase_path(value['file'],prefix)) for key,value in prepared['crops'].items()]
                    supplied = sorted({p for values in candidates.values() for p in values})
                    images += [('CATALOGUE '+p,root/plates[p]['file']) for p in supplied]
                    prompt = batch_prompt(targets,candidates,cards)
                    saved = read(directory/'initial.json')
                elif stage == 'refine':
                    initial = read(directory/'initial.json')
                    targets = [t for t in targets if requires_refinement(initial[t['object_id']],prepared['rankings'][t['object_id']],config['confidence_threshold'])]
                    refinement = read(directory/'refinement_inputs.json')
                    expanded = refinement['expanded_candidates']
                    assert set(expanded) == {t['object_id'] for t in targets}
                    assert all(set(v) == set(catalogue) and len(v) == len(catalogue) for v in expanded.values())
                    candidates = expanded
                    images = [('WHOLE SCENE',directory/'scene.jpg')]
                    for target in targets:
                        name = target['object_id']
                        images += [('TARGET '+name+' physical machine',phase_path(prepared['crops'][name]['file'],prefix)),
                                   ('TARGET '+name+' ORIGINAL DETAIL',phase_path(refinement['crops'][name]['file'],prefix))]
                    images += [('CATALOGUE '+p,root/plates[p]['file']) for p in catalogue]
                    images += [('NON-CATALOGUE LOOKALIKE '+p,root/plates[p]['file']) for p in cards if not cards[p]['in_catalog']]
                    for p,detail in refinement['original_reference_details'].items():
                        images.append(('CATALOGUE '+p+' ORIGINAL REFERENCE DETAIL',root/detail['file']))
                    prompt = batch_prompt(targets,candidates,cards,initial=initial)
                    saved = read(directory/'refined.json')
                else:
                    raise AssertionError('Unexpected stage: '+stage)
                expected_ids = {target['object_id'] for target in targets}
                if not truncated:
                    assert len(raw['results']) == len(expected_ids) and {r['object_id'] for r in raw['results']} == expected_ids
                if job in offline_recoveries:
                    assert job in repair_originals and job in repair_receipts, 'Repair lacks provenance or receipt'
                    negatives={key for key,value in cards.items() if value['in_catalog'] is False}
                    assert set(repair_policy['known_non_catalogue_ids'])==negatives
                    normalised,removals=normalise_advisory(raw,candidates,negatives)
                    assert normalised==offline_recoveries[job]['result'], 'Independent bounded normalisation differs from recovered result'
                    receipt=repair_receipts[job]
                    assert receipt['removed_ids']=={item['object_id']:item['unverified_alternatives'] for item in normalised['results'] if item.get('unverified_alternatives')}, 'Repair removed-ID evidence differs'
                    expected_context={str((directory/'observations.json').relative_to(root)),str((directory/('prepared.json' if stage=='identify' else 'refinement_inputs.json')).relative_to(root))}
                    assert set(receipt['context_sha256'])==expected_context, 'Repair context files omitted or expanded'
                    for item in normalised['results']:
                        gate(item,candidates[item['object_id']],config['confidence_threshold'])
                    raw=normalised
                    independently_normalised_jobs.add(job)
                if job in usage_recovery_originals:
                    for item in raw['results']:
                        derived=gate(item,candidates[item['object_id']],config['confidence_threshold'])
                        region=derived.get('decisive_region')
                        target=next(t for t in targets if t['object_id']==item['object_id'])
                        assert region is None or intersects(region,target['box_2d']), 'Input-bound recovery region does not overlap its target'
                    independently_gated_usage_jobs.add(job)
                if saved is not None and not truncated:
                    for answer in raw['results']:
                        name = answer['object_id']
                        derived = gate(answer,candidates[name],config['confidence_threshold'])
                        assert derived['decision'] == saved[name]['decision'], 'Saved decision differs from raw independent gate: '+name
                        assert derived['candidate_checks'] == saved[name]['candidate_checks'], 'Saved candidate checks differ: '+name
                        raw_checks += 1
            request_hash,payload = Client.generate(captures[prefix],job,'flash37high',prompt,images)
            assert request_hash == row['request_sha256'], 'Reconstructed request hash differs'
            assert payload['provider']['only'] == phase_config['models']['flash37high']['provider_only'] and payload['provider']['allow_fallbacks'] is False
            text_parts = [part['text'] for part in payload['messages'][1]['content'] if part['type']=='text']
            for forbidden in ('"source_label"','"source_url"','"source_title"','"label_basis"','"labels"'):
                assert all(forbidden not in text for text in text_parts), 'Source metadata entered inference request'
            request_checks += 1
            phase_counts[prefix]+=1
            request_hash_checked_jobs.add(job)
        attempt(job,audit_row)

    for image_id in completed:
        directory = out/'photos'/image_id
        initial = read(directory/'initial.json', {})
        final = copy.deepcopy(initial)
        final.update(read(directory/'refined.json', {}))
        for variant,values in [('evidence_initial',initial),('evidence_final',final)]:
            rows = [r for r in results if r['image_id']==image_id and r['variant']==variant and not r.get('detection_missed')]
            for row in rows:
                check(row['decision'] == values[row['object_id']]['decision'], 'Per-photo stage/result mismatch: '+image_id+':'+variant)

    old_results = read(root/'out/pipeline/results.json')
    old_detections = read(root/'out/pipeline/detections.json')
    old_gemini = [r for r in old_results if r['model']=='flash37high' and r['variant']=='telling_details']
    common_manifest = [r for r in manifest if r['image_id'] in config['comparison_photo_ids']]
    common_old = score(common_manifest,old_gemini,old_detections,catalogue)
    common_new = score(common_manifest,final_rows,detections,catalogue)
    before = {r['image_id']:r for r in initial_score['per_photo']}
    transitions = []
    for after in final_score['per_photo']:
        first = before[after['image_id']]
        outcome = lambda r:'correct' if r['correct'] else 'unresolved' if r['status']=='not_sure' else 'wrong'
        if outcome(first) != outcome(after):
            transitions.append({'image_id':after['image_id'],'initial':outcome(first),'final':outcome(after)})
    saved_scoreboard = read(out/'scoreboard.json')
    scoreboard_current = bool(saved_scoreboard and saved_scoreboard['costs']['completed_original_photos']==len(completed)
                              and abs(saved_scoreboard['costs']['new_accounted_usd']-(prior_corrected_spend+accounted))<1e-10)
    if scoreboard_current:
        groups = {g['variant']:g for g in saved_scoreboard['all_photos']['groups']}
        for variant,independent in [('evidence_initial',initial_score),('evidence_final',final_score)]:
            if variant not in groups:
                check(not completed,'Saved scoreboard group missing: '+variant)
                continue
            for key in ('single_photo_count','correct_total','confidently_wrong_count','not_sure_count','resolved_count','accuracy'):
                check(independent['metrics'][key] == groups[variant]['metrics'][key], 'Saved scoreboard metric mismatch: '+variant+':'+key)
            check(independent['metrics']['wrong_total'] == len(groups[variant]['wrong_answers']),'Saved scoreboard wrong count mismatch')
            for value in independent['multi_photo_results']:
                saved = next((m for m in groups[variant]['multi_photo_results'] if m['image_id']==value['image_id']),{})
                for key in ('predicted_identity_set','correct_resolved_identity_set','unresolved'):
                    check(value[key] == saved.get(key),'Saved multi score mismatch: '+key)
    else:
        notes.append('Saved scoreboard is absent or stale during the active run; independent scores use current saved rows.')
    if args.require_complete:
        check(len(manifest)==58 and sum(r['evaluation_role']=='labelled_single' for r in manifest)==57,'Unexpected labelled denominator')
        check(set(completed)=={r['image_id'] for r in manifest},'Not all58photos completed')
        check(not unresolved,'Current requests remain unresolved')
        check(scoreboard_current,'Final scoreboard is absent or stale')
        validation_jobs={logical(r) for r in new_calls if r['status']=='validation_error'}
        latest_jobs={logical(r):r for r in new_calls}
        check(all(job in offline_recoveries and latest_jobs[job]['status']=='ok' for job in validation_jobs),'An unrecovered validation failure remains')
        check(set(offline_recoveries)==independently_normalised_jobs,'An offline recovery was not independently reproduced')
        check(set(usage_recoveries)==independently_gated_usage_jobs,'An input-bound recovery was not independently validated')
        check(len(requests_to_audit)==request_checks,'Not every successful logical request was reconstructed')
        receipt = read(continuation/'run_receipt.json',{})
        check(receipt.get('completed_count')==58 and receipt.get('status')=='completed','Final continuation receipt is incomplete')
        check(not receipt.get('reused_jobs'),'Partial prior responses were reused after the route change')
        check(set(completed)-set(previous_completed)=={r['image_id'] for r in results if r['image_id'] not in previous_completed},'Continuation result coverage changed')
    shared_preprocessing = sum(r['estimated_cost_usd'] for _,rows in old_ledgers[:1] for r in rows
                               if logical(r).startswith(('detect:','embed:')))
    preflight_spend = sum(source['accounted_cost_usd'] for source in config['previous_ledgers'] if source['file'].startswith('out/pipeline_v2/'))
    reporting = config['reporting_usd_inr']
    report = {
        'audit_status':'FAIL' if errors else 'PASS' if args.require_complete else 'IN_PROGRESS_CHECKS_PASS',
        'errors':errors,'notes':notes,'completed_photo_count':len(completed),'expected_photo_count':len(manifest),
        'initial':initial_score,'final':final_score,'common_old_gemini':common_old,'common_new_gemini':common_new,
        'old_gemini_saved_photo_scope':len({r['image_id'] for r in old_gemini}),
        'refinement_transitions':transitions,'refined_photo_ids':sorted({r['image_id'] for r in final_rows if r.get('refined')}),
        'integrity':{'audit_self_checks_passed':self_checks,'frozen_file_count':len(config['frozen_files']),'frozen_changes':frozen_changes,
                     'physical_paid_jobs_across_all_ledgers':len(paid),'duplicate_paid_job_ids':duplicate_jobs,
                     'corrected_request_hashes_reconstructed':request_checks,'truncated_request_hash_reconstructed':logical(length_failure) in request_hash_checked_jobs,'phase_request_checks':dict(phase_counts),'prior_snapshot_changes':snapshot_changes,'prior_completed_photo_count':len(previous_completed),'offline_recovery_count':len(offline_recoveries),'independently_normalised_jobs':sorted(independently_normalised_jobs),'offline_recovery_additional_cost_usd':sum(r['estimated_cost_usd'] for r in recovery_events),'expected_preserved_length_failure':{'job_id':expected_failure,'charged_usd':length_failure.get('estimated_cost_usd'),'accepted_as_result':False},'new_independent_raw_decision_checks':raw_checks,
                     'new_raw_observation_checks':observation_checks,'old_unresolved_requests':unresolved_old,'replay_adapter_receipt':adapter_receipt,
                     'input_bound_recovery_count':len(usage_recoveries),'independently_gated_usage_recovery_jobs':sorted(independently_gated_usage_jobs),'input_bound_recovery_additional_cost_usd':sum(r['estimated_cost_usd'] for r in usage_events),'input_bound_repair_receipt':usage_repair_receipt},
        'transport':{'corrected_paid_requests':len(corrected_paid),'new_paid_requests':len(new_paid),'new_errors':[r['job_id'] for r in new_paid if r['status']!='ok'],
                     'retry_attempt_counts':{job:n for job,n in attempts.items() if n>1},'retry_backoff_gaps':retry_gaps,'minimum_finish_to_start_gap_seconds':min(gaps) if gaps else None,
                     'actual_model_counts':dict(Counter(r.get('model_version') for r in corrected_paid if r['status']=='ok')),
                     'actual_provider_counts':dict(Counter(r.get('provider') for r in corrected_paid if r['status']=='ok')),
                     'actual_service_tier_counts':dict(Counter(r.get('provider_response',{}).get('service_tier') for r in corrected_paid if r['status']=='ok')),
                     'maximum_input_tokens':max((r.get('usage_metadata',{}).get('prompt_tokens',0) for r in corrected_paid),default=0),
                     'prior_phase_rate_limit_errors':[r['job_id'] for r in physical(full_calls) if r.get('http_status')==429],
                     'phase_maximum_input_tokens':{prefix:max((r.get('usage_metadata',{}).get('prompt_tokens',0) for r in corrected_paid if logical(r).startswith(prefix+':')),default=0) for prefix in ('v2full','v2standard','v2long')},
                     'usage_cost_records_checked':settled_cost_checks,'unresolved_jobs':list(unresolved)},
        'costs':{'prior_six_ledgers_usd':prior_spend,'prior_corrected_flex_phase_usd':full_spend,'prior_corrected_standard_phase_usd':standard_spend,'new_settled_usd':new_spend,'unresolved_reserve_usd':reserved,
                 'new_accounted_usd':accounted,'new_accounted_inr':accounted*reporting,
                 'combined_stage_guard_inr':(prior_spend+accounted)*config['budget']['usd_inr'],
                 'stage_ceiling_inr':config['stage_ceiling_inr'],
                 'remaining_stage_guard_inr':config['stage_ceiling_inr']-(prior_spend+accounted)*config['budget']['usd_inr'],
                 'combined_stage_reporting_inr':(prior_spend+accounted)*reporting,
                 'overall_guard_inr':config['budget']['prior_accounted_inr']+accounted*config['budget']['usd_inr'],
                 'corrected_run_per_completed_photo_inr':(prior_corrected_spend+accounted)*reporting/len(completed) if completed else None,
                 'corrected_run_and_failed_preflight_per_completed_photo_inr':(prior_corrected_spend+accounted+preflight_spend)*reporting/len(completed) if completed else None,
                 'reused_v1_detection_and_embedding_usd':shared_preprocessing,
                 'corrected_run_plus_shared_preprocessing_per_photo_inr':(prior_corrected_spend+accounted+shared_preprocessing)*reporting/len(completed) if completed else None},
        'scope':{'extra_photo_completion_tested':False,'expected_product_live_arm_tested':False,
                 'old_preflight_request_hashes_rebuilt':False,'vertex_phase_receipt_expected_to_remain_stopped':True,'provider_routes':{'v2full':full_config['models']['flash37high']['provider_only'],'v2standard':standard_config['models']['flash37high']['provider_only'],'v2long':config['models']['flash37high']['provider_only']},'reason':'Original preflight retains its source/config; current reconstruction covers all three corrected phases, using archived P022/P051 partial-photo inputs for their old phases.'}}
    print(json.dumps(report,indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
