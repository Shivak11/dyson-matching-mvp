# Manufacturer reference evidence for the revised Gemini workflow

The pack has six catalogue families and three non-catalogue lookalikes. Each catalogue family has three complementary manufacturer views. Four unchanged manufacturer image files were added; the remaining views reuse the existing catalogue files. Native image viewing checked all 32 existing images and the four new references. No test photograph or test label was used in these cards.

Visible features combine manufacturer text with native inspection of the referenced images. A colour, generic head or invisible specification is not an exclusive identity cue. V8 filter variants are explicitly retained.

## Sources and short supporting passages

### Dyson Big Ball

[Dyson Big Ball corded vacuum](https://www.dyson.in/big-ball-vacuum) supports: “Rides on a ball, to steer easily around corners and into difficult places.”

Images: `data/catalog/dyson_big_ball/00.png` (Full canister, hose and wand), `data/catalog/dyson_big_ball/02.png` (Canister and bin front view), `data/catalog/dyson_big_ball/03.png` (Canister and hose in use).

### Dyson V8 Absolute family

[Dyson V8 Absolute vacuum cleaner](https://www.dyson.in/dyson-v8-absolute-vacuum) supports: “The motor and battery are positioned around the handle, creating the optimum centre of gravity for floor-to-ceiling cleaning.”

[Choose your Dyson V8 support](https://www.dyson.com/support/vacuum-cleaners/cordless/v8) supports: “The top of this filter is light purple and translucent.”

[Dyson V8 SV10 operating manual, page 20](https://www.dyson.com.cy/medialibrary/manuals/214747_01_V8) supports: “pull the red lever back and lift upwards to release the cyclone.”

Images: `data/catalog/dyson_v8_absolute/00.png` (Full machine), `data/catalog/dyson_v8_absolute/01.png` (Front and side body layout), `data/catalog/dyson_v8_absolute/05.jpg` (Handheld motor, bin and controls at larger scale).

### Dyson V12 Detect Slim

[Dyson V12 Detect Slim Absolute vacuum](https://www.dyson.in/dyson-v12-detect-slim-vacuum-cleaner) supports: “Single-button power control; No need to hold the trigger.”

[Dyson illuminated cordless vacuum comparison](https://www.dyson.com/vacuum-cleaners/cordless/illumination) supports: “Dyson V15™ Detect; Trigger; Dyson V12™ Detect Slim; Button”

Images: `data/catalog/dyson_v12_detect_slim/01.jpg` (Side and front machine views), `data/reference_images_v2/v12_button.jpg` (Close-up of single on/off button and rear motor housing), `data/catalog/dyson_v12_detect_slim/02.jpg` (Larger motor/bin and rear-display view).

### Dyson V15 Detect

[Dyson V15 Detect vacuum cleaner](https://www.dyson.in/dyson-v15-detect-vacuum-cleaner) supports: “LCD screen intelligently reports in real time”

The shared Dyson comparison source is listed under V12 above.
Images: `data/catalog/dyson_v15_detect/01.jpg` (Side and front views), `data/catalog/dyson_v15_detect/02.jpg` (Larger motor and rear-display view), `data/catalog/dyson_v15_detect/05.jpg` (Alternative manufacturer body angle).

### Dyson V16 Piston Animal

[Dyson V16 Piston Animal cordless vacuum](https://www.dyson.in/v16-piston-animal-cordless-vacuum) supports: “New dual conical cleaner head; New compressing bin; LCD screen for instant feedback”

Images: `data/catalog/dyson_v16_piston_animal/01.png` (Body and handle from side and front), `data/catalog/dyson_v16_piston_animal/02.jpg` (Dual-conical cleaner head detail), `data/catalog/dyson_v16_piston_animal/00.png` (Full machine and supplied attachments).

### Dyson WashG1

[Dyson WashG1 wet floor cleaner](https://www.dyson.in/washg1-wet-cleaner-blue-black) supports: “Two motorised counter-rotating microfibre rollers”

Images: `data/catalog/dyson_wash_g1/00.png` (Full machine), `data/catalog/dyson_wash_g1/01.png` (Side and front body/tank views), `data/catalog/dyson_wash_g1/04.jpg` (Lower body and tank layout in use).

### Dyson V11, non-catalogue lookalike

[Dyson V11 cordless vacuum cleaner for business](https://www.dyson.com/commercial/vacuums/v11-blue) supports: “The motor, bin, and cyclone are aligned”

Images: `data/reference_images_v2/v11_side_front.jpg` (Official V11 front and side views).

### Dyson Gen5detect, non-catalogue lookalike

[Dyson Gen5detect Iron/Purple](https://www.dyson.com/vacuum-cleaners/cordless/gen5/detect-hepa-purple-iron) supports: “Power at the touch of a button, with no trigger to hold”

[Dyson Gen5detect and Gen5outsize launch](https://www.dyson.com/discover/innovation/new-machines/gen5detect-gen5outsize-launch) supports: “Hidden inside the wand is a built-in dusting and crevice tool”

Images: `data/reference_images_v2/gen5_side_front.png` (Official Gen5detect Iron/Purple front and side views).

### Shark Stratos cordless family, non-catalogue lookalike

[Shark Stratos IZ400UK cordless vacuum](https://www.sharkninja.co.uk/shark-stratos-anti-hair-wrap-plus-cordless-vacuum-single-battery-iz400uk/IZ400UK.html) supports: “Shark Stratos Anti Hair Wrap Plus Cordless Vacuum”

[Shark official IZ400UK product-image manifest](https://assets.sharkninja.com/image/list/IZ400UK.json) supports: “storefront/products-UK/IZ400UK/IZ400UK_01”

Images: `data/reference_images_v2/shark_stratos.png` (Official UK Stratos whole machine and accessories).

## Retrieval failures and the primary-source substitutes

Direct Python HTTP reads of the Dyson V11, Gen5 shop-all and V8 support HTML returned HTTP 403. Native web reads of the official pages succeeded, and the unchanged official asset URLs downloaded successfully. No authentication bypass was used.

The former US Shark Stratos IZ862H product URL redirected to a different Shark PowerDetect product. That page and its imagery were excluded. The official UK Stratos IZ400UK product page and its official image manifest supplied the family reference instead; the card retains the regional-variant limitation.

One guessed Gen5 URL failed; the official shop-all page linked the working Gen5detect Iron/Purple product page. A web fetch of the large US V8 manual exceeded the web size limit; the official Dyson Cyprus SV10 operating manual supplied the red-lever passage on PDF page 20. Web image fetches sometimes returned cache-miss errors; direct official image downloads succeeded.

The V16 page exposes a shared bin image whose asset path names a Submarine variant. That image was not added. Existing V16 Piston Animal manufacturer images provide the body and dual-cone head views.

## Verification

All referenced local files exist and their SHA-256 digests are recorded in the JSON pack. No paid model call was made to curate these references. Old catalogue images, the original reference pack, all labels and prior result files were left unchanged. The revised runtime must freeze this new JSON and referenced image hashes before paid calls.
