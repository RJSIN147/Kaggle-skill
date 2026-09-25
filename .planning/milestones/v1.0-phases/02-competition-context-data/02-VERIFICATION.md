---
phase: 02-competition-context-data
verified: 2026-07-11T00:30:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/4
  gaps_closed:
    - "capture_competition/analyze_data derive a correct CV scheme from the data structure (grouped/temporal/stratified) — success criterion 1 (closed by 02-06, reframed per operator-approved D-05 clarification: framework surfaces evidence + a non-authoritative advisory hint, the AI decides, tooling persists the AI's chosen value enum-validated — never auto-commits)"
    - "On a 403, the framework detects the UI-only gate and surfaces one clear browser instruction, never busy-loops the download — success criterion 3 (closed by 02-07: rc==127/124 now routed to tailored remediation before the UI-gate fallthrough, mirroring capture_competition._gateway_failure)"
  gaps_remaining: []
  regressions: []
---

# Phase 2: Competition Context & Data Verification Report

**Phase Goal:** Before any experiment is authored, the workspace holds a correct, machine-derived competition "constitution" and the data needed to run locally — with the UI-only Kaggle gates cleared and all ingested Kaggle text treated as untrusted.
**Verified:** 2026-07-11T00:30:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (plans 02-06 and 02-07)

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | `capture_competition`/`analyze_data` populate `competition.md` with metric, schema, rules, daily limit, and a **correct** CV scheme + AV finding | ✓ VERIFIED | Root-caused and closed by 02-06: `analyze_data.py` no longer auto-commits `evidence["recommend"]` (the `scheme = committed or evidence["recommend"]` fallback is deleted — confirmed by direct code read, `scripts/analyze_data.py:456-465`). `cv.scheme` is written ONLY via `set_config_field(config_path, ("cv","scheme"), args.cv_scheme)` when `args.cv_scheme is not None`; with no flag it stays reserved-null and `competition.md` gets a `_cv_section_pending` DECISION-PENDING body. `detect_group_candidates` (`scripts/cv_evidence.py:200-242`) now excludes mostly-empty columns and continuous-numeric columns (`_looks_continuous_numeric`, fractional-value guard) before the many-entities check. Independently reproduced (NOT the checked-in fixture — a freshly-generated titanic-shaped dataset built in this verification pass): `detect_group_candidates` on Age/Fare/Cabin-shaped columns returns `[]`, and `recommend_cv` resolves to `StratifiedKFold`. Regression-pinned by `tests/test_cv_evidence.py::test_titanic_shape_recommends_stratified_no_group_falsepos` and `test_grouped_still_flags_group_after_tightening` (no regression on the genuine-group case). `recommend_is_hint`/`recommend_note` label the mechanical value advisory (`test_recommendation_labeled_advisory_hint`). Non-tabular pairs degrade to `recommend=None` (`test_non_tabular_pair_degrades_to_no_scheme`). This reframes success criterion 1 per the operator-approved D-05 clarification recorded in `02-CONTEXT.md` (2026-07-10): the framework surfaces evidence, the AI decides, tooling persists enum-validated — the scheme is still machine-derived-and-verified evidence-backed, just AI-committed rather than framework-auto-committed. |
| 2 | All Kaggle-sourced text is wrapped in untrusted-content markers with source attribution; no directive can drive a path/command/fetch | ✓ VERIFIED (regression-checked) | `scripts/untrusted.py` unchanged by this gap-closure round; `tests/test_untrusted.py` (`test_fence_cannot_be_broken`, `test_no_competition_text_reaches_subprocess`) still pass in the full suite run. |
| 3 | On a 403, the framework detects the UI-only gate, surfaces one clear browser instruction with the exact URL, verifies via a probe, never busy-loops | ✓ VERIFIED | Closed by 02-07: `scripts/download_data.py:178-191` now branches `rc == 127` (install-CLI remediation, `return rc`) and `rc == 124` (timeout/egress remediation, `return rc`) BEFORE the `if rc != 0:` UI-gate fallthrough — confirmed by direct code read, mirroring `capture_competition._gateway_failure` exactly (same branch pattern verified at `scripts/capture_competition.py:215-228`). Neither new branch calls `gw.dump_last_error`/`gw.classify_gate` (no raw-buffer echo for these fixed, secret-free markers). `grep -c 'sleep(' scripts/download_data.py` → 0 (no busy-loop introduced). Regression-pinned by `tests/test_gate.py::test_missing_cli_rc127_reports_install_not_ui_gate` and `test_timeout_rc124_reports_egress_not_ui_gate` (both assert `slept["n"] == 0` and the correct return code/message). Pre-existing exit-77 paths (`test_gate_false_exits_ui_gate_without_busy_loop`, `test_unclassified_403_fails_closed_naming_both_urls`) still pass — no regression. Independently confirmed by `02-REVIEW.md` (2026-07-11 re-review): "A prior REVIEW.md flagged `download_data.py` collapsing every non-zero download rc into a UI-gate misreport; that is now FIXED... That stale finding is dropped." |
| 4 | Competition data downloads locally and extracts with zip-slip-protected extraction; no file can escape the data directory | ✓ VERIFIED (regression-checked) | `scripts/safe_extract.py` unchanged by this gap-closure round; `tests/test_extract.py` still passes in the full suite run; `02-REVIEW.md` independently re-confirms zip-slip rejection (absolute/drive paths, `..` traversal, symlink members, realpath-escaping members) before any write. |

