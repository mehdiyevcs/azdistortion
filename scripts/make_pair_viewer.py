"""Build side-by-side pair pages (source left, news right, draft claims) and empty label sheets for the pilot pairs.

Inputs: annotation/announcements.csv, annotation/news_items.csv, annotation/claims_draft.csv, data/raw/.
Outputs: annotation/pairs/<news_id>.html, and per annotator annotation/labels_<annotator>.csv and annotation/pairs_<annotator>.csv.
Usage: python3 scripts/make_pair_viewer.py <annotator> [<annotator> ...]
"""
import csv, glob, html, os, sys
ann = {r["ann_id"]: r for r in csv.DictReader(open("annotation/announcements.csv", encoding="utf-8"))}
news = list(csv.DictReader(open("annotation/news_items.csv", encoding="utf-8")))
claims = list(csv.DictReader(open("annotation/claims_draft.csv", encoding="utf-8")))
BOILER = ("gov.az domeni", "Güvənilir vebsayt", "URL çubuğunda", "Dili seçin", "Axtar")
def src_text(aid):
    parts = []
    for f in sorted(glob.glob(f"data/raw/announcements/{aid}/text_*.txt")) + sorted(glob.glob(f"data/raw/announcements/{aid}/tables_*.txt")):
        t = "\n".join(l for l in open(f, encoding="utf-8").read().splitlines() if l.strip() and not any(b in l for b in BOILER))
        parts.append(f"=== {os.path.basename(f)} ===\n{t}")
    return "\n\n".join(parts)
os.makedirs("annotation/pairs", exist_ok=True)
CSS = "body{font-family:sans-serif;margin:0}header{padding:8px 16px;background:#eef3f8}.wrap{display:flex;gap:12px;padding:12px}.col{flex:1;min-width:0}pre{white-space:pre-wrap;font-size:13px;line-height:1.45;border:1px solid #ccd;padding:10px;max-height:78vh;overflow:auto}ol li{margin:4px 0;font-size:13px}"
for n in news:
    nid, aid = n["news_id"], n["ann_id"]
    nt = open(f"data/raw/news/{nid}/text_0.txt", encoding="utf-8").read() if os.path.exists(f"data/raw/news/{nid}/text_0.txt") else "(missing)"
    cl = "".join(f"<li><b>{c['claim_id']}</b>{' [HEADLINE]' if c['in_headline']=='1' else ''}: {html.escape(c['claim_text'])}</li>" for c in claims if c["news_id"] == nid)
    page = (f"<!doctype html><meta charset=utf-8><title>{nid} vs {aid}</title><style>{CSS}</style>"
            f"<header><b>{nid}</b> ({html.escape(n['outlet'])}, {html.escape(n['pub_datetime'])}) vs <b>{aid}</b> (release {html.escape(ann[aid]['release_date'])}). "
            f"Step 1: list A's key conditions BEFORE reading the right column.</header><div class=wrap>"
            f"<div class=col><h3>A: official source</h3><pre>{html.escape(src_text(aid))}</pre></div>"
            f"<div class=col><h3>N: news item</h3><pre>{html.escape(nt)}</pre><h3>Draft claims (edit freely)</h3><ol>{cl}</ol></div></div>")
    open(f"annotation/pairs/{nid}.html", "w", encoding="utf-8").write(page)
for a in sys.argv[1:]:
    w = csv.writer(open(f"annotation/labels_{a}.csv", "w", newline="", encoding="utf-8"))
    w.writerow(["claim_id", "news_id", "ann_id", "annotator", "claim_text", "in_headline", "label", "evidence", "content_tags", "cause", "unsure", "notes"])
    for c in claims:
        w.writerow([c["claim_id"], c["news_id"], c["ann_id"], a, c["claim_text"], c["in_headline"], "", "", "", "", "", ""])
    p = csv.writer(open(f"annotation/pairs_{a}.csv", "w", newline="", encoding="utf-8"))
    p.writerow(["news_id", "ann_id", "annotator", "key_conditions", "omission", "omission_note", "framing", "framing_note", "minutes"])
    for n in news:
        p.writerow([n["news_id"], n["ann_id"], a, "", "", "", "", "", ""])
print(len(news), "pair pages;", "sheets for", sys.argv[1:])
