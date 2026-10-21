# Queue and worker repair, 21 October 2026

The owner authorised implementation after the report-only breaker audit. The original audit results and raw failures remain unchanged. This follow-up records the repair and its verification separately.

SQLite job rows now supply pending work. The in-memory queue only wakes workers. A failed upload/retry acknowledgement therefore retains a discoverable job; repeating the same request ID reconciles that job. Claims are atomic and checkpointed before inference. A failed claim returns to the database queue, and exceptions no longer terminate worker capacity. Terminal database, export and checkpoint persistence have three bounded attempts without repeating inference. The local HTTP listen backlog is 128.

Startup preserves queued jobs. Running jobs resume only when saved call records establish successful responses and no unresolved provider request. Resume validates the pinned model and frozen budget configuration. The transport still checks each exact request digest before using its cached response, and current shared accounting still controls any new paid call. An unknown request outcome retains its reservation and becomes interrupted; it is never silently submitted again.

The private authenticated `/__runtime` endpoint retains up to 20 redacted lifecycle events in Durable Object storage. It records timestamps, event types, exit codes, reason enums and error classes. It exposes no prompts, provider credentials or image contents. Diagnostic write failures do not stop the application. The earlier container interruption has no established historical cause; installed SDK inspection found no three-minute stop deadline.

## Local verification

The integrated Python regression set passed 95 checks. The 19 direct queue, checkpoint, claim, restart and transport-cache regressions were then repeated twice. They include the original upload and retry acknowledgement failures, two final checkpoint failures with three jobs and two surviving workers, and three six-client simultaneous upload bursts per run. Burst submissions retain one job per request ID. App restart after durable inventory completes with one remaining provider call and one inventory charge. A cached inventory cannot bypass the current budget for the next call.

Worker session/privacy/lifecycle tests and multiple-view UI assertions passed. These checks use temporary state, invented images and fake model responses; they cost INR0. No additional automated review-fix cycle was started. Earlier review count remains three.

## Hosted verification

Pending deployment. The pre-deployment checkpoint has SQLite integrity `ok`, 29 jobs, 47 media records, all corresponding files and all charged ledgers. Accounted spending is INR305.39505, including INR21.888 in unresolved reservations. Its compressed archive SHA-256 is `465ccf7c4610d0746b3bbe4af8fce07c65987b94bdcde0ae5e216c2288eb9f9e`. No job is active. Separate schema diagnostics account for INR44.016675, leaving INR150.588275 in the combined INR500 allowance before any new verification call.

Technical decisions and evidence remain in this repository. Wiki consultation is read-only; no wiki, tracking or QMD state was changed.
