# Frontend implementation

Preserve the current layout and tokens. Implement only these additions in the frontend-owned files:

- Remove historical evaluation/report navigation and its client rendering paths.
- Render JSON/CSV attachment links above an available saved result and in its History row. Gate with `job.exports_available`; use GET `/api/jobs/<id>/export.json` and `/api/jobs/<id>/export.csv`. Unavailable or failed downloads preserve the result and explain the next action.
- Render `job.run_details` in native `details`/`summary`. Map fields exactly from `docs/private-testing-api.md`; include elapsed time, pipeline/config identity, requested model/provider, and per-request actual model/provider/duration/charged/reserved records. Null is unknown. Preserve focus and expansion across updates; contain table scrolling.
- Render the selected Match's `retake_guidance` string list after its evidence. Keep all existing match/status/verification logic and thresholds unchanged.
- Add the two plain Identify/Verify sentences from states.md beside the existing mode control. Require a claimed model before Verify. Keep verification separate from identity status.
- Keep existing polling, upload preview, allowance and explicit Run. Errors retain photos and require an explicit new run; do not add paid retries.

Use frames 01–03 for result hierarchy/details, 07/23 for History exports, 09/18/24 for Verify, and 10–15/22 for narrow and error states. Do not copy the fixture banner, state selector, fixture names/results, alerts, fixed metadata, render scripts or any package assets into product code or the deployment bundle. Reuse current manufacturer references at runtime. The design prototype owns no API.

Verify keyboard summary activation, object selection, native selects, focus retention, 390px page overflow, contained table scrolling, null legacy metadata, all export-availability states, and the actual download files. The fixture does not prove those runtime behaviours.
