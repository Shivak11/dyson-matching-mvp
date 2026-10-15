# Whole-photo similarity baseline

Qwen3.7 Flash completed 348 successful comparisons: 58 labelled photos against one fixed reference image for each of six catalogue products. The model, prompt, images, references and thresholds were frozen before scoring. There were no Qwen request failures or reruns. The first successful preflight comparison is included in the 348 calls.

The client exact Gemini model and prompt were unavailable. Shiva replaced Argon with a cheaper model during this run. These results therefore describe a reconstructed whole-photo similarity method on Qwen; they are not a measurement of the client application. No detection, embedding shortlist, telling-details prompt or second model was used.

## Single-product photos

These results cover 57 photos: 38 catalogue products and 19 non-catalogue products. The two-product photo is reported separately.

| Result | Threshold 80 | Threshold 90 |
|---|---:|---:|
| Correct decisions | 25 | 23 |
| Correct catalogue matches, out of 38 | 18 | 12 |
| Correct non-catalogue rejections, out of 19 | 7 | 11 |
| Wrong matches accepted | 16 | 12 |
| Wrong matches with score at least 90 | 12 | 12 |
| Not sure | 8 | 5 |
| Not in catalogue | 15 | 28 |

Overall correct decisions were 25/57 (43.9%) at threshold 80 and 23/57 (40.4%) at threshold 90. At 90, 12 of 24 accepted matches were wrong. The 12 confidently wrong answers are accepted wrong model choices with similarity score at least 90. Similarity is not a calibrated probability.

A unique highest score at or above the threshold returns a match. An exact highest-score tie returns not sure with two guesses. If every score is below the threshold, the baseline returns not in catalogue. This rule misclassified 8 catalogue photos as not in catalogue at threshold 80 and 17 at threshold 90. The tie policy is a declared reconstruction assumption; the client tie policy was not supplied.

At threshold 90, six V11 photos were accepted as V8 Absolute, two V12 photos as V15 Detect, two Gen5detect photos as V8 Absolute, one V12 photo as V8 Absolute and one Big Ball photo as V8 Absolute. Source variants and model-family label scope are retained in the answer key.

## Known-model verification

The same scores also evaluate whether a proposed catalogue identity is accepted. All 348 image/reference pairs contain 40 source-positive pairs and 308 source-negative pairs, including two positives in the multi-product photo. This exhaustive pair set is not a forecast of the client positive/negative workload mix.

| Pair decision | Threshold 80 | Threshold 90 |
|---|---:|---:|
| Correct expected identities accepted, out of 40 | 28 | 17 |
| Wrong expected identities accepted, out of 308 | 33 | 17 |
| Correct expected identities rejected, out of 40 | 12 | 23 |
| Wrong expected identities rejected, out of 308 | 275 | 291 |

## Two-product photo

P059 contains a source-labelled V12 and V15. Both received 85. At threshold 80 the baseline returned not sure with V12 and V15. At threshold 90 it returned not in catalogue. It did not locate or return separate product instances.

## Cost

OpenRouter reported USD 0.03054383 for the complete Qwen run. At the ECB reference rate of INR 95.157034 per USD, dated 2026-10-14, this is INR 2.91 total and INR 0.0501 per original photo, including all six comparisons. Mean cost per individual comparison was INR 0.00835. The stage ceiling was INR 50.

The earlier Argon run was stopped on Shiva's instruction after 43 saved comparisons. Returned token usage implies INR 22.51 at the published rates. Up to two in-flight requests and the earlier rejected format request have no returned usage; INR 17.27 remains reserved for them. Combined recorded model cost is INR 25.41; including the reserve, INR 42.68 is accounted against the INR 2,000 total ceiling. Native Gemini amounts are token-based estimates, and OpenRouter amounts use returned request costs; this is not invoice verification.

Cost sources: https://openrouter.ai/qwen/qwen3.7-flash ; https://openrouter.ai/blog/insights/cost-vs-quality-tradeoff-framework-for-agent-models/ ; https://ai.google.dev/gemini-api/docs/pricing ; https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml .

## Evidence and next step

out/baseline-qwen/calls.jsonl preserves each response text, score, requested/returned model, provider, usage, reported cost, timing and request digest. scores.csv and scores.json contain the complete score matrix. summary.json contains all per-photo decisions. independent_checks.json verifies 348 unique successful comparisons, raw output/parsed-score consistency, CSV values, independent threshold counts and provider cost totals. Ten offline checks passed before the live run. Prepared-image proportions and hashes were checked for all 64 query/reference inputs. The key is in the ignored project .env with mode 600 and was checked absent from tracked files; no key value is recorded here.

The set contains public review photographs from 11 source groups, including partial views and close-ups. Several photos share a reviewer and setting. Labels cover model families with source variants preserved. These results do not establish exact regional SKU identity or accuracy on Multiplier store photos.

Step 3 is complete. Stop before step 4. The proposed next experiment is in docs/cheaper-model-approach.md: locate each product, preserve the embedding-shortlist experiment, compare each cheap checker alone with a second visual check, and measure wrong automatic matches alongside the not-sure rate and cost. The claim that two models improve accuracy remains untested.

Technical findings and the cost correction are saved in this project. The wiki owner adapter requires an explicit capture request; none was given. No wiki, wiki tracking or QMD state was changed. No new skill observation was logged because the run used existing output-validation, budget and source-verification guidance.
