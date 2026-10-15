# Step 4: bundled matching experiment

Status: implementation and live preflights completed; full comparisons are running. This document is not a final accuracy result.

The approved stage ceiling is INR 400, within INR 2,000 overall. Previous spend and unknown-usage reserves total INR 42.68. The guard uses INR 100 per USD; reporting uses the frozen baseline exchange rate of 95.15703439035285. Configuration and all requests are saved under out/pipeline/.

The shared pipeline uses Gemini 3.8 Flash to locate each cleaner, 6% crop padding, original scene context, 18 selected manufacturer reference views and one Gemini Embedding 2 vector per image. Each crop retrieves three product families by its best matching reference view. The checker sees the crop, scene and two references for each candidate. Qwen3.7 Flash and Gemma 4 26B A4B run independently, with and without manufacturer-reference detail notes. Their agreement rule is evaluated from saved answers. Automatic catalogue matches require confidence at least 90 and consistent candidate decisions. Confidence is not a measured probability.

The owner additionally requested higher Gemini models. Gemini 4 Argon is scheduled across the full set, subject to the shared cap. Gemini 3.1 Pro Preview, GPT-5.5 and GPT-6.1 Sol use the same fixed 16-photo subset and the telling-details bundle. The subset rule is the first and last single photo for each catalogue family, the first V11, Gen5detect and Shark photo, and the source-labelled pair. This rule was saved before new comparison results. Direct model rankings must use the same subset.

A local photo can be passed with --photo PATH --run. --expected-product CATALOGUE_ID ensures that product is supplied even if retrieval omitted it. Upload results stay outside benchmark accuracy. The browser upload screen and client HTML report belong to the remaining delivery work.

## Preflight repair and review

Gemma returned top_two:null with a not_in_catalogue decision on P001. The batch stopped and retained the original response, cost and validation failure. A local parser repair accepts an empty alternatives list for this outside-catalogue answer. An explicit offline validation recovery reused the same saved response and added a zero-cost audit event. No model request was repeated, and Gemma's answer and confidence were unchanged. This repair changed no prompt, source label, reference or confidence threshold.

Fresh read-only code review found three issues: conflicting candidate checks could pass as resolved, missing crop results could make a photo appear complete, and an expected-product input was absent. These were repaired with regression tests. The orchestrator reran all 44 tests successfully from the worktree. Recorded detection IDs now govern completeness. A photo with an unchecked detected object stays unresolved; source labels never enter model requests.

## Detection and retrieval inspection

Gemini located 65 objects across all 58 photos, with no empty detections. Native review of all four saved detection sheets found cleaner-containing crops, but the detector sometimes split connected or detached components: P031 includes a canister and wand/head separately; P037 includes a detached tank; P057 includes an additional part; P058 includes several views/background objects. These are retained, with no manually corrected boxes. The source identifies the reviewed product family and does not supply identities for every background object. Do not claim per-instance identity accuracy on these photos. P059 has two source-labelled families but no source-backed identity-to-position mapping, so score only its photo identity set.

At photo level, both/source catalogue labels occur in the union of top-three crop shortlists for 37 of 39 catalogue photos. P012 and P035 miss the source-labelled product. This is retrieval recall on the development set, not matching accuracy. The two misses remain in the evaluation denominator.

All public review photos have already been exposed in the baseline and error review. They support a development comparison. Client store-photo performance and retake success are not yet measured.
