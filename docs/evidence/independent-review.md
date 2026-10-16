Degraded: single-context review (one reviewer assigned both assessments).

## 1. identity

Intent: /Users/shivakakkar/Python Projects/Multiplier-dyson/app/.engineering/super-outer/intent/local-app.md, version 1. Design package: .engineering/super-outer/design/local-app/v1, version 1. Manifest SHA-256: c247bec7f016f41e2c957446d98f009ab6e44d681b5fa3d1466e1097cb097fa1, verified with shasum -a 256. All 12 recorded frame hashes match; no newer package directory exists.

Route: http://127.0.0.1:8768/ and /report. Revision: fe7ba160f4b6dd1d6ce29e65c3f4f4f638cb09a9, following initial 72d0d9e5796fd3833a7de43ad5d1b112c61d5cf5. Environment: existing local single-user server, SQLite read with mode=ro, actual completed OpenRouter job ledgers. Target: Chromium through agent-browser, light theme, 1440×1000 and 390×844. No test account required.

Initial tracked status was clean. Final status contains orchestrator changes to docs/local-app-verification.md and untracked docs/evidence/. This reviewer made no repository or database writes. Builder/orchestrator messages were present; their success claims were not used as evidence. The named source files, current pixels, read-only API, SQLite and raw call records were inspected independently.

## 2. method

Rendered review with agent-browser in isolated session dyson-independent-review. Both assessments assigned; design assessment recorded in design-assessment-A.md and mechanical assessment in mechanical-assessment-B.md. No Run, Save or Retry action, POST, paid request, service restart or installation occurred. Browser-only file selection, keyboard navigation and offline simulation were used. Browser session was closed after each review pass.

The isolated assessments and unrelated-product test adapt pbakaus/impeccable's critique method, Apache-2.0. The single reviewer context limits isolation.

## 3. journey

1. Opened the real entry route at desktop dimensions. Upload controls and stored queue were visible, with actual allowance. Evidence02-empty.png and bootstrap.json.
2. Selected existing P059 locally. Original image preview appeared before Run; Identify was default. Verify exposed a required expected-model select, disabling Run until V12 was selected. No new DB job appeared. Evidence03-selected.png,11-selected-narrow.png, jobs.json.
3. Opened the saved P001 Verify run. Store image, box, V8 identity, High confidence, manufacturer views, supporting details and explicit expected-V12 mismatch were shown together. Evidence01-result-desktop.png.
4. Inspected manufacturer catalogue, V8 alternate image and edit form. Six active products and three separate negative references were present. Stored text prepopulated; Escape returned without saving; keyboard focus had a visible 2px outline. Evidence06-catalogue.png,07-product-detail.png,08-add-product.png,12-keyboard-reduced-motion.png.
5. Left through History and returned to the saved result; reload reopened the selected persisted job. Both Identify and Verify jobs remained completed with charges 6.948 and 5.162775 INR. Evidence09-history.png,jobs.json,runtime-proof.json.
6. Opened Saved evaluation P059 with keyboard activation. Selecting machine2 changed the V15 model, manufacturer reference and selected box. Narrow layout retained controls and images. Evidence14-evaluation-keyboard.png,15-evaluation-second-machine.png,10-result-narrow.png.
7. Opened /report. Selecting Confidently wrong displayed exactly P013,P022,P023,P025,P030 and hid53 other cards. No script security error occurred. Evidence16-report-narrow-filter.png,17-report-desktop-filter.png.
8. Browser-only offline mode showed a concrete connection error while preserving History. Restoring the connection cleared it. Evidence18-offline.png.
9. Found and rechecked narrow table overflow. After the committed fix all three table views stay 390px wide. Internal evaluation scrolling reaches 165px while document scrollX stays 0. Evidence 21–24.

## 4. intent_claims

