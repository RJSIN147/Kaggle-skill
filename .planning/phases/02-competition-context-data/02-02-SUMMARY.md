---
phase: 02-competition-context-data
plan: 02
subsystem: infra
tags: [kaggle-cli, prompt-injection, untrusted-content, config-write, section-merge, pytest, security]

# Dependency graph
requires:
  - phase: 02-competition-context-data (plan 02-01)
    provides: "scripts/kaggle_gateway.py — run_kaggle / dump_last_error / classify_gate / UI_GATE / LIMIT_NEEDS_USER (the single D-16 CLI chokepoint)"
  - phase: 01-workspace-credentials-egress-guardrails
    provides: "init_workspace.create_if_absent / _render_text / write_control_json / MalformedControlJSON / SCAFFOLD explicit-path staging; leak_scan.py pre-commit guard; competition.md.tmpl + config.json.tmpl; pytest conftest (run_script/seeded_workspace)"
provides:
  - "scripts/untrusted.py — escape_markers (fence-lookalike neutraliser) + wrap_untrusted (source-attributed fence writer)"
  - "scripts/competition_doc.py — replace_section, the ONE shared section-safe-merge for competition.md (used by capture AND analyze)"
  - "scripts/capture_competition.py — pages+files → curated competition.md + control/raw provenance + tooling-written config machine fields"
  - "init_workspace.set_config_field(config_path, key_path, value) — the generalized direct-overwrite setter that CAN fill a reserved-null key (set_execution_target is now a thin wrapper)"
  - "config.json.tmpl submission{daily_limit,limit_provenance} + competition{type} reserved keys"
  - "control/raw/competition-pages.json (tracked provenance) + competition-type-signals.json (D-14 signals+recommendation)"
affects: [02-04-analyze-data, 03-experiment-loop, 05-scoring-submission]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Untrusted-content boundary (D-02): escape_markers neutralises every fence lookalike (case/tag/whitespace) with an inert fullwidth sentinel; no aggressive sanitize"
    - "No-derived-execution invariant (D-02): every subprocess argv comes only from config.json + argparse; no path/command/URL is derived from competition text"
    - "Direct-overwrite config setter (set_config_field) vs add-missing-only merge (write_control_json): values LAND on reserved-null keys; structure is reserved by the merge"
    - "Section-safe-merge at section granularity (D-04): replace_section fills a section only while its body holds the _TODO (Phase 2)_ default; curated/populated sections survive"
    - "Provenance-tagged facts (D-13): daily_limit always travels with limit_provenance ∈ {extracted,user-supplied,assumed_default}"
    - "Tooling-emits-signals → AI-commits → tooling-writes (D-14): capture emits competition.type signals+recommendation; the AI commits via --set-competition-type; set_config_field writes"

key-files:
  created:
    - "scripts/untrusted.py"
    - "scripts/competition_doc.py"
    - "scripts/capture_competition.py"
    - "tests/test_untrusted.py"
    - "tests/test_limit_regex.py"
    - "tests/test_capture.py"
    - "tests/fixtures/pages_all.json"
  modified:
    - "scripts/init_workspace.py"
    - "scripts/templates/config.json.tmpl"
    - "scripts/templates/competition.md.tmpl"
    - "tests/conftest.py"

key-decisions:
  - "set_execution_target generalized (not forked) into set_config_field — mirrors the D-16 generalize-don't-fork posture; SETUP-02 unchanged"
  - "escape_markers uses a fullwidth '＜' (U+FF1C) sentinel — visible to a reader, inert as a fence opener"
  - "capture writes ONLY the metric + rules sections of competition.md; the Data-schema/CV sections are left for analyze_data.py (02-04) so replace_section's D-04 skip never blocks the authoritative schema write"
  - "competition.md.tmpl intro reworded to avoid a literal '<untrusted-content …>' documentation marker so the doc's real data fences stay perfectly balanced"

