---
phase: 04-kaggle-kernel-execution-gpu-path
verified: 2026-07-11T20:49:05Z
status: gaps_found
score: 12/13 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Silent kernel failure is genuinely caught — no combination of a Kaggle-confirmed terminal failure + non-matching log text + a leftover result.json can be recorded SUCCESS"
    status: failed
    reason: "record_experiment.py's kernel-path classification ladder (main(), lines ~331-359) only calls scan_kernel_log() against six hardcoded substring markers in kernel_log.txt. It never reads kernel_run.json's 'status' field, which poll_kernel.py authoritatively sets to ERROR or CANCEL_ACKNOWLEDGED (poll_kernel.py:297-313) on a CONFIRMED Kaggle-side terminal failure. Because the kernel path re-pushes to the SAME deterministic slug (<username>/<slug>-exp-NNN), a stale/valid result.json from an earlier successful push realistically persists in the exp dir. If the new failing run's log text does not literally contain one of the six markers (a Kaggle-side provisioning error, a SIGSEGV without the literal word 'Killed', an assertion not prefixed with a literal '\\n' before 'Error:'/'Exception:' — see WR-04), the ladder falls through to _validate_result(stale_result, metric), which validates the STALE file and records status='SUCCESS'. kernel_run.json.status is not even copied into meta['kernel'] for audit (lines 412-421 omit 'status'), so there is no trace of the ignored Kaggle-confirmed failure either. This is the code review's CR-01, independently reproduced by reading record_experiment.py:331-359 and poll_kernel.py:297-313 directly, and it is untested — tests/test_record_kernel.py only exercises marker-hit and clean-log cases, never a kernel_run.json.status=ERROR + non-matching-log + stale-result combination."
    artifacts:
      - path: "scripts/record_experiment.py"
        issue: "Classification ladder (lines 331-359) and kernel provenance merge (lines 409-422) never read/consult kernel_run.json's 'status' field for FAILED/SUCCESS classification or for audit"
      - path: "scripts/poll_kernel.py"
        issue: "Writes an authoritative ERROR/CANCEL_ACKNOWLEDGED terminal status into kernel_run.json (lines 297-313) that no downstream consumer classification-checks"
      - path: "tests/test_record_kernel.py"
        issue: "No test covers a kernel_run.json.status=ERROR/CANCEL_ACKNOWLEDGED scenario combined with a non-matching log and a present result.json"
    missing:
      - "Read kernel_run.json's status field in record_experiment.py BEFORE the result.json fallthrough; treat status in {ERROR, CANCEL_ACKNOWLEDGED} as an unconditional kernel_error, exactly like a log-marker hit (per the review's suggested fix)"
      - "Copy kernel_run.json's status into meta['kernel']['status'] for audit even on the success path"
      - "A regression test seeding kernel_run.json with status=ERROR + a clean-looking log + a present valid result.json, asserting the run is still recorded FAILED(kernel_error)"
deferred:
  - truth: "One opt-in live push runs the full push->poll->pull->record loop against a real kernel and confirms the three/four live-only unknowns (T4x2 accelerator string, kernel-log shape, status render, push-output version string)"
    addressed_in: "Operator-owned, deliberately deferred at the 04-05 human-verify checkpoint"
    evidence: "04-05-SUMMARY.md 'Deferred Verification (operator-owned)' section: the plan itself scopes this as a non-blocking, explicit human-verify task; the operator elected to defer pending Phase 1 creds + Phase 2 data + a Phase 3 scaffolded experiment. The mocked suite (199 passed) already exercises the untrusted-text/egress/silent-failure code paths via fixtures independent of this live push."
human_verification:
  - test: "Run the one opt-in live GPU push (deferred by operator) end-to-end: convert -> push -> poll -> pull -> record against a real Kaggle kernel, including one deliberately-throwing kernel"
    expected: "A completed kernel run is recorded to the ledger with kernel provenance; a deliberately-throwing kernel is recorded FAILED(kernel_error) despite a COMPLETE status; the T4x2 accelerator string, kernel-log shape, status render, and push version-string format are captured into references/kaggle-cli-behavior.md"
    why_human: "Requires live Kaggle GPU compute and spends real 30h/week quota; cannot be exercised by static analysis or the mocked test suite. This item was already explicitly deferred by the operator per 04-05-SUMMARY.md and does not by itself change this phase's status (gaps_found is already driven by the CR-01 finding above)."
---

# Phase 4: Kaggle Kernel Execution (GPU Path) Verification Report

