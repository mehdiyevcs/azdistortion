"""Build the source package (T1, T2) of each drawn and benchmark announcement (prereg D3).

T1 is the text of the press release page (HTML texts in data/raw/announcements/<id>/), page furniture removed.
T2 is the full decision text: the files in <id>-DEC/ plus a PDF attached to the press release (CBAR-5446, CBAR-5535)
when it is not already in <id>-DEC (same sha256). For PDFs with struck-through wording, text_<k>_nostrike.txt is used
and the raw table file is skipped (it keeps deleted rows) unless a hand-checked tables_<k>_checked.txt exists.
Outputs: data/sources/<id>/T1.txt, T2.txt (empty if none), meta.json (files used, has_t2, t1_is_act);
sampling/sources_summary.csv
Usage: python3 scripts/build_sources.py
"""
import csv, glob, hashlib, json, os, re
csv.field_size_limit(10**9)
BOILER = ("gov.az domeni", "Güvənilir vebsayt", "URL çubuğunda", "Dili seçin", "Axtar")
T1_IS_ACT = {"DVX-4587", "DVX-5080", "DVX-4572", "DVX-4629", "DVX-4631", "DVX-4878"}  # issuer post already holds the full act (T2 5-gram share in T1 >= 0.99; prereg D3 and D3 addendum)
# notes put at the top of T2 for annotators and models
SOURCE_NOTES = {"CBAR-5514": "[Study note: this is the consolidated text frozen on 2026-11-09. It also includes amendments of 4 August 2026 (decision 35/2) "
                "and 18 August 2026 (decision 36/2), made after the news reports. Those later amendments change points 2.1.4, 2.1.5.6, 2.1.5.9, 2.1.13, "
                "5.4-4 and Annex 4, not the provisions of decision 18/11 announced on 25 June 2026.]"}


def clean(t):
    return "\n".join(l for l in t.splitlines() if l.strip() and not any(b in l for b in BOILER))


def pdf_parts(d, k, used):
    """Return the (path, text) parts to use for raw_<k>.pdf in folder d and add their paths to used."""
    log = f"{d}/strike_{k}.log"
    struck = os.path.exists(log) and any(not l.endswith(" 0") for l in open(log).read().splitlines())
    tf = f"{d}/text_{k}_nostrike.txt" if struck else f"{d}/text_{k}.txt"
    parts = [(tf, open(tf, encoding="utf-8").read())]
    chk = f"{d}/tables_{k}_checked.txt"
    if os.path.exists(chk):
        parts.append((chk, open(chk, encoding="utf-8").read()))
    elif not struck and os.path.exists(f"{d}/tables_{k}.txt"):
        parts.append((f"{d}/tables_{k}.txt", open(f"{d}/tables_{k}.txt", encoding="utf-8").read()))
    used.extend(p for p, _ in parts)
    return parts


t2 = {r["cand_id"]: r for f in ("sampling/t2_links.csv", "sampling/t2_links_benchmark.csv") for r in csv.DictReader(open(f, encoding="utf-8"))}
# announcements: the final draw (D10) plus the benchmark announcements
_ids = [r["cand_id"] for r in csv.DictReader(open("sampling/drawn_final.csv", encoding="utf-8"))]
_ids += sorted({r["ann_id"] for r in csv.DictReader(open("sampling/reports_benchmark.csv", encoding="utf-8"))} - set(_ids))
rows = [{"cand_id": i} for i in _ids]
T2_ALIAS = {"DVX-4532": "DVX-4543"}  # both announcements refer to the same Tax Code amendment law, which contains the voluntary-disclosure change
summary = []
for r in rows:
    aid = r["cand_id"]; base = f"data/raw/announcements/{aid}"; dec = f"data/raw/announcements/{T2_ALIAS.get(aid, aid)}-DEC"
    meta = json.load(open(f"{base}/meta.json", encoding="utf-8"))
    used1, used2, T1, T2 = [], [], [], []
    dec_sha = set()
    if os.path.isdir(dec):
        for f in json.load(open(f"{dec}/meta.json", encoding="utf-8"))["files"]:
            if f.get("sha256"):
                dec_sha.add(f["sha256"])
    for k, f in enumerate(meta["files"]):
        if not f.get("raw"):
            continue
        if f["raw"].endswith(".html"):
            p = f"{base}/text_{k}.txt"; T1.append(clean(open(p, encoding="utf-8").read())); used1.append(p)
        elif f["raw"].endswith(".pdf") and f["sha256"] not in dec_sha:
            for p, t in pdf_parts(base, k, used2):
                T2.append(f"=== {os.path.basename(p)} ===\n{clean(t)}")
    if os.path.isdir(dec):
        for k, f in enumerate(json.load(open(f"{dec}/meta.json", encoding="utf-8"))["files"]):
            if not f.get("raw"):
                continue
            if f["raw"].endswith(".pdf"):
                for p, t in pdf_parts(dec, k, used2):
                    T2.append(f"=== {os.path.basename(p)} ===\n{clean(t)}")
            else:
                p = f"{dec}/text_{k}.txt"; T2.append(f"=== {os.path.basename(p)} ===\n{clean(open(p, encoding='utf-8').read())}"); used2.append(p)
    if aid in SOURCE_NOTES and T2:
        T2.insert(0, SOURCE_NOTES[aid])
    out = f"data/sources/{aid}"; os.makedirs(out, exist_ok=True)
    open(f"{out}/T1.txt", "w", encoding="utf-8").write("\n\n".join(T1))
    open(f"{out}/T2.txt", "w", encoding="utf-8").write("\n\n".join(T2))
    m = {"ann_id": aid, "t1_files": used1, "t2_files": used2, "has_t2": int(bool(T2)), "t2_status": t2.get(aid, {}).get("has_t2", "missing"),
         "t1_is_act": int(aid in T1_IS_ACT),
         "sha256_T1": hashlib.sha256("\n\n".join(T1).encode()).hexdigest(), "sha256_T2": hashlib.sha256("\n\n".join(T2).encode()).hexdigest(),
         "chars_T1": len("\n\n".join(T1)), "chars_T2": len("\n\n".join(T2))}
    json.dump(m, open(f"{out}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    summary.append(m)
w = csv.DictWriter(open("sampling/sources_summary.csv", "w", newline="", encoding="utf-8"), fieldnames=["ann_id", "has_t2", "t2_status", "t1_is_act", "chars_T1", "chars_T2", "sha256_T1", "sha256_T2"])
w.writeheader(); w.writerows({k: m[k] for k in w.fieldnames} for m in summary)
print("built", len(summary), "; with T2:", sum(m["has_t2"] for m in summary), "; T1 empty:", [m["ann_id"] for m in summary if m["chars_T1"] < 200],
      "; largest T2 chars:", sorted((m["chars_T2"], m["ann_id"]) for m in summary)[-4:])
