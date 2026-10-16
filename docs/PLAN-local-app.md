# Local Dyson matching app

Version 1, 16 October 2026. Branch: codex/local-app. Base: ff82806.

## Outcome and limits

Shiva will open a local browser, inspect manufacturer images and brochure details stored in SQLite, upload store photographs, and receive a model identity for each physical machine with qualitative confidence and visible supporting details. Both identification and expected-model verification are supported, as already requested in the interview. No training, local OCR, Apple OCR, or direct Google model calls. All new model requests go through OpenRouter. Existing benchmarks and their inputs remain byte-for-byte unchanged.

This is a local single-user MVP bound to 127.0.0.1. No cloud deployment, accounts, production infrastructure or public upload service. The GitHub destination must be a private repository owned by Shivak11. Push the feature branch without rewriting main. Manufacturer material and public test images remain separate from new user uploads. Runtime SQLite, uploads, model responses and keys are ignored by Git.

## Customer walk

| Moment | Behaviour |
| --- | --- |
| First visit | Six manufacturer products are seeded from the existing source records. Store uploads are the primary action. |
| Add reference material | Add a product with its name, manufacturer source URL, brochure details and one or more images, or add details/images to an existing product. A PDF can be stored as its original manufacturer document; no fabricated extracted text. |
| Upload | Preview JPEG/PNG/WebP images, choose Identify or an expected catalogue model, then explicitly run. No call happens on selection. |
| Wait | Persist each job before starting it. One paid worker, at least 15 seconds after a response, bounded 429 retries. Show actual stages by polling; do not invent percentage progress. |
| Inspect | Keep the original store photo beside the proposed model/reference. List each physical machine separately, with its box, evidence, missing detail and qualitative confidence. An outside-catalogue result is allowed. |
| Return | SQLite retains uploads and results. Closing the browser does not cancel the worker. Restarting the server marks interrupted jobs for review without automatically rebilling them. |
| Failure | Preserve uploads and charges, show an actionable error, allow deliberate retry as a new job. No silent provider/model fallback. |
| Review accuracy | Keep saved evaluation results distinct from live uploads. A printable accuracy page reports the historical full-set and selected-failure results separately, including confidently wrong counts and model costs. |

## Decisions

- Owner: use a local database and OpenRouter models; manufacturer images and brochure details are catalogue evidence, store images are queries.
- Owner: use design-taste-frontend and design-everyday-things. The former explicitly excludes app screens; apply its restrained visual choices and real imagery without its landing-page structure or arbitrary motion quotas.
- Owner: do not train models or use native/local OCR.
- Engineering recommendation: Python standard library HTTP server and SQLite with the existing Pillow dependency, plus plain browser JavaScript/CSS. A React build is the runner-up; it adds packaging without changing this local workflow.
- Engineering recommendation: reuse existing validated inventory/evidence rules and metered OpenRouter transport; do not launch historical experiment runners. The scout will identify the smallest reusable inference path. At six products, comparing all references is acceptable when the existing image embedding route would require a direct Google call. Record the actual runtime path without claiming new accuracy.
- Confidence is the model's qualitative evidence assessment, never an empirically calibrated probability.
- Runtime cap: at most INR 100 initially from the remaining INR 198.0317559 stage guard. Include runtime spend/reservations and old stage ledgers in the budget display; do not release unknown historical reserves. No automatic paid benchmark rerun.

## Ownership and phases

Orchestrator owns this plan, product intent, shared API contract, tests for integration, README, .gitignore, final commits, GitHub and all verification. Design agent owns only .engineering/super-outer/design/local-app/v1/. It supplies real browser frames and a standalone prototype before a UI builder starts. Scout is read-only. Backend builder owns app_server.py, webapp/__init__.py, webapp/store.py, webapp/inference.py, tests/test_webapp.py and tests/test_webapp_inference.py. Frontend builder owns web/index.html, web/app.js and web/style.css after the design package and API are pinned. No agent writes shared files, commits, pushes or makes paid calls. Stat owned files before writing; on unexpected changes, immediately copy the foreign file and git diff to /tmp/dyson-app-collisions and stop. Never revert another agent's changes.

1. Inspect reusable inference and data; render the principal screen and connected states.
2. Pin API and design; implement backend and frontend on disjoint files.
3. Orchestrator verifies disk source, offline tests, real browser upload/catalogue/history/error journeys and one tightly bounded live OpenRouter inference when the remaining budget allows. A fixture run is labelled as a test and never claimed as live inference.
4. Fresh read-only reviewer operates the built app and checks intent. Fix substantive findings, commit verified units, scan tracked history for secrets, create/use a private Shivak11 repository, push the feature branch and verify the remote commit.

## Completion evidence

Record source tests, local runtime, browser journeys, live provider inference, independent experience review, remote push and owner acceptance separately in docs/local-app-verification.md. Owner acceptance remains pending until Shiva tries or accepts the app. No deployment claim. Old accuracy figures remain old measurements; the web app itself has no fresh accuracy score.

16 October interview outcome: Shiva confirmed both Identify(default) and Verify, with six starting Dyson products and the ability to add manufacturer images and brochure details.
