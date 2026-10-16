# Focused recovery preflight, 16 October 2026

The implementation is committed and its203 offline tests pass. The frozen experiment selects14 remaining failure cases and3 controls. The first live request, v4:predicates:P030, returned HTTP200 with length/MAX_TOKENS. It used16,377 completion tokens, including11,091 reasoning tokens, and cost USD0.07347975. No new photo decision completed. No Sol or Mistral OCR request ran, no retry occurred and no request remains pending.

The seven-question, up-to-three-reference checklist exceeded the16,384-token output allowance at high reasoning. Its partial JSON is excluded from validation and scoring. The original response, cost, frozen inputs and failed receipt remain in out/focused_recovery/. The partial audit has one expected unresolved-terminal-error failure; all1,218 frozen hashes and prior strict audits still pass.

New reporting cost is INR6.9921155. Stage guard spending is INR785.1389111, leaving INR214.8610889 of INR1,000. The prior complete round remains six recoveries, one confidently wrong and13 unsure among20 failures, with two correct controls and P019 unsure. No new full58 score is established.

The next engineering change to the visual experiment would reduce the checklist to the actual disputed features and avoid repeating the full feature/reference matrix. It has not been implemented or paid-tested.

Shiva subsequently directed a separate targeted OCR step on P054 and the13 unsure photos. It does not resume the failed visual checklist or add spending allowance. Its plan is docs/plan-targeted-ocr.md.
