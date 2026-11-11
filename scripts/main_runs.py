"""Bookkeeping for the main LLM test runs (prereg section 5, D9): merging, cost log, re-parsing and cost projection.

  merge   SYS SAMPLE : runs/e1_<SYS>_C2_<SAMPLE>/ = C2 predictions of the claims with a T2 (run e1_<SYS>_C2t2_<SAMPLE>)
                       + C1 predictions copied for the claims without a T2 (run e1_<SYS>_C1_<SAMPLE>), column copied_from_C1 = 1.
                       Without a T2 the C2 request is byte-identical to C1 (prereg D3 also for t1_is_act), so the copy is the
                       same request; it avoids a second, noisy answer to an identical prompt.
  log                : logs/runs_main.csv (one row per run) and the "Main test runs" section of logs/budget.md.
  reparse RUN...     : re-derive labels of cached raw records with the current strict parser (label = first call that parses,
                       as the runner would have stopped there; REFUSED kept); updates raw/*.json and predictions.csv.
  project SYS        : projected full cost of SYS over its planned workload, calibrated on its finished records.
"""
import csv, glob, json, math, os, re, sys, time
from collections import defaultdict

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MAIN, "scripts"))
INP = os.path.join(MAIN, "runs", "main_inputs")
RUN_RE = re.compile(r"^(e1|e3|e4t|e5|e10|stab)_")
LINES = {"haiku": 30.0, "sonnet": 165.0, "gpt55": 175.0}   # planned spend per system (USD)
ACCOUNT = {"haiku": "Anthropic", "sonnet": "Anthropic", "gpt55": "OpenAI", "qwen": "local"}
# spending limit per API account for these runs (USD)
ACCOUNT_ROOM = {"Anthropic": 194.0, "OpenAI": 194.0}


def run_cap(sysname, rid):
    """--cost-cap for run rid: min(1.2 x the system's line, room left on the account) minus what other runs spent."""
    spent_sys = spent_acc = 0.0
    for d in glob.glob(os.path.join(MAIN, "runs", "*")):
        b = os.path.basename(d)
        if not RUN_RE.match(b) or b == rid:
            continue
        sname = next((x for x in ACCOUNT if f"_{x}_" in b), None)
        if sname is None or ACCOUNT[sname] != ACCOUNT[sysname]:
            continue
        c = sum(r["cost"] for r in raw_recs(b)) + err_cost(b)
        spent_acc += c
        spent_sys += c if sname == sysname else 0
    room = min(1.2 * LINES[sysname] - spent_sys, ACCOUNT_ROOM[ACCOUNT[sysname]] - spent_acc)
    return math.floor(room * 100) / 100 if room >= 0.01 else -1  # -1: the runner stops without any call


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8")))


def raw_recs(rid):
    return [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(MAIN, "runs", rid, "raw", "*.json")))]


def err_cost(rid):
    p = os.path.join(MAIN, "runs", rid, "errors.jsonl")
    return sum(json.loads(l).get("cost", 0) for l in open(p, encoding="utf-8")) if os.path.exists(p) else 0.0


def merge(sysname, sample):
    exp = "e5" if sample == "edit" else "e1"   # E5 (edit set): runs e5_<sys>_<cond>_edit, input e5_edits.csv
    c1, c2 = f"{exp}_{sysname}_C1_{sample}", f"{exp}_{sysname}_C2t2_{sample}"
    out = f"{exp}_{sysname}_C2_{sample}"
    claims = rd(os.path.join(INP, "e5_edits.csv" if sample == "edit" else f"{sample}_all.csv"))
    p1 = {r["claim_id"]: r for r in rd(os.path.join(MAIN, "runs", c1, "predictions.csv"))}
    p2 = {r["claim_id"]: r for r in rd(os.path.join(MAIN, "runs", c2, "predictions.csv"))}
    rows, miss = [], []
    for c in claims:
        src = p2 if c["has_t2"] == "1" else p1
        r = src.get(c["claim_id"])
        if r is None or r.get("error"):
            miss.append(c["claim_id"]); continue
        rows.append(dict(r, copied_from_C1=0 if c["has_t2"] == "1" else 1, source_run=c2 if c["has_t2"] == "1" else c1))
    if miss:
        raise SystemExit(f"{out}: {len(miss)} claims missing or errored in {c1}/{c2}, e.g. {miss[:3]}; merge not written")
    d = os.path.join(MAIN, "runs", out); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "predictions.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    m1, m2 = (json.load(open(os.path.join(MAIN, "runs", x, "meta.json"))) for x in (c1, c2))
    json.dump({"run_id": out, "system": sysname, "condition": "C2", "sample": sample, "merged": True, "n": len(rows),
               "n_called_C2": sum(1 for r in rows if r["copied_from_C1"] == 0), "n_copied_from_C1": sum(1 for r in rows if r["copied_from_C1"] == 1),
               "parts": [c2, c1], "raw": f"runs/{c2}/raw (C2 calls) and runs/{c1}/raw (copied C1 calls)",
               "prompt_sha256": m2.get("prompt_sha256"), "model_id": m2.get("model_id"), "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
               "note": "cost and minutes of this run = those of the C2t2 part; the copied rows were paid in the C1 run"},
              open(os.path.join(d, "meta.json"), "w"), indent=1)
    print(out, len(rows))


