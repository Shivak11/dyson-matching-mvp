Current status: the YouTube route remains blocked, but step 2 was completed using source-labelled review photographs after Shiva authorised alternative search methods. See docs/step-2-test-set.md.

# Step 2 collection blocker

Date: 15 October 2026

Step 2 is incomplete. Collection stopped under Shiva's instruction to record a blocker and stop.

## What was tried

1. Read the inherited frame extraction script and source list. The original collector captures subprocess errors without reporting them accurately, so it was not run across the whole list.
2. Fetch live metadata for https://www.youtube.com/watch?v=yft0rDip4jc with yt-dlp. This succeeded and confirmed the title “This VACUUM cleaner gets the job DONE // Dyson V8 Absolute REVIEW!”, duration 231 seconds and an MP4 format.
3. Test the handover's proposed fix on that video: use the saved live metadata and `yt-dlp -f 18 --download-sections '*50-52'` to download a two-second clip. No full video was requested.

## Failure

The video server returned HTTP 403 Forbidden to ffmpeg. yt-dlp exited with code 1 and reported `ffmpeg exited with code 8`. No clip was saved and no new frame was extracted. The sanitised diagnostic is in `out/collection_probe.log`.

## State at the stop

The copied project's existing single frame and manifest remain unchanged. No new test photos were saved. The 30–60-image test set, presence review, dropped-image count and test contact sheet have not been completed. No matching API calls were made. The baseline, pipeline and client report have not started.

The client workflow clarification has been recorded: both expected-model verification and catalogue identification occur; manufacturer brochures and images are available; store photographs have unreliable quality and staff can be asked for another photograph.
