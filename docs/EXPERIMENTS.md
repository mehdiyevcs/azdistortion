# Experimental settings

This file lists every model, hyperparameter and setting used in the study, with the place in the repository where it is set and the reason for it. Reasons point to the pre-registration (prereg.md, sections and deviations D1-D18 in section 10), the prompts, development results in released files, or code comments in scripts/. "Reason not recorded" means that no released source gives a reason; none has been added here.

The label code `MISREPRESENTED` in the files is the label called MISLEADING in the paper. The exact configuration of every run (model id, effort, token limits, prompt hash, source cap, condition) is also stored in `runs/<run_id>/meta.json`, and the per-claim model id and effort are in `runs/<run_id>/predictions.csv`.

Conventions: paths are relative to the repository root. Line numbers are omitted; settings are located by script, function or constant name.

## Frozen inputs used by all systems

| Item | Value | Source |
|---|---|---|
| Guidelines | annotation/guidelines_v1.2.md, sha256 099ccfd615e9426a... | prereg.md section 10 (first bullet) |
| Main prompt | prompts/main.txt = prompts/e4_v1.txt, file sha256 d8c1612a043ffe98... The `prompt_sha256` field in runs/*/meta.json (4cd86262...) hashes the prompt text after the `#!` header lines are removed | prereg.md D11; scripts/run_llm.py `load_prompt`, `run` |
| Claims | annotation/claims/claims_s1.csv (3,593 claims); runs/main_inputs/*.csv (hashes in runs/main_inputs/inputs.sha256) | runs/main_inputs/inputs.sha256 |
| Sources | data/sources/<ann_id>/T1.txt, T2.txt, meta.json (`t1_is_act`) | scripts/run_llm.py `source_lines` |
| Runner code at the main runs | scripts/run_llm.py sha256 c5e4f43e... | runs/main_inputs/code_inputs.sha256 |

## 1. Claim splitting

| Setting | Value | Source | Reason |
|---|---|---|---|
| Segmenter S1 (all 355 reports) | Claude Code CLI 2.1.319, `claude -p --model sonnet` with `--strict-mcp-config --setting-sources project --no-session-persistence --tools ""`, run in an empty temporary directory, timeout 900 s | scripts/split_claims.py | prereg.md section 2 "Claims": S1 = Claude agent |
| S1 underlying model version | Not recorded. The call uses the CLI alias `sonnet`; stdout was saved as plain text without `--output-format json`, so no model id was logged | scripts/split_claims.py | - |
| S1 effort / thinking / temperature | Not set (CLI defaults); not recorded | scripts/split_claims.py | reason not recorded |
| Segmenter S2 (check set) | Codex CLI 0.163.0, `codex exec -s read-only --skip-git-repo-check -o <file> -`, timeout 1200 s | scripts/split_claims.py | prereg.md section 2: "Codex splits a random 20% of reports independently" |
| S2 underlying model | `gpt-6.1-sol` at the default reasoning effort. The model id is taken from the local Codex session logs of these runs, which are not part of this repository | - | - |
| S2 report set | Seeded 20% of reports, random.Random(20261117); 69 reports run, 68 scored | scripts/split_claims.py; annotation/claims/claims_s2.csv | prereg.md section 2 (20%) |
| Prompt | Inline constant `RULES` (no separate prompt file), with the round-2 list rule | scripts/split_claims.py `RULES` | The list rule was revised once after a round-1 boundary F1 of 0.623, below the 0.75 gate; prereg.md section 2: "revise once, redo" |
| Input format | HEADLINE line, then numbered paragraphs ("paragraph 1 is the lead"); page boilerplate lines removed by regex | scripts/split_claims.py | Boilerplate removed before part assignment; further reason not recorded |
| Retries | S1: one retry when the JSON is broken (one report, R0022, needed it); S2: none | scripts/split_claims.py | reason not recorded |
| Parallel workers | S1 4, S2 3 | scripts/split_claims.py | reason not recorded |
| Span matching | (1) exact `str.find` from the previous claim's position, then anywhere; (2) quote characters normalised to `"` and searched again (`span_match` = 1); (3) approximate window match with difflib ratio >= 0.9, windows stepped by 3 characters (`span_match` = 2); otherwise `span_found` = 0 and the model's `part` is kept | scripts/split_claims.py | Code comment: "quotes typed differently by the model". The 0.9 threshold: reason not recorded |
| Text part | headline if the span starts in the title, lead if in the first body paragraph, else body | scripts/split_claims.py | prereg.md section 3: the codebook defines headline / lead / body |
| Boundary F1 | One-to-one matching of character spans, Jaccard >= 0.5; gate 0.75. Result: F1 0.811 on 68 reports | scripts/split_claims.py | Gate: prereg.md section 2. The Jaccard 0.5 threshold: reason not recorded |
| Unlocated spans | 2 of 3,593 (R0029-C03, R0244-C05), kept with `span_found` = 0 | annotation/claims/claims_s1.csv | Kept and flagged; reason not recorded |

## 2. LLM annotators A1 and A2

### A1 (Claude Opus 5.5)

| Setting | Value | Source | Reason |
|---|---|---|---|
| Model id | `claude-opus-5-5` (Anthropic API, Python SDK); all 422 report calls returned `model: claude-opus-5-5` | scripts/annotate_llm.py | prereg.md section 1: A1 = Claude Opus. API instead of `claude -p`: D6 ("Claude models are called through the Anthropic API with the guidelines and the source in cached system blocks") |
| Effort / thinking | `output_config.effort = "high"`; adaptive thinking (cannot be disabled on this model) | scripts/annotate_llm.py | D6: Opus 5.5 cannot run without thinking. The level "high": reason not recorded |
| Temperature | Not sent | scripts/annotate_llm.py | D6: Opus 5.5 does not accept a temperature |
| max_tokens | 32,000 | scripts/annotate_llm.py | reason not recorded |
| Input | system block 1 = role + guidelines v1.2 + "Step 1: read A and write key_conditions"; system block 2 = source A (T1 + T2, or `<full_decision_text>none`); user = report text N + claim list (`claim_id [part]: text`) + JSON output spec | scripts/annotate_llm.py | prereg.md section 3 "LLM labels": source = press release + full text |
| Caching | Both system blocks `cache_control: ephemeral` (5 min); reports of one announcement run in one worker so later reports read the cache. Valid outputs are skipped on re-run | scripts/annotate_llm.py | Code comment: "its first report writes the prompt cache ... the rest read it" |
| Retries | SDK `max_retries=4`, timeout 1800 s; then up to 2 attempts per report (30 s wait after an API error); valid = JSON with every claim_id. 38 of 422 reports needed attempt 2 | scripts/annotate_llm.py | reason not recorded |
| Workers | `--jobs`, default 3 | scripts/annotate_llm.py | reason not recorded |
| Cost | $44.5 total | - | - |

### A2 (Codex CLI)

| Setting | Value | Source | Reason |
|---|---|---|---|
| Interface | `codex exec -s read-only --skip-git-repo-check -o <out> -` with the full prompt on stdin, run in an empty temporary directory, timeout 2400 s | scripts/annotate_llm.py | prereg.md section 1: A2 = Codex CLI (OpenAI) |
| Model | Codex CLI 0.163.0 with the gpt-6.1-sol model at the default reasoning effort; the model id is taken from the local Codex session logs of the annotation runs, which are not part of this repository. Sandbox read-only, approval policy never | - | - |
| Temperature | Not settable through `codex exec`; not set | scripts/annotate_llm.py | D6 (GPT-5.x reasoning models run without a temperature). For the Codex model itself: reason not recorded |
| Prompt | One self-contained prompt per report: instruction not to open files, run commands or use outside knowledge, guidelines v1.2, source A, report N, claims, same JSON spec as A1 | scripts/annotate_llm.py | Same guidelines as A1; code docstring: "The annotators are blind to each other" |
| Caching | None at model level; valid outputs reused on re-run | scripts/annotate_llm.py | - |
| Retries | Up to 2 attempts per report; all 422 succeeded on the first attempt | scripts/annotate_llm.py | reason not recorded |

Collection: `annotate_llm.py A1|A2 --collect` writes annotation/llm/labels_A1.csv and labels_A2.csv for the 3,593 current claims. Rows of the 67 reports dropped by D10 are kept apart.

## 3. Edit generation (Claude Opus 5.5)

| Setting | Value | Source | Reason |
|---|---|---|---|
| Model | `claude-opus-5-5`, Anthropic API, effort high, adaptive thinking, no temperature, max_tokens 32,000; all 107 calls returned model claude-opus-5-5, stop_reason end_turn | scripts/edit_set_v2.py | prereg.md section 6 and D14: generator Claude Opus 5.5. Effort level: reason not recorded |
| Calls | One call per announcement covering all its base claims; guidelines + source A in two cached system blocks; first pass 57 calls, rebalancing pass 50 calls; $10.71 total | scripts/edit_set_v2.py | reason not recorded |
| Long sources | If T1 + T2 > 60,000 chars: T1 whole + T2 chunks of 1,500 chars with the highest word overlap (words >= 4 letters) with the base claims, up to 40,000 chars, in document order | scripts/edit_set_v2.py | Thresholds: reason not recorded |
| Base claims | 150 random-sample claims, A1 = A2 = SUPPORTED, outside S-H, no unsure/split_error flag, >= 5 words, de-duplicated; 50 per issuer; tiered preference (number/date, then condition/scope/actor markers, then rest); seed random.Random(20261124) | scripts/edit_set_v2.py | D14 |
| Per-announcement cap | Code `CAP = 4`; realised maximum is 3 (37 announcements with 3); D14 text says "at most 3" | scripts/edit_set_v2.py; annotation/edits/edit_set_v2.csv | See "Known gaps" |
| Subtype rotation (MISREPRESENTED edit) | Target type `MIS_TYPES[i % 5]` over status, scope, actor, inference, dropped_condition in base-claim order (issuer, then draw order): 30 targets per type. If infeasible, the generator uses another type and reports it (`target_feasible`, `used_type`) | scripts/edit_set_v2.py | prereg.md section 6: edit types fixed before generation; D14: types rotate over the five types |
| CONTRADICTED edit type | Chosen by the generator from amount, date, actor, scope, status, condition | scripts/edit_set_v2.py | reason not recorded |
| Automatic checks | Evidence is a substring of T1/T2; edit differs from base; MISREPRESENTED edit differs from CONTRADICTED edit; failures regenerated once | scripts/edit_set_v2.py | reason not recorded |
| Rebalancing | Second pass asking for status distortions for bases whose first-pass type had > 30 edits; feasible candidates replace in seeded order random.Random(20261125) while status < 30 | scripts/edit_set_v2.py | The first pass gave 10 status edits (20 of 30 status targets judged infeasible); D14 |

## 4. Test LLMs (E1, E3, E4, E5, E10, stability)

All main-study LLM runs use scripts/run_llm.py with `--prompt prompts/main.txt --src-root data/sources --workers 4 --cost-cap <cap>` (scripts/run_api_main.sh, scripts/run_qwen_main.sh). Exact ids and effort are confirmed in every row of runs/*/predictions.csv (columns `model_id`, `effort`). The shell scripts call scripts/main_runs.py to merge the C2 runs (C2 predictions for claims with a full text plus C1 predictions copied for the others), to re-parse cached outputs and to log costs.

