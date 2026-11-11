"""Run the E2 encoder fine-tuning of D12 from a data bundle (on Google Colab, or locally for a dev test); shipped inside the bundle.

It only calls the project's scripts with their protocol defaults: sys_encoder.py with --resume, --out and
--micro-batch (how the batch of 16 is split for memory; gradients are accumulated to 16, so the optimisation is the
same), plus the bundle's data arguments. Priorities run in the D12 order (1-4), then priority 5 (C0) of HOWTO_colab.md.
Every fit's rows are written by sys_encoder.py straight into --out (a Google Drive folder on Colab), so after a
disconnect the same call resumes from the last finished fit; sys_encoder.py validates what it keeps.

CLI (the notebook calls the same functions):
  python run_e2.py --root BUNDLE_DIR --out RESULTS_DIR --verify --preflight
  python run_e2.py --root BUNDLE_DIR --out RESULTS_DIR --priorities 1,2,3,4,5 [--require-cuda] [--test-cap]
  python run_e2.py --root BUNDLE_DIR --out RESULTS_DIR --h7
  python run_e2.py --root BUNDLE_DIR --out RESULTS_DIR --zip DEST.zip
--test-cap (dev bundles only) adds --max-steps 1 --lr-grid 1e-5,2e-5 --seeds 1: a pipeline test, never results.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time, zipfile

TEST_CAP = ["--max-steps", "1", "--lr-grid", "1e-5,2e-5", "--seeds", "1"]
NOISE = re.compile(r"(?i)warn|loading weights|UNEXPECTED|MISSING|^Notes|^- |^\s*$|^Key|^-+\+|ForSequenceClassification|^ *\||Some weights|You should probably")


def manifest(root):
    return json.load(open(os.path.join(root, "bundle_manifest.json"), encoding="utf-8"))


def verify_bundle(root):
    """Every manifest file present with its sha256; no unlisted file and no .env in the bundle."""
    man = manifest(root)
    bad = []
    for p, v in man["files"].items():
        fp = os.path.join(root, p)
        if not os.path.exists(fp) or hashlib.sha256(open(fp, "rb").read()).hexdigest() != v["sha256"]:
            bad.append(p)
    extra = []
    for d, _, fs in os.walk(root):
        if "__pycache__" in d:
            continue
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/")
            if f.startswith(".env"):
                raise SystemExit(f"bundle contains {rel}: refusing to run")
            if rel != "bundle_manifest.json" and rel not in man["files"]:
                extra.append(rel)
    if bad or extra:
        raise SystemExit(f"bundle check failed: changed/missing {bad[:5]}, unlisted {extra[:5]}")
    print(f"bundle {man['name']} ({man['mode']}, {man['n_claims']} claims): {len(man['files'])} files verified, content {man['content_sha256'][:12]}")
    return man


def requirements(root):
    return [f"{p}=={v}" for p, v in manifest(root)["requirements"].items()]


def check_versions(root, python=sys.executable):
    """Installed versions in `python` vs the pinned ones; returns a list of mismatches."""
    want = manifest(root)["requirements"]
    code = "import importlib.metadata as m, json\nout={}\nfor p in %r:\n    try: out[p]=m.version(p)\n    except Exception: out[p]=None\nprint(json.dumps(out))" % list(want)
    have = json.loads(subprocess.check_output([python, "-c", code], text=True))
    return [f"{p}: installed {have[p]}, pinned {v}" for p, v in want.items() if have[p] != v]


def _abs(root, p):
    return os.path.normpath(os.path.join(root, "main", p))


def data_args(root, man):
    out, it = [], iter(man["data_args"])
    for x in it:
        out.append(x)
        if x in ("--claims", "--gold", "--train-labels", "--clusters"):
            out.append(_abs(root, next(it)))
    return out


def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def prepare_out(root, out):
    """Bind the results folder to this bundle's content; copy the seed folds/tradml outputs once."""
    man = manifest(root)
    os.makedirs(os.path.join(out, "logs"), exist_ok=True)
    p = os.path.join(out, "run_info.json")
    if os.path.exists(p):
        old = json.load(open(p, encoding="utf-8"))
        if old.get("core_sha256") != man["core_sha256"]:
            raise SystemExit(f"{out} belongs to bundle {old.get('name')} (core {old.get('core_sha256', '')[:12]}), not to this "
                             f"bundle {man['name']} (core {man['core_sha256'][:12]}): its data or scripts differ; use another results folder")
        if old.get("edits_sha256") and old["edits_sha256"] != man["edits_sha256"]:
            raise SystemExit(f"{out} was run with another edit set ({old['edits_sha256'][:12]}); this bundle has "
                             f"{man['edits_sha256'][:12] or 'none'}: use another results folder")
        if man["content_sha256"] not in old.get("bundles", []) or old.get("edits_sha256", "") != man["edits_sha256"]:
            old["bundles"] = sorted(set(old.get("bundles", []) + [man["content_sha256"]]))
            old["edits_sha256"] = man["edits_sha256"]          # reached only when an edit set is added for the first time
            _atomic_json(p, old)
    else:
        _atomic_json(p, dict(name=man["name"], mode=man["mode"], core_sha256=man["core_sha256"], edits_sha256=man["edits_sha256"],
                             bundles=[man["content_sha256"]], created=time.strftime("%Y-%m-%d %H:%M:%S")))
    seed = os.path.join(root, "main", "runs", "seed")
    if os.path.isdir(seed):
        for f in sorted(os.listdir(seed)):
            dst = os.path.join(out, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(seed, f), dst)
            elif f == "folds.csv" and open(dst, "rb").read() != open(os.path.join(seed, f), "rb").read():
                raise SystemExit(f"{dst} differs from the bundle's seed folds.csv")
    return man


