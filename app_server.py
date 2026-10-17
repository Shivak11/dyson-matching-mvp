#!/usr/bin/env python3
"""Loopback-only local app, SQLite catalogue and one paid OpenRouter worker."""
import argparse
import fcntl
import hmac
import hashlib
import json
import os
from contextlib import contextmanager
import queue
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from webapp.store import Store, ID, ConflictError, now
from webapp import cloud_runtime
from webapp.predictions import collect_run_details, TERMINAL
from webapp.inference import Inference, BudgetError, settings, ledger_accounting, api_configured, api_key_for, checked_accounting

ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 65 * 1024 * 1024


class CloudStore(Store):
    @contextmanager
    def connect(self):
        with cloud_runtime.LOCK, super().connect() as connection:
            yield connection


class App:
    def __init__(self, root=ROOT, data_dir=None, *, start_worker=True, inference_factory=Inference):
        self.root = Path(root).resolve()
        cloud_runtime.configure(self.root)
        if cloud_runtime.enabled() and data_dir is not None and Path(data_dir).resolve() != self.root / 'var':
            raise ValueError('Cloud runtime data must stay in var.')
        self.runtime = self.root / 'var'
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runtime.chmod(0o700)
        self.lock_file = (self.runtime / 'worker.lock').open('a+')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            raise RuntimeError('Another local app is already running for this repository.') from None
        self.ledger_root = self.runtime / 'runtime'
        self.ledger_root.mkdir(exist_ok=True, mode=0o700)
        self.ledger_root.chmod(0o700)
        try:
            self.store = (CloudStore if cloud_runtime.enabled() else Store)(self.root, data_dir or self.runtime)
            self.store.interrupt_unfinished()
            try:
                costs = checked_accounting(self.ledger_root, self.store.jobs())['per_job']
            except (ValueError, KeyError, TypeError, OSError):
                costs = None
            if costs is not None:
                for job in self.store.jobs():
                    cost = costs.get(job['id'], job['cost_inr'])
                    if not job.get('exports_available') and cost != job['cost_inr']:
                        self.store.update_job(job['id'], cost_inr=cost)
            self.engine = inference_factory(self.root, self.ledger_root, self.store)
            cloud_runtime.checkpoint()
        except Exception:
            self.lock_file.close()
            raise
        self.csrf_token = secrets.token_urlsafe(32)
        self.queue = queue.Queue()
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self._work, name='openrouter-single-worker', daemon=True)
        if start_worker:
            self.worker.start()

    def close(self):
        self.stop.set()
        self.queue.put(None)
        if self.worker.is_alive():
            self.worker.join(timeout=1)
        # Keep the process lock during an active network request, even after the HTTP listener closes.
        if not self.worker.is_alive():
            self.lock_file.close()

    def _cost(self, key):
        try:
            return ledger_accounting(self.ledger_root)['per_job'].get(key, 0.0)
        except (ValueError, KeyError, TypeError, OSError):
            return self.store.job(key)['cost_inr']

    def _work(self):
        try:
            while not self.stop.is_set():
                key = self.queue.get()
                if key is None or self.stop.is_set():
                    return
                self.process_job(key)
        finally:
            if self.stop.is_set():
                self.lock_file.close()

    def process_job(self, key):
        job = self.store.claim_job(key)
        if job is None:
            return
        started = time.monotonic()
        try:
            matches = self.engine.run(job, lambda stage: self.store.update_job(key, stage=stage, cost_inr=self._cost(key)))
            self.store.update_job(key, status='completed', stage='Complete', matches=matches, cost_inr=self._cost(key), error=None,
                                  completed_at=now(), elapsed_seconds=time.monotonic() - started)
        except Exception as error:
            diagnostic = str(error)[:6000]
            try:
                diagnostic = diagnostic.replace(api_key_for('OPENROUTER_API_KEY'), '[REDACTED]')
            except Exception:
                pass
            folder = self.ledger_root / key
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            (folder / 'error.json').write_text(json.dumps({'type': type(error).__name__, 'message': diagnostic}))
            if isinstance(error, BudgetError):
                message = 'The remaining spending allowance cannot cover another request. This upload and any charges were kept.'
            elif isinstance(error, ValueError):
                message = 'The result could not be validated. This upload and any charges were kept. Retry as a new run if needed.'
            else:
                message = 'The model request failed. This upload and any charges were kept. Retry as a new run if needed.'
            self.store.update_job(key, status='failed', stage='Run stopped', error=message, cost_inr=self._cost(key),
                                  completed_at=now(), elapsed_seconds=time.monotonic() - started)
        self._seal_prediction(key)

    def enqueue(self, jobs, created=True):
        cloud_runtime.checkpoint()
        if created:
            for job in jobs:
                self.queue.put(job['id'])
        return {'jobs': jobs}

    def bootstrap(self):
        return {'csrf_token': self.csrf_token, 'catalogue': self.store.products(), 'jobs': self.public_jobs(),
                'settings': settings(self.ledger_root, self.store.jobs())}

    def _seal_prediction(self, key):
        with cloud_runtime.LOCK:
            result = self._save_prediction(key)
            cloud_runtime.checkpoint()
            return result

    def _save_prediction(self, key):
        try:
            job = self.store.job(key)
            if job.get('exports_available'):
                return job
            costs = ledger_accounting(self.ledger_root)['per_job']
            cost = costs.get(key, job['cost_inr'])
            job = self.store.update_job(key, cost_inr=job['cost_inr'] if cost <= 0 < job['cost_inr'] else cost)
            internal = self.store.job(key, internal=True)
            details = collect_run_details(internal, internal['_snapshot'], self.ledger_root / key, job['cost_inr'])
            return self.store.seal_prediction(key, details)
        except Exception:
            return self.store.update_job(key, exports_available=False,
                export_error='The prediction could not be saved for download. Keep this run and reopen the app to try saving it again.')

    def public_jobs(self, key=None):
        jobs = [self.store.job(key)] if key is not None else self.store.jobs()
        try:
            costs = ledger_accounting(self.ledger_root)['per_job'] if any(not job.get('exports_available') for job in jobs) else {}
        except (ValueError, KeyError, TypeError, OSError):
            costs = {}
        for index, job in enumerate(jobs):
            if not job.get('exports_available'):
                job['cost_inr'] = costs.get(job['id'], job['cost_inr'])
                if job['status'] in TERMINAL:
                    jobs[index] = self._seal_prediction(job['id'])
                elif job['status'] == 'running':
                    internal = self.store.job(job['id'], internal=True)
                    try:
                        job['run_details'] = collect_run_details(internal, internal['_snapshot'], self.ledger_root / job['id'], job['cost_inr'])
                    except Exception:
                        job['run_details'] = None
            jobs[index].setdefault('exports_available', False)
            jobs[index].setdefault('run_details', None)
            jobs[index].setdefault('export_error', None)
        return jobs


