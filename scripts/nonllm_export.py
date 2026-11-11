"""Export the non-LLM system outputs to the LLM run layout: runs/<run_id>/predictions.csv + meta.json.

Reads the work directories written by the sys_*.py scripts:
  runs/nonllm_random     (claims_random.csv, 2,020 claims; C0, C1, C2)
  runs/nonllm_benchmark  (claims_benchmark.csv, 1,573 claims; C1, C2 only, D9)
  runs/nonllm_e5         (runs/main_inputs/e5_edits.csv, 300 edits; C0, C1, C2; S1 only, E5)
  runs/colab_results/results_<sample>/  (E2 encoder predictions from Colab, D12)
and writes one run directory per system x condition x sample, named like the LLM runs:
  e1_<system>_<cond>_<sample>   E1 systems: majority (S0), nli (S1, frozen k = 3), logreg, gbm (S0b, natural training),
                                encoders xlmr, azbert, mdeberta (S2, S2b) with one run per training seed (s1-s3)
  e2_<system>_<cond>_<sample>   E2 variants: logreg_edits, gbm_edits (trained with edits, random sample only), logreg_hum,
                                gbm_hum (prereg.md 4a secondary: human labels only), and the same variants of the encoders
  e3_nli_k<k>_C2_<sample>       S1 with k = 1 and 5 (E3 evidence size; k = 3 is the E1 run)
  e5_nli_<cond>_edit            S1 on the 300 E5 edits
predictions.csv columns: claim_id, ann_id, gold, label (as the LLM runs; gold is left empty, the analysis joins the frozen
reference), then model_id, system, fold, seed, setting, source_file. For E5 rows, fold = the outer fold of the edit's
cluster in runs/nonllm_random/folds.csv (S1 is not trained, so the fold is informational).
Checks: every claim of the input file exactly once per run, labels valid, condition and system as expected; stops otherwise.
Also writes runs/nonllm_inputs/exported_runs.csv (run_id, predictions_sha256).
"""
import csv, hashlib, json, os, sys, time

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(MAIN, "runs")
LABELS = {"SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"}
NLI_MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
COLS = ["claim_id", "ann_id", "gold", "label", "model_id", "system", "fold", "seed", "setting", "source_file"]


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8")))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def export(run_id, rows, claims, cond, sample, system, model_id, src, fold_override=None, note=""):
    ann = {c["claim_id"]: c["ann_id"] for c in claims}
    got = [r for r in rows if r["condition"] == cond and r["system"] == system]
    ids = [r["claim_id"] for r in got]
    if sorted(ids) != sorted(ann) or len(ids) != len(set(ids)):
        raise SystemExit(f"{run_id}: {len(ids)} rows for {len(ann)} claims (missing {len(set(ann) - set(ids))}, dup {len(ids) - len(set(ids))})")
    bad = [r["claim_id"] for r in got if r["label"] not in LABELS]
    if bad:
        raise SystemExit(f"{run_id}: invalid labels {bad[:5]}")
    d = os.path.join(RUNS, run_id)
    os.makedirs(d, exist_ok=True)
    order = {c["claim_id"]: i for i, c in enumerate(claims)}
    got.sort(key=lambda r: order[r["claim_id"]])
    with open(os.path.join(d, "predictions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(COLS)
        for r in got:
            fo = fold_override[r["claim_id"]] if fold_override else r["fold"]
            w.writerow([r["claim_id"], ann[r["claim_id"]], "", r["label"], model_id, system, fo, r["seed"], r["setting"], os.path.relpath(src, MAIN)])
    meta = dict(run_id=run_id, system=system, condition=cond, sample=sample, n=len(got), model_id=model_id,
                source_file=os.path.relpath(src, MAIN), source_sha256=sha(src), predictions_sha256=sha(os.path.join(d, "predictions.csv")),
                cost=0.0, finished=time.strftime("%Y-%m-%d %H:%M:%S"), note=note)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return run_id, meta["predictions_sha256"]


def main():
    out = []
    claims = {"random": rd(os.path.join(MAIN, "annotation/claims/claims_random.csv")),
              "benchmark": rd(os.path.join(MAIN, "annotation/claims/claims_benchmark.csv"))}
    conds = {"random": ["C0", "C1", "C2"], "benchmark": ["C1", "C2"]}
    for sample in ("random", "benchmark"):
        wd = os.path.join(RUNS, f"nonllm_{sample}")
        cl = claims[sample]
        p = os.path.join(wd, "predictions_majority.csv"); rows = rd(p)
        for c in conds[sample]:
            out.append(export(f"e1_majority_{c}_{sample}", rows, cl, c, sample, "S0_majority", "majority:SUPPORTED", p))
        p = os.path.join(wd, "predictions_nli.csv"); rows = rd(p)
        for c in conds[sample]:
            out.append(export(f"e1_nli_{c}_{sample}", rows, cl, c, sample, "S1_nli_k3", NLI_MODEL, p, note="frozen k = 3"))
        for k in (1, 5):
            out.append(export(f"e3_nli_k{k}_C2_{sample}", rows, cl, "C2", sample, f"S1_nli_k{k}", NLI_MODEL, p, note=f"E3 evidence size k = {k}"))
        for suffix, exp in (("", "e1"), ("_edits", "e2"), ("_hum", "e2")):
            p = os.path.join(wd, f"predictions_tradml{suffix}.csv")
            if not os.path.exists(p):
                if not (suffix == "_edits" and sample == "benchmark"):
                    print(f"missing {p}", file=sys.stderr)
                continue
            rows = rd(p)
            for kind in ("logreg", "gbm"):
                for c in conds[sample]:
                    out.append(export(f"{exp}_{kind}{suffix}_{c}_{sample}", rows, cl, c, sample, f"S0b_{kind}{suffix}", f"sklearn:{kind}", p))
    # E2 encoders (Colab, D12): one exported run per model x variant x condition x sample x training seed; the analysis
    # reports the mean and range over the pre-registered seeds 1-3. Source: runs/colab_results/results_<sample>/
    for sample in ("random", "benchmark"):
        wd = os.path.join(RUNS, "colab_results", f"results_{sample}")
        cl = claims[sample]
        for model, sysbase, mid in (("xlmr", "S2_xlmr", "FacebookAI/xlm-roberta-base"), ("azbert", "S2b_azbert", "allmalab/bert-base-aze"),
                                    ("mdeberta", "S2_mdeberta", "microsoft/mdeberta-v3-base")):
            for suffix, exp in (("", "e1"), ("_edits", "e2"), ("_hum", "e2")):
                p = os.path.join(wd, f"predictions_enc_{model}{suffix}.csv")
                if not os.path.exists(p) or os.path.getsize(p) == 0:
                    continue
                rows = rd(p)
                have = {(r["condition"], r["seed"]) for r in rows}
                for c in conds[sample]:
                    for seed in ("1", "2", "3"):
                        if (c, seed) not in have:
                            continue
                        sub = [r for r in rows if r["condition"] == c and r["seed"] == seed]
                        out.append(export(f"{exp}_{model}s{seed}{suffix}_{c}_{sample}", sub, cl, c, sample, f"{sysbase}{suffix}", mid, p,
                                          note=f"E2 encoder, training seed {seed} (mean and range over seeds 1-3 in the analysis)"))
    # E5: S1 on the 300 edits; fold = outer fold of the edit's cluster in the random run
    e5 = rd(os.path.join(RUNS, "main_inputs/e5_edits.csv"))
    rf = rd(os.path.join(RUNS, "nonllm_random/folds.csv"))
    fold_of_cl = {r["cluster"]: r["fold"] for r in rf}
    cl_of_ann = {r["ann_id"]: r["cluster"] for r in rf}
    fo = {e["claim_id"]: fold_of_cl[cl_of_ann[e["ann_id"]]] for e in e5}
    p = os.path.join(RUNS, "nonllm_e5/predictions_nli.csv"); rows = rd(p)
    for c in ("C0", "C1", "C2"):
        out.append(export(f"e5_nli_{c}_edit", rows, e5, c, "edit", "S1_nli_k3", NLI_MODEL, p, fold_override=fo, note="frozen k = 3; E5 edit set"))
    with open(os.path.join(RUNS, "nonllm_inputs/exported_runs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["run_id", "predictions_sha256"]); w.writerows(out)
    for r, h in out:
        print(r, h[:16])
    print(f"{len(out)} runs exported")


if __name__ == "__main__":
    main()
