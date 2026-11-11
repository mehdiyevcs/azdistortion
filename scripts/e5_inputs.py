"""Write the E5 system inputs for the 300 edits of the edit set (annotation/edits/edit_set_v2.csv).

Outputs: runs/main_inputs/e5_edits.csv (claim_id = edit_id, claim_text = edited_claim, report_id/ann_id/part of the
base claim, sample = edit) and runs/main_inputs/e5_edits_t2.csv (edits with has_t2 = 1, as random_t2.csv).
has_t2 = 1 when sampling/sources_summary.csv has has_t2 = 1 and t1_is_act = 0 (D3).
Base claims are random-sample claims, so their predictions come from the E1 random runs; no base file is written.
"""
import csv, os
MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = {r["ann_id"]: r for r in csv.DictReader(open(os.path.join(MAIN, "sampling/sources_summary.csv"), encoding="utf-8"))}
R = {r["claim_id"]: r for r in csv.DictReader(open(os.path.join(MAIN, "runs/main_inputs/random_all.csv"), encoding="utf-8"))}
E = list(csv.DictReader(open(os.path.join(MAIN, "annotation/edits/edit_set_v2.csv"), encoding="utf-8")))
assert len(E) == 300 and len({e["edit_id"] for e in E}) == 300
cols = ["claim_id", "report_id", "ann_id", "part", "sample", "has_t2", "claim_text"]
rows = []
for e in E:
    b = R[e["claim_id"]]  # base must be a random-sample claim with the same announcement, part and text
    assert b["ann_id"] == e["ann_id"] and b["part"] == e["part"] and b["claim_text"] == e["base_claim"], e["edit_id"]
    s = S[e["ann_id"]]
    t2 = int(s["has_t2"] == "1" and s["t1_is_act"] != "1")
    assert str(t2) == b["has_t2"], e["edit_id"]  # same rule as the E1 input of the base claim
    rows.append({"claim_id": e["edit_id"], "report_id": b["report_id"], "ann_id": e["ann_id"], "part": e["part"], "sample": "edit",
                 "has_t2": t2, "claim_text": e["edited_claim"]})
for name, rs in (("e5_edits.csv", rows), ("e5_edits_t2.csv", [r for r in rows if r["has_t2"] == 1])):
    with open(os.path.join(MAIN, "runs/main_inputs", name), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rs)
    print(name, len(rs))
