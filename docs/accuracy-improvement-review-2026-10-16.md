# Improving correct answers and reducing unresolved photos

Status: proposed revision, supported by an error audit and an offline policy replay. No product code, frozen benchmark result, source label or model request was changed. No paid model call was made for this review.

## What the four Gemini cases show

| Case | Saved result and inspected input | Engineering response |
|---|---|---|
| P031, source-labelled Big Ball | Gemini correctly identified the visible canister at confidence 98. The detector also returned an upholstery tool as a separate part-only object. Its unresolved answer prevented the photo from resolving. | Detect physical machines separately from accessories. Associate connected components where visible, and do not treat a detached accessory as an independently unidentified vacuum when a machine body is present. Preserve every independent machine in a multi-product scene. |
| P006, source-labelled V8 Absolute | V8 is already the highest embedding candidate. Gemini rejected it using a claimed absence of a release lever; native viewing shows a red lever. This is a visual-evidence error, not a retrieval miss. | Verify the claimed contradictory feature on a targeted crop before rejecting the family. Ask for target observations before supplying candidate comparison claims, and compare the relevant reference detail. |
| P012, source-labelled V12 Detect Slim | The photo mainly shows a hair-screw accessory and a small portion of the connected housing. The motor, controls and main body are outside the frame. The correct family is absent from the top-three shortlist. | Broaden candidates, inspect any usable detail, and use validated manufacturer accessory compatibility only if it can distinguish families. A missing main-body view may require one additional photo. |
| P018, source-labelled V15 Detect | The photo shows a cleaner head on a rug, with the identifying main body outside the frame. V15 is supplied to the model, but that does not supply visual identity evidence. | Inspect the complete original frame before requesting another image. If the family cannot be distinguished from the visible head, request a main-body photo. Do not force an identity from the source label. |

The answer key remains source-derived. Native viewing was used to inspect visible features and framing, not to assign a new model label. A source can identify the equipment used in a review even where a particular photograph does not show enough of it for independent identification.

## Offline grouping-policy replay

The proposed general rule removes part_only detections only when the same photo also contains at least one whole_machine or main_body detection. It retains all photos, all body detections and every part-only photo. Applied read-only to the existing detection records, this affects accessory boxes in P031, P037, P057 and P058. Every unchanged and changed output was compared on the full saved population for the reported models.

On the fixed 15 single-family photos, Gemini changes from 11 correct, one confidently wrong and three unresolved to 12 correct, one confidently wrong and two unresolved. P031 is the only changed photo-level answer. Sol High does not change. The completed cheaper Qwen visual run changes from 30 to 31 correct out of 57, with its 20 confidently wrong decisions unchanged; its detail-note run changes from 26 to 27 correct, with 12 confidently wrong unchanged. These are counterfactual policy results from saved answers, not a new inference benchmark. The original scoreboard stays frozen.

## Recommended revision

Keep Gemini 3.7 Flash High as the primary model. Replace universal two-model agreement with a short sequence that obtains and checks specific evidence.

1. Find each physical machine and record accessory/body relationships. Do not let an unrelated accessory invalidate a resolved machine. Keep unknown independent machines visible in the output.
2. Extract target observations before family selection: body layout, controls, release mechanism, display, readable model text and which regions are actually visible. Distinguish absent from hidden. Keep these observations tied to image regions.
3. Use a manufacturer reference record for each family, with complementary angles, close-ups, brochure-backed visible distinctions, known variants and source-backed lookalikes. Invisible specifications do not establish image identity. Add separate manufacturer references for V11, Gen5detect and Shark as non-catalogue comparisons; do not use test photos as references.
4. Use the expected-product input when available, while still checking for contradictory evidence. For identification, embeddings rank candidates. With only six catalogue families, a rejection or unresolved shortlist should trigger checking the remaining families rather than treating top three as a complete catalogue. This is a proposed change to the frozen top-three experiment, not an applied change.
5. On an unresolved answer, a catalogue rejection or disagreement between retrieval and the claimed visual evidence, crop the relevant part from the original-resolution image. Compare it with the corresponding manufacturer detail. The same model can perform this check. Sol may inspect a disputed cue, but should not veto every Gemini answer through an unconditional identity vote. A self-reported high confidence is not a reason to skip checking a contradiction.
6. Read a visible product/model identifier where available and reconcile it with the image and catalogue. Nearby shelf text must be associated with the correct physical object. A preselected product or neighbouring label is context, not proof.
7. If the original photo lacks the distinguishing evidence after that inspection, request one specific follow-up view, such as the motor, bin and controls. Give a framing instruction before the first photo where practical. Measure successful completion after that additional photo separately from first-photo accuracy.

This revision targets two different outcomes: recovering correct answers from usable existing pixels and obtaining the missing evidence where the original frame is inadequate. It preserves no training, source-backed labels, non-catalogue decisions and visible error counts.

## Research supporting the mechanisms

[Swiggy's June 2026 engineering article](https://medium.com/swiggy-bytes/building-production-scale-visual-ai-for-claims-and-returns-at-swiggy-instamart-a0918a0abf28) separates verification tasks, emphasises observable product design, uses deterministic aggregation and requests specific new photos when needed. Its reported RQC result concerns real-photo return verification, not our catalogue identification task. Its automated prompt optimisation is not part of this proposed no-training experiment.

[Zoom-Refine](https://arxiv.org/abs/2506.01663) describes a training-free sequence in which a model locates a relevant region, receives the crop from the high-resolution original and revisits its answer with global context. Its reported benchmarks concern high-resolution multimodal questions, not Dyson recognition.

[R2P](https://arxiv.org/abs/2503.18623) describes training-free reference retrieval followed by attribute verification and pairwise comparison when evidence conflicts. It supports checking specific visible attributes rather than treating an unrestricted model vote as independent evidence.

[Google's product-search guidance](https://docs.cloud.google.com/vision/product-search/docs/general-tips) recommends varied reference orientations and explains that product size and clarity matter. Its reference-count guidance is for that service, not an accuracy guarantee for this pipeline. [Gemini's media-resolution guidance](https://ai.google.dev/gemini-api/docs/media-resolution) distinguishes image-detail processing from reasoning settings. Cropping should preserve real pixels; upscaling cannot recover an absent or unreadable identifier.

## How to test the revision

Preserve the existing comparison. Run the revised workflow on all 58 development photos, including the original 15 difficult/comparison cases and the labelled two-family scene. Include V11, Gen5detect and Shark; do not remove difficult images to improve the rate. Report correct decisions, wrong decisions, confidently wrong decisions, unresolved cases, first-photo completion, completion after one requested photo and cost per original photo. Break out expected-product verification from unknown-product identification; the completed benchmark tested identification.

A newly requested photo must have source-backed identity and must depict the same physical product. Do not fabricate a follow-up image or pair an arbitrary manufacturer's image with a test query. New labelled store photos, when available, should remain an untouched test before the final client claim. The current development set cannot establish store accuracy or a guaranteed improvement from this proposal.

No new calls are authorised by this document itself. The existing stage and total ceilings remain unchanged. The known-product live check, browser upload screen and client HTML report remain separate unfinished work.
