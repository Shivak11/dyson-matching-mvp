# Cloudflare demo status

17 October 2026. The isolated implementation is on `codex/cloudflare-demo`, with the existing local app preserved. The new local preview is http://127.0.0.1:8770/.

## Completed

- Reworked upload workspace, catalogue guidance and explicitly assumed dataset requirements.
- Replayable four-step tour: dataset, manufacturer catalogue, store uploads, saved predictions and independent scoring.
- Existing Gemini/OpenRouter prompts, model settings, confidence gates and catalogue families preserved.
- Container-only gateway token, secret-backed access-code cookie and private R2 state transport implemented.
- SQLite backup, uploads and cost ledger checkpointed to private R2; restored before startup. In-flight reservations persist before paid calls. Restart does not automatically repeat paid calls.
- Manufacturer-only Docker seed and previous cost ledgers prepared locally. No historic store photos, blind-test inputs, answers, result exports or API keys enter the image.

## Evidence

- `python3 -m unittest discover -s tests -p test_cloud_runtime.py -v`: four passing focused tests.
- `node cloudflare/worker.test.mjs`: session integrity, expiry and unauthorised API/state assertions passed.
- Python and JavaScript syntax checks passed.
- Wrangler 4.151.1 gateway dry run with `--containers-rollout=none` passed. This validates the gateway bundle only; it does not validate or deploy the container image.
- Browser inspection at 1280px showed the actual upload workspace and manufacturer catalogue. The complete four-step tour was operated, including its dataset and confidence explanations. Key configuration became available through the ignored local environment; values were not displayed.
- Existing runtime allowance carried forward: approximately INR44.39 remaining at inspection. No new paid model call was made.

## Blockers and attempted recovery

1. The existing Wrangler OAuth login is for the research account, rather than the owner's requested paid Shivak11/kakkar11 profile. Its token also lacks container deployment scopes. A scope-limited login request was opened in the default browser. The page shows two saved profiles; owner action is needed to choose the paid personal profile and authorise Wrangler. Login attempts timed out without a callback. No resource was created in the research account. The Worker account ID and app origin must be populated from the verified paid account before deploy; current origin is intentionally invalid.
2. Docker Desktop is installed and its processes started, but the engine socket is absent. `docker info`, `docker desktop start`, direct app launches and the startup log were inspected. The log reports a pending macOS administrator authorisation to configure privileged port mapping. The owner must complete that operating-system prompt. The full Wrangler dry run correctly stopped because Docker could not build the image.

## Resume deployment

After owner authentication, verify the personal Cloudflare account and its Workers subdomain. Set the exact account ID and `APP_ORIGIN` in `cloudflare/wrangler.jsonc`. Create the unique private `multiplier-photo-demo-state` R2 bucket. Set `OPENROUTER_API_KEY`, `CLOUD_STATE_TOKEN`, `CLOUD_CONTAINER_TOKEN` and `DEMO_ACCESS_CODE` with Wrangler secret bulk input through stdin; never commit or display values. Retain an ignored owner-local access-code receipt. Verify Docker readiness, build/deploy the container and gateway, and run one authenticated real-photo upload/export within the carried-forward allowance. Confirm persistence after a controlled restart. Do not create a new budget or silently reset the seeded ledgers.

No Cloudflare deployment, hosted secret configuration, private runtime transfer or hosted inference has happened. The implementation uses a single demo container with bounded R2 checkpoints; it is not a production multi-tenant service.
