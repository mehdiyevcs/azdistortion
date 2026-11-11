# E2 fine-tuned encoders: macro-F1 mean over training seeds 1-3 [95% CI], seed range and MISLEADING F1

| system | condition | sample | n_seeds | seeds | macro_f1_mean | macro_lo | macro_hi | macro_f1_min | macro_f1_max | f1_MIS_mean | n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| azbert | C0 | random | 3 | 1,2,3 | 0.394 | 0.325 | 0.462 | 0.382 | 0.408 | 0.000 | 351 |
| azbert | C1 | benchmark | 3 | 1,2,3 | 0.499 | 0.411 | 0.578 | 0.492 | 0.510 | 0.000 | 155 |
| azbert | C1 | pooled | 3 | 1,2,3 | 0.543 | 0.495 | 0.585 | 0.530 | 0.555 | 0.000 | 506 |
| azbert | C1 | random | 3 | 1,2,3 | 0.577 | 0.524 | 0.618 | 0.558 | 0.599 | 0.000 | 351 |
| azbert | C2 | benchmark | 3 | 1,2,3 | 0.536 | 0.468 | 0.599 | 0.526 | 0.542 | 0.000 | 155 |
| azbert | C2 | pooled | 3 | 1,2,3 | 0.576 | 0.536 | 0.610 | 0.570 | 0.582 | 0.000 | 506 |
| azbert | C2 | random | 3 | 1,2,3 | 0.606 | 0.563 | 0.635 | 0.592 | 0.626 | 0.000 | 351 |
| azbert_edits | C1 | random | 3 | 1,2,3 | 0.562 | 0.504 | 0.607 | 0.546 | 0.582 | 0.017 | 351 |
| azbert_edits | C2 | random | 3 | 1,2,3 | 0.579 | 0.537 | 0.613 | 0.568 | 0.591 | 0.030 | 351 |
| azbert_hum | C2 | benchmark | 3 | 1,2,3 | 0.333 | 0.265 | 0.400 | 0.293 | 0.391 | 0.041 | 155 |
| azbert_hum | C2 | pooled | 3 | 1,2,3 | 0.439 | 0.382 | 0.492 | 0.432 | 0.447 | 0.034 | 506 |
| azbert_hum | C2 | random | 3 | 1,2,3 | 0.500 | 0.430 | 0.561 | 0.476 | 0.512 | 0.000 | 351 |
| mdeberta | C0 | random | 3 | 1,2,3 | 0.294 | 0.273 | 0.311 | 0.294 | 0.294 | 0.000 | 351 |
| mdeberta | C1 | benchmark | 3 | 1,2,3 | 0.289 | 0.267 | 0.307 | 0.289 | 0.289 | 0.000 | 155 |
| mdeberta | C1 | pooled | 3 | 1,2,3 | 0.292 | 0.278 | 0.305 | 0.292 | 0.292 | 0.000 | 506 |
| mdeberta | C1 | random | 3 | 1,2,3 | 0.294 | 0.273 | 0.311 | 0.294 | 0.294 | 0.000 | 351 |
| mdeberta | C2 | benchmark | 3 | 1,2,3 | 0.289 | 0.267 | 0.307 | 0.289 | 0.289 | 0.000 | 155 |
| mdeberta | C2 | pooled | 3 | 1,2,3 | 0.292 | 0.278 | 0.305 | 0.292 | 0.292 | 0.000 | 506 |
| mdeberta | C2 | random | 3 | 1,2,3 | 0.294 | 0.273 | 0.311 | 0.294 | 0.294 | 0.000 | 351 |
| mdeberta_edits | C2 | random | 3 | 1,2,3 | 0.294 | 0.273 | 0.311 | 0.294 | 0.294 | 0.000 | 351 |
| mdeberta_hum | C2 | benchmark | 3 | 1,2,3 | 0.289 | 0.267 | 0.307 | 0.289 | 0.289 | 0.000 | 155 |
| mdeberta_hum | C2 | pooled | 3 | 1,2,3 | 0.292 | 0.278 | 0.305 | 0.292 | 0.292 | 0.000 | 506 |
| mdeberta_hum | C2 | random | 3 | 1,2,3 | 0.294 | 0.273 | 0.311 | 0.294 | 0.294 | 0.000 | 351 |
| xlmr | C0 | random | 3 | 1,2,3 | 0.364 | 0.307 | 0.419 | 0.338 | 0.380 | 0.000 | 351 |
| xlmr | C1 | benchmark | 3 | 1,2,3 | 0.422 | 0.361 | 0.479 | 0.404 | 0.447 | 0.000 | 155 |
| xlmr | C1 | pooled | 3 | 1,2,3 | 0.493 | 0.449 | 0.530 | 0.468 | 0.513 | 0.000 | 506 |
| xlmr | C1 | random | 3 | 1,2,3 | 0.543 | 0.489 | 0.584 | 0.503 | 0.566 | 0.000 | 351 |
| xlmr | C2 | benchmark | 3 | 1,2,3 | 0.491 | 0.415 | 0.557 | 0.484 | 0.504 | 0.000 | 155 |
| xlmr | C2 | pooled | 3 | 1,2,3 | 0.541 | 0.498 | 0.578 | 0.532 | 0.549 | 0.000 | 506 |
| xlmr | C2 | random | 3 | 1,2,3 | 0.580 | 0.532 | 0.614 | 0.552 | 0.599 | 0.000 | 351 |
| xlmr_edits | C1 | random | 3 | 1,2,3 | 0.437 | 0.367 | 0.508 | 0.397 | 0.471 | 0.060 | 351 |
| xlmr_edits | C2 | random | 3 | 1,2,3 | 0.491 | 0.428 | 0.545 | 0.480 | 0.499 | 0.021 | 351 |
| xlmr_hum | C2 | benchmark | 3 | 1,2,3 | 0.259 | 0.212 | 0.305 | 0.238 | 0.294 | 0.007 | 155 |
| xlmr_hum | C2 | pooled | 3 | 1,2,3 | 0.333 | 0.303 | 0.363 | 0.307 | 0.349 | 0.007 | 506 |
| xlmr_hum | C2 | random | 3 | 1,2,3 | 0.355 | 0.317 | 0.402 | 0.315 | 0.394 | 0.000 | 351 |

CI: percentile interval of the seed-mean of the paired cluster-bootstrap replicates. _edits = edit-augmented training (variant b, random only); _hum = human labels only (prereg 4a secondary). mDeBERTa-v3 predicts SUPPORTED for every claim in every run.
