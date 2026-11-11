"""List the news items of the Ministry of Labour and Social Protection of the Population (sosial.gov.az).

Output: data/candidates/sosial_news.csv (id, title_az, url)
Usage: python3 scripts/list_sosial.py <number of listing pages>
"""
import csv, re, sys, time, html, urllib.request
pages = int(sys.argv[1]); rows, seen = [], set()
for p in range(1, pages + 1):
    url = f"https://sosial.gov.az/az/media/xeberler?page={p}"
    try:
        s = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research crawler)"}), timeout=60).read().decode("utf-8", "ignore")
    except Exception as e:
        print("ERR", p, e); continue
    for h, t in re.findall(r'href="(https://sosial\.gov\.az/az/media/xeberler/[^"]+-(?:\d+))"[^>]*>\s*([^<]{15,250})<', s):
        if h in seen: continue
        seen.add(h); rows.append({"id": h.rsplit("-", 1)[1], "title_az": html.unescape(t).strip(), "url": h})
    time.sleep(1)
w = csv.DictWriter(open("data/candidates/sosial_news.csv", "w", newline="", encoding="utf-8"), fieldnames=["id", "title_az", "url"])
w.writeheader(); w.writerows(rows); print(len(rows))
