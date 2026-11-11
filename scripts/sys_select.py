"""H7 cross-candidate selection inside the nested CV (prereg 4a "Nested CV for H7").

Prereg 4a: inside each outer training part, the inner 3-fold grouped CV chooses the candidate (logistic regression,
gradient boosting, XLM-R-base, mDeBERTa-v3-base, Azerbaijani BERT) and its settings by macro-F1; the chosen model is
refit on the outer training part and predicts the outer test fold. sys_tradml.py and sys_encoder.py already tune each
candidate's settings on the same inner splits (same claims, same folds, same label set) and refit the best setting
per candidate. Choosing, per outer fold, the candidate with the highest inner score and taking its refit prediction
is therefore the joint nested CV over all candidates and settings, run in pieces.

Correctness checks (always; the run stops on any failure):
  - every candidate's manifest (manifest_<stem><suffix>.json) agrees on sources, shared code, outer folds, inner
    splits, claim population and labels, edit set, label set, min-label-n, inner-score mode, training variant, dev flag;
  - the manifest matches the suffix (edits present iff '_edits', train_on human iff '_hum');
  - the run directory's folds.csv reproduces the folds fingerprint of every manifest;
  - the inner rows of each outer fold are the complete grid of the candidate's manifest, each setting with inner folds
    0, 1, 2 exactly once; exactly one 'chosen' row per fold, equal to the grid-order argmax of the inner means;
  - predictions: every requested seed (neural) or seed 1 (logreg, gbm; copied to every seed, they are deterministic),
    every claim of folds.csv exactly once per seed, in its own fold, a valid label, and made with the chosen setting.
Protocol checks (confirmatory runs; violations stop the run unless --allow-nonprotocol): condition C2 (H7);
producer script and sys_common.py hashes equal to the current files; seeds exactly 1,2,3;
candidates exactly logreg,gbm,xlmr,mdeberta,azbert (tie order); only azbert may be absent; human-weighted inner
scoring; not dev; min-label-n 10; no --limit; LR/GB grids of prereg 4a; encoders with lr grid 1e-5,2e-5,3e-5, 3 epochs,
batch 16, length 512, no step cap, selection seed 1, all outer folds, top-k equal to sys_encoder.TOP_K_FROZEN, and the
candidate's own checkpoint (sys_encoder.MODELS) at its pinned revision.
With --allow-nonprotocol, outputs always carry the system name H7_selected<suffix>_NONCONFIRMATORY and confirmatory = 0
in the selection CSV, even when no check fails; the violations are listed in selection_h7_<cond><suffix>.json.

Usage: .venv/bin/python scripts/sys_select.py --out runs/<run> --condition C2 [--suffix _edits]
Output: <out>/predictions_h7_<cond><suffix>.csv, <out>/selection_h7_<cond><suffix>.csv, <out>/selection_h7_<cond><suffix>.json
"""
import argparse, csv, hashlib, json, math, os
from collections import defaultdict
import sys_common as S
import sys_encoder as E          # frozen top-k and model table (no heavy imports at module level)

CANDS = {"logreg": ("tradml", "S0b_logreg"), "gbm": ("tradml", "S0b_gbm"), "xlmr": ("enc_xlmr", "S2_xlmr"),
         "mdeberta": ("enc_mdeberta", "S2_mdeberta"), "azbert": ("enc_azbert", "S2b_azbert")}
PROTO_CANDS = ["logreg", "gbm", "xlmr", "mdeberta", "azbert"]
PROTO_OPTIONAL = {"azbert"}
PROTO_SEEDS = [1, 2, 3]
PROTO_ENC = {"lr_grid": "1e-5,2e-5,3e-5", "epochs": 3, "batch": 16, "max_len": 512, "max_steps": 0, "select_seed": 1, "outer_folds": ""}
TRAD = {"logreg": [{"C": 0.1}, {"C": 1}, {"C": 10}],
        "gbm": [{"max_depth": d, "n_estimators": n} for d in (2, 3) for n in (100, 300)]}