**Phase Goal:** The same experiment can run on Kaggle GPU compute as a pure addition to the proven loop — push, poll, pull — reusing (never re-deriving) the machine-checked result contract, with silent kernel failure caught.
**Verified:** 2026-07-11T20:49:05Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Push generates valid kernel-metadata (correct id/code_file, competition_sources, GPU on, internet off by default) via the gateway | ✓ VERIFIED | `scripts/push_kernel.py` renders `kernel-metadata.json.tmpl` (`scripts/templates/kernel-metadata.json.tmpl`) matching the golden fixture exactly (`tests/test_push_kernel.py::test_metadata_golden` passes, `uv run pytest -q` → 199 passed). Kernel id built only from `_SLUG_RE`-validated slug + `_USERNAME_RE`-validated username + exp_id (`push_kernel.py:210-227`). **Caveat: see WR/CR-02 below — `exp_id` itself is not charset-gated (WARNING, not blocking normal usage).** |
| 2 | Kernel id is deterministic `<username>/<slug>-exp-NNN`, username resolved via `kaggle config view` with no secret echoed | ✓ VERIFIED | `push_kernel.py:86-132` `_resolve_username` matches the `- username:` line only, never prints `out`; `dump_last_error` quarantines raw output on failure. |
| 3 | Push writes `kernel_run.json` handoff (slug, code_file, competition, accelerator, effective internet flag, pushed_at, status=PENDING) that poll/pull re-read without re-pushing | ✓ VERIFIED | `push_kernel.py:277-291`; `poll_kernel.py:267` and `pull_kernel.py:191` both read `kernel_run.json.kernel_slug` and never call `kernels push`. |
| 4 | Non-blocking GPU-quota heads-up surfaces before push and never blocks it (D-13) | ✓ VERIFIED | `push_kernel.py:135-167` `_quota_heads_up` swallows every exception/non-zero rc and always returns; called before the push call at line 244, return value discarded. |
| 5 | Every kaggle CLI call routes through `run_kaggle`; no raw status/quota/push buffer is printed | ✓ VERIFIED | `grep -n "print(out\|print(combined" scripts/{convert_notebook,push_kernel,poll_kernel,pull_kernel,record_experiment}.py` → no matches (independently re-checked by reading all 5 files in full). |
| 6 | Polling reaches a terminal status under bounded exponential backoff + jitter; no 429 storm | ✓ VERIFIED | `poll_kernel.py:101-114` `compute_delay` (exponential, capped at `MAX_DELAY=120s`, full jitter); `test_poll_kernel.py::test_backoff_budget` passes. |
| 7 | On our-side budget expiry with kernel in-flight, poller DETACHES (never cancels); a re-run reattaches | ✓ VERIFIED | `poll_kernel.py:182-191,315-324` writes `status="DETACHED"`, returns distinct `EXIT_DETACHED=3`; `cancel_fn` is accepted only to prove it's never called (`poll_loop` docstring + `test_detach_not_cancel`). |
| 8 | Pull lands `result.json` + artifacts + rendered `.ipynb` into the SAME contract the local runner uses | ✓ VERIFIED | `pull_kernel.py:211-216` `kernels output -p <exp_dir> --force` writes flat into `exp_dir`, matching `run_local.py:87`'s "result.json under the experiment folder" contract. |
| 9 | `kernel_log.txt` written for the recorder (never echoed); image/machine provenance merged into `kernel_run.json` (D-14) | ✓ VERIFIED | `pull_kernel.py:218-230`; log written via `.write_text(out)` (not printed), `_merge_provenance` merges `docker_image`/`machine_shape` preserving existing keys. |
| 10 | A kernel log containing a D-11 traceback/OOM marker is recorded FAILED(kernel_error) even when a valid `result.json` is present (log scanned BEFORE result.json is trusted) | ✓ VERIFIED | `record_experiment.py:99-118,324-339`; `tests/test_record_kernel.py::test_traceback_beats_valid_result`, `::test_oom_marker`, `::test_clean_log_success` all pass. |
| 11 | **Silent kernel failure is genuinely caught** — a Kaggle-confirmed terminal failure (poll-observed ERROR/CANCEL_ACKNOWLEDGED) can never be recorded SUCCESS, regardless of what the log text happens to contain | ✗ **FAILED** | **Independently reproduced (CR-01).** `record_experiment.py`'s classification ladder never reads `kernel_run.json`'s `status` field (confirmed by reading lines 331-359 and 409-422 directly — no `kernel_run.get("status")` anywhere in the classification path). `poll_kernel.py:297-313` authoritatively sets that field to `ERROR`/`CANCEL_ACKNOWLEDGED` on a confirmed terminal Kaggle failure. Because the kernel path re-pushes to the SAME deterministic slug, a stale/valid `result.json` from an earlier push realistically persists in the exp dir (the PLAN's own docs call this scenario "realistic"). If the new failing run's log text doesn't literally match one of the six hardcoded substrings, the ladder falls through and validates the stale `result.json` — recording **SUCCESS**. No test exercises this combination. This is a real hole in "silent kernel failure caught," not merely a theoretical one. |
| 12 | Local record path (no `--kernel-log`) is byte-for-byte unchanged; `FAILURE_REASONS` gains exactly ONE new reason | ✓ VERIFIED | `tests/test_record_experiment.py` (pre-existing local suite) all green alongside the new kernel tests; `FAILURE_REASONS = (..., "kernel_error")` — exactly one addition (`record_experiment.py:62-63`). |
| 13 | SKILL.md documents the kernel path as discrete resumable steps, detach/resume without re-push, D-13/D-06 notes, and scripts-table rows | ✓ VERIFIED | `SKILL.md:269-380` — "Kaggle kernel loop (EXP-05, GPU path)" section present with all five steps, "without re-pushing" language present, four new scripts-table rows + amended `record_experiment.py` row. |

**Score:** 12/13 truths verified

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | One opt-in live GPU push confirming T4x2 string / log shape / status render / push-version string | Operator-owned, deferred at the 04-05 human-verify checkpoint | 04-05-SUMMARY.md: "Task 2 live GPU push DEFERRED to the operator (deliberate, not skipped/failed)." The plan itself scopes this as non-blocking; the mocked suite (199 passed) already exercises the same code paths via fixtures. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `scripts/convert_notebook.py` | D-02 non-destructive `.py`→`.ipynb` via `uv run --no-sync jupytext` | ✓ VERIFIED | Exists, contains `--no-sync`, no `pip install`; `test_convert_notebook.py::test_reconvert_idempotent` passes. |
| `scripts/push_kernel.py` | metadata gen + quota heads-up + push + `kernel_run.json` write | ✓ VERIFIED (with WARNING) | Exists, routes through `run_kaggle`. Charset-gates `slug`/`username` but NOT `exp_id` (CR-02, see Anti-Patterns). |
| `scripts/templates/kernel-metadata.json.tmpl` | VERIFIED schema, explicit `enable_internet` | ✓ VERIFIED | Matches golden fixture byte-for-byte after substitution. |
| `scripts/templates/config.json.tmpl` | `kernel.enable_internet` leaf, default false | ✓ VERIFIED | `grep enable_internet scripts/templates/config.json.tmpl` confirms. |
| `scripts/poll_kernel.py` | status-enum classify + backoff/jitter/budget + detach-not-cancel | ✓ VERIFIED | `KernelWorkerStatus` sets present; `_STATUS_RE` anchored on `status "..."`, not case-insensitive grep. |
| `scripts/pull_kernel.py` | output + logs + image provenance via gateway | ✓ VERIFIED | No `unzip`/zip-slip logic (correctly omitted — kernel output is flat); `run_kaggle` used throughout. |
| `scripts/templates/gitignore.tmpl` | ignore kernel artifacts + `kernel_log.txt`; keep `kernel_run.json` tracked | ✓ VERIFIED | `kernel_log.txt` ignored, `!experiments/*/kernel_run.json` present. |
| `scripts/record_experiment.py` | extended recorder: `scan_kernel_log` first rung + `kernel_error` reason + `--kernel-log` flag + kernel provenance merge | ⚠️ **HOLLOW ON ONE AXIS** | Artifact exists, is substantive, and is wired (tests pass) for the log-marker case — but the classification ladder is incomplete: it never consults `kernel_run.json.status`, so the anti-silent-failure guarantee has the CR-01 gap documented above. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `push_kernel.py` | `kaggle_gateway.run_kaggle` | config view / quota / kernels push | ✓ WIRED | Confirmed by direct read; `dump_last_error` used on rc!=0. |
| `push_kernel.py` | `experiments/exp-NNN/kernel_run.json` | write handoff incl. effective `enable_internet` | ✓ WIRED | `push_kernel.py:277-291`. |
| `push_kernel.py` | `kernel-metadata.json.tmpl` | `_render_text` safe_substitute | ✓ WIRED, but **UNSAFE FOR ARBITRARY exp_id** | See CR-02 below — `exp_id` is not gated before entering the raw-JSON template substitution. |
| `poll_kernel.py` | `experiments/exp-NNN/kernel_run.json` | read slug/version; write DETACHED/terminal status | ✓ WIRED | Confirmed. |
| `pull_kernel.py` | `experiments/exp-NNN/kernel_log.txt` | write pulled log; hand path to recorder | ✓ WIRED | Confirmed; log is written not printed. |
| `record_experiment.py` | `experiments/exp-NNN/kernel_log.txt` | `--kernel-log` scanned for D-11 markers BEFORE result.json | ✓ WIRED (partial guarantee) | Log scan works exactly as tested; **but this is only half of the intended anti-silent-failure link** — see CR-01. |
| `record_experiment.py` | `experiments/exp-NNN/kernel_run.json` | merge provenance into meta.json | ⚠️ **PARTIAL** | `backend`/`kernel_slug`/`competition_slug`/`enable_internet`/`accelerator`/`docker_image`/`machine_shape`/`kernel_version` ARE merged (`record_experiment.py:412-421`); `status` is READ but never merged and never consulted for classification (CR-01). |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full mocked suite green | `uv run pytest -q` | `199 passed, 1 skipped, 9 deselected in 10.70s` | ✓ PASS |
| No debt markers in phase-modified files | `grep -n TODO\|FIXME\|XXX\|TBD\|HACK\|PLACEHOLDER` across the 9 phase-touched files | no matches | ✓ PASS |
| Recorder correctly ignores `kernel_run.json.status` for classification (independently reproduced) | Direct read of `record_experiment.py:331-359,409-422` | confirmed: no `kernel_run.get("status")` used in classification or copied to `meta["kernel"]` | ✗ FAIL (confirms CR-01) |
| `push_kernel.py` charset-gates `slug`/`username` but not `exp_id` | Direct read of `push_kernel.py:43-57,197,227-241` | confirmed: `_SLUG_RE`/`_USERNAME_RE` exist and are applied to slug/username; `exp_id = Path(exp_rel).name` has no matching gate before entering `kernel_slug`/`title`/raw-JSON template write | ✗ FAIL (confirms CR-02, WARNING severity — see below) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| EXP-05 | 04-01, 04-02, 04-03, 04-04, 04-05 | User can push a notebook to a Kaggle Kernel, run it on Kaggle compute (GPU), poll to completion, and pull results/artifacts back — with silent-failure (traceback-in-log) detection | ⚠️ **PARTIALLY SATISFIED** | Push/poll/pull mechanics fully verified (truths 1-9, 12-13). The literal "traceback-in-log detection" clause is satisfied and tested (truth 10). The broader "silent kernel failure caught" phase-goal framing has a real, reproduced gap (truth 11 / CR-01): a Kaggle-confirmed terminal failure can still be recorded SUCCESS if the log text doesn't match one of six hardcoded substrings and a stale result.json is present. |

No orphaned requirements found — REQUIREMENTS.md maps only EXP-05 to Phase 4, and it is claimed by all five plans' frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `scripts/record_experiment.py` | 331-359, 409-422 | Classification ladder never reads `kernel_run.json.status`; poll-confirmed ERROR/CANCEL_ACKNOWLEDGED is silently ignored and never even copied into `meta["kernel"]` for audit | 🛑 **BLOCKER** | Directly undermines the phase's headline "silent kernel failure caught" guarantee (CR-01, independently reproduced). |
| `scripts/push_kernel.py` | 197, 227-241 | `exp_id = Path(exp_rel).name` is not charset-gated (unlike `slug`/`username`) before entering `kernel_slug`/`title`, which are rendered via unescaped `Template.safe_substitute` into hand-written JSON and written with no `json.loads` round-trip validation | ⚠️ WARNING | JSON-injection into `kernel-metadata.json` is possible via a crafted `--exp-dir` basename, which could override `enable_internet` in the *pushed* metadata while `kernel_run.json` (built with safe `json.dumps`) records a different value — an audit-vs-reality divergence (CR-02). Does not affect the normal/documented flow, where `--exp-dir` is always `experiments/exp-NNN` from `scaffold_experiment.py`. |
| `scripts/record_experiment.py` | 333-337 | An unreadable `--kernel-log` file is silently treated as "no evidence of failure" and defers to the result ladder rather than failing closed | ⚠️ WARNING | Compounds CR-01: a partial/failed `pull_kernel.py` run (log missing) plus a stale result.json can also slip through as SUCCESS (WR-03 from the code review). |
| `scripts/record_experiment.py` | 70-77, 99-118 | `\nError:` / `\nException:` markers require a literal preceding newline; a failure that is the very first line of the log is missed | ⚠️ WARNING | Narrows the effective marker coverage below what the docstring implies (WR-04 from the code review). |
| All 5 kernel-path scripts | various | `--exp-dir` is never confined to the workspace (no `..`-escape check), unlike `download_data.py`'s documented containment posture elsewhere in the codebase | ⚠️ WARNING | Path-traversal risk if `--exp-dir` is ever attacker/AI-malformed (WR-01 from the code review); out of scope for this verification's BLOCKER determination since normal usage always passes a scaffold-generated `experiments/exp-NNN` path. |

### Human Verification Required

### 1. Live Kaggle GPU push (already deferred by operator — informational only)

**Test:** Run `convert_notebook.py -> push_kernel.py -> poll_kernel.py -> pull_kernel.py -> record_experiment.py --kernel-log ...` against a real Kaggle kernel, including one deliberately-throwing kernel, per the sequence documented in 04-05-SUMMARY.md.
**Expected:** A completed kernel run recorded to the ledger with kernel provenance; a deliberately-throwing kernel recorded FAILED(kernel_error) despite a COMPLETE status. The T4x2 accelerator string, real kernel-log shape, exact status render, and push-output version-string format are captured into `references/kaggle-cli-behavior.md`.
**Why human:** Requires live Kaggle GPU compute and spends real 30h/week quota — cannot be exercised by static analysis or the mocked suite. This item was already explicitly and deliberately deferred by the operator at the 04-05 checkpoint per the plan's own sanctioned "not a phase-wide blocker" framing, and does not drive this report's `gaps_found` status (that is driven by the CR-01 finding, which is independent of the live push).

## Gaps Summary

The phase's push/poll/pull mechanics (SC-1, SC-2, and the narrow "log-marker beats a valid result.json" contract from SC-3) are fully built, tested, and independently verified against the actual code — SUMMARY.md's claims of a green 199-test mocked suite are accurate, and the never-echo / detach-not-cancel / non-blocking-quota guarantees hold exactly as documented.

However, the phase's own stated goal — **"silent kernel failure caught"** — is not fully delivered. Independently re-reading `record_experiment.py` and `poll_kernel.py` confirms the code review's CR-01 finding: the recorder's classification ladder scans the kernel log for six hardcoded substrings but never consults `kernel_run.json`'s `status` field, which `poll_kernel.py` itself authoritatively sets to `ERROR`/`CANCEL_ACKNOWLEDGED` on a confirmed Kaggle-side terminal failure. Combined with the deterministic re-push slug (a stale `result.json` realistically persists across pushes to the same kernel) and a log whose failure text doesn't happen to hit one of the six markers, this produces a genuine SUCCESS mis-record of a Kaggle-confirmed failed run — the exact class of bug ("silent kernel failure") this phase exists to prevent. No test in `tests/test_record_kernel.py` exercises this combination, so nothing in the current green suite would catch a regression here either.

CR-02 (JSON injection via an unsanitized `exp_id` into hand-written `kernel-metadata.json`) is a real, independently-confirmed gap in the codebase's own stated defense-in-depth posture (slug and username ARE gated; `exp_id` is not), but it does not manifest under the documented/normal usage pattern (`--exp-dir` is always a scaffold-generated `experiments/exp-NNN` path) — it is reported as a WARNING, not a status-driving BLOCKER, though it should be fixed before this surface is exposed to less-trusted input.

The one opt-in live GPU push (Task 2 of plan 04-05) was deliberately deferred by the operator, exactly as the plan sanctions — this is correctly treated as a deferred/informational item, not a gap, and does not by itself change the phase's status.

**Recommended fix for the BLOCKER (CR-01):** In `record_experiment.py`, read `kernel_run.json`'s `status` field before the result.json fallthrough and treat `status in {"ERROR", "CANCEL_ACKNOWLEDGED"}` as an unconditional `kernel_error`, exactly like a log-marker hit; also copy `status` into `meta["kernel"]` for audit. Add a regression test seeding `kernel_run.json.status="ERROR"` + a clean-looking log + a present valid `result.json`, asserting the run is still recorded `FAILED(kernel_error)`.

---

*Verified: 2026-07-11T20:49:05Z*
*Verifier: Claude (gsd-verifier)*
