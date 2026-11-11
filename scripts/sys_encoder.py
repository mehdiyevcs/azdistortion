"""Fine-tune and score the encoder systems S2 / S2b on (claim, retrieved source passages) with nested grouped CV (prereg.md 4a, 5; E2).

Models (--model):
  xlmr     FacebookAI/xlm-roberta-base            (S2)
  azbert   allmalab/bert-base-aze                 (S2b, Azerbaijani-only BERT; gated, HF_TOKEN read from .env in the repository root)
  mdeberta microsoft/mdeberta-v3-base             (prereg 4a lists it as an H7 encoder candidate)
Input: text_a = claim, text_b = retrieved passages of the condition's source (C1 = T1, C2 = T1 + T2); C0 = the
claim alone (single sequence, no source). Passages (sys_common.chunk) are ranked by the word-overlap score; at most
--top-k of them (frozen default TOP_K_FROZEN, frozen on the dev claims; 0 = no cap)
are added best-first while they fit the 512-token budget (claim and special tokens counted first; the top passage is
cut if it alone is too long); the kept passages are then put back in document order. Every claim's retrieval is
logged to enc_retrieval_<model><suffix>.csv. Checkpoints and tokenizers load at the pinned sys_common.REVISIONS.
Every claim is predicted; UNASSESSABLE / unlabelled claims are not training targets and are not scored.
Training (prereg 4a): 3 epochs, batch 16 (micro-batches with gradient accumulation if --micro-batch < 16), max
length 512, AdamW (weight decay 0.01, linear schedule, 10% warm-up, grad-norm clip 1.0), cross-entropy with balanced
class weights computed on the training part, fp32 (CUDA if available, else Apple MPS, else CPU; see sys_common.device).
Nested CV: for each outer fold (sys_common.outer_folds, grouped by cluster) the learning rate is chosen from
{1e-5, 2e-5, 3e-5} by mean inner 3-fold grouped CV macro-F1 (training seed --select-seed, default 1); the chosen lr is
refit on the whole outer training part with each training seed (1, 2, 3) and predicts the outer test fold.
--edits FILE (E2 variant b): accepted edits join a training part (inner or outer) only when their base claim's
cluster is in that part; they are never validated or tested on.

Usage (full, main study):
  python scripts/sys_encoder.py --model xlmr --conditions C2 --gold <gold.csv> --out runs/<run> [--edits FILE] [--resume]
Smoke test (dev): add --dev --epochs 1 --max-steps 3 (and optionally --outer-folds 0 --lr-grid 2e-5 --seeds 1).
E5 (--e5-claims FILE, e.g. runs/main_inputs/e5_edits.csv: claim_id, ann_id, part, claim_text): every outer refit also
predicts the E5 edit claims whose announcement's cluster is in its outer test fold (held-out folds), so no model predicts
an edit of a cluster it was trained on. Written to predictions_enc_<model><suffix>_e5.csv
(same columns; fold = the outer fold of the edit's cluster), each block before the natural block of the same refit, so a
complete natural block implies a complete E5 block. E5 rows are never training rows and never scored inside this script.
Resume: blocks are kept only if every row is complete and valid, the block covers its fold exactly, and its setting
is the setting the inner CV chooses now; inner rows are kept only if valid; both files are rewritten atomically.
Outputs (in --out): predictions_enc_<model><suffix>.csv, inner_enc_<model><suffix>.csv, trainlog_enc_<model><suffix>.csv,
enc_retrieval_<model><suffix>.csv, meta_enc_<model><suffix>.json.
"""
import argparse, copy, csv, gc, hashlib, json, math, os, random, time
from collections import Counter
import sys_common as S

MODELS = {"xlmr": ("FacebookAI/xlm-roberta-base", "S2_xlmr"), "azbert": ("allmalab/bert-base-aze", "S2b_azbert"),
          "mdeberta": ("microsoft/mdeberta-v3-base", "S2_mdeberta")}
TOP_K_FROZEN = 3           # frozen on the dev claims (0 = fill the 512-token window)


