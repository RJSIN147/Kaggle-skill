---
phase: 10
status: passed
verified: 2026-09-26
method: live runs (/tmp/kx-live/{equity,ps6e2}) + offline suite
---

# Phase 10 verification — research & ensembling

| Req | Evidence (live) |
|---|---|
| RES-01 discussions | equity (closed → `top`): 5 threads with full bodies via SDK `list_topic_messages` fenced as untrusted into `research/cache/discussions/` (gitignored); `index.json` keeps metadata only. |
| RES-02 notebooks | equity by `scoreDescending`: 4th/3rd/16th-place solutions pulled in memory via `get_kernel` (notebook code cells, magics dropped), sources recorded: `cdeotte/pip-install-lifelines` (offline wheels), `metric/eefs-concordance-index`. |
| RES-03 ideas → strategy | AI summary note written for the 4th-place notebook; `kx research idea` queued "Kaplan-Meier target"; `kx new --from-idea 1` ran it as exp-004 (idea text tagged `[from notebook: …]`, idea marked `tried:exp-004`); the strategy doc lists open research ideas. Result recorded honestly: C-index 0.393 (target direction inverted — the next hypothesis). |
| RES-04 host metric | `kx research metric` found `metric/eefs-concordance-index`; adopted with `--use-metric` (sha256-pinned, inlined lazily as `host_metric`); CV computed by its `score()` on a kernel: 0.6382 ± 0.0019 (lifelines installed offline from the attached kernel's wheels). |
| ENS-02 blending | playground-series-s6e2: LightGBM 0.95513 + XGBoost 0.95525 (kernels) → `kx ensemble --method hill` 0.955282 (weights 1/3, 2/3) and `--method weights` 0.955282; each recorded as its own experiment through the fail-closed recorder, with a submission file. |
