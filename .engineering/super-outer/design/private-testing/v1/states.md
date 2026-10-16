# Private testing additions

This package serves `.engineering/super-outer/intent/private-testing.md`, version 1, and the committed plan `docs/PLAN-private-testing-app.md`. It preserves the existing comparison workspace in `web/index.html`, `web/app.js` and `web/style.css`. The orchestrator authorised the standalone host mirror because this assignment cannot edit product source. This package replaces no earlier version.

## Interaction specification

Keep the existing upload queue, catalogue, comparison and object selection. Remove Saved evaluation and Accuracy report navigation. Keep the existing catalogue screens and behaviour. The prototype's fixture banner, state selector, fixture assets, fixed values and alerts are design tools only and must never enter the runtime bundle.

A completed saved result places Download JSON and Download CSV beside its saved state, above the comparison. History offers the same actions in the relevant row. Use `job.exports_available` to decide availability. A running or failed job without a sealed prediction shows a short explanation instead of download links. Terminal status alone does not establish export availability. Download actions use the existing saved record and do not run inference.

Run details uses native `details` and `summary`, initially collapsed. Show recorded elapsed and queue time, start/completion timestamps, configured model/provider, reasoning setting, pipeline version, configuration and catalogue digests, and recorded cost/basis. Show actual model and provider per request with duration and charged/reserved cost. Keep unknown charges explicitly unknown or reserved. Never turn null into a known zero or replace legacy metadata with current settings. Preserve expansion and focus during object changes and polling. Request records use a labelled, keyboard-scrollable container; the document itself must not overflow.

Retake guidance belongs to the selected physical machine, after its supporting and missing evidence. Changing the box, object button or machine select changes the reference, evidence and guidance together. The result remains available without another photograph. Render server strings as text. Use the supplied guidance or existing missing evidence, without another model request or new matching prompt.

Identify is the default. The visible explanation is: “Identify finds the catalogue model for each machine. Verify checks whether each machine matches the model you select.” Verify exposes the claimed-model control and requires a selection before Run. A Verify result retains the identity status and separately shows confirmation, rejection or unresolved verification with the claimed model. A claimed model is never an answer key.

## Connected states

| State | Starts when | Visible content | Next action and end |
| --- | --- | --- | --- |
| loading | Bootstrap is pending | Existing loading heading and busy state | Successful bootstrap shows queue/empty; error offers refresh |
| empty | No photos are queued | Upload action, supported types, one-to-five limit and mode explanation | Choose photos opens preview |
| selected | Photos are chosen or a failed run is reviewed | Saved preview, mode control, allowance and explicit Run action | Remove returns empty; Run creates a job only after validation |
| verify-selected | Verify is chosen | Claimed-model selector and mode explanation | Choosing a model enables Run; switching Identify hides the claim |
| queued | Job is saved before execution | Preserved photo and actual queued stage | Poll advances to running or terminal state |
| running | Backend reports active work | Actual stage, recorded elapsed time, preserved photo and History exit | Existing polling changes the screen on completion/failure; there is no retry action while waiting |
| long-running | Stage remains active | Same stage and increasing recorded elapsed time | History remains available; no invented percentage or automatic paid retry |
| return | History opens a nonterminal job | Current persisted stage for that job | Resume polling; do not create a replacement job |
| result | Saved prediction is available | Comparison, per-object status/evidence/guidance, exports and collapsed details | Select machine, expand details, download or upload more |
| details | Summary is activated | Recorded metadata and actual request costs | Click, Enter or Space collapses; focus stays on summary |
| not-sure | Evidence does not establish one model | Written Not sure status, missing evidence and targeted retake guidance | Inspect/download existing result or explicitly select another photo |
| outside | Decision is not in catalogue | Written Not in catalogue status and no implied matched reference | Inspect/download existing result; catalogue remains separate |
| failed | Backend reports failure | Preserved photo, error reason, review action and History | Review photo first; explicit new Run creates another record |
| history | History navigation is selected | Persisted rows with status and row-local actions | Open result/run or download available sealed prediction |
| export-unavailable | Envelope is absent or export fails | Explanation beside the relevant result/row; failed download leaves the result intact | Refresh run or retry download; never trigger inference |
| legacy-details | Saved job has null provenance | “Run details were not recorded for this run.” | Result remains inspectable; exports follow availability |
| narrow | Viewport is 390px wide | Photo, reference, evidence and details stack; row tables scroll internally | Same actions and keyboard order as desktop |
| reduced-motion | User requests reduced motion | Current state remains visible; spinner rotation stops | Polling still updates real stages |

## Keyboard and selection

Use real buttons for object boxes, native labelled selects and native summary activation. Retain visible blue focus. Buttons communicate selected state with `aria-pressed`; navigation uses `aria-current`. Keep the existing skip link and focusable main element. Do not move focus during passive polling. Announce meaningful stage completion and errors through the existing status/alert regions. No custom modal or dismissal interaction is introduced. Native selects retain their normal Escape dismissal.

## Components, tokens and assets

Reuse the existing heading, queue, toolbar, comparison, evidence, status, table and button classes. Add only the saved-action group, per-object retake section and native Run details styling. The inline prototype CSS is a snapshot of existing `web/style.css`; rebuild only the bounded additions in product source. Use its Arial/Helvetica system typography and `--paper`, `--canvas`, `--ink`, `--muted`, `--line`, `--blue`, `--bluewash`, `--green`, `--greenwash`, `--amber`, `--amberwash`, `--red`, `--radius` and `--focus` tokens. Existing app styling outranks marketing-page rules; design-taste-frontend explicitly excludes app screens.

The fixture photograph and manufacturer image are copied from the earlier design's existing local assets, without editing pixels. Boxes, identities, guidance, times, digests, providers and costs are fixed illustrative values. Their display proves layout only. No paid service was called.

## Render and wording review

Frames use native agent-browser viewport screenshots, with actual viewport/visibility readback and PNG dimensions verified. Desktop is 1440×1000; narrow is 390×844. Source images loaded, page errors were empty and document overflow was false. Native Space opens/closes Run details. Keyboard selection changes guidance; Verify disables Run until a claim is chosen; running has no export links; History returns to the same fixture job; error review retains the fixture photo. Horizontal table frames include the far-right actions/cost columns.

The wording review corrected a fixture guidance string that named the wrong selected machine. The final rendered Not sure frame names machine 1 consistently. Copy describes actions and recorded results without an accuracy claim. Design-everyday-things diagnostic: 10/10 for the five specified affordance/feedback/recovery/mapping/constraint rows in this fixture; no user-comprehension or owner-acceptance claim follows from this review.

Live upload, persistence, download bytes, provider calls and application polling were not exercised by the design prototype. The builder and independent reviewer must verify those against the actual runtime. Only the existing light theme is supported; no dark-theme design is introduced. Owner acceptance remains pending.
