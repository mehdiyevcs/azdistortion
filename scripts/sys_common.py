"""Shared code for the non-LLM systems (S0, S0b, S1, S2, S2b; prereg sections 4a and 5).

Data loading (dev = pilot, main = frozen main-study files), source conditions C0/C1/C2, passage chunking and
overlap retrieval, the grouped outer/inner CV folds of prereg 4a, the macro-F1 label set, and output writers.
All system scripts (sys_majority.py, sys_tradml.py, sys_nli.py, sys_encoder.py, sys_select.py) import this file,
so every system sees the same claims, the same sources, the same retrieval and the same folds.

Prereg 4a points implemented here:
  - outer 5-fold CV grouped by cluster (announcement clusters; ann_id when sampling/clusters.csv is absent),
    inner 3-fold grouped CV inside each outer training part; fold seed 20261111;
  - inner scoring = macro-F1 over the evaluation label set (labels with >= 10 raw claims in the human-verified
    reference); if fewer than 2 labels qualify, binary error detection F1 (CON or MIS vs rest) is used instead;
  - training labels = human label where one exists, otherwise the agreed-LLM label (--train-on merged), or human
    labels only (--train-on human, the secondary variant);
  - edits (E2 variant b) join a training part only if their base claim's cluster is in that training part, and are
    never in a validation or test part;
  - UNASSESSABLE (prereg section 3; excluded from scores): every claim is kept and predicted; a claim whose training
    label is UNASSESSABLE (or missing) is not used as a training target; scoring (inner here, outer in the analysis)
    drops claims whose human-verified reference label is UNASSESSABLE, at scoring time only.
The dev mode reads the pilot files from a folder "pilot" next to the repository root.
"""
import csv, glob, hashlib, json, math, os, re, sys, time, warnings
from collections import Counter, defaultdict

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILOT = os.path.join(os.path.dirname(MAIN), "pilot")
LABELS = ["SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"]
SCORED_LABELS = [l for l in LABELS if l != "UNASSESSABLE"]     # labels that enter scores and training targets
ERROR_LABELS = {"CONTRADICTED", "MISREPRESENTED"}
CONDITIONS = ["C0", "C1", "C2"]
SEED_CV = 20261111
OUTER_K, INNER_K = 5, 3
BOILER = ("gov.az domeni", "Güvənilir vebsayt", "URL çubuğunda", "Dili seçin", "Axtar")
PRED_COLS = ["claim_id", "condition", "system", "fold", "seed", "setting", "label"]   # setting = JSON of the setting that made the row
# Pinned Hugging Face commits (frozen with the retrieval settings, prereg 5). Every load passes revision=REVISIONS[name].
REVISIONS = {
    "FacebookAI/xlm-roberta-base": "e73636d4f797dec63c3081bb6ed5c7b0bb3f2089",
    "allmalab/bert-base-aze": "5fd824965138a261552fc5ca333e91f4fa45cc67",
    "microsoft/mdeberta-v3-base": "a0484667b22365f84929a935b5e50a51f71f159d",
    "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7": "b5113eb38ab63efdd7f280f8c144ea8b13f978ce",
}


def parse_conditions(s):
    """Comma list of source conditions; only C0, C1, C2 are valid (anything else, an empty list or a repeat stops)."""
    out = [x.strip() for x in (s or "").split(",") if x.strip()]
    bad = [x for x in out if x not in CONDITIONS]
    if not out or bad or len(out) != len(set(out)):
        raise SystemExit(f"invalid --conditions {s!r}: use a comma list of distinct values from {CONDITIONS}")
    return out


# ---------------------------------------------------------------- text
def norm(s):
    """Lowercase with Azerbaijani/Turkish dotted/dotless I handled (Python's lower() turns 'İ' into 'i' + U+0307)."""
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def toks(s):
    return re.findall(r"\w+", norm(s))


def stems(s, n=5):
    """Crude stemmer for an agglutinative language: the first n characters of each word token."""
    return [t[:n] for t in toks(s)]


