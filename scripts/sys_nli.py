"""S1 zero-shot NLI: mDeBERTa-v3-base XNLI with retrieval (prereg section 5).

Model: MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 (the model used in the pilot), loaded at the pinned
revision sys_common.REVISIONS[MODEL]; manifest_nli.json records it with code hashes.
Premises: the condition's source (C1 = T1, C2 = T1 + T2) is split into passages (sys_common.chunk) and ranked by the
pilot overlap score; the top-k passages are scored one by one as premise, with the claim as hypothesis (max length
512, longest-first truncation). C0 uses the premise "." (no source).
Aggregation: CONTRADICTED if any passage has P(contradiction) > 0.5; else SUPPORTED if the max P(entailment) > 0.5;
else NOT_IN_SOURCE. S1 cannot output MISREPRESENTED (MISLEADING in the paper) or UNASSESSABLE, so its MISREPRESENTED
F1 is 0 by design.
There is no training and no CV; the fold column carries the claim's outer fold (sys_common.outer_folds) so that rows
can be pooled with the trained systems; seed = na.
k is a retrieval setting fixed on dev (prereg section 5); --k 1,3,5 writes one system per k (S1_nli_k1, ...).
The default K_FROZEN was chosen on dev by rule 2 of scripts/sys_devchoice.py.
Probabilities for every scored passage go to nli_scores.csv, the retrieval to nli_retrieval.csv.
Every claim is predicted, UNASSESSABLE ones too; they are dropped only at scoring.

Usage: .venv/bin/python scripts/sys_nli.py --dev --conditions C0,C1,C2 --k 1,3,5 --out runs/dev_smoke
"""
import argparse, json, time
import sys_common as S

MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
THR = 0.5
K_FROZEN = "3"               # chosen on dev, see scripts/sys_devchoice.py


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    S.add_data_args(ap)
    ap.add_argument("--conditions", default="C0,C1,C2")
    ap.add_argument("--k", default=K_FROZEN, help="comma list of top-k values; the largest k is scored once and smaller k reuse it "
                    "(default: the dev-frozen k)")
    ap.add_argument("--batch", type=int, default=16)
    a = ap.parse_args()
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    conds = S.parse_conditions(a.conditions)
    if a.k is None:
        raise SystemExit("--k: pass --k explicitly (dev only)")
    try:
        ks = sorted({int(x) for x in a.k.split(",")})
    except ValueError:
        raise SystemExit(f"invalid --k {a.k!r}")
    if not ks or min(ks) < 1:
        raise SystemExit(f"invalid --k {a.k!r}")
    t0 = time.time()
    claims, info = S.load_claims(a)
    fold = S.outer_folds(claims)
    fh = S.write_folds(claims, fold, a.out)
    labels = S.label_set(claims, a.min_label_n)
    rev = S.REVISIONS[MODEL]
    S.check_manifest(a.out, "manifest_nli.json", S.manifest(a, claims, [], fold, labels, dict(
        model=MODEL, model_revision=rev, k=ks, k_frozen=K_FROZEN, threshold=THR, conditions=conds), __file__), False)
    dev = S.device()
    tok = AutoTokenizer.from_pretrained(MODEL, revision=rev)
    m = AutoModelForSequenceClassification.from_pretrained(MODEL, revision=rev).to(dev).eval()
    id2 = {i: l.lower() for i, l in m.config.id2label.items()}
    ie, ic = [i for i, l in id2.items() if l == "entailment"][0], [i for i, l in id2.items() if l == "contradiction"][0]
    S.reset(a.out, ["predictions_nli.csv", "nli_scores.csv", "nli_retrieval.csv"])
    wp, ws, wr = S.Writer(a.out, "predictions_nli.csv"), S.Writer(a.out, "nli_scores.csv"), S.Writer(a.out, "nli_retrieval.csv")
    timing, n_pairs = {}, {}
    for cond in conds:
        t1 = time.time()
        pairs, owner = [], []
        for ci, c in enumerate(claims):
            if cond == "C0":
                prem = [(-1, ".")]
            else:
                src, _ = S.source_text(c["ann_id"], cond, a.dev)
                ps = S.chunk(src)
                rank = S.rank_passages(c["claim_text"], ps)[:max(ks)]
                prem = [(i, ps[i]) for i in rank] or [(-1, ".")]
                wr.row(["condition", "claim_id", "n_passages", "ranked_ids", "premise_words"],
                       [cond, c["claim_id"], len(ps), json.dumps(rank), json.dumps([len(ps[i].split()) for i in rank])])
            for r, (pid, p) in enumerate(prem):
                pairs.append((p, c["claim_text"])); owner.append((ci, r, pid))
        probs = []
        with torch.no_grad():
            for b in range(0, len(pairs), a.batch):
                chunk = pairs[b:b + a.batch]
                x = tok([p for p, _ in chunk], [h for _, h in chunk], truncation="longest_first", max_length=512, padding=True, return_tensors="pt").to(dev)
                probs += m(**x).logits.float().softmax(-1).cpu().tolist()
        per = {}
        for (ci, r, pid), pr in zip(owner, probs):
            per.setdefault(ci, []).append((r, pr[ie], pr[ic]))
            ws.row(["condition", "claim_id", "rank", "passage_id", "p_entail", "p_contra"], [cond, claims[ci]["claim_id"], r, pid, round(pr[ie], 5), round(pr[ic], 5)])
        for k in ks:
            for ci, c in enumerate(claims):
                sc = [x for x in per[ci] if x[0] < k]
                if any(pc > THR for _, _, pc in sc):
                    lab = "CONTRADICTED"
                elif max(pe for _, pe, _ in sc) > THR:
                    lab = "SUPPORTED"
                else:
                    lab = "NOT_IN_SOURCE"
                wp.row(S.PRED_COLS, [c["claim_id"], cond, f"S1_nli_k{k}", fold[c["claim_id"]], "na", S.setting_json({"k": k}), lab])
        timing[cond] = round(time.time() - t1, 1); n_pairs[cond] = len(pairs)
        print(f"{cond}: {len(pairs)} pairs, {timing[cond]}s", flush=True)
    S.write_meta(a.out, "meta_nli.json", dict(data=info, model=MODEL, model_revision=rev, device=str(dev), k=ks, threshold=THR, folds_sha256=fh,
                 aggregation="CON if any P(con)>0.5; else SUP if max P(ent)>0.5; else NOT_IN_SOURCE", seconds=timing, pairs=n_pairs,
                 total_seconds=round(time.time() - t0, 1)))
    print(f"S1: {len(claims)} claims, {time.time() - t0:.1f}s -> {wp.path}")


if __name__ == "__main__":
    main()
