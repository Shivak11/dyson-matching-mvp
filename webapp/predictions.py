"""Saved run diagnostics and deterministic public prediction exports."""
import csv
import io
import json
import math
import re
from datetime import datetime

from .transport import digest, encoded

PIPELINE_VERSION = 'fresh-photo-v1'
TERMINAL = {'completed', 'failed', 'interrupted'}
CSV_FIELDS = ('prediction_id', 'filename', 'photograph_sha256', 'mode', 'claimed_model',
              'job_status', 'object_id', 'box_2d', 'decision_status', 'model_family',
              'qualitative_confidence', 'verification', 'evidence', 'missing_evidence',
              'retake_guidance', 'elapsed_seconds', 'requested_model', 'actual_models',
              'actual_providers', 'config_sha256', 'catalogue_sha256', 'cost_inr')


def seconds_between(start, end):
    try:
        return max(0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    except (TypeError, ValueError):
        return None


def number(value):
    return value if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None


def label(value):
    if not isinstance(value, str) or len(value) > 200 or any(ord(c) < 32 for c in value):
        return None
    if value.startswith(('/', '\\')) or '..' in value or '\\' in value:
        return None
    return value


def sha256(value):
    return value if isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) else None


def collect_run_details(job, snapshot, folder, cost_inr):
    """Read this run's own ledger; never consult the current runtime config."""
    saved = job.get('run_details') or {}
    model = {}
    config = folder / 'frozen_config.json'
    config_hash = saved.get('config_sha256')
    if config.is_file():
        frozen = json.loads(config.read_text())
        model = frozen.get('models', {}).get('flash37high', {})
        config_hash = config_hash or digest(encoded(frozen))
    records_path = folder / 'calls.jsonl'
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line.strip()] if records_path.is_file() else []
    config_hashes = {row.get('config_sha256') for row in records if sha256(row.get('config_sha256'))}
    if not config_hash and len(config_hashes) == 1:
        config_hash = next(iter(config_hashes))
    requested_models = {row.get('requested_model') for row in records if label(row.get('requested_model'))}
    if not model.get('model') and len(requested_models) == 1:
        model['model'] = next(iter(requested_models))
    settled = {row.get('job_id') for row in records if row.get('status') != 'validation_error'}
    pending_path = folder / 'inflight.json'
    pending = json.loads(pending_path.read_text()) if pending_path.is_file() else {}
    requests = []
    for row in records + [dict(row, status='unresolved') for key, row in sorted(pending.items()) if key not in settled]:
        if row.get('status') == 'validation_error':
            continue
        basis = row.get('cost_basis')
        reserved = basis not in ('provider_reported_cost', 'reported_tokens_and_configured_rates', 'published_per_image_estimate', 'offline_validation_recovery') or row.get('status') == 'unresolved'
        requests.append({'operation': row['operation'] if row.get('operation') in ('generate', 'embed') else None,
                         'status': row['status'] if row.get('status') in ('ok', 'error', 'unresolved') else None,
                         'model': label(row.get('model_version')), 'provider': label(row.get('provider')),
                         'elapsed_seconds': number(row.get('elapsed_seconds')),
                         'cost_usd': None if reserved else number(row.get('estimated_cost_usd')),
                         'reserved_cost_usd': number(row.get('reserved_cost_usd')),
                         'cost_basis': 'reserved_upper_bound_usage_unavailable' if reserved else basis if basis in
                         ('provider_reported_cost', 'reported_tokens_and_configured_rates', 'published_per_image_estimate', 'offline_validation_recovery') else 'unknown'})
    started = job.get('started_at', saved.get('started_at'))
    completed = job.get('completed_at', saved.get('completed_at'))
    cost_basis = ('includes_unresolved_or_reserved_usage' if any(row['cost_usd'] is None for row in requests)
                  else 'recorded_request_costs' if requests else 'saved_job_cost_without_request_ledger' if cost_inr else 'no_recorded_requests')
    return {'pipeline_version': saved.get('pipeline_version', 'legacy-local-app'),
            'config_sha256': sha256(config_hash),
            'catalogue_sha256': sha256(saved.get('catalogue_sha256')) or digest(encoded(snapshot)),
            'requested_model': label(saved.get('requested_model', model.get('model'))),
            'requested_provider': label(saved.get('requested_provider', (model.get('provider_only') or [model.get('provider')])[0])),
            'reasoning_effort': label(saved.get('reasoning_effort', model.get('thinking_level'))),
            'started_at': started, 'completed_at': completed,
            'elapsed_seconds': number(job.get('elapsed_seconds')) if job.get('elapsed_seconds') is not None else seconds_between(started, completed),
            'queued_seconds': seconds_between(job.get('created_at'), started),
            'requests': requests, 'cost_inr': cost_inr, 'cost_basis': cost_basis}


