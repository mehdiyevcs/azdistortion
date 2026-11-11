"""Annotator agreement (RQ4, E7): the human annotator (R1) with the LLM annotators A1 and A2, and A1 with A2.

A1 is Claude Opus 5.5 and A2 the Codex command-line agent; R1 is the only human annotator (prereg D17).
- R1 vs A1, R1 vs A2: on the 506 claims R1 labelled; primary = design-weighted (phase weights, D17 correction) Cohen's
  kappa, overall and per label (one vs rest), with positive specific agreement (PSA); two-stage cluster bootstrap CIs
  (domain 'all'). Unweighted values and the S-H-only values are reported as well.
- A1 vs A2: census over all 3,593 claims (unweighted; cluster bootstrap over announcement clusters) and, for comparison,
  design-weighted on the 506 reference claims.
- H6 is not tested (D17 c). The calibration kappa (R1 vs R2, 69 dev claims, 0.82) is quoted from prereg D2 as a
  description of the guidelines' reliability only.
- Exploratory (prereg 7): S-A and S-N miss rates; in S-D, whom the human sided with.
"""
import numpy as np
import pandas as pd
from common import *


def pair_stats(gold, pred, w, counts):
    P = pair_onehot(gold, pred)
    pt, rp = confs(P, w, counts)
    k, po = kappa_from_conf(pt)
    out = {"kappa": float(k), "agreement": float(po), "n": int(len(gold)), "kish_n": kish(w)}
    if rp is not None:
        kr, por = kappa_from_conf(rp)
        out["kappa_ci"] = ci(kr); out["agreement_ci"] = ci(por)
    per = {}
    for l in LABELS:
        kl, psa = kappa_label(pt, l)
        d = {"kappa": float(kl), "psa": float(psa), "n_first": int(sum(np.array(gold) == l)), "n_second": int(sum(np.array(pred) == l))}
        if rp is not None:
            klr, psar = kappa_label(rp, l)
            d["kappa_ci"] = ci(klr); d["psa_ci"] = ci(psar)
        per[l] = d
    out["per_label"] = per
    return out, pt


