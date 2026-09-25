---
phase: 02-competition-context-data
reviewed: 2026-07-11T09:30:00Z
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
  warning: 7
  info: 5
  total: 12
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-07-11T09:30:00Z
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Re-review at the post-gap-closure state (the single Kaggle gateway, the
capture/download/analyze entry points, the zip-slip extractor, the untrusted-content
fence, the section-merge helper, and the egress allowlist). A prior REVIEW.md flagged
`download_data.py` collapsing every non-zero download rc into a UI-gate misreport;
that is now FIXED — `download_data.py:178-191` branches on `127`/`124` before the
fail-closed 403 path, matching `capture_competition._gateway_failure`. That stale
finding is dropped.

The security core remains strong and I could not break it. `safe_extract.py` rejects
absolute/drive paths, `..` traversal, symlink members, and realpath-escaping members
BEFORE any write, so a malicious archive leaves the tree untouched (confirmed by
`test_extract.py` and by manual probing). The no-derived-execution invariant holds:
every `subprocess.run` uses list args, never `shell=True`, and no argv is built from
page prose (the `_TAINT` test confirms the sentinel reaches no subprocess). Token-
shaped output is quarantined to a gitignored `last-error.txt` and never echoed. The
full non-live suite passes (90 passed, 8 live deselected).

No BLOCKER-level defect (security break, data loss, crash on well-formed input) was
found. The findings below are correctness/robustness gaps that survive the current
tests because those tests use clean, complete fixtures — real Kaggle data is
missing-value-laden and its rules prose is messier. The two most impactful (WR-04,
WR-05) can put silently-wrong operator-facing state (a wrong gate verdict, a wrong
submission limit) into the workspace.

## Structural Findings (fallow)

No `<structural_findings>` block was provided with this review; there is no structural
pre-pass to reconcile. All findings below are from direct (narrative) code review.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: A valid-JSON-but-not-object `config.json` crashes the fail-clear path instead of failing clear

**File:** `scripts/init_workspace.py:499-516`, `scripts/capture_competition.py:271-283`, `scripts/analyze_data.py:405-414`
**Issue:** The fail-clear contract catches `json.JSONDecodeError` and preserves the
file byte-for-byte. But a file that is *valid JSON of the wrong type* (`[]`, `"oops"`,
`42`) parses cleanly and then hits unguarded dict operations. Verified live:
`set_config_field(cp, ("cv","scheme"), "KFold")` on a config containing `[]` raises
`AttributeError: 'list' object has no attribute 'get'` (from `node = cfg; node.get(key)`
at `init_workspace.py:511`). The same shape crashes `write_control_json` →
`deep_merge_add_missing(current, desired)` (`current[key] = …` on a list → `TypeError`)
and `capture_competition.main` / `analyze_data.main`, which call
`cfg.get("competition_slug")` directly. `download_data.read_slug`/`read_credentials`
correctly guard with `isinstance(data, dict)`; the config writers/readers above do not,
so a malformed-but-parseable config produces a raw stack trace to the user instead of
the documented fail-clear message.
**Fix:** Assert the object shape right after every `json.loads` of a control-plane file:
```python
cfg = json.loads(config_path.read_text())
if not isinstance(cfg, dict):
    raise MalformedControlJSON(config_path, ...)   # or the fail-clear print + return 1
```

### WR-02: AV subprocess non-zero is always reported as "ML env absent", misdirecting a synced user

**File:** `scripts/analyze_data.py:175-176`, `scripts/analyze_data.py:329-339`
**Issue:** Any non-zero return from the AV runner collapses to one reason:
`return {"status": "skipped", "reason": "ML env absent (uv run non-zero)"}`, and
`_av_section_skipped` then writes, unconditionally, *"SKIPPED (ML env absent; run
`uv sync`)"*. But `_AV_RUNNER_SRC` can exit non-zero with a fully-synced env — e.g.
`cross_val_predict(..., cv=5)` fails when the `__is_test__` label has a class with
fewer than 5 rows (a small test set), or any other runtime error. A user whose env is
present but whose split is small is told to run `uv sync`, which will not fix it.
**Fix:** Distinguish an import/env failure from a runtime failure by inspecting the
subprocess stderr (already captured), surfacing a truncated secret-free reason:
```python
if proc.returncode != 0:
    err = proc.stderr or ""
    reason = ("ML env absent (uv run could not import the stack)"
              if "ModuleNotFoundError" in err
              else f"AV runner failed: {(err.strip().splitlines()[-1:] or ['non-zero exit'])[0][:200]}")
    return {"status": "skipped", "reason": reason}
```