- PASS: store photograph remains the main object, with manufacturer comparison and visible written confidence/evidence; desktop and narrow result frames.
- PASS: immediate preview, Identify default, required expected model for Verify, and explicit unpaid-to-paid action boundary before Run; selected frames and unchanged two-job database.
- PASS: saved results contain distinct physical-machine boxes and accessible native selection; P059 second-object selection.
- PASS: actual catalogue contains six starting products, source links, image views and stored manufacturer details, with three negative-reference families separated; catalogue API and rendered screens.
- PASS: existing Identify and Verify results, costs and snapshots are persisted; both raw completed provider outputs independently reconstructed through current validators/display projection exactly equal SQLite matches. Both per-job request gaps exceed 15 seconds (15.009726 and15.005729); no inflight reservations remain. Evidence runtime-proof.json.
- PASS: historical 58-photo results and original/recovery counts remain distinct from live uploads; evaluation.json and report.
- PASS: keyboard navigation, visible focus, form cancellation, narrow result/preview use and connection-error recovery on observed paths.
- PASS after recheck: tables scroll within their own containers without page-wide horizontal movement.
- UNPROVED: a newly submitted upload progressing through queued/running to completion in this independent review; no paid Run was permitted.
- UNPROVED: actual catalogue Save and deliberate paid Retry, validation errors after those submissions, and server-restart interruption interaction; read-only assignment excluded those actions. Existing source guards and stored records were inspected, but these are not interaction proof.
- UNPROVED: live outside-catalogue or insufficient-evidence results on newly uploaded photos; historical versions were available, with no fresh paid rerun.

## 5. frame_comparisons

Package frames are under .engineering/super-outer/design/local-app/v1/frames/.

-01-result-desktop: built01-result-desktop.png preserves photo-dominant split comparison, reference, model selector, written confidence and evidence placement. Actual V8/Verify content replaces simulated two-object data, allowed by manifest simulations.
-02-empty: built02-empty.png preserves upload-centred workspace and persistent queue.
-03-selected: built03-selected.png preserves original preview and explicit Run controls; five-photo strip implements API batch support.
-04-running: no matching live state was operated; UNPROVED.
-05-error:18-offline.png demonstrates actual connection failure, but is not paid-worker failure/retry proof; that comparison remains UNPROVED.
-06-catalogue: built06-catalogue.png preserves six-row reference table and Add product placement. Columns now show actual manufacturer/PDF status from API; no hierarchy/action contradiction. Separate negative references follow API contract.
-07-product-detail: built07-product-detail.png preserves image/detail split with secondary manufacturer source and material editing.
-08-add-product: built08-add-product.png preserves labelled fields, image/PDF inputs and Save/Cancel placement.
-09-history: built09-history.png preserves saved-row table with actual timestamps, states, costs and Open run.
-10-result-narrow: built10-result-narrow.png preserves stacked photo/reference/evidence and native object selector, with actual saved evaluation content.
-11-selected-narrow: built11-selected-narrow.png preserves stacked preview and labelled run controls.
-12-keyboard-reduced-motion: built12-keyboard-reduced-motion.png has visible focus under reduced motion. No animated paid-running state was operated.

Required removal of the prototype simulation strip follows states.md. Added Saved evaluation/report navigation follows the recorded plan/API. No unresolved observed hierarchy or action-placement contradiction.

## 6. mechanical_findings

M1, resolved at fe7ba16: History initially had document.scrollWidth 572 at 390px; absolute screen-reader-only Action heading escaped table clipping, allowing document scrollX182. Catalogue also overflowed. states.md explicitly requires table-only scrolling. The shared position:relative containment fix was verified from committed source and rendered independently on History, Catalogue and Saved evaluation: all document widths 390, internal scrolling preserved, accessible Action heading retained. Evidence 19–24.

No other substantive observed defect. Controls remain reachable by keyboard; native selects group six expected models and report's five filter choices; written confidence and evidence remain present independently of colour. Real store/manufacturer imagery and per-machine evidence make the principal screen specific to product matching. No interaction pass was inferred from screenshots alone.

## 7. evidence_files

All evidence files are outside the repository under /tmp/dyson-app-independent-review/:
- 01-result-desktop.png
- 02-empty.png
- 03-selected.png
- 06-catalogue.png
- 07-product-detail.png
- 08-add-product.png
- 09-history.png
- 10-result-narrow.png
- 11-selected-narrow.png
- 12-keyboard-reduced-motion.png
- 13-evaluation-desktop.png
- 14-evaluation-keyboard.png
- 15-evaluation-second-machine.png
- 16-report-narrow-filter.png
- 17-report-desktop-filter.png
- 18-offline.png
- 19-history-narrow.png
- 20-history-horizontal-overflow.png
- 21-history-narrow-fixed.png
- 22-catalogue-narrow-fixed.png
- 23-evaluation-narrow-fixed.png
- 24-evaluation-table-scroll-fixed.png
- bootstrap.json
- catalogue.json
- design-assessment-A.md
- evaluation.json
- jobs.json
- mechanical-assessment-B.md
- protocol-checkpoint.txt
- runtime-proof.json
- review.md
- summary.json


## 8. verdict

UNPROVED — Every observed path passes after the narrow-table fix, while paid submission, catalogue saving and deliberate retry remain unoperated under this read-only assignment.