**Score:** 4/4 truths VERIFIED (both prior gaps closed; truths 2 and 4 regression-clean).

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `scripts/cv_evidence.py` | advisory-hint labeling + tightened `detect_group_candidates` + non-tabular degradation | ✓ VERIFIED | `_looks_continuous_numeric`, mostly-empty guard, `recommend_is_hint`/`recommend_note`, `NON_TABULAR_NOTE` sentinel branch all present and wired into `build_evidence`. Stdlib-only (no pandas/sklearn import) — confirmed by reading the full file. |
| `scripts/analyze_data.py` | `cv.scheme` written ONLY from an explicit enum-validated `--cv-scheme`; no-choice pending path | ✓ VERIFIED | `committed = args.cv_scheme; if committed is not None: set_config_field(...)` — no `or evidence["recommend"]` fallback anywhere in the file (grep-confirmed absent). `_cv_section_pending` present and wired on the no-flag path. |
| `tests/cv_fixtures.py` | titanic-shaped fixture builder | ✓ VERIFIED | `SHAPES = ("grouped", "temporal", "imbalanced", "titanic", "degenerate")`; `_build_titanic` present with continuous fractional-repeating Age/Fare + sparse Cabin + binary Survived, no true group. |
| `tests/test_cv_evidence.py` | regression tests pinning StratifiedKFold on titanic + AI-decides commit contract | ✓ VERIFIED | `test_titanic_shape_recommends_stratified_no_group_falsepos`, `test_grouped_still_flags_group_after_tightening`, `test_recommendation_labeled_advisory_hint`, `test_non_tabular_pair_degrades_to_no_scheme`, `test_analyze_no_cv_scheme_leaves_null_pending` all present and passing. |
| `SKILL.md` | documented D-05 two-step Analyze flow | ✓ VERIFIED | Lines 136-165: two-step flow (surface evidence → AI reasons over `cv-evidence.json` → re-invoke with `--cv-scheme <enum>`); explicit "framework NEVER auto-picks it (D-05)" statement; Scripts-table row updated (line 220). |
| `scripts/download_data.py` | `rc==127`/`rc==124` branching mirrored from `capture_competition._gateway_failure`, BEFORE the UI-gate fallthrough | ✓ VERIFIED | Lines 178-191, placed immediately after `run_kaggle` and before `if rc != 0:`. No `sleep(` call anywhere in the file (grep-confirmed, count 0). |
| `tests/test_gate.py` | regression tests for the 127/124 tailored remediation + no-sleep assertion | ✓ VERIFIED | `test_missing_cli_rc127_reports_install_not_ui_gate`, `test_timeout_rc124_reports_egress_not_ui_gate` present, both asserting `slept["n"] == 0` and correct return codes/messages, distinct from the UI-gate text. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `scripts/analyze_data.py` | `config.json cv.scheme` | `set_config_field` only when `args.cv_scheme is not None` | ✓ WIRED | Confirmed by code read; `tests/test_cv_evidence.py::test_analyze_no_cv_scheme_leaves_null_pending` proves the no-write path; `test_analyze_lands_nonnull_cv_scheme_and_rationale` proves the write path. |
| `scripts/cv_evidence.py` | `control/raw/cv-evidence.json` | recommendation labeled advisory hint (not committed) | ✓ WIRED | `recommend_is_hint`/`recommend_note` present in the written JSON; `test_recommendation_labeled_advisory_hint` passes. |
| `scripts/download_data.py` | `capture_competition._gateway_failure` branch pattern | `rc in (127, 124)` handled before `classify_gate`/`UI_GATE` | ✓ WIRED | Identical branch structure confirmed side-by-side in both files; `02-REVIEW.md` independently confirms the mirror is correct and the stale finding is dropped. |

### Data-Flow Trace (Level 4) — independent reproduction

