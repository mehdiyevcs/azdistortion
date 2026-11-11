"""Score the detection systems: E1 (main grid, H4), E3 (retrieval), E4 (prompt variants), E10 (two-pass judge),
run-to-run stability, the non-LLM systems and H7 (each when its prediction files exist).

Scoring (prereg 4): against the human-verified reference (labels of the human annotator R1, D17) with phase design weights; macro-F1 over the labels
with >= 10 raw claims in the reference (fixed once, from all 506 claims, before any prediction is read); per-label F1 from
the weighted confusion matrix (zero_division 0); binary error detection (CON or MIS vs rest) and the false-alarm rate on
gold SUPPORTED as secondary metrics. Invalid outputs (not one of the five labels) are scored as SUPPORTED and counted.
CIs: two-stage cluster bootstrap (prereg 4a: announcement clusters everywhere; 2,000 reps, seed 20261110), with the same
replicates for every system of a domain, so differences are paired.
H4: per LLM system, macro-F1(C1) - macro-F1(C0) and macro-F1(C2) - macro-F1(C1) on the random-sample claims whose
announcement has a full text (has_t2 = 1 and not t1_is_act; D3 and D3 addendum), one-sided bootstrap p, Holm over 8.
Benchmark C2 of the t1_is_act announcements (DVX-4572/4629/4631/4878, DVX-4587/5080) takes the C1 prediction where a C1
run exists (D3 addendum).
"""
import glob, hashlib, json, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import *

ROLE = {"E1": "main", "NONLLM": "main", "E10": "exploratory (D16)", "E2VAR": "E2 variant (secondary)", "E3NLI": "E3 retrieval k (exploratory)",
        "E3": "E3 retrieval (exploratory)", "E4": "E4 prompt (exploratory)"}
ORDER = ["haiku", "sonnet", "gpt55", "qwen", "majority", "logreg", "gbm", "nli", "haiku_2pass"]
LSET = None          # macro-F1 label set, fixed in run() from the reference counts
SKIP_DIRS = {"dev_smoke", "dev_choice", "apicache_haiku_C2_10", "apicache_sonnet_C2_10"}
ENC_SEED = re.compile(r"^(xlmr|azbert|mdeberta)s([123])(_edits|_hum)?$")      # exported E2 encoder runs, one per training seed


def read_preds(path):
    d = pd.read_csv(path, usecols=lambda c: c in {"claim_id", "label", "error"})
    return dict(zip(d["claim_id"], d["label"].fillna("").astype(str)))


