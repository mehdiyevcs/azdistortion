"""Compute report copy ratios, syndication flags and announcement clusters (prereg H2 and "Linking and verification").

copy_ratio = share of the report's word 5-grams (lowercased, punctuation removed) found in T1, the press release page
(data/raw/announcements/<ann_id>/text_*.txt of the HTML files only; T2 is not used). rewritten = copy_ratio < 0.6.
Two reports are syndicated if the containment of the shorter report's 5-grams in the other is >= 0.9 (Jaccard is also
recorded). Union-find over syndication pairs and over report URLs linked to more than one announcement gives the
announcement clusters used by the bootstrap and the CV folds.
Inputs: sampling/reports_main.csv, data/raw/news/, data/raw/announcements/, sampling/reports_pool.csv (if present)
Usage: python3 scripts/copy_ratio.py
Outputs: sampling/report_features.csv, sampling/syndication_pairs.csv, sampling/clusters.csv
"""
import csv, glob, json, os, re, unicodedata
csv.field_size_limit(10**9)


def norm_words(t):
    t = unicodedata.normalize("NFC", t).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return t.split()


def grams(t, n=5):
    w = norm_words(t)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def report_text(rid):
    t = open(f"data/raw/news/{rid}/text_0.txt", encoding="utf-8").read().split("\n")
    title = t[0][7:] if t and t[0].startswith("TITLE: ") else ""
    return title + "\n" + "\n".join(l for l in t[1:] if not re.match(r"^(DATE|AUTHOR): ", l))


def t1_text(aid):
    d = f"data/raw/announcements/{aid}"
    meta = json.load(open(f"{d}/meta.json", encoding="utf-8"))
    out = []
    for k, f in enumerate(meta["files"]):
        if f.get("raw", "").endswith(".html") and os.path.exists(f"{d}/text_{k}.txt"):
            out.append(open(f"{d}/text_{k}.txt", encoding="utf-8").read())
    return "\n".join(out)


reps = list(csv.DictReader(open("sampling/reports_main.csv", encoding="utf-8")))
G = {r["report_id"]: grams(report_text(r["report_id"])) for r in reps}
T1 = {}
feat = []
for r in reps:
    a = r["ann_id"]
    if a not in T1:
        T1[a] = grams(t1_text(a))
    g = G[r["report_id"]]
    cr = len(g & T1[a]) / len(g) if g else 0.0
    feat.append({**r, "n_5grams": len(g), "copy_ratio": round(cr, 4), "rewritten": int(cr < 0.6)})
pairs = []
ids = [r["report_id"] for r in reps]
for i in range(len(ids)):
    for j in range(i + 1, len(ids)):
        a, b = G[ids[i]], G[ids[j]]
        if not a or not b:
            continue
        inter = len(a & b)
        cont = inter / min(len(a), len(b)); jac = inter / len(a | b)
        if cont >= 0.9:
            pairs.append({"report_a": ids[i], "report_b": ids[j], "containment": round(cont, 4), "jaccard": round(jac, 4)})
syn = {p["report_a"] for p in pairs} | {p["report_b"] for p in pairs}
for f in feat:
    f["syndicated"] = int(f["report_id"] in syn)
# union-find over announcements
par = {}
def find(x):
    par.setdefault(x, x)
    while par[x] != x:
        par[x] = par[par[x]]; x = par[x]
    return x
def union(a, b):
    par[find(a)] = find(b)
ann_of = {r["report_id"]: r["ann_id"] for r in reps}
for r in reps:
    find(r["ann_id"])
by_url = {}
for r in reps:
    by_url.setdefault(r["url"], []).append(r["ann_id"])
for anns in by_url.values():
    for x in anns[1:]:
        union(anns[0], x)
for p in pairs:
    union(ann_of[p["report_a"]], ann_of[p["report_b"]])
# prereg D10 addendum: a verified report URL linked to two announcements in the verified pool joins them
if os.path.exists("sampling/reports_pool.csv"):
    bu = {}
    for r in csv.DictReader(open("sampling/reports_pool.csv", encoding="utf-8")):
        bu.setdefault(r["url"], set()).add(r["ann_id"])
    for anns in bu.values():
        anns = sorted(anns)
        for x in anns[1:]:
            if x in par or anns[0] in par:
                union(anns[0], x)
for f in feat:
    f["cluster"] = find(f["ann_id"])
w = csv.DictWriter(open("sampling/report_features.csv", "w", newline="", encoding="utf-8"), fieldnames=list(feat[0])); w.writeheader(); w.writerows(feat)
w = csv.DictWriter(open("sampling/syndication_pairs.csv", "w", newline="", encoding="utf-8"), fieldnames=["report_a", "report_b", "containment", "jaccard"]); w.writeheader(); w.writerows(pairs)
cl = sorted({(f["ann_id"], f["cluster"]) for f in feat})
w = csv.writer(open("sampling/clusters.csv", "w", newline="", encoding="utf-8")); w.writerow(["ann_id", "cluster"]); w.writerows(cl)
import statistics
print(len(feat), "reports; median copy ratio", statistics.median(f["copy_ratio"] for f in feat), "; rewritten", sum(f["rewritten"] for f in feat),
      "; syndication pairs", len(pairs), "; syndicated reports", len(syn), "; clusters", len({c for _, c in cl}), "of", len({a for a, _ in cl}), "announcements")
