---
phase: 02-competition-context-data
reviewed: 2026-07-10T16:23:11Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - references/egress-allowlist.md
  - references/kaggle-cli-behavior.md
  - scripts/analyze_data.py
  - scripts/capture_competition.py
  - scripts/competition_doc.py
  - scripts/cv_evidence.py
  - scripts/download_data.py
  - scripts/init_workspace.py
  - scripts/kaggle_gateway.py
  - scripts/safe_extract.py
  - scripts/templates/competition.md.tmpl
  - scripts/templates/config.json.tmpl
  - scripts/templates/gitignore.tmpl
  - scripts/templates/pyproject.toml.tmpl
  - scripts/templates/settings.json.tmpl
  - scripts/untrusted.py
  - tests/conftest.py
  - tests/cv_fixtures.py
  - tests/fixtures/pages_all.json
  - tests/test_capture.py
  - tests/test_competition_live.py
  - tests/test_cv_evidence.py
  - tests/test_egress_allowlist.py
  - tests/test_extract.py
  - tests/test_gate.py
  - tests/test_gateway.py
  - tests/test_limit_regex.py
  - tests/test_untrusted.py
findings:
  critical: 0
  warning: 5
  info: 5
  total: 10
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-07-10T16:23:11Z
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

This phase implements the competition-context/data slice: the untrusted-content fence
(`untrusted.py`), the zip-slip guard (`safe_extract.py`), the single Kaggle CLI gateway
(`kaggle_gateway.py`), the capture/download/analyze entry points, the CV-evidence engine,
and the egress allowlist. I reviewed all 27 files at standard depth with particular focus
on the five security-critical invariants this phase owns.

**The security-critical invariants are, on the whole, well-implemented and well-tested:**

- **Zip-slip guard (`safe_extract.py`)** validates every member (absolute/drive, `..`,
  symlink external_attr, and realpath-containment) *before* a single write, and raises
  rather than silently skipping. I could not construct a traversal that escapes `dest`.
- **Credential/token hygiene (`kaggle_gateway.py`, `download_data.py`)** never echoes the
  captured buffer; the raw output is quarantined to a gitignored `last-error.txt` and only
  framework-authored, secret-free messages reach the terminal. Verified by the leak tests.
- **Gate flow** probes exactly once, never sleeps/polls, and exits the reserved 77/78 codes.
- **No-derived-execution** holds even for the one ML step: the AV runner is a static source
  constant executed via `uv run`, and every subprocess argv is built from config/argv only —
  never from competition prose (the `_TAINT` test confirms the sentinel reaches no argv).
- **Egress allowlist** carries `api.kaggle.com` in both `settings.json.tmpl` and the
  reference doc.

No BLOCKER-level defect (security break, data loss, or crash-on-normal-input) was found.
The findings below are correctness/robustness degradations and quality issues — the most
impactful being inconsistent CLI-failure handling in `download_data.py` (WR-01) that can
send an operator into an unresolvable "accept-the-rules" loop when the real cause is a
missing CLI or a stalled egress.

## Structural Findings (fallow)

No `<structural_findings>` block was provided with this review; no structural pre-pass to
reconcile. All findings below are from direct (narrative) code review.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: `download_data.py` misclassifies a missing CLI (127) / timeout (124) as a UI gate

**File:** `scripts/download_data.py:169-179`
**Issue:** The download call handles *every* non-zero return code identically as an
unclassifiable 403:

```python
rc, combined = gw.run_kaggle("competitions", "download", slug, "-p", str(data_dir))
if rc != 0:
    dump_path = gw.dump_last_error(ws, combined)
    print(gw.classify_gate(combined, slug))   # names rules + phone URLs
    ...
    return gw.UI_GATE   # 77
```

