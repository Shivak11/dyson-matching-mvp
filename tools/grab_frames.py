"""Grab 3 still frames from each listed video (no full download). Writes data/test/frames.json."""
import json, subprocess, os, concurrent.futures as cf
src = json.load(open("data/test_video_sources.json"))
src.pop("STORE_SCENE", None)
os.makedirs("data/test/frames", exist_ok=True)
jobs = []
for label, vids in src.items():
    for v in vids[:3]:
        jobs.append((label, v))
def run(job):
    label, v = job
    rows = []
    for frac in (0.22, 0.48, 0.74):
        t = int(v["duration"] * frac)
        out = f"data/test/frames/{label.replace(':','__')}__{v['id']}__{t}.jpg"
        clip = f"/tmp/dyson_clip_{v['id']}_{t}.mp4"
        subprocess.run(["yt-dlp", "--no-update", "-q", "-f", "best[height<=720][ext=mp4]/18", "--download-sections", f"*{t}-{t+2}", "--force-overwrites", "-o", clip, v["url"]], capture_output=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", clip, "-frames:v", "1", "-q:v", "3", out], capture_output=True)
        if os.path.exists(clip): os.remove(clip)
        if os.path.exists(out):
            rows.append({"file": out, "label": label.split(":")[-1], "in_catalog": not label.startswith("NOT_IN_CATALOG"),
                         "source_url": f"{v['url']}&t={t}", "source_title": v["title"], "label_basis": "video title names this model"})
    return rows
allrows = []
with cf.ThreadPoolExecutor(6) as ex:
    for rows in ex.map(run, jobs): allrows += rows
json.dump(allrows, open("data/test/frames.json", "w"), indent=1)
print(len(allrows), "frames;", sum(1 for r in allrows if "error" in r), "errors")
