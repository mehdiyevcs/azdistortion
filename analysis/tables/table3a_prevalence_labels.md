# RQ1: claim-level label distribution, random sample (design-weighted)

| label | share | lo | hi | n_raw | est_total_retained_claims | est_total_expanded_claims |
|---|---|---|---|---|---|---|
| SUPPORTED | 0.685 | 0.530 | 0.837 | 273 | 1697.440 | 3704.832 |
| CONTRADICTED | 0.003 | 0.000 | 0.011 | 2 | 4.000 | 15.500 |
| MISREPRESENTED | 0.013 | 0.002 | 0.027 | 13 | 31.412 | 71.912 |
| NOT_IN_SOURCE | 0.297 | 0.147 | 0.448 | 62 | 415.109 | 1606.200 |
| UNASSESSABLE | 0.002 | 0.000 | 0.010 | 1 | 2.000 | 11.500 |
| ERROR (CON+MIS) | 0.016 | 0.004 | 0.031 | 15 | 35.412 | 87.412 |

est_total_retained_claims: phase weights only, total over the 2020 retained claims; est_total_expanded_claims: phase x D10 report weights (claims of all verified reports). Human-verified reference, random sample: 351 labelled claims of 2020; Kish n_eff 75.9. Weights: phase weight x D10 report weight. 95% percentile CIs, two-stage cluster bootstrap (2,000 reps).
