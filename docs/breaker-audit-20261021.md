# Dyson matching MVP breaker audit

The report-only audit reproduced four defects: an upload or retry can remain queued after a storage error, final save failures can remove both workers, a job-claim write failure can remove a worker and its queued action, and a six-request local HTTP burst can lose a connection. The findings are open in [the ledger](breaker-findings-20261021.md).

## Target and persona

The target was source `9ceb1734eb73617e16d5e4934c3485c4e75a1be2`, using the actual Python HTTP handler, SQLite store, background workers, transport, request coordinator, cloud checkpoint implementation and evidence validators. The app listened only on `127.0.0.1`. All photos and catalogue images were newly generated solid-colour fixtures; all external services were faked. Product source was checked against the frozen commit before the final run and its Python modules were hashed in the receipt.

The persona was an impatient Delhi retail supervisor submitting several display photos, repeating an action after an error, adding product views, and checking that later jobs still run. He expects to leave the browser without losing work and does not want duplicate charges.

## Scenario results

The original run executed 18 scenarios twice, for 36 executions. An independent rerun of all 36 executions reproduced the three recovery findings and failed one burst case with a connection reset. Ten targeted burst iterations then reproduced four transport failures. Five scenarios now contribute to four open findings; the other 12 scenarios demonstrated specific guards under the supplied local conditions. There is no overall pass.

| Scenario | What was attempted | Observed twice |
| --- | --- | --- |
| 01 | Six simultaneous identical HTTP uploads followed by changed content under the same request ID | Initially passed; independent rerun had one connection reset. Four of ten targeted iterations then lost a connection. Successful iterations retained one job and one queue entry; changed content returned 409. BRK-004. |
| 02 | Upload checkpoint fails, storage recovers, browser repeats the same upload | HTTP 500 then 202, but the saved queued job has no queue entry. BRK-001. |
| 03 | Retry checkpoint fails, storage recovers, browser repeats the same retry | HTTP 500 then 202, but the retry has no queue entry. BRK-001. |
| 04 | Three jobs with two final prediction-seal checkpoint failures | Both workers exit; the third job stays queued. BRK-002. |
| 05 | A transient job-claim write failure after the worker pops the queue | One worker exits and the job stays queued without a queue entry. BRK-003. |
| 06 | Provider returns truncated JSON while reporting valid usage | The response is rejected, actual cost retained, reservation settled. |
| 07 | Token-truncated completion and an unexpected strict-schema field | Both are rejected; their reported costs remain recorded. |
| 08 | Two transient reservation-checkpoint failures, then recovery | The identical snapshot is retried; exactly one fake provider call starts after persistence succeeds. |
| 09 | Persistent reservation-checkpoint failure, then client reopen | No provider call starts; the unresolved upper-bound reservation remains and prevents replay. |
| 10 | Two transient settlement-checkpoint failures, then recovery | One provider call and one recorded charge; state writes recover without another model call. |
| 11 | Persistent settlement failure followed by restoring the last successful checkpoint | Local state has the actual charge; restored state retains the conservative unresolved reservation and refuses a duplicate call. |
| 12 | Three actual transport clients sharing a two-call coordinator | At most two mock provider calls overlap; all three eventually settle. |
| 13 | Two simultaneous clients when allowance covers only one upper-bound reservation | One is admitted and the other is rejected before a provider call. |
| 14 | Two actual client launches separated by four simulated seconds | The coordinator waits 11 simulated seconds and launches at seconds 0 and 15. |
| 15 | App reopen with a running job, a settled call and an unresolved reservation | Job becomes interrupted, both charges/reservations remain accounted, no automatic paid resume occurs. |
| 16 | Contradictory joint views and a feature referring to an unsupplied view | Contradictory views produce `not_sure`; an unsupplied view is rejected. |
| 17 | Catalogue changes between views, duplicate photo and fourth view | Original catalogue lineage is retained; duplicate content and a fourth view are rejected. |
| 18 | HTTP 429 followed by a malformed strict-schema response | Exactly two fake attempts; unknown first-call usage is reserved conservatively, actual second-call usage is retained. |

## Calls, cost and isolation

Each initially successful full run recorded **22 loopback HTTP attempts** and **28 fake provider exchanges**. The independent full rerun recorded **21 loopback HTTP attempts**, **28 fake provider exchanges** and one failing burst case. The ten targeted burst iterations recorded **66 loopback HTTP attempts**, no provider exchanges and four failing cases. Every run made **zero real model calls** and **zero production calls**. The socket guard recorded zero attempted external connections. The audit cost **₹0**. It did not open `.env`, `cloudflare/secrets.json`, real uploaded photos or production checkpoints. Dummy API-key resolution was installed before exercising any paid-request boundary.

The first sandbox attempt could not bind a loopback HTTP server; the non-HTTP scenarios ran locally. The authorised escalated run enabled loopback binding while the harness continued blocking all external sockets. An initial successful run was repeated after adding source fingerprints; both produced the same recovery findings. The independent full rerun exposed the intermittent burst defect. Its failing receipt was copied before targeted testing, which writes a separate `burst-results.json` and does not overwrite the full-run failure.

## Evidence and remaining gaps

The standalone harness is `tests/breaker_audit_20261021.py`; it is outside ordinary unit-test discovery because its assertions intentionally reproduce defects. Run it directly with the bundled Python and `PYTHONPATH=.:tests`. The harness and ledger are checked-in candidates; the generated evidence remains ignored under `var/breaker-20261021/`. The two initially successful logs are `run-first.log` and `run.log`. The independent failing full-run evidence is preserved in `root-results-first.json` and `root-run-first.log`; the targeted follow-up is in `burst-results.json` and `burst-run.log`. JSON receipts include tested source hashes. Green assertions in the initial runs confirm reproduced defects rather than establish a defect-free service. The later failing assertions remain failures. No product fixes, commits, deployments or external service mutations were performed by this audit.

These tests do not establish visual identification accuracy, provider schema support, real response latency, the rendered browser transitions, Cloudflare container lifetime, R2 network behaviour or automatic durability across a deployed container replacement. Simulated time proves the launch-spacing calculation, not real clock scheduling under load. A restored unresolved reservation intentionally remains conservative when actual upstream usage is unavailable.

The owner session separately observed a deployed verification becoming interrupted after a successful inventory call, without an intervening owner deployment or explicit restart. Its cause is unproved. This audit did not access that run or infer that one of the four local findings caused it. Background persistence on the deployed service remains unproved; a local recovery test cannot establish that it continues across a real container restart.