# ---------------------------------------------------------------- retrieval + tokenisation
class Encoder:
    def __init__(self, tok, max_len, dev_mode, log, top_k=0):
        self.tok, self.max_len, self.dev_mode, self.log, self.top_k = tok, max_len, dev_mode, log, top_k
        self.src = {}
        self.special = tok.num_special_tokens_to_add(pair=True)

    def _src(self, ann, cond):
        k = (ann, cond)
        if k not in self.src:
            text, _ = S.source_text(ann, cond, self.dev_mode)
            ps = S.chunk(text)
            lens = [len(x) for x in self.tok(ps, add_special_tokens=False)["input_ids"]] if ps else []
            self.src[k] = (ps, lens)
        return self.src[k]

    def encode(self, row, cond):
        if cond == "C0":                  # claim only (no source)
            enc = self.tok(row["claim_text"], truncation=True, max_length=self.max_len)
            self.log.row(["condition", "claim_id", "n_passages", "source_tokens", "kept_ids_rank_order", "n_kept", "input_tokens", "all_source_fits", "top_passage_cut", "claim_cut"],
                         [cond, row["claim_id"], 0, 0, "[]", 0, len(enc["input_ids"]), 1, 0, 0])
            return {k: v for k, v in enc.items()}
        claim_ids = self.tok(row["claim_text"], add_special_tokens=False)["input_ids"]
        budget = self.max_len - self.special - len(claim_ids)
        ps, lens = self._src(row["ann_id"], cond)
        rank = S.rank_passages(row["claim_text"], ps)
        if self.top_k:
            rank = rank[:self.top_k]
        keep, used = [], 0
        for i in rank:                    # strict rank prefix: stop at the first passage that does not fit
            if used + lens[i] + 1 > budget:
                break
            keep.append(i); used += lens[i] + 1
        top_cut = 0
        if not keep and rank:             # the best passage alone is too long: keep it, cut by truncation
            keep, top_cut = [rank[0]], 1
        sel = sorted(keep)
        passage = " ".join(ps[i] for i in sel)
        claim_cut = int(len(claim_ids) > self.max_len // 2)   # an over-long claim: cut claim and passage together
        enc = self.tok(row["claim_text"], passage, truncation="longest_first" if claim_cut else "only_second", max_length=self.max_len)
        self.log.row(["condition", "claim_id", "n_passages", "source_tokens", "kept_ids_rank_order", "n_kept", "input_tokens", "all_source_fits", "top_passage_cut", "claim_cut"],
                     [cond, row["claim_id"], len(ps), sum(lens), json.dumps(keep), len(keep), len(enc["input_ids"]), int(len(keep) == len(ps)), top_cut, claim_cut])
        return {k: v for k, v in enc.items()}


# ---------------------------------------------------------------- train / predict
def set_seed(seed):
    import numpy as np, torch
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)


_BASE = {}


def fresh_model(name, n_labels, seed):
    rev = S.REVISIONS[name]
    """Pretrained encoder with a newly initialised classification head, seeded. The checkpoint is read from disk once
    per (model, n_labels) and kept on CPU; each fit deep-copies it and re-initialises the parameters the checkpoint
    does not contain (the head, and the pooler where absent), with N(0, initializer_range) weights and zero biases,
    the transformers default. Equivalent to from_pretrained per fit, without reloading 0.5-1.1 GB each time."""
    import torch
    from transformers import AutoModelForSequenceClassification
    if (name, n_labels) not in _BASE:
        m, info = AutoModelForSequenceClassification.from_pretrained(name, revision=rev, num_labels=n_labels, output_loading_info=True)
        _BASE[(name, n_labels)] = (m, sorted({k.rsplit(".", 1)[0] for k in info["missing_keys"]}))
    base, mods = _BASE[(name, n_labels)]
    set_seed(seed)
    m = copy.deepcopy(base)
    std = getattr(m.config, "initializer_range", 0.02)
    with torch.no_grad():
        for mn in mods:
            mod = m.get_submodule(mn)
            if isinstance(mod, torch.nn.Linear):
                mod.weight.normal_(0.0, std)
                if mod.bias is not None:
                    mod.bias.zero_()
            elif isinstance(mod, torch.nn.LayerNorm):
                mod.weight.fill_(1.0); mod.bias.zero_()
            else:
                raise SystemExit(f"cannot re-initialise new module {mn} ({type(mod).__name__})")
    return m


