# Dyson matching MVP: step 2

## Confirmed scope
Collect 30–60 independently sourced real-world photos covering the six catalogue families and V11, Gen5detect and Shark Stratos. Preserve the existing catalogue and scratch-frame files. Every retained photo needs source_url, source_title and source-derived label_basis. Do not label products visually. Inspect vacuum or floor-cleaner presence with native image viewing, record exclusions and show the test contact sheet, then stop before baseline calls. Keep total downloaded images below 100 MB. No training. No paid matching calls in this step.

## Implementation
Use independent reviewer-original photographs when YouTube media requests return HTTP 403. Keep source model variants explicit. Save original image bytes and source groups. A small standard-library collector and Pillow contact-sheet routine are sufficient. The orchestrator owns all files; no concurrent builder is assigned. Work in the dedicated step-2 worktree.

## Verification
Check every retained file, dimensions, SHA-256, source fields, label coverage, exact duplicates against catalogue and test set, and total bytes from disk. Keep source evidence outside model image inputs. Review the rendered sheets natively. Keep multi-product store scenes separate when item labels are unavailable. Do not claim store-photo accuracy from review photographs.

## Current client decisions
Both expected-model verification and catalogue identification are required later. Compare Gemini 4 Argon, GPT-5.5 and GPT-6.1 Sol; Claude Opus is removed. API budget is INR 2,000 including reruns. Return not sure/top-two or not in catalogue where appropriate. The local upload demo and scrolling HTML accuracy report follow later numbered steps.

## Step 2 status
The reviewed photo set and contact sheet are complete. File checks passed. Shiva has not yet reviewed the delivered contact sheet. Stop before step 3. See docs/step-2-test-set.md.

## Step 3 authorised on 15 October 2026
Shiva wrote: "cool run it...." Run the baseline and stop after reporting its numbers. Use the frozen settings in data/baseline_config.json. The exact client prompt and Gemini version are unavailable, so name the result a reconstructed baseline. Use Gemini 4 Argon, whole photos, one fixed 00.png catalogue reference per product, no detection, no embeddings and no telling-details prompt. Report thresholds 80 and 90 without tuning. Similarity scores are not calibrated probabilities. Exact highest-score ties are not sure; this tie policy is an explicit reconstruction assumption.

The orchestrator owns data/baseline_config.json, tools/run_baseline.py, tests/test_baseline.py, out/baseline/, docs/step-3-baseline.md, PLAN.md and the current-status section of HANDOVER.md. No concurrent builder is assigned. Use the existing dedicated worktree on codex/baseline-v1. Preserve all source photos and answer-key records.

Save each provider response, usage, request/input digests, model version and time before continuing. Keep metadata and model labels out of requests. Track thinking tokens in output cost, reserve worst-case cost for in-flight requests and halt before exceeding INR 600 for this stage, retaining the total INR 2,000 ceiling. No automatic retries or fallback model. If blocked, save failure and cost evidence, then stop.

Verify score parsing, threshold/tie/rejection scoring, missing-result handling, cost accounting, budget stop and resumability with small offline tests from disk. Freeze config before the first generation. Count 57 single-photo results separately from the two-product scene; run all 58 photos against all six references. Save exact score tables and the multi-scene scores. Stop before step 4.

Transport preflight: the first request was rejected with HTTP 400 because the structured-output guide used application/json where the REST reference requires the APPLICATION_JSON enum. Correct only that serialization value; the frozen prompt, images, model, thinking level and scoring rules remain unchanged. Keep the rejected attempt and its unknown-usage reserve in the ledger.
