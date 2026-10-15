"""Search YouTube for review videos per model; keep titles naming exactly one catalog model."""
import json, subprocess, re, sys
Q = {
 "dyson_v8_absolute": ["dyson v8 absolute review", "dyson v8 unboxing"],
 "dyson_v12_detect_slim": ["dyson v12 detect slim review", "dyson v12 detect slim unboxing"],
 "dyson_v15_detect": ["dyson v15 detect review", "dyson v15 detect unboxing"],
 "dyson_v16_piston_animal": ["dyson v16 piston animal review"],
 "dyson_big_ball": ["dyson big ball vacuum review", "dyson cinetic big ball"],
 "dyson_wash_g1": ["dyson wash g1 review", "dyson wash g1 unboxing"],
 "NOT_IN_CATALOG:dyson_v11": ["dyson v11 review"],
 "NOT_IN_CATALOG:dyson_gen5_detect": ["dyson gen5detect review"],
 "NOT_IN_CATALOG:shark_stick": ["shark stratos cordless review"],
 "STORE_SCENE": ["dyson store tour india", "dyson demo store vacuum display"],
}
PAT = {"dyson_v8_absolute": r"\bv8\b", "dyson_v12_detect_slim": r"\bv12\b", "dyson_v15_detect": r"\bv15\b",
       "dyson_v16_piston_animal": r"\bv16\b", "dyson_big_ball": r"big ?ball", "dyson_wash_g1": r"wash ?g1",
       "NOT_IN_CATALOG:dyson_v11": r"\bv11\b", "NOT_IN_CATALOG:dyson_gen5_detect": r"gen ?5", "NOT_IN_CATALOG:shark_stick": r"shark"}
others = lambda k: [p for kk, p in PAT.items() if kk != k]
out = {}
for label, qs in Q.items():
    seen, keep = set(), []
    for q in qs:
        r = subprocess.run(["yt-dlp", f"ytsearch12:{q}", "--flat-playlist", "-J"], capture_output=True, text=True)
        for e in json.loads(r.stdout).get("entries", []):
            t = (e.get("title") or "").lower(); vid = e["id"]
            if vid in seen or (e.get("duration") or 0) < 120: continue
            seen.add(vid)
            if label != "STORE_SCENE":
                if not re.search(PAT[label], t) or any(re.search(p, t) for p in others(label)) or " vs" in t: continue
            keep.append({"id": vid, "title": e.get("title"), "duration": e.get("duration"), "url": f"https://www.youtube.com/watch?v={vid}"})
    out[label] = keep[:4]
    print(label, len(keep), [k["title"][:60] for k in keep[:4]], file=sys.stderr)
json.dump(out, open("data/test_video_sources.json", "w"), indent=1)
