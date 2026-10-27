# Frozen H tail continuation: portable-source delta draft

The two new public entrypoints derive from actual-run sources `resume_frozen_H_postprocessing_batch.py` (48615e61…) and `supervise_frozen_H_postprocessing_resume.py` (8a466eb4…). `H_resume_source_delta.json` records full original/public SHAs and every external binding key. Public source bytes are different and have not executed the historical continuation.

`postprocessing_control_primitives.py` is the minimal direct-import closure: only need, sha, bound, read_bound, save_new and stamp from the original supervisor. File I/O first requires the existing strict `portable_runtime` explicit authorization. The previous 21 public scientific sources, runtime, main synthetic suite and README remain unchanged.

Supply `--runtime-manifest PATH --runtime-manifest-sha256 SHA` alongside original plan/release arguments. The public supervisor passes these exact runtime arguments to its public child driver. `templates/H_resume_runtime_bindings.example.json` defaults execution authorization to false. Missing original design/evidence/source/prefix/identity bindings fail closed; no authorization is implied by this template. Public implementations and original-driver/helper source dependencies require a new exact source closure and independent review. A historical original-source receipt cannot authenticate a relocated file.

Parent output identities and prefix bytes remain frozen; only the original not-started tail may run under a new independent once release. The 894-second tail, combined 900-second cap, 12-second cleanup reserve, per-record .25 seconds/50000 checks, 2 threads, one worker, GPU0 and 4 GiB are retained. Resource unknowns and integrity failures remain distinct. Pure source checks do not authorize replaying a historical batch.

Standalone, private-data-free validation:

```sh
python -B research/peak_assignment/H_resume_synthetic_checks.py
```

This performs isolated direct imports, pure synthetic state transitions, exact resource-error matching, compile/SHA checks and actual default-deny CLI attempts. It never invokes a real helper, model, solver, score, parent artifact read or real resume. Stage B moving sources are not included. This delta awaits combined stable source relocation review and root CI/Git publication.
