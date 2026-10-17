# Store-photo and owner-review checks

17 October 2026. All ten noisy store photos now have a completed result. IMG_001 required the validation fix and one deliberate retry; IMG_002 and IMG_003 had already completed on the preceding deployment. The six additional owner-review frames produced four correct identifications and two uncertain results, with zero confidently wrong answers and no technical failures. The separate blind scoring key was not opened.

## New review frames

| Frame | Source label | Result | Confidence | Seconds | INR |
|---|---|---|---|---:|---:|
| U001 | V8 Absolute family | correct | High | 126.67 | 5.15 |
| U002 | V8 Absolute family | correct | High | 207.18 | 9.82 |
| U003 | V12 Detect Slim | correct | High | 317.40 | 15.93 |
| U004 | V12 Detect Slim | correct | High | 110.70 | 3.99 |
| U005 | V15 Detect | uncertain | Low | 171.01 | 7.36 |
| U006 | V15 Detect | uncertain | Low | 226.86 | 10.76 |

These six frames come from three videos, with two frames per video. They cost INR53.01 in total. Their labels come from source titles and owner narration. Titles, URLs, label basis and actual player timestamps are retained in the source manifest; those labels were excluded from inference inputs. One buffering candidate was discarded because no vacuum was visible. The source screenshots were captured in Dia and cropped to the observed video content without adding noise or enhancing features.

U005 shows the particle-count display but hides the handle and upper power controls. U006 shows the trigger and side body but not an active display or readable model label. Both are from the V15 review. Their separate evidence is recorded for a possible future combined-view test; no combined-view recovery was run or claimed.

## Noisy store photos

The latest ten runs contain eleven accepted product identities, one uncertain machine and three photographs with no detected vacuum. IMG_006 confirmed the selected V8 expectation; IMG_007 rejected the selected V12 expectation and identified V8. IMG_009 contains two accepted identities and one uncertain machine. These are completion and output counts, not accuracy scores, because the independent answer key remains unopened.

The latest ten runs cost INR49.93. The original failed IMG_001 run remains saved separately with INR3.91 charged; its deliberate post-fix retry is included in the completed ten. All sixteen latest runs completed without another technical failure.

## Fixes and verification

IMG_001 failed because a hidden reference feature carried unused placeholder coordinates. Those coordinates are now removed without adding supporting evidence. The original failure was preserved. The saved response passed offline replay; the live retry identified WashG1 and Big Ball with High confidence. Existing visible-region and identity gates remain unchanged.

Hosted settings, jobs and JSON/CSV exports now use a public allowlist. OpenRouter calls, provider/model configuration, prompts and request ledgers remain server-side. Normal browser upload/result requests remain visible. The original detailed records remain private and unchanged. The GitHub destination Shivak11/dyson-matching-mvp was verified private.

The focused validator checks, hosted privacy HTTP check, JavaScript syntax check and run-details reservation-label self-check passed. Browser work covered selection, disabled saving controls, queued/running, no-vacuum, multi-machine selection, confirmed expectation, rejected expectation, uncertain result, original failure, retry and downloads. No full 58-photo rerun or production load test was performed.

The CSV contains the sixteen latest runs plus the separately marked original failure, including mode, selected expectation and verification outcome. Sanitised JSON/CSV predictions and the source manifest are also retained under docs/evidence as store-photo-review-results.json, store-photo-review-results.csv and review-video-frames.json. The ignored var/vipul-ui-review directory retains original screenshots, cropped test inputs, per-run downloads and review-results.zip. Old results and catalogue/settings were preserved. The new review frames, IMG_001 retry and IMG_004–IMG_010 used the deployed validation-fix image. IMG_002 and IMG_003 completed earlier. The later UI-only reservation label correction does not change these results.

## Knowledge disposition

The validation recovery, output counts and paired-view edge case are recorded in this project. The wiki consultation remains read-only, so the no-update admission gate applies: no wiki page, tracking file or QMD state was changed. No new skill observation was logged because the failures and checks are specific to this app and the relevant deployment-proof rule is already recorded in observation 226.

## Resources used

Transcript API supplied candidate videos and timed owner narration. Native Dia screenshots supplied the actual test frames. The Browser plugin operated the hosted upload/results UI. Gemini ran through the existing OpenRouter route and pacing. Cloudflare Workers, Containers and private R2 supplied the hosted application and saved state. Docker and Wrangler built and deployed it. Each use is evidenced in the retained manifests, UI captures, predictions or deployment receipt; the app’s existing provider and model were unchanged.