Reproduced the original Gap-1 failure mode directly in this verification pass, using a **freshly-generated** titanic-shaped dataset (not the repo's checked-in fixture, to rule out a fixture-only fix):

```python
header = ["PassengerId","Survived","Pclass","Age","Fare","Cabin"]
# 891 rows, fractional-repeating Age/Fare, sparse Cabin, binary Survived (~38% minority)
detect_group_candidates(header, rows, "PassengerId", "Survived", []) → []
recommend_cv({...}) → "StratifiedKFold"
```

Age/Fare/Cabin are no longer flagged as group candidates and the mechanical hint resolves to `StratifiedKFold` — the textbook-correct answer for Titanic. This confirms the fix operates on the underlying heuristic, not merely on the specific fixture values checked into the test file.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full non-live suite green | `uv run python -m pytest -q` | 90 passed, 8 deselected | ✓ PASS |
| Gap-closure test files isolated | `uv run pytest tests/test_cv_evidence.py tests/test_gate.py -q` | 26 passed | ✓ PASS |
| `time.sleep` absent from download path | `grep -vE '^\s*#' scripts/download_data.py \| grep -c 'sleep('` | `0` | ✓ PASS |
| No debt markers in touched files | `grep -nE "TBD\|FIXME\|XXX"` across `cv_evidence.py`, `analyze_data.py`, `download_data.py`, `SKILL.md`, `tests/cv_fixtures.py`, `tests/test_cv_evidence.py`, `tests/test_gate.py` | no matches | ✓ PASS |
| Independent titanic false-positive reproduction (fresh data, not repo fixture) | inline Python (see Data-Flow Trace) | `group_candidates=[]`, `recommend="StratifiedKFold"` | ✓ PASS |
| Commit provenance | `git show --stat` on all 7 claimed commit hashes (52ded6f, 8fdd6e3, 45900ab, 04815d7, bc97062, fabf24f, cf7b100) | all found in `git log` | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this repo. Step 7c: SKIPPED (no probe scripts declared or discoverable) — the pytest suite is this project's probe-equivalent and was executed directly above.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| COMP-01 | 02-01, 02-02, 02-04, 02-05, 02-06 | Capture static competition context (metric, schema, rules, limit, **correct** CV scheme) into `competition.md` | ✓ SATISFIED | CV-scheme sub-clause now closed by 02-06 (see truth 1). Metric/schema/rules/limit previously verified and unchanged. |
| COMP-02 | 02-01, 02-02, 02-03, 02-05, 02-07 | Preflight UI-only gates; clear one-time browser instructions on a 403 | ✓ SATISFIED | 127/124 misclassification closed by 02-07 (see truth 3). Rules-gate + unclassified-403 handling previously verified and unchanged. |
| COMP-03 | 02-03, 02-05 | Download competition data locally with safe zip-slip-protected extraction | ✓ SATISFIED | Unchanged, previously fully verified; regression-checked in this pass. |

No orphaned requirements: `.planning/REQUIREMENTS.md`'s Phase 2 row maps exactly COMP-01/02/03, and every plan's frontmatter `requirements:` field (including the two gap-closure plans: 02-06 → `[COMP-01]`, 02-07 → `[COMP-02]`) draws only from that set.

### Anti-Patterns Found

None blocking. `02-REVIEW.md` (re-review dated 2026-07-11, post-gap-closure) reports 0 critical findings, 7 warnings, 5 info — all narrower correctness/robustness gaps in edge-case territory (e.g. a valid-JSON-but-wrong-type `config.json` crashing instead of failing clear; AV runtime-error misreported as "ML env absent"; an untested fence-regex whitespace variant; a submission-limit multi-figure ambiguity; a marginal-shift report dropping columns with any missing cell). None of these touch the two gaps this round closed, none are debt markers (no unreferenced TBD/FIXME/XXX in any file touched this phase), and the review explicitly confirms the prior download-classification finding is now FIXED. These are pre-existing/narrower findings appropriate for a future hardening pass, not phase-blocking for COMP-01/02/03.

### Human Verification Required

None. Both gap closures are pure code/logic changes verifiable by direct inspection, an independently-reproduced (non-fixture) data test, and the automated suite (executed, not narrated). No UI, real-time, or external-service behavior was altered by 02-06/02-07.

### Gaps Summary

Both gaps from the prior `gaps_found` verification are closed:

1. **CV-scheme correctness (truth 1):** Root-caused past the detector alone — the framework was auto-committing a mechanical default, violating D-05's intent. 02-06 removed the auto-commit entirely; `cv.scheme` is now persisted only from an explicit, enum-validated AI decision, with the mechanical recommendation demoted to a labeled advisory hint and the detector tightened so the hint itself is no longer egregiously wrong on continuous features (Titanic Age/Fare/Cabin no longer false-flagged). This is a deliberate, operator-approved reframing of the success criterion's mechanism (recorded in `02-CONTEXT.md`'s D-05 clarification), not a scope reduction — the Phase 2→3 contract is unchanged, and the value Phase 3 reads is now guaranteed correct-or-absent rather than mechanically-wrong-and-committed.
2. **Download exit-code misclassification (truth 3, WR-01):** 02-07 mirrored `capture_competition._gateway_failure`'s rc==127/124 branches into `download_data.py` before the UI-gate fallthrough. A missing CLI or stalled egress now gets its own correct, distinct remediation and exit code instead of a misleading "accept the rules" instruction; no busy-loop was introduced.

No regressions were found in the previously-clean truths (untrusted-content wrapping, zip-slip-protected extraction). The full non-live test suite is green (90 passed, 8 deselected), and a post-gap-closure code review (`02-REVIEW.md`) independently confirms both fixes and finds no blocker-level defects remaining.

---

_Verified: 2026-07-11T00:30:00Z_
_Verifier: Claude (gsd-verifier)_
