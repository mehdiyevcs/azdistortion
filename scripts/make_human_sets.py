"""Draw the human label sets and write the annotation packets (prereg section 3 "Human labels: a two-phase design", D13).

Phase 1 (needs the final report list and the claims):  python3 scripts/make_human_sets.py sh
  S-H = random 10% of the pairs (pair = report) of the random sample, stratified by issuer, random.Random(20261113)
  per stratum (sorted ids), n_stratum = round(0.10 * N_stratum), at least 1. Every claim of S-H is labelled.
Phase 2 (needs the A1 and A2 labels of all claims):  python3 scripts/make_human_sets.py phase2
  S-D = census of the claims outside S-H where A1 != A2 or either label is not SUPPORTED, except claims where both say
        NOT_IN_SOURCE.
  S-A = random 15% of the claims outside S-H where A1 = A2 = SUPPORTED, random.Random(20261112).
  S-N = random 15% of the claims outside S-H where A1 = A2 = NOT_IN_SOURCE, random.Random(20261112).
  Each annotator gets one shuffled queue of S-D, S-A and S-N items, so the reason an item was chosen is hidden.
Packets are written for the two pre-registered annotators R1 and R2 (annotation/human/<R>/: pairs/*.html with the
official source A on the left, the report N and its claims on the right, the sheets and guidelines v1.2); no LLM labels
are shown. Under D17 only the human annotator (R1) labelled, including the R2 packets.
Design weights (S-H 1, S-D 1, S-A and S-N N/n, the exact inverse inclusion probability) go to annotation/human/design.csv,
which is kept out of the packets because it shows set membership.
"""
import csv, html, os, random, shutil, sys
from collections import defaultdict
csv.field_size_limit(10**9)
OUT = "annotation/human"
CSS = ("body{font-family:sans-serif;margin:0}header{padding:8px 16px;background:#eef3f8;font-size:14px}.wrap{display:flex;gap:12px;padding:12px}"
       ".col{flex:1;min-width:0}pre{white-space:pre-wrap;font-size:13px;line-height:1.45;border:1px solid #ccd;padding:10px;max-height:72vh;overflow:auto}"
       "ol li{margin:4px 0;font-size:13px}.hl{background:#fff3b0}")
CLAIM_COLS = ["claim_id", "report_id", "part", "claim_text", "label", "distortion_type", "content_tags", "evidence_quote", "cause", "unsure", "split_error", "note"]
PAIR_COLS = ["report_id", "ann_id", "key_conditions", "omission(0/1)", "omission_note", "framing(0/1)", "framing_note", "minutes"]


