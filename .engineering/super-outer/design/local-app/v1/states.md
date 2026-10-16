# Local photo matching app design

Serves `.engineering/super-outer/intent/local-app.md`, version 1. Design package version 1. No previous package is replaced. The standalone prototype is design code and must not ship as the app implementation.

## Working screen

The first rendered frame is the recurring result inspection screen. At 1440 × 1000, a 248 px photo queue sits beside the working area. The store image occupies approximately three fifths of the comparison area. A manufacturer image, product name and alternate views occupy the remainder. Evidence and missing evidence appear directly below both images. The confidence label belongs to the selected physical machine, not the entire photograph. Numbered boxes, a labelled native select and two object buttons all select the same machine.

The production first visit is the empty upload state. The result screen is the primary design frame because inspection is the recurring task. There is no marketing landing page. Catalogue and history remain separate navigation destinations; preserve the current photograph when moving between them. Add a compact Saved evaluation link to `/report`, without adding another primary action or summary-card row.

## States and transitions

| State | Starts when | Visible content | Next actions | Ends when |
| --- | --- | --- | --- | --- |
| empty | No store photos have been saved | Choose photos, supported formats, clear empty area | Choose JPEG/PNG/WebP files | At least one valid file is selected |
| selected | User chooses photographs | Original preview, filename, Identify default, Verify option, model selection, explicit Run matching | Inspect, remove, choose expected model, run | User starts a job or removes the selection |
| queued | Job is saved behind the current paid request | Saved photo, Queued status and job position if known | Leave page, reopen from History | Worker starts or job becomes interrupted |
| running | Paid worker starts | Original photo, actual stage names, no invented percentage | Inspect History or another photo | Stored result or actionable failure arrives |
| result | Complete job has stored object results | Boxes, object selector, identity, qualitative confidence, evidence, missing evidence, manufacturer image, configured model | Select another machine, inspect reference views or product, upload another photo | User navigates away |
| error | Provider error or bounded retries exhausted | Concrete provider failure, preserved image and request record | Deliberate retry as a new job; review history | User explicitly starts another job |
| catalog | Catalogue navigation | Six seeded products in rows with real reference thumbnails, source and image counts | Open a product or Add product | Detail or add form opens |
| detail | User opens a manufacturer product | Images, stored manufacturer source and details, stored PDF availability | Inspect alternate view, open source, add/edit reference material | User saves, cancels or returns to catalogue |
| add | User chooses Add product | Labelled name, manufacturer, source URL, brochure text, image files, optional PDF | Validate and save; cancel | Stored product is returned or validation error appears |
| history | User opens saved jobs | Filenames, saved time, actual state, actual charge or reservation | Reopen result or interrupted job | Selected job opens |
| keyboard-reduced-motion | Keyboard use with reduced motion enabled | Visible focus ring; identical content; spinner animation removed | Tab/Shift+Tab, native select arrow keys, Enter/Space, Escape from form | Focus or navigation changes |
| narrow | Viewport below 760 px | Photo and reference stack, queue sidebar collapses, upload remains in page header, navigation stays visible | Same primary actions as desktop | Viewport changes |

Queued and running use the same status layout. Replace the current step wording from persisted API state. Do not show a step as complete unless the backend records it. Browser departure does not cancel a saved job. On return, poll the saved job and show its actual latest state. A server restart must expose interrupted jobs without silently retrying paid work.

## Result rules

Show High confidence, Moderate confidence, Low confidence, or Insufficient evidence using the API's qualitative result. Do not derive an accuracy percentage from these labels. High uses a subdued green fill; Moderate/Low uses subdued amber; Insufficient evidence uses neutral fill. Always include the written label. Keep the sentence explaining that confidence is not a measured probability.

For an outside-catalogue result, state Outside catalogue, retain the object crop/box and evidence, and omit any fictitious manufacturer match. For insufficient evidence, state Model not established and show the specific missing details and any returned alternatives. An expected-model verification result must state Matches expected model, Does not match expected model, or Cannot verify, alongside the actual evidence. Do not force a matched reference merely to fill the right column.

Boxes use the image's actual content rectangle, including letterboxing; transform stored normalized coordinates after image load and on resize. Object selectors provide keyboard access even when boxes are pointer targets. A box must not imply that accessories are separate machines. Never show sample boxes on new uploads.

## Interaction and constraints

