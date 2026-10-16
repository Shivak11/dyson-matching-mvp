# Local app verification

16 October 2026. Delivery is a local single-user web app and a private GitHub feature branch. No cloud deployment is claimed.

The app has a persistent SQLite catalogue, original manufacturer images and PDF storage, entered brochure details, Identify and Verify modes, saved uploads and per-machine qualitative results. Every run retains its catalogue snapshot. New model calls use Gemini 3.7 Flash high through OpenRouter with the Google AI Studio provider pinned. All candidates are compared; there is no direct Google embedding call or local OCR.

## Source and regression evidence

All 245 Python tests pass after the recorded-input geometry repair. JavaScript syntax and whitespace checks pass. Tests cover validated uploads, catalogue persistence, immutable reference snapshots, CSRF and loopback checks, idempotent submissions and retries, atomic worker claims, interrupted jobs, aggregate costs and reservations, cross-job pacing, finite coordinates, native pixel detail crops, and the shared-control V16/Gen5 ambiguity.

The historic strict audit passes with all 1,240 frozen inputs unchanged. Old benchmark accuracy and costs remain unchanged. The new web-app inference path has not received a fresh full-set accuracy evaluation.

## Browser evidence

Twenty frontend fixture checks passed before real integration. The orchestrator then opened the actual server, confirmed the six catalogue products plus three negative references, added a fourth source-backed V8 manufacturer image, saved it, and confirmed it survived reload. Identify is the default. Verify requires an expected catalogue model. A queued job survived browser reload. The result displays the actual store photograph and box beside its snapshot reference, evidence, missing detail and qualitative confidence. Individual history costs include current in-flight reservations after the final fix.

The portable report embeds all 58 photographs. Desktop 1440 by 1000 and narrow 390 by 844 were rendered. All embedded images load. Its filters show exactly five confidently wrong and 15 unsure cases. The report separates the selected recovery experiments from the complete 58-photo benchmark.

A fresh read-only reviewer independently inspected desktop and narrow screens, saved-result reconstruction, catalogue inspection, local preview, multi-machine selection, History, report filtering and browser offline/recovery. The reviewer found one narrow table overflow defect. A shared positioning fix passed independent rechecks on History, Catalogue and Saved evaluation, retaining accessible column labels. No observed defect remains. The review's overall verdict is UNPROVED because its read-only assignment prohibited fresh paid submission, saving, paid retry and restart interruption. The orchestrator separately exercised live submission and catalogue saving; offline tests cover retries and interrupted jobs. A real paid retry was not exercised. The bounded review and exact source revision are retained in docs/evidence/.

## Live OpenRouter verification

The first uploaded photo generated two complete paid responses, detection and comparison. The model returned V8, while one of three supporting detail regions extended one normalized coordinate unit outside the detected machine. Initial strict validation rejected the whole response. The original error, complete raw response and charge remain preserved.

The repair marks that detail unverified and excludes it from support. The two independently located body/bin comparisons remain valid. A recorded-input regression proves the original response is unchanged. Offline replay recovered the V8 result without another call or charge. Source labels were not used in the model prompt or gate.

A second, deliberate live run selected V12 as the expected model on the same V8 photograph. It completed normally, identified V8 with High confidence and rejected the expected V12. Both jobs remain inspectable in History. These are two workflow checks on one photograph, not a new accuracy benchmark. No further paid calls are planned.

The two jobs made four physical requests, with zero retries and zero pending requests. The minimum measured finish-to-next-start pause was 15.0057 seconds. Their total guard cost is INR 12.110775, leaving INR 87.889225 of the app's INR 100 allowance and INR 185.9209809 of the authorised stage budget. The app counts uncertain charges, uses one worker and permits bounded rate-limit retries without fallback. The original experiment budget and reserves are preserved. Sanitised response and accounting evidence is in docs/evidence/openrouter-runtime.json.

## Delivery and remaining proof

Default port 8766 was already occupied by other listeners. They were left untouched; the app uses 127.0.0.1:8768. The completed result and catalogue material survived a graceful server restart. Runtime databases, uploads, responses and keys are ignored by Git. A history scan found no actual credential values or credential patterns before the first push.

The private repository is Shivak11/dyson-matching-mvp, branch codex/local-app. Delivery uses that feature branch and checks its remote commit against the local commit. The global JaipuriaAI account was left unchanged; push credentials were explicitly scoped to Shivak11. Source main was not merged or rewritten.

Owner acceptance, client-store holdout accuracy, cloud deployment and remote CI are unproved. The delivered scope is local. Original uploaded brochure PDFs are stored without extraction; entered brochure text is used for matching.

## Knowledge disposition and resources

This implementation depends on the existing pipeline_api transport and evidence validators, Python SQLite and HTTP server, Pillow image handling, OpenRouter Gemini, the two requested design skills, Super-outer, and agent-browser rendering. Their concrete uses are recorded above and in the committed plan. Tool availability alone is not treated as use. The engineering and recovery findings remain project records.

The wiki-update owner adapter requires an explicit capture request. None was made, so the admission gate is NO_UPDATE: no vault page, tracking file, maintenance contract or QMD state was opened or changed. No new general skill observation was logged; these findings are project-specific and the existing runtime-proof principle already applies.
