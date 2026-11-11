"""Train and score system S0b: logistic regression and gradient boosting on overlap and cue features (prereg.md 4a, 5).

Features (C1, C2; computed against the condition's source, T1 or T1+T2):
  overlap  : share of claim word tokens / 5-char stems found in the source; best single-passage stem coverage and
             Jaccard; stem coverage of the top-3 passages (overlap retrieval, sys_common.rank_passages);
             share of claim word 3-grams and 5-grams found in the source (claim-level copy ratio)
  numbers  : count in claim, share found in source, any claim number missing from source, missing from the best
             passage, percent sign in claim
  dates    : years, dd.mm.yyyy dates and "<day> <month>" in claim; share found in source; any missing
  cues     : Azerbaijani cue groups (hedge/plan, done-status, universal quantifier, future/obligation, negation,
             inference connective, a fixed word list plan_list) counted in the claim, present in the best
             passage, and "in claim but in no top-3 passage"
  part     : headline / lead / body flags; claim length; log source length; has_t2
C0 (no source): TF-IDF of claim word 1-2 grams (fitted on the training part only) + the claim-only features
  (cues in claim, numbers/dates counts, part, length): the claim-words-only version.

Models and grids (prereg 4a): LogisticRegression C in {0.1, 1, 10} (lbfgs, class_weight balanced, features
standardised on the training part); GradientBoostingClassifier max_depth in {2, 3} x n_estimators in {100, 300}
(random_state 1, balanced sample weights). Each candidate is tuned by the inner 3-fold grouped CV of each outer
training part (macro-F1 over the evaluation label set), refit on the whole outer training part, and predicts the
outer test fold. Inner scores are written so sys_select.py can do the H7 cross-candidate selection.

Usage:
  python scripts/sys_tradml.py --dev --conditions C0,C1,C2 [--edits FILE] --out runs/dev_smoke
  (data options are defined in sys_common.add_data_args)
Outputs (in --out): predictions_tradml[_edits][_hum].csv, inner_tradml*.csv, features_<cond>.csv, meta_tradml*.json
"""
import argparse, json, math, os, re, time, warnings
from collections import Counter
import numpy as np
import sys_common as S

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]
CUES = {
    "hedge": r"planlaşdırıl|nəzərdə tutul|ola bilər|gözlənil|ehtimal|mümkün|layihə|təklif|müzakirə|hazırlan|nəzərdən keçiril|tövsiyə",
    "done": r"qəbul edil|təsdiq edil|təsdiqlən|qüvvəyə min|imzala|tətbiq olun|artıq|başlayıb|həyata keçirilib",
    "universal": r"\bhamı|\bbütün\b|\bhər bir\b|\bheç bir\b|\byalnız\b|\bancaq\b|\btamamilə\b|\bhər kəs",
    "future": r"\w+(?:acaq|əcək)(?:dır|dir|lar|lər)?\b|\w+(?:malı|məli)(?:dır|dir)?\b|məcburi|mütləq",
    "negation": r"\bdeyil\b|\byox\b|\byoxdur\b|qadağan|ləğv|\w+(?:mayacaq|məyəcək|mır|mir|mur|mür)\b",
    "inference": r"\byəni\b|\bdeməli\b|buna görə|nəticəsində|səbəbindən|bununla da",
    "plan_list": r"layihə|təklif|nəzərdə tutulur|\bhamı|\bbütün\b|ödəyəcək|tutulacaq|\byəni\b",
}
CUE_RE = {k: re.compile(v) for k, v in CUES.items()}
GRIDS = {"logreg": [{"C": c} for c in (0.1, 1, 10)],
         "gbm": [{"max_depth": d, "n_estimators": n} for d in (2, 3) for n in (100, 300)]}


def numbers(s):
    out = set()
    for m in re.findall(r"\d+(?:[.,]\d+)?", s):
        x = m.replace(",", ".")
        try:
            out.add(("%f" % float(x)).rstrip("0").rstrip("."))
        except ValueError:
            pass
    return out