def batches(feats, idx, size, tok, dev):
    import torch
    for b in range(0, len(idx), size):
        part = [feats[i] for i in idx[b:b + size]]
        x = tok.pad(part, return_tensors="pt")
        yield {k: v.to(dev) for k, v in x.items()}, idx[b:b + size]


def train_predict(a, name, tok, train_rows, test_rows, enc, lr, seed, stat):
    """Fine-tune on train_rows (fit_label), return predicted labels for test_rows."""
    import torch
    from transformers import get_linear_schedule_with_warmup
    dev = S.device()
    labs = [l for l in S.SCORED_LABELS if any(r["fit_label"] == l for r in train_rows)]
    if not labs:
        raise SystemExit("empty training part (check --train-on human and the gold file)")
    if len(labs) == 1:
        return [labs[0]] * len(test_rows)
    l2i = {l: i for i, l in enumerate(labs)}
    y = [l2i[r["fit_label"]] for r in train_rows]
    cnt = Counter(y)
    cw = torch.tensor([len(y) / (len(labs) * cnt[i]) for i in range(len(labs))], dtype=torch.float32, device=dev)
    model = fresh_model(name, len(labs), seed).to(dev)
    set_seed(seed)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps_per_epoch = math.ceil(len(train_rows) / a.batch)
    total = steps_per_epoch * a.epochs if not a.max_steps else min(a.max_steps, steps_per_epoch * a.epochs)
    sch = get_linear_schedule_with_warmup(opt, int(0.1 * total), total)
    lossf = torch.nn.CrossEntropyLoss(weight=cw, reduction="sum")
    feats = [enc[r["claim_id"]] for r in train_rows]
    g = random.Random(seed)
    t0, step = time.time(), 0
    for ep in range(a.epochs):
        order = list(range(len(train_rows))); g.shuffle(order)
        for b in range(0, len(order), a.batch):
            if step >= total:
                break
            big = order[b:b + a.batch]
            opt.zero_grad()
            wsum = sum(cw[y[i]].item() for i in big)
            for x, ids in batches(feats, big, a.micro_batch, tok, dev):
                yt = torch.tensor([y[i] for i in ids], device=dev)
                loss = lossf(model(**x).logits.float(), yt) / wsum     # weighted mean over the full batch of 16
                loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sch.step(); step += 1
    t_train = time.time() - t0
    model.eval()
    tf = [enc[r["claim_id"]] for r in test_rows]
    order = sorted(range(len(tf)), key=lambda i: len(tf[i]["input_ids"]))
    pred = [None] * len(tf)
    t1 = time.time()
    with torch.no_grad():
        for x, ids in batches(tf, order, 32, tok, dev):
            for i, p in zip(ids, model(**x).logits.argmax(-1).tolist()):
                pred[i] = labs[p]
    stat.update(n_train=len(train_rows), steps=step, train_s=round(t_train, 1), n_test=len(test_rows), pred_s=round(time.time() - t1, 1),
                s_per_step=round(t_train / max(1, step), 3))
    del model, opt
    gc.collect()
    if dev.type == "mps":
        torch.mps.empty_cache()
    elif dev.type == "cuda":
        torch.cuda.empty_cache()
    return pred