def discover():
    """Every scorable prediction set: key -> dict(exp, system, condition, sample, preds, path, seed)."""
    D = load(); claims = D["claims"]
    act = set(claims.loc[claims["t1_is_act"] == 1, "claim_id"])
    ids_edit = set(D["edit_set"]["edit_id"])
    skipped = []
    R = os.path.join(MAIN, "runs")
    out = {}
    for d in sorted(os.listdir(R)):
        m = re.match(r"^e1_(\w+?)_(C0|C1|C2)_(random|benchmark)$", d)
        if m and m.group(1) in SYSTEMS_LLM and os.path.exists(os.path.join(R, d, "predictions.csv")):
            s, c, smp = m.groups()
            pr = read_preds(os.path.join(R, d, "predictions.csv"))
            assert set(claims.loc[claims["sample"] == smp, "claim_id"]) <= set(pr), f"incomplete E1 run {d}"
            out[f"e1|{s}|{c}|{smp}"] = dict(exp="E1", system=s, condition=c, sample=smp, preds=read_preds(os.path.join(R, d, "predictions.csv")), path=f"runs/{d}")
    # non-LLM systems: only the exported runs listed in runs/nonllm_inputs/exported_runs.csv (sha256 checked); the
    # working folders runs/nonllm_* hold the same predictions under other names and are not read
    exl = os.path.join(R, "nonllm_inputs", "exported_runs.csv")
    exported = pd.read_csv(exl) if os.path.exists(exl) else pd.DataFrame(columns=["run_id", "predictions_sha256"])
    for rid, h in zip(exported["run_id"], exported["predictions_sha256"]):
        fp = os.path.join(R, rid, "predictions.csv")
        if not os.path.exists(fp):
            skipped.append({"file": f"runs/{rid}", "why": "listed but missing"}); continue
        if hashlib.sha256(open(fp, "rb").read()).hexdigest() != h:
            skipped.append({"file": f"runs/{rid}", "why": "sha256 differs from exported_runs.csv"}); continue
        m1 = re.match(r"^e1_(\w+?)_(C0|C1|C2)_(random|benchmark)$", rid)
        m2 = re.match(r"^e2_(\w+?)_(edits|hum)_(C0|C1|C2)_(random|benchmark)$", rid)
        m3 = re.match(r"^e3_nli_k(\d)_(C2)_(random|benchmark)$", rid)
        if m1:
            s, c, smp = m1.groups(); key, exp, sysn, cond = f"nl|{s}|{c}|{smp}", "NONLLM", s, c
        elif m2:
            s, var, c, smp = m2.groups(); key, exp, sysn, cond = f"e2|{s}_{var}|{c}|{smp}", "E2VAR", f"{s}_{var}", c
        elif m3:
            k_, c, smp = m3.groups(); key, exp, sysn, cond = f"e3nli|nli_k{k_}|{c}|{smp}", "E3NLI", f"nli_k{k_}", c
        else:
            continue                 # e5_* runs are read by the E5 rule below
        pr = read_preds(fp)
        if not set(claims.loc[claims["sample"] == smp, "claim_id"]) <= set(pr):
            skipped.append({"file": f"runs/{rid}", "why": "incomplete"}); continue
        out[key] = dict(exp=exp, system=sysn, condition=cond, sample=smp, preds=pr, path=f"runs/{rid}")
    # prereg D3 addendum: benchmark C2 = C1 for t1_is_act claims
    fixes = {}
    for k, v in list(out.items()):
        if v["exp"] in ("E1", "NONLLM", "E2VAR") and v["condition"] == "C2" and v["sample"] == "benchmark":
            k1 = k.replace("|C2|", "|C1|")
            n = 0
            if k1 in out:
                for cid in act & set(v["preds"]):
                    if v["preds"][cid] != out[k1]["preds"].get(cid):
                        n += 1
                    v["preds"][cid] = out[k1]["preds"][cid]
            fixes[f"{v['exp']}:{v['system']}"] = {"changed": n, "c1_available": k1 in out}
    for d in sorted(os.listdir(R)):
        m = re.match(r"^e3_haiku_(bm25|e5)_k(\d)$", d)
        if m:
            out[f"e3|haiku|{m.group(1)}_k{m.group(2)}|e3"] = dict(exp="E3", system="haiku", condition=f"{m.group(1)} k={m.group(2)}", sample="e3",
                                                               preds=read_preds(os.path.join(R, d, "predictions.csv")), path=f"runs/{d}")
        m = re.match(r"^e4t_haiku_C2_(v\d)_random$", d)
        if m:
            out[f"e4|haiku|{m.group(1)}|random"] = dict(exp="E4", system="haiku", condition=m.group(1), sample="random",
                                                       preds=read_preds(os.path.join(R, d, "predictions.csv")), path=f"runs/{d}")
        m = re.match(r"^stab_(\w+)_C2_(r\d)$", d)
        if m:
            out[f"stab|{m.group(1)}|{m.group(2)}|random"] = dict(exp="STAB", system=m.group(1), condition=m.group(2), sample="random",
                                                               preds=read_preds(os.path.join(R, d, "predictions.csv")), path=f"runs/{d}")
        m = re.match(r"^e5_(\w+?)_(C0|C1|C2)_edit$", d)
        if m and os.path.exists(os.path.join(R, d, "predictions.csv")):
            meta = os.path.join(R, d, "meta.json")
            complete = True
            if os.path.exists(meta):
                mj = json.load(open(meta)); complete = mj.get("complete", True) and not mj.get("partial", False)
            pr = read_preds(os.path.join(R, d, "predictions.csv"))
            if not ids_edit <= set(pr):      # a cost slice or a run still in progress: not scored
                skipped.append({"file": f"runs/{d}", "why": f"incomplete {len(set(pr) & ids_edit)}/{len(ids_edit)} edits"})
                continue
            out[f"e5|{m.group(1)}|{m.group(2)}|edit"] = dict(exp="E5", system=m.group(1), condition=m.group(2), sample="edit",
                                                            preds=pr, path=f"runs/{d}", complete=complete)
    # E10 combination (D16)
    for smp in ("random", "benchmark"):
        a, b = os.path.join(R, f"e10_haiku_literal_{smp}", "predictions.csv"), os.path.join(R, f"e10_haiku_implicature_{smp}", "predictions.csv")
        if os.path.exists(a) and os.path.exists(b):
            lit, imp = read_preds(a), read_preds(b)
            comb = {}
            for cid, l in lit.items():
                i = imp.get(cid, "")
                if l == "CONTRADICTED":
                    comb[cid] = "CONTRADICTED"
                elif l == "UNASSESSABLE":
                    comb[cid] = "UNASSESSABLE"
                elif i == "MISREPRESENTED" and l in ("SUPPORTED", "NOT_IN_SOURCE"):
                    comb[cid] = "MISREPRESENTED"
                else:
                    comb[cid] = l
            out[f"e10|haiku_2pass|C2|{smp}"] = dict(exp="E10", system="haiku_2pass", condition="C2", sample=smp, preds=comb,
                                                    path=f"runs/e10_haiku_literal_{smp}", path2=f"runs/e10_haiku_implicature_{smp}")
    # H7 selection files (sys_select.py: predictions_h7_<cond>*.csv) anywhere under runs/
    ids_nat = set(claims["claim_id"])
    sample_of = dict(zip(claims["claim_id"], claims["sample"])).get
    n_by_sample = claims["sample"].value_counts().to_dict()
    for root, dirs, files in os.walk(R):
        rel = os.path.relpath(root, R)
        if rel.split(os.sep)[0] in SKIP_DIRS:
            continue
        for fn in files:
            if not (fn.startswith("predictions_h7_") and fn.endswith(".csv")):   # H7 selection output only
                continue
            path = os.path.join(root, fn)
            try:
                d = pd.read_csv(path)
            except Exception:
                continue
            if not {"claim_id", "condition", "system", "label"} <= set(d.columns):
                continue
            if "seed" not in d.columns:
                d["seed"] = "na"
            d["seed"] = d["seed"].astype(str)
            tag = os.path.relpath(path, MAIN)
            for (sysn, cond, seed), g in d.groupby(["system", "condition", "seed"]):
                if g["claim_id"].duplicated().any():
                    skipped.append({"file": tag, "system": sysn, "condition": cond, "seed": seed, "why": "duplicate claim ids"}); continue
                nat = g[g["claim_id"].isin(ids_nat)]; ed = g[g["claim_id"].isin(ids_edit)]
                if len(nat):
                    smps = sorted(set(nat["claim_id"].map(sample_of)))
                    need = sum(n_by_sample[s] for s in smps)
                    if len(nat) < need:      # a file still being written, or a partial run: not scored
                        skipped.append({"file": tag, "system": sysn, "condition": cond, "seed": seed, "why": f"incomplete {len(nat)}/{need}"})
                    else:
                        smp = smps[0] if len(smps) == 1 else "all"
                        out[f"nonllm|{sysn}|{cond}|{smp}|seed{seed}|{tag}"] = dict(exp="NONLLM", system=str(sysn), condition=str(cond), sample=smp, seed=seed,
                                                                                 preds=dict(zip(nat["claim_id"], nat["label"].astype(str))), path=tag)
                if len(ed):
                    out[f"e5|{sysn}|{cond}|edit|seed{seed}|{tag}"] = dict(exp="E5", system=str(sysn), condition=str(cond), sample="edit", seed=seed,
                                                                        preds=dict(zip(ed["claim_id"], ed["label"].astype(str))), path=tag, complete=True)
    fixes["nonllm_skipped"] = skipped
    return out, fixes


