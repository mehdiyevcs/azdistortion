"""Select the web reports of the benchmark add-on (prereg.md section 2 "Random sample vs benchmark add-on", D8).

The pool is verified news reports of eligible announcements that are not in the random-sample draw and not dev items.
Run from the repository root.
Usage:
  python scripts/bench_select.py pool      -> data/bench_pool.csv (pool, headline overlap, cues, near-duplicate clusters)
  python scripts/bench_select.py explain   -> data/bench_explainer.csv (Claude screen of cue hits; raw output in logs/benchmark_explainer_raw.txt)
  python scripts/bench_select.py select [web_target] -> data/bench_selected_web.csv (first selection rule)
  python scripts/bench_select.py select2   -> data/bench_selected_web.csv, data/bench_web_leftover.csv (final D8 rule)
"""
import csv, json, os, random, re, sys, unicodedata
csv.field_size_limit(10**9)
sys.path.insert(0, "scripts")
from link_news import get_page, claude, jparse  # noqa: E402
import trafilatura  # noqa: E402

SEED = 20261118
DEV = {"CBAR-5573", "CBAR-5417", "CBAR-5463", "CBAR-5459", "CBAR-5569", "DVX-4939", "DVX-4940", "DVX-4966", "DVX-5048",
       "EMSMN-9192", "EMSMN-9975", "EMSMN-9920", "EMSMN-10013"}
SUF = {"cbar": "cbar", "tax": "tax_w", "social": "social_w"}
STOP = {"və", "ilə", "üçün", "olan", "olub", "edib", "edilib", "edilir", "olunub", "olunur", "daha", "artıq", "bütün", "haqqında", "barədə", "üzrə"}
CUES = ["nə dəyiş", "nələr dəyiş", "kimlər", "kimə aid", "kimlərə aid", "nə deməkdir", "yəni", "necə", "nələr", "bəs ", "izah", "sual",
        "nəzərə alın", "bilməli"]


def low(s):
    s = unicodedata.normalize("NFC", s).replace("I", "ı").replace("İ", "i")
    return s.lower()


def stems(s):
    w = re.sub(r"[^\w\s]", " ", low(s)).split()
    return {x[:5] for x in w if len(x) >= 3 and x not in STOP}


def overlap(h, t):
    H = stems(h)
    return round(len(H & stems(t)) / len(H), 3) if H else 0.0


def grams(t, n=5):
    """Word 5-grams normalised exactly as scripts/copy_ratio.py (NFC, str.lower, punctuation removed)."""
    w = re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", t).lower()).split()
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def text_of(url):
    s = get_page(url)
    return (trafilatura.extract(s, include_tables=True) or "") if s else ""


def _pool_suffix(iss, suf, drawn, main_urls, rows, log, keep):
    elig = {r["cand_id"] for r in csv.DictReader(open(f"sampling/eligibility_final_{iss}.csv", encoding="utf-8")) if r["final"] == "eligible"}
    T = {r["cand_id"]: r for r in csv.DictReader(open(f"data/candidates/{iss}.csv", encoding="utf-8"))}
    cx = {(r["ann_id"], r["url"]): r["verdict"] for r in csv.DictReader(open(f"data/link_verified_codex_{suf}.csv", encoding="utf-8"))}
    for r in csv.DictReader(open(f"data/link_verified_claude_{suf}.csv", encoding="utf-8")):
        if r["verdict"] != "same_decision" or not keep(r["ann_id"]):
            continue
        k = (r["ann_id"], r["url"])
        why = ("codex_disagrees" if k in cx and cx[k] != "same_decision" else "not_eligible" if r["ann_id"] not in elig
               else "drawn" if r["ann_id"] in drawn else "dev" if r["ann_id"] in DEV else "in_reports_main" if r["url"] in main_urls else "")
        log[why or "kept"] = log.get(why or "kept", 0) + 1
        if why:
            continue
        rows.append(dict(r, issuer=iss, ann_title=T[r["ann_id"]]["title"], ann_date=T[r["ann_id"]]["date"],
                         verified_by="claude+codex" if k in cx else "claude", link_set=suf))