| Setting | Haiku | Sonnet | GPT-5.5 | Qwen |
|---|---|---|---|---|
| Model id | `claude-haiku-5-5` | `claude-sonnet-5-5` | `gpt-5.5-2026-04-23` | `mlx-community/Qwen2.5-7B-Instruct-4bit` (mlx-lm, local) |
| Source in run_llm.py | `CLAUDE_API_MODELS` | `CLAUDE_API_MODELS` | `OPENAI_PRICE` keys, `call_openai` | `QWEN_REPO` |
| API | Anthropic Messages, streaming | same | OpenAI Responses (plain HTTPS, no SDK) | local MLX |
| Effort / thinking | `output_config.effort = "low"` (adaptive thinking) | `"medium"` | `reasoning.effort = "low"` (`OPENAI_EFFORT`) | none (greedy decoding) |
| Temperature | not sent (not accepted) | not sent | not sent | 0.0 (`make_sampler(temp=0.0)`) |
| Max output tokens | 8,000 | 8,000 | 4,000 | 16 new tokens |
| Max source chars | 400,000 | 400,000 | 400,000 | 20,000 (`MAX_CHARS`) |
| Truncated claims | none (`truncated` False) | none | none | yes, logged per claim (e.g. 51 of 2,020 in e1_qwen_C1_random) |
| Prompt caching | instructions and source as 2 cached system blocks (ephemeral, 5 min); claims of one announcement in one worker | same | instructions + source in `instructions` (automatic prefix cache), `prompt_cache_key` = announcement, condition, prompt hash, k | none |
| Caching source | `build_claude_request`, `run` | same | `call_openai`, `run` | `call_qwen` |

