---
phase: 1
reviewers: [codex]
reviewers_attempted: [codex, opencode, cursor]
reviewers_unavailable:
  opencode: "Insufficient balance (opencode.ai account has no credit)"
  cursor: "Authentication required (cursor-agent not logged in / no CURSOR_API_KEY)"
  claude: "Skipped for independence — this review runs inside Claude Code"
  gemini: "CLI not installed"
  qwen: "CLI not installed"
  coderabbit: "CLI not installed"
reviewed_at: 2026-07-09T17:32:08Z
plans_reviewed: [01-01-PLAN.md, 01-02-PLAN.md, 01-03-PLAN.md, 01-04-PLAN.md]
---

# Cross-AI Plan Review — Phase 1

> **Reviewer coverage note:** Of the CLIs requested via `--all`, only **Codex** produced a
> review. `opencode` failed (insufficient account balance) and `cursor` failed (not
> authenticated); `gemini`/`qwen`/`coderabbit` are not installed; `claude` was skipped for
> independence (this command runs inside Claude Code). A single-reviewer pass means there is
> **no cross-model consensus signal** — treat Codex's findings as one strong perspective, not a
> triangulated verdict. Re-run with a second CLI authenticated (`opencode`/`cursor`/`gemini`)
> for genuine adversarial cross-review.

## Codex Review

## Summary

Overall the phase is well-structured and mostly executable: it separates contract/tests, scaffolding, egress/git hardening, and credential validation in a sensible order. The strongest parts are the explicit safe-merge rule, the recognition that CLI egress must be controlled through `sandbox.network.allowedDomains`, and the decision to scaffold even when Kaggle auth fails. The main readiness gaps are contract drift between locked decisions and script behavior, under-tested security/egress guarantees, and several places where the test suite appears too shallow to prove the advertised Phase 1 success criteria.

## Strengths

- Clear vertical MVP boundary: workspace init, config/state/ledger, git tracking, egress settings, and credential validation are the right first slice.
- Good sequencing: 01-01 defines the interface, 01-02 builds the stable workspace core, 01-03 and 01-04 can mostly proceed in parallel after that.
- Safe-merge/idempotency is correctly treated as a first-class invariant.
- D-07 is pragmatic: failed credentials should not block scaffolding.
- Egress research is materially better than copying `WebFetch` permissions and assuming subprocesses are covered.
- Credential handling has good baseline instincts: `shutil.which` first, no raw secret output, chmod hardening, masked display, and state-based validation.

## Concerns

- **HIGH: D-01 is not actually enforced by the implementation contract.**
  01-02 allows `init_workspace.py --workspace <dir>` with optional `--slug` and default execution target. That can create files before the "ask slug + execution target, confirm, THEN create" flow. If the skill orchestrates prompts but the script itself can scaffold without required answers, the locked decision is only convention, not enforced.

- **HIGH: Success criterion 5 is overstated for Phase 1.**
  The plans correctly note that missing `socat` silently degrades sandbox enforcement and project settings may prompt rather than hard-block. That means "off-allowlist fetch is refused" is not guaranteed by generated workspace files alone. The phase can produce settings and warnings, but actual enforcement depends on host/runtime state and possibly managed/org settings.

- **HIGH: 01-03 and 01-04 both depend on 01-02 but share state semantics indirectly.**
  01-03 creates initial commits and scans the scaffold. 01-04 mutates `control/state.json` credentials status and may populate `.env` with consent. If run in parallel on the same workspace, git status/commit timing and state updates can race. As plans they are parallelizable in repo implementation, but not necessarily against the same generated workspace during verification.

- **HIGH: Initial commit ordering may commit too much or fail unpredictably.**
  `git add -A` after scaffolding will include all non-ignored files in the workspace. In a supposedly empty folder that is fine, but "safe-merge/idempotent/re-runnable" plus user-provided files means rerunning init in a non-empty workspace could stage unrelated user files. This violates the spirit of not touching unrelated work.

