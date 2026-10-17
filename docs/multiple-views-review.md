# Cumulative product views

The owner requested a minimal flow that adds a second and third photo to an existing identification. Each new check sends all accumulated views of the same user-confirmed physical product together. The original one-photo results remain saved. This is a new joint-view variant; it does not rewrite the earlier six-image score or establish a new dataset accuracy figure.

## What changed

A completed Identify result containing one machine offers Add another view. The user selects one image, reviews all views, confirms they show the same physical product, and deliberately starts Identify using 2 views or Identify using 3 views. The saved-result strip shows actual identification and qualitative confidence at each step. Confidence can remain unchanged or decrease. No inferred accuracy percentage appears.

Each result has its own immutable job and export, linked to its parent. The catalogue snapshot stays the same across the chain. A grouped retry retains all views. A fourth view, duplicate image, missing confirmation, Verify parent or multiple-machine parent is rejected before inference. Existing independent uploads and Verify behaviour remain available.

Both joint inventory and joint comparison receive every cumulative image as a separate neutral-labelled view. No previous predicted identity, source title or answer label is supplied as evidence. Feature regions are validated against the correct machine in their own view. The existing two-feature requirement, including body/bin/identifier evidence, still applies. The user establishes grouping; incompatible visible identifiers, bodies or controls prevent a resolved joint match.

Hosted JSON/CSV retains view count, ordered inputs, lineage and per-view evidence. Private per-input hashes are sealed separately and excluded from hosted downloads, along with the existing private model/provider/prompt/request details. Old single-photo export columns and sealed bytes remain unchanged.

## Source and focused verification

Implementation source is committed at 55ec4f7, with backend d0b7e10 and frontend 55ec4f7. The independent source reviewer compared the exact committed diff and found no actionable defect. Root ran 47 focused offline app, inference, multi-view and privacy checks, including the actual loopback HTTP route; all passed. The actual-function Node UI assertions, JavaScript syntax and whitespace checks passed.

Two existing budget tests still assumed the former INR100 allowance. Their fixtures were updated to exercise the already authorised INR300 limit; no spending limit or accounting behaviour changed.

The design package uses the existing result screen, tokens and controls. Root inspected the preview, then the live narrow-width preview at 538×668. It showed both real images, an initially unchecked same-product confirmation, a disabled paid-run button and the original Low-confidence result. The saving state disabled mutations. Queued/running retained the previous result and no speculative third-view outcome.

## Deployment recovery

Cloudflare reported the uploaded image and completed rollouts while HTTP still served the old frontend. An existing process-signal restart did not switch it. The private recovery action now recreates the ephemeral container only when a non-empty private checkpoint exists. It retains the same strong authentication, namespace, singleton and R2 key. Worker authentication, missing-checkpoint and recreation-control assertions passed.

The recreation request returned a transient 503, but subsequent direct readback served the exact new frontend hash f42cda3018b1af23c0a16e330b138af7c56ce782aa051ef82f7ba1391424e0eb. All nineteen prior attempts and INR175.798425 of prior spending were restored. A separate checkpoint read verified SQLite integrity, all nineteen attempts, all 41 media records' original/provider files, every charged job's request ledger and zero active jobs. The full archive and images were not persisted or printed during this verification. The presence check alone is not proof of checkpoint completeness; completeness was checked separately for this deployment.

Current Worker version: 265182bc-2a0f-4b90-87a4-dec5f30a1256. Container image: sha256:522cb9ad5403745c31660392e56b62fd59944509c7e3e869ebe3ee01eb98d15b. Previous image f7f5d02d555d6ccf7732478f2ad48b648673bf98156d316ed4738234db29d8e5 remains the rollback reference. No keys, access policy, model, provider, catalogue or budget settings changed.

## Live check

Reuse U005's saved one-view V15 result as the first step. Add existing U006 as the second view. The third input U007 is a distinct native screenshot from the same source review at 06:26. Source title and opening narration supply the V15 label; that source metadata stays outside inference. The images are correlated views of one machine, selected to exercise a known edge case.

| Cumulative views | Result | Confidence | Elapsed seconds | New cost INR |
|---|---|---|---:|---:|
| 1, existing U005 | Not established | Low | Existing result | 0.00 |
| 2, U005 + U006 | Dyson V15 Detect, correct | High | 161.73 | 7.20 |
| 3, U005 + U006 + U007 | Dyson V15 Detect, correct | High | 126.10 | 5.58 |

The two grouped runs cost INR12.778275 in total. Runtime spending is INR188.576700, leaving INR111.423300. Both completed without model or validation errors: four successful paid requests, with no reruns or tuning between outcomes. There are now twenty-one saved attempts and zero active/queued jobs. All nineteen original public job records compare equal to the pre-change capture.

The two-view result used the trigger and in-line bin/body from View 2 alongside the particle-count LCD from View 1. The third-view result additionally cited the trigger in View 3. Both distinguish the source-labelled V15 on this same-machine example. This is one targeted product recovery, not two independent new successes for a dataset score. The original six-image result remains 4 correct, 2 unsure, 0 confidently wrong.

The actual hosted UI was operated through selection, unchecked confirmation, disabled Run, saving, queued/running, completed results, all three image selectors and saved-step navigation back to the original Low-confidence result. The add-view action is absent at three views. Images 2 and 3 were checked after loading; both have non-zero native dimensions. The actual three-view JSON/CSV downloads passed view-count, order, lineage, identity and public-privacy assertions. At the observed 538×668 viewport the document has no horizontal overflow. The full-page result screenshot is retained in var/multiple-views/three-view-result.jpg.

Source/model labels never entered inference, and no source image or catalogue was changed to obtain these outcomes. Existing model/provider, spending caps and 15-second pacing remained unchanged.

## Resources and knowledge scope

The existing Python/SQLite app stores immutable linked runs without a database migration. Gemini 3.7 Flash high through OpenRouter/Google AI Studio performs both joint calls with the unchanged single-worker queue, 15-second pacing and spending guards. The browser plugin operates the real upload/confirmation/result controls and captured the third review frame. Cloudflare Workers, Containers and private R2 host and persist the app; Docker and Wrangler package/deploy it. The existing native image viewer verified the third screenshot contained the vacuum. Manufacturer catalogue data was reused, with no new references or documents.

Cloudflare's official rollout and lifecycle references informed the delivery diagnosis: https://developers.cloudflare.com/containers/configuration/rollouts/ and https://developers.cloudflare.com/containers/api/durable-object-container/ . These describe platform operations; the actual served-file and state checks establish this deployment's result.

Wiki consultation remains read-only under the existing no-update admission gate. Technical implementation, evidence and limitations stay in these project records; no wiki Markdown, tracking files or QMD state was changed. No new professional preference incident was captured from these task-specific instructions.

Final records are also tracked at docs/evidence/multiple-view-results.json, multiple-view-results.csv and multiple-view-third-source.json. Docker Desktop reported stopped; Chrome is not running and ports 8768/8770 have no listeners. The hosted app remains open on the final three-view result. No broad 58-photo rerun, production load test or general accuracy claim was made.
