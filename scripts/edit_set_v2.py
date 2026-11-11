"""Build the controlled edit set v2 for E5 and H5 (prereg.md section 6, D14) and the human check packets.

Base claims are random-sample claims outside S-H where A1 and A2 agree on SUPPORTED. Claude Opus 5.5 writes one
contradiction edit (intended CONTRADICTED) and one distortion edit (intended MISREPRESENTED, MISLEADING in the paper)
per base claim.
Usage (python scripts/edit_set_v2.py <step>; the script changes to the repository root itself):
  sample            -> annotation/edits/base_claims_v2.csv (150 claims, 50 per issuer)
  generate          -> annotation/edits/raw/<ann_id>.json (one API call per announcement) + logs/edit_set_v2_cost.jsonl
  generate --retry  -> regenerate once the items that failed the automatic checks (annotation/edits/retry_todo.json)
  rebalance         -> second pass asking for status distortions where a type is over-filled (raw/<ann_id>_status.json)
  check             -> annotation/edits/edit_set_v2.csv + logs/edit_set_v2_checks.md (automatic checks)
  packets           -> annotation/human/R1/EDITS/, annotation/human/R2/EDITS/, annotation/edits/packet_key_v2.csv
The packets were built for two human annotators; under D17 only one human checked edits (see D17 correction).
"""
import csv, html, json, os, random, re, sys, time, unicodedata, concurrent.futures as cf
from collections import Counter, defaultdict

csv.field_size_limit(10**9)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
OUT = "annotation/edits"
RAW = f"{OUT}/raw"
BASE = f"{OUT}/base_claims_v2.csv"
SET = f"{OUT}/edit_set_v2.csv"
COST = "logs/edit_set_v2_cost.jsonl"
SEED_SAMPLE, SEED_PACKETS = 20261124, 20261125
ISSUERS = ["CBAR", "DVX", "EMSMN"]
PER_ISSUER, CAP = 50, 4
MIS_TYPES = ["status", "scope", "actor", "inference", "dropped_condition"]
CON_TYPES = ["amount", "date", "actor", "scope", "status", "condition"]
MODEL, EFFORT = "claude-opus-5-5", "high"
PRICE = (4.00, 20.00, 0.20, 5.00)  # USD per million tokens: input, output, cache read, cache write (as in scripts/annotate_llm.py)
LONG, T2_KEEP, CHUNK = 60000, 40000, 1500

MONTHS = "yanvar|fevral|mart|aprel|may|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr"
TIER1 = re.compile(rf"\d|%|\b({MONTHS})|faiz|manat|qəpik|\bAZN\b", re.I)
TIER2 = re.compile(r"yalnız|istisna|halda|şərt|əgər|tərəfindən|şamil|aid ed|daxil|etibarən|müddətində|ödəyici|işəgötürən|vətəndaş|sahibkar", re.I)


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip()


def key(s):
    return re.sub(r"[\W_]+", "", norm(s).lower())


def rcsv(p, enc="utf-8"):
    return list(csv.DictReader(open(p, encoding=enc)))


def src(aid):
    t1 = open(f"data/sources/{aid}/T1.txt", encoding="utf-8").read()
    t2 = open(f"data/sources/{aid}/T2.txt", encoding="utf-8").read()
    return t1, t2


# ---------------------------------------------------------------- sample
# tier 1: numbers, dates or amounts; tier 2: conditions, actors or scope words; tier 3: other
def tier(t):
    return 1 if TIER1.search(t) else 2 if TIER2.search(t) else 3


