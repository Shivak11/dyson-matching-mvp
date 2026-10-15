# Dyson matching MVP: step 2

## Confirmed scope
Collect 30–60 independently sourced real-world photos covering the six catalogue families and V11, Gen5detect and Shark Stratos. Preserve the existing catalogue and scratch-frame files. Every retained photo needs source_url, source_title and source-derived label_basis. Do not label products visually. Inspect vacuum or floor-cleaner presence with native image viewing, record exclusions and show the test contact sheet, then stop before baseline calls. Keep total downloaded images below 100 MB. No training. No paid matching calls in this step.

## Implementation
Use independent reviewer-original photographs when YouTube media requests return HTTP 403. Keep source model variants explicit. Save original image bytes and source groups. A small standard-library collector and Pillow contact-sheet routine are sufficient. The orchestrator owns all files; no concurrent builder is assigned. Work in the dedicated step-2 worktree.

## Verification
Check every retained file, dimensions, SHA-256, source fields, label coverage, exact duplicates against catalogue and test set, and total bytes from disk. Keep source evidence outside model image inputs. Review the rendered sheets natively. Keep multi-product store scenes separate when item labels are unavailable. Do not claim store-photo accuracy from review photographs.

## Current client decisions
Both expected-model verification and catalogue identification are required later. Compare Gemini 4 Argon, GPT-5.5 and GPT-6.1 Sol; Claude Opus is removed. API budget is INR 2,000 including reruns. Return not sure/top-two or not in catalogue where appropriate. The local upload demo and scrolling HTML accuracy report follow later numbered steps.

## Step 2 status
The reviewed photo set and contact sheet are complete. File checks passed. Shiva has not yet reviewed the delivered contact sheet. Stop before step 3. See docs/step-2-test-set.md.
