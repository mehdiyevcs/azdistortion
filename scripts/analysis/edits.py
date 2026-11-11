"""Score E5 (edit set v2) and test H5 (recall on natural MISREPRESENTED claims vs on accepted distortion edits).

MISREPRESENTED is called MISLEADING in the paper. Rules: prereg sections 4, 4a and 6, D14, D17 (d), D17 addendum (d1)
and D17 correction.

Edits used: R1-accepted edits only (verdict = intended label and base_supported = 1): distortion edits (up to 150 checked)
and contradiction edits (30 cross-check items). The 120 contradiction edits without a human check are reported separately
as a secondary, LLM-generated set and never pooled with accepted ones.
Hit rule: exact label (recall of MISREPRESENTED on MIS edits / natural MIS, of CONTRADICTED on CON edits); the
error-detection hit (CON or MIS) is reported as secondary.
H5 (per LLM, C2): natural recall (design-weighted, all samples, R1 MIS claims) minus post-stratified edit recall: type
weights = shares of the design-weighted natural MIS claims over R1's distortion types; edit recall = weighted mean of
per-type recall over the types present in both sets (edit type = the intended type fixed before generation; R1's type on
the edit as a sensitivity analysis); if natural MIS types without accepted edits hold > 20% of the natural MIS weight, H5
is inconclusive. Joint bootstrap: edits carry the multiplicity of their base claim's announcement cluster in the same
replicates as the natural claims. E5 runs that do not exist yet are reported as pending.
"""
import json, os
import numpy as np
import pandas as pd
from common import *

TYPES = ["status", "scope", "actor", "inference", "dropped_condition"]


def edit_preds(runs):
    """system -> condition -> {edit_id: label}; C2 = merged run, else C2t2 for has_t2 edits + C1 for the rest."""
    out = {}
    for k, v in runs.items():
        if v["exp"] == "E5":
            key = v["system"] + (f"@seed{v['seed']}" if "seed" in v and v["exp"] == "E5" and "|seed" in k else "")
            out.setdefault(key, {})[v["condition"]] = v["preds"]
    R = os.path.join(MAIN, "runs")
    for s in SYSTEMS_LLM:
        if s in out and "C2" not in out[s] and "C1" in out[s]:
            t2 = os.path.join(R, f"e5_{s}_C2t2_edit", "predictions.csv")
            if os.path.exists(t2):
                d = pd.read_csv(t2)
                out[s]["C2"] = {**out[s]["C1"], **dict(zip(d["claim_id"], d["label"].astype(str)))}
    return out


