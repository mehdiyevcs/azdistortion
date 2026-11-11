"""Compare the Claude and Codex eligibility screening of one issuer's candidate announcements.

Items on which both screeners agree on eligible or not_eligible are marked agreed; all others go to the human
annotator (R1).
Output: sampling/screen_merged_<issuer>.csv
Usage: python3 scripts/screen_compare.py cbar|tax|social
"""
import csv, sys
csv.field_size_limit(10**9)
from collections import Counter
iss = sys.argv[1]
a = {r["cand_id"]: r for r in csv.DictReader(open(f"sampling/screen_claude_{iss}.csv", encoding="utf-8"))}
b = {r["cand_id"]: r for r in csv.DictReader(open(f"sampling/screen_codex_{iss}.csv", encoding="utf-8"))}
c = {r["cand_id"]: r for r in csv.DictReader(open(f"data/candidates/{iss}.csv", encoding="utf-8"))}
E = lambda x: x == "eligible"
ks = list(a); n = len(ks)
po = sum(E(a[k]["decision"]) == E(b[k]["decision"]) for k in ks) / n
pa = sum(E(a[k]["decision"]) for k in ks) / n; pb = sum(E(b[k]["decision"]) for k in ks) / n
pe = pa * pb + (1 - pa) * (1 - pb); kap = (po - pe) / (1 - pe)
rows = []
for k in ks:
    da, db = a[k]["decision"], b[k]["decision"]
    status = "agreed" if da == db and da in ("eligible", "not_eligible") else "to_R1"
    rows.append({"cand_id": k, "date": c[k]["date"], "title": c[k]["title"], "url": c[k]["url"], "claude": da, "claude_reason": a[k]["reason"],
                 "codex": db, "codex_reason": b[k]["reason"], "status": status, "agreed_decision": da if status == "agreed" else ""})
w = csv.DictWriter(open(f"sampling/screen_merged_{iss}.csv", "w", newline="", encoding="utf-8"), fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(iss, "n", n, "agreement", round(po, 3), "kappa(eligible vs rest)", round(kap, 3), Counter(r["status"] for r in rows), Counter(r["agreed_decision"] for r in rows if r["agreed_decision"]))