Hardware for Qwen: Apple M4 Pro Mac, 24 GB.

Reasons:
- Model choice: prereg.md section 5 lists Haiku, Sonnet, "a general OpenAI GPT-5.x model (not Codex)" and "one open-weight LLM". GPT-5.5 was chosen as the GPT-5.x model for budget reasons. The choice of Qwen2.5-7B-Instruct and of the 4-bit MLX build: reason not recorded.
- Effort, Claude: code comment in run_llm.py: low for Haiku, medium for Sonnet, "since one-label classification needs little thinking", set before the E4 runs. A Haiku medium-effort run on dev (runs/e4_haiku_C2_v5_medium, dev macro-F1 0.685 vs 0.748 at low) did not change the choice.
- Effort, GPT-5.5: code comment "lowest reasoning effort used in the cost test" (`OPENAI_EFFORT`). No further reason recorded.
- Temperature: D6 (Claude 5.5 models do not accept a temperature; GPT-5.x are reasoning models run without one; "temperature 0 where settable" applies only to Qwen and the encoders).
- Max tokens 8,000 (Claude): code comment "covers adaptive thinking + a one-line answer". 4,000 (GPT): reason not recorded. 16 (Qwen): code comment "LABEL: NOT_IN_SOURCE is about 8 tokens".
- Source cap 400,000: code comment "raised so no main-study source (max T1+T2 about 160k chars) is cut for API models (prereg section 5: cut only beyond the context)".
- Qwen cap 20,000 chars: reason not recorded. It is not a dev-chosen top-k as prereg.md section 5 asks ("cut to the top-k retrieved chunks (k fixed on dev)").

Qwen truncation (run_llm.py `cut`, `build_claude_request`): lines of T1/T2 are scored by the pilot overlap score |claim tokens & line tokens| / sqrt(1 + |line tokens|); the best lines are kept up to the cap and put back in document order. If the press release fits, it is kept whole and only T2 is cut; otherwise T1 and T2 are cut together. The cut is claim-specific and logged (`truncated`, `src_chars`).

