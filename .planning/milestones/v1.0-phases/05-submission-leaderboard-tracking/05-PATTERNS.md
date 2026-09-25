# Phase 5: Submission & Leaderboard Tracking - Pattern Map

**Mapped:** 2026-07-12
**Files analyzed:** 22 (4 new scripts, 6 modified, 9 new tests, 1 fixture dir, 2 doc/config)
**Analogs found:** 21 / 22 (1 with no analog: the D-05/D-06 gate policy)

This project has exactly two tiers (CLAUDE.md §Stack Patterns):

| Tier | Rules | Members |
|------|-------|---------|
| **Plumbing (stdlib-only)** | `argparse` in / **exit code** out, self-locating `Path(__file__)`, `--workspace`-driven, **never interactive**, never a bare `subprocess` to `kaggle`, never echoes a raw CLI buffer | all `scripts/*.py` |
| **ML tier** | may import numpy/pandas/sklearn; **imports NO skill code** (kernel-portable, Phase 3 D-03) | `scripts/templates/experiment.py.tmpl` only |

Every new Phase 5 file is plumbing except the `run_cv` extension. **Do not cross the tiers.**

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/submissions_log.py` **(NEW)** | module (importable, no `main()`) | schema + file I/O | `scripts/experiment_meta.py` (+ `rebuild_ledger._atomic_write`) | **exact** |
| `scripts/check_submission.py` **(NEW)** | entry point / validator | read-only request-response | `scripts/record_experiment.py` (fail-closed validation ladder) + `scripts/cv_evidence.py` (compute-and-render, never commits) | **role-match** |
| `scripts/submit.py` **(NEW)** | entry point / side-effecting | request-response + bounded poll | `scripts/push_kernel.py` (write handoff) + `scripts/poll_kernel.py` (poll/detach) | **role-match** |
| `scripts/fetch_lb.py` **(NEW)** | entry point / resumable poller | polling + in-place status transition | `scripts/poll_kernel.py` (resume-from-handoff) + `scripts/rebuild_ledger.py` (`--reconcile` = rebuild-from-canonical) | **exact** |
| gate policy (D-05/D-06/D-08) — `check_submission.py` or a `submission_gate.py` | pure decision fn | transform | **NO ANALOG** (see §No Analog Found) — nearest posture: `regen_strategy._current_best_body` (direction-aware best pick) | **partial** |
| CV→LB join + rank-inversion alarm (D-10) — a `lb_gap.py` module | pure derived-view fn | transform / join | `scripts/regen_strategy.py` `_read_ledger` + `_current_best_body` | **role-match** |
| `scripts/kaggle_gateway.py` **(MOD)** | config / constants | — | itself, lines 38–48 (the reserved-code table) | **exact** |
| `scripts/templates/experiment.py.tmpl` **(MOD)** | ML harness | batch transform + file-out | itself, `run_cv` lines 100–162 | **exact** |
| `scripts/scaffold_experiment.py` **(MOD, likely)** | generator | template render | itself, lines ~170–200 (literal rendering) | **exact** |
| `scripts/regen_strategy.py` + `templates/strategy.md.tmpl` **(MOD)** | renderer | derived view | itself, `_render` lines 157–169 | **exact** |
| `SKILL.md` **(MOD)** | doc | — | itself, §Scripts table lines 365–382 + §gate protocol lines 169–180 | **exact** |
| `references/kaggle-cli-behavior.md` **(MOD)** | doc / fixture record | — | itself (Phase 2/4 entries) | **exact** |
| `.gitignore` / `templates/gitignore.tmpl` **(MOD?)** | config | — | itself | **exact** — ⚠ see §Shared Patterns G |
| `tests/test_submissions_log.py` **(NEW)** | test | — | `tests/test_experiment_meta.py` | **exact** |
| `tests/test_check_submission.py` **(NEW)** | test | — | `tests/test_gateway.py` (monkeypatch gateway) | **exact** |
| `tests/test_submit.py` **(NEW)** | test | — | `tests/test_gateway.py` + `tests/test_poll_kernel.py::test_source_routes_through_gateway` | **exact** |
| `tests/test_fetch_lb.py` **(NEW)** | test | — | `tests/test_poll_kernel.py` (`_FakeClock` + `_sequence`) | **exact** |
| `tests/test_budget.py` **(NEW)** | test | — | `tests/test_poll_kernel.py` (pure-fn unit) | **role-match** |
| `tests/test_gate_policy.py` **(NEW)** | test | — | `tests/test_metric_registry.py` (pure-fn matrix) | **role-match** |
| `tests/test_lb_gap.py` **(NEW)** | test | — | `tests/test_regen_strategy.py` | **role-match** |
| `tests/test_submission_live.py` **(NEW)** | test (live) | — | `tests/test_kernel_live.py` / `tests/test_competition_live.py` | **exact** |
| `tests/fixtures/submissions/*.json` **(NEW)** | fixture | — | `tests/fixtures/status/*.txt` | **exact** |
| `tests/test_run_cv.py` **(MOD)** | test | — | itself, lines 21–67 (spy-transformer fold test) | **exact** |

---

## Pattern Assignments

### `scripts/submissions_log.py` (NEW — module, schema + file I/O)

**Analog:** `scripts/experiment_meta.py` — **this is the direct structural twin.** `experiment_meta.py` is
"the ONE source of the `meta.json` ⇄ `ledger.jsonl` schema", imported by *both* `record_experiment.py` (writes
a row) and `rebuild_ledger.py` (rebuilds all rows). `submissions_log.py` is the identical shape: the ONE source
of the `submissions.jsonl` row schema + status/score parse, imported by all three entry points **plus**
`regen_strategy.py`. Copy its **module contract**: importable, **no `main()`**, no side effects on import,
stdlib-only (so importing it never drags in the ML stack — the Phase 3 D-06 split).

**Module docstring + schema-constants pattern** (`experiment_meta.py:22–56`):
```python
"""...
Portability (CLAUDE.md §Stack Patterns): stdlib-only, importable, NO side effects on
import, NO ``main()`` — mirrors ``competition_doc.py``. Importing it pulls no ML stack
(the D-06 stdlib-plumbing split): the recorder can import it without dragging in
sklearn/pandas/numpy.
"""
from __future__ import annotations

STATUSES = ("SUCCESS", "FAILED")
REQUIRED_TOP_KEYS = ("exp_id", "status")
LEDGER_ROW_KEYS = (          # fixed order → a full rebuild is BYTE-STABLE
    "exp_id", "status", "idea", "metric", "greater_is_better", "cv_mean", "cv_std",
    "git_commit", "seed", "created", "verdict_path",
)
```
→ Phase 5 emits `SUB_STATUSES = ("PENDING", "SCORED", "FAILED")` and a fixed-order
`SUBMISSION_ROW_KEYS` tuple (RESEARCH §R6 gives the 14-key schema). **Fixed key order is load-bearing** —
it is what makes an atomic full rewrite byte-stable.

**Validate-don't-fabricate pattern** (`experiment_meta.py:87–125`) — returns a list of human-readable
error strings, `[]` == valid; the *caller* decides to skip/block. Copy this for a submissions-row validator:
```python
def validate_meta(meta: dict) -> list[str]:
    if not isinstance(meta, dict):
        return [f"meta must be a JSON object, got {type(meta).__name__}"]
    errors: list[str] = []
    for key in REQUIRED_TOP_KEYS:
        if key not in meta or meta[key] in (None, ""):
            errors.append(f"missing required key: {key}")
    ...
    return errors
```

**Atomic rewrite pattern** — `submissions.jsonl` needs an in-place `PENDING → SCORED` transition
(RESEARCH §R5 option (a)). The exact established mechanism is `rebuild_ledger.py:76–84`:
```python
def _atomic_write(path: Path, text: str) -> None:
    """Crash-safe overwrite: render to a sibling ``.tmp`` then ``os.replace``.

    The live target is never partial-written; on a crash the previous file survives.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
```
And the JSONL render (`rebuild_ledger.py:102–107`) — **compact separators, newline-terminated, byte-empty when
empty**:
```python
lines = [json.dumps(row, separators=(",", ":")) for row in rows]
text = ("\n".join(lines) + "\n") if lines else ""
_atomic_write(ws / "control" / "ledger.jsonl", text)
```
→ Use `separators=(",", ":")` for `submissions.jsonl` too (git-diffable one-line-per-row).

**Fail-clear JSONL read pattern** (`regen_strategy.py:49–75`) — a single malformed line must never abort with
a traceback; skip-and-warn, and **skip non-dict rows** so a scalar line cannot later raise `AttributeError`:
```python
for line in path.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
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

**Status-literal parse pattern** — `poll_kernel.py:54–98` is the *exact* precedent for the
`"SubmissionStatus.COMPLETE"` trap. Copy the **anchored-regex, never-substring-grep** posture and the
`None == transient, never a false terminal` contract:
```python
# poll_kernel.py:59–66
TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"}
IN_FLIGHT = {"QUEUED", "RUNNING", "NEW_SCRIPT", "CANCEL_REQUESTED"}
# Anchored ... tolerates both the `KernelWorkerStatus.NAME` and a bare `NAME` render.
_STATUS_RE = re.compile(r'status\s+"(?:KernelWorkerStatus\.)?([A-Z_]+)"')

# poll_kernel.py:89–98
def classify_status(combined: str) -> str | None:
    """Return the KernelWorkerStatus token from a status buffer, or ``None``.

    ``None`` means the buffer was unparseable (a transient blip / garbage) and
    the caller MUST retry — it is NEVER a false terminal (D-10).
    """
    m = _STATUS_RE.search(combined)
    return m.group(1) if m else None
```
→ Phase 5's is `_SUB_STATUS_RE = re.compile(r"^(?:SubmissionStatus\.)?(PENDING|COMPLETE|ERROR)$")` with
`_TO_OURS = {"PENDING": "PENDING", "COMPLETE": "SCORED", "ERROR": "FAILED"}`, `parse_status() -> str | None`.
`parse_score()` returns `float | None` — **`""` → `None`, never `0.0`** (RESEARCH Pitfall 3).

---

### `scripts/check_submission.py` (NEW — entry point, FREE / read-only)

**Analog (validation ladder):** `scripts/record_experiment.py` — the codebase's canonical **fail-closed
validation ladder that returns a machine reason string, never a boolean**. `check_submission` is the same
shape applied to a CSV instead of a `result.json`.

**⚠ VERIFIED FOR THE PLANNER — RESEARCH assumption A4 is RESOLVED (do not re-verify):**
`record_experiment._validate_result` (lines 143–178) checks **key PRESENCE only** — it never rejects unknown
keys:
```python
# record_experiment.py:79-80
REQUIRED_RESULT_KEYS = ("metric", "n_folds", "fold_scores", "cv_mean", "cv_std")

# record_experiment.py:150-152  — presence-only; additive keys are TOLERATED
for key in REQUIRED_RESULT_KEYS:
    if key not in result:
        return "schema_invalid"
```
**⇒ Adding `submission_path` to `result.json` (D-09) is SAFE — the recorder will not fail the experiment.**
Better still, `record_experiment.py:427` already does `"artifacts": valid_result.get("artifacts", [])`, so
appending `"submission.csv"` to `result["artifacts"]` flows into `meta.json` **with zero recorder changes.**

**Failure-reason enum pattern** (`record_experiment.py:62–63`) — a closed tuple of machine reasons, so the
message layer can name *why*:
```python
FAILURE_REASONS = ("missing_result", "schema_invalid", "non_finite", "out_of_range",
                   "kernel_error")
```
→ D-02 wants a parallel closed enum, e.g.
`VALIDATION_REASONS = ("header_mismatch", "row_count_mismatch", "id_set_mismatch", "blank_prediction", "no_sample_reference")`.

**Sample-file resolution — REUSE, do not re-derive** (`capture_competition.py:147–177`). This is the
`submission_csv_in_manifest` heuristic D-02 must consume. Note the code's **own** weakness comment:
```python
    names = [str(f.get("name", "")) for f in files if isinstance(f, dict)]
    submission_csv = next(
        (n for n in names if "submission" in n.lower() and n.lower().endswith(".csv")),
        None,
    )
    ...
    signals = {
        "code_language_in_rules": code_signal,
        # WEAK — names vary (titanic's is gender_submission.csv, not sample_submission.csv).
        "submission_csv_in_manifest": submission_csv,
        "test_csv_in_manifest": test_csv,
    }
```
**Where it is persisted (NOT `config.json`):** `capture_competition.py:75` →
`TYPE_SIGNALS_REL = "control/raw/competition-type-signals.json"`, written at lines 325–334 under
`signals.submission_csv_in_manifest`. The extracted file lands in `data/` via `download_data.py`.
→ Resolution ladder: `control/raw/competition-type-signals.json` → `data/<name>` → glob `data/*submission*.csv`
→ `data/test.csv` first column → **fail closed (exit 65)**. **Print which file was picked** so a human can
spot a wrong pick.

**Read-only-CLI + `--format json` parse pattern** — every `competitions submissions` call routes through the
gateway and reuses its banner-tolerant parser (`kaggle_gateway.py:102–121`). **Never a last-line parse** — the
CLI pretty-prints across many lines:
```python
def _parse_json_array(text: str):
    """Parse a JSON array from CLI output, tolerating a leading banner line.

    CLI 2.2.3 **pretty-prints** the array across MANY lines ... so a last-line-only
    parse fails on the closing ``]``. Parse the WHOLE payload; if that fails because a
    banner precedes the array, retry from the first ``[``. Returns the list, or ``None``.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        if start == -1:
            return None
        try:
            parsed = json.loads(text[start:])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, list) else None
```

**Compute-and-render-but-never-commit posture** — `scripts/cv_evidence.py` is the precedent for a script that
renders decision material for a human/AI and **deliberately does not act on it** ("a NON-authoritative advisory
`recommend` hint the AI reasons over; never commits `cv.scheme`", `SKILL.md:372`). `check_submission.py` is the
same: it renders the recommendation; **the human decides; `submit.py` acts.**

---

### `scripts/submit.py` (NEW — entry point, spends the slot)

**Analog:** `scripts/poll_kernel.py` for the poll/detach half; `scripts/push_kernel.py` for the
"side-effecting call → write a handoff file" half.

**Self-location + gateway import + exit-code block** (`poll_kernel.py:37–52, 78–86`) — copy verbatim:
```python
from __future__ import annotations

import argparse, json, random, re, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kaggle_gateway import dump_last_error, run_kaggle  # noqa: E402

# Reserved exit codes — DISTINCT per outcome so the SKILL/caller can branch.
# 0 = COMPLETE; the rest are non-zero and mutually distinct. 124/127 are reserved
# by the gateway (timeout / CLI-missing) and surfaced verbatim.
EXIT_COMPLETE = 0
EXIT_TERMINAL_FAIL = 2   # kernel reached ERROR or CANCEL_ACKNOWLEDGED
EXIT_DETACHED = 3        # our-side budget expired, kernel still in-flight (D-09)
EXIT_TRANSIENT_FAIL = 4  # consecutive transient errors exceeded the threshold
```
→ `submit.py` / `fetch_lb.py` mirror **exactly** these local codes: `0 = SCORED`, `2 = submission FAILED`,
`3 = DETACHED (PENDING — re-run fetch_lb)`, `4 = transient / fail-closed`.

**Gateway routing — never a bare subprocess** (`poll_kernel.py:280–283`):
```python
    def _status_fn():
        # Route the status poll through the gateway (no-echo, timeout-bounded).
        # NEVER a bare subprocess and NEVER a cancel argv (detach-not-cancel).
        return run_kaggle("kernels", "status", slug, timeout=args.poll_timeout)
```
→ `run_kaggle("competitions", "submit", slug, "-f", str(csv_path), "-m", message, timeout=300)` and
`run_kaggle("competitions", "submissions", slug, "--format", "json", "--page-size", "200", timeout=60)`.
**Never pass `-k` / `-v` / `--sandbox`** (RESEARCH §R1: `--sandbox` is a host-admin flag, NOT a dry run).

**Bounded-poll + detach-not-cancel** — `poll_kernel.py:101–195` is the shape to reuse.
**Import `compute_delay` from `poll_kernel`; do NOT fork it and do NOT refactor `poll_loop`** (Phase 4 is
complete and verified — RESEARCH §R5):
```python
# poll_kernel.py:101-114  — full jitter, provably budget-safe (sleep ∈ (0, base])
def compute_delay(attempt: int, rng: random.Random | None = None) -> float:
    base = min(BASE_DELAY * (BACKOFF_MULTIPLIER ** attempt), MAX_DELAY)
    if rng is None:
        return base
    return rng.uniform(0.0, base)
```
The **budget check happens BEFORE the sleep** — copy this ordering (`poll_kernel.py:182–194`):
```python
        # OUR-side budget check BEFORE sleeping: on expiry with an in-flight (or
        # still-indeterminate) kernel, DETACH — never cancel (D-09).
        if (now() - start) >= budget_s:
            return {"terminal": False, "status": "DETACHED", "reason": "budget",
                    "last_out": last_out, "last_token": last_token}
        sleep(compute_delay(attempt, rng=rng))
        attempt += 1
```
Injected `now` / `sleep` / `rng` (`poll_kernel.py:285–293`) is what makes the loop deterministically testable
**with no real waiting** — replicate the injection seam or the tests cannot be written.

**Detach branch → distinct exit code + a resume instruction** (`poll_kernel.py:315–324`):
```python
    if reason == "budget":
        # DETACH, not cancel (D-09): record the detach and stop. A re-run
        # reattaches from the same handoff.
        _write_status(run_path, kernel_run, "DETACHED")
        print(
            f"poll budget ({args.budget}s) expired — {slug} is still running. "
            f"DETACHED (never cancelled); status set to DETACHED in "
            f"{exp_rel}/kernel_run.json. Re-run poll_kernel.py to reattach."
        )
        return EXIT_DETACHED
```
→ Phase 5's detach leaves the `submissions.jsonl` row at `status: "PENDING"` and prints
"re-run `fetch_lb.py`". **⚠ Write-ordering requirement (RESEARCH Pitfall 6): the PENDING row must be written
BEFORE the poll begins** — otherwise a crash mid-poll loses the exp_id↔ref provenance of a spent slot.

**Never-echo + quarantine on failure** (`poll_kernel.py:326–335` + `kaggle_gateway.py:236–250`):
```python
    # reason == "transient": consecutive transient errors exceeded the threshold.
    dump_last_error(ws, result.get("last_out", ""))
    print(
        f"cannot poll: {MAX_CONSECUTIVE_ERRORS} consecutive status errors — "
        "giving up (fail-closed). Raw output withheld (may carry a secret) and "
        "quarantined to control/raw/last-error.txt. Re-run poll_kernel.py to "
        "retry.",
        file=sys.stderr,
    )
    return EXIT_TRANSIENT_FAIL
```
→ The submit stdout is **matched** against the two fail-open literals, then `dump_last_error`'d — **never
printed** (it can carry a token-shaped string). See §Shared Patterns C.

---

### `scripts/fetch_lb.py` (NEW — resumable poller + `--reconcile`)

**Analog (resume):** `poll_kernel.py:259–283` — resume by **re-reading the handoff file**, not by re-doing the
side effect. `poll_kernel` re-reads `kernel_run.json` for the `kernel_slug`; `fetch_lb` re-reads
`submissions.jsonl` for the `PENDING` rows + their `kaggle_ref`. **It never re-submits.**

**Fail-clear handoff read** (`poll_kernel.py:197–224`) — the exact posture for reading `submissions.jsonl`:
```python
def _read_kernel_run(path: Path):
    """Fail-clear read of ``kernel_run.json`` (mirrors record_experiment._read_json).

    Returns the parsed dict, or ``None`` (after a clear message) when the file is
    absent or not valid JSON — the file is left byte-intact and the caller blocks.
    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        print(f"cannot poll: no {path} — push the kernel first (push_kernel.py).",
              file=sys.stderr)
        return None
    ...
```

**Analog (`--reconcile`):** `scripts/rebuild_ledger.py:87–108` — the canonical **"derived state is a pure
function of the authoritative source; a re-run self-heals"** entry point. `fetch_lb --reconcile` is the same
idea with Kaggle (not the folders) as the authoritative source:
```python
def rebuild_ledger_file(ws: Path) -> list[dict]:
    """Rewrite ``control/ledger.jsonl`` as a PURE FUNCTION of the meta folders (atomic).
    ... Because it is a full rebuild (not an incremental append), a hand-corrupted or
    partial ledger self-heals on a re-run.
    """
    rows = _rows_from_folders(ws)
    lines = [json.dumps(row, separators=(",", ":")) for row in rows]
    text = ("\n".join(lines) + "\n") if lines else ""
    _atomic_write(ws / "control" / "ledger.jsonl", text)
    return rows
```
⚠ **Difference to hold:** `submissions.jsonl` is **canonical**, not derived — `--reconcile` back-fills it from
Kaggle (recovering out-of-band submissions), it does not regenerate it wholesale. Rows whose `description` has
no `exp-NNN` prefix get `exp_id: null`.

**Skip-and-warn, never-fabricate** (`rebuild_ledger.py:46–73`) — copy for a corrupt submissions row:
```python
        errors = validate_meta(meta)
        if errors:
            print(
                f"rebuild: skipping {folder} — meta.json failed validation "
                f"(no row fabricated): {'; '.join(errors)}.",
                file=sys.stderr,
            )
            continue
```

---

### `scripts/kaggle_gateway.py` (MODIFIED — 3 new reserved exit codes)

**Analog:** itself. The new codes go **beside** the existing table, with the same comment discipline
(`kaggle_gateway.py:38–48`):
```python
# --------------------------------------------------------------------------- #
# Reserved exit codes (D-10, §17) — sysexits.h-aligned. SKILL.md branches on the
# EXACT values; downstream plan 02-02 imports LIMIT_NEEDS_USER.
#   77 = EX_NOPERM  ("did not have sufficient permission") — the 403 UI gate.
#   78 = EX_CONFIG  ("configuration error") — submission-limit extraction failed
#        → the SKILL must ask the user (D-13 step 2).
# 124 is ALREADY the TimeoutExpired code (GNU-timeout convention) — do NOT reuse;
# 126/127/128+ are bash-reserved — never used for app signals.
# --------------------------------------------------------------------------- #
UI_GATE = 77
LIMIT_NEEDS_USER = 78
```
→ Add (RESEARCH §R6, sysexits-aligned, provably non-colliding):
`VALIDATION_FAILED = 65` (EX_DATAERR), `SUBMIT_UNSUPPORTED = 69` (EX_UNAVAILABLE),
`GATE_BLOCKED = 75` (EX_TEMPFAIL — *"temporary failure; the user is invited to retry"* — exactly D-05's
retryable-after-human-confirmation state, **not an error**).
**Note the two-tier convention** (`poll_kernel.py:78–86` comment): **global sysexits codes live in the
gateway; small script-local codes (2/3/4) express one script's outcomes.** Follow both.
Pinned by test (`tests/test_gateway.py:85–88`):
```python
def test_exit_code_constants():
    gw = _gateway()
    assert gw.UI_GATE == 77
    assert gw.LIMIT_NEEDS_USER == 78
```

---

### `scripts/templates/experiment.py.tmpl` (MODIFIED — D-09 fold-averaged `submission.csv`)

**Analog:** itself, `run_cv` lines 100–162. **This is the ONLY ML-tier file in the phase** — it may use numpy,
it must import **no skill code** (kernel-portability, Phase 3 D-03), and it currently imports only `numpy`
(+ sklearn lazily). **Write the CSV with the stdlib `csv` module** so `run_cv` stays pandas-free.

**The signature to extend** (lines 100–112) — all new args default `None` ⇒ backward-compatible **and**
D-09's "optional/graceful" is satisfied *by construction*:
```python
def run_cv(*, X, y, model_factory, preprocess_factory=None, feature_fn=None,
           metric, registry_entry, cv_scheme, n_splits=5, seed=DEFAULT_SEED,
           groups=None, splitter=None, exp_dir=".", prediction_type=None):
    """Leakage-safe CV fold loop. Writes result.json (D-04) and OOF; returns the result dict.
    ...
    """
    import numpy as np
    metric_fn, ptype = _resolve_metric(metric, registry_entry)
    ptype = prediction_type or ptype
```

**The fold-loop seam** (lines 125–140) — the fitted `pp` and `model` for each fold already exist here; predict
test **inside** the loop, reusing **that same fold's `pp`** (this is what makes the anti-leakage contract hold
for test too):
```python
    for tr, va in split.split(*split_args):
        Xtr, Xva, ytr = Xv[tr], Xv[va], yv[tr]
        if preprocess_factory is not None:
            pp = preprocess_factory()
            Xtr = pp.fit_transform(Xtr, ytr)  # FIT on the train fold only
            Xva = pp.transform(Xva)           # TRANSFORM the val fold — no leakage
        model = model_factory()
        model.fit(Xtr, ytr)
        if ptype == "proba":
            proba = model.predict_proba(Xva)
            pred = proba[:, 1] if proba.shape[1] == 2 else proba
        else:
            pred = model.predict(Xva)
        fold_scores.append(float(metric_fn(yv[va], pred)))
```

**The result-dict + write pattern to extend** (lines 142–162) — note `artifacts` is a plain list and the file
is written with `indent=2` + trailing newline:
```python
    result = {
        "schema_version": 1,
        "metric": metric if isinstance(metric, str) else "custom",
        ...
        "oof_path": "artifacts/oof.npy",
        "written_by": "run_cv",
        "artifacts": ["artifacts/oof.npy"],
    }
    art_dir = Path(exp_dir) / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    np.save(art_dir / "oof.npy", oof)
    (Path(exp_dir) / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
```
→ Add `result["submission_path"] = None` always; set it to `"submission.csv"` and append to
`result["artifacts"]` only when test preds exist. **Write the CSV FLAT at `Path(exp_dir)/"submission.csv"`, NOT
under `artifacts/`** — `pull_kernel.py` pulls kernel output as flat files into `experiments/exp-NNN/`, so the
flat path makes the kernel path work with **zero changes to `pull_kernel.py`** (RESEARCH §R3).

**⚠ THE CORRECTNESS TRAP — the aggregation MUST be type-aware.** `scripts/metric_registry.py:21–37` is the
authority (`prediction_type ∈ {"label", "proba", "raw"}`), and it is **not an edge case** — titanic's default
metric is on the broken path:
```python
# metric_registry.py:21-26
# prediction_type ∈ {"label", "proba", "raw"} tells the harness's run_cv whether to
# call model.predict (label/raw) or model.predict_proba (proba). custom => None.
REGISTRY = {
    "roc_auc":  {"greater_is_better": True,  "prediction_type": "proba", ...},
    "logloss":  {"greater_is_better": False, "prediction_type": "proba", ...},
    "accuracy": {"greater_is_better": True,  "prediction_type": "label", ...},   # ← TITANIC
```
| `prediction_type` | Metrics | Correct fold aggregation |
|---|---|---|
| `proba` | roc_auc, logloss | **mean** across folds (soft-vote) |
| `raw` | rmse, mae, rmsle, mape, r2 | **mean** across folds |
| `label` | **accuracy**, f1, f1_macro, precision, recall, qwk, mcc | ⚠ **MEAN IS WRONG** — averaging 5 folds' `0/1` yields `0.6`. Soft-vote-then-argmax (preferred) / majority-vote (fallback). |

A naive `np.mean(test_preds, axis=0)` emits `0.4`/`0.6` where Kaggle wants `0`/`1` — and **D-02's validator
would pass it** (it only checks headers/count/ids/blanks), so a real slot gets spent on garbage.

**Escape-hatch pattern (Phase 3 D-07 tension)** — the template already treats a callable as first-class
(`_resolve_metric`, lines 79–97: *"A callable `metric` is a first-class escape hatch"*; and `splitter=` bypasses
scheme selection entirely). Follow it: expose `submission_agg=` so the AI can override aggregation **without
editing the harness**.

**Where `X_test` is loaded — the AI-edited block** (lines 199–209). RESEARCH Open Question 2 recommends
pre-loading it *guarded* so the common case is zero-effort and a diagnostic experiment still runs:
```python
    data_dir = resolve_data_dir(args.slug, args.data_dir)

    # ----------------------------------------------------------------------- #
    # AI EDITS BELOW: load the data, build X / y (and `groups` for GroupKFold),
    # then hand unfitted factories to run_cv. This starter assumes a train.csv
    # with a "target" column — adjust to the competition's schema.
    # ----------------------------------------------------------------------- #
    train = pd.read_csv(data_dir / "train.csv")
```

---

### `scripts/scaffold_experiment.py` (MODIFIED — render the submission header literals)

**Analog:** itself. The scaffolder already renders per-experiment **literals** into the template
(`scaffold_experiment.py:170`, `:198` — `exp_id = f"exp-{n:03d}"`, then a substitution mapping containing
`"EXP_ID": exp_id`, `SLUG`, `METRIC_NAME`, `CV_SCHEME`, `registry_entry`). RESEARCH Open Question 3 recommends
rendering the **sample-file header** (id column + target column) the same way — so the harness writes a
correctly-headed `submission.csv` **by construction** and the kernel-portability contract (the experiment
imports no skill code, has no access to `control/`) stays intact. If the header is unavailable at scaffold
time, render `None` → the harness skips emission (graceful, per D-09).

---

### `scripts/regen_strategy.py` + `scripts/templates/strategy.md.tmpl` (MODIFIED — the LB/gap block)

**Analog:** itself. **EXTEND the Phase 3 D-11/D-12 contract — do not fork it.** The split is by *who authors*:
tooling renders FACTS; the AI's `--reasoning-file` is spliced VERBATIM. Add **one more facts renderer** into
`_render`.

**The splice point** (`regen_strategy.py:157–169`) — add `_lb_gap_body(...)` alongside the existing two:
```python
def _render(slug: str, rows: list[dict], greater_is_better: bool, reasoning: str) -> str:
    """Assemble the full strategy.md document (header + FACTS + verbatim REASONING)."""
    title = f"# Strategy — {slug}" if slug else "# Strategy"
    return (
        f"{title}\n\n"
        f"> {HEADER_NOTE}\n\n"
        f"## Current best\n\n"
        f"{_current_best_body(rows, greater_is_better)}\n\n"
        f"## Tried-list digest\n\n"
        f"{_tried_list_body(rows)}\n\n"
        f"## Reasoning (hypothesis queue & next action)\n\n"
        f"{reasoning.strip()}\n"
    )
```

**The facts-renderer pattern to copy** (`regen_strategy.py:115–134`) — **direction-aware**, number sourced
ONLY from the ledger, honest empty-state string, never a fabricated row:
```python
def _current_best_body(rows: list[dict], greater_is_better: bool) -> str:
    """FACT: the best SUCCESS row by the metric's direction, or "None yet." ...
    The number is sourced ONLY from the ledger (never the reasoning file), so it
    cannot be fabricated or drift (T-03-05-01).
    """
    winners = [r for r in rows if r.get("status") == "SUCCESS" and _is_number(r.get("cv_mean"))]
    if not winners:
        return "None yet."
    pick = max if greater_is_better else min
    best = pick(winners, key=lambda r: r["cv_mean"])
```
→ `_lb_gap_body(sub_rows, ledger_rows, greater_is_better)` renders the CV→LB table (exp_id, cv_mean, lb_score,
gap) for SCORED rows + the D-10 alarm — or the **honest** line
*"Divergence alarm: needs ≥2 scored submissions (have N)."* (never fake a signal from one point).

**Direction source** (`regen_strategy.py:78–94`) — `greater_is_better` is read from tooling-written config,
**never guessed**; a missing metric **blocks**:
```python
def _read_greater_is_better(config_path: Path) -> tuple[bool | None, str | None]:
    """Fail-clear read of `config.json.metric.greater_is_better`. Returns (gib, error_msg).

    The direction is what orders the current-best pick, so it MUST come from the
    tooling-written config (T-03-05-04) — never guessed.
    """
```

**Atomic full overwrite** (`regen_strategy.py:172–181`) — unchanged; the whole doc is a pure function of
ledger + submissions + reasoning file.

**The `.tmpl` stub already promises this feature** (`strategy.md.tmpl:20–21`) — Phase 5 makes it real:
```markdown
## Notes
_Discipline: CV-first. Track the CV→LB gap; ration submissions against CV signal._
```

---

### `SKILL.md` (MODIFIED — 3 script rows + the submit gate protocol)

**Analog:** itself. The scripts table (lines 365–382) — copy the row density and the "what it guarantees" voice:
```markdown
| `scripts/poll_kernel.py` | EXP-05/D-09 VERIFIED-enum status classify + bounded jittered backoff; DETACHES (never cancels) on our-side budget expiry — re-run to reattach without re-pushing (exit 0/2/3/4) |
| `scripts/record_experiment.py` | EXP-04/D-05/06 the anti-lie recorder: recompute the mean, attach provenance, persist `meta.json` + ledger row + `VERDICT.md`; a bad run is FAILED-with-verdict... |
```
The **gate-protocol** section (lines 169–180) is the shape D-05's human loop copies — note the standing rule
*"The scripts **never** poll, sleep, or block on stdin. When one prints a reserved exit code..."*:
```markdown
- **Exit 77 (`UI_GATE`)** from `download_data.py`: the rules gate. Surface the exact rules URL...
- **Exit 78 (`LIMIT_NEEDS_USER`)** from `capture_competition.py`: the daily submission limit...
```
→ Add exit **75 (`GATE_BLOCKED`)**, **65 (`VALIDATION_FAILED`)**, **69 (`SUBMIT_UNSUPPORTED`)**, and the
`check_submission → [human decides] → submit → fetch_lb` sequence. **The human confirmation lives HERE, never
in an `input()`** (Phase 2 D-10).

---

### `tests/*` (NEW — the monkeypatch-the-gateway seam)

**Analog:** `tests/test_gateway.py` — **this is THE pattern that makes the submit path testable without ever
spending a slot.** Copy the deferred-import helper + the fake-gateway factory (`test_gateway.py:21–37`):
```python
import importlib
import json


def _gateway():
    """Import scripts/kaggle_gateway.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("kaggle_gateway")


def _fake_run_kaggle(rows):
    """Return a ``run_kaggle`` stand-in yielding ``(0, <json-array line>)``."""
    payload = json.dumps(rows)

    def _fake(*argv, timeout=60):
        return 0, payload + "\n"

    return _fake
```
Used as `monkeypatch.setattr(mod, "run_kaggle", _fake_run_kaggle(rows))` (`test_gateway.py:48`). **Note it is
patched on the *importing* module's namespace** (`poll_kernel.run_kaggle`, `submit.run_kaggle`) because the
scripts do `from kaggle_gateway import run_kaggle`.
→ For `test_submit.py`, capture the **argv** the fake receives — that is how you *prove* the exact command
shape (and that `-k` / `-v` / `--sandbox` are **never** passed) **without executing it.**

**Module-level import is FORBIDDEN** — `tests/conftest.py:1–16` and every test docstring state the rule: the
module is imported **inside** the test body so collection never crashes at RED (`test_poll_kernel.py:1–19`).

**No-echo assertion pattern** (`test_gateway.py:94–125`) — splice a token-shaped sentinel into the fake CLI
buffer and assert it never reaches the message:
```python
GENERIC_403 = (
    "\n403 Client Error: Forbidden for url: "
    "https://api.kaggle.com/v1/competitions.CompetitionApiService/DownloadDataFiles"
    " TOKENLEAK_SENTINEL_kagat_ZZZZ"
)

def test_classify_gate_never_echoes_raw_buffer(monkeypatch):
    """D-11 / T-02-LEAK: the raw combined CLI buffer NEVER appears in the returned message."""
    ...
    msg = gw.classify_gate(GENERIC_403, "titanic")
    assert "TOKENLEAK_SENTINEL" not in msg
    assert "kagat_" not in msg
    assert GENERIC_403 not in msg
```

**Deterministic-clock + sequenced-status pattern for `test_fetch_lb.py`** (`test_poll_kernel.py:32–61`) — copy
verbatim; **no real sleeping**:
```python
def _sequence(items):
    """A status_fn stand-in: yields each item in turn, then repeats the last forever
    (so an over-eager poll loop can never raise StopIteration)."""
    it = iter(items)
    last = {"v": items[-1]}
    def _next():
        try:
            last["v"] = next(it)
        except StopIteration:
            pass
        return last["v"]
    return _next


class _FakeClock:
    """A monotonic clock advanced only by the injected sleep — deterministic, no real waiting."""
    def __init__(self):
        self.t = 0.0
        self.sleeps = []
    def now(self):
        return self.t
    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds
```
And the **detach assertion** (`test_poll_kernel.py:114–129`) — the direct model for
`test_detach_preserves_pending`:
```python
    assert result["terminal"] is False
    assert result["status"] in ("DETACHED", "PENDING")
    assert cancel_calls == [], "poll must NEVER cancel the kernel (detach-not-cancel)"
    assert clock.now() >= 100, "loop must run until the wall-clock budget"
```

**Source-guard test pattern** (`test_poll_kernel.py:132–136`) — a mechanical grep of the module source. This is
the precedent for the phase's **irreversibility guarantee** (`test_no_live_test_ever_submits`):
```python
def test_source_routes_through_gateway():
    """Source-invariant (goes GREEN in 04-02): status polling routes through run_kaggle,
    never a bare subprocess nor a printed raw status buffer."""
    src = (SCRIPTS_DIR / "poll_kernel.py").read_text()
    assert "run_kaggle" in src
```

**Fixture-file convention** (`test_poll_kernel.py:24–29` + `tests/fixtures/status/{queued,running,complete,error,cancel_acknowledged}.txt`):
```python
FIXTURES = Path(__file__).resolve().parent / "fixtures"

def _status(name: str) -> str:
    return (FIXTURES / "status" / f"{name}.txt").read_text()
```
→ `tests/fixtures/submissions/{complete,pending,error,empty,unscored}.json` + `submit_404.txt` /
`submit_upload_failed.txt`, loaded by the identical helper. **Transcribe from the live output in RESEARCH §R1/§R2
— do not invent shapes** (Phase 2 learned this the hard way).

**ML-tier test gating** (`tests/test_run_cv.py:8–18`) — the D-09 tests extend this file and MUST keep the
skip-clean posture (the default offline suite reports SKIPPED, never RED):
```python
import pytest
pytest.importorskip("numpy")
pytest.importorskip("sklearn")

import numpy as np  # noqa: E402  (gated by importorskip above)
from test_resolve_data_dir import render_experiment  # noqa: E402  (shared renderer)
```
The **spy-transformer** test (`test_run_cv.py:21–67`) is the direct model for
`test_test_preds_use_fold_preprocessor` — a fresh spy per fold records disjoint fit/transform row sets:
```python
        def fit_transform(self, X, y=None):
            self.fit_ids = set(np.asarray(X)[:, 0].astype(int).tolist())
            return X
        def transform(self, X):
            self.transform_ids = set(np.asarray(X)[:, 0].astype(int).tolist())
            return X
    ...
        assert spy.fit_ids.isdisjoint(spy.transform_ids)
```

**Live-test convention:** `tests/test_kernel_live.py` / `tests/test_competition_live.py` (`-m live`, excluded by
default via `pyproject.toml` `addopts = "-m 'not live'"`). `test_submission_live.py` copies this — and is
**read-only** (`competitions submissions` only; **never** `submit`).

---

## Shared Patterns

### A. Entry-point skeleton — argparse in / exit code out, never interactive
**Source:** `scripts/poll_kernel.py:237–260`, `scripts/rebuild_ledger.py:111–127`
**Apply to:** `check_submission.py`, `submit.py`, `fetch_lb.py`
```python
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="poll_kernel.py",
        description="Poll a pushed Kaggle kernel to a terminal status under a "
                    "bounded, jittered, 429-safe backoff...",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-dir", required=True,
                    help="Experiment folder relative to the workspace "
                         "(e.g. experiments/exp-001).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()
    exp_dir = (ws / args.exp_dir).resolve()
    ...
    return EXIT_COMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
```
**Non-negotiable:** `main(argv=None)` returns an `int`; `raise SystemExit(main())` at the bottom; **no
`input()` anywhere** — the human loop is SKILL.md's job (Phase 2 D-10).
⚠ **Path confinement (RESEARCH Security):** `--exp-dir` is resolved under `ws/experiments/` — do not regress
IN-01.

### B. Gateway routing — one runner, no bare subprocess
**Source:** `scripts/kaggle_gateway.py:69–96`
**Apply to:** every Kaggle call in `check_submission.py`, `submit.py`, `fetch_lb.py`
```python
def run_kaggle(*argv: str, timeout: int = 60) -> tuple[int, str]:
    """Run ``kaggle <argv>``; return ``(returncode, combined_stdout_stderr)``.
    ...
      * ``kaggle`` absent from PATH → ``(127, "kaggle CLI not found on PATH")``
      * ``TimeoutExpired``          → ``(124, "kaggle timed out")`` — a fixed, secret-free marker
      * otherwise                   → ``(returncode, stdout + "\n" + stderr)``.
    """
    if shutil.which("kaggle") is None:
        return 127, "kaggle CLI not found on PATH"
    try:
        proc = subprocess.run(["kaggle", *argv], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "kaggle timed out"
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")
```
**124 / 127 are surfaced verbatim** by callers — never remapped.

### C. Never echo a CLI buffer — MATCH, then quarantine
**Source:** `scripts/kaggle_gateway.py:236–250` (`dump_last_error`) + its module docstring (lines 11–20)
**Apply to:** `submit.py` (the fail-open literal match), `fetch_lb.py`, `check_submission.py`
```python
LAST_ERROR_REL = "control/raw/last-error.txt"

def dump_last_error(ws: Path, combined: str) -> Path:
    """Quarantine the raw CLI ``combined`` to ``ws/control/raw/last-error.txt`` (D-11).

    Ensures the transient dump is GITIGNORED BEFORE writing the (possibly
    token-shaped) content ... Returns the path written.
    """
    _append_line_if_absent(ws / ".gitignore", LAST_ERROR_REL)
    dump_path = ws / LAST_ERROR_REL
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    dump_path.write_text(combined)
    return dump_path
```
The contract, verbatim from the gateway docstring:
> *captured stdout+stderr is NEVER echoed — a token-shaped string can ride on either stream ... Remediation is
> derived by MATCHING; the raw text is quarantined to a gitignored `control/raw/last-error.txt`, never the
> terminal.*

⇒ `submit.py` matches `("Could not find competition", "Could not submit to competition")` against the buffer
and **prints its own framework-authored message** — it never prints `out`.

### D. 403 / gate classification — reuse, don't re-derive
**Source:** `scripts/kaggle_gateway.py:167–206` (`classify_gate`) → exit **77**
**Apply to:** `submit.py` (submit hits the same 403 as download: rules-not-accepted / phone-verification)
Do **not** write a second gate classifier. `rc != 0` + a 403 → `classify_gate(out, slug)` → print the returned
(secret-free) message → return `UI_GATE`.

### E. Fail-closed on an indeterminate read
**Source:** `kaggle_gateway.preflight_entered` (lines 124–158): *"`None` — indeterminate ... Callers MUST fail
closed on `None` (D-12)"*; `record_experiment._validate_result` (the ladder returns a reason, never a guess).
**Apply to:** D-04's budget count (unfetchable/unparseable ⇒ **block, never guess a count**), D-02's validation,
`parse_status`/`parse_score` returning `None`.

### F. Numbers are tooling-written, never AI-typed
**Source:** `experiment.py.tmpl:18–19` (*"Numbers are TOOLING-WRITTEN (D-05) ... Do not hand-type a CV score
anywhere"*), `regen_strategy.py:115–121` (the current-best number comes from the ledger).
**Apply to:** the LB score (parsed from CLI JSON by `parse_score`), the budget count, the CV→LB gap, the
rank-inversion alarm. `public_score` / `private_score` are stored as **parsed floats or `null`** — never
Kaggle's `""` string.

### G. `.gitignore` — ⚠ VERIFIED, and it needs an explicit stated decision
**Source:** `scripts/templates/gitignore.tmpl`
```gitignore
# Phase 3 experiment artifacts — declared now so .gitignore isn't rewritten later (D-13)
experiments/*/artifacts/
experiments/*/*.csv          # ← submission.csv is ALREADY swept up by this
...
# Tracked-but-anticipated exceptions: keep experiment code + meta.json (Phase 3) and
# the kernel_run.json provenance (Phase 4)
!experiments/*/*.py
!experiments/*/*.ipynb
!experiments/*/meta.json
!experiments/*/kernel_run.json
```
- `experiments/*/submission.csv` is **ignored today.** RESEARCH recommends **leaving it ignored** (it is a heavy
  artifact; provenance is preserved *better* by the `file_sha256` in `submissions.jsonl`, and reproducibility by
  the tracked `experiment.py` + seed + git_commit). **Do NOT add a `!experiments/*/submission.csv` negation.**
  The planner must make this an **explicit, stated decision**, not a silent trip-over.
- `control/submissions.jsonl` is **already tracked** — no rule covers it (only `control/raw/last-error.txt` is
  ignored). ✅ No change needed.
- ⚠ If a rule *is* added, note `kaggle_gateway._append_line_if_absent` (lines 218–233) is the established
  **retrofit** mechanism — editing `gitignore.tmpl` alone does **not** update an already-scaffolded workspace.

### H. Untrusted Kaggle-authored text
**Source:** `scripts/untrusted.py` (`escape_markers` / `wrap_untrusted`), `record_experiment.scan_kernel_log`
(lines 99–118: *"Pure pattern-match ... NEVER echoes the log and NEVER derives an executed path/command from
its content (V5/V7)"*).
**Apply to:** the `description` / status / error text from `competitions submissions`. Match `exp_id` with a
**strict anchored regex** (`^exp-\d{3}\b`); **never** derive a filesystem path or a subprocess argv from
Kaggle-returned text.

---

## No Analog Found

| File / capability | Role | Data Flow | Reason |
|---|---|---|---|
| The **D-05/D-06/D-08 gate policy** (block-by-default + noise-aware CV comparison + assumed-limit last-slot rule) | pure decision fn | transform | **No blocking, human-overridable policy gate exists anywhere in the codebase.** The closest postures are (a) `regen_strategy._current_best_body` for the direction-aware best-pick, and (b) `SKILL.md`'s exit-77/78 protocol for "script blocks, SKILL asks the human" — but the *policy itself* (noise bound `k · cv_std`, the BLOCKED-vs-clear recommendation, the first-submission-is-always-clear baseline) is genuinely new. **Use RESEARCH Pattern 5 as the spec.** Keep it a **pure function** (`is_meaningful(cand_cv, cand_std, best_cv, greater_is_better, k)`) so `tests/test_gate_policy.py` is a plain matrix test with no I/O. |
| The **D-04 UTC-boundary budget count** | pure fn | transform | No existing script does date arithmetic on Kaggle-returned timestamps. **RESEARCH Pattern 3 is the spec**; the trap (naive ISO string ⇒ must `.replace(tzinfo=timezone.utc)` and compare to `datetime.now(timezone.utc)`) has no in-repo precedent to copy. Its *fail-closed sentinel* posture, however, does — see §Shared Patterns E. |

Both are pure functions with no I/O — which is exactly why they are cheap to test exhaustively despite having
no analog.

---

## Metadata

**Analog search scope:** `scripts/` (23 modules), `scripts/templates/` (14 templates), `tests/` (33 files),
`tests/fixtures/`, `SKILL.md`, `references/`
**Files scanned:** 20 read (11 in full, 9 targeted)
**Pattern extraction date:** 2026-07-12

**Assumption resolved during mapping (planner: do not re-verify):**
- **RESEARCH A4 — RESOLVED ✅.** `record_experiment._validate_result` (lines 143–178) is **presence-only**
  (`for key in REQUIRED_RESULT_KEYS: if key not in result: return "schema_invalid"`). It does **not** reject
  unknown keys. Adding `submission_path` to `result.json` is safe, and appending `"submission.csv"` to
  `result["artifacts"]` flows into `meta.json` automatically via `record_experiment.py:427`
  (`"artifacts": valid_result.get("artifacts", [])`) with **zero recorder changes.**
