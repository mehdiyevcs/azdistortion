"""Freeze the news reports of sampling/reports_final.csv that are not frozen yet.

Web outlets are fetched with scripts/freeze.py (up to three attempts). APA and AZERTAC block automated requests
(prereg D4), so for them the page text saved from a browser (data/news_cache_browser, listed in
data/link_candidates_browser.csv) is copied to data/raw/news/<report_id>/ with a meta.json (source, cached file, sha256).
Usage: python3 scripts/freeze_final.py [reports.csv]
"""
import csv, hashlib, json, os, subprocess, sys, time
csv.field_size_limit(10**9)
br = {(r["cand_id"], r["url"]): r for r in csv.DictReader(open("data/link_candidates_browser.csv", encoding="utf-8"))}
todo = [r for r in csv.DictReader(open(sys.argv[1] if len(sys.argv) > 1 else "sampling/reports_final.csv", encoding="utf-8"))
        if not os.path.exists(f"data/raw/news/{r['report_id']}/meta.json")]
print(len(todo), "to freeze", flush=True)
bad = []
for r in todo:
    d = f"data/raw/news/{r['report_id']}"
    if r["outlet"].lower() in ("apa", "azertac"):
        b = br.get((r["ann_id"], r["url"]))
        if not b:
            bad.append(r["report_id"]); continue
        lines = open(b["cached_file"], encoding="utf-8").read().split("\n", 2)
        os.makedirs(d, exist_ok=True)
        txt = f"TITLE: {b['title']}\nDATE: {b['pub_date']}\nAUTHOR: {r['outlet']}\n" + lines[2]
        open(f"{d}/text_0.txt", "w", encoding="utf-8").write(txt)
        raw = open(b["cached_file"], "rb").read()
        json.dump({"id": r["report_id"], "kind": "news", "files": [{"url": r["url"], "fetched_at": lines[1], "source": "browser (get_page_text)",
                   "cached_file": b["cached_file"], "sha256": hashlib.sha256(raw).hexdigest()}]}, open(f"{d}/meta.json", "w"), ensure_ascii=False, indent=1)
    else:
        for t in range(3):
            out = subprocess.run([".venv/bin/python", "scripts/freeze.py", "news", r["report_id"], r["url"]], capture_output=True, text=True).stdout
            if "saved" in out:
                break
            time.sleep(5)
        else:
            bad.append(r["report_id"])
print("failed:", bad)
