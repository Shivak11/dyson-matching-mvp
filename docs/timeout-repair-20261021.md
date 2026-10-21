# Hosted matching repair, 21 October 2026

The owner requested a repair for long processing, a reported 325-second timeout, a failed result for `12807_2_8.jpg`, background processing, parallel calls where possible and structured JSON enforcement. The provider, Gemini 3.7 Flash high settings, catalogue, confidence/evidence rules and INR500 runtime allowance remain unchanged.

## Recorded failures

Job `c7f9f3acc8544207abeace744159bec9` was interrupted by the previous budget deployment. Its two successful calls took 72.28 and 182.08 seconds and accounted for INR14.1594. The rollout began before the later idle restart check. This was a deployment interruption, not a proved Gemini timeout. Check idle state before publishing any Worker/container rollout.

Retry `528868b9584547a3b371d6152931a555` failed at 217.624 seconds after two successful calls, accounting for INR8.7231. The comparison used the literal field name `detail: short visible diagnostic comparison` instead of `detail`, causing local evidence validation to stop. The compatibility repair accepts only that exact alias when canonical `detail` is absent. Canonical invalid values, unsupported regions and inadequate evidence remain rejected. Offline replay accepted two matches and retained one unsure result because its handle region was outside the target. This is validator replay, not an independently scored accuracy result.

The initial strict-schema deployment's verification job `e7a5c2d6b6514548bf68c03cdda33178` returned HTTP202 in 4.58 seconds but failed before inference: Google AI Studio rejected the full inventory schema with HTTP400. It stopped after 30.423 seconds including checkpoint work; the network call took 3.494 seconds. The missing provider usage retained an INR21.888 conservative reservation, which is not a confirmed provider bill. This attempt remains immutable.

## Changes

Every application inference call now requests `json_schema`, `strict: true` and provider `require_parameters: true`. Exact required fields, types and permitted enum values are supplied for inventory, comparison, crop refinement and cumulative views. The original full local schema is checked before the existing evidence validators; a supplied schema never silently downgrades to plain JSON mode.

A minimal schema succeeded against the actual endpoint; the full inventory failed even after nullable syntax adaptation. The complete inventory succeeded after removing numeric/array bounds from the provider payload. Gemini receives nullable type arrays and closed required objects. Pattern, string-length, numeric and array bounds remain in the original local schema and are checked on every result. The provider's complexity limit therefore does not remove box geometry, count or identity checks. No-image diagnostics also established acceptance of the full joint inventory and joint comparison structures; their intentionally empty arrays tested endpoint compatibility only.

Two background workers can process independent jobs concurrently. A shared semaphore permits at most two provider requests in flight. A shared admission lock preserves 15 seconds between launches and serialises global budget rechecks with durable reservation writes. Reservations from both jobs count against the same cap. Dependencies inside one identification remain ordered; all candidates/objects are already compared in one batch. Separate uploaded jobs are not treated as cumulative views.

Provider reservations are checkpointed before paid requests. Response-ledger settlement and reservation removal now share one checkpoint, reducing a successful call from three remote checkpoints to two. Gzip level 1 replaces level 9. A synthetic 6.49 MB mixed-image/JSON checkpoint benchmark measured median CPU down 10.67%, wall time down 11.65% and archive size up 0.158%; these are local microbenchmark results, not measured Cloudflare speed gains.

The shared state lock still covers synchronous snapshot/upload work. A provider call can still take minutes with high reasoning, and a remote failure can still occur. This repair does not guarantee that every photo resolves or that external services cannot fail. Failed paid attempts are preserved rather than automatically replayed and charged again.

## Verification and review

The initial integrated repair passed 72 focused Python tests, cumulative-view JavaScript tests, Worker boundary tests and whitespace checks. After the provider compatibility adjustment, 43 relevant Python checks passed, including outgoing strict-schema requests, preservation of local constraints, exact alias handling, candidate evidence and cumulative views. Actual transport concurrency and budget-race tests use two clients and a fake network barrier; they do not create paid load.

Independent automated review cycle one cleared the integrated source. Cycle two cleared the compatibility delta and independently exercised local rejection of a string-length violation omitted from the provider payload. Two of the maximum three review-fix cycles have been used. Reviews do not substitute for live endpoint or image-run evidence.

