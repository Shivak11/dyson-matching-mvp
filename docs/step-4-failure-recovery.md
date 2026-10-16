# Aligned-reference failure experiment

The aligned-reference method correctly identifies six of the 20 previous failures. It introduces a confidently wrong Gen5detect-to-V16 answer on P054 at 95 and leaves 13 unsure. These are selected development cases; this is not a new full-set accuracy result.

| Result on the 20 failures | Raw answer | Accepted answer |
|---|---:|---:|
| Correct | 6 | 6 |
| Confidently wrong | 1 | 1 |
| Unsure | 13 | 13 |
| Not run | 0 | 0 |

Four of the five originally wrong answers are now correct: P013, P022, P023 and P025. P030 changed from wrong to unsure. Two of the 15 originally unsure answers are correct: P031 and P042. P054 changed from unsure to a wrong accepted match. All six recoveries have the exact source-labelled reference family; correct outside-catalogue rejection has not hidden a wrong family assignment.

The V8 and V15 controls, P006 and P014, remain correct. P019 is an incomplete V16 control: Gemini exhausted 32,768 output tokens. Its response and USD 0.14911875 charge remain recorded. The stopped original run has completed 22 of 23 selected photos. A separately frozen output-limit completion is being prepared; the incomplete control is not an unsure or wrong identification.

## Per-photo result

| Photo | Source family | Accepted result | Confidence |
|---|---|---|---:|
| P012 | V12 | Unsure | 50 |
| P013 | V15 | V15 | 95 |
| P018 | V15 | Unsure | 0 |
| P022 | V16 | V16 | 95 |
| P023 | V16 | V16 | 95 |
| P025 | V16 | V16 | 95 |
| P028 | Big Ball | Unsure | 0 |
| P029 | Big Ball | Unsure | 0 |
| P030 | Big Ball | Unsure | 95 |
| P031 | Big Ball | Big Ball | 95 |
| P040 | V11 | Unsure | 90 |
| P042 | V11 | V11, outside catalogue | 95 |
| P043 | V11 | Unsure | 35 |
| P045 | V11 | Unsure | 40 |
| P046 | V11 | Unsure | 0 |
| P048 | Gen5detect | Unsure | 40 |
| P049 | Gen5detect | Unsure | 95 |
| P050 | Gen5detect | Unsure | 40 |
| P051 | Gen5detect | Unsure | 65 |
| P054 | Gen5detect | V16 | 95 |

## Engineering changes and limits

Gemini 3.7 Flash high first makes a fresh inventory without earlier identities or source labels. It compares each physical machine with 25 neutral manufacturer component panels across nine reference families. The enlarged V16 control view and revised machine/accessory grouping are tested as one bundle; individual causal effects were not isolated.

The gate requires two visible diagnostic feature types, exactly one supported reference, no selected-reference conflict and confidence of at least 90. P054 demonstrates that multiple shared features can still pass that rule incorrectly when another reference lacks the corresponding view. The parser verifies declared structure and regions; it cannot prove the descriptions are true. The next handoff method must address shared features and manufacturer variants explicitly.

All ten photos classed before the run as primarily attachment-only remain unsure. The other ten cases contain usable body regions or body fragments: six are correct, one is wrong and three are unsure. This grouping is a presence/visibility observation, not a visual source of product labels.

Two complete responses, P013 and P006, failed physical-target containment. The tested offline rule marks only their out-of-target comparisons unobserved, preserves the original records and then applies the unchanged gate. Both repairs cost zero. The original charge, validation error, full comparisons and immutable repair receipts remain in the ledger and geometry_repairs directory.

## Cost and verification

The stopped phase has made 42 paid requests and costs INR 182.53 at the reporting exchange rate. This includes the incomplete control. Its conservative guard is INR 191.82. All eight stage ledgers total INR 729.53 at the reporting rate, or INR 766.66 under the guard, leaving INR 233.34 of the INR 1,000 stage ceiling. The overall ceiling remains INR 2,000; old unknown-usage reserves remain counted. The completion retry is additional and will have its own ledger.

All 166 offline tests pass. The partial audit verifies 969 unchanged input/source/reference hashes, the saved completed outputs, request reconstruction, costs and pauses. It retains a failed status because P019 is a known terminal output-limit error; it is not a completed 23-photo audit. A fresh strict audit of the preserved earlier 58-photo benchmark still passes.

The old benchmark remains 37 correct, five confidently wrong and 15 unsure on 57 singles, plus the correct V12/V15 identity set. Client-store holdout accuracy, paid expected-product verification, retake completion, the local upload screen and client HTML remain untested or pending. See edge-case-register.md for the requested case record.
