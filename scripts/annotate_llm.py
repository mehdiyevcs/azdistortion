"""Label every fixed claim of the main study with the two LLM annotators (prereg.md section 3 "LLM labels").

A1 = Claude Opus 5.5 via the Anthropic API (claude-opus-5-5, effort high, adaptive thinking; guidelines and source are
prompt-cached; this model does not accept a temperature). A2 = the Codex command-line agent (codex exec, read-only sandbox).
Each annotator labels all claims of a report (annotation/claims/claims_s1.csv) against the source package
(data/sources/<ann_id>/T1.txt + T2.txt), following the frozen guidelines v1.2. The annotators are blind to each other.
Run from the repository root.
Usage: python3 scripts/annotate_llm.py A1|A2 [--jobs N] [--only R0001,R0002] [--collect]
Outputs: annotation/llm/<A>/<report_id>.json (+ .prompt.txt, .meta.json), then annotation/llm/labels_<A>.csv
"""
import tempfile
import csv, json, os, re, subprocess, sys, time, concurrent.futures as cf
csv.field_size_limit(10**9)
GUIDE = open("annotation/guidelines_v1.2.md", encoding="utf-8").read()
LABELS = "SUPPORTED|CONTRADICTED|MISREPRESENTED|NOT_IN_SOURCE|UNASSESSABLE"
SPEC = ('Return ONLY one JSON object, no prose, no code fence:\n'
        '{"report_id": "...", "key_conditions": "3-8 short lines from A only, written BEFORE you read N, separated by \' | \'",\n'
        ' "claims": [{"claim_id": "...", "label": "' + LABELS + '", "evidence": "sentence or table cell of A (empty for NOT_IN_SOURCE/UNASSESSABLE)",\n'
        '   "content_tags": "subset of amount;actor;date;scope;status;inference, only for CONTRADICTED or MISREPRESENTED",\n'
        '   "distortion_type": "status|scope|actor|inference|dropped_condition, only for MISREPRESENTED",\n'
        '   "cause": "section_conflation|copied|unknown or empty", "unsure": 0 or 1, "split_error": 0 or 1, "note": "short"}],\n'
        ' "omission": 0 or 1, "omission_note": "...", "framing": 0 or 1, "framing_note": "..."}\n'
        'Label every claim_id exactly once. Do not split, merge or add claims.')


PRICE = {"claude-opus-5-5": (4.00, 20.00, 0.20, 5.00)}  # USD per million tokens: input, output, cache read, cache write (5 min)
A1_MODEL, A1_EFFORT = "claude-opus-5-5", "high"


def api_parts(rep, claims, ann):
    """Build the API prompt: system = [instructions + guidelines] + [source A], both cached; user = N + claims + output spec."""
    aid = rep["ann_id"]
    t1 = open(f"data/sources/{aid}/T1.txt", encoding="utf-8").read()
    t2 = open(f"data/sources/{aid}/T2.txt", encoding="utf-8").read()
    a = f"<press_release>\n{t1}\n</press_release>\n" + (f"<full_decision_text>\n{t2}\n</full_decision_text>\n" if t2.strip() else "<full_decision_text>none</full_decision_text>\n")
    sys1 = (f"You are annotator {ann} in a research study. Work only from the text you are given. Use no outside knowledge.\n\n"
            "Task: label the claims of a news report N against the official source A, following these annotation guidelines exactly. "
            "A is the press release plus, where present, the full decision text; both count as A. The claims are already split and fixed.\n\n"
            f"<guidelines>\n{GUIDE}\n</guidelines>\n\nStep 1: read A and write key_conditions. Only then read N.")
    sys2 = f"<A id=\"{aid}\">\n{a}</A>"
    nt = open(f"data/raw/news/{rep['report_id']}/text_0.txt", encoding="utf-8").read()
    cl = "\n".join(f"{c['claim_id']} [{c['part']}]: {c['claim_text']}" for c in claims)
    user = f"<N id=\"{rep['report_id']}\" outlet=\"{rep['outlet']}\" date=\"{rep['pub_date']}\">\n{nt}\n</N>\n\n<claims>\n{cl}\n</claims>\n\n{SPEC}"
    return sys1, sys2, user


