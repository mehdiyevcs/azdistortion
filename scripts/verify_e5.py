"""Check the completeness of the E5 edit-set runs runs/e5_<system>_<condition>_edit for the given systems.

For each condition (C0, C1, C2 on the claims with a full text, C2) prints coverage of the edit claims, duplicates,
errors, invalid labels, UNPARSEABLE/REFUSED counts and cost; for C2 it also checks that rows copied from C1 (claims
without a full text) match the C1 run.
Usage: python3 scripts/verify_e5.py <system> [...]
"""
import csv, json, os, glob, sys, collections
M = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda p: list(csv.DictReader(open(p, encoding="utf-8")))
E = rd(f"{M}/runs/main_inputs/e5_edits.csv"); T2 = {r["claim_id"] for r in E if r["has_t2"] == "1"}
ALL = {r["claim_id"] for r in E}
LAB = {"SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE", "REFUSED"}
for s in sys.argv[1:]:
    for c in ("C0", "C1", "C2t2", "C2"):
        rid = f"e5_{s}_{c}_edit"; d = f"{M}/runs/{rid}"
        if not os.path.exists(f"{d}/predictions.csv"):
            print(rid, "MISSING"); continue
        P = rd(f"{d}/predictions.csv"); ids = [p["claim_id"] for p in P]
        want = T2 if c == "C2t2" else ALL
        raw = len(glob.glob(f"{d}/raw/*.json"))
        errs = sum(1 for _ in open(f"{d}/errors.jsonl")) if os.path.exists(f"{d}/errors.jsonl") else 0
        labs = collections.Counter(p["label"] for p in P)
        print(rid, "n", len(P), "cover", set(ids) == want, "dups", len(ids) - len(set(ids)), "errcol", sum(bool(p["error"]) for p in P),
              "errors.jsonl", errs, "raw", raw if c != "C2" else "-", "badlabel", sum(l not in LAB for l in labs.elements()), "unp/ref", labs["UNPARSEABLE"], labs["REFUSED"],
              "cost", round(sum(float(p["cost"] or 0) for p in P), 4))
        if c == "C2":
            P1 = {p["claim_id"]: p for p in rd(f"{M}/runs/e5_{s}_C1_edit/predictions.csv")}
            bad = [p["claim_id"] for p in P if p["copied_from_C1"] == "1" and (p["label"] != P1[p["claim_id"]]["label"] or p["raw_text"] != P1[p["claim_id"]]["raw_text"])]
            wrong = [p["claim_id"] for p in P if (p["copied_from_C1"] == "1") != (p["claim_id"] not in T2)]
            print("   copied", sum(p["copied_from_C1"] == "1" for p in P), "copy!=C1", len(bad), "copy-flag wrong", len(wrong))
