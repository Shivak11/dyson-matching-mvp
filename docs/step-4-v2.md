# Gemini evidence workflow: final results on 58 photos

All 58 photos completed on 16 October 2026 using Gemini 3.7 Flash at high reasoning through OpenRouter. The revised workflow does not improve the result on the original common test set. Keep the earlier workflow and these results for comparison; this revision does not meet the requested high accuracy.

## Accuracy

The main population contains 57 source-labelled single-family photos. P059 contains a source-labelled V12/V15 pair and is scored separately by identity set.

| Result on 57 single-family photos | Count |
| --- | ---: |
| Correct catalogue match | 28 |
| Correct rejection of a non-catalogue product | 9 |
| Total correct | 37 (64.9%) |
| Wrong accepted catalogue match | 2 |
| Wrong rejection of a catalogue product | 3 |
| Total confidently wrong | 5 |
| Not sure | 15 (26.3%) |

All five wrong answers have model-reported confidence of 95/100. That confidence is not a calibrated probability. There are 30 accepted matches, of which 28 are correct, giving 93.3% accepted-match precision at 52.6% acceptance coverage. Including outside-catalogue decisions, 42 of 57 photos receive a resolved answer and 37 of those answers are correct. These coverage figures do not remove unresolved photos from the 64.9% overall score.

| Source family | Photos | Correct | Confidently wrong | Not sure |
| --- | ---: | ---: | ---: | ---: |
| V8 | 6 | 6 | 0 | 0 |
| V12 | 6 | 5 | 0 | 1 |
| V15 | 6 | 4 | 1 | 1 |
| V16 | 7 | 4 | 3 | 0 |
| Big Ball | 6 | 2 | 1 | 3 |
| WashG1 | 7 | 7 | 0 | 0 |
| V11, outside catalogue | 7 | 2 | 0 | 5 |
| Gen5detect, outside catalogue | 8 | 3 | 0 | 5 |
| Shark, outside catalogue | 4 | 4 | 0 | 0 |

P059 correctly returns both V12 and V15. The answer key provides the identity set, not per-box product labels, so this does not establish identity-to-box accuracy. Counting this successful pair as one whole-photo success gives 38 successful photos out of 58; the main single-family metric remains 37/57.

## Comparison with the earlier Gemini workflow

| Same 15 single-family photos | Correct | Confidently wrong | Not sure |
| --- | ---: | ---: | ---: |
| Earlier Gemini 3.7 Flash high | 11 (73.3%) | 1 | 3 |
| Revised Gemini evidence workflow | 10 (66.7%) | 2 | 3 |

Both workflows correctly return the V12/V15 identity set in P059. The revised workflow fixes P006, which was previously a false outside-catalogue rejection. It changes previously correct P013 to V12 instead of V15 and P025 to outside the catalogue instead of V16. The old Gemini run did not cover all 58 photos, so there is no earlier full-set Gemini number to compare with 37/57.

Within the revised workflow, refinement improves the initial result from 34 correct, six wrong and 17 unsure to 37 correct, five wrong and 15 unsure. It recovers P011 and P052 from unresolved answers and P035 from a wrong answer. No photo moves to a worse scoring category after refinement in this saved run. Thirty-four photos receive refinement. This measured benefit within the new workflow does not establish that the complete revision beats the earlier workflow.

## What changed

The workflow first records physical machines, accessories and visible details without selecting a product. It groups clear accessories with their parent machine, retains independent partial machines and returns a separate decision for each machine. Saved Gemini Embedding 2 rankings from overlapping earlier crops supply the first three candidates; no new embedding calls or training are used.

Matching sees crops from original pixels and a manufacturer reference pack containing images, visible features, supported variants and limits of shared attachments. Uncertain, rejected, conflicting or non-first-ranked answers receive original-image detail checks against all six catalogue families and V11, Gen5detect and Shark references. Integer confidence uses a 0..100 scale, with 90 as the acceptance threshold. The expected-product helper treats a supplied model as a verification hypothesis, but this paid benchmark tests unknown-product identification only.

The manufacturer evidence and source records are in docs/reference-evidence-v2.md. Source labels and query source metadata are excluded from inference prompts. Old inputs, labels, configurations, results and charges remain unchanged. Current combined results and detections are in out/pipeline_v2_full/; the final combined scoreboard and receipt are in out/pipeline_v2_recovery/. Earlier phase scoreboards and stop receipts remain as their historical snapshots.

## The five confidently wrong answers

| Photo | Source label | Revised answer | Confidence |
| --- | --- | --- | ---: |
| P013 | V15 | V12 | 95 |
| P022 | V16 | Outside catalogue | 95 |
| P023 | V16 | V12 | 95 |
| P025 | V16 | Outside catalogue | 95 |
| P030 | Big Ball | Outside catalogue | 95 |

