---
phase: 01-workspace-credentials-egress-guardrails
reviewed: 2026-07-09T23:19:42Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - SKILL.md
  - pyproject.toml
  - references/egress-allowlist.md
  - references/kaggle-cli-behavior.md
  - scripts/check_credentials.py
  - scripts/init_workspace.py
  - scripts/leak_scan.py
  - scripts/templates/competition.md.tmpl
  - scripts/templates/config.json.tmpl
  - scripts/templates/env.tmpl
  - scripts/templates/gitignore.tmpl
  - scripts/templates/pre-commit.tmpl
  - scripts/templates/pyproject.toml.tmpl
  - scripts/templates/README.md.tmpl
  - scripts/templates/settings.json.tmpl
  - scripts/templates/state.json.tmpl
  - scripts/templates/strategy.md.tmpl
  - tests/conftest.py
  - tests/test_config.py
  - tests/test_credentials_live.py
  - tests/test_credentials.py
  - tests/test_gitignore.py
  - tests/test_init_workspace.py
  - tests/test_leak_scan.py
  - tests/test_no_credential_leak.py
  - tests/test_settings.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-07-09T23:19:42Z
**Depth:** standard
**Files Reviewed:** 25
**Status:** issues_found

## Summary

This is the security-critical Phase 1 slice: credential detection/validation, an egress
allowlist written into `.claude/settings.json`, and a pre-commit secret-leak guard. The
credential-handling code is generally careful — exit-code-only validation, captured CLI
output is never echoed raw, masking is applied on the one path that prints a token value,
and consent (`--yes`) genuinely gates both the `chmod 600` self-heal and the `.env`
population. The scaffolder's deep-merge is non-destructive and fails clear (byte-preserving)
on corrupt control JSON, and the git staging is explicitly path-scoped (never `git add -A`).

However, the **primary secret-leak defense fails open**: the pre-commit scanner silently skips
any staged file whose name is non-ASCII (and, more broadly, on any `git` subprocess error),
allowing a real Kaggle credential in such a file to be committed unscanned. This was verified
empirically and is the one BLOCKER. The remaining findings are robustness and consistency
gaps: a missing subprocess timeout that can hang the checker under the very stall-timeout
egress-denial mechanism this phase documents, a corrupt-`state.json` clobber that resets the
experiment counter, a credential-source precedence that contradicts its own "env-canonical"
claim, and a security-flag (`failIfUnavailable`) that no test pins.

No hardcoded secrets, no injection sinks (the slug is JSON-escaped and never used as a path),
and no raw-credential echo were found in the shipped code.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Leak-scan guard fails open on non-ASCII (and other unrepresentable) staged filenames

**File:** `scripts/leak_scan.py:52-71`
**Issue:**
The scanner enumerates staged paths with `git diff --cached --name-only` (text mode) and reads
each blob with `git show :{path}`. With git's default `core.quotePath=true`, any path containing
a non-ASCII byte is emitted **C-quoted and octal-escaped**, e.g. `"caf\303\251.env"` (surrounding
quotes included). That quoted string is not a real pathspec, so `git show :"caf\303\251.env"`
fails, and `staged_blob` maps a non-zero return code to `""` — the file is **silently not scanned**.
The scan then reports no hits and the commit proceeds.

Verified empirically in a throwaway repo: a file named `café.env` containing
`KAGGLE_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` is emitted as `"caf\303\251.env"`, `git show`
returns `fatal: ... unknown revision or path`, and the blob is skipped — the secret would be
committed. Non-ASCII filenames are entirely plausible in a real workspace (data files,
international names), and for any file **not** covered by `.gitignore` this scanner is the only
automated secret defense — so this is a genuine fail-open of the last line of defense, not a
theoretical one.

The same fail-open class also applies to `staged_files()` (line 52-59): it ignores
`result.returncode` entirely, so if `git diff --cached` fails for any reason the function returns
`[]`, `scan_staged()` returns no hits, and `main()` exits 0 — a security guard that treats its
own failure as "clean." A defense-critical hook must fail **closed**.

**Fix:**
```python
def staged_files() -> list[str]:
    result = subprocess.run(
        # -z => NUL-delimited, un-quoted paths (no core.quotePath escaping)
        ["git", "-c", "core.quotePath=false",
         "diff", "--cached", "-z", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
    )
    if result.returncode != 0:
        # fail CLOSED: cannot enumerate staged files -> block the commit
        print("[BLOCKED] leak scan could not read the git index; refusing commit "
              "(override a genuine issue with `git commit --no-verify`).", file=sys.stderr)
        raise SystemExit(1)
    out = result.stdout.decode("utf-8", errors="surrogateescape")
    return [p for p in out.split("\0") if p]


def staged_blob(path: str) -> str:
    result = subprocess.run(["git", "show", f":{path}"], capture_output=True)  # path is a real, unquoted pathspec now
    if result.returncode != 0:
        # fail CLOSED for an ACM path we could not read (deletes are excluded by the filter)
        print(f"[BLOCKED] leak scan could not read staged blob for {path!r}; refusing commit.",
              file=sys.stderr)
        raise SystemExit(1)
    return result.stdout.decode("utf-8", errors="ignore")
```
(Add `import sys`.) Using `-z` + `core.quotePath=false` yields real pathspecs; converting a git
error into a hard block makes the guard fail closed instead of open.