Before the compatibility rollout, the hosted app was idle with 26 saved attempts, 46 media records and INR259.5966 accounted. The private checkpoint passed SQLite integrity, media completeness and paid-ledger equality checks. SHA256: `3c359f3e6330ebdda4e07449affe444e7c347cb70895e71d721ae5eaa2225487`.

## Delivery verification

The compatibility repair is deployed in Worker version `270893e4-e547-4729-961b-63237b092ccf`, with image `sha256:4b48bfb7e36cb0f9501464304aee1c5e786537dbb0f5103daa96b93bf3a7feb2`. The cf application readback names that exact digest. Idle checkpoint verification preceded publishing and explicit activation. All 26 earlier public attempts, their charges and the catalogue remained equal after recreation.

The deliberate affected-photo retry `5f585828951741ebb11b834e9ff728d9` completed without a technical error. It queued for 3.806 seconds, then took 235.219 seconds and cost INR10.8813. Inventory took 64.545 seconds (INR3.562575); comparison took 122.433 seconds (INR7.318725). Both returned strict shapes accepted by the original local schemas. The remaining approximately 48.24 seconds include pacing, checkpoint and application work; that difference is not an isolated storage measurement. No browser was required to keep processing active. A status read during processing returned in 1.18 seconds; another returned in 1.70 seconds.

The saved result identifies V12 Detect Slim, V8 Absolute family and WashG1, each with High confidence and evidence. These are predictions, not an independently labelled accuracy score. The JSON export was downloaded and verified. No mass dataset rerun or paid concurrency/load test was performed.

Hosted accounting now records INR270.4779 spent and INR229.5221 remaining under the unchanged INR500 allowance. Separate local no-image schema diagnostics account for INR44.016675, including two INR21.888 conservative reservations without provider usage. Combined accounted spend is INR314.494575; those reservations are not confirmed provider charges. No ledger or failed attempt was reset to reduce the displayed spending.

The repaired run took longer than the earlier 217.624-second validation failure. It completed successfully, but this verification does not establish a faster end-to-end result. High-reasoning provider calls still take minutes. Background continuation, bounded concurrency, fewer checkpoints and enforced structured responses are delivered separately from an unproved latency improvement.

Source and image references were committed to the private Shivak11 repository. Docker Desktop was stopped after building. A local port 8768 listener and Chrome for Testing processes belonged to another active project and were left alone. No task browser or preview process was started during this repair. Detailed verification remains in ignored `var/timeout-20261021/`.

## Resource and knowledge scope

The work used the existing Python/OpenRouter transport, Google AI Studio Gemini 3.7 Flash high endpoint, Cloudflare Containers/R2, cf 1.0.0-beta.20 for inspection, pinned Wrangler 4.151.1 and Docker for building. Bundled Python ran regressions; Node ran the existing Worker/UI checks. Google structured-output documentation explained provider complexity limits. These are observed uses; no substitute or general necessity claim is inferred.

The existing wiki consultation was read-only. The no-update admission gate remains terminal: technical findings stay in this project record, with no wiki Markdown, tracking or QMD changes. No new professional preference record or skill observation was created from these task-specific requests.

## Follow-up checkpoint failure

The owner's later upload, job `8688a69784df47058753d7fe015d6e6a`, failed after 152.805 seconds. Inventory succeeded in 113.615 seconds with INR6.139575 provider-reported cost. The next reservation checkpoint raised `Cloud state could not be saved`; the comparison request was never sent. Its INR21.888 pending reservation remains conservatively accounted, so the displayed INR28.027575 is not a confirmed provider bill. No original attempt or reservation was edited.

The subsequent failure-record checkpoint succeeded. The current private archive contains 41,841,075 compressed bytes, 53,351,928 expanded bytes and 474 files, below every configured storage bound. The original implementation discarded the underlying storage exception, so its exact HTTP/network cause is unavailable. This is a storage-write failure, not evidence of another Gemini response/schema failure.