Request content, same for all four systems (run_llm.py `build_claude_request`):
- instruction block = prompts/main.txt (in C0 plus "You do not have the official text A; judge from your knowledge only.");
- source block = `<A id=...><press_release>...</press_release>[<full_decision_text>...]</A>`;
- user turn = `CLAIM (from a news report): <claim_text>`, without the claim's text part.

Conditions and copying:
- C2 is called only for claims with a T2 (has_t2 = 1 and not t1_is_act). Other C2 rows are copied from C1 into the merged `e1_<sys>_C2_<sample>` runs (`copied_from_C1` = 1); see runs/e1_haiku_C2_random/meta.json.
- t1_is_act announcements get C2 = C1 (D3 and D3 addendum; run_llm.py `source_lines`).
- Benchmark: C1 and C2 only; GPT-5.5 runs C2 only (D9, for budget reasons).

Label parsing (strict for every `--prompt` run; run_llm.py `parse_label`):
1. The last `LABEL: X` line; a second, different upper-case label on that line makes it invalid.
2. Else a first line that is exactly one label (code comment: added because "Haiku 5.5 sometimes appends an echo such as '<A id=...>'").
3. Else the last line starting with a label.
4. Otherwise invalid.

Retries and errors:
- An invalid output is retried once (prereg.md section 5; run_llm.py `run`); if still invalid it is UNPARSEABLE.
- An Anthropic `stop_reason` "refusal" or an OpenAI refusal gives REFUSED, with no retry (`call_claude_api`, `call_openai`).
- UNPARSEABLE and REFUSED are scored as SUPPORTED (prereg.md section 5; run_llm.py `score`).
- Transport retries: Anthropic SDK `max_retries=4`, timeout 600 s (`anthropic_client`). OpenAI: 4 attempts on HTTP 429/5xx (wait 5 s x attempt) and on network errors (wait 10 s x attempt), timeout 300 s (`call_openai`).
- Errored claims are not cached. run_api_main.sh runs every run twice, so the second pass retries them (code comment in scripts/run_api_main.sh).
- Qwen is greedy, so its retry repeats the same output.

Response cache and resume: every response is stored per claim during the run. A resumed record must match the configuration fingerprint (model, condition, effort, max tokens, prompt text, placement, source root, cap, builder version), the claim-text hash and the request hash, or the run stops (run_llm.py `run`).

Prompt and effort selection (dev = 155 pilot claims; selection rule prompts/e4_rule.txt, written before the E4 runs):
- E4 dev runs (Haiku, low, C2; runs/e4_haiku_C2_v1 to v5, macro-F1 on the pilot gold labels v1 with labels >= 5): v1 0.723, v2 0.621, v3 0.711, v4 0.686, v5 0.748; repeats v1 0.708 (runs/e4_haiku_C2_v1_rep2), v5 0.617 (runs/e4_haiku_C2_v5_rep2).
- The rule picked v5 on one run. The frozen prompt is v1, because "repeated runs showed the v1-v5 difference was within run-to-run noise" (D11).
- A variant with a headline line and the claim part (runs/e4_haiku_C2_main) was tried once and not adopted. Reason not recorded beyond D11.
- Dev E4 runs used max_chars 150,000 (runs/e4_haiku_C2_v1/meta.json); the main runs used 400,000.

Cost test (runs/dev_choice/cost_test.csv; systems Haiku, Sonnet, GPT-5.5, GPT-5.4-mini, Qwen, and Opus on a 20-claim sample):
- Run on the 155 development claims with the built-in ASK prompt (no `--prompt`; run_llm.py `ASK`) and max_chars 150,000.
- The Claude effort of these runs is not recorded (`effort: null`). The run_llm.py comment states the API defaults (Haiku medium, Sonnet high); whether these applied is an inference, not a record.
- This test fixed the LLM side of H7: GPT-5.5 C2 macro-F1 0.596 vs Sonnet 0.586 (D18 (3)).

## 5. Majority baseline and feature classifiers

