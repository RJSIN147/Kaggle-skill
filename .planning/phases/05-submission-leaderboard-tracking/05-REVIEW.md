---
phase: 05-submission-leaderboard-tracking
reviewed: 2026-07-12T00:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - SKILL.md
  - references/kaggle-cli-behavior.md
  - scripts/check_submission.py
  - scripts/fetch_lb.py
  - scripts/kaggle_gateway.py
  - scripts/lb_gap.py
  - scripts/poll_kernel.py
  - scripts/regen_strategy.py
  - scripts/scaffold_experiment.py
  - scripts/submission_gate.py
  - scripts/submissions_log.py
  - scripts/submit.py
  - scripts/templates/config.json.tmpl
  - scripts/templates/experiment.py.tmpl
  - scripts/templates/gitignore.tmpl
  - scripts/templates/strategy.md.tmpl
  - tests/test_budget.py
  - tests/test_check_submission.py
  - tests/test_fetch_lb.py
  - tests/test_gate_policy.py
  - tests/test_lb_gap.py
  - tests/test_no_credential_leak.py
  - tests/test_regen_strategy.py
  - tests/test_run_cv.py
  - tests/test_submission_live.py
  - tests/test_submissions_log.py
  - tests/test_submit.py
findings:
  critical: 3
  warning: 11
  info: 0
  total: 14
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-07-12
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

The slot-safety core is largely well built: the fail-open exit-code posture, read-back
confirmation, PENDING-before-poll write ordering, the injected-clock UTC budget count, the
`math.isclose` IEEE-754 guard, and the no-echo credential quarantine all hold up under trace.
I verified the two headline claims empirically:

- `submission_gate.is_meaningful(0.81, 0.01, 0.80, True)` → `False`. The `math.isclose` guard
  is correct, and it is applied at the *only* site the strict-inequality comparison occurs
  (`submission_gate.py:133`). No other module re-derives the comparison. **Confirmed sound.**
- `charged_today` → `-1` → `remaining_slots` → `None` → `decide` → `BLOCKED`. The sentinel does
  not leak into arithmetic and `None` is not read as permissive. **Confirmed sound** at the
  exit-code level (but see WR-02 for what the *renderer* then does with it).

Three defects nevertheless reach the irreversible surface:

1. **The double-spend guard is defeated by the framework's own recovery path.** After
   `fetch_lb.py --reconcile` — the command `submit.py` itself tells the user to run when a
   read-back fails and a slot *may already be spent* — the back-filled row carries
   `file_sha256: null`, so `_refuse_double_spend` no longer matches. The guard fails precisely
   in the scenario it exists for. Reproduced in-process.
2. **`submit.py` never validates the CSV against the sample**, despite `SKILL.md` documenting
   exit 65 (sample mismatch) as a `submit.py` outcome. Nothing mechanical stops an unvalidated
   file from being uploaded.
3. **`check_submission` clears a submission whose CV is missing.** A first submission with a
   non-numeric `cv_mean` renders `CV: None +/- None` and exits `0 — CLEAR to submit`.

The known `submissions_log.fetch_submissions()` binding hazard is real, but it is a symptom of
a broader defect: the `competitions submissions` argv is now constructed in **four** places
across three modules, and the module that owns the schema owns a copy that has zero callers.

---

## Critical Issues

### CR-01: `--reconcile` silently disarms the double-spend guard — a second slot can be spent on the same file

**File:** `scripts/submit.py:184-197`, `scripts/fetch_lb.py:479-493`
**Severity:** BLOCKER (irreversible double-spend)

`_refuse_double_spend` requires **all three** of `exp_id`, `file_sha256` and `status != FAILED`
to match:

```python
if (
    row.get("exp_id") == exp_id
    and row.get("file_sha256") == digest      # <-- None for every reconciled row
    and row.get("status") != "FAILED"
):
```

`fetch_lb._row_from_kaggle` deliberately writes `file=None, file_sha256=None` (correctly — the
bytes of an out-of-band submission are genuinely unknown). So **any row that arrived via
`--reconcile` can never satisfy the guard**, and a re-run of `submit.py --confirm` sails past it
and spends a second slot.