Native inspection of the saved images and supplied references found a false comparison in P022: the final answer claims that the V16 reference lacks a rear button, although the supplied manufacturer image shows one above its display. P013's top two embedding scores are only 0.0015415 apart, but the rank-one V12 answer at 95 bypasses refinement. P031 still has an unresolved grouping result despite a visible partial Big Ball body and a separate tool. These are observed errors, not proof that a particular untested prompt or model combination will fix them. No labels or predictions were edited to improve the score.

## Cost and rate limits

| Accounting item | Amount |
| --- | ---: |
| Corrected full run, including its failures and reserves | INR 302.31 |
| Corrected full run per original photo, 58 photos | INR 5.21 |
| Corrected run plus reused detection and embedding work, per photo | INR 5.36 |
| Separate initial technical preflight | INR 1.90 |
| Revision including technical preflight | INR 304.21 |
| All seven step-4 ledgers, including earlier model work | INR 547.01 |
| Conservative step-4 budget guard | INR 574.84 of INR 600 |
| Remaining allowance under the guard | INR 25.16 |
| Overall guard including the prior baseline stage | INR 617.52 of INR 2,000 |

Reporting uses the preserved INR 95.15703439035285/USD rate. Budget admission uses INR 100/USD. Unknown-usage failed attempts retain their full cost reservations; these amounts are accounting reserves, not confirmed provider bills. The corrected run totals USD3.17693925. Its per-photo cost counts all 58 original photos and includes additional observations, matching, refinements, the truncated response and unresolved historical rate-limit cost reserves. Shared old detection and embedding work is shown separately to avoid charging it twice. The earlier Gemini comparison cost INR 1.38/photo including its old failure reserve, or INR 0.89/photo without that reserve.

The run uses one request at a time, at least 15 seconds after each response, and recorded HTTP429 retries after 60, 120 and 240 seconds with jitter and bounded Retry-After. The measured minimum response-to-next-request gap is 15.000837 seconds. Five Vertex Flex rate-limit attempts are preserved. After settling that phase, a recorded manual change selects the same advertised Gemini model on OpenRouter's google-ai-studio standard route. There is no automatic provider fallback. All new Gemini calls use OpenRouter; the saved records distinguish the Flex and standard phases.

## Failures and recovery

The first P001 technical preflight identified V8 but returned confidence as 0.95 because the prompt omitted percentage units. Its three original calls, outputs and costs remain in out/pipeline_v2/. They are not rescaled. The corrected protocol requires integer 0..100.

After 49 photos completed, P051's standard-route identify response exhausted its 16,384 output-token limit. Its incomplete JSON is not accepted, and its USD0.06693675 charge remains recorded. A separately frozen recovery restarts only the nine unfinished photos with the same model, high reasoning, prompts and reference images, and a 32,768 output-token cap.

P051 then returned complete JSON but included a known non-catalogue identifier in an unresolved advisory top-two list. The bounded offline repair removes only that unsupplied advisory ID, retains it as an unverified alternative and leaves the substantive answer unchanged. It adds no charge. A subsequent cached-replay mismatch was traced to object-key ordering inside the prompt JSON; replay now preserves the original provider order after verifying equal JSON content. No successful request was repeated to resolve that mismatch.

P058's five-object refinement reported 37,957 input tokens, above the frozen estimate of 28,000. The complete response cost USD0.05000775, below its USD0.14388 reservation. An exact-job offline recovery verifies unchanged JSON, all five object decisions, usage arithmetic, monetary limits, frozen inputs and original-response hashes. It retains the original error and charge and appends one zero-cost success record. The remaining P059 calls then complete normally. Both offline repair receipts and all original errors are retained in out/pipeline_v2_recovery/.

## Verification and remaining work

All 136 offline tests pass. The independent strict audit passes with all 58 photos complete, no pending requests, all 441 frozen file hashes unchanged, no duplicate physical paid jobs, all seven ledgers counted once, and 153 corrected-phase request hashes reconstructed. It independently checks saved raw observations and decisions, both offline recoveries, confidence gates, per-photo aggregation, rate-limit delays and costs. The final audit source, JSON result, test log and verification receipt are in out/pipeline_v2_recovery/.

These public review photos were used during development; they are not a fresh client-store holdout. Source evidence names product families, with no exhaustive instance-level labels for every background object. No real additional photos of the same physical machine were supplied, so completion after a retake request remains untested. The known-product helper has offline tests but no paid live evaluation. The local upload screen and one-page client HTML report remain pending. This benchmark is complete; it does not establish that the requested high store-photo accuracy has been reached.