def score(preds, domain, mask=None):
    """Metrics of one prediction set on one bootstrap domain; returns (dict, replicate arrays)."""
    dom, bt = boot(domain)
    have = dom["claim_id"].isin(set(preds)).to_numpy(copy=True)
    if mask is not None:
        have &= np.asarray(mask, bool)
    sub = dom[have]
    if len(sub) == 0:
        return None, None
    pr = [preds[c] for c in sub["claim_id"]]
    invalid = sum(1 for x in pr if x not in LIX)
    P = pair_onehot(sub["label"].tolist(), pr)
    w = sub["w_phase"].values
    pt, rp = confs(P, w, bt.sub(have))
    res = {"n": int(len(sub)), "kish_n": kish(w), "invalid_scored_supported": invalid}
    reps = {"macro_f1": macro_f1(rp, LSET)}
    res["macro_f1"] = float(macro_f1(pt, LSET)); res["macro_f1_ci"] = ci(reps["macro_f1"])
    fp, fr = f1_from_conf(pt, LABELS), f1_from_conf(rp, LABELS)
    for l in LABELS:
        res[f"f1_{l}"] = float(fp[l]); res[f"f1_{l}_ci"] = ci(fr[l]); reps[f"f1_{l}"] = fr[l]
        pr_, rc_ = prf_label(pt, l); res[f"recall_{l}"] = float(rc_); res[f"precision_{l}"] = float(pr_)
        reps[f"recall_{l}"] = prf_label(rp, l)[1]
    bp, br = binary_metrics(pt), binary_metrics(rp)
    for k in bp:
        res[k] = float(bp[k]); res[k + "_ci"] = ci(br[k]); reps[k] = br[k]
    return res, reps


def domain_for(sample):
    return {"random": "random", "benchmark": "benchmark", "all": "all", "e3": "all", "edit": None}[sample]


