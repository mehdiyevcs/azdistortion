# Penalised weighted logistic regression of claim-is-CON-or-MIS (odds ratios)

| predictor | OR | lo | hi | ci_rule |
|---|---|---|---|---|
| rewritten | 17.027 | 1.000 | 80.344 | degenerate reps at OR = 1 |
| part_headline | 0.582 | 0.151 | 4.572 | degenerate reps at OR = 1 |
| part_lead | 7.053 | 0.256 | 64.558 | non-degenerate reps only (descriptive) |
| outlet_general portal | 0.592 | 0.056 | 8.154 | non-degenerate reps only (descriptive) |
| outlet_finance portal | 0.135 | 0.027 | 0.562 | non-degenerate reps only (descriptive) |
| issuer_DVX | 0.534 | 0.038 | 13.038 | non-degenerate reps only (descriptive) |
| issuer_EMSMN | 0.718 | 0.040 | 7.349 | non-degenerate reps only (descriptive) |

Random sample, 351 human-labelled claims, 15 error claims (raw); prereg minimum for H2/H3 is 30, so the model is descriptive only. L2-penalised (C = 1), which shrinks ORs toward 1. CIs: two-stage cluster bootstrap.
