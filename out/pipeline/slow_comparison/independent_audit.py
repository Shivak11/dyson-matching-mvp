"""Read-only audit of saved Dyson requests, raw answers, labels, spending and pacing."""
import argparse, ast, base64, collections, hashlib, json, math, mimetypes
from pathlib import Path

MODELS = ('flash37high', 'solhigh')
AUDIT_ONLY = {'offline_validation_recovery', 'validation_only_no_new_request'}


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def assert_close(left, right, message, tolerance=1e-8):
    assert math.isclose(left, right, rel_tol=0, abs_tol=tolerance), (message, left, right)


def prompt_literal(root):
    tree = ast.parse((root/'tools/run_pipeline.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == 'CHECK_PROMPT' for x in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('Frozen check prompt not found')


def request_hash(config, model_key, prompt, images):
    model = config['models'][model_key]
    content = [{'type':'text', 'text':prompt}]
    for label, path in images:
        mime = mimetypes.guess_type(path.name)[0]
        content.extend([{'type':'text', 'text':label}, {'type':'image_url', 'image_url':{'url':'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()}}])
    payload = {'model':model['model'], 'messages':[{'role':'system','content':'Return one valid JSON object. Follow the requested JSON fields exactly.'},{'role':'user','content':content}], 'max_tokens':model['max_output_tokens'], 'reasoning':{'effort':model['thinking_level'].lower()}, 'response_format':{'type':'json_object'}, 'provider':{'sort':'price','allow_fallbacks':False,'max_price':{'prompt':model['input_usd_per_million'],'completion':model['output_usd_per_million']},'only':model['provider_only']}, 'usage':{'include':True}}
    return hashlib.sha256(b'https://openrouter.ai/api/v1/chat/completions\n'+encoded(payload)).hexdigest()


def raw_answer(record):
    response = record['provider_response']
    choice, = response['choices']
    assert choice['finish_reason'] == 'stop'
    answer = json.loads(choice['message']['content'])
    assert isinstance(answer, dict)
    return answer


def gate(answer, candidates, threshold):
    # Independently check the returned shape, then apply the frozen acceptance rules.
    decision, checks = answer['decision'], answer['candidate_checks']
    status, product, confidence = decision['status'], decision['product'], decision['confidence']
    assert status in {'match','not_sure','not_in_catalogue'}
    assert isinstance(confidence, (int,float)) and not isinstance(confidence,bool) and math.isfinite(confidence) and 0 <= confidence <= 100
    assert product in candidates if status == 'match' else product is None
    assert len(checks) == len(candidates) and sorted(c['product'] for c in checks) == sorted(candidates)
    outcomes = {c['product']:('insufficient_evidence' if c['outcome'] == 'not_sure' else c['outcome']) for c in checks}
    assert all(v in {'confirmed','contradicted','insufficient_evidence'} for v in outcomes.values())
    assert all(isinstance(c['evidence'],str) and c['evidence'].strip() for c in checks)
    if status == 'match':
        assert outcomes[product] == 'confirmed'
    if status != 'not_sure':
        assert any(isinstance(v,str) and v.strip() for v in decision['evidence'])
    confirmed = [c['product'] for c in checks if outcomes[c['product']] == 'confirmed']
    if status == 'match' and (confirmed != [product] or confidence < threshold) or status == 'not_in_catalogue' and any(v != 'contradicted' for v in outcomes.values()):
        status, product = 'not_sure', None
    return {'status':status,'product':product,'confidence':confidence}


def unsure():
    return {'status':'not_sure','product':None,'confidence':0}


def unanimous(first, second):
    if first['status'] == second['status'] != 'not_sure' and first['product'] == second['product']:
        return {'status':first['status'],'product':first['product'],'confidence':min(first['confidence'],second['confidence'])}
    return unsure()


def aggregate(decisions, complete):
    if not complete or not decisions:
        return unsure()
    if all(d['status'] == 'not_in_catalogue' for d in decisions) or all(d['status'] == 'match' for d in decisions) and len({d['product'] for d in decisions}) == 1:
        return {'status':decisions[0]['status'],'product':decisions[0]['product'],'confidence':min(d['confidence'] for d in decisions)}
    return unsure()


def audit(root):
    out = root/'out/pipeline'; new = out/'slow_comparison'
    config = read(root/'data/pipeline_slow_comparison_config.json')
    assert config['requested_models'] == list(MODELS)
    assert config['models']['flash37high'] == read(root/'data/pipeline_high_reasoning_config.json')['models']['flash37high']
    assert config['models']['solhigh']['thinking_level'] == 'high'
    assert config['rate_limit_policy'] == {'rate_limit_retries':3,'request_interval_seconds':15,'max_retry_delay_seconds':300}
    for filename, field in [('data/test/test_manifest.json','test_manifest_sha256'),('data/reference_pack.json','reference_pack_sha256'),('data/telling_details.json','telling_details_sha256')]:
        assert digest(root/filename) == config[field], filename
    manifest = read(root/'data/test/test_manifest.json'); rows = {r['image_id']:r for r in manifest}; ids = config['premium_subset_ids']
    assert len(ids) == len(set(ids)) == 16
    singles = [i for i in ids if rows[i]['evaluation_role'] == 'labelled_single']
    assert len(singles) == 15
    assert all(rows[i].get('source_url') and rows[i].get('source_title') and rows[i].get('label_basis') for i in ids)
    assert all(digest(root/rows[i]['file']) == rows[i]['sha256'] for i in ids)
    old = []
    ledger_counts = {}
    for source in config['previous_ledgers']:
        path = root/source['file']; assert digest(path) == source['sha256'], 'Historical ledger changed'
        assert not read(path.with_name('inflight.json')), 'Historical requests unresolved'
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert_close(sum(r['estimated_cost_usd'] for r in records), source['accounted_cost_usd'], 'Historical spend')
        old.extend(records); ledger_counts[source['file']] = len(records)
    old_spend = sum(r['estimated_cost_usd'] for r in old)
    assert_close(old_spend, 2.004048736, 'Old stage cost')
    assert_close(config['budget']['stage_max_inr'] + old_spend*config['budget']['usd_inr'], 400, 'Combined cap')
    new_rows = [json.loads(line) for line in (new/'calls.jsonl').read_text().splitlines()] if (new/'calls.jsonl').exists() else []
    ledger_counts['out/pipeline/slow_comparison/calls.jsonl'] = len(new_rows)
    assert not read(new/'inflight.json'), 'New requests unresolved'
    assert read(new/'frozen_config.json') == config
    all_calls = old + new_rows
    actual = [r for r in all_calls if r['cost_basis'] not in AUDIT_ONLY]
    physical_jobs = [r['job_id'] for r in actual]
    assert len(physical_jobs) == len(set(physical_jobs)), 'Duplicate physical paid job'
    latest = {r.get('logical_job_id',r['job_id']):r for r in all_calls}
    paid_new = [r for r in new_rows if r['cost_basis'] not in AUDIT_ONLY]
    attempts = collections.Counter(r.get('logical_job_id',r['job_id']) for r in paid_new)
    assert all(n <= 4 for n in attempts.values()), 'More than initial+3retry calls'
    for r in paid_new:
        logical = r.get('logical_job_id',r['job_id'])
        assert r['job_id'].startswith(logical+':attempt:')
        assert logical.split(':')[1] in MODELS
        assert r['config_sha256'] == hashlib.sha256(encoded(config)).hexdigest()
    gaps = []
    for previous, current in zip(paid_new, paid_new[1:]):
        gap = current['request_started_unix'] - previous['request_finished_unix']; gaps.append(gap)
        assert gap >= 14.99, ('Pause below15seconds',previous['job_id'],current['job_id'],gap)
        if previous.get('http_status') == 429 and previous.get('logical_job_id') == current.get('logical_job_id'):
            assert gap + .01 >= previous['retry_delay_seconds'], '429backoff not observed'
    inputs = read(out/'inputs.json'); detections = read(out/'detections.json'); rankings = read(out/'shortlists.json'); cards = read(root/'data/telling_details.json')
    assert sum(len(detections[i]) for i in ids) == 18
    for photo in inputs['photos'].values():
        assert digest(root/photo['file']) == photo['sha256']
    for refs in inputs['references'].values():
        for ref in refs:
            assert digest(root/ref['file']) == ref['sha256']
    expected_hashes, candidates_by_instance = {}, {}
    base = prompt_literal(root)
    for image_id in ids:
        for obj in detections[image_id]:
            instance = obj['instance_id']; assert digest(root/obj['crop_file']) == obj['crop_sha256']
            ranking = rankings[instance]; candidates = sorted(r['product'] for r in ranking); candidates_by_instance[instance] = candidates
            images = [('Whole scene for context',root/inputs['photos'][image_id]['file']),('TARGET CROP',root/obj['crop_file'])]
            for product in candidates:
                ranked = next(r for r in ranking if r['product'] == product); refs = inputs['references'][product]
                chosen = [ranked['references'][0]['reference']]; chosen.extend(r['id'] for r in refs if r['id'] not in chosen)
                for n,reference_id in enumerate(chosen[:config['reference_images_per_candidate']]):
                    reference = next(r for r in refs if r['id'] == reference_id)
                    images.append(('Catalogue '+product+' reference '+str(n+1),root/reference['file']))
            prompt = base+'\nSupplied candidate IDs: '+json.dumps(candidates)+'\nReference comparison notes; inspect the images to verify whether these details are visible. These cues are not individually unique:\n'+json.dumps({p:cards[p]['text'] for p in candidates})
            for model in MODELS:
                expected_hashes['check:'+model+':telling_details:'+instance] = request_hash(config,model,prompt,images)
    old_latest = {r.get('logical_job_id',r['job_id']):r for r in old}
    reused = []
    for job, sha in expected_hashes.items():
        if job in old_latest:
            assert old_latest[job]['request_sha256'] == sha
            if old_latest[job]['status'] == 'ok':
                reused.append(job)
                assert not any(r.get('logical_job_id',r['job_id']) == job for r in paid_new), 'Successful historical call repeated'
    assert len(reused) == 13 and all(':flash37high:' in j for j in reused)
    raw_gated = {}
    for job, sha in expected_hashes.items():
        if job not in latest or latest[job]['status'] != 'ok':
            continue
        record = latest[job]; assert record['request_sha256'] == sha
        model, variant, instance = job.split(':')[1:4]
        decision = gate(raw_answer(record),candidates_by_instance[instance],config['confidence_threshold'])
        raw_gated[(model,instance)] = decision
    saved = {(r['model'],r['instance_id']):r for r in read(out/'results.json') if r['variant'] == 'telling_details' and r['model'] in MODELS}
    for key, decision in raw_gated.items():
        assert key in saved, ('Raw success missing saved cropresult',key)
        assert all(saved[key]['decision'][field] == decision[field] for field in decision), ('Saved decision differs from raw/gate',key)
    assert all(key in raw_gated for key in saved), 'Saved result lacks raw request proof'
    catalogue = set(config['catalogue_order']); photo_rows = {}
    for model in (*MODELS,'flash37high+solhigh'):
        values = []
        for image_id in singles:
            instances = [o['instance_id'] for o in detections[image_id]]
            if '+' in model:
                complete = bool(instances) and all((m,j) in raw_gated for m in MODELS for j in instances)
                decisions = [unanimous(raw_gated.get((MODELS[0],j),unsure()),raw_gated.get((MODELS[1],j),unsure())) for j in instances]
            else:
                complete = bool(instances) and all((model,j) in raw_gated for j in instances)
                decisions = [raw_gated.get((model,j),unsure()) for j in instances]
            decision = aggregate(decisions,complete); label, = rows[image_id]['labels']
            correct = decision['status'] == 'match' and decision['product'] == label or decision['status'] == 'not_in_catalogue' and label not in catalogue
            values.append({'image_id':image_id,'source_label':label,'result_complete':complete,'correct':bool(correct),**decision})
        photo_rows[model] = values
    common = [i for i in singles if all(next(p for p in photo_rows[m] if p['image_id'] == i)['result_complete'] for m in MODELS)]
    summaries = {}
    def summary(values):
        complete = [p for p in values if p['result_complete']]
        wrong = [p for p in complete if p['status'] != 'not_sure' and not p['correct']]
        return {'single_photo_denominator':len(values),'completed_single_photos':len(complete),'correct':sum(p['correct'] for p in complete),'wrong':len(wrong),'confidently_wrong':sum(p['confidence'] >= 90 for p in wrong),'unsure_among_completed':sum(p['status'] == 'not_sure' for p in complete),'unrun_or_incomplete':len(values)-len(complete),'wrong_answers':wrong,'per_photo':values}
    for model, values in photo_rows.items():
        summaries[model] = {'fixed15':summary(values),'common_complete':summary([p for p in values if p['image_id'] in common])}
    multi = {}
    for model in (*MODELS,'flash37high+solhigh'):
        objects = detections['P059']; instance_ids = [o['instance_id'] for o in objects]
        if '+' in model:
            complete = all((m,j) in raw_gated for m in MODELS for j in instance_ids)
            decisions = [unanimous(raw_gated.get((MODELS[0],j),unsure()),raw_gated.get((MODELS[1],j),unsure())) for j in instance_ids]
        else:
            complete = all((model,j) in raw_gated for j in instance_ids)
            decisions = [raw_gated.get((model,j),unsure()) for j in instance_ids]
        predicted = sorted({d['product'] for d in decisions if d['status'] == 'match'}); expected = sorted(set(rows['P059']['labels']) & catalogue)
        multi[model] = {'result_complete':complete,'expected_identity_set':expected,'predicted_identity_set':predicted,'correct_resolved_identity_set':complete and predicted == expected and all(d['status'] == 'match' for d in decisions),'crop_decisions':decisions,'scope':'Identity set only; no source-backed per-box model labels.'}
    shared, checks = collections.defaultdict(float), collections.defaultdict(float); reference = 0; recomputed = 0
    cost_basis_counts = collections.Counter()
    for record in all_calls:
        basis = record['cost_basis']; cost_basis_counts[basis] += 1
        amount = record['estimated_cost_usd']; assert isinstance(amount,(int,float)) and math.isfinite(amount) and amount >= 0
        if basis in AUDIT_ONLY:
            expected_cost = 0
        elif basis in {'reserved_upper_bound_usage_unavailable','published_per_image_estimate'}:
            expected_cost = record['reserved_cost_usd']
        elif basis == 'provider_reported_cost':
            expected_cost = record['provider_response']['usage']['cost']
        elif basis == 'reported_tokens_and_configured_rates':
            usage = record['provider_response'].get('usageMetadata',record['provider_response'].get('usage',{}))
            parts = record['job_id'].split(':'); model_key = 'detector' if parts[0] == 'detect' else parts[1]; model = config['models'][model_key]
            prompt = usage.get('promptTokenCount',usage.get('prompt_tokens',0)); cache = usage.get('cachedContentTokenCount',0)
            output = usage.get('candidatesTokenCount',usage.get('completion_tokens',0))+usage.get('thoughtsTokenCount',0)
            expected_cost = ((prompt-cache)*model['input_usd_per_million']+cache*model.get('cached_input_usd_per_million',model['input_usd_per_million'])+output*model['output_usd_per_million'])/1e6
        else:
            raise AssertionError(('Unexpected cost basis',basis))
        assert_close(amount,expected_cost,'Raw cost reconciliation',1e-12); recomputed += expected_cost
        if basis in AUDIT_ONLY:
            continue
        parts = record['job_id'].split(':')
        if parts[0] == 'detect': shared[parts[1]] += amount
        elif parts[0] == 'embed':
            if parts[1].startswith(('P','U')): shared[parts[1].split('_')[0]] += amount
            else: reference += amount
        elif parts[0] == 'check': checks[(parts[1],parts[3].split('_')[0])] += amount
    new_spend = sum(r['estimated_cost_usd'] for r in new_rows); rate = config['reporting_usd_inr']
    assert new_spend*config['budget']['usd_inr'] <= config['budget']['stage_max_inr'] + 1e-8
    assert recomputed*config['budget']['usd_inr'] <= 400 + 1e-8
    costs = {}
    for model in (*MODELS,'flash37high+solhigh'):
        members = model.split('+'); complete_ids = [p['image_id'] for p in photo_rows[model] if p['result_complete']]
        if multi[model]['result_complete']: complete_ids.append('P059')
        check_usd = sum(checks[(m,i)] for m in members for i in complete_ids); shared_usd = sum(shared[i] for i in complete_ids)
        costs[model] = {'completed_original_photos':len(complete_ids),'checking_usd':check_usd,'shared_detection_retrieval_usd':shared_usd,'cost_per_completed_original_photo_inr':(check_usd+shared_usd)*rate/len(complete_ids) if complete_ids else None,'includes_failed_attempts_for_completed_photos':True}
    p006 = next(p for p in photo_rows['flash37high'] if p['image_id'] == 'P006')
    assert p006['source_label'] == 'dyson_v8_absolute' and p006['status'] == 'not_in_catalogue' and p006['confidence'] == 95 and not p006['correct']
    return {'audit':'PASS','independent_scorer':True,'production_scorer_imported':False,'scope':'Saved development comparison; no network calls. Only complete common photos enter the paired denominator.','fixed_ids':ids,'common_complete_single_ids':common,'ledger_record_counts':ledger_counts,'unique_paid_request_count':len(physical_jobs),'new_paid_request_count':len(paid_new),'new_attempt_counts':dict(attempts),'exact_historical_gemini_reuse_count':len(reused),'reconstructed_request_hash_count':len(expected_hashes),'verified_successful_raw_answers':len(raw_gated),'minimum_new_finish_to_start_pause_seconds':min(gaps) if gaps else None,'model_summaries':summaries,'P059_two_family_identity_sets':multi,'costs':{'old_usd':old_spend,'new_usd':new_spend,'combined_usd':recomputed,'combined_reporting_inr':recomputed*rate,'combined_guard_inr':recomputed*config['budget']['usd_inr'],'unknown_usage_reserve_inr':sum(r['estimated_cost_usd'] for r in all_calls if r['cost_basis'] == 'reserved_upper_bound_usage_unavailable')*rate,'one_time_catalogue_embedding_inr':reference*rate,'cost_basis_counts':dict(cost_basis_counts),'per_completed_photo':costs},'Gemini_P006_confidently_wrong':p006}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); args = parser.parse_args()
    assert args.output.resolve().is_relative_to(Path('/tmp').resolve()), 'Audit receipt must stay under /tmp'
    result = audit(args.root.resolve()); args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'audit':result['audit'],'receipt':str(args.output),'common_complete_single_photos':len(result['common_complete_single_ids']),'combined_guard_inr':result['costs']['combined_guard_inr']}))


if __name__ == '__main__':
    main()
