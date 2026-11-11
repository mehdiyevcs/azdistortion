"""Retrieve the top 5 passages per claim from the C2 source for the E3 retrieval variants (prereg section 7).

Claims: every main-study claim whose announcement has a T2 (runs/main_inputs/random_t2.csv and benchmark_t2.csv,
i.e. has_t2 = 1 and not t1_is_act, prereg D3); they are written to runs/main_inputs/e3_claims.csv.
Source: T1 + T2 (sys_common.source_text, C2), split by sys_common.chunk (sentences/lines, 6-120 words), the same
passages as the NLI system S1.
Methods (k = 1, 3, 5 are the first k of the top 5):
  bm25 : Okapi BM25 (k1 = 1.2, b = 0.75, idf = ln(1 + (N - n + 0.5) / (n + 0.5))) over the passages of one announcement,
         tokens = sys_common.toks (word tokens, Azerbaijani-aware lowercasing), no stemming.
  e5   : intfloat/multilingual-e5-base (pinned revision), "query: " + claim, "passage: " + passage, mean pooling,
         L2-normalised, cosine; max length 512.
Outputs: runs/main_inputs/e3_<method>.jsonl, one line per claim (claim_id, ann_id, n_passages, passages [{idx, text, score}]),
and runs/main_inputs/e3_retrieval_meta.json.
Usage: python3 scripts/e3_retrieve.py
"""
import csv, json, math, os, sys
from collections import Counter

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MAIN, "scripts"))
import sys_common as S

INP = os.path.join(MAIN, "runs", "main_inputs")
E5 = ("intfloat/multilingual-e5-base", "d128750597153bb5987e10b1c3493a34e5a4502a")
TOPN = 5


def bm25_rank(query, passages, k1=1.2, b=0.75):
    docs = [S.toks(p) for p in passages]
    N = len(docs); avg = sum(map(len, docs)) / max(1, N)
    df = Counter(t for d in docs for t in set(d))
    q = S.toks(query)
    scores = []
    for d in docs:
        tf = Counter(d); s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


def main():
    claims = []
    for f in ("random_t2.csv", "benchmark_t2.csv"):
        claims += list(csv.DictReader(open(os.path.join(INP, f), encoding="utf-8")))
    with open(os.path.join(INP, "e3_claims.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(claims[0])); w.writeheader(); w.writerows(claims)
    passages = {}
    for c in claims:
        if c["ann_id"] not in passages:
            text, has = S.source_text(c["ann_id"], "C2", dev=False)
            assert has, c["ann_id"]
            passages[c["ann_id"]] = S.chunk(text)
    print(len(claims), "claims;", len(passages), "announcements;", sum(map(len, passages.values())), "passages")

    with open(os.path.join(INP, "e3_bm25.jsonl"), "w", encoding="utf-8") as fh:
        for c in claims:
            ps = passages[c["ann_id"]]; sc = bm25_rank(c["claim_text"], ps)
            top = sorted(range(len(ps)), key=lambda i: (-sc[i], i))[:TOPN]
            fh.write(json.dumps({"claim_id": c["claim_id"], "ann_id": c["ann_id"], "n_passages": len(ps),
                                 "passages": [{"idx": i, "text": ps[i], "score": round(sc[i], 4)} for i in top]}, ensure_ascii=False) + "\n")

    import torch
    from transformers import AutoModel, AutoTokenizer
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(E5[0], revision=E5[1])
    model = AutoModel.from_pretrained(E5[0], revision=E5[1]).to(dev).eval()

    def emb(texts, bs=32):
        out = []
        for i in range(0, len(texts), bs):
            x = tok(texts[i:i + bs], max_length=512, truncation=True, padding=True, return_tensors="pt").to(dev)
            with torch.no_grad():
                h = model(**x).last_hidden_state
            m = x["attention_mask"].unsqueeze(-1).float()
            v = (h * m).sum(1) / m.sum(1)
            out.append(torch.nn.functional.normalize(v, dim=-1).cpu())
        return torch.cat(out)

    pe = {a: emb(["passage: " + p for p in ps]) for a, ps in passages.items()}
    qe = emb(["query: " + c["claim_text"] for c in claims])
    with open(os.path.join(INP, "e3_e5.jsonl"), "w", encoding="utf-8") as fh:
        for j, c in enumerate(claims):
            ps = passages[c["ann_id"]]; sc = (pe[c["ann_id"]] @ qe[j]).tolist()
            top = sorted(range(len(ps)), key=lambda i: (-sc[i], i))[:TOPN]
            fh.write(json.dumps({"claim_id": c["claim_id"], "ann_id": c["ann_id"], "n_passages": len(ps),
                                 "passages": [{"idx": i, "text": ps[i], "score": round(sc[i], 4)} for i in top]}, ensure_ascii=False) + "\n")
    json.dump({"e5_model": E5[0], "e5_revision": E5[1], "device": dev, "topn": TOPN, "bm25": {"k1": 1.2, "b": 0.75, "tokens": "sys_common.toks"},
               "chunker": "sys_common.chunk(min_words=6, max_words=120)", "n_claims": len(claims)},
              open(os.path.join(INP, "e3_retrieval_meta.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
