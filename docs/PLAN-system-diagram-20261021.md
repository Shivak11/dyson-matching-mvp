# System architecture diagram

The owner requested a system architecture diagram using draw-system-diagram. Document the existing Cloudflare deployment; do not change application behaviour, deploy an image or call a paid model.

## Scope

1. Verify the deployed image and trace browser, Worker, Durable Object, Python workers, model calls and saved state from current source.
2. Draw a self-contained SVG, render a PNG at twice its dimensions and inspect the final export.
3. Add source-backed architecture facts, a focused regression check and maintenance instructions. Correct directly conflicting README descriptions.
4. Commit the diagram, export, check and maintenance note together. Preserve the unrelated untracked .cursor directory.

## Verified starting state

The isolated codex/cloudflare-demo worktree is at bd38b65. Cloudflare application version 22 runs image sha256:e5289555f5c91a9206d3145675dc66f622c095bc4f1becd0d4bdc97194341ee1. The only pre-existing working-tree entry is the untracked .cursor directory. The wiki remains read-only.

## Verification

Compare diagram facts with source using the existing unittest runner. Deliberately change one fact and confirm failure before restoring it. Run the skill's SVG checker, render and inspect the actual PNG, then check the final staged paths and whitespace. No dataset rerun or paid inference is needed.