def sample():
    A1 = {r["claim_id"]: r for r in rcsv("annotation/llm/labels_A1.csv")}
    A2 = {r["claim_id"]: r for r in rcsv("annotation/llm/labels_A2.csv")}
    rep = {r["report_id"]: r for r in rcsv("sampling/reports_main.csv")}
    sh = {r["report_id"] for r in rcsv("annotation/human/SH_pairs.csv", "utf-8-sig")}
    log = Counter()
    frame = []
    for c in sorted(rcsv("annotation/claims/claims_s1.csv"), key=lambda c: c["claim_id"]):
        if rep.get(c["report_id"], {}).get("sample") != "random":
            continue
        if c["report_id"] in sh:
            log["in_SH"] += 1; continue
        a, b = A1.get(c["claim_id"]), A2.get(c["claim_id"])
        if not (a and b and a["label"] == "SUPPORTED" and b["label"] == "SUPPORTED"):
            continue
        log["agreed_supported"] += 1
        if "1" in (a.get("unsure"), b.get("unsure"), a.get("split_error"), b.get("split_error")):
            log["drop_unsure_or_split"] += 1; continue
        if len(c["claim_text"].split()) < 5:
            log["drop_short"] += 1; continue
        frame.append(c)
    rng = random.Random(SEED_SAMPLE)
    picked = []
    for iss in ISSUERS:
        fr = [c for c in frame if c["ann_id"].split("-")[0] == iss]
        rng.shuffle(fr)
        seen, by = set(), defaultdict(list)
        for c in fr:
            k = (c["ann_id"], key(c["claim_text"]))
            if k in seen:
                log["drop_duplicate"] += 1; continue
            seen.add(k); by[c["ann_id"]].append(c)
        anns = sorted(by); rng.shuffle(anns)
        n_ann, got = Counter(), []
        for t in (1, 2, 3):
            progress = True
            while len(got) < PER_ISSUER and progress:
                progress = False
                for a in anns:
                    if len(got) >= PER_ISSUER or n_ann[a] >= CAP:
                        continue
                    nxt = next((c for c in by[a] if tier(c["claim_text"]) == t and c not in got), None)
                    if nxt:
                        got.append(nxt); n_ann[a] += 1; progress = True
        assert len(got) == PER_ISSUER, (iss, len(got))
        picked += got
        log[f"{iss}_frame"] = len(fr); log[f"{iss}_announcements"] = len(n_ann)
    rot = {}
    w = csv.writer(open(BASE, "w", newline="", encoding="utf-8"))
    w.writerow(["base_id", "claim_id", "report_id", "ann_id", "issuer", "part", "tier", "mis_target", "claim_text"])
    for i, c in enumerate(picked):
        w.writerow([f"B{i+1:03d}", c["claim_id"], c["report_id"], c["ann_id"], c["ann_id"].split("-")[0], c["part"],
                    tier(c["claim_text"]), MIS_TYPES[i % 5], norm(c["claim_text"])])
    print(dict(log)); print("tiers", Counter(tier(c["claim_text"]) for c in picked), "parts", Counter(c["part"] for c in picked))
    print("announcements", len({c["ann_id"] for c in picked}), "max per ann", max(Counter(c["ann_id"] for c in picked).values()))
    json.dump(dict(log), open(f"{OUT}/base_claims_v2_log.json", "w"), indent=1)


