# Step 2: test-photo collection

Status: collection and file checks complete. The contact sheet is ready for Shiva to inspect. Stop before baseline calls.

## Saved set
There are 58 source-labelled photos across 11 review articles: 57 single-product photos and one V12/V15 two-product photo. There is also one unlabelled display photo for a demo; it must not enter model-accuracy totals. Native image viewing excluded three of 62 downloaded candidates: P044 shows only detached accessories; P060 and P061 show shop exteriors with no discernible vacuum. WashG1 is included as the catalogue floor cleaner even though it is not a suction vacuum. Partial views and close-ups of visible machines remain in the set.

Single-product counts are V8 Absolute 6, V12 Detect Slim 6, V15 Detect 6, V16 Piston Animal 7, Big Ball 6, WashG1 7, V11 7, Gen5detect 8 and Shark Stratos 4. The V12/V15 pair adds one labelled photo with two source-named products.

The answer key is data/test/test_manifest.json. The unlabelled display is in data/test/demo_manifest.json. Exclusions are in data/test/excluded_photos.json; all presence decisions are in data/test/presence_review.json. Every row retains source_url, source_title and label_basis. Labels came from page headings and the selected image's own alt text. Model identity was not assigned by viewing the image. Source variants and model-family granularity are explicit; these labels do not establish exact regional SKU, colour or accessory-bundle identity.

The source table is data/review_photo_sources.json. Image files have neutral P-number names. Source text and labels must never be sent with query images to a matching model. The pre-existing scratch frame and frames.json were preserved and are outside this evaluated set.

## Collection route and recoveries
The prior YouTube clip route remains HTTP 403-blocked. Parallel search located original independent review photographs. Direct public-page reads worked for GeekDad, The Guardian, TechRadar, Expert Reviews, T3 and TechGearLab. Vacuum Wars and Modern Castle returned HTTP 403; alternatives supplied those models. Five original V16 images exceeded the collector's 10 MB limit; the same page's published 1200px srcset images succeeded. One exploratory Commons URL filter initially missed a URL carrying query parameters; parsing its URL path corrected it. All 62 final photo downloads succeeded.

Downloaded photo files total 52,960,393 bytes. No paid detection, embedding or matching calls were made. Search-connector billing is not exposed by these tools and is not included in a model-cost claim. API keys were not read or printed.

## Checks and evidence limit
The collector verified image decoding, dimensions, file hashes, populated source fields, HTTPS sources, unique IDs, no exact duplicate files within candidates and no exact catalogue-image duplicates. Negative checks rejected duplicate IDs, a file URL, empty label evidence and a changed file hash. Native viewing covered the candidate sheets, the five subsequently downloaded V16 photos, P057 at full reading size, the display photo and the final contact sheet.

The final sheet is out/test_contact_sheet.jpg (1800 by 2602 pixels). Its SHA-256 is recorded in out/test_set_summary.json. These public review photos cover real backgrounds, viewing angles and partial machines. They are not a measured sample of Multiplier's store-photo quality, and several images share a review source. Public-set results must be reported with this scope and rerun on client photos when available. No accuracy result is available yet.

## Scope and knowledge disposition
Only numbered step 2 was completed. Baseline, detection, embeddings, model comparisons, telling-details evaluation and the accuracy report remain pending. This collection used an existing review-photo fallback and standard file checks; no new reusable skill finding was logged. Findings belong in this project note. The wiki owner adapter requires an explicit capture request, which is absent; no wiki, wiki tracking or QMD state was changed.