patterns-established:
  - "Pattern 1: fence-writer (untrusted.py) — escape THEN wrap; the framework's own outer markers are the only real fence"
  - "Pattern 2: one section-safe-merge (competition_doc.replace_section) shared by every doc-populating script"
  - "Pattern 3: machine fields written only by the enum/argparse-validated tooling path, never hand-written"

requirements-completed: [COMP-01, COMP-02]

# Metrics
duration: ~30min
completed: 2026-07-10
---

# Phase 2 Plan 02: Capture Competition Constitution Summary

**Machine-derived competition constitution (metric, rules, provenance-tagged daily limit, competition type) captured into competition.md through the kaggle CLI, with every ingested page passed through an unbreakable untrusted-content fence and a no-derived-execution invariant, and machine facts landed in config.json by a new direct-overwrite setter.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-07-10T17:16:00+05:30 (worktree base)
- **Completed:** 2026-07-10T17:46:00+05:30
- **Tasks:** 3
- **Files modified:** 11 (7 created, 4 modified)

## Accomplishments
- `escape_markers` neutralises every untrusted-content fence lookalike (case / tag / whitespace / attribute variants) via an inert fullwidth sentinel — the fence provably cannot be broken from inside (`test_fence_cannot_be_broken`).
- No-derived-execution invariant proven: a `TAINT_a1b2c3` sentinel embedded in the rules page reaches NO subprocess argv, and every recorded `argv[0]` is on the `{kaggle,git,uv,python3}` allowlist (`test_no_competition_text_reaches_subprocess`).
- The config-write BLOCKER is fixed: `set_config_field` direct-overwrites a reserved-null key, so a non-null `daily_limit=10` / `competition.type="code"` LANDS on the exact key-exists-as-null config that `write_control_json`'s add-missing-only merge could never fill (regression GREEN).
- `capture_competition.py` fetches pages+files through the D-16 gateway (D-15, no scraping), extracts the anchored `per day` limit (titanic → 10, avoiding the "up to 5 final" trap), always tags `limit_provenance` (D-13), emits `competition.type` signals+recommendation for the AI to commit (D-14), and writes competition.md metric+rules via the shared section-safe-merge.
- Provenance (`control/raw/competition-pages.json`, `competition-type-signals.json`) is staged by explicit path — verified end-to-end that the gitignored `last-error.txt` is never swept in.

## Task Commits

Each task was committed atomically:

1. **Task 1: RED tests + fixture + seeded_workspace fix** - `5c51915` (test)
2. **Task 2: escape_markers fence writer + section-safe-merge** - `6a9d586` (feat)
3. **Task 3: capture_competition.py + generalized set_config_field** - `7618de3` (feat)

_Task 2 and Task 3 are `tdd="true"`; the Task 1 RED commit is the shared failing-test gate for both (RED → GREEN across 6a9d586/7618de3)._

## Files Created/Modified
- `scripts/untrusted.py` - `escape_markers` (fence-lookalike neutraliser) + `wrap_untrusted` (source-attributed fence writer with the data-not-instructions note)
- `scripts/competition_doc.py` - `replace_section`, the single section-safe-merge keyed on the `_TODO (Phase 2)_` sentinel with a `## ` boundary rule
- `scripts/capture_competition.py` - pages+files → escape/fence → competition.md + control/raw provenance + tooling-written config machine fields; `--set-competition-type`, `--daily-limit`, `--assume-default-limit`
- `scripts/init_workspace.py` - added `set_config_field` (direct-overwrite setter); `set_execution_target` re-expressed as a thin wrapper over it
- `scripts/templates/config.json.tmpl` - reserved `submission{daily_limit,limit_provenance}` + `competition{type}` as null
- `scripts/templates/competition.md.tmpl` - five `_TODO (Phase 2)_` sections (Evaluation metric, Data schema, Rules & limits, Cross-validation, Adversarial validation); balanced-fence intro
- `tests/conftest.py` - `seeded_workspace` extended with the reserved-null submission/competition keys (the exact blocker shape)
- `tests/test_untrusted.py`, `tests/test_limit_regex.py`, `tests/test_capture.py`, `tests/fixtures/pages_all.json` - the two C2 deliverable tests + limit-regex + capture (incl. the config-write regression) + titanic fixture

