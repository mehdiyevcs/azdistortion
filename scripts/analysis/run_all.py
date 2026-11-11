"""Run the whole pre-registered analysis and write analysis/numbers.json, analysis/tables/, analysis/figures/,
analysis/error_analysis/ and analysis/hypotheses.md.

Usage: .venv/bin/python scripts/analysis/run_all.py
Systems whose prediction files appear later (E5 runs, non-LLM / encoder / H7 outputs under runs/) are picked up
automatically on the next run. Nothing under annotation/ or runs/ is written.
"""
import datetime, hashlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import agreement, prevalence, where_distortion, systems, edits, style_cues, error_samples, hypotheses

FROZEN = ["annotation/reference/reference_R1.csv", "annotation/reference/pairs_R1.csv", "annotation/reference/edits_R1.csv",
          "annotation/reference/weights.json", "annotation/claims/claims_s1.csv", "annotation/llm/labels_A1.csv", "annotation/llm/labels_A2.csv",
          "annotation/edits/edit_set_v2.csv", "sampling/reports_main.csv", "sampling/report_features.csv", "sampling/clusters.csv",
          "sampling/sources_summary.csv", "runs/dev_choice/cost_test.csv", "prereg.md"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    t0 = time.time()
    for d in (OUT, TAB, FIG, ERR):
        os.makedirs(d, exist_ok=True)
    N = {"meta": {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "bootstrap_reps": B, "bootstrap_seed": SEED,
                  "label_note": "label codes as in the data; MISREPRESENTED = MISLEADING in the paper",
                  "inputs_sha256": {f: sha(p(f)) for f in FROZEN}}}
    print("agreement ..."); N["agreement"] = agreement.run()
    print("prevalence / H1 ..."); N["prevalence"] = prevalence.run()
    print("H2/H3 regression ..."); N["where"] = where_distortion.run()
    print("systems ..."); sysres, runs, scored, _ = systems.run(); N["systems"] = sysres
    print("E5 / H5 ..."); N["edits"] = edits.run(runs)
    print("E9 ..."); N["style_cues_E9"] = style_cues.run()
    print("error samples ..."); N["error_samples"] = error_samples.run(runs)
    H = hypotheses.decide(N["prevalence"], N["where"], sysres, N["edits"])
    N["hypotheses"] = H
    N["meta"]["prediction_files_sha256"] = {v["path"]: sha(p(v["path"], "predictions.csv")) for v in runs.values()
                                            if os.path.exists(p(v["path"], "predictions.csv"))}
    N["meta"]["prediction_files_sha256"].update({v["path"]: sha(p(v["path"])) for v in runs.values() if v["path"].endswith(".csv") and os.path.exists(p(v["path"]))})
    N["meta"]["prediction_files_sha256"].update({v["path2"]: sha(p(v["path2"], "predictions.csv")) for v in runs.values() if "path2" in v})
    for d in sorted(os.listdir(p("runs"))):          # E5 C2t2 parts (used when a merged C2 run is missing)
        if d.startswith("e5_") and d.endswith("_C2t2_edit") and os.path.exists(p("runs", d, "predictions.csv")):
            N["meta"]["prediction_files_sha256"][f"runs/{d}"] = sha(p("runs", d, "predictions.csv"))
    N["pending"] = {
        "E5_H5": [s for s in SYSTEMS_LLM if N["edits"]["H5"].get(s, {}).get("status") != "done"],
        "H7": sysres["H7"].get("status") != "done",
        "non_llm_systems_found": sorted({v["system"] for v in runs.values() if v["exp"] == "NONLLM"}),
    }
    json.dump(clean(N), open(os.path.join(OUT, "numbers.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    hypotheses.write_md(H, N)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
