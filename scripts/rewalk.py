"""Re-walk the draw after the full-window relink with the unchanged rule (D10 (b)).

An item counts as covered if it had a verified report in the earlier linking (draw.py) or has a same_decision report
from the relink (Claude verdict; Claude/Codex disagreements are resolved by the human annotator (R1)). The walk stops
at an item whose coverage depends on a pending R1 check or that was never checked.
Outputs: sampling/draw2_<iss>.csv, sampling/walk_log2_<iss>.csv, sampling/draw_changes.csv.
"""
import csv, collections
csv.field_size_limit(10**9)
R = lambda f: list(csv.DictReader(open(f, encoding="utf-8-sig")))
cx = {(r["ann_id"], r["url"]): r["verdict"] for r in R("data/link_verified_codex_relink.csv")}
r1 = {}
try:
    r1 = {(r["ann_id"], r["report_url"]): r["decision"] for r in R("annotation/R1/relink/R1_link_check_relink.csv")}
except FileNotFoundError:
    pass
cov = collections.defaultdict(lambda: {"v": 0, "p": 0})
for r in R("data/link_verified_claude_relink.csv"):
    k = (r["ann_id"], r["url"]); cl = r["verdict"] == "same_decision"; co = cx.get(k)
    if co and co != "MISSING" and (co == "same_decision") != cl:
        d = r1.get(k, ""); st = "v" if d == "same_decision" else ("" if d else "p")
    else:
        st = "v" if cl else ""
    if st:
        cov[r["ann_id"]][st] += 1
old = {}
for iss in ("cbar", "tax", "social"):
    for r in R(f"sampling/walk_log_{iss}.csv"):
        old[r["cand_id"]] = r["result"]
changes = []
for iss in ("cbar", "tax", "social"):
    final = {r["cand_id"]: r["final"] for r in R(f"sampling/eligibility_final_{iss}.csv")}
    drawn_old = [l for l in open(f"sampling/draw_{iss}.csv").read().split()[1:]]
    drawn, log, stop = [], [], None
    for r in R(f"sampling/walk_order_{iss}.csv"):
        c = r["cand_id"]
        if len(drawn) == 20:
            break
        if r["dev_excluded"] == "1":
            log.append((r["rank"], c, "skip_dev")); continue
        if final[c] != "eligible":
            log.append((r["rank"], c, "skip_not_eligible")); continue
        covered_old = old.get(c) == "drawn"
        if covered_old or cov[c]["v"] > 0:
            drawn.append(c); log.append((r["rank"], c, "drawn")); continue
        if cov[c]["p"] > 0:
            stop = f"{c}: coverage depends on a pending R1 link check"; log.append((r["rank"], c, "STOP_pending")); break
        if old.get(c) is None:
            stop = f"{c}: not checked in the earlier walk or the relink"; log.append((r["rank"], c, "STOP_unchecked")); break
        log.append((r["rank"], c, "skip_no_coverage"))
    with open(f"sampling/draw2_{iss}.csv", "w") as f:
        f.write("cand_id\n" + "".join(x + "\n" for x in drawn))
    w = csv.writer(open(f"sampling/walk_log2_{iss}.csv", "w", newline="")); w.writerow(["rank", "cand_id", "result"]); w.writerows(log)
    for c in drawn:
        if c not in drawn_old: changes.append((iss, c, "added"))
    for c in drawn_old:
        if c not in drawn: changes.append((iss, c, "dropped"))
    print(iss, "drawn", len(drawn), "stop:", stop, "added", [c for i, c, k in changes if i == iss and k == "added"], "dropped", [c for i, c, k in changes if i == iss and k == "dropped"])
w = csv.writer(open("sampling/draw_changes.csv", "w", newline="")); w.writerow(["issuer", "cand_id", "change"]); w.writerows(changes)
