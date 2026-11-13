# AzDistortion

Data and code for the paper

> Mehdiyev, J.S. (2026). Limitations of Language Models in Detecting Misleading Information in Azerbaijani News. *Problems of Information Society*.

AzDistortion is a claim-level dataset of Azerbaijani news reports checked against the official announcements they report on. Each claim is labelled against the press release and, where one exists, the full decision text. The repository contains the data, the annotation guidelines, the pre-registration, every system prediction, the analysis outputs and the code of every pipeline stage.

## Contents

| Path | What it holds |
|---|---|
| `prereg.md` | Pre-registration (v1.2) with all deviations D1-D18 in section 10. |
| `annotation/guidelines_v1.2.md` | Annotation guidelines used for every label. |
| `prompts/` | Prompt of the test LLMs (`main.txt`) and the variants of E4 and E10. |
| `data/sources/` | Official texts: press release (`T1.txt`) and full decision text (`T2.txt`) of 145 announcements. |
| `sampling/` | Sampling frame, draw, report list with URLs, copy features and clusters. |
| `annotation/claims/` | Claim units of the 355 reports (2,020 random-sample and 1,573 benchmark claims). |
| `annotation/llm/` | Labels of the two LLM annotators for every claim. |
| `annotation/reference/` | Human reference labels (506 claims), design weights and the human check of the edit set. |
| `annotation/edits/` | Constructed edit set (300 edits). |
| `runs/` | Predictions and settings of every reported run. |
| `scripts/analysis/` | Every number, table and figure of the paper (`numbers.json`, `tables/`, `figures/`, `hypotheses.md`). |
| `scripts/` | Pipeline code (see below). |
| `colab/` | Notebook and bundle builder for the encoder runs on Google Colab. |
| `docs/DATA.md` | Description of every data file and column. |
| `docs/EXPERIMENTS.md` | Every model, hyperparameter and setting, with the reason for each choice. |

## Labels

| Label | Meaning |
|---|---|
| SUPPORTED | The official text states the claim, directly or by one simple calculation. |
| CONTRADICTED | The claim and the official text cannot both be true. |
| MISREPRESENTED | The official text addresses the point and the claim is not strictly incompatible with it, but a reader who believes the claim gets a wrong picture of the decision. Called **MISLEADING** in the paper. |
| NOT_IN_SOURCE | A fact the official text does not settle. |
| UNASSESSABLE | Vague claims and questions; not scored. |

The label was named MISREPRESENTED during annotation and is called MISLEADING in the paper; the definition is the same. Each MISREPRESENTED claim has a subtype: status, scope, actor, inference or dropped condition.

## News text

News reports are not redistributed. `sampling/reports_main.csv` gives the URL, outlet, date and headline of each report, and the claim files give each claim unit with its sentence span. The official texts are included in full.

## Reproducing the paper