def dates(s):
    t = S.norm(s)
    out = set(re.findall(r"\b(?:19|20)\d\d\b", t))
    out |= {f"{int(d)}.{int(m)}.{y}" for d, m, y in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.((?:19|20)\d\d)\b", t)}
    for d, mon in re.findall(r"\b(\d{1,2})[- ](" + "|".join(MONTHS) + r")", t):
        out.add(f"{int(d)}.{MONTHS.index(mon) + 1}")
    return out


def date_in_source(dt, src_dates_set, src_norm):
    if dt in src_dates_set:
        return True
    if dt.count(".") == 1:   # "<day>.<month>" also matches a dd.mm.yyyy date of the source
        return any(x.startswith(dt + ".") for x in src_dates_set)
    return dt in src_norm


def ngrams(t, n):
    return {tuple(t[i:i + n]) for i in range(len(t) - n + 1)}


def claim_only(c):
    t = S.norm(c["claim_text"])
    f = {f"cue_{k}": len(r.findall(t)) for k, r in CUE_RE.items()}
    f.update(n_words=len(t.split()), n_num=len(numbers(c["claim_text"])), n_date=len(dates(c["claim_text"])), pct=int("%" in t),
             part_headline=int(c["part"] == "headline"), part_lead=int(c["part"] == "lead"), part_body=int(c["part"] not in ("headline", "lead")))
    return f


_PASS = {}


def features(c, cond, dev):
    f = claim_only(c)
    src, has_t2 = S.source_text(c["ann_id"], cond, dev)
    key = (c["ann_id"], cond)
    if key not in _PASS:
        _PASS[key] = (S.chunk(src), set(S.toks(src)), set(S.stems(src)), S.toks(src), numbers(src), dates(src), S.norm(src))
    passages, stoks, sstems, slist, snums, sdates, snorm = _PASS[key]
    ct, cs = S.toks(c["claim_text"]), S.stems(c["claim_text"])
    cts, css = set(ct), set(cs)
    rank = S.rank_passages(c["claim_text"], passages)
    top = [passages[i] for i in rank[:3]]
    best = top[0] if top else ""
    bst = set(S.stems(best))
    top_st = set(S.stems(" ".join(top)))
    cn, cd = numbers(c["claim_text"]), dates(c["claim_text"])
    bn = numbers(best)
    src_ng3, src_ng5 = ngrams(slist, 3), ngrams(slist, 5)
    cg3, cg5 = ngrams(ct, 3), ngrams(ct, 5)
    f.update(
        tok_cov=len(cts & stoks) / max(1, len(cts)), stem_cov=len(css & sstems) / max(1, len(css)),
        best_cov=len(css & bst) / max(1, len(css)), best_jacc=len(css & bst) / max(1, len(css | bst)),
        top3_cov=len(css & top_st) / max(1, len(css)),
        copy3=len(cg3 & src_ng3) / max(1, len(cg3)) if cg3 else 0.0, copy5=len(cg5 & src_ng5) / max(1, len(cg5)) if cg5 else 0.0,
        num_match=len(cn & snums) / len(cn) if cn else 1.0, num_mismatch=int(bool(cn - snums)), num_mismatch_best=int(bool(cn - bn)),
        date_match=(sum(date_in_source(d, sdates, snorm) for d in cd) / len(cd)) if cd else 1.0,
        date_mismatch=int(any(not date_in_source(d, sdates, snorm) for d in cd)),
        log_src_words=math.log1p(len(slist)), has_t2=has_t2, n_passages=len(passages))
    bnorm, tnorm = S.norm(best), S.norm(" ".join(top))
    for k, r in CUE_RE.items():
        f[f"best_{k}"] = int(bool(r.search(bnorm)))
        f[f"only_claim_{k}"] = int(f[f"cue_{k}"] > 0 and not r.search(tnorm))
        f[f"src_{k}"] = int(bool(r.search(snorm)))
    return f


class Model:
    """One candidate with one setting. kind in {logreg, gbm}; text=True adds claim TF-IDF (C0)."""

    def __init__(self, kind, setting, text):
        self.kind, self.setting, self.text = kind, setting, text

    def _X(self, rows, fit):
        from scipy import sparse
        X = np.array([[r["_f"][k] for k in self.keys] for r in rows], dtype=float)
        if self.kind == "logreg":
            if fit:
                self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
            X = (X - self.mu) / self.sd
        if not self.text:
            return X
        if fit:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, preprocessor=S.norm, token_pattern=r"(?u)\b\w+\b")
            T = self.vec.fit_transform([r["claim_text"] for r in rows])
        else:
            T = self.vec.transform([r["claim_text"] for r in rows])
        return sparse.hstack([sparse.csr_matrix(X), T]).tocsr()

    def fit(self, rows):
        if not rows:
            raise SystemExit("empty training part (check --train-on human and the gold file)")
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.utils.class_weight import compute_sample_weight
        self.keys = sorted(rows[0]["_f"])
        X, y = self._X(rows, True), [r["fit_label"] for r in rows]
        self.single = None
        if len(set(y)) < 2:
            self.single = y[0]; return self
        if self.kind == "logreg":
            self.m = LogisticRegression(C=self.setting["C"], solver="lbfgs", class_weight="balanced", max_iter=5000)
            self.m.fit(X, y)
        else:
            self.m = GradientBoostingClassifier(random_state=1, **self.setting)
            self.m.fit(X, y, sample_weight=compute_sample_weight("balanced", y))
        return self

    def predict(self, rows):
        if self.single:
            return [self.single] * len(rows)
        return list(self.m.predict(self._X(rows, False)))


