"""Shared data loading, bootstrap, metrics and output helpers for the pre-registered analysis (prereg.md, deviations D1-D18).

Reads only frozen inputs; never writes under annotation/ or runs/.
Conventions:
  - label codes as in the data (MISREPRESENTED); the paper name MISLEADING is used only in tables and figures (out_label).
  - design weights: phase weights of D17 correction (S-H 1, S-D 204/102, S-A 2508/187, S-N 719/55, from reference_R1.csv);
    RQ1 estimates (prevalence, H1-H3, E9 random) multiply them by the D10 (c) report weight n_verified / n_kept.
  - resampling: two-stage cluster bootstrap (prereg 4a, D17 addendum a2), 2,000 replicates, seed 20261110.
"""
import json, math, os, re
import numpy as np
import pandas as pd

MAIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(MAIN, "analysis")
TAB = os.path.join(OUT, "tables")
FIG = os.path.join(OUT, "figures")
ERR = os.path.join(OUT, "error_analysis")
B = 2000
SEED = 20261110
SEED_ERRSAMPLE = 20261124          # seed of the error-analysis samples (not a prereg seed; logged in numbers.json)
LABELS = ["SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"]
LIX = {l: i for i, l in enumerate(LABELS)}
ERRL = {"CONTRADICTED", "MISREPRESENTED"}
PAPER = {"MISREPRESENTED": "MISLEADING"}
STRATA2 = ["S-D", "S-A", "S-N"]
OUTLET_TYPE = {"APA": "agency", "apa": "agency", "Report": "agency", "Trend": "agency", "azertac": "agency", "AZERTAC": "agency",
               "Oxu.az": "general portal", "Qafqazinfo": "general portal", "Musavat": "general portal", "Banker.az": "finance portal"}
SYSTEMS_LLM = ["haiku", "sonnet", "gpt55", "qwen"]
SYS_NAME = {"haiku": "Claude Haiku 5.5", "sonnet": "Claude Sonnet 5.5", "gpt55": "GPT-5.5", "qwen": "Qwen2.5-7B (open-weight)",
            "majority": "Majority baseline", "logreg": "Logistic regression", "gbm": "Gradient boosting", "nli": "NLI mDeBERTa (k=3)",
            "nli_k1": "NLI mDeBERTa (k=1)", "nli_k5": "NLI mDeBERTa (k=5)", "haiku_2pass": "Haiku two-pass (E10)",
            "logreg_edits": "Logistic regression + edits (E2b)", "gbm_edits": "Gradient boosting + edits (E2b)",
            "logreg_hum": "Logistic regression, human labels only", "gbm_hum": "Gradient boosting, human labels only",
            "xlmr": "XLM-R", "azbert": "AzBERT", "mdeberta": "mDeBERTa-v3"}


def out_label(x):
    if isinstance(x, str):
        for k, v in PAPER.items():
            x = x.replace(k, v)
    return x


def p(*a):
    return os.path.join(MAIN, *a)


def issuer(ann_id):
    return {"CBAR": "CBAR", "DVX": "DVX", "EMSMN": "EMSMN"}[ann_id.split("-")[0]]


# Data
_cache = {}