def public_match(match):
    fields = ('object_id', 'box_2d', 'status', 'product_id', 'product_name', 'confidence',
              'evidence', 'missing_evidence', 'retake_guidance', 'verification')
    value = {key: match.get(key) for key in fields}
    for key in ('evidence', 'missing_evidence', 'retake_guidance'):
        value[key] = [item for item in match.get(key, []) if isinstance(item, str)]
    value['alternatives'] = [{key: candidate.get(key) for key in ('id', 'name')}
                             for candidate in match.get('alternatives', []) if isinstance(candidate, dict)]
    return value


def hosted_run_details(details):
    if not isinstance(details, dict):
        return None
    return {key: details.get(key) for key in
            ('started_at', 'completed_at', 'elapsed_seconds', 'queued_seconds', 'cost_inr')}


def hosted_job(job):
    value = {key: job.get(key) for key in
             ('id', 'filename', 'image_url', 'created_at', 'status', 'mode', 'expected_product_id',
              'expected_product_name', 'cost_inr', 'error', 'exports_available', 'export_error',
              'started_at', 'completed_at', 'elapsed_seconds', 'retry_of') if key in job}
    value['stage'] = {'queued': 'Waiting to run', 'running': 'Processing photograph',
                      'completed': 'Complete', 'failed': 'Run stopped',
                      'interrupted': 'Run interrupted'}.get(job.get('status'), 'Saved')
    value['matches'] = []
    for match in job.get('matches', []):
        result = public_match(match)
        result.update({key: match.get(key) for key in ('reference_image_url', 'source_url')})
        result['reference_images'] = [{key: image.get(key) for key in ('id', 'url', 'filename')}
                                      for image in match.get('reference_images', []) if isinstance(image, dict)]
        value['matches'].append(result)
    value['run_details'] = hosted_run_details(job.get('run_details'))
    return value


def hosted_prediction(value, kind):
    public = {key: value.get(key) for key in
              ('schema_version', 'prediction_id', 'saved_at', 'mode', 'claimed_product', 'status')}
    public['photograph'] = {'filename': value['photograph']['filename']}
    public['matches'] = [public_match(match) for match in value.get('matches', [])]
    public['run_details'] = hosted_run_details(value.get('run_details'))
    if kind == 'json':
        return encoded(public) + b'\n'
    fields = ('prediction_id', 'filename', 'mode', 'claimed_model', 'job_status', 'object_id',
              'box_2d', 'decision_status', 'model_family', 'qualitative_confidence', 'verification',
              'evidence', 'missing_evidence', 'retake_guidance', 'elapsed_seconds', 'cost_inr')
    return csv_bytes(public, fields=fields)


def envelope(job, photograph_sha256, saved_at):
    return {'schema_version': 1, 'prediction_id': job['id'], 'saved_at': saved_at,
            'photograph': {'filename': job['filename'], 'sha256': photograph_sha256},
            'mode': job['mode'], 'claimed_product': {'id': job['expected_product_id'], 'name': job['expected_product_name']}
            if job.get('expected_product_id') else None, 'status': job['status'],
            'matches': [public_match(match) for match in job['matches']], 'run_details': job.get('run_details')}


def csv_bytes(value, fields=CSV_FIELDS):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    details = value.get('run_details') or {}
    actual_models = list(dict.fromkeys(row['model'] for row in details.get('requests', []) if row.get('model')))
    actual_providers = list(dict.fromkeys(row['provider'] for row in details.get('requests', []) if row.get('provider')))
    for match in value['matches'] or [{}]:
        row = {'prediction_id': value['prediction_id'], 'filename': value['photograph']['filename'],
               'photograph_sha256': value['photograph'].get('sha256'), 'mode': value['mode'],
               'claimed_model': value['claimed_product']['name'] if value['claimed_product'] else None,
               'job_status': value['status'], 'object_id': match.get('object_id'), 'box_2d': match.get('box_2d'),
               'decision_status': match.get('status'), 'model_family': match.get('product_name'),
               'qualitative_confidence': match.get('confidence'), 'verification': match.get('verification'),
               'evidence': match.get('evidence', []), 'missing_evidence': match.get('missing_evidence', []),
               'retake_guidance': match.get('retake_guidance', []), 'elapsed_seconds': details.get('elapsed_seconds'),
               'requested_model': details.get('requested_model'), 'actual_models': actual_models,
               'actual_providers': actual_providers, 'config_sha256': details.get('config_sha256'),
               'catalogue_sha256': details.get('catalogue_sha256'), 'cost_inr': details.get('cost_inr')}
        row = {key: row[key] for key in fields}
        for key, item in row.items():
            text = json.dumps(item, ensure_ascii=False, separators=(',', ':'), allow_nan=False) if isinstance(item, (list, dict)) else '' if item is None else str(item)
            # Spreadsheet programs may ignore leading whitespace before a formula.
            row[key] = "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text
        writer.writerow(row)
    return output.getvalue().encode('utf-8')
