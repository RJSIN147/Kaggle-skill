# Phase 3: Local Experiment Loop, Ledger & Strategy - Pattern Map

**Mapped:** 2026-07-11
**Files analyzed:** 13 (9 new scripts/modules + 3 new templates + 4 extended/modified files)
**Analogs found:** 13 / 13 (every new file has a same-repo analog — this is a greenfield-in-an-established-convention phase, not a novel-architecture one)

## Orientation for the planner

Every Phase-3 script is a **stdlib-only, self-locating, `--workspace`-in / exit-code-out, non-interactive** helper that sits beside the Phase-2 scripts and REUSES their imported helpers rather than reinventing them. The load-bearing conventions to replicate, all already proven in `scripts/`:

- **Self-location header** (verbatim, every new `scripts/*.py`):
  ```python
  SCRIPT_DIR = Path(__file__).resolve().parent
  if str(SCRIPT_DIR) not in sys.path:
      sys.path.insert(0, str(SCRIPT_DIR))
  ```
- **Reuse the shared helpers** — do NOT reimplement: `from init_workspace import _render_text, create_if_absent, set_config_field, write_control_json, MalformedControlJSON`; `from competition_doc import replace_section`. These are the write primitives.
- **The AI decides / tooling writes** flow (D-05 → D-08): argparse `choices=`-validated flag → `set_config_field(config_path, key_path, value)`. The framework NEVER auto-picks an enum value.
- **Stdlib-plumbing / one-ML-step-behind-`uv run`** split (D-06): NO `scripts/*.py` imports pandas/sklearn/lightgbm. The ML stack is imported ONLY inside the generated `experiment.py` (run via `uv run --no-sync`). `run_local.py` is the shell-out; it mirrors `analyze_data.run_adversarial_validation` exactly.
- **Explicit-path git staging** (never `git add -A`): `git add -- <path> ...` for named provenance paths only — the leak guard trips on a blanket stage.
- **Fail-clear on malformed JSON**: a corrupt `config.json`/`state.json`/`meta.json` is left byte-for-byte untouched and the script returns non-zero (the `MalformedControlJSON` posture).

