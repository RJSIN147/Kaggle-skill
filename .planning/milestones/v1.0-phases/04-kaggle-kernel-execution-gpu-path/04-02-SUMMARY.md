---
phase: 04-kaggle-kernel-execution-gpu-path
plan: 02
subsystem: kernel-gpu-path-push
tags: [nyquist, wave-2, exp-05, convert, push, kernel-metadata, provenance, tdd]
requires:
  - "04-01 (the RED convert + push tests this turns GREEN)"
provides:
  - "scripts/convert_notebook.py (D-02 non-destructive .py→.ipynb via uv run jupytext)"
  - "scripts/push_kernel.py (metadata gen + quota heads-up + kernels push + kernel_run.json handoff)"
  - "scripts/templates/kernel-metadata.json.tmpl (VERIFIED schema; explicit enable_internet)"
  - "config.json.tmpl kernel.enable_internet toggle (D-06, default false)"
  - "experiments/exp-NNN/kernel_run.json handoff schema (consumed by 04-03 poll/pull and 04-04 recorder)"
affects:
  - "04-03 (poll/pull re-read kernel_run.json without re-pushing)"
  - "04-04 (recorder merges kernel_run.json provenance)"
  - "04-05 (SKILL sequencing + live-push checkpoint confirms A1/A4)"
tech-stack:
  added:
    - "jupytext>=1.16 (workspace pyproject floor; operator uv sync — never runtime-installed)"
  patterns:
    - "uv run --no-sync shell-out for a build step (convert), mirroring run_local.py"
    - "template-render→overwrite for per-push build artifacts (kernel-metadata.json)"
    - "gateway-routed kaggle calls (no-echo, timeout, exit-code); dump_last_error quarantine"
    - "provenance-only integer scrape from CLI prose (never derives a path/command — V5)"
key-files:
  created:
    - scripts/convert_notebook.py
    - scripts/push_kernel.py
    - scripts/templates/kernel-metadata.json.tmpl
  modified:
    - scripts/templates/config.json.tmpl
    - scripts/templates/pyproject.toml.tmpl
    - tests/test_push_kernel.py
decisions:
  - "kernel_run.json schema pinned (12 keys) — documented below for 04-03/04-04 to consume."
  - "Added a defense-in-depth _USERNAME_RE gate: the config-view username is validated before it enters the kernel id (block, don't guess) — beyond the plan's explicit _SLUG_RE requirement (Rule 2)."
  - "Added test_version_provenance to test_push_kernel.py (the plan's Task-3 behavior directed asserting it; Wave 1 shipped no such node) — locks the D-05 int-or-null version scrape."
metrics:
  duration: ~5min
  tasks: 3
  files: 6
  completed: 2026-07-12
---

# Phase 04 Plan 02: Kernel-Path Front Half (convert + push) Summary

Built the front half of the kernel loop — the thinnest slice that takes the SAME Phase-3
`experiment.py` from local to a live Kaggle kernel: a non-destructive `.py→.ipynb` convert, a
VERIFIED-schema kernel-metadata generator, a non-blocking GPU-quota heads-up, a gateway-routed
`kernels push`, and the `kernel_run.json` push→poll→pull handoff state. Turns the 04-01 convert +
push RED tests GREEN (6 nodes).

## What Was Built

**Task 1 — `scripts/convert_notebook.py` (commit 77aa057):**
Mirrors `run_local.py`'s portability posture (stdlib-only, self-locating, `--workspace`/`--exp-dir`/
`--timeout`, argparse-in / exit-code-out). Shells `uv run --no-sync jupytext --to notebook
<exp.py> -o <exp.ipynb>` with the load-bearing uv-absent gate (`shutil.which("uv") is None` ⇒ print
the `uv sync` remediation, convert nothing — never a runtime install). The `.ipynb` is a regenerable
build artifact: overwritten every run, and `experiment.py` is never mutated (D-02). Same
`TimeoutExpired`/`OSError` handlers as run_local.

**Task 2 — templates (commit dfedc62):**
- `scripts/templates/kernel-metadata.json.tmpl` — the VERIFIED schema with `${KEY}` placeholders for
  `_render_text`/`safe_substitute`. `enable_internet` is rendered as a bare JSON bool via
  `${ENABLE_INTERNET}` (Pitfall 4 guard — the CLI's own `kernels init` writes `true`; we emit an
  explicit value, default false). `is_private:true`, `enable_gpu:true`, `enable_tpu:false`,
  `competition_sources:["${COMPETITION_SLUG}"]`, the four `*_sources` arrays.
- `config.json.tmpl` — added a `"kernel": { "enable_internet": false }` leaf (D-06). Because
  `deep_merge_add_missing` only ADDS absent keys, an already-scaffolded workspace is retrofitted on
  the next `init` merge without clobbering. A later toggle uses `set_config_field` on
  `("kernel","enable_internet")` (the setter path 04-05/SKILL should document).
- `pyproject.toml.tmpl` — declared `jupytext>=1.16` in the workspace ML deps (DECLARE-in-template;
  operator runs `uv sync`; the skill never runtime-installs). CLAUDE.md-verified stack.