## Decisions Made
- Generalized `set_execution_target` into `set_config_field` rather than forking a second writer (D-16 generalize-don't-fork posture); SETUP-02 tests remain green with the wrapper.
- Capture populates only the metric + rules sections of competition.md; the Data-schema and CV sections are deliberately left for `analyze_data.py` (02-04) so `replace_section`'s D-04 skip does not pre-empt the authoritative schema write.
- Reworded the `competition.md.tmpl` intro to drop a literal `<untrusted-content …>` documentation marker (see deviation 1).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] competition.md intro emitted an unbalanced (phantom) fence-open marker**
- **Found during:** Task 3 (end-to-end smoke verification)
- **Issue:** The `competition.md.tmpl` intro blockquote documented the fence with a literal `` `<untrusted-content …>` ``. That illustrative marker rendered into the generated `competition.md` as an extra, unmatched `<untrusted-content` open — harmless (framework-authored, not a data fence) but it left the doc's fence markers unbalanced and would trip any downstream fence-integrity scan.
- **Fix:** Reworded the intro to "source-attributed untrusted-content fences" (no literal open marker). The real data fences from `wrap_untrusted` are now the only fence-regex matches; a smoke test confirms the count is even.
- **Files modified:** scripts/templates/competition.md.tmpl
- **Verification:** Smoke test asserts `len(findall(r"</?\\s*untrusted-content", md)) % 2 == 0`; full suite green.
- **Committed in:** 7618de3 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Cosmetic/integrity fix to template documentation; no behavior or scope change. No scope creep.

## Issues Encountered
- The Task 1 RED verification flagged `test_bogus_competition_type_rejected` as "passed" at RED — it passes vacuously (the not-yet-built script exits non-zero, config unchanged). It passes for the correct reason at GREEN (argparse `choices` rejects the value before any write), so this is expected, not a false RED.
- `strip_html` incidentally removes tag-shaped fence lookalikes (`</untrusted-content>`) before `escape_markers` runs; the fence guarantee still holds because `escape_markers` is unit-tested directly on raw (un-stripped) inputs across all variants.

## User Setup Required
None - no external service configuration required. (Live capture needs the Kaggle credential + `api.kaggle.com` egress, both established in Phase 1 / plan 02-01; all tests here are mock-backed.)

## Next Phase Readiness
- The two shared write-boundary primitives (`set_config_field`, `competition_doc.replace_section`) are ready for `analyze_data.py` (02-04) to write the Data-schema / CV / Adversarial-validation sections and `cv.scheme` without reimplementing a setter or section parser.
- `submission.daily_limit` + `limit_provenance` and `competition.type` are now recorded truthfully for Phase 5's budget gate (a fabricated `5` is no longer byte-identical to an extracted one).
- Concern: live `competition.type` still requires the AI to invoke `--set-competition-type` after reading the emitted signals; a plain capture leaves it `null` (which safely blocks Phase 5's CSV path) — this is the intended D-14 flow, not a gap.

## Self-Check: PASSED
- Created files: all 7 FOUND (untrusted.py, competition_doc.py, capture_competition.py, test_untrusted.py, test_limit_regex.py, test_capture.py, fixtures/pages_all.json)
- Modified files: all 4 FOUND (init_workspace.py, config.json.tmpl, competition.md.tmpl, conftest.py)
- Commits: 5c51915, 6a9d586, 7618de3 all FOUND
- Full suite: 58 passed

---
*Phase: 02-competition-context-data*
*Completed: 2026-07-10*
