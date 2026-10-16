# Private testing API additions

Preserve existing catalogue and upload/job routes in docs/local-app-api.md. This contract supersedes that document only for the fields/routes below. Historical evaluation, /report and eval-P media are absent from the testing runtime and bootstrap. Existing research files remain outside the app.

## Completed predictions and diagnostics

Each job adds exports_available:boolean and run_details:object|null. Existing jobs may have null details until a read-only reconstruction of their own saved snapshot/ledger can establish those details; never substitute the current configuration or call a model. Pending jobs never claim completion.

Run details fields: pipeline_version:string, config_sha256:string|null, catalogue_sha256:string|null, requested_model:string|null, requested_provider:string|null, reasoning_effort:string|null, started_at:string|null, completed_at:string|null, elapsed_seconds:number|null, queued_seconds:number|null, requests:list, cost_inr:number, cost_basis:string. Request items contain only operation, status, model, provider, elapsed_seconds, cost_usd, reserved_cost_usd and cost_basis when known. Exact upstream fields are explicitly selected. Missing or unknown usage remains unknown/reserved; do not show zero as known usage. No paths, request headers, secrets, raw prompts or image bytes are exposed. Times use real recorded timestamps; no model latency is inferred from generic progress stages.

Each Match adds retake_guidance:list[string], copied from the existing model decision's retake_request (string/list as actually returned) and/or its existing missing_evidence. Do not change model prompts or thresholds to add this field. Verify continues to return confirmed/rejected/unresolved/null separately from identity status, and never treats expected_product_id as a truth label.

## Immutable exports

GET /api/jobs/<id>/export.json and GET /api/jobs/<id>/export.csv return attachment files only after a terminal prediction envelope is persisted. GET before availability returns409 with a plain error. Unknown IDs return404. Same Host/Origin/security checks as existing GET routes. No model call, rerun or recalculation from the current catalogue occurs on export.

JSON envelope: schema_version, prediction_id, saved_at, photograph:{filename,sha256}, mode, claimed_product:{id,name}|null, status, matches, run_details. Matches are a saved whitelist of public decision fields (including boxes, qualitative confidence, evidence, missing evidence, retake guidance, alternatives and verification). Reference image IDs/URLs may be omitted; image bytes and source catalogue text are not exported. Final envelope bytes are persisted once and returned unchanged on repeated downloads, catalogue edits or restart. Preserve old jobs; additive database fields only. A repaired/retried prediction is a separate record; never overwrite a sealed prediction.

CSV has one row per physical object, or one job-status row when no objects exist. Include prediction_id, filename, photograph_sha256, mode, claimed_model, job_status, object_id, box_2d, decision_status, model_family, qualitative_confidence, verification, evidence, missing_evidence, retake_guidance, elapsed_seconds, requested_model, actual_models, actual_providers, config_sha256, catalogue_sha256 and cost_inr. Multivalue fields are JSON strings. Protect spreadsheet formula cells and generate deterministic UTF-8 CSV from the sealed envelope. A content digest response header may bind each download; never hash credential values.

## Runtime isolation

The runtime uses a model-only configuration and manufacturer-only local seed prepared outside pushed source. The orchestrator's allowlist packager receives any extracted runtime dependencies from the backend worker. Backend returns the exact code/config seed contract and a list of required runtime files; the package must start and exercise fresh inference with all historical directories absent. No direct Google calls, local OCR, training, extra models or live paid calls are introduced.