But `run_kaggle` reserves `127` for "kaggle CLI not found on PATH" and `124` for
"kaggle timed out" (`kaggle_gateway.py:78-95`). The sibling script
`capture_competition._gateway_failure` (`capture_competition.py:215-231`) explicitly
branches on `127` and `124` with tailored messages ("install it…", "check the egress
allowlist…") and returns those codes. `download_data.py` does not — so:

- a **missing CLI** (127) is reported as "clear whichever UI-only gate applies in a browser"
  and exits `77`. The SKILL branches on `77` → tells the human to accept the rules → re-run
  → CLI still missing → `77` again → an unresolvable human loop.
- a **stalled off-allowlist egress** (124) is likewise reported as a rules/phone gate rather
  than "check the egress allowlist", losing the diagnostic capture's path preserves.

Note the earlier `entered = gw.preflight_entered(slug)` also returns `None` on a missing CLI
(rc 127 → indeterminate), so control falls through to the download call and this misreport.

**Fix:** Mirror `capture_competition._gateway_failure`'s 127/124 handling before the
fail-closed gate branch:

```python
if rc == 127:
    print("[BLOCKED] the kaggle CLI was not found on PATH. Install it "
          "(`uv pip install kaggle`) and re-run.", file=sys.stderr)
    return rc
if rc == 124:
    print("[BLOCKED] the kaggle CLI timed out (stalled/blocked egress). "
          "Check the egress allowlist and re-run.", file=sys.stderr)
    return rc
# else: unclassifiable 403 → fail closed as today
```

### WR-02: AV failure always reported as "ML env absent" even when the env is present but AV errored

**File:** `scripts/analyze_data.py:173-174` and `scripts/analyze_data.py:305-315`
**Issue:** Any non-zero return from the AV subprocess is collapsed to a single reason:

```python
if proc.returncode != 0:
    return {"status": "skipped", "reason": "ML env absent (uv run non-zero)"}
```

and `_av_section_skipped` then writes, unconditionally, *"SKIPPED (ML env absent; run
`uv sync`)"*. But the AV runner (`_AV_RUNNER_SRC`) can exit non-zero for reasons unrelated
to a missing env: `cross_val_predict(..., cv=5)` on a StratifiedKFold default fails when the
`__is_test__` label has a class with fewer than 5 rows (a tiny test set), among other runtime
errors. A user whose ML env is fully synced but whose test split is small will be told to run
`uv sync` — wrong remediation that will not fix the problem.

**Fix:** Distinguish "env/import failure" from "AV ran but raised". Capture the subprocess
stderr and surface a truncated, secret-free reason, or classify on an import-error signature
vs a runtime error, e.g.:

```python
if proc.returncode != 0:
    tail = (proc.stderr or "").strip().splitlines()[-1:] or ["non-zero exit"]
    reason = ("ML env absent (uv run could not import the stack)"
              if "ModuleNotFoundError" in (proc.stderr or "")
              else f"AV runner failed: {tail[0][:200]}")
    return {"status": "skipped", "reason": reason}
```

### WR-03: fence marker-escaping does not neutralize a `< /untrusted-content` (space-after-`<`) variant

**File:** `scripts/untrusted.py:36` and `scripts/untrusted.py:47-55`
**Issue:** The neutralizer regex is `</?\s*untrusted-content` — it allows whitespace *after*
an optional `/`, but not *between* `<` and `/`. So a lookalike of the form
`< /untrusted-content` (space immediately after `<`) does not match and is not escaped. This
is the one mechanical guarantee this module exists to provide, so a gap is worth recording.

Practical exploitability is low: in the capture pipeline `escape_markers` runs on
`strip_html(...)` output, and `strip_html`'s `<[^>]+>` tag regex removes the well-formed
`< /untrusted-content>` (with a closing `>`) as an HTML tag before escaping ever runs. The
residual case is an unterminated `< /untrusted-content` (no `>`), which is a weak fence
lookalike unlikely to be honored as a close tag — and the no-derived-execution invariant is
the real backstop. Still, the escaper should be complete on its own terms.

**Fix:** Broaden the regex to tolerate whitespace on both sides of the slash:

```python
_FENCE = re.compile(r"<\s*/?\s*untrusted-content", re.IGNORECASE)
```

(and keep replacing only the leading `<`).

### WR-04: `replace_section` boundary detection can be confused by untrusted prose that begins with `## `

**File:** `scripts/competition_doc.py:49-52` and `scripts/capture_competition.py:392-403`
**Issue:** `replace_section` finds a section's end with `lines[j].startswith("## ")`. The
document it parses embeds *untrusted competition prose* (the fenced Rules/Evaluation bodies).
If that prose, after `strip_html`, begins with the characters `## ` (reachable via e.g.
HTML-entity-encoded `&#35;&#35;` at the start of the rules text), the fenced line becomes a
spurious level-2 heading / structural boundary inside a document that is later re-read as a
*trusted* project doc (D-01). This is precisely the class of "untrusted content influencing
structure" that this phase guards against.

Practical impact is limited: `strip_html` collapses the body to a single line (so a full
injected multi-section block is not possible), and the section-*start* match is exact
(`line.rstrip("\n") == target`), so a body line cannot be mistaken for a real header start;
the observable effect is a cosmetic spurious sub-heading and a mildly misparsed boundary on
subsequent edits. Recording it as a defense-in-depth gap rather than an exploit.

**Fix:** Neutralize a leading `## ` in fenced untrusted bodies (the fence writer is the right
place), e.g. prefix-escape a body line that begins with `#` inside `wrap_untrusted`, or make
the boundary scan fence-aware (skip lines between `<untrusted-content …>` and
`</untrusted-content>`).

### WR-05: config.json that is valid JSON but not an object bypasses the fail-clear path and crashes