def pool():
    drawn = {r["cand_id"] for r in csv.DictReader(open("sampling/drawn_60.csv", encoding="utf-8"))}
    for iss in SUF:  # the re-walked draw (D10 (b)) is excluded too
        f = f"sampling/draw2_{iss}.csv"
        if os.path.exists(f):
            drawn |= {r["cand_id"] for r in csv.DictReader(open(f, encoding="utf-8"))}
    main_urls = {r["url"] for r in csv.DictReader(open("sampling/reports_main.csv", encoding="utf-8"))}
    rows, log = [], {}
    PFX = {"CBAR": "cbar", "DVX": "tax", "EMSMN": "social"}
    for iss, suf in list(SUF.items()) + [(None, "benchpool")]:
        if iss is None:  # full-window relink of further eligible non-drawn announcements; issuer from the ann_id prefix
            for iss2 in SUF:
                _pool_suffix(iss2, suf, drawn, main_urls, rows, log, lambda a, i=iss2: PFX[a.split("-")[0]] == i)
            continue
        _pool_suffix(iss, suf, drawn, main_urls, rows, log, lambda a: True)
    # one announcement per URL
    rng = random.Random(SEED)
    by_url = {}
    for r in rows:
        by_url.setdefault(r["url"], []).append(r)
    rows = []
    for u in sorted(by_url):
        rs = sorted(by_url[u], key=lambda r: r["ann_id"])
        if len(rs) > 1:
            log["multi_ann_url"] = log.get("multi_ann_url", 0) + 1
        rows.append(rs[0] if len(rs) == 1 else rng.choice(rs))
    out = []
    for r in rows:
        t = text_of(r["url"])
        if len(t) < 200:
            log["short_text"] = log.get("short_text", 0) + 1
            continue
        head = low(r["title"] + "\n" + t[:1500])
        cues = [c for c in CUES if c in head] + (["?"] if "?" in r["title"] else [])
        out.append(dict(r, n_chars=len(t), overlap=overlap(r["title"], r["ann_title"]), cues="|".join(cues), _t=t))
    # near-duplicate clusters: 5-gram containment of the shorter text >= 0.9 (union-find)
    G = [grams(r["title"] + "\n" + r["_t"]) for r in out]
    par = list(range(len(out)))

    def f(i):
        while par[i] != i:
            i = par[i]
        return i
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            a, b = G[i], G[j]
            if a and b and len(a & b) / min(len(a), len(b)) >= 0.9:
                par[f(i)] = f(j)
    for i, r in enumerate(out):
        r["dup_cluster"] = f(i)
    sizes = {}
    for r in out:
        sizes[r["dup_cluster"]] = sizes.get(r["dup_cluster"], 0) + 1
    log["near_dup_reports_in_clusters>1"] = sum(v for v in sizes.values() if v > 1)
    fields = ["issuer", "ann_id", "ann_date", "ann_title", "outlet", "url", "pub_date", "title", "verified_by", "link_set", "n_chars", "overlap", "cues", "dup_cluster"]
    with open("data/bench_pool.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(out)
    print(json.dumps(log), "pool", len(out))


EXPLAIN_PROMPT = """You classify Azerbaijani news reports about an official decision (central bank, tax service or labour/social ministry).
A report is an EXPLAINER if it explains what the decision means for readers: who is affected, what changes for them, how to apply or comply, what they must do, or worked examples / answers to readers' questions, beyond restating the press release. A report that only restates or summarises the announcement (even with a question headline used as clickbait) is NOT an explainer.
For each report return label "explainer" or "not_explainer" and a reason in English (max 15 words).
Return ONLY a JSON list: [{"id": "...", "label": "...", "reason": "..."}] covering every report."""


def flat(t):
    return re.sub(r"\s+", " ", t)


def explain():
    P = [r for r in csv.DictReader(open("data/bench_pool.csv", encoding="utf-8")) if r["cues"]]
    res, raw = [], []
    for i in range(0, len(P), 10):
        b = P[i:i + 10]
        items = "\n\n".join(f"### id: E{i + k}\nANNOUNCEMENT TITLE: {r['ann_title']}\nREPORT HEADLINE: {r['title']}\nREPORT TEXT: {flat(text_of(r['url']))[:2500]}" for k, r in enumerate(b))
        out = claude(EXPLAIN_PROMPT + "\n\n" + items)
        raw.append(f"=== batch {i // 10}\n{out}")
        J = {d.get("id"): d for d in (jparse(out) or [])}
        for k, r in enumerate(b):
            d = J.get(f"E{i + k}", {})
            res.append({"url": r["url"], "ann_id": r["ann_id"], "label": d.get("label", "MISSING"), "reason": d.get("reason", "")})
    open("logs/benchmark_explainer_raw.txt", "w", encoding="utf-8").write("\n".join(raw))
    with open("data/bench_explainer.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["url", "ann_id", "label", "reason"]); w.writeheader(); w.writerows(res)
    print("screened", len(res), "explainer", sum(r["label"] == "explainer" for r in res))


def select(web_target=65):
    rng = random.Random(SEED)
    P = list(csv.DictReader(open("data/bench_pool.csv", encoding="utf-8")))
    E = {(r["ann_id"], r["url"]): r for r in csv.DictReader(open("data/bench_explainer.csv", encoding="utf-8"))}
    for r in P:
        e = E.get((r["ann_id"], r["url"]))
        r["is_a"] = bool(e and e["label"] == "explainer")
        r["is_b"] = float(r["overlap"]) <= 0.30
        r["bench_type"] = "explainer+headline_diff" if r["is_a"] and r["is_b"] else "explainer" if r["is_a"] else "headline_diff" if r["is_b"] else ""
        r["rank"] = 0 if (r["is_a"] and r["is_b"]) else 1 if r["is_a"] else 2
        r["tie"] = rng.random()
        r["reason"] = "; ".join(x for x in [f"explainer screen: {e['reason']}" if r["is_a"] else "",
                                             f"headline word overlap with issuer title {float(r['overlap']):.2f} <= 0.30" if r["is_b"] else "",
                                             f"cues: {r['cues']}" if r["is_a"] else ""] if x)
    Q = [r for r in P if r["bench_type"]]
    # near-duplicate clusters: keep the top-priority report only
    best = {}
    for r in sorted(Q, key=lambda r: (r["rank"], float(r["overlap"]), r["tie"])):
        best.setdefault(r["dup_cluster"], r)
    Q = list(best.values())
    # per announcement: order by priority with outlet spread, cap 3
    per_ann = {}
    for r in Q:
        per_ann.setdefault(r["ann_id"], []).append(r)
    for a, rs in per_ann.items():
        rs.sort(key=lambda r: (r["rank"], float(r["overlap"]), r["tie"]))
        ordered, used = [], set()
        while rs:
            nxt = next((r for r in rs if r["outlet"] not in used), rs[0])
            ordered.append(nxt); used.add(nxt["outlet"]); rs.remove(nxt)
        per_ann[a] = ordered[:3]
    avail = {iss: [r for a, rs in per_ann.items() for r in rs if r["issuer"] == iss] for iss in SUF}
    quota = {"cbar": 22, "tax": 22, "social": 21}
    scale = web_target / 65
    quota = {k: round(v * scale) for k, v in quota.items()}
    # move the quota an issuer cannot fill to the other issuers
    while True:
        short = sum(max(0, quota[i] - len(avail[i])) for i in quota)
        for i in quota:
            quota[i] = min(quota[i], len(avail[i]))
        open_ = [i for i in quota if len(avail[i]) > quota[i]]
        if not short or not open_:
            break
        for k, i in enumerate(sorted(open_)):
            quota[i] += short // len(open_) + (1 if k < short % len(open_) else 0)
    chosen = []
    for iss in ("cbar", "tax", "social"):
        anns = sorted({r["ann_id"] for r in avail[iss]})
        rng2 = random.Random(f"{SEED}-{iss}"); rng2.shuffle(anns)
        queues = {a: [r for r in per_ann[a]] for a in anns}
        used_out, got = {}, []
        while len(got) < quota[iss] and any(queues.values()):
            for a in anns:
                if len(got) >= quota[iss]:
                    break
                if not queues[a]:
                    continue
                # among this announcement's remaining reports of the best rank, prefer the least-used outlet
                top = min(r["rank"] for r in queues[a])
                cand = [r for r in queues[a] if r["rank"] == top]
                r = min(cand, key=lambda r: (used_out.get(r["outlet"], 0), float(r["overlap"]), r["tie"]))
                queues[a].remove(r); got.append(r); used_out[r["outlet"]] = used_out.get(r["outlet"], 0) + 1
        chosen += got
    fields = ["issuer", "ann_id", "ann_title", "outlet", "url", "pub_date", "title", "verified_by", "overlap", "cues", "bench_type", "reason"]
    with open("data/bench_selected_web.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(chosen)
    from collections import Counter
    print("qualifying after dedup/cap", {i: len(v) for i, v in avail.items()}, "quota", quota, "chosen", len(chosen))
    print(Counter((r["issuer"], r["bench_type"]) for r in chosen)); print(Counter(r["outlet"] for r in chosen))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "pool":
        pool()
    elif cmd == "explain":
        explain()
    elif cmd == "select":
        select(int(sys.argv[2]) if len(sys.argv) > 2 else 65)


# ---------------- Final selection rule (D8): fixed report signals, 50 web reports per issuer ----------------
def t1_text(aid):
    d = f"data/raw/announcements/{aid}"
    if not os.path.exists(f"{d}/meta.json"):
        return None
    meta = json.load(open(f"{d}/meta.json", encoding="utf-8"))
    out = [open(f"{d}/text_{k}.txt", encoding="utf-8").read() for k, f in enumerate(meta["files"])
           if f.get("raw", "").endswith(".html") and os.path.exists(f"{d}/text_{k}.txt")]
    return "\n".join(out) if out else None


def cue_hits(title, text):
    head = low(title + "\n" + text[:1500])
    return [c for c in CUES if c in head] + (["?"] if "?" in title else [])


def signals(r, text, ann_title, aid):
    t1 = t1_text(aid)
    g = grams(r["title"] + "\n" + text)
    crx = len(g & grams(t1)) / len(g) if (t1 and g) else None
    cr = round(crx, 3) if crx is not None else None
    ov = overlap(r["title"], ann_title)
    cues = cue_hits(r["title"], text)
    s = [n for n, ok in (("rewritten", crx is not None and crx < 0.6), ("explainer", bool(cues)), ("headline_diff", ov <= 0.30)) if ok]
    return s, {"copy_ratio": cr, "overlap": ov, "cues": "|".join(cues)}


def select2():
    rng = random.Random(SEED)
    P = list(csv.DictReader(open("data/bench_pool.csv", encoding="utf-8")))
    for r in P:
        s, v = signals(r, text_of(r["url"]), r["ann_title"], r["ann_id"])
        if v["copy_ratio"] is None:
            raise SystemExit(f"no T1 text for {r['ann_id']}")
        r.update(v, sig=s, n_sig=len(s), tie=rng.random())
        r["bench_type"] = "+".join(s) or "none"
    # near-duplicate clusters: keep one report (most signals, ties broken by the seeded draw)
    best = {}
    for r in sorted(P, key=lambda r: (-r["n_sig"], r["tie"])):
        best.setdefault(r["dup_cluster"], r)
    dropped_dup = len(P) - len(best)
    Q = list(best.values())
    per_ann = {}
    for r in Q:
        per_ann.setdefault(r["ann_id"], []).append(r)
    capped = 0
    for a, rs in per_ann.items():
        rs.sort(key=lambda r: (-r["n_sig"], r["tie"]))
        ordered, used = [], set()
        while rs:  # signal count first; outlet spread only within the highest remaining signal count
            top = [r for r in rs if r["n_sig"] == rs[0]["n_sig"]]
            nxt = next((r for r in top if r["outlet"] not in used), top[0])
            ordered.append(nxt); used.add(nxt["outlet"]); rs.remove(nxt)
        capped += max(0, len(ordered) - 3)
        per_ann[a] = ordered[:3]
    avail = {iss: [r for rs in per_ann.values() for r in rs if r["issuer"] == iss] for iss in SUF}
    chosen = []
    for iss in ("cbar", "tax", "social"):
        cand = avail[iss][:]
        got, used = [], {}
        for tier in (lambda n: n >= 2, lambda n: n == 1, lambda n: n == 0):
            pool_t = sorted([r for r in cand if tier(r["n_sig"])], key=lambda r: r["tie"])
            while pool_t and len(got) < 50:
                r = min(pool_t, key=lambda r: (used.get(r["outlet"], 0), r["tie"]))
                pool_t.remove(r); got.append(r); used[r["outlet"]] = used.get(r["outlet"], 0) + 1
        for r in got:
            r["tier"] = "2+" if r["n_sig"] >= 2 else str(r["n_sig"])
        chosen += got
    left = [r for rs in avail.values() for r in rs if r not in chosen]
    fields = ["issuer", "ann_id", "ann_title", "outlet", "url", "pub_date", "title", "verified_by", "copy_ratio", "overlap", "cues",
              "bench_type", "n_sig", "tier", "tie"]
    for name, rows in (("data/bench_selected_web.csv", chosen), ("data/bench_web_leftover.csv", left)):
        with open(name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print("pool", len(P), "dropped near-dup", dropped_dup, "dropped by cap", capped, "web chosen", len(chosen), "leftover", len(left))
    print(Counter(r["issuer"] for r in chosen), Counter(r["tier"] for r in chosen))
    print(Counter(r["bench_type"] for r in chosen)); print(Counter(r["outlet"] for r in chosen))


if __name__ == "__main__" and sys.argv[1] == "select2":
    select2()
