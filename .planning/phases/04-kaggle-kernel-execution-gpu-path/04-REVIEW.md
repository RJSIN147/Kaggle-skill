---
phase: 04-kaggle-kernel-execution-gpu-path
reviewed: 2026-07-11T20:41:03Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - scripts/convert_notebook.py
  - scripts/push_kernel.py
  - scripts/poll_kernel.py
  - scripts/pull_kernel.py
  - scripts/record_experiment.py
  - scripts/templates/kernel-metadata.json.tmpl
  - scripts/templates/config.json.tmpl
  - scripts/templates/pyproject.toml.tmpl
  - scripts/templates/gitignore.tmpl
  - SKILL.md
findings:
  critical: 2
  warning: 7
  info: 3
  total: 12
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-07-11T20:41:03Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the Phase 4 kernel-path scripts (`convert -> push -> poll -> pull -> record`) plus
their templates and `SKILL.md`. The good news: the "never echo credentials" and "detach, not
cancel" guarantees are implemented correctly and consistently — `run_kaggle`'s combined
stdout/stderr buffer is never `print()`-ed anywhere in these five scripts, only quarantined to
`control/raw/last-error.txt` or written to `kernel_log.txt`, and `poll_kernel.py` genuinely never
issues a `kernels cancel`.

However, the **anti-silent-failure guarantee that is this phase's core deliverable has a real
gap**: `record_experiment.py`'s kernel-path ladder scans `kernel_log.txt` for six hardcoded text
markers but never cross-checks `kernel_run.json`'s terminal `status` (which `poll_kernel.py` sets
to `ERROR` / `CANCEL_ACKNOWLEDGED` on a confirmed kernel failure). A kernel failure whose log text
doesn't happen to match one of the six markers, combined with a stale `result.json` left on disk
from a prior push, can still be recorded as `SUCCESS`. There is also a JSON-injection bug in
`push_kernel.py`'s kernel-metadata rendering (the `exp_id` component is not charset-gated the way
`slug`/`username` are, and template substitution is raw text, not JSON-safe), which can corrupt or
override fields such as `enable_internet` in the pushed kernel metadata. Several other
robustness/quality gaps are listed below.

## Critical Issues

### CR-01: Recorder never checks kernel_run.json's terminal status — silent-success gap survives

**File:** `scripts/record_experiment.py:331-360` (classification ladder), and `:409-422` (kernel
provenance merge, where `status` is read from `kernel_run.json` for other fields but discarded)

**Issue:** The stated guarantee for this phase is: "a kernel that threw must never be recorded as
success (scan kernel log FIRST, fail closed)." The implementation only does half of that —
`scan_kernel_log()` substring-matches `kernel_log.txt` against six hardcoded markers
(`Traceback (most recent call last)`, `\nError:`, `\nException:`, an OOM string, `Killed`,
`Notebook Exceeded`). It never reads `kernel_run.json`'s `status` field, which `poll_kernel.py`
authoritatively set to `"ERROR"` or `"CANCEL_ACKNOWLEDGED"` on a *confirmed* terminal kernel
failure (see `poll_kernel.py:297-313`).

Concretely: if a kernel fails for a reason whose log text does not literally contain one of the
six markers (e.g. a Kaggle-side provisioning error, a SIGSEGV whose shell wrapper doesn't emit the
literal word "Killed", an assertion/library error not prefixed with `\n` — see WR-04 below), *and*
a `result.json` from an earlier successful push is still sitting in the experiment directory (the
kernel path re-pushes to the **same** deterministic kernel slug, so a stale `result.json` in the
exp dir is a realistic scenario), the classification ladder falls straight through to
`_validate_result(result, metric_name)`, which will happily validate the stale file and record
`status = "SUCCESS"`. `kernel_run.json`'s `status: "ERROR"` is completely ignored for
classification purposes, and — worse — is not even copied into the persisted `meta["kernel"]`
block (lines 412-421 copy `backend`/`kernel_slug`/`competition_slug`/`enable_internet`/
`accelerator`/`docker_image`/`machine_shape`/`kernel_version`, but never `status`), so there is no
audit trail of the actual poll-observed terminal state either.

This is exactly the "kernel reported COMPLETE / has a valid result.json but actually failed"
scenario the phase's docstrings claim to guard against — except here the gap is the *inverse*:
kernel reported (or was detached from) a non-success terminal state, but the recorder never looks.

