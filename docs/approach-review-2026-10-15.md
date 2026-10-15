# Dyson matching approach review

Date: 15 October 2026

The task is paused after step 1. The project was copied to `/Users/shivakakkar/Python Projects/dyson-matching-mvp` and its 41 original files were verified against the supplied folder. No photo collection or model experiment has run.

## Confirmed scope and correction

Shiva confirmed a local upload demo, an on-screen HTML report with all test results, a decision about what the client should prototype next, and a total API ceiling of INR 2,000 including reruns. He has now replaced Claude Opus 5.5 with GPT-6.1 Sol. The comparison therefore retains Gemini 4 Argon and GPT-5.5 and uses GPT-6.1 Sol in place of Opus. Official [OpenAI model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol) supports image input; [OpenRouter lists the route](https://openrouter.ai/openai/gpt-6.1-sol) `openai/gpt-6.1-sol`. Account access has not been tested.

The remaining approach recommendations below are proposals for discussion, not implemented or approved changes to the handover.

## What the recording establishes

The native Voicenotes search and recording tool returned `binYonet`, titled “Fixing Gemini Vision product matching for Dyson retail images”, created on 15 October 2026. Its automated transcript includes these relevant passages:

- Around 04:59, the discussion distinguishes manufacturer catalogue coverage from the photography protocol available to field staff.
- Around 06:14–06:59, the team discusses specifications and product information generated through Gemini. Those outputs are not independently verified manufacturer facts.
- Around 08:08, the discussion proposes multiple reference and field views, extracting specific visible differences between similar models, and checking those differences in the query photo.
- Around 11:17, the request is for labelled examples of the correct match and confusing alternatives. Around 13:06, the discussion identifies the problem of treating a whole multi-product photo as one unit.

Speaker labels and some timestamps are imperfect. This note preserves the recording's timestamps and does not treat automatic speaker naming as independent verification. The private transcript was read through the native connector and was not sent to a public research service or another model.

## Independent research findings

[Swiggy's June 2026 engineering article](https://medium.com/swiggy-bytes/building-production-scale-visual-ai-for-claims-and-returns-at-swiggy-instamart-a0918a0abf28) describes catalogue-to-customer image verification, explicit ambiguity, task-specific model evaluation, and requests for better photos. Its wrong-item task starts with a known ordered product; that differs from identifying every unknown model in a store display. It supports visual evidence checks and task-level evaluation, without proving our proposed shortlist or Dyson accuracy. Its automated prompt optimisation is outside the present no-training scope.

[Google Product Search guidance](https://docs.cloud.google.com/vision/product-search/docs/general-tips) documents localisation followed by per-item ranking, varied reference views, and uncalibrated similarity scores across queries. Its service uses both the box and the original image context. This supports retaining the original scene as well as a crop, and measuring useful reference coverage. It does not establish that Gemini scores have a particular calibration.

[ICCV 2025 R2P](https://arxiv.org/html/2503.18623v2) is a training-free precedent for reference images plus distinctive textual attributes and direct image comparisons. It verifies attributes because generated descriptions can hallucinate details. Its recognition ablation does not establish that every additional stage improves the result. Its objects, models and benchmark differ from Dyson. The separate research note read from disk also considered MIMEX and frozen DINOv2; neither establishes exact-Dyson accuracy.

[Cat2Real](https://arxiv.org/html/2607.09888v1) contains the Gemini Embedding 2 baseline cited by the handover, alongside its trained system. The figures support investigating retrieval on noisy retail crops; they are not forecasts for appliances, an evaluation of our complete pipeline, or evidence that a top-three shortlist will preserve every correct Dyson candidate.

[TypeSafe's Jev 1.14 release](https://typesafe.ai/blog/jev-1-14), dated 14 October, and its [image documentation](https://docs.typesafe.ai/images) correct the handover's text-only assumption. Images can appear in state, instructions and choice criteria, including reference-image examples. Vision requires an explicit experimental header. [Box](https://docs.typesafe.ai/primitives/box) returns one box per question and needs Jev 1.14. Neither feature is evidence of reliable exact-product recognition. The [confidence documentation](https://docs.typesafe.ai/confidence) defines a statistic derived from answer probabilities, not independently measured Dyson correctness.

[OpenAI Decisions](https://developers.openai.com/api/docs/guides/decisions) accepts images and text for typed predicates, choices and rubric scores. The current documented model is GPT-6 Luna, separate from the requested GPT-6.1 Sol comparator. The guide requires application-labelled examples when selecting action thresholds. The API's response format does not itself prove matching quality.

## Assessment: are pictures enough?

Pictures can support an exact match only when distinguishing evidence is visible at sufficient resolution and covered by the references. More reference views can address viewpoint gaps. A second field photo can reveal a hidden feature. Neither a generated description nor another judge can recover a distinction absent from every input image.

A useful stronger comparison is the image plus a source-checked record of visible distinguishing features. Manufacturer specifications that cannot be observed in the photo cannot establish the match. A description generated from the same photo may direct attention, but it is not additional independent evidence. If the difference is an invisible internal specification or an accessory bundle outside the frame, return insufficient evidence or obtain an identifier or another view.

## Recommended experiment, pending discussion

Shiva subsequently clarified that accuracy is the primary goal and embeddings are acceptable during testing. Keep the embedding stage in the experiment. Measure its candidate recall independently from the final matching result. The all-six comparison below is an additional diagnostic control; it does not remove the prescribed embedding experiment. No numerical acceptance target has yet been agreed.

Keep the original whole-photo/single-reference method as the baseline. Its exact Gemini model, prompt and thresholds are not supplied; until obtained, label our reproduction as a reconstructed baseline.

For the six-product catalogue, add a direct comparison against all six candidates. Compare it with the prescribed embedding-top-three method over the same detected products. Report shortlist recall separately: a checker cannot select a correct candidate the shortlist removed. Preserve original scene context alongside each crop.

Compare image references alone with the same references plus sourced visible-detail cards. Keep prompts, inputs and rejection rules fixed before scoring. Use source-derived labels, keep source titles and filenames out of query prompts, avoid near-duplicate video frames, and report independent source counts. Public review photos and unlabelled store demos do not establish accuracy on the client's actual display photos.

Screen Jev 1.14 and GPT-6 Luna Decisions on a small labelled set of difficult crop/reference comparisons as optional alternative verifiers. Ask narrow observable questions: whether the distinguishing feature is visible, whether it agrees with a candidate, and whether evidence is sufficient. A judge checking only another model's prose is not an independent visual check. Model agreement is not a replacement for source labels.

Choose a runtime model from measured results. Calling every comparator and every judge for each uploaded photo is not currently justified. No model training, fine-tuning, learned calibration or automated prompt search is proposed.

## Verification and limits

Primary Swiggy, Google, R2P, Cat2Real, OpenAI and TypeSafe pages were read. The existing catalogue contact sheet was inspected with native image viewing. Some PDF and TypeSafe shortcut/Markdown URLs failed; canonical HTML pages supplied the relevant contents. Model documentation is verified; account access, route forwarding of experimental flags, actual costs, detection quality and matching accuracy remain untested.

Wiki admission is no-update: no explicit capture was requested. This research stays in project notes; the vault, its tracking files and QMD remain unchanged.

## Confirmed client workflow and collection status

On 15 October, Shiva confirmed that both expected-model verification and identification from a known catalogue occur. Manufacturer brochures and images are available to the client. Field photo quality is uncontrolled, although another photo can be requested. The test design must distinguish an identity mismatch from insufficient visible evidence. Targeted recapture remains a proposed workflow; it has not been evaluated.

Step 2 stopped at the first clip-download probe. Public video metadata was accessible; the two-second clip fix still returned HTTP 403 from the video server. See `out/step-2-collection-blocker.md`. No new test photos or accuracy measurements were produced.
