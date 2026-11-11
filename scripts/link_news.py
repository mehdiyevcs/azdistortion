"""Link news reports to announcements (prereg section 2, "Linking and verification").

Steps (cached and resumable; <set> is the announcement list's file name without "link_set_" and ".csv"):
  keys         : Claude writes URL-slug keywords (ASCII, lowercase) and 2 search phrases per announcement -> data/link_keys.json
  cands        : pool entries (data/news_pool.csv) in the window [d-1, d+7] (estimated dates with a 2-day margin; undated
                 entries at any date) with at least 2 keyword hits in the URL slug, at most 8 per outlet, plus Banker.az
                 WordPress full-text search in the window -> data/link_candidates_<set>.csv
  fetch        : fetch each candidate page (cache data/news_cache/), extract title, date and text, flag pages outside the
                 window -> data/link_fetched_<set>.csv
  verify       : Claude (claude -p, Sonnet) decides same_decision / same_topic_only / unrelated for every in-window
                 candidate with more than 200 characters of text -> data/link_verified_claude_<set>.csv
  verify_codex : the Codex command-line agent does the same for a seeded 20% -> data/link_verified_codex_<set>.csv
Usage: python3 -P -E scripts/link_news.py keys|cands|fetch|verify|verify_codex <link_set_X.csv>
"""
import tempfile
import csv, datetime as dt, hashlib, json, os, re, subprocess, sys, time, urllib.parse, urllib.request, unicodedata
csv.field_size_limit(10**9)
import concurrent.futures as cf
import trafilatura

UA = {"User-Agent": "Mozilla/5.0 (research crawler; academic study of news accuracy)"}
LIGHT = ["--strict-mcp-config", "--setting-sources", "project", "--no-session-persistence", "--tools", ""]
NCACHE = "data/news_cache"


def asciify(s):
    s = urllib.parse.unquote(s).lower().replace("ə", "e").replace("ı", "i")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def claude(p, model="sonnet", timeout=900):
    return subprocess.run(["claude", "-p", "--model", model, *LIGHT], input=p, capture_output=True, text=True, timeout=timeout, cwd=tempfile.gettempdir()).stdout


