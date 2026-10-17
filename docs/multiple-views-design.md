# Same-product view design

Package v1: var/multiple-views-design/v1/. Intent: docs/PLAN-multiple-views.md at commit 4639bbb. Manifest SHA-256: 0008483bdc42978d4cf46d3890126b98f158e0875e844985cc16fb48ef8574cb.

Use the existing result screen. Place the three saved result steps below the identification heading; each completed step opens its saved result. Unused steps say Not added; pending steps say Queued or Checking. Show actual qualitative confidence only.

Add another view opens one file selection and then an inline preview containing all earlier photos plus the new photo. Require This photo shows the same physical product as View 1. The primary action is Identify using 2 views or Identify using 3 views. Cancel preserves the earlier result. Disable changes while saving, preserve file/request ID on error, and retain prior outcomes while queued or running.

After completion, show View 1 / View 2 / View 3 selectors below the store image. Change photo and its own boxes together. Each feature names its supporting view. At three views, omit the add action. Existing Upload more creates independent results. No new navigation, dashboard, percentage accuracy or forced confidence progression.

Four actual agent-browser frames at 1440 × 1000 are in frames/one.png, preview.png, running.png and three.png. All identification, confidence and processing in these frames are simulated, visibly labelled; public manufacturer images are placeholders for example store inputs. states.md records keyboard, saving/error/retry/return and narrow-layout rules. No product source edited or paid calls made.