def load():
    """All frozen inputs, joined. Cached."""
    if _cache:
        return _cache
    ref = pd.read_csv(p("annotation/reference/reference_R1.csv"), dtype={"distortion_type": str, "content_tags": str, "cause": str})
    for c in ("distortion_type", "content_tags", "cause"):
        ref[c] = ref[c].fillna("")
    claims = pd.read_csv(p("annotation/claims/claims_s1.csv"))
    rep = pd.read_csv(p("sampling/report_features.csv"))
    src = pd.read_csv(p("sampling/sources_summary.csv"))
    clu = pd.read_csv(p("sampling/clusters.csv"))
    a1 = pd.read_csv(p("annotation/llm/labels_A1.csv"))
    a2 = pd.read_csv(p("annotation/llm/labels_A2.csv"))
    wj = json.load(open(p("annotation/reference/weights.json")))
    claims = claims.merge(rep[["report_id", "sample", "outlet", "weight", "copy_ratio", "rewritten", "syndicated"]].rename(columns={"weight": "rep_weight"}),
                          on="report_id", how="left")
    claims = claims.merge(src[["ann_id", "has_t2", "t1_is_act", "chars_T2"]], on="ann_id", how="left")
    claims = claims.merge(clu, on="ann_id", how="left")
    assert claims["cluster"].notna().all() and claims["sample"].notna().all()
    claims["issuer"] = claims["ann_id"].map(issuer)
    claims["outlet_type"] = claims["outlet"].map(OUTLET_TYPE)
    assert claims["outlet_type"].notna().all(), claims[claims.outlet_type.isna()].outlet.unique()
    claims["c2_eligible"] = ((claims["has_t2"] == 1) & (claims["t1_is_act"] == 0)).astype(int)
    claims["A1"] = claims["claim_id"].map(dict(zip(a1.claim_id, a1.label)))
    claims["A2"] = claims["claim_id"].map(dict(zip(a2.claim_id, a2.label)))
    assert claims["A1"].notna().all() and claims["A2"].notna().all()
    # reference: check weights against weights.json, attach claim attributes
    for s, w in wj["weight"].items():
        assert np.allclose(ref.loc[ref.set == s, "weight"], w, atol=1e-5), s
        assert (ref.set == s).sum() == wj["n_R1"][s], s
    keep = ["claim_id", "outlet", "outlet_type", "rep_weight", "copy_ratio", "rewritten", "syndicated", "has_t2", "t1_is_act",
            "c2_eligible", "cluster", "issuer", "chars_T2", "span", "claim_text", "span_found"]
    ref = ref.merge(claims[keep], on="claim_id", how="left")
    assert ref["cluster"].notna().all()
    assert (ref["A1"] == ref["claim_id"].map(dict(zip(claims.claim_id, claims.A1)))).all()
    ref["w_phase"] = ref["weight"].astype(float)
    ref["w_rq1"] = ref["w_phase"] * ref["rep_weight"]
    ref["is_err"] = ref["label"].isin(ERRL).astype(int)
    ref = ref.reset_index(drop=True)
    _cache.update(ref=ref, claims=claims, rep=rep, src=src, clu=clu, weights=wj,
                  edits=pd.read_csv(p("annotation/reference/edits_R1.csv"), dtype={"distortion_type": str, "intended_distortion_type": str}),
                  edit_set=pd.read_csv(p("annotation/edits/edit_set_v2.csv")),
                  pairs=pd.read_csv(p("annotation/reference/pairs_R1.csv")))
    return _cache


# Bootstrap
class Boot:
    """Two-stage cluster bootstrap for one domain (prereg 4a; D17 addendum a2).

    Stage 1: resample the domain's clusters (union-find clusters of sampling/clusters.csv) with replacement; the pool is
    every cluster that holds at least one claim of the domain's samples (labelled or not).
    Stage 2: inside each resampled cluster copy, R1's claims of each phase-2 stratum (S-D, S-A, S-N) are resampled with
    replacement within the stratum; S-H claims are kept as they are (census given phase 1).
    m_c copies of a cluster with L claims in a stratum are drawn as Multinomial(m_c * L, 1/L) over those L claims, which
    has the same distribution as m_c independent size-L resamples.
    counts: (B, n) int matrix over the domain's reference rows; M: (B, K) cluster multiplicities (used for edits, H5)."""

    def __init__(self, ref_dom, samples, b=B, seed=SEED):
        claims = load()["claims"]
        self.clusters = sorted(claims.loc[claims["sample"].isin(samples), "cluster"].unique())
        self.cix = {c: i for i, c in enumerate(self.clusters)}
        self.ids = list(ref_dom["claim_id"])
        self.pos = {c: i for i, c in enumerate(self.ids)}
        n, K = len(ref_dom), len(self.clusters)
        rng = np.random.default_rng(seed)
        groups = {}
        for i, (c, s) in enumerate(zip(ref_dom["cluster"], ref_dom["set"])):
            groups.setdefault((self.cix[c], s), []).append(i)
        self.M = np.zeros((b, K), dtype=np.int32)
        self.counts = np.zeros((b, n), dtype=np.int32)
        glist = sorted(groups.items())
        for r in range(b):
            m = np.bincount(rng.integers(0, K, K), minlength=K)
            self.M[r] = m
            for (k, s), idx in glist:
                if m[k] == 0:
                    continue
                if s == "S-H":
                    self.counts[r, idx] += m[k]
                else:
                    self.counts[r, idx] += rng.multinomial(m[k] * len(idx), [1.0 / len(idx)] * len(idx))

    def sub(self, mask):
        """Counts restricted to a boolean mask over the domain rows (domain estimation inside the same replicates)."""
        return self.counts[:, np.asarray(mask, dtype=bool)]