| Setting | Value | Source | Reason |
|---|---|---|---|
| Majority (S0) | Predicts SUPPORTED for every claim and condition (`model_id` majority:SUPPORTED); the most frequent fit label per outer training part is logged | scripts/sys_majority.py | prereg.md section 5 (majority baseline) |
| Training labels | Human label (annotation/reference/reference_R1.csv, 506) where present, otherwise agreed A1 = A2 label (3,003); 3,509 labels | scripts/sys_common.py | prereg.md 4a "Training labels" |
| Variants | merged (primary); `_hum` = human labels only (secondary); `_edits` = plus 150 accepted edits (120 MISREPRESENTED + 30 CONTRADICTED), random sample only | scripts/sys_common.py | prereg.md 4a (secondary variant); `_edits`: E2 variant b (scripts/sys_encoder.py docstring) |
| Features C1/C2 | token and 5-char-stem coverage of the source; best-passage stem coverage and Jaccard; top-3-passage coverage; claim word 3-gram and 5-gram copy share; number count, match share, mismatch (source and best passage), percent sign; year / dd.mm.yyyy / day-month dates, match share, mismatch; 7 cue groups (hedge, done, universal, future, negation, inference, plan_list) counted in the claim, present in the best passage, in source, "only in claim"; part flags; claim length; log source words; has_t2; number of passages | scripts/sys_tradml.py | prereg.md section 5: "logistic regression on overlap and cue features, gradient boosting as a check". The specific cue groups and stem length 5: reason not recorded |
| Features C0 | TF-IDF of claim word 1-2-grams (min_df 2, sublinear tf, fitted on the training part) + claim-only features | scripts/sys_tradml.py | Docstring: "the claim-words-only version". Further reason not recorded |
| Passages | sys_common.chunk (sentences/lines, merged to >= 6 words, cut at 120 words), ranked by the pilot overlap score | scripts/sys_common.py `chunk`, `rank_passages` | Code comment: pilot retrieval score |
| Logistic regression | sklearn LogisticRegression, lbfgs, class_weight balanced, max_iter 5000, features standardised on the training part; grid C in {0.1, 1, 10} | scripts/sys_tradml.py | Grid: prereg.md 4a. Balanced weights: reason not recorded |
| Gradient boosting | sklearn GradientBoostingClassifier, random_state 1, default learning_rate 0.1, balanced sample weights; grid max_depth {2, 3} x n_estimators {100, 300} | scripts/sys_tradml.py | Grid: prereg.md 4a. Balanced weights: reason not recorded |
| Chosen values | Chosen per outer fold by the inner CV (ties: first in grid order), so they differ by fold. Example, random sample, merged labels, C2: logreg C = 0.1 (2 folds), 1 (2), 10 (1); gbm (2, 100) in 3 folds, (3, 100) in 2 | runs/colab_results/results_{random,benchmark}/inner_tradml*.csv, rows with inner_fold = chosen | prereg.md 4a nested CV |
| CV | Outer 5-fold, inner 3-fold StratifiedGroupKFold(shuffle=True, random_state=20261111), grouped by cluster (sampling/clusters.csv), stratified by training label | scripts/sys_common.py `outer_folds` | prereg.md 4a (5/3 folds, grouped, seed 20261111). Stratification: code comment "a design choice"; further reason not recorded |
| Inner score | macro-F1 over the label set (SUPPORTED, MISREPRESENTED, NOT_IN_SOURCE), on inner-validation claims with a human label, design-weighted (`human_weighted`) | scripts/sys_common.py; manifests `inner_score` | prereg.md 4a; code comment: "the same objective and exclusion as the outer evaluation" |
| Library versions | scikit-learn 1.9.1, numpy 2.5.4, scipy 1.18.1 | runs/colab_results/results_*/manifest_tradml*.json `libraries` | - |
| Hardware | Mac (Apple M4 Pro, 24 GB) | - | - |

## 6. Zero-shot NLI (S1)