The repair prepares one snapshot and retries only its identical PUT bytes after transient HTTP408/429/500/502/503/504 or network errors, at most three attempts. Socket timeouts are at most 15 seconds and no more than the remaining 30-second retry budget after snapshot preparation; one/two-second backoffs count toward the budget. GET/restore retains its existing timeout. Permanent HTTP errors, snapshot limits and invalid configuration do not trigger retries. Socket timeouts are per blocking operation; the budget governs attempts and backoff, not an independently timed cancellation of a live socket operation.

A typed storage error now gives the public result an accurate save-failure message. Private diagnostics retain only an HTTP code or exception class. Required durability, shared state locking, model-call pacing, schema/evidence checks and spending caps remain unchanged. The recovery never resends a paid model request.

Independent review cycle three found that reusing the old 90-second timeout for three writes could block status reads for about 273 seconds. The resulting remediation introduced the shorter retry budget. A fake-clock regression verifies exhausted attempts receive 15 and 14 seconds, with one second of backoff. Twenty-four focused tests passed, including storage recovery before exactly one paid call, permanent-error stops, pending-reservation preservation, accurate error classification and background admission. No fourth automated review cycle was run.

Before deployment, 28 saved attempts and 47 media records were verified idle and complete. SQLite integrity and settled costs plus pending reservations matched INR298.505475. Checkpoint SHA256: `1890ed6d867aa5d910c3786fcc2c0e1fed38aebdc12458597fe049831994bf45`.

The storage repair is deployed in Worker `17fc20ec-9e66-450a-b4b5-9afec498ece5` with image `sha256:846e83ebe138e182cfd974657b34e729b24aba55e323389677a5ac50dbe55822`. The subsequent verification did not complete. Job `952b4d27153641279db852dcafbd0b0d` was accepted in 5.572 seconds and later became interrupted. Its saved inventory call succeeded in 134.980 seconds with INR6.889575 cost. Its checkpoint contains no error file, no comparison call and an empty pending-request file. No deployment or explicit restart was issued after this retry was created. The cf instance readback confirms the expected image but supplies no interruption cause; do not attribute the interruption to a particular local defect without evidence. Further paid tests were stopped.

The final allowance readback at 10:21:35 UTC confirms 29 saved attempts, zero active jobs, INR305.39505 accounted and INR194.60495 remaining under INR500. Local no-image diagnostic accounting remains INR44.016675, giving INR150.588275 combined remaining. These figures include conservative amounts without provider usage; they describe the demo allowance, not an independently verified OpenRouter wallet balance.

## Owner-requested independent breaker audit

After three automated repair review-fix cycles, the owner explicitly requested a thorough breaker audit. SHVA's `break-the-service` procedure was applied to a local copy only, with invented photos/catalogue data, fake provider/storage and an external-socket guard. This was report-only; no production probes, real credentials, paid calls or product fixes were performed by the breaker. Its cost was INR0.

The independent audit covers 18 scenarios repeated twice. Root reran all 36, reproduced the three queue/worker findings and encountered a burst connection reset. Ten targeted six-submission burst iterations then produced four transport failures. The retained failures are not represented as passing tests. The standalone report-only harness is excluded from ordinary unit-test discovery by its filename; it remains directly runnable.

Four findings remain open: BRK-001 (High), failed upload/retry persistence followed by a repeated request can acknowledge a queued job with no queue entry; BRK-002 (High), persistent final save failures can terminate both workers; BRK-003 (Medium), a claim-write failure can remove a worker and drop its popped queue entry; BRK-004 (Medium locally), six simultaneous submissions can lose a connection. The local burst finding does not establish Cloudflare gateway behaviour. These findings do not establish the cause of the separate live interruption.

See `docs/breaker-audit-20261021.md`, `docs/breaker-findings-20261021.md` and `tests/breaker_audit_20261021.py`. Queue reconciliation, safe worker recovery and runtime interruption diagnosis remain required work. The MVP is not verified reliable. No fourth automatic repair cycle was run; the requested audit provides evidence for the next implementation decision.

The new resource used was SHVA's installed `break-the-service` skill, whose role was report-only adversarial testing; evidence is the local 18-scenario/targeted-burst harness and retained receipts. No substitute or general necessity claim is inferred. Findings stay in project records because wiki authority remains read-only, with no wiki or QMD changes. These task-specific defects add no new professional-preference interpretation or installed-skill observation.
