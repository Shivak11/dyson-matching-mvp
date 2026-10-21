# Maintaining the system diagram

The SVG documents the deployed Cloudflare application and appears at the top of the README. The PNG is the same diagram rendered at twice its dimensions. The diagram uses the installed Super-outer draw-system-diagram skill, its house template, checker and Chrome renderer.

Blue identifies the browser, orange the application, green external model services, purple saved state, teal release work and indigo the actual request trace. Solid borders mean live. The dashed request-logging card is switched off in the deployment configuration; the separate private lifecycle event recording remains live. There is no agreed future component to add as a planned service.

Redraw the SVG in the same commit when a component, storage path, provider, model, reasoning level, route, concurrency limit, timing, feature switch or deployed image changes. Update the facts block with the picture. Preserve the distinction between the container's working files and R2 checkpoints, and between separate photo jobs and cumulative views of one product.

The release reference is application version 22, image sha256:e5289555f5c91a9206d3145675dc66f622c095bc4f1becd0d4bdc97194341ee1, checked through the Cloudflare CLI on 21 October 2026. The real request trace is the completed run in ../evidence/worker-repair/hosted-observation.json. It is an example flow, with no claim that every run has the same latency or outcome. Manufacturer PDFs remain original attachments; entered brochure text and actual reference images supply comparison evidence.

From the repository root, use Python with Pillow installed:

```sh
python3 -m unittest discover -s tests -p 'test_architecture_diagram.py' -v
node /Users/shivakakkar/.codex/plugins/cache/super-outer-developer-update/super-outer/5.22.0/skills/draw-system-diagram/scripts/check-diagram.mjs docs/architecture/system-diagram.svg
node /Users/shivakakkar/.codex/plugins/cache/super-outer-developer-update/super-outer/5.22.0/skills/draw-system-diagram/scripts/render-diagram.mjs docs/architecture/system-diagram.svg
```

Inspect the final PNG after each layout change, then rerun the facts test. These checks require no model request or deployment.
