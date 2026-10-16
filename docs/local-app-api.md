# Local app API, version 1

All responses are JSON except static files, media and /report. Same-origin browser requests only. Bind to 127.0.0.1. Return errors as {"error":"plain explanation"} with an appropriate HTTP status. Reject non-loopback Host/Origin and cross-site mutations. GET /api/bootstrap returns a CSRF token; POST/PATCH require X-CSRF-Token. Keep keys and local paths out of responses. Static assets live under /web but / serves web/index.html.

## Objects

Product: {id,name,manufacturer,in_catalog,source_url,brochure_details,brochure_url,images:[{id,url,filename}],image_url}. id is stable. image_url is the first image or null. Seed the six catalogue products and three separately marked lookalikes from existing manufacturer records. Brochure details contain actual manufacturer source passages; do not call a webpage excerpt an uploaded brochure. Uploaded brochure PDF is optional and served unchanged.

Job: {id,filename,image_url,created_at,status,stage,mode,expected_product_id,expected_product_name,cost_inr,error,matches:[]}. status is queued/running/completed/failed/interrupted. mode is identify/verify. stage is a plain current action. Match: {object_id,box_2d,status,product_id,product_name,confidence,evidence,missing_evidence,alternatives,reference_image_url,verification}. box_2d uses [ymin,xmin,ymax,xmax] on 0..1000. status is match/not_in_catalog/not_sure. confidence is High/Medium/Low and is not calibrated. alternatives are {id,name} objects. verification is confirmed/rejected/unresolved or null.

## Routes

- GET /api/bootstrap -> {csrf_token,catalogue:[Product],jobs:[Job],settings:{model_label,api_configured,runtime_cap_inr,runtime_spent_inr,runtime_remaining_inr,stage_remaining_inr,request_pause_seconds},evaluation:{singles,correct,confidently_wrong,unsure,multi_photo_count}}.
- GET /api/catalogue -> {products:[Product]}; GET /api/catalogue/<id> -> Product.
- POST /api/catalogue -> Product. Input {name,manufacturer,source_url,brochure_details,images:[{filename,data_url}],brochure:null|{filename,data_url}}. Require nonempty name, http(s) manufacturer source, and at least one validated image. New products are in_catalog=true.
- PATCH /api/catalogue/<id> -> Product. Same editable metadata; images append. No destructive replace/delete in MVP. Preserve omitted fields.
- POST /api/jobs -> {jobs:[Job]}. Input {images:[{filename,data_url}],expected_product_id:null|id}. One to five images. Each image <=12 MiB, request <=65 MiB; validate bytes with Pillow, <=40 megapixels, JPEG/PNG/WebP only, strip EXIF for provider views while preserve original uploaded bytes. PDF <=12 MiB for catalogue only. Explicit POST is the paid run action. Persist all valid uploads before queueing; never partially accept a batch with invalid files.
- GET /api/jobs -> {jobs:[Job]}; GET /api/jobs/<id> -> Job. Poll while queued/running. Failed jobs retain their files and partial charges. Reuse its image via POST /api/jobs/<id>/retry -> {jobs:[Job]} as a deliberate new job, old result preserved. Retry includes original expected product. Do not offer retry while running.
- GET /api/evaluation -> {summary,photos:[{id,filename,image_url,source_title,source_url,outcome,matches:[Match]}]}. Read-only saved 58-photo evaluation, separate from live jobs. Summary includes the frozen original counts and selected-failure wave counts separately. No new model calls.
- GET /report -> printable one-page HTML accuracy report from saved measured results. Keep confidently wrong counts visible. Costs identify their model, scope and whether shared pipeline costs are included.
- GET /media/<opaque-id> serves only DB-authorised media; no arbitrary file path parameter. Also allow safe predefined evaluation images by ID through this route. PDFs served as application/pdf with safe filename, no HTML uploads.

## Runtime inference

Use one queued worker and a process lock, persist at every stage. On server restart, queued/running jobs become interrupted; no automatic paid resume. Never allow a second process to make concurrent calls. Reuse existing pipeline_api.Client in separate runtime/job ledgers with aggregate cap accounting before every job; do not overwrite old model evidence. Pass source image pixels and only manufacturer catalogue data to models, never evaluation labels, filenames, titles or earlier benchmark answers.

New calls use the existing pinned Gemini 3.7 Flash high OpenRouter configuration. Dynamic prompts use existing inventory and evidence validation. Compare every active catalogue candidate (six initially), including existing outside-catalogue lookalikes as negative references; query embedding via direct Google is excluded. This app path has no newly measured accuracy; report that in developer notes. At most inventory, comparison and one targeted refinement per job; skip refinement for a complete supported match. Reject invalid outputs instead of displaying invented results. For a new catalogue entry lacking some discriminating views/details, show the missing evidence rather than inventing it.

Use INR100 as the maximum app runtime allowance and aggregate it with the remaining stage budget. Existing stage guard is INR801.9682441/1000. Reserve unknown charges. At least15seconds after response; bounded429 retry honours Retry-After. A terminal failure does not disable the queue forever or release uncertain usage. No silent model/provider fallback. API configured status does not reveal credential contents.
