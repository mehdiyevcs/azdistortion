"""Write the training inputs of the non-LLM systems to runs/nonllm_inputs/.

train_labels.csv  claim_id,label,source for every claim of annotation/claims/claims_s1.csv that has a training label:
                  the human label of annotation/reference/reference_R1.csv (source=human), otherwise the A1 label when
                  A1 == A2 (annotation/llm/labels_A1.csv, labels_A2.csv; source=agreed_llm). This is the rule that
                  scripts/sys_common.load_claims applies when --train-labels is empty (prereg 4a); the file only makes
                  it explicit so the Colab bundle (which has no LLM label files) uses identical labels.
edits_train.csv   E2 variant (b) training edits in the format of sys_common.load_edits: edit_id, base_claim_id, ann_id,
                  claim_text (edited claim), label (intended: CON -> CONTRADICTED, MIS -> MISREPRESENTED), accepted
                  (D17 addendum d1 / correction: R1 verdict == intended label and base_supported == 1, as built in
                  annotation/reference/edits_R1.csv; edits without a human check have accepted = 0).
Nothing under annotation/reference/ or annotation/human/ is written. Prints counts and sha256 of the outputs.
"""
import csv, hashlib, os
from collections import Counter

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(MAIN, "runs/nonllm_inputs")
LABELS = {"SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"}


def rd(p):
    return list(csv.DictReader(open(os.path.join(MAIN, p), encoding="utf-8")))


def main():
    os.makedirs(OUT, exist_ok=True)
    claims = rd("annotation/claims/claims_s1.csv")
    ref = {r["claim_id"]: r for r in rd("annotation/reference/reference_R1.csv")}
    l1 = {r["claim_id"]: r["label"] for r in rd("annotation/llm/labels_A1.csv")}
    l2 = {r["claim_id"]: r["label"] for r in rd("annotation/llm/labels_A2.csv")}
    ids = {c["claim_id"] for c in claims}
    assert len(ids) == len(claims) == 3593, len(claims)
    assert set(ref) <= ids, "reference claims outside claims_s1"
    out = []
    for c in claims:
        cid = c["claim_id"]
        if cid in ref and ref[cid]["label"]:
            out.append((cid, ref[cid]["label"], "human"))
        elif cid in l1 and cid in l2 and l1[cid] == l2[cid]:
            out.append((cid, l1[cid], "agreed_llm"))
    assert all(l in LABELS for _, l, _ in out)
    p = os.path.join(OUT, "train_labels.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["claim_id", "label", "source"]); w.writerows(out)
    print(f"train_labels.csv: {len(out)} of {len(claims)} claims; by source {dict(Counter(s for _, _, s in out))}; "
          f"labels {dict(Counter(l for _, l, _ in out))}")

    es = rd("annotation/edits/edit_set_v2.csv")
    chk = {r["edit_id"]: r for r in rd("annotation/reference/edits_R1.csv")}
    assert len(es) == 300 and set(chk) <= {e["edit_id"] for e in es}
    rows = []
    for e in es:
        lab = {"CON": "CONTRADICTED", "MIS": "MISREPRESENTED"}[e["kind"]]
        acc = chk[e["edit_id"]]["accepted"] if e["edit_id"] in chk else "0"
        assert acc in ("0", "1")
        rows.append(dict(edit_id=e["edit_id"], base_claim_id=e["claim_id"], ann_id=e["ann_id"], claim_text=e["edited_claim"], label=lab,
                         accepted=acc, human_checked=int(e["edit_id"] in chk)))
    p2 = os.path.join(OUT, "edits_train.csv")
    with open(p2, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"edits_train.csv: {len(rows)} edits; accepted by label {dict(Counter(r['label'] for r in rows if r['accepted'] == '1'))}; "
          f"human-checked {sum(r['human_checked'] for r in rows)}")
    for q in (p, p2):
        print(os.path.relpath(q, MAIN), hashlib.sha256(open(q, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
