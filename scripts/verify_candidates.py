"""Fetch each candidate news page, extract title, date and text, and check it against hand-written event anchors.

Anchors are event terms, not numbers. A candidate is in the window if it appeared 0-7 days after the release date.
Inputs: annotation/announcements.csv, annotation/news_candidates.csv
Usage: python3 scripts/verify_candidates.py
Output: annotation/news_candidates_checked.csv
"""
import csv, hashlib, os, re, time, urllib.request, datetime as dt
import trafilatura

UA = {"User-Agent": "Mozilla/5.0 (AzDistortion research crawler)"}
CACHE = "data/candidate_cache"
# Every group must match title + text (case-insensitive); a group is a regex of alternatives.
ANCHORS = {
    "CBAR-5573": [r"Mərkəzi Bank|MB", r"kartdan.karta|karta köçürmə|BKM|Banklararası Kart"],
    "CBAR-5417": [r"uçot dərəcəsi", r"Mərkəzi Bank"],
    "CBAR-5463": [r"icbari sığorta|icbari.*sığortası", r"avtonəqliyyat|avtomobil|nəqliyyat vasitə|sürücü"],
    "CBAR-5459": [r"interçeync|interchange"],
    "CBAR-5569": [r"kredit risk", r"Mərkəzi Bank|prudensial"],
    "DVX-4939": [r"Vergi Məcəllə", r"depozit|445|Fərman"],
    "DVX-4959": [r"bəyannamə", r"qayda|forma"],
    "DVX-5048": [r"ƏDV", r"yaşayış|mənzil|qeyri-yaşayış"],
    "EMSMN-10013": [r"müalicə müddəti"],
    "EMSMN-9975": [r"hipertenziya"],
    "EMSMN-9920": [r"pensiya", r"9 ay|yanvar.sentyabr|doqquz ay"],
    "DVX-4966": [r"vergi uçotuna|ƏDV", r"rəqəmsal|beynəlxalq şirkət|Xsolla|Valve"],
    "EMSMN-9192": [r"müalicə müddəti", r"əlillik|əlilliy"],
}


def fetch(url):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".html")
    if os.path.exists(f):
        return open(f, encoding="utf-8").read()
    try:
        s = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")
    except Exception as e:
        return ""
    open(f, "w", encoding="utf-8").write(s); time.sleep(0.6)
    return s


def main():
    anns = {r["ann_id"]: r for r in csv.DictReader(open("annotation/announcements.csv", encoding="utf-8"))}
    out = []
    for r in csv.DictReader(open("annotation/news_candidates.csv", encoding="utf-8")):
        s = fetch(r["url"])
        md = trafilatura.extract_metadata(s) if s else None
        text = (trafilatura.extract(s, include_tables=True) or "") if s else ""
        title = (md.title if md and md.title else "")
        date = (md.date if md and md.date else r["sitemap_date"])
        blob = title + "\n" + text
        ok = all(re.search(g, blob, re.I) for g in ANCHORS[r["ann_id"]])
        rel = anns[r["ann_id"]]["release_date"]
        in_win = ""
        if rel and date:
            try:
                d0 = dt.datetime.strptime(rel, "%d.%m.%Y").date(); d1 = dt.date.fromisoformat(date[:10])
                in_win = str(0 <= (d1 - d0).days <= 7)
            except ValueError:
                pass
        out.append({**r, "title": title.strip()[:200], "pub_date": date, "anchors_ok": ok, "in_window": in_win, "n_chars": len(text)})
        print(r["ann_id"], ok, in_win, date, title[:80], flush=True)
    w = csv.DictWriter(open("annotation/news_candidates_checked.csv", "w", newline="", encoding="utf-8"), fieldnames=list(out[0].keys()))
    w.writeheader(); w.writerows(out)


if __name__ == "__main__":
    main()
