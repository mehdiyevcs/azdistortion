"""Decide H1-H7 (prereg 4a) from the prevalence, where-distortion, system and edit results.

Holm within families F1 {H1, H2, H3}, F2 (8 tests of H4), F3 {H5 per system, H7}, F4 {H6}; supported = Holm p < 0.05
and the point estimate reaches the smallest effect of interest; contradicted = point estimate in the opposite
direction and the unadjusted one-sided p for the opposite direction < 0.05; everything else inconclusive (including
unmet minimum information, > 5% degenerate replicates for H2/H3, and > 20% uncovered natural MIS weight for H5; MIS =
MISREPRESENTED, MISLEADING in the paper). H6 is not tested (D17 c). Pending inputs give 'pending'; Holm in F3 then
runs over the available tests and is marked provisional.
"""
from common import *


def verdict(est, p_adj, p_opp, null, sesoi, direction, min_info=True, extra_inconclusive=None):
    if est is None:
        return "pending", "no estimate"
    if not min_info:
        return "inconclusive", "minimum-information rule not met"
    if extra_inconclusive:
        return "inconclusive", extra_inconclusive
    reach = est >= sesoi if direction == ">" else est <= sesoi
    opposite = est < null if direction == ">" else est > null
    if p_adj < 0.05 and reach:
        return "supported", ""
    if opposite and p_opp < 0.05:
        return "contradicted", ""
    if p_adj < 0.05 and not reach:
        return "inconclusive", "significant but below the smallest effect of interest"
    return "inconclusive", "not significant after Holm"


