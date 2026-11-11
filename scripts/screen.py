"""Screen the sampling frame for eligibility (prereg.md section 2), with two independent LLM screeners.

The screeners are Claude Sonnet (claude command-line tool) and the Codex command-line agent; each judges batches of
announcements from title and text only.
Usage: python3 scripts/screen.py claude|codex cbar|tax|social [--batch 20] [--jobs 4]
Reads data/candidates/<issuer>.csv; writes sampling/screen_<who>_<issuer>.csv (cand_id, decision, reason) and the raw
outputs in sampling/raw_<who>/.
"""
import tempfile
import csv, json, os, re, subprocess, sys, concurrent.futures as cf
csv.field_size_limit(10**9)

RULE = """You screen official announcements for a research sample. For EACH announcement decide: eligible, not_eligible or borderline.
ELIGIBLE: the announcement reports an adopted or proposed decision, rule, tariff, fee, rate, tax, benefit, payment, eligibility condition or deadline that applies to citizens, firms or financial institutions. This includes statistics releases on payments or refunds made under such rules (e.g. "pensions paid in 9 months", "VAT refunded").
NOT ELIGIBLE: events, meetings, trainings, outreach visits, awards, personnel changes, international cooperation, conferences, holidays and greetings, generic awareness campaigns, announcements with no checkable content.
BORDERLINE: you cannot decide from the text; say why.
Judge only from the title and text given. Reason in English, max 15 words.
Return ONLY a JSON list: [{"cand_id": "...", "decision": "eligible|not_eligible|borderline", "reason": "..."}] with one object per announcement, same order."""
LIGHT = ["--strict-mcp-config", "--setting-sources", "project", "--no-session-persistence", "--tools", ""]


def load(issuer):
    return list(csv.DictReader(open(f"data/candidates/{issuer}.csv", encoding="utf-8")))


def prompt(batch):
    items = "\n\n".join(f"### cand_id: {r['cand_id']}\nTITLE: {r['title']}\nTEXT: {re.sub(r'\s+', ' ', r['text'])[:1500]}" for r in batch)
    return RULE + "\n\n" + items


def run(who, batch, i, issuer):
    raw = f"sampling/raw_{who}/{issuer}_{i:03d}.txt"
    if os.path.exists(raw) and os.path.getsize(raw) > 10:
        out = open(raw, encoding="utf-8").read()
    else:
        p = prompt(batch)
        if who == "claude":
            out = subprocess.run(["claude", "-p", "--model", "sonnet", *LIGHT], input=p, capture_output=True, text=True, timeout=900, cwd=tempfile.gettempdir()).stdout
        else:
            of = os.path.abspath(raw + ".codex")
            subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", of, "-"], input=p, capture_output=True, text=True, timeout=1200, cwd=tempfile.gettempdir())
            out = open(of, encoding="utf-8").read() if os.path.exists(of) else ""
        open(raw, "w", encoding="utf-8").write(out)
    m = re.search(r"\[.*\]", out, re.S)
    try:
        res = {d["cand_id"]: d for d in json.loads(m.group(0))} if m else {}
    except json.JSONDecodeError:
        res = {}
    return [{"cand_id": r["cand_id"], "decision": res.get(r["cand_id"], {}).get("decision", "MISSING"), "reason": res.get(r["cand_id"], {}).get("reason", "")} for r in batch]


def main():
    who, issuer = sys.argv[1], sys.argv[2]; bs = int(sys.argv[sys.argv.index("--batch") + 1]) if "--batch" in sys.argv else 20
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 4
    os.makedirs(f"sampling/raw_{who}", exist_ok=True)
    rows = load(issuer); batches = [rows[i:i + bs] for i in range(0, len(rows), bs)]
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda a: run(who, a[1], a[0], issuer), enumerate(batches)))
    out = [x for b in res for x in b]
    with open(f"sampling/screen_{who}_{issuer}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["cand_id", "decision", "reason"]); w.writeheader(); w.writerows(out)
    from collections import Counter
    print(who, len(out), Counter(r["decision"] for r in out))


if __name__ == "__main__":
    main()
