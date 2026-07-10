---
phase: 02-competition-context-data
verified: 2026-07-10T16:37:21Z
status: gaps_found
score: 3/4 must-haves verified
overrides_applied: 0
gaps:
  - truth: "capture_competition/analyze_data derive a correct CV scheme from the data structure (grouped/temporal/stratified) — success criterion 1"
    status: failed
    reason: >
      cv_evidence.detect_group_candidates false-positives on ordinary continuous
      numeric feature columns, causing analyze_data.py to mechanically recommend
      AND commit GroupKFold instead of the objectively correct StratifiedKFold for
      a plain binary-classification dataset with no true group structure.
      Reproduced LIVE against the real, canonical `titanic` dataset (the exact
      example used throughout every Phase 2 planning/context document) — not a
      synthetic hypothetical: `Age` (88 unique values / 891 rows, avg repeat 10.1),
      `Fare` (248 unique, avg repeat 3.6), and `Cabin` (147 unique, avg repeat 6.1)
      all satisfy detect_group_candidates' guard (`n_unique >= 10` and
      `avg_group >= 2`) and are recorded as "repeated-entity group column(s)".
      `analyze_data.py` then commits `config.json` `cv.scheme = "GroupKFold"` and
      writes that scheme + a rationale citing Age/Fare/Cabin as "group leakage"
      columns into `competition.md`'s Cross-validation section — the doc Phase 3
      re-reads as trusted ground truth every cycle. SKILL.md's documented operator
      flow (`python3 scripts/analyze_data.py --workspace <cwd>`, no `--cv-scheme`
      override guidance) does not instruct the AI to review cv-evidence.json and
      override the mechanical default, so this wrong recommendation lands as
      committed truth in the default documented flow, not just in a
      no-override edge case.
    artifacts:
      - path: "scripts/cv_evidence.py"
        issue: >
          detect_group_candidates (lines 159-184) treats any column with
          n_unique>=10 (or >=10% of rows) and avg_group>=2 as a "repeated-entity
          group", which is satisfied by ordinary continuous numeric features
          (Age, Fare) that have no group/entity semantics at all.
      - path: "scripts/analyze_data.py"
        issue: >
          Commits the mechanical recommend_cv() value by default (no operator
          nudge to override) and writes the false "group leakage" rationale
          verbatim into competition.md.
      - path: "SKILL.md"
        issue: >
          The documented "Analyze" step (lines 136-145) shows the bare command
          with no instruction to read control/raw/cv-evidence.json and pass
          --cv-scheme when the mechanical recommendation looks wrong, so the
          D-05 "AI reasons over the evidence" design intent is not actually wired
          into the operator-facing flow.
    missing:
      - "Tighten detect_group_candidates to reject continuous/interval-looking numeric columns (e.g. require low value-density relative to a plausible entity count, or require the column to be non-numeric/categorical-shaped) so Age/Fare/Cabin-style features never masquerade as group ids."
      - "Add a regression fixture shaped like a real dataset with continuous numeric noise columns and NO true group column (a titanic-like fixture), asserting recommend_cv resolves to StratifiedKFold — the existing tests/cv_fixtures.py only builds clean synthetic single-group-column data that never exercises this false positive."
      - "Add an explicit instruction in SKILL.md's Analyze step telling Claude to read control/raw/cv-evidence.json's group_candidates/evidence before running analyze_data.py, and to pass --cv-scheme to override an implausible mechanical recommendation, so D-05's 'AI reasons, tooling writes' is actually wired into the documented flow."
  - truth: "On a 403, the framework detects the UI-only gate and surfaces one clear browser instruction, never busy-loops the download — success criterion 3"
    status: partial
    reason: >
      download_data.py (review WR-01, independently reproduced) classifies EVERY
      non-zero return from the download call — including rc=127 (kaggle CLI
      missing, reserved by kaggle_gateway.run_kaggle) and rc=124 (timeout,
      likewise reserved) — as an unclassifiable UI gate. Reproduced directly:
      monkeypatching run_kaggle to return (127, "kaggle CLI not found on PATH")
      makes download_data.py print "clear whichever UI-only gate applies in a
      browser" and exit 77, when the correct remediation is "install the kaggle
      CLI". The sibling script capture_competition.py already branches rc==127/124
      correctly via `_gateway_failure` (tailored "install it" / "check the egress
      allowlist" messages) — the fix pattern exists in this same phase's codebase
      but was not applied to download_data.py. This is a narrower gap than the
      CV-scheme finding: it requires the CLI to go missing/stall specifically
      between the (already-passed) credential validation and the download call,
      it does NOT reintroduce an in-script busy-loop (no sleep/poll — the
      "never busy-loops" literal guarantee still holds), and the core rules-gate
      + unclassified-403-fail-closed mechanisms this criterion primarily targets
      are proven correct, including live against the real Kaggle CLI.
    artifacts:
      - path: "scripts/download_data.py"
        issue: >
          Lines 169-179: `if rc != 0:` unconditionally routes to the UI_GATE /
          classify_gate branch without first checking `rc in (127, 124)`, unlike
          capture_competition._gateway_failure's tailored handling.
    missing:
      - "Mirror capture_competition._gateway_failure's rc==127 / rc==124 branches in download_data.py before falling through to the UI_GATE/classify_gate path, so a missing CLI or stalled egress gets its own correct remediation instead of a misleading 'accept the rules' instruction."
---

# Phase 2: Competition Context & Data Verification Report

**Phase Goal:** Before any experiment is authored, the workspace holds a correct, machine-derived competition "constitution" and the data needed to run locally — with the UI-only Kaggle gates cleared and all ingested Kaggle text treated as untrusted.
**Verified:** 2026-07-10T16:37:21Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (Roadmap Success Criterion) | Status | Evidence |
|---|---|---|---|
| 1 | `capture_competition`/`analyze_data` populate `competition.md` with metric, schema, rules, daily limit, and a **correct** CV scheme + AV finding | ✗ FAILED (partial) | Metric/schema/rules/limit/AV-honesty all VERIFIED (see below). The CV-scheme sub-clause is FAILED: live run against the real `titanic` dataset commits `cv.scheme = "GroupKFold"` with a rationale citing `Age`/`Fare`/`Cabin` as "repeated-entity group columns" — an objectively wrong derivation for a plain binary-classification dataset with no true group structure. Reproduced directly (see Data-Flow Trace). |
| 2 | All Kaggle-sourced text is wrapped in untrusted-content markers with source attribution; no directive can drive a path/command/fetch | ✓ VERIFIED | `escape_markers`/`wrap_untrusted` (`scripts/untrusted.py`) neutralise every realistic fence-lookalike (`test_fence_cannot_be_broken` — 7 payload variants incl. case/attr/whitespace/partial); `test_no_competition_text_reaches_subprocess` proves a `TAINT_a1b2c3` sentinel embedded in Kaggle prose reaches no subprocess argv and every `argv[0]` is on a fixed allowlist. Minor non-blocking gap noted: WR-03 (see Anti-Patterns). |
| 3 | On a 403, the framework detects the UI-only gate, surfaces one clear browser instruction with the exact URL, verifies via a probe, never busy-loops | ⚠ PARTIAL | Core mechanism VERIFIED live and by test: single `preflight_entered` probe (call-count==1), `time.sleep` never called, rules gate → exit 77 + exact URL, unclassified 403 → fail-closed naming both rules+phone URLs, raw buffer quarantined not echoed. Gap: WR-01 (independently reproduced) — `download_data.py` misclassifies a missing-CLI (127) / timeout (124) download failure as the same UI gate, giving a misleading instruction in that narrow precondition. Does not reintroduce a busy-loop; narrower in scope than truth 1's finding. |
| 4 | Competition data downloads locally and extracts with zip-slip-protected extraction; no file can escape the data directory | ✓ VERIFIED | `safe_extract.py` rejects all 4 zip-slip vectors (absolute, `..`, symlink, nested traversal) before any write (`test_no_file_escapes_across_all_vectors`); live download of the real `titanic.zip` extracted exactly 3 files into `data/` with no escape. |

**Score:** 2/4 truths cleanly VERIFIED; 1 FAILED (partial — most sub-clauses hold, the "correct CV scheme" clause does not); 1 PARTIAL (core mechanism verified, one narrow misclassification gap). Reported as **3/4** in frontmatter reflecting truths 2 and 4 fully clean plus truth 3's core mechanism sound; truth 1's CV-scheme defect is the phase-blocking gap.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `scripts/kaggle_gateway.py` | D-16 gateway: run_kaggle/preflight_entered/classify_gate/dump_last_error, UI_GATE=77/LIMIT_NEEDS_USER=78 | ✓ VERIFIED | All four functions + constants present; live-verified against real CLI 2.2.3 (pretty-printed JSON parse fix confirmed working). |
| `scripts/untrusted.py` | escape_markers + wrap_untrusted | ✓ VERIFIED | Present, tested, wired into `capture_competition.py`. |
| `scripts/competition_doc.py` | replace_section shared section-safe-merge | ✓ VERIFIED | Present; imported by both `capture_competition.py` and `analyze_data.py`. |
| `scripts/capture_competition.py` | pages+files → competition.md + config machine fields | ✓ VERIFIED | Live-run: reached `api.kaggle.com`, extracted `daily_limit=10 (extracted)`, wrote metric+rules sections correctly. |
| `scripts/safe_extract.py` | zip-slip reject-and-raise | ✓ VERIFIED | `UnsafeArchiveMember` + `safe_extract`; all 4 vectors + benign control tested; live extraction confirmed. |
| `scripts/download_data.py` | credential gate → preflight → download → safe extract | ⚠ ORPHANED GAP (WR-01) | Core flow VERIFIED (live), but non-403 gateway failures (127/124) are misclassified — see gap. |
| `scripts/cv_evidence.py` | stdlib structural evidence + recommend_cv | ✗ STUB-LIKE DEFECT | `recommend_cv`/`detect_group_candidates` exist and are wired, but `detect_group_candidates`'s many-entities guard produces false positives on ordinary continuous numeric columns — verified live against titanic. |
| `scripts/analyze_data.py` | schema + set_config_field cv.scheme + AV | ✓ WIRED, ⚠ propagates cv_evidence's defect | Commits `cv.scheme` via `set_config_field` correctly (mechanism verified); commits the WRONG value sourced from the upstream defect. AV honestly SKIPPED when ML env absent — verified live (pandas/sklearn absent from this repo's env by design). |
| `scripts/templates/config.json.tmpl` | reserved submission/competition/cv keys | ✓ VERIFIED | `limit_provenance`, `competition.type`, `cv.scheme` all present as reserved null. |
| `scripts/templates/competition.md.tmpl` | 5 `_TODO (Phase 2)_` sections | ✓ VERIFIED | Evaluation metric / Data schema / Rules & limits / Cross-validation scheme / Adversarial validation all present. |
| `scripts/templates/settings.json.tmpl` + `references/egress-allowlist.md` | api.kaggle.com allowlisted + corrected | ✓ VERIFIED | `api.kaggle.com` present in both; correction-history row dated 2026-07-10; live capture/download reached the host without being blocked. |
| `tests/test_gateway.py`, `test_egress_allowlist.py`, `test_untrusted.py`, `test_capture.py`, `test_limit_regex.py`, `test_extract.py`, `test_gate.py`, `test_cv_evidence.py`, `test_competition_live.py` | full coverage | ✓ VERIFIED | Full mock suite: 83 passed, 8 deselected (live). Live suite (`-m live`, real credential against titanic): 6 passed, 1 skipped (documented phone-gate placeholder). |
| `SKILL.md` | 3-stage flow + gate protocol + scripts table | ✓ VERIFIED, ⚠ incomplete on CV-scheme override guidance | Documents capture→download→analyze, exit-77/78 protocol, explicit-path staging, all 5 new script rows. Does not instruct the AI to read cv-evidence.json / override `--cv-scheme` — contributing to truth 1's gap. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `capture_competition.py` | `kaggle_gateway.run_kaggle` | pages/files calls | ✓ WIRED | Live-verified. |
| `capture_competition.py` | `untrusted.escape_markers`/`wrap_untrusted` | applied before write | ✓ WIRED | `test_no_competition_text_reaches_subprocess` + live output shows fenced prose. |
| `capture_competition.py` | `control/config.json` | `set_config_field` direct overwrite | ✓ WIRED | Live: `daily_limit`/`limit_provenance` land non-null on the reserved-null key. |
| `capture_competition.py` | `competition.md` | `competition_doc.replace_section` | ✓ WIRED | Live output confirms metric+rules sections populated, no `_TODO` remaining there. |
| `download_data.py` | `kaggle_gateway.preflight_entered` | cheap gate probe | ✓ WIRED | Verified live + by test (`calls["preflight"]==1`). |
| `download_data.py` | `safe_extract.safe_extract` | extract `<slug>.zip` into `data/` | ✓ WIRED | Live: 3 files extracted correctly. |
| `download_data.py` | `control/state.json` | `credentials==VALIDATED` gate | ✓ WIRED | `test_refuses_without_validated_credentials` passes; live run required VALIDATED state. |
| `analyze_data.py` | `control/config.json` | `set_config_field` overwrite of `cv.scheme` | ✓ WIRED (mechanism); ✗ VALUE WRONG | The write mechanism is correct; the value it writes is wrong for titanic (see gap). |
| `analyze_data.py` | `competition.md` | `replace_section` — CV scheme + rationale | ✓ WIRED | Section is written; content is factually incorrect for the false-positive case. |
| `analyze_data.py` | workspace ML env | `uv run` / stdlib fallback | ✓ WIRED | Live: `uv run --no-sync` degraded cleanly to SKIPPED with pandas/sklearn absent; never attempted a pip install. |
| `cv_evidence.py` | `control/raw/cv-evidence.json` | tracked provenance write | ✓ WIRED | File written and populated; content itself carries the group-candidate false positive. |