def chunk(text, min_words=6, max_words=120):
    """Split a source into passages: sentences / lines, short pieces merged forward, long pieces cut into windows."""
    pieces = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        pieces += [p.strip() for p in re.split(r"(?<=[.!?;])\s+(?=[\"“«(A-ZƏÖÜĞÇŞİ0-9])", line) if p.strip()]
    out, buf = [], ""
    for p in pieces:
        buf = (buf + " " + p).strip() if buf else p
        if len(buf.split()) >= min_words:
            out.append(buf); buf = ""
    if buf:
        if out and len(out[-1].split()) + len(buf.split()) <= max_words:
            out[-1] = out[-1] + " " + buf
        else:
            out.append(buf)
    final = []
    for p in out:
        w = p.split()
        if len(w) <= max_words:
            final.append(p)
        else:
            for i in range(0, len(w), max_words):
                final.append(" ".join(w[i:i + max_words]))
    return final


def overlap_score(claim_toks, passage):
    """Retrieval score used in the pilot: |q & t| / sqrt(1 + |t|) over word-token sets."""
    t = set(toks(passage))
    return len(claim_toks & t) / math.sqrt(1 + len(t))


def rank_passages(claim, passages):
    """Indices of passages, best first (ties: document order)."""
    q = set(toks(claim))
    return sorted(range(len(passages)), key=lambda i: (-overlap_score(q, passages[i]), i))


# ---------------------------------------------------------------- sources
def _pilot_lines(folder):
    out = []
    for f in sorted(glob.glob(f"{folder}/text_*.txt")) + sorted(glob.glob(f"{folder}/tables_*.txt")):
        out += [l.strip() for l in open(f, encoding="utf-8") if l.strip() and not any(b in l for b in BOILER)]
    return "\n".join(out)


_SRC_CACHE = {}