def run():
    D = load(); ref = D["ref"]; claims = D["claims"]
    dom, bt = boot("all")
    res = {"note": "R1 = the only human annotator (D17); weighted = phase design weights; CIs = two-stage cluster bootstrap, 2,000 reps, seed 20261110"}
    rows, conf_rows = [], []
    w = dom["w_phase"].values
    for other in ("A1", "A2"):
        st, pt = pair_stats(dom["label"].tolist(), dom[other].tolist(), w, bt.counts)
        res[f"R1_vs_{other}_weighted"] = st
        un, ptu = pair_stats(dom["label"].tolist(), dom[other].tolist(), np.ones(len(dom)), bt.counts)
        res[f"R1_vs_{other}_unweighted"] = un
        sh = dom["set"] == "S-H"
        shs, _ = pair_stats(dom.loc[sh, "label"].tolist(), dom.loc[sh, other].tolist(), np.ones(sh.sum()), bt.sub(sh))
        res[f"R1_vs_{other}_SH"] = shs
        for tag, s in (("weighted (all 506)", st), ("unweighted (all 506)", un), ("S-H only (162)", shs)):
            rows.append({"pair": f"R1-{other}", "set": tag, "label": "ALL", "kappa": s["kappa"], "kappa_lo": s.get("kappa_ci", [None])[0],
                         "kappa_hi": s.get("kappa_ci", [None, None])[1], "agreement": s["agreement"], "psa": np.nan, "n": s["n"]})
            for l in LABELS:
                d = s["per_label"][l]
                rows.append({"pair": f"R1-{other}", "set": tag, "label": l, "kappa": d["kappa"], "kappa_lo": (d.get("kappa_ci") or [None])[0],
                             "kappa_hi": (d.get("kappa_ci") or [None, None])[1], "agreement": np.nan, "psa": d["psa"], "n": d["n_first"]})
        for tag, cm in (("weighted", pt), ("raw", ptu)):
            C = cm.reshape(5, 5)
            for i, g in enumerate(LABELS):
                conf_rows.append({"pair": f"R1-{other}", "count": tag, "R1 label": g, **{l: float(C[i, j]) for j, l in enumerate(LABELS)}})
    # A1 vs A2 on the reference (weighted)
    st, _ = pair_stats(dom["A1"].tolist(), dom["A2"].tolist(), w, bt.counts)
    res["A1_vs_A2_weighted_reference"] = st
    # A1 vs A2 census of all claims: cluster bootstrap (stage 1 only; no phase-2 sampling here)
    cix = np.array([bt.cix[c] for c in claims["cluster"]])
    cnt = bt.M[:, cix]
    st2, pta = pair_stats(claims["A1"].tolist(), claims["A2"].tolist(), np.ones(len(claims)), cnt)
    res["A1_vs_A2_all_claims"] = st2
    for tag, s in (("all 3,593 claims (census)", st2), ("weighted (reference 506)", st)):
        rows.append({"pair": "A1-A2", "set": tag, "label": "ALL", "kappa": s["kappa"], "kappa_lo": s["kappa_ci"][0], "kappa_hi": s["kappa_ci"][1],
                     "agreement": s["agreement"], "psa": np.nan, "n": s["n"]})
        for l in LABELS:
            d = s["per_label"][l]
            rows.append({"pair": "A1-A2", "set": tag, "label": l, "kappa": d["kappa"], "kappa_lo": d["kappa_ci"][0], "kappa_hi": d["kappa_ci"][1],
                         "agreement": np.nan, "psa": d["psa"], "n": d["n_first"]})
    C = pta.reshape(5, 5)
    for i, g in enumerate(LABELS):
        conf_rows.append({"pair": "A1-A2", "count": "raw (all claims)", "R1 label": "A1=" + g, **{l: float(C[i, j]) for j, l in enumerate(LABELS)}})
    write_table(pd.DataFrame(rows), "table7_agreement", "Agreement: R1 (only human) vs A1/A2, and A1 vs A2; kappa overall and per label (one vs rest), PSA",
                note="Weighted = phase design weights (D17 correction); CIs: two-stage cluster bootstrap (2,000 reps). H6 not tested (D17 c). "
                     "Calibration (R1 vs R2, 69 dev claims, before the main study): kappa 0.82, descriptive only.")
    write_table(pd.DataFrame(conf_rows), "agreement_confusion", "Confusion matrices: rows = first annotator (R1, or A1), columns = second")
    res["calibration_kappa_R1_R2_dev"] = {"value": 0.82, "n_claims": 69, "source": "prereg D2 (calibration before the main study)",
                                          "use": "descriptive only (D17 c)"}
    res["H6"] = "not tested (D17 c: one human annotator)"
    # exploratory: S-A / S-N miss rates, S-D sides
    ex = {}
    for s, agreed in (("S-A", "SUPPORTED"), ("S-N", "NOT_IN_SOURCE")):
        m = (dom["set"] == s).values
        x = dom[m]
        ne = (x["label"] != agreed).astype(float).values
        er = x["is_err"].astype(float).values
        cs = bt.sub(m)
        with np.errstate(invalid="ignore"):
            r_ne = (cs * ne).sum(1) / cs.sum(1); r_er = (cs * er).sum(1) / cs.sum(1)
        ex[s] = {"n": int(m.sum()), "share_R1_differs": float(ne.mean()), "share_R1_differs_ci": ci(r_ne), "n_R1_differs": int(ne.sum()),
                 "share_R1_error": float(er.mean()), "share_R1_error_ci": ci(r_er), "n_R1_error": int(er.sum()),
                 "R1_labels": x["label"].value_counts().to_dict(),
                 "estimated_error_claims_in_stratum": float(er.mean() * D["weights"]["N"][s])}
    sd = dom[(dom["set"] == "S-D")]
    dis = sd[sd["A1"] != sd["A2"]]
    side = np.where(dis["label"] == dis["A1"], "A1", np.where(dis["label"] == dis["A2"], "A2", "neither"))
    agr = sd[sd["A1"] == sd["A2"]]
    ex["S-D"] = {"n": int(len(sd)), "n_A1_ne_A2": int(len(dis)), "sided": pd.Series(side).value_counts().to_dict(),
                 "n_A1_eq_A2": int(len(agr)), "human_agrees_when_A1_eq_A2": int((agr["label"] == agr["A1"]).sum()),
                 "R1_labels": sd["label"].value_counts().to_dict()}
    res["exploratory"] = ex
    res["annotation_hours_total"] = "7-8"
    res["annotation_time_note"] = ("self-reported by the human annotator for all 686 items (S-H 162 claims + phase 2 344 + edit check 180), "
                                   "about 0.6-0.7 min per item; per-pair minutes not recorded (logs/annotation_time.md)")
    return res
