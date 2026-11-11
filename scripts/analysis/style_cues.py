"""Compare sensational style cues in error claims and other claims (E9, exploratory, D15; no hypothesis, no Holm family).

On the human-verified reference: weighted share of claims (and of headline claims) with a sensational surface cue among
CON/MIS claims vs the other claims. Cue list fixed in D15: the words şok, sensasiya, böyük, təcili, diqqət, vacib, bomba,
yeni dövr, nəhayət, açıqlandı (any case, whole-word match), any all-caps word of 4+ letters, '!' or '?'.
Text = the claim's exact span in the report (claim_text when the span was not located).
Primary: all samples with phase weights (domain 'all'); also the random sample with RQ1 weights.
"""
import re
import numpy as np
import pandas as pd
from common import *

WORDS = ["şok", "sensasiya", "böyük", "təcili", "diqqət", "vacib", "bomba", "yeni dövr", "nəhayət", "açıqlandı"]
WRE = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in WORDS) + r")(?!\w)", re.UNICODE)
CAPS = re.compile(r"(?<!\w)([^\W\d_]{4,})(?!\w)", re.UNICODE)


def cues(text):
    t = str(text)
    hits = []
    if WRE.search(az_lower(t)):
        hits.append("word")
    if any(w.isupper() for w in CAPS.findall(t)):
        hits.append("caps")
    if "!" in t or "?" in t:
        hits.append("punct")
    return hits


def run():
    res = {}
    rows = []
    for domain, wcol in (("all", "w_phase"), ("random", "w_rq1")):
        dom, bt = boot(domain)
        text = np.where(dom["span_found"] == 1, dom["span"], dom["claim_text"])
        h = [cues(t) for t in text]
        cue = np.array([len(x) > 0 for x in h], float)
        err = dom["is_err"].values.astype(float); w = dom[wcol].values
        for scope, m in (("all claims", np.ones(len(dom), bool)), ("headlines", (dom["part"] == "headline").values)):
            mm = m.astype(float)
            def sh(g, cnt=None):
                if cnt is None:
                    den = (w * g * mm).sum(); return (w * g * mm * cue).sum() / den if den > 0 else np.nan
                with np.errstate(invalid="ignore", divide="ignore"):
                    return ((cnt * (w * g * mm * cue)).sum(1)) / ((cnt * (w * g * mm)).sum(1))
            a, b = sh(err), sh(1 - err)
            ra, rb = sh(err, bt.counts), sh(1 - err, bt.counts)
            d = ra - rb
            r = {"domain": domain, "scope": scope, "share_cue_error": a, "lo_error": ci(ra)[0], "hi_error": ci(ra)[1],
                 "share_cue_other": b, "lo_other": ci(rb)[0], "hi_other": ci(rb)[1], "diff": a - b, "diff_lo": ci(d)[0], "diff_hi": ci(d)[1],
                 "n_error": int((err * mm).sum()), "n_other": int(((1 - err) * mm).sum()), "n_cue_raw": int((cue * mm).sum())}
            rows.append(r); res[f"{domain}|{scope}"] = r
        res[f"{domain}|cue_type_counts"] = pd.Series([c for x in h for c in x]).value_counts().to_dict()
    write_table(pd.DataFrame(rows), "table_e9_style_cues", "E9 (exploratory, D15): share of claims with a sensational cue, CON/MIS vs other claims",
                note="Weighted shares; 95% CIs from the two-stage cluster bootstrap. Exploratory, no test.")
    return res