**Fix:**
```python
# record_experiment.py — read kernel_run.json BEFORE the result-ladder fallthrough,
# and treat a poll-confirmed terminal failure as an unconditional kernel_error,
# exactly like a log-marker hit.
if args.kernel_log is not None:
    try:
        log_text = args.kernel_log.read_text()
    except (FileNotFoundError, OSError):
        log_text = None
    kernel_run_for_status, _ = _read_json(exp_dir / "kernel_run.json")
    kernel_status = (
        kernel_run_for_status.get("status")
        if isinstance(kernel_run_for_status, dict) else None
    )
    if kernel_status in ("ERROR", "CANCEL_ACKNOWLEDGED"):
        status, failure_reason, kernel_error_hit = "FAILED", "kernel_error", True
    elif log_text is not None and scan_kernel_log(log_text):
        status, failure_reason, kernel_error_hit = "FAILED", "kernel_error", True
```
Also add `"status": kernel_run.get("status")` to the `kernel_block` dict at line ~412 so the
poll-observed terminal state is preserved in `meta.json` for audit even on the success path.

### CR-02: JSON injection into kernel-metadata.json via unsanitized `exp_id`

**File:** `scripts/push_kernel.py:197` (`exp_id = Path(exp_rel).name`), `:227-241`
(`kernel_slug`/`title` built from `exp_id`, rendered via `_render_text` and written raw)

**Issue:** The module's own docstring/comments (lines 43-48) say the kernel id's inputs must be
charset-gated as "defense-in-depth" before entering the pushed metadata: `slug` is checked against
`_SLUG_RE` and the Kaggle-resolved `username` against `_USERNAME_RE`. `exp_id` — the third
component of both `kernel_slug` (`f"{username}/{slug}-{exp_id}"`) and `title`
(`f"{slug}-{exp_id}"`) — has **no such gate**. It is simply `Path(args.exp_dir).name`, i.e. the
raw basename of an operator/AI-supplied `--exp-dir` argument, which may legally contain quote
characters, backslashes, or other JSON-significant bytes on a POSIX filesystem.

`_render_text()` (`init_workspace.py:95-102`) is a raw `string.Template.safe_substitute` over the
hand-written `kernel-metadata.json.tmpl` — it performs **no JSON escaping**. The result is written
directly with `.write_text(metadata)` (`push_kernel.py:241`) with no `json.loads`/round-trip
validation afterward. A `--exp-dir` value such as `experiments/exp-001", "enable_internet": true, "x":"`
(or one containing a bare unescaped `"`) breaks the JSON string literal in
`"id": "${KERNEL_ID}"` and can inject or override arbitrary sibling keys in the pushed
`kernel-metadata.json` — including `enable_internet`, defeating the "internet off by default,
effective value recorded as auditable provenance" guarantee this exact file exists to uphold,
since the *rendered* metadata (what Kaggle actually receives) can diverge from the *recorded*
`kernel_run.json` (which is built with safe `json.dumps`, so the audit record itself would lie
about what was actually pushed).

**Fix:**
```python
# push_kernel.py — gate exp_id exactly like slug/username, OR (better) build the
# metadata as a dict and json.dumps it instead of raw-templating into hand-written JSON.
_EXP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")  # mirrors scaffold_experiment's exp-NNN shape

if not _EXP_ID_RE.match(exp_id):
    print(
        f"cannot push: exp_id {exp_id!r} is not a well-formed identifier — "
        "refusing to build a kernel id from it (block, don't guess).",
        file=sys.stderr,
    )
    return 1
```
Longer-term, replace the `Template.safe_substitute`-into-hand-written-JSON pattern with
`json.dumps({"id": kernel_slug, "title": title, ...}, indent=2)` so no user-influenced string can
ever break out of a JSON literal regardless of future template edits.

## Warnings

### WR-01: `--exp-dir` is never confined to the workspace (path traversal) across all 5 scripts

**File:** `scripts/convert_notebook.py:58-59`, `scripts/push_kernel.py:195-196`,
`scripts/poll_kernel.py:263-264`, `scripts/pull_kernel.py:187-188`,
`scripts/record_experiment.py:280-281`

