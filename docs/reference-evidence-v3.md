# Manufacturer component references for the failure experiment

The manifest reuses 16 existing manufacturer source images to define 25 panels across nine families. All 16 sources were inspected with native image viewing before selecting the boxes. A private crop sheet was then inspected to verify the chosen regions. No test photograph is a reference. No source file was changed and no image was downloaded.

Each panel records the exact source file, source SHA-256, official image URL, normalised crop box and a generic component description. Coordinates are [ymin, xmin, ymax, xmax] on 0–1000 of the source image. Product mappings remain local metadata. Inference receives only neutral family/panel IDs, generic descriptions and the rendered pixels; no family names or catalogue membership are added to the images. Existing writing visible inside a manufacturer image remains unchanged.

| Alias | Local family mapping | Panels and purpose |
|---|---|---|
| R01 | Dyson Big Ball | R01-P1: complete machine, hose and wand; R01-P2: canister, bin and cyclone assembly; R01-P3: canister side and hose connection |
| R02 | Dyson V12 Detect Slim | R02-P1: motor, bin and handle from the side; R02-P2: upper housing and power control; R02-P3: rear display and surrounding housing |
| R03 | Dyson V15 Detect | R03-P1: motor, bin and handle from the side; R03-P2: motor and bin from the front; R03-P3: rear display and surrounding housing |
| R04 | Dyson V16 Piston Animal | R04-P1: motor, bin and handle from the side; R04-P2: rear display and controls; R04-P3: motor and bin from the front |
| R05 | Dyson V8 Absolute | R05-P1: motor, bin and handle from the side; R05-P2: handheld body, bin and controls; R05-P3: motor and bin from the front |
| R06 | Dyson WashG1 | R06-P1: complete machine from the side and front; R06-P2: lower body, tanks and cleaning head; R06-P3: handle display and controls |
| R07 | Dyson V11 | R07-P1: motor, bin and handle from the side; R07-P2: motor and bin from the front |
| R08 | Dyson Gen5detect | R08-P1: motor, bin, handle and upper wand from the side; R08-P2: motor, bin and upper wand from the front |
| R09 | Shark Stratos | R09-P1: complete machine; R09-P2: upper body, bin and controls; R09-P3: cleaner head and lower wand |

## Crop choices and evidence limits

R01 keeps a complete machine view beside enlarged canister/front and hose-connection views. It represents the manufacturer variant in the existing pack. These crops do not establish that every Big Ball variant must have identical cyclone tiers, colours or bin details. They do not identify a shared detached tool by itself.

R02 and R03 align side body/handle views and rear displays. R02 also exposes the separate upper power control. R03 exposes its side handle in the original manufacturer image. A hand covering a query handle supplies no evidence that a trigger is absent. Body scale in these rendered crops is normalised for visibility; it must not be treated as real-world size.

R04-P2 extracts the rear-control inset from the existing V16 primary image, rather than reducing the whole primary image to a small panel. The source visibly contains a red control above its LCD and a lower silver control. R04-P1 and R04-P3 retain the side/front motor, handle and bin geometry. The rear inset contains approximately 160 by 176 source pixels; enlargement makes those pixels easier to inspect and cannot add detail.

V16 and Gen5detect both have manufacturer-supported push-button power control. A rear button cannot be used as a Gen5-exclusive identifier: the V16 source explicitly shows that arrangement. The local Gen5 source contains only front and side views, so it does not establish the location or absence of a rear control. This is a reference-view gap, not an image contradiction. No missing rear view was filled with a query photo or an invented feature.

R05 retains a side body view, a larger handheld view and a front view. Existing manufacturer support records distinguish V8 filter variants. The shown cap, wand and filter colours are examples, not mandatory family features.

R06 keeps a complete front/side view, the lower body with tanks and head, and the handle controls. A wet-cleaner silhouette alone is not an exclusive identifier.

R07 and R08 expose the upper body, bin, handle and neck instead of shrinking the entire stick vacuum. The local front/side views cannot verify an unseen rear-screen interface. A missing or obscured feature cannot be used to contradict either family.

R09 excludes the separate accessory collection from the complete-machine crop and adds the upper body and cleaner head. This is the official UK Stratos IZ400UK image retained in V2. It is a family lookalike reference, not exhaustive coverage of US IZ862H or other Shark variants.

The source URLs and local mappings come from the existing catalogue-source and V2 reference-card records. This change adds component framing, not new product specifications or exclusive textual classification rules.

## Verification before inference

Every source path exists, decodes as an image, matches its recorded SHA-256 and belongs to data/catalog/ or data/reference_images_v2/. Every box is ordered and bounded by 0–1000. Each family has two or three panels. The first six aliases follow the frozen catalogue order; the final three are V11, Gen5detect and Shark. The runtime must additionally verify the final rendered plates with native image viewing before paid calls.