- **MEDIUM: RED tests do not appear to pin all locked decisions.**
  Missing or weak coverage likely includes: no write before confirmation, no overwrite outside `--set-execution-target`, deep-merge nested preservation, malformed JSON behavior, atomic write behavior, `.claude/settings.json` merge behavior, consent gating for chmod/env population, no raw secret in subprocess stderr/stdout, and git not staging unrelated files.

- **MEDIUM: Deep merge behavior is under-specified.**
  "Add missing keys, keep user edits" needs rules for type mismatches, malformed JSON, arrays, null values, and schema upgrades. For example, if `config.json` has `"cv": "custom"` or invalid JSON, does init fail, back up, skip, or repair with consent?

- **MEDIUM: Credential precedence may be too Kaggle-CLI-specific and brittle.**
  Access token, `KAGGLE_API_TOKEN`, username/key, `kaggle.json`, OAuth precedence should be verified against the actual installed Kaggle package. If the framework's detection disagrees with the CLI, the tool may report one active source while Kaggle uses another.

- **MEDIUM: Leak scanner has likely false negatives.**
  It scans staged diff text, but secrets can appear in renamed files, binary-ish files, multiline formats, base64 blobs, notebooks, dotenv variants with quotes/spaces/export, lowercase env names, or username/key pairs where only the key is sensitive. Regexes listed are a good start but not enough to justify broad "credential-leak check passes."

- **MEDIUM: Leak scanner has likely false positives around JSON `"key"` fields.**
  Any 32-hex JSON key field may be blocked even when unrelated. That may be acceptable, but the plan should document the tradeoff and provide an override procedure that does not normalize bypassing the hook.

- **MEDIUM: `.gitignore` experiment artifact rules may ignore useful source files accidentally.**
  Patterns like `experiments/*/*.{csv,zip,pkl,parquet}` depend on Git's pattern behavior and may not handle deeper paths. Also notebooks are explicitly unignored, but notebook outputs can contain secrets or large data unless stripped later.

- **MEDIUM: `allowedDomains` wildcard semantics are not tested.**
  The plan includes `*.storage.googleapis.com`. Depending on the settings parser, wildcard behavior may differ or be unsupported. The tests only check set inclusion, not runtime enforcement or schema validity.

- **MEDIUM: `.claude/settings.json` safe-merge is missing.**
  01-03 says write settings via `create_if_absent`. D-09 says write/merge allowlist. If a user already has `.claude/settings.json`, create-if-absent skips it and the allowlist is not installed.

- **MEDIUM: `SKILL.md allowed-tools` may be too broad or inconsistent.**
  `Bash(git *)`, `Bash(uv run *)`, and `Bash(kaggle *)` are broad. Maybe acceptable for MVP, but they should be justified against the threat model. Also the scripts use `python3 scripts/...`; if allowed-tools only includes `uv run *`, the invocation path should be consistent.

- **LOW: The test count mismatch is real and should be fixed before execution.**
  The plan says conftest + 8 RED test files, but frontmatter and named files suggest 9 test files depending how `test_config.py` is counted.

- **LOW: `pyproject.toml` appears in both skill package and scaffolded workspace.**
  This is fine, but the plans should explicitly distinguish repo-root skill `pyproject.toml` from workspace-template `pyproject.toml.tmpl` to avoid accidental overwrite/confusion.

- **LOW: `git init -b main` portability needs fallback.**
  Older Git versions may not support `-b`. The plan should handle fallback to `git init` plus branch rename.

## Suggestions

- Make `--slug` required for creation, or add an explicit `--yes-scaffold`/`--confirmed` flag so the script enforces D-01 mechanically.

- Split init into a dry-run/plan phase and an apply phase:
  `init_workspace.py --plan ...` prints intended files, then `--apply --confirmed` writes.

