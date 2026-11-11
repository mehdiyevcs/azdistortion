"""Full-window relinking for the sitemap outlets (Report, Oxu.az, Qafqazinfo, Musavat), replacing the keyword step (prereg D10 a).

For every announcement in the list, every pool entry of those outlets dated in [d-1, d+7] (estimated dates with a 2-day
margin) is screened by Claude Haiku 5.5 in batches of 400 URL slugs for "possibly about this decision" (inclusive). The
possible ones are fetched (link_news.fetch) and verified by Claude Sonnet 5.5 with the link_news verify prompt; Codex
checks a seeded 20% (link_news.verify, who=codex).
Steps (cached, resumable):
  python3 scripts/full_relink.py screen|fetch|verify|verify_codex <ann_list.csv> <suffix>
  python3 scripts/full_relink.py validate
validate: on the 10 recall-audit announcements, compare the Haiku screen with the Sonnet audit screen
(data/recall_screen.csv) and count the verified reports the Haiku screen catches.
API calls read the Anthropic key from the environment and log token costs to logs/full_relink_cost.jsonl. With the
environment variable RELINK_CLI set, screening and verification run through the Claude Code CLI with the same models.
"""
import csv, json, os, re, sys, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import link_news as ln
import recall_audit as ra
csv.field_size_limit(10**9)
SCREEN_MODEL, VERIFY_MODEL = "claude-haiku-5-5", "claude-sonnet-5-5"
PRICE = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}  # USD per million tokens (input, output)
COST = "logs/full_relink_cost.jsonl"


def api(prompt, model, max_tokens=8000):
    if os.environ.get("RELINK_CLI"):  # CLI route (same models), used when the API route timed out; cost is logged as 0
        alias = "haiku" if "haiku" in model else "sonnet"
        with open(COST, "a") as fh:
            fh.write(json.dumps({"model": f"cli:{alias}", "cost": 0}) + "\n")
        return ln.claude(prompt, model=alias)
    import anthropic
    client = anthropic.Anthropic(max_retries=2, timeout=90)
    for attempt in range(3):
        try:
            with client.messages.stream(model=model, max_tokens=max_tokens, output_config={"effort": "low"},
                                        messages=[{"role": "user", "content": prompt}]) as st:
                m = st.get_final_message()
            u = m.usage; pr = PRICE[model]
            with open(COST, "a") as fh:
                fh.write(json.dumps({"model": m.model, "in": u.input_tokens, "out": u.output_tokens, "stop": m.stop_reason,
                                     "cost": round((u.input_tokens * pr[0] + u.output_tokens * pr[1]) / 1e6, 5)}) + "\n")
            return "".join(b.text for b in m.content if b.type == "text")
        except Exception as e:
            print("api error", type(e).__name__, flush=True)
    return ""


