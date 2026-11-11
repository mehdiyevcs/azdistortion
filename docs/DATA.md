# Data files

All tables are UTF-8 CSV. Identifiers link the files:

- `ann_id`: an official announcement, e.g. `CBAR-5397` (issuer prefix: CBAR = Central Bank of the Republic of Azerbaijan, DVX = State Tax Service, EMSMN = Ministry of Labour and Social Protection of the Population).
- `report_id`: a news report. `R....` = random sample, `B....` = benchmark sample.
- `claim_id`: a claim unit, `<report_id>-Cnn`.

Label codes: `SUPPORTED`, `CONTRADICTED`, `MISREPRESENTED`, `NOT_IN_SOURCE`, `UNASSESSABLE`. The code `MISREPRESENTED` is the label called MISLEADING in the paper (the name changed after annotation, the definition did not). "Error claims" are CONTRADICTED and MISREPRESENTED claims. Subtypes of MISREPRESENTED (column `distortion_type`): `status`, `scope`, `actor`, `inference`, `dropped_condition`.

## Official texts

| Path | Content |
|---|---|
| `data/sources/<ann_id>/T1.txt` | Press release (text and tables). |
| `data/sources/<ann_id>/T2.txt` | Full decision or legal text, where one was found (34 of 145 announcements). |
| `data/sources/<ann_id>/meta.json` | Source files, `has_t2`, `t1_is_act` (press release is the act itself), character counts and SHA-256 of T1 and T2. |
| `sampling/sources_summary.csv` | The same flags for all 145 announcements in one table. |

## Sampling

| File | Content |
|---|---|
| `sampling/drawn_final.csv` | Announcements that entered the final draw (id, issuer, date, title, URL, text). |
| `sampling/eligibility_final_<issuer>.csv` | Eligibility decision per candidate announcement (`final`, with the screening reason). |
| `sampling/walk_log2_<issuer>.csv` | Seeded walk order of the draw and the coverage result per announcement; used for the issuer weights. |
| `sampling/reports_main.csv` | The 355 news reports: outlet, URL, publication date, headline, how the link was verified, sample, report weight. |
| `sampling/report_features.csv` | `reports_main.csv` plus copy features: number of word 5-grams, `copy_ratio` (share of 5-grams found in the press release), `rewritten` (copy ratio below 0.6), `syndicated`, `cluster`. |
| `sampling/clusters.csv` | Cluster of each announcement. Announcements that share a report or a syndicated copy form one cluster; clusters are the resampling and cross-validation unit. |

The report weight (`weight`) is `n_verified / n_kept`: at most four verified reports per announcement enter the random sample.

## Claims

| File | Content |
|---|---|
| `annotation/claims/claims_s1.csv` | Main claim split: 3,593 claims of 355 reports. `part` = headline, lead or body; `span` = the sentence span of the report the claim comes from (`span_found` = 1 if it was located verbatim); `claim_text` = the claim unit that was labelled. |
| `annotation/claims/claims_random.csv`, `claims_benchmark.csv` | The same claims split by sample (2,020 random, 1,573 benchmark). |
| `annotation/claims/claims_s2.csv` | Independent second split of 68 reports, used for the split agreement in the paper. |

## Labels

| File | Content |
|---|---|
| `annotation/llm/labels_A1.csv`, `labels_A2.csv` | LLM annotator labels for every claim: label, evidence quote from the official text, content tags, subtype, cause, unsure flag, split error flag, note, and the report flags `omission` and `framing`. A1 = Claude Opus 5.5, A2 = the OpenAI Codex command-line agent. |
| `annotation/reference/reference_R1.csv` | Human reference: 506 claims (351 random, 155 benchmark) labelled by the human annotator (R1). `set` = stratum (S-H, S-D, S-A, S-N), `weight` = design weight of the stratum, plus the A1 and A2 labels of the same claim. |
| `annotation/reference/weights.json` | Stratum sizes `N`, labelled counts `n_R1` and design weights. |
| `annotation/reference/pairs_R1.csv` | Report flags (omission, misleading framing) of the 20 S-H reports. |
| `annotation/guidelines_v1.2.md` | Annotation guidelines (frozen version used for all labels). |

## Edit set

| File | Content |
|---|---|
| `annotation/edits/edit_set_v2.csv` | Constructed edits: for each base claim one CONTRADICTED (`kind` = CON) and one MISREPRESENTED (`kind` = MIS) edit, with the edited claim, target subtype and evidence. |
| `annotation/reference/edits_R1.csv` | Human check of 180 edits: verdict, subtype, whether the base claim is SUPPORTED, `accepted`, and whether the subtype matches the intended one. |

## Runs and results

| Path | Content |
|---|---|
| `runs/<run_id>/predictions.csv` | One row per claim: gold (where available), predicted `label`, raw model output and, for LLM runs, model id, effort, tokens and cost. |
| `runs/<run_id>/meta.json` | Settings of the run (system, condition, prompt, source limits, input hashes). |
| `runs/main_inputs/` | Claim slices given to the systems, retrieval outputs for E3 and the edit inputs for E5. |
| `runs/colab_results/` | Fine-tuned encoder outputs (predictions, inner-fold scores, training logs, H7 selection). |
| `runs/dev_choice/cost_test.csv` | Development-set scores used to choose the LLM for H7 before the test runs. |
| `analysis/numbers.json` | Every number reported in the paper. |
| `analysis/tables/`, `analysis/figures/`, `analysis/hypotheses.md` | Tables, figures and hypothesis verdicts. |

Run ids follow `e<experiment>_<system>_<condition>_<sample>`, e.g. `e1_sonnet_C2_random`. Conditions: C0 = claim only, C1 = press release, C2 = press release and full text; `C2t2` runs hold only the claims that have a separate full text and are merged with C1 into the C2 run.