- Add tests for:
  - no files created when required answers are missing;
  - rerun preserves edited docs and config;
  - nested deep-merge preserves `cv` subkeys;
  - malformed JSON fails clearly without overwriting;
  - existing `.claude/settings.json` gets merged, not skipped;
  - `git add` only stages scaffold-owned files;
  - secret values are absent from captured stdout/stderr;
  - chmod/env population requires explicit consent.

- Treat egress enforcement as two deliverables:
  - generated settings correctness;
  - host enforcement verification.

  Do not claim Phase 1 fully satisfies refusal unless `socat`/sandbox enforcement is verified in CI or during the human checkpoint.

- Change initial commit logic to stage only known scaffold paths, not `git add -A`.

- Define a schema-versioned merge policy:
  preserve unknown keys, add missing known keys, fail on invalid JSON, and require consent/backups for type conflicts.

- Add runtime validation for `.claude/settings.json` if Claude Code exposes any schema check; otherwise add a reference fixture and keep the test strict about exact keys.

- Make 01-03 and 01-04 "parallel in implementation, serialized in workspace verification." That avoids git/state races while preserving wave efficiency.

- Harden leak scanning for dotenv spacing/quotes/export, notebooks, and staged filenames. Consider scanning staged file contents via `git show :path` rather than only unified diff lines.

- Record real Kaggle CLI stderr/exit-code observations in a checked-in reference note or test fixture so future changes are not based on tribal memory.

## Risk Assessment

**Overall risk: MEDIUM.**

The architecture is sound for an MVP, and the plans show unusually good awareness of security and runtime constraints. The risk is not that the phase is directionally wrong; it is that several success criteria are stronger than what the implementation/tests currently prove. The biggest execution risks are D-01 contract drift, egress enforcement depending on host/runtime state, and git/secret handling edge cases. Tightening those before implementation would make Phase 1 much more defensible.

---

## OpenCode Review

OpenCode review unavailable — CLI returned `Error: Insufficient balance` (opencode.ai account has no credit). No review produced.

---

## Cursor Review

Cursor review unavailable — `cursor-agent` requires authentication (`Error: Authentication required. Please run 'cursor agent login' first, or set CURSOR_API_KEY`). No review produced.

---

## Consensus Summary

Only one reviewer (Codex) produced output, so this is a **single-reviewer synthesis, not a cross-model consensus**. The points below are Codex's, triaged by severity and cross-checked against the plan text so the planner can act on them directly.

### Agreed Strengths

