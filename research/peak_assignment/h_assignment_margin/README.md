# H211 assignment-margin experiment sources

This directory preserves the source used by the frozen H211 A/B completion and the prepared offline evaluation adapters. The completion failed; it provides no completed equal-budget accuracy comparison. The full receipts and reports remain in the local experiment archive.

The canonical trainer is `nmr_transfer/h_assignment_margin_train.py`. It uses `nmr_assignment/margin_admission.py` for source-relative noisy-label admission and `nmr_assignment/assignment_margin.py` for frozen full-support, certified G/A costs. The checkpoint, private labels, frozen input manifests, support payloads and execution releases are not included.

The trainer and `launch_bounded_assignment_completion.py` are byte-identical to the executed package. Their historical staging wording is retained so the recorded hashes stay valid. The trainer preserves the reviewed singleton initialization and finite-state/solver checks. Its lifecycle cleanup clears model, teacher, optimizer, batch, metrics and parameter owners before collecting cycles. The continuation path retains the completed 211/A segment and requires three complete remaining jobs; it never initializes a job from retained A.

`cache_adapter.py`, `score_adapter.py` and `paired_summary.py` are prepared, unexecuted adapters. They require full four-job success and new explicit release/application-review evidence before actual evaluation. Their shared metadata guard preserves both prior failed receipts and rejects incomplete or washed segmented provenance. No approved runtime release is published.

The scoring adapter also binds historical runner/evaluator source hashes and private control inputs that are external to this source-only publication. These exact archived adapters are preserved for review; this directory is not a standalone executable evaluation package.

`source_provenance.json` maps every preserved source file to the local staging artifact and its SHA-256. Source publication does not change the frozen protocol or authorize another run. The previous workspace trainer bytes are archived locally under their original SHA; historical receipts remain unchanged.

Focused engineering checks use AST extraction, fake objects and synthetic metadata only:

```sh
python -B -m unittest discover -s tests/assignment -p test_margin_runtime_contracts.py -v
```

The fake lifecycle checks verify release of Python owners and failure propagation. They do not measure allocator RSS or certify a scientific solve. Existing assignment CI runs on each matching main commit. Data, weights, source labels, runtime receipts and private filesystem paths are excluded from this source-only publication.
