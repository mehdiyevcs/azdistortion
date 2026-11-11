# Pre-registered design and hypotheses (main study)

Version 1.2, 2026-11-09. FROZEN (sha256 in prereg.sha256). v1.0 and v1.1 were reviewed by Codex and an independent Claude agent:
- round 1: checks/prereg.codex.md, checks/prereg.claude.md;
- round 2: checks/prereg2.codex.md, checks/prereg2.claude.md.

v1.2 answers both rounds (section 9). The statistical rules are in section 4a.

v1.2 is frozen with a sha256 hash once its cross-check passes, and before any test-data labelling. Later changes go to section 10 "Deviations", with date and reason.

Naming: the human annotators are **R1** and **R2**, two anonymous researchers. The LLM annotators are **A1** (Claude Opus, via `claude -p --model opus`) and **A2** (Codex CLI, OpenAI). Hypotheses are **H1-H7**.

## 1. Research questions

- RQ1 (prevalence): how often do Azerbaijani news reports misrepresent or contradict official announcements of CBAR, the State Tax Service (DVX) and the Ministry of Labour and Social Protection (EMSMN)? In which outlet types and text parts, and with which distortion types?
- RQ2 (detection): how well do automatic systems detect these errors at claim level?
- RQ3 (source): how much does detection depend on access to the official text and on its form (none / press release / press release + full decision text)?
- RQ4 (annotation): how well do LLM annotators agree with human annotators on this task?

## 2. Units, population and sampling

### Units

- An **announcement** is one official post.
- A **report** is one news item (URL) about one announcement.
- A **pair** is a (report, announcement) pair.
- A **claim** is one checkable statement from a report. The headline is its own unit.

### Target population (estimand for RQ1)

Claims in Azerbaijani-language reports, from the fixed outlet list, about eligible announcements published 1 Nov 2025 to 31 Oct 2026 that received at least one report from that list ("covered eligible announcements").

The window is the most recent 12 complete months before data collection. It covers one full budget and tax cycle, since Tax Code amendments are usually adopted late in the year with effect from 1 January.

### Eligibility (from the announcement title and text)

- Eligible: the announcement reports an adopted or proposed decision, rule, tariff, fee, rate, tax, benefit, payment, eligibility condition or deadline that applies to citizens, firms or financial institutions. This includes statistics releases on payments or refunds made under such rules.
- Not eligible: events, meetings, trainings, outreach visits, awards, personnel changes, international cooperation, conferences, holidays and greetings, generic awareness campaigns, and announcements with no checkable content.
- Procedure:
  1. Screener 1 (Claude agent) and screener 2 (Codex) screen every candidate independently, each with a reason.
  2. Disagreements, and items either screener marks "borderline", go to R1, who decides.
  3. R1 also checks a random 10% of the agreed decisions.
  4. Report kappa(S1, S2), the R1-check agreement and the false-exclusion rate in that check.

### Outlet list (frozen)

| Type | Outlets |
|---|---|
| Agencies | APA, Report, Trend |
| General portals | Oxu.az, Qafqazinfo, Musavat |
| Finance portal | Banker.az |

AZERTAC returns HTTP 403 to automated requests. It is included only if its pages can be saved manually (decision by 16 Nov); otherwise it is excluded and listed as a limitation. Meydan TV and Azadliq (RFE/RL) were not reachable from the study's network on 9 Nov 2026 and are excluded; this is listed as a limitation.

Outlet type is coded from this table.

### Draw

