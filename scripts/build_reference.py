"""Build the human-verified reference from the sheets of the human annotator (R1), the only human annotator (D17).

Inputs:  annotation/human/design.csv, annotation/claims/claims_s1.csv, annotation/llm/labels_A1.csv, labels_A2.csv,
         the returned sheets in annotation/human/R1/returned_2026-11-10/ (sheet_claims_R1.csv = S-H,
         sheet_items_R1.csv = phase 2, sheet_pairs_R1.csv = pair flags, items_R1.csv = edit check),
         annotation/edits/packet_key_v2.csv, edit_set_v2.csv.
Outputs: annotation/reference/reference_R1.csv   one row per labelled claim: set, sample, weight, R1 fields, A1, A2
         annotation/reference/pairs_R1.csv       S-H pair flags (omission, framing, minutes)
         annotation/reference/edits_R1.csv       edit verdicts with the accepted flag (D17 (d))
         annotation/reference/weights.json       N, n_R1 and weight per set
         annotation/reference/format_issues.csv  values outside the allowed sets (kept as given, flagged)
Weights (D17 (a), D17 correction): S-H 1 (random 10% of random-sample pairs, its own stage in the analysis);
         S-D, S-A, S-N: N_set / n_R1, with N_set the stratum size (S-D census 204; S-A 2,508; S-N 719).
"""
import csv, json, os, collections

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RET = os.path.join(MAIN, "annotation/human/R1/returned_2026-11-10")
OUT = os.path.join(MAIN, "annotation/reference")
LAB = {"SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"}
DT = {"status", "scope", "actor", "inference", "dropped_condition"}
VERD = LAB - {"UNASSESSABLE"} | {"UNCLEAR"}
N_SET = {"S-D": 204, "S-A": 2508, "S-N": 719}   # stratum sizes from scripts/make_human_sets.py


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def norm(v):
    return (v or "").strip()


def main():
    os.makedirs(OUT, exist_ok=True)
    design = rd(os.path.join(MAIN, "annotation/human/design.csv"))
    claims = {c["claim_id"]: c for c in rd(os.path.join(MAIN, "annotation/claims/claims_s1.csv"))}
    sample = {r["report_id"]: r["sample"] for r in rd(os.path.join(MAIN, "sampling/reports_main.csv"))}
    a1 = {r["claim_id"]: r["label"] for r in rd(os.path.join(MAIN, "annotation/llm/labels_A1.csv"))}
    a2 = {r["claim_id"]: r["label"] for r in rd(os.path.join(MAIN, "annotation/llm/labels_A2.csv"))}
    r1 = {}
    for f in ("sheet_claims_R1.csv", "sheet_items_R1.csv"):
        for r in rd(os.path.join(RET, f)):
            assert r["claim_id"] not in r1, ("duplicate", r["claim_id"])
            r1[r["claim_id"]] = r
    # D17 correction: the returned phase-2 and edit sheets are the packets planned for R2, so the human's items
    # are S-H plus the half of phase 2 assigned to R2 in design.csv.
    HUMAN_PACKET = "R2"
    mine = [d for d in design if d["set"] == "S-H" or d["annotator"] == HUMAN_PACKET]
    n_r1 = collections.Counter(d["set"] for d in mine)
    w = {"S-H": 1.0, **{s: N_SET[s] / n_r1[s] for s in N_SET}}
    issues, rows = [], []
    for d in mine:
        cid = d["claim_id"]
        if cid not in r1:
            issues.append({"file": "sheets", "id": cid, "field": "row", "value": "missing"}); continue
        x = r1[cid]
        lab = norm(x["label"]).upper()
        dt = norm(x["distortion_type"]).lower()
        if lab not in LAB:
            issues.append({"file": "sheets", "id": cid, "field": "label", "value": x["label"]})
        if lab == "MISREPRESENTED" and dt not in DT:
            issues.append({"file": "sheets", "id": cid, "field": "distortion_type", "value": x["distortion_type"]})
        if lab != "MISREPRESENTED" and dt:
            issues.append({"file": "sheets", "id": cid, "field": "distortion_type_on_non_MIS", "value": x["distortion_type"]})
        rows.append({"claim_id": cid, "report_id": d["report_id"], "ann_id": claims[cid]["ann_id"], "part": claims[cid]["part"],
                     "sample": sample[d["report_id"]], "set": d["set"], "weight": round(w[d["set"]], 6),
                     "label": lab, "distortion_type": dt if lab == "MISREPRESENTED" else "", "content_tags": norm(x["content_tags"]),
                     "cause": norm(x["cause"]), "unsure": norm(x["unsure"]) or "0", "split_error": norm(x["split_error"]) or "0",
                     "A1": a1[cid], "A2": a2[cid]})
    extra = set(r1) - {d["claim_id"] for d in mine}
    for cid in sorted(extra):
        issues.append({"file": "sheets", "id": cid, "field": "row", "value": "not in the human design (S-H + R2 half)"})
    cols = list(rows[0])
    with open(os.path.join(OUT, "reference_R1.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols); wr.writeheader(); wr.writerows(rows)

    pairs = rd(os.path.join(RET, "sheet_pairs_R1.csv"))
    with open(os.path.join(OUT, "pairs_R1.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["report_id", "ann_id", "omission", "framing", "minutes"]); wr.writeheader()
        for p in pairs:
            wr.writerow({"report_id": p["report_id"], "ann_id": p["ann_id"], "omission": norm(p["omission(0/1)"]),
                         "framing": norm(p["framing(0/1)"]), "minutes": norm(p["minutes"])})

    key = {r["item_id"]: r for r in rd(os.path.join(MAIN, "annotation/edits/packet_key_v2.csv")) if r["annotator"] == HUMAN_PACKET}
    eset = {r["edit_id"]: r for r in rd(os.path.join(MAIN, "annotation/edits/edit_set_v2.csv"))}
    erows = []
    for r in rd(os.path.join(RET, "items_R1.csv")):
        k = key[r["item_id"]]; v = norm(r["verdict"]).upper(); dt = norm(r["distortion_type"]).lower()
        e = eset[k["edit_id"]]; kind = "CON" if e["kind"].upper().startswith("CON") else "MIS"   # intended edit type
        if v not in VERD:
            issues.append({"file": "items_R1.csv", "id": r["item_id"], "field": "verdict", "value": r["verdict"]})
        target = "CONTRADICTED" if kind == "CON" else "MISREPRESENTED"
        bs = norm(r["base_supported(1/0)"])
        erows.append({"item_id": r["item_id"], "edit_id": k["edit_id"], "role": k["role"], "kind": kind, "verdict": v,
                      "distortion_type": dt, "base_supported": bs,
                      # accepted = the human verdict equals the intended label and the base claim is SUPPORTED
                      "accepted": int(v == target and bs == "1"),
                      "intended_distortion_type": e["target_type"] if kind == "MIS" else "",
                      "type_match": int(kind == "MIS" and v == "MISREPRESENTED" and dt == e["target_type"])})
    with open(os.path.join(OUT, "edits_R1.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(erows[0])); wr.writeheader(); wr.writerows(erows)
    with open(os.path.join(OUT, "format_issues.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["file", "id", "field", "value"]); wr.writeheader(); wr.writerows(issues)
    json.dump({"N": N_SET, "n_R1": dict(n_r1), "weight": w}, open(os.path.join(OUT, "weights.json"), "w"), indent=1)
    print(f"reference rows {len(rows)} (sets {dict(n_r1)}), edits {len(erows)}, pairs {len(pairs)}, format issues {len(issues)}")


if __name__ == "__main__":
    main()
