# Dyson matching MVP breaker findings

This is a report-only ledger for source `9ceb1734eb73617e16d5e4934c3485c4e75a1be2`, tested on 21 October 2026. No product code was changed. The target was the actual Python app running locally against invented images, a temporary SQLite database and fake provider/state services. No deployed service was called.

The persona is a Delhi retail supervisor who has several displays to verify before leaving the store. He uploads photos quickly, repeats a submission after an error, and expects a previous upload to continue while he handles another display. He does not understand request IDs, worker threads or cloud checkpoints. He expects the upload and its charge to remain visible and wants to avoid paying twice.

## BRK-001: A storage error can leave an upload permanently queued

- **Severity:** High.
- **Date and target:** 21 October 2026, `9ceb173`.
- **Category:** Lost queued action and misleading acknowledgement.
- **Status:** Fixed in source `4dded4f`; the recorded failure sequence passed twice with corrected behaviour. See `docs/breaker-repair-20261021.md`.
- **Reproductions:** Two independent upload runs and two independent retry runs, each with fresh temporary state.
- **Exact input:** `POST /api/jobs` with `{"images":[<invented white PNG named store.png>],"request_id":"resubmit-after-storage-error"}`. Raise `CloudStateError("invented temporary storage outage")` at the checkpoint performed by `App.enqueue`, then restore the state service and submit the identical body again. The retry variant uses `POST /api/jobs/<invented-failed-id>/retry` with `{"request_id":"retry-after-storage-error"}`.
- **Observed:** The first response is HTTP 500. The repeated response is HTTP 202 with the saved job's `status` equal to `queued`. The queue contains zero entries. Exactly one uploaded job exists. The retry route produces the same outcome.
- **Evidence:** Scenarios `test_02_http_upload_checkpoint_loss_then_repeat` and `test_03_http_retry_checkpoint_loss_then_repeat` in `var/breaker-20261021/results.json` record `first_status:500`, `repeated_status:202` and `queue:0` twice each.
- **Expected:** After storage recovers, a deliberate repeated submission should either safely enqueue the existing unstarted job or return an explicit recoverable failure. It should not acknowledge work that no worker can reach.
- **Relevant source:** `app_server.py:152` checkpoints after `Store.create_jobs` has committed, before adding IDs to the in-memory queue. The cached-request branches at `app_server.py:370` and `app_server.py:389` return without enqueueing. Startup marks unfinished jobs interrupted rather than resuming them.
- **Scope:** This is a reproduced failure sequence. It does not establish the cause of a particular deployed failure.

## BRK-002: Final checkpoint failures can terminate both workers

- **Severity:** High.
- **Date and target:** 21 October 2026, `9ceb173`.
- **Category:** Background processing stops while queued work remains.
- **Status:** Fixed in source `4dded4f`; the recorded failure sequence passed twice with corrected behaviour. See `docs/breaker-repair-20261021.md`.
- **Reproductions:** Two independent runs, each starting two actual app workers and three invented jobs.
- **Exact input:** Submit three ordinary invented photos named `a.png`, `b.png` and `c.png`. Use a fake inference engine returning an empty valid machine list. At each final prediction-seal checkpoint raise `CloudStateError("invented final seal outage")`.
- **Observed:** Both worker threads exit with that exception. The job states are `completed`, `completed`, `queued`; one queue entry remains and `remaining_workers` becomes zero. The application process itself remains available. This does not require a model response failure or model timeout.
- **Evidence:** Scenario `test_04_two_final_seal_failures_remove_both_workers` records `workers_alive:0`, `queue:1` and two worker errors in each execution.
- **Expected:** A failed final save should be visible as a recovery state and should not permanently remove worker capacity. Further paid work should remain stopped while durability is unavailable, but the workers must survive and be able to recover when storage becomes available.
- **Relevant source:** `app_server.py:150` invokes `_seal_prediction` outside the `process_job` exception handler. `_seal_prediction` calls `cloud_runtime.checkpoint` at `app_server.py:175`. `_work` has a `finally` block but no exception handler around `process_job` at `app_server.py:115`.
- **Scope:** This proves worker loss under the injected save failure. It does not prove the cause of a Cloudflare container restart or of the separately observed interrupted live run.

