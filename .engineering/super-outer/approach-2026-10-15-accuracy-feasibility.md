# Approach: test how engineering changes Dyson matching accuracy

Date: 2026-10-15
Depth: QUICK, returned by the installed Super-outer 5.16.3 local router; the engineering-approach stage is also explicitly requested by Shiva.
Runnable: true for the repository; this deliverable is an engineering assessment, with no matcher implementation or paid inference.
Objective: choose the smallest training-free experiment that can show whether the MVP makes fewer wrong automatic matches at useful coverage and cost.
Status: proposal for review. No measured improvement is claimed.

## See
Read the saved baseline responses, source labels and existing product brief; inspect the actual photos behind important errors; compare the proposed experiment against primary technical sources. The existing medium is a terminal evaluation with saved images and results. A local upload screen and the HTML report are later deliverables. The inventory found Python code and test files but did not discover their commands; the recorded baseline command is `python3 -m unittest discover -s tests -p 'test_baseline.py'`.

Protected files: data/catalog/, data/test/, data/baseline_config.json, data/baseline_qwen_config.json, tests/test_baseline.py, tools/run_baseline.py, out/baseline/, out/baseline-qwen/, the existing product brief and recorded owner decisions. No source label, baseline score or paid-run setting changes in this assessment.
Assumption encoded: source identity and visible identification evidence are different things; a source-labelled photo can contain too little visual information to support an exact match.

## Stop
Machine: compare every numerical claim with saved results, verify the proposed scope against the owner decisions, run `git diff --check`, and obtain one fresh read-only review of this document. Allow one repair pass and finish within this turn; no token limit was specified. No paid calls occur in this review.
User: Shiva reads the recommendation and the boundaries before a revised matching experiment is built. This is the original step-3-to-step-4 boundary, with an engineering review added at his request.

## Shape
One author produces this assessment; one fresh reviewer checks the document against the requirements and evidence without receiving the author's reasoning. Detection, retrieval and visual comparison must be evaluated in sequence because failures in earlier stages constrain later stages. More model agents are an experimental treatment, not the default implementation.

## Confirmed requirements

- The client will choose an approach and model to prototype; the deliverable remains a local upload demo and one HTML report with all test results.
- Support both a known expected model and identification from the catalogue.
- No training, fine-tuning, learned calibration or automated prompt search. New products are added through reference material.
- Retain product localisation, the Gemini Embedding 2 experiment, multiple catalogue images, the telling-details comparison and explicit not-sure/top-two and not-in-catalogue outcomes.
- Accuracy is the priority. The user has not specified a numerical production acceptance target or a minimum automatically resolved share.
- Total API ceiling remains INR 2,000 including reruns. Shiva rejected the INR 600 Argon baseline budget and requested cheaper OpenRouter vision models.
- Qwen3.7 Flash completed the baseline. GPT-5.5 and GPT-6.1 Sol remain requested comparators; the cheap-first proposal below does not silently cancel them. Opus stays removed. Jev and Decisions remain possible alternatives under discussion.
- The already recorded interview settles this assessment's scope; no additional product judgement is required to produce it.

## What the current evidence establishes

The Qwen baseline made 348 comparisons over 58 labelled photos and six single-image references. Among 57 single-product photos, 25 decisions were correct at threshold 80 and 23 at threshold 90. There were 12 accepted wrong matches scoring at least 90. The complete Qwen run cost INR 2.91, approximately INR 0.05 per photo including six comparisons. These are observations about this model and reconstructed similarity method, not the client's exact Gemini implementation.

P029 is source-labelled Big Ball. Native viewing shows the floor head and a short section of its connection, without the complete machine. The response against V8 says that both pictures show the same model and assigns 95. This is evidence of an unsupported whole-model conclusion from a partial view. It does not prove that every floor-head photograph is unidentifiable, or that the same error explains every wrong answer. P009 also received inconsistent design descriptions across reference comparisons. A fluent explanation is not an independently verified observation.

The current catalogue contains 32 image files. Multiple files do not necessarily provide multiple useful whole-product angles: the material includes close-ups, accessories and lifestyle views. Audit and tag the actual files before reference selection. The existing catalogue contact sheet is an overview, not a current file inventory.

The labelled set has 11 source groups, several with multiple images of the same reviewed unit. Some model families have only one source group. All 58 photos have already been exposed to the baseline and error review. They remain a useful fixed development and regression set, but cannot now be described as an untouched final test set. Source labels stay unchanged, including on visually insufficient photographs.