def run(runs):
    D = load(); ed = D["edits"].copy(); es = D["edit_set"]; claims = D["claims"]
    ed = ed.merge(es[["edit_id", "ann_id", "claim_id", "target_type", "base_id"]], on="edit_id", how="left")
    clmap = dict(zip(claims["ann_id"], claims["cluster"]))
    ed["cluster"] = ed["ann_id"].map(clmap)
    ed["distortion_type"] = ed["distortion_type"].fillna("")
    ed["intended_distortion_type"] = ed["intended_distortion_type"].fillna("")
    res = {"edits_checked": {"MIS": int((ed.kind == "MIS").sum()), "CON": int((ed.kind == "CON").sum())},
           "edits_accepted": {"MIS": int(((ed.kind == "MIS") & (ed.accepted == 1)).sum()), "CON": int(((ed.kind == "CON") & (ed.accepted == 1)).sum())},
           "verdicts": {k: g["verdict"].value_counts().to_dict() for k, g in ed.groupby("kind")},
           "base_supported_0": int((ed["base_supported"].astype(str) != "1").sum())}
    acc_mis = ed[(ed.kind == "MIS") & (ed.accepted == 1)]
    res["type_match_accepted_MIS"] = {"n": int(len(acc_mis)), "match": int(acc_mis["type_match"].sum()),
                                      "share": float(acc_mis["type_match"].mean()) if len(acc_mis) else None,
                                      "crosstab": pd.crosstab(acc_mis["intended_distortion_type"], acc_mis["distortion_type"]).to_dict()}
    checked = set(ed["edit_id"])
    unchecked = es[~es["edit_id"].isin(checked)].copy()
    unchecked["cluster"] = unchecked["ann_id"].map(clmap)
    res["edits_unchecked"] = unchecked["kind"].value_counts().to_dict()
    ep = edit_preds(runs)
    res["e5_systems_found"] = {s: sorted(c) for s, c in ep.items()}
    rows = []
    sets = {"accepted MIS": acc_mis, "accepted CON": ed[(ed.kind == "CON") & (ed.accepted == 1)], "unchecked CON (secondary, LLM-generated)": unchecked[unchecked["kind"].str.upper().str.startswith("CON")]}
    bases = ed[ed["base_supported"].astype(str) == "1"].drop_duplicates("base_id")
    for s, conds in sorted(ep.items()):
        for c, pr in sorted(conds.items()):
            for name, d in sets.items():
                ids = [x for x in d["edit_id"] if x in pr]
                if not ids:
                    continue
                lab = np.array([norm_pred(pr[x]) for x in ids])
                tgt = "MISREPRESENTED" if "MIS" in name else "CONTRADICTED"
                row = {"system": s, "condition": c, "set": name, "n": len(ids), "recall_exact": float((lab == tgt).mean()),
                       "recall_error_label": float(np.isin(lab, list(ERRL)).mean())}
                if "MIS" in name:
                    tt = d.set_index("edit_id").loc[ids, "intended_distortion_type"].values
                    for t in TYPES:
                        m = tt == t
                        row[f"recall {t}"] = float((lab[m] == tgt).mean()) if m.any() else np.nan
                        row[f"n {t}"] = int(m.sum())
                else:
                    tt = d.set_index("edit_id").loc[ids, "target_type"].values
                    for t in sorted(set(tt)):
                        row[f"CON recall {t}"] = float((lab[tt == t] == tgt).mean())
                        row[f"CON n {t}"] = int((tt == t).sum())
                rows.append(row)
            # SUPPORTED retention on the R1-confirmed base claims (E1 predictions of the same system and condition)
            e1 = runs.get(f"e1|{s}|{c}|random")
            if e1:
                b = [x for x in bases["claim_id"] if x in e1["preds"]]
                rows.append({"system": s, "condition": c, "set": "originals (SUPPORTED retention)", "n": len(b),
                             "recall_exact": float(np.mean([norm_pred(e1["preds"][x]) == "SUPPORTED" for x in b])) if b else np.nan})
    if rows:
        write_table(pd.DataFrame(rows), "table6_edits", "Edit set v2: recall on R1-accepted edits by type; SUPPORTED retention on originals",
                    note="Accepted = R1 verdict equals the intended label and base claim confirmed SUPPORTED (D17 addendum d1). "
                         "Unchecked contradiction edits are a secondary, LLM-generated set (D17 d). recall_exact: exact label; recall_error_label: CON or MIS.")
    res["table6_rows"] = rows
    # ---------------- H5
    dom, bt = boot("all")
    mis = (dom["label"] == "MISREPRESENTED").values
    w = dom["w_phase"].values
    nat_t = dom["distortion_type"].values
    kidx = np.array([bt.cix[c] for c in acc_mis["cluster"]]) if len(acc_mis) else np.array([], int)
    h5 = {}
    natw = {t: float((w * mis * (nat_t == t)).sum()) for t in TYPES}
    tot = sum(natw.values())
    res["natural_MIS"] = {"n_raw": int(mis.sum()), "weighted_type_shares": {t: natw[t] / tot for t in TYPES} if tot else None,
                          "raw_types": pd.Series(nat_t[mis]).value_counts().to_dict(), "min_info_met": bool(mis.sum() >= 15)}
    for s in SYSTEMS_LLM:
        nat_pred = {}
        for smp in ("random", "benchmark"):
            if f"e1|{s}|C2|{smp}" in runs:
                nat_pred.update(runs[f"e1|{s}|C2|{smp}"]["preds"])
        if s not in ep or "C2" not in ep[s]:
            h5[s] = {"status": "pending", "note": "E5 C2 predictions not found"}
            continue
        epr = ep[s]["C2"]
        out = {}
        for typecol, tag in (("intended_distortion_type", "primary_intended_type"), ("distortion_type", "sensitivity_R1_type")):
            have = np.array([x in epr for x in acc_mis["edit_id"]])
            if len(acc_mis) == 0 or not have.all():
                out[tag] = {"status": "pending", "note": f"{(~have).sum()} accepted edits without a C2 prediction"}
                continue
            hit_e = np.array([norm_pred(epr[x]) == "MISREPRESENTED" for x in acc_mis["edit_id"]], float)
            et = acc_mis[typecol].values
            hit_n = np.array([norm_pred(nat_pred.get(c, "SUPPORTED")) == "MISREPRESENTED" for c in dom["claim_id"]], float)
            assert all(c in nat_pred for c in dom.loc[mis, "claim_id"])
            covered = [t for t in TYPES if natw[t] > 0 and (et == t).any()]
            uncovered_share = 1 - sum(natw[t] for t in covered) / tot

            def stat(wn, me):
                """wn: natural weights (n,), me: edit multiplicities (n_edits,) -> (natural recall, edit recall, diff)."""
                den = (wn * mis).sum()
                if den <= 0:
                    return np.nan, np.nan, np.nan
                nr = (wn * mis * hit_n).sum() / den
                tw, tr = [], []
                for t in covered:
                    mt = et == t
                    if me[mt].sum() > 0:
                        tw.append((wn * mis * (nat_t == t)).sum()); tr.append((me[mt] * hit_e[mt]).sum() / me[mt].sum())
                if not tw or sum(tw) <= 0:
                    return nr, np.nan, np.nan
                er = float(np.dot(tw, tr) / sum(tw))
                return nr, er, nr - er

            nr, er, d = stat(w, np.ones(len(acc_mis)))
            reps = np.array([stat(w * bt.counts[b], bt.M[b, kidx].astype(float))[2] for b in range(B)])
            pv, und = p_one_sided(reps, 0.0, "<"); pvc, _ = p_one_sided(reps, 0.0, ">")
            raw_edit = float(hit_e.mean())
            # secondary: error-detection hit
            hit_e2 = np.array([norm_pred(epr[x]) in ERRL for x in acc_mis["edit_id"]], float)
            hit_n2 = np.array([norm_pred(nat_pred.get(c, "SUPPORTED")) in ERRL for c in dom["claim_id"]], float)
            nr2 = (w * mis * hit_n2).sum() / (w * mis).sum()
            out[tag] = {"natural_recall": nr, "edit_recall_poststratified": er, "edit_recall_raw": raw_edit, "estimate": d, "ci": ci(reps),
                        "p": pv, "p_opposite": pvc, "undefined_reps": und, "sesoi": -0.05, "covered_types": covered,
                        "uncovered_natural_weight_share": uncovered_share, "inconclusive_coverage": uncovered_share > 0.20,
                        "n_natural_MIS_raw": int(mis.sum()), "n_edits": int(len(acc_mis)),
                        "secondary_error_hit": {"natural_recall": float(nr2), "edit_recall_raw": float(hit_e2.mean())}}
        out["status"] = "done" if all(isinstance(v, dict) and v.get("status") != "pending" for v in out.values()) else "pending"
        h5[s] = out
    res["H5"] = h5
    # edit length by type (prereg 4: type length distributions are reported)
    es2 = es.copy(); es2["len_words"] = es2["edited_claim"].astype(str).str.split().str.len()
    acc_ids = set(acc_mis["edit_id"])
    lr = []
    for t in TYPES:
        a = es2[es2["edit_id"].isin(acc_ids) & (es2["target_type"] == t)]["len_words"]
        nm = dom.loc[mis & (nat_t == t), "claim_text"].astype(str).str.split().str.len()
        lr.append({"type": t, "edits_n": int(len(a)), "edits_median_words": float(a.median()) if len(a) else np.nan,
                   "natural_n": int(len(nm)), "natural_median_words": float(nm.median()) if len(nm) else np.nan})
    write_table(pd.DataFrame(lr), "table_edit_lengths", "Length (words) of accepted distortion edits and natural MISLEADING claims by type")
    res["lengths_by_type"] = lr
    return res