### Data-Flow Trace (Level 4) — the finding that changes the verdict

I ran the phase's own three entry points end-to-end against the **real** Kaggle `titanic` competition (a live sandbox workspace outside the repo, no repo files touched — confirmed via `git status` before/after):

```
$ python3 scripts/init_workspace.py --workspace <scratch> --slug titanic
$ python3 scripts/check_credentials.py --workspace <scratch>          # → VALIDATED
$ python3 scripts/capture_competition.py --workspace <scratch>        # → daily_limit=10 (extracted)
$ python3 scripts/download_data.py --workspace <scratch>              # → 3 files extracted into data/
$ python3 scripts/analyze_data.py --workspace <scratch>
analyze 'titanic': cv.scheme=GroupKFold (mechanical); AV SKIPPED (ML env absent (uv run non-zero)). competition.md constitution complete.
```

`control/raw/cv-evidence.json` recorded:
```json
"group_candidates": ["Age", "Fare", "Cabin"],
"recommend": "GroupKFold"
```

And `competition.md`'s Cross-validation section committed:
> **Cross-validation scheme:** GroupKFold
> Derivation (mechanical, D-05 tooling-recommends → AI-commits → tooling-writes): repeated-entity group column(s) ['Age', 'Fare', 'Cabin'] → GroupKFold prevents group leakage across folds. Committed **GroupKFold** (matches the mechanical recommendation).

