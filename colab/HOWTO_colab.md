# Encoder training (E2) on Google Colab

The fine-tuned encoders (XLM-R, AzBERT, mDeBERTa-v3) were trained on Google Colab GPUs (an NVIDIA L4 for the random sample, an A100 80 GB for the benchmark sample). The returned results are in `runs/colab_results/`. This note explains how to run the training again.

## What you need

- A Colab runtime with a GPU.
- A Hugging Face token with access to the gated checkpoint `allmalab/bert-base-aze`.
- Two data bundles built with `colab/make_bundle.py --final` (see `python colab/make_bundle.py --help`). The arguments used for the study bundles (claims file, reference labels, training labels, edit set, E5 edits) are recorded in `colab/bundle_random.manifest.json` and `colab/bundle_benchmark.manifest.json` (`data_args`, `edits_arg`, `e5_arg`). The training labels and edit inputs are written by `scripts/nonllm_inputs.py`. The random bundle covers C0, C1 and C2 with the edit set; the benchmark bundle covers C1 and C2 only (D9).

Each study bundle holds the frozen labels, official texts, clusters, folds and the feature-classifier results (`seed_results` in the manifest), so the H7 selection can run at the end. It holds no keys.

## Steps

1. In Google Drive create `MyDrive/azd_colab/` and upload the bundle zips there.
2. Open `encoders.ipynb` in Colab and set `BUNDLE_NAME = "random"` (or `"benchmark"`) in the first code cell.
3. Choose a GPU runtime.
4. Add the secret `HF_TOKEN` (key icon in the left bar) and switch on notebook access.
5. Run all. The last cell writes `MyDrive/azd_colab/results_<bundle>.zip`.

## Run order and behaviour

- Priorities follow D12: (1) XLM-R and AzBERT under C2, (2) mDeBERTa-v3 under C2, (3) all three under C1, (4) all three trained with the edit set, (5) all three under C0, (6) all three under C2 trained on human labels only. The benchmark bundle runs 1-3 and 6.
- Every fit on the random bundle also predicts the E5 edits of its held-out fold (`predictions_enc_<model>*_e5.csv`).
- Every finished fit is written to Drive at once. After a disconnect, Run all again keeps the finished fits and retrains only the interrupted one. GPU training is not guaranteed to be bit-identical across runs or GPU types.
- A failed step is recorded and the notebook goes on with the next one. The last cell lists what did not finish.
- Use one GPU type per results folder and do not open the same bundle in two tabs; the notebook refuses to mix results.