| Setting | Value | Source | Reason |
|---|---|---|---|
| Model | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`, revision b5113eb38ab63efdd7f280f8c144ea8b13f978ce | scripts/sys_nli.py; scripts/sys_common.py `REVISIONS` | Docstring: the pilot model. prereg.md section 5: "mDeBERTa-v3 XNLI with retrieval" |
| Hypothesis / premise | No template: the claim text itself is the hypothesis; each of the top-k passages is a premise. C0: premise "." | scripts/sys_nli.py | C0 premise ".": docstring "the pilot's no-source ablation" |
| Passage ranking | sys_common.chunk + pilot overlap score | scripts/sys_nli.py | as section 5 |
| Tokenisation | max_length 512, truncation longest_first, batch 16 | scripts/sys_nli.py | Docstring: "so an over-long claim cannot crash" |
| Aggregation | CONTRADICTED if any passage has P(contradiction) > 0.5; else SUPPORTED if max P(entailment) > 0.5; else NOT_IN_SOURCE. Cannot output MISREPRESENTED or UNASSESSABLE | scripts/sys_nli.py | reason not recorded |
| k | Frozen k = 3 (E1, E5); k = 1 and k = 5 exported as E3 variants (runs/e3_nli_k1_*, runs/e3_nli_k5_*) | scripts/sys_nli.py `K_FROZEN` | Dev rule 2 of scripts/sys_devchoice.py (written before the run): dev C2 macro-F1 k1 0.3084, k3 0.3326, k5 0.2970; tied set {3}, so k = 3 |
| Device | Apple MPS | - | - |
| Libraries | torch 2.15.0, transformers 5.22.2, tokenizers 0.23.3 | - | - |

## 7. Fine-tuned encoders (E2) and H7 selection

| Setting | Value | Source | Reason |
|---|---|---|---|
| Models (pinned revisions) | `FacebookAI/xlm-roberta-base` e73636d4f797dec63c3081bb6ed5c7b0bb3f2089; `allmalab/bert-base-aze` 5fd824965138a261552fc5ca333e91f4fa45cc67; `microsoft/mdeberta-v3-base` a0484667b22365f84929a935b5e50a51f71f159d | scripts/sys_encoder.py `MODELS`; scripts/sys_common.py `REVISIONS`; meta_enc_*.json `model_revision` | prereg.md 4a candidate list; Azerbaijani BERT "if available" (prereg.md section 5), found public, MIT-licensed and gated |
| Learning-rate grid | {1e-5, 2e-5, 3e-5} | scripts/sys_encoder.py; meta `lr_grid` | prereg.md 4a |
| Epochs, batch, max length | 3, 16, 512 | scripts/sys_encoder.py; meta | prereg.md 4a |
| Micro-batch | 8 by default; Colab runs used 16 (meta `micro_batch` 16); gradients accumulated to 16 | scripts/sys_encoder.py; colab/run_e2.py | Docstring of run_e2.py: "how the batch of 16 is split for memory; gradients are accumulated to 16, so the optimisation is the same" |
| Optimizer and schedule | AdamW, weight decay 0.01, linear schedule with 10% warm-up, grad-norm clip 1.0 | scripts/sys_encoder.py | reason not recorded |
| Loss and class weights | Cross-entropy with balanced weights n / (L x n_l) computed on each training part; head labels = labels present in the training part | scripts/sys_encoder.py | prereg.md 4a ("balanced class weights") |
| Head initialisation | New head (and mDeBERTa pooler) re-initialised under the training seed, N(0, initializer_range), zero bias | scripts/sys_encoder.py | Code comment: "Equivalent to from_pretrained per fit, without reloading" |
| Precision | fp32 (no autocast or fp16 in the code) | scripts/sys_encoder.py | reason not recorded |
| Input | text_a = claim, text_b = up to top-3 passages (pilot overlap ranking) that fit the 512-token budget after the claim and special tokens, put back in document order; best passage truncated if it alone does not fit; truncation `only_second`, or `longest_first` if the claim is longer than 256 tokens. C0 = claim alone | scripts/sys_encoder.py | Top-3: dev rule 1 of scripts/sys_devchoice.py (`TOP_K_FROZEN = 3`): fill-512 0.1478 vs top-3 0.1282, difference 0.0196 <= 0.02 (`TIE`), so the pre-stated tie rule kept top-3. With 3 optimizer steps on dev, this was decided by the tie rule, not by a meaningful difference |
| Seeds | lr selected with training seed 1; the chosen lr refit with seeds 1, 2, 3 | scripts/sys_encoder.py | prereg.md 4a seeds 1-3. Single selection seed: reason not recorded |
| Nested CV | Outer 5 x inner 3 grouped by cluster, same folds as section 5; selection by mean inner macro-F1 (human_weighted); ties: first lr in grid order | scripts/sys_encoder.py; scripts/sys_common.py | prereg.md 4a |
| Chosen lr | Varies by fold and run; listed in runs/colab_results/results_*/inner_enc_*.csv, rows with inner_fold = chosen. mDeBERTa chose 1e-5 in every fold and run | inner_enc_*.csv | prereg.md 4a |
| Hardware | Random bundle: NVIDIA L4 / CUDA 13.2. Benchmark bundle: NVIDIA A100-SXM4-80GB / CUDA 13.2. One results folder is bound to one GPU type | runs/colab_results/results_*/run_info.json `hardware`; colab/run_e2.py | D12 (Colab Pro GPU). GPU type per bundle: reason not recorded |
| Software (Colab) | Python 3.13.16; pinned installs: torch 2.15.0, transformers 5.22.2, tokenizers 0.23.3, scikit-learn 1.9.1, numpy 2.5.4, scipy 1.18.1, sentencepiece 0.2.3, huggingface_hub 2.4.0, safetensors 0.8.0, protobuf 7.36.2; Colab's preinstalled torchaudio, torchvision and peft uninstalled | meta_enc_*.json `python`; manifest_*.json `libraries`; colab/encoders.ipynb install cell | Same versions as the Mac runs, so candidate manifests match (checked by scripts/sys_select.py). Uninstall: a CUDA version mismatch broke the transformers import |
| Run order | (1) XLM-R and AzBERT C2; (2) mDeBERTa C2; (3) all C1; (4) all with edits; (5) C0; (6) human-only C2. Benchmark: 1-3 and 6 | D12; colab/make_bundle.py; colab/HOWTO_colab.md | D12. Benchmark skips 4-5 by D9 |
| Not completed | Random priority 4, mDeBERTa with edits under C1: stopped in outer fold 0 (the log ends mid-fold); only C2 exported | runs/colab_results/results_random/logs/p4_mdeberta_C2C1_edits.log | D12: unfinished runs are dropped |

H7 selection (scripts/sys_select.py):
- Per outer fold, the candidate with the highest inner score is taken among logreg, gbm, xlmr, mdeberta, azbert (ties broken in that order), with its refit prediction.
- Protocol checks: C2, seeds 1-3, the prereg grids, top-k 3, pinned revisions, human-weighted inner scoring.
- Random sample, C2: gbm in folds 0 and 3, AzBERT in 1 and 2, XLM-R in 4. Benchmark: gbm in 0, 1 and 3, logreg in 2 and 4 (runs/colab_results/results_*/selection_h7_C2.csv).
- The LLM side of H7 is GPT-5.5, the best dev C2 macro-F1 in the cost test, 0.596 vs Sonnet 0.586 (D18 (3)).

Dev choices: scripts/sys_devchoice.py applies both rules on the dev claims with `--min-label-n 5` and encoder runs with `--epochs 1 --max-steps 3`. The label threshold is 5 on dev because with the pre-registered threshold of 10 only SUPPORTED qualifies on the 155 dev claims.

## 8. Retrieval (E3)

| Setting | Value | Source | Reason |
|---|---|---|---|
| Claims | 949 claims with a T2 (random_t2 + benchmark_t2), C2 source | scripts/e3_retrieve.py; runs/main_inputs/e3_retrieval_meta.json | Docstring: claims whose announcement has a T2 (D3) |
| Passages | sys_common.chunk(min_words=6, max_words=120) over T1 + T2, the same passages as NLI | scripts/e3_retrieve.py; e3_retrieval_meta.json `chunker` | Docstring: same passages as S1 |
| BM25 | Own implementation, Okapi BM25, k1 = 1.2, b = 0.75, idf = ln(1 + (N - n + 0.5) / (n + 0.5)), over the passages of one announcement; tokens = sys_common.toks (Azerbaijani-aware lowercasing), no stemming | scripts/e3_retrieve.py | prereg.md section 7 (retrieval variants, exploratory). k1 and b values: reason not recorded |
| Dense | `intfloat/multilingual-e5-base`, revision d128750597153bb5987e10b1c3493a34e5a4502a; "query: " / "passage: " prefixes, mean pooling, L2-normalised, cosine; max length 512; batch 32; MPS | scripts/e3_retrieve.py; e3_retrieval_meta.json | Model choice and size: reason not recorded |
| Top-k | Top 5 stored; runs use k = 1, 3, 5 (first k), passages given in document order as `<retrieved_passages k=...>` | scripts/e3_retrieve.py; scripts/run_llm.py `build_claude_request` | reason not recorded |
| Systems | Haiku only (6 runs e3_haiku_{bm25,e5}_k{1,3,5}, effort low, prompts/main.txt); NLI k1/k5 (overlap ranking, not BM25/E5) | scripts/run_api_main.sh | Haiku only: for budget reasons |

## 9. E4 prompt variants, E10 two-pass judge, stability re-runs

| Setting | Value | Source | Reason |
|---|---|---|---|
| E4 test check | Haiku (low), C2 request, prompts e4_v1 to e4_v5, all 2,020 random claims (runs e4t_haiku_C2_v{1..5}_random) | scripts/run_api_main.sh; runs/e4t_*/meta.json | prereg.md section 7 (prompt variants, exploratory). Haiku only: reason not recorded |
| E4 variants | v1 base (= main); v2 full guidelines v1.2 instead of definitions; v3 one reason sentence before the label; v4 source in the user turn; v5 no 4-step decision order | prompts/e4_v*.txt `#!` headers | reason not recorded |
| E10 | Haiku (low), C2, all random and benchmark claims; pass 1 prompts/e10_literal.txt (no MISREPRESENTED), pass 2 prompts/e10_implicature.txt | runs/e10_*/meta.json; scripts/run_e10.sh | D16 (exploratory) |
| E10 combination | CONTRADICTED if pass 1 = CONTRADICTED; UNASSESSABLE if pass 1 = UNASSESSABLE; MISREPRESENTED if pass 2 = MISREPRESENTED and pass 1 in {SUPPORTED, NOT_IN_SOURCE}; else the pass 1 label | scripts/analysis/systems.py | Fixed in D16 before any human label was seen |
| Stability | Haiku (low) and Sonnet (medium), 2 re-runs each, C2, 200 random claims (random.Random(20261123), runs/main_inputs/stab200.csv), prompts/main.txt; compared with the E1 C2 run: pairwise agreement and kappa, all-three-same share, Fleiss kappa | scripts/run_api_main.sh; runs/stab_*; scripts/analysis/systems.py | D6: "Run-to-run variation is measured by the stability re-runs" |