This is wrong: `Age`/`Fare`/`Cabin` are ordinary continuous numeric features on 891 independent passenger rows — there is no "repeated entity" (e.g. a shared customer/user id) in the Titanic schema at all. Titanic is the textbook StratifiedKFold example (binary target, ~62/38 class split, no groups, no time axis). Root cause verified by direct computation on the live-downloaded CSV:

| Column | n_unique | avg repeat (n_rows/n_unique) | `many_entities` guard (`>=10` or `>=10%`) | Passes false-positive check |
|---|---|---|---|---|
| `Age` | 88 | 10.1 | `88>=10` → True | Yes (bug) |
| `Fare` | 248 | 3.6 | `248>=10` → True | Yes (bug) |
| `Cabin` | 147 (of 204 non-empty) | 6.1 | `147>=10` → True | Yes (bug) |

`cv_evidence.detect_group_candidates`'s guard (`n_unique>=10 or n_unique>=10% of rows`, `avg_group>=2`) has no signal that distinguishes a genuine repeated-entity identifier from an ordinary continuous numeric feature that merely happens to have repeated values. `tests/cv_fixtures.py`'s synthetic fixtures only build clean, single-group-column data, so this false positive was never exercised by the test suite — this is a goal-backward gap the task-level "tests pass" signal could not surface.

