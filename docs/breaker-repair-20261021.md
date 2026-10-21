# Queue and worker repair, 21 October 2026

The owner authorised implementation after the report-only breaker audit. The original audit results and raw failures remain unchanged. This follow-up records the repair and its verification separately.

SQLite job rows now supply pending work. The in-memory queue only wakes workers. A failed upload/retry acknowledgement therefore retains a discoverable job; repeating the same request ID reconciles that job. Claims are atomic and checkpointed before inference. A failed claim returns to the database queue, and exceptions no longer terminate worker capacity. Terminal database, export and checkpoint persistence have three bounded attempts without repeating inference. The local HTTP listen backlog is 128.

Startup preserves queued jobs. Running jobs resume only when saved call records establish successful responses and no unresolved provider request. Resume validates the pinned model and frozen budget configuration. The transport still checks each exact request digest before using its cached response, and current shared accounting still controls any new paid call. An unknown request outcome retains its reservation and becomes interrupted; it is never silently submitted again.

The private authenticated `/__runtime` endpoint retains up to 20 redacted lifecycle events in Durable Object storage. It records timestamps, event types, exit codes, reason enums and error classes. It exposes no prompts, provider credentials or image contents. Diagnostic write failures do not stop the application. The earlier container interruption has no established historical cause; installed SDK inspection found no three-minute stop deadline.

## Local verification

The integrated Python regression set passed 95 checks. The 19 direct queue, checkpoint, claim, restart and transport-cache regressions were then repeated twice. They include the original upload and retry acknowledgement failures, two final checkpoint failures with three jobs and two surviving workers, and three six-client simultaneous upload bursts per run. Burst submissions retain one job per request ID. App restart after durable inventory completes with one remaining provider call and one inventory charge. A cached inventory cannot bypass the current budget for the next call.

Worker session/privacy/lifecycle tests and multiple-view UI assertions passed. These checks use temporary state, invented images and fake model responses; they cost INR0. No additional automated review-fix cycle was started. Earlier review count remains three.

## Hosted verification

Source repair `4dded4f` was built and the verified Python source hashes matched the container. The deployed container image is `sha256:33807655e3dbe70d4512681fcf619819cce0dfd70e547e1b9d52ba8af622388c`. Cloudflare application version 20 had no active rollout and reported that image on the running instance. The pinned Worker is `980b0d93-fef7-4909-8dca-39b9ed426b78`. The private diagnostic endpoint initially returned 503; after the protected readback amendment it returned HTTP200 with healthy state. Its historical 503 cause is unconfirmed.

An idle checkpoint-guarded recreation restored all prior jobs, catalogue entries and spending unchanged. The pre-deployment checkpoint has SQLite integrity `ok`, 29 jobs, 47 media records, all corresponding files and all charged ledgers. Accounted spending is INR305.39505, including INR21.888 in unresolved reservations. Its compressed archive SHA-256 is `465ccf7c4610d0746b3bbe4af8fce07c65987b94bdcde0ae5e216c2288eb9f9e`. No job is active. Separate schema diagnostics account for INR44.016675, leaving INR150.588275 in the combined INR500 allowance before any new verification call.

Technical decisions and evidence remain in this repository. Wiki consultation is read-only; no wiki, tracking or QMD state was changed.

The single affected-photo retry is `8dd0f136b5024295885f96c92253daf0`. It was acknowledged HTTP202 in 9.667 seconds. No rollout or restart was performed after its submission. It completed in 225.756 seconds for INR10.350675. The private checkpoint proves two HTTP200 successful physical calls: inventory 59.188 seconds and comparison 111.120 seconds. There is no pending reservation for this run. JSON and CSV downloads returned HTTP200 and retain the same prediction ID. The browser changed automatically from processing to the saved result; its screenshot is retained in ignored `var/timeout-20261021/worker-repair-completed.png`. The returned predictions passed the local validators; no labelled accuracy score was measured.

All 29 prior public job records and the catalogue remain equal. There are 30 saved attempts and zero active jobs. The final private checkpoint has SQLite integrity `ok`, 47 complete media records and SHA-256 `c56787ea0bb1e0908e39d8d28a99faf25cfe86b739f43c10b36059be8fc20abb`. Hosted accounting is INR315.745725 and UI allowance INR184.254275. Including INR44.016675 separate diagnostics leaves INR140.2376 in the combined allowance. The prior INR21.888 unresolved reservation remains conservatively accounted; no old cost or failed result was cleared.

The four scoped completion claims (source regressions, built package, hosted photo completion and browser result) passed the current Super-outer 5.22.0 completion check. Evidence and its one-day review period are recorded in `docs/evidence/worker-repair/`. No fresh automated release review was started after the owner’s three-cycle ceiling; the owner’s explicit fix instruction authorised these recorded repairs and direct regressions. Remote CI was not run; this remains the existing five-minute demo, with scoped source, container, API and browser verification.

Docker Desktop was stopped after building. The private temporary log stream was closed, and unrelated Rehearsal processes were preserved. Source, deployment and runtime observations remain separate in the evidence record.
