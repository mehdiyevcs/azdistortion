"""Build the zip bundle for the E2 encoder runs on Google Colab (prereg D12): colab/bundle_<name>.zip.

The zip holds exactly what sys_encoder.py and sys_select.py need, laid out like the project so that the scripts'
own path logic (repository root = parent of scripts/, pilot folder next to it) works unchanged after unzipping:

  bundle_manifest.json     mode, pinned library versions, run arguments, the D12 priority list, sha256 of every file
  run_e2.py                the runner the notebook calls (copied from colab/run_e2.py)
  main/scripts/            sys_common.py, sys_encoder.py, sys_select.py (+ sys_tradml.py, hashed by sys_select's
                           protocol check; never run on Colab)
  main/...                 --final: claims file, data/sources/<ann_id>/T1.txt,T2.txt of the claims' announcements,
                           sampling/clusters.csv (if present), the human-verified reference (--gold), the training-label
                           file (--train-labels), the validated edit set (--edits, optional)
  pilot/...                --dev: pilot/adjudication/gold_labels_v1.csv, the pilot announcement texts
                           (text_*.txt, tables_*.txt), pilot/annotation/edit_set.csv
  main/runs/seed/          optional (--with-tradml DIR): folds.csv and the logreg/gbm outputs of the Mac run, so the
                           Colab run is forced onto the same folds and H7 (sys_select.py) can run there

No secrets: only the listed study files are added (an explicit allow-list; a file named .env* is refused). As a second
guard every bundled file and the manifest are scanned for the values in .env in the repository root (4+ characters)
and for common key formats (hf_, sk-, AKIA, AIza, key/token/secret assignments), and the build stops on a hit. The
scan cannot recognise unknown key formats; the allow-list is the real protection. The Hugging Face token is entered
in Colab only.
After writing the zip, the script unzips it to a temporary folder and runs run_e2.py --verify --preflight on it.

Usage:
  .venv/bin/python colab/make_bundle.py --dev                                   # pilot dev claims (pipeline test)
  .venv/bin/python colab/make_bundle.py --final --gold <reference.csv> --train-labels <train_labels.csv> \
      [--edits <validated_edits.csv>] [--e5-claims runs/main_inputs/e5_edits.csv] [--sample random|benchmark] \
      [--claims ...] [--with-tradml runs/<R>] [--name NAME]
"""
import argparse, csv, glob, hashlib, io, json, os, re, subprocess, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.dirname(HERE)
PILOT = os.path.join(os.path.dirname(MAIN), "pilot")
SCRIPTS = ["sys_common.py", "sys_encoder.py", "sys_select.py", "sys_tradml.py"]
# libraries recorded in every sys_* manifest (sys_common.lib_versions) plus the hub/tokenizer helpers they load with
PINNED = ["torch", "transformers", "tokenizers", "scikit-learn", "numpy", "scipy", "sentencepiece", "huggingface_hub",
          "safetensors", "protobuf"]
LABELS = {"SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"}
MODELS = ["xlmr", "azbert", "mdeberta"]
SECRET_RX = [re.compile(r"hf_[A-Za-z0-9]{30,}"), re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), re.compile(r"AKIA[0-9A-Z]{16}"),
             re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), re.compile(r"(?i)(api[_-]?key|token|secret)\s*=\s*['\"]?[A-Za-z0-9_\-]{20,}")]