def preflight(root):
    """Load claims, edits, folds and label set with the bundled sys_common (no model, no training)."""
    code = ("import sys, argparse; sys.path.insert(0, %r); import sys_common as S\n"
            "ap = S.add_data_args(argparse.ArgumentParser()); ap.add_argument('--x'); a = ap.parse_args(sys.argv[1:])\n"
            "c, info = S.load_claims(a); e, ei = S.load_edits(a, c); f = S.outer_folds(c)\n"
            "print('preflight:', len(c), 'claims,', info['n_clusters'], 'clusters,', ei.get('edits_used', 0), 'edits; label set', S.label_set(c, a.min_label_n),"
            " '; outer fold sizes', [sum(v == k for v in f.values()) for k in range(5)])") % os.path.join(root, "main", "scripts")
    man = manifest(root)
    args = data_args(root, man) + (["--edits", _abs(root, man["edits_arg"])] if man["edits_arg"] else [])
    subprocess.run([sys.executable, "-c", code] + args, check=True)


def cuda_info(python=sys.executable):
    """GPU name and CUDA runtime of torch, or 'none'."""
    return subprocess.check_output([python, "-c", "import torch; print(f'{torch.cuda.get_device_name(0)} / CUDA {torch.version.cuda}' "
                                    "if torch.cuda.is_available() else 'none')"], text=True).strip()


def bind_hardware(out, hw):
    """One results folder = one hardware type (the encoder manifests record only cuda/mps/cpu, not the GPU model)."""
    p = os.path.join(out, "run_info.json")
    info = json.load(open(p, encoding="utf-8"))
    if info.get("hardware") and info["hardware"] != hw:
        raise SystemExit(f"{out} was run on {info['hardware']}, this runtime is {hw}: choose that GPU in Runtime > Change runtime "
                         "type (fits from different GPUs are not mixed in one results folder)")
    if not info.get("hardware"):
        info["hardware"] = hw
        _atomic_json(p, info)


def _progress(out, key, **kw):
    p = os.path.join(out, "progress.json")
    d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    d.setdefault(key, {}).update(kw)
    _atomic_json(p, d)