def source_text(ann_id, cond, dev):
    """(text, has_t2) for a condition. C0 -> ''. C1 -> T1. C2 -> T1 + T2 (T2 empty when the announcement has none).
    dev: pilot folders as run_llm.py reads them (<aid>/ = T1, <aid>-DEC/ = T2). main: data/sources/<aid>/T1.txt, T2.txt."""
    if cond not in CONDITIONS:
        raise SystemExit(f"unknown condition {cond!r}")
    if cond == "C0":
        return "", 0
    key = (ann_id, dev)
    if key not in _SRC_CACHE:
        if dev:
            root = os.path.join(PILOT, "data/raw/announcements")
            t1 = _pilot_lines(os.path.join(root, ann_id))
            d = os.path.join(root, ann_id + "-DEC")
            t2 = _pilot_lines(d) if os.path.isdir(d) else ""
        else:
            root = os.path.join(MAIN, "data/sources", ann_id)
            t1 = open(os.path.join(root, "T1.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(root, "T1.txt")) else ""
            p2 = os.path.join(root, "T2.txt")
            t2 = open(p2, encoding="utf-8").read() if os.path.exists(p2) else ""
            mp = os.path.join(root, "meta.json")
            if t2.strip() and os.path.exists(mp) and json.load(open(mp, encoding="utf-8")).get("t1_is_act") == 1:
                t2 = ""            # prereg D3 (+ addendum): T1 is the full act, so C2 = C1 (as scripts/run_llm.py source_lines)
            if not t1:
                warnings.warn(f"empty T1 for {ann_id}")
        _SRC_CACHE[key] = (t1, t2)
    t1, t2 = _SRC_CACHE[key]
    if cond == "C1":
        return t1, 0
    return (t1 + ("\n\n" + t2 if t2.strip() else "")), int(bool(t2.strip()))


# ---------------------------------------------------------------- claims and labels
def add_data_args(p):
    g = p.add_argument_group("data")
    g.add_argument("--dev", action="store_true", help="use the 155 pilot dev claims (pilot/adjudication/gold_labels_v1.csv) and pilot sources")
    g.add_argument("--claims", default=os.path.join(MAIN, "annotation/claims/claims_s1.csv"))
    g.add_argument("--clusters", default=os.path.join(MAIN, "sampling/clusters.csv"), help="ann_id,cluster; if missing, cluster = ann_id")
    g.add_argument("--gold", default=os.path.join(MAIN, "annotation/reference/reference_R1.csv"),
                   help="human-verified reference: claim_id,label,weight (prereg section 3; frozen 2026-11-10 under D17)")
    g.add_argument("--train-labels", default="", help="claim_id,label for every claim (human where it exists, else agreed-LLM). "
                   "If empty: gold label, else the A1 label when A1 == A2 (annotation/llm/labels_A1.csv, labels_A2.csv)")
    g.add_argument("--train-on", choices=["merged", "human"], default="merged", help="merged = prereg primary; human = secondary variant")
    g.add_argument("--edits", default="", help="accepted edit set CSV (E2 variant b): adds edits to training parts only")
    g.add_argument("--min-label-n", type=int, default=10, help="macro-F1 label set threshold (prereg: 10; change only for dev smoke tests)")
    g.add_argument("--inner-score", choices=["human_weighted", "train"], default="human_weighted",
                   help="inner-CV selection objective (see sys_common.inner_score)")
    g.add_argument("--limit", type=int, default=0, help="debug: first N claims only")
    g.add_argument("--out", default=os.path.join(MAIN, "runs/dev_smoke"))
    return p


def _read(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def load_claims(a):
    """Returns list of dicts: claim_id, ann_id, cluster, part, claim_text, train_label, fit_label, gold_label (or None), weight.
    Every claim of the claims file is kept and predicted; no claim is dropped because of its label.
    train_label = human label where one exists, else agreed-LLM (prereg 4a); it stratifies the folds for every variant
    (claims without one are stratified as "NONE"), so folds are identical across variants. fit_label is what models
    are trained on: train_label (--train-on merged) or the human label (--train-on human), and None (not a training
    target) when that label is missing or UNASSESSABLE (UNASSESSABLE is excluded from all scores, prereg section 3)."""
    info = {}
    if a.dev:
        rows = _read(os.path.join(PILOT, "adjudication/gold_labels_v1.csv"))
        claims = []
        for r in rows:
            claims.append(dict(claim_id=r["claim_id"], ann_id=r["ann_id"], part="headline" if r["in_headline"] == "1" else "body",
                               claim_text=r["claim_text"], train_label=r["gold_label"] or None, fit_label=r["gold_label"] or None,
                               gold_label=r["gold_label"] or None, weight=1.0))
        info["source"] = "dev: pilot/adjudication/gold_labels_v1.csv (gold_label used as both training label and reference, weight 1)"
    else:
        rows = _read(a.claims)
        gold = {r["claim_id"]: r for r in _read(a.gold)} if os.path.exists(a.gold) else {}
        if not gold:
            warnings.warn(f"no gold file at {a.gold}: claims have no reference label (inner CV still runs on training labels)")
        tl = {}
        if a.train_labels:
            tl = {r["claim_id"]: r["label"] for r in _read(a.train_labels)}
            info["train_labels"] = a.train_labels
        else:
            l1 = {r["claim_id"]: r["label"] for r in _read(os.path.join(MAIN, "annotation/llm/labels_A1.csv"))}
            p2 = os.path.join(MAIN, "annotation/llm/labels_A2.csv")
            l2 = {r["claim_id"]: r["label"] for r in _read(p2)} if os.path.exists(p2) else {}
            for cid, lab in l1.items():
                if cid in l2 and l2[cid] == lab:
                    tl[cid] = lab
            info["train_labels"] = "derived: agreed A1 == A2 labels, overridden by gold"
        claims = []
        for r in rows:
            g = gold.get(r["claim_id"])
            human = g["label"] if g else None
            train = human or tl.get(r["claim_id"])
            claims.append(dict(claim_id=r["claim_id"], ann_id=r["ann_id"], part=r.get("part", "body"), claim_text=r["claim_text"],
                               train_label=train, fit_label=human if a.train_on == "human" else train, gold_label=human,
                               weight=float(g["weight"]) if g and g.get("weight") else None))
        info["source"] = f"main: {a.claims}; gold {a.gold} ({len(gold)} rows); train_on={a.train_on}"
    for c in claims:
        for k in ("train_label", "fit_label", "gold_label"):
            if c[k] is not None and c[k] not in LABELS:
                raise SystemExit(f"{c['claim_id']}: unknown {k} {c[k]!r}")
        if c["fit_label"] not in SCORED_LABELS:
            c["fit_label"] = None
        if c["claim_id"].startswith("EDIT:"):
            raise SystemExit(f"natural claim id {c['claim_id']} uses the reserved edit prefix EDIT:")
    info["n_not_training_target"] = sum(c["fit_label"] is None for c in claims)
    info["n_train_label_unassessable"] = sum(c["train_label"] == "UNASSESSABLE" for c in claims)
    info["n_no_train_label"] = sum(c["train_label"] is None for c in claims)
    info["n_gold_unassessable_not_scored"] = sum(c["gold_label"] == "UNASSESSABLE" for c in claims)
    if a.limit:
        claims = claims[:a.limit]
    cl = {}
    if os.path.exists(a.clusters) and not a.dev:
        cl = {r["ann_id"]: r["cluster"] for r in _read(a.clusters)}
        info["clusters"] = a.clusters
    else:
        info["clusters"] = "none found: cluster = ann_id"
    for c in claims:
        c["cluster"] = cl.get(c["ann_id"], c["ann_id"])
    ids = [c["claim_id"] for c in claims]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate claim_id in the claims file")
    info["n_claims"] = len(claims)
    info["train_label_counts"] = dict(Counter(str(c["train_label"]) for c in claims))
    info["n_clusters"] = len({c["cluster"] for c in claims})
    return claims, info


def load_edits(a, claims):
    """Accepted edits as training-only rows. Columns accepted: row_id|edit_id, orig_claim_id|base_claim_id, claim_text,
    gold|label, optional accepted (1/yes/accepted). Only CONTRADICTED / MISREPRESENTED rows are edits (the originals are
    natural claims already in the data). Cluster = cluster of the base claim's announcement."""
    if not a.edits:
        return [], {}
    by_id = {c["claim_id"]: c for c in claims}
    out, skipped = [], Counter()
    for r in _read(a.edits):
        lab = r.get("label") or r.get("gold")
        if lab not in ERROR_LABELS:
            skipped["not_an_edit_row"] += 1; continue
        acc = (r.get("accepted") or "1").strip().lower()
        if acc not in ("1", "yes", "accepted", "true"):
            skipped["not_accepted"] += 1; continue
        base = r.get("base_claim_id") or r.get("orig_claim_id")
        if base not in by_id:               # the base claim must be a natural claim of this run: it fixes cluster and fold
            skipped["base_claim_not_in_data"] += 1; continue
        if r["claim_text"].strip() == "":
            raise SystemExit(f"edit {r.get('edit_id') or r.get('row_id')}: empty claim_text")
        b = by_id[base]
        if r.get("ann_id") and r["ann_id"] != b["ann_id"]:
            raise SystemExit(f"edit {r.get('edit_id') or r.get('row_id')}: ann_id {r['ann_id']} != base claim's {b['ann_id']}")
        eid = (r.get("edit_id") or r.get("row_id") or "").strip()
        if not eid:
            raise SystemExit("edit row without edit_id/row_id")
        out.append(dict(claim_id="EDIT:" + eid, ann_id=b["ann_id"], cluster=b["cluster"], part=b.get("part", "body"),
                        claim_text=r["claim_text"], train_label=lab, fit_label=lab, gold_label=None, weight=None, base_claim_id=base, is_edit=1))
    ids = [e["claim_id"] for e in out]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate edit ids in " + a.edits)
    clash = set(ids) & set(by_id)          # natural ids cannot start with EDIT: (load_claims), so this is a second guard
    if clash:
        raise SystemExit(f"edit ids collide with natural claim ids: {sorted(clash)[:5]}")
    return out, {"edits_used": len(out), "edits_label_counts": dict(Counter(e["train_label"] for e in out)), "edits_skipped": dict(skipped)}


def fit_rows(rows):
    """Rows usable for fitting (fit_label present; never UNASSESSABLE)."""
    return [r for r in rows if r.get("fit_label") in SCORED_LABELS]


def edits_for(edits, train_clusters):
    """Edits that may join a training part: those whose base claim's cluster is inside it."""
    return [e for e in edits if e["cluster"] in train_clusters]


# ---------------------------------------------------------------- folds
def _sgkf(k, y, groups, seed):
    from sklearn.model_selection import StratifiedGroupKFold
    n_groups = len(set(groups))
    if n_groups < k:
        raise SystemExit(f"grouped {k}-fold CV is not feasible: only {n_groups} clusters (prereg 4a fixes 5 outer / 3 inner folds)")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return list(StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed).split(list(range(len(y))), y, groups))


def outer_folds(claims):
    """claim_id -> outer fold (0..4). StratifiedGroupKFold by cluster, stratified on the training label (a design
    choice; claims without one count as "NONE"), seed 20261111."""
    y = [c["train_label"] or "NONE" for c in claims]
    g = [c["cluster"] for c in claims]
    fold = {}
    for f, (_, te) in enumerate(_sgkf(OUTER_K, y, g, SEED_CV)):
        for i in te:
            fold[claims[i]["claim_id"]] = f
    return fold


def inner_splits(train_claims):
    """3 grouped inner splits of an outer training part (natural claims only): list of (train_idx, val_idx)."""
    y = [c["train_label"] or "NONE" for c in train_claims]
    g = [c["cluster"] for c in train_claims]
    return _sgkf(INNER_K, y, g, SEED_CV)


def write_folds(claims, fold, out_dir):
    """Write folds.csv; if the run directory already has a different folds.csv, stop (one run dir = one fold set)."""
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "folds.csv")
    rows = [(c["claim_id"], c["ann_id"], c["cluster"], fold[c["claim_id"]]) for c in claims]
    import io
    buf = io.StringIO(newline="")
    w = csv.writer(buf); w.writerow(["claim_id", "ann_id", "cluster", "fold"]); w.writerows(rows)
    data = buf.getvalue().encode("utf-8")
    h = hashlib.sha256(data).hexdigest()
    if os.path.exists(p):
        old = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if old != h:
            raise SystemExit(f"{p} exists with different folds (claims, clusters or labels changed): use a new --out directory")
    else:
        open(p, "wb").write(data)
    # leakage guard: no cluster in two outer folds
    cf = defaultdict(set)
    for _, _, cl, fo in rows:
        cf[cl].add(fo)
    assert all(len(v) == 1 for v in cf.values()), "a cluster spans two outer folds"
    return h


def inner_hash(claims, fold):
    """Hash of every outer fold's inner (train, val) claim-id partition: candidates are comparable only if equal."""
    parts = []
    for f in range(OUTER_K):
        tr = [c for c in claims if fold[c["claim_id"]] != f]
        for _, va in inner_splits(tr):
            parts.append(f"{f}:" + ",".join(sorted(tr[i]["claim_id"] for i in va)))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def data_hash(rows):
    """Hash of the training population (claims and edits with clusters and labels)."""
    key = sorted((r["claim_id"], r["ann_id"], r["cluster"], str(r.get("part")), str(r.get("base_claim_id")), str(r["train_label"]),
                  str(r["fit_label"]), str(r.get("gold_label")), str(r.get("weight")), r["claim_text"]) for r in rows)
    return hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()


def sources_hash(claims, dev):
    """Hash of the T1 and T2 texts of every announcement in the run (the evidence all source conditions read)."""
    h = hashlib.sha256()
    for ann in sorted({c["ann_id"] for c in claims}):
        source_text(ann, "C1", dev)
        t1, t2 = _SRC_CACHE[(ann, dev)]
        h.update(f"{ann}\x00{t1}\x00{t2}\x00".encode("utf-8"))
    return h.hexdigest()


def file_hash(path):
    return hashlib.sha256(open(os.path.abspath(path), "rb").read()).hexdigest()


def code_hash():
    """Hash of the shared code (sys_common.py) that defines chunking, retrieval, folds and scoring."""
    return file_hash(__file__)


def lib_versions():
    import importlib.metadata as md
    out = {}
    for p in ("torch", "transformers", "tokenizers", "scikit-learn", "numpy", "scipy", "sentencepiece"):
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


def manifest(a, claims, edits, fold, labels, extra, producer):
    """Everything that must match for runs/candidates to be combined (resume, H7 selection). producer = the calling
    script's path; its hash is recorded with the shared code's hash, the library versions and (in extra) the model
    name and pinned revision."""
    return dict(sources_sha256=sources_hash(claims, a.dev), common_code_sha256=code_hash(), producer=os.path.basename(producer),
                producer_sha256=file_hash(producer), libraries=lib_versions(),
                folds_sha256=hashlib.sha256(json.dumps(sorted(fold.items())).encode()).hexdigest(), inner_sha256=inner_hash(claims, fold),
                claims_sha256=data_hash(claims), edits_sha256=data_hash(edits) if edits else "", label_set=labels,
                min_label_n=a.min_label_n, inner_score=a.inner_score, train_on=a.train_on, dev=bool(a.dev), limit=a.limit, **extra)


def atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def check_manifest(out_dir, name, man, resume, outputs=()):
    """Write the manifest (atomically); when resuming, stop if an existing one differs. A resume without a manifest
    is refused unless none of the run's output files exist yet (then it is a fresh start)."""
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, name)
    if resume and not os.path.exists(p):
        if any(os.path.exists(os.path.join(out_dir, o)) for o in outputs) or not outputs:
            raise SystemExit(f"--resume refused: no manifest {p} but outputs exist; start a fresh run (new --out or no --resume)")
    elif resume:
        old = json.load(open(p, encoding="utf-8"))
        diff = [k for k in set(old) | set(man) if old.get(k) != man.get(k)]
        if diff:
            raise SystemExit(f"--resume refused: {p} differs in {diff}; use a new --out or drop --resume")
        return
    atomic_json(p, man)