**Task 3 — `scripts/push_kernel.py` (commit 5622b0b):**
Fail-clear `control/config.json` read → `competition_slug` (validated by `_SLUG_RE`) + effective
`enable_internet` from `config["kernel"]["enable_internet"]` (default false). Username resolved via
`run_kaggle("config","view",timeout=30)` matching the `- username:` line — the raw buffer is NEVER
echoed, and a failure quarantines it via `dump_last_error`. Kernel id built ONLY from
`_SLUG_RE`-validated slug + `_USERNAME_RE`-validated username + `exp-NNN` (V5 no-derive). Renders
`kernel-metadata.json` (per-push build artifact — overwrite). D-13 non-blocking quota heads-up
(`kaggle quota --format json`) that is silently skipped on any failure and NEVER blocks the push.
Push via the gateway with reserved-code branches (127 CLI-missing, 124 timeout, rc!=0 quarantine +
fail-closed). Provenance-only version scrape (`r"[Vv]ersion\s+(\d+)"`, int-or-null, D-05). Writes
`kernel_run.json` handoff (`json.dumps(..., indent=2)+"\n"`) with the effective internet flag
recorded (D-06 guard) and `status="PENDING"`.

## kernel_run.json schema (for 04-03 poll/pull and 04-04 recorder)

`experiments/exp-NNN/kernel_run.json` — written by push, re-read (never re-pushed) by poll/pull:

| Key | Type | Value written by push |
|-----|------|-----------------------|
| `exp_id` | str | `exp-NNN` (basename of `--exp-dir`) |
| `kernel_slug` | str | `<username>/<slug>-exp-NNN` (the push id; poll/pull's status/output target) |
| `kernel_version` | int \| null | provenance-only version scraped from push output; null when unparseable (A4) |
| `code_file` | str | `"experiment.ipynb"` |
| `competition_slug` | str | validated slug |
| `accelerator` | str | the `--accelerator` value, else `"enable_gpu"` |
| `enable_internet` | bool | the EFFECTIVE flag (D-06 auditable-exception guard) |
| `pushed_at` | str | `_iso_now()` UTC ISO-8601 Z |
| `status` | str | `"PENDING"` (poll flips to terminal / detach re-writes PENDING per D-09) |
| `backend` | str | `"kernel"` |
| `docker_image` | null | reserved for 04-03 pull `kernels pull -m` image provenance (D-14) |
| `machine_shape` | null | reserved for 04-03 pull machine-shape provenance |

04-03 (poll/pull): read `kernel_slug` for `kernels status`/`output`/`logs`; flip `status`; on our-side
budget expiry write `status="PENDING"` back (detach-not-cancel, D-09); merge `docker_image`/
`machine_shape` from `kernels pull -m`. 04-04 (recorder): merge `enable_internet`/`kernel_slug`/
`backend` provenance into `meta.json`.

## Verification

- `uv run pytest tests/test_convert_notebook.py tests/test_push_kernel.py -x -q` → **6 passed**
  (`test_reconvert_idempotent`, `test_source_routes_through_uv_no_sync_no_pip_install`,
  `test_metadata_golden`, `test_internet_provenance`, `test_version_provenance`,
  `test_source_routes_through_gateway`).
- Task 2 template assertions (is_private/enable_internet/COMPETITION_SLUG placeholders, config
  `enable_internet` leaf, `jupytext` in pyproject) pass; `config.json.tmpl` still parses as valid JSON.
- Acceptance greps: `convert_notebook.py` contains `--no-sync` and NOT `pip install`; `push_kernel.py`
  contains `run_kaggle` + `dump_last_error` and never `print(out`/`print(combined`.
- Full suite: **191 passed, 8 failed, 1 skipped, 9 deselected**. The 8 failures are exclusively
  `test_poll_kernel.py` (04-03) and `test_record_kernel.py` (04-04) RED nodes — downstream waves,
  out of this plan's scope. No regression to any pre-existing test (was 185 passed in Wave 1; +6 now
  green from this plan).
- `test_init_workspace.py` + `test_config.py` GREEN after the `config.json.tmpl` change (no config-
  golden regression).

## Deviations from Plan

### Auto-added (Rule 2 — defense-in-depth)

**1. [Rule 2 - Security] Username validation before it enters the kernel id**
- **Found during:** Task 3
- **Issue:** The plan mandates `_SLUG_RE` on the slug but the username also enters the kernel id and
  originates from Kaggle prose (`config view`). An exotic handle would ride into the id/push unchecked.
- **Fix:** Added `_USERNAME_RE = ^[A-Za-z0-9][A-Za-z0-9_-]*$`; a non-matching username blocks the push
  (block, don't guess) — consistent with the plan's threat register T-4-04 (kernel id built only from
  validated inputs).
- **Files modified:** scripts/push_kernel.py
- **Commit:** 5622b0b

### Test added (plan-directed)

**2. test_version_provenance in tests/test_push_kernel.py**
- The plan's Task-3 behavior explicitly directs asserting the version scrape in `test_push_kernel.py`
  ("extend test_internet_provenance or add test_version_provenance — no new fixture file needed").
  Wave 1 shipped no such node, so it was added here to lock the D-05 int-or-null contract (version
  present ⇒ int; absent ⇒ null; push exit code unaffected either way).
- **Commit:** 5622b0b

## Notes for Downstream Plans

- **04-03 (poll/pull):** consume the `kernel_run.json` schema above. `kaggle kernels status` has no
  `--format json` (RESEARCH) — parse the status token via regex. Detach-not-cancel writes
  `status="PENDING"` back on budget expiry. The exact push-output version string (A4) and status
  render (A2) are confirmed at the 04-05 live-push checkpoint.
- **04-05 (SKILL / config setter):** document `set_config_field(("kernel","enable_internet"), true)`
  as the deliberate opt-in path for an internet-on run (the auditable D-06 exception), and add the
  `convert → push → poll → pull → record` sequencing rows.
- The `--accelerator` override exposes only the VERIFIED `NvidiaTeslaT4`/`NvidiaTeslaP100` IDs
  (argparse `choices`); the T4×2 string (A1) stays out until the live checkpoint confirms it.

## Self-Check: PASSED
