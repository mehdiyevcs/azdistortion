"""Assemble the benchmark add-on report list (prereg D8) from the selected web reports and outlet Telegram posts.

Rows are ordered web reports first, then social posts, each by issuer (cbar, tax, social), ann_id and url. The
signals of social posts are computed on the post text with the same definitions as for web reports
(scripts/bench_select.py). Near-duplicates over web and social are dropped (see below).
Inputs: data/bench_selected_web.csv, data/bench_selected_social.csv, optionally data/bench_web_leftover.csv
Usage: python3 scripts/bench_build.py [--prev <earlier reports_benchmark.csv>] [--with-leftover]
Output: sampling/reports_benchmark.csv
"""
import csv, sys
csv.field_size_limit(10**9)
sys.path.insert(0, "scripts")
from bench_select import signals, grams, text_of, SEED  # noqa: E402
import random

O = {"cbar": 0, "tax": 1, "social": 2}


def reason(sig, v, social=False):
    parts = []
    if "rewritten" in sig:
        parts.append(f"rewritten (copy ratio {v['copy_ratio']:.2f} < 0.6)")
    if "explainer" in sig:
        parts.append(f"explainer cues ({v['cues']})")
    if "headline_diff" in sig:
        parts.append(f"headline differs from issuer title (overlap {float(v['overlap']):.2f} <= 0.30)")
    if social:
        parts.insert(0, "outlet Telegram post (public preview, no login)")
    return "; ".join(parts) or "seeded random fill (no signal)"


web = list(csv.DictReader(open("data/bench_selected_web.csv", encoding="utf-8")))
if "--with-leftover" in sys.argv:  # shortfall rule of the benchmark selection; not used for the final benchmark
    web += list(csv.DictReader(open("data/bench_web_leftover.csv", encoding="utf-8")))
soc = list(csv.DictReader(open("data/bench_selected_social.csv", encoding="utf-8")))
rows = []
for r in sorted(web, key=lambda r: (O[r["issuer"]], r["ann_id"], r["url"])):
    sig = [s for s in r["bench_type"].split("+") if s != "none"]
    v = {"copy_ratio": float(r["copy_ratio"]), "overlap": r["overlap"], "cues": r["cues"]}
    rows.append(dict(issuer=r["issuer"], ann_id=r["ann_id"], outlet=r["outlet"], url=r["url"], pub_date=r["pub_date"], title=r["title"],
                     verified_by=r["verified_by"], bench_type=r["bench_type"], signals="+".join(sig), copy_ratio=r["copy_ratio"],
                     overlap=r["overlap"], cues=r["cues"], n_signals=len(sig), reason=reason(sig, v), _text=text_of(r["url"])))
for r in sorted(soc, key=lambda r: (O[r["issuer"]], r["ann_id"], r["url"])):
    title = r["title"]
    sig, v = signals({"title": title}, r["post_text"], r["ann_title"], r["ann_id"])
    rows.append(dict(issuer=r["issuer"], ann_id=r["ann_id"], outlet=r["outlet"], url=r["url"], pub_date=r["pub_date"], title=title,
                     verified_by=r["verified_by"], bench_type="+".join(["social"] + sig), signals="+".join(sig),
                     copy_ratio=v["copy_ratio"], overlap=v["overlap"], cues=v["cues"], n_signals=len(sig), reason=reason(sig, v, True), _text=r["post_text"]))
# Near-duplicates over web and social: containment of the shorter text's word 5-grams >= 0.9.
# Keep the report with the most signals; ties are broken by random.Random(SEED).
rng = random.Random(SEED)
for r in rows:
    r["_g"] = grams(r["title"] + "\n" + (r.get("_text") or ""))
    r["_tie"] = rng.random()
drop = set()
for i in range(len(rows)):
    for j in range(i + 1, len(rows)):
        a, b = rows[i]["_g"], rows[j]["_g"]
        if a and b and len(a & b) / min(len(a), len(b)) >= 0.9:
            lo = min((i, j), key=lambda k: (-rows[k]["n_signals"], -rows[k]["_tie"]))
            loser = j if lo == i else i
            drop.add(loser)
            print("near-duplicate:", rows[i]["url"], rows[j]["url"], "-> drop", rows[loser]["url"])
rows = [r for k, r in enumerate(rows) if k not in drop]
F = ["report_id", "ann_id", "outlet", "url", "pub_date", "title", "verified_by", "sample", "bench_type", "reason",
     "issuer", "signals", "n_signals", "copy_ratio", "overlap", "cues"]
# Stable ids: with --prev <csv> (an earlier reports_benchmark.csv) a report selected again keeps its id (matched by url);
# new reports continue after the highest earlier id, in the row order above.
prev = {}
if "--prev" in sys.argv:
    prev = {r["url"]: r["report_id"] for r in csv.DictReader(open(sys.argv[sys.argv.index("--prev") + 1], encoding="utf-8"))}
nxt = max([int(v[1:]) for v in prev.values()] or [0]) + 1
for r in rows:
    if r["url"] in prev:
        r["report_id"] = prev[r["url"]]
    else:
        r["report_id"] = f"B{nxt:04d}"; nxt += 1
rows.sort(key=lambda r: r["report_id"])
with open("sampling/reports_benchmark.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=F, extrasaction="ignore"); w.writeheader()
    for r in rows:
        w.writerow(dict(r, sample="benchmark"))
print("rows", len(rows))