# ---------------------------------------------------------------- scoring
def inner_score(va_rows, pred, labels, mode):
    """Inner-CV selection score (prereg 4a: macro-F1 over the evaluation label set).
    mode 'human_weighted': natural validation claims with a human-verified label other than UNASSESSABLE, scored
    against that label with the design weights (the same objective and exclusion as the outer evaluation); stops if a
    validation part has no such claim or a weight is missing. mode 'train': validation claims with a fit label, unweighted."""
    if mode == "human_weighted":
        idx = [i for i, r in enumerate(va_rows) if r.get("gold_label") in SCORED_LABELS]
        bad = [va_rows[i]["claim_id"] for i in idx if not (isinstance(va_rows[i].get("weight"), float) and math.isfinite(va_rows[i]["weight"]) and va_rows[i]["weight"] > 0)]
        if bad:
            raise SystemExit(f"human-verified claims without a positive finite design weight: {bad[:5]}")
        if not idx:
            raise SystemExit("an inner validation part has no human-verified claim; human_weighted inner scoring is infeasible "
                             "(use --inner-score train only if that is recorded as a deviation)")
        return macro_f1([va_rows[i]["gold_label"] for i in idx], [pred[i] for i in idx], labels, [va_rows[i]["weight"] for i in idx])
    idx = [i for i, r in enumerate(va_rows) if r.get("fit_label") in SCORED_LABELS]
    if not idx:
        raise SystemExit("an inner validation part has no fit labels")
    return macro_f1([va_rows[i]["fit_label"] for i in idx], [pred[i] for i in idx], labels)