**Reserved exit codes** live in `kaggle_gateway.py` (`UI_GATE = 77`, `LIMIT_NEEDS_USER = 78`). Phase 3 needs NO gateway import (no Kaggle calls in the loop), but `set_metric.py` should follow the same **reserved-exit-code-to-signal-block** convention (a dedicated code for "metric uncaptured/unmappable → block, don't guess", D-08) that `capture_competition.py` uses with `LIMIT_NEEDS_USER`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/metric_registry.py` | utility (stdlib data module) | transform (lookup) | `scripts/cv_evidence.py` (module-level `CV_SCHEMES` enum + notes) | role-match |
| `scripts/experiment_meta.py` | utility (schema + (de)serialize) | transform | `scripts/competition_doc.py` (single-purpose importable stdlib helper, no import side-effects) | role-match |
| `scripts/set_metric.py` | config-setter (entry point) | request-response (setter mode) | `scripts/capture_competition.py` `--set-competition-type` branch + `analyze_data.py --cv-scheme` | exact |
| `scripts/scaffold_experiment.py` | scaffolder (entry point) | file-I/O (template render + id-cursor) | `scripts/init_workspace.py` (`scaffold`, `_render_text`, `create_if_absent`) | exact |
| `scripts/run_local.py` | runner (entry point) | request-response (subprocess) | `scripts/analyze_data.py` `run_adversarial_validation` (`uv run --no-sync` shell-out) | exact |
| `scripts/record_experiment.py` | recorder/validator (entry point) | transform + file-I/O (validate→persist) | `scripts/capture_competition.py` (fetch→validate→`set_config_field`+`replace_section`+`_stage_provenance`) | role-match |
| `scripts/rebuild_ledger.py` | index-builder (entry point) | batch (glob→derive→atomic write) | `scripts/init_workspace.py` atomic-write + `cv_evidence.write_evidence` glob/JSON pattern | role-match |
| `scripts/regen_strategy.py` | doc-renderer (entry point) | transform (facts+reasoning→overwrite) | `scripts/analyze_data.py` section-body builders + `init_workspace` atomic write | role-match |
| `scripts/templates/experiment.py.tmpl` | ML-env template (generated code) | file-I/O + CRUD (CV loop) | `analyze_data._AV_RUNNER_SRC` (the ONLY existing ML-under-`uv-run` source) + `strategy.md.tmpl` | role-match |
| `scripts/templates/meta.json.tmpl` | template | — | `scripts/templates/config.json.tmpl` / `state.json.tmpl` | exact |
| `scripts/templates/VERDICT.md.tmpl` | template | — | `scripts/templates/strategy.md.tmpl` / `competition.md.tmpl` | exact |
| `control/config.json` (+`metric` field) | config (extended) | — | Phase-2 `cv.scheme` / `submission` / `competition.type` reserved-null keys | exact |
| `control/state.json.next_exp_id` (cursor read/inc) | state (extended) | CRUD | `state.json.tmpl` (`next_exp_id: 1` already scaffolded) | exact |
| `strategy.md` (static stub → per-cycle regen) | doc (extended) | — | `strategy.md.tmpl` (rewritten wholesale) | exact |
| workspace `pyproject.toml` (ML floors) | config (extended) | — | `scripts/templates/pyproject.toml.tmpl` (extends the existing `pandas>=2.2`/`scikit-learn>=1.5` floors) | exact |

## Shared Patterns (apply to ALL new scripts)

### Self-location + shared-helper import block
**Source:** `scripts/capture_competition.py` lines 44-63, `scripts/analyze_data.py` lines 50-60
**Apply to:** every new `scripts/*.py` entry point
```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from init_workspace import (  # noqa: E402
    MalformedControlJSON,
    _render_text,
    create_if_absent,
    set_config_field,
    write_control_json,
)
from competition_doc import replace_section  # noqa: E402
```

### `--workspace` argparse boilerplate + `main`/`raise SystemExit` shape
**Source:** `scripts/analyze_data.py` lines 380-394, 397-399, 497-498
**Apply to:** every new entry point
```python
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="<name>.py", description="...")
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    return ap

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()
    config_path = ws / "control" / "config.json"
    ...
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### Fail-clear config read (never touch a corrupt file)
**Source:** `scripts/analyze_data.py` lines 402-413
**Apply to:** every script that reads `config.json` / `state.json` / `meta.json`
```python
if not config_path.exists():
    print(f"<verb> refused: no {config_path} — run init first.", file=sys.stderr)
    return 1
try:
    cfg = json.loads(config_path.read_text())
except json.JSONDecodeError as exc:
    print(f"<verb> refused: {config_path.name} is not valid JSON and was left "
          f"untouched (fail-clear, D-02): {exc}.", file=sys.stderr)
    return 1
```

### The tooling-writes machine field (D-05 → D-08 metric)
**Source:** `scripts/init_workspace.py` `set_config_field` lines 475-519 (the general setter) + `analyze_data.py` lines 456-462 (the `--cv-scheme` caller)
**Apply to:** `set_metric.py` (writes `config.json.metric`), `record_experiment.py` (never trusts an emitted number)
The rule verbatim from `set_config_field`'s docstring: *"Enum validation stays at the argparse `choices` boundary in every caller, so a non-enum value is rejected before any write — the AI never hand-writes a field; it passes a validated flag and tooling writes."* Reserved-null keys (`cv.scheme`, `submission.daily_limit`, `competition.type`) can NEVER be filled by `write_control_json`'s merge — only by this direct setter. `config.json.metric` is a NEW reserved-null key of the same kind.

### Explicit-path git staging (never `git add -A`)
**Source:** `scripts/capture_competition.py` `_stage_provenance` lines 185-198
**Apply to:** `record_experiment.py` (stages `experiments/exp-NNN/experiment.py` + `meta.json`)
```python
def _stage_provenance(ws: Path, *rels: str) -> None:
    if not (ws / ".git").exists():
        return
    present = [rel for rel in rels if (ws / rel).exists()]
    if not present:
        return
    subprocess.run(["git", "add", "--", *present],
                   cwd=str(ws), capture_output=True, text=True, check=False)
```
(Anti-pattern, RESEARCH §Anti-Patterns: `git add -A` trips the leak guard on `control/raw/last-error.txt`.)

### Atomic overwrite (crash-safe file replace)
**Source:** RESEARCH §Don't Hand-Roll (tempfile + os.replace); `init_workspace` uses `write_text` on freshly-built content
**Apply to:** `regen_strategy.py` (D-12 full overwrite), `rebuild_ledger.py` (atomic ledger rebuild)
```python
import os, tempfile
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(rendered)
os.replace(tmp, path)   # crash-safe swap
```

## Pattern Assignments

### `scripts/metric_registry.py` (utility, stdlib data module)

**Analog:** `scripts/cv_evidence.py` lines 37-60 (a module-level enum tuple + explanatory notes, imported by other scripts).

**Pattern to replicate:** a module-level constant dict + an argparse-`choices` tuple derived from it, exactly like `cv_evidence.CV_SCHEMES = ("GroupKFold", "TimeSeriesSplit", "StratifiedKFold", "KFold")` which `analyze_data.py` imports as `choices=cve.CV_SCHEMES`. The full `REGISTRY` dict + `SUPPORTED = tuple(REGISTRY)` is specified in RESEARCH §Pattern 1 (lines 224-253) — copy it directly.

**Critical constraint:** stdlib ONLY (`from math import inf`). NO sklearn import — the module names the callable as a string (`"sklearn_callable"`) that the harness resolves inside the ML env. This is the D-06 split applied to metrics; importing this in the stdlib recorder must never pull scikit-learn.

---

### `scripts/experiment_meta.py` (utility, schema + (de)serialize)

**Analog:** `scripts/competition_doc.py` (a single-purpose, importable, stdlib-only helper with NO side effects on import — see its docstring lines 18: *"Portability: stdlib-only, importable, no side effects on import."*).

**Pattern to replicate:** pure functions, no `main()`, no I/O at import time. Provides `to_ledger_row(meta: dict) -> dict` (the `meta.json` → one-line `ledger.jsonl` subset, RESEARCH §Ledger lines 484-486) and a `validate_meta(meta) -> list[str]` returning error strings. Both `record_experiment.py` and `rebuild_ledger.py` import it so the row schema lives in ONE place — the same single-source-of-truth rationale `competition_doc.replace_section` embodies for section merging.

---

### `scripts/set_metric.py` (config-setter, request-response) — EXACT analog

**Analog:** `scripts/capture_competition.py` lines 244-247 (the `--set-competition-type` argparse) + lines 263-266 (the setter-mode early-return branch); reinforced by `analyze_data.py` lines 388-393 + 456-462.

**Argparse (choices-validated enum), copy this shape** (`capture_competition.py` 244-247):
```python
ap.add_argument("--set-competition-type", choices=COMPETITION_TYPES, default=None,
                help="Commit competition.type (D-14). The AI passes the enum it "
                     "classified from the fenced evidence; tooling writes it. ...")
```
→ becomes `--metric`, `choices=metric_registry.SUPPORTED`, plus (for `name="custom"`) an explicit `--greater-is-better/--no-greater-is-better` because direction can't be looked up (RESEARCH §Pattern 1 line 250, §Summary line 64).

**Setter-mode early return, copy this shape** (`capture_competition.py` 263-266):
```python
if args.set_competition_type is not None:
    return set_config_field(config_path, ("competition", "type"), args.set_competition_type)
```
→ becomes `set_config_field(config_path, ("metric",), {"name": ..., "greater_is_better": ...})`.

**Block-don't-guess (D-08):** if the competition metric was never captured / is unmappable, print a clear message and return a **reserved exit code** (mirror `capture_competition.py`'s `LIMIT_NEEDS_USER` posture, lines 377-385) rather than writing a guessed value. Never auto-map a competition metric onto a "close" scorer (RESEARCH §Anti-Patterns line 399).

---

### `scripts/scaffold_experiment.py` (scaffolder, file-I/O) — EXACT analog

**Analog:** `scripts/init_workspace.py` — `scaffold` (lines 301-333), `_render_text` (95-102), `create_if_absent` (105-111), `_iso_now` (90-92).

**Template render (reuse the imported helper):** `_render_text("experiment.py.tmpl", mapping)` then `create_if_absent(exp_dir / "experiment.py", ...)` — do NOT reimplement templating (`init_workspace._render_text` uses `string.Template.safe_substitute`, lines 95-102).

**Id-cursor read-increment-write** (RESEARCH §Runtime State Inventory line 523): read `state.json.next_exp_id` (scaffolded to `1`, `state.json.tmpl`), mint `exp-NNN` zero-padded (`f"exp-{n:03d}"`), then write the incremented cursor back via `set_config_field(state_path, ("next_exp_id",), n + 1)` — the SAME direct-setter used for config leaves (init_workspace 475-519 works on any control-plane JSON path, not just config.json). Guard with the fail-clear read block above.

**Directory creation:** mirror `init_workspace` WORKSPACE_DIRS loop (322-324) — create `experiments/exp-NNN/artifacts/` with `mkdir(parents=True, exist_ok=True)`.

---

### `scripts/run_local.py` (runner, request-response) — EXACT analog

**Analog:** `scripts/analyze_data.py` `run_adversarial_validation` lines 142-190 — THE existing `uv run` shell-out; copy its posture verbatim.

**The shell-out (copy this exactly, adjust argv):** lines 151-176
```python
if shutil.which("uv") is None:
    return {"status": "skipped", "reason": "uv not on PATH"}
...
cmd = ["uv", "run", "--no-sync", "python", str(exp_py),
       "--exp-dir", str(exp_dir), "--slug", slug]
try:
    proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, timeout=<N>)
except (subprocess.TimeoutExpired, OSError) as exc:
    return {"status": "skipped", "reason": f"uv run failed: {exc}"}
if proc.returncode != 0:
    return {"status": "skipped", "reason": "ML env absent (uv run non-zero)"}
```
**Key rules (RESEARCH §Pattern 4 line 388, §Pitfall 5 lines 557-561):**
- `--no-sync` is load-bearing: a missing ML env → clean non-zero (D-06 FAILED / degrade), NEVER a silent network install. On non-zero, print `"workspace ML env not synced — run \`uv sync\`"` and record nothing / a clear SKIPPED, exactly like the AV degrade.
- **NEVER trust stdout for a score.** Unlike AV (which parses stdout JSON), the runner captures ONLY the exit code and hands off to `record_experiment.py`, which reads the on-disk `result.json` (D-05). Do not scrape a score line (RESEARCH §Anti-Patterns line 395, D-05).
- Timeout-bounded (`timeout=`), like the AV call's `timeout=600` (line 165).

---

### `scripts/record_experiment.py` (recorder/validator, transform+file-I/O)

**Analog:** `scripts/capture_competition.py` `main` (the fetch → validate → `set_config_field` + `replace_section` + `_stage_provenance` spine, lines 257-410) — the same emit-external / verify / tooling-persist shape.

**Fail-closed validation ladder (D-06), implement in order** (RESEARCH §result.json schema lines 441-450): result.json exists+parses → required keys+types & `len(fold_scores)==n_folds` & `n_folds>=2` → every score `math.isfinite` → **`abs(cv_mean - statistics.mean(fold_scores)) < 1e-6`** (the anti-lie recompute — NEVER trust the emitted mean, RESEARCH §Pitfall 2 / Anti-Patterns line 395) → `metric` matches `config.json.metric.name` (or `"custom"`) → `range_lo <= cv_mean <= range_hi` from `metric_registry`. ANY failure → still write `meta.json` with `status="FAILED"`, `failure_reason=<enum>`, and a VERDICT stub (a failure is recorded WITH a verdict, never dropped — criterion 3).

**Provenance from stdlib** (RESEARCH §Provenance lines 489-499) — no ML import:
```python
import hashlib, subprocess, uuid
run_id = uuid.uuid4().hex
artifact_hash = "sha256:" + hashlib.sha256((exp_dir / "experiment.py").read_bytes()).hexdigest()
commit = subprocess.run(["git","rev-parse","--short","HEAD"], cwd=ws,
                        capture_output=True, text=True).stdout.strip()
dirty  = bool(subprocess.run(["git","status","--porcelain","--", str(exp_dir)], cwd=ws,
                             capture_output=True, text=True).stdout.strip())
```

**Persist:** write `meta.json` (canonical) via template+`json.dumps(..., indent=2)`; append the derived row to `control/ledger.jsonl` (via `experiment_meta.to_ledger_row`); create `VERDICT.md` from template via `create_if_absent`; stage `experiment.py`+`meta.json` by explicit path (`_stage_provenance`). Reads `config.json.metric` with the fail-clear block; imports `metric_registry` for the range check (stdlib, no sklearn).

---

### `scripts/rebuild_ledger.py` (index-builder, batch)

**Analog:** the glob-derive-write pattern of `cv_evidence.write_evidence` (structural-facts→JSON) + `init_workspace` atomic write; row derivation delegated to `experiment_meta.to_ledger_row`.

**Semantics (RESEARCH §rebuild_ledger lines 501-504):** glob `experiments/exp-*/meta.json`, sort by `exp_id`, derive each row via `experiment_meta.to_ledger_row`, write `control/ledger.jsonl` **atomically** (tempfile + `os.replace`). Full rebuild (a pure function of the folders — MEM-01) preferred over incremental. **Corrupt/partial `meta.json`:** do NOT fabricate — on `JSONDecodeError` or missing required keys, emit a `stderr` warning naming the folder and SKIP it (mirrors the fail-clear-and-flag posture of `analyze_data.py`'s missing-capture note, lines 424-429). Never partial-writes the live file (atomic replace).

---

### `scripts/regen_strategy.py` (doc-renderer, transform)

**Analog:** `scripts/analyze_data.py` section-body builders (`_cv_section_body`, `_av_section_ok`, lines 251-347 — tooling renders FACT sections from evidence) for the FACTS half; `init_workspace` atomic write for the overwrite.

**Hybrid facts+reasoning (D-11/D-12):**
- FACTS from `ledger.jsonl` (tooling-rendered, cannot drift): current-best = `max/min(cv_mean)` by `greater_is_better` among `status=="SUCCESS"` rows; tried-list digest = every row `exp-NNN | idea | status | cv_mean±std | verdict link` (RESEARCH lines 509-511). Empty ledger → "None yet." Reads `config.json.metric.greater_is_better` for the direction (fail-clear block).
- REASONING (AI-authored, fresh) delivered via `--reasoning-file <path>` argparse (RESEARCH line 512) — a markdown fragment the tool splices into the reasoning sections; keeps mechanical sections tooling-owned.
- **FULL OVERWRITE (D-12), unlike competition.md's `replace_section`:** render header+facts+reasoning to `strategy.md.tmp`, `os.replace` onto `strategy.md`. Header verbatim: *"Generated each cycle from control/ledger.jsonl — manual edits are overwritten."* Do NOT use `replace_section` here (that's section-safe-merge for competition.md; strategy.md is deliberately the opposite — D-12).

---

### `scripts/templates/experiment.py.tmpl` (ML-env template, generated code)

**Analog:** `scripts/analyze_data.py` `_AV_RUNNER_SRC` lines 73-136 — the ONLY existing example of ML-stack code that runs under `uv run` (imports pandas/sklearn, has its own argparse `main()`, `raise SystemExit(main())`). The scaffold template mirrors this shape but ships as a `.tmpl` file (like `strategy.md.tmpl`) that `scaffold_experiment.py` renders.

**Ships two helpers the AI plugs into (both specified verbatim in RESEARCH):**
- `resolve_data_dir(slug, override)` — RESEARCH §Pattern 2 lines 286-293 (backend detection is CODE not config: prefer `/kaggle/input/<slug>/`, else `Path(__file__).resolve().parents[2] / "data"`). This is the D-03 Phase-4 seam — the same file runs on a kernel untouched.
- `run_cv(*, X, y, model_factory, preprocess_factory=None, ...)` — RESEARCH §Pattern 3 lines 301-382 (the full harness; copy it). Leakage-safe BY CONSTRUCTION: the harness calls `fit_transform(train)/transform(val)` itself; the AI supplies an UNFITTED `preprocess_factory()`, never a fitted object (§Anti-leakage note line 384, criterion 1). Custom splitter + custom metric callable are first-class (D-07 tension).

**Template argparse contract** matches what `run_local.py` shells: `--exp-dir`, `--slug`. Writes `result.json` at `exp_dir/result.json` (D-05: notebook emits; recorder verifies). Uses a LightGBM starter the AI edits (RESEARCH structure line 213). Stable-API floors only (pandas `>=2.2`, no pandas-3.0-only behavior — §Pitfall 6).

---

### `scripts/templates/meta.json.tmpl` & `VERDICT.md.tmpl` (templates) — EXACT analog

**Analog:** `scripts/templates/config.json.tmpl` (for `meta.json.tmpl` — a JSON skeleton with `__PLACEHOLDER__`-style tokens rendered by `_render_text`) and `scripts/templates/strategy.md.tmpl` (for `VERDICT.md.tmpl` — a prose skeleton with a header note). `meta.json` full shape is RESEARCH §Ledger lines 455-482. VERDICT.md is worked/didn't/why prose that REFERENCES tooling-written numbers, never types them (D-05, Claude's Discretion).

---

### Modified: `control/config.json` (+`metric`), `control/state.json` (cursor), `strategy.md`, workspace `pyproject.toml`

- **`config.json` gains `metric`:** a NEW reserved-null key, filled ONLY by `set_metric.py` via `set_config_field` — same mechanism/rationale as Phase-2's `cv.scheme`/`competition.type` (config.json.tmpl lines 5-7). The template (`config.json.tmpl`) should reserve `"metric": null` alongside the existing reserved keys, so `write_control_json`'s merge adds the structure and the setter fills the leaf.
- **`state.json.next_exp_id`:** already scaffolded to `1` (`state.json.tmpl` line 3) — `scaffold_experiment.py` read-increments it (no template change; a runtime cursor).
- **`strategy.md`:** flips from the static `strategy.md.tmpl` stub to a per-cycle `regen_strategy.py` overwrite (D-12). The tmpl's `## Current best` / `## Hypothesis queue` / `## Log of moves` sections map to the regen's FACTS (current-best, tried-list) + REASONING (hypothesis queue) layout.
- **workspace `pyproject.toml`:** extend the EXISTING floors in `scripts/templates/pyproject.toml.tmpl` (lines 22-25 already have `pandas>=2.2`, `scikit-learn>=1.5`) by adding `numpy>=1.26`, `lightgbm>=4.5`, `xgboost>=2.1`, `catboost>=1.2` (RESEARCH §Standard Stack lines 118-128). FLOORS not newest majors (Kaggle-image parity, §Pitfall 6). Runtime pip install forbidden; operator runs `uv sync`. NOTE: this edits the WORKSPACE template, NOT the skill repo's own `pyproject.toml`.

## No Analog Found

None. Every Phase-3 file maps to an existing same-repo analog. The only genuinely new *shape* is the ML-env `run_cv` harness inside `experiment.py.tmpl`, and even that has a direct precedent in `analyze_data._AV_RUNNER_SRC` (ML code run behind `uv run`) — plus RESEARCH ships the harness source verbatim (§Pattern 3), so the planner copies rather than derives.

## Metadata

**Analog search scope:** `scripts/*.py` (11 scripts), `scripts/templates/*.tmpl` (10 templates), `SKILL.md`.
**Files scanned in full:** `analyze_data.py`, `capture_competition.py`, `init_workspace.py`, `competition_doc.py`; partial: `cv_evidence.py`, `kaggle_gateway.py`, `SKILL.md`; templates: `config.json.tmpl`, `state.json.tmpl`, `strategy.md.tmpl`, `pyproject.toml.tmpl`.
**Pattern extraction date:** 2026-07-11
```