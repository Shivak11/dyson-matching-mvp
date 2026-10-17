"""Metered OpenRouter transport for fresh-photo inference."""
import base64
import copy
import hashlib
import shlex
from contextlib import nullcontext
from email.utils import parsedate_to_datetime
import json
import math
import mimetypes
import os
import random
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

from . import cloud_runtime

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def usage_cost(usage, pricing):
    if 'cost' in usage:
        cost = usage['cost']
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            raise ValueError('Invalid reported cost')
        return cost
    if 'prompt_tokens' in usage:
        usage = {'promptTokenCount': usage['prompt_tokens'], 'candidatesTokenCount': usage['completion_tokens']}
    prompt = usage['promptTokenCount']
    cached = usage.get('cachedContentTokenCount', 0)
    output = usage.get('candidatesTokenCount', 0) + usage.get('thoughtsTokenCount', 0)
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in (prompt, cached, output)) or cached > prompt:
        raise ValueError('Invalid usage counters')
    return ((prompt - cached) * pricing['input_usd_per_million'] + cached * pricing['cached_input_usd_per_million'] + output * pricing['output_including_thinking_usd_per_million']) / 1_000_000


def api_key_for(name):
    if os.environ.get(name):
        return os.environ[name]
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            field, separator, value = line.partition('=')
            if separator and field.strip().removeprefix('export ') == name:
                parts = shlex.split(value, comments=True)
                if len(parts) == 1:
                    return parts[0]
    raise RuntimeError(name + ' is unavailable')


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
        raise ValueError('Unsupported provider')
    result = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
    if not isinstance(result, dict):
        raise ValueError('Generation must return a JSON object')
    return result


