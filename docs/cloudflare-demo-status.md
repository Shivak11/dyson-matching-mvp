# Cloudflare demo status

17 October 2026. The demo is deployed at https://multiplier-photo-demo.shiva-research11.workers.dev/ from the isolated `codex/cloudflare-demo` worktree. The original local app remains unchanged.

## Account and deployment

The owner explicitly confirmed `shiva.research11@gmail.com` as the intended paid account. A fresh Wrangler OAuth authorisation succeeded with Workers and Containers scopes. The earlier automatic review rejection was resolved by that explicit account confirmation before retrying.

- Account ID: `22744e58d83f933700484b130caec4fb`.
- Worker version: `17fc20ec-9e66-450a-b4b5-9afec498ece5`.
- Container application: `a03c2ba7-42f7-446a-9696-d95272efec2c`.
- Container image digest: `sha256:846e83ebe138e182cfd974657b34e729b24aba55e323389677a5ac50dbe55822`.
- Private R2 bucket: `multiplier-photo-demo-state`.
- `OPENROUTER_API_KEY`, `CLOUD_STATE_TOKEN`, `CLOUD_CONTAINER_TOKEN` and `DEMO_ACCESS_CODE` are hosted Worker secrets. Their values are excluded from source and image.
- The six-digit owner access receipt is in ignored `cloudflare/demo-access.txt`. The access value and provider keys are not committed.

## Interface and documents

The owner clarified that SHVA dashboard guidance is inspiration for hierarchy and evidence, not a request for a dashboard. This remains a photo identification application. The owner rejected the first UI. The revision uses left navigation, one upload workflow, manufacturer imagery, catalogue cards and expandable model/budget details. The eight-step tour highlights real controls with a cut-out backdrop, Next/Back/Skip, Escape and focus handling. It never starts a paid run.

The assumed dataset guide describes manufacturer references, independently labelled store evaluation photos and separate scoring of exports. Saved predictions include qualitative confidence, evidence, missing details, latency and cost.

Six official unchanged Dyson manuals were downloaded. Big Ball, V8 and WashG1 fit the existing 12 MiB attachment limit and are seeded as original PDFs. V12, V15 and V16 remain official links with page-supported facts. WashG1 has no extracted text; its attachment is not represented as parsed evidence. See `manufacturer-document-manifest.json` and `manufacturer-document-sources.md`. No accuracy improvement has been measured from these additions.

## Verification

- Five focused state-transport/checkpoint tests passed.
- Three focused catalogue seed tests passed, including original PDF preservation and path rejection.
- Worker session integrity, expiry and unauthorised API/state assertions passed.
- JavaScript syntax and Git whitespace checks passed.
- Browser inspection covered desktop and narrow layout, catalogue details and all eight tour steps.
- A fresh catalogue seed contains six active models, three outside references and three original PDFs.
- Authenticated hosted assets match the committed frontend bytes. The nine catalogue records and three hosted PDFs are accessible.
- Existing spend was carried forward without resetting any ledger. Before the final retry, INR61.14735 was spent and INR238.85265 remained in the owner-increased INR300 runtime allowance.
- The initial hosted acceptance run used frontend SHA-256 `5716ea86191be189d0a078f5d778209a851fff771425e4288292eb9da77be5b2`; the current hash is recorded in the later review section.
- Normal browser sign-in accepts the six-digit code. The login page uses `Referrer-Policy: same-origin` so its form supplies the origin required by the existing server check. Null and cross-origin submissions remain rejected.

## Hosted acceptance recovery

The first public review photo P001 reached Gemini but stopped during validation because the model returned a flat object instead of the requested nested `result` wrapper. Job `e38940a42e604b21bdae1b89557b304e` remains failed, with sealed JSON/CSV exports and INR5.534175 charged. No failed result was rewritten as successful.

A one-line parser compatibility fix accepts both layouts through the same evidence validators. The already-paid response was replayed offline and passed as a High-confidence V8 identification. Focused checks still reject fractional confidence, invalid geometry and shared controls that cannot distinguish a family. No prompts or confidence thresholds changed.

The owner then authorised another INR200. The runtime allowance is INR300 and cumulative stage ceiling INR1200; both constrain the same ledger. INR61.14735 was already spent, leaving INR238.85265 before the deliberate retry. The deliberate retry, job `1a3963acd593486d8e5a07b271600a65`, completed through the app using the existing Gemini 3.7 Flash high/OpenRouter route and 15-second pacing. It identified the Dyson V8 Absolute family with High confidence, three specific evidence statements and no recorded missing details. The run took 153.347 seconds and cost INR7.8015 across two successful provider calls. JSON and CSV were downloaded to ignored `var/cloudflare-smoke/retry-prediction.*`. Total runtime spend is INR68.94885, leaving INR231.05115. The prior failed run remains separately saved.