### WR-03: `escape_markers` does not neutralize the `< /untrusted-content` (space-before-slash) variant

**File:** `scripts/untrusted.py:36,47-55`
**Issue:** `_FENCE = re.compile(r"</?\s*untrusted-content", re.IGNORECASE)` allows
whitespace only AFTER the optional `/`, not between `<` and `/`. Verified: both
`< /untrusted-content>` and `<  /untrusted-content>` pass through unescaped (the
leading `<` survives). The docstring claims it neutralises "case / tag / whitespace /
attribute variants," and `test_fence_cannot_be_broken` only exercises
`</ untrusted-content>` (slash-then-space), so this gap is untested. Exploitability is
low (in the capture pipeline `strip_html`'s `<[^>]+>` removes a well-formed
`< /untrusted-content>` as a tag before escaping runs, and no-derived-execution is the
real backstop), but this is the one mechanical guarantee the module exists to provide.
**Fix:** Tolerate whitespace on both sides of the slash:
```python
_FENCE = re.compile(r"<\s*/?\s*untrusted-content", re.IGNORECASE)
```
and add the space-before-slash payloads to `test_fence_cannot_be_broken`.

### WR-04: `preflight_entered` conflates a missing/null `userHasEntered` with an explicit `false`

**File:** `scripts/kaggle_gateway.py:153-158`
**Issue:** The exact-slug branch returns `bool(row.get("userHasEntered"))`. A row for
the exact slug that omits the field (or sets it `null`) yields `bool(None) == False` —
indistinguishable from an explicit `false`. In `download_data.main:157-165` a `False`
prints the rules-acceptance URL and exits `UI_GATE` (77); the SKILL then tells the
human to accept rules, they re-run, and the preflight returns `False` again — an
unresolvable loop for an already-entered competition. `None` (indeterminate) is the
value the design reserves for exactly this "can't tell" case, but it is collapsed to
`False` here. (Fails closed — no leak — so this is a functional dead-end, not a
security hole; the risk is conditional on the CLI omitting the field.)
**Fix:**
```python
val = row.get("userHasEntered")
if isinstance(val, bool):
    return val
return None   # absent / unexpected type → indeterminate; caller fails closed (D-12)
```

### WR-05: `extract_daily_limit` records the first "N … per day" match authoritatively when several appear