KEYS = ["sources_sha256", "common_code_sha256", "folds_sha256", "inner_sha256", "claims_sha256", "edits_sha256", "label_set",
        "min_label_n", "inner_score", "train_on", "dev", "limit"]


def die(msg):
    raise SystemExit(msg)


def grid_of(cand, man):
    if cand in TRAD:
        return [dict(x) for x in man["grids"][cand]]
    return [{"lr": float(x)} for x in man["lr_grid"].split(",")]


def protocol_violations(cand, man, condition):
    v = []
    if condition != "C2":
        v.append(f"condition {condition} (H7 is specified under C2)")
    producer = "sys_tradml.py" if cand in TRAD else "sys_encoder.py"
    if man.get("producer") != producer or man.get("producer_sha256") != S.file_hash(os.path.join(os.path.dirname(os.path.abspath(__file__)), producer)):
        v.append(f"producer {man.get('producer')} hash differs from the current {producer}")
    if man.get("common_code_sha256") != S.code_hash():
        v.append("sys_common.py hash differs from the current file")
    if man.get("dev"):
        v.append("dev data")
    if man.get("inner_score") != "human_weighted":
        v.append(f"inner_score={man.get('inner_score')}")
    if man.get("min_label_n") != 10:
        v.append(f"min_label_n={man.get('min_label_n')}")
    if man.get("limit"):
        v.append(f"limit={man.get('limit')}")
    if cand in TRAD:
        if man.get("grids", {}).get(cand) != TRAD[cand]:
            v.append("grid")
    else:
        v += [f"{k}={man.get(k)!r}" for k, val in PROTO_ENC.items() if man.get(k) != val]
        if E.TOP_K_FROZEN is None or man.get("top_k") != E.TOP_K_FROZEN or man.get("top_k_frozen") != E.TOP_K_FROZEN:
            v.append(f"top_k={man.get('top_k')} (frozen in sys_encoder.py: {E.TOP_K_FROZEN})")
        model = E.MODELS[cand][0]
        if man.get("model") != model:
            v.append(f"model {man.get('model')} (required {model})")
        if not S.REVISIONS.get(model) or man.get("model_revision") != S.REVISIONS[model]:
            v.append(f"model_revision {man.get('model_revision')} (pinned {S.REVISIONS.get(model)})")
    return [f"{cand}: {x}" for x in v]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--condition", default="C2")
    ap.add_argument("--suffix", default="", choices=["", "_edits", "_hum", "_edits_hum"])
    ap.add_argument("--candidates", default=",".join(PROTO_CANDS))
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--optional", default="azbert", help="candidates that may be absent (recorded)")
    ap.add_argument("--allow-nonprotocol", action="store_true",
                    help="smoke tests only: accept non-protocol settings; outputs are marked NONCONFIRMATORY")
    a = ap.parse_args()
    (cond,) = S.parse_conditions(a.condition) if "," not in a.condition else die("--condition takes one condition")
    cands = [x for x in a.candidates.split(",") if x]
    optional = set(x for x in a.optional.split(",") if x)
    if not cands or any(c not in CANDS for c in cands) or len(cands) != len(set(cands)) or not optional <= set(cands):
        die(f"invalid --candidates/--optional: {a.candidates!r} / {a.optional!r}")
    try:
        seeds = [int(s) for s in a.seeds.split(",")]
    except ValueError:
        die(f"invalid --seeds {a.seeds!r}")
    if len(seeds) != len(set(seeds)):
        die("duplicate seeds")
    viol = []
    if seeds != PROTO_SEEDS:
        viol.append(f"seeds {seeds} (protocol 1,2,3)")
    if cands != PROTO_CANDS:
        viol.append(f"candidates {cands} (protocol {PROTO_CANDS})")
    if not optional <= PROTO_OPTIONAL:
        viol.append(f"optional {sorted(optional)} (protocol: azbert only)")
    folds = {}
    for r in csv.DictReader(open(os.path.join(a.out, "folds.csv"), encoding="utf-8")):
        if r["claim_id"] in folds:
            die(f"folds.csv: duplicate claim {r['claim_id']}")
        folds[r["claim_id"]] = int(r["fold"])
    folds_sha = hashlib.sha256(json.dumps(sorted(folds.items())).encode()).hexdigest()   # as in sys_common.manifest
    nfold = max(folds.values()) + 1
    if nfold != S.OUTER_K:
        die(f"folds.csv has {nfold} folds, expected {S.OUTER_K}")
    inner, preds, avail, missing, ref, mans = {}, {}, [], [], None, {}
    for cand in cands:
        stem, sysname = CANDS[cand]
        sysname += a.suffix
        fi, fp = os.path.join(a.out, f"inner_{stem}{a.suffix}.csv"), os.path.join(a.out, f"predictions_{stem}{a.suffix}.csv")
        fm = os.path.join(a.out, f"manifest_{stem}{a.suffix}.json")
        if not all(os.path.exists(x) for x in (fi, fp, fm)):
            if cand in optional:
                print(f"optional candidate {cand} absent"); missing.append(cand); continue
            die(f"required candidate {cand}: missing {fi}, {fp} or {fm}")
        man = json.load(open(fm, encoding="utf-8"))
        mans[cand] = {k: man.get(k) for k in ("producer", "producer_sha256", "common_code_sha256", "model", "model_revision", "top_k")}
        if ref is None:
            ref = (cand, {k: man.get(k) for k in KEYS})
        bad = [k for k in KEYS if man.get(k) != ref[1][k]]
        if bad:
            die(f"{cand} is not comparable with {ref[0]}: manifests differ in {bad}")
        if man.get("folds_sha256") != folds_sha:
            die(f"{cand}: {a.out}/folds.csv does not match the folds fingerprint in its manifest")
        if bool(man.get("edits_sha256")) != ("_edits" in a.suffix) or (man.get("train_on") == "human") != ("_hum" in a.suffix):
            die(f"{cand}: manifest (edits, train_on) does not match suffix {a.suffix!r}")
        if cand in TRAD and (cand not in man.get("candidates", []) or cond not in man.get("conditions", [])):
            die(f"{cand}: manifest says it was not run for {cond}")
        viol += protocol_violations(cand, man, cond)
        grid = grid_of(cand, man)
        # inner rows: complete grid x inner folds, one chosen row per fold
        cells, ch = {}, {}
        for r in csv.DictReader(open(fi, encoding="utf-8")):
            if r["condition"] != cond or r["system"] != sysname:
                continue
            try:
                f, sc, st = int(r["outer_fold"]), float(r["score"]), json.loads(r["setting"])
            except (TypeError, ValueError):
                die(f"{cand}: malformed inner row {r}")
            if not math.isfinite(sc) or not 0 <= f < nfold:
                die(f"{cand}: invalid inner row {r}")
            gi = next((i for i, g in enumerate(grid) if g == st), None)
            if gi is None:
                die(f"{cand}: inner setting {r['setting']} is not in its manifest grid")
            if r["inner_fold"] == "chosen":
                if f in ch:
                    die(f"{cand}: more than one chosen row for outer fold {f}")
                ch[f] = (sc, gi)
            else:
                k = (f, gi, r["inner_fold"])
                if r["inner_fold"] not in ("0", "1", "2") or k in cells:
                    die(f"{cand}: invalid or duplicate inner row {r}")
                cells[k] = sc
        for f in range(nfold):
            if f not in ch:
                die(f"{cand}: no chosen row for outer fold {f}")
            means = []
            for gi in range(len(grid)):
                v = [cells.get((f, gi, str(ii))) for ii in range(S.INNER_K)]
                if any(x is None for x in v):
                    die(f"{cand}: outer fold {f}, setting {grid[gi]}: inner folds incomplete")
                means.append(sum(v) / len(v))
            bi = max(range(len(grid)), key=lambda i: (means[i], -i))
            sc, gi = ch[f]
            if gi != bi or abs(means[bi] - sc) > 1e-9:
                die(f"{cand}: chosen setting of outer fold {f} does not follow from its inner scores")
        if len({k[0] for k in cells}) != nfold:
            die(f"{cand}: inner rows for unexpected outer folds")
        # predictions: complete, unique, own fold, valid label, chosen setting
        pr = defaultdict(dict)
        for r in csv.DictReader(open(fp, encoding="utf-8")):
            if r["condition"] != cond or r["system"] != sysname:
                continue
            cid = r["claim_id"]
            if cid not in folds or folds[cid] != int(r["fold"]):
                die(f"{cand}: prediction for {cid} not in its folds.csv fold (different folds.csv?)")
            if r["label"] not in S.LABELS:
                die(f"{cand}: invalid label {r['label']!r} for {cid}")
            try:
                st = json.loads(r["setting"])
            except (TypeError, ValueError):
                die(f"{cand}: prediction for {cid} has no valid setting")
            if st != grid[ch[folds[cid]][1]]:
                die(f"{cand}: prediction for {cid} (fold {folds[cid]}) was made with {st}, not the chosen {grid[ch[folds[cid]][1]]}")
            s = int(r["seed"])
            if cid in pr[s]:
                die(f"{cand}: duplicate prediction for {cid} seed {s}")
            pr[s][cid] = r["label"]
        if cand in TRAD:
            if set(pr) != {1}:
                die(f"{cand}: deterministic candidate should have seed 1 only")
            pr = {s: pr[1] for s in seeds}          # deterministic: same predictions for every seed
        for s in seeds:
            if s not in pr or set(pr[s]) != set(folds):
                die(f"{cand} seed {s}: predictions missing or incomplete")
        inner[cand] = {f: (ch[f][0], S.setting_json(grid[ch[f][1]])) for f in ch}
        preds[cand] = pr
        avail.append(cand)
    if not avail:
        die("no complete candidate")
    if viol and not a.allow_nonprotocol:
        die("not a protocol (confirmatory) run:\n  " + "\n  ".join(viol) + "\nuse --allow-nonprotocol only for smoke tests")
    if a.allow_nonprotocol:
        viol.append("--allow-nonprotocol given (outputs are never confirmatory with this flag)")
    confirmatory = not viol
    sysout = "H7_selected" + a.suffix + ("" if confirmatory else "_NONCONFIRMATORY")
    sel_rows, out_rows = [], []
    for f in range(nfold):
        best = max(avail, key=lambda c: (inner[c][f][0], -avail.index(c)))
        sel_rows.append([f, best, inner[best][f][1], repr(inner[best][f][0])] + [repr(inner[c][f][0]) for c in avail])
        bset = S.setting_json({"candidate": best, "setting": json.loads(inner[best][f][1])})
        for s in seeds:
            for cid, fo in folds.items():
                if fo == f:
                    out_rows.append([cid, cond, sysout, f, s, bset, preds[best][s][cid]])
    base = os.path.join(a.out, f"selection_h7_{cond}{a.suffix}")
    with open(base + ".csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo); w.writerow(["outer_fold", "selected", "setting", "inner_score"] + [f"inner_{c}" for c in avail] + ["absent_optional", "confirmatory"])
        w.writerows([r + [";".join(missing), int(confirmatory)] for r in sel_rows])
    S.atomic_json(base + ".json", dict(confirmatory=confirmatory, violations=viol, system=sysout, condition=cond, suffix=a.suffix,
                                       candidates=avail, absent_optional=missing, seeds=seeds, candidate_manifests=mans,
                                       shared=ref[1], select_sha256=S.file_hash(__file__)))
    with open(os.path.join(a.out, f"predictions_h7_{cond}{a.suffix}.csv"), "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo); w.writerow(S.PRED_COLS); w.writerows(out_rows)
    print(f"H7 selection {cond}{a.suffix} ({'confirmatory' if confirmatory else 'NONCONFIRMATORY: ' + str(len(viol)) + ' violations'}): "
          f"candidates {avail}; per fold {[r[1] for r in sel_rows]}")


if __name__ == "__main__":
    main()