def decide(prev, where, sysres, edres):
    H = {}
    # F1
    f1 = {"H1": prev["H1"]["p"], "H2": where["H2"]["p"], "H3": where["H3"]["p"]}
    adj = holm(f1)
    h = prev["H1"]
    v, why = verdict(h["estimate"], adj["H1"], h["p_opposite"], 0.5, 0.6, ">", h["min_info_met"])
    H["H1"] = dict(family="F1", estimate=h["estimate"], ci=h["ci"], p=h["p"], p_holm=adj["H1"], verdict=v, why=why,
                   what="design-weighted share MIS / (CON + MIS), random sample; null 0.5, SESOI 0.6",
                   note=f"{h['n_err_raw']} error claims raw ({h['n_mis_raw']} MIS, {h['n_con_raw']} CON); undefined reps {h['undefined_reps']}")
    for k, nm in (("H2", "OR(rewritten vs copied)"), ("H3", "OR(headline vs body)")):
        h = where[k]
        v, why = verdict(h["estimate_OR"], adj[k], h["p_opposite"], 1.0, 1.5, ">", h["min_info_met"],
                         "more than 5% degenerate replicates" if h["too_many_degenerate"] else None)
        H[k] = dict(family="F1", estimate=h["estimate_OR"], ci=h["ci"], p=h["p"], p_holm=adj[k], verdict=v, why=why,
                    what=f"penalised weighted logistic regression, {nm}; null 1, SESOI 1.5",
                    note=f"{h['n_err_raw']} error claims raw (minimum 30); degenerate reps {h['degenerate_reps']} ({h['degenerate_share']:.1%})")
    # F2
    h4 = sysres["H4"]
    adj4 = holm({k: v["p"] for k, v in h4.items()})
    H["H4"] = {"family": "F2", "tests": {}}
    for k, x in h4.items():
        v, why = verdict(x["estimate"], adj4[k], x["p_opposite"], 0.0, 0.05, ">")
        H["H4"]["tests"][k] = dict(estimate=x["estimate"], ci=x["ci"], p=x["p"], p_holm=adj4[k], verdict=v, why=why, n=x["n"])
    vs = [t["verdict"] for t in H["H4"]["tests"].values()]
    H["H4"]["summary"] = {s: vs.count(s) for s in ("supported", "inconclusive", "contradicted")}
    H["H4"]["what"] = "paired difference of macro-F1 on the random-sample C2-eligible claims (C0->C1, C1->C2), 4 systems x 2 = 8 tests; SESOI 0.05"
    # F3
    f3, items = {}, {}
    for s, x in edres["H5"].items():
        pr = x.get("primary_intended_type") if isinstance(x, dict) else None
        if pr and pr.get("status") != "pending" and "p" in pr:
            f3[f"H5:{s}"] = pr["p"]; items[f"H5:{s}"] = pr
    h7 = sysres["H7"]
    if h7.get("status") == "done":
        f3["H7"] = h7["p"]
    adj3 = holm(f3) if f3 else {}
    provisional = len(f3) < 5
    H["H5"] = {"family": "F3", "tests": {}, "holm_provisional": provisional,
               "what": "natural MIS recall minus post-stratified recall on R1-accepted distortion edits, per LLM under C2; SESOI -0.05"}
    nat_ok = edres["natural_MIS"]["min_info_met"]
    for s in SYSTEMS_LLM:
        x = edres["H5"].get(s, {})
        pr = x.get("primary_intended_type") if isinstance(x, dict) else None
        if not pr or pr.get("status") == "pending" or "p" not in pr:
            H["H5"]["tests"][s] = dict(verdict="pending", why="E5 predictions not available")
            continue
        v, why = verdict(pr["estimate"], adj3[f"H5:{s}"], pr["p_opposite"], 0.0, -0.05, "<", nat_ok,
                         "natural MIS types without accepted edits > 20% of the weight" if pr["inconclusive_coverage"] else None)
        H["H5"]["tests"][s] = dict(estimate=pr["estimate"], ci=pr["ci"], p=pr["p"], p_holm=adj3[f"H5:{s}"], verdict=v, why=why,
                                   natural_recall=pr["natural_recall"], edit_recall=pr["edit_recall_poststratified"])
    v5 = [t["verdict"] for t in H["H5"]["tests"].values()]
    if "pending" in v5:
        H["H5"]["verdict"] = "pending"
    elif v5.count("supported") >= len(v5) / 2:
        H["H5"]["verdict"] = "supported"
    else:
        H["H5"]["verdict"] = "inconclusive"
    if h7.get("status") == "done":
        v, why = verdict(h7["estimate"], adj3["H7"], h7["p_opposite"], 0.0, 0.05, ">")
        H["H7"] = dict(family="F3", estimate=h7["estimate"], ci=h7["ci"], p=h7["p"], p_holm=adj3["H7"], verdict=v, why=why, llm=h7["llm"],
                       holm_provisional=provisional)
    else:
        H["H7"] = dict(family="F3", verdict="pending", why=h7.get("note", "E2 encoder outputs not available"), llm=h7.get("llm"))
    H["H7"]["what"] = "macro-F1(selected LLM, C2) - macro-F1(nested-CV selected encoder) on identical pooled out-of-fold claims; SESOI 0.05"
    H["H6"] = dict(family="F4", verdict="not tested", why="D17 (c): only one human annotator; PSA_MIS(R1, R2) on S-H cannot be computed")
    return H


