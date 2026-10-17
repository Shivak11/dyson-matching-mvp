import { Container } from '@cloudflare/containers';

const encoder = new TextEncoder();
const COOKIE = 'multiplier_demo';
const MAX_STATE = 100 * 1024 * 1024;

export async function equalSecret(left, right) {
  if (!left || !right) return false;
  const a = new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(left)));
  const b = new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(right)));
  return a.reduce((difference, value, index) => difference | (value ^ b[index]), 0) === 0;
}

async function key(secret) {
  return crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);
}

export async function sessionToken(secret, expires) {
  const payload = String(expires);
  const signature = new Uint8Array(await crypto.subtle.sign('HMAC', await key(secret), encoder.encode(payload)));
  return payload + '.' + Array.from(signature, byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function validSession(request, secret) {
  const cookie = (request.headers.get('cookie') || '').split(';').map(part => part.trim()).find(part => part.startsWith(COOKIE + '='));
  const token = cookie?.slice(COOKIE.length + 1) || '';
  if (!/^\d{10,13}\.[a-f0-9]{64}$/.test(token)) return false;
  const [expires, signature] = token.split('.');
  if (Number(expires) <= Date.now() || Number(expires) > Date.now() + 8 * 86400000) return false;
  return crypto.subtle.verify('HMAC', await key(secret), Uint8Array.from(signature.match(/../g), byte => parseInt(byte, 16)), encoder.encode(expires));
}

export class PhotoDemo extends Container {
  defaultPort = 8080;
  sleepAfter = '30m';
  enableInternet = true;

  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = {
      CLOUD_MODE: '1',
      CLOUD_STATE_URL: env.APP_ORIGIN + '/__state',
      CLOUD_STATE_TOKEN: env.CLOUD_STATE_TOKEN,
      CLOUD_CONTAINER_TOKEN: env.CLOUD_CONTAINER_TOKEN,
      OPENROUTER_API_KEY: env.OPENROUTER_API_KEY,
      PYTHONUNBUFFERED: '1',
    };
  }

  async allowLogin() {
    const now = Date.now();
    const stored = await this.ctx.storage.get('login-window');
    const window = stored && now - stored.started < 60000 ? stored : { started: now, count: 0 };
    window.count += 1;
    await this.ctx.storage.put('login-window', window);
    return window.count <= 20;
  }
}

function response(body, status = 200, headers = {}) {
  return new Response(body, { status, headers: {
    'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY', ...headers,
  } });
}

function loginPage(failed = false) {
  return response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Multiplier · Photo matching</title><style>*,*:before,*:after{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#12181f;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh;display:grid;place-items:center;padding:24px}main{background:white;border:1px solid #dde3e7;border-radius:16px;max-width:460px;width:100%;padding:42px}h1{font-size:30px;line-height:1.2;letter-spacing:-1px;margin:0 0 14px}p{color:#5a6874;margin:0 0 30px}label{display:block;font-weight:600;margin-bottom:8px}input{font:inherit;width:100%;padding:12px;border:1px solid #b8c3ca;border-radius:8px}button{font:inherit;font-weight:600;border:0;border-radius:8px;background:#126a54;color:white;width:100%;padding:13px;margin-top:20px;cursor:pointer}:focus-visible{outline:3px solid #5a7488;outline-offset:3px}.error{color:#a63129;margin:12px 0 0}</style></head><body><main><h1>Store photo matching</h1><p>Enter the demo access code to open the Multiplier workspace.</p><form action="/login" method="post"><label for="code">Access code</label><input id="code" name="code" type="password" autocomplete="current-password" required maxlength="200" autofocus>${failed ? '<p class="error" role="alert">The access code was not accepted. Try again.</p>' : ''}<button type="submit">Open workspace</button></form></main></body></html>`, failed ? 401 : 200, { 'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'" });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === '/__state') {
        if (!env.CLOUD_STATE_TOKEN || !await equalSecret(request.headers.get('authorization'), 'Bearer ' + env.CLOUD_STATE_TOKEN)) return response('Not found', 404);
        if (request.method === 'GET') {
          const saved = await env.STATE.get('demo/state.tar.gz');
          return saved ? response(saved.body, 200, { 'Content-Type': 'application/gzip' }) : response('Not found', 404);
        }
        if (request.method === 'PUT') {
          const length = Number(request.headers.get('content-length'));
          if (!Number.isSafeInteger(length) || length <= 0 || length > MAX_STATE) return response('State exceeds the demo limit', 413);
          await env.STATE.put('demo/state.tar.gz', request.body, { httpMetadata: { contentType: 'application/gzip' } });
          return response('Saved');
        }
        return response('Method not allowed', 405);
      }
      if (url.pathname === '/health') return response('{"ok":true}', 200, { 'Content-Type': 'application/json' });
      if (!env.DEMO_ACCESS_CODE || !env.CLOUD_CONTAINER_TOKEN || !env.CLOUD_STATE_TOKEN || !env.OPENROUTER_API_KEY) return response('Demo configuration is incomplete.', 503);
      if (url.pathname === '/login' && request.method === 'POST') {
        if (request.headers.get('origin') !== url.origin || Number(request.headers.get('content-length')) > 2048) return response('Use the demo sign-in page.', 403);
        const instance = env.PHOTO_DEMO.getByName('multiplier-single-demo');
        if (!await instance.allowLogin()) return response('Too many sign-in attempts. Try again in a minute.', 429);
        const form = new URLSearchParams(await request.text());
        if (!await equalSecret(form.get('code'), env.DEMO_ACCESS_CODE)) return loginPage(true);
        const token = await sessionToken(env.CLOUD_CONTAINER_TOKEN, Date.now() + 7 * 86400000);
        return response(null, 303, { Location: '/', 'Set-Cookie': `${COOKIE}=${token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=604800` });
      }
      if (!await validSession(request, env.CLOUD_CONTAINER_TOKEN)) {
        if (request.method === 'GET' && !url.pathname.startsWith('/api/')) return loginPage();
        return response('{"error":"Enter the demo access code again."}', 401, { 'Content-Type': 'application/json' });
      }
      if (!['GET', 'HEAD'].includes(request.method) && request.headers.get('origin') !== url.origin) return response('Use the same workspace address.', 403);
      const target = new URL(request.url);
      target.hostname = 'localhost'; target.port = '8080'; target.protocol = 'http:';
      const headers = new Headers(request.headers);
      headers.set('Host', 'localhost:8080');
      headers.set('X-Container-Token', env.CLOUD_CONTAINER_TOKEN);
      headers.delete('Cookie'); headers.delete('Authorization');
      if (headers.has('Origin')) headers.set('Origin', 'http://localhost:8080');
      const forwarded = new Request(target, { method: request.method, headers, body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body, redirect: 'manual' });
      return await env.PHOTO_DEMO.getByName('multiplier-single-demo').fetch(forwarded);
    } catch {
      return response('{"error":"The demo is starting or temporarily unavailable. Refresh shortly."}', 503, { 'Content-Type': 'application/json', 'Retry-After': '10' });
    }
  },
};