def jparse(out):
    m = re.search(r"[\[{].*[\]}]", out, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def anns(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def keys(alist):
    f = "data/link_keys.json"; K = json.load(open(f)) if os.path.exists(f) else {}
    todo = [a for a in alist if a["cand_id"] not in K]
    def one(batch):
        p = ("For each official announcement below, give search keys to find news reports about the SAME decision.\n"
             "slug_keys: 4-8 lowercase ASCII word stems as they would appear in an Azerbaijani news URL slug (ə->e, ı->i, ö->o, ü->u, ğ->g, ş->s, ç->c), "
             "specific to this decision (not generic words like 'bank', 'merkezi', 'vergi', 'nazirlik'); use stems of 5-8 letters.\n"
             "phrases: 2 short Azerbaijani search phrases (2-3 words, with Azerbaijani letters).\n"
             'Return ONLY JSON: {"<cand_id>": {"slug_keys": [...], "phrases": [...]}, ...}\n\n' +
             "\n\n".join(f"cand_id: {a['cand_id']}\nTITLE: {a['title']}\nTEXT: {re.sub(r'\s+', ' ', a['text'])[:700]}" for a in batch))
        return jparse(claude(p)) or {}
    batches = [todo[i:i + 15] for i in range(0, len(todo), 15)]
    with cf.ThreadPoolExecutor(4) as ex:
        for r in ex.map(one, batches):
            K.update(r); json.dump(K, open(f, "w"), ensure_ascii=False, indent=1)
    print("keys for", len(K))


def cands(alist):
    K = json.load(open("data/link_keys.json"))
    pool = list(csv.DictReader(open("data/news_pool.csv", encoding="utf-8")))
    rows = []
    for a in alist:
        k = K.get(a["cand_id"])
        if not k:
            continue
        d0 = dt.date.fromisoformat(a["date"]); lo, hi = d0 - dt.timedelta(days=1), d0 + dt.timedelta(days=7)
        stems = [s.lower() for s in k["slug_keys"] if len(s) >= 4]
        scored = []
        for p in pool:
            if p["date"] or p.get("est_date"):
                try:
                    pd = dt.date.fromisoformat(p["date"] or p["est_date"])
                except ValueError:
                    continue
                m = 0 if p["date"] else 2  # estimated dates (from URL ids) get a 2-day margin
                if not (lo - dt.timedelta(days=m)) <= pd <= (hi + dt.timedelta(days=m)):
                    continue
            hits = sum(1 for s in stems if s in p["slug_text"])
            if hits >= 2:
                scored.append((hits, p))
        scored.sort(key=lambda x: -x[0])
        per = {}
        for h, p in scored:
            if per.get(p["outlet"], 0) < 8:
                per[p["outlet"]] = per.get(p["outlet"], 0) + 1
                rows.append({"ann_id": a["cand_id"], "outlet": p["outlet"], "url": p["url"], "pool_date": p["date"], "hits": h, "found_by": "sitemap_slug"})
        for q in k["phrases"][:2]:  # Banker.az WordPress full-text search
            u = ("https://banker.az/wp-json/wp/v2/posts?per_page=20&_fields=date,link&search=" + urllib.parse.quote(q) +
                 f"&after={lo.isoformat()}T00:00:00&before={(hi + dt.timedelta(days=1)).isoformat()}T00:00:00")
            try:
                res = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40))
            except Exception:
                res = []
            for x in res:
                rows.append({"ann_id": a["cand_id"], "outlet": "Banker.az", "url": x["link"], "pool_date": x["date"][:10], "hits": "", "found_by": "wp_search"})
            time.sleep(0.6)
    seen, out = set(), []
    for r in rows:
        if (r["ann_id"], r["url"]) not in seen:
            seen.add((r["ann_id"], r["url"])); out.append(r)
    w = csv.DictWriter(open(f"data/link_candidates_{SUF}.csv", "w", newline="", encoding="utf-8"), fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    from collections import Counter
    print(len(out), "candidates;", Counter(r["outlet"] for r in out))


def get_page(url):
    os.makedirs(NCACHE, exist_ok=True)
    f = os.path.join(NCACHE, hashlib.md5(url.encode()).hexdigest() + ".html")
    if os.path.exists(f):
        return open(f, encoding="utf-8").read()
    for k in range(3):
        try:
            s = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")
            open(f, "w", encoding="utf-8").write(s); time.sleep(0.8); return s
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return ""
            time.sleep(4 * (k + 1))
        except Exception:
            time.sleep(4 * (k + 1))
    return ""


def fetch(alist):
    A = {a["cand_id"]: a for a in alist}
    rows = list(csv.DictReader(open(f"data/link_candidates_{SUF}.csv", encoding="utf-8")))
    def one(r):
        s = get_page(r["url"])
        md = trafilatura.extract_metadata(s) if s else None
        text = (trafilatura.extract(s, include_tables=True) or "") if s else ""
        date = (md.date if md and md.date else r["pool_date"]) or ""
        d0 = dt.date.fromisoformat(A[r["ann_id"]]["date"])
        try:
            dd = dt.date.fromisoformat(date[:10]); inw = (d0 - dt.timedelta(days=1)) <= dd <= (d0 + dt.timedelta(days=7))
        except ValueError:
            inw = None
        return {**r, "title": (md.title if md and md.title else "").strip()[:250], "pub_date": date[:10], "in_window": inw, "n_chars": len(text)}
    with cf.ThreadPoolExecutor(3) as ex:
        out = list(ex.map(one, rows))
    w = csv.DictWriter(open(f"data/link_fetched_{SUF}.csv", "w", newline="", encoding="utf-8"), fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    from collections import Counter
    print(len(out), Counter(str(r["in_window"]) for r in out))


def page_text(url):
    s = get_page(url)
    return (trafilatura.extract(s, include_tables=True) or "") if s else ""


def verify(alist, who="claude", frac=1.0):
    """Verify candidates in one batch per announcement; who=codex verifies a seeded random 20% (prereg)."""
    import random
    A = {a["cand_id"]: a for a in alist}
    rows = [r for r in csv.DictReader(open(f"data/link_fetched_{SUF}.csv", encoding="utf-8")) if r["in_window"] == "True" and int(r["n_chars"] or 0) > 200]
    if who == "codex":
        rng = random.Random(20261114); rows = [r for r in rows if rng.random() < 0.2]
    f = f"data/link_verified_{who}_{SUF}.csv"
    done = {(r["ann_id"], r["url"]) for r in csv.DictReader(open(f, encoding="utf-8"))} if os.path.exists(f) else set()
    groups = {}
    for r in rows:
        if (r["ann_id"], r["url"]) not in done:
            groups.setdefault(r["ann_id"], []).append(r)
    def one(item):
        aid, rs = item; a = A[aid]
        items = "\n\n".join(f"### report_id: R{k}\nOUTLET: {r['outlet']} DATE: {r['pub_date']}\nTITLE: {r['title']}\nTEXT: {re.sub(r'\s+', ' ', page_text(r['url']))[:1200]}" for k, r in enumerate(rs))
        p = ("For each NEWS REPORT decide whether it is about the SAME official decision/announcement as the ANNOUNCEMENT (not just the same topic or another decision of the same body).\n"
             "verdict: same_decision, same_topic_only, or unrelated. reason: max 12 words.\n"
             'Return ONLY a JSON list: [{"report_id": "R0", "verdict": "...", "reason": "..."}, ...] covering every report.\n\n'
             f"ANNOUNCEMENT ({a['date']}): {a['title']}\n{re.sub(r'\s+', ' ', a['text'])[:1800]}\n\n{items}")
        if who == "claude":
            out = claude(p)
        else:
            of = os.path.abspath(f"data/codex_tmp_{aid}.txt")
            subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", of, "-"], input=p, capture_output=True, text=True, timeout=1200, cwd=tempfile.gettempdir())
            out = open(of, encoding="utf-8").read() if os.path.exists(of) else ""
            if os.path.exists(of):
                os.remove(of)
        j = jparse(out) or []
        J = {d.get("report_id"): d for d in j} if isinstance(j, list) else {}
        return [{"ann_id": aid, "outlet": r["outlet"], "url": r["url"], "pub_date": r["pub_date"], "title": r["title"],
                 "verdict": J.get(f"R{k}", {}).get("verdict", "MISSING"), "reason": J.get(f"R{k}", {}).get("reason", "")} for k, r in enumerate(rs)]
    new = not os.path.exists(f)
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ann_id", "outlet", "url", "pub_date", "title", "verdict", "reason"])
        if new:
            w.writeheader()
        with cf.ThreadPoolExecutor(4 if who == "claude" else 3) as ex:
            for res in ex.map(one, groups.items()):
                w.writerows(res); fh.flush()
    print("verified", sum(len(v) for v in groups.values()), "in", len(groups), "groups")


if __name__ == "__main__":
    step, alist = sys.argv[1], anns(sys.argv[2])
    SUF = os.path.basename(sys.argv[2]).replace("link_set_", "").replace(".csv", "")
    {"keys": keys, "cands": cands, "fetch": fetch, "verify": verify}[step](alist) if step != "verify_codex" else verify(alist, "codex")
