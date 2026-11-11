"""Verify the APA and AZERTAC candidate reports found by browser site search (prereg "Linking and verification", D4).

Same prompt and rules as link_news.verify: Claude checks every candidate in the window [d-1, d+7] with more than
200 characters of text, Codex a seeded 20% (random.Random(20261114)). The text is the page text saved from the
browser (the file in cached_file; its first two lines are the URL and the save time).
Inputs: data/link_candidates_browser.csv, sampling/drawn_60.csv, sampling/drawn_final.csv
Usage: python3 scripts/verify_browser.py claude|codex
Output: data/link_verified_<who>_browser.csv
"""
import tempfile
import csv, datetime as dt, os, random, re, subprocess, sys, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__))
import link_news as L
csv.field_size_limit(10**9)
who = sys.argv[1]
A = {r["cand_id"]: r for f in ("sampling/drawn_60.csv", "sampling/drawn_final.csv") for r in csv.DictReader(open(f, encoding="utf-8"))}
rows = []
for r in csv.DictReader(open("data/link_candidates_browser.csv", encoding="utf-8")):
    t = open(r["cached_file"], encoding="utf-8").read().split("\n", 2)[-1]
    d0 = dt.date.fromisoformat(A[r["cand_id"]]["date"])
    try:
        inw = d0 - dt.timedelta(days=1) <= dt.date.fromisoformat(r["pub_date"][:10]) <= d0 + dt.timedelta(days=7)
    except ValueError:
        inw = False
    if inw and len(t) > 200:
        rows.append({**r, "text": t})
if who == "codex":
    rng = random.Random(20261114); rows = [r for r in rows if rng.random() < 0.2]
groups = {}
for r in rows:
    groups.setdefault(r["cand_id"], []).append(r)


def one(item):
    aid, rs = item; a = A[aid]
    items = "\n\n".join(f"### report_id: R{k}\nOUTLET: {r['outlet']} DATE: {r['pub_date']}\nTITLE: {r['title']}\nTEXT: {re.sub(r'\s+', ' ', r['text'])[:1200]}" for k, r in enumerate(rs))
    p = ("For each NEWS REPORT decide whether it is about the SAME official decision/announcement as the ANNOUNCEMENT (not just the same topic or another decision of the same body).\n"
         "verdict: same_decision, same_topic_only, or unrelated. reason: max 12 words.\n"
         'Return ONLY a JSON list: [{"report_id": "R0", "verdict": "...", "reason": "..."}, ...] covering every report.\n\n'
         f"ANNOUNCEMENT ({a['date']}): {a['title']}\n{re.sub(r'\s+', ' ', a['text'])[:1800]}\n\n{items}")
    if who == "claude":
        out = L.claude(p)
    else:
        of = os.path.abspath(f"data/codex_tmp_b_{aid}.txt")
        subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", of, "-"], input=p, capture_output=True, text=True, timeout=1200, cwd=tempfile.gettempdir())
        out = open(of, encoding="utf-8").read() if os.path.exists(of) else ""
        if os.path.exists(of):
            os.remove(of)
    j = L.jparse(out) or []
    J = {d.get("report_id"): d for d in j} if isinstance(j, list) else {}
    return [{"ann_id": aid, "outlet": r["outlet"], "url": r["url"], "pub_date": r["pub_date"], "title": r["title"],
             "verdict": J.get(f"R{k}", {}).get("verdict", "MISSING"), "reason": J.get(f"R{k}", {}).get("reason", "")} for k, r in enumerate(rs)]


with cf.ThreadPoolExecutor(4 if who == "claude" else 3) as ex:
    res = [x for g in ex.map(one, groups.items()) for x in g]
w = csv.DictWriter(open(f"data/link_verified_{who}_browser.csv", "w", newline="", encoding="utf-8"), fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
from collections import Counter
print(who, len(res), Counter(r["verdict"] for r in res))