def write_md(H, numbers):
    L = ["# Hypothesis decisions (prereg v1.2, section 4a; deviations D1-D17)", "",
         "Generated by scripts/analysis/run_all.py. Human reference: one annotator (the author, R1; D17). Estimates are design-weighted; "
         "95% CIs are percentile intervals of the two-stage cluster bootstrap (2,000 replicates, seed 20261110); p-values are one-sided "
         "bootstrap p; Holm within families F1-F4. The paper label for code MISREPRESENTED is MISLEADING.", "",
         "| Hypothesis | Estimate | 95% CI | p | Holm p | Verdict | Note |", "|---|---|---|---|---|---|---|"]

    def row(name, x, note=""):
        c = x.get("ci") or [None, None]
        L.append(f"| {name} | {f(x.get('estimate'))} | [{f(c[0])}, {f(c[1])}] | {f(x.get('p'), 4)} | {f(x.get('p_holm'), 4)} | {x['verdict']} | "
                 f"{'; '.join(t for t in (x.get('why', ''), note) if t)} |")

    row("H1 MIS share of errors", H["H1"], H["H1"]["note"])
    row("H2 OR rewritten", H["H2"], H["H2"]["note"])
    row("H3 OR headline", H["H3"], H["H3"]["note"])
    for k, x in H["H4"]["tests"].items():
        row(f"H4 {k}", x, f"n = {x['n']}")
    for s, x in H["H5"]["tests"].items():
        extra = f"natural {f(x.get('natural_recall'))} vs edits {f(x.get('edit_recall'))}" if "natural_recall" in x else ""
        row(f"H5 {s}", x, extra + ("; Holm provisional (F3 incomplete)" if H["H5"]["holm_provisional"] and x["verdict"] != "pending" else ""))
    L.append(f"| H6 | - | - | - | - | not tested | {H['H6']['why']} |")
    row("H7", H["H7"], f"LLM side: {H['H7'].get('llm')}")
    L += ["", f"H4 summary: {H['H4']['summary']} of 8 tests. H5 overall (supported if supported for at least half of the systems): {H['H5']['verdict']}.", ""]
    for k in ("H1", "H2", "H3"):
        L.append(f"- {k}: {H[k]['what']}.")
    L.append(f"- H4: {H['H4']['what']}.")
    L.append(f"- H5: {H['H5']['what']}.")
    L.append(f"- H7: {H['H7']['what']}.")
    L.append("- H6: not tested (D17 c). Calibration kappa R1-R2 0.82 (69 dev claims) is descriptive only.")
    sysn, ed, pv = numbers["systems"], numbers["edits"], numbers["prevalence"]
    h4n = next(iter(sysn["H4"].values()), {}).get("n_raw_labels", {}) if sysn["H4"] else {}
    L += ["", "## Reading notes", "",
          "- Weights: H1-H3 (RQ1) use the phase design weight (D17 correction) times the D10 (c) report weight; without the report weight H1 is "
          f"{f(pv['H1']['sensitivity_phase_weight_only']['estimate'])} (one-sided p {f(pv['H1']['sensitivity_phase_weight_only']['p'], 4)}, before Holm). "
          "System scores and H4/H5/H7 use the phase weights only.",
          "- The variance of the phase-1 selection of S-H pairs is not modelled (prereg 4a); stage 2 resamples R1's S-D, S-A and S-N claims "
          "with replacement, without finite-population correction (D17 addendum a2).",
          f"- Macro-F1 runs over {', '.join(sysn['label_set_macro_f1'])}: the labels with >= 10 raw claims among all 506 reference claims "
          f"(counts {sysn['label_counts_reference']}), fixed before any prediction was scored. In the H4 domain (random sample, C2-eligible "
          f"claims) the raw counts are {h4n}, so the H4 macro-F1 rests on few MIS and NOT_IN_SOURCE claims.",
          f"- H5: {ed['natural_MIS']['n_raw']} natural MIS claims (all samples) and {ed['edits_accepted']['MIS']} R1-accepted distortion edits; "
          "hit = exact MISREPRESENTED label; edit type = intended type (R1's type as sensitivity in numbers.json). "
          + "; ".join(f"{s}: uncovered natural weight {f(x['primary_intended_type']['uncovered_natural_weight_share'])}, undefined reps {x['primary_intended_type']['undefined_reps']}"
                      for s, x in ed["H5"].items() if x.get("status") == "done"),
          "- H1 undefined replicates (no error claim) count as at the null; H2/H3 degenerate replicates keep OR = 1 (counts in the table).",
          "- A verdict 'pending' means the system's predictions did not exist when run_all.py ran; rerun after E5 / E2 outputs arrive."]
    open(os.path.join(OUT, "hypotheses.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
