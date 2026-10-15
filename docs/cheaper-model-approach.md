# Cheaper models and a second visual check

Shiva asked to replace Argon with a cheaper model, inspect OpenRouter's VLMs and consider whether two models could improve accuracy. This note records the proposed step-4 experiment. It does not authorise additional step-4 API calls.

## Current run
The active step-3 baseline is Qwen3.7 Flash on OpenRouter. It uses the same 58 source-labelled photos, six fixed single-image references, visual-similarity prompt, and thresholds 80 and 90. It has an INR 50 stage limit. The prior Argon run was stopped after 43 saved successful comparisons; incomplete Argon results must not be presented as a full-set accuracy benchmark or mixed into Qwen's results. Cost evidence and reserves are in out/baseline/STOPPED.json.

OpenRouter's live models API and the model pages were read on 15 October 2026. Qwen3.7 Flash accepts images and advertises USD 0.03 per million input tokens and USD 0.13 per million output tokens. Gemma 4 26B A4B accepts images and advertises USD 0.09 and USD 0.30 respectively. These are candidate prices, not evidence of Dyson recognition quality. The first Qwen request succeeded on the saved query/reference pair and returned usage.cost of USD 0.00008828. The default runner now selects Qwen and uses provider price caps; it does not fall back to another model.

Sources: https://openrouter.ai/qwen/qwen3.7-flash ; https://openrouter.ai/google/gemma-4-26b-a4b-it ; https://openrouter.ai/api/v1/models . OpenRouter reports request cost in usage.cost: https://openrouter.ai/blog/insights/cost-vs-quality-tradeoff-framework-for-agent-models/ .

## Proposed matching experiment
Keep finding each product and the Gemini Embedding 2 shortlist from the handover. Compare the matching check with Qwen alone, Gemma alone, and a two-model decision rule over the same saved crops and candidates. The telling-details variant remains a separate comparison. There is no training.

Qwen proposes a catalogue match, not in catalogue, or insufficient evidence. The second model sees the actual crop and candidate references. It should assess visible distinguishing details without receiving Qwen's confidence or justification. During evaluation, use an independent second selection so the second model can contradict the first. A second model that reads only the first model's prose does not verify the photo.

Check every proposed automatic acceptance during the experiment, including high-scoring answers. Restricting verification to low-confidence cases would leave confidently wrong answers unchecked. If the two models disagree, or the necessary feature is hidden, return not sure with the leading candidates. A targeted additional photo or a readable model identifier can provide missing evidence. Agreement between models cannot establish a feature absent from the inputs.

For photos with a known expected product, the manufacturer reference is already known. Verification should test that expected product's visible evidence and mismatch alternatives. For identification, find each product and shortlist plausible catalogue models first. Avoid adding unrelated brochure specifications that cannot be observed in a photo. The exact known-product optimisation remains a step-4 design proposal.

Measure wrong automatic acceptances, correct catalogue matches, correct non-catalogue rejections, not-sure rate, automatically resolved share and total cost per original photo. Report each model alone beside the combined rule. The combined rule may improve precision while leaving more photos unresolved; the labels determine whether it actually helps. Public review photos remain an exploratory test and do not establish accuracy on Multiplier's store photos.

## Credential handling
The environment initially lacked OpenRouter. Automatic review rejected a Bitwarden unlock, which was not retried. Shiva then explicitly authorised another project's environment as the source, excluding Rehearsal backend and mobile, and asked to save the key here. A valid key from Daily DB was saved only in the ignored primary project .env with mode 600. The worktree .env links to that file. Rehearsal backend and mobile were excluded. Keys are absent from requests' recorded bodies, Git and reports.