def screen(alist, suf):
    out = f"data/full_screen_{suf}.csv"
    pool = list(csv.DictReader(open("data/news_pool.csv", encoding="utf-8")))
    done = {(r["ann_id"], r["batch"]) for r in csv.DictReader(open(out, encoding="utf-8"))} if os.path.exists(out) else set()
    jobs = []
    for a in alist:
        wp = ra.window_pool(a, pool)
        for b in range(0, len(wp), 400):
            if (a["cand_id"], str(b // 400)) not in done:
                jobs.append((a, b // 400, wp[b:b + 400]))
    print(len(alist), "announcements,", len(jobs), "batches to screen", flush=True)
    def one(job):
        a, bi, ps = job
        p = ("Below is an official ANNOUNCEMENT and a numbered list of news URL slugs (Azerbaijani, transliterated to ASCII) from the same week.\n"
             "List the numbers of ALL slugs that could POSSIBLY be a report about this same decision/announcement (its figures, its measure, "
             "its programme, or the issuer's statement on it). Be inclusive: when in doubt, include. Ignore reports clearly about other matters.\n"
             'Return ONLY JSON: {"possible": [numbers]}\n\n'
             f"ANNOUNCEMENT ({a['date']}): {a['title']}\n{re.sub(r'\s+', ' ', a['text'])[:1200]}\n\nSLUGS:\n" +
             "\n".join(f"{k}: {p['slug_text']}" for k, p in enumerate(ps)))
        j = ln.jparse(api(p, SCREEN_MODEL)) or {}
        ok = isinstance(j, dict) and "possible" in j
        poss = set(j.get("possible", [])) if ok else set()
        return [{"ann_id": a["cand_id"], "batch": bi, "outlet": p["outlet"], "url": p["url"], "date": p["date"] or p.get("est_date", ""),
                 "slug_text": p["slug_text"], "possible": int(k in poss), "parse_ok": int(ok)} for k, p in enumerate(ps)]
    new = not os.path.exists(out)
    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ann_id", "batch", "outlet", "url", "date", "slug_text", "possible", "parse_ok"])
        if new:
            w.writeheader()
        with cf.ThreadPoolExecutor(6) as ex:
            for res in ex.map(one, jobs):
                if res and res[0]["parse_ok"]:
                    w.writerows(res); fh.flush()
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    print("screened", len(rows), "possible", sum(int(r["possible"]) for r in rows), "announcements", len({r["ann_id"] for r in rows}))


def validate():
    """Haiku screen vs the Sonnet audit screen on the 10 audit announcements, and coverage of every verified report."""
    S = ra.pick()
    open("sampling/relink_validate.csv", "w").write("")
    w = csv.DictWriter(open("sampling/relink_validate.csv", "w", newline="", encoding="utf-8"), fieldnames=list(S[0].keys())); w.writeheader(); w.writerows(S)
    screen(S, "validate")
    h = {(r["ann_id"], r["url"]) for r in csv.DictReader(open("data/full_screen_validate.csv", encoding="utf-8")) if r["possible"] == "1"}
    s = {(r["ann_id"], r["url"]) for r in csv.DictReader(open("data/recall_screen.csv", encoding="utf-8")) if r["possible"] == "1"}
    ver = {(r["ann_id"], r["url"]) for r in csv.DictReader(open("data/link_verified_claude_recall.csv", encoding="utf-8")) if r["verdict"] == "same_decision"}
    known = {(r["ann_id"], r["url"]) for r in csv.DictReader(open("sampling/reports_verified_drawn.csv", encoding="utf-8")) if r["outlet"] in ra.OUTLETS}
    target = (ver | known) & {(a, u) for a, u in ver | known if a in {x["cand_id"] for x in S}}
    print(f"Haiku possible {len(h)}, Sonnet possible {len(s)}, overlap {len(h & s)}")
    print(f"verified reports (audit + keyword) {len(target)}; caught by Haiku screen {len(target & h)}; missed {sorted(target - h)}")


def cands(suf):
    rows = [r for r in csv.DictReader(open(f"data/full_screen_{suf}.csv", encoding="utf-8")) if r["possible"] == "1"]
    out = [{"ann_id": r["ann_id"], "outlet": r["outlet"], "url": r["url"], "pool_date": r["date"] if r["outlet"] in ("Report", "Oxu.az") else "",
            "hits": "", "found_by": "full_screen"} for r in rows]
    w = csv.DictWriter(open(f"data/link_candidates_{suf}.csv", "w", newline="", encoding="utf-8"), fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print(len(out), "candidates")


if __name__ == "__main__":
    step = sys.argv[1]
    if step == "validate":
        validate(); sys.exit()
    alist, suf = ln.anns(sys.argv[2]), sys.argv[3]
    ln.SUF = suf
    if step == "screen":
        screen(alist, suf)
    elif step == "fetch":
        cands(suf); ln.fetch(alist)
    elif step == "verify":
        if not os.environ.get("RELINK_CLI"):  # API route; with RELINK_CLI, link_news.claude (CLI, Sonnet) is used unchanged
            ln.claude = lambda p, model="sonnet", timeout=900: api(p, VERIFY_MODEL, 16000)
        ln.verify(alist, "claude")
    elif step == "verify_codex":
        ln.verify(alist, "codex")