## 10. Statistics

| Setting | Value | Source | Reason |
|---|---|---|---|
| Bootstrap | Two-stage cluster bootstrap: announcement clusters (union-find), then claims within the S-D, S-A and S-N strata; 2,000 replicates; seed 20261110 | scripts/analysis/common.py; analysis/numbers.json `meta` | prereg.md 4a; D17 addendum (a2); D18 (2) |
| Design weights | S-H 1; S-D 204/102; S-A 2508/187; S-N 719/55. RQ1, H1-H3 and E9 (random) multiply these by the report weight n_verified / n_kept | scripts/analysis/common.py; annotation/reference/weights.json | D17 correction; D18 (1) (post-hoc) |
| Holm families | F1 {H1, H2, H3}; F2 the 8 H4 tests; F3 {H5 per system, H7}; F4 {H6, not tested} | scripts/analysis/hypotheses.py; scripts/analysis/common.py | prereg.md 4a |
| Decision rule | Supported if Holm p < 0.05 and the estimate reaches the SESOI; one-sided bootstrap p = (1 + count at or beyond null) / (B + 1) | prereg.md 4a; scripts/analysis/hypotheses.py | prereg.md 4a |
| SESOI | H1 share >= 0.6; H2, H3 OR >= 1.5; H4 difference >= 0.05; H5 <= -0.05; H6 >= 0.05; H7 >= 0.05 | prereg.md section 4 table; scripts/analysis/hypotheses.py | prereg.md section 4 |
| H2/H3 model | LogisticRegression(C=1.0, solver lbfgs, intercept_scaling=100, max_iter=5000), sample_weight = weights; > 5% degenerate replicates gives inconclusive | scripts/analysis/where_distortion.py | prereg.md 4a. Note: scikit-learn applies `intercept_scaling` only with the liblinear solver; with lbfgs the intercept is unpenalised anyway |
| Macro-F1 label set | Labels with >= 10 raw (unweighted) claims among all 506 reference claims: SUPPORTED, MISREPRESENTED, NOT_IN_SOURCE; zero_division = 0 | scripts/analysis/common.py; analysis/numbers.json `label_set_macro_f1` | prereg.md section 4 "Macro-F1"; D18 (5) (post-hoc: fixed from all 506 claims) |
| H5 hit | Exact MISREPRESENTED prediction; post-stratified by intended edit type | scripts/analysis/hypotheses.py | D18 (4) (post-hoc) |
| Error-analysis seed | 20261124 | scripts/analysis/common.py | D18 (7) |
| Other seeds | sampling 20261109, CV 20261111, S-A 20261112, S-H 20261113, report cap 20261120, edit base 20261124, edit packets 20261125, stability 20261123, S2 split 20261117 | prereg.md 4a "Seeds"; D10 (c) and D10 addendum; scripts/edit_set_v2.py; scripts/split_claims.py | prereg.md 4a; respective deviations |

