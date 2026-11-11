"""Build the pool of candidate news URLs for the study window (31 Oct 2025 - 7 Nov 2026) from outlet sitemaps.

Outlets via sitemaps: Report (monthly archive), Oxu.az (yearly article sitemaps), Qafqazinfo (yearly), Musavat (numbered parts).
Banker.az and Trend are linked by other scripts (link_news.py, link_trend.py).
Dates: Report and Oxu.az carry lastmod; Qafqazinfo and Musavat do not, so their dates are checked when a page is fetched.
Sitemaps are cached in data/sitemaps_cache.
Usage: python3 -P -E scripts/news_pool.py  -> data/news_pool.csv (outlet, url, date, slug_text)
"""
import csv, datetime as dt, hashlib, os, re, time, urllib.parse, urllib.request, unicodedata

UA = {"User-Agent": "Mozilla/5.0 (research crawler; academic study of news accuracy)"}
CACHE = "data/sitemaps_cache"
LO, HI = dt.date(2025, 10, 31), dt.date(2026, 11, 7)


def get(url, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".xml")
    if os.path.exists(f) and not refresh:
        return open(f, encoding="utf-8").read()
    for k in range(3):
        try:
            t = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read().decode("utf-8", "ignore")
            open(f, "w", encoding="utf-8").write(t); time.sleep(0.8); return t
        except Exception as e:
            err = e; time.sleep(4)
    print("FAIL", url, err, flush=True); return ""


def entries(xml):
    out = []
    for b in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*([^<]+)", b); lm = re.search(r"<(?:lastmod|news:publication_date)>\s*([^<]+)", b)
        if loc:
            out.append((loc.group(1).strip(), lm.group(1).strip()[:10] if lm else ""))
    return out


def asciify(s):
    s = urllib.parse.unquote(s).lower().replace("ə", "e").replace("ı", "i")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def slug_text(u):
    tail = urllib.parse.urlparse(u).path.rstrip("/").split("/")[-1]
    tail = re.sub(r"[_-]?\d{5,}(\.html)?$", "", tail).replace(".html", "")
    return asciify(tail).replace("-", " ").replace("_", " ").strip()


def in_win(d):
    try:
        return LO <= dt.date.fromisoformat(d) <= HI
    except ValueError:
        return False


def main():
    pool = []
    d = dt.date(LO.year, LO.month, 1)
    while d <= HI:  # Report monthly archive parts (the current month is refreshed)
        for part in range(1, 6):
            xml = get(f"https://report.az/sitemap-posts-archive-{d.year}-{d.month}-{part}.xml", refresh=(d.year, d.month) == (HI.year, HI.month))
            if "<loc>" not in xml:
                break
            pool += [("Report", u, x) for u, x in entries(xml) if "/en/" not in u and "/ru/" not in u and in_win(x)]
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    for y in (2025, 2026):  # Oxu.az
        for suf in ("", "-2", "-3", "-4"):
            xml = get(f"https://oxu.az/sitemap-articles-az-{y}{suf}.xml", refresh=(y == 2026))
            pool += [("Oxu.az", u, x) for u, x in entries(xml) if in_win(x)]
    for y in (2025, 2026):  # Qafqazinfo (no dates)
        pool += [("Qafqazinfo", u, "") for u, _ in entries(get(f"https://qafqazinfo.az/sitemaps/sitemap-{y}.xml", refresh=(y == 2026)))]
    # Musavat: numbered parts, newest first; stop at the first part whose newest article id is below 1195000. The bound is
    # set well below the window start on purpose (reference point: pilot item N0001, article id 1296422, dated 14.10.2026).
    top = max(int(x) for x in re.findall(r"sitemap_part_(\d+)\.xml", get("https://musavat.com/sitemap.xml", refresh=True)))
    p = top + 200
    while p > 0:
        ent = entries(get(f"https://musavat.com/sitemap_part_{p}.xml"))
        ids = [int(m) for u, _ in ent for m in re.findall(r"_(\d{6,})\.html", u)]
        if ids:
            pool += [("Musavat", u, "") for u, _ in ent]
            if max(ids) < 1195000:
                break
        p -= 1
    rows = [{"outlet": o, "url": u, "date": x, "slug_text": slug_text(u)} for o, u, x in pool]
    seen, out = set(), []
    for r in rows:
        if r["url"] not in seen:
            seen.add(r["url"]); out.append(r)
    with open("data/news_pool.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["outlet", "url", "date", "slug_text"]); w.writeheader(); w.writerows(out)
    from collections import Counter
    print(len(out), Counter(r["outlet"] for r in out))


if __name__ == "__main__":
    main()