1. Fix the sampling frame (data/candidates/*.csv) and hash it.
2. Shuffle each issuer's eligible list with `random.Random(20261109)`.
3. Walk the shuffled list. Keep an announcement if at least one verified report exists, until there are 20 per issuer. Skipped items are logged with the reason.
4. The share of eligible announcements with no coverage is reported per issuer.

Pooled RQ1 estimates are reported unweighted and weighted. The weighted estimate weights each issuer by its number of covered eligible announcements in the frame (estimated from the walk).

### Linking and verification

- Candidate reports are found by:
  - outlet sitemaps (slug and keyword match);
  - WordPress search (Banker.az);
  - outlet search pages where they return server-side HTML.
- Window: announcement date -1 to +7 days.
- A candidate is verified when the report describes the same decision as the announcement, not only the same topic. A Claude agent checks every candidate. Codex checks a random 20%, and R1 decides disagreements.
- Syndication: reports whose word 5-gram overlap with another report in the set is 0.9 or more are flagged as syndicated. They are kept in the data and analysed with announcement clustering.
- Overlap audit: no test announcement may be one of the dev announcements, or a re-release of one.

### Random sample vs benchmark add-on

- The random sample is all verified reports of the 60 drawn announcements.
- The benchmark add-on is chosen on purpose: explainers, headlines that differ from the issuer's title, and outlet social posts. It is flagged `sample=benchmark` and is never used for RQ1.

### Claims

- Segmenter S1 (Claude agent) splits every report. Codex splits a random 20% of reports independently.
- Boundary F1 is reported, with a gate of 0.75. Below the gate, the rules are revised once and the split is redone.
- R1 reviews a random 10% of the final splits, and the correction rate is reported.

## 3. Labels and gold

### Labels

Labels follow guidelines v1.1, frozen as v1.2 (with a headline rule) before test labelling:
- SUPPORTED;
- CONTRADICTED (CON);
- MISREPRESENTED (MIS);
- NOT_IN_SOURCE;
- UNASSESSABLE.

Distortion types: status, scope, actor, inference, dropped condition. The codebook defines the text parts: headline, lead (first paragraph), body.

### LLM labels

A1 and A2 label every claim independently. Source: press release + full text. Settings: temperature 0 where settable, model version strings logged.

### Human labels: a two-phase design

All human labelling is blind to LLM labels.

- **S-H (phase 1, probability sample).** A random 25% of pairs, stratified by issuer and sample. Every claim is labelled by R1 and R2 independently.
  - R1 and R2 then discuss their disagreements and record a consensus.
  - If they still disagree, the claim is marked "contested" and R1's label is used in the primary analyses (a pre-named tie-break). Sensitivity analyses use R2's label, and then exclude contested claims.
  - R1-R2 agreement on S-H is reported as a proxy for the error of single-annotator labels in phase 2.
- **Phase 2, outside S-H.**
  - S-D: every claim where A1 and A2 disagree, or either gives a label other than SUPPORTED, is labelled by one human (R1 or R2, alternating).
  - S-A: a simple random sample of 15% of the claims where both LLMs said SUPPORTED. Half is labelled by R1 and half by R2.
  - S-D and S-A items are shuffled into one queue, so the annotator cannot tell why an item was selected.

### Human-verified reference (primary)

Every claim in S-H, S-D and S-A has a human label. With design weights, this set represents all claims:
- S-H: weight 1;
- S-D: weight 1, since it is a census of its stratum;
- S-A: weight 1/0.15 for its stratum, the agreed-SUPPORTED claims outside S-H.

The effective sample size (Kish) of every weighted estimate is reported.

**All confirmatory analyses use this human-verified reference with weights.** The full "agreed-LLM gold" is used only for secondary analyses and for training encoders.

## 4. Hypotheses (confirmatory)

All tests are one-sided in the predicted direction. Decisions follow section 4a.

| ID | Hypothesis | Estimate | Smallest effect of interest | Minimum information |
|---|---|---|---|---|
| H1 | Among error claims (CON + MIS) in the random sample, MIS is the majority | design-weighted share MIS / (CON + MIS), tested against 0.5 | share >= 0.6 | at least 10 error claims, otherwise inconclusive. Given the pilot (0 CON), H1 is expected to hold; its value is the size of the share |
| H2 | Claims in rewritten reports are distorted more often than claims in copied reports | penalised logistic regression (section 4a) of claim-is-CON-or-MIS on: rewritten (report copy ratio < 0.6, copy ratio = share of the report's word 5-grams, lowercased, punctuation removed, found in T1, the press release), text part (headline / lead / body), outlet type (agency / general portal / finance portal), issuer (3). OR(rewritten) > 1. The copy ratio is a report-level property applied to all of its claims | OR >= 1.5 | at least 30 error claims, otherwise descriptive only |
| H3 | Headline claims are distorted more often than body claims | same model, OR(headline vs body) > 1 | OR >= 1.5 | same |
| H4 | For each LLM system (Haiku, Sonnet, GPT, open-weight), macro-F1 rises from C0 to C1 and from C1 to C2 | paired difference of macro-F1 on the same C2-eligible claims, 4 systems x 2 contrasts = 8 tests | difference >= 0.05 | - |
| H5 | For each LLM system under C2, recall on natural MIS claims is lower than recall on validated distortion edits (E-MIS) | recall difference. Edits are post-stratified to the natural MIS distribution over distortion types; type length distributions are reported | difference <= -0.05 | at least 15 natural MIS claims |
| H6 | On MIS, LLM-human agreement is lower than human-human agreement | on S-H only: PSA_MIS(R1, R2) minus the mean of PSA_MIS(R1,A1), PSA_MIS(R1,A2), PSA_MIS(R2,A1), PSA_MIS(R2,A2), where PSA = positive specific agreement = 2a / (2a + b + c) | difference >= 0.05 | at least 15 claims labelled MIS by R1 or R2 in S-H, otherwise inconclusive with the estimate reported |
| H7 | The selected fine-tuned encoder scores lower macro-F1 than the selected LLM under C2 | nested CV (section 4a); difference of macro-F1 on identical pooled out-of-fold claims | difference >= 0.05 | - |

**Macro-F1:** the mean F1 over the labels with at least 10 raw (unweighted) claims in the human-verified evaluation set. The label set is fixed from these counts before predictions are scored. The label set is exactly the labels that meet this threshold. For example, if CON has fewer than 10 claims, macro-F1 runs over the remaining labels that meet it, and the paper says so. If fewer than two labels meet it, macro-F1 is not reported and binary error detection takes its place in H4 and H7. A label that a system never predicts gets precision 0 and F1 0 (zero_division = 0). Per-label F1, weighted by the design weights, is computed from the confusion matrix. Binary error detection (CON or MIS vs the rest) is reported for every system as a secondary metric.

The simulation covers precision for prevalence and H1 only. No power simulation was done for H2-H7. For H4 and H7, the pilot gaps (macro-F1 0.71 vs 0.05) are far above the smallest effect of interest. H2, H3, H5 and H6 can end inconclusive, and their minimum-information rules say when.

**Precision expected** (scripts/power_sim.py, from pilot rates, 60 announcements): at a claim-level MIS rate of 4.5%, the random sample should hold about 40 MIS claims (minimum 14 over 150 simulations). The claim-level prevalence CI should be about ±2-2.5 points, and the report-level one about ±8 points. H6 has low power, as S-H is expected to hold about 10-20 MIS claims, and is likely to be inconclusive. That is stated in advance.

## 4a. Statistical specification

**Weights.**
- Every confirmatory estimate uses the two-phase design weights of section 3 (1, 1, 1/0.15).
- Issuer weights are used only for the secondary pooled RQ1 estimate. They are computed from the coverage walk and treated as fixed, which the paper states.

**Resampling.** A two-stage bootstrap with 2,000 replicates and seed 20261110:
1. Resample announcements with replacement, with all their reports and claims.
2. Within each resampled announcement, resample the S-A claims with replacement inside the S-A stratum. This carries the phase-2 sampling variance.

S-H and S-D are censuses of their strata given phase 1. The variance from the phase-1 selection of S-H pairs is not modelled, and the paper says so.

**p-values and decisions.**
- One-sided bootstrap p-value: p = (1 + number of replicates where the estimate is at or beyond the null in the wrong direction) / (B + 1). "At or beyond the null" means <= 0.5 for H1, <= 1 for odds ratios, and on the null-or-wrong side of 0 for differences. Ties count against support. A replicate where the statistic is undefined (for example, no error claims for H1, or a zero PSA denominator for H6) also counts as at the null. The number of such replicates is reported.
- Holm is applied to these p-values within each family:
  - F1 = {H1, H2, H3};
  - F2 = the 8 tests of H4;
  - F3 = {H5 (one test per system), H7};
  - F4 = {H6}.
- **Supported:** the Holm-adjusted p < 0.05 and the point estimate reaches the smallest effect of interest.
- **Inconclusive:** every result that is neither supported nor contradicted. This includes a significant effect below the smallest effect of interest, and the case where the minimum-information rule is not met.
- **Contradicted:** the point estimate is in the opposite direction and the one-sided p for the opposite direction is < 0.05.
- For display, the paper shows unadjusted 95% percentile CIs and the adjusted p-values.
- For H5, which has one test per system, "supported" means supported for at least half of the systems. The per-system results are always shown.
- H5 post-stratification:
  - the weight of distortion type t is its share of the design-weighted natural MIS claims;
  - edit recall is the weighted mean of per-type edit recall over the types present in both sets;
  - if natural MIS types with no accepted edits make up more than 20% of the natural MIS weight, H5 is "inconclusive";
  - edits belong to the announcement of their base claim, so the announcement bootstrap resamples natural claims and edits jointly.
- H6 uses R1's and R2's independent labels from before their discussion, together with A1's and A2's labels.
- Grouping: a report linked to more than one announcement, or syndicated across announcements (5-gram overlap >= 0.9), joins their announcements into one cluster (union-find). Bootstrap and CV both use these clusters.
- Issuer weights (secondary pooled RQ1 only):
  - for issuer i, E_i is the number of eligible announcements in the frozen frame;
  - c_i/k_i is the covered share among the k_i eligible announcements checked during the walk;
  - the estimated number of covered eligible announcements is N_i = E_i x c_i / k_i;
  - each drawn announcement of issuer i gets weight N_i / 20.

**Model for H2/H3.**
- Weighted logistic regression with an L2 penalty (scikit-learn LogisticRegression, C = 1.0, lbfgs). Predictors are dummy-coded; the intercept is not penalised (intercept_scaling = 100); sample_weight = the design weights.
- The penalty prevents failures under separation. It shrinks the odds ratios toward 1, which makes the test conservative; the paper states this.
- A bootstrap replicate with no error claims, or with no error claims in a level of a tested predictor, keeps its estimate at OR = 1 and is counted. If more than 5% of replicates are degenerate, the result is "inconclusive".

**Nested CV for H7.**
- Encoder candidates:
  - logistic regression on features;
  - gradient boosting on features;
  - XLM-R-base;
  - mDeBERTa-v3-base;
  - Azerbaijani BERT, if available.
- The outer loop is 5-fold, grouped by announcement, so syndicated reports stay with their announcement. Inside each outer training part, an inner 3-fold grouped CV chooses the candidate and its settings by macro-F1. The chosen model is refit on the outer training part and predicts the outer test fold.
- Tuning grids for the inner CV:
  - logistic regression: C in {0.1, 1, 10};
  - gradient boosting: max_depth in {2, 3}, n_estimators in {100, 300};
  - transformer encoders: learning rate in {1e-5, 2e-5, 3e-5}, 3 epochs, batch 16, max length 512, balanced class weights.
- Inner-fold scoring uses macro-F1 over the same label set as the outer evaluation.
- Out-of-fold predictions are pooled and scored against the weighted human-verified reference.
- Training labels: the human label where one exists, otherwise the agreed-LLM label. A secondary variant trains on human labels only.
- The LLM side of H7 is the LLM with the best dev macro-F1 under C2, fixed before the test runs. It is scored on the same pooled claims.
- The CIs are conditional on the fitted models. Training-procedure variance is not estimated, and the paper says so.

**Seeds.** Sampling 20261109; bootstrap 20261110; CV folds 20261111; S-A selection 20261112; S-H selection 20261113; training seeds 1-3 (with mean and range reported for neural encoders).

**Frozen inputs.** Every analysis reads only hashed, frozen files: sources T1 and T2 as frozen on retrieval, reports, claims, labels and predictions. A source that changes on the live site after freezing is not re-fetched.

## 5. Systems and conditions

- Systems:
  - majority baseline;
  - traditional ML (logistic regression on overlap and cue features, gradient boosting as a check);
  - mDeBERTa-v3 XNLI with retrieval;
  - fine-tuned XLM-R, plus an Azerbaijani-only BERT if a usable public checkpoint exists;
  - Claude Haiku;
  - Claude Sonnet;
  - a general OpenAI GPT-5.x model (not Codex);
  - one open-weight LLM.
- Family flags: Haiku and Sonnet are Claude-family, like A1 (Opus), and the GPT model is OpenAI-family, like A2 (Codex). All three are flagged. Their primary scores come from the human-verified reference, which removes the circularity of LLM-made gold.
- Opus and Codex are not test systems, since they are the annotators and the edit generator.
- Conditions:
  - C0: no source;
  - C1: press release;
  - C2: press release + full decision text.
  - H4 compares all three conditions on the claims whose announcement has a full text.
  - Sources longer than a model's context are cut to the top-k retrieved chunks (k fixed on dev). Each truncation is logged.
- Frozen before test runs, with a hash:
  - prompts, retrieval settings and thresholds, all chosen on the dev set only;
  - model version strings and temperature 0.
- Invalid outputs are retried once, then scored as SUPPORTED, and counted.
- Contamination: each model's stated training cutoff is recorded. Results on announcements dated after the latest cutoff are reported separately (exploratory).

## 6. Edit set (for H5)

The protocol is in EXPERIMENT_PLAN.md Phase C:
- 150 base claims, chosen from human-verified SUPPORTED claims;
- for each base claim, one contradiction edit and one distortion edit, written by Opus;
- R1 validates every contradiction edit and R2 every distortion edit, each cross-checking 20% of the other's;
- only accepted edits are used;
- edit types are fixed before generation.

## 7. Secondary and exploratory analyses

- Secondary: all results on the agreed-LLM gold; prevalence in the benchmark add-on; per-issuer results; the contested-claims sensitivity analysis.
- Exploratory:
  - retrieval variants;
  - prompt variants;
  - text length;
  - error-cause coding;
  - cost;
  - pre- vs post-cutoff;
  - the S-A miss rate as an estimate of the errors both LLMs miss.

## 8. Reporting

Every number in the paper comes from scripts run on frozen, hashed files. Tables are generated, not typed. The paper reports all seven hypotheses, whatever their outcome.

## 9. Response to the reviews

Round 2 (v1.1 to v1.2): bootstrap p-values, Holm and the decision rule defined (4a); weights made explicit, two-stage bootstrap for phase-2 variance; copy ratio against T1 only, text part with 3 levels, penalised model fully specified with a degenerate-replicate rule; contested claims resolved by R1 in the primary analysis; nested CV specified; S-A split between R1 and R2; effective sample size reported; smallest effects set for H1-H3; H5 post-stratified by type; H6 comparison defined; seeds and frozen inputs listed; binary detection made secondary.

Round 1 (v1.0 to v1.1):

| Point (reviewer) | Change |
|---|---|
| Gold mostly LLM-made, circular (both) | two-phase, human-verified, weighted reference is primary (section 3); agreed-LLM gold only secondary |
| S-A too small (Claude) | 5% raised to 15% |
| Blinding, contested, overlaps, "pairs" undefined (both) | units and procedures defined (sections 2-3) |
| H1 degenerate, independence (both) | weighted share with announcement bootstrap; minimum information rule |
| H2/H3 formula, sparse events (both) | formula, copy ratio and Firth estimator fixed; minimum events |
| H4: McNemar vs F1; populations differ (both) | paired bootstrap of the macro-F1 difference on the same C2-eligible claims |
| H5 protocol (both) | edit protocol fixed; matching by type; joint bootstrap |
| H6 kappa depends on prevalence (Claude); subsets (Codex) | positive specific agreement on S-H only; low power stated |
| H7 selection (both) | selection on dev or inner CV; identical held-out folds |
| Clustering level (both) | bootstrap by announcement everywhere |
| Coverage-conditioned estimand, issuer weights (both) | estimand named; weighted and unweighted estimates |
| Reproducibility of linking, outlets, window (Codex) | outlet list frozen, linking rules, window rationale |
| Power (both) | simulation added |
| Macro-F1 with absent classes (both) | label set fixed by gold counts of 10 or more; binary detection co-primary |
| Multiplicity families, effect size (Claude) | families listed; smallest effect of interest 0.05 |
| Naming clash H1 (Claude) | annotators renamed R1, R2 |
| Haiku not flagged; versions; contamination (Claude) | all same-family systems flagged; versions, temperature and cutoffs logged |
| Screening only 10% human (Claude) | all disagreements and borderline items go to R1 |
| Syndication, dev/test overlap (Codex) | syndication flag; overlap audit |

## 10. Deviations and later records

- Guidelines v1.2 (annotation/guidelines_v1.2.md), frozen 2026-11-09 before any test labelling: sha256 099ccfd615e9426a730dc0f0cf6c2cbef01289664e1d4976658e549d24e0d9aa (final version, with the distortion_type field, D2 (f)).
- Deviations:
  - D1 (2026-11-09, before any draw): the walk order in section 2 "Draw" is a seeded shuffle (random.Random(20261109)) of each issuer's full frozen frame, ordered by cand_id, skipping items that are not eligible. It replaces "shuffle each issuer's eligible list". Reason: the walk order then does not depend on R1's screening decisions, so news linking can run in walk order while R1 screens. Which items are drawn is still a uniformly random order of the eligible items. The frame hashes are in sampling/frame.sha256.
  - D2 (2026-11-09, before any test labelling): guidelines v1.2 add the headline rule allowed in section 3 and, after the calibration round (R1/R2, 69 dev claims, kappa 0.82, 5 disagreements), also:
    (a) definitions of the text parts headline / lead / body (as in section 3 "Labels");
    (b) clarification 1, a restatement of rule v1.1 (a simplification copied from the press release is SUPPORTED, cause = copied), except a status upgrade in A's own headline;
    (c) clarification 2: a claim with two facts takes the label of the more serious part (an UNASSESSABLE part takes the other part's label), with split_error = 1, because in the main study the claim split is fixed for all annotators and models;
    (d) clarification 3: a fact that A does not state, and that does not distort a point A addresses, is NOT_IN_SOURCE; a simple derivation from A stays SUPPORTED;
    (e) process: minutes per pair in the sheet instead of logs/timing.csv; human annotators must not use AI tools to suggest or check labels (tools for file handling are allowed). Reason: in calibration R1 used an LLM to handle the files, and this makes the boundary explicit.
    (f) a distortion_type field (status, scope, actor, inference, dropped_condition) for every MISREPRESENTED claim, as section 3 requires; it was missing from the first frozen v1.2 file and was added the same day, before any test labelling.
    No label definition or decision step changed. Under (c)-(d) the dev claim N0017-C02 would be NOT_IN_SOURCE, while its pilot label is SUPPORTED; the pilot (dev) labels are not re-adjudicated and are used only for prompt development. Checks: checks/guide12*.md.
  - D3 (2026-11-09, before any test labelling): source conditions. T1 is the text of the press release page only. A PDF of the act attached to the press release (CBAR-5446, CBAR-5535) counts as T2. Where the issuer's post is itself the full act (DVX-4587, DVX-5080), T1 already contains the act, so C1 and C2 are the same for those claims and they are left out of the H4 comparison of C1 with C2. Consolidated CBAR rules print deleted wording struck through; T2 text for those PDFs is extracted without struck characters (scripts/strike_extract.py, checked by eye on a rendered page). e-qanun.az needs JavaScript and was not used; laws and decrees were taken from president.az, CBAR rules from cbar.az. Of the 60 drawn announcements, 12 have a T2 and 2 are uncertain (logs/t2_summary.md).
  - D4 (2026-11-09): outlets. APA and AZERTAC block automated requests and have no usable sitemap. Their candidates were found with each outlet's own site search, run in the project owner's browser at human pace within the window [d-1, d+7], with the 2 search phrases per announcement, and the page text was saved from the browser (logs/browser_linking.md). Verification is the same as for other outlets (Claude all, Codex 20%, R1 on disagreements). Their recall therefore depends on the site search, and this is stated as a limitation.
  - D5 (2026-11-09, before any test labelling and before S-H is drawn): S-H is set to a random 15% of the pairs, stratified by issuer and sample as before, instead of 25%. Reason: the random sample has about 2,000 claims instead of the planned about 1,200, so 25% would need about 23-27 hours from each human annotator. 15% is the fallback already named in the plan and stays above the 10% minimum; it is chosen now, not after a delay. The S-A rate (15%) and the S-D census are unchanged. The design weights follow the actual rates.
  - D6 (2026-11-09, before any test run): sampling settings. Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5 do not accept a temperature, and Opus 5.5 cannot run without thinking; GPT-5.x are reasoning models and are run without a temperature. "Temperature 0 where settable" therefore applies only to Qwen (greedy decoding) and the encoders. Run-to-run variation is measured by the stability re-runs (section 5). Claude models are called through the Anthropic API with the guidelines and the source in cached system blocks; exact model ids, effort settings and token counts are logged per run.
  - D7 (2026-11-09, before any test labelling): annotator roles. R1 is the author of the study (who also wrote the guidelines with the agents and knows the pilot); R2 is an independent colleague who was not involved in the design. R1 labels blind to the LLM labels and to R2, exactly as R2. Because R1 is not independent of the study aims, the paper states this, reports R1-R2 agreement on S-H separately, and reports S-D/S-A results by annotator. "Two anonymous researchers" in this file is replaced by: R1 = the author, R2 = an anonymous independent colleague.
  - D8 (2026-11-09, before any benchmark report is labelled): the benchmark add-on is enlarged from about 80 to about 150 reports and enriched for likely distortion. Reason: the LLM labels of the random sample (not yet human-verified) suggest a claim-level error rate of about 1-3%, too few natural errors for stable detection scores. Enrichment uses only report features fixed in advance (rewritten: copy ratio < 0.6; explainers; headlines that differ from the issuer's title; outlet social posts if feasible), never an LLM label of the report, so the detection results are not biased toward the annotating models. The random sample (60 announcements) is unchanged, and the benchmark is never used for RQ1. Benchmark results are reported separately from the random sample.
  - D9 (2026-11-09, before any run on the benchmark): run plan for the benchmark sample. On benchmark claims, all systems run C1 and C2 only (C0 is answered on the random sample, RQ3), and GPT-5.5 runs C2 only. The random sample keeps the full C0/C1/C2 grid for every system. Reason: budget (user decision, option "Lean", total about $390).
  - D10 (2026-11-09, before any human labelling, user decision "option B"): linking recall and report cap. A recall audit (logs/recall_audit.md: 10 seeded drawn announcements, every sitemap slug in the window screened) found that the keyword step found only 18 of 40 verified reports (recall 0.45), and the missed reports differ in wording from the press release. Therefore:
    (a) for the four sitemap outlets, the keyword step is replaced by a full-window screen: every pool entry in [d-1, d+7] is screened by Claude Haiku 5.5 (inclusive), then fetched and verified as before (Claude Sonnet 5.5 for all candidates, Codex for a seeded 20%, R1 on disagreements). Validated on the 10 audit announcements: the Haiku screen caught 40 of 40 verified reports. Applied to the 60 drawn announcements and to the 21 walk items earlier skipped for "no coverage" (scripts/full_relink.py);
    (b) the draw walk is re-run with the new coverage, with the unchanged rule (first 20 covered eligible items per issuer in walk order); any change in the drawn set is logged;
    (c) per announcement, at most 4 verified reports enter the random sample, chosen with random.Random(20261120) from all its verified reports (all outlets); each kept report gets the weight n_verified / n_kept of its announcement for RQ1 estimates. Benchmark reports are not capped this way.
    Outlets searched by site search (Banker.az, APA, AZERTAC) and Trend keep their own method (D4).
  - D11 (2026-11-09, before any test run): main prompt. The E4 selection rule written before the dev runs picked variant v5 on one run; repeated runs showed the v1-v5 difference was within run-to-run noise (v5 0.748 then 0.617, v1 0.723 then 0.708 dev macro-F1), so the frozen main prompt is v1 (label definitions + the 4-step decision order), prompts/main.txt, sha256 d8c1612a043ffe98fb056d81794ec20ecb5c23c99980a764e9427413e9791273. Dev scores were not used for any other choice.
  - D12 (2026-11-09, before any training): compute for E2. Encoder fine-tuning runs on a Google Colab Pro GPU (the author's account), with the full pre-registered grid (XLM-R, allmalab/bert-base-aze, mDeBERTa-v3; nested grouped CV; seeds 1-3). The order is fixed in advance: (1) XLM-R and AzBERT, C2, natural; (2) mDeBERTa-v3, C2, natural; (3) all three, C1; (4) all three with the edit set. The author's Mac runs (1) in parallel as a backup; the Colab run is the reported one, and the Mac run, if complete, is reported as a cross-hardware check. Runs not finished by the numbers freeze are dropped from the bottom of this list and reported as not run. Data uploaded to Colab is the study data only (no API keys).
  - D10 addendum (2026-11-09, same day, before any human labelling): (c) is implemented with hash ranking, key sha256("20261120|" + url), the 4 smallest keys kept per announcement, so that a later R1 link decision moves only the report it concerns. Earlier keyword-found reports of the sitemap outlets are kept only if the full-window verification of the same page did not reject them (Codex check, checks/finalreports.codex.md). Three report URLs are linked both to DVX-4543 and DVX-4532 (same Tax Code law); such reports join the two announcements into one cluster for the bootstrap and CV.
  - D13 (2026-11-09, before any human labelling, user decision "B3"): human sets. With 3,593 claims the pre-registered sets would need about 1,100 claims per annotator. Changes: (a) S-H is a random 10% of the random-sample pairs (the minimum named in the plan), stratified by issuer; the benchmark has no S-H; (b) S-D is the census of claims outside S-H where A1 and A2 disagree, or either gives CONTRADICTED, MISREPRESENTED or UNASSESSABLE; (c) claims where both say SUPPORTED, and claims where both say NOT_IN_SOURCE, are two audit strata, each sampled at 15% (seed 20261112), weight N/n per stratum; (d) S-D and the audit items are split between R1 and R2 and mixed in one queue as before. Every claim either LLM flags as an error, or where they disagree, still gets a human label. R1-R2 agreement is measured on S-H (random sample only). Labelling over 3 days (12-14 Nov). Link rule (R1, stop 1): a report about one provision of an announced act counts as a report about the same decision.
  - D14 (2026-11-09, before any edit validation): edit set v2 (annotation/edits/edit_set_v2.csv; rules logs/edit_set_v2_rules.md). Base claims are 150 random-sample claims where A1 and A2 agree on SUPPORTED (not yet human-verified), stratified by issuer (50 each), at most 3 per announcement, with a fixed preference for claims stating a number, date, actor, scope or condition; generator Claude Opus 5.5. Each base gets one contradiction edit and one distortion edit; distortion types rotate over the five types, and a logged second pass rebalanced the status type after Opus judged 20 status targets impossible. Validation: R1 checks all contradiction edits and 20% of distortion edits, R2 all distortion edits and 20% of contradiction edits, and both also confirm that the base claim is SUPPORTED (base_supported); edits whose base is not confirmed are dropped from E5/H5.
  - D15 (2026-11-09, before any human labelling): one EXPLORATORY analysis is added (not a hypothesis, no Holm family): E9 style cues. On the human-verified reference, compare the share of claims (and of headlines) with a sensational surface cue among MISREPRESENTED/CONTRADICTED vs other claims. Cue list fixed now: the words şok, sensasiya, böyük, təcili, diqqət, vacib, bomba, yeni dövr, nəhayət, açıqlandı (any case), any all-caps word of 4+ letters, "!" or "?". Reported as weighted shares with bootstrap CIs, labelled exploratory.
  - D3 addendum (2026-11-09, before any scoring): a check of all 145 source packages (share of T2 word 5-grams already in T1) found four more announcements whose issuer post already holds the full act (DVX-4572, DVX-4629, DVX-4631, DVX-4878; share >= 0.99). They are treated like DVX-4587 and DVX-5080: C2 = C1, and they are left out of the C1-vs-C2 comparison (H4).
  - D16 (2026-11-09, before any human label is seen): one EXPLORATORY system is added (E10, not a hypothesis, no Holm family): a two-pass Haiku judge on C2 for all random and benchmark claims. Pass 1 (prompts/e10_literal.txt) asks only whether the claim is literally correct (SUPPORTED, CONTRADICTED, NOT_IN_SOURCE, UNASSESSABLE). Pass 2 (prompts/e10_implicature.txt) asks only whether the claim gives a wrong picture of the decision. Combination fixed now: CONTRADICTED if pass 1 says CONTRADICTED; UNASSESSABLE if pass 1 says UNASSESSABLE; MISREPRESENTED if pass 2 says MISREPRESENTED and pass 1 says SUPPORTED or NOT_IN_SOURCE; otherwise the pass 1 label. Scored like the other systems and reported as exploratory, compared with Haiku on the frozen main prompt.
  - D17 (2026-11-10, after R1 returned the sheets and before any human label is read or analysed; user decision): R2 is not available, so R1 is the only human annotator. R1 completed all R1 sheets (S-H 162 claims and pair flags, phase-2 queue 344 items, edit check 180 items). R1 states that the decisions are R1's own and that an AI tool was used only to collect R1's answers into the sheet files; the paper says so in one sentence. Changes: (a) the human reference is R1's label on every claim R1 labelled (S-H 162, S-D 102 of 204, S-A 189 of 376, S-N 53 of 108). R1's half of S-D, S-A and S-N is the seeded random half already fixed by scripts/make_human_sets.py (seeds 20261112, 20261119), so each set stays a probability sample: weights become N_set / n_R1 per set (S-D 204/102 = 2; S-A and S-N as in D13 with n = R1's count), and the variance uses the same two-stage bootstrap. The 102 S-D claims assigned to R2 have no human label and enter the estimates only through the weights. (b) No R1-R2 consensus and no contested-claim tie-break or sensitivity analysis. (c) H6 cannot be tested as written (it needs two independent humans on S-H) and is reported as not tested; the calibration agreement (R1 vs R2, 69 dev claims, kappa 0.82, measured before the main study) is reported only as a description of the guidelines' reliability, not as a test. RQ4 is answered with R1 vs A1 and R1 vs A2 on the claims R1 labelled. (d) Edit set: R1 checked all 150 contradiction edits and 30 distortion edits (the planned cross-check). E5 primary results use the edits R1 accepted; the 120 distortion edits without a human check are reported separately as a secondary, LLM-generated set and never pooled with the accepted ones. (e) If R1 labels further items before the numbers are frozen (the other 102 S-D claims, the other 120 distortion edits), they are added as R1 labels with the weights recomputed by the same rule, and the paper reports when they were labelled. (f) Limitation stated in the paper: single human annotator for the main study.
  - D17 addendum (2026-11-10, after the Codex check checks/d17.codex.md and before any human label is read; replaces D17 (e) and makes D17 (a) and (d) precise): (a1) Weights N_set / n_R1 (S-D 2, S-A 2508/189, S-N 719/53) give unbiased stratum totals conditional on phase 1; ratios, F1 and regression estimates are weighted plug-in estimates, as before. (a2) Resampling: the two-stage bootstrap (2,000 replicates, seed 20261110) keeps stage 1 (announcement clusters with the union-find clusters) and in stage 2 resamples, inside each resampled cluster, R1's claims with replacement within each of the three phase-2 strata S-D, S-A and S-N (S-D is now a 50% sample, no longer a census); no finite-population correction (conservative); S-H stays as before. (d1) Edit acceptance: an edit is accepted if R1's verdict equals its intended label (CONTRADICTED for contradiction edits, MISREPRESENTED for distortion edits, whatever the distortion type) and R1 marked the base claim as SUPPORTED (base_supported = 1, replacing D14's two-human wording); agreement of R1's distortion_type with the intended type is reported separately. E5 and H5 use only R1-accepted edits; H5 keeps its post-stratification over the types present in both sets and the minimum-information rule, and if too few distortion edits are accepted H5 is inconclusive as prescribed. (e1) No further human labels are added: the allocation is fixed as returned on 10 Nov (S-H 162, phase 2 344, edits 180). The 102 S-D claims and 120 distortion edits assigned to R2 stay without a human label, and clause (e) of D17 is withdrawn. (g) D7's per-annotator reporting of S-D/S-A results and the separate R1-R2 agreement are not available; the paper states that the only human annotator is the author.
  - D17 correction (2026-11-10, before any human label is read; found when the reference was first built and stopped on an unknown item id): the phase-2 sheet and the edit sheet R1 returned as sheet_items_R1.csv and items_R1.csv are the R2 packets (same item ids, order and claim texts as annotation/human/R2/P2/sheet_items_R2.csv and R2/EDITS/items_R2.csv); the S-H sheet is the shared S-H sheet. All 379 evidence quotes in the returned claim sheets are found in the source of the claim on their own row, so the answers belong to these items. The only human annotator (the author, called R1 in the paper) therefore labelled S-H (162) and the phase-2 half assigned to R2: S-D 102 of 204, S-A 187 of 2,508 strata claims drawn (of 376), S-N 55 of 108. That half is the other seeded random half of the same split, so D17 and its addendum apply unchanged with these counts: weights S-D 204/102 = 2, S-A 2508/187, S-N 719/55. Edits: the human checked the R2 edit packet, all 150 distortion edits and 30 contradiction edits (cross-check items); E5 and H5 use the accepted ones by rule (d1), so H5 rests on up to 150 checked distortion edits and E5 contradiction results on up to 30.
  - D18 (2026-11-10, AFTER the human reference was read and a first analysis run; disclosed as post-hoc analysis details in the paper): the analysis code (scripts/analysis/, checks/analysis.codex.md, checks/analysis_recompute.md) had to fix details the plan leaves open. (1) H1-H3 and prevalence use the phase weight times the D10 (c) report weight n_verified / n_kept; without the report weight H1 = 0.887 (Holm p about 0.064), so the verdict (inconclusive) does not depend on this choice, and both values are reported. (2) System scores use the announcement-cluster bootstrap of section 4a (as for all estimates), not the report-level bootstrap named in EXPERIMENT_PLAN.md; this plan wins. (3) H7 LLM side = GPT-5.5, the best development C2 macro-F1 among the four test LLMs in the cost test before the main runs (logs/cost_test.csv: 0.596 vs Sonnet 0.586). (4) H5: a hit is an exact MISREPRESENTED prediction; post-stratification uses the intended edit type, with the human's type as a sensitivity analysis. (5) The macro-F1 label set (labels with at least 10 claims) is fixed from all 506 reference claims. (6) Report-level prevalence is given as the S-H estimate plus a lower bound for all 205 random reports, since outside S-H only a sample of claims has a human label. (7) The error-analysis samples use seed 20261124. (8) Contamination (pre/post model cutoff) and cost-per-claim analyses are descriptive only. No hypothesis verdict changes under the alternatives named in (1) and (4).
