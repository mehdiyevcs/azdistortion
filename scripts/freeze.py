"""Freeze one source (announcement or news item): save raw bytes, extracted text, tables and metadata.

Usage:
  python3 scripts/freeze.py ann  CBAR-5573 <url> [<url2> ...]   # announcement page + its PDFs
  python3 scripts/freeze.py news N0001     <url>

Output: data/raw/<announcements|news>/<id>/ with
  raw_<k>.html|pdf, text_<k>.txt, tables_<k>.txt (PDF tables, row-wise), meta.json (url, fetched_at, sha256, status)
Add --wayback as the last argument to also ask the Wayback Machine to archive each URL (off by default; it sends the URL to a public service).
"""
import hashlib, json, os, sys, time, urllib.request, datetime

UA = {"User-Agent": "Mozilla/5.0 (AzDistortion research crawler)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def html_text(raw):
    import trafilatura
    s = raw.decode("utf-8", "ignore")
    body = trafilatura.extract(s, include_tables=True, favor_recall=True) or ""
    md = trafilatura.extract_metadata(s)
    head = []
    if md:
        head = [f"TITLE: {md.title}", f"DATE: {md.date}", f"AUTHOR: {md.author}", ""]
    return "\n".join(head) + body


def pdf_text_and_tables(path):
    import pdfplumber
    texts, tables = [], []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            texts.append(f"--- page {i} ---\n" + (page.extract_text() or ""))
            for j, tb in enumerate(page.extract_tables(), 1):
                tables.append(f"--- page {i} table {j} ---")
                for row in tb:
                    tables.append(" | ".join((c or "").replace("\n", " ").strip() for c in row))
    return "\n".join(texts), "\n".join(tables)


def wayback(url):
    try:
        urllib.request.urlopen(urllib.request.Request("https://web.archive.org/save/" + url, headers=UA), timeout=60)
        return "requested"
    except Exception as e:
        return f"failed: {e}"


def main():
    args = sys.argv[1:]
    use_wb = "--wayback" in args
    args = [a for a in args if a != "--wayback"]
    kind, item_id, urls = args[0], args[1], args[2:]
    out = os.path.join("data", "raw", "announcements" if kind == "ann" else "news", item_id)
    os.makedirs(out, exist_ok=True)
    meta = {"id": item_id, "kind": kind, "files": []}
    for k, url in enumerate(urls):
        rec = {"url": url, "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            status, ctype, raw = fetch(url)
        except Exception as e:
            rec["error"] = str(e); meta["files"].append(rec); print("ERROR", url, e); continue
        is_pdf = "pdf" in ctype.lower() or raw[:4] == b"%PDF"
        raw_path = os.path.join(out, f"raw_{k}.{'pdf' if is_pdf else 'html'}")
        open(raw_path, "wb").write(raw)
        rec.update({"status": status, "content_type": ctype, "sha256": hashlib.sha256(raw).hexdigest(), "raw": raw_path})
        if is_pdf:
            text, tables = pdf_text_and_tables(raw_path)
            open(os.path.join(out, f"tables_{k}.txt"), "w", encoding="utf-8").write(tables)
        else:
            text = html_text(raw)
        open(os.path.join(out, f"text_{k}.txt"), "w", encoding="utf-8").write(text)
        rec["wayback"] = wayback(url) if use_wb else "not requested"
        meta["files"].append(rec)
        print("saved", raw_path, len(raw), "bytes;", len(text), "chars of text")
        time.sleep(1)
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