def run():
    global LSET
    D = load(); ref = D["ref"]; claims = D["claims"]
    LSET = lab_set(ref)
    res = {"label_set_macro_f1": LSET, "label_counts_reference": ref["label"].value_counts().to_dict()}
    runs, fixes = discover()
    res["d3_benchmark_c2_from_c1"] = fixes
    res["discovered"] = sorted(runs)
    scored, reps_all = {}, {}

    def put(key, sample, s, r):
        scored[(key, sample)] = s; reps_all[(key, sample)] = r

    for k, v in runs.items():
        if v["exp"] in ("E5", "STAB"):
            continue
        if v["exp"] == "NONLLM":
            for smp in (("random", "benchmark", "all") if v["sample"] == "all" else (v["sample"],)):
                s, r = score(v["preds"], smp)
                if s:
                    put(k, "pooled" if smp == "all" else smp, s, r)
            continue
        s, r = score(v["preds"], domain_for(v["sample"]))
        if s:
            put(k, v["sample"], s, r)
    # pooled random + benchmark per system/condition (E1, E10)
    for k, v in runs.items():
        if v["exp"] in ("E1", "E10", "NONLLM", "E2VAR", "E3NLI") and v["sample"] == "random":
            kb = k.replace("|random", "|benchmark")
            if kb in runs:
                pooled = {**v["preds"], **runs[kb]["preds"]}
                s, r = score(pooled, "all")
                put(k.replace("|random", "|pooled"), "pooled", s, r)
    # long table
    rows = []
    for (k, smp), s in sorted(scored.items()):
        v = runs.get(k) or runs.get(k.replace("|pooled", "|random"))
        row = {"exp": v["exp"], "role": ROLE.get(v["exp"], ""), "system": SYS_NAME.get(v["system"], v["system"]), "condition": v["condition"], "sample": smp, "seed": v.get("seed", ""),
               "n": s["n"], "kish_n": s["kish_n"], "macro_f1": s["macro_f1"], "macro_lo": s["macro_f1_ci"][0], "macro_hi": s["macro_f1_ci"][1]}
        for l in LABELS:
            row[f"F1 {l}"] = s[f"f1_{l}"]
        row.update({"err_P": s["err_precision"], "err_R": s["err_recall"], "err_F1": s["err_f1"], "false_alarm": s["false_alarm"],
                    "invalid": s["invalid_scored_supported"], "source": v["path"]})
        rows.append(row)
    long = pd.DataFrame(rows)
    write_table(long, "systems_all_scores", "All system scores against the weighted human-verified reference",
                note=f"macro-F1 over {', '.join(LSET)} (labels with >= 10 raw reference claims). Weighted per-label F1. CIs: two-stage cluster bootstrap.")
    res["scores"] = {f"{k}@{smp}": s for (k, smp), s in scored.items()}
    # Table 5 (E1 LLMs + non-LLM): macro-F1 [CI] and MIS F1 per condition
    t5 = []
    sys_list = sorted({v["system"] for v in runs.values() if v["exp"] in ("E1", "E10", "NONLLM") and not ENC_SEED.match(v["system"])},
                      key=lambda s: (ORDER.index(s) if s in ORDER else len(ORDER), s))
    for sname in sys_list:
        for smp, conds in (("random", ["C0", "C1", "C2"]), ("benchmark", ["C1", "C2"]), ("pooled", ["C2"])):
            row = {"system": SYS_NAME.get(sname, sname), "sample": smp}
            anyv = False
            for c in conds:
                hit = [(kk, s) for (kk, ss), s in scored.items() if ss == smp and kk.split("|")[1] == sname and kk.split("|")[2] == c
                       and (kk.startswith("e1|") or kk.startswith("e10|") or kk.startswith("nl|"))]
                if hit:
                    kk, s = hit[0]
                    anyv = True
                    row[f"{c} macro-F1"] = f"{s['macro_f1']:.3f} [{f(s['macro_f1_ci'][0])}, {f(s['macro_f1_ci'][1])}]"
                    row[f"{c} F1 MISREPRESENTED"] = round(s["f1_MISREPRESENTED"], 3)
                    row[f"{c} n"] = s["n"]
                    if len(hit) > 1:
                        row[f"{c} note"] = f"{len(hit)} prediction sets (seeds/files); first shown, all in systems_all_scores"
            if anyv:
                t5.append(row)
    # E2 encoders: mean over training seeds 1-3 (prereg: mean and range for neural encoders); CI from the seed-mean of the
    # paired bootstrap replicates (as for H7)
    enc = {}
    for (kk, smp), s_ in scored.items():
        parts = kk.split("|")
        m = ENC_SEED.match(parts[1]) if len(parts) > 2 else None
        if not m or parts[0] not in ("nl", "e2"):
            continue
        base = m.group(1) + (m.group(3) or "")
        enc.setdefault((base, parts[2], smp), []).append((m.group(2), s_, reps_all[(kk, smp)]))
    erows_enc = []
    for (base, c, smp), lst in sorted(enc.items()):
        lst.sort(key=lambda t: t[0])
        mf = [t[1]["macro_f1"] for t in lst]; mis = [t[1]["f1_MISREPRESENTED"] for t in lst]
        rep = np.mean([t[2]["macro_f1"] for t in lst], axis=0)
        erows_enc.append({"system": base, "condition": c, "sample": smp, "n_seeds": len(lst), "seeds": ",".join(t[0] for t in lst),
                          "macro_f1_mean": float(np.mean(mf)), "macro_lo": ci(rep)[0], "macro_hi": ci(rep)[1],
                          "macro_f1_min": float(min(mf)), "macro_f1_max": float(max(mf)), "f1_MIS_mean": float(np.mean(mis)),
                          "n": lst[0][1]["n"]})
    res["encoders_mean_over_seeds"] = erows_enc
    write_table(pd.DataFrame(erows_enc), "table_encoders", "E2 fine-tuned encoders: macro-F1 mean over training seeds 1-3 [95% CI], seed range and MISLEADING F1",
                note="CI: percentile interval of the seed-mean of the paired cluster-bootstrap replicates. _edits = edit-augmented training (variant b, random only); "
                     "_hum = human labels only (prereg 4a secondary). mDeBERTa-v3 predicts SUPPORTED for every claim in every run.")
    for base in ("xlmr", "azbert", "mdeberta"):
        for smp, conds in (("random", ["C0", "C1", "C2"]), ("benchmark", ["C1", "C2"]), ("pooled", ["C2"])):
            row = {"system": f"{SYS_NAME.get(base, base)} (E2, mean of 3 seeds)", "sample": smp}
            anyv = False
            for c in conds:
                hit = [r for r in erows_enc if r["system"] == base and r["condition"] == c and r["sample"] == smp]
                if hit:
                    r = hit[0]; anyv = True
                    row[f"{c} macro-F1"] = f"{r['macro_f1_mean']:.3f} [{f(r['macro_lo'])}, {f(r['macro_hi'])}] (seeds {f(r['macro_f1_min'])}-{f(r['macro_f1_max'])})"
                    row[f"{c} F1 MISREPRESENTED"] = round(r["f1_MIS_mean"], 3)
                    row[f"{c} n"] = r["n"]
            if anyv:
                t5.append(row)
    write_table(pd.DataFrame(t5), "table5_main_results", "Main results: macro-F1 [95% CI] and MISLEADING F1 by source condition",
                note=f"Reference: R1 labels, design-weighted. Random sample: C0/C1/C2; benchmark: C1/C2 (D9; GPT-5.5 C2 only); pooled = random + benchmark under C2. "
                     f"macro-F1 over {', '.join(LSET)}. haiku_2pass = E10 (exploratory, D16).")
    # ---------------- H4
    dom, bt = boot("random")
    elig = dom["c2_eligible"].values == 1
    h4 = {}
    for sname in SYSTEMS_LLM:
        cs = {c: runs.get(f"e1|{sname}|{c}|random") for c in ("C0", "C1", "C2")}
        if not all(cs.values()):
            continue
        need = elig & dom["claim_id"].map(lambda x: all(x in cs[c]["preds"] for c in cs)).values
        sc = {c: score(cs[c]["preds"], "random", need) for c in cs}
        for a, b_ in (("C0", "C1"), ("C1", "C2")):
            d = sc[b_][1]["macro_f1"] - sc[a][1]["macro_f1"]
            est = sc[b_][0]["macro_f1"] - sc[a][0]["macro_f1"]
            pv, und = p_one_sided(d, 0.0, ">"); pvc, _ = p_one_sided(d, 0.0, "<")
            h4[f"{sname}:{a}->{b_}"] = {"estimate": est, "ci": ci(d), "p": pv, "p_opposite": pvc, "undefined_reps": und, "sesoi": 0.05,
                                        f"macro_f1_{a}": sc[a][0]["macro_f1"], f"macro_f1_{b_}": sc[b_][0]["macro_f1"],
                                        "n": sc[a][0]["n"], "kish_n": sc[a][0]["kish_n"],
                                        "n_raw_labels": dom.loc[need, "label"].value_counts().to_dict()}
    res["H4"] = h4
    # secondary H4: C1 -> C2 on random + benchmark eligible claims (systems with benchmark C1)
    doma, _ = boot("all")
    sec = {}
    for sname in SYSTEMS_LLM:
        ks = [f"e1|{sname}|{c}|{s}" for c in ("C1", "C2") for s in ("random", "benchmark")]
        if not all(k in runs for k in ks):
            continue
        p1 = {**runs[ks[0]]["preds"], **runs[ks[1]]["preds"]}; p2 = {**runs[ks[2]]["preds"], **runs[ks[3]]["preds"]}
        m = doma["c2_eligible"].values == 1
        s1, r1 = score(p1, "all", m); s2, r2 = score(p2, "all", m)
        d = r2["macro_f1"] - r1["macro_f1"]
        sec[sname] = {"estimate": s2["macro_f1"] - s1["macro_f1"], "ci": ci(d), "p_one_sided": p_one_sided(d, 0, ">")[0], "n": s1["n"]}
    res["H4_secondary_C1_C2_pooled"] = sec
    # ---------------- exploratory paired comparisons (two-sided bootstrap p, Holm within each family)
    expl = {}

    def paired(fam, name, ka, kb, smp, mask=None):
        dsm = domain_for(smp) if smp != "pooled" else "all"
        pa = runs[ka]["preds"] if ka in runs else None
        pb = runs[kb]["preds"] if kb in runs else None
        if pa is None or pb is None:
            return
        domx, _ = boot(dsm)
        common_ = np.array(domx["claim_id"].map(lambda x: x in pa and x in pb), dtype=bool)
        if mask is not None:
            common_ &= mask
        sa, ra = score(pa, dsm, common_); sb, rb = score(pb, dsm, common_)
        d = ra["macro_f1"] - rb["macro_f1"]
        expl.setdefault(fam, {})[name] = {"diff": sa["macro_f1"] - sb["macro_f1"], "ci": ci(d), "p_two_sided": p_two_sided(d), "n": sa["n"],
                                          "a": sa["macro_f1"], "b": sb["macro_f1"]}

    # E10 vs Haiku main prompt (C2), pooled over random + benchmark
    for smp in ("random", "benchmark"):
        paired("E10", f"2pass_vs_haiku_C2_{smp}", f"e10|haiku_2pass|C2|{smp}", f"e1|haiku|C2|{smp}", smp)
    # E3 retrieval variants vs whole text (Haiku C2 on the E3 claims)
    whole = {**runs.get("e1|haiku|C2|random", {"preds": {}})["preds"], **runs.get("e1|haiku|C2|benchmark", {"preds": {}})["preds"]}
    runs["e1|haiku|C2|whole"] = dict(exp="E1", system="haiku", condition="whole text", sample="all", preds=whole, path="runs/e1_haiku_C2_*")
    for k in [k for k in runs if k.startswith("e3|")]:
        e3ids = set(runs[k]["preds"])
        m = doma["claim_id"].isin(e3ids).values
        paired("E3", f"{runs[k]['condition']}_vs_whole", k, "e1|haiku|C2|whole", "all", m)
    for k in [k for k in runs if k.startswith("e4|") and not k.startswith("e4|haiku|v1")]:
        paired("E4", f"{runs[k]['condition']}_vs_v1", k, "e4|haiku|v1|random", "random")
    for fam, d in expl.items():
        adj = holm({k: v["p_two_sided"] for k, v in d.items()})
        for k in d:
            d[k]["p_holm"] = adj[k]
    res["exploratory_paired"] = expl
    erows = [{"family": fam, "comparison": k, "macro_f1_a": v["a"], "macro_f1_b": v["b"], "diff": v["diff"], "lo": v["ci"][0], "hi": v["ci"][1],
              "p_two_sided": v["p_two_sided"], "p_holm": v["p_holm"], "n": v["n"]} for fam, d in expl.items() for k, v in d.items()]
    write_table(pd.DataFrame(erows), "table_exploratory_E3_E4_E10", "Exploratory paired comparisons (macro-F1 difference a - b)",
                note="Two-sided bootstrap p, Holm within each family (E3, E4, E10). Exploratory, not hypotheses.")
    # ---------------- stability
    stab = {}
    for sname in ("haiku", "sonnet"):
        rs = [runs.get(f"stab|{sname}|r1|random"), runs.get(f"stab|{sname}|r2|random"), runs.get(f"e1|{sname}|C2|random")]
        if not all(rs):
            continue
        ids = sorted(set(rs[0]["preds"]) & set(rs[1]["preds"]) & set(rs[2]["preds"]))
        labs = [[norm_pred(r["preds"][i]) for i in ids] for r in rs]
        pairs_ = {}
        for (i, a), (j, b_) in [((0, "r1"), (1, "r2")), ((0, "r1"), (2, "main")), ((1, "r2"), (2, "main"))]:
            P = pair_onehot(labs[i], labs[j]); cf = np.ones(len(ids)) @ P
            k_, po = kappa_from_conf(cf)
            pairs_[f"{a}-{b_}"] = {"agreement": float(po), "kappa": float(k_)}
        allsame = float(np.mean([labs[0][t] == labs[1][t] == labs[2][t] for t in range(len(ids))]))
        # Fleiss kappa over the 3 runs
        cnt = np.zeros((len(ids), 5))
        for L in labs:
            for t, x in enumerate(L):
                cnt[t, LIX[x]] += 1
        pj = cnt.sum(0) / cnt.sum(); Pi = ((cnt ** 2).sum(1) - 3) / (3 * 2)
        fk = (Pi.mean() - (pj ** 2).sum()) / (1 - (pj ** 2).sum())
        stab[sname] = {"n": len(ids), "pairs": pairs_, "all_three_same": allsame, "fleiss_kappa": float(fk)}
    res["stability"] = stab
    write_table(pd.DataFrame([{"system": s, "n": v["n"], **{f"{k} agreement": x["agreement"] for k, x in v["pairs"].items()},
                               **{f"{k} kappa": x["kappa"] for k, x in v["pairs"].items()}, "all three same": v["all_three_same"],
                               "Fleiss kappa": v["fleiss_kappa"]} for s, v in stab.items()]),
                "table_stability", "Run-to-run stability (C2, 200 random claims): two re-runs and the main run")
    # ---------------- agreed-LLM gold (secondary)
    ag = claims[claims["A1"] == claims["A2"]]
    agl = [l for l in LABELS if (ag["A1"] == l).sum() >= 10]
    gold = dict(zip(ag["claim_id"], ag["A1"]))
    agr = []
    for k, v in runs.items():
        if v["exp"] not in ("E1", "E10", "NONLLM") or k.endswith("|whole") or ENC_SEED.match(v["system"]):
            continue          # encoders are trained on the agreed labels: scoring them against that gold would be circular
        ids = [c for c in v["preds"] if c in gold]
        if not ids:
            continue
        P = pair_onehot([gold[c] for c in ids], [v["preds"][c] for c in ids]); cf = np.ones(len(ids)) @ P
        agr.append({"system": v["system"], "condition": v["condition"], "sample": v["sample"], "seed": v.get("seed", ""), "n": len(ids),
                    "macro_f1": float(macro_f1(cf, agl)), **{f"F1 {l}": float(f1_from_conf(cf, [l])[l]) for l in agl}})
    write_table(pd.DataFrame(agr), "systems_agreed_llm_gold", "Secondary: scores against the agreed-LLM gold (claims with A1 = A2, unweighted)",
                note=f"macro-F1 over {', '.join(agl)} (>= 10 claims in the agreed set). Same-family flags: Haiku/Sonnet with A1 (Opus), GPT-5.5 with A2 (Codex).")
    res["agreed_llm_gold"] = {"label_set": agl, "n_claims": int(len(ag))}
    # ---------------- C1 -> C2 label change on the random sample (exploratory)
    ch = {}
    e = claims[(claims["sample"] == "random") & (claims["c2_eligible"] == 1)]["claim_id"]
    for sname in SYSTEMS_LLM:
        a, b_ = runs.get(f"e1|{sname}|C1|random"), runs.get(f"e1|{sname}|C2|random")
        if a and b_:
            l1 = np.array([a["preds"][c] for c in e]); l2 = np.array([b_["preds"][c] for c in e])
            nis = l1 == "NOT_IN_SOURCE"
            ch[sname] = {"n": int(len(e)), "share_changed": float((l1 != l2).mean()), "n_NIS_C1": int(nis.sum()),
                         "share_NIS_C1_to_SUPPORTED_C2": float((l2[nis] == "SUPPORTED").mean()) if nis.any() else None,
                         "pred_dist_C1": pd.Series(l1).value_counts().to_dict(), "pred_dist_C2": pd.Series(l2).value_counts().to_dict()}
    res["c1_to_c2_label_change_random"] = ch
    # ---------------- Figure 3: E3 variants + length terciles
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.3))
    ax = axes[0]
    names = [k for k in runs if k.startswith("e3|")] + ["e1|haiku|C2|whole"]
    labs_, vals, los, his = [], [], [], []
    for k in names:
        e3ids = set(runs[[x for x in runs if x.startswith("e3|")][0]]["preds"])
        m = doma["claim_id"].isin(e3ids).values
        s, _ = score(runs[k]["preds"], "all", m)
        labs_.append(runs[k]["condition"]); vals.append(s["macro_f1"]); los.append(s["macro_f1"] - s["macro_f1_ci"][0]); his.append(s["macro_f1_ci"][1] - s["macro_f1"])
        res.setdefault("E3_scores", {})[runs[k]["condition"]] = {"macro_f1": s["macro_f1"], "ci": s["macro_f1_ci"], "n": s["n"],
                                                                 "f1_MISREPRESENTED": s["f1_MISREPRESENTED"]}
    x = np.arange(len(labs_))
    ax.bar(x, vals, color=["#8DA0CB"] * (len(x) - 1) + ["#4C72B0"]); ax.errorbar(x, vals, yerr=[los, his], fmt="none", ecolor="k", capsize=3, lw=1)
    ax.set_xticks(x); ax.set_xticklabels(labs_, rotation=40, ha="right", fontsize=8); ax.set_ylabel("macro-F1 (Haiku, C2)", fontsize=8)
    ax.set_title("Retrieved passages vs whole text", fontsize=9); ax.spines[["top", "right"]].set_visible(False)
    ax = axes[1]
    el = doma[doma["c2_eligible"] == 1]
    terc = pd.qcut(el["chars_T2"], 3, labels=["short", "medium", "long"], duplicates="drop")
    tmask = {t: doma["claim_id"].isin(el.loc[terc == t, "claim_id"]).values for t in ["short", "medium", "long"]}
    tl = {}
    for j, sname in enumerate(SYSTEMS_LLM):
        pooled = {}
        for smp in ("random", "benchmark"):
            if f"e1|{sname}|C2|{smp}" in runs:
                pooled.update(runs[f"e1|{sname}|C2|{smp}"]["preds"])
        ys = []
        for t in ["short", "medium", "long"]:
            s, _ = score(pooled, "all", tmask[t])
            ys.append(s["macro_f1"] if s else np.nan)
            tl.setdefault(sname, {})[t] = {"macro_f1": s["macro_f1"] if s else None, "n": s["n"] if s else 0}
        ax.plot([0, 1, 2], ys, marker="o", label=SYS_NAME[sname])
    res["C2_by_T2_length_tercile"] = tl
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels([f"{t}\n(n={tl['haiku'][t]['n']})" for t in ["short", "medium", "long"]], fontsize=8)
    ax.set_title("C2 macro-F1 by full-text length tercile", fontsize=9); ax.legend(fontsize=7); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(FIG, f"fig3_evidence.{ext}"), dpi=200)
    plt.close(fig)
    # ---------------- H7 (needs E2 output)
    res["H7"] = h7(runs)
    return res, runs, scored, reps_all