A real private R2 checkpoint was downloaded and restored offline. It retained all nine catalogue records, the original job and manufacturer PDFs matching their source SHA-256 hashes. A deployment restart also preserved the failed run and its costs.

## Resolved startup issues

Docker Desktop required the owner's operating-system authorisation; its engine is now ready. The confirmed account removed the earlier authentication ambiguity. Cloudflare rejects Python's default request identifier with error 1010, so the private checkpoint client now explicitly sends `User-Agent: MultiplierPhotoDemo/1.0`. No Cloudflare security setting was weakened. The first authenticated container request returned a transient startup error; a subsequent request succeeded.

Cloudflare container rollout completion lagged the CLI deployment receipt. The final image was pinned by immutable digest and verified from the actual served file after rollout `8c3c065e-eefc-4049-b16c-91b441f99930` completed. Private restart control requires the existing state bearer token and retained saved data.

## Scope

This remains one demo container with bounded private R2 checkpoints. Historical research runs, blind inputs, answer keys and past result exports were excluded from the image. The source prompts, confidence gates, catalogue families and model selection are unchanged; only the owner-authorised manufacturer facts and documents were added. No full dataset rerun or load test was performed. The existing HTTP allowance/origin/CSRF check passed after the budget update; its loopback socket needed sandbox escalation.

The wiki taste consultation was read-only. Professional interface guidance changed hierarchy, progressive disclosure and tour behaviour; no wiki page, tracking state or QMD index was modified. Contract digest read for that consultation: `4575babeb47b0d426c3bf829c8aef7131f72d7d0e05a25d02606db5861af06b2`.

## Cleanup

Docker Desktop reported stopped. Google Chrome is no longer running. The temporary worktree preview process was stopped. Unrelated applications and other project processes were preserved; the Cloudflare deployment continues independently.

## Resources used

Wrangler 4.151.1 deployed the Worker and hosted secrets; Cloudflare Containers runs the unchanged Python application, and private R2 checkpoints preserve its database, media and request ledgers. Docker Desktop built the allowlisted image locally. OpenRouter routes the Gemini 3.7 Flash high requests to Google AI Studio with the existing pacing and limits. Official Dyson original PDFs and page-supported text supply catalogue references. SHVA so-what-dashboard guidance changed the result hierarchy and progressive disclosure; the owner explicitly excluded dashboard features. CUA operated the real hosted sign-in, result state and spotlight tour. These uses are recorded here because wiki consultation was read-only.

## Sequential store-photo and owner-review checks

The ten noisy store photos now have completed results, including the explicit post-fix retry of IMG_001. IMG_002 and IMG_003 completed before that deployment. The new six source-labelled owner-review frames were captured in Dia and tested separately in Identify mode on the frozen validation-fix image. Four were identified correctly, two V15 views remained unsure, and none was confidently wrong. All six completed without a technical failure. The labels and transcript/source records were excluded from inference.

The six frames cost INR53.006925. This review, including the ten latest store runs and the preserved first failure, cost INR106.849575. Runtime spending is INR175.798425 and INR124.201575 remains under the unchanged INR300 cap. No further paid tests were started after U006. The app uses the existing Gemini 3.7 Flash high/OpenRouter route and pacing. No prompts, catalogue or thresholds changed during these tests.

The first store-photo validation bug and the hosted privacy boundaries are fixed. Hidden placeholder coordinates no longer stop a valid result or add invisible evidence. Public settings/jobs/downloads exclude private configuration and request details while preserving normal predictions, references, timing and cost. A UI-only correction distinguishes pending spent/reserved amounts from completed charges. The new image is recorded above. Authenticated live JavaScript matches the local SHA-256 27ec8833a951f45ee7b3d2b2aad511c1d0de4e91dedcfffcac07cd75b9432ea4. All nineteen saved attempts survived the idle restart, and no paid job was active.

The source manifest, per-case outcomes, costs, latency and scoped verification are in docs/store-photo-ui-review.md. Ignored var/vipul-ui-review contains the actual source screenshots, neutral test inputs, public exports, results.json, results.csv and review-results.zip. U005/U006 are retained as a possible paired-view edge case in docs/edge-case-register.md; no combined-view recovery was run. The GitHub repository was verified private before pushing.

Final cleanup: Docker Desktop is stopped, Google Chrome is not running, and neither task preview port 8768 nor 8770 has a listener. The hosted app remains open. Further Dia inspection was left alone after automatic approval review identified a possible unrelated-project window; all six requested review captures had already been saved. No further model calls were needed for deployment verification.

## Cumulative views, 17 October