def _run(cmd, log, cwd):
    """Run a command, stream its output (noise filtered) and append everything to the log file."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", TOKENIZERS_PARALLELISM="false")
    with open(log, "a", encoding="utf-8") as lf:
        lf.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(cmd)}\n")
        pr = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in pr.stdout:
            lf.write(line); lf.flush()
            if not NOISE.search(line):
                print(line, end="", flush=True)
        return pr.wait()


def run_priority(root, out, n, micro_batch=16, test_cap=False, require_cuda=False, c0_before_edits=False):
    """Run one D12 priority (all its steps, in order). Safe to call again after a disconnect: --resume skips finished fits.
    Priority 5 waits while priority 4 lacks its edit set (the D12 order drops runs from the bottom), unless c0_before_edits."""
    man = prepare_out(root, out)
    pr = next(p for p in man["priorities"] if p["n"] == n)
    p4 = next(p for p in man["priorities"] if p["n"] == 4)
    if n == 5 and p4.get("skip") and not c0_before_edits and not pr.get("skip"):
        print("priority 5 (C0): NOT STARTED - priority 4 is waiting for the validated edit set, and D12 runs priority 4 first. "
              "Rebuild the bundle with --edits and Run all again (or set C0_BEFORE_EDITS = True to run C0 now).")
        _progress(out, "priority_5", status="waiting for priority 4")
        return
    if pr.get("skip"):
        print(f"priority {n} ({pr['title']}): SKIPPED - {pr['skip']}")
        _progress(out, f"priority_{n}", status="skipped", reason=pr["skip"])
        return
    if test_cap and man["mode"] != "dev":
        raise SystemExit("--test-cap is for dev bundles only (it would write non-protocol fits into the main results)")
    mm = check_versions(root)
    if mm:
        raise SystemExit("installed libraries differ from the bundle's pins: " + "; ".join(mm))
    hw = cuda_info()
    if require_cuda and hw == "none":
        raise SystemExit("no CUDA GPU: Runtime > Change runtime type > GPU. Refusing to run on CPU (the manifest records the device "
                         "and resume would refuse to mix hardware).")
    bind_hardware(out, hw if hw != "none" else "local non-CUDA (" + sys.platform + ")")
    scripts = os.path.join(root, "main", "scripts")
    t0 = time.time()
    _progress(out, f"priority_{n}", status="running", title=pr["title"], started=time.strftime("%Y-%m-%d %H:%M:%S"), failed_steps=[])
    failed = []                                        # a failed step is recorded and the next step still runs
    for step in pr["steps"]:
        model, conds, edits = step[:3]
        human = len(step) > 3 and step[3] == "human"      # priority 6: --train-on human (prereg 4a secondary variant)
        cmd = [sys.executable, os.path.join(scripts, "sys_encoder.py"), "--model", model, "--conditions", conds, "--out", out, "--resume",
               "--micro-batch", str(micro_batch)] + data_args(root, man)
        if edits:
            cmd += ["--edits", _abs(root, man["edits_arg"])]
        if man.get("e5_arg"):
            cmd += ["--e5-claims", _abs(root, man["e5_arg"])]
        if human:
            cmd += ["--train-on", "human"]
        if test_cap:
            cmd += TEST_CAP
        key = f"p{n}_{model}_{conds.replace(',', '')}{'_edits' if edits else ''}{'_hum' if human else ''}"
        print(f"\n### priority {n}: {model} {conds}{' + edits' if edits else ''}", flush=True)
        ts = time.time()
        rc = _run(cmd, os.path.join(out, "logs", key + ".log"), os.path.join(root, "main"))
        _progress(out, key, returncode=rc, seconds=round(time.time() - ts, 1), finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        if rc != 0:
            failed.append(key)
            print(f"!!! priority {n} step {key} FAILED (exit {rc}); see {out}/logs/{key}.log. Its finished fits are kept; "
                  f"continuing with the next step. Re-running later resumes it.", flush=True)
    if failed:
        _progress(out, f"priority_{n}", status="failed", failed_steps=failed, seconds=round(time.time() - t0, 1),
                  finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        raise SystemExit(f"priority {n}: {len(failed)} of {len(pr['steps'])} steps failed: {', '.join(failed)} (logs in {out}/logs/). "
                         "Finished fits are kept on Drive; Run all again resumes.")
    _progress(out, f"priority_{n}", status="done", seconds=round(time.time() - t0, 1), finished=time.strftime("%Y-%m-%d %H:%M:%S"))
    print(f"priority {n} done in {time.time() - t0:.0f}s")


def run_h7(root, out, test_cap=False):
    """H7 selection (sys_select.py) in results folders seeded with the logreg/gbm outputs of the local run. Confirmatory for final
    bundles; dev bundles are always marked NONCONFIRMATORY by sys_select itself (--allow-nonprotocol)."""
    man = manifest(root)
    sel = os.path.join(root, "main", "scripts", "sys_select.py")
    failed = []
    for suffix in ("", "_edits", "_hum"):
        if not os.path.exists(os.path.join(out, f"manifest_tradml{suffix}.json")):
            print(f"H7{suffix}: no manifest_tradml{suffix}.json in {out} (bundle built without --with-tradml): run H7 on the Mac")
            continue
        cmd = [sys.executable, sel, "--out", out, "--condition", "C2"] + (["--suffix", suffix] if suffix else [])
        if man["mode"] == "dev":
            cmd += ["--allow-nonprotocol"]
        if test_cap:
            cmd += ["--seeds", "1"]
        rc = _run(cmd, os.path.join(out, "logs", f"h7{suffix}.log"), os.path.join(root, "main"))
        _progress(out, f"h7{suffix}", returncode=rc, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        print(f"H7{suffix}: exit {rc}" + ("" if rc == 0 else f" (see {out}/logs/h7{suffix}.log)"))
        if rc != 0:
            failed.append(f"H7{suffix}")
    if failed:
        raise SystemExit(f"{', '.join(failed)} failed: see {out}/logs/")


def zip_results(out, dest):
    tmp = dest + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(out):
            for f in fs:
                if not f.endswith(".tmp"):
                    fp = os.path.join(d, f)
                    z.write(fp, os.path.relpath(fp, os.path.dirname(out)))
    os.replace(tmp, dest)
    print(f"results zipped: {dest} ({os.path.getsize(dest) / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--priorities", default="")
    ap.add_argument("--micro-batch", type=int, default=16)
    ap.add_argument("--test-cap", action="store_true")
    ap.add_argument("--require-cuda", action="store_true")
    ap.add_argument("--c0-before-edits", action="store_true")
    ap.add_argument("--h7", action="store_true")
    ap.add_argument("--zip", default="")
    a = ap.parse_args()
    a.root, a.out = os.path.abspath(a.root), os.path.abspath(a.out)
    if a.verify:
        verify_bundle(a.root)
        mm = check_versions(a.root)
        print("library versions:", "match the manifest" if not mm else "MISMATCH " + "; ".join(mm))
    if a.preflight:
        preflight(a.root)
    errs = []                               # as in the notebook: a failed priority does not stop the next ones
    for n in [int(x) for x in a.priorities.split(",") if x]:
        try:
            run_priority(a.root, a.out, n, a.micro_batch, a.test_cap, a.require_cuda, a.c0_before_edits)
        except (SystemExit, Exception) as e:
            errs.append(f"priority {n}: {e}"); print(f"!!! priority {n} did not finish: {e} -> continuing", flush=True)
    if a.h7:
        try:
            run_h7(a.root, a.out, a.test_cap)
        except (SystemExit, Exception) as e:
            errs.append(f"H7: {e}")         # zip first, then report the failure
    if a.zip:
        zip_results(a.out, a.zip)
    if errs:
        raise SystemExit("did not finish: " + " | ".join(errs))


if __name__ == "__main__":
    main()
