"""Metered, resumable transport for the frozen pipeline experiment."""
import base64
import copy
import json
import math
import mimetypes
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

try:
    from .run_baseline import api_key_for, digest, usage_cost
except ImportError:
    from run_baseline import api_key_for, digest, usage_cost


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def positive(value, name, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(name + ' must be a finite positive number')
    return value


def image_part(path):
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in ('image/jpeg', 'image/png', 'image/webp'):
        raise ValueError('Unsupported image type: ' + path.suffix)
    data = path.read_bytes()
    if not data:
        raise ValueError('Empty image')
    return {'inlineData': {'mimeType': mime, 'data': base64.b64encode(data).decode()}}


def parse_generation(response, provider):
    if provider == 'openrouter':
        candidate, = response['choices']
        if candidate.get('finish_reason') != 'stop':
            raise ValueError('Incomplete provider result: ' + str(candidate.get('finish_reason')))
        text = candidate['message']['content']
    else:
        candidate, = response['candidates']
        if candidate.get('finishReason') != 'STOP':
            raise ValueError('Incomplete provider result: ' + str(candidate.get('finishReason')))
        text = ''.join(part.get('text', '') for part in candidate['content']['parts'] if not part.get('thought'))
    result = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
    if not isinstance(result, dict):
        raise ValueError('Generation must return a JSON object')
    return result


class Client:
    """The runner holds the process lock; this class serialises ledger updates."""
    def __init__(self, config, root, out):
        self.config = copy.deepcopy(config)
        self.root, self.out = Path(root), Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.config_sha256 = digest(encoded(config))
        self.lock = threading.RLock()
        budget = config['budget']
        rate = positive(budget['usd_inr'], 'usd_inr')
        self.cap_usd = min(positive(budget['stage_max_inr'], 'stage_max_inr'), positive(budget['total_max_inr'], 'total_max_inr') - positive(budget['prior_accounted_inr'], 'prior_accounted_inr', True)) / rate
        if self.cap_usd <= 0:
            raise ValueError('No authorised budget remains')
        frozen = self.out / 'frozen_config.json'
        if frozen.exists():
            if digest(encoded(json.loads(frozen.read_text()))) != self.config_sha256:
                raise ValueError('Config changed after pipeline preparation')
        else:
            self._atomic_json(frozen, config)
        self.calls_path = self.out / 'calls.jsonl'
        records = [json.loads(line) for line in self.calls_path.read_text().splitlines()] if self.calls_path.exists() else []
        self.records = {}
        for row in records:
            if row['config_sha256'] != self.config_sha256:
                raise ValueError('Config changed after metered calls')
            self.records[row['job_id']] = row
        self.spent_usd = sum(positive(row['estimated_cost_usd'], 'recorded cost', True) for row in records if row['status'] != 'validation_error')
        self.pending_path = self.out / 'inflight.json'
        self.pending = json.loads(self.pending_path.read_text()) if self.pending_path.exists() else {}
        if any(row['config_sha256'] != self.config_sha256 for row in self.pending.values()):
            raise ValueError('Config changed with requests in flight')
        # A saved terminal response settles its reservation even if the process stopped before removal.
        self.pending = {job: row for job, row in self.pending.items() if job not in self.records}
        self.failure = bool(self.pending) or any(row['status'] != 'ok' for row in self.records.values())
        if self.pending_path.exists():
            self._atomic_json(self.pending_path, self.pending)

    def _atomic_json(self, path, value):
        temporary = path.with_suffix(path.suffix + '.tmp')
        with temporary.open('wb') as target:
            target.write(encoded(value) + b'\n')
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _append(self, record):
        with self.calls_path.open('ab') as target:
            target.write(encoded(record) + b'\n')
            target.flush()
            os.fsync(target.fileno())
        self.records[record['job_id']] = record

    @property
    def accounted_cost_usd(self):
        with self.lock:
            return self.spent_usd + sum(row['reserved_cost_usd'] for row in self.pending.values())

    def generate(self, job_id, model_key, prompt, images, schema=None):
        model = self.config['models'][model_key]
        provider = model['provider']
        parts = [{'text': prompt}]
        for label, path in images:
            parts.extend([{'text': label}, image_part(path)])
        if provider == 'openrouter':
            content = []
            for part in parts:
                if 'text' in part:
                    content.append({'type': 'text', 'text': part['text']})
                else:
                    item = part['inlineData']
                    content.append({'type': 'image_url', 'image_url': {'url': 'data:' + item['mimeType'] + ';base64,' + item['data']}})
            reasoning = {'effort': model['thinking_level'].lower()} if model.get('thinking_level') else {'enabled': False}
            payload = {'model': model['model'], 'messages': [{'role': 'system', 'content': 'Return one valid JSON object. Follow the requested JSON fields exactly.'}, {'role': 'user', 'content': content}], 'max_tokens': model['max_output_tokens'], 'reasoning': reasoning, 'response_format': {'type': 'json_object'}, 'provider': {'sort': 'price', 'allow_fallbacks': False, 'max_price': {'prompt': model['input_usd_per_million'], 'completion': model['output_usd_per_million']}}, 'usage': {'include': True}}
            url = 'https://openrouter.ai/api/v1/chat/completions'
        elif provider == 'gemini':
            text_format = {'mimeType': 'APPLICATION_JSON'}
            if schema is not None:
                text_format['schema'] = schema
            generation = {'maxOutputTokens': model['max_output_tokens'], 'responseFormat': {'text': text_format}}
            if model.get('thinking_level'):
                generation['thinkingConfig'] = {'thinkingLevel': model['thinking_level'].upper()}
            payload = {'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': generation}
            url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model['model'] + ':generateContent'
        else:
            raise ValueError('Unsupported provider')
        reservation = (positive(model['input_token_bound'], 'input_token_bound') * positive(model['input_usd_per_million'], 'input price', True) + positive(model['max_output_tokens'], 'max_output_tokens') * positive(model['output_usd_per_million'], 'output price', True)) / 1_000_000
        return self._call(job_id, 'generate', model, payload, url, reservation, lambda response: parse_generation(response, provider))

    def embed(self, job_id, path):
        model = self.config['embedding']
        if model['dimensions'] != 3072:
            raise ValueError('This experiment requires 3072 embedding dimensions')
        payload = {'model': 'models/' + model['model'], 'content': {'parts': [image_part(path)]}, 'outputDimensionality': model['dimensions']}
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model['model'] + ':embedContent'
        def parse(response):
            vector = response['embedding']['values']
            if not isinstance(vector, list) or len(vector) != model['dimensions'] or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in vector) or not any(vector):
                raise ValueError('Invalid embedding vector')
            return vector
        return self._call(job_id, 'embed', dict(model, provider='gemini'), payload, url, positive(model['usd_per_image'], 'embedding price'), parse)

    def _call(self, job_id, operation, model, payload, url, reservation, parse):
        if not isinstance(job_id, str) or not job_id:
            raise ValueError('A non-empty job ID is required')
        body = encoded(payload)
        request_sha = digest(url.encode() + b'\n' + body)
        with self.lock:
            old = self.records.get(job_id)
            if old:
                if old['request_sha256'] != request_sha:
                    raise ValueError('Request changed for cached job: ' + job_id)
                if old['status'] != 'ok':
                    raise RuntimeError('Previously failed job cannot be retried: ' + job_id)
                return copy.deepcopy(old['result'])
            if self.failure or job_id in self.pending:
                raise RuntimeError('Pipeline stopped after failed or unresolved request; inspect calls.jsonl and inflight.json')
            if (self.out / 'STOP').exists():
                raise RuntimeError('Pipeline STOP file is present')
            if self.accounted_cost_usd + reservation > self.cap_usd + 1e-12:
                raise RuntimeError('Pipeline budget stop before request: ' + job_id)
            key = api_key_for('OPENROUTER_API_KEY' if model['provider'] == 'openrouter' else 'GEMINI_API_KEY')
            record = {'job_id': job_id, 'operation': operation, 'config_sha256': self.config_sha256, 'request_sha256': request_sha, 'requested_model': model['model'], 'provider_route': model['provider'], 'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'reserved_cost_usd': reservation}
            self.pending[job_id] = record
            self._atomic_json(self.pending_path, self.pending)
        start = time.monotonic()
        response = None
        usage = {}
        try:
            headers = {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + key} if model['provider'] == 'openrouter' else {'x-goog-api-key': key})}
            request = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=180) as reply:
                response = json.load(reply)
            record['provider_response'] = response
            usage = response.get('usage', {}) if model['provider'] == 'openrouter' else response.get('usageMetadata', {})
            record['usage_metadata'] = usage
            record['model_version'] = response.get('model') if model['provider'] == 'openrouter' else response.get('modelVersion')
            record['provider'] = response.get('provider')
            record['response_id'] = response.get('id') if model['provider'] == 'openrouter' else response.get('responseId')
            record.update(status='ok', result=parse(response))
            if operation == 'generate' and usage.get('prompt_tokens', usage.get('promptTokenCount', 0)) > model['input_token_bound']:
                raise ValueError('Reported input tokens exceed reserved bound')
        except Exception as error:
            message = str(error)
            if isinstance(error, urllib.error.HTTPError):
                message += ' ' + error.read(3000).decode(errors='replace')
            record.update(status='error', error=message.replace(key, '[REDACTED]'))
        record['elapsed_seconds'] = time.monotonic() - start
        if operation == 'embed':
            record['estimated_cost_usd'] = reservation
            record['cost_basis'] = 'published_per_image_estimate' if response is not None else 'reserved_upper_bound_usage_unavailable'
        else:
            try:
                if 'cost' not in usage and not (('prompt_tokens' in usage and 'completion_tokens' in usage) or ('promptTokenCount' in usage and 'candidatesTokenCount' in usage)):
                    raise ValueError('Incomplete usage')
                pricing = {'input_usd_per_million': model['input_usd_per_million'], 'cached_input_usd_per_million': model.get('cached_input_usd_per_million', model['input_usd_per_million']), 'output_including_thinking_usd_per_million': model['output_usd_per_million']}
                record['estimated_cost_usd'] = usage_cost(usage, pricing)
                record['cost_basis'] = 'provider_reported_cost' if 'cost' in usage else 'reported_tokens_and_configured_rates'
            except (KeyError, ValueError, TypeError):
                record['estimated_cost_usd'] = reservation
                record['cost_basis'] = 'reserved_upper_bound_usage_unavailable'
        if record['estimated_cost_usd'] > reservation + 1e-12:
            record.update(status='error', error='Provider cost exceeded request reservation')
        with self.lock:
            self._append(record)
            self.spent_usd += record['estimated_cost_usd']
            del self.pending[job_id]
            self._atomic_json(self.pending_path, self.pending)
            if record['status'] != 'ok':
                self.failure = True
        if record['status'] != 'ok':
            raise RuntimeError(job_id + ': ' + record['error'])
        return copy.deepcopy(record['result'])

    def record_validation_failure(self, job_id, error):
        """Keep returned usage when a caller rejects a domain-invalid JSON object."""
        with self.lock:
            old = self.records[job_id]
            record = {key: old[key] for key in ('job_id', 'config_sha256', 'request_sha256', 'requested_model')}
            record.update(status='validation_error', error=str(error), estimated_cost_usd=0, cost_basis='validation_only_no_new_request')
            self._append(record)
            self.failure = True

    def recover_validation(self, job_id, validator):
        """Revalidate a saved successful response offline; never repeat a paid request."""
        with self.lock:
            previous = self.records[job_id]
            if previous['status'] != 'validation_error':
                raise ValueError('Only domain-validation failures can be recovered offline')
            history = [json.loads(line) for line in self.calls_path.read_text().splitlines()]
            originals = [(index, row) for index, row in enumerate(history, 1) if row['job_id'] == job_id and row['status'] == 'ok' and row['cost_basis'] != 'offline_validation_recovery']
            if len(originals) != 1:
                raise ValueError('Expected exactly one original successful response')
            line, original = originals[0]
            if original['request_sha256'] != previous['request_sha256'] or original['config_sha256'] != self.config_sha256:
                raise ValueError('Validation recovery input changed')
            result = validator(copy.deepcopy(original['result']))
            if not isinstance(result, dict):
                raise ValueError('Offline validator must return the validated JSON object')
            record = copy.deepcopy(original)
            record.update(result=result, estimated_cost_usd=0, cost_basis='offline_validation_recovery', recovered_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), recovery={'original_response_line': line, 'original_record_sha256': digest(encoded(original)), 'validation_failure_sha256': digest(encoded(previous)), 'reason': previous['error']})
            self._append(record)
            self.failure = bool(self.pending) or any(row['status'] != 'ok' for row in self.records.values())
            return copy.deepcopy(result)