## BRK-003: A job-claim write failure drops a queue entry and removes a worker

- **Severity:** Medium.
- **Date and target:** 21 October 2026, `9ceb173`.
- **Category:** Lost queued action and reduced worker capacity.
- **Status:** Fixed in source `4dded4f`; the recorded failure sequence passed twice with corrected behaviour. See `docs/breaker-repair-20261021.md`.
- **Reproductions:** Two independent runs with fresh state.
- **Exact input:** Upload one invented photo. When its actual worker pops the queue entry, make the SQLite claim boundary raise `OSError("invented SQLite write failure")`; then remove the injected failure.
- **Observed:** One worker exits. The job remains `queued`, its queue entry is gone, and only one worker survives. Restoring the write boundary does not resubmit the popped job or replace the worker.
- **Evidence:** Scenario `test_05_claim_write_failure_terminates_worker` records `status:queued`, `queue:0`, `workers_alive:1` and the exact injected error twice.
- **Expected:** A claim failure should retain a recoverable job and worker capacity without starting a paid call. A transient write failure should not silently remove the job from all active work queues.
- **Relevant source:** `app_server.py:112` removes the queue item before `process_job` calls `claim_job` at `app_server.py:123`, outside its exception handler. `_work` does not catch that exception.
- **Scope:** This is an injected local dependency failure. No real database was damaged or modified.

## BRK-004: Six simultaneous local uploads can lose a connection

- **Severity:** Medium for the local HTTP service; deployed gateway behaviour is unproved.
- **Date and target:** 21 October 2026, `9ceb173`.
- **Category:** A modest request burst produces a transport error instead of a response.
- **Status:** Fixed in source `4dded4f`; the recorded failure sequence passed twice with corrected behaviour. See `docs/breaker-repair-20261021.md`.
- **Reproductions:** Four failures in ten targeted iterations after an independent full-suite rerun first exposed the failure. Each iteration starts a fresh local actual-code server and temporary database.
- **Exact input:** Six simultaneous `POST /api/jobs` requests containing the same invented white PNG and `request_id:"supervisor-double-tap"`, released by a six-thread barrier. No model call is made.
- **Observed:** Four of ten iterations return five HTTP responses for six requests. Two record `URLError: <urlopen error [Errno 54] Connection reset by peer>` and two record `URLError: <urlopen error [Errno 32] Broken pipe>`. No test thread remains alive. The other six iterations return six 202 responses for one job and one queued action, and reject changed content under the same ID with 409.
- **Evidence:** `var/breaker-20261021/burst-results.json` records all ten iterations and captured thread exceptions; `burst-run.log` retains the four assertion failures. `root-results-first.json` and `root-run-first.log` preserve the independent earlier 36-execution run with one burst failure.
- **Expected:** Each accepted local connection should receive an application response or an explicit overload response. A browser should be able to recover a failed acknowledgement without duplicate paid work.
- **Relevant source:** `app_server.py:429` subclasses `ThreadingHTTPServer`. The exact cause of the connection resets was not isolated. Listen backlog, scheduling and local operating-system behaviour remain possible explanations; this audit does not establish one.
- **Scope:** This is reproducible on the local actual-code HTTP server. It does not prove that Cloudflare exhibits the same failure. It also does not invalidate the observed no-duplicate-job guard in iterations that completed all responses.

## Evidence and recheck rule

The harness is `tests/breaker_audit_20261021.py`. The initial breaker runs are logged in `var/breaker-20261021/run-first.log` and `run.log`. They reached their expected observations, including BRK-001 to BRK-003; those green assertions were never a defect-free result. The independently rerun full-suite receipt is retained as `root-results-first.json`, and the targeted burst receipt is `burst-results.json`. Both include SHA-256 hashes of the tested Python product modules. The independent full-suite failure and the four targeted failures remain recorded and were not changed into passing assertions.

All four entries were open at the end of the report-only audit. The later owner-authorised repair in `4dded4f` passed each sequence twice using direct regressions in `tests/test_job_resilience.py`. The original failing observations remain unchanged. Hosted verification and its limits are recorded separately in `docs/breaker-repair-20261021.md`.
