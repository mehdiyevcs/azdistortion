"""Merge per-pair JSON annotations of one LLM annotator into labels_<ANN>.csv and pairs_<ANN>.csv, or list disagreements.

A disagreement is a different claim label (or, for CONTRADICTED, different content tags) or a different
omission/framing flag of a pair.

Usage:
  python3 scripts/merge_runs.py annotation/a1_runs A1
  python3 scripts/merge_runs.py --disagreements A1 A2   -> adjudication/disagreements.csv
"""
import csv, glob, json, re, sys

FIELDS = ["claim_id", "news_id", "ann_id", "annotator", "claim_text", "in_headline", "label", "evidence", "content_tags", "cause", "unsure", "notes"]


def parse(path):
    s = open(path, encoding="utf-8").read()
    return json.loads(re.search(r"\{.*\}", s, re.S).group(0))


def merge(runs, ann):
    draft = list(csv.DictReader(open("annotation/claims_draft.csv", encoding="utf-8")))
    news = list(csv.DictReader(open("annotation/news_items.csv", encoding="utf-8")))
    got, bad = {}, []
    for f in glob.glob(f"{runs}/N*.json"):
        try:
            d = parse(f); got[d["news_id"]] = d
        except Exception as e:
            bad.append((f, str(e)[:60]))
    byc = {c["claim_id"]: c for d in got.values() for c in d.get("claims", [])}
    w = csv.DictWriter(open(f"annotation/labels_{ann}.csv", "w", newline="", encoding="utf-8"), fieldnames=FIELDS)
    w.writeheader()
    miss = 0
    for c in draft:
        x = byc.get(c["claim_id"], {})
        miss += not x
        w.writerow({"claim_id": c["claim_id"], "news_id": c["news_id"], "ann_id": c["ann_id"], "annotator": ann,
                    "claim_text": c["claim_text"], "in_headline": c["in_headline"],
                    **{k: str(x.get(k, "")) for k in ("label", "evidence", "content_tags", "cause", "unsure", "notes")}})
    pf = ["news_id", "ann_id", "annotator", "key_conditions", "omission", "omission_note", "framing", "framing_note", "minutes"]
    p = csv.DictWriter(open(f"annotation/pairs_{ann}.csv", "w", newline="", encoding="utf-8"), fieldnames=pf)
    p.writeheader()
    for n in news:
        d = got.get(n["news_id"], {})
        p.writerow({"news_id": n["news_id"], "ann_id": n["ann_id"], "annotator": ann,
                    **{k: str(d.get(k, "")) for k in ("key_conditions", "omission", "omission_note", "framing", "framing_note")}, "minutes": ""})
    print(f"{ann}: {len(got)} items, {miss} claims missing a label, parse errors: {bad}")


def disagreements(a, b):
    A = {r["claim_id"]: r for r in csv.DictReader(open(f"annotation/labels_{a}.csv", encoding="utf-8"))}
    B = {r["claim_id"]: r for r in csv.DictReader(open(f"annotation/labels_{b}.csv", encoding="utf-8"))}
    PA = {r["news_id"]: r for r in csv.DictReader(open(f"annotation/pairs_{a}.csv", encoding="utf-8"))}
    PB = {r["news_id"]: r for r in csv.DictReader(open(f"annotation/pairs_{b}.csv", encoding="utf-8"))}
    w = csv.writer(open("adjudication/disagreements.csv", "w", newline="", encoding="utf-8"))
    w.writerow(["kind", "id", "ann_id", "claim_text", f"{a}_label", f"{a}_tags", f"{a}_notes", f"{b}_label", f"{b}_tags", f"{b}_notes", "gold_label", "gold_tags", "adjudication_note"])
    n = 0
    for cid, x in A.items():
        y = B.get(cid)
        if y and (x["label"] != y["label"] or (x["label"] == "CONTRADICTED" and x["content_tags"] != y["content_tags"])):
            w.writerow(["claim", cid, x["ann_id"], x["claim_text"], x["label"], x["content_tags"], x["notes"], y["label"], y["content_tags"], y["notes"], "", "", ""]); n += 1
    m = 0
    for nid, x in PA.items():
        y = PB.get(nid)
        for flag in ("omission", "framing"):
            if y and str(x[flag]) != str(y[flag]):
                w.writerow([flag, nid, x["ann_id"], "", x[flag], "", x[flag + "_note"], y[flag], "", y[flag + "_note"], "", "", ""]); m += 1
    print(f"{n} claim disagreements, {m} pair-flag disagreements -> adjudication/disagreements.csv")


if __name__ == "__main__":
    if sys.argv[1] == "--disagreements":
        disagreements(sys.argv[2], sys.argv[3])
    else:
        merge(sys.argv[1], sys.argv[2])
