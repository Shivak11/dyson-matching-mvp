"""Build comparable scope and cost tables from saved evidence; no API calls."""
import json
from collections import defaultdict
from pathlib import Path
import statistics
from evaluate_pipeline import evaluate

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/pipeline'
AUDIT_ONLY={'offline_validation_recovery','validation_only_no_new_request'}


def cost_tables(config, calls, results, image_ids):
    shared=defaultdict(float); checks=defaultdict(float); latency=defaultdict(list)
    reference=0.; models={k:v['model'] for k,v in config['models'].items()}
    actual=[r for r in calls if r['cost_basis'] not in AUDIT_ONLY]
    for r in actual:
        parts=r['job_id'].split(':'); usd=r['estimated_cost_usd']
        if parts[0]=='detect': shared[parts[1]]+=usd
        elif parts[0]=='embed':
            name=parts[1]
            if name.startswith(('P','U')): shared[name.split('_')[0]]+=usd
            else: reference+=usd
        elif parts[0]=='check':
            model,variant,instance=parts[1:4];image=instance.split('_')[0]
            checks[(model,variant,image)]+=usd
            latency[(model,variant)].append(r.get('elapsed_seconds',0))
    groups=defaultdict(set)
    for r in results:
        if r['image_id'] in image_ids: groups[(r['model'],r['variant'])].add(r['image_id'])
    rows=[];rate=config['reporting_usd_inr']
    for (model,variant),ids in sorted(groups.items()):
        members=model.split('+')
        model_usd=sum(checks[(m,variant,i)] for m in members for i in ids)
        shared_usd=sum(shared[i] for i in ids)
        times=[t for m in members for t in latency.get((m,variant),[])]
        rows.append({'model':model,'provider_models':[models[m] for m in members],'variant':variant,'photo_count':len(ids),
                     'checking_usd':model_usd,'shared_detection_retrieval_usd':shared_usd,
                     'pipeline_cost_inr':(model_usd+shared_usd)*rate,
                     'cost_per_original_photo_inr':(model_usd+shared_usd)*rate/len(ids),
                     'checking_cost_per_photo_inr':model_usd*rate/len(ids),
                     'median_check_request_seconds':statistics.median(times) if times else None,
                     'latency_scope':'Model request time; multiple product requests and shared-stage time are separate.'})
    spent=sum(r['estimated_cost_usd'] for r in calls)
    return {'models':rows,'one_time_reference_embeddings_inr':reference*rate,'stage_cost_inr':spent*rate,
            'guard_accounted_inr':spent*config['budget']['usd_inr'],'stage_ceiling_inr':config['budget']['stage_max_inr'],
            'api_call_count':len(actual),'api_error_count':sum(r['status']!='ok' for r in actual),
            'validation_failure_count':sum(r['status']=='validation_error' for r in calls),
            'offline_recovery_count':sum(r['cost_basis']=='offline_validation_recovery' for r in calls),
            'cost_basis_counts':dict(__import__('collections').Counter(r['cost_basis'] for r in actual)),
            'exchange_rate_usd_inr':rate,
            'interpretation':'Per-photo cost includes all detected objects and shared detection/retrieval once. Catalogue embeddings are one-time. Gemini costs use published rates; OpenRouter uses returned cost when available. Stage total includes every paid variant and preflight.'}


def make_study(config,manifest,results,detections,calls):
    full=evaluate(manifest,results,config['catalogue_order'],detections)
    subset=set(config['premium_subset_ids'])
    paired=evaluate([r for r in manifest if r['image_id'] in subset],results,config['catalogue_order'],detections)
    costs=cost_tables(config,calls,results,{r['image_id'] for r in manifest})
    paired_costs=cost_tables(config,calls,results,subset)
    return {'full_set':full,'fixed_subset':paired,'costs':costs,'fixed_subset_costs':paired_costs,
            'scope':'Development comparison on public review photos. The fixed subset is the fair cross-model comparison; full-set figures for subset models include unrun cases and must not be ranked against full runs.'}


def main():
    config=json.loads((ROOT/'data/pipeline_config.json').read_text())
    manifest=json.loads((ROOT/'data/test/test_manifest.json').read_text())
    results=json.loads((OUT/'results.json').read_text())
    detections=json.loads((OUT/'detections.json').read_text())
    calls=[json.loads(line) for line in (OUT/'calls.jsonl').read_text().splitlines()]
    study=make_study(config,manifest,results,detections,calls)
    (OUT/'study.json').write_text(json.dumps(study,indent=2)+'\n')
    print(json.dumps({'stage_cost_inr':study['costs']['stage_cost_inr'],'api_call_count':study['costs']['api_call_count'],'groups':len(study['full_set']['groups'])}))

if __name__=='__main__': main()
