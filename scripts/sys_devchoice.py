"""Apply the two dev-set choice rules of the non-LLM systems and print the statistics behind them.

Rule 1 (encoder evidence): mean C2 inner-CV score of XLM-R with the source filled to 512 tokens (top-k 0) vs the
top-3 retrieved chunks; within TIE the top-3 setting is kept. Rule 2 (NLI retrieval k): C2 macro-F1 of k = 1, 3, 5
on the scored labels; among the values within TIE of the best, k = 3 is preferred, else the smallest k.
Uses only the pilot dev claims and their gold labels.
Inputs: runs/dev_choice/{enc_topk0,enc_topk3,nli}, <pilot>/adjudication/gold_labels_v1.csv
Usage: .venv/bin/python scripts/sys_devchoice.py
"""
import csv, os
import sys_common as S

R = os.path.join(S.MAIN, "runs/dev_choice")
TIE = 0.02


def enc_stat(d):
    rows = [r for r in csv.DictReader(open(os.path.join(R, d, "inner_enc_xlmr.csv"), encoding="utf-8"))
            if r["condition"] == "C2" and r["inner_fold"] == "chosen"]
    assert sorted(int(r["outer_fold"]) for r in rows) == list(range(S.OUTER_K)), d
    return sum(float(r["score"]) for r in rows) / len(rows), [round(float(r["score"]), 4) for r in rows]


def main():
    gold = {r["claim_id"]: r["gold_label"] for r in csv.DictReader(open(os.path.join(S.PILOT, "adjudication/gold_labels_v1.csv"), encoding="utf-8"))}
    claims = [dict(claim_id=c, gold_label=g, train_label=g) for c, g in gold.items()]
    labels = S.label_set(claims, 5)
    a, af = enc_stat("enc_topk0")
    b, bf = enc_stat("enc_topk3")
    top_k = 3 if abs(a - b) <= TIE else (0 if a > b else 3)
    print(f"label set {labels}")
    print(f"rule 1: fill-512 (top-k 0) {a:.4f} per fold {af}; top-3 {b:.4f} per fold {bf}; |diff| {abs(a - b):.4f} -> top_k = {top_k}")
    pr = list(csv.DictReader(open(os.path.join(R, "nli", "predictions_nli.csv"), encoding="utf-8")))
    st = {}
    for k in (1, 3, 5):
        p = {r["claim_id"]: r["label"] for r in pr if r["condition"] == "C2" and r["system"] == f"S1_nli_k{k}"}
        assert set(p) == set(gold), k
        ids = [c for c in gold if gold[c] in S.SCORED_LABELS]
        st[k] = S.macro_f1([gold[c] for c in ids], [p[c] for c in ids], labels)
    m = max(st.values())
    tied = [k for k in (1, 3, 5) if st[k] >= m - TIE]
    k = 3 if 3 in tied else min(tied)
    print(f"rule 2: NLI C2 macro-F1 " + ", ".join(f"k{k_}={v:.4f}" for k_, v in st.items()) + f"; tied set {tied} -> k = {k}")
    print(f"scored claims: {len([c for c in gold if gold[c] in S.SCORED_LABELS])} of {len(gold)}")


if __name__ == "__main__":
    main()
