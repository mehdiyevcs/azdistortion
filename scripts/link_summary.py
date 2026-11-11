"""Summarise the news-to-announcement link verification of one link set.

Prints agreement and kappa between the Claude and Codex verdicts (same_decision vs rest) and the coverage per
announcement, and writes the disagreements to sampling/R1_link_queue_<set>.csv for the human annotator (R1).
Usage: python3 scripts/link_summary.py cbar|tax_w|social_w
"""
import csv, sys
from collections import Counter
s = sys.argv[1]
a = {(r["ann_id"], r["url"]): r for r in csv.DictReader(open(f"data/link_verified_claude_{s}.csv", encoding="utf-8"))}
b = {(r["ann_id"], r["url"]): r for r in csv.DictReader(open(f"data/link_verified_codex_{s}.csv", encoding="utf-8"))}
S = lambda v: v == "same_decision"
ks = [k for k in b if k in a]
po = sum(S(a[k]["verdict"]) == S(b[k]["verdict"]) for k in ks) / len(ks)
pa = sum(S(a[k]["verdict"]) for k in ks) / len(ks); pb = sum(S(b[k]["verdict"]) for k in ks) / len(ks); pe = pa * pb + (1 - pa) * (1 - pb)
dis = [k for k in ks if S(a[k]["verdict"]) != S(b[k]["verdict"])]
cov = Counter(r["ann_id"] for r in a.values() if S(r["verdict"]))
print(s, "claude", dict(Counter(r["verdict"] for r in a.values())), "| overlap", len(ks), "agree", round(po, 3), "kappa", round((po - pe) / (1 - pe), 3) if pe < 1 else "n/a", "| disagreements", len(dis))
print("  covered anns", len(cov), "of", len({r["ann_id"] for r in a.values()}), "| matched reports", sum(cov.values()), dict(Counter(r["outlet"] for r in a.values() if S(r["verdict"]))))
with open(f"sampling/R1_link_queue_{s}.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["ann_id", "url", "claude", "codex"])
    for k in dis:
        w.writerow([k[0], k[1], a[k]["verdict"], b[k]["verdict"]])
