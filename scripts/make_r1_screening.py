"""Build the blind eligibility-screening sheet for the human annotator (R1).

The sheet holds all to_R1 items (screener disagreements and borderline cases) plus a seeded random 10% of the agreed
decisions, shuffled together, without the screeners' decisions. The key for scoring is kept separately.
Usage: python3 scripts/make_r1_screening.py -> annotation/R1/screening/R1_screening_sheet.csv, sampling/R1_screening_key.csv
"""
import csv, os, random, re
csv.field_size_limit(10**9)
OUT = "annotation/R1/screening"; os.makedirs(OUT, exist_ok=True)
rng = random.Random(20261115); items, key = [], []
for iss in ("cbar", "tax", "social"):
    txt = {r["cand_id"]: r["text"] for r in csv.DictReader(open(f"data/candidates/{iss}.csv", encoding="utf-8"))}
    for r in csv.DictReader(open(f"sampling/screen_merged_{iss}.csv", encoding="utf-8")):
        why = "to_R1" if r["status"] == "to_R1" else ("check10" if rng.random() < 0.10 else None)
        if why:
            items.append({"cand_id": r["cand_id"], "date": r["date"], "title": r["title"], "url": r["url"],
                          "text_start": re.sub(r"\s+", " ", txt[r["cand_id"]])[:700], "decision": "", "note": ""})
            key.append({"cand_id": r["cand_id"], "why": why, "claude": r["claude"], "codex": r["codex"], "agreed_decision": r["agreed_decision"]})
rng.shuffle(items)
with open(f"{OUT}/R1_screening_sheet.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(items[0].keys())); w.writeheader(); w.writerows(items)
with open("sampling/R1_screening_key.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(key[0].keys())); w.writeheader(); w.writerows(key)
from collections import Counter
print(len(items), Counter(k["why"] for k in key))