**Issue:** Every entry point resolves `exp_dir = (ws / args.exp_dir).resolve()` and then reads
from / writes to / pushes that directory, with no check that the resolved path is actually inside
`ws`. A `--exp-dir` containing `..` segments (e.g. `../../some/other/dir`) escapes the workspace
sandbox entirely — `push_kernel.py` would then `kaggle kernels push -p <outside-dir>`, uploading
arbitrary filesystem content to a live Kaggle kernel, and `pull_kernel.py`/`record_experiment.py`
would read/write files outside the workspace. The codebase already treats this class of bug
seriously elsewhere (`download_data.py`'s documented zip-slip protection); this argument gets no
equivalent containment check.

**Fix:**
```python
exp_dir = (ws / exp_rel).resolve()
if ws not in exp_dir.parents and exp_dir != ws:
    print(f"cannot proceed: --exp-dir {exp_rel!r} escapes the workspace.", file=sys.stderr)
    return 1
```
Apply the same guard at the top of each of the five scripts.

### WR-02: Config reads assume the parsed JSON is a dict, crashing on a corrupted-but-valid config

**File:** `scripts/push_kernel.py:66-83` (`_read_control_json`) and `:210-221`
(`config.get(...)`, `kernel_cfg.get(...)`); `scripts/record_experiment.py:121-135`
(`_read_config_metric`, `config.get("metric")` at line 129)

**Issue:** `poll_kernel.py._read_kernel_run` correctly checks `isinstance(data, dict)` after
`json.loads` and fails clear with a message if not (lines 218-223). `push_kernel.py`'s
`_read_control_json` and `record_experiment.py`'s `_read_config_metric` do not: if
`control/config.json` is valid JSON but not an object (e.g. `[]`, `null`, or a bare string — an
easy state to reach via manual editing or a bug elsewhere), `config.get("competition_slug")` /
`config.get("metric")` raises an uncaught `AttributeError` instead of the "fail-clear, block don't
guess" message this codebase otherwise guarantees everywhere else.

**Fix:** Add the same `isinstance(data, dict)` guard used in `poll_kernel.py`/`pull_kernel.py`
before calling `.get()` on the parsed config.

### WR-03: Unreadable `--kernel-log` silently defers to the result ladder instead of failing closed

**File:** `scripts/record_experiment.py:333-339`

**Issue:**
```python
if args.kernel_log is not None:
    try:
        log_text = args.kernel_log.read_text()
    except (FileNotFoundError, OSError):
        log_text = None  # unreadable log = no kernel_error evidence; defer to result ladder
```
When the kernel path is explicitly invoked (`--kernel-log` was passed) but the log file is
missing/unreadable (e.g. `pull_kernel.py` never ran, or ran and failed partway, or the file was
deleted), this is treated as "no evidence of failure" and the recorder falls through to trusting
`result.json` unconditionally. Per this phase's own stated posture ("scan kernel log FIRST, fail
closed"), an *evidentiary gap* on the kernel path should block with a clear error ("cannot record:
kernel log not found — run pull_kernel.py first"), not be silently treated as equivalent to "log
scanned clean."

**Fix:**
```python
if args.kernel_log is not None:
    try:
        log_text = args.kernel_log.read_text()
    except (FileNotFoundError, OSError) as exc:
        print(
            f"cannot record: --kernel-log {args.kernel_log} is unreadable ({exc}) — "
            "run pull_kernel.py first (fail-closed: a kernel-path record needs the log).",
            file=sys.stderr,
        )
        return 1
```

### WR-04: `\nError:` / `\nException:` markers miss a failure that is the first line of the log

**File:** `scripts/record_experiment.py:70-77` (`_KERNEL_ERROR_MARKERS`), `:99-118`
(`scan_kernel_log`)

**Issue:** Two of the six markers require a literal preceding `\n`. If the kernel's very first
printed line is e.g. `Error: could not load checkpoint` (position 0, no leading newline — or the
first record's `data` field in the JSON-array log shape), neither `"\nError:"` nor
`"\nException:"` matches, and this specific failure signal is missed. (`"Traceback (most recent
call last)"` doesn't have this problem since it has no newline-prefix requirement.)

**Fix:** Also match the marker at the very start of `scan_target`, e.g.
`scan_target.startswith("Error:") or "\nError:" in scan_target` (and similarly for `Exception:`),
or simply prepend a sentinel newline before scanning: `scan_target = "\n" + scan_target`.

### WR-05: Kernel-log failure markers are unanchored substrings — false-positive risk

**File:** `scripts/record_experiment.py:70-77`, `:99-118`

**Issue:** Markers like `"Killed"` and `"\nError:"` are matched as bare substrings anywhere in the
(possibly large, arbitrary) execution log. A genuinely successful experiment that legitimately
prints something like `"Validation Error: 0.023"` or `"...outlier rows Killed during cleaning..."`
as normal stdout would trip `scan_kernel_log()` and be recorded `FAILED(kernel_error)` even though
the kernel completed successfully with a valid `result.json`. This fails in the "safe" direction
(false failure rather than false success) but still burns GPU quota and produces an incorrect
ledger row that the AI must then puzzle over.

**Fix:** Anchor markers more precisely where possible (e.g. require the marker at the start of a
line via a compiled `re.MULTILINE` pattern like `r'^Error:'` rather than a raw substring), or scope
the OOM/`Killed` markers to Kaggle's exact known wrapper-line shape rather than the bare word.

### WR-06: SKILL.md documents an `enable_internet` opt-in command that doesn't exist

**File:** `SKILL.md:296-300`; `scripts/init_workspace.py:457-472` (`build_parser`), `:538-546`
(`main`)

**Issue:** SKILL.md's kernel-loop section says: "to opt into an internet-ON run deliberately, set
it first via `python3 scripts/init_workspace.py --workspace <cwd>` config setter path
(`set_config_field(("kernel","enable_internet"), true)`) — never hand-edit." But
`init_workspace.py`'s `build_parser()` only exposes `--slug`, `--execution-target`, and
`--set-execution-target`; there is no flag that reaches `set_config_field` with
`("kernel", "enable_internet")`. Following the documented instruction literally does not work, and
the same sentence forbids the only real fallback (hand-editing `config.json`). This fails safe
(internet stays off by default), but the documented workflow for the deliberate-opt-in path is a
dead end.

**Fix:** Either add a `--set-kernel-internet {true,false}` flag to `init_workspace.py` that calls
`set_config_field(config_path, ("kernel", "enable_internet"), value)`, or correct SKILL.md to
document the actual working invocation.

### WR-07: Duplicated helper logic across the kernel-path scripts

**File:** `scripts/poll_kernel.py:197-224` (`_read_kernel_run`) vs.
`scripts/pull_kernel.py:68-95` (`_read_kernel_run`, byte-for-byte identical body);
`scripts/push_kernel.py:94-131` (inline 127/124/else rc handling in `_resolve_username`) vs.
`:250-269` (the same shape inlined again for the push call) vs.
`scripts/pull_kernel.py:98-123` (`_handle_required_rc`, which factors the identical shape out)

**Issue:** `_read_kernel_run` is copy-pasted verbatim between two files instead of living in
`kaggle_gateway.py` (the module whose stated purpose is to be "the single Kaggle CLI gateway").
Similarly, the 127/124/other rc-handling ladder is written out twice inline in `push_kernel.py`
rather than reusing a shared helper the way `pull_kernel.py` does with `_handle_required_rc`. This
is a maintainability risk — a future fix to one copy (e.g. an additional reserved exit code) can
silently miss the other copies.

**Fix:** Move `_read_kernel_run` into `kaggle_gateway.py` (or a small shared `kernel_run_io.py`)
and import it from both `poll_kernel.py` and `pull_kernel.py`; factor `push_kernel.py`'s two
inline rc ladders into a shared `_handle_required_rc`-style helper.

## Info

### IN-01: `_ACCELERATORS` allowlist is narrower than the documented accelerator set

**File:** `scripts/push_kernel.py:54-57`

**Issue:** `_ACCELERATORS = ("NvidiaTeslaT4", "NvidiaTeslaP100")`, while `CLAUDE.md`/`SKILL.md`
reference a wider verified set (`NvidiaTeslaT4Highmem`, `NvidiaTeslaA100`, `NvidiaL4`,
`NvidiaH100`, `TpuV38`). This may be intentional ("verified IDs only" per the comment), but is
worth a one-line note in the docstring so it's clear this is a deliberate subset, not an oversight.

**Fix:** Either expand `_ACCELERATORS` to the full verified set from RESEARCH, or add a comment
explaining why only two of the documented IDs are exposed.

### IN-02: Username resolution takes the first `- username:` line only

**File:** `scripts/push_kernel.py:49` (`_USERNAME_LINE_RE`), `:114-123` (`_resolve_username`)

**Issue:** `.search()` returns the first match. The stack notes mention Kaggle CLI 2.x's "OAuth
flow + multiple named tokens" support; if `kaggle config view` ever lists more than one profile,
the first line found may not be the active one used for the actual push, producing a
`kernel_slug` built from the wrong username. Low likelihood today, worth a defensive comment/test
if multi-profile support becomes relevant.

### IN-03: `poll_loop`'s `last_token` result field is computed but never consumed

**File:** `scripts/poll_kernel.py:189-191` (`"last_token": last_token` in the budget-branch return
dict), `scripts/poll_kernel.py:315-324` (`main()`'s `"budget"` branch, which never reads
`result.get("last_token")`)

**Issue:** Minor dead value — harmless, but slightly misleading for a future reader who might
assume it's used for something (e.g. surfacing the last-seen in-flight status on detach).

**Fix:** Either surface it in the detach message (`f"... last observed status: {result.get('last_token')}"`) or drop the key.

---

_Reviewed: 2026-07-11T20:41:03Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
