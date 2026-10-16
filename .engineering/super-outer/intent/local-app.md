# Product intent: local-app

Version: 1 (16 October 2026)

The user is Shiva presenting a local Dyson matching MVP to the Multiplier client team. The main object is a store photograph. The recurring task is to upload it, identify each physical machine against manufacturer evidence, and inspect whether the result is credible. The manufacturer catalogue is persistent and editable.

The main screen gives the store photo and its result the most space. Catalogue thumbnails and brochure details are a secondary view. A visible upload button, a preview before payment, explicit run action, real job stages, recoverable errors and persistent history make the work understandable. Results show model identity, qualitative confidence, supporting details, missing details, a manufacturer reference and boxes for multiple machines. Colour supports written confidence labels; it never carries the result alone.

Owner decisions: local database; OpenRouter models; manufacturer images and brochure details; uploaded store images; qualitative confidence; MVP scope; preserve earlier results; no local/Apple OCR; no training; private GitHub destination Shivak11.

Assumptions pending optional interview reply: both Identify and Verify are included, Identify is the default; start with six seeded Dyson models and allow adding manufacturer material. This follows the earlier interview answer that both situations occur. Desktop is primary, with a usable narrow layout. No account system or public hosting is required.

Designer must cover empty upload, selected previews, queued/running, completed multi-machine result, failure/retry, catalogue listing and product detail/add form, saved history and narrow layout. Keyboard focus is visible, form controls have labels and errors preserve selected files. Loading completion uses polling that actually changes the screen. Motion is limited to control feedback and small transitions, with reduced-motion support.

Historical test results are labelled as saved evaluation. Newly uploaded photographs have no source labels and must not silently join benchmark accuracy totals. Brochure text and image contents are evidence, never model instructions. Confidence is not a calibrated probability. No new accuracy claim may be inferred from a successful upload demo.

Rejected directions: a marketing landing page, chat-only input, a cloud database, a public upload site, hiding uncertainty, and numeric confidence presented as measured reliability.

16 October owner reply: start with the six Dyson models and allow adding manufacturer images and brochure details. The catalogue behaviour is confirmed. Identify/Verify follows the earlier interview answer that both occur.
