"""Recall audit of the keyword linking step for the sitemap outlets Report, Oxu.az, Qafqazinfo and Musavat (prereg D10).

Steps:
  pick   : 10 drawn announcements, random.Random(20261116).sample(sorted(cand_ids), 10)
  screen : every pool entry of the 4 outlets dated in the window [d-1, d+7] (estimated dates with a 2-day margin), no
           keyword filter; Claude (Sonnet, claude command-line tool) screens the slugs in batches of 400 for
           "possibly about this decision" -> data/recall_screen.csv
  fetch  : link_news.fetch with SUF="recall" on the possible ones
           (data/link_candidates_recall.csv -> data/link_fetched_recall.csv)
  verify : link_news.verify with SUF="recall" (same prompt, Claude only) -> data/link_verified_claude_recall.csv
  report : missed = verified same_decision reports not in sampling/reports_verified_drawn.csv
           -> sampling/recall_audit_missed.csv; prints recall of the keyword step
Usage: .venv/bin/python scripts/recall_audit.py screen|fetch|verify|report
"""
import csv, datetime as dt, json, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concurrent.futures as cf
import link_news as ln

SEED = 20261116
OUTLETS = ("Report", "Oxu.az", "Qafqazinfo", "Musavat")
SCR = "data/recall_screen.csv"


def pick():
    A = {a["cand_id"]: a for a in ln.anns("sampling/drawn_60.csv")}
    return [A[i] for i in random.Random(SEED).sample(sorted(A), 10)]


def window_pool(a, pool):
    d0 = dt.date.fromisoformat(a["date"]); lo, hi = d0 - dt.timedelta(days=1), d0 + dt.timedelta(days=7)
    out = []
    for p in pool:
        if p["outlet"] not in OUTLETS or not (p["date"] or p.get("est_date")):
            continue
        try:
            pd = dt.date.fromisoformat(p["date"] or p["est_date"])
        except ValueError:
            continue
        m = 0 if p["date"] else 2
        if (lo - dt.timedelta(days=m)) <= pd <= (hi + dt.timedelta(days=m)):
            out.append(p)
    return out


def screen():
    S = pick()
    pool = list(csv.DictReader(open("data/news_pool.csv", encoding="utf-8")))
    done = {(r["ann_id"], r["batch"]) for r in csv.DictReader(open(SCR, encoding="utf-8"))} if os.path.exists(SCR) else set()
    jobs = []
    for a in S:
        wp = window_pool(a, pool)
        print(a["cand_id"], a["date"], len(wp), "pool entries", flush=True)
        for b in range(0, len(wp), 400):
            if (a["cand_id"], str(b // 400)) not in done:
                jobs.append((a, b // 400, wp[b:b + 400]))
    def one(job):
        a, bi, ps = job
        p = ("Below is an official ANNOUNCEMENT and a numbered list of news URL slugs (Azerbaijani, transliterated to ASCII) from the same week.\n"
             "List the numbers of ALL slugs that could POSSIBLY be a report about this same decision/announcement (its figures, its measure, "
             "its programme, or the issuer's statement on it). Be inclusive: when in doubt, include. Ignore reports clearly about other matters.\n"
             'Return ONLY JSON: {"possible": [numbers]}\n\n'
             f"ANNOUNCEMENT ({a['date']}): {a['title']}\n{re.sub(r'\s+', ' ', a['text'])[:1200]}\n\nSLUGS:\n" +
             "\n".join(f"{k}: {p['slug_text']}" for k, p in enumerate(ps)))
        j = ln.jparse(ln.claude(p)) or {}
        poss = set(j.get("possible", [])) if isinstance(j, dict) else set()
        ok = isinstance(j, dict) and "possible" in j
        return [{"ann_id": a["cand_id"], "batch": bi, "outlet": p["outlet"], "url": p["url"], "date": p["date"] or p.get("est_date", ""),
                 "slug_text": p["slug_text"], "possible": int(k in poss), "parse_ok": int(ok)} for k, p in enumerate(ps)]
    new = not os.path.exists(SCR)
    with open(SCR, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ann_id", "batch", "outlet", "url", "date", "slug_text", "possible", "parse_ok"])
        if new:
            w.writeheader()
        with cf.ThreadPoolExecutor(4) as ex:
            for res in ex.map(one, jobs):
                w.writerows(res); fh.flush()
    rows = list(csv.DictReader(open(SCR, encoding="utf-8")))
    print("screened", len(rows), "possible", sum(int(r["possible"]) for r in rows), "parse failures", sum(1 for r in rows if r["parse_ok"] == "0"))


def make_cands():
    rows = [r for r in csv.DictReader(open(SCR, encoding="utf-8")) if r["possible"] == "1"]
    out = [{"ann_id": r["ann_id"], "outlet": r["outlet"], "url": r["url"], "pool_date": r["date"] if r["outlet"] in ("Report", "Oxu.az") else "",
            "hits": "", "found_by": "recall_screen"} for r in rows]
    w = csv.DictWriter(open("data/link_candidates_recall.csv", "w", newline="", encoding="utf-8"), fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print(len(out), "candidates")


def report():
    S = pick()
    known = {}
    for r in csv.DictReader(open("sampling/reports_verified_drawn.csv", encoding="utf-8")):
        known.setdefault(r["ann_id"], set()).add(r["url"])
    ver = [r for r in csv.DictReader(open("data/link_verified_claude_recall.csv", encoding="utf-8")) if r["verdict"] == "same_decision"]
    fetched = list(csv.DictReader(open("data/link_fetched_recall.csv", encoding="utf-8")))
    scr = list(csv.DictReader(open(SCR, encoding="utf-8")))
    allrep = list(csv.DictReader(open("sampling/reports_verified_drawn.csv", encoding="utf-8")))
    lines, missed, F, M = [], [], 0, 0
    for a in S:
        aid = a["cand_id"]
        found = [r for r in allrep if r["ann_id"] == aid and r["outlet"] in OUTLETS]
        fu = {r["url"] for r in found}
        v = [r for r in ver if r["ann_id"] == aid]
        miss = [r for r in v if r["url"] not in known.get(aid, set())]
        refound = sum(1 for r in v if r["url"] in fu)
        F += len(found); M += len(miss); missed += miss
        n_scr = sum(1 for r in scr if r["ann_id"] == aid); n_pos = sum(1 for r in scr if r["ann_id"] == aid and r["possible"] == "1")
        n_f = sum(1 for r in fetched if r["ann_id"] == aid and r["in_window"] == "True" and int(r["n_chars"] or 0) > 200)
        lines.append(f"| {aid} | {a['date']} | {n_scr} | {n_pos} | {n_f} | {len(found)} | {refound} | {len(miss)} |")
    w = csv.DictWriter(open("sampling/recall_audit_missed.csv", "w", newline="", encoding="utf-8"),
                       fieldnames=["ann_id", "outlet", "url", "pub_date", "title", "verdict", "reason"]); w.writeheader(); w.writerows(missed)
    return S, lines, F, M, missed


if __name__ == "__main__":
    step = sys.argv[1]
    ln.SUF = "recall"
    if step == "screen":
        screen()
    elif step == "fetch":
        make_cands(); ln.fetch(pick())
    elif step == "verify":
        ln.verify(pick())
    elif step == "report":
        S, lines, F, M, missed = report()
        print([a["cand_id"] for a in S]); print("\n".join(lines)); print("found", F, "missed", M, "recall", F / (F + M) if F + M else None)
        for r in missed:
            print(r["ann_id"], r["outlet"], r["url"], r["title"])