- Selecting a file causes an immediate local preview and no paid request. Run matching is disabled until at least one valid image is ready. Reject invalid/oversized files inline with the actual backend limits and preserve the valid selection.
- Identify is the default. Verify reveals a required expected-model select. Return to Identify hides that field without changing the catalogue.
- Disable repeat Run submission while a job is being created. The backend is authoritative for the job ID and polling state. Do not use the preview timer in production.
- The original photograph remains available when a provider call fails. Retry creates a new paid job only after an explicit click; record previous charges and reservations.
- New product requires a name, source URL and valid image material according to the API contract. Form labels remain visible. Inline errors sit beside the relevant field and focus the first invalid field.
- An existing-product edit prepopulates its stored values and attaches new material to that product ID. Cancel returns without writing. The prototype add form demonstrates layout and validation; it does not implement persistence or a complete edit flow.
- Reference thumbnails change the main manufacturer image. Product/source links are secondary. External source links use a new tab and noreferrer.
- Do not place destructive deletion near Run matching. Only removing an unsubmitted local selection is shown in this MVP.
- Use a native file input, select, buttons and table semantics. Keep focus visible and at least 40 px button height. Escape dismisses the unsubmitted product form back to the catalogue.
- Display real configured model names and actual costs/reservations from the API. The prototype's Gemini Flash, ₹100 allowance, ₹1.84 history cost and timestamps are examples.

## Components and tokens

No app component or design token system existed when this package started. Use plain semantic HTML and CSS in the production stack chosen by the plan. These tokens are designer recommendations:

| Token | Value | Purpose |
| --- | --- | --- |
| --paper | #ffffff | Work surfaces |
| --canvas | #f6f6f3 | Page background |
| --ink | #20241f | Primary text |
| --muted | #686f67 | Supporting text |
| --line | #dce0d8 | Boundaries |
| --blue | #2457bc | Primary action and selection |
| --bluewash | #edf2fc | Selected machine/photo |
| --green / --greenwash | #236a43 / #edf5ee | High confidence |
| --amber / --amberwash | #8a5a12 / #fff6e6 | Moderate or low confidence |
| --red | #a13131 | Errors |
| --radius | 6px | Form controls and work panels |

Use the system Arial/Helvetica sans-serif stack. Body 14 px; metadata 12 px; primary heading 26 px desktop/23 px narrow; product heading 20 px. Main content padding 32 px desktop/16 px narrow. Comparison evidence uses columns on desktop and stacks on narrow screens. Tables scroll within their own container, never the whole page. Only light theme is supported. Reduced motion removes spinner animation; written stage feedback remains.

New components: application header/navigation, photo queue, upload preview, run controls, status panel, image comparison, object selector, confidence label, evidence list, reference viewer, catalogue table, product form, history table. CSS and structure are in prototype.html; rebuild behaviour against the shared API rather than copying simulated state.

## Provenance and simulations

Owner decisions come from the app request and the parent-confirmed interview: local SQLite, OpenRouter, Identify default plus Verify, six seeded Dyson products with adding manufacturer material, qualitative confidence, no training or native/local OCR, preserve historical evaluation. Layout, tokens, neutral type and desktop/narrow dimensions are designer recommendations. Light-only is an MVP working assumption.

The prototype uses real public test image `data/test/review_photos/P059.jpg` and existing manufacturer assets from `data/reference_pack.json`. Image source identity remains in `data/test/test_manifest.json`; the filename shop-floor-01.jpg is invented and the photo is not presented as a client store image. Example model results, boxes, confidence, evidence, jobs, history and costs are simulated. Catalogue text passages are copied from the existing `data/reference_cards_v2.json` source records. No external source or extra product claim was invented for brochure text. The design preview strip is intentionally visible and must be removed from the real app after its mocked services are replaced.

## Verification and limits

Real agent-browser frames cover nine desktop states at 1440 × 1000, result and selected states at 390 × 844, and keyboard focus with reduced motion. Measurements and prototype interaction checks are recorded in render-evidence.json. All measured screens had no page-wide horizontal overflow and all images loaded. Native required fields, Verify reveal, Escape, explicit retry, completion and second-machine selection were exercised. The simulated retry timer was initially checked too early; waiting for the result selector passed. No uncaught page error was observed.

Design of Everyday Things diagnostic: discoverability 2/2, evaluation 2/2, recovery 2/2, mapping 2/2, constraints 2/2 for the demonstrated prototype paths. This is an internal walkthrough of signifiers and state feedback, not an owner usability acceptance or runtime validation.

No live OpenRouter request, SQLite persistence, production edit flow, error response parsing or accuracy test was executed in this design assignment. Queued, outside-catalogue and insufficient-evidence outcomes are specified but have no dedicated rendered frame; the builder must implement them using the same result/status components and a later experience review must operate them.