def label_set(claims, min_n):
    """Prereg 4a: labels with >= min_n raw claims in the human-verified evaluation set (gold_label), UNASSESSABLE
    excluded (it is not scored). If there is no gold yet, the training labels are used (and this is logged)."""
    src = [c["gold_label"] for c in claims if c.get("gold_label")] or [c["train_label"] for c in claims]
    cnt = Counter(src)
    return [l for l in SCORED_LABELS if cnt.get(l, 0) >= min_n]


def scored(c):
    """True if a natural claim enters scoring: it has a human-verified reference label other than UNASSESSABLE.
    The outer evaluation applies the same rule (UNASSESSABLE claims are predicted but never scored)."""
    return c.get("gold_label") in SCORED_LABELS


def macro_f1(y, p, labels, w=None):
    """Macro-F1 over `labels` (zero_division = 0); if fewer than 2 labels, binary error-detection F1 (CON or MIS vs rest)."""
    w = w or [1.0] * len(y)
    if len(labels) < 2:
        tp = sum(wi for yi, pi, wi in zip(y, p, w) if yi in ERROR_LABELS and pi in ERROR_LABELS)
        fp = sum(wi for yi, pi, wi in zip(y, p, w) if yi not in ERROR_LABELS and pi in ERROR_LABELS)
        fn = sum(wi for yi, pi, wi in zip(y, p, w) if yi in ERROR_LABELS and pi not in ERROR_LABELS)
        return 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    fs = []
    for l in labels:
        tp = sum(wi for yi, pi, wi in zip(y, p, w) if yi == l and pi == l)
        fp = sum(wi for yi, pi, wi in zip(y, p, w) if yi != l and pi == l)
        fn = sum(wi for yi, pi, wi in zip(y, p, w) if yi == l and pi != l)
        fs.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(fs) / len(fs)