## What can be improved, and what cannot be assumed

| Situation | Engineering response | What remains to be proved |
|---|---|---|
| Several products in one scene | Locate each product, retain scene context, and evaluate each instance | Detection may miss or merge products; the current set has only one labelled two-product scene |
| Product occupies a small part of the photo | Use a padded crop plus the original scene, preserving original pixels | Cropping can remove distinguishing parts or useful context |
| Query angle differs from the reference | Select useful manufacturer views and part close-ups | Reference coverage may still omit the necessary view |
| Two models have similar overall appearance | Compare candidates together and check sourced visible differences | Models can invent the presence of a detail; written cards need factual verification |
| A distinguishing detail is unreadable or hidden | Return not sure and name the specific missing view or identifier | Additional reasoning cannot recover evidence absent from the inputs |
| Product is outside the six-model catalogue | Preserve an explicit outside-catalogue outcome, tested on hard negatives | Low similarity or a rejected top-three list alone does not establish non-membership |
| Expected model is supplied | Verify its evidence and test plausible contradictory alternatives | The expected label is a claim to check, not proof of identity |
| Two cheap models agree | Test a separately run second visual assessment | Their errors can be correlated; agreement alone cannot establish correctness |
| Exact regional SKU differs only in an unseen bundle or internal specification | Require a visible identifier linked to the product or report insufficient evidence | These model-family labels cannot establish exact-SKU accuracy |

Manufacturer brochures provide reference facts. They only help identification when a relevant fact can be checked in the submitted photo or a new photo. A shelf card can belong to an adjacent unit; text association must be visible. AI-generated enhancement must not supply invented identity details.

## Recommended experimental design

Use a bounded Python workflow and the existing saved-file evaluation approach. A general-purpose agent framework, database, queue and autonomous debate loop add no demonstrated value to this six-product experiment.

For catalogue identification, retain the handover's localisation and embedding-top-three method. Keep the original scene alongside each crop. Compare against an all-six control: if the right candidate is absent from the top three, record a retrieval failure rather than attributing it to the checker. For expected-model verification, always include the expected model and plausible lookalikes; allow confirmed, contradicted and insufficient-evidence results.

A model's structured output should identify the candidate, the relevant visible region, observed distinguishing details, contradictions and missing evidence. Validate output IDs and coordinates in code. Unsupported or missing decisive evidence leads to not sure; a high self-reported score does not bypass the evidence requirement. This rule still depends on fallible visual observations, so it must be evaluated against source labels.

Use useful manufacturer views selected without test labels. Reference curation can use product names and manufacturer facts; query prompts must not receive test source titles, label-bearing filenames or the answer key. Do not add any test image to the reference set.

The primary candidate is a cheap visual matcher with explicit evidence checks. Start with Qwen3.7 Flash to preserve comparison with the baseline. Gemma 4 26B A4B is a candidate second checker, subject to an image-input preflight. Both make their own assessment of the same images and candidate set; the second receives neither the first answer nor its confidence or explanation. Different model families do not guarantee independent errors.

The runner-up is one better-performing low-cost visual model using the same inputs and rules. Retain the second checker only if its measured reduction in wrong automatic decisions justifies its unresolved rate, latency and cost compared with the best single model. GPT-5.5 and GPT-6.1 Sol comparisons can use identical saved inputs within the authorised total budget; their inclusion and exact cost must be visible in the run configuration.

Jev or Decisions could express narrow visual checks such as whether a required detail is visible. Their structured decision APIs do not establish superior vision or provide a ground-truth judge. Keep them optional until a specific failed check warrants a bounded comparison. Do not send the private client recording to model providers.

## Small experiment matrix

Run a small, fixed diagnostic batch first. Freeze each configuration before scoring; record changes as distinct variants. Any batch selected using known errors is development evidence.

| Comparison | Question answered |
|---|---|
| Existing similarity baseline vs exact-identity decision prompt with the same images and references | Does stating the actual task reduce unsupported matches? |
| Whole photo vs crop plus original scene, keeping the checker and references fixed | Does localisation help, or remove evidence? |
| One reference vs several useful views, keeping the task and query fixed | Does reference coverage fix viewpoint failures? |
| All six candidates vs embedding top three on identical crops | How much accuracy is lost through retrieval? |
| Images alone vs images plus source-checked telling details | Do the written distinctions help without increasing false claims? |
| Qwen alone, the second model alone, and the combined decision rule on identical inputs | Does the second check improve the useful result? |

