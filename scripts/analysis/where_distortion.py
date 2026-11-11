"""Where distortion arises: H2 (rewritten vs copied) and H3 (headline vs body), prereg 4 and 4a "Model for H2/H3".

Weighted logistic regression with an L2 penalty: scikit-learn LogisticRegression(C=1.0, solver='lbfgs',
intercept_scaling=100); outcome = claim is CON or MIS; dummy-coded predictors: rewritten (copy ratio < 0.6 vs T1),
text part (headline, lead; reference body), outlet type (general portal, finance portal; reference agency), issuer (DVX,
EMSMN; reference CBAR); sample_weight = design weights (phase x D10 report weight, as for all RQ1 estimates).
Random sample only. Bootstrap: two-stage cluster bootstrap (domain 'random'); a replicate with no error claims, or no
error claims in a level of the tested predictor, keeps OR = 1 and is counted; > 5% degenerate replicates -> inconclusive.
Minimum information: at least 30 error claims (raw), otherwise descriptive only (inconclusive).
"""
import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from common import *

COLS = ["rewritten", "part_headline", "part_lead", "outlet_general portal", "outlet_finance portal", "issuer_DVX", "issuer_EMSMN"]


def design(d):
    X = pd.DataFrame({"rewritten": d["rewritten"].astype(float).values})
    for lev in ("headline", "lead"):
        X[f"part_{lev}"] = (d["part"] == lev).astype(float).values
    for lev in ("general portal", "finance portal"):
        X[f"outlet_{lev}"] = (d["outlet_type"] == lev).astype(float).values
    for lev in ("DVX", "EMSMN"):
        X[f"issuer_{lev}"] = (d["issuer"] == lev).astype(float).values
    return X[COLS].values


def fit(X, y, sw):
    m = LogisticRegression(C=1.0, solver="lbfgs", intercept_scaling=100, max_iter=5000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.fit(X, y, sample_weight=sw)
    return dict(zip(COLS, np.exp(m.coef_[0])))


def run_model(dom, bt, wcol):
    X = design(dom); y = dom["is_err"].values; w = dom[wcol].values
    point = fit(X, y, w)
    tested = {"H2": ("rewritten", lambda d: [d["rewritten"] == 1, d["rewritten"] == 0]),
              "H3": ("part_headline", lambda d: [d["part"] == "headline", d["part"] == "body"])}
    reps = {h: np.ones(B) for h in tested}; degen = {h: 0 for h in tested}
    allrep = {c: np.full(B, np.nan) for c in COLS}
    lv = {h: [np.asarray(m.values) for m in fn(dom)] for h, (_, fn) in tested.items()}
    for b in range(B):
        sw = w * bt.counts[b]
        pos = sw > 0
        errw = (sw * y)
        if errw.sum() == 0 or len(np.unique(y[pos])) < 2:
            for h in tested:
                degen[h] += 1
            continue
        o = fit(X[pos], y[pos], sw[pos])
        for c in COLS:
            allrep[c][b] = o[c]
        for h, (c, _) in tested.items():
            if any(errw[m].sum() == 0 for m in lv[h]):
                degen[h] += 1          # OR stays 1
            else:
                reps[h][b] = o[c]
    return point, reps, degen, allrep


def run():
    dom, bt = boot("random")
    res = {}
    n_err = int(dom["is_err"].sum())
    point, reps, degen, allrep = run_model(dom, bt, "w_rq1")
    rows = []
    tested_rep = {"rewritten": reps["H2"], "part_headline": reps["H3"]}
    for c in COLS:
        r_ = tested_rep.get(c, allrep[c])     # tested predictors: degenerate replicates kept at OR = 1 (prereg 4a)
        rows.append({"predictor": c, "OR": point[c], "lo": ci(r_)[0], "hi": ci(r_)[1],
                     "ci_rule": "degenerate reps at OR = 1" if c in tested_rep else "non-degenerate reps only (descriptive)"})
    for h, c in (("H2", "rewritten"), ("H3", "part_headline")):
        pv, _ = p_one_sided(reps[h], 1.0, ">")
        pvc, _ = p_one_sided(reps[h], 1.0, "<")
        res[h] = {"estimate_OR": point[c], "ci": ci(reps[h]), "p": pv, "p_opposite": pvc, "degenerate_reps": degen[h],
                  "degenerate_share": degen[h] / B, "too_many_degenerate": degen[h] / B > 0.05, "null": 1.0, "sesoi": 1.5,
                  "n_err_raw": n_err, "min_info_met": n_err >= 30}
    sp, sreps, sdeg, _ = run_model(dom, bt, "w_phase")
    res["sensitivity_phase_weight_only"] = {h: {"OR": sp[c], "ci": ci(sreps[h])} for h, c in (("H2", "rewritten"), ("H3", "part_headline"))}
    res["model"] = {"n_claims": int(len(dom)), "n_err_raw": n_err, "odds_ratios": {r["predictor"]: r for r in rows}}
    note = (f"Random sample, {len(dom)} human-labelled claims, {n_err} error claims (raw); prereg minimum for H2/H3 is 30, "
            f"so the model is descriptive only. L2-penalised (C = 1), which shrinks ORs toward 1. CIs: two-stage cluster bootstrap.")
    write_table(pd.DataFrame(rows), "table_regression_h2h3", "Penalised weighted logistic regression of claim-is-CON-or-MIS (odds ratios)", note=note)
    return res
