"""Estimate RQ1 prevalence and test H1 on the random sample (prereg.md sections 2-4a, D10 (c), D17).

Weights: phase design weight (D17 correction) x D10 (c) report weight n_verified / n_kept. Variance: two-stage cluster
bootstrap on the domain 'random' (2,000 replicates, seed 20261110). Pooled estimates are given without issuer weights
(primary) and with the issuer weights of prereg.md 4a (secondary): N_i = E_i * c_i / k_i, weight N_i / 20 per drawn
announcement.
Report-level prevalence: (a) S-H reports, where all claims are labelled (10% of random-sample pairs); (b) a lower bound
over all random-sample reports (share with at least one human-confirmed error claim), since outside S-H only a sample
of claims is labelled.
Outputs: tables table3a-c and analysis/figures/fig2_error_rate.{png,pdf}; the returned dict goes to numbers.json.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import *


def issuer_weights():
    out = {}
    for iss, f in (("CBAR", "cbar"), ("DVX", "tax"), ("EMSMN", "social")):
        el = pd.read_csv(p(f"sampling/eligibility_final_{f}.csv"))
        E = int((el["final"] == "eligible").sum())
        wl = pd.read_csv(p(f"sampling/walk_log2_{f}.csv"))
        c = int((wl["result"] == "drawn").sum()); k = int(wl["result"].isin(["drawn", "skip_no_coverage"]).sum())
        N = E * c / k
        out[iss] = {"E": E, "c": c, "k": k, "N_covered": N, "uncovered_share": 1 - c / k, "weight": N / 20}
    return out


def ratio(num, den, counts):
    pt = float(num.sum() / den.sum()) if den.sum() > 0 else np.nan
    with np.errstate(invalid="ignore", divide="ignore"):
        rp = (counts * num).sum(1) / (counts * den).sum(1)
    return pt, rp


def run():
    D = load(); claims = D["claims"]
    dom, bt = boot("random")
    w = dom["w_rq1"].values
    err = dom["is_err"].values.astype(float)
    res = {"n_claims_random": int((claims["sample"] == "random").sum()), "n_ref_random": int(len(dom)),
           "kish_n": kish(w), "n_err_raw": int(err.sum()), "n_raw_by_label": dom["label"].value_counts().to_dict()}
    rows = []
    # claim-level shares per label
    for l in LABELS + ["ERROR (CON+MIS)"]:
        y = (dom["label"] == l).values.astype(float) if l in LIX else err
        pt, rp = ratio(w * y, w, bt.counts)
        pu, rpu = ratio(dom["w_phase"].values * y, dom["w_phase"].values, bt.counts)
        res.setdefault("claim_share", {})[l] = {"est": pt, "ci": ci(rp), "n_raw": int(y.sum()), "est_phase_weight_only": pu, "ci_phase_weight_only": ci(rpu)}
        rows.append({"label": l, "share": pt, "lo": ci(rp)[0], "hi": ci(rp)[1], "n_raw": int(y.sum()), "est_total_retained_claims": float((dom["w_phase"].values * y).sum()),
                     "est_total_expanded_claims": float((w * y).sum())})
    write_table(pd.DataFrame(rows), "table3a_prevalence_labels", "RQ1: claim-level label distribution, random sample (design-weighted)",
                note=f"est_total_retained_claims: phase weights only, total over the {res['n_claims_random']} retained claims; est_total_expanded_claims: phase x D10 report weights (claims of all verified reports). Human-verified reference, random sample: {len(dom)} labelled claims of {res['n_claims_random']}; Kish n_eff {res['kish_n']:.1f}. "
                     "Weights: phase weight x D10 report weight. 95% percentile CIs, two-stage cluster bootstrap (2,000 reps).")
    # issuer-weighted pooled (secondary)
    iw = issuer_weights(); res["issuer_weights"] = iw
    aw = dom["issuer"].map(lambda i: iw[i]["weight"]).values
    pt, rp = ratio(w * aw * err, w * aw, bt.counts)
    res["claim_share_error_issuer_weighted"] = {"est": pt, "ci": ci(rp)}
    # breakdowns
    brows = []
    for var in ("issuer", "outlet_type", "part", "rewritten"):
        for lev, g in dom.groupby(var):
            m = (dom[var] == lev).values
            pt, rp = ratio(w * err * m, w * m, bt.counts)
            brows.append({"by": var, "level": str(lev), "error_share": pt, "lo": ci(rp)[0], "hi": ci(rp)[1], "n_ref": int(m.sum()),
                          "n_err_raw": int(err[m].sum()), "kish_n": kish(w[m])})
    bdf = pd.DataFrame(brows)
    res["by"] = {f"{r.by}={r.level}": {"est": r.error_share, "ci": [r.lo, r.hi], "n_ref": r.n_ref, "n_err_raw": r.n_err_raw} for r in bdf.itertuples()}
    write_table(bdf, "table3b_prevalence_by_stratum", "RQ1: share of CON+MIS claims by issuer, outlet type, text part and copy status (random sample)",
                note="Design-weighted; descriptive. rewritten = report copy ratio < 0.6 against T1.")
    # distortion types among MISREPRESENTED (MISLEADING in the paper) claims, weighted
    mis = (dom["label"] == "MISREPRESENTED").values
    trows = []
    for t in ["status", "scope", "actor", "inference", "dropped_condition"]:
        m = (dom["distortion_type"] == t).values & mis
        pt, rp = ratio(w * m, w * mis, bt.counts)
        trows.append({"distortion_type": t, "share_of_MIS": pt, "lo": ci(rp)[0], "hi": ci(rp)[1], "n_raw": int(m.sum())})
    res["distortion_types_random"] = {r["distortion_type"]: r for r in trows}
    # raw type counts over all samples (descriptive)
    ref = D["ref"]; mm = ref["label"] == "MISREPRESENTED"
    for r in trows:
        r["n_raw_all_samples"] = int(((ref["distortion_type"] == r["distortion_type"]) & mm).sum())
    write_table(pd.DataFrame(trows), "table3c_distortion_types", "Distortion types among MISREPRESENTED claims (random sample, weighted share; raw counts also for all samples)")
    # H1: share of MISREPRESENTED among CON+MIS claims, null 0.5, SESOI 0.6
    con = (dom["label"] == "CONTRADICTED").values.astype(float)
    pt, rp = ratio(w * mis, w * (mis + con), bt.counts)
    pv, und = p_one_sided(rp, 0.5, ">")
    pvc, _ = p_one_sided(rp, 0.5, "<")
    pts, rps = ratio(dom["w_phase"].values * mis, dom["w_phase"].values * (mis + con), bt.counts)
    res["H1"] = {"estimate": pt, "ci": ci(rp), "p": pv, "p_opposite": pvc, "undefined_reps": und, "null": 0.5, "sesoi": 0.6,
                 "n_err_raw": int(err.sum()), "n_mis_raw": int(mis.sum()), "n_con_raw": int(con.sum()), "min_info_met": bool(err.sum() >= 10),
                 "sensitivity_phase_weight_only": {"estimate": pts, "ci": ci(rps), "p": p_one_sided(rps, 0.5, ">")[0],
                                                   "note": "without the D10 (c) report weight"}}
    # report-level prevalence
    rep_err = dom.groupby("report_id")["is_err"].max()
    sh = dom[dom["set"] == "S-H"]
    shr = sh.groupby("report_id").agg(err=("is_err", "max"), rw=("rep_weight", "first"), cl=("cluster", "first"))
    k = np.array([bt.cix[c] for c in shr["cl"]])
    cnt = bt.M[:, k]
    num = shr["rw"].values * shr["err"].values; den = shr["rw"].values
    pt, rp = ratio(num, den, cnt)
    res["report_share_SH"] = {"est": pt, "ci": ci(rp), "n_reports": int(len(shr)), "n_with_error": int(shr["err"].sum())}
    allr = claims[claims["sample"] == "random"].groupby("report_id").agg(rw=("rep_weight", "first"), cl=("cluster", "first"))
    allr["err"] = allr.index.map(lambda r: int(rep_err.get(r, 0)))
    k = np.array([bt.cix[c] for c in allr["cl"]])
    pt, rp = ratio(allr["rw"].values * allr["err"].values, allr["rw"].values, bt.M[:, k])
    res["report_share_lower_bound_all"] = {"est": pt, "ci": ci(rp), "n_reports": int(len(allr)), "n_with_confirmed_error": int(allr["err"].sum())}
    # pair flags (S-H)
    pr = D["pairs"]
    res["SH_pair_flags"] = {"n_pairs": int(len(pr)), "omission": int(pr["omission"].sum()), "framing": int(pr["framing"].sum())}
    # secondary: benchmark prevalence (phase weights) and agreed-LLM gold prevalence (random)
    bd, bb = boot("benchmark")
    wb = bd["w_phase"].values
    pt, rp = ratio(wb * bd["is_err"].values, wb, bb.counts)
    res["benchmark_error_share"] = {"est": pt, "ci": ci(rp), "n_ref": int(len(bd)), "n_err_raw": int(bd["is_err"].sum()), "note": "secondary; never used for RQ1"}
    cr = claims[(claims["sample"] == "random") & (claims["A1"] == claims["A2"])]
    res["agreed_llm_gold_random"] = {"n": int(len(cr)), "error_share_report_weighted": float((cr["rep_weight"] * cr["A1"].isin(ERRL)).sum() / cr["rep_weight"].sum()),
                                     "labels": cr["A1"].value_counts().to_dict(), "note": "secondary; A1 = A2 claims only"}
    # figure 2
    os.makedirs(FIG, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), sharey=True)
    for ax, var, order in ((axes[0], "outlet_type", ["agency", "general portal", "finance portal"]), (axes[1], "part", ["headline", "lead", "body"])):
        sub = bdf[bdf["by"] == var].set_index("level").reindex(order)
        x = np.arange(len(order)); y = sub["error_share"].values * 100
        lo = (sub["error_share"] - sub["lo"]).values * 100; hi = (sub["hi"] - sub["error_share"]).values * 100
        ax.bar(x, y, color="#4C72B0", width=0.6)
        ax.errorbar(x, y, yerr=[lo, hi], fmt="none", ecolor="black", capsize=3, lw=1)
        ax.set_xticks(x); ax.set_xticklabels([f"{o}\n(n={int(sub.loc[o, 'n_ref'])})" for o in order], fontsize=8)
        ax.set_title({"outlet_type": "Outlet type", "part": "Text part"}[var], fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("CONTRADICTED + MISLEADING claims (%)", fontsize=8)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(FIG, f"fig2_error_rate.{ext}"), dpi=200)
    plt.close(fig)
    return res
