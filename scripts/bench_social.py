"""Select outlet Telegram posts for the benchmark add-on (prereg D8, "outlet social posts").

Posts are found through the public channel preview t.me/s/<channel>?q=<phrase> (no login), with 2 search phrases per
announcement, in the window [d-1, d+7]. Announcements are tried in seeded order, those in data/bench_pool.csv first,
then the other eligible ones that are neither drawn for the random sample nor dev announcements (at most 60).
A post is kept only if both Claude and Codex judge it to be about the same decision; at most 2 posts per
announcement, one per channel, and at most 3 benchmark reports per announcement counting the web reports. target = number of posts wanted for the issuer.
Usage: python3 scripts/bench_social.py <issuer> <target> [--with-leftover]
Outputs: data/bench_social_cands.csv (all window posts found), data/bench_social_verified.csv (Claude and Codex
verdicts), data/bench_selected_social.csv (selected posts); search pages are cached in data/tg_cache/.
"""
import tempfile
import csv, datetime as dt, hashlib, html, json, os, random, re, subprocess, sys, threading, time, urllib.parse, urllib.request
csv.field_size_limit(10**9)
sys.path.insert(0, "scripts")
from link_news import claude, jparse  # noqa: E402
from bench_select import DEV, SEED  # noqa: E402

CH = {"oxuaze": "Oxu.az", "Banker_az": "Banker.az", "reportnewsaz": "Report", "TVmusavat": "Musavat"}
UA = {"User-Agent": "Mozilla/5.0 (AzDistortion research crawler)"}
PER_ANN, MAX_TRIED, MAX_PAGES = 2, 60, 8
CACHE = "data/tg_cache"
_lock = threading.Lock()


def get(url):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".html")
    if os.path.exists(f):
        return open(f, encoding="utf-8").read()
    for k in range(3):
        try:
            with _lock:
                s = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")
                time.sleep(1.0)
            open(f, "w", encoding="utf-8").write(s); return s
        except Exception:
            time.sleep(5 * (k + 1))
    return ""


def parse(s, ch):
    out = []
    for blk in s.split('class="tgme_widget_message_wrap')[1:]:
        m = re.search(r'data-post="([^"]+)"', blk); t = re.search(r'<time datetime="([^"]+)"', blk)
        tx = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        if not (m and t):
            continue
        txt = html.unescape(re.sub(r"<[^>]+>", " ", (tx.group(1) if tx else "").replace("<br/>", "\n")))
        out.append({"post": m.group(1), "dt": t.group(1)[:10], "text": re.sub(r"[ \t]+", " ", txt).strip()})
    return out


def search(ch, phrase, lo, hi):
    found, before = [], None
    for _ in range(MAX_PAGES):
        u = f"https://t.me/s/{ch}?q={urllib.parse.quote(phrase)}" + (f"&before={before}" if before else "")
        ps = parse(get(u), ch)
        if not ps:
            break
        found += [p for p in ps if lo <= p["dt"] <= hi]
        if min(p["dt"] for p in ps) < lo:
            break
        before = min(int(p["post"].split("/")[1]) for p in ps)
    return found