def reports():
    rows = list(csv.DictReader(open("sampling/reports_main.csv", encoding="utf-8")))
    if os.path.exists("sampling/reports_benchmark.csv") and not any(r.get("sample") == "benchmark" for r in rows):
        rows += list(csv.DictReader(open("sampling/reports_benchmark.csv", encoding="utf-8")))
    iss = {"CBAR": "cbar", "DVX": "tax", "EMSMN": "social"}
    for r in rows:
        r["issuer"] = iss[r["ann_id"].split("-")[0]]
        r["sample"] = r.get("sample") or ""
        assert r["sample"] in ("random", "benchmark"), f"sample flag missing for {r['report_id']}"
    ids = [r["report_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate report ids"
    return {r["report_id"]: r for r in rows}


def claims():
    out = defaultdict(list)
    for f in ("annotation/claims/claims_s1.csv", "annotation/claims/claims_s1_benchmark.csv"):
        if os.path.exists(f):
            for c in csv.DictReader(open(f, encoding="utf-8")):
                out[c["report_id"]].append(c)
    return out


def pair_page(rep, cl, mark=None):
    aid = rep["ann_id"]
    t1 = open(f"data/sources/{aid}/T1.txt", encoding="utf-8").read()
    t2 = open(f"data/sources/{aid}/T2.txt", encoding="utf-8").read()
    nt = open(f"data/raw/news/{rep['report_id']}/text_0.txt", encoding="utf-8").read()
    items = "".join(f"<li{' class=hl' if mark and c['claim_id'] in mark else ''}><b>{c['claim_id']}</b> [{c['part']}]: {html.escape(c['claim_text'])}</li>" for c in cl)
    return (f"<!doctype html><meta charset=utf-8><title>{rep['report_id']} vs {aid}</title><style>{CSS}</style>"
            f"<header><b>{rep['report_id']}</b> ({html.escape(rep['outlet'])}, {html.escape(rep['pub_date'])}) vs official source <b>{aid}</b>. "
            f"Read the left column first and write its key conditions BEFORE reading the right column.</header><div class=wrap>"
            f"<div class=col><h3>A: press release</h3><pre>{html.escape(t1)}</pre><h3>A: full decision text</h3><pre>{html.escape(t2) if t2.strip() else 'none'}</pre></div>"
            f"<div class=col><h3>N: news report</h3><pre>{html.escape(nt)}</pre><h3>Claims</h3><ol>{items}</ol></div></div>")


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)


def sh():
    R = reports(); C = claims()
    nocl = [rid for rid in R if not C.get(rid)]
    if nocl:
        sys.exit(f"STOP: {len(nocl)} reports have no claims yet (split them first), e.g. {nocl[:5]}")
    strata = defaultdict(list)
    for rid, r in R.items():
        if r["sample"] == "random":  # D13: S-H on the random sample only
            strata[(r["issuer"], r["sample"])].append(rid)
    chosen = []
    log = []
    for key in sorted(strata):
        ids = sorted(strata[key]); n = max(1, round(0.10 * len(ids)))  # D13: 10%
        pick = sorted(random.Random(20261113).sample(ids, n)); chosen += pick
        log.append(f"{key}: {n} of {len(ids)} pairs, {sum(len(C[i]) for i in pick)} claims")
    os.makedirs(OUT, exist_ok=True)
    write_csv(f"{OUT}/SH_pairs.csv", ["report_id", "ann_id", "issuer", "sample"], [{k: R[i][k] for k in ("report_id", "ann_id", "issuer", "sample")} for i in chosen])
    for ann in ("R1", "R2"):
        d = f"{OUT}/{ann}/SH"; os.makedirs(f"{d}/pairs", exist_ok=True)
        for i in chosen:
            open(f"{d}/pairs/{i}.html", "w", encoding="utf-8").write(pair_page(R[i], C[i]))
        write_csv(f"{d}/sheet_claims_{ann}.csv", CLAIM_COLS, [{"claim_id": c["claim_id"], "report_id": i, "part": c["part"], "claim_text": c["claim_text"]} for i in chosen for c in C[i]])
        write_csv(f"{d}/sheet_pairs_{ann}.csv", PAIR_COLS, [{"report_id": i, "ann_id": R[i]["ann_id"]} for i in chosen])
        shutil.copy("annotation/guidelines_v1.2.md", f"{d}/guidelines_v1.2.md")
    open(f"{OUT}/SH_log.txt", "w").write("S-H draw, seed 20261113, 10% per stratum of the random sample (D13)\n" + "\n".join(log) + f"\nTotal: {len(chosen)} pairs, {sum(len(C[i]) for i in chosen)} claims\n")
    print(open(f"{OUT}/SH_log.txt").read())


def phase2():
    R = reports(); C = claims()
    sh_ids = {r["report_id"] for r in csv.DictReader(open(f"{OUT}/SH_pairs.csv", encoding="utf-8-sig"))}
    lab = {}
    for a in ("A1", "A2"):
        for r in csv.DictReader(open(f"annotation/llm/labels_{a}.csv", encoding="utf-8")):
            assert (a, r["claim_id"]) not in lab, f"duplicate {a} label for {r['claim_id']}"
            assert r["label"] in ("SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"), f"invalid {a} label {r['label']} for {r['claim_id']}"
            lab[(a, r["claim_id"])] = r["label"]
    sd, agreed, agreed_nis, missing = [], [], [], []
    for rid, cl in C.items():
        if rid in sh_ids or rid not in R:
            continue
        for c in cl:
            a1, a2 = lab.get(("A1", c["claim_id"])), lab.get(("A2", c["claim_id"]))
            if a1 is None or a2 is None:
                missing.append(c["claim_id"]); continue
            if a1 == a2 == "SUPPORTED":
                agreed.append(c["claim_id"])
            elif a1 == a2 == "NOT_IN_SOURCE":  # D13: audit stratum, not census
                agreed_nis.append(c["claim_id"])
            else:
                sd.append(c["claim_id"])
    if missing:
        sys.exit(f"STOP: {len(missing)} claims lack an A1 or A2 label, e.g. {missing[:5]}")
    agreed.sort(); agreed_nis.sort(); sd.sort()
    sa = sorted(random.Random(20261112).sample(agreed, round(0.15 * len(agreed))))
    sn = sorted(random.Random(20261112).sample(agreed_nis, round(0.15 * len(agreed_nis))))
    rng = random.Random(20261119)
    sd_sh = sd[:]; rng.shuffle(sd_sh)
    sa_sh = sa + sn; rng.shuffle(sa_sh)
    assign = {c: ("R1" if k % 2 == 0 else "R2") for k, c in enumerate(sd_sh)}
    assign.update({c: ("R1" if k < len(sa_sh) / 2 else "R2") for k, c in enumerate(sa_sh)})
    design = [{"claim_id": c["claim_id"], "report_id": rid, "set": "S-H", "weight": 1, "annotator": "R1+R2"} for rid in sh_ids for c in C[rid]]
    byid0 = {c["claim_id"]: c["report_id"] for cl in C.values() for c in cl}
    w_sa = len(agreed) / len(sa)  # exact inverse inclusion probability N/n (about 1/0.15)
    w_sn = len(agreed_nis) / len(sn)
    design += [{"claim_id": c, "report_id": byid0[c], "set": "S-D", "weight": 1, "annotator": assign[c]} for c in sd]
    design += [{"claim_id": c, "report_id": byid0[c], "set": "S-A", "weight": round(w_sa, 6), "annotator": assign[c]} for c in sa]
    design += [{"claim_id": c, "report_id": byid0[c], "set": "S-N", "weight": round(w_sn, 6), "annotator": assign[c]} for c in sn]
    write_csv(f"{OUT}/design.csv", ["claim_id", "report_id", "set", "weight", "annotator"], design)
    byid = {c["claim_id"]: c for cl in C.values() for c in cl}
    for ann in ("R1", "R2"):
        q = [c for c in sd + sa + sn if assign[c] == ann]; random.Random(20261119 + (ann == "R2")).shuffle(q)
        d = f"{OUT}/{ann}/P2"; os.makedirs(f"{d}/pairs", exist_ok=True)
        # one page per item with only that claim highlighted, so the number of selected claims in a report is not visible
        for c in q:
            rid = byid[c]["report_id"]
            open(f"{d}/pairs/{c}.html", "w", encoding="utf-8").write(pair_page(R[rid], C[rid], {c}))
        write_csv(f"{d}/sheet_items_{ann}.csv", CLAIM_COLS, [{"claim_id": c, "report_id": byid[c]["report_id"], "part": byid[c]["part"], "claim_text": byid[c]["claim_text"]} for c in q])
        shutil.copy("annotation/guidelines_v1.2.md", f"{d}/guidelines_v1.2.md")
    msg = (f"Phase 2: outside S-H, S-D {len(sd)} claims (census), agreed-SUPPORTED {len(agreed)} -> S-A {len(sa)} (15%), agreed-NIS {len(agreed_nis)} -> S-N {len(sn)} (15%). "
           f"R1 {sum(1 for v in assign.values() if v == 'R1')} items, R2 {sum(1 for v in assign.values() if v == 'R2')} items.")
    open(f"{OUT}/P2_log.txt", "w").write(msg + "\n"); print(msg)


if __name__ == "__main__":
    {"sh": sh, "phase2": phase2}[sys.argv[1]]()