def call_api(rep, claims, ann, out):
    import anthropic
    client = anthropic.Anthropic(max_retries=4, timeout=1800)
    sys1, sys2, user = api_parts(rep, claims, ann)
    with client.messages.stream(model=A1_MODEL, max_tokens=32000, output_config={"effort": A1_EFFORT},
                                system=[{"type": "text", "text": sys1, "cache_control": {"type": "ephemeral"}},
                                        {"type": "text", "text": sys2, "cache_control": {"type": "ephemeral"}}],
                                messages=[{"role": "user", "content": user}]) as st:
        m = st.get_final_message()
    txt = "".join(b.text for b in m.content if b.type == "text")
    open(out, "w", encoding="utf-8").write(txt)
    u = m.usage; pr = PRICE[A1_MODEL]
    cost = (u.input_tokens * pr[0] + u.output_tokens * pr[1] + (u.cache_read_input_tokens or 0) * pr[2] + (u.cache_creation_input_tokens or 0) * pr[3]) / 1e6
    return m.stop_reason, json.dumps({"model": m.model, "stop_reason": m.stop_reason, "effort": A1_EFFORT, "input": u.input_tokens, "output": u.output_tokens,
                                      "cache_read": u.cache_read_input_tokens, "cache_write": u.cache_creation_input_tokens, "cost_usd": round(cost, 4)})


def prompt(rep, claims, ann):
    aid = rep["ann_id"]
    t1 = open(f"data/sources/{aid}/T1.txt", encoding="utf-8").read()
    t2 = open(f"data/sources/{aid}/T2.txt", encoding="utf-8").read()
    nt = open(f"data/raw/news/{rep['report_id']}/text_0.txt", encoding="utf-8").read()
    cl = "\n".join(f"{c['claim_id']} [{c['part']}]: {c['claim_text']}" for c in claims)
    a = f"<press_release>\n{t1}\n</press_release>\n" + (f"<full_decision_text>\n{t2}\n</full_decision_text>\n" if t2.strip() else "<full_decision_text>none</full_decision_text>\n")
    return f"""You are annotator {ann} in a research study. Work ONLY from the text in this prompt. Do not open, list or search any file or website. Do not run commands. Use no outside knowledge.

Task: label the claims of a news report N against the official source A, following these annotation guidelines exactly. A is the press release plus, where present, the full decision text; both count as A. The claims are already split and fixed.

<guidelines>
{GUIDE}
</guidelines>

Step 1: read A and write key_conditions. Only then read N.

<A id="{aid}">
{a}</A>

<N id="{rep['report_id']}" outlet="{rep['outlet']}" date="{rep['pub_date']}">
{nt}
</N>

<claims>
{cl}
</claims>

{SPEC}"""


def call(ann, p, out, rep=None, claims=None):
    if ann == "A1":
        return call_api(rep, claims, ann, out)
    if ann == "A2":
        r = subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", os.path.abspath(out), "-"], input=p, capture_output=True, text=True, timeout=2400, cwd=tempfile.gettempdir())
        return r.returncode, ""
    r = subprocess.run(["claude", "-p", "--model", "opus", "--output-format", "json", "--strict-mcp-config", "--setting-sources", "project",
                        "--no-session-persistence", "--tools", ""], input=p, capture_output=True, text=True, timeout=2400, cwd=tempfile.gettempdir())
    try:
        j = json.loads(r.stdout)
        open(out, "w", encoding="utf-8").write(j.get("result", ""))
        return r.returncode, json.dumps({"cost_usd": j.get("total_cost_usd"), "usage": j.get("usage"), "model": list((j.get("modelUsage") or {}).keys())})
    except json.JSONDecodeError:
        open(out, "w", encoding="utf-8").write(r.stdout)
        return r.returncode, ""


def valid(out, claims):
    try:
        t = open(out, encoding="utf-8").read()
        j = json.loads(re.search(r"\{.*\}", t, re.S).group(0))
        got = {c["claim_id"] for c in j["claims"]}
        return got >= {c["claim_id"] for c in claims}
    except Exception:
        return False


