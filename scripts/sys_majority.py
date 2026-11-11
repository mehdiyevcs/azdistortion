"""S0 majority baseline (prereg section 5): predicts SUPPORTED for every claim.

The fold column is the claim's outer fold of the shared grouped CV. The most frequent fit label of each outer
training part is logged in the meta file, and a warning is printed if it is not SUPPORTED. The same rows are written
for every condition in --conditions (default C0,C1,C2). Every claim is predicted, UNASSESSABLE ones too; they are
dropped only at scoring.

Usage:
  .venv/bin/python scripts/sys_majority.py --dev --out runs/dev_smoke            # pilot dev claims
  .venv/bin/python scripts/sys_majority.py --gold adjudication/<gold>.csv --out runs/<run>   # main study
Output: <out>/predictions_majority.csv (claim_id, condition, system, fold, seed, label), <out>/folds.csv, meta json.
"""
import argparse, time
from collections import Counter
import sys_common as S


def main():
    ap = S.add_data_args(argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter))
    ap.add_argument("--conditions", default="C0,C1,C2")
    a = ap.parse_args()
    conds = S.parse_conditions(a.conditions)
    t0 = time.time()
    claims, info = S.load_claims(a)
    fold = S.outer_folds(claims)
    fh = S.write_folds(claims, fold, a.out)
    labels = S.label_set(claims, a.min_label_n)
    S.check_manifest(a.out, "manifest_majority.json", S.manifest(a, claims, [], fold, labels, dict(conditions=conds), __file__), False)
    S.reset(a.out, ["predictions_majority.csv"])
    w = S.Writer(a.out, "predictions_majority.csv")
    chosen = {}
    for f in range(S.OUTER_K):
        train = S.fit_rows([c for c in claims if fold[c["claim_id"]] != f])
        cnt = Counter(c["fit_label"] for c in train)
        lab = max(S.LABELS, key=lambda l: (cnt.get(l, 0), -S.LABELS.index(l)))
        chosen[f] = lab
        if lab != "SUPPORTED":
            print(f"WARNING: training majority of outer fold {f} is {lab}; S0 still predicts SUPPORTED (plan Phase E)")
        for c in claims:
            if fold[c["claim_id"]] == f:
                for cond in conds:
                    w.row(S.PRED_COLS, [c["claim_id"], cond, "S0_majority", f, "na", "na", "SUPPORTED"])
    S.write_meta(a.out, "meta_majority.json", dict(data=info, folds_sha256=fh, prediction="SUPPORTED", training_majority_by_fold=chosen, seconds=round(time.time() - t0, 2)))
    print(f"S0 majority: {len(claims)} claims, label by fold {chosen}, {time.time() - t0:.1f}s -> {w.path}")


if __name__ == "__main__":
    main()
