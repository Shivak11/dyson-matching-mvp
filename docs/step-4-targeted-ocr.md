# Targeted OCR results, 16 October 2026

Mistral OCR through OpenRouter completed on P054 and the 13 remaining unsure photos. No other photos or controls were tested. All 14 responses completed normally, with no 429 retries, provider fallback, duplicate requests or pending calls. The minimum response-to-request pause was15.004 seconds.

The run returned no usable model name or part code and recovered no identities. P054 yielded an image placeholder, so its Gen5/V16 confusion remains unresolved by OCR. P051 yielded generic filter and brand text. P012 yielded the fragment “UOSho”; it is not a verified identifier. Native inspection of the returned P012 image confirmed upright pixels and visible branding. Twelve responses contain only file, image or empty table markup. This does not prove that those original photos have no readable text; this document-OCR route generally retained the photograph as an image block.

| Photo | Extracted content after removing transport markup | Model or part identifier | Result |
|---|---|---|---|
| P054 | File, image or empty table markup only | None | No identity recovered |
| P012 | UOSho | None | No identity recovered |
| P018 | File, image or empty table markup only | None | No identity recovered |
| P028 | File, image or empty table markup only | None | No identity recovered |
| P029 | File, image or empty table markup only | None | No identity recovered |
| P030 | File, image or empty table markup only | None | No identity recovered |
| P040 | File, image or empty table markup only | None | No identity recovered |
| P043 | File, image or empty table markup only | None | No identity recovered |
| P045 | File, image or empty table markup only | None | No identity recovered |
| P046 | File, image or empty table markup only | None | No identity recovered |
| P048 | File, image or empty table markup only | None | No identity recovered |
| P049 | File, image or empty table markup only | None | No identity recovered |
| P050 | File, image or empty table markup only | None | No identity recovered |
| P051 | WASHABLE HEPA FILTER / dyson | None | No identity recovered |

The raw annotations are preserved. The original raw summary counts14 nonempty text blocks because its text field includes transport markup. interpretation.json and the independent audit distinguish the 2 photos with content from those wrappers. No source label or prior matching result changed.

OpenRouter reported USD 0.02829333 for the 14 requests: INR 2.69 total, or INR 0.19 per photo at the recorded reporting rate. An additional USD 0.14 parser-fee reserve remains in the budget records. With that reserve, new accounted cost is INR 16.01 at the reporting rate, or INR 16.83 under the INR 100/USD guard. Total stage guard spending is INR 801.97, leaving INR 198.03 of the authorised INR 1,000. Overall guard spending is INR 844.65 of INR 2,000. The earlier failed Gemini preflight remains charged and unchanged.

All 210 offline tests pass. The strict independent audit reconstructs all 14 requests, original-pixel crops, one-page PDFs and server annotations, verifies all 1,240 frozen hashes and all 11 ledger totals, and retains the earlier completed and stopped audit states separately. The saved PDF wrapper performs no local text extraction. The Qwen response used to obtain the file-parser annotations is excluded from OCR evidence.

The last complete matching round remains six correct recoveries, one confidently wrong and 13 unsure among the 20 earlier failures, with two correct controls and P019 unsure. This OCR step adds no matching recovery. The focused Gemini visual preflight is still stopped; its seven-question/reference checklist needs to be reduced before another visual experiment. No new58-photo matching score is established.

Evidence is in out/targeted_ocr/independent_audit.json, interpretation.json and verification_receipt.json. The edge cases and the assessment using no additional photographs are recorded in docs/edge-case-register.md and docs/no-additional-photo-assessment.md.
