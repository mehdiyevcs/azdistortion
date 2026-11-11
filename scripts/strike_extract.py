"""Re-extract PDF text with struck-through (deleted) wording removed.

Consolidated CBAR rules print deleted wording with a strike line. A character counts as struck if a thin horizontal
line or rectangle crosses it in the middle band (30-75% of its height) over at least half its width.
Raw files are not changed.
Outputs (next to the raw PDF): text_<k>_nostrike.txt (struck characters removed), strike_<k>.log (counts per page)
Usage: python scripts/strike_extract.py data/raw/announcements/<id>-DEC/raw_<k>.pdf [...]
"""
import os, re, sys
import pdfplumber


def struck(ch, segs):
    h = ch["bottom"] - ch["top"]
    lo, hi = ch["top"] + 0.30 * h, ch["top"] + 0.75 * h
    w = ch["x1"] - ch["x0"]
    for (x0, x1, y) in segs:
        if lo <= y <= hi and min(x1, ch["x1"]) - max(x0, ch["x0"]) >= 0.5 * w:
            return True
    return False


def page_segments(page):
    segs = []
    for l in page.lines:
        if abs(l["top"] - l["bottom"]) < 1.5:
            segs.append((l["x0"], l["x1"], (l["top"] + l["bottom"]) / 2))
    for r in page.rects:
        if r["height"] < 2.0 and r["width"] > 2:
            segs.append((r["x0"], r["x1"], (r["top"] + r["bottom"]) / 2))
    return segs


def main(path):
    d, base = os.path.split(path)
    k = re.search(r"raw_(\d+)\.pdf", base).group(1)
    out, log = [], []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            segs = page_segments(page)
            n_struck = 0
            if segs:
                def keep(obj):
                    nonlocal n_struck
                    if obj.get("object_type") == "char" and struck(obj, segs):
                        n_struck += 1
                        return False
                    return True
                page = page.filter(keep)
            out.append(f"--- page {i} ---\n" + (page.extract_text() or ""))
            log.append(f"page {i}: struck chars {n_struck}")
    open(os.path.join(d, f"text_{k}_nostrike.txt"), "w", encoding="utf-8").write("\n".join(out))
    open(os.path.join(d, f"strike_{k}.log"), "w").write("\n".join(log))
    tot = sum(int(x.split()[-1]) for x in log)
    print(path, "pages", len(log), "struck chars", tot, "pages with strikes", sum(1 for x in log if not x.endswith(" 0")))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