# ---------------------------------------------------------------- output
class Writer:
    def __init__(self, out_dir, name):
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, name)
        new = not os.path.exists(self.path)
        self.f = open(self.path, "a", newline="", encoding="utf-8")
        self.w = csv.writer(self.f)
        self.header_written = not new

    def row(self, header, values):
        if not self.header_written:
            self.w.writerow(header); self.header_written = True
        self.w.writerow(values); self.f.flush()


def reset(out_dir, names):
    for n in names:
        p = os.path.join(out_dir, n)
        if os.path.exists(p):
            os.remove(p)


def write_meta(out_dir, name, meta):
    os.makedirs(out_dir, exist_ok=True)
    meta = dict(meta, python=sys.version.split()[0], written=time.strftime("%Y-%m-%d %H:%M:%S"))
    atomic_json(os.path.join(out_dir, name), json.loads(json.dumps(meta, default=str)))


def setting_json(d):
    """Canonical JSON of a setting (key order fixed), used in predictions, inner rows and selection."""
    return json.dumps(d, sort_keys=True)


def same_setting(x, y):
    """Compare two settings given as JSON strings or dicts (floats compared exactly after parsing)."""
    px = json.loads(x) if isinstance(x, str) else x
    py = json.loads(y) if isinstance(y, str) else y
    return px == py


def device():
    """CUDA (e.g. the Colab GPU of D12) if available, else Apple MPS, else CPU. Recorded in each meta file."""
    import torch
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")


def load_hf_token():
    """Read HF_TOKEN from .env in the repository root into the environment (never printed)."""
    p = os.path.join(MAIN, ".env")
    if os.path.exists(p) and not os.environ.get("HF_TOKEN"):
        for line in open(p, encoding="utf-8"):
            if line.startswith("HF_TOKEN="):
                os.environ["HF_TOKEN"] = line.split("=", 1)[1].strip().strip('"').strip("'")
