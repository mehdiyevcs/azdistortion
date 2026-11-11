"""Link Trend (az.trend.az, Azerbaijani only) reports to the drawn announcements (prereg.md section 2, "Linking and verification").

Trend's site search ignores the query and its URLs are numeric, so slug matching is impossible. Instead:
  crawl  : monthly archive sitemaps (https://az.trend.az/sitemap_az.xml -> sitemaps/sitemap_archive_az_YYYY_MM.xml, cached in
           data/sitemaps_cache); keep URLs in categories business/*, azerbaijan/society, azerbaijan/gundem whose lastmod date
           falls in the union of the drawn windows [d-1, d+7]; fetch each page once (link_news.get_page, cache
           data/news_cache) and index title, date and text length -> data/trend_index.csv
  cands  : per announcement, pages in its window whose asciified title+text has >= 2 slug_key stem hits or a phrase hit
           (keys from data/link_keys.json, read only) -> data/link_candidates_trend.csv and data/link_fetched_trend.csv
           (same columns as the link_news fetch step)
  verify_chunked / verify_codex_chunked : as link_news.verify (same filter, prompt and seeded Codex 20%), but reports are
           sent in chunks of <= 25 per announcement. These steps produced the Trend links used in the study; the unchunked
           steps verify / verify_codex are kept but were not used.
Usage: python3 scripts/link_trend.py crawl|cands|verify_chunked|verify_codex_chunked sampling/drawn_60.csv
"""
import tempfile
import csv, datetime as dt, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trafilatura
import link_news as ln
import news_pool as npl

CATS = ("business", "azerbaijan/society", "azerbaijan/gundem")
IDX = "data/trend_index.csv"


def windows(alist):
    W = {}
    for a in alist:
        d0 = dt.date.fromisoformat(a["date"]); W[a["cand_id"]] = (d0 - dt.timedelta(days=1), d0 + dt.timedelta(days=7))
    return W


def sitemap_urls(W):
    days = {lo + dt.timedelta(days=k) for lo, hi in W.values() for k in range((hi - lo).days + 1)}
    months = sorted({(d.year, d.month) for d in days})
    out = []
    for y, m in months:
        xml = npl.get(f"https://az.trend.az/sitemaps/sitemap_archive_az_{y}_{m:02d}.xml")
        for u, lm in npl.entries(xml):
            cat = re.sub(r"^https://az\.trend\.az/|/\d+\.html$", "", u)
            if not cat.startswith(CATS) or not lm:
                continue
            if dt.date.fromisoformat(lm[:10]) in days:
                out.append((u, cat, lm[:10]))
    seen, res = set(), []
    for r in sorted(out, key=lambda x: x[2]):
        if r[0] not in seen:
            seen.add(r[0]); res.append(r)
    return res


def crawl(alist):
    urls = sitemap_urls(windows(alist))
    done = {r["url"] for r in csv.DictReader(open(IDX, encoding="utf-8"))} if os.path.exists(IDX) else set()
    print(len(urls), "urls in windows;", len(done), "already indexed", flush=True)
    new = not os.path.exists(IDX)
    with open(IDX, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["url", "cat", "lastmod", "title", "pub_date", "n_chars"])
        if new:
            w.writeheader()
        for i, (u, cat, lm) in enumerate(urls):
            if u in done:
                continue
            s = ln.get_page(u)
            if not s:  # failed or 404: not indexed, retried on the next run
                print("FAIL", u, flush=True); continue
            md = trafilatura.extract_metadata(s) if s else None
            text = (trafilatura.extract(s, include_tables=True) or "") if s else ""
            w.writerow({"url": u, "cat": cat, "lastmod": lm, "title": (md.title if md and md.title else "").strip()[:250],
                        "pub_date": ((md.date if md and md.date else "") or "")[:10], "n_chars": len(text)}); fh.flush()
            if i % 200 == 0:
                print(i, lm, time.strftime("%H:%M:%S"), flush=True)
    print("crawl done")


def asc_text(u):
    return ln.asciify(ln.page_text(u))