The hosted Identify screen now accepts an explicitly confirmed second and third view of one product. Each new run compares all cumulative images jointly and preserves previous results. The saved U005 V15 result remained uncertain alone; U005+U006 identified V15 Detect with High confidence, and adding U007 retained the correct High-confidence V15 result. The two new checks cost INR12.778275. Runtime spending is INR188.576700, leaving INR111.423300. All nineteen original public records remain equal; twenty-one attempts are now saved, with no active jobs. The original six-image score is unchanged.

The actual hosted UI matches source SHA-256 f42cda3018b1af23c0a16e330b138af7c56ce782aa051ef82f7ba1391424e0eb. An idle process restart did not refresh the image; the private checkpoint-guarded container recreation loaded it and restored all prior records/media/ledgers. The recreation request returned a transient 503, while subsequent app readback confirmed successful restoration. No R2 or Durable Object data was deleted. See docs/multiple-views-review.md for source checks, exact grouped jobs, screenshots, exports, costs and the scoped inference result.

## Allowance increase, 21 October 2026

The owner authorised another INR200. Runtime allowance increased from INR300 to INR500; the cumulative ceiling increased from INR1200 to INR1400, preserving the historical guard and every spending ledger. Only the two budget constants and the immutable deployment image reference changed.

The hosted readback confirmed INR207.097500 spent and INR292.902500 remaining, with all 23 saved attempts and the catalogue equal before and after the idle restart. A new user run began during the initial publish and was interrupted by that rollout; the later explicit restart waited for idle state. The subsequent repair investigation established this distinction. Future rollout checks must precede publishing as well as explicit restart. The verified private checkpoint contained 23 attempts and all files for 45 media records; SQLite integrity and charged request ledgers passed. Archive SHA256: 40bcb0cba76287ef5678fe539ecad69b26b54974917eaca8d3bcbeaa8dc0b757.

Eighteen focused inference/accounting tests passed using the bundled Python runtime. The built container separately confirmed INR500/INR1400. No paid test or broad dataset rerun was started. Docker Desktop was started for the build and stopped afterwards. cf 1.0.0-beta.20 inspected the application; the existing pinned Wrangler 4.151.1 procedure built and deployed it. Evidence is in ignored var/budget-20261021/. This routine configuration amendment adds no new wiki knowledge; no wiki files or QMD state changed.

## Structured JSON and background processing repair, 21 October 2026

The failed store-photo retry used a malformed evidence-field name. The repair handles that exact alias and requests strict JSON schemas on all single-image, refinement and joint-view inference calls. Gemini receives required closed fields, types and enums; unsupported/complex bounds are retained in the original server-side schema validator. Real no-image probes established endpoint acceptance before the final photo retry.

Independent jobs can now use two background workers, with a shared budget admission lock, durable reservations, at most two provider requests in flight and 15-second launch spacing. Successful call settlement needs one fewer remote checkpoint, and gzip uses level 1. These changes preserve the current model, catalogue and evidence rules.

The affected photo completed in job `5f585828951741ebb11b834e9ff728d9`: 235.219 seconds, INR10.8813, with three saved predictions (V12 Detect Slim, V8 Absolute family and WashG1). Both provider outputs passed the original local schemas and evidence checks. This is a successful technical verification, not a labelled accuracy score or proof of reduced total latency. All 26 earlier records and the catalogue remained unchanged. Hosted spend is INR270.4779, leaving INR229.5221; separate schema diagnostics account for INR44.016675 including conservative no-usage reservations. See `docs/timeout-repair-20261021.md` for measured call times, review scope and accounting.

The deployed digest and Worker version are recorded above. The source repair passed focused tests and two independent review cycles. Docker is stopped. Wiki scope remains read-only; project findings are recorded here without wiki or QMD writes.

## Current reliability findings, 21 October 2026

The later storage-write repair adds bounded retries and correct error classification, but its new paid verification became interrupted after successful inventory. Its cause is unproved. No paid tests were started after that interruption. The demo is accessible, but background processing is not verified reliable across storage failures and restarts.

The owner's independent report-only breaker audit reproduced four open findings: two High queue/final-save recovery failures, one Medium job-claim worker-loss failure and one Medium local HTTP burst failure. Root independently reproduced the recovery defects; targeted bursts failed in four of ten iterations. The audit used no real credentials, provider requests or production mutations and cost INR0. See `docs/breaker-audit-20261021.md` and the findings ledger. These findings remain unfixed; no overall pass is claimed.

The final live allowance readback shows INR305.39505 accounted and INR194.60495 remaining, with 29 saved attempts and no active jobs. Including INR44.016675 in separately recorded local diagnostics leaves INR150.588275 in the combined allowance. Conservative reservations are included; this is not a wallet-balance statement. Further implementation requires resolving the open queue/worker recovery defects and investigating the hosted interruption. Docker remains stopped and wiki scope remains read-only.