class Client:
    """The runner holds the process lock; this class serialises ledger updates."""
    def __init__(self, config, root, out, *, reuse_records=(), rate_limit_retries=0, request_interval_seconds=0, max_retry_delay_seconds=300):
        if isinstance(rate_limit_retries, bool) or not isinstance(rate_limit_retries, int) or rate_limit_retries < 0:
            raise ValueError('rate_limit_retries must be a non-negative integer')
        self.rate_limit_retries = rate_limit_retries
        self.request_interval_seconds = positive(request_interval_seconds, 'request_interval_seconds', True)
        self.max_retry_delay_seconds = positive(max_retry_delay_seconds, 'max_retry_delay_seconds', True)
        reuse_records = copy.deepcopy(list(reuse_records))
        self.retry_enabled = bool(reuse_records) or rate_limit_retries > 0
        self.reused_jobs = set()
        self.reuse_records = {row.get('logical_job_id', row['job_id']): row for row in reuse_records}
        self.reuse_job_ids = {row['job_id'] for row in reuse_records}
        self.request_lock = threading.Lock()
        self.last_request_finished_at = None
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
        self.logical_records = {}
        self.attempts = {}
        for row in records:
            if row['config_sha256'] != self.config_sha256:
                raise ValueError('Config changed after metered calls')
            self._index_record(row)
        self.spent_usd = sum(positive(row['estimated_cost_usd'], 'recorded cost', True) for row in records if row['status'] != 'validation_error')
        self.pending_path = self.out / 'inflight.json'
        self.pending = json.loads(self.pending_path.read_text()) if self.pending_path.exists() else {}
        if any(row['config_sha256'] != self.config_sha256 for row in self.pending.values()):
            raise ValueError('Config changed with requests in flight')
        # A saved terminal response settles its reservation even if the process stopped before removal.
        self.pending = {job: row for job, row in self.pending.items() if job not in self.records}
        self.unresolved_jobs = set(self.pending)
        self._refresh_failure()
        finished = [row['request_finished_unix'] for row in records + reuse_records if isinstance(row.get('request_finished_unix'), (int, float)) and math.isfinite(row['request_finished_unix'])]
        if finished:
            self.last_request_finished_at = time.monotonic() - max(0, time.time() - max(finished))
        if self.pending_path.exists():
            self._atomic_json(self.pending_path, self.pending)

    def _atomic_json(self, path, value):
        with cloud_runtime.LOCK:
            self._write_json(path, value)
            cloud_runtime.checkpoint()

    def _write_json(self, path, value):
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
        with cloud_runtime.LOCK:
            with self.calls_path.open('ab') as target:
                target.write(encoded(record) + b'\n')
                target.flush()
                os.fsync(target.fileno())
            self._index_record(record)
            cloud_runtime.checkpoint()

    def _index_record(self, record):
        logical_id = record.get('logical_job_id', record['job_id'])
        self.records[record['job_id']] = record
        self.logical_records[logical_id] = record
        if 'reserved_cost_usd' in record:
            self.attempts.setdefault(logical_id, set()).add(record['job_id'])

    @staticmethod
    def _is_rate_limit(record):
        # Older frozen ledgers predate the explicit HTTP status field.
        return record['status'] == 'error' and (record.get('http_status') == 429 or ('http_status' not in record and record.get('error', '').startswith('HTTP Error 429:')))

    def _recoverable(self, logical_id, record):
        return self.retry_enabled and self._is_rate_limit(record) and not record.get('retry_exhausted') and len(self.attempts.get(logical_id, ())) < 1 + self.rate_limit_retries

    def _refresh_failure(self):
        latest = {**self.reuse_records, **self.logical_records}
        self.failure = bool(self.unresolved_jobs) or any(row['status'] != 'ok' and not self._recoverable(job, row) for job, row in latest.items())

    def _wait(self, seconds):
        deadline = time.monotonic() + seconds
        while True:
            if (self.out / 'STOP').exists():
                raise RuntimeError('Pipeline STOP file is present')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 30))

    def _retry_delay(self, record, count):
        delay = 60 * (2 ** min(max(count - 1, 0), 10)) + random.uniform(0, 1)
        return max(delay, record.get('retry_after_seconds', 0))

    @staticmethod
    def _retry_after(header):
        if not isinstance(header, str) or len(header) > 256:
            return None
        try:
            delay = float(header)
        except ValueError:
            try:
                when = parsedate_to_datetime(header)
                if when.tzinfo is None:
                    return None
                delay = max(0, when.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                return None
        return delay if math.isfinite(delay) and delay >= 0 else None

    @property
    def accounted_cost_usd(self):
        with self.lock:
            return self.spent_usd + sum(row['reserved_cost_usd'] for row in self.pending.values())

    def generate(self, job_id, model_key, prompt, images, schema=None):
        model = self.config['models'][model_key]
        provider = model['provider']
        if 'provider_only' in model:
            only = model['provider_only']
            if provider != 'openrouter' or not isinstance(only, list) or not only or any(not isinstance(name, str) or not name.strip() for name in only):
                raise ValueError('provider_only must be a non-empty string list for OpenRouter')
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
            if 'provider_only' in model:
                payload['provider']['only'] = model['provider_only']
            url = 'https://openrouter.ai/api/v1/chat/completions'
        else:
            raise ValueError('Unsupported provider')
        reservation = (positive(model['input_token_bound'], 'input_token_bound') * positive(model['input_usd_per_million'], 'input price', True) + positive(model['max_output_tokens'], 'max_output_tokens') * positive(model['output_usd_per_million'], 'output price', True)) / 1_000_000
        return self._call(job_id, 'generate', model, payload, url, reservation, lambda response: parse_generation(response, provider))


    def _call(self, job_id, operation, model, payload, url, reservation, parse):
        timeout = positive(model.get('request_timeout_seconds', 180), 'request_timeout_seconds')
        if not isinstance(job_id, str) or not job_id:
            raise ValueError('A non-empty job ID is required')
        body = encoded(payload)
        request_sha = digest(url.encode() + b'\n' + body)
        sequential = self.retry_enabled or self.request_interval_seconds > 0
        with self.request_lock if sequential else nullcontext():
            with self.lock:
                old = self.logical_records.get(job_id, self.reuse_records.get(job_id))
                if old:
                    if old['request_sha256'] != request_sha:
                        raise ValueError('Request changed for cached job: ' + job_id)
                    if old['status'] == 'ok':
                        if job_id not in self.logical_records:
                            self.reused_jobs.add(job_id)
                        return copy.deepcopy(old['result'])
                    if not self._recoverable(job_id, old):
                        raise RuntimeError('Previously failed job cannot be retried: ' + job_id)
                if self.failure or any(row.get('logical_job_id', pending_id) == job_id for pending_id, row in self.pending.items()):
                    raise RuntimeError('Pipeline stopped after failed or unresolved request; inspect calls.jsonl and inflight.json')
            if old:
                delay = old.get('retry_delay_seconds', self._retry_delay(old, len(self.attempts.get(job_id, ()))))
                if delay > self.max_retry_delay_seconds:
                    raise RuntimeError('Rate-limit retry delay exceeds configured maximum: ' + job_id)
                self._wait(delay)
            while True:
                if self.last_request_finished_at is not None:
                    self._wait(max(0, self.request_interval_seconds - (time.monotonic() - self.last_request_finished_at)))
                attempt_id = job_id
                if self.retry_enabled:
                    number = 1
                    while job_id + ':attempt:' + str(number) in self.records or job_id + ':attempt:' + str(number) in self.reuse_job_ids:
                        number += 1
                    attempt_id = job_id + ':attempt:' + str(number)
                try:
                    return self._paid_call(attempt_id, job_id, operation, model, body, request_sha, url, reservation, parse, timeout)
                except RuntimeError:
                    with self.lock:
                        failed = self.logical_records.get(job_id)
                        if not failed or failed['job_id'] != attempt_id or not self._recoverable(job_id, failed):
                            raise
                    self._wait(failed['retry_delay_seconds'])

    def _paid_call(self, job_id, logical_id, operation, model, body, request_sha, url, reservation, parse, timeout):
        with self.lock:
            if self.failure or job_id in self.pending:
                raise RuntimeError('Pipeline stopped after failed or unresolved request; inspect calls.jsonl and inflight.json')
            if (self.out / 'STOP').exists():
                raise RuntimeError('Pipeline STOP file is present')
            if self.accounted_cost_usd + reservation > self.cap_usd + 1e-12:
                raise RuntimeError('Pipeline budget stop before request: ' + job_id)
            key = api_key_for('OPENROUTER_API_KEY')
            record = {'job_id': job_id, 'operation': operation, 'config_sha256': self.config_sha256, 'request_sha256': request_sha, 'requested_model': model['model'], 'provider_route': model['provider'], 'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'reserved_cost_usd': reservation}
            if self.retry_enabled:
                record['logical_job_id'] = logical_id
            if self.retry_enabled or self.request_interval_seconds:
                record['request_started_unix'] = time.time()
            self.pending[job_id] = record
            self._atomic_json(self.pending_path, self.pending)
        start = time.monotonic()
        response = None
        usage = {}
        try:
            headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}
            request = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                record['http_status'] = getattr(reply, 'status', 200)
                response = json.load(reply)
            record['provider_response'] = response
            usage = response.get('usage', {})
            record['usage_metadata'] = usage
            record['model_version'] = response.get('model')
            record['provider'] = response.get('provider')
            record['response_id'] = response.get('id')
            record.update(status='ok', result=parse(response))
            if operation == 'generate' and usage.get('prompt_tokens', usage.get('promptTokenCount', 0)) > model['input_token_bound']:
                raise ValueError('Reported input tokens exceed reserved bound')
        except Exception as error:
            message = str(error)
            if isinstance(error, urllib.error.HTTPError):
                record['http_status'] = error.code
                retry_after = self._retry_after(error.headers.get('Retry-After')) if error.headers is not None else None
                if retry_after is not None:
                    record['retry_after_seconds'] = retry_after
                try:
                    message += ' ' + error.read(3000).decode(errors='replace')
                finally:
                    error.close()
            record.update(status='error', error=message.replace(key, '[REDACTED]'))
        self.last_request_finished_at = time.monotonic()
        if self.retry_enabled or self.request_interval_seconds:
            record['request_finished_unix'] = time.time()
        record['elapsed_seconds'] = self.last_request_finished_at - start
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
            if self.retry_enabled and self._is_rate_limit(record):
                count = len(self.attempts.get(logical_id, ())) + 1
                delay = self._retry_delay(record, count)
                record['retry_delay_seconds'] = delay
                record['retry_exhausted'] = count >= 1 + self.rate_limit_retries or delay > self.max_retry_delay_seconds
            self._append(record)
            self.spent_usd += record['estimated_cost_usd']
            del self.pending[job_id]
            self._atomic_json(self.pending_path, self.pending)
            self._refresh_failure()
        if record['status'] != 'ok':
            raise RuntimeError(job_id + ': ' + record['error'])
        return copy.deepcopy(record['result'])

    def record_validation_failure(self, job_id, error):
        """Keep returned usage when a caller rejects a domain-invalid JSON object."""
        with self.lock:
            old = self.logical_records.get(job_id, self.reuse_records.get(job_id))
            if old is None:
                raise ValueError('No saved response for validation: ' + job_id)
            record = {key: old[key] for key in ('job_id', 'config_sha256', 'request_sha256', 'requested_model')}
            if job_id not in self.logical_records:
                record.update(job_id=job_id, logical_job_id=job_id, config_sha256=self.config_sha256, reused_record_sha256=digest(encoded(old)))
            if 'logical_job_id' in old:
                record['logical_job_id'] = old['logical_job_id']
            record.update(status='validation_error', error=str(error), estimated_cost_usd=0, cost_basis='validation_only_no_new_request')
            self._append(record)
            self.failure = True