def die(msg):
    raise SystemExit("make_bundle: " + msg)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rows(path):
    with open(path, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return rd.fieldnames or [], list(rd)


def priorities(sample, has_edits):
    """Run order: prereg D12 priorities 1-4, then C0 (5) and training on human labels only (6).
    Each step = [model, conditions, edits] or [model, conditions, edits, train_on]."""
    p = [dict(n=1, title="XLM-R and AzBERT, C2, natural", steps=[[m, "C2", False] for m in ("xlmr", "azbert")]),
         dict(n=2, title="mDeBERTa-v3, C2, natural", steps=[["mdeberta", "C2", False]]),
         dict(n=3, title="all three, C1, natural", steps=[[m, "C1", False] for m in MODELS]),
         dict(n=4, title="all three with the edit set (C2, then C1)", steps=[[m, "C2,C1", True] for m in MODELS]),
         dict(n=5, title="all three, C0, natural (run guide priority 5; random sample only, D9)", steps=[[m, "C0", False] for m in MODELS]),
         dict(n=6, title="all three, C2, trained on human labels only (prereg 4a secondary variant, H7 _hum)",
              steps=[[m, "C2", False, "human"] for m in MODELS])]
    if sample == "benchmark":
        p[3]["skip"] = "the edit set is built on random-sample claims only (D14), so the benchmark has no edit variant"
    elif not has_edits:
        p[3]["skip"] = "no validated edit set in this bundle (rebuild with --edits after validation)"
    if sample == "benchmark":
        p[4]["skip"] = "benchmark sample runs C1 and C2 only (D9)"
    return p


def rel_in_bundle(path):
    """Bundle path for a project file: main/<rel> inside MAIN, pilot/<rel> inside PILOT, else main/inputs/<basename>."""
    ap = os.path.abspath(path)
    for root, pre in ((MAIN, "main"), (PILOT, "pilot")):
        if ap.startswith(root + os.sep):
            return pre + "/" + os.path.relpath(ap, root).replace(os.sep, "/")
    return "main/inputs/" + os.path.basename(ap)


def arg_path(bpath):
    """Script argument for a bundle path, relative to main/ (the runner makes it absolute)."""
    return bpath[5:] if bpath.startswith("main/") else "../" + bpath


def resolve(p):
    return p if os.path.isabs(p) else os.path.join(MAIN, p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--dev", action="store_true", help="158 pilot dev claims (pipeline test; not results)")
    m.add_argument("--final", action="store_true", help="main-study data (after the human labels are frozen)")
    ap.add_argument("--name", default="", help="bundle name (default: dev, or the sample name); the results folder is results_<name>")
    ap.add_argument("--sample", choices=["random", "benchmark"], default="random")
    ap.add_argument("--claims", default="", help="claims CSV (default annotation/claims/claims_s1.csv; the benchmark needs its own file)")
    ap.add_argument("--gold", default="", help="--final: human-verified reference claim_id,label,weight (passed as --gold)")
    ap.add_argument("--train-labels", default="", help="--final: training labels claim_id,label (passed as --train-labels)")
    ap.add_argument("--edits", default="", help="--final: validated edit set (passed as --edits); without it priority 4 is skipped")
    ap.add_argument("--e5-claims", default="", help="--final: E5 edit claims (runs/main_inputs/e5_edits.csv) predicted by the held-out "
                    "outer models of every encoder step (sys_encoder.py --e5-claims)")
    ap.add_argument("--clusters", default="sampling/clusters.csv", help="ann_id,cluster (included if it exists)")
    ap.add_argument("--with-tradml", default="", help="optional run dir with folds.csv and the sys_tradml.py outputs, for H7 on Colab")
    ap.add_argument("--python", default=os.path.join(MAIN, ".venv/bin/python"), help="interpreter whose library versions are pinned")
    a = ap.parse_args()

    files, srcs = {}, {}  # bundle path -> bytes, source path

    def add(src, dst=None):
        if os.path.basename(src) == ".env" or os.path.basename(src).startswith(".env"):
            die(f"refusing to bundle {src}")
        dst = dst or rel_in_bundle(src)
        data = open(src, "rb").read()
        if dst in files:
            if files[dst] != data or srcs[dst] != os.path.abspath(src):
                die(f"two different inputs map to {dst} ({srcs[dst]} and {src}): rename one")
            return dst
        files[dst], srcs[dst] = data, os.path.abspath(src)
        return dst

    for s in SCRIPTS:
        add(os.path.join(MAIN, "scripts", s))
    add(os.path.join(HERE, "run_e2.py"), "run_e2.py")

    if a.dev:
        if a.gold or a.train_labels or a.edits or a.claims:
            die("--dev uses the pilot files only; --gold/--train-labels/--edits/--claims are for --final")
        name = a.name or "dev"
        gold = os.path.join(PILOT, "adjudication/gold_labels_v1.csv")
        add(gold)
        _, g = rows(gold)
        anns = sorted({r["ann_id"] for r in g})
        root = os.path.join(PILOT, "data/raw/announcements")
        for ann in anns:
            for d in (ann, ann + "-DEC"):
                for f in sorted(glob.glob(os.path.join(root, d, "text_*.txt")) + glob.glob(os.path.join(root, d, "tables_*.txt"))):
                    add(f)
        ed = add(os.path.join(PILOT, "annotation/edit_set.csv"))
        data_args = ["--dev", "--min-label-n", "5"]       # lower label-set threshold for the small dev set
        edits_arg = arg_path(ed)
        e5_arg = ""
        sample, n_claims = "dev", len(g)
    else:
        if not (a.gold and a.train_labels):
            die("--final needs --gold (human-verified reference) and --train-labels (training labels)")
        name = a.name or a.sample      # fixed name: a rebuilt bundle (e.g. with the edit set) continues in the same results folder
        claims = resolve(a.claims or "annotation/claims/claims_s1.csv")
        cf, cr = rows(claims)
        for col in ("claim_id", "ann_id", "claim_text"):
            if col not in cf:
                die(f"{claims}: missing column {col}")
        data_args = []
        data_args += ["--claims", arg_path(add(claims))]
        gf, gr = rows(resolve(a.gold))
        if not {"claim_id", "label", "weight"} <= set(gf):
            die(f"{a.gold}: needs claim_id,label,weight")
        bad = [r["claim_id"] for r in gr if r["label"] not in LABELS]
        if bad:
            die(f"{a.gold}: unknown labels for {bad[:5]}")
        data_args += ["--gold", arg_path(add(resolve(a.gold)))]
        tf, tr = rows(resolve(a.train_labels))
        if not {"claim_id", "label"} <= set(tf):
            die(f"{a.train_labels}: needs claim_id,label")
        bad = [r["claim_id"] for r in tr if r["label"] not in LABELS]
        if bad:
            die(f"{a.train_labels}: unknown labels for {bad[:5]}")
        data_args += ["--train-labels", arg_path(add(resolve(a.train_labels)))]
        ids = {r["claim_id"] for r in cr}
        miss = sorted(ids - {r["claim_id"] for r in tr})
        if miss:
            print(f"warning: {len(miss)} claims have no training label (not training targets): {miss[:5]}")
        cl = resolve(a.clusters)
        if os.path.exists(cl):
            data_args += ["--clusters", arg_path(add(cl))]
        else:
            print(f"warning: no clusters file at {cl}: cluster = ann_id (D10 addendum joins some announcements into one cluster)")
        anns = sorted({r["ann_id"] for r in cr})
        for ann in anns:
            for t in ("T1.txt", "T2.txt", "meta.json"):     # meta.json: t1_is_act (prereg D3, read by sys_common.source_text)
                p = os.path.join(MAIN, "data/sources", ann, t)
                if os.path.exists(p):
                    add(p)
                elif t == "T1.txt":
                    die(f"missing source {p}")
        e5_arg = ""
        if a.e5_claims:
            ef, er = rows(resolve(a.e5_claims))
            if not {"claim_id", "ann_id", "claim_text"} <= set(ef):
                die(f"{a.e5_claims}: needs claim_id, ann_id, claim_text")
            miss = sorted({r["ann_id"] for r in er} - set(anns))
            if miss:
                die(f"{a.e5_claims}: announcements without natural claims in this bundle: {miss[:5]}")
            e5_arg = arg_path(add(resolve(a.e5_claims)))
        edits_arg = ""
        if a.edits:
            ef, er = rows(resolve(a.edits))
            need = [("claim_text",), ("label", "gold"), ("base_claim_id", "orig_claim_id"), ("edit_id", "row_id")]
            for alts in need:
                if not any(c in ef for c in alts):
                    die(f"{a.edits}: needs one of {alts} (sys_common.load_edits); the raw edit_set_v2.csv must first be "
                        "converted to the validated set with these columns")
            edits_arg = arg_path(add(resolve(a.edits)))
        sample, n_claims = a.sample, len(cr)

    if a.with_tradml:
        d = resolve(a.with_tradml)
        seed = [os.path.join(d, "folds.csv")] + sorted(glob.glob(os.path.join(d, "*_tradml*.csv")) + glob.glob(os.path.join(d, "manifest_tradml*.json")))
        seed = [p for p in seed if os.path.basename(p).split("_")[0] in ("folds.csv", "predictions", "inner", "manifest")]
        if not os.path.exists(seed[0]) or not any("manifest_tradml" in p for p in seed):
            die(f"{d}: needs folds.csv and manifest_tradml*.json")
        for p in seed:
            add(p, "main/runs/seed/" + os.path.basename(p))

    # library versions to pin, read from the local interpreter (--python)
    code = "import importlib.metadata as m, json, sys; print(json.dumps({'python': sys.version.split()[0], 'libs': {p: m.version(p) for p in %r}}))" % PINNED
    env = json.loads(subprocess.check_output([a.python, "-c", code], text=True))


    man = dict(name=name, mode="dev" if a.dev else "final", sample=sample, n_claims=n_claims, n_announcements=len(anns),
               created=time.strftime("%Y-%m-%d %H:%M:%S"), python_local=env["python"], requirements=env["libs"],
               data_args=data_args, edits_arg=edits_arg, e5_arg=e5_arg, seed_results=bool(a.with_tradml),
               priorities=priorities(sample, bool(edits_arg)),
               protocol_note="sys_encoder.py defaults are the protocol (lr grid 1e-5,2e-5,3e-5; 3 epochs; batch 16; max length 512; "
                             "top-k = TOP_K_FROZEN; seeds 1,2,3; selection seed 1; all outer folds). The runner adds only --resume, "
                             "--out and --micro-batch (memory chunking of the batch of 16).",
               files={p: dict(sha256=sha(d), bytes=len(d)) for p, d in sorted(files.items())})
    man["content_sha256"] = sha("\n".join(f"{p}\0{v['sha256']}" for p, v in man["files"].items()).encode())
    # core = every file except the runner and the edit set, plus the pinned requirements and the run settings. A bundle
    # rebuilt only to add the validated edit set (priority 4) or with a fixed runner may continue in the same results
    # folder (run_e2.prepare_out also refuses a changed edit set once one was used); any other change may not.
    edits_bpath = "" if not edits_arg else (edits_arg[3:] if edits_arg.startswith("../") else "main/" + edits_arg)
    man["edits_sha256"] = man["files"][edits_bpath]["sha256"] if edits_bpath else ""
    man["core_sha256"] = sha(("\n".join(f"{p}\0{v['sha256']}" for p, v in man["files"].items() if p not in {"run_e2.py", edits_bpath})
                              + "\nrequirements\0" + json.dumps(man["requirements"], sort_keys=True)
                              + "\nexecution\0" + json.dumps(dict(mode=man["mode"], sample=man["sample"], data_args=man["data_args"], e5_arg=man["e5_arg"],
                                                                  steps=[[p["n"], p["steps"]] for p in man["priorities"]]), sort_keys=True)).encode())
    man_bytes = json.dumps(man, ensure_ascii=False, indent=1).encode("utf-8")
    # secret scan: values from .env (read, never written or printed) and key-like patterns
    secrets = []
    envp = os.path.join(MAIN, ".env")
    if os.path.exists(envp):
        for line in open(envp, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if len(v) >= 4:
                    secrets.append(v.encode())
    for p, data in list(files.items()) + [("bundle_manifest.json", man_bytes)]:
        if any(s in data for s in secrets):
            die(f"{p} contains a value from MAIN/.env")
        txt = data.decode("utf-8", "ignore")
        for rx in SECRET_RX:
            mm = rx.search(txt)
            if mm:
                die(f"{p} contains a key-like string at offset {mm.start()}")
    secrets.clear()


    out = os.path.join(HERE, f"bundle_{name}.zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bundle_manifest.json", man_bytes)
        for p, d in sorted(files.items()):
            z.writestr(p, d)
    tmp = out + ".tmp"
    open(tmp, "wb").write(buf.getvalue())
    os.replace(tmp, out)
    json.dump(man, open(os.path.join(HERE, f"bundle_{name}.manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{out}: {len(files)} files, {len(buf.getvalue()) / 1e6:.1f} MB, {n_claims} claims, {len(anns)} announcements, "
          f"content {man['content_sha256'][:12]}")
    for p in man["priorities"]:
        print(f"  priority {p['n']}: {p['title']}" + (f"  [SKIPPED: {p['skip']}]" if p.get("skip") else ""))
    # self-check: unzip to a temporary folder and run the bundled runner's verify and preflight steps
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(out).extractall(td)
        subprocess.run([a.python, os.path.join(td, "run_e2.py"), "--root", td, "--out", os.path.join(td, "_unused"), "--verify", "--preflight"], check=True)


if __name__ == "__main__":
    main()
