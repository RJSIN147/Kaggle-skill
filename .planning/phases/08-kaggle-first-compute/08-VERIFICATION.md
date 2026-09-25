---
phase: 8
status: passed_with_gaps
verified: 2026-09-26
method: live runs (/tmp/kx-live/{digits,titanic,equity,probes}) + offline suite
gaps: ISIC closed-vision pipeline and the text run need the user to accept those competitions' rules
---

# Phase 8 verification — Kaggle-first compute

| Criterion | Evidence |
|---|---|
| 1. Two-stage vision pipeline (template: fold loop, OOF, AMP, checkpoints; downstream via kernel_sources only after upstream COMPLETE; manifests; consumed upstream version) | LIVE on digit-recognizer (image, mounts without joining): `deep` T4 kernel (fp16 autocast, per-epoch checkpoints, kx-preds/1 OOF) → SUCCESS 0.9738; `kx new --after exp-001` → `deep-infer` CPU kernel reading `/kaggle/input/notebooks/<owner>/<slug>/checkpoints`, pushed only after upstream COMPLETE+recorded (unit-tested refusal), `consumed: v2` by manifest nonce. **Gap:** ISIC-2024 refuses the data source until the user accepts its rules (kx now returns `needs_user/rules_not_accepted`). |
| 2. Text run + resume after the runtime limit | Resume LIVE (digits): time budget stop → COMPLETE → FAILED(runtime_limit, resumable) → `kx run exp-001 --resume` mounted its own output at `/kaggle/input/<slug>/checkpoints` → "KX_RESUMED fold 0 at epoch 23" → SUCCESS. Probe: a Kaggle hard-cancelled kernel (no COMPLETE version) is rejected as a kernel source, hence the self-stopping budget. **Gap:** text run (nlp-getting-started / llm-prompt-recovery) blocked on rules acceptance; text mode is in the template and unit-covered. |
| 3. Raise + runtime limit → FAILED with traceback, log, partials; detach and resume from a new session | Raise: Phase 6 exp-002 and um-mcts exp-002/003 (traceback + log kept). Hard limit: titanic exp-004 → CANCEL_ACKNOWLEDGED → FAILED(runtime_limit), partial.txt + log. Detach: digits exp-002 `--wait 0` → running; a separate `kx status`/`kx run` process resumed polling and recorded without re-pushing. |
| 4. One resolver on kernel (mixed-case ref) and locally; local subsample marked | Kernel: equity manifest `data_dir=/kaggle/input/competitions/equity-post-HCT-survival-predictions`. Local: titanic exp-005 via `KX_DATA_DIR=data/titanic` on a 0.5 subsample → ledger `subsample: 0.5`, digest "(subsample 0.5)", excluded from current best. Too-large data: `kx sync --files …` single-file path (≤10 files). |
| 5. Image digest + library versions, side by side with local | Every meta records `environment.docker_image` (CPU `kaggle-images`, GPU `kaggle-private-byod`) and libraries; `kx env` live: numpy 2.0.2 / pandas 2.3.3 / sklearn 1.6.1 / torch 2.10.0+cu128 vs local 2.5.3 / 3.0.6 / 1.9.1. |

Verified mount paths (live probe): datasets `/kaggle/input/datasets/<owner>/<slug>/`, models
`/kaggle/input/models/<owner>/<model>/<framework>/<variation>/…`, other kernels
`/kaggle/input/notebooks/<owner>/<slug>/`, own previous output `/kaggle/input/<slug>/`.
