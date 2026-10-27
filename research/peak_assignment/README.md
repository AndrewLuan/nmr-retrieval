# Peak assignment outer sources

This subtree contains portable source copies for reference → anonymous public inputs / hidden gold → frozen native cache → per-input lineage → B0/B1/B2 → evaluation and validation-only calibration → reporting. It contains no source rows, spectra, weights, registry contents, actual predictions, fitted thresholds or run outputs.

The existing `nmr_assignment` and `nmr_transfer` packages are reused in place. The native cache requires the compatible native PyTorch / torch_geometric environment and independently supplied checkpoints. Assignment/report interfaces require Python 3.11+ (SciPy 1.17.1 requires Python >=3.11), with frozen SciPy 1.17.1, RDKit 2026.3.6 and psutil 7.2.2. See the existing `research/nmr_retrieval/requirements-common.txt` dependency declarations. Graph transport requires the **explicit manifest RDKit version**, not any installed version. Native PyTorch / torch_geometric remain in the original model environment; these assignment dependencies do not authorize replacing that environment. This delivery does not install or select another model/runtime.

## Source lineage and external bindings

`source_manifest.json` lists each D producer's original byte SHA and the different portable SHA. These public copies were not used for the historical actual runs. Their transformation is source relocation: AST formatting, repository discovery, external artifact paths, exact source/asset/review SHA bindings, opaque corrected IDs and cohort-size bindings. Numerical algorithm constants, scientific gate bodies, complete joint variants, raw-byte verification, failure denominators, deadlines and threshold evidence checks remain in the source. External values require separate review; a matching manifest SHA is not scientific approval.

Every non-pure entrypoint accepts two leading common arguments:

```text
python research/peak_assignment/ENTRY.py --runtime-manifest /private/runtime.json --runtime-manifest-sha256 EXACT_SHA [original entrypoint arguments]
```

The shared runtime removes those two arguments before the original parser. `templates/runtime_manifest.example.json` enumerates required binding keys without real values. Fill only with a separately frozen run's paths, identities, counts and reviewed SHA values. A `sha_or_identity` key is an exact original scalar binding; the producer's existing identity/hash checks still consume it. The mapping's per-file line-independent key is stable for these public source bytes. Do not fill public-source checks with historical D-source SHAs. Re-freeze all public implementation digests and independent reviews for any future execution. `workspace` points outside this source tree; `artifacts` explicitly relocates an original artifact filename. Python siblings resolve to this public subtree. Core modules resolve to the repository root.

The example manifest defaults `execution_authorized=false`. Missing bindings fail closed. Execution, aggregation and read-only mode flags are mutually exclusive; adding `--help`, `--self-test` or a check-only flag never weakens execution authorization. Both final-delivery verifiers resolve their artifact root from the external `workspace` and honor explicit artifact-path overrides; private evidence does not belong in this source directory. Public execution requires the runtime authorization **and** original producer approvals/plan gates; no example grants them. Keep all private artifacts outside this source tree. Root maintains Git exclusions and CI coverage separately.

## Command chain

1. `prepare_H_reference_inputs.py` / `prepare_C_reference_inputs.py` extract the already frozen train/validation cohort. Remote extraction source remains visible in these files; SSH host, remote Python, source paths and source SHAs are external bindings. No sampling or test selection is added.
2. `build_H_source_reference_batch.py` or `build_C_reference_batch.py` with `C_reference_rule_producer.py` construct source-relative references using core transport/reference. Corrected IDs are external only; raw source is not silently replaced. Preserve complete mapping families and all admission failures.
3. `build_frozen_prediction_cache.py` consumes explicit cohort/assets/plan paths and SHAs and reuses native source closure. The H/C supervisor and verification entrypoints retain resource envelopes, pre/post hashes, native graph/layout/mass/width checks. Supply independent asset nomination and width provenance; never synthesize them.
4. `prepare_H_scoring_artifacts.py` / `prepare_C_scoring_artifacts.py` bind public, hidden gold, admission, cache and lineage. Unavailable public rows retain independent identity coverage.
5. `run_frozen_assignment_baselines.py` / `run_frozen_C_assignment_baselines.py` consume the exact frozen plan. Each record's original deadline starts before reading it; failures retain all three methods' independently frozen gold denominators. There is no retry/replacement or extra forward.
6. `assignment_evaluation_adapter.py` verifies execution receipts and complete prediction projection before confidence publication. Calibration remains validation-only with the frozen connectivity partition.
7. `summarize_frozen_assignment_outputs.py` / `summarize_frozen_C_assignment_outputs.py` require an actually completed manifest; compare final rows to independent initial inventories and reconstruct calibration counts at the stored threshold. Thresholds must belong to original calibration publishable scores. The report helper keeps micro, record→connectivity macro, supported conditional rates, paired connectivity bootstrap and separate whole/strict endpoints.
8. `verify_assignment_complete.py` and `verify_source_relative_delivery.py` provide the original closure checks with external manifest bindings.

The two `execute_*_once.py` historical machine-specific launch wrappers are deliberately excluded. Invoke the portable caller explicitly under an external supervisor that freezes argv, environment, source/input SHA closure and resource envelope. Do not run a historical wrapper against public sources.

## Synthetic validation without private files

From a clean repository checkout:

```sh
python -B research/peak_assignment/synthetic_checks.py
```

This compiles the explicit source inventory, rejects private machine path / corrected-ID leakage, runs the adapter's synthetic receipt tests and the estimator's synthetic tests, and checks default-deny runtime authorization. It does not enumerate real cohorts, load a model, solve a real batch or read a test spectrum. The full extraction/cache/packaging chain needs externally supplied private manifests and new public-source independent review; syntax/interface checks are not an end-to-end scientific reproduction claim.

`templates/numerical_implementation_config.json` and `templates/report_estimand_contract.json` remove private thread metadata. The helper retains its original estimand provenance SHA; that is distinct from the sanitized template's byte SHA. Neither this package nor its tests manufactures independent experimental truth or solver certificates.

For the narrow authorization/path relocation regression only: `python -B research/peak_assignment/synthetic_checks.py --relocation-only`. Missing independent delivery evidence must remain PENDING.

## Complete additive H/A/B source preparation

The current source inventory additionally includes H parent diagnostics and supervision, the single-record postprocessor, saved descriptive aggregation, exact tail continuation and its six-control-function import closure; reviewed Stage A schema-fixed outer and native-test producer; and stable Stage B control/execution/supervision/package/caller/report plus referenced regression source. See [H resume](H_RESUME_README.md), [H parent / A](H_PARENT_A_README.md), and [B](STAGE_B_README.md) for source-specific boundaries. The earlier per-delta inventory hashes are preserved historical preparation snapshots; `source_manifest.json` is the combined public-source inventory.

`templates/complete_runtime_manifest.example.json` enumerates all external binding keys with no real values and maps public/core source binding roles to repository-relative targets. It defaults authorization false. Do not substitute old actual-run SHA values for new public code. The model, registry, label, calibration-outcome and test artifact directories remain external. `PUBLIC_SOURCE_JSON_ALLOWLIST.json` lists only checked-in source manifests and deidentified templates for root's ignore-rule review; it contains no private runtime manifest.

The main synthetic command now includes the three additive H-resume, H-parent/A and B interface checks. These are source/interface/authorization checks, not scientific reruns or a claim that full original process-regression suites ran. Existing assignment/native source is reused. Of the frozen native cache's 220 source entries, 216 already match repository native paths; the other four are existing `nmr_assignment/native_adapter.py`, `__init__.py`, `contracts.py`, and `mapping.py`. All four are covered by the existing core, not a reason to copy another model package.
