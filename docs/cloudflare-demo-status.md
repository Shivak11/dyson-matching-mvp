# Cloudflare demo status

17 October 2026. The demo is deployed at https://multiplier-photo-demo.shiva-research11.workers.dev/ from the isolated `codex/cloudflare-demo` worktree. The original local app remains unchanged.

## Account and deployment

The owner explicitly confirmed `shiva.research11@gmail.com` as the intended paid account. A fresh Wrangler OAuth authorisation succeeded with Workers and Containers scopes. The earlier automatic review rejection was resolved by that explicit account confirmation before retrying.

- Account ID: `22744e58d83f933700484b130caec4fb`.
- Worker version: `e99af30f-cc1f-4ac8-aed9-1ecac6fa45cb`.
- Container application: `a03c2ba7-42f7-446a-9696-d95272efec2c`.
- Container image digest: `sha256:b4714be57ffc4370156c6488d93ef38f6806386273faccb7fcd409c77862e86d`.
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
- The final hosted JavaScript matches the committed source SHA-256 `5716ea86191be189d0a078f5d778209a851fff771425e4288292eb9da77be5b2`.
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

The wiki taste consultation was read-only. Professional interface guidance changed hierarchy, progressive disclosure and tour behaviour; no wiki page, tracking state or QMD index was modified. Current contract digest: `4575babeb47b0d426c3bf829c8aef7131f72d7d0e05a25d02606db5861af06b2`.

## Cleanup

Docker Desktop reported stopped. Google Chrome is no longer running. The temporary worktree preview process was stopped. Unrelated applications and other project processes were preserved; the Cloudflare deployment continues independently.

## Resources used

Wrangler 4.151.1 deployed the Worker and hosted secrets; Cloudflare Containers runs the unchanged Python application, and private R2 checkpoints preserve its database, media and request ledgers. Docker Desktop built the allowlisted image locally. OpenRouter routes the Gemini 3.7 Flash high requests to Google AI Studio with the existing pacing and limits. Official Dyson original PDFs and page-supported text supply catalogue references. SHVA so-what-dashboard guidance changed the result hierarchy and progressive disclosure; the owner explicitly excluded dashboard features. CUA operated the real hosted sign-in, result state and spotlight tour. These uses are recorded here because wiki consultation was read-only.
