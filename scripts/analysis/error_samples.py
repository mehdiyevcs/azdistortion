"""Draw the error-analysis samples for manual coding of disagreement and error causes.

Outputs:
  analysis/error_analysis/human_llm_disagreements_20.csv: 20 reference claims where the human annotator (R1)
    differs from A1 or A2.
  analysis/error_analysis/system_errors_30.csv: 30 (claim, system) errors of the four LLM systems under C2:
    10 false alarms (R1 SUPPORTED, system CON/MIS), 10 missed errors (R1 CON/MIS, system neither), 10 other confusions.
Each claim appears at most once per file. Seed SEED_ERRSAMPLE (numpy default_rng); this seed is not a prereg seed.
The columns cause_code and coder_note are left empty for the coder (codes: missed condition, over-literal reading,
legal inference, headline context, other).
"""
import os
import numpy as np
import pandas as pd
from common import *


def run(runs):
    D = load(); ref = D["ref"]
    os.makedirs(ERR, exist_ok=True)
    rng = np.random.default_rng(SEED_ERRSAMPLE)
    a1 = pd.read_csv(p("annotation/llm/labels_A1.csv")).set_index("claim_id")
    a2 = pd.read_csv(p("annotation/llm/labels_A2.csv")).set_index("claim_id")
    dis = ref[(ref["label"] != ref["A1"]) | (ref["label"] != ref["A2"])].sort_values("claim_id")
    pick = dis.iloc[sorted(rng.choice(len(dis), size=min(20, len(dis)), replace=False))]
    out = pick[["claim_id", "report_id", "ann_id", "sample", "set", "part", "claim_text", "label", "distortion_type", "A1", "A2"]].rename(columns={"label": "R1"}).copy()
    out["A1_evidence"] = out["claim_id"].map(a1["evidence"]); out["A1_note"] = out["claim_id"].map(a1["note"])
    out["A2_evidence"] = out["claim_id"].map(a2["evidence"]); out["A2_note"] = out["claim_id"].map(a2["note"])
    out["source_T1"] = "data/sources/" + out["ann_id"] + "/T1.txt"; out["report_text"] = "data/raw/news/" + out["report_id"]
    out["cause_code"] = ""; out["coder_note"] = ""
    for c in ("R1", "A1", "A2"):
        out[c] = out[c].map(out_label)
    out.to_csv(os.path.join(ERR, "human_llm_disagreements_20.csv"), index=False)
    # errors of the LLM systems under C2
    recs = []
    for s in SYSTEMS_LLM:
        pr = {}
        for smp in ("random", "benchmark"):
            if f"e1|{s}|C2|{smp}" in runs:
                pr.update(runs[f"e1|{s}|C2|{smp}"]["preds"])
        for r in ref.itertuples():
            if r.claim_id in pr:
                q = norm_pred(pr[r.claim_id])
                if q != r.label:
                    cls = ("false_alarm" if r.label == "SUPPORTED" and q in ERRL else
                           "missed_error" if r.label in ERRL and q not in ERRL else "other")
                    recs.append({"class": cls, "system": s, "claim_id": r.claim_id, "report_id": r.report_id, "ann_id": r.ann_id, "sample": r.sample,
                                 "part": r.part, "claim_text": r.claim_text, "R1": r.label, "distortion_type": r.distortion_type, "system_label": q,
                                 "chars_T2": r.chars_T2})
    E = pd.DataFrame(recs).sort_values(["class", "claim_id", "system"]).reset_index(drop=True)
    picks = []
    counts = {}
    for cls in ("false_alarm", "missed_error", "other"):
        g = E[E["class"] == cls]
        counts[cls] = {"pairs": int(len(g)), "claims": int(g["claim_id"].nunique())}
        order = rng.permutation(len(g))
        seen = set()
        for i in order:
            r = g.iloc[i]
            if r["claim_id"] in seen or any(r["claim_id"] == x["claim_id"] for x in picks):
                continue
            seen.add(r["claim_id"]); picks.append(r.to_dict())
            if len(seen) == 10:
                break
    S = pd.DataFrame(picks)
    for c in ("R1", "system_label"):
        S[c] = S[c].map(out_label)
    S["source_T1"] = "data/sources/" + S["ann_id"] + "/T1.txt"; S["cause_code"] = ""; S["coder_note"] = ""
    S.to_csv(os.path.join(ERR, "system_errors_30.csv"), index=False)
    return {"seed": SEED_ERRSAMPLE, "n_disagreements_pool": int(len(dis)), "n_disagreement_sample": int(len(out)),
            "system_error_pool": counts, "n_system_error_sample": int(len(S))}