*(Single reviewer — these are Codex's, not corroborated by a second model.)*

- Sound vertical-MVP decomposition: contract/tests → scaffolder → egress/git hardening → credentials, in a defensible order.
- The egress finding (enforce via `sandbox.network.allowedDomains`, not `WebFetch` permissions) is correctly identified as the crux and is materially better than the exemplar.
- Safe-merge/idempotency and D-07 (scaffold-anyway-flag-creds) are treated as first-class invariants.
- Credential handling instincts are good: `shutil.which` first, exit-code validation, masking, chmod self-heal, no raw secret output.

### Agreed Concerns (highest priority — verified against the plans)

These are the findings most worth acting on before execution. Where a finding was checked against the actual plan text, the verification note is included.

1. **[HIGH] D-01 (guided-then-scaffold) is convention, not enforced by the script.** `init_workspace.py` can scaffold with a defaulted `--execution-target local` and no confirmation gate. **Verified:** 01-02 argparse gives `--execution-target` a default and does not require a confirmation flag. *Action:* make the script mechanically enforce the prompt-first contract (required `--slug` for creation, or a `--confirmed`/`--yes-scaffold` gate), so a direct script call can't bypass D-01.

2. **[HIGH] `.claude/settings.json` is written with `create_if_absent`, contradicting D-09's "write/**merge**".** **Verified — this is a real bug in the plan:** 01-03 Task 1 explicitly says "write `.claude/settings.json` … via `create_if_absent` (never overwrite — D-02)", but D-09/CONTEXT says *merge* the allowlist. A user who already has a `.claude/settings.json` (very common in a Claude Code project) will have the scaffold **skip** it entirely — egress is then silently never installed, directly defeating success criterion 5. *Action:* settings.json needs the same deep-merge treatment as the control-plane JSON (merge `sandbox.network.allowedDomains` and `permissions.allow`), not create-if-absent. Add a test for the pre-existing-settings case.

3. **[HIGH] `git add -A` can stage unrelated user files on a re-run of a non-empty workspace.** **Verified:** 01-03 Task 2 uses `git add -A` before the initial commit. Combined with the safe-merge "re-runnable on a partial/non-empty workspace" promise, this can sweep user files into the scaffold commit. *Action:* stage only scaffold-owned paths explicitly; also guard the "one initial commit" assumption when `.git` already exists (re-run should not attempt a second `chore: scaffold workspace` commit).

4. **[HIGH] Success criterion 5 ("off-allowlist fetch refused") is stronger than what Phase 1 can prove.** Enforcement depends on `socat` (missing on host → silent unsandboxed fallback) and, for a true no-prompt block, managed settings. The plans acknowledge this (01-03 Task 3 checkpoint + warnings), but the *success criterion wording* still over-claims. *Action:* split into "generated settings are correct" (automated) vs "host enforcement verified" (checkpoint), and don't mark criterion 5 fully met unless the socat-installed refusal is actually observed.

5. **[MEDIUM] Deep-merge semantics under-specified.** No rule for type mismatches, arrays, null values, malformed/corrupt `config.json`, or schema upgrades. *Action:* define a schema-versioned merge policy (preserve unknown keys, add missing known keys, fail-clearly on invalid JSON without overwriting, consent+backup on type conflict) and test malformed-JSON + nested `cv` subkey preservation.

6. **[MEDIUM] RED suite likely under-pins the locked decisions.** Behaviors plausibly untested: no-write-before-confirm, no-overwrite-outside-setter, deep-merge nested preservation, settings.json merge, consent gating for chmod/`.env` population, no-secret-in-subprocess-output. Because 01-01 is explicitly the behavioral contract for all GREEN work, any decision without a test is a decision the later plans aren't actually forced to honor. *Action:* add the tests listed in Codex's Suggestions before/within 01-01.

7. **[MEDIUM] Leak scanner false-negatives and false-positives.** Diff-only scanning misses dotenv `export`/quoted/spaced variants, lowercase env names, notebooks, base64, renamed files; the bare-32-hex `"key":` rule can false-positive on unrelated JSON. *Action:* scan staged *content* (`git show :path`) not only unified-diff lines; broaden dotenv patterns; document the false-positive tradeoff + a non-normalizing override path.

8. **[MEDIUM] `allowedDomains` wildcard (`*.storage.googleapis.com`) semantics are asserted but not validated** against the Claude Code settings schema; tests only check set-membership, not schema validity or enforcement.

9. **[MEDIUM] Credential precedence is asserted from docs, not the installed package.** If the detector's precedence disagrees with the actual `kaggle` CLI, the tool can report a different active source than the one Kaggle uses. *Action:* pin the observed precedence with the real CLI during 01-04 (already partly planned via the throwaway-env capture) and record it as a fixture.

### Divergent Views

None — only one reviewer produced output, so there is nothing to compare. **This is itself a gap:** the value of `/gsd:review` is adversarial cross-model triangulation, and this run achieved a single perspective. Re-running with a second authenticated CLI is recommended before treating these findings as settled.

### Reviewer's overall verdict

**MEDIUM risk.** Directionally sound MVP with unusually good security/runtime awareness; the exposure is that several success criteria (esp. #5 egress, and the D-01/D-09 contracts) are currently stronger than the implementation and tests prove. Tightening the settings.json merge, the `git add` scope, D-01 enforcement, and the deep-merge/test coverage would make Phase 1 defensible.
