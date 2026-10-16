"""Validate the single saved P058 response without another paid request."""
import argparse
import copy
import fcntl
import json
import math
from pathlib import Path
import time

import run_pipeline_v2 as v2
import run_pipeline_v2_recovery as recovery
from repair_v2_alternatives import load_context
from pipeline_api import Client, digest, encoded, parse_generation, positive

ROOT = v2.ROOT
JOB = 'v2long:refine:P058'
ERROR = 'Reported input tokens exceed reserved bound'
RECEIPT = recovery.NEW/'usage_bound_repair_P058.json'
POLICY = ('Accept only the complete saved P058 refinement after its exact input-token-bound error. '
          'Require unchanged provider JSON, full frozen domain validation and verified published-price '
          'usage within the original monetary reservation and authorised budgets. Make no paid request.')


def repair(*, apply=False, root=ROOT):
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
    matching = [(line,row) for line,row in enumerate(records,1)
                if row.get('logical_job_id',row['job_id'])==JOB]
    if len(matching)!=1 or matching[0][1] != records[-1]:
        raise ValueError('Expected one latest physical P058 refinement response')
    line, original = matching[0]
    if (original.get('job_id')!=JOB+':attempt:1' or original.get('status')!='error'
        or original.get('error')!=ERROR or original.get('http_status')!=200
        or original.get('cost_basis')!='provider_reported_cost'):
        raise ValueError('Only the exact settled P058 input-token-bound failure can be repaired')
    latest = {row.get('logical_job_id',row['job_id']):row for row in records}
    if any(name!=JOB and row['status']!='ok' for name,row in latest.items()):
        raise ValueError('Another failed job remains unresolved')
    model = config['models']['flash37high']
    if original['config_sha256']!=digest(encoded(config)) or original['requested_model']!=model['model']:
        raise ValueError('Saved response does not match the frozen configuration')
    response = original['provider_response']
    choice, = response['choices']
    if choice.get('finish_reason')!='stop' or choice.get('native_finish_reason')!='STOP':
        raise ValueError('Provider response is incomplete')
    raw = parse_generation(response,'openrouter')
    if encoded(raw)!=encoded(original.get('result')):
        raise ValueError('Saved result differs from the provider JSON')
    usage = response['usage']
    if usage != original.get('usage_metadata'):
        raise ValueError('Saved usage differs from the provider response')
    prompt, completion = usage['prompt_tokens'], usage['completion_tokens']
    cached = usage.get('prompt_tokens_details',{}).get('cached_tokens',0)
    if any(isinstance(value,bool) or not isinstance(value,int) or value<0 for value in (prompt,completion,cached)):
        raise ValueError('Invalid provider token counts')
    if prompt<=model['input_token_bound'] or completion>model['max_output_tokens'] or cached>prompt:
        raise ValueError('Response does not fit the exact input-bound recovery policy')
    input_cost = ((prompt-cached)*model['input_usd_per_million']+cached*model.get('cached_input_usd_per_million',model['input_usd_per_million']))/1_000_000
    output_cost = completion*model['output_usd_per_million']/1_000_000
    actual = positive(usage['cost'],'provider cost',True)
    reservation = (model['input_token_bound']*model['input_usd_per_million']+model['max_output_tokens']*model['output_usd_per_million'])/1_000_000
    if (not math.isclose(input_cost+output_cost,actual,rel_tol=0,abs_tol=1e-10)
        or not math.isclose(original['estimated_cost_usd'],actual,rel_tol=0,abs_tol=1e-10)
        or not math.isclose(original['reserved_cost_usd'],reservation,rel_tol=0,abs_tol=1e-10)
        or actual>reservation+1e-12):
        raise ValueError('Cost arithmetic or original reservation does not agree')
    details = usage.get('cost_details',{})
    for key,expected in [('upstream_inference_prompt_cost',input_cost),('upstream_inference_completions_cost',output_cost),('upstream_inference_cost',actual)]:
        if key in details and not math.isclose(details[key],expected,rel_tol=0,abs_tol=1e-10):
            raise ValueError('Provider cost details do not agree')
    current = recovery.spent(records)*config['budget']['usd_inr']
    prior = sum(source['accounted_cost_usd'] for source in config['previous_ledgers'])*config['budget']['usd_inr']
    if prior+current>config['stage_ceiling_inr']+1e-8 or config['budget']['prior_accounted_inr']+current>config['budget']['total_max_inr']+1e-8:
        raise ValueError('Accounted costs exceed authorised spending')
    targets, candidate_map, _, context = load_context(JOB,config,root)
    v2.validate_batch(raw,targets,candidate_map,config['confidence_threshold'])
    receipt = {'job_id':JOB,'original_record_line':line,'original_record_sha256':digest(encoded(original)),
               'provider_response_sha256':digest(encoded(response)),'result_sha256':digest(encoded(raw)),
               'request_sha256':original['request_sha256'],'config_sha256':original['config_sha256'],
               'helper_source_sha256':v2.sha(Path(__file__)),'context_sha256':context,'policy':POLICY,
               'original_error':ERROR,'original_actual_cost_usd':actual,'original_reserved_cost_usd':reservation,
               'published_input_cost_usd':input_cost,'published_output_cost_usd':output_cost,
               'paid_requests':0,'additional_cost_usd':0}
    if apply:
        receipt_path = root/RECEIPT
        if receipt_path.exists(): raise ValueError('Immutable P058 repair receipt already exists')
        before = path.read_bytes()
        client = Client(config,root,root/recovery.NEW,**config['rate_limit_policy'])
        record = copy.deepcopy(original)
        record.pop('error')
        record.update(status='ok',estimated_cost_usd=0,cost_basis='offline_usage_bound_recovery',
                      recovered_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                      recovery={'original_record_line':line,'original_record_sha256':receipt['original_record_sha256'],
                                'provider_response_sha256':receipt['provider_response_sha256'],
                                'request_sha256':receipt['request_sha256'],'config_sha256':receipt['config_sha256'],
                                'reason':POLICY,'original_error':ERROR,'helper_source_sha256':receipt['helper_source_sha256'],
                                'context_sha256':context})
        with client.lock:
            client._append(record)
            client._refresh_failure()
        if not path.read_bytes().startswith(before) or client.failure:
            raise RuntimeError('Offline repair did not preserve settled ledger state')
        receipt['recovery_record_sha256'] = digest(encoded(record))
        with receipt_path.open('x') as target:
            json.dump(receipt,target,indent=2);target.write('\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair',action='store_true')
    args = parser.parse_args()
    with (ROOT/'out/pipeline/run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(repair(apply=args.repair,root=ROOT)),flush=True)


if __name__=='__main__':main()
