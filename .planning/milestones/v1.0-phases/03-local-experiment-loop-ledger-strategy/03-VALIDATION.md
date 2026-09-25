---
phase: 03
slug: local-experiment-loop-ledger-strategy
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-11
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from 03-RESEARCH.md §"Validation Architecture" (lines 681-730).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥8.0 (dev group) [VERIFIED: repo pyproject.toml] |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`; `addopts = -m 'not live'` (the `live` marker is excluded by default so the offline mock suite stays green) |
| **Quick run command** | `uv run pytest tests/test_<file>.py -x -q` |
| **Full suite command** | `uv run pytest` (mock suite, offline, `-m 'not live'`) |
| **Estimated runtime** | ~30 seconds (offline mock suite) |

Scripts are exercised as **subprocesses** via the existing `run_script` fixture
(`tests/conftest.py`) — the `python3 scripts/<name>.py --workspace <dir>` contract —
never imported at module top level. `tests/test_run_cv.py` is the one exception that
needs the real ML stack: gate it on `pytest.importorskip("sklearn")` (or a new `ml`
marker excluded like `live`) so the default offline suite stays green without `uv sync`.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_<file>.py -x -q` (the task's own test)
- **After every plan wave:** Run `uv run pytest` (full offline mock suite)
- **Before `/gsd:verify-work`:** Full suite must be green (`-m 'not live'`)
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | D-08 (EXP-03/04) | T-03-01-01 / T-03-01-02 | Metric enum → direction/range/prediction_type looked up from ONE stdlib registry; never guessed | unit | `uv run pytest tests/test_metric_registry.py -x -q` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | D-08 (EXP-03/04) | T-03-01-01 / T-03-01-02 | Metric written only via `set_config_field` behind `choices=SUPPORTED`; `custom` requires explicit direction or blocks (exit 2) | unit | `uv run pytest tests/test_set_metric.py -x -q` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | EXP-03 | T-03-01-SC | Workspace pyproject declares Kaggle-parity ML floors (no newest-major); no runtime install | unit | `python3 -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('scripts/templates/pyproject.toml.tmpl').read_text()); deps=d['project']['dependencies']; assert all(any(p in x for x in deps) for p in ['lightgbm','xgboost','catboost','numpy'])"` | ✅ (edit) | ⬜ pending |
| 03-02-01 | 02 | 1 | MEM-01, EXP-04 | T-03-02-01 | `to_ledger_row`/`validate_meta` single-source schema; a row emits only when all four provenance fields present | unit | `uv run pytest tests/test_experiment_meta.py -x -q` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | MEM-01 | T-03-02-02 / T-03-02-03 | `ledger.jsonl` is a pure function of `meta.json` folders; corrupt meta skipped-and-warned; atomic `os.replace` | unit | `uv run pytest tests/test_rebuild_ledger.py -x -q` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 1 | EXP-04 | T-03-02-01 | meta/VERDICT templates carry provenance + numbers-referenced-not-typed | unit (covered by test_experiment_meta) | `uv run pytest tests/test_experiment_meta.py -x -q` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | EXP-02 / criterion 1 | T-03-03-01 / T-03-03-03 | `run_cv` fit_transform(train)/transform(val) leakage-safe; named metric resolves via rendered `registry_entry["sklearn_callable"]`; custom splitter+metric first-class | unit (ml-gated `importorskip("sklearn")`) | `uv run pytest tests/test_run_cv.py -x -q` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | EXP-02, D-03 | T-03-03-01 | `resolve_data_dir` prefers `/kaggle/input/<slug>` else workspace `data/`; `--data-dir` override | unit | `uv run pytest tests/test_resolve_data_dir.py -x -q` | ❌ W0 | ⬜ pending |
| 03-03-02 | 03 | 2 | EXP-01, D-02 | T-03-03-04 | `scaffold_experiment` mints `exp-NNN`, advances `next_exp_id`, renders resolved `registry_entry` literal into experiment.py; idempotent | unit | `uv run pytest tests/test_scaffold_experiment.py -x -q` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 3 | EXP-03, D-06 | T-03-04-05 | `run_local` bounded `uv run --no-sync`; captures exit code only (never scrapes stdout); env-absent → clear non-zero, never installs | unit | `uv run pytest tests/test_run_local.py -x -q` | ❌ W0 | ⬜ pending |
| 03-04-02 | 04 | 3 | EXP-04, D-05/D-06 | T-03-04-01..04 | Fail-closed ladder; recompute `mean(fold_scores)`; range/finite gates; throwing notebook → FAILED-with-verdict, no success row; explicit-path git provenance | unit | `uv run pytest tests/test_record_experiment.py -x -q` | ❌ W0 | ⬜ pending |
| 03-05-01 | 05 | 4 | MEM-03, D-11/D-12 | T-03-05-01/02/04 | Current-best + tried-list tooling-rendered from ledger by direction; AI supplies only prose; full atomic overwrite | unit | `uv run pytest tests/test_regen_strategy.py -x -q` | ❌ W0 | ⬜ pending |
| 03-05-02 | 05 | 4 | MEM-02, D-13 | T-03-05-03 | SKILL.md documents scaffold→run→record→regen loop + never-repeat prompt protocol | doc grep (behavioral part manual) | `grep -q "regen_strategy" SKILL.md && grep -q "never-repeat" SKILL.md` | ✅ (edit) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_metric_registry.py` — REQ D-08 (registry direction/range/prediction_type correctness)
- [ ] `tests/test_set_metric.py` — REQ D-08 (setter + block-don't-guess + custom direction)
- [ ] `tests/test_experiment_meta.py` — REQ MEM-01/EXP-04 (to_ledger_row + validate_meta schema)
- [ ] `tests/test_rebuild_ledger.py` — REQ MEM-01 (rebuild + corrupt-skip + atomic)
- [ ] `tests/test_run_cv.py` — REQ EXP-02/criterion 1 (leakage-safety, named-metric resolution, result.json); gate on `pytest.importorskip("sklearn")` or a new `ml` marker so the default offline suite stays green without the ML env
- [ ] `tests/test_resolve_data_dir.py` — REQ EXP-02/D-03 (mount-vs-data path resolution)
- [ ] `tests/test_scaffold_experiment.py` — REQ EXP-01/D-02 (id cursor + idempotency + rendered registry_entry)
- [ ] `tests/test_run_local.py` — REQ EXP-03/D-06 (exit-code capture, env-absent message)
- [ ] `tests/test_record_experiment.py` — REQ EXP-04/D-05/D-06 (all five FAILED reasons + SUCCESS + provenance + idea/hypothesis carry-forward)
- [ ] `tests/test_regen_strategy.py` — REQ MEM-03/D-11/D-12 (facts-from-ledger + reasoning splice + atomic overwrite)
- [ ] Shared fixture: a tiny deterministic `train.csv`/`test.csv` + a seeded workspace with `config.metric` (extend `tests/conftest.py` / reuse `cv_fixtures.py`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| The AI actually checks a new idea against the tried-list digest before authoring `experiment.py` (the never-repeat behavior, as opposed to the documented protocol) | MEM-02, D-13 | Prompt-driven agent behavior — the SKILL instructs the AI; whether the AI honors it is a session-level behavioral outcome, not a script assertion. The doc-presence is grep-automated (03-05-02); the behavior is observed. | Run the loop twice with an idea already in the ledger; confirm the AI surfaces the prior attempt and does not re-propose it verbatim. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-11