# ---------------------------------------------------------------- main
def _atomic_rows(path, header, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    os.replace(tmp, path)                  # atomic: an interruption leaves the old file intact


def _setting_ok(st, lrs):
    try:
        d = json.loads(st)
    except (TypeError, ValueError):
        return False
    return isinstance(d, dict) and set(d) == {"lr"} and any(d["lr"] == l for l in lrs)


def clean_predictions(path, fold, sysname, lrs):
    """Resume: keep only complete, valid (condition, fold, seed) blocks: every column present, condition C0-C2, the
    run's system name, the claim's own fold, integer seed, a label the encoder can output, one lr setting from the grid
    for the whole block, and every claim of the fold exactly once. Rewrites the file atomically without other rows.
    Returns {(condition, fold, seed): setting}."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:   # 0-byte file: killed before the first row
        return {}
    with open(path, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != S.PRED_COLS:
            raise SystemExit(f"{path}: unexpected columns {rd.fieldnames}; start a fresh run")
        rows = list(rd)
    want = {}
    for cid, fo in fold.items():
        want.setdefault(str(fo), []).append(cid)
    blocks = {}
    for r in rows:
        blocks.setdefault((r["condition"], r["fold"], r["seed"]), []).append(r)
    ok = {}
    for k, rs in blocks.items():
        ids = [r["claim_id"] for r in rs]
        valid = (k[0] in S.CONDITIONS and k[2].isdigit() and sorted(ids) == sorted(want.get(k[1], [])) and len(ids) == len(set(ids))
                 and all(all(r.get(c) not in (None, "") for c in S.PRED_COLS) and r["system"] == sysname and str(fold.get(r["claim_id"])) == r["fold"]
                         and r["label"] in S.SCORED_LABELS and _setting_ok(r["setting"], lrs) for r in rs)
                 and len({json.dumps(json.loads(r["setting"]), sort_keys=True) for r in rs}) == 1)
        if valid:
            ok[k] = rs[0]["setting"]
    dropped = sum(len(rs) for k, rs in blocks.items() if k not in ok)
    if dropped:
        print(f"resume: dropped {dropped} prediction rows in incomplete or invalid blocks", flush=True)
    _atomic_rows(path, S.PRED_COLS, [[r[c] for c in S.PRED_COLS] for r in rows if (r["condition"], r["fold"], r["seed"]) in ok])
    return ok


IH = ["condition", "system", "outer_fold", "setting", "inner_fold", "score"]


def clean_inner(path, sysname, lrs):
    """Resume: keep valid inner rows (columns complete, condition C0-C2, the run's system, outer fold 0-4, setting in the
    lr grid, inner fold 0-2 or 'chosen', finite score); identical duplicates are dropped, conflicting ones stop the run.
    Rewrites the file atomically."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:   # 0-byte file: killed before the first row
        return []
    with open(path, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != IH:
            raise SystemExit(f"{path}: unexpected columns {rd.fieldnames}; start a fresh run")
        raw = list(rd)
    rows, seen, bad = [], {}, 0
    for r in raw:
        try:
            sc = float(r["score"])
            v = (r["condition"] in S.CONDITIONS and r["system"] == sysname and r["outer_fold"] in [str(i) for i in range(S.OUTER_K)]
                 and _setting_ok(r["setting"], lrs) and r["inner_fold"] in ("0", "1", "2", "chosen") and math.isfinite(sc))
        except (TypeError, ValueError):
            v = False
        if not v:
            bad += 1; continue
        k = (r["condition"], r["outer_fold"], r["setting"], r["inner_fold"]) if r["inner_fold"] != "chosen" else (r["condition"], r["outer_fold"], "chosen")
        if k in seen:
            if (seen[k]["setting"], float(seen[k]["score"])) != (r["setting"], sc):
                raise SystemExit(f"{path}: conflicting inner rows for {k}; start a fresh run")
            continue
        seen[k] = r; rows.append(r)
    if bad:
        print(f"resume: dropped {bad} invalid inner rows", flush=True)
    _atomic_rows(path, IH, [[r[c] for c in IH] for r in rows])
    return rows


def load_e5(path, claims, fold):
    """E5 edit claims as prediction-only rows (internal id 'E5:<claim_id>'), with the outer fold of their cluster."""
    if not path:
        return [], {}
    cl_of_ann = {c["ann_id"]: c["cluster"] for c in claims}
    fold_of_cl = {c["cluster"]: fold[c["claim_id"]] for c in claims}
    rows, ids = [], set()
    for r in S._read(path):
        cid = (r.get("claim_id") or "").strip()
        if not cid or cid in ids or not r.get("claim_text", "").strip():
            raise SystemExit(f"{path}: empty or duplicate claim_id / empty claim_text ({cid!r})")
        if r["ann_id"] not in cl_of_ann:
            raise SystemExit(f"{path}: {cid} belongs to {r['ann_id']}, which has no natural claim in this run (no held-out fold)")
        ids.add(cid)
        cl = cl_of_ann[r["ann_id"]]
        rows.append(dict(claim_id="E5:" + cid, out_id=cid, ann_id=r["ann_id"], cluster=cl, part=r.get("part", "body"),
                         claim_text=r["claim_text"], e5_fold=fold_of_cl[cl]))
    return rows, dict(e5_file=path, e5_rows=len(rows), e5_by_fold=dict(Counter(r["e5_fold"] for r in rows)),
                      e5_sha256=hashlib.sha256(json.dumps(sorted((r["out_id"], r["ann_id"], r["cluster"], r["part"], r["claim_text"]) for r in rows),
                                                          ensure_ascii=False).encode()).hexdigest())


def clean_e5(path, e5, sysname, done_pred):
    """Resume: keep E5 rows only for natural blocks kept by clean_predictions, and only complete blocks (every E5 claim of
    the fold exactly once, same setting as the natural block). A kept natural block without its complete E5 block stops."""
    if not e5:
        return
    rows = []
    if os.path.exists(path) and os.path.getsize(path) > 0:     # 0-byte file: killed before the first row
        with open(path, encoding="utf-8") as f:
            rd = csv.DictReader(f)
            if rd.fieldnames != S.PRED_COLS:
                raise SystemExit(f"{path}: unexpected columns {rd.fieldnames}; start a fresh run")
            rows = list(rd)
    want = {}
    for r in e5:
        want.setdefault(str(r["e5_fold"]), []).append(r["out_id"])
    blocks = {}
    for r in rows:
        blocks.setdefault((r["condition"], r["fold"], r["seed"]), []).append(r)
    keep = []
    for k, st in done_pred.items():
        rs = blocks.get(k, [])
        ids = [r["claim_id"] for r in rs]
        ok = (sorted(ids) == sorted(want.get(k[1], [])) and all(r["system"] == sysname and r["label"] in S.SCORED_LABELS
                                                               and S.same_setting(r["setting"], st) for r in rs))
        if not ok:
            raise SystemExit(f"resume: natural block {k} is complete but its E5 block in {path} is not; start a fresh run")
        keep += rs
    _atomic_rows(path, S.PRED_COLS, [[r[c] for c in S.PRED_COLS] for r in keep])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    S.add_data_args(ap)
    ap.add_argument("--e5-claims", default="", help="E5 edit claims to predict with the held-out outer models (prediction only)")
    ap.add_argument("--model", choices=list(MODELS), required=True)
    ap.add_argument("--conditions", required=True, help="comma list from C0, C1, C2")
    ap.add_argument("--lr-grid", default="1e-5,2e-5,3e-5")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--micro-batch", type=int, default=8, help="forward/backward chunk; gradients are accumulated to --batch")
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--top-k", type=int, default=TOP_K_FROZEN, help="cap on retrieved passages (default: the dev-frozen value; "
                    "0 = as many top-ranked passages as fit 512 tokens)")
    ap.add_argument("--max-steps", type=int, default=0, help="smoke only: cap optimizer steps per fine-tune")
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--select-seed", type=int, default=1)
    ap.add_argument("--outer-folds", default="", help="smoke only: subset of outer folds, e.g. 0")
    ap.add_argument("--resume", action="store_true", help="keep existing output files and skip finished (cond, fold, lr, inner fold) / (cond, fold, seed)")
    a = ap.parse_args()
    conds = S.parse_conditions(a.conditions)
    if a.top_k is None or a.top_k < 0:
        raise SystemExit("--top-k: pass --top-k explicitly (dev only)")
    S.load_hf_token()
    from transformers import AutoTokenizer
    t0 = time.time()
    name, sysbase = MODELS[a.model]
    claims, info = S.load_claims(a)
    edits, einfo = S.load_edits(a, claims)
    fold = S.outer_folds(claims)
    fh = S.write_folds(claims, fold, a.out)
    labels = S.label_set(claims, a.min_label_n)
    e5, e5info = load_e5(a.e5_claims, claims, fold)
    suffix = ("_edits" if a.edits else "") + ("_hum" if a.train_on == "human" else "")
    sysname = sysbase + suffix
    files = {k: f"{k}_enc_{a.model}{suffix}.csv" for k in ("predictions", "inner", "trainlog")}
    lrs = [float(x) for x in a.lr_grid.split(",")]
    S.check_manifest(a.out, f"manifest_enc_{a.model}{suffix}.json", S.manifest(a, claims, edits, fold, labels, dict(
        model=name, model_revision=S.REVISIONS[name], lr_grid=a.lr_grid, epochs=a.epochs, batch=a.batch, micro_batch=a.micro_batch,
        max_len=a.max_len, top_k=a.top_k, top_k_frozen=TOP_K_FROZEN, max_steps=a.max_steps, select_seed=a.select_seed,
        outer_folds=a.outer_folds, device=S.device().type, e5_sha256=e5info.get("e5_sha256", "")), __file__), a.resume,
        outputs=list(files.values()) + ([f"predictions_enc_{a.model}{suffix}_e5.csv"] if e5 else []))
    e5_path = os.path.join(a.out, f"predictions_enc_{a.model}{suffix}_e5.csv")
    S.reset(a.out, [f"enc_retrieval_{a.model}{suffix}.csv"])      # regenerated on every run
    if not a.resume:
        S.reset(a.out, list(files.values()) + [os.path.basename(e5_path)])
    inner_rows = clean_inner(os.path.join(a.out, files["inner"]), sysname, lrs)
    done_inner = {(r["condition"], r["outer_fold"], r["setting"], r["inner_fold"]) for r in inner_rows}
    chosen_done = {(r["condition"], r["outer_fold"]): r["setting"] for r in inner_rows if r["inner_fold"] == "chosen"}
    done_pred = clean_predictions(os.path.join(a.out, files["predictions"]), fold, sysname, lrs)
    clean_e5(e5_path, e5, sysname, done_pred)
    # A 0-byte output file (created, then killed before its first row) is removed so the writer starts it with a header.
    # This is done here, not in sys_common.Writer, so that the hash of the shared code recorded in the manifests stays the same.
    for _n in [os.path.basename(e5_path)] + [files[k] for k in ("predictions", "inner", "trainlog")] + [f"enc_retrieval_{a.model}{suffix}.csv"]:
        _p = os.path.join(a.out, _n)
        if os.path.exists(_p) and os.path.getsize(_p) == 0:
            os.remove(_p)
    we5 = S.Writer(a.out, os.path.basename(e5_path)) if e5 else None
    wp, wi, wt = (S.Writer(a.out, files[k]) for k in ("predictions", "inner", "trainlog"))
    wr = S.Writer(a.out, f"enc_retrieval_{a.model}{suffix}.csv")
    tok = AutoTokenizer.from_pretrained(name, revision=S.REVISIONS[name])
    seeds = [int(x) for x in a.seeds.split(",")]
    outer = [int(x) for x in a.outer_folds.split(",")] if a.outer_folds else list(range(S.OUTER_K))
    TH = ["condition", "system", "outer_fold", "phase", "inner_fold", "lr", "seed", "n_train", "n_edits", "steps", "train_s", "n_test", "pred_s", "s_per_step"]
    for cond in conds:
        t1 = time.time()
        E = Encoder(tok, a.max_len, a.dev, wr, a.top_k)
        enc = {r["claim_id"]: E.encode(r, cond) for r in claims + edits + e5}
        print(f"{cond}: tokenised {len(enc)} rows in {time.time() - t1:.1f}s", flush=True)
        for f in outer:
            outer_tr = [c for c in claims if fold[c["claim_id"]] != f]
            outer_te = [c for c in claims if fold[c["claim_id"]] == f]
            splits = S.inner_splits(outer_tr)
            mean = {}
            for lr in lrs:
                sc = []
                for ii, (tr, va) in enumerate(splits):
                    key = (cond, str(f), S.setting_json({"lr": lr}), str(ii))
                    if key in done_inner:
                        sc += [float(r["score"]) for r in inner_rows if (r["condition"], r["outer_fold"], r["setting"], r["inner_fold"]) == key]
                        continue
                    tr_rows = [outer_tr[i] for i in tr]
                    ed = S.edits_for(edits, {r["cluster"] for r in tr_rows})
                    va_rows = [outer_tr[i] for i in va]
                    st = {}
                    p = train_predict(a, name, tok, S.fit_rows(tr_rows) + ed, va_rows, enc, lr, a.select_seed, st)
                    s = S.inner_score(va_rows, p, labels, a.inner_score)
                    sc.append(s)
                    wi.row(IH, [cond, sysname, f, S.setting_json({"lr": lr}), ii, repr(s)])
                    wt.row(TH, [cond, sysname, f, "inner", ii, lr, a.select_seed, st.get("n_train"), len(ed), st.get("steps"), st.get("train_s"),
                                st.get("n_test"), st.get("pred_s"), st.get("s_per_step")])
                    print(f"  {cond} outer {f} lr {lr} inner {ii}: score {s:.3f} ({st.get('train_s')}s train)", flush=True)
                mean[lr] = sum(sc) / len(sc)
            best = max(lrs, key=lambda l: (mean[l], -lrs.index(l)))      # ties: first lr in grid order
            bj = S.setting_json({"lr": best})
            if (cond, str(f)) in chosen_done:
                if not S.same_setting(chosen_done[(cond, str(f))], bj):
                    raise SystemExit(f"resume: stored chosen setting {chosen_done[(cond, str(f))]} for {cond} fold {f} != {bj} from the inner rows")
            else:
                wi.row(IH, [cond, sysname, f, bj, "chosen", repr(mean[best])])
            ed = S.edits_for(edits, {r["cluster"] for r in outer_tr})
            for seed in seeds:
                k = (cond, str(f), str(seed))
                if k in done_pred:
                    if not S.same_setting(done_pred[k], bj):
                        raise SystemExit(f"resume: prediction block {k} was made with {done_pred[k]}, but the inner CV chooses {bj}")
                    continue
                st = {}
                e5_te = [r for r in e5 if r["e5_fold"] == f]
                p = train_predict(a, name, tok, S.fit_rows(outer_tr) + ed, outer_te + e5_te, enc, best, seed, st)
                p, pe5 = p[:len(outer_te)], p[len(outer_te):]
                for r, l in zip(e5_te, pe5):          # E5 block first: a complete natural block implies a complete E5 block
                    we5.row(S.PRED_COLS, [r["out_id"], cond, sysname, f, seed, bj, l])
                for c, l in zip(outer_te, p):
                    wp.row(S.PRED_COLS, [c["claim_id"], cond, sysname, f, seed, bj, l])
                wt.row(TH, [cond, sysname, f, "refit", "", best, seed, st.get("n_train"), len(ed), st.get("steps"), st.get("train_s"),
                            st.get("n_test"), st.get("pred_s"), st.get("s_per_step")])
                print(f"  {cond} outer {f} refit lr {best} seed {seed}: {st.get('train_s')}s train", flush=True)
    S.write_meta(a.out, f"meta_enc_{a.model}{suffix}.json", dict(
        data=info, edits=einfo, e5=e5info, model=name, model_revision=S.REVISIONS[name], top_k=a.top_k, conditions=conds, system=sysname, device=str(S.device()), folds_sha256=fh, label_set=labels,
        inner_scoring="macro-F1 over label_set" if len(labels) >= 2 else "binary error-detection F1",
        lr_grid=lrs, epochs=a.epochs, batch=a.batch, micro_batch=a.micro_batch, max_len=a.max_len, max_steps=a.max_steps,
        seeds=seeds, select_seed=a.select_seed, outer_folds=outer, total_seconds=round(time.time() - t0, 1)))
    print(f"{sysname}: done in {time.time() - t0:.1f}s -> {wp.path}")


if __name__ == "__main__":
    main()