## Warnings

### WR-01: `run_kaggle_list` has no subprocess timeout — the checker can hang indefinitely

**File:** `scripts/check_credentials.py:301-306`
**Issue:**
`subprocess.run(["kaggle", "competitions", "list"], capture_output=True, text=True)` has no
`timeout=`. `references/egress-allowlist.md` (§2 "Denial mechanism") documents that the sandbox
denies off-allowlist egress precisely by **stalling the proxy CONNECT until the client times out**
— so a network stall is the *expected* failure shape here, not an exotic one. With no timeout the
checker blocks forever on a hung connection, defeating the D-07 "degrade gracefully, don't abort"
intent. CLAUDE.md's own open-risks note likewise stresses "always bound the poll with a timeout."
**Fix:**
```python
try:
    proc = subprocess.run(
        ["kaggle", "competitions", "list"],
        capture_output=True, text=True, timeout=60,
    )
except subprocess.TimeoutExpired:
    return 124, "kaggle competitions list timed out"
return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")
```
Treat the timeout as a non-zero (UNVALIDATED) result with a secret-free remediation.

### WR-02: `write_credentials_state` silently clobbers a corrupt `state.json` and resets `next_exp_id`

**File:** `scripts/check_credentials.py:264-277`
**Issue:**
On a `JSONDecodeError`/`OSError` reading `control/state.json`, the function sets `data = {}` and
then writes a fresh `{"credentials": ..., "next_exp_id": 1}`. This **overwrites** a
corrupt/partially-written state file and **resets `next_exp_id` back to 1**, discarding the
experiment counter and any user/machine keys. That is a data-loss path (later phases derive
`exp-NNN` dir names from `next_exp_id`, so a silent reset to 1 risks colliding with / overwriting
existing experiment directories) and it is inconsistent with the D-02 fail-clear contract that
`init_workspace.py` applies to every other control-plane JSON (corrupt → preserve bytes, exit
non-zero). A machine-managed file that has become unparseable should not be silently rewritten.
**Fix:** On a decode failure, do not write; print a fail-clear message naming `control/state.json`
and return non-zero (mirroring `MalformedControlJSON` handling in `init_workspace.py`), so the
corrupt file is preserved for repair rather than overwritten and the counter is never reset.

### WR-03: Credential-source precedence ranks the `access_token` file above env vars, contradicting the "env-canonical" claim

**File:** `scripts/check_credentials.py:86-102`
**Issue:**
`detect_source` returns `("access_token", None)` as soon as `~/.kaggle/access_token` exists —
**before** checking `KAGGLE_API_TOKEN` / `KAGGLE_USERNAME`+`KAGGLE_KEY`. Yet the module docstring
(line 11) and the `_SOURCE_LABELS` text advertise "env beats a file; D-04 env-canonical," and
`references/kaggle-cli-behavior.md` (§Observed source precedence) records the CLI's own guidance
order as `KAGGLE_API_TOKEN` **then** `~/.kaggle/access_token`. So for a user who has *both* an
`access_token` file and an env token set, the checker reports `access_token file` as the ACTIVE
source while the CLI may actually use the env token. Validation is exit-code based so pass/fail is
unaffected, but the reported source and the source-specific remediation can be wrong/misleading
(e.g., pointing the user at the wrong credential to fix). The "env-canonical" wording is only
actually true relative to the legacy `kaggle.json` (checked after env), not `access_token`.
**Fix:** Reconcile the ranking with the CLI's documented order (env token/pair ahead of the
`access_token` file), or narrow the "env-canonical" claim to `kaggle.json` only so the reported
source matches reality.

### WR-04: Legacy 32-hex API key evades the scanner outside a `"key":` / `KAGGLE_KEY` context

**File:** `scripts/leak_scan.py:41-49`
**Issue:**
The four patterns catch the new OAuth/scoped token shapes (`kagat_`/`kagrt_`/`KGAT_`) in any
context, but a **legacy 32-hex Kaggle API key** is only caught inside a `"key": "<32hex>"` JSON
field or a `KAGGLE_KEY=`/`KAGGLE_API_TOKEN=` assignment. A real legacy key pasted under any other
name — e.g. `api_key = "0123...ef"`, `token = "0123...ef"`, or a bare value in a notebook cell —
is **not** detected. This is a deliberate tradeoff (documented in the module header) to avoid
false-positives on commit SHAs / hashes, and `.gitignore` covers the canonical files, but it is a
real residual gap in the "defense-in-depth" secret scanner for the legacy key format.
**Fix:** Acceptable to keep as a documented tradeoff, but surface it explicitly (the header lists
it only implicitly) and consider a lower-false-positive heuristic (e.g. flag a bare 32-hex only
when co-located with a `kaggle`/`key`/`token` token on the same or adjacent line).

