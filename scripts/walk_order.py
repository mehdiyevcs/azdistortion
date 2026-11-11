"""Write the draw walk order (prereg.md section 2 "Draw", D1): a seeded shuffle of each issuer's full frozen frame
(sorted by cand_id), with dev items marked as excluded.

Usage: python3 scripts/walk_order.py [K] -> sampling/walk_order_<issuer>.csv, plus sampling/link_set_<issuer>_w.csv with the
first K (default 45) items not screened out as not_eligible, for news linking.
"""
import csv, random, sys
csv.field_size_limit(10**9)
DEV = {"CBAR-5573", "CBAR-5417", "CBAR-5463", "CBAR-5459", "CBAR-5569", "DVX-4939", "DVX-4940", "DVX-4966", "DVX-5048",
       "EMSMN-9192", "EMSMN-9975", "EMSMN-9920", "EMSMN-10013"}  # pilot items and their companion/re-release posts
K = int(sys.argv[1]) if len(sys.argv) > 1 else 45
for iss in ("cbar", "tax", "social"):
    frame = sorted(r["cand_id"] for r in csv.DictReader(open(f"data/candidates/{iss}.csv", encoding="utf-8")))
    rng = random.Random(20261109); order = frame[:]; rng.shuffle(order)
    m = {r["cand_id"]: r for r in csv.DictReader(open(f"sampling/screen_merged_{iss}.csv", encoding="utf-8"))}
    rows = [{"rank": i + 1, "cand_id": c, "dev_excluded": int(c in DEV), "status": m[c]["status"], "agreed_decision": m[c]["agreed_decision"]} for i, c in enumerate(order)]
    w = csv.DictWriter(open(f"sampling/walk_order_{iss}.csv", "w", newline="", encoding="utf-8"), fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    poss = [r["cand_id"] for r in rows if not r["dev_excluded"] and r["agreed_decision"] != "not_eligible"][:K]
    cand = {r["cand_id"]: r for r in csv.DictReader(open(f"data/candidates/{iss}.csv", encoding="utf-8"))}
    w = csv.DictWriter(open(f"sampling/link_set_{iss}_w.csv", "w", newline="", encoding="utf-8"), fieldnames=list(cand[poss[0]].keys())); w.writeheader(); w.writerows(cand[c] for c in poss)
    print(iss, len(rows), "frame;", sum(r["dev_excluded"] for r in rows), "dev excluded;", len(poss), "in link set")
