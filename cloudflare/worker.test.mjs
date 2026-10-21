import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = (await readFile(new URL('./worker.js', import.meta.url), 'utf8'))
  .replace("import { Container } from '@cloudflare/containers';", `class Container {
    constructor(ctx) { this.ctx = ctx; this.container = { running: true }; this.stops = 0; }
    onStart() { this.starts = (this.starts || 0) + 1; }
    onStop(params) { this.stopParams = params; }
    onError(error) { throw error; }
    async onActivityExpired() { if (this.container.running) await this.stop(); }
    async stop() { this.stops += 1; }
    async getState() { return { status: 'healthy', lastChange: 123, exitCode: 7, env: 'PRIVATE', message: 'PRIVATE' }; }
  }`);
const worker = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const secret = 'test-only-gateway-secret';
const token = await worker.sessionToken(secret, Date.now() + 60000);
const request = value => new Request('https://demo.example/api/bootstrap', { headers: { cookie: 'multiplier_demo=' + value } });
assert.equal(await worker.validSession(request(token), secret), true);
assert.equal(await worker.validSession(request(token), 'wrong-secret'), false);
assert.equal(await worker.validSession(request(await worker.sessionToken(secret, Date.now() - 1000)), secret), false);
assert.equal(await worker.equalSecret('first', 'second'), false);
const env = { DEMO_ACCESS_CODE: 'test-only-code', CLOUD_CONTAINER_TOKEN: secret, CLOUD_STATE_TOKEN: 'test-only-state', OPENROUTER_API_KEY: 'test-only-key' };
assert.equal((await worker.default.fetch(new Request('https://demo.example/api/jobs', { method: 'POST' }), env)).status, 401);
assert.equal((await worker.default.fetch(new Request('https://demo.example/__state'), env)).status, 404);
assert.equal((await worker.default.fetch(new Request('https://demo.example/__state', { headers: { authorization: 'Bearer undefined' } }), {})).status, 404);
let recreates = 0;
const controlEnv = { ...env, STATE: { head: async () => ({ size: 100 }) }, PHOTO_DEMO: { getByName: () => ({ destroy: async () => { recreates += 1; } }) } };
const restart = authorization => new Request('https://demo.example/__state', { method: 'POST', headers: { authorization, 'x-demo-action': 'restart' } });
assert.equal((await worker.default.fetch(restart('Bearer wrong'), controlEnv)).status, 404);
assert.equal(recreates, 0);
assert.equal((await worker.default.fetch(restart('Bearer test-only-state'), { ...controlEnv, STATE: { head: async () => null } })).status, 409);
assert.equal(recreates, 0);
assert.equal((await worker.default.fetch(restart('Bearer test-only-state'), controlEnv)).status, 200);
assert.equal(recreates, 1);
const login = await worker.default.fetch(new Request('https://demo.example/'), env);
assert.equal(login.status, 200);
assert.equal(login.headers.get('Referrer-Policy'), 'same-origin');
assert.match(await login.text(), /Enter the demo access code/);
const loginRequest = origin => new Request('https://demo.example/login', { method: 'POST', headers: { origin }, body: new URLSearchParams({ code: env.DEMO_ACCESS_CODE }) });
const loginEnv = { ...env, PHOTO_DEMO: { getByName: () => ({ allowLogin: async () => true }) } };
assert.equal((await worker.default.fetch(loginRequest('null'), loginEnv)).status, 403);
const accepted = await worker.default.fetch(loginRequest('https://demo.example'), loginEnv);
assert.equal(accepted.status, 303);
assert.match(accepted.headers.get('Set-Cookie'), /HttpOnly; Secure; SameSite=Strict/);
console.log('Session validation and unauthorised API/state checks passed.');

