"""Apply the screening and link decisions of the human annotator (R1), then draw 20 covered eligible announcements per issuer.

Implements prereg section 2 "Draw" with deviation D1:
  - final eligibility: R1's decision for every item R1 saw; otherwise the agreed screener decision.
  - a report is verified if Claude says same_decision, unless Codex checked it and disagreed; then R1's link
    decision counts (same_decision: verified; other decision: not verified; empty: pending).
  - walk order: sampling/walk_order_<iss>.csv, dev items skipped. An item is kept if it has at least one verified
    report, until 20 are drawn. An item whose coverage depends only on a pending link stops the walk for that issuer.
Outputs: sampling/draw_<iss>.csv, sampling/walk_log_<iss>.csv, sampling/eligibility_final_<iss>.csv
Usage: python3 scripts/draw.py
"""
import csv, collections
csv.field_size_limit(10**9)
R = lambda f: list(csv.DictReader(open(f, encoding="utf-8-sig")))
r1 = {r["cand_id"]: r["decision"].strip() for r in R("annotation/R1/screening/Result/R1_screening_sheet.csv")}
assert all(v in ("eligible", "not_eligible") for v in r1.values()), "blank or unknown R1 screening decision"
key = {r["cand_id"]: r for r in R("sampling/R1_screening_key.csv")}
r1link = {(r["ann_id"], r["report_url"]): r["decision"].strip() for r in R("annotation/R1/screening/Result/R1_link_check_sheet.csv")}
SETS = {"cbar": ["cbar"], "tax": ["tax_w"], "social": ["social_w"]}
out_stats = {}
DEVSET = {r["cand_id"] for iss in SETS for r in R(f"sampling/walk_order_{iss}.csv") if r["dev_excluded"] == "1"}
for iss, sufs in SETS.items():
    merged = {r["cand_id"]: r for r in R(f"sampling/screen_merged_{iss}.csv")}
    final = {}
    for c, m in merged.items():
        final[c] = r1[c] if c in r1 else m["agreed_decision"]
    ef = [{"cand_id": c, "agreed_decision": merged[c]["agreed_decision"], "R1": r1.get(c, ""), "why_R1": key.get(c, {}).get("why", ""), "final": final[c]} for c in sorted(merged)]
    w = csv.DictWriter(open(f"sampling/eligibility_final_{iss}.csv", "w", newline="", encoding="utf-8"), fieldnames=list(ef[0])); w.writeheader(); w.writerows(ef)
    linked, cov = set(), collections.defaultdict(lambda: {"verified": 0, "pending": 0})
    for s in sufs:
        lset = {r["cand_id"] for r in R(f"sampling/link_set_{s}.csv")}; linked |= lset
        cx = {(r["ann_id"], r["url"]): r["verdict"] for r in R(f"data/link_verified_codex_{s}.csv")}
        for r in R(f"data/link_verified_claude_{s}.csv"):
            k = (r["ann_id"], r["url"]); cl = r["verdict"]; co = cx.get(k)
            if co and co != "MISSING" and (co == "same_decision") != (cl == "same_decision"):
                d = r1link.get(k, "")
                st = "verified" if d == "same_decision" else ("no" if d else "pending")
            else:
                st = "verified" if cl == "same_decision" else "no"
            if st != "no":
                cov[r["ann_id"]][st] += 1
    drawn, log, stop = [], [], None
    for r in R(f"sampling/walk_order_{iss}.csv"):
        c = r["cand_id"]
        if len(drawn) == 20 or stop:
            break
        if r["dev_excluded"] == "1":
            log.append({"rank": r["rank"], "cand_id": c, "result": "skip_dev"}); continue
        if final[c] != "eligible":
            log.append({"rank": r["rank"], "cand_id": c, "result": "skip_not_eligible"}); continue
        if c not in linked:
            stop = f"rank {r['rank']} {c}: eligible but not linked yet"; log.append({"rank": r["rank"], "cand_id": c, "result": "STOP_not_linked"}); break
        v = cov[c]
        if v["verified"] > 0:
            drawn.append(c); log.append({"rank": r["rank"], "cand_id": c, "result": "drawn"})
        elif v["pending"] > 0:
            stop = f"rank {r['rank']} {c}: coverage depends on a pending R1 link check"; log.append({"rank": r["rank"], "cand_id": c, "result": "STOP_pending_link"}); break
        else:
            log.append({"rank": r["rank"], "cand_id": c, "result": "skip_no_coverage"})
    w = csv.DictWriter(open(f"sampling/walk_log_{iss}.csv", "w", newline="", encoding="utf-8"), fieldnames=["rank", "cand_id", "result"]); w.writeheader(); w.writerows(log)
    with open(f"sampling/draw_{iss}.csv", "w", encoding="utf-8") as f:
        f.write("cand_id\n" + "".join(c + "\n" for c in drawn))
    res = collections.Counter(x["result"] for x in log)
    elig_seen = res["drawn"] + res["skip_no_coverage"]
    out_stats[iss] = dict(res, eligible_final_nondev=sum(v == "eligible" and c not in DEVSET for c, v in final.items()), frame=len(final), stop=stop,
                          covered_share=f"{res['drawn']}/{elig_seen}")
for k, v in out_stats.items():
    print(k, v)