def build_app(root=ROOT, data_dir=None, **options):
    return App(root, data_dir, **options)


class Handler(BaseHTTPRequestHandler):
    server_version = 'DysonLocal/1'

    def log_message(self, format, *args):
        # Uploaded names, query strings and errors never enter access logs.
        return

    @property
    def app(self):
        return self.server.app

    def _security(self, mutate=False):
        if cloud_runtime.enabled() and not hmac.compare_digest(self.headers.get('X-Container-Token', ''), os.environ.get('CLOUD_CONTAINER_TOKEN', '')):
            self.send_json(403, {'error': 'Open this demo through its authorised address.'})
            return False
        port = self.server.server_address[1]
        host = self.headers.get('Host', '')
        valid_hosts = {'127.0.0.1:' + str(port), 'localhost:' + str(port)}
        if port == 80:
            valid_hosts |= {'127.0.0.1', 'localhost'}
        if host not in valid_hosts:
            self.send_json(403, {'error': 'Open this app through its local address.'})
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin != 'http://' + host:
            self.send_json(403, {'error': 'Use the app from the same local browser address.'})
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send_json(403, {'error': 'Cross-site requests are not allowed.'})
            return False
        if mutate and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), self.app.csrf_token):
            self.send_json(403, {'error': 'Refresh this page before submitting changes.'})
            return False
        return True

    def _headers(self, status, mime, size):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(size))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")

    def send_json(self, status, data):
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self._headers(status, 'application/json; charset=utf-8', len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def file(self, path, mime, name=None):
        if not path.is_file():
            raise KeyError('File not found.')
        content = path.read_bytes()
        self._headers(200, mime, len(content))
        if name and mime == 'application/pdf':
            self.send_header('Content-Disposition', 'inline; filename="brochure.pdf"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if not self._security():
            return
        try:
            path = urlsplit(self.path).path
            if unquote(path) != path:
                raise KeyError('Page not found.')
            if path == '/api/bootstrap':
                self.send_json(200, self.app.bootstrap())
            elif path == '/api/catalogue':
                self.send_json(200, {'products': self.app.store.products()})
            elif re.fullmatch(r'/api/catalogue/[A-Za-z0-9_-]{1,80}', path):
                self.send_json(200, self.app.store.product(path.rsplit('/', 1)[1]))
            elif path == '/api/jobs':
                self.send_json(200, {'jobs': self.app.public_jobs()})
            elif re.fullmatch(r'/api/jobs/[A-Za-z0-9_-]{1,80}', path):
                self.send_json(200, self.app.public_jobs(path.rsplit('/', 1)[1])[0])
            elif re.fullmatch(r'/api/jobs/[A-Za-z0-9_-]{1,80}/export\.(json|csv)', path):
                key, kind = path.split('/')[3], path.rsplit('.', 1)[1]
                if not self.app.store.job(key).get('exports_available'):
                    self.app.public_jobs(key)
                content = self.app.store.prediction_export(key, kind)
                mime = 'application/json; charset=utf-8' if kind == 'json' else 'text/csv; charset=utf-8'
                self._headers(200, mime, len(content))
                self.send_header('Content-Disposition', 'attachment; filename="prediction-' + key + '.' + kind + '"')
                self.send_header('X-Content-SHA256', hashlib.sha256(content).hexdigest())
                self.end_headers()
                self.wfile.write(content)
            elif re.fullmatch(r'/media/[A-Za-z0-9_-]{1,80}', path):
                self.file(*self.app.store.media(path.rsplit('/', 1)[1]))
            elif path in ('/', '/web/index.html', '/web/app.js', '/web/style.css'):
                filename = 'index.html' if path == '/' else path.rsplit('/', 1)[1]
                mime = {'html': 'text/html; charset=utf-8', 'css': 'text/css; charset=utf-8', 'js': 'text/javascript; charset=utf-8'}[filename.rsplit('.', 1)[1]]
                self.file(self.app.root / 'web' / filename, mime)
            elif path == '/favicon.ico':
                self._headers(204, 'image/x-icon', 0)
                self.end_headers()
            else:
                raise KeyError('Page not found.')
        except ConflictError as error:
            self.send_json(409, {'error': str(error)})
        except KeyError:
            self.send_json(404, {'error': 'The requested item was not found.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_json(500, {'error': 'The saved data could not be read. Check the local app before continuing.'})

    def _body(self):
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip() != 'application/json':
            raise ValueError('Send this request as JSON.')
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked uploads are not supported.')
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            raise ValueError('A valid request length is required.') from None
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError('Upload requests must be 65 MiB or smaller.')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('The upload ended before the whole request arrived.')
        try:
            return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid number')))
        except (ValueError, UnicodeError):
            raise ValueError('The request contains invalid JSON.') from None

    def _mutate(self, method):
        with cloud_runtime.LOCK:
            self._mutate_locked(method)

    def _mutate_locked(self, method):
        if not self._security(mutate=True):
            return
        try:
            path = urlsplit(self.path).path
            body = self._body()
            if method == 'POST' and path == '/api/catalogue':
                product = self.app.store.edit_product(body)
                cloud_runtime.checkpoint()
                self.send_json(201, product)
            elif method == 'PATCH' and re.fullmatch(r'/api/catalogue/[A-Za-z0-9_-]{1,80}', path):
                product = self.app.store.edit_product(body, path.rsplit('/', 1)[1])
                cloud_runtime.checkpoint()
                self.send_json(200, product)
            elif method == 'POST' and path == '/api/jobs':
                if not isinstance(body, dict) or not isinstance(body.get('request_id'), str) or not ID.fullmatch(body['request_id']):
                    raise ValueError('A request ID is required before running a photo.')
                cached = self.app.store.cached_jobs(body)
                if cached is not None:
                    self.send_json(202, {'jobs': cached})
                    return
                if not api_configured():
                    self.send_json(503, {'error': 'Add OPENROUTER_API_KEY to the local .env before running a photo.'})
                    return
                budget = settings(self.app.ledger_root, self.app.store.jobs())
                if budget['accounting_error']:
                    self.send_json(409, {'error': budget['accounting_error']})
                    return
                if budget['runtime_remaining_inr'] <= 0:
                    self.send_json(409, {'error': 'The app spending limit has been reached.'})
                    return
                self.send_json(202, self.app.enqueue(*self.app.store.create_jobs(body, with_created=True)))
            elif method == 'POST' and re.fullmatch(r'/api/jobs/[A-Za-z0-9_-]{1,80}/retry', path):
                if not isinstance(body, dict) or set(body) != {'request_id'} or not isinstance(body['request_id'], str) or not ID.fullmatch(body['request_id']):
                    raise ValueError('A new request ID is required for a deliberate retry.')
                original_id = path.split('/')[3]
                cached = self.app.store.cached_jobs(body, original_id)
                if cached is not None:
                    self.send_json(202, {'jobs': cached})
                    return
                if not api_configured():
                    self.send_json(503, {'error': 'Add OPENROUTER_API_KEY to the local .env before retrying a photo.'})
                    return
                budget = settings(self.app.ledger_root, self.app.store.jobs())
                if budget['accounting_error']:
                    self.send_json(409, {'error': budget['accounting_error']})
                    return
                if budget['runtime_remaining_inr'] <= 0:
                    self.send_json(409, {'error': 'The app spending limit has been reached.'})
                    return
                self.send_json(202, self.app.enqueue(*self.app.store.retry(original_id, body['request_id'], with_created=True)))
            else:
                self.send_json(404, {'error': 'The requested action was not found.'})
        except ConflictError as error:
            self.send_json(409, {'error': str(error)})
        except ValueError as error:
            self.send_json(400, {'error': str(error)})
        except KeyError:
            self.send_json(404, {'error': 'The requested item was not found.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_json(500, {'error': 'This change could not be saved. Check the local app before trying again.'})

    def do_POST(self):
        self._mutate('POST')

    def do_PATCH(self):
        self._mutate('PATCH')

    def do_OPTIONS(self):
        if self._security():
            self.send_json(403, {'error': 'Cross-origin requests are not allowed.'})


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self):
        super().server_close()
        if hasattr(self, 'app'):
            self.app.close()


def make_server(app=None, port=8768, *, root=ROOT, data_dir=None, **options):
    created = app is None
    app = app or build_app(root, data_dir, **options)
    try:
        server = LocalServer(('0.0.0.0' if cloud_runtime.enabled() else '127.0.0.1', port), Handler)
    except Exception:
        if created:
            app.close()
        raise
    server.app = app
    return server


def main():
    parser = argparse.ArgumentParser(description='Run the local Dyson matching app.')
    parser.add_argument('--port', type=int, default=8080 if cloud_runtime.enabled() else 8768)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    server = make_server(port=args.port, data_dir=args.data_dir)
    print('Local app: http://127.0.0.1:' + str(args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
