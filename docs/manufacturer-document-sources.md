# Official manufacturer documents

17 October 2026. Six unchanged PDF user manuals were downloaded from official Dyson domains. No separate marketing brochure was found in the bounded search. No model calls, OCR, catalogue edits or database changes were performed.

The integration manifest is `var/manufacturer-documents/manifest.json`. Each document records the family, title, official source URL, owner page, filename, SHA-256, byte size, page count, attachment eligibility, verified page facts and variant limits.

| Product family | Official edition | Original bytes | Integration |
|---|---|---:|---|
| Big Ball | India CY23 | 3,509,081 | Attach original PDF; verified text includes the rating plate location behind the clear bin on page 2. |
| V8 Absolute | US V8/SV10 family | 3,075,739 | Attach original PDF; pages 1 and 12 support mode labels and trigger/filter references. This does not establish the India Absolute accessory package. |
| V12 Detect Slim | US family | 48,606,230 | Link official PDF; exceeds the unchanged 12 MiB attachment cap. Verified details are recorded from pages 3, 4 and 7. |
| V15 Detect | India-linked family | 66,011,259 | Link official PDF; exceeds the attachment cap. Verified details are recorded from pages 2, 4 and 7. |
| V16 Piston Animal | UK SV53-A family | 39,766,778 | Link official PDF; exceeds the attachment cap. Pages 2, 3 and 10 support built-in tools, remote release and dust compression. |
| WashG1 | Hong Kong English family | 10,261,955 | Attach original PDF. It has no extractable text; do not report its contents as parsed diagnostic evidence. |

The three eligible attachments total 16,846,775 bytes. Large PDFs are local research evidence and must remain outside seeded media and the cloud checkpoint. Original PDF bytes were not recompressed or modified.

PDF text was extracted with `pdftotext`, without OCR. An initial `pypdf` extraction was stopped because it was slow. Some V8 English pages have no text layer. WashG1 has no text layer on any page; its manifest intentionally contains no extracted identification details.

Generic maintenance wording in the V12 PDF mentions a trigger. It must not establish the V12 power-control type. V15 and V16 covers contain placeholder SV12/JN text; it must not establish those families' model identifiers. The UK V16 manual and US owner page also differ on bin-release colour, so the recorded detail describes the separate compression and release mechanisms.

All details are comparison evidence. Accessories, shared LCD features and regional packages cannot independently prove an exact variant. No accuracy improvement has been measured from these additions.