def cands(alist):
    import json
    K = json.load(open("data/link_keys.json"))
    W = windows(alist)
    idx = list(csv.DictReader(open(IDX, encoding="utf-8")))
    import concurrent.futures as cf  # extract each cached page once, in parallel (reads the cache only, no requests)
    with cf.ProcessPoolExecutor(8) as ex:
        TXT = dict(zip([r["url"] for r in idx], ex.map(asc_text, [r["url"] for r in idx], chunksize=50)))
    cand, fetched = [], []
    for a in alist:
        k = K.get(a["cand_id"])
        if not k:
            print("no keys", a["cand_id"]); continue
        lo, hi = W[a["cand_id"]]
        stems = [s.lower() for s in k["slug_keys"] if len(s) >= 4]
        phr = [ln.asciify(q) for q in k["phrases"][:2]]
        for r in idx:
            if not lo <= dt.date.fromisoformat(r["lastmod"]) <= hi or not r["title"]:
                continue
            t = ln.asciify(r["title"]) + " " + TXT[r["url"]]
            hits = sum(1 for s in stems if s in t)
            ph = sum(1 for q in phr if q and q in t)
            if hits >= 2 or ph:
                base = {"ann_id": a["cand_id"], "outlet": "Trend", "url": r["url"], "pool_date": r["lastmod"], "hits": hits,
                        "found_by": "sitemap_text" + ("+phrase" if ph else "")}
                cand.append(base)
                try:
                    dd = dt.date.fromisoformat((r["pub_date"] or r["lastmod"])[:10]); inw = lo <= dd <= hi
                except ValueError:
                    inw = None
                fetched.append({**base, "title": r["title"], "pub_date": (r["pub_date"] or r["lastmod"])[:10], "in_window": inw, "n_chars": r["n_chars"]})
    for f, rows in (("data/link_candidates_trend.csv", cand), ("data/link_fetched_trend.csv", fetched)):
        w = csv.DictWriter(open(f, "w", newline="", encoding="utf-8"), fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(len(cand), "candidates for", len({r["ann_id"] for r in cand}), "announcements;", Counter(str(r["in_window"]) for r in fetched))


if __name__ == "__main__" and "chunked" not in sys.argv[1]:
    step, alist = sys.argv[1], ln.anns(sys.argv[2])
    ln.SUF = "trend"
    {"crawl": crawl, "cands": cands, "verify": lambda a: ln.verify(a), "verify_codex": lambda a: ln.verify(a, "codex")}[step](alist)


def verify_chunked(alist, who="claude", size=25):
    """Run link_news.verify with the same row filter, Codex 20% draw (random.Random(20261114) over the same rows in the same
    order) and the same prompt, but send each announcement's reports in chunks of at most `size` (text matching gives up to
    about 400 candidates per announcement, too long for one prompt)."""
    import random, subprocess, concurrent.futures as cf
    A = {a["cand_id"]: a for a in alist}
    rows = [r for r in csv.DictReader(open("data/link_fetched_trend.csv", encoding="utf-8")) if r["in_window"] == "True" and int(r["n_chars"] or 0) > 200]
    if who == "codex":
        rng = random.Random(20261114); rows = [r for r in rows if rng.random() < 0.2]
    f = f"data/link_verified_{who}_trend.csv"
    done = {(r["ann_id"], r["url"]) for r in csv.DictReader(open(f, encoding="utf-8"))} if os.path.exists(f) else set()
    groups = {}
    for r in rows:
        if (r["ann_id"], r["url"]) not in done:
            groups.setdefault(r["ann_id"], []).append(r)
    jobs = [(aid, k, rs[i:i + size]) for aid, rs in groups.items() for k, i in enumerate(range(0, len(rs), size))]
    def one(job):
        aid, ci, rs = job; a = A[aid]
        items = "\n\n".join(f"### report_id: R{k}\nOUTLET: {r['outlet']} DATE: {r['pub_date']}\nTITLE: {r['title']}\nTEXT: {re.sub(r'\s+', ' ', ln.page_text(r['url']))[:1200]}" for k, r in enumerate(rs))
        p = ("For each NEWS REPORT decide whether it is about the SAME official decision/announcement as the ANNOUNCEMENT (not just the same topic or another decision of the same body).\n"
             "verdict: same_decision, same_topic_only, or unrelated. reason: max 12 words.\n"
             'Return ONLY a JSON list: [{"report_id": "R0", "verdict": "...", "reason": "..."}, ...] covering every report.\n\n'
             f"ANNOUNCEMENT ({a['date']}): {a['title']}\n{re.sub(r'\s+', ' ', a['text'])[:1800]}\n\n{items}")
        if who == "claude":
            out = ln.claude(p)
        else:
            of = os.path.abspath(f"data/codex_tmp_trend_{aid}_{ci}.txt")
            subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", of, "-"], input=p, capture_output=True, text=True, timeout=1200, cwd=tempfile.gettempdir())
            out = open(of, encoding="utf-8").read() if os.path.exists(of) else ""
            if os.path.exists(of):
                os.remove(of)
        j = ln.jparse(out) or []
        J = {d.get("report_id"): d for d in j} if isinstance(j, list) else {}
        return [{"ann_id": aid, "outlet": r["outlet"], "url": r["url"], "pub_date": r["pub_date"], "title": r["title"],
                 "verdict": J.get(f"R{k}", {}).get("verdict", "MISSING"), "reason": J.get(f"R{k}", {}).get("reason", "")} for k, r in enumerate(rs)]
    new = not os.path.exists(f)
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ann_id", "outlet", "url", "pub_date", "title", "verdict", "reason"])
        if new:
            w.writeheader()
        with cf.ThreadPoolExecutor(4 if who == "claude" else 3) as ex:
            for res in ex.map(one, jobs):
                w.writerows([x for x in res if x["verdict"] != "MISSING"]); fh.flush()  # MISSING rows are retried on the next run
    print("verified", sum(len(v) for v in groups.values()), "in", len(jobs), "chunks")


if __name__ == "__main__" and sys.argv[1] in ("verify_chunked", "verify_codex_chunked"):
    verify_chunked(ln.anns(sys.argv[2]), "codex" if "codex" in sys.argv[1] else "claude")
