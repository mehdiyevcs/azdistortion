"""Split the news reports into claims (prereg section 2 "Claims"; guidelines v1.2 section 2).

Segmenter S1 is Claude (Sonnet, claude command-line tool) on all reports; segmenter S2 is the Codex command-line agent
on a seeded random 20% of the reports (random.Random(20261117)), used to measure boundary agreement.
Each claim is an exact contiguous span of the report text (located by string search) plus claim_text, a minimal
stand-alone wording (only words from the same sentence may be added, e.g. the subject of a list item).
Text parts: headline = TITLE line; lead = first paragraph of the body; body = the rest.
Usage:
  python3 scripts/split_claims.py s1|s2 [report_id ...]   -> annotation/claims/raw_<seg>/<rid>.json, annotation/claims/claims_<seg>.csv
  python3 scripts/split_claims.py f1                       -> boundary F1 of S1 vs S2 on the S2 reports, logs/split_f1.md
"""
import tempfile
import csv, json, os, random, re, subprocess, sys, concurrent.futures as cf
csv.field_size_limit(10**9)
OUT = "annotation/claims"
LIGHT = ["--strict-mcp-config", "--setting-sources", "project", "--no-session-persistence", "--tools", ""]
RULES = """You split a news report into CLAIMS for a study that checks news against an official announcement.
A claim is one checkable statement about the announcement or the decision it reports: one number, one actor, one date where possible.
Rules:
- The HEADLINE is split on its own (its claims have part=headline).
- Lists (rule revised once after round 1, boundary F1 0.62): a list whose items share one statement is ONE claim, for example the institutions a rule
  applies to, the topics a document covers, or the aims of a measure. Split a list into one claim per item ONLY when each item has its own
  number, rate, amount or date (for example tariff bands, a rate per category, a deadline per group).
- A sentence with several numbers about different things gives one claim per number. Purpose or aim statements of the issuer are one claim per sentence.
- Do NOT make claims from: quotes or opinions of experts or citizens, questions to readers, calls to comment, outlet self-promotion,
  background about other events, unless they state a fact about the announcement or decision. "Yəni ..." explanations by the outlet ARE claims.
- Statements that repeat facts from the announcement's own background (inflation, statistics in the release) ARE claims.
- span: copy the shortest CONTIGUOUS piece of the text that carries the fact, EXACTLY as written (same letters, spaces, punctuation). Do not fix typos.
- claim_text: the fact as one short stand-alone Azerbaijani sentence. Keep the report's words; you may only add words from the same sentence
  (for example the subject or verb of a list) so the claim stands alone. Do not add facts, do not correct, do not translate.
Return ONLY JSON: {"claims": [{"part": "headline|lead|body", "span": "...", "claim_text": "..."}, ...]} in reading order."""


def load_report(rid):
    t = open(f"data/raw/news/{rid}/text_0.txt", encoding="utf-8").read()
    lines = t.split("\n")
    title = lines[0][len("TITLE: "):].strip() if lines and lines[0].startswith("TITLE: ") else ""
    body = [l for l in lines[1:] if l.strip() and not re.match(r"^(DATE|AUTHOR): ", l)]
    # page furniture that the extractor keeps (repeated title, section label, date and time lines, subscribe prompts)
    BOIL = re.compile(r"^(-\s*\d{1,2}\s+\w+,\s*\d{4}|-\s*\d{1,2}:\d{2}|Yeniliklərdən dərhal xəbərdar olun!?|Report\.az-ı Google.*|"
                      r"Maliyyə|Sosial müdafiə|Milli Məclis|Daxili siyasət|İqtisadiyyat|Cəmiyyət|Gündəm|Biznes|Vergi|Bank)$")
    body = [l for l in body if not BOIL.match(l.strip()) and l.strip() != title.strip()]
    return title, body


def prompt(rid):
    title, body = load_report(rid)
    return RULES + "\n\nHEADLINE:\n" + title + "\n\nTEXT (paragraph 1 is the lead):\n" + "\n".join(f"[{i + 1}] {p}" for i, p in enumerate(body))


