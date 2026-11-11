"""Check the integrity of the non-LLM system runs; prints PASS/FAIL per check and exits 1 if any check fails.

No scores are computed. Checks:
  1. coverage: every exported runs/<run_id>/predictions.csv has every claim of its input exactly once, with valid labels
  2. work files: predictions_*.csv in runs/nonllm_<sample>/ cover claims x conditions x systems x seeds exactly once;
     encoder E5 files (predictions_*_e5.csv, from Colab) cover the 300 edits once per block, with the fold of the
     base claim's cluster
  3. folds: one folds.csv per sample, 5 non-empty folds, no cluster in two folds, clusters as in sampling/clusters.csv,
     and every prediction's fold equal to the claim's fold in folds.csv
  4. labels: runs/nonllm_inputs/train_labels.csv follows the sys_common rule (reference label, else the A1 label when
     A1 == A2), and every reference claim trains on its human label
  5. leakage, re-derived independently of the system scripts: per outer fold, the training claims share no cluster
     with the test fold, no training edit has its base claim's cluster in the test fold, and the inner splits share
     no cluster between their training and validation parts
  6. manifests: all manifests of a sample agree on folds, inner splits, sources and the shared-code hash
Usage: python3 scripts/nonllm_verify.py
"""
import csv, glob, json, os, sys
from collections import Counter, defaultdict

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MAIN, "scripts"))
LABELS = {"SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"}
FAIL = []


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8")))


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def main():
    clusters = {r["ann_id"]: r["cluster"] for r in rd(os.path.join(MAIN, "sampling/clusters.csv"))}
    inputs = {"random": rd(os.path.join(MAIN, "annotation/claims/claims_random.csv")),
              "benchmark": rd(os.path.join(MAIN, "annotation/claims/claims_benchmark.csv")),
              "edit": rd(os.path.join(MAIN, "runs/main_inputs/e5_edits.csv"))}
    # 1 exported runs
    ex = rd(os.path.join(MAIN, "runs/nonllm_inputs/exported_runs.csv"))
    n_ok = 0
    for r in ex:
        rid = r["run_id"]; sample = rid.rsplit("_", 1)[1]
        p = rd(os.path.join(MAIN, "runs", rid, "predictions.csv"))
        ids = [x["claim_id"] for x in p]
        want = {c["claim_id"]: c["ann_id"] for c in inputs[sample]}
        ok = sorted(ids) == sorted(want) and all(x["label"] in LABELS and want[x["claim_id"]] == x["ann_id"] for x in p)
        n_ok += ok
        if not ok:
            check(f"coverage {rid}", False)
    check(f"coverage of {len(ex)} exported runs", n_ok == len(ex), f"{n_ok} ok")
    conds = {"random": ["C0", "C1", "C2"], "benchmark": ["C1", "C2"]}
    ref = {r["claim_id"]: r for r in rd(os.path.join(MAIN, "annotation/reference/reference_R1.csv"))}
    tl = {r["claim_id"]: r["label"] for r in rd(os.path.join(MAIN, "runs/nonllm_inputs/train_labels.csv"))}
    edits = [e for e in rd(os.path.join(MAIN, "runs/nonllm_inputs/edits_train.csv")) if e["accepted"] == "1"]
    for sample in ("random", "benchmark"):
        wd = os.path.join(MAIN, "runs", f"nonllm_{sample}")
        cl = inputs[sample]
        folds = {r["claim_id"]: r for r in rd(os.path.join(wd, "folds.csv"))}
        # 3 folds
        check(f"{sample}: folds.csv covers the claims", sorted(folds) == sorted(c["claim_id"] for c in cl))
        cf = defaultdict(set)
        for r in folds.values():
            cf[r["cluster"]].add(r["fold"])
        check(f"{sample}: no cluster in two outer folds", all(len(v) == 1 for v in cf.values()), f"{len(cf)} clusters")
        check(f"{sample}: clusters from sampling/clusters.csv", all(clusters[r["ann_id"]] == r["cluster"] for r in folds.values()))
        check(f"{sample}: 5 non-empty folds", Counter(r["fold"] for r in folds.values()).keys() == {"0", "1", "2", "3", "4"},
              str(sorted(Counter(r["fold"] for r in folds.values()).items())))
        # 2 work files (encoder E5 files first)
        cl_fold = {r["cluster"]: r["fold"] for r in folds.values()}
        e5_ids = {e["claim_id"]: clusters[e["ann_id"]] for e in inputs["edit"]}
        for p in sorted(glob.glob(os.path.join(wd, "predictions_*_e5.csv"))):     # encoder E5 files from Colab
            rows = rd(p)
            keys = Counter((r["claim_id"], r["condition"], r["system"], r["seed"]) for r in rows)
            per = Counter((r["condition"], r["system"], r["seed"]) for r in rows)
            ok = (sample == "random" and max(keys.values()) == 1 and all(v == len(e5_ids) for v in per.values())
                  and all(r["claim_id"] in e5_ids and r["fold"] == cl_fold[e5_ids[r["claim_id"]]] for r in rows)
                  and all(r["label"] in LABELS for r in rows))
            check(f"{sample}: {os.path.basename(p)} covers the 300 edits per block, held-out fold = base cluster's fold", ok, f"{len(rows)} rows")
        for p in sorted(glob.glob(os.path.join(wd, "predictions_*.csv"))):
            if p.endswith("_e5.csv"):
                continue
            rows = rd(p)
            keys = Counter((r["claim_id"], r["condition"], r["system"], r["seed"]) for r in rows)
            systems = {r["system"] for r in rows}
            per = Counter((r["condition"], r["system"], r["seed"]) for r in rows)     # one block = one condition x system x seed
            cset = {r["condition"] for r in rows}
            # CPU systems run every condition of the sample (D9); encoder files may hold a subset (D12 priorities, e.g. _hum = C2)
            want_c = cset <= set(conds[sample]) if os.path.basename(p).startswith("predictions_enc_") else cset == set(conds[sample])
            ok = (max(keys.values()) == 1 and all(v == len(cl) for v in per.values()) and want_c
                  and len({(c, sy) for c, sy, _ in per}) * len({sd for _, _, sd in per}) == len(per)
                  and all(r["fold"] == folds[r["claim_id"]]["fold"] for r in rows) and all(r["label"] in LABELS for r in rows))
            check(f"{sample}: {os.path.basename(p)} complete, unique, folds match", ok, f"{len(rows)} rows, systems {sorted(systems)}")
        # 6 manifests
        mans = {os.path.basename(m): json.load(open(m)) for m in glob.glob(os.path.join(wd, "manifest_*.json"))}
        for k in ("folds_sha256", "inner_sha256", "sources_sha256", "common_code_sha256"):
            vals = {m.get(k) for m in mans.values()}
            check(f"{sample}: manifests agree on {k}", len(vals) == 1, f"{len(mans)} manifests")
        # 5 leakage, re-derived
        import sys_common as S
        ok_leak = True
        byf = defaultdict(list)
        for c in cl:
            byf[folds[c["claim_id"]]["fold"]].append(c)
        base_cl = {}
        allc = {c["claim_id"]: c for k in ("random", "benchmark") for c in inputs[k]}
        for e in edits:
            base_cl[e["edit_id"]] = clusters[allc[e["base_claim_id"]]["ann_id"]]
        for f, te in byf.items():
            te_cl = {clusters[c["ann_id"]] for c in te}
            tr = [c for c in cl if folds[c["claim_id"]]["fold"] != f]
            tr_cl = {clusters[c["ann_id"]] for c in tr}
            if te_cl & tr_cl:
                ok_leak = False
            ed_in = [e for e in edits if base_cl[e["edit_id"]] in tr_cl]
            if any(base_cl[e["edit_id"]] in te_cl for e in ed_in):
                ok_leak = False
            trc = [dict(claim_id=c["claim_id"], cluster=clusters[c["ann_id"]], train_label=tl.get(c["claim_id"])) for c in tr]
            for a, b in S.inner_splits(trc):
                if {trc[i]["cluster"] for i in a} & {trc[i]["cluster"] for i in b}:
                    ok_leak = False
        check(f"{sample}: no cluster shared between train and test (outer, inner, edits)", ok_leak)
    # 4 labels
    l1 = {r["claim_id"]: r["label"] for r in rd(os.path.join(MAIN, "annotation/llm/labels_A1.csv"))}
    l2 = {r["claim_id"]: r["label"] for r in rd(os.path.join(MAIN, "annotation/llm/labels_A2.csv"))}
    want = {}
    for c in rd(os.path.join(MAIN, "annotation/claims/claims_s1.csv")):
        cid = c["claim_id"]
        if cid in ref and ref[cid]["label"]:
            want[cid] = ref[cid]["label"]
        elif cid in l1 and l1[cid] == l2.get(cid):
            want[cid] = l1[cid]
    check("train_labels.csv = reference label else agreed A1/A2", want == tl, f"{len(tl)} labels, {len(ref)} human")
    check("every reference claim trains on its human label", all(tl.get(k) == v["label"] for k, v in ref.items()))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