def h7(runs):
    """H7: macro-F1(selected LLM, C2) - macro-F1(H7_selected encoder) on identical pooled out-of-fold claims (> 0 predicted)."""
    # confirmatory input only: predictions_h7_C2.csv (sys_select.py output, system H7_selected, condition C2); a file per
    # sample is allowed and combined within each seed
    cand = {k: v for k, v in runs.items() if v["exp"] == "NONLLM" and v["condition"] == "C2" and v["system"] == "H7_selected"
            and os.path.basename(v["path"]) == "predictions_h7_C2.csv"}
    dev = pd.read_csv(p("runs/dev_choice/cost_test.csv"))
    dev = dev[(dev["condition"] == "C2") & dev["system"].isin(SYSTEMS_LLM) & (dev["run_id"] == dev["system"] + "_C2")]   # full 155-claim dev runs only
    llm = dev.sort_values("macro_f1", ascending=False).iloc[0]["system"]
    info = {"llm": llm, "llm_rule": "best dev macro-F1 under C2 among the four test LLMs (runs/dev_choice/cost_test.csv, before the test runs)",
            "dev_macro_f1_C2": dict(zip(dev["system"], dev["macro_f1"]))}
    if not cand:
        nonconf = [v["system"] for v in runs.values() if v["exp"] == "NONLLM" and v["system"].startswith("H7_selected")]
        info.update(status="pending", note="no confirmatory predictions_h7_C2.csv (system H7_selected) found yet", nonconfirmatory_found=sorted(set(nonconf)))
        return info
    lp = {}
    for smp in ("random", "benchmark"):
        if f"e1|{llm}|C2|{smp}" in runs:
            lp.update(runs[f"e1|{llm}|C2|{smp}"]["preds"])
    dom, _ = boot("all")
    by_seed = {}
    for v in cand.values():
        d = by_seed.setdefault(v["seed"], {})
        overlap = set(d) & set(v["preds"])
        if overlap:
            info.update(status="error", note=f"seed {v['seed']}: claims predicted in more than one file ({len(overlap)})")
            return info
        d.update(v["preds"])
    cover = [set(d) for d in by_seed.values()]
    if any(c != cover[0] for c in cover):
        info.update(status="error", note="seeds cover different claim sets")
        return info
    ids = cover[0] & set(lp)
    m = dom["claim_id"].isin(ids).values
    sl, rl = score(lp, "all", m)
    seeds = sorted(by_seed)
    encs = [score(by_seed[sd], "all", m) for sd in seeds]
    enc_pt = float(np.mean([s_["macro_f1"] for s_, _ in encs])); enc_rp = np.mean([r_["macro_f1"] for _, r_ in encs], axis=0)
    d = rl["macro_f1"] - enc_rp
    pv, und = p_one_sided(d, 0, ">"); pvc, _ = p_one_sided(d, 0, "<")
    by = [s_["macro_f1"] for s_, _ in encs]
    info.update(status="done", estimate=sl["macro_f1"] - enc_pt, ci=ci(d), p=pv, p_opposite=pvc, undefined_reps=und, sesoi=0.05, n=sl["n"],
                n_oof_claims=len(cover[0]), n_reference_not_in_oof=int(len(dom) - m.sum()),
                llm_macro_f1=sl["macro_f1"], encoder_macro_f1_mean_over_seeds=enc_pt, seeds=seeds,
                encoder_macro_f1_by_seed=by, encoder_macro_f1_range=[min(by), max(by)], files=sorted({v["path"] for v in cand.values()}))
    return info