def run(rep, claims, ann):
    d = f"annotation/llm/{ann}"; out = f"{d}/{rep['report_id']}.json"
    if os.path.exists(out) and valid(out, claims):
        return rep["report_id"], "cached"
    p = prompt(rep, claims, ann)
    open(f"{d}/{rep['report_id']}.prompt.txt", "w", encoding="utf-8").write(p)
    rc = None
    for attempt in range(2):
        t0 = time.time()
        try:
            rc, meta = call(ann, p, out, rep, claims)
        except subprocess.TimeoutExpired:
            rc, meta = "timeout", ""
        except Exception as e:  # API errors after the SDK's own retries: log, wait, try again
            rc, meta = f"error {type(e).__name__}", ""
            time.sleep(30)
        open(f"{d}/{rep['report_id']}.meta.json", "w").write(json.dumps({"attempt": attempt, "rc": str(rc), "seconds": round(time.time() - t0, 1), "meta": meta}))
        if os.path.exists(out) and valid(out, claims):
            return rep["report_id"], f"ok ({attempt})"
    return rep["report_id"], f"FAILED ({rc})"


def collect(ann):
    rows = []
    for f in sorted(os.listdir(f"annotation/llm/{ann}")):
        if not re.match(r"[RB]\d+\.json$", f):
            continue
        try:
            j = json.loads(re.search(r"\{.*\}", open(f"annotation/llm/{ann}/{f}", encoding="utf-8").read(), re.S).group(0))
        except Exception:
            continue
        for c in j["claims"]:
            rows.append({"annotator": ann, "report_id": f[:-5], "claim_id": c.get("claim_id"), "label": c.get("label"), "evidence": c.get("evidence", ""),
                         "content_tags": c.get("content_tags", ""), "distortion_type": c.get("distortion_type", ""), "cause": c.get("cause", ""),
                         "unsure": c.get("unsure", 0), "split_error": c.get("split_error", 0), "note": c.get("note", ""),
                         "omission": j.get("omission", ""), "framing": j.get("framing", "")})
    # Raw JSON also exists for reports dropped by the re-walk and report cap (D10). Only claims in claims_s1.csv go to
    # labels_<A>.csv; the rest go to labels_<A>_dropped.csv, which the analysis does not use.
    current = {c["claim_id"] for c in csv.DictReader(open("annotation/claims/claims_s1.csv", encoding="utf-8"))}
    dropped = [r for r in rows if r["claim_id"] not in current]
    rows = [r for r in rows if r["claim_id"] in current]
    missing = current - {r["claim_id"] for r in rows}
    if missing:
        print("WARNING: current claims without a label:", len(missing))
    for path, rr in ((f"annotation/llm/labels_{ann}.csv", rows), (f"annotation/llm/labels_{ann}_dropped.csv", dropped)):
        w = csv.DictWriter(open(path, "w", newline="", encoding="utf-8"), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rr)
    print(ann, "dropped-report rows written separately:", len(dropped))
    from collections import Counter
    print(ann, len(rows), "claims;", Counter(r["label"] for r in rows))


if __name__ == "__main__":
    ann = sys.argv[1]; a = sys.argv[2:]
    if "--collect" in a:
        collect(ann); sys.exit()
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 3
    only = set(a[a.index("--only") + 1].split(",")) if "--only" in a else None
    os.makedirs(f"annotation/llm/{ann}", exist_ok=True)
    reps = [r for r in csv.DictReader(open("sampling/reports_main.csv", encoding="utf-8")) if not only or r["report_id"] in only]
    claims = list(csv.DictReader(open("annotation/claims/claims_s1.csv", encoding="utf-8")))
    # One announcement per worker: its first report writes the prompt cache (shared prefix: guidelines + A), the rest read it.
    groups = {}
    for r in reps:
        groups.setdefault(r["ann_id"], []).append(r)
    def do_group(rs):
        out = []
        for r in rs:
            out.append(run(r, [c for c in claims if c["report_id"] == r["report_id"]], ann))
            print(ann, *out[-1], flush=True)
        return out
    with cf.ThreadPoolExecutor(jobs) as ex:
        list(ex.map(do_group, groups.values()))
    collect(ann)