def run_candidate(kind, natural, edits, fold, labels, cond, text, sysname, w_pred, w_inner, mode):
    for f in range(S.OUTER_K):
        outer_tr = [c for c in natural if fold[c["claim_id"]] != f]
        outer_te = [c for c in natural if fold[c["claim_id"]] == f]
        splits = S.inner_splits(outer_tr)
        scores = []
        for si, setting in enumerate(GRIDS[kind]):
            fs = []
            for ii, (tr, va) in enumerate(splits):
                tr_rows = [outer_tr[i] for i in tr]
                va_rows = [outer_tr[i] for i in va]
                tr_fit = S.fit_rows(tr_rows) + S.edits_for(edits, {r["cluster"] for r in tr_rows})
                p = Model(kind, setting, text).fit(tr_fit).predict(va_rows)
                sc = S.inner_score(va_rows, p, labels, mode)
                fs.append(sc)
                w_inner.row(["condition", "system", "outer_fold", "setting", "inner_fold", "score"], [cond, sysname, f, S.setting_json(setting), ii, repr(sc)])
            scores.append(sum(fs) / len(fs))
        bi = max(range(len(scores)), key=lambda i: (scores[i], -i))   # ties: first setting in grid order
        best = GRIDS[kind][bi]
        w_inner.row(["condition", "system", "outer_fold", "setting", "inner_fold", "score"], [cond, sysname, f, S.setting_json(best), "chosen", repr(scores[bi])])
        tr_fit = S.fit_rows(outer_tr) + S.edits_for(edits, {r["cluster"] for r in outer_tr})
        p = Model(kind, best, text).fit(tr_fit).predict(outer_te)
        for c, l in zip(outer_te, p):
            w_pred.row(S.PRED_COLS, [c["claim_id"], cond, sysname, f, 1, S.setting_json(best), l])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    S.add_data_args(ap)
    ap.add_argument("--conditions", default="C0,C1,C2")
    ap.add_argument("--candidates", default="logreg,gbm")
    a = ap.parse_args()
    conds = S.parse_conditions(a.conditions)
    cands = [x for x in a.candidates.split(",") if x]
    if not cands or any(x not in GRIDS for x in cands) or len(cands) != len(set(cands)):
        raise SystemExit(f"invalid --candidates {a.candidates!r}: use values from {list(GRIDS)}")
    t0 = time.time()
    claims, info = S.load_claims(a)
    edits, einfo = S.load_edits(a, claims)
    fold = S.outer_folds(claims)
    fh = S.write_folds(claims, fold, a.out)
    labels = S.label_set(claims, a.min_label_n)
    suffix = ("_edits" if a.edits else "") + ("_hum" if a.train_on == "human" else "")
    pname, iname = f"predictions_tradml{suffix}.csv", f"inner_tradml{suffix}.csv"
    S.check_manifest(a.out, f"manifest_tradml{suffix}.json", S.manifest(a, claims, edits, fold, labels, dict(
        grids=GRIDS, conditions=conds, candidates=cands), __file__), False)
    S.reset(a.out, [pname, iname])
    w_pred, w_inner = S.Writer(a.out, pname), S.Writer(a.out, iname)
    timing = {}
    for cond in conds:
        t1 = time.time()
        for r in claims + edits:
            r["_f"] = claim_only(r) if cond == "C0" else features(r, cond, a.dev)
        keys = sorted(claims[0]["_f"])
        with open(os.path.join(a.out, f"features_{cond}.csv"), "w", encoding="utf-8") as fo:
            fo.write("claim_id," + ",".join(keys) + "\n")
            for r in claims + edits:
                fo.write(r["claim_id"] + "," + ",".join(str(round(r["_f"][k], 5)) for k in keys) + "\n")
        tf = time.time() - t1
        for kind in cands:
            t2 = time.time()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                run_candidate(kind, claims, edits, fold, labels, cond, cond == "C0", f"S0b_{kind}{suffix}", w_pred, w_inner, a.inner_score)
            timing[f"{cond}_{kind}"] = round(time.time() - t2, 1)
        timing[f"{cond}_features"] = round(tf, 1)
        print(f"{cond}: done ({timing})", flush=True)
    S.write_meta(a.out, f"meta_tradml{suffix}.json", dict(data=info, edits=einfo, folds_sha256=fh, label_set=labels,
                 inner_scoring="macro-F1 over label_set" if len(labels) >= 2 else "binary error-detection F1 (fewer than 2 labels qualify)",
                 grids=GRIDS, seconds=timing, total_seconds=round(time.time() - t0, 1)))
    print(f"S0b: {len(claims)} claims (+{len(edits)} edits), label set {labels}, {time.time() - t0:.1f}s -> {w_pred.path}")


if __name__ == "__main__":
    main()