const saved = new Map();
const storage = {
  get: async key => structuredClone(saved.get(key)),
  put: async (key, value) => { saved.set(key, structuredClone(value)); },
  transaction: async callback => callback(storage),
};
const instance = new worker.PhotoDemo({ storage }, { ...env, APP_ORIGIN: 'https://demo.example' });
const runtimeEnv = { ...env, PHOTO_DEMO: { getByName: () => instance } };
const runtimeRequest = (authorization, method = 'GET') => new Request('https://demo.example/__runtime', { method, headers: authorization ? { authorization } : {} });
assert.equal((await worker.default.fetch(runtimeRequest(), runtimeEnv)).status, 404);
assert.equal((await worker.default.fetch(runtimeRequest('Bearer wrong'), runtimeEnv)).status, 404);
assert.equal((await worker.default.fetch(runtimeRequest('Bearer undefined'), {})).status, 404);
assert.equal((await worker.default.fetch(runtimeRequest('Bearer test-only-state', 'POST'), runtimeEnv)).status, 405);
for (let index = 0; index < 24; index += 1) await instance.onStart();
assert.equal(instance.starts, 24);
await instance.onStop({ exitCode: 137, reason: 'exit', message: 'PRIVATE STOP', env: 'PRIVATE' });
assert.equal(instance.stopParams.exitCode, 137);
const privateError = new TypeError('PRIVATE MESSAGE');
await assert.rejects(instance.onError(privateError), error => error === privateError);
await instance.onActivityExpired();
assert.equal(instance.stops, 1);
instance.container.running = false;
await instance.onActivityExpired();
assert.equal(instance.stops, 1);
const runtime = await worker.default.fetch(runtimeRequest('Bearer test-only-state'), runtimeEnv);
assert.equal(runtime.status, 200);
assert.equal(runtime.headers.get('Cache-Control'), 'no-store');
const diagnostics = await runtime.json();
assert.equal(diagnostics.events.length, 20);
assert.equal(diagnostics.telemetry_available, true);
assert.deepEqual(diagnostics.state, { status: 'healthy', lastChange: 123, exitCode: 7 });
assert.equal(diagnostics.events.filter(event => event.type === 'stop')[0].exitCode, 137);
assert.equal(diagnostics.events.filter(event => event.type === 'stop')[0].reason, 'exit');
assert.equal(diagnostics.events.filter(event => event.type === 'error')[0].error_name, 'TypeError');
assert.match(diagnostics.events[0].timestamp_utc, /^\d{4}-\d{2}-\d{2}T.*Z$/);
assert.doesNotMatch(JSON.stringify(diagnostics), /PRIVATE|OPENROUTER|test-only/);
assert.equal(saved.get('lifecycle-events').length, 20);
await instance.onError({ name: 'PRIVATE CUSTOM ERROR', message: 'PRIVATE' }).catch(() => {});
await instance.onStop({ exitCode: 'PRIVATE', reason: 'PRIVATE' });
const redacted = await instance.runtimeStatus();
assert.equal(redacted.events.at(-2).error_name, 'Error');
assert.equal(redacted.events.at(-1).exitCode, null);
assert.equal(redacted.events.at(-1).reason, 'unknown');
assert.doesNotMatch(JSON.stringify(redacted), /PRIVATE/);
saved.set('lifecycle-events', [{ timestamp_utc: new Date().toISOString(), type: 'start', message: 'PRIVATE', stack: 'PRIVATE' },
  { timestamp_utc: 'PRIVATE', type: 'PRIVATE' }]);
instance.getState = async () => ({ status: 'PRIVATE', secret: 'PRIVATE' });
const filtered = await instance.runtimeStatus();
assert.equal(filtered.events.length, 1);
assert.equal(filtered.state, null);
assert.doesNotMatch(JSON.stringify(filtered), /PRIVATE/);
assert.equal(instance.starts, 24);
const failingStorage = { get: async () => { throw privateError; }, transaction: async () => { throw privateError; } };
const unavailable = new worker.PhotoDemo({ storage: failingStorage }, { ...env, APP_ORIGIN: 'https://demo.example' });
await unavailable.onStart();
await unavailable.onStop({ exitCode: 0, reason: 'exit' });
await unavailable.onActivityExpired();
assert.equal(unavailable.starts, 1);
assert.equal(unavailable.stops, 1);
await assert.rejects(unavailable.onError(privateError), error => error === privateError);
const unavailableStatus = await unavailable.runtimeStatus();
assert.equal(unavailableStatus.telemetry_available, false);
assert.deepEqual(unavailableStatus.events, []);
assert.doesNotMatch(JSON.stringify(unavailableStatus), /PRIVATE/);
console.log('Private bounded lifecycle telemetry, redaction and lifecycle behaviour checks passed.');