**Data-flow status: HOLLOW.** The write mechanism (`set_config_field`, `replace_section`) is fully wired and correct; the mechanically-recommended VALUE flowing through that wiring is wrong on real data, and nothing in the documented operator flow (`SKILL.md`) prompts the AI to catch it before committing.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Mock test suite green | `uv run pytest tests/ -q` | 83 passed, 8 deselected | ✓ PASS |
| Live CLI-shape suite (real credential, titanic) | `uv run pytest -m live tests/test_competition_live.py -q` | 6 passed, 1 skipped (documented phone-gate placeholder) | ✓ PASS |
| End-to-end capture→download→analyze (real Kaggle, sandboxed workspace) | manual run, see Data-Flow Trace | competition.md fully populated; CV scheme WRONG (GroupKFold) | ✗ FAIL (surfaced the truth-1 gap) |
| WR-01 reproduction: download_data.py on rc=127 (kaggle CLI missing) | monkeypatched `run_kaggle`/`preflight_entered` | exits 77, prints "clear whichever UI-only gate applies in a browser" (misleading) | ✗ FAIL (confirms WR-01) |
| WR-05 reproduction: config.json valid-JSON-but-not-object | `set_config_field(cfg=[], ...)` | `AttributeError: 'list' object has no attribute 'get'` (uncaught crash, not fail-clear) | ✗ FAIL (confirms WR-05; narrow precondition, INFO/WARNING only) |
| IN-02 reproduction: 8-digit numeric string parsed as ISO date | `datetime.fromisoformat("20200101")` | Succeeds → would be misclassified as datetime | ✗ Confirms IN-02 (narrow; no observed impact on titanic's actual columns) |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this repo (a stdlib-Python + pytest project, not a shell-probe-driven migration). Step 7c: SKIPPED (no probe scripts declared or discoverable) — the pytest suite (mock + live) is this project's probe-equivalent and was executed directly above (not merely narrated).

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| COMP-01 | 02-01, 02-02, 02-04, 02-05 | Capture static competition context (metric, schema, rules, limit, **correct** CV scheme) into `competition.md` | ✗ BLOCKED (partial) | Metric/schema/rules/limit fully satisfied and live-verified. CV-scheme sub-clause fails — see truth 1 gap. |
| COMP-02 | 02-01, 02-02, 02-03, 02-05 | Preflight UI-only gates; clear one-time browser instructions on a 403 | ⚠ PARTIAL | Rules-gate + unclassified-403 handling verified live and by test. WR-01 narrows "clear instruction" for the 127/124 sub-case. |
| COMP-03 | 02-03, 02-05 | Download competition data locally with safe zip-slip-protected extraction | ✓ SATISFIED | Fully verified by test and live run; no orphaned gap. |

No orphaned requirements: `.planning/REQUIREMENTS.md`'s Phase 2 row maps exactly COMP-01/02/03, and every plan's frontmatter `requirements:` field draws only from that set (02-01:[COMP-01,COMP-02], 02-02:[COMP-01,COMP-02], 02-03:[COMP-02,COMP-03], 02-04:[COMP-01], 02-05:[COMP-01,COMP-02,COMP-03]).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `scripts/cv_evidence.py` | 159-184 | `detect_group_candidates` false-positives on continuous numeric columns | 🛑 Blocker (drives truth 1's FAILED status) | Wrong CV scheme committed as trusted fact on real data — see Data-Flow Trace. |
| `scripts/download_data.py` | 169-179 | Non-403 gateway failures (127/124) collapsed into the UI-gate branch (WR-01, independently reproduced) | ⚠ Warning | Misleading remediation in a narrow precondition (CLI missing/stalled mid-flow); no busy-loop introduced. |
| `scripts/analyze_data.py` | 173-174, 305-315 | AV failure always reported "ML env absent" even if the env is present but AV errored (WR-02, reviewer-found, not independently re-verified beyond code read) | ⚠ Warning | Wrong remediation text in a narrower runtime-error case; does not affect the honest-SKIPPED labeling guarantee. |
| `scripts/untrusted.py` | 36 | Fence regex doesn't neutralise `<` + space + `/untrusted-content` (WR-03, reviewer-found; independently confirmed via regex inspection) | ℹ️ Info | Mitigated in practice by `strip_html` removing well-formed tag variants first; the no-derived-execution invariant is the real backstop regardless. |
| `scripts/competition_doc.py` | 49-52 | `replace_section` boundary can be confused by untrusted prose beginning with `## ` after HTML-entity decoding (WR-04, reviewer-found) | ℹ️ Info | Cosmetic spurious sub-heading risk only; `strip_html` collapses bodies to one line, limiting blast radius. |
| `scripts/init_workspace.py`, `capture_competition.py`, `analyze_data.py` | various | Valid-JSON-but-wrong-type `config.json` (e.g. `[]`) bypasses fail-clear and raises an uncaught `AttributeError`/`TypeError` (WR-05, independently reproduced) | ⚠ Warning | Narrow precondition (manual corruption to a non-object type); violates the project's own documented fail-clear invariant when it occurs. |
| `scripts/cv_evidence.py` | 90-109 | `_try_parse_date` accepts some 8-digit numeric strings as ISO dates, contradicting its own docstring (IN-02, reviewer-found; independently confirmed) | ℹ️ Info | No observed impact on titanic's real columns (no 8-digit numeric feature present); narrow risk on other datasets. |

No unresolved `TBD`/`FIXME`/`XXX` debt markers found in any file touched by this phase (grep matches were all references to the intentional `_TODO (Phase 2)_` template sentinel, not debt markers).

### Human Verification Required

None. All four success criteria were verified either by direct code inspection, the existing automated suite (executed, not narrated), or a live, reproducible run against the real Kaggle API in a disposable sandbox workspace (no repo files touched, confirmed via `git status`). The phase's own PLAN 02-05 already discharged the two genuinely human-only steps (browser rules acceptance, phone-URL confirmation) during execution, and that resolution is not in question here.

### Gaps Summary

The phase over-delivers on three of its four success criteria: the untrusted-content fence, the no-derived-execution invariant, the rules-gate/fail-closed-403 flow, and zip-slip-protected extraction are all solid, tested, AND independently reproduced live against the real Kaggle API in this verification pass.

The blocking gap is narrower but real: **success criterion 1's explicit word "correct"** does not hold. Running the phase's own reference example — `titanic`, the dataset every plan, fixture comment, and CONTEXT.md decision cites — through the full `capture → download → analyze` flow as SKILL.md documents it produces an objectively wrong committed CV scheme (`GroupKFold`, rationalized as "group leakage" on `Age`/`Fare`/`Cabin`) instead of the textbook-correct `StratifiedKFold`. The root cause is a false-positive in `cv_evidence.detect_group_candidates`'s "many entities" heuristic, which cannot distinguish a genuine repeated-entity id column from an ordinary continuous numeric feature. Because `config.json cv.scheme` and `competition.md`'s Cross-validation section are read as trusted ground truth by every downstream Phase-3+ experiment cycle, this defect propagates a wrong fact forward with unwarranted authority — exactly the failure mode Phase 2 exists to prevent for the daily-submission-limit provenance tagging (D-13), but which slips through unaddressed here for the CV scheme.

A secondary, narrower gap (WR-01, independently reproduced) means `download_data.py`'s "one clear browser instruction" guarantee degrades to a misleading instruction when the failure is actually a missing CLI or a stalled egress rather than a 403 — a fixable inconsistency, since the sibling `capture_competition.py` already implements the correct branching.

Both gaps have a concrete, scoped fix (tighten the group-candidate heuristic + add a regression fixture; mirror `_gateway_failure`'s 127/124 branches into `download_data.py`) and neither requires re-architecting any of the phase's sound design decisions (D-01 through D-16 all hold).

---

## Gap Closure Direction (operator decision, 2026-07-10)

Recorded for `/gsd:plan-phase 2 --gaps`:

- **Gap 1 (CV false-positive):** Fix depth = **tighten detection + test on real data**.
  Fix `cv_evidence.detect_group_candidates` so ordinary continuous numeric features
  (e.g. titanic `Age`/`Fare`) no longer read as group ids, and add a titanic-shaped
  fixture to `tests/cv_fixtures.py` so the regression is pinned. Keep the "tooling writes,
  AI never hand-writes" posture — an AI-override prompt in SKILL.md was explicitly NOT
  chosen for this pass.
- **Gap 2 (download exit-code classification / WR-01):** mirror the branch logic
  `capture_competition._gateway_failure` already uses — surface 127 (CLI missing) and
  124 (timeout) distinctly instead of collapsing them into the exit-77 UI-gate path.

---

_Verified: 2026-07-10T16:37:21Z_
_Verifier: Claude (gsd-verifier)_