def jparse(out):
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def run_one(seg, rid):
    f = f"{OUT}/raw_{seg}/{rid}.json"
    if os.path.exists(f):
        return json.load(open(f, encoding="utf-8"))
    p = prompt(rid)
    if seg == "s1":
        out = subprocess.run(["claude", "-p", "--model", "sonnet", *LIGHT], input=p, capture_output=True, text=True, timeout=900, cwd=tempfile.gettempdir()).stdout
    else:
        of = os.path.abspath(f"{OUT}/raw_{seg}/{rid}.tmp")
        subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", of, "-"], input=p, capture_output=True, text=True, timeout=1200, cwd=tempfile.gettempdir())
        out = open(of, encoding="utf-8").read() if os.path.exists(of) else ""
        if os.path.exists(of):
            os.remove(of)
    j = jparse(out)
    if not (j and isinstance(j.get("claims"), list)) and seg == "s1":  # one retry on a broken JSON answer
        out = subprocess.run(["claude", "-p", "--model", "sonnet", *LIGHT], input=p, capture_output=True, text=True, timeout=900, cwd=tempfile.gettempdir()).stdout
        j = jparse(out)
    if j and isinstance(j.get("claims"), list):
        json.dump(j, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return j


def locate(rid, claims):
    """Map spans to (part, start, end) in a canonical text = title + '\n' + body paragraphs joined by '\n'."""
    title, body = load_report(rid)
    canon = title + "\n" + "\n".join(body)
    lead_end = len(title) + 1 + (len(body[0]) if body else 0)
    rows, pos = [], 0
    for k, c in enumerate(claims, 1):
        sp = c.get("span", "")
        i = canon.find(sp, pos) if sp else -1
        if i < 0 and sp:
            i = canon.find(sp)
        st, en = (i, i + len(sp)) if i >= 0 else (-1, -1)
        approx = 0
        if i < 0 and sp:  # quotes typed differently by the model: 1:1 quote normalisation, then approximate match (ratio >= 0.9)
            Q = str.maketrans({c: '"' for c in "“”„«»‘’'"})
            i = canon.translate(Q).find(sp.translate(Q))
            if i >= 0:
                st, en = i, i + len(sp); approx = 1
            else:
                import difflib
                best, bi = 0, -1
                L = len(sp)
                for j in range(0, max(1, len(canon) - L + 1), 3):
                    r = difflib.SequenceMatcher(None, canon[j:j + L], sp, autojunk=False).quick_ratio()
                    if r > best:
                        best, bi = r, j
                if bi >= 0:
                    r = difflib.SequenceMatcher(None, canon[bi:bi + L], sp, autojunk=False).ratio()
                    if r >= 0.9:
                        st, en = bi, bi + L; approx = 2
            i = st
        part = "headline" if 0 <= st < len(title) else ("lead" if 0 <= st < lead_end else ("body" if st >= 0 else c.get("part", "")))
        if i >= 0:
            pos = i
        rows.append({"claim_id": f"{rid}-C{k:02d}", "report_id": rid, "part": part, "start": st, "end": en, "span_found": int(st >= 0), "span_match": approx,
                     "span": sp, "claim_text": c.get("claim_text", "")})
    return rows


def segment(seg, rids):
    os.makedirs(f"{OUT}/raw_{seg}", exist_ok=True)
    with cf.ThreadPoolExecutor(4 if seg == "s1" else 3) as ex:
        list(ex.map(lambda r: run_one(seg, r), rids))
    rep = {r["report_id"]: r for r in csv.DictReader(open("sampling/reports_main.csv", encoding="utf-8"))}
    rows, bad = [], []
    for rid in sorted(rep):
        f = f"{OUT}/raw_{seg}/{rid}.json"
        if not os.path.exists(f):
            continue
        for r in locate(rid, json.load(open(f, encoding="utf-8"))["claims"]):
            r["ann_id"] = rep[rid]["ann_id"]; rows.append(r)
            if not r["span_found"]:
                bad.append(r["claim_id"])
    fn = ["claim_id", "report_id", "ann_id", "part", "start", "end", "span_found", "span_match", "span", "claim_text"]
    w = csv.DictWriter(open(f"{OUT}/claims_{seg}.csv", "w", newline="", encoding="utf-8"), fieldnames=fn); w.writeheader(); w.writerows(rows)
    print(seg, len(rows), "claims from", len({r['report_id'] for r in rows}), "reports; spans not found:", len(bad), bad[:10])


def s2_sample():
    if os.path.exists("sampling/s2_set.txt"):  # fixed S2 set; reports added later by R1's link decisions have no S2 split
        return [l.strip() for l in open("sampling/s2_set.txt") if l.strip()]
    """Round-2 S2 set (27 reports of the first 135, seed 20261117) plus a seeded 20% of every report added later (random and benchmark),
    so the reports already checked stay checked (prereg D10)."""
    old = sorted(r["report_id"] for r in csv.DictReader(open("sampling/reports_main_v1.csv", encoding="utf-8")))
    first = sorted(random.Random(20261117).sample(old, max(1, round(0.2 * len(old)))))
    allr = sorted(r["report_id"] for r in csv.DictReader(open("sampling/reports_main.csv", encoding="utf-8")))
    new = [r for r in allr if r not in set(old)]
    return sorted(set(first) | set(random.Random(20261117).sample(new, round(0.2 * len(new)))))


def f1():
    def load(seg):
        d = {}
        for r in csv.DictReader(open(f"{OUT}/claims_{seg}.csv", encoding="utf-8")):
            if r["span_found"] == "1":
                d.setdefault(r["report_id"], []).append((int(r["start"]), int(r["end"])))
        return d
    a, b = load("s1"), load("s2")
    rids = sorted(set(a) & set(b))
    tp = fp = fn = ex = 0
    for rid in rids:
        A, B = a[rid][:], b[rid][:]
        for s in A:
            exact = s in B
            best, bj = None, 0
            for t in B:
                inter = max(0, min(s[1], t[1]) - max(s[0], t[0])); uni = max(s[1], t[1]) - min(s[0], t[0])
                j = inter / uni if uni else 0
                if j > bj:
                    best, bj = t, j
            if best is not None and bj >= 0.5:
                tp += 1; ex += exact; B.remove(best)
            else:
                fn += 1
        fp += len(B)
    p = tp / (tp + fp) if tp + fp else 0; r = tp / (tp + fn) if tp + fn else 0; F = 2 * p * r / (p + r) if p + r else 0
    msg = (f"Boundary F1 (S1 Claude vs S2 Codex), {len(rids)} reports; a claim matches if its character span overlaps a claim of the other "
           f"segmenter with Jaccard >= 0.5 (one-to-one).\nS1 claims {tp + fn}, S2 claims {tp + fp}, matched {tp} (exact span {ex}).\n"
           f"precision (S2 vs S1) {p:.3f}, recall {r:.3f}, F1 {F:.3f}. Gate 0.75: {'PASS' if F >= 0.75 else 'FAIL'}.\n")
    open("logs/split_f1.md", "w").write(msg); print(msg)


if __name__ == "__main__":
    step = sys.argv[1]
    allr = sorted(r["report_id"] for r in csv.DictReader(open("sampling/reports_main.csv", encoding="utf-8")))
    if step == "s1":
        segment("s1", sys.argv[2:] or allr)
    elif step == "s2":
        segment("s2", sys.argv[2:] or s2_sample())
    elif step == "f1":
        f1()
