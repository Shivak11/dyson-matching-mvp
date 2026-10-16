# Sites deployment feasibility

16 October 2026. The unchanged Python app cannot be deployed through the documented Sites workflow. The local implementation continues. No Site, hosted secret, tunnel, storage service or paid inference was created for this investigation. No private photograph or code was sent to research services.

Sites supports owner-private ChatGPT sign-in, Worker request handlers, D1 records and R2 files. Its installed 1.0.0 workflow packages static output or JavaScript ESM/Vinext Workers. It does not document packaging a normal persistent Python HTTP server. The current app uses fcntl file locks, ThreadingHTTPServer, a daemon inference thread and filesystem-backed SQLite, media and cost ledgers. These facilities cannot be retained unchanged in that supported Sites architecture.

Cloudflare itself supports Python Workers through Pyodide, and current Pyodide packages include Pillow. That does not establish a supported Python publishing route through Sites. Pyodide removes fcntl and has non-functional threading/sockets. The present image limit permits a 40-megapixel RGB decode of about 120 MB before extra copies; the Workers 128 MB limit also needs explicit validation for any port.

There is no blanket 30-second HTTP request limit while a client stays connected. The relevant limit is post-response work: waitUntil extends execution for at most 30 seconds after response/disconnection. The app returns 202 and then completes potentially multiple 480-second requests with 15-second pacing. Durable inference execution is therefore required; the inspected Sites workflow does not expose the necessary Queue/Workflow binding.

A hosted version requires either a supported Worker port with private D1/R2 storage, compatible image processing and durable jobs, or a separately authenticated Python host with persistent storage. It also requires configuring the hosted OpenRouter secret and authorising private-photo/record transfer. Those dependencies were not provisioned or tested. Do not expose the Mac database or use an unauthenticated tunnel as a substitute.

## Evidence inspected

- Installed Sites skill: /Users/shivakakkar/.codex/plugins/cache/openai-curated-remote/sites/1.0.0/skills/sites/SKILL.md and its identity-and-secrets.md, storage.md and worker-esm-starter/README.md references.
- [Cloudflare Python runtime](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/) and [Python package support](https://developers.cloudflare.com/workers/languages/python/packages/).
- [Pyodide runtime constraints](https://pyodide.org/en/stable/usage/wasm-constraints.html) and [package catalogue](https://pyodide.org/en/stable/usage/packages-in-pyodide.html).
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/).
- Actual server, store and inference source: app_server.py, webapp/store.py and webapp/inference.py. The read-only runtime scout used generic official-documentation requests only.
