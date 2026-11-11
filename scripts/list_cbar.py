"""List the Central Bank (CBAR) press releases published in a date range.

Usage: python3 scripts/list_cbar.py 01/01/2025 04/11/2026
Output: data/candidates/cbar_press_releases.csv
"""
import csv, re, sys, time, html, urllib.request
BASE = "https://www.cbar.az/press-releases/index?dateFrom={f}&dateTo={t}&type=1&page={p}&language=az"
f, t = sys.argv[1], sys.argv[2]
rows, seen = [], set()
for p in range(1, 200):
    req = urllib.request.Request(BASE.format(f=f, t=t, p=p), headers={"User-Agent": "Mozilla/5.0 (research crawler)"})
    s = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
    items = re.findall(r'data-key="(\d+)".*?<span>([\d.]+)</span><p>(.*?)</p><a href="([^"]+)"', s, re.S)
    new = [i for i in items if i[0] not in seen]
    if not new:
        break
    for k, d, title, href in new:
        seen.add(k)
        rows.append({"id": k, "date": d, "title_az": html.unescape(re.sub("<[^>]+>", "", title)).strip(),
                     "url": "https://www.cbar.az" + href + "?language=az"})
    time.sleep(1.0)
with open("data/candidates/cbar_press_releases.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["id", "date", "title_az", "url"]); w.writeheader(); w.writerows(rows)
print(len(rows), "press releases")
