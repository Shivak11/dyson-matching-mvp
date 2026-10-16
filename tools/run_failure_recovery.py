"""Run the separately frozen Gemini failure experiment; --run permits metered calls."""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import time
from PIL import Image, ImageOps

from run_pipeline import ROOT, read, save, sha, pixel_box
from pipeline_api import Client, positive
from run_slow_comparison import verify_history
from evaluate_pipeline import evaluate
from failure_protocol import inventory_prompt, validate_inventory, build_comparison_prompt, validate_comparison

OUT = Path('out/failure_recovery')
CONFIG = Path('data/failure_recovery_config.json')
SCOPE = Path('data/failure_recovery_scope.json')
VIEWS = Path('data/reference_views_v3.json')
AUTH = Path('data/pipeline_budget_amendment_additional_400.json')
CONTROLS = ['P006', 'P014', 'P019']


def ledger(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def render_references(root):
    references = read(root/VIEWS, {})['references']
    if len(references) != 9 or set(references) != {f'R{i:02d}' for i in range(1, 10)}:
        raise ValueError('Exactly nine neutral reference families are required')
    if len({item['product'] for item in references.values()}) != 9 or sum(item['in_catalog'] is True for item in references.values()) != 6:
        raise ValueError('Reference mapping must contain six catalogue and three distinct outside families')
    if any(not isinstance(item['in_catalog'],bool) for item in references.values()):
        raise ValueError('Reference catalogue flags must be boolean')
    cards = read(root/'data/reference_cards_v2.json',{})['products']
    projected, images = {}, []
    for alias, reference in references.items():
        card = cards.get(reference['product'])
        if not card or card['in_catalog'] is not reference['in_catalog']:
            raise ValueError('Reference mapping differs from its manufacturer source record')
        source_hashes = {item['file']:item['sha256'] for item in card['images']}
        panels = reference['panels']
        if not 1 <= len(panels) <= 3:
            raise ValueError('Reference needs one to three component panels')
        projected[alias] = {'product':reference['product'], 'in_catalog':reference['in_catalog'], 'panels':[]}
        for panel in panels:
            name = panel['panel_id']
            if name in {item['panel_id'] for item in images} or not name.startswith(alias+'-P'):
                raise ValueError('Invalid or repeated reference panel ID')
            source = root/panel['source_file']
            if source_hashes.get(panel['source_file']) != panel['source_sha256']:
                raise ValueError('Panel source does not belong to its manufacturer family record')
            if not (panel['source_file'].startswith('data/catalog/') or panel['source_file'].startswith('data/reference_images_v2/')):
                raise ValueError('References must come from existing manufacturer images')
            if sha(source) != panel['source_sha256']:
                raise ValueError('Manufacturer image changed')
            destination = root/OUT/'references'/(name+'.jpg')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as raw:
                image = ImageOps.exif_transpose(raw).convert('RGBA')
                bounds = pixel_box(panel['box_2d'], image.width, image.height, 0)
                crop = image.crop(bounds)
                crop.thumbnail((768,768))
                canvas = Image.new('RGBA',crop.size,'white'); canvas.alpha_composite(crop)
                canvas.convert('RGB').save(destination,quality=95)
            projected[alias]['panels'].append(name)
            images.append({'panel_id':name,'file':str(destination.relative_to(root)),'sha256':sha(destination),
                           'source_file':panel['source_file'],'source_sha256':panel['source_sha256'],
                           'source_pixel_box':bounds,'width':crop.width,'height':crop.height})
    save(root/OUT/'reference_panels.json',{'references':projected,'images':images})
    return projected, images


def prepare(root=ROOT):
    root = Path(root)
    if (root/CONFIG).exists():
        raise ValueError('The experiment configuration already exists; do not regenerate frozen inputs')
    baseline = read(root/'out/pipeline_v2_recovery/independent_audit.json',{})
    if baseline.get('audit_status') != 'PASS' or baseline.get('completed_photo_count') != 58:
        raise ValueError('A verified completed 58-photo baseline is required')
    failures = [row['image_id'] for row in baseline['final']['per_photo'] if not row['correct']]
    if len(failures) != 20 or set(failures)&set(CONTROLS):
        raise ValueError('Unexpected failure or control population')
    scope = {'failure_ids':failures,'control_ids':CONTROLS,'photo_ids':failures+CONTROLS,
             'preflight_id':'P022','basis':'All 15 unsure and five confidently wrong photos from the saved benchmark; three previously correct sanity controls.'}
    save(root/SCOPE,scope)
    _, images = render_references(root)
    previous = read(root/'data/pipeline_v2_recovery_config.json',{})
    if previous != read(root/'out/pipeline_v2_recovery/frozen_config.json',{}):
        raise ValueError('Historical configuration differs from its frozen copy')
    for name, expected in previous['frozen_files'].items():
        if sha(root/name) != expected:
            raise ValueError('Historical frozen input changed: '+name)
    prior_receipt = read(root/'out/pipeline_v2_recovery/verification_receipt.json',{})
    for group in ('ledger_sha256','result_sha256'):
        for name, expected in prior_receipt[group].items():
            if sha(root/name) != expected:
                raise ValueError('Completed benchmark evidence changed: '+name)
    if sha(root/'out/pipeline_v2_recovery/independent_audit.json') != prior_receipt['audit_result_sha256']:
        raise ValueError('Completed benchmark audit changed')
    history = copy.deepcopy(previous['previous_ledgers'])
    last = Path('out/pipeline_v2_recovery/calls.jsonl')
    history.append({'file':str(last),'sha256':sha(root/last),
                    'accounted_cost_usd':sum(positive(row['estimated_cost_usd'],'cost',True) for row in ledger(root/last))})
    if len({item['file'] for item in history}) != 7:
        raise ValueError('Expected seven distinct historical ledgers')
    authorisation = read(root/AUTH,{})
    if authorisation.get('new_stage_ceiling_inr') != 1000 or authorisation.get('overall_ceiling_inr') != 2000:
        raise ValueError('Missing additional spending authorisation')
    prior = sum(item['accounted_cost_usd'] for item in history)*100
    if abs(prior-authorisation['prior_stage_guard_inr']) > 1e-8:
        raise ValueError('Prior spending changed after the new authorisation')
    models = {}
    for name, bound, cap in [('inventory',20000,16384),('comparison',50000,32768)]:
        model = copy.deepcopy(previous['models']['flash37high'])
        model.update(input_token_bound=bound,max_output_tokens=cap)
        models[name] = model
    frozen = dict(previous['frozen_files'])
    paths = [AUTH,VIEWS,SCOPE,Path('data/pipeline_v2_recovery_config.json'),Path('out/pipeline_v2_recovery/independent_audit.json'),
             Path('out/pipeline_v2_recovery/verification_receipt.json'),OUT/'reference_panels.json']
    for directory in ['out/pipeline_v2','out/pipeline_v2_full','out/pipeline_v2_continuation','out/pipeline_v2_recovery']:
        paths += [path.relative_to(root) for path in (root/directory).rglob('*') if path.is_file()]
    paths += [path.relative_to(root) for directory in ['tools','tests'] for path in (root/directory).glob('*.py')]
    paths += [Path(item['file']) for item in images]
    for path in paths:
        current_hash = sha(root/path)
        if str(path) in frozen and frozen[str(path)] != current_hash:
            raise ValueError('Inherited frozen hash conflicts with current input: '+str(path))
        frozen[str(path)] = current_hash
    config = {'study_id':'failure-recovery-aligned-reference-v3','models':models,'confidence_threshold':90,
              'catalogue_order':previous['catalogue_order'],'scope':scope,'previous_ledgers':history,
              'stage_ceiling_inr':1000,'prior_stage_accounted_inr':previous['prior_stage_accounted_inr'],
              'budget':{'usd_inr':100,'stage_max_inr':1000-prior,'total_max_inr':2000,
                        'prior_accounted_inr':prior+previous['prior_stage_accounted_inr']},
              'reporting_usd_inr':previous['reporting_usd_inr'],'rate_limit_policy':previous['rate_limit_policy'],
              'frozen_files':frozen,'selected_failure_evaluation':True}
    save(root/CONFIG,config)
    verify_config(config,root)
    return config


def verify_config(config, root=ROOT):
    if not config.get('frozen_files'):
        raise ValueError('Frozen input manifest is empty')
    for name, expected in config['frozen_files'].items():
        if sha(Path(root)/name) != expected:
            raise ValueError('Frozen input changed: '+name)
    if len(config['previous_ledgers']) != 7 or len({item['file'] for item in config['previous_ledgers']}) != 7:
        raise ValueError('Historical ledgers must be counted exactly once')
    return verify_history(config,Path(root))


def query_crop(source, box, destination, root=ROOT, maximum=1536):
    with Image.open(source) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
        bounds = pixel_box(box,image.width,image.height,.04)
        crop = image.crop(bounds); crop.thumbnail((maximum,maximum))
        destination.parent.mkdir(parents=True,exist_ok=True); crop.save(destination,quality=95)
    return {'file':str(destination.relative_to(root)),'pixel_box':bounds,'sha256':sha(destination)}


def generate(client,job,model,prompt,images,validator):
    raw = client.generate(job,model,prompt,images)
    try:
        return validator(raw)
    except Exception as error:
        client.record_validation_failure(job,str(error))
        raise


def run_photo(client,config,photo,panels,root=ROOT):
    root = Path(root); image_id = photo['image_id']; directory = root/OUT/'photos'/image_id
    directory.mkdir(parents=True,exist_ok=True)
    scene = directory/'scene.jpg'; query_crop(root/photo['file'],[0,0,1000,1000],scene,root,2048)
    inventory = generate(client,'v3:inventory:'+image_id,'inventory',inventory_prompt(),
                         [('WHOLE SCENE',scene)],validate_inventory)
    save(directory/'inventory.json',inventory)
    targets = inventory['machines']
    if not targets or all(target.get('accessory_only') for target in targets):
        reason = 'Only shared accessories are visible; no identifying main body is available.' if targets else 'No physical cleaner was located.'
        rows = [{'image_id':image_id,'instance_id':image_id+'_'+target['object_id'],
                 'model':'flash37high_v3','variant':'aligned_reference','candidates':config['catalogue_order'],
                 'decision':{'status':'not_sure','product':None,'confidence':0,'top_two':[],
                             'evidence':[],'missing_evidence':[reason],'contradictions':[],
                             'retake':'Photograph the main body, handle and controls.'},'comparison_skipped':True}
                for target in targets]
        if not targets:
            rows = [{'image_id':image_id,'instance_id':image_id+'_none','model':'flash37high_v3',
                     'variant':'aligned_reference','candidates':[],'detection_missed':True,
                     'decision':{'status':'not_sure','product':None,'confidence':0,'top_two':[],
                                 'evidence':[],'missing_evidence':[reason],'contradictions':[],
                                 'retake':'Photograph the main body, handle and controls.'},'comparison_skipped':True}]
        return targets, rows
    images = [('WHOLE SCENE',scene)]; crops = {}
    for target in targets:
        key = target['object_id']
        body = query_crop(root/photo['file'],target['box_2d'],directory/(key+'_body.jpg'),root)
        images.append(('TARGET '+key,root/body['file'])); crops[key]=[body]
        for index, feature in enumerate(target['observations']):
            if feature['visible']:
                detail = query_crop(root/photo['file'],feature['box_2d'],directory/(key+'_detail_'+str(index)+'.jpg'),root)
                images.append(('TARGET '+key+' DETAIL '+str(index),root/detail['file']));crops[key].append(detail)
    save(directory/'query_crops.json',crops)
    images += [(item['panel_id'],root/item['file']) for item in panels['images']]
    compared = generate(client,'v3:compare:'+image_id,'comparison',build_comparison_prompt(targets,panels['references']),
                        images,lambda raw:validate_comparison(raw,targets,panels['references'],config['confidence_threshold']))
    save(directory/'comparison.json',compared)
    rows = [{'image_id':image_id,'instance_id':image_id+'_'+target['object_id'],'model':'flash37high_v3',
             'variant':'aligned_reference','candidates':config['catalogue_order'],**compared[target['object_id']]}
            for target in targets]
    return targets,rows


def raw_rows(rows, references):
    output = []
    for row in rows:
        initial = copy.deepcopy(row); initial['variant']='reference_raw'
        if 'raw' in row:
            decision = copy.deepcopy(row['raw']['decision'])
            alias = decision.pop('reference')
            if decision['status']=='same_family':
                decision['status']='match' if references[alias]['in_catalog'] else 'not_in_catalogue'
                decision['product']=references[alias]['product'] if decision['status']=='match' else None
            else:
                decision['status']='not_in_catalogue' if decision['status']=='other_brand' else 'not_sure'
                decision['product']=None
            decision['top_two']=[references[key]['product'] for key in decision['top_two']]
            initial['decision']=decision
        output.append(initial)
    return output


def report(config,root=ROOT):
    root = Path(root); out = root/OUT
    manifest = read(root/'data/test/test_manifest.json',[])
    selected = [row for row in manifest if row['image_id'] in config['scope']['photo_ids']]
    results,detections = read(out/'results.json',[]),read(out/'detections.json',{})
    summary = evaluate(selected,results,config['catalogue_order'],detections)
    calls = ledger(out/'calls.jsonl'); pending = read(out/'inflight.json',{})
    settled = {row['job_id'] for row in calls}
    new_cost = sum(row['estimated_cost_usd'] for row in calls)+sum(row['reserved_cost_usd'] for job,row in pending.items() if job not in settled)
    prior = sum(item['accounted_cost_usd'] for item in config['previous_ledgers'])
    baseline = {row['image_id']:row for row in read(root/'out/pipeline_v2_recovery/independent_audit.json',{})['final']['per_photo']}
    current = {row['image_id']:row for group in summary['groups'] if group['variant']=='aligned_reference' for row in group['per_photo']}
    transitions = []
    completed = set(read(out/'completed_photos.json',[]))
    for image_id in config['scope']['photo_ids']:
        old = baseline[image_id]; new = current.get(image_id)
        transitions.append({'image_id':image_id,'cohort':'failure' if image_id in config['scope']['failure_ids'] else 'control',
                            'old_status':old['status'],'old_correct':old['correct'],
                            'new_status':new['status'] if new and image_id in completed and new.get('result_present') else 'not_run',
                            'new_correct':bool(new and image_id in completed and new['correct']),
                            'completed':image_id in completed})
    failure_rows = [row for row in transitions if row['cohort']=='failure']
    outcomes = {'recovered_correct':0,'still_wrong':0,'new_wrong':0,'wrong_to_unsure':0,'still_unsure':0,'not_run':0}
    for row in failure_rows:
        key = ('not_run' if not row['completed'] else 'recovered_correct' if row['new_correct'] else
               ('still_unsure' if row['old_status']=='not_sure' else 'wrong_to_unsure') if row['new_status']=='not_sure' else
               'new_wrong' if row['old_status']=='not_sure' else 'still_wrong')
        outcomes[key] += 1
    output = {'scope':config['scope'],'summary':summary,'transitions':transitions,'failure_outcomes':outcomes,
              'control_regressions':[row['image_id'] for row in transitions if row['cohort']=='control' and row['completed'] and not row['new_correct']],
              'completed_count':len(read(out/'completed_photos.json',[])),
              'costs':{'new_accounted_usd':new_cost,'new_accounted_inr':new_cost*config['reporting_usd_inr'],
                       'combined_stage_guard_inr':(prior+new_cost)*config['budget']['usd_inr'],
                       'combined_stage_reporting_inr':(prior+new_cost)*config['reporting_usd_inr'],
                       'remaining_guard_inr':config['stage_ceiling_inr']-(prior+new_cost)*config['budget']['usd_inr'],
                       'stage_ceiling_inr':config['stage_ceiling_inr']},
              'full_set_accuracy_retested':False}
    save(out/'scoreboard.json',output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--run',action='store_true')
    parser.add_argument('--preflight',action='store_true')
    args = parser.parse_args()
    if args.prepare and (args.run or args.preflight):parser.error('--prepare is separate from paid execution')
    if args.preflight and not args.run:parser.error('--preflight requires --run')
    with (ROOT/'out/pipeline/run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config = prepare() if args.prepare else read(ROOT/CONFIG,{})
        verify_config(config)
        if args.prepare:print(json.dumps({'status':'prepared','budget':config['budget']}));return
        if not args.run:print(json.dumps({'status':'offline','report':report(config)}));return
        panels = read(ROOT/OUT/'reference_panels.json',{})
        photos = {row['image_id']:row for row in read(ROOT/'data/test/test_manifest.json',[])}
        selected = [config['scope']['preflight_id']] if args.preflight else config['scope']['photo_ids']
        client = Client(config,ROOT,ROOT/OUT,**config['rate_limit_policy'])
        results = read(ROOT/OUT/'results.json',[]);detections = read(ROOT/OUT/'detections.json',{})
        completed = read(ROOT/OUT/'completed_photos.json',[]);failure = None
        started = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        try:
            for image_id in selected:
                if image_id in completed:continue
                targets,rows = run_photo(client,config,photos[image_id],panels)
                detections[image_id] = [{**target,'instance_id':image_id+'_'+target['object_id']} for target in targets]
                results = [row for row in results if row['image_id']!=image_id]+raw_rows(rows,panels['references'])+rows
                save(ROOT/OUT/'detections.json',detections);save(ROOT/OUT/'results.json',results)
                completed.append(image_id);save(ROOT/OUT/'completed_photos.json',completed)
                print(json.dumps({'photo':image_id,'completed':len(completed),'decisions':[row['decision'] for row in rows]}),flush=True)
        except Exception as error:
            failure = str(error)
            save(ROOT/OUT/'blocker.json',{'error':failure,'attempted':'Fresh inventory, aligned references, one paced Gemini worker; no fallback or silent repair.'})
        finally:
            score = report(config)
            save(ROOT/OUT/'run_receipt.json',{'started_utc':started,'settled_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                 'status':'stopped' if failure else ('preflight_completed' if args.preflight else 'completed'),
                 'completed_count':len(completed),'selected_photo_ids':selected,'all_photo_ids':config['scope']['photo_ids'],
                 'error':failure,'inflight_count':len(client.pending),'workers':1,'costs':score['costs']})
            print(json.dumps({'status':'stopped' if failure else 'completed','costs':score['costs']}),flush=True)
        if failure:raise SystemExit('Stopped: '+failure)


if __name__=='__main__':main()