_boots = {}


def boot(domain):
    """domain: 'random' (random sample), 'benchmark', or 'all'. Same replicates reused by every statistic of the domain."""
    if domain not in _boots:
        ref = load()["ref"]
        samples = {"random": ["random"], "benchmark": ["benchmark"], "all": ["random", "benchmark"]}[domain]
        dom = ref[ref["sample"].isin(samples)].reset_index(drop=True)
        _boots[domain] = (dom, Boot(dom, samples))
    return _boots[domain]


# Metrics
def norm_pred(x):
    """Prediction label; anything that is not one of the five labels is scored as SUPPORTED (prereg 5)."""
    return x if x in LIX else "SUPPORTED"


def pair_onehot(gold, pred):
    g = np.array([LIX[x] for x in gold]); q = np.array([LIX[norm_pred(x)] for x in pred])
    P = np.zeros((len(g), 25)); P[np.arange(len(g)), g * 5 + q] = 1
    return P


def confs(P, w, counts=None):
    """Weighted confusion matrices: point (25,) and replicates (B, 25)."""
    pt = w @ P
    if counts is None:
        return pt, None
    return pt, (counts * w) @ P


def f1_from_conf(cf, labels):
    """cf (..., 25) -> dict label -> F1 (zero_division 0), plus precision/recall."""
    C = cf.reshape(cf.shape[:-1] + (5, 5))
    out = {}
    for l in labels:
        i = LIX[l]
        tp = C[..., i, i]; fp = C[..., :, i].sum(-1) - tp; fn = C[..., i, :].sum(-1) - tp
        den = 2 * tp + fp + fn
        out[l] = np.where(den > 0, 2 * tp / np.where(den > 0, den, 1), 0.0)
    return out


def prf_label(cf, l):
    C = cf.reshape(cf.shape[:-1] + (5, 5)); i = LIX[l]
    tp = C[..., i, i]; ps = C[..., :, i].sum(-1); gs = C[..., i, :].sum(-1)
    return (np.where(ps > 0, tp / np.where(ps > 0, ps, 1), 0.0), np.where(gs > 0, tp / np.where(gs > 0, gs, 1), np.nan))


def macro_f1(cf, labels):
    f = f1_from_conf(cf, labels)
    return np.mean([f[l] for l in labels], axis=0)


def binary_metrics(cf):
    """Error detection (CON or MIS vs the rest): precision, recall, F1; false-alarm rate on gold SUPPORTED."""
    C = cf.reshape(cf.shape[:-1] + (5, 5))
    e = [LIX["CONTRADICTED"], LIX["MISREPRESENTED"]]
    ne = [i for i in range(5) if i not in e]
    tp = C[..., e, :][..., :, e].sum((-1, -2)); fp = C[..., ne, :][..., :, e].sum((-1, -2)); fn = C[..., e, :][..., :, ne].sum((-1, -2))
    prec = np.where(tp + fp > 0, tp / np.where(tp + fp > 0, tp + fp, 1), 0.0)
    rec = np.where(tp + fn > 0, tp / np.where(tp + fn > 0, tp + fn, 1), np.nan)
    f1 = np.where(2 * tp + fp + fn > 0, 2 * tp / np.where(2 * tp + fp + fn > 0, 2 * tp + fp + fn, 1), 0.0)
    s = LIX["SUPPORTED"]; sup = C[..., s, :].sum(-1)
    fa = np.where(sup > 0, C[..., s, e].sum(-1) / np.where(sup > 0, sup, 1), np.nan)
    return {"err_precision": prec, "err_recall": rec, "err_f1": f1, "false_alarm": fa}


def kappa_from_conf(cf):
    C = cf.reshape(cf.shape[:-1] + (5, 5))
    n = C.sum((-1, -2)); n = np.where(n > 0, n, np.nan)
    po = np.trace(C, axis1=-2, axis2=-1) / n
    pe = (C.sum(-1) * C.sum(-2)).sum(-1) / n ** 2
    return (po - pe) / (1 - pe), po


