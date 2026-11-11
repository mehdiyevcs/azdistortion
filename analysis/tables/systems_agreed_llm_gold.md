# Secondary: scores against the agreed-LLM gold (claims with A1 = A2, unweighted)

| system | condition | sample | seed | n | macro_f1 | F1 SUPPORTED | F1 CONTRADICTED | F1 MISLEADING | F1 NOT_IN_SOURCE |
|---|---|---|---|---|---|---|---|---|---|
| gpt55 | C0 | random |  | 1933 | 0.305 | 0.844 | 0.000 | 0.167 | 0.211 |
| gpt55 | C1 | random |  | 1933 | 0.628 | 0.960 | 0.300 | 0.385 | 0.868 |
| gpt55 | C2 | benchmark |  | 1484 | 0.606 | 0.970 | 0.333 | 0.194 | 0.927 |
| gpt55 | C2 | random |  | 1933 | 0.639 | 0.977 | 0.273 | 0.369 | 0.936 |
| haiku | C0 | random |  | 1933 | 0.058 | 0.055 | 0.000 | 0.000 | 0.176 |
| haiku | C1 | benchmark |  | 1484 | 0.564 | 0.916 | 0.333 | 0.211 | 0.797 |
| haiku | C1 | random |  | 1933 | 0.503 | 0.953 | 0.074 | 0.125 | 0.859 |
| haiku | C2 | benchmark |  | 1484 | 0.629 | 0.969 | 0.444 | 0.194 | 0.909 |
| haiku | C2 | random |  | 1933 | 0.516 | 0.964 | 0.069 | 0.136 | 0.894 |
| qwen | C0 | random |  | 1933 | 0.202 | 0.484 | 0.000 | 0.000 | 0.325 |
| qwen | C1 | benchmark |  | 1484 | 0.402 | 0.882 | 0.071 | 0.017 | 0.639 |
| qwen | C1 | random |  | 1933 | 0.406 | 0.925 | 0.000 | 0.018 | 0.683 |
| qwen | C2 | benchmark |  | 1484 | 0.433 | 0.927 | 0.083 | 0.024 | 0.699 |
| qwen | C2 | random |  | 1933 | 0.402 | 0.938 | 0.000 | 0.000 | 0.669 |
| sonnet | C0 | random |  | 1933 | 0.099 | 0.067 | 0.000 | 0.000 | 0.330 |
| sonnet | C1 | benchmark |  | 1484 | 0.624 | 0.925 | 0.375 | 0.385 | 0.813 |
| sonnet | C1 | random |  | 1933 | 0.607 | 0.963 | 0.316 | 0.256 | 0.891 |
| sonnet | C2 | benchmark |  | 1484 | 0.709 | 0.981 | 0.471 | 0.439 | 0.944 |
| sonnet | C2 | random |  | 1933 | 0.667 | 0.987 | 0.316 | 0.400 | 0.964 |
| majority | C0 | random |  | 1933 | 0.220 | 0.880 | 0.000 | 0.000 | 0.000 |
| majority | C1 | random |  | 1933 | 0.220 | 0.880 | 0.000 | 0.000 | 0.000 |
| majority | C2 | random |  | 1933 | 0.220 | 0.880 | 0.000 | 0.000 | 0.000 |
| nli | C0 | random |  | 1933 | 0.101 | 0.060 | 0.000 | 0.000 | 0.343 |
| nli | C1 | random |  | 1933 | 0.335 | 0.781 | 0.011 | 0.000 | 0.549 |
| nli | C2 | random |  | 1933 | 0.332 | 0.778 | 0.011 | 0.000 | 0.540 |
| logreg | C0 | random |  | 1933 | 0.341 | 0.826 | 0.000 | 0.140 | 0.399 |
| logreg | C1 | random |  | 1933 | 0.414 | 0.888 | 0.000 | 0.049 | 0.717 |
| logreg | C2 | random |  | 1933 | 0.418 | 0.898 | 0.000 | 0.061 | 0.712 |
| gbm | C0 | random |  | 1933 | 0.347 | 0.786 | 0.000 | 0.229 | 0.371 |
| gbm | C1 | random |  | 1933 | 0.449 | 0.934 | 0.000 | 0.071 | 0.793 |
| gbm | C2 | random |  | 1933 | 0.437 | 0.929 | 0.000 | 0.043 | 0.774 |
| majority | C1 | benchmark |  | 1484 | 0.213 | 0.854 | 0.000 | 0.000 | 0.000 |
| majority | C2 | benchmark |  | 1484 | 0.213 | 0.854 | 0.000 | 0.000 | 0.000 |
| nli | C1 | benchmark |  | 1484 | 0.330 | 0.724 | 0.014 | 0.000 | 0.583 |
| nli | C2 | benchmark |  | 1484 | 0.335 | 0.730 | 0.014 | 0.000 | 0.597 |
| logreg | C1 | benchmark |  | 1484 | 0.384 | 0.823 | 0.000 | 0.078 | 0.634 |
| logreg | C2 | benchmark |  | 1484 | 0.411 | 0.865 | 0.000 | 0.046 | 0.732 |
| gbm | C1 | benchmark |  | 1484 | 0.390 | 0.852 | 0.000 | 0.062 | 0.646 |
| gbm | C2 | benchmark |  | 1484 | 0.418 | 0.907 | 0.000 | 0.000 | 0.765 |
| haiku_2pass | C2 | random |  | 1933 | 0.521 | 0.965 | 0.182 | 0.110 | 0.828 |
| haiku_2pass | C2 | benchmark |  | 1484 | 0.528 | 0.964 | 0.178 | 0.103 | 0.866 |
| H7_selected | C2 | benchmark | 1 | 1484 | 0.428 | 0.891 | 0.000 | 0.090 | 0.731 |
| H7_selected | C2 | benchmark | 2 | 1484 | 0.428 | 0.891 | 0.000 | 0.090 | 0.731 |
| H7_selected | C2 | benchmark | 3 | 1484 | 0.428 | 0.891 | 0.000 | 0.090 | 0.731 |
| H7_selected_hum | C2 | benchmark | 1 | 1484 | 0.426 | 0.890 | 0.000 | 0.087 | 0.728 |
| H7_selected_hum | C2 | benchmark | 2 | 1484 | 0.426 | 0.890 | 0.000 | 0.087 | 0.728 |
| H7_selected_hum | C2 | benchmark | 3 | 1484 | 0.426 | 0.890 | 0.000 | 0.087 | 0.728 |
| H7_selected | C2 | random | 1 | 1933 | 0.424 | 0.933 | 0.000 | 0.000 | 0.764 |
| H7_selected | C2 | random | 2 | 1933 | 0.419 | 0.930 | 0.000 | 0.000 | 0.748 |
| H7_selected | C2 | random | 3 | 1933 | 0.425 | 0.934 | 0.000 | 0.000 | 0.765 |
| H7_selected_edits | C2 | random | 1 | 1933 | 0.413 | 0.848 | 0.000 | 0.015 | 0.789 |
| H7_selected_edits | C2 | random | 2 | 1933 | 0.423 | 0.877 | 0.000 | 0.030 | 0.783 |
| H7_selected_edits | C2 | random | 3 | 1933 | 0.417 | 0.868 | 0.000 | 0.020 | 0.778 |
| H7_selected_hum | C2 | random | 1 | 1933 | 0.432 | 0.926 | 0.000 | 0.087 | 0.715 |
| H7_selected_hum | C2 | random | 2 | 1933 | 0.432 | 0.926 | 0.000 | 0.087 | 0.715 |
| H7_selected_hum | C2 | random | 3 | 1933 | 0.432 | 0.926 | 0.000 | 0.087 | 0.715 |

macro-F1 over SUPPORTED, CONTRADICTED, MISLEADING, NOT_IN_SOURCE (>= 10 claims in the agreed set). Same-family flags: Haiku/Sonnet with A1 (Opus), GPT-5.5 with A2 (Codex).
