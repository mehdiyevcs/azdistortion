"""Build the final random-sample report list (D10 (c) and its addendum).

Merges all verified reports of the final draw (sampling/drawn_final.csv) from every outlet, then keeps at most 4 per
announcement. Verified = Claude says same_decision, unless Codex checked the pair and disagreed; then the human annotator
(R1) decides (sheets in R1_FILES); pairs without a decision are pending and stay out of the pool.
Sources: full-window relink (Report, Oxu.az, Qafqazinfo, Musavat), earlier keyword links (sampling/reports_main_v1.csv,
includes Banker.az), the later keyword/Banker.az links (new4), APA/AZERTAC (browser, D4) and Trend.
Cap: each report gets the key sha256("20261120|" + url); per announcement the 4 smallest keys are kept, so adding or
removing one report (an R1 decision) changes only that report's own membership. Weight of a kept report =
n_verified(announcement) / n_kept(announcement).
Report ids: ids already given (R0001-R0135 in the first list) are kept for the same url and announcement; new reports get
the next free ids in sorted order.
Optional rule file sampling/link_rules.json, e.g. {"exclude_urls": [...]} for reports R1 rules out.
Usage: python3 scripts/final_reports.py -> sampling/reports_final.csv, sampling/reports_pool.csv, sampling/link_pending_R1.csv
"""
import csv, hashlib, json, os, collections
csv.field_size_limit(10**9)
R = lambda f: list(csv.DictReader(open(f, encoding="utf-8-sig"))) if os.path.exists(f) else []
drawn = {r["cand_id"] for r in R("sampling/drawn_final.csv")}
R1_FILES = ["annotation/R1/screening/Result/R1_link_check_sheet.csv", "annotation/R1/stop1/R1_link_checks.csv"]
r1 = {}
for f in R1_FILES:
    for r in R(f):
        u = r.get("report_url") or r.get("url"); d = (r.get("decision") or "").strip()
        if u and d:
            r1[(r["ann_id"], u)] = "same_decision" if d in ("same", "same_decision") else "not_same"
rules = json.load(open("sampling/link_rules.json")) if os.path.exists("sampling/link_rules.json") else {}
excl = set(rules.get("exclude_urls", []))


def verified(claude_f, codex_f, source):
    cx = {(r["ann_id"], r["url"]): r["verdict"] for r in R(codex_f)}
    out, pend = [], []
    for r in R(claude_f):
        if r["ann_id"] not in drawn:
            continue
        k = (r["ann_id"], r["url"]); cl = r["verdict"] == "same_decision"; co = cx.get(k)
        if co and co != "MISSING" and (co == "same_decision") != cl:
            d = r1.get(k)
            if d is None:
                pend.append({**r, "source": source, "claude": r["verdict"], "codex": co}); continue
            ok = d == "same_decision"
        else:
            ok = cl
        if ok:
            out.append({"ann_id": r["ann_id"], "outlet": r["outlet"], "url": r["url"], "pub_date": r.get("pub_date", ""), "title": r.get("title", ""), "source": source})
    return out, pend


pool, pending = [], []
for cf_, xf, src in [("data/link_verified_claude_relink.csv", "data/link_verified_codex_relink.csv", "relink"),
                     ("data/link_verified_claude_new4.csv", "data/link_verified_codex_new4.csv", "keyword_new4"),
                     ("data/link_verified_claude_browser.csv", "data/link_verified_codex_browser.csv", "browser"),
                     ("data/link_verified_claude_trend.csv", "data/link_verified_codex_trend.csv", "trend")]:
    o, p = verified(cf_, xf, src); pool += o; pending += p
old = {(r["ann_id"], r["url"]): r for r in R("sampling/reports_main_v1.csv")}  # the frozen first report list (reports_main.csv is rewritten later)
relink_seen = {(r["ann_id"], r["url"]) for r in R("data/link_verified_claude_relink.csv")}
relink_ok = {(r["ann_id"], r["url"]) for r in pool if r["source"] == "relink"}
pend_keys = {(r["ann_id"], r["url"]) for r in pending}
for (a, u), r in old.items():  # earlier verified keyword links (incl. Banker.az) of announcements still drawn
    if a not in drawn:
        continue
    if (a, u) in relink_seen and (a, u) not in relink_ok:  # the newer full-window verification of the same page wins
        continue
    if (a, u) in pend_keys:
        continue
    pool.append({"ann_id": a, "outlet": r["outlet"], "url": u, "pub_date": r["pub_date"], "title": r["title"], "source": "keyword"})
seen, P = set(), []
for r in pool:
    k = (r["ann_id"], r["url"])
    if k in seen or r["url"] in excl:
        continue
    seen.add(k); r["key"] = hashlib.sha256(("20261120|" + r["url"]).encode()).hexdigest(); P.append(r)
by = collections.defaultdict(list)
for r in P:
    by[r["ann_id"]].append(r)
kept = []
for a, rs in by.items():
    rs.sort(key=lambda r: r["key"]); n = len(rs); k = rs[:4]
    for r in k:
        r["n_verified"] = n; r["n_kept"] = len(k); r["weight"] = round(n / len(k), 6)
    kept += k
ids = {(a, u): r["report_id"] for (a, u), r in old.items()}
ids.update({(r["ann_id"], r["url"]): r["report_id"] for r in R("sampling/reports_final.csv")})  # keep ids already given
nxt = max(int(i[1:]) for i in ids.values()) + 1 if ids else 1
for r in sorted(kept, key=lambda r: (r["ann_id"], r["outlet"], r["url"])):
    k = (r["ann_id"], r["url"])
    if k in ids:
        r["report_id"] = ids[k]
    else:
        r["report_id"] = f"R{nxt:04d}"; nxt += 1
    r["sample"] = "random"
fn = ["report_id", "ann_id", "outlet", "url", "pub_date", "title", "source", "n_verified", "n_kept", "weight", "sample", "key"]
w = csv.DictWriter(open("sampling/reports_final.csv", "w", newline="", encoding="utf-8"), fieldnames=fn); w.writeheader()
w.writerows(sorted(({k: r.get(k, "") for k in fn} for r in kept), key=lambda r: r["report_id"]))
w = csv.DictWriter(open("sampling/reports_pool.csv", "w", newline="", encoding="utf-8"), fieldnames=["ann_id", "outlet", "url", "source", "key"]); w.writeheader()
w.writerows({k: r[k] for k in ("ann_id", "outlet", "url", "source", "key")} for r in P)
w = csv.DictWriter(open("sampling/link_pending_R1.csv", "w", newline="", encoding="utf-8"), fieldnames=["ann_id", "outlet", "url", "title", "source", "claude", "codex"]); w.writeheader()
w.writerows({k: r.get(k, "") for k in ("ann_id", "outlet", "url", "title", "source", "claude", "codex")} for r in pending)
print("pool", len(P), "reports for", len(by), "announcements; kept", len(kept), "; pending R1", len(pending),
      "; outlets kept", dict(collections.Counter(r["outlet"] for r in kept)), "; announcements without a report:", sorted(drawn - set(by)))