def kappa_label(cf, l):
    """One label vs the rest (Cohen's kappa on the 2x2 collapse) and positive specific agreement 2a/(2a+b+c)."""
    C = cf.reshape(cf.shape[:-1] + (5, 5)); i = LIX[l]
    a = C[..., i, i]; b = C[..., i, :].sum(-1) - a; c = C[..., :, i].sum(-1) - a
    n = C.sum((-1, -2)); d = n - a - b - c
    n = np.where(n > 0, n, np.nan)
    po = (a + d) / n; pe = ((a + b) * (a + c) + (c + d) * (b + d)) / n ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        k = (po - pe) / (1 - pe)
        psa = np.where(2 * a + b + c > 0, 2 * a / (2 * a + b + c), np.nan)
    return k, psa


def kish(w):
    w = np.asarray(w, float)
    return float(w.sum() ** 2 / (w ** 2).sum()) if len(w) and (w ** 2).sum() > 0 else 0.0


def ci(reps, lo=2.5, hi=97.5):
    r = np.asarray(reps, float); r = r[~np.isnan(r)]
    if len(r) == 0:
        return [None, None]
    return [float(np.percentile(r, lo)), float(np.percentile(r, hi))]


def p_one_sided(reps, null, direction, b=B):
    """Prereg 4a: p = (1 + #replicates at or beyond the null in the wrong direction) / (B + 1); undefined (nan) replicates
    count as at the null. direction '>' means the hypothesis predicts estimate > null."""
    r = np.asarray(reps, float)
    und = np.isnan(r)
    bad = (r <= null) if direction == ">" else (r >= null)
    bad = bad | und
    return float((1 + bad.sum()) / (b + 1)), int(und.sum())


def p_two_sided(reps, null=0.0, b=B):
    lo, _ = p_one_sided(reps, null, ">", b); hi, _ = p_one_sided(reps, null, "<", b)
    return float(min(1.0, 2 * min(lo, hi)))


def holm(pvals):
    """Holm step-down adjusted p-values, dict key -> adjusted p (monotone, capped at 1)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, run, out = len(items), 0.0, {}
    for j, (k, pv) in enumerate(items):
        run = max(run, min(1.0, (m - j) * pv))
        out[k] = run
    return out


def f(x, d=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "NA"
    return f"{x:.{d}f}"


# Outputs
def write_table(df, name, title=None, note=None):
    """CSV + Markdown copy; label codes mapped to the paper name."""
    os.makedirs(TAB, exist_ok=True)
    d = df.copy()
    for c in d.columns:         # count columns stay integers when NaN made them float
        if re.search(r"(^n$|^n[ _]|[ _]n$|[ _]n[ _])", str(c)) and d[c].dtype.kind == "f":
            v = d[c].dropna()
            if len(v) and (v == v.round()).all():
                d[c] = d[c].astype("Int64")
    d.columns = [out_label(str(c)) for c in d.columns]
    for c in d.columns:
        if d[c].dtype == object:
            d[c] = d[c].map(out_label)
    d.to_csv(os.path.join(TAB, name + ".csv"), index=False)
    with open(os.path.join(TAB, name + ".md"), "w", encoding="utf-8") as fh:
        if title:
            fh.write(f"# {out_label(title)}\n\n")
        cols = list(d.columns)
        fh.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for _, r in d.iterrows():
            fh.write("| " + " | ".join("" if (v is pd.NA or (isinstance(v, float) and math.isnan(v))) else (f"{v:.3f}" if isinstance(v, float) else str(v)) for v in r) + " |\n")
        if note:
            fh.write(f"\n{out_label(note)}\n")


def clean(o):
    """JSON-safe conversion (numpy -> python, nan -> None)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if math.isnan(float(o)) else round(float(o), 6)
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    return o


def lab_set(ref_rows, min_n=10):
    """Prereg 4: macro-F1 label set = labels with >= 10 raw (unweighted) claims in the human-verified evaluation set."""
    vc = ref_rows["label"].value_counts()
    return [l for l in LABELS if vc.get(l, 0) >= min_n]


AZ_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def az_lower(s):
    return s.translate(AZ_LOWER).lower()