The analysis runs from the released files alone and takes a few seconds:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/analysis/run_all.py
```

It rewrites `analysis/numbers.json`, `analysis/tables/`, `analysis/figures/` and `analysis/hypotheses.md`. The released outputs were produced this way and match the numbers in the paper.

Not every stage can be rerun from this repository alone. The analysis can. The system runs can, with API keys or a GPU. Collection, linking, claim splitting and the building of the human reference read web caches, pilot data and returned annotation sheets that are not released, so their scripts document how the data were made rather than run out of the box.

Rerunning the systems or the data collection needs `requirements-full.txt`, API keys in a `.env` file in the repository root (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `HF_TOKEN` for the gated AzBERT checkpoint), and, for the collection steps, network access to the outlets. Collection and annotation scripts write caches (`data/news_cache/`, `data/raw/`, `logs/`) that are not part of the repository. LLM outputs can differ between runs; the released predictions are the ones scored in the paper.

## Pipeline

All scripts run from the repository root, for example `python scripts/run_llm.py --help`.

**1. Sampling frame and draw**

| Script | Purpose |
|---|---|
| `list_cbar.py`, `list_tax.py`, `list_sosial.py` | List the announcements of the three issuers. |
| `fetch_candidates.py` | Crawl the 12-month sampling frame of one issuer with title, date and text. |
| `screen.py`, `screen_compare.py`, `make_r1_screening.py` | Eligibility screening by two LLM screeners, comparison, and the sheet for the human annotator. |
| `walk_order.py`, `draw.py`, `rewalk.py` | Seeded walk order and draw of 20 covered announcements per issuer (D1, D10). |
| `power_sim.py` | Precision simulation for the planned sample size. |

**2. Linking news reports to announcements**

| Script | Purpose |
|---|---|
| `news_pool.py`, `estimate_dates.py` | Pool of candidate news URLs from outlet sitemaps; dates of undated entries. |
| `link_news.py`, `link_chain.sh`, `link_trend.py`, `full_relink.py` | Candidate search and same-decision verification (D10 full-window relinking). |
| `verify_browser.py`, `verify_candidates.py`, `recall_audit.py`, `link_summary.py` | Verification of browser-found candidates, recall audit of the keyword step, link summaries. |
| `bench_select.py`, `bench_social.py`, `bench_build.py` | Selection of the benchmark sample by fixed report signals (D8). |
| `final_reports.py` | Final random-sample report list with the cap of four reports per announcement and report weights. |

**3. Sources and reports**

| Script | Purpose |
|---|---|
| `freeze.py`, `freeze_final.py` | Save each announcement and report page (raw bytes, text, tables, metadata). |
| `strike_extract.py` | Re-extract PDF text without struck-through wording. |
| `build_sources.py` | Build the press release (T1) and full text (T2) of each announcement (D3). |
| `copy_ratio.py` | Copy ratio, syndication flags and announcement clusters. |

**4. Claims and annotation**

| Script | Purpose |
|---|---|
| `split_claims.py` | Split reports into claims and measure boundary agreement on a second split. |
| `annotate_llm.py`, `merge_runs.py` | LLM annotators A1 and A2 and collection of their labels. |
| `make_human_sets.py`, `make_pair_viewer.py` | Draw the human label strata and build the annotation sheets. |
| `build_reference.py` | Build the human reference labels and design weights (D17). |
| `edit_set_v2.py` | Generate and check the constructed edit set (D14). |

**5. Detection systems**

| Script | Purpose |
|---|---|
| `run_llm.py`, `main_runs.py` | Run one test LLM on one source condition; merge, re-parse and log runs. |
| `run_api_main.sh`, `run_qwen_main.sh`, `run_e5.sh`, `run_e10.sh` | The exact run sequences of the main study. |
| `e3_retrieve.py` | BM25 and dense retrieval for E3. |
| `e5_inputs.py`, `verify_e5.py` | Inputs and completeness check of the edit-set runs. |
| `sys_common.py` | Shared code for the non-LLM systems (data, folds, passages, scoring). |
| `sys_majority.py`, `sys_tradml.py`, `sys_nli.py`, `sys_encoder.py` | Majority baseline, feature classifiers, zero-shot NLI, fine-tuned encoders. |
| `sys_devchoice.py`, `sys_select.py` | Development-set choices and the H7 selection inside the nested cross-validation. |
| `nonllm_inputs.py`, `nonllm_export.py`, `nonllm_verify.py` | Training labels, export to the run layout and integrity checks of the non-LLM runs. |
| `colab/make_bundle.py`, `colab/run_e2.py`, `colab/encoders.ipynb` | Encoder runs on Google Colab (D12). |

**6. Analysis**

| Script | Purpose |
|---|---|
| `scripts/analysis/run_all.py` | Runs the whole analysis. |
| `scripts/analysis/common.py` | Data loading, design weights, cluster bootstrap, metrics, Holm correction. |
| `scripts/analysis/agreement.py` | Agreement of the LLM annotators with the human annotator (RQ4). |
| `scripts/analysis/prevalence.py`, `analysis/where_distortion.py` | Prevalence and H1; regression for H2 and H3. |
| `scripts/analysis/systems.py`, `analysis/edits.py` | Scores of all systems (RQ2, RQ3, H4, H7) and of the edit set (H5). |
| `scripts/analysis/style_cues.py`, `analysis/error_samples.py`, `analysis/hypotheses.py` | E9, error-analysis samples and hypothesis verdicts. |

Some steps used the Claude Code and Codex command-line tools as screeners, claim splitters and annotators; the pre-registration and `docs/EXPERIMENTS.md` describe where.

## Frozen records

`prereg.md` and `annotation/guidelines_v1.2.md` are released exactly as frozen during the study. They mention internal review files (`checks/`, `EXPERIMENT_PLAN.md`, `prereg.sha256`) that are not part of this repository. `runs/main_inputs/code_inputs.sha256` and the `meta.json` files record the code as it was run. The released scripts differ from it only in comments, docstrings, file paths and log messages; the program logic is unchanged.

## Citation

Please cite the paper (see `CITATION.cff`).

## Licence

Code: MIT (`LICENSE`). Data, annotations, guidelines, pre-registration and documentation: CC BY 4.0 (`LICENSE-DATA`). Rights in news report text remain with the outlets, and the official texts keep the terms of their publishers.