This is not a theoretical path. It is *the documented recovery path*. `submit.py:319-327`, on a
failed read-back, prints:

> "A slot MAY still have been spent. … if the submission is there, run `fetch_lb.py --reconcile`
> to back-fill it."

The user reconciles, the row lands with a null hash, and the next `submit.py --confirm` (which
the SKILL's exit-75 loop makes an ordinary next step) double-spends. Reproduced in-process:

```
reconciled row: {"exp_id": "exp-007", "kaggle_ref": 46780678, "file_sha256": null,
                 "status": "SCORED", "public_score": 0.77511, ...}
double-spend guard fires? False
```

`tests/test_refuses_double_spend` only exercises a row written by `submit.py` itself (which does
carry the hash), so the suite is green on a guard that has a hole in the exact case it protects.

**Fix:** treat a hash-less row as an *unknown-bytes* match, not a non-match. Block on `exp_id`
alone when the recorded hash is absent, and make the user's escape explicit:

```python
def _refuse_double_spend(ws: Path, exp_id: str, digest: str) -> tuple[bool, str]:
    """(refuse, why). A row with NO recorded hash (an out-of-band/reconciled submission)
    matches on exp_id ALONE: we cannot prove the bytes differ, and the cost of being wrong
    is an irreversible slot."""
    for row in read_rows(ws):
        if row.get("exp_id") != exp_id or row.get("status") == "FAILED":
            continue
        recorded = row.get("file_sha256")
        if recorded == digest:
            return True, "these exact bytes were already submitted for this experiment"
        if recorded is None:
            return True, (
                f"{exp_id} already has a non-FAILED submission (kaggle_ref "
                f"{row.get('kaggle_ref')}) whose file hash was never recorded (it was "
                "back-filled by --reconcile). The bytes cannot be proven different, so a "
                "re-submit is REFUSED rather than risk a double-spend. Use --resubmit to "
                "deliberately spend another slot."
            )
    return False, ""
```

Add a regression test that reconciles a row and then asserts `submit.py --confirm` refuses.

---

### CR-02: `submit.py` never validates `submission.csv` against the sample — `SKILL.md` claims it does

**File:** `scripts/submit.py:170-181`, `SKILL.md:188-191`, `scripts/submit.py:56` (docstring)
**Severity:** BLOCKER (a slot can be spent on a structurally invalid file)

`submit.py` is the only module that spends the irreversible resource, and its entire file check is:

```python
csv_path = exp_dir / SUBMISSION_CSV
if not csv_path.is_file():
    ...
    return VALIDATION_FAILED
```

It checks **existence**. It never compares the header, the row count, the id set, or blank/NaN
cells against the competition's reference file. All of that lives in
`check_submission.validate_submission`, which `submit.py` does not import and does not call.

`SKILL.md:188-191` documents the opposite:

> "**Exit 65 (`VALIDATION_FAILED`)** from `check_submission.py` / `submit.py`: `submission.csv`
> does not match the competition's sample. … **Never submit an unvalidated file.**"

`submit.py` cannot produce that outcome; its 65s are only "file missing", "bad exp-id shape",
and "path escape". `submit.py`'s own docstring line 56 likewise claims 65 means "missing **or
unusable**". The "never submit an unvalidated file" invariant is enforced only by prose in
`SKILL.md` — i.e. by the agent remembering to run `check_submission.py` first. Every other
irreversible invariant in this phase (type refusal, TOCTOU, double-spend, confirm) is enforced
mechanically *inside* `submit.py`. This one is not.

The failure is not free even though Kaggle does not charge processing errors (D-13): a
header/id-set mismatch is frequently *scored*, not errored — a wrong-but-parseable file burns a
real slot and lands a garbage score on the board.

**Fix:** re-run the D-02 validation inside `submit.py`, immediately before the TOCTOU re-hash.
The functions are already pure and importable:

```python
from check_submission import _resolve_reference, validate_submission  # noqa: E402

ref = _resolve_reference(ws)
if ref is None:
    print("REFUSING to submit: nothing to validate submission.csv against "
          "(no reference file under data/). An unvalidated file is never submitted.",
          file=sys.stderr)
    return VALIDATION_FAILED
reason, message = validate_submission(csv_path, ref)
if reason is not None:
    print(f"REFUSING to submit [{reason}]: {message}\n"
          "No slot was spent. Fix the harness, re-run the experiment, then re-check.",
          file=sys.stderr)
    return VALIDATION_FAILED
```

(If the cross-import is unwanted, lift `_resolve_reference` / `validate_submission` into a shared
`submission_file.py` — the same move `submissions_log.py` already makes for the schema.)

---

### CR-03: a first submission with a missing/non-numeric CV is rendered "CLEAR to submit"

**File:** `scripts/submission_gate.py:116-118`, `scripts/check_submission.py:689-756`
**Severity:** BLOCKER (fail-open in the module whose sole job is to protect the slot)

`is_meaningful` short-circuits on `best_cv is None` **before** it validates anything else:

```python
# The baseline case, checked FIRST: an empty comparison set is always clear.
if best_cv is None:
    return True
candidate = _as_number(cand_cv)   # never reached on the first submission
```

So when nothing has been submitted yet, a candidate with `cand_cv=None` (a ledger `SUCCESS` row
whose `cv_mean` is absent, `null`, or a string) is declared meaningful. Verified in-process:

```
first-submission, cand_cv=None -> SUBMIT requires_confirmation=False CLEAR=True
```

`check_submission.main` then prints `CV: None +/- None`, `RECOMMENDATION: SUBMIT`,
`CLEAR to submit.` and returns **exit 0**. Per `SKILL.md`, exit 0 means "clear to submit" and the
skill proceeds — a slot is spent on an experiment whose CV the framework could not read. That is
the exact "confident-but-wrong" arithmetic the module docstring says it fails closed against, and
it defeats SCORE-02's "CV is the decision metric" (there is no CV).

The empty-comparison-set rule is correct; it is only the **ordering** that is wrong. Garbage input
must be rejected before the baseline shortcut.

**Fix (`submission_gate.py`):**

```python
def is_meaningful(cand_cv, cand_std, best_cv, greater_is_better, k=NOISE_K_DEFAULT) -> bool:
    candidate = _as_number(cand_cv)
    if candidate is None:
        return False  # no readable CV => nothing to reason about => fail closed.

    # The baseline case: an empty comparison set is always clear.
    if best_cv is None:
        return True

    baseline = _as_number(best_cv)
    std = _as_number(cand_std)
    ...
```

and give `decide()` a matching explicit reason so the human sees *why*:

```python
if _as_number(cand_cv) is None:
    reasons.append(
        f"BLOCKED: this experiment has no readable CV score (cv_mean={cand_cv!r}). "
        "CV is the decision metric — a slot is never spent on a number we cannot read."
    )
    return {"recommendation": "BLOCKED", "reasons": reasons, "warnings": warnings,
            "requires_confirmation": False}
```

Add a `test_gate_policy.py` case: `decide(cand_cv=None, best_cv=None, remaining=5, ...)` must be
`BLOCKED`.

---

## Warnings

### WR-01: the `competitions submissions` argv is built in four places; the schema owner's copy has zero callers and mis-binds `run_kaggle`

**File:** `scripts/submissions_log.py:347-372`, `scripts/check_submission.py:416-460`,
`scripts/fetch_lb.py:117-136`, `scripts/submit.py:391-401`

Confirmed by grep: `submissions_log.fetch_submissions()` is referenced **only** by
`tests/test_budget.py`. No production code calls it. Its hazard is real — it resolves `run_kaggle`
from its own module globals, so a caller who monkeypatches `run_kaggle` on the *importing* module
is silently bypassed and the real CLI shells out from inside a supposedly-mocked test.

But the *severity* is not "a latent trap in one dead function". It is that the module which
`submissions_log.py:5-8` declares to be "the ONE source … never re-derived per caller" now has the
same argv re-derived **three more times**:

| Site | Binding | Callers |
|------|---------|---------|
| `submissions_log.fetch_submissions` | own module globals (the trap) | **0** |
| `check_submission.fetch_submissions` | own module globals | 1 |
| `fetch_lb.read_submissions(runner=…)` | **injectable** — the correct shape | 2 |
| `submit.read_status_payload` | own module globals | 1 (poll ticks) |

The other functions in `submissions_log.py` do **not** share the hazard — they are pure
(`parse_status`, `parse_score`, `parse_utc`, `charged_today`, `remaining_slots`,
`find_by_exp_id`) or take an explicit `ws` — so the binding trap is confined to
`fetch_submissions`. `check_submission.fetch_submissions` and `submit.read_status_payload` have
the same *shape* but are safe because their tests patch them in their own module (and the
docstrings say so).

**Fix:** delete `submissions_log.fetch_submissions` and repoint `tests/test_budget.py` at
`fetch_lb.read_submissions(slug, runner=fake)`. Have `check_submission` and `submit` call
`fetch_lb.read_submissions(..., runner=run_kaggle)` too, so the argv exists once. Remove the
`references/kaggle-cli-behavior.md:277-285` footgun note along with the footgun.

---

### WR-02: a fail-closed budget block is rendered to the human as an ordinary, overridable recommendation

**File:** `scripts/check_submission.py:736-754`, `scripts/submission_gate.py:199-204`
**Related:** `scripts/submit.py` has no budget check of any kind

`submission_gate.decide` carefully distinguishes two BLOCKED states:

- `remaining is None` (unknowable — the `-1` sentinel) → `requires_confirmation: False`, with the
  explicit rationale *"there is nothing coherent to confirm, because we do not know what we would
  be confirming."*
- within-noise CV gain → `requires_confirmation: True` (a real, informed human override).

`check_submission.main` then **discards that distinction**. `requires_confirmation` only feeds the
`clear` boolean (which is `False` for both, since `recommendation == "BLOCKED"`), and both states
render the identical footer:

```python
print("This is a RECOMMENDATION, not a refusal (D-05) — you make the call. To override and submit anyway:")
print(f'  python3 scripts/submit.py --workspace {ws} --exp-id {exp_id} --confirm ...')
```

So when Kaggle's submission list is unfetchable, or a row carries an unparseable status/date, the
framework prints a copy-pasteable command to spend a slot it just said it could not account for —
and `submit.py` will execute it, because `submit.py` never re-reads the budget. The `-1` sentinel
never reaches arithmetic (good), but the *fail-closed posture it encodes* is not surfaced.

(Note: an **exhausted** budget being overridable *is* by design — `SKILL.md:192-198` lists it as an
exit-75 human-decision case. The **unknowable** budget is different, and the gate module says so.)

**Fix:** branch the footer on `requires_confirmation`:

```python
if clear:
    print("CLEAR to submit. To spend the slot:")
elif verdict["requires_confirmation"]:
    print("This is a RECOMMENDATION, not a refusal (D-05) — you make the call. "
          "To override and submit anyway:")
    print(f'  python3 scripts/submit.py --workspace {ws} --exp-id {exp_id} --confirm ...')
else:
    print("BLOCKED and NOT overridable from here: the budget could not be established, so "
          "there is nothing coherent to confirm. Fix the underlying read "
          "(credentials / network / an unparseable Kaggle row) and re-run this check.")
```

and give `submit.py` a budget re-check of its own so the spend path does not depend on the caller
having run the gate.

---

### WR-03: `check_submission` maps **every** non-zero CLI exit to `UI_GATE` (77) — an auth failure is reported as "accept the rules / verify your phone"

**File:** `scripts/check_submission.py:445-455`

```python
if rc != 0:
    # A 403 / gate response.
    dump_path = dump_last_error(ws, out)
    print(classify_gate(out, slug), file=sys.stderr)
    ...
    return None, UI_GATE
```

There is no 403 test. A 401 (`HTTPError` → exit 1 per `references/kaggle-cli-behavior.md:225`), a
network blip, or any 5xx all land here and are handed to `classify_gate`, which then makes a
*second* live Kaggle call (`preflight_entered`) and prints the rules-URL / phone-URL remediation.
`submit.py:276` gets this right — it guards with `if "403" in payload or "forbidden" in payload.lower()`
before reaching for `classify_gate`. `check_submission` does not, so the two scripts classify the
same CLI failure differently.

**Fix:** mirror `submit.py`'s guard.

```python
if rc != 0:
    dump_path = dump_last_error(ws, out)
    if "403" in out or "forbidden" in out.lower():
        print(classify_gate(out, slug), file=sys.stderr)
        print(f"  (raw CLI output quarantined to {dump_path.relative_to(ws)})", file=sys.stderr)
        return None, UI_GATE
    print(f"cannot check the budget: the kaggle CLI failed (exit {rc}). The raw output is "
          f"withheld (it can carry a secret) and quarantined to {dump_path.relative_to(ws)}. "
          "Check your credentials (check_credentials.py) and the network, then re-run.",
          file=sys.stderr)
    return None, None   # rows=None => charged=-1 => remaining=None => BLOCKED (fail closed)
```

---

### WR-04: `submissions_log.validate_row` has zero callers, and the rows `fetch_lb` writes would fail it

**File:** `scripts/submissions_log.py:242-273`, `scripts/fetch_lb.py:479-493`

`validate_row` is defined, documented as the `experiment_meta.validate_meta` contract, and never
invoked anywhere in `scripts/`. It is not merely dead — it *disagrees* with the code that writes
rows. Verified in-process on a reconciled row:

```
validate_row(reconciled) -> ['required key must not be empty: file']
```

`REQUIRED_NONEMPTY_KEYS` includes `exp_id` and `file`, but `_row_from_kaggle` legitimately writes
both as `None` for an out-of-band submission. So the schema validator, if it were ever wired up as
written, would reject rows the schema owner's sibling module deliberately produces.

**Fix:** either (a) wire it into `append_row` / `write_rows` and relax `REQUIRED_NONEMPTY_KEYS` to
`("kaggle_ref", "competition_slug", "submitted_at", "status")` (the keys that are genuinely always
knowable), or (b) delete it. Leaving an unenforced, wrong schema contract in the module that
claims to own the schema is the worst of the three options.

---

### WR-05: the Kaggle `ref` recovered from the read-back is never validated; a `None` ref corrupts `upsert_row`

**File:** `scripts/submit.py:330-350`

```python
ref = confirmed.get("ref")     # never checked
append_row(ws, new_row(..., kaggle_ref=ref, ...))
...
select=lambda krows: by_ref(krows, ref)
```

If Kaggle's row lacks `ref` (or ships `null`), `submit.py` writes a row with `kaggle_ref: null` —
which `validate_row` would reject (WR-04) and which `fetch_lb._resume:408-415` can never resume
("it carries no kaggle_ref"). Worse, `by_ref(rows, None)` matches the *first* row whose `ref` is
`None`, and `upsert_row(ws, None)` (`submissions_log.py:494`) updates **every** local row whose
`kaggle_ref` is `None` — a mass mis-transition. Every other Kaggle-authored field in this phase is
treated as untrusted; `ref` is not.

**Fix:**

```python
ref = confirmed.get("ref")
if not isinstance(ref, int):
    print(
        f"CANNOT RECORD the submission for {exp_id}: the read-back row carries no usable "
        f"Kaggle ref ({ref!r}). The slot WAS likely spent. Run `fetch_lb.py --reconcile` to "
        f"back-fill it from Kaggle: {submissions_url(slug)}",
        file=sys.stderr,
    )
    return EXIT_TRANSIENT_FAIL
```

and guard `upsert_row` against a `None` key (`if kaggle_ref is None: raise ValueError(...)`).

---

### WR-06: `charged_today` fails closed on **any** row in the 200-row page, including rows that cannot affect today

**File:** `scripts/submissions_log.py:310-329`

The status parse runs *before* the date parse, so a single historical row with an unrecognized
status literal (a future Kaggle enum, a legacy value) returns `-1` — permanently. Since
`--page-size 200` returns the whole recent history, one such row blocks the budget count for that
competition on every subsequent day, forever, with no non-override escape.

The stated rationale ("skipping would UNDERCOUNT") only holds for rows that *could* be today's. A
row whose **date** parses cleanly to a past day cannot change today's count regardless of its
status.

**Fix:** parse the date first; only fail closed on an unparseable status for a row that is (or may
be) today.

```python
for row in rows:
    if not isinstance(row, dict):
        return COUNT_UNAVAILABLE
    ts = parse_utc(row.get("date"))
    if ts is None:
        return COUNT_UNAVAILABLE      # an unknowable DAY is always fatal
    if ts.date() != today:
        continue                      # a past row cannot change today's count
    status = parse_status(row.get("status"))
    if status is None:
        return COUNT_UNAVAILABLE      # an unknowable TODAY row IS fatal
    if status == "FAILED":
        continue                      # D-13 — never charged
    count += 1
```

This preserves the fail-closed guarantee exactly where it matters and removes the permanent-brick
mode. Update the `test_budget.py::test_fails_closed_when_count_unavailable` fixtures accordingly
(the unknown-status row there is dated *today*, so it still fails closed).

---

### WR-07: the slot-safety source guard matches three exact literal spellings and is trivially evaded

**File:** `tests/test_submit.py:537-561`

```python
if (
    "competitions submit" in src
    or '"competitions", "submit"' in src
    or "'competitions', 'submit'" in src
):
```

This is the *only* mechanical guarantee that no live test can spend a real slot. It is a substring
match on three formattings. `run_kaggle("competitions","submit", ...)` (no space after the comma),
a line-wrapped argv, `run_kaggle(*SUBMIT_ARGV)`, or `run_kaggle("competitions", SUBCMD)` all pass
it. `ruff format` changing quote style would also silently narrow it.

**Fix:** normalize before matching, and additionally forbid the bare token in any argv-looking
position:

```python
import re
_SUBMIT = re.compile(r"""["']competitions["']\s*,\s*["']submit["']|competitions\s+submit""")
for path in live_files:
    src = path.read_text()
    if _SUBMIT.search(src) or re.search(r'["\']submit["\']', src):
        offenders.append(path.name)
```

(The second clause is deliberately blunt — a live test has no legitimate reason to contain the
string `"submit"` at all.)

---

### WR-08: `lb_gap.alarm_body` de-duplicates by `exp_id`, so a re-submitted experiment prints numbers that disagree with the inversion it detected

**File:** `scripts/lb_gap.py:203-220`

`join_cv_lb` correctly emits **one row per scored submission** ("MANY SUBMISSIONS PER EXPERIMENT
are handled naturally"). `to_pairs` preserves that. But `alarm_body` then collapses them:

```python
lookup = {i: (cv, lb) for i, cv, lb in pairs}   # last write wins
```

With two scored submissions of `exp-007` (LB 0.75, then LB 0.70) and one of `exp-008`,
`rank_inversions` may fire on the (cv, 0.75) pair while `lookup["exp-007"]` returns 0.70. The
rendered line then names an LB score and a `Δlb` that do not correspond to the pair that actually
inverted — a fabricated-looking number in the one section whose whole premise is
"TOOLING-WRITTEN, the AI can never fabricate an LB score".

**Fix:** have `rank_inversions` return the four scores it compared, rather than re-looking them up:

```python
inversions.append((b_id, a_id, abs(b_cv - a_cv), abs(a_lb - b_lb), (b_cv, b_lb), (a_cv, a_lb)))
```

and render from the tuple. Alternatively, key the pairs on `kaggle_ref` (unique) and carry the
`exp_id` as a label.

---

### WR-09: unguarded CSV reads outside `validate_submission`'s try block

**File:** `scripts/check_submission.py:197-205` (`_read_csv`), called from `_resolve_reference:246`
and `:259`, and from `label_trap_warning:395`

`validate_submission` wraps `_read_csv` in `except (OSError, UnicodeDecodeError, csv.Error)`. The
three other call sites do not. A reference file with a NUL byte (`csv.Error: line contains NUL`), a
non-UTF-8 encoding, or a permissions problem produces a raw traceback out of the FREE gate — which
`SKILL.md` promises is "argparse in, exit code out". A crashed gate is a gate the agent may route
around.

**Fix:** give `_read_csv` a `(header, rows) | None` failure return, or wrap the three call sites:

```python
try:
    header, rows = _read_csv(chosen)
except (OSError, UnicodeDecodeError, csv.Error) as exc:
    print(f"reference file {chosen.name} could not be read: {exc}", file=sys.stderr)
    return None      # -> VALIDATION_FAILED, fail closed
```

---

### WR-10: `_resolve_exp_dir` accepts `--exp-dir experiments` (the containment check passes on the root itself)

**File:** `scripts/check_submission.py:553`

```python
if candidate != root and root not in candidate.parents:
```

When `candidate == root`, the first clause is `False` and the `and` short-circuits — the refusal
never fires. `--exp-dir experiments` therefore resolves to the experiments root, yielding
`exp_id = "experiments"` and a lookup for `experiments/submission.csv`. It exits 65 in practice, so
this is not exploitable today, but the containment predicate does not mean what it reads as, and
the `exp_id` it derives is nonsense that flows into the ledger join and the printed override
command.

**Fix:**

```python
if root not in candidate.parents:
    print(f"refusing to read {candidate} — it is not an experiment directory under {root}.",
          file=sys.stderr)
    return None
```

---

### WR-11: `check_submission` prints the `-1` sentinel to the human as if it were a count

**File:** `scripts/check_submission.py:722`

```python
print(f"slots left:     {budget} today (UTC day; charged={charged})")
```

When the count is unavailable this renders `slots left: UNKNOWN (fail closed) today (UTC day;
charged=-1)`. The `budget` half is handled; the `charged` half leaks the raw sentinel — the one
value `submissions_log.py:281` explicitly says "is not a count: callers MUST fail closed on it and
never coerce it". Printing it as `charged=-1` invites exactly the "minus one submissions?"
misreading, and this line is what `SKILL.md:196-198` instructs the agent to relay **verbatim** to
the user.

**Fix:**

```python
charged_text = "UNKNOWN" if charged == COUNT_UNAVAILABLE else str(charged)
print(f"slots left:     {budget} today (UTC day; charged={charged_text})")
```

---

## Verified sound (checked, no finding)

Recorded so a future reviewer does not re-litigate these:

- **`math.isclose` IEEE-754 guard** (`submission_gate.py:133`) — correct, and applied at the sole
  comparison site. `is_meaningful(0.81, 0.01, 0.80, True)` → `False`. No other module re-derives
  `margin > k * std`.
- **`-1` / `None` fail-closed chain** — `charged_today` → `remaining_slots` → `decide`. The sentinel
  never enters arithmetic; `remaining=None` short-circuits to `BLOCKED` before `_as_number(remaining)`
  is ever called. (What the *renderer* does with that block is WR-02.)
- **Write ordering** (`submit.py:336-350`) — the PENDING row is appended after read-back
  confirmation and before the poll; the `except Exception` around `poll_lb` (line 377) cannot orphan
  it. `rc == 0` is genuinely advisory: the fail-open literal match (line 289) and the read-back
  (line 312) both gate it.
- **Credential leakage** — no `print` of a raw CLI buffer in any of the four submission scripts;
  every failure path routes through `dump_last_error`. `submit.py:276` reaches into `payload` only
  for substring *matching*, never echo.
- **CV-vs-LB discipline (SCORE-02)** — `lb_gap` is pure and derived; `regen_strategy._lb_gap_body`
  only renders. No LB score reaches `best_submitted_cv`, `is_meaningful`, or `decide`. The
  comparison set in `best_submitted_cv` is keyed on `cv_mean` from the ledger and filtered by
  submission *status*, never by `public_score`. **CV remains the sole decision metric.**
- **`fetch_lb` cannot submit** — no `submit` argv is constructible in the module; the two argv sites
  (`read_submissions`, `_resume._status_fn`) are both `competitions submissions … --format json`.

---

_Reviewed: 2026-07-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