## 11. Software and hardware versions

| Component | Version | Source | Note |
|---|---|---|---|
| Python (Mac) | 3.15.1 | - | recorded at the start of the main study |
| Python (Colab) | 3.13.16 | meta_enc_*.json `python` | - |
| OS and hardware (Mac) | macOS-15.8.2-arm64; Apple M4 Pro, 24 GB | - | - |
| Claude Code CLI | 2.1.319 | - | used for the S1 claim split |
| Codex CLI | 0.163.0 | - | A2 and the S2 split |
| torch / transformers / tokenizers | 2.15.0 / 5.22.2 / 0.23.3 | runs/colab_results/results_*/manifest_*.json `libraries`; requirements-full.txt | recorded at run time |
| scikit-learn / numpy / scipy / sentencepiece | 1.9.1 / 2.5.4 / 1.18.1 / 0.2.3 | same; requirements.txt | recorded at run time |
| huggingface_hub / safetensors / protobuf (Colab) | 2.4.0 / 0.8.0 / 7.36.2 | colab/encoders.ipynb install cell | pinned for Colab |
| mlx / mlx-lm | 0.32.4 / 0.32.2 | requirements-full.txt | installed versions after the runs; not logged at run time |
| anthropic SDK | 2.6.0 | requirements-full.txt | installed version after the runs; not logged at run time. The SDK version used for A1 is not recorded |
| pandas (analysis) | 3.1.0 | requirements.txt | installed version after the runs; not logged at run time |
| OpenAI API | plain HTTPS to /v1/responses, no SDK | scripts/run_llm.py `call_openai` | - |

## Known gaps

1. The A2 model (`gpt-6.1-sol`, default reasoning effort) and the S2 claim-split model are recorded only in local Codex session logs, which are not part of this repository. The per-report A2 meta records do not contain the model id.
2. The S1 claim-split model version and effort are not recorded (CLI alias `sonnet`, plain-text output).
3. The Claude effort in the cost test, which fixed the LLM side of H7 (D18 (3)), is not recorded (`effort: null`). The comment in run_llm.py gives the API defaults, not a record of the request.
4. The edit-base cap differs: the code says 4 per announcement, D14 says 3, and the realised maximum is 3.
5. No recorded reason for: Qwen's 20,000-character cap (prereg.md section 5 asks for a dev-chosen k); GPT-5.5 max_output_tokens 4,000; A1 and edit-generator effort "high" and max_tokens 32,000; BM25 k1/b; the choice of multilingual-e5-base; encoder optimizer, warm-up, weight decay and fp32; the span-match 0.9 and boundary-F1 Jaccard 0.5 thresholds; the GPU type per Colab bundle.
6. The choice of Qwen2.5-7B-Instruct (4-bit) as the open-weight model is not backed by a recorded comparison with other open-weight models.
7. No reason is recorded for the set of E4 prompt variants (v1-v5). Claims are sent in file order, and the label is parsed from a `LABEL:` line rather than JSON output.
8. The run-time versions of mlx, mlx-lm, the anthropic SDK and pandas were not logged. The values above are the versions installed after the runs.
9. The Anthropic model strings are the ids `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5` as returned by the API. No dated snapshot id is recorded.
10. Each model's stated training cutoff (prereg.md section 5, "Contamination") is not recorded in scripts/ or analysis/.
11. Encoder runs are not bit-reproducible on GPU or Apple MPS, and results depend on the GPU type (L4 vs A100).