def log():
    rows = []
    for d in sorted(glob.glob(os.path.join(MAIN, "runs", "*"))):
        rid = os.path.basename(d)
        if not RUN_RE.match(rid) or not os.path.exists(os.path.join(d, "meta.json")):
            continue
        m = json.load(open(os.path.join(d, "meta.json")))
        if m.get("merged"):
            part = m["parts"][0]; recs = raw_recs(part); pm = json.load(open(os.path.join(MAIN, "runs", part, "meta.json")))
            preds = rd(os.path.join(d, "predictions.csv"))
            rows.append({"run_id": rid, "system": m["system"], "condition": "C2", "sample": m["sample"], "n": m["n"],
                         "cost": round(sum(r["cost"] for r in recs) + err_cost(part), 4), "minutes": round(pm.get("wall_seconds_total", 0) / 60, 1),
                         "unparseable": sum(p["label"] == "UNPARSEABLE" for p in preds), "refused": sum(p["label"] == "REFUSED" for p in preds),
                         "n_called": m["n_called_C2"], "n_copied_from_C1": m["n_copied_from_C1"], "truncated": sum(p["truncated"] == "True" for p in preds),
                         "complete": True, "note": f"merged: {part} + copied C1 rows (cost counted once, in the parts)"})
            continue
        recs = raw_recs(rid)
        claims_file = os.path.join(MAIN, m["claims"]) if m.get("claims") else ""
        n_plan = len(rd(claims_file)) if claims_file and os.path.exists(claims_file) else len(recs)
        sample = "edit" if rid.startswith("e5_") else "random" if "random" in rid or "stab" in rid or rid.startswith("e4t") else ("benchmark" if "benchmark" in rid else
                 ("random+benchmark" if rid.startswith("e3") else ""))
        rows.append({"run_id": rid, "system": m["system"], "condition": m["condition"] + (f" ({os.path.basename(m['retrieval'] or '')} k={m['k']})" if m.get("retrieval") else ""),
                     "sample": sample, "n": len(recs), "cost": round(sum(r["cost"] for r in recs) + err_cost(rid), 4),
                     "minutes": round(m.get("wall_seconds_total", 0) / 60, 1), "unparseable": sum(r["label"] == "UNPARSEABLE" for r in recs),
                     "refused": sum(r["label"] == "REFUSED" for r in recs), "n_called": len(recs), "n_copied_from_C1": 0,
                     "truncated": sum(bool(r["truncated"]) for r in recs), "complete": len(recs) == n_plan,
                     "note": "" if len(recs) == n_plan else f"partial: {len(recs)} of {n_plan}"})
    cols = ["run_id", "system", "condition", "sample", "n", "cost", "minutes", "unparseable", "refused", "n_called", "n_copied_from_C1", "truncated", "complete", "note"]
    with open(os.path.join(MAIN, "logs", "runs_main.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    spent = defaultdict(float)
    for r in rows:
        if not r["note"].startswith("merged"):
            spent[r["system"]] += r["cost"]
    smoke = sum(sum(x["cost"] for x in raw_recs(os.path.basename(d))) for d in glob.glob(os.path.join(MAIN, "runs", "smoke_main_*")))
    sec = ["<!-- MAIN-RUNS-START -->", "## Main test runs (actual spend, API list prices; written by scripts/main_runs.py log)", "",
           f"Updated {time.strftime('%Y-%m-%d %H:%M')}. Per run: logs/runs_main.csv.", "",
           "| system | account | spent $ | line $ |", "|---|---|---|---|"]
    for s in ["haiku", "sonnet", "gpt55", "qwen"]:
        sec.append(f"| {s} | {ACCOUNT[s]} | {spent.get(s, 0):.2f} | {LINES.get(s, 0) or '-'} |")
    a = spent.get("haiku", 0) + spent.get("sonnet", 0)
    sec += ["", f"Anthropic main runs: ${a:.2f} of the about $195 line (account ceiling $250, $45 spent before). "
            f"OpenAI main runs: ${spent.get('gpt55', 0):.2f} of the about $175 line (ceiling $200, $6 spent before). "
            f"Runner smoke tests: ${smoke:.2f}.", "<!-- MAIN-RUNS-END -->"]
    bp = os.path.join(MAIN, "logs", "budget.md"); b = open(bp, encoding="utf-8").read()
    b = re.sub(r"\n?<!-- MAIN-RUNS-START -->.*<!-- MAIN-RUNS-END -->", "", b, flags=re.S).rstrip() + "\n\n" + "\n".join(sec) + "\n"
    open(bp, "w", encoding="utf-8").write(b)
    print("\n".join(sec[5:12]))


# ------------------------------------------------------------------ projection
def plan(sysname):
    """(run_id, claims csv, condition, extra) of the planned workload."""
    P = []
    for s, conds in (("random", ["C0", "C1", "C2t2"]), ("benchmark", ["C1", "C2t2"])):
        for c in conds:
            if sysname == "gpt55" and s == "benchmark":
                continue
            P.append((f"e1_{sysname}_{c}_{s}", f"{s}_{'t2' if c == 'C2t2' else 'all'}.csv", c[:2], None))
    if sysname == "gpt55":
        P.append(("e1_gpt55_C2_benchmark", "benchmark_all.csv", "C2", None))
    # E5 edit set: C0, C1 on all 300 edits, C2 on the edits with a T2
    P += [(f"e5_{sysname}_{c}_edit", "e5_edits_t2.csv" if c == "C2t2" else "e5_edits.csv", c[:2], None) for c in ("C0", "C1", "C2t2")]
    if sysname in ("haiku", "sonnet"):
        P += [(f"stab_{sysname}_C2_r{i}", "stab200.csv", "C2", None) for i in (1, 2)]
    if sysname == "haiku":
        P += [(f"e4t_haiku_C2_v{i}_random", "random_all.csv", "C2", f"prompts/e4_v{i}.txt") for i in range(1, 6)]
        P += [(f"e3_haiku_{m}_k{k}", "e3_claims.csv", "C2", f"retr:{m}:{k}") for m in ("bm25", "e5") for k in (1, 3, 5)]
        # E10 (D16)
        P += [(f"e10_haiku_{p}_{s}", f"{s}_all.csv", "C2", f"prompts/e10_{p}.txt") for p in ("literal", "implicature") for s in ("random", "benchmark")]
    return P


def project(sysname):
    import run_llm as R
    prompt = R.load_prompt(os.path.join(MAIN, "prompts", "main.txt"))
    done = [r for d in glob.glob(os.path.join(MAIN, "runs", f"*_{sysname}_*")) if RUN_RE.match(os.path.basename(d)) for r in raw_recs(os.path.basename(d))]
    if not done:
        raise SystemExit("no finished records")
    tok_per_char = sum(r["in_tok"] for r in done) / sum(r["prompt_chars"] for r in done)
    out_by_cond = defaultdict(list)
    for r in done:
        out_by_cond[r["condition"]].append(r["out_tok"])
    mean_out = {c: sum(v) / len(v) for c, v in out_by_cond.items()}
    allout = sum(r["out_tok"] for r in done) / len(done)
    spent = sum(r["cost"] for r in done)
    total, lines = 0.0, []
    for rid, cf, cond, extra in plan(sysname):
        path = os.path.join(INP, cf)
        if not os.path.exists(path):
            lines.append(f"{rid}: input {cf} not built yet; skipped"); continue
        claims = rd(path)
        have = {r["claim_id"]: r["cost"] for r in raw_recs(rid)}
        groups = defaultdict(list)
        for c in claims:
            groups[c["ann_id"]].append(c)
        cost = 0.0
        for ann, cs in groups.items():
            if extra and extra.startswith("retr:"):   # short claim-specific source: about 2k instruction chars + k x 800 chars
                k = int(extra.split(":")[2]); src_chars, instr_chars = 0, len(prompt["text"])
                per = [(instr_chars, 800 * k + 150)] * len(cs)
            else:
                pr = R.load_prompt(os.path.join(MAIN, extra)) if extra else prompt
                req, _, _ = R.build_claude_request(cs[0], cond, os.path.join(MAIN, "data/sources"), R.MAX_CHARS.get(sysname, R.DEFAULT_MAX_CHARS), pr)
                prefix = sum(len(b["text"]) for b in req["system"]) + (sum(len(b["text"]) for b in req["messages"][0]["content"][:-1]) if isinstance(req["messages"][0]["content"], list) else 0)
                per = [(prefix, len(c["claim_text"]) + 30) for c in cs]
            for i, (pre, unc) in enumerate(per):
                cid = cs[i]["claim_id"]
                if cid in have:
                    cost += have[cid]; continue
                pt, ut, ot = pre * tok_per_char, unc * tok_per_char, mean_out.get(cond, allout)
                first = i == 0 or (extra or "").startswith("retr:")
                if sysname in R.CLAUDE_API_MODELS:
                    m = R.CLAUDE_API_MODELS[sysname]
                    cost += R.claude_cost(m, ut, ot, 0 if first else pt, pt if first else 0)
                else:
                    pi, pc, po = R.OPENAI_PRICE[R.OPENAI_MODELS[sysname]]
                    cached = 0 if first or pt < 1024 else pt
                    cost += ((pt + ut - cached) * pi + cached * pc + ot * po) / 1e6
        total += cost
        lines.append(f"{rid}: n={len(claims)} done={len(have)} projected ${cost:.2f}")
    print("\n".join(lines))
    print(f"{sysname}: calibrated on {len(done)} records (spent ${spent:.2f}); tokens/char {tok_per_char:.3f}; mean out tok {dict((k, round(v)) for k, v in mean_out.items())}")
    line = LINES.get(sysname)
    print(f"PROJECTED TOTAL {sysname}: ${total:.2f}" + (f" vs line ${line:.0f} ({total / line:.0%})" if line else ""))
    return total


def reparse(rids):
    import run_llm as R
    for rid in rids:
        d = os.path.join(MAIN, "runs", rid); ch = 0; new = {}
        for f in sorted(glob.glob(os.path.join(d, "raw", "*.json"))):
            r = json.load(open(f, encoding="utf-8"))
            if r["label"] == "REFUSED" or not r.get("fingerprint"):
                new[r["claim_id"]] = r["label"]; continue
            lab = next((R.parse_label(c["text"], strict=True) for c in r["calls"] if R.parse_label(c["text"], strict=True)), None) or "UNPARSEABLE"
            if lab != r["label"]:
                ch += 1; print(f"{rid} {r['claim_id']}: {r['label']} -> {lab}")
                r["label_before_reparse"] = r["label"]; r["label"] = lab
                json.dump(r, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            new[r["claim_id"]] = lab
        pp = os.path.join(d, "predictions.csv")
        if ch and os.path.exists(pp):
            rows = rd(pp)
            for x in rows:
                x["label"] = new.get(x["claim_id"], x["label"])
            with open(pp, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        print(f"{rid}: {ch} labels changed")
        if ch:  # rebuild merged C2 runs built from this run
            for mp in glob.glob(os.path.join(MAIN, "runs", "*", "meta.json")):
                m = json.load(open(mp))
                if m.get("merged") and rid in m.get("parts", []):
                    merge(m["system"], m["sample"])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "merge":
        merge(sys.argv[2], sys.argv[3])
    elif cmd == "log":
        log()
    elif cmd == "cap":
        print(run_cap(sys.argv[2], sys.argv[3]))
    elif cmd == "reparse":
        reparse(sys.argv[2:])
    elif cmd == "project":
        project(sys.argv[2])