Reuse saved stage outputs. Do not run every combination or change multiple components and then attribute the gain to one. After the diagnostic comparison, run the selected frozen variants on the complete development set. Record that choices were informed by these data. A new independent-source or client set is required before making generalisation claims; several families currently lack enough independent groups for a meaningful balanced holdout.

Manually inspected product boxes may be used only as a diagnostic control, with object identity still coming from the source. They must be clearly separated from automatic detection results. Do not exclude hard partial views from the headline end-to-end denominator. Add a visibility category to explain failures; do not alter the answer key.

## Measures and selection rule

For unknown-product identification, report correct in-catalogue identification, wrong accepted identities, correct outside-catalogue decisions, catalogue products wrongly rejected as outside, and not-sure outcomes. Report confidently wrong answers separately using the frozen definition, while showing every wrong automatic acceptance regardless of score.

Report precision among accepted catalogue identities and the share of all photos receiving a decision. Also report accuracy among all automatically resolved outcomes, including outside-catalogue decisions; an all-reject system must not look good. Show totals over every original photo, and separate per-instance outcomes for multi-product photos. A missed detection is a failure in the end-to-end result, not a missing row.

For known-model verification, report false acceptance and false rejection separately on positive and negative pairs. The exhaustive pair distribution is not the expected client workload. For detection, retrieval and checking, report their own failures; conditional checker accuracy is not overall system accuracy.

Compare methods at comparable automatically resolved shares where the data permits. A method that removes errors only by deferring nearly everything is a trade-off, not an unqualified improvement. No numerical production target is set by this document. Rank the observed precision/coverage/cost trade-offs for Shiva and the client to judge.

## Cost and stop conditions for the next paid batch

Proposed initial batch ceiling: INR 50, including localisation, embeddings, visual checks and any preflight. This is a spending cap, not a quoted cost or an accuracy promise. Confirm current routes and prices before starting. Estimate the full run from returned usage before scaling up; preserve the total INR 2,000 ceiling and all prior charges and reserves.

There is no automatic expensive fallback or repeated critique loop. Save every response and cost before continuing. A provider error, invalid output or missing usage must remain visible. Apply the existing budget-reservation mechanism and the user's instruction to record what failed, what was tried, then stop on a blocker.

Cost per photo includes shared detection and retrieval, all product instances, checks and retries. Report one-time catalogue preparation separately. Report latency and cost per correct automatic decision as well as per original photo.

## Primary evidence and its scope

- [Swiggy, 16 June 2026](https://medium.com/swiggy-bytes/building-production-scale-visual-ai-for-claims-and-returns-at-swiggy-instamart-a0918a0abf28): practitioner case supporting task-specific visual checks, ambiguity and targeted retakes. Its known-product claims/return task and self-reported performance are not a Dyson accuracy forecast.
- [Google Product Search guidance](https://docs.cloud.google.com/vision/product-search/docs/general-tips), read 15 October: official guidance supporting useful varied references and retaining scene context. Its score-calibration statements apply to that service, not directly to Qwen or Gemini-generated confidence.
- [R2P, ICCV 2025](https://arxiv.org/html/2503.18623v2), read 15 October: primary empirical precedent for training-free retrieval, distinctive attributes and visual verification. Its benchmarks do not establish this product pipeline's result.
- [Jev 1.14](https://typesafe.ai/blog/jev-1-14) and [image input](https://docs.typesafe.ai/images), reread 15 October: official experimental vision capability, with no exact-Dyson performance evidence.
- Local evidence: `out/baseline-qwen/summary.json`, `out/baseline-qwen/calls.jsonl`, `data/test/test_manifest.json`, actual catalogue files, `docs/step-3-baseline.md`, and the existing product brief. Main checkout at review start: `2dc8826`.

The previously researched provider prices are candidate-selection evidence only. Account access to Qwen is proved by the completed run. Access and behaviour of the other proposed routes remain unproved. No new model call has run for this assessment.

## Delivery boundary

The completed output of this turn is a reviewed engineering proposal, not step 4 completion. Matcher accuracy gains, detection quality, retake success, multi-product accuracy and production performance are unproved. New implementation follows the owner's review of this concrete proposal, as required by Super-outer's story-walk procedure and the task's numbered stops.
