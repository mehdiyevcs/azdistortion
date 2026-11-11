"""List State Tax Service posts by post id and write data/candidates/tax_posts.csv.

Usage: python3 scripts/list_tax.py <lowest_id> <highest_id>   (e.g. 4800 5116)
"""
import csv, re, sys, time, html, urllib.request
lo, hi = int(sys.argv[1]), int(sys.argv[2]); rows = []
for i in range(hi, lo - 1, -1):
    url = f"https://www.taxes.gov.az/az/post/{i}"
    try:
        s = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research crawler)"}), timeout=40).read().decode("utf-8", "ignore")
    except Exception as e:
        rows.append({"id": i, "date": "", "title_az": f"ERROR {e}", "url": url}); continue
    t = re.search(r'<meta property="og:title" content="([^"]+)"', s) or re.search(r"<title>(.*?)</title>", s, re.S)
    d = re.search(r"(\d{2}[./]\d{2}[./]20\d{2})", s)
    rows.append({"id": i, "date": d.group(1) if d else "", "title_az": html.unescape(t.group(1)).strip() if t else "", "url": url})
    time.sleep(0.7)
w = csv.DictWriter(open("data/candidates/tax_posts.csv", "w", newline="", encoding="utf-8"), fieldnames=["id", "date", "title_az", "url"])
w.writeheader(); w.writerows(rows); print(len(rows))
