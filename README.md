# Dyson photo matching

A local web app for comparing store photographs with manufacturer images and brochure details. It uses SQLite and Gemini 3.7 Flash high through OpenRouter. The saved accuracy report and earlier experiments remain in this repository.

## Run locally

Use Python 3.11 or newer with Pillow installed:

```bash
python3 -m pip install -r requirements.txt
```

Set `OPENROUTER_API_KEY` in the server environment or in the ignored `.env` file in this folder. Keep the key on the server. In this research checkout, prepare the manufacturer-only seed and selected model configuration locally:

```bash
python3 tools/build_private_app.py --output . --prepare-catalogue --inputs-only
```

This writes the private seed under `var/catalogue-seed` and the ignored `runtime_config.json`. It does not copy test photographs or evaluation records. An existing catalogue database is preserved.

```bash
python3 app_server.py --port 8768
```

Open [the local app](http://127.0.0.1:8768). It starts with six Dyson catalogue products and three outside-catalogue comparison references. The app binds to this computer's loopback address; it is not a public upload service.

Choose **Identify** to find a model, or **Verify** to check a claimed catalogue model. Select up to five JPEG, PNG or WebP store photographs, inspect the previews, then run the comparison. Selecting photographs does not make a paid call. Results and the catalogue persist in the local database. Each run retains its own catalogue snapshot.

In **Catalogue**, add manufacturer images and source-backed brochure details or add a new product. An uploaded PDF is stored as the original file. Enter the relevant brochure details in the text field; this MVP does not automatically extract uploaded PDFs.

Each result shows a selectable box and model-family decision for each physical machine, qualitative confidence, visible evidence, missing details and any retake guidance. Confidence is the model's assessment, not a measured probability. The live app path compares all catalogue candidates and has not had a fresh full-set accuracy evaluation. Shared controls or an interchangeable attachment cannot uniquely identify a model.

Expand **Run details** to inspect recorded latency, the AI model/provider, configuration identity and request charges or reservations. Unknown metadata is marked as unrecorded. Use **Download JSON** or **Download CSV** beside a saved result or in History. Downloads preserve the prediction and run details recorded at completion; later catalogue edits do not change their bytes. CSV cells are protected against spreadsheet formulas.

## Costs and recovery

The app has a shared initial runtime cap of ₹100, within the remaining experiment budget. It keeps a separate metered ledger for each job and includes unfinished-request reserves. One paid worker runs at a time, with at least 15 seconds after a response and bounded retries for rate limits. There is no silent model or provider fallback.

Closing the browser does not cancel a running job. Restarting the server marks unfinished jobs as interrupted; it does not repeat paid calls. Review the preserved upload and deliberately retry when appropriate. The initial cap cannot be reset by choosing another database location.

Runtime databases, uploads, responses and `.env` are ignored by Git. The historic public-photo experiment evidence remains tracked for reproducibility. Do not add client uploads or keys to Git.

## Accuracy report and saved evidence

[The historical HTML report](web/report.html) includes the measured comparison, costs and every development test photograph. Open that file directly. The private testing app does not serve the report, evaluation data or research-photo routes. Rebuild the report in this research checkout without API calls:

```bash
python3 tools/build_accuracy_report.py
```

The completed full-set Gemini run resolved 37 of 57 single-model photos correctly, with five confidently wrong answers and 15 not sure. The separate two-model photograph returned the correct identity set. Recovery experiments are reported separately; they are not fresh full-set scores. See [the handover](HANDOVER.md), [edge cases](docs/edge-case-register.md) and [the local-app verification record](docs/local-app-verification.md).

## Check the source

```bash
python3 -m unittest discover -s tests -v
```

These tests do not call paid models. Browser and live OpenRouter verification are recorded separately.

## Isolated local bundle and hosting

Build a code-only archive and a separate local working copy with manufacturer inputs:

```bash
python3 tools/build_private_app.py --output var/private-testing-app --prepare-catalogue
```

Choose an empty output folder. The adjacent `private-testing-app-code.zip` contains only the server, runtime modules, requirements and three web assets. It excludes source data, model configuration, databases, photos, keys, tests, reports and experiment outputs. The prepared local folder additionally contains the private manufacturer seed and selected model configuration; those inputs are never public static assets. The archive is a transport artifact, not a deployed Site. Runtime credentials are supplied separately through the server environment.

Sites hosting is blocked for the unchanged Python server and background worker. Owner-private sign-in is supported, but hosting requires adapting execution, private storage and durable jobs, and configuring a hosted OpenRouter secret. See [the exact runtime findings](docs/private-testing-sites-feasibility.md). No Site, tunnel, hosted service or private data transfer was created for this conversion.
