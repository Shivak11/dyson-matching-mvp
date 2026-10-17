# Sequential views of one product

17 October 2026. Owner: “Yes do a minimal....like they upload 1 image then 2 and then 3 and user sees the accuracy and identification going up...only this much”. Clarification: “second and third are being treated in conjunction with first one ... three images of one product”.

## Outcome and limits

Extend the existing hosted Identify result with Add another view. The user confirms the new photo shows the same physical product, reviews the images, then deliberately runs the next check. Step 2 sends photos 1+2 together; step 3 sends all three together. Show the actual identification and qualitative confidence for each saved step. Confidence can decrease; never invent accuracy percentages or a guaranteed improvement. This is a bounded MVP extension, not a redesign. No training or new models. Preserve all old results, existing independent uploads and Verify mode.

Only completed Identify jobs containing exactly one machine can begin/continue this flow. Up to three cumulative views. One new image per step. Multiple unrelated machines in a later view must remain unresolved, without combining their features. Manufacturer catalogue snapshot is frozen across the chain. A low-quality or contradictory view can produce not_sure. Original standalone predictions must never be rewritten. No automatic camera association or same-unit detection.

## API contract

Reuse POST /api/jobs. Existing payload unchanged. For a next view add parent_job_id and same_product:true, with images containing exactly one validated new image; expected_product_id must be null/absent. Existing idempotency fingerprints include those fields. Return the normal jobs array containing one new queued child. Require completed Identify parent with exactly one result, and fewer than three views. Keep all existing readiness, spending, queue, reservation, pacing, checkpoint and privacy gates.

Grouped job fields: view_count (2 or 3), views ordered as [{view_id:"view_1",filename,image_url},...], parent_job_id and root_job_id. Internal media IDs remain private. Old jobs may omit these fields; frontend derives a one-view fallback from filename/image_url. New grouped retries retain every view and frozen catalogue. Existing single-photo retry semantics stay unchanged.

Grouped matches retain existing public fields and may add view_evidence [{view_id,feature,detail}] and view_boxes {view_1:box,...}. Each feature supporting a joint match must name an actual supplied view and have a valid visible region inside that view's detected target. Aggregate only validated features. Preserve the existing two distinct diagnostic feature types, including body/bin/identifier, candidate checks and confidence gates. No previous predicted identity, source title or answer label becomes model evidence.

Exports retain photograph for compatibility and add views/count/lineage for grouped runs. Hosted responses expose only public filenames/images/view IDs/evidence, never hashes, model/provider configuration, prompts or ledgers. Original sealed exports stay byte-identical. JSON/CSV must identify grouped runs.

## Visible flow

Keep the current product decision, qualitative confidence, evidence and side-by-side manufacturer comparison. Add a compact 1 view / 2 views / 3 views comparison showing each saved result in the current chain. Clicking a completed step opens that saved result. Add another view appears only for eligible Identify results below three views. A dedicated single-file chooser opens a preview showing existing thumbnails plus the new photo, a required same-product confirmation, Cancel and Identify using 2/3 views. Disable mutation while saving; preserve selection/request ID on errors. Queued/running states show the view count and prior completed outcomes. On completion retain all photos with an accessible view selector; boxes correspond to the selected view. Third view has no further add action. Generic Upload more continues independent matching.

## Ownership and sequencing

Root owns this plan, design intent/evidence, integration, Cloudflare config, deploy, source verification, bounded real calls, reporting and commits. Design prototyper owns only ignored var/multiple-views-design plus a short docs/multiple-views-design.md package; produce the main result, add-view preview and running/completed states using the existing design before frontend implementation.

Backend builder owns app_server.py, webapp/store.py, webapp/inference.py, webapp/predictions.py, optional webapp/multiview.py and tests/test_multiview.py only. Frontend builder owns web/app.js, web/index.html, web/style.css and optional tests/test_multiview_ui.cjs only. Shared API contract above is reserved to root; changes require acknowledgement before write. No builder deploys, commits, reads keys or runs paid calls. Workers are not alone: preserve others' changes. At unexpected mtime advance, immediately copy the foreign file and save git diff to ignored scratch before any overwrite; stop that file and report.

## Verification and completion

Focused offline tests: immutable 1→2→3 chain; fourth-view/Verify/invalid parent/duplicate/mixed-machine rejection; idempotency; grouped retries and sealed exports; actual joint request includes all views with neutral labels and unchanged model/budget/pacing; per-view feature/region and conflict validation; hosted privacy projections and grouped JSON/CSV. Run existing directly affected app/inference/privacy tests, JS syntax and a compact UI state check. No full 58-photo rerun or broad production testing.

Operate real hosted UI through first result, second-view selection, confirmation, saving, queued/running, completed confidence progression and third-view limit. Use existing U005/U006 source-labelled V15 frames and at most one additional distinct frame of that same reviewer machine for the third-view check. Keep labels out of inference. Prefer existing saved photo1 result over rerunning it. Reconcile hosted spending before any paid call, stop within existing remaining allowance and retain 15-second request pauses. Freeze this new variant separately; original 4/6 results remain unchanged. Deploy only when no paid job is active. Verify actual served UI bytes and state persistence; retain previous Worker/image for rollback. Use existing authorised private Cloudflare demo and Shivak11 feature branch; no Vercel migration.

Super-outer: FOCUSED bounded shared change. CLI is unavailable; apply evidence-based module guidance. No judgement call remains because the owner explicitly chose cumulative same-product uploads and an MVP scope. UI and AI modules apply. Completion means an invited user can add view2 and view3 and see real joint identifications on the existing hosted app. Owner acceptance remains separate from our runtime proof.

## Delivery recovery

The uploaded image contains the verified source, but three Worker publishes and an idle process-signal restart still serve the preceding frontend hash. Cloudflare reports the new application image and completed rollouts; those control-plane receipts do not prove the served application. The existing private restart control only calls stop(SIGKILL). Root will change that control to destroy the ephemeral container only after the existing private R2 checkpoint is present and non-empty, then restore through the unchanged startup path. Same singleton, namespace, bucket, authentication and secrets. Verify no active paid job before invoking; preserve checkpoint and all nineteen saved attempts. No R2 or Durable Object data deletion. This is a bounded delivery repair, not a new architecture. Official references: https://developers.cloudflare.com/containers/configuration/rollouts/ and https://developers.cloudflare.com/containers/api/durable-object-container/ .
