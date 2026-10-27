# NMR retrieval experiments

Research code for NMR spectrum retrieval, forward prediction, ranking and diagnostic analysis.

This repository was separated from `AndrewLuan/SpectraExpert` at commit `abe77f15396ecd966629462eafb7ca7346f643fc`. It preserves the original paths and source files, including the subsequent diagnostic additions. The historical import and reproduction notes are in [research/nmr_retrieval/README.md](research/nmr_retrieval/README.md). References there to the original repository and its `pytest.ini` describe that historical layout.

| Path | Contents |
| --- | --- |
| `nmr_forward/` | Forward prediction models and tests |
| `nmr_transfer/` | Retrieval, observation and ranking code and tests |
| `research/nmr_retrieval/` | Experiment configuration, diagnostic tools and provenance |
| `tests/training/` | Pool ranker test |

The original source provenance is retained unchanged. Archived runs predate this repository: use the recorded source hashes to identify their code. Data, spectra, checkpoints, outputs and credentials are not included. Some archived stages require private inputs and their recorded historical layout.

For environment details and focused checks, see the [experiment notes](research/nmr_retrieval/README.md).