**File:** `scripts/capture_competition.py:80,103-111`
**Issue:** `_LIMIT_RE.search(...)` returns the FIRST
`(\d+)\s+(?:entries|submissions)\s+per\s+day` hit and tags it `provenance="extracted"`.
Rules that phrase a ramped or multi-clause limit ("2 entries per day for the first
week, then 5 entries per day") land the wrong number as if authoritatively extracted.
This value feeds submission-budget rationing (a first-class project concern), so a
silently-wrong `daily_limit` can push the operator past the real cap. The tests only
cover a single-figure page.
**Fix:** Only trust an unambiguous extraction; otherwise fall through to the
`LIMIT_NEEDS_USER` prompt:
```python
figures = {int(m.group(1)) for m in _LIMIT_RE.finditer(strip_html(rules_text))}
return figures.pop() if len(figures) == 1 else None
```

### WR-06: `marginal_shift_report` drops any numeric column that has a single missing/non-float cell

**File:** `scripts/analyze_data.py:207-215`
**Issue:** `_means` returns `None` for a column the moment one value fails `float(v)` —
and an empty string (a missing cell) fails `float("")`. Real Kaggle numeric columns
routinely have missing values (Titanic `Age`, `Fare`), so the stdlib marginal-shift
fallback — the report that runs precisely when the ML env is absent and real AV is
SKIPPED — silently omits most numeric features and often emits
`"(no numeric feature columns to compare.)"` even on a fully numeric frame. The weaker
fallback is weaker than intended in the exact case it exists to cover.
**Fix:** Skip only the non-parseable cells, not the whole column:
```python
def _means(rows, col):
    nums = []
    for r in rows:
        v = str(r.get(col, "")).strip()
        if v == "":
            continue
        try:
            nums.append(float(v))
        except ValueError:
            return None   # a genuinely non-numeric token → not a numeric column
    return sum(nums) / len(nums) if nums else None
```

### WR-07: `replace_section` boundary detection can be nudged by untrusted prose beginning with `## `

**File:** `scripts/competition_doc.py:49-52`, `scripts/capture_competition.py:392-403`
**Issue:** `replace_section` ends a section at the next line where
`lines[j].startswith("## ")`. The parsed document embeds *untrusted competition prose*
(the fenced Rules/Evaluation bodies). If that prose, after `strip_html`, begins with
`## ` (reachable via HTML-entity-encoded `&#35;&#35;`, which `strip_html` unescapes),
the fenced line reads as a spurious level-2 boundary inside a doc later re-read as a
*trusted* project doc (D-01) — the "untrusted content influencing structure" class this
phase guards against. Impact is limited (`strip_html` collapses the body to one line, so
no multi-section injection, and section *starts* are matched exactly), so the observable
effect is a cosmetic spurious sub-heading / mildly misparsed boundary on later edits —
recorded as a defense-in-depth gap.
**Fix:** Neutralize a leading `#` inside `wrap_untrusted` bodies, or make the boundary
scan fence-aware (skip lines between `<untrusted-content …>` and `</untrusted-content>`).

## Info

### IN-01: Redundant / dead ternary in target derivation

**File:** `scripts/cv_evidence.py:367-370`
**Issue:** `target = target_candidates[0] if len(target_candidates) == 1 else (target_candidates[0] if target_candidates else None)` —
both non-empty branches return `target_candidates[0]`, so the special-case is dead. The
convolution hides that a multi-column train/test diff silently picks the first extra
column as the target.
**Fix:** `target = target_candidates[0] if target_candidates else None` (and log when
`len(target_candidates) > 1`, since the choice is then a heuristic worth surfacing).

### IN-02: 8-digit integer columns can be mis-detected as datetime, contradicting the docstring

**File:** `scripts/cv_evidence.py:106-125,132-142`
**Issue:** `_try_parse_date` claims "plain integers/floats (ids, numeric features) do
NOT parse," but on Python 3.11+ `datetime.fromisoformat("20200101")` succeeds (verified
→ `2020-01-01`). A column of 8-digit integers (some id encodings) would then be
classified datetime and could push `recommend_cv` toward `TimeSeriesSplit`. Narrow
(needs ≥90% 8-digit values) but the docstring's guarantee is inaccurate.
**Fix:** Reject purely-numeric tokens before the ISO attempt (`if s.isdigit(): return None`,
or require a date separator) and correct the docstring.

### IN-03: Reference docs disagree on the CLI API endpoint host

**File:** `references/kaggle-cli-behavior.md:29`
**Issue:** Line 29 still states the validation command hits
`www.kaggle.com/api/v1/competitions/list`, while `references/egress-allowlist.md:47-49,232`
establishes (VERIFIED-LIVE, with a correction-history entry) that CLI 2.2.3 routes
competition RPCs to `api.kaggle.com`. Both hosts are allowlisted so nothing breaks, but
two security references contradict each other.
**Fix:** Footnote/update line 29 to note 2.2.3 targets `api.kaggle.com` (cross-ref the
egress-allowlist correction history).

### IN-04: `analyze_data.main` re-resolves the pair and unpacks without a None guard

**File:** `scripts/analyze_data.py:447-448`
**Issue:** `pair = cve.resolve_pair(ws / "data"); train_path, test_path = pair`. `pair`
is non-`None` only because `evidence["status"] == "ok"` implied a resolve moments earlier
in `write_evidence`; if the files vanish between the two calls, `resolve_pair` returns
`None` and the tuple-unpack raises `TypeError` instead of degrading to SKIPPED. Also a
redundant second resolve of the same directory.
**Fix:** Guard the re-resolve (`if pair is None: <SKIPPED path>`), or thread the
already-resolved pair out of `build_evidence`/`write_evidence`.

### IN-05: NUL-byte member name raises `ValueError` instead of the clean reject-and-raise

**File:** `scripts/safe_extract.py:76`
**Issue:** `os.path.realpath(os.path.join(dest_real, name))` raises
`ValueError: embedded null byte` for a member whose name contains `\x00`, so such a
member aborts with `ValueError` rather than the module's `UnsafeArchiveMember` contract.
It still fails before `extractall` (no escape), so this is a contract/consistency gap in
the reject path, not a vulnerability.
**Fix:** Wrap the validation in `try/except (ValueError, OSError)` re-raising as
`UnsafeArchiveMember`, or reject names containing `"\x00"` explicitly.

---

_Reviewed: 2026-07-11T09:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
