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

## User cost correction and cheaper baseline
Shiva requested a lower model, said INR 600 is too costly, asked to inspect OpenRouter's VLMs and proposed exploring two models. The Argon run was stopped with 43 saved comparisons; its incomplete results remain separate. Use Qwen3.7 Flash for the complete baseline, with the same whole-photo inputs, reference images, prompt and thresholds. The new frozen config is data/baseline_qwen_config.json; results go to out/baseline-qwen/. The stage ceiling is INR 50. Previous reported cost and unknown-usage reserves count toward the INR 2,000 total.

Shiva explicitly authorised retrieving OpenRouter from another project's env, excluding Rehearsal backend/mobile, then saving it here. A valid key was obtained from Daily DB and saved only as OPENROUTER_API_KEY in the ignored primary .env, mode 600; the worktree .env links to it. No key is to enter Git, reports or logs. The denied Bitwarden unlock was not retried.

Extend the existing runner for the OpenRouter request/response format, local JSON validation, reported usage.cost and graceful stop after recording in-flight responses. Retain the native Gemini path for interpreting saved Argon records; the default paid run must now use Qwen. Orchestrator ownership extends to .gitignore, data/baseline_qwen_config.json and docs/cheaper-model-approach.md. Stop after baseline results.

The proposed step-4 study compares a cheap model alone with a second visual checker, potentially Gemma 4 26B A4B. This is a proposal, not approval to run new step-4 calls. Check every proposed automatic acceptance during that experiment, including high-scoring ones; agreement alone is not proof. Preserve no-training, embedding shortlist and insufficient-evidence decisions.

## Step 3 status
Completed the full Qwen baseline and independent score/cost verification. Results are in docs/step-3-baseline.md and out/baseline-qwen/. No further baseline API calls are required. Stop before step 4; the proposed two-model check is not yet implemented or evaluated.

## Step 4 authorised on 15 October 2026
Shiva authorised continuing and INR 300–400 for this stage, and asked to combine useful engineering changes rather than isolate each one. Cap all step-4 calls and unknown-usage reserves at INR 400, within the original INR 2,000 total; carry forward INR 42.68 prior accounted spend/reserve. No guaranteed improvement is claimed. Experimental results remain alongside the frozen baseline. No deployment or training.

Build one shared workflow: Gemini 3.8 Flash localisation, padded crops plus scene context, useful multiple manufacturer reference views, Gemini Embedding 2 top-three product retrieval, and an evidence-based exact-family decision. Test Qwen3.7 Flash and Gemma 4 26B A4B independently on identical inputs, then combine their saved decisions conservatively. Test written telling-details cards as a bundled variant. Preserve requested GPT-5.5 and GPT-6.1 Sol comparisons as bounded runs if their live cost permits; report their actual scope. Argon was removed by the user's cost correction. No automatic provider fallback or paid retry loop.

File ownership: orchestrator owns tools/run_pipeline.py, data/pipeline_config.json, data/reference_pack.json, data/telling_details.json, tests/test_pipeline.py, PLAN.md, HANDOVER.md, .gitignore, .engineering/super-outer/product-brief.md, docs/step-4-pipeline.md and out/pipeline/. Transport worker owns only tools/pipeline_api.py and tests/test_pipeline_api.py. Evaluation worker owns only tools/evaluate_pipeline.py and tests/test_evaluate_pipeline.py. All workers share the dedicated codex/pipeline-v1 worktree and must snapshot any unexpected overlapping file change at detection (copy plus git diff), then stop on that file. Orchestrator verifies files and tests from disk and commits explicit paths after auditing full status.

Data contract: pipeline results are a list of objects with image_id, instance_id, variant, model, candidates (ranked product IDs), decision (status match/not_sure/not_in_catalogue, product or null, confidence 0–100, top_two, evidence, missing_evidence, contradictions, retake), and candidate_checks (product, outcome confirmed/contradicted/insufficient_evidence, evidence). Detection-miss rows remain not_sure. Each candidate check is evaluated only when actually supplied to the model; expected-product verification must separately include the expected product if absent from retrieval. No claim that retrieval negatives were individually verified. P059 supports photo identity-set scoring only, not source-backed identity-to-box scoring. All 58 photographs are development/regression data already exposed in baseline analysis; the unlabelled store demo is excluded from accuracy.

Transport contract: Client(config, root, out), generate(job_id, model_key, prompt, images, schema=None) -> parsed JSON result; images are (label, Path) tuples; embed(job_id, path) -> vector; calls.jsonl saves request hash, response, usage, price basis, cost, latency and failure before returning. Model config contains provider, model, input_usd_per_million, output_usd_per_million, max_output_tokens, input_token_bound, optional thinking_level. Config budget contains stage_max_inr, total_max_inr, prior_accounted_inr, usd_inr=100 for guards; reporting exchange rate remains separately explicit. Call caching verifies request hash. Reserve before network; failed requests stop with recorded evidence and no automatic retry. Embedding uses one image per request and 3072 dimensions; published per-image estimate is clearly marked if token usage absent.

Verification: offline tests for crop geometry, vector similarity, parsing, conservative combination, omitted/multiple instances, scoring denominators and budget/caching/error accounting; one paid preflight per route before the full run. Freeze config before calls, retain responses and digests, run the complete appropriate test suite and independently recompute headline metrics/costs from saved records. Stop after reporting step 4, before writing the client HTML report in step 5. Local upload demo remains required for the overall delivery; stage 4 exposes a reusable runner without building new screens.