def keys_for(anns):
    K = json.load(open("data/link_keys.json", encoding="utf-8"))
    f = "data/bench_social_keys.json"; B = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    todo = [a for a in anns if a["cand_id"] not in K and a["cand_id"] not in B]
    for i in range(0, len(todo), 15):
        batch = todo[i:i + 15]
        p = ("For each official announcement below, give search keys to find news reports about the SAME decision.\n"
             "slug_keys: 4-8 lowercase ASCII word stems as they would appear in an Azerbaijani news URL slug (ə->e, ı->i, ö->o, ü->u, ğ->g, ş->s, ç->c), "
             "specific to this decision (not generic words like 'bank', 'merkezi', 'vergi', 'nazirlik'); use stems of 5-8 letters.\n"
             "phrases: 2 short Azerbaijani search phrases (2-3 words, with Azerbaijani letters).\n"
             'Return ONLY JSON: {"<cand_id>": {"slug_keys": [...], "phrases": [...]}, ...}\n\n' +
             "\n\n".join(f"cand_id: {a['cand_id']}\nTITLE: {a['title']}\nTEXT: {re.sub(r'\s+', ' ', a['text'])[:700]}" for a in batch))
        B.update(jparse(claude(p)) or {})
        json.dump(B, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {a["cand_id"]: (K.get(a["cand_id"]) or B.get(a["cand_id"]) or {}).get("phrases", [])[:2] for a in anns}


def verify(a, posts, who):
    items = "\n\n".join(f"### report_id: R{k}\nOUTLET: {CH[p['post'].split('/')[0]]} (Telegram post) DATE: {p['dt']}\nTEXT: {re.sub(r'\s+', ' ', p['text'])[:1200]}" for k, p in enumerate(posts))
    pr = ("For each NEWS REPORT decide whether it is about the SAME official decision/announcement as the ANNOUNCEMENT (not just the same topic or another decision of the same body).\n"
          "verdict: same_decision, same_topic_only, or unrelated. reason: max 12 words.\n"
          'Return ONLY a JSON list: [{"report_id": "R0", "verdict": "...", "reason": "..."}, ...] covering every report.\n\n'
          f"ANNOUNCEMENT ({a['date']}): {a['title']}\n{re.sub(r'\s+', ' ', a['text'])[:1800]}\n\n{items}")
    if who == "claude":
        out = claude(pr)
    else:
        of = os.path.abspath(f"data/codex_tmp_bench_{a['cand_id']}.txt")
        subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", of, "-"], input=pr, capture_output=True, text=True, timeout=1200, cwd=tempfile.gettempdir())
        out = open(of, encoding="utf-8").read() if os.path.exists(of) else ""
        if os.path.exists(of):
            os.remove(of)
    J = {d.get("report_id"): d for d in (jparse(out) or []) if isinstance(d, dict)}
    return [J.get(f"R{k}", {"verdict": "MISSING", "reason": ""}) for k in range(len(posts))]


def own_text(t):
    return re.sub(r"https?://\S+", "", t).strip()


VCACHE = "data/bench_social_vcache.json"


def cached_verify(a, posts, who):
    C = json.load(open(VCACHE, encoding="utf-8")) if os.path.exists(VCACHE) else {}
    key = f"{who}|{a['cand_id']}|" + ",".join(p["post"] for p in posts)
    if key not in C:
        C[key] = verify(a, posts, who)
        json.dump(C, open(VCACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return C[key]


def append(name, rows):
    if not rows:
        return
    new = not os.path.exists(name)
    with open(name, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)


def main(iss, target):
    drawn = {r["cand_id"] for r in csv.DictReader(open("sampling/drawn_60.csv", encoding="utf-8"))}
    for i in ("cbar", "tax", "social"):  # the re-walked draw (prereg D10 b) is excluded too
        if os.path.exists(f"sampling/draw2_{i}.csv"):
            drawn |= {r["cand_id"] for r in csv.DictReader(open(f"sampling/draw2_{i}.csv", encoding="utf-8"))}
    web = list(csv.DictReader(open("data/bench_selected_web.csv", encoding="utf-8")))
    if "--with-leftover" in sys.argv:  # shortfall case only: leftover web reports are taken before further posts
        web += list(csv.DictReader(open("data/bench_web_leftover.csv", encoding="utf-8")))
    n_web = {}
    for r in web:
        n_web[r["ann_id"]] = n_web.get(r["ann_id"], 0) + 1
    prev = list(csv.DictReader(open("data/bench_selected_social.csv", encoding="utf-8"))) if os.path.exists("data/bench_selected_social.csv") else []
    prev_iss = [r for r in prev if r["issuer"] == iss]
    done_ann = {r["ann_id"] for r in csv.DictReader(open("data/bench_social_cands.csv", encoding="utf-8"))} if os.path.exists("data/bench_social_cands.csv") else set()
    A = {r["cand_id"]: r for r in csv.DictReader(open(f"data/candidates/{iss}.csv", encoding="utf-8"))}
    elig = sorted(r["cand_id"] for r in csv.DictReader(open(f"sampling/eligibility_final_{iss}.csv", encoding="utf-8"))
                  if r["final"] == "eligible" and r["cand_id"] not in drawn and r["cand_id"] not in DEV)
    first = sorted({r["ann_id"] for r in csv.DictReader(open("data/bench_pool.csv", encoding="utf-8")) if r["issuer"] == iss})
    rng = random.Random(f"{SEED}-social-{iss}"); rng.shuffle(first)
    rest = [c for c in elig if c not in first]; rng.shuffle(rest)
    order = (first + rest)[:MAX_TRIED]
    K = keys_for([A[c] for c in order])
    got = list(prev_iss)
    for c in order:
        if len(got) >= target:
            break
        if c in done_ann:
            continue
        room = min(PER_ANN, 3 - n_web.get(c, 0))
        a = A[c]; d0 = dt.date.fromisoformat(a["date"])
        lo, hi = str(d0 - dt.timedelta(days=1)), str(d0 + dt.timedelta(days=7))
        posts = {}
        if room > 0:
            for ch in CH:
                for ph in K.get(c, []):
                    for p in search(ch, ph, lo, hi):
                        posts[p["post"]] = p
        posts = [p for p in sorted(posts.values(), key=lambda p: p["post"]) if len(own_text(p["text"])) >= 30]
        print(iss, c, "room", room, "window posts", len(posts), flush=True)
        ver, ok = [], []
        if posts:
            vc = cached_verify(a, posts, "claude")
            keep = [(p, v) for p, v in zip(posts, vc) if v.get("verdict") == "same_decision"]
            vx = cached_verify(a, [p for p, _ in keep], "codex") if keep else []
            for p, v in zip(posts, vc):
                x = next((x for (q, _), x in zip(keep, vx) if q["post"] == p["post"]), {})
                ver.append({"ann_id": c, "post": p["post"], "claude": v.get("verdict"), "codex": x.get("verdict", ""),
                            "claude_reason": v.get("reason", ""), "codex_reason": x.get("reason", "")})
                if v.get("verdict") == "same_decision" and x.get("verdict") == "same_decision":
                    ok.append((p, v))
        used = {}
        for r in got:
            used[r["outlet"]] = used.get(r["outlet"], 0) + 1
        rng.shuffle(ok)
        ok.sort(key=lambda pv: used.get(CH[pv[0]["post"].split("/")[0]], 0))
        chans, new = set(), []
        for p, v in ok:
            ch = p["post"].split("/")[0]
            if ch in chans or len(new) >= room or len(got) + len(new) >= target:
                continue
            chans.add(ch)
            new.append({"issuer": iss, "ann_id": c, "ann_title": a["title"], "outlet": CH[ch], "url": f"https://t.me/{p['post']}",
                        "pub_date": p["dt"], "title": own_text(p["text"]).split("\n")[0][:200], "verified_by": "claude+codex",
                        "post_text": p["text"], "reason": f"outlet Telegram post (public preview); Claude: {v.get('reason', '')}"})
        got += new
        append("data/bench_social_cands.csv", [{"ann_id": c, "issuer": iss, "post": p["post"], "date": p["dt"], "text": p["text"]} for p in posts]
               or [{"ann_id": c, "issuer": iss, "post": "", "date": "", "text": ""}])
        append("data/bench_social_verified.csv", ver)
        append("data/bench_selected_social.csv", new)
    print(iss, "selected", len(got), "target", target, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))  # add --with-leftover in the shortfall case
