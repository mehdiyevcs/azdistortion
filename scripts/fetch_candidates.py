"""Build the 12-month sampling frame (1 Nov 2025 - 31 Oct 2026) of one issuer, with title, date and body text.

Crawling uses a research user agent, a 0.8 s delay between requests and 3 retries. The CBAR list is read from the
pilot candidate file ../pilot/data/candidates/cbar_press_releases.csv.
Outputs: data/candidates/<issuer>.csv; raw HTML cached in data/ann_cache/ (file name = md5 of the URL)
Usage: python3 -P -E scripts/fetch_candidates.py cbar|tax|social
"""
import csv, hashlib, html, os, re, sys, time, datetime as dt, urllib.request, urllib.error
import trafilatura

UA = {"User-Agent": "Mozilla/5.0 (research crawler; academic study of news accuracy)"}
CACHE = "data/ann_cache"
LO, HI = dt.date(2025, 11, 1), dt.date(2026, 10, 31)
MON = {m: i + 1 for i, m in enumerate("yanvar fevral mart aprel may iyun iyul avqust sentyabr oktyabr noyabr dekabr".split())}


def get(url, cache=True):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".html")
    if cache and os.path.exists(f):
        return open(f, encoding="utf-8").read()
    for k in range(3):
        try:
            s = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")
            if cache:
                open(f, "w", encoding="utf-8").write(s)
            time.sleep(0.8)
            return s
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return ""
            print("retry", k, url, e, flush=True); time.sleep(5 * (k + 1))
        except Exception as e:
            print("retry", k, url, e, flush=True); time.sleep(5 * (k + 1))
    return ""


MONTHS = "yanvar|fevral|mart|aprel|may|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr"


def tax_date(s):
    """Publication date on taxes.gov.az: <time>28 noyabr 2025, 10:49</time>."""
    m = re.search(r"<time>\s*(\d{1,2})\s+(" + MONTHS + r")\s+(20\d\d)", s, re.I)
    return dt.date(int(m.group(3)), MON[m.group(2).lower().replace("i̇", "i")], int(m.group(1))) if m else None


def social_date(s):
    """Publication date on sosial.gov.az: 'Noyabr 5, 2026 10:45 | Baxış sayı'."""
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))
    m = re.search(r"(" + MONTHS + r")\s+(\d{1,2}),\s+(20\d\d)\s+\d\d:\d\d\s*\|\s*Baxış", t, re.I)
    return dt.date(int(m.group(3)), MON[m.group(1).lower().replace("i̇", "i")], int(m.group(2))) if m else None


def body(s):
    return (trafilatura.extract(s, include_tables=True) or "").strip()


def title_of(s):
    t = re.search(r'<meta property="og:title" content="([^"]+)"', s) or re.search(r"<title>(.*?)</title>", s, re.S)
    return html.unescape(t.group(1)).strip() if t else ""


def cbar():
    rows = []
    for r in csv.DictReader(open("../pilot/data/candidates/cbar_press_releases.csv", encoding="utf-8")):
        d = dt.datetime.strptime(r["date"], "%d.%m.%Y").date()
        if LO <= d <= HI:
            s = get(r["url"]); rows.append({"cand_id": "CBAR-" + r["id"], "date": d.isoformat(), "title": r["title_az"], "url": r["url"], "text": body(s)})
            print(rows[-1]["cand_id"], d, len(rows[-1]["text"]), flush=True)
    return rows


def tax(lo_id=4330, hi_id=5130):
    rows = []
    for i in range(lo_id, hi_id + 1):
        url = f"https://www.taxes.gov.az/az/post/{i}"; s = get(url)
        if not s:
            continue
        d = tax_date(s)
        if d and LO <= d <= HI:
            rows.append({"cand_id": f"DVX-{i}", "date": d.isoformat(), "title": title_of(s), "url": url, "text": body(s)})
            print(rows[-1]["cand_id"], d, rows[-1]["title"][:60], flush=True)
    return rows


def social(max_pages=80):
    seen, links = set(), []
    for p in range(1, max_pages + 1):
        s = get(f"https://sosial.gov.az/az/media/xeberler?page={p}", cache=False)
        new = []
        for h in re.findall(r'href="(https://sosial\.gov\.az/az/media/xeberler/[^"]+-\d+)"', s):
            if h.rsplit("-", 1)[1] not in seen:
                seen.add(h.rsplit("-", 1)[1]); new.append(h)
        if not new:
            break
        links += new
    rows, old = [], 0
    for h in links:
        s = get(h); d = social_date(s)
        if d and LO <= d <= HI:
            rows.append({"cand_id": "EMSMN-" + h.rsplit("-", 1)[1], "date": d.isoformat(), "title": title_of(s), "url": h, "text": body(s)})
            print(rows[-1]["cand_id"], d, rows[-1]["title"][:60], flush=True)
        elif d and d < LO:
            old += 1
            if old > 30:  # stop once more than 30 items predate the window
                break
    return rows


if __name__ == "__main__":
    which = sys.argv[1]
    rows = {"cbar": cbar, "tax": tax, "social": social}[which]()
    os.makedirs("data/candidates", exist_ok=True)
    with open(f"data/candidates/{which}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["cand_id", "date", "title", "url", "text"]); w.writeheader(); w.writerows(rows)
    print(which, len(rows), "candidates in window")