# ---------------------------------------------------------------- generate
def source_for_model(aid, claims):
    t1, t2 = src(aid)
    note = ""
    if len(t1) + len(t2) > LONG and t2.strip():
        words = set(w for c in claims for w in re.findall(r"\w{4,}", c.lower()))
        chunks = [t2[i:i + CHUNK] for i in range(0, len(t2), CHUNK)]
        score = sorted(range(len(chunks)), key=lambda i: -len(words & set(re.findall(r"\w{4,}", chunks[i].lower()))))
        keep = sorted(score[:T2_KEEP // CHUNK])
        t2 = "\n[...]\n".join(chunks[i] for i in keep)
        note = f"T2 cut to {len(keep)} of {len(chunks)} chunks"
    a = f"<press_release>\n{t1}\n</press_release>\n" + (f"<full_decision_text>\n{t2}\n</full_decision_text>\n" if t2.strip() else "<full_decision_text>none</full_decision_text>\n")
    return a, note


GUIDE = open("annotation/guidelines_v1.2.md", encoding="utf-8").read()

SYS1 = f"""You build a controlled test set for a research study on Azerbaijani news reports of official announcements.
Each base claim below comes from a news report and is SUPPORTED by the official source A (press release, plus full decision text where present).
For each base claim you write two minimal edits of the claim. The labels are defined by these annotation guidelines:

<guidelines>
{GUIDE}
</guidelines>

Edit 1, CONTRADICTION (intended label CONTRADICTED): change the claim minimally so that the edited claim and A CANNOT both be true
(guidelines decision step 3). Pick ONE type from: amount, date, actor, scope, status, condition (the one that fits the claim best).
The conflict must be clear to a careful reader of A.

Edit 2, DISTORTION (intended label MISREPRESENTED, with the given target distortion_type): change the claim minimally so that it is
NOT strictly incompatible with A (A and the claim could both be true), but a reader who believes it gets a wrong picture of what A says
(decision step 4). Target types, as in the guidelines:
- status: a plan, proposal, possibility or recommendation in A reported as decided or certain, or "may" as "must", or a start
  reported as more certain than A says (without stating a date that conflicts with A);
- scope: a narrower or wider group, product or system than in A, worded so that it is misleading but not a flat contradiction
  (for example "pensioners" for "pensioners over 80");
- actor: a misleading picture of who pays, benefits or is obligated, without naming an actor that is incompatible with A;
- inference: add a short explanation or consequence ("yəni ...", "bu o deməkdir ki ...", "buna görə ...") that misreads A's rule
  (reversed direction, wrong group affected);
- dropped_condition: drop a condition, threshold or exception inside the claim so that its meaning changes (the condition must be one A
  attaches to this point).
The distortion must NOT be a mere omission of detail, rounding or a shorter wording (those stay SUPPORTED), must NOT add a fact A does not
address (that is NOT_IN_SOURCE), and must NOT be a flat contradiction.

Rules for both edits:
- Minimal: change as few words as possible; keep the language (Azerbaijani), register and style of the base claim; keep it one sentence of
  similar length. Do not add hedges or markers that reveal the edit.
- evidence: copy, character for character, ONE sentence or table cell from A (from the text given below, not from the guidelines) that shows
  the conflict (edit 1) or what A really says on the distorted point (edit 2). It must be a verbatim substring of A: no ellipses, no
  paraphrase, no added quotes, no text from different places joined.
- If the target distortion type is truly impossible for a claim, still write your best distortion edit of another type, and set
  "target_feasible": false and "used_type" to the type you used. Otherwise "target_feasible": true and "used_type" = the target.
"""

SPEC = """Return ONLY one JSON object, no prose, no code fence:
{"edits": [{"base_id": "...",
  "con": {"edited_claim": "...", "type": "amount|date|actor|scope|status|condition", "evidence": "verbatim from A", "why": "one short sentence"},
  "mis": {"edited_claim": "...", "target_feasible": true, "used_type": "status|scope|actor|inference|dropped_condition", "evidence": "verbatim from A", "why": "one short sentence"}}]}
One entry per base_id, in the given order."""


def call_api(aid, items, extra=""):
    import anthropic
    client = anthropic.Anthropic(max_retries=4, timeout=1800)
    a, note = source_for_model(aid, [b["claim_text"] for b in items])
    sys2 = f"<A id=\"{aid}\">\n{a}</A>"
    lines = "\n".join(f"{b['base_id']} [target distortion_type: {b['mis_target']}]: {b['claim_text']}" for b in items)
    user = f"Base claims (each SUPPORTED by A):\n{lines}\n\n{extra}{SPEC}"
    t0 = time.time()
    with client.messages.stream(model=MODEL, max_tokens=32000, output_config={"effort": EFFORT},
                                system=[{"type": "text", "text": SYS1, "cache_control": {"type": "ephemeral"}},
                                        {"type": "text", "text": sys2, "cache_control": {"type": "ephemeral"}}],
                                messages=[{"role": "user", "content": user}]) as st:
        m = st.get_final_message()
    txt = "".join(b.text for b in m.content if b.type == "text")
    u = m.usage
    cost = (u.input_tokens * PRICE[0] + u.output_tokens * PRICE[1] + (u.cache_read_input_tokens or 0) * PRICE[2] + (u.cache_creation_input_tokens or 0) * PRICE[3]) / 1e6
    meta = {"ann_id": aid, "n": len(items), "model": m.model, "stop_reason": m.stop_reason, "effort": EFFORT, "input": u.input_tokens,
            "output": u.output_tokens, "cache_read": u.cache_read_input_tokens, "cache_write": u.cache_creation_input_tokens,
            "cost_usd": round(cost, 4), "seconds": round(time.time() - t0), "source_note": note, "retry": bool(extra)}
    return txt, meta


def parse(txt):
    return json.loads(re.search(r"\{.*\}", txt, re.S).group(0))


def run_ann(aid, items, tag="", extra=""):
    os.makedirs(RAW, exist_ok=True)
    out = f"{RAW}/{aid}{tag}.json"
    last = None
    for attempt in range(2):
        try:
            txt, meta = call_api(aid, items, extra)
            with open(COST, "a") as f:
                f.write(json.dumps(meta) + "\n")
            d = parse(txt)
            json.dump({"meta": meta, "items": [b["base_id"] for b in items], "result": d}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return aid, "ok", meta["cost_usd"]
        except Exception as e:
            last = repr(e)[:300]
            print(f"{aid}{tag} attempt {attempt}: {last}", flush=True)
    return aid, f"FAIL {last}", 0


def spent():
    return sum(json.loads(l)["cost_usd"] for l in open(COST)) if os.path.exists(COST) else 0.0


def generate(jobs=6, only=None):
    base = rcsv(BASE)
    by = defaultdict(list)
    for b in base:
        by[b["ann_id"]].append(b)
    todo = [a for a in sorted(by) if (only is None or a in only) and not os.path.exists(f"{RAW}/{a}.json")]
    print(f"{len(todo)} announcements to run; spent so far ${spent():.2f}", flush=True)
    with cf.ThreadPoolExecutor(jobs) as ex:
        for aid, st, c in ex.map(lambda a: run_ann(a, by[a]), todo):
            print(aid, st, c, f"total ${spent():.2f}", flush=True)


# ---------------------------------------------------------------- rebalance (status type under-filled after the first pass)
def rebalance(jobs=6):
    """Second pass (D14): every base claim whose first-pass MIS edit used an over-filled type (more than 30 edits) gets one
    more call asking for a status distortion. The output is stored separately; check() uses it to replace over-filled types,
    in seeded order, until status reaches 30 or no feasible candidate is left."""
    rows = rcsv(SET)
    cnt = Counter(r["target_type"] for r in rows if r["kind"] == "MIS")
    over = {t for t, n in cnt.items() if n > 30}
    base = {b["base_id"]: b for b in rcsv(BASE)}
    by = defaultdict(list)
    for r in rows:
        if r["kind"] == "MIS" and r["target_type"] in over:
            by[r["ann_id"]].append(dict(base[r["base_id"]], mis_target="status"))
    todo = [a for a in sorted(by) if not os.path.exists(f"{RAW}/{a}_status.json")]
    extra = ("Second pass for the DISTORTION edit only: for each claim, try target distortion_type status (a plan, proposal, possibility, "
             "recommendation or conditional rule in A reported as decided, certain, mandatory or already in effect, without a date that conflicts "
             "with A). Set target_feasible false if A gives no basis for a status distortion of this claim. Also return the con edit as usual.\n\n")
    print(f"rebalance: over-filled {over}; {sum(len(v) for v in by.values())} claims in {len(todo)} announcements", flush=True)
    with cf.ThreadPoolExecutor(jobs) as ex:
        for aid, st, c in ex.map(lambda a: run_ann(a, by[a], "_status", extra), todo):
            print(aid, st, c, f"total ${spent():.2f}", flush=True)


# ---------------------------------------------------------------- checks
def exact_span(ev, aid):
    """Return (where, exact source span). Whitespace runs are matched loosely; the span is returned exactly as it
    stands in T1/T2."""
    e = norm(ev)
    if not e or len(e) < 15:
        return "", ""
    pat = re.compile(r"\s+".join(re.escape(w) for w in e.split(" ")))
    for name, t in zip(("T1", "T2"), src(aid)):
        m = pat.search(unicodedata.normalize("NFC", t))
        if m:
            return name, m.group(0)
    return "", ""


def in_source(ev, aid):
    return exact_span(ev, aid)[0]


def check_one(b, d):
    """Check the con and mis edits of one base claim; return {kind: row} and a list of failure strings."""
    rows, fails = {}, []
    for kind in ("con", "mis"):
        e = (d or {}).get(kind) or {}
        ed, ev = norm(e.get("edited_claim", "")), e.get("evidence", "")
        where, span = exact_span(ev, b["ann_id"])
        f = []
        if not ed:
            f.append("no edited claim")
        if key(ed) == key(b["claim_text"]):
            f.append("edited = base")
        if not where:
            f.append("evidence not in source")
        if kind == "con" and e.get("type") not in CON_TYPES:
            f.append(f"bad con type {e.get('type')}")
        if kind == "mis" and e.get("used_type") not in MIS_TYPES:
            f.append(f"bad mis type {e.get('used_type')}")
        if f:
            fails += [f"{kind}: {x}" for x in f]
        rows[kind] = dict(edited=ed, evidence=span, where=where, ok=not f,
                          type=e.get("type") if kind == "con" else e.get("used_type"),
                          feasible=e.get("target_feasible", True), why=e.get("why", ""))
    if rows["con"]["edited"] and key(rows["con"]["edited"]) == key(rows["mis"]["edited"]):
        fails.append("mis: same as con"); rows["mis"]["ok"] = False
    return rows, fails


def load_results():
    res = {}
    for fn in sorted(os.listdir(RAW)):
        if not fn.endswith(".json"):
            continue
        j = json.load(open(f"{RAW}/{fn}", encoding="utf-8"))
        tag = "retry" if "_retry" in fn else "status" if "_status" in fn else "first"
        allowed = set(j["items"])
        for e in j["result"].get("edits", []):
            bid = e.get("base_id")
            if bid not in allowed:
                print(f"WARNING {fn}: base_id {bid} was not requested in this call; ignored"); continue
            if tag in res.get(bid, {}):
                print(f"WARNING {fn}: duplicate {bid}; first kept"); continue
            res.setdefault(bid, {})[tag] = e
    return res


def check():
    base = rcsv(BASE)
    res = load_results()
    out, log, retry = [], [], defaultdict(list)
    first_fail = Counter()
    for b in base:
        r = res.get(b["base_id"], {})
        rows, fails = check_one(b, r.get("first"))
        for k, v in rows.items():
            if not v["ok"]:
                first_fail[k] += 1
        if fails:
            log.append(f"{b['base_id']} first: {'; '.join(fails)}")
            if "retry" in r:
                rows2, fails2 = check_one(b, r["retry"])
                for k in ("con", "mis"):
                    if not rows[k]["ok"]:
                        rows[k] = rows2[k]
                        if not rows2[k]["ok"]:
                            log.append(f"{b['base_id']} retry {k}: {'; '.join(x for x in fails2 if x.startswith(k))} -> DROPPED")
            else:
                retry[b["ann_id"]].append(b["base_id"])
        if rows["con"]["ok"] and rows["mis"]["ok"] and key(rows["con"]["edited"]) == key(rows["mis"]["edited"]):
            rows["mis"]["ok"] = False
            log.append(f"{b['base_id']} final pair: mis same as con -> MIS DROPPED")
        for k in ("con", "mis"):
            v = rows[k]
            if v["ok"]:
                out.append({"base_id": b["base_id"], "edit_id": f"{b['base_id']}-{k.upper()}", "kind": k.upper(),
                            "target_type": v["type"], "base_claim": b["claim_text"], "edited_claim": v["edited"],
                            "evidence": v["evidence"], "ann_id": b["ann_id"], "issuer": b["issuer"], "claim_id": b["claim_id"],
                            "part": b["part"], "evidence_in": v["where"],
                            "mis_target_assigned": b["mis_target"] if k == "mis" else "",
                            "target_feasible": v["feasible"] if k == "mis" else "", "generator_note": v["why"]})
    # replace edits of over-filled types with feasible status edits from the second pass
    swaps = []
    cand = []
    for b in base:
        st = res.get(b["base_id"], {}).get("status")
        if not st:
            continue
        rws, _ = check_one(dict(b, mis_target="status"), st)
        v = rws["mis"]
        if v["ok"] and v["type"] == "status" and v["feasible"] is True:
            cand.append((b, v))
    random.Random(SEED_SAMPLE + 1).shuffle(cand)
    for b, v in cand:
        cnt = Counter(r["target_type"] for r in out if r["kind"] == "MIS")
        if cnt["status"] >= 30:
            break
        cur = next((r for r in out if r["base_id"] == b["base_id"] and r["kind"] == "MIS"), None)
        con_row = next((r for r in out if r["base_id"] == b["base_id"] and r["kind"] == "CON"), None)
        if cur is None or (con_row and key(con_row["edited_claim"]) == key(v["edited"])) or cnt[cur["target_type"]] <= 30:
            continue
        swaps.append(f"{b['base_id']}: {cur['target_type']} -> status")
        cur.update(target_type="status", edited_claim=v["edited"], evidence=v["evidence"], evidence_in=v["where"],
                   target_feasible=True, generator_note=v["why"], mis_target_assigned=cur["mis_target_assigned"] + ">rebalanced:status")
    log.append(f"rebalancing: {len(cand)} feasible status candidates; {len(swaps)} swaps: " + "; ".join(swaps))
    json.dump({k: v for k, v in retry.items()}, open(f"{OUT}/retry_todo.json", "w"), indent=1)
    cols = ["base_id", "edit_id", "kind", "target_type", "base_claim", "edited_claim", "evidence", "ann_id",
            "issuer", "claim_id", "part", "evidence_in", "mis_target_assigned", "target_feasible", "generator_note"]
    w = csv.DictWriter(open(SET, "w", newline="", encoding="utf-8"), fieldnames=cols)
    w.writeheader(); w.writerows(out)
    kinds = Counter(r["kind"] for r in out)
    mis = Counter(r["target_type"] for r in out if r["kind"] == "MIS")
    con = Counter(r["target_type"] for r in out if r["kind"] == "CON")
    iss = Counter((r["issuer"], r["kind"]) for r in out)
    swapped = [r["base_id"] for r in out if r["kind"] == "MIS" and r["target_type"] != r["mis_target_assigned"].split(">")[0]]
    s = (f"# Edit set v2 automatic checks\n\nrows {len(out)}; by kind {dict(kinds)}\nMIS types {dict(mis)}\nCON types {dict(con)}\n"
         f"by issuer x kind {dict(sorted(iss.items()))}\nfirst-pass failures by kind {dict(first_fail)}\n"
         f"MIS used type differs from assigned target: {len(swapped)} {swapped}\npending retry: {dict(retry)}\n\n## Failure log\n" + "\n".join(log) + "\n")
    open("logs/edit_set_v2_checks.md", "w").write(s)
    print(s)


def retry_failed(jobs=6):
    todo = json.load(open(f"{OUT}/retry_todo.json"))
    base = {b["base_id"]: b for b in rcsv(BASE)}
    res = load_results()
    jobsl = []
    for aid, ids in todo.items():
        items = [base[i] for i in ids]
        notes = []
        for i in ids:
            _, fails = check_one(base[i], res.get(i, {}).get("first"))
            notes.append(f"{i}: previous attempt failed the automatic check ({'; '.join(fails)}).")
        extra = ("These are second attempts. " + " ".join(notes) +
                 " Copy the evidence exactly as it appears in A (verbatim substring, same characters, no ellipsis).\n\n")
        jobsl.append((aid, items, extra))
    with cf.ThreadPoolExecutor(jobs) as ex:
        for aid, st, c in ex.map(lambda x: run_ann(x[0], x[1], "_retry", x[2]), jobsl):
            print(aid, st, c, f"total ${spent():.2f}", flush=True)


# ---------------------------------------------------------------- packets
HOWTO = """# HOWTO: checking edited claims ({who}, {n} items, about {mins} minutes)

1. Open items_{who}.csv (your answer sheet) and the folder items/. Each row has an item_id; items/<item_id>.html shows that item.
2. Each item shows the official source A (press release, and the relevant part of the full decision text where there is one), a base claim, and an edited claim.
3. The base claim was taken from a real news report; the edited claim is a changed version of it. Judge ONLY the edited claim, against A.
4. In `verdict` write one of: CONTRADICTED (the edited claim and A cannot both be true), MISREPRESENTED (not strictly incompatible with A, but misleading about what A says), SUPPORTED, NOT_IN_SOURCE, or UNCLEAR.
5. If MISREPRESENTED, write in `distortion_type` one of: status, scope, actor, inference, dropped_condition (definitions: guidelines section 3).
6. Use guidelines v1.2 (guidelines_v1.2.md in this folder) for the label definitions and the 4-step decision order.
7. If the edited claim is not fluent Azerbaijani, or changes more than needed, still give a verdict and say so in `note`.
8. `note`: one short line, required for UNCLEAR and whenever you hesitate.
9. Items are in random order. Work alone; do not use AI tools to suggest or check verdicts.
10. When done, save the CSV (UTF-8) and send it back.
"""


def page(item_id, aid, t1, t2part, base_claim, edited):
    e = html.escape
    t2h = (f"<h3>Full decision text (relevant part)</h3><pre>{e(t2part)}</pre>" if t2part.strip() else "<p><i>No full decision text.</i></p>")
    return f"""<!doctype html><html lang="az"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{item_id}</title><style>body{{font-family:system-ui,sans-serif;margin:16px;max-width:1500px}}.wrap{{display:flex;gap:24px;flex-wrap:wrap}}
.src{{flex:3 1 600px;max-height:88vh;overflow:auto;border:1px solid #bbb;padding:8px}}.cl{{flex:2 1 380px}}pre{{white-space:pre-wrap;font-family:inherit}}
.box{{border:1px solid #888;padding:10px;margin:8px 0}}</style></head><body>
<h2>{item_id}</h2><div class="wrap"><div class="src"><h3>Official source A ({aid}): press release</h3><pre>{e(t1)}</pre>{t2h}</div>
<div class="cl"><h3>Base claim (from a news report)</h3><div class="box">{e(base_claim)}</div>
<h3>Edited claim (judge this one against A)</h3><div class="box"><b>{e(edited)}</b></div>
<p>Write in the sheet: verdict = CONTRADICTED / MISREPRESENTED / SUPPORTED / NOT_IN_SOURCE / UNCLEAR; distortion_type if MISREPRESENTED; short note.</p></div></div></body></html>"""


def t2_excerpt(aid, texts, limit=12000):
    """Return the relevant part of T2 for a packet item: the whole T2 if short; else the chunks that hold the generator's
    evidence (last text, when it lies in T2) plus the chunks with the most word overlap with the given texts, up to
    `limit` characters, in document order, with [...] gaps. Nothing is highlighted."""
    _, t2 = src(aid)
    if len(t2) <= limit:
        return t2
    paras = [p for p in re.split(r"\n+", t2) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > CHUNK and cur:
            chunks.append(cur); cur = ""
        cur += p + "\n"
    if cur:
        chunks.append(cur)
    words = set(w for t in texts for w in re.findall(r"\w{4,}", t.lower()))
    must = []
    if texts[-1]:  # all chunks the evidence span overlaps (it may cross a chunk boundary)
        full = "".join(chunks)
        m = re.search(r"\s+".join(re.escape(w) for w in norm(texts[-1]).split(" ")), full)
        if m:
            pos, end, start = m.start(), m.end(), 0
            for i, c in enumerate(chunks):
                if start < end and start + len(c) > pos:
                    must.append(i)
                start += len(c)
    score = sorted(range(len(chunks)), key=lambda i: -len(words & set(re.findall(r"\w{4,}", chunks[i].lower()))))
    keep, size = list(must), sum(len(chunks[i]) for i in must)
    for i in score:
        if i in keep:
            continue
        if size + len(chunks[i]) > limit:
            continue
        keep.append(i); size += len(chunks[i])
    keep = sorted(set(keep))
    out, prev = [], -2
    for i in keep:
        if i != prev + 1:
            out.append("[...]")
        out.append(chunks[i].strip()); prev = i
    if keep and keep[-1] != len(chunks) - 1:
        out.append("[...]")
    return "\n".join(out)


def packets():
    rows = rcsv(SET)
    con = [r for r in rows if r["kind"] == "CON"]
    mis = [r for r in rows if r["kind"] == "MIS"]
    rng = random.Random(SEED_PACKETS)
    x_mis = rng.sample(sorted(mis, key=lambda r: r["edit_id"]), round(0.2 * len(mis)))
    x_con = rng.sample(sorted(con, key=lambda r: r["edit_id"]), round(0.2 * len(con)))
    plan = {"R1": con + x_mis, "R2": mis + x_con}
    key_rows = []
    for who, items in plan.items():
        d = f"annotation/human/{who}/EDITS"
        os.makedirs(f"{d}/items", exist_ok=True)
        for fn in os.listdir(f"{d}/items"):
            os.remove(f"{d}/items/{fn}")
        items = sorted(items, key=lambda r: r["edit_id"])
        rng.shuffle(items)
        sheet = []
        for i, r in enumerate(items):
            item_id = f"{who}-E{i+1:03d}"
            t1, _ = src(r["ann_id"])
            t2p = t2_excerpt(r["ann_id"], [r["base_claim"], r["edited_claim"], r["evidence"] if r["evidence_in"] == "T2" else ""])
            open(f"{d}/items/{item_id}.html", "w", encoding="utf-8").write(page(item_id, r["ann_id"], t1, t2p, r["base_claim"], r["edited_claim"]))
            sheet.append([item_id, r["ann_id"], r["base_claim"], r["edited_claim"], "", "", ""])
            key_rows.append([who, item_id, r["edit_id"], "primary" if (who == "R1") == (r["kind"] == "CON") else "crosscheck"])
        w = csv.writer(open(f"{d}/items_{who}.csv", "w", newline="", encoding="utf-8-sig"))
        w.writerow(["item_id", "ann_id", "base_claim", "edited_claim", "verdict", "distortion_type", "note"])
        w.writerows(sheet)
        open(f"{d}/guidelines_v1.2.md", "w", encoding="utf-8").write(GUIDE)
        open(f"{d}/HOWTO_{who}.md", "w").write(HOWTO.format(who=who, n=len(items), mins=round(len(items) * 1.5 / 10) * 10))
        print(who, len(items), Counter(r["kind"] for r in items))
    # the key that maps item ids to edits is kept outside the packets
    w = csv.writer(open(f"{OUT}/packet_key_v2.csv", "w", newline="", encoding="utf-8"))
    w.writerow(["annotator", "item_id", "edit_id", "role"])
    w.writerows(key_rows)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sample":
        sample()
    elif cmd == "generate":
        if "--retry" in sys.argv:
            retry_failed()
        else:
            generate(only=set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None)
    elif cmd == "rebalance":
        rebalance()
    elif cmd == "check":
        check()
    elif cmd == "packets":
        packets()