### WR-05: No test pins the security-critical `sandbox.failIfUnavailable: true` fail-closed flag

**File:** `tests/test_settings.py:31-63`
**Issue:**
`references/egress-allowlist.md` and `merge_settings` treat `sandbox.failIfUnavailable: true` as a
core control (it converts a missing socat/bubblewrap back-end from "silently unsandboxed, egress
open" into a hard failure). But no test asserts it is written on a fresh workspace or forced on a
merge — `test_egress_allowlist*` only check `allowedDomains` membership and `sandbox.enabled`. A
regression that dropped `failIfUnavailable` from `settings.json.tmpl` or from `merge_settings`
would leave the whole suite green while silently reopening the unsandboxed-fallback hole.
**Fix:** Add assertions, e.g. `assert settings["sandbox"]["failIfUnavailable"] is True` in both
`test_egress_allowlist` and `test_egress_allowlist_merges_existing`.

### WR-06: Credential unit tests are non-hermetic — they hit the live Kaggle API when the CLI is installed

**File:** `tests/test_credentials.py:30-127`
**Issue:**
`test_precedence`, `test_chmod_600`, `test_chmod_600_requires_consent`, and
`test_env_population_requires_consent` do not scrub `PATH` or stub the CLI, so when a real `kaggle`
binary is present (the 01-04 Task 3 checkpoint explicitly installs it) `check_credentials.py`
reaches its live-validation branch and runs `kaggle competitions list` against the network with
fabricated creds. The assertions only inspect chmod/`.env`/detection output, so the tests still
pass — but they make an unintended network round-trip, and because neither `run_kaggle_list`
(WR-01) nor `conftest.run_script` sets a timeout, they can **hang** under the documented
stall-timeout egress denial, or flake offline. This is the same non-hermeticity class that was
already fixed for `test_kaggle_missing` (PATH-scrubbed) and `test_subprocess_output_no_secret`
(CLI stubbed); these four were left inconsistent.
**Fix:** Scrub `PATH` to an empty dir (as `test_kaggle_missing` does) or point at a stub `kaggle`
so the live branch is deterministic and offline-safe for tests that only exercise
detection/chmod/`.env`.

## Info

### IN-01: Unused `import sys` and unused module constant `SCRIPT_DIR`

**File:** `scripts/check_credentials.py:38,41`
**Issue:** `import sys` has no `sys.*` reference (exit is via `raise SystemExit(main())`, a
builtin), and `SCRIPT_DIR = Path(__file__).resolve().parent` is never used (this script accesses
no bundled templates). Dead code that invites confusion about self-location intent.
**Fix:** Remove both. (Note the fix for CR-01 reintroduces a legitimate `import sys` in
`leak_scan.py`, not here.)

### IN-02: `_mask` discloses the last 4 characters of the secret

**File:** `scripts/check_credentials.py:47-55`
**Issue:** With the default `prefix=0`, `_mask` returns `"*"*(len-4) + value[-4:]`, i.e. the last
four characters of the token appear in output (the one call site prints a masked env value).
Showing last-4 is a conventional masking choice and the unit tests confirm the *full* value never
appears, but it is still a partial disclosure of a high-entropy secret to logs/transcripts.
**Fix:** Optional hardening — for token-typed values, fully mask (`****` / show only the token
*type*), reserving last-4 for lower-sensitivity identifiers.

### IN-03: `--slug` is unvalidated (safe now, but untrusted downstream)

**File:** `scripts/init_workspace.py:464-465, 279-284`
**Issue:** `--slug` is accepted verbatim. In Phase 1 this is safe: it is JSON-escaped via
`json.dumps` and only ever substituted as *text* into markdown/JSON — it is never used to build a
filesystem path (no traversal) and cannot inject into the JSON. But later phases will feed
`config.competition_slug` into `kaggle competitions download <slug>` / kernel metadata; if any of
those is ever assembled through a shell, an unvalidated slug becomes an injection vector.
**Fix:** Add a cheap format guard now (`re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)`), matching
Kaggle's own slug shape, so the untrusted value is constrained at the point of entry.

### IN-04: `--diff-filter=ACM` excludes renames, contradicting the scanner's own rationale

**File:** `scripts/leak_scan.py:17, 55`
**Issue:** The module docstring justifies content scanning because "a secret can hide in a renamed
file," yet `--diff-filter=ACM` deliberately omits `R` (renamed). This is harmless in practice (a
blob detected as a rename source must already exist in `HEAD`, i.e. it was already committed, so no
*new* leak is introduced via a pure rename), but the stated rationale and the filter disagree and
could mislead a future maintainer.
**Fix:** Drop the "renamed file" clause from the docstring, or intentionally include `R` in the
filter if renamed-in content is meant to be rescanned.

---

_Reviewed: 2026-07-09T23:19:42Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
