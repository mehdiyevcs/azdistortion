"""Estimate publication dates of undated pool entries (Musavat, Qafqazinfo) from their sequential URL ids.

Pages already fetched with a known date serve as anchors (piecewise-linear interpolation of id -> date). The estimate is
written to data/news_pool.csv, column est_date; the real date is checked again when the page is fetched. Also prints the
leave-one-out error of the interpolation on the anchors. Run from the repository root.
"""
import csv, glob, re, datetime as dt, bisect
csv.field_size_limit(10**9)
anch = {}
for f in glob.glob("data/link_fetched_*.csv"):
    for r in csv.DictReader(open(f, encoding="utf-8")):
        m = re.search(r"[_-](\d{5,})(?:\.html)?/?$", r["url"])
        if r["outlet"] in ("Musavat", "Qafqazinfo") and m and r["pub_date"][:4].isdigit():
            try:
                anch.setdefault(r["outlet"], []).append((int(m.group(1)), dt.date.fromisoformat(r["pub_date"][:10]).toordinal()))
            except ValueError:
                pass
for o in anch:
    anch[o] = sorted(set(anch[o]))
    print(o, len(anch[o]), "anchors", anch[o][0], anch[o][-1])
def est(o, i):
    A = anch.get(o)
    if not A or len(A) < 5:
        return ""
    ids = [a for a, _ in A]; k = bisect.bisect_left(ids, i)
    k = min(max(k, 1), len(A) - 1); (i0, d0), (i1, d1) = A[k - 1], A[k]
    d = d0 + (d1 - d0) * (i - i0) / (i1 - i0) if i1 != i0 else d0
    return dt.date.fromordinal(int(round(d))).isoformat()
rows = list(csv.DictReader(open("data/news_pool.csv", encoding="utf-8")))
for r in rows:
    m = re.search(r"[_-](\d{5,})(?:\.html)?/?$", r["url"])
    r["est_date"] = est(r["outlet"], int(m.group(1))) if (not r["date"] and m) else ""
w = csv.DictWriter(open("data/news_pool.csv", "w", newline="", encoding="utf-8"), fieldnames=["outlet", "url", "date", "slug_text", "est_date"]); w.writeheader(); w.writerows(rows)
# accuracy check: leave-one-out error on anchors
for o, A in anch.items():
    errs = []
    for j in range(1, len(A) - 1):
        (i0, d0), (i, d), (i1, d1) = A[j - 1], A[j], A[j + 1]
        p = d0 + (d1 - d0) * (i - i0) / (i1 - i0) if i1 != i0 else d0
        errs.append(abs(p - d))
    errs.sort(); print(o, "LOO abs error days: median", errs[len(errs) // 2], "p95", errs[int(.95 * len(errs))])