**File:** `scripts/init_workspace.py:509-516`, `scripts/capture_competition.py:272`, `scripts/analyze_data.py:380`
**Issue:** The fail-clear contract catches `json.JSONDecodeError` and preserves the file
byte-for-byte. But a file that is *valid JSON of the wrong type* (a top-level list or scalar,
e.g. `[]` or `"oops"`) parses cleanly and then hits an unguarded `.get()` / item assignment:

- `set_config_field`: `node = cfg; ... node.get(key)` → `AttributeError` if `cfg` is a list.
- `write_control_json` → `deep_merge_add_missing(current, desired)` → `current[key] = …` on a
  list → `TypeError`.
- `capture_competition.main:280` and `analyze_data.main:388` call `cfg.get("competition_slug")`
  directly.

`download_data.read_slug` and `read_credentials` correctly guard with
`isinstance(data, dict)`; the config writers/readers above do not, so a malformed-but-parseable
config raises an uncaught exception (a stack trace to the user) instead of the documented
fail-clear message.

**Fix:** After `json.loads`, assert the object shape and raise `MalformedControlJSON` (or print
the same fail-clear message) when it is not a `dict`:

```python
cfg = json.loads(config_path.read_text())
if not isinstance(cfg, dict):
    raise MalformedControlJSON(config_path, ...)   # or the fail-clear print + return 1
```

## Info

### IN-01: redundant / dead ternary in target derivation

**File:** `scripts/cv_evidence.py:293-295`
**Issue:** `target = target_candidates[0] if len(target_candidates) == 1 else (target_candidates[0] if target_candidates else None)`
— both the `len == 1` branch and the multi-candidate branch return `target_candidates[0]`, so
the whole expression is equivalent to `target_candidates[0] if target_candidates else None`.
The special-case is dead and obscures that a multi-column train/test diff silently picks the
first extra column as the target.
**Fix:** `target = target_candidates[0] if target_candidates else None` (and, if desired, log
when `len(target_candidates) > 1` since the choice is then a heuristic).

### IN-02: 8-digit integer columns can be mis-detected as datetime (contradicts the docstring)

**File:** `scripts/cv_evidence.py:90-109`
**Issue:** `_try_parse_date` claims "plain integers/floats (ids, numeric features) do NOT
parse," but on Python 3.11+ `datetime.fromisoformat("20200101")` succeeds (verified:
`datetime(2020, 1, 1)`), so a column of 8-digit integers would be classified as datetime and
could push `recommend_cv` toward `TimeSeriesSplit`. Narrow (needs ≥90% 8-digit values) but the
docstring's guarantee is inaccurate.
**Fix:** Reject purely-numeric tokens before the ISO attempt, e.g. `if s.isdigit(): return None`
(or require a date separator), and update the docstring.

### IN-03: reference docs disagree on the CLI API endpoint host

**File:** `references/kaggle-cli-behavior.md:29`
**Issue:** This line still states the validation command hits
`www.kaggle.com/api/v1/competitions/list`, while `references/egress-allowlist.md:47-49,232`
establishes (VERIFIED-LIVE, with a correction-history entry) that CLI 2.2.3 routes competition
RPCs to `api.kaggle.com`. Both hosts are allowlisted so there is no functional break, but the
two security references contradict each other.
**Fix:** Footnote or update line 29 to note that 2.2.3 targets `api.kaggle.com` (cross-ref the
egress-allowlist correction history).

### IN-04: `analyze_data.main` re-resolves the pair and unpacks without a None guard

**File:** `scripts/analyze_data.py:421-422`
**Issue:** `pair = cve.resolve_pair(ws / "data"); train_path, test_path = pair`. `pair` is only
guaranteed non-`None` because `evidence["status"] == "ok"` implies it resolved a moment earlier
in `write_evidence`; if the train/test files are removed between the two calls, `resolve_pair`
returns `None` and the tuple-unpack raises `TypeError` instead of degrading to SKIPPED. Also a
redundant second `resolve_pair` of the same directory.
**Fix:** Guard the re-resolve (`if pair is None: <SKIPPED path>`) or thread the already-resolved
pair out of `build_evidence`/`write_evidence` instead of resolving twice.

### IN-05: NUL-byte member name raises `ValueError` rather than the clean reject-and-raise

**File:** `scripts/safe_extract.py:76`
**Issue:** `os.path.realpath(os.path.join(dest_real, name))` raises `ValueError: embedded null
byte` for a member whose name contains `\x00`, so such a member aborts with `ValueError` rather
than the module's `UnsafeArchiveMember` contract. No extraction occurs (it still fails before
`extractall`), so this is not an escape — only a contract/consistency gap in the reject path.
**Fix:** Wrap the realpath/validation in a `try/except (ValueError, OSError)` that re-raises as
`UnsafeArchiveMember`, or explicitly reject names containing `"\x00"`.

---

_Reviewed: 2026-07-10T16:23:11Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
