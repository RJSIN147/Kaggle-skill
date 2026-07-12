# Phase 5: Submission & Leaderboard Tracking - Research

**Researched:** 2026-07-12
**Domain:** Kaggle CLI submission surface + LB read-back, CV-first budget gating, fold-averaged test prediction
**Confidence:** HIGH (R1/R2/R4/R5/R6 verified live or from installed source; R3 verified by reading the actual template)

## Summary

The two load-bearing research items (R1 `competitions submit`, R2 `competitions submissions`) are now
**fully pinned against the live CLI 2.2.3 installed in this project's `.venv`** — via `--help`, the
installed package source (`kaggle/api/kaggle_api_extended.py`, `kaggle/cli.py`,
`kagglesdk/competitions/types/submission_status.py`), and **read-only live calls** against `titanic`.
**No submission was ever made; no slot was spent.**

Three findings reshape the phase and the planner must hold all three:

1. **`kaggle competitions submit` is FAIL-OPEN on its exit code.** A nonexistent competition (404) and a
   failed upload both **print a message and exit 0**. `rc == 0` therefore does **not** prove the submission
   landed. This is the *exact* silent-failure class Phase 4 already fought (kernel says COMPLETE but threw),
   and the project already owns the correct posture: never trust the happy exit code — **confirm the
   submission by reading it back**.
2. **The CLI never surfaces a submission id from `submit`** (the API response carries `.ref`, but
   `competition_submit_cli` returns only `.message`). So the *only* reliable exp_id↔Kaggle correlation
   channel is the **`-m/--message` string, which round-trips into the `description` field on read-back**.
   `-m` is a **required** flag — put `exp-NNN` in it. This simultaneously solves correlation, gives us the
   real `ref` id, and gives us the confirmation the fail-open exit code cannot.
3. **There is NO submission-quota command.** `kaggle quota` exists but is **GPU/TPU hours only**
   (live-verified). D-04's "count today's charged submissions" must therefore be **derived by counting rows**
   from `competitions submissions --format json` — filtering to today (UTC) and excluding `ERROR` rows
   (D-13's "not charged" rule falls out for free).

Everything else follows cleanly. `submissions --format json` exposes exactly seven fields with
**live-verified** literals, including a status enum that serializes as the fully-qualified
**`"SubmissionStatus.COMPLETE"`** (not a bare `COMPLETE`) — the same parse-trap `poll_kernel.py` already
handles for `KernelWorkerStatus`. Fold-averaged test predictions drop into `run_cv` at an obvious seam,
with one sharp correctness trap (averaging **hard labels** is wrong — and `accuracy`, titanic's metric, is
exactly that path).

**Primary recommendation:** Build `check_submission.py` → `submit.py` → `fetch_lb.py` on top of the existing
gateway. In `submit.py`, treat the CLI's exit code as advisory only: after the call, **read back
`competitions submissions` and require a new row whose `description` starts with our `exp-NNN`** — that
read-back is simultaneously the success proof, the source of the Kaggle `ref` id, and the first poll tick.
Count the budget from that same read-back. Never parse the submit stdout for success.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Submission CSV production | Experiment/ML tier (`experiment.py.tmpl` `run_cv`) | — | Fold models already exist there; pandas/numpy allowed. Rides `pull_kernel` for free. |
| Pre-submit file validation | Plumbing tier (`check_submission.py`) | — | Stdlib `csv` only; must run without the ML env present. |
| Budget count / gate decision | Plumbing tier (`check_submission.py`) | Kaggle (authoritative source) | Kaggle owns truth; we only count + render. |
| Kaggle CLI invocation | Gateway (`kaggle_gateway.run_kaggle`) | — | D-16: one no-echo, timeout-bounded runner. Never a bare subprocess. |
| Submit/don't-submit decision | **Human**, sequenced by `SKILL.md` | Framework (computes + recommends) | PROJECT.md: human-in-the-loop is the point. Scripts never block on stdin. |
| LB score persistence | Plumbing (`submissions.jsonl`) | — | Canonical, append-only, git-tracked. Never `meta.json` (D-11). |
| CV→LB gap / divergence alarm | Plumbing (`regen_strategy.py` extension) | — | Derived view: join `submissions.jsonl` × `ledger.jsonl` on `exp_id`. |

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: CSV-only submit path for v1.** `05-01` targets `kaggle competitions submit -f submission.csv` for
  `competition.type == csv`. For `competition.type ∈ {code, unknown}` the submit path **refuses with a clear,
  framework-authored instruction and never spends a slot** (the Phase 2 D-14 contract). NOT a combined
  CSV+code path.
- **D-02: Pre-submit validation is referenced against `sample_submission.csv`.** Checks: **exact column
  headers**, **exact row count**, **id column present and the id SET matches order-independently**, and **no
  NaN/blank values in prediction columns**. All four with the **stdlib `csv` module**. Fail-closed with a
  **distinct reserved exit code** and a precise message naming the exact mismatch. ⚠ **The sample filename
  varies** (titanic's is `gender_submission.csv`) — reuse Phase 2's `submission_csv_in_manifest` heuristic,
  don't re-derive it. Fall back to deriving expected ids from `test.csv`'s id column **only** when no sample
  file exists in the manifest.
- **D-03: Bounded-poll then DETACH for LB read-back** — reuse the **proven Phase 4 poller shape**
  (D-08/D-09/D-10). Bounded wait budget + exponential backoff + jitter. On budget expiry, **DETACH** — record
  the submission as `PENDING` (never lose a spent slot); a discrete **`fetch_lb`** step records the score
  later. Transient poll errors tolerated; fail-closed only on persistent errors or budget expiry. NOT an
  unbounded poll; NOT always-detach.
- **D-04: The BLOCKING budget gate reconciles against KAGGLE's authoritative submission count**, not our
  local records. At submit-time, query `kaggle competitions submissions` to derive the true count used today.
  Processing-error submissions are **not charged**; out-of-band submissions are invisible to a local counter.
  `submissions.jsonl` remains our **local provenance record**, NOT the gate's source of truth. **Fail-closed**
  if the authoritative count cannot be fetched. The UTC-aware daily reset is **Kaggle's own boundary**.
- **D-05: BLOCK-BY-DEFAULT with an informed human override — the framework never auto-submits and never
  silently hard-refuses.** ⚠ **Load-bearing; the planner must hold it.** The framework **takes a position**:
  it computes and presents the decision material (this experiment's CV vs the best already-submitted CV,
  whether the gain is beyond fold-noise, the CV→LB history/divergence state, remaining slots today). When CV
  improvement **is** meaningful → recommendation is **submit**. When it **is not** → the default state is
  **BLOCKED / "not recommended"**, and the human must **consciously confirm** to proceed. **The human always
  makes the final call.** NOT a hard mechanical wall; NOT pure advisory with no blocked state.
- **D-06: "Meaningful improvement" = beats the best already-submitted CV by MORE THAN FOLD-NOISE.**
  `cv_mean` beats the best submitted `cv_mean` by a margin exceeding a noise bound derived from **fold std**
  (e.g. `> k · cv_std`), respecting `greater_is_better` from `config.metric`. Rejected: "strictly beats best
  CV"; rejected: a fixed absolute/relative threshold. *Planner: `k` is a concrete constant to choose and
  state; keep it configurable.*
- **D-07: The override reason is OPTIONAL, and recorded to provenance when supplied.** Overriding requires
  **explicit human confirmation** but **not** a mandatory reason string. When given, it is written into the
  `submissions.jsonl` row. Do not force the user to type a justification to proceed.
- **D-08: On `limit_provenance == "assumed_default"` — WARN every time, and never spend the FINAL assumed
  slot without explicit confirmation.** Every submission decision surfaces *"budget is ASSUMED (5/day — not
  confirmed against the rules page)"*, and the **last** assumed slot is gated behind an explicit confirmation.
  NOT warn-only; NOT refuse-until-confirmed.
- **D-09: Phase 5 EXTENDS the Phase 3 scaffold/harness so an experiment emits test predictions to
  `experiments/exp-NNN/submission.csv`.** ⚠ **Discovered gap, not scope creep.** **Mechanism — reuse the CV
  fold models:** average the per-fold models' test predictions rather than refitting on full train. Rejected:
  a separate full-train refit step; rejected: leaving it to ad-hoc AI code per experiment. ✅ `submission.csv`
  becomes a first-class hashed experiment artifact that flows back through the **Phase 4 `pull_kernel` path
  unchanged**. ⚠ **Planner:** test-prediction emission must be **optional/graceful** — a pure-diagnostic
  experiment that doesn't produce predictions must still record a valid CV result, not fail.
- **D-10: The divergence alarm fires on RANK INVERSION — CV says better, LB says worse.** Experiment B has a
  better CV than A, but scores worse on the leaderboard. **Scale-free**, no per-competition tuning. Requires
  ≥2 scored submissions before it can fire — state that plainly. Rejected: an absolute `|CV − LB|` gap
  threshold. *The CV→LB gap is still **computed and trended per experiment**; rank inversion raises the
  **alarm**.*
- **D-11: `submissions.jsonl` is the CANONICAL LB record; per-experiment CV→LB views are DERIVED by joining
  on `exp_id`.** Row shape (at minimum): `exp_id`, **submission file hash**, UTC timestamp,
  `status ∈ {PENDING, SCORED, FAILED}`, LB score, and the optional D-07 override reason. **The LB score is
  NEVER written back into `meta.json`.** Naturally handles many-submissions-per-experiment.
- **D-12: Final selection / nomination is OUT of v1.** ⚠ **A deliberate, user-directed deviation from roadmap
  plan `05-02`.** **The planner must NOT build it** — not the advisory recommendation, not a CLI nomination.
- **D-13: A FAILED submission is RECORDED but NOT COUNTED.** Kaggle does **not charge a slot** for
  processing-error submissions. Write the failed attempt to `submissions.jsonl` with `status=FAILED` + the
  error. The budget arithmetic comes **free from D-04's Kaggle-authoritative reconciliation**.
- **D-14: Three DISCRETE, idempotent entry points — `check_submission` → `submit` → `fetch_lb`.** Each is
  stdlib-only, self-locating, `--workspace`-driven, argparse-in / exit-code-out; **SKILL.md sequences them and
  holds the human submit/don't-submit loop**; scripts never block on stdin.
  - **`check_submission.py`** — validates the file (D-02) **AND** renders the full decision material (D-05,
    D-06 noise read, remaining slots, D-08 assumed-budget warning, gate recommendation). **Exit code signals
    gate-blocked vs clear vs validation-failed.** **Crucially: FREE — it never spends a slot.**
  - **`submit.py`** — spends the slot **only when explicitly invoked** (carrying the human's confirmation and
    the optional D-07 reason), then bounded-polls per D-03.
  - **`fetch_lb.py`** — the D-03 detach fallback; re-runnable, records a `PENDING` submission's score.
  Rejected: folding validation + gate into `submit.py` behind a `--force` flag.
  *Planner: new reserved exit codes follow the existing sysexits-aligned convention in
  `scripts/kaggle_gateway.py` (77 = UI_GATE, 78 = LIMIT_NEEDS_USER already taken; 124/126/127/128+ reserved).*

### Claude's Discretion

- **The noise constant `k` in D-06** (`improvement > k · cv_std`) — pick a concrete, defensible default and
  make it configurable; state it wherever the recommendation is rendered.
- **D-03 poll constants** — initial interval, multiplier, cap, jitter, and the default LB wait budget. LB
  scoring is typically far faster than a kernel run, so the Phase 4 constants are a starting point, not a
  mandate.
- **`submissions.jsonl` full row schema** beyond the D-11 named fields — keep it small, append-only,
  git-diffable, and rebuildable.
- **Exact reserved exit-code numbering** for gate-blocked / validation-failed.
- **How the fold-averaged test prediction is exposed in the harness signature** (D-09). Must satisfy the
  Phase 3 D-07 tension: flexible enough that the AI rarely needs to bypass it.
- **How the D-05 decision material is rendered** and where the submit flow surfaces in `SKILL.md`'s scripts
  table + gate protocol.
- **Whether `strategy.md`'s regenerated mechanical sections gain an LB/gap block** (extend the Phase 3
  D-11/D-12 regen contract, don't fork it).
- **Where a `sample_submission.csv` is located/resolved** for D-02 given the varying filename.

### Deferred Ideas (OUT OF SCOPE)

- **Code-competition (notebook→submit) submission flow** — scoped out of v1 by D-01. v1 refuses cleanly
  rather than spending a slot.
- **Final-selection / nomination rule** — explicitly scoped out of v1 by the user (D-12).
- **Nominating via the CLI** — rejected even if final selection returns.
- **GPU-hour budget model + push gating** — still deferred (Phase 4 D-13). Phase 5 builds the *submission*
  budget only.
- **In-notebook version pinning to match the `kaggle/python` image** — still deferred; D-10's alarm is the
  detector, pinning is a remedy.
- **Adversarial-validation-driven CV strategy** — experiment design, not submission tracking.
- **Semantic idea dedup (ANLY-01), ledger comparison views (ANLY-02), evidence-ranked strategy synthesis
  (ANLY-03)** — v2.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCORE-01 | User can submit predictions to the competition via the Kaggle CLI and record the resulting LB score | §R1 (submit surface + the fail-open exit-code trap + the `-m` correlation channel), §R2 (read-back shape + status literals), §R3 (`submission.csv` production — it does not exist today), §R5 (bounded poll → detach) |
| SCORE-02 | CV is the decision metric everywhere; the framework computes and trends the CV→LB gap with a divergence alarm | §R2 (`publicScore` is a **string**; `""` = unscored), §R6 (`ledger.jsonl` join keys: `exp_id`, `cv_mean`, `cv_std`, `greater_is_better`), §Pattern 4 (rank-inversion alarm), §Pattern 6 (strategy regen extension) |
| SCORE-03 | Submissions are rationed against the daily limit; the framework gates submissions on CV improvement and tracks remaining budget | §R2 (**no quota command exists** — must count rows; UTC-boundary trap), §Pattern 3 (the D-05/D-06/D-08 gate), §R6 (exit-code table for gate-blocked) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

| Directive | Consequence for this phase |
|-----------|---------------------------|
| Skill scripts are **stdlib-only** | `check_submission.py` / `submit.py` / `fetch_lb.py` use `csv`, `json`, `hashlib`, `datetime`, `argparse`, `re`, `time`, `random` — **no pandas/numpy**. The ML tier (`experiment.py.tmpl`) may use pandas/numpy. |
| **`kaggle` CLI is the sole primitive** | Every call routes through `kaggle_gateway.run_kaggle`. No MCP, no `kagglehub` (it cannot submit anyway). |
| **No runtime `pip install`** | Nothing installs at submit time. |
| **Never echo credentials / raw CLI buffers** | Submit/read-back output is matched, never printed; persistent failures quarantine to `control/raw/last-error.txt` via `dump_last_error`. |
| Scripts are self-locating, `--workspace`-driven, argparse-in / exit-code-out, **never interactive** | The human submit/don't-submit decision lives in `SKILL.md`, never an `input()`. |
| Failed (processing-error) submissions do **not** count against the daily limit | **VERIFIED as reachable**: `status == ERROR` rows are returned by `submissions` and are excludable (§R2). |
| `enable_internet: false` default; egress allowlist | `api.kaggle.com` + `storage.googleapis.com` already allowlisted (`references/egress-allowlist.md`); submission upload routes there. No change needed. |
| Numbers are tooling-written, never AI-typed | The LB score is parsed from CLI JSON by tooling, exactly like the CV score. |

---

## R1 — `kaggle competitions submit`: the live surface

> **Provenance:** `kaggle competitions submit --help` (live, CLI 2.2.3) + the installed source
> `kaggle/api/kaggle_api_extended.py::competition_submit / competition_submit_cli` and `kaggle/cli.py::main`.
> **`kaggle competitions submit` was NEVER executed.** Nothing below cost a slot.

### Invocation [VERIFIED: live `--help`, CLI 2.2.3]

```
usage: kaggle competitions submit [-h] [-f FILE_NAME] [-k KERNEL] -m MESSAGE
                                  [-v VERSION] [-q] [--sandbox]
                                  [competition]
```

| Flag | Notes |
|------|-------|
| `competition` | **POSITIONAL**, not `-c`. Optional — falls back to `kaggle config set competition`. **Always pass it explicitly** (never rely on ambient CLI config). |
| `-f/--file` | Path to the CSV. (For code comps this is instead the *name* of the kernel's output file — not our path.) |
| `-m/--message` | **REQUIRED** (no brackets in the usage string). ⭐ **This is the exp_id correlation channel** — it round-trips into `description` on read-back. |
| `-k/--kernel`, `-v/--version` | **Code-competition only.** D-01 refuses that path → **never pass these.** The CLI raises `ValueError` if only one of the pair is given. |
| `-q/--quiet` | Suppresses upload-progress output. |
| `--sandbox` | ⚠ **TRAP: this is NOT a dry-run.** Source + help: "competition hosts/admins only". Do **not** reach for it as a safe test mode. |

**The v1 command shape:**
```bash
kaggle competitions submit <slug> -f experiments/exp-007/submission.csv -m "exp-007 | cv=0.84123"
```

### ⚠ CRITICAL: `submit` is FAIL-OPEN on its exit code [VERIFIED: installed source]

`kaggle/cli.py::main` sets `error = True` — and thus `exit(1)` — for **only** `HTTPError`, `ApiException`,
and `ValueError`. Everything else exits **0**. And `competition_submit_cli` **swallows its own failures
before they can propagate**:

```python
# kaggle/api/kaggle_api_extended.py::competition_submit_cli  (~line 1786)
except RequestException as e:
    if e.response and e.response.status_code == 404:
        print("Could not find competition - please verify that you "
              "entered the correct competition ID and that the "
              "competition is still accepting submissions.")
        return ""                      # <-- swallowed. main() prints "" and exits 0.
    else:
        raise e                        # non-404 -> propagates -> exit 1

# kaggle/api/kaggle_api_extended.py::competition_submit  (~line 1718)
if upload_status != ResumableUploadResult.COMPLETE:
    resp = ApiCreateSubmissionResponse()
    resp.message = "Could not submit to competition"
    return resp                        # <-- upload failed. main() prints it and exits 0.
```

| Failure mode | Exit code | Detectable by |
|--------------|-----------|---------------|
| Bad/closed competition slug (404) | **0** ⚠ | stdout literal `Could not find competition` |
| Upload failed | **0** ⚠ | stdout literal `Could not submit to competition` (client-hardcoded — reliable) |
| Auth failure (401) | 1 | `HTTPError` → stderr |
| Gate / 403 (rules not accepted) | 1 | `HTTPError` → stderr `403 Client Error: Forbidden` |
| Code-comp flags half-given | 1 | `ValueError` |
| Success | 0 | **server-authored** message string — **UNVERIFIED, do not parse** |

**Consequence for the planner (load-bearing):** `submit.py` must **not** conclude success from `rc == 0`.
The success message is authored server-side and could not be pinned without spending a slot — treat it as
**unknown text**. The correct posture, and the one this project already uses elsewhere:

1. `rc != 0` → hard failure (classify via the gateway; 403 → `classify_gate`).
2. `rc == 0` **AND** stdout contains `Could not find competition` or `Could not submit to competition` →
   **failure** (a fail-open lie). Record nothing as spent; surface the framework-authored message.
3. Otherwise → **do not assume success.** Immediately **read back** `competitions submissions` and require a
   NEW row whose `description` begins with our `exp-NNN` and whose `date` ≥ the submit start time. That row
   *is* the proof, *and* it carries the `ref` id the submit call refused to give us.

This is structurally identical to Phase 4's `record_experiment --kernel-log` posture (a kernel can report
COMPLETE and still have lied). Reuse the instinct.

### Does submit block until scored? **No.** [VERIFIED: source]

`competition_submit` calls `create_submission` and returns the response immediately — there is no polling in
the client. The submission then appears in `submissions` with status `PENDING` and is scored asynchronously.
**D-03's poller is genuinely needed.**

### Does submit return a submission id? **Not via the CLI.** [VERIFIED: source]

`ApiCreateSubmissionResponse` carries both `.message` **and** `.ref`, but `competition_submit_cli` returns
**only `submit_result.message`**. The id is discarded before it reaches stdout. → The `ref` must be recovered
from the read-back (which the fail-open problem forces us to do anyway — so this costs nothing).

---

## R2 — `kaggle competitions submissions`: the read-back surface

> **Provenance:** live READ-ONLY calls against `titanic` (spends nothing) + `--help` + the installed source
> (`submission_fields`, `print_results`/`get_json_serializable`, `_resolve_projection`) +
> `kagglesdk/competitions/types/submission_status.py`.

### The command [VERIFIED: live]

```bash
kaggle competitions submissions <slug> --format json --page-size 200
```

### Exact output shape [VERIFIED-LIVE, 2026-07-12, CLI 2.2.3]

Real output (sanitized only by being the researcher's own public titanic history):

```json
[
  {
    "ref": 46780678,
    "fileName": "submission.csv",
    "date": "2025-09-10T11:29:01.560000",
    "description": "",
    "status": "SubmissionStatus.COMPLETE",
    "publicScore": "0.77511",
    "privateScore": ""
  },
  ...
]
```

| Field | Type in JSON | Notes — **all live-verified** |
|-------|--------------|-------------------------------|
| `ref` | **int** | The Kaggle submission id. Store it in `submissions.jsonl`. |
| `fileName` | str | Basename of the uploaded file (`submission.csv`). Weak correlator on its own — every experiment uploads the same basename. |
| `date` | str, ISO-8601 | ⚠ **NAIVE — no timezone suffix** (`"2025-09-10T11:29:01.560000"`). See the UTC trap below. |
| `description` | str | **The `-m/--message` text, round-tripped.** ⭐ The exp_id correlation channel. `""` when no message was given. |
| `status` | str | ⚠ **`"SubmissionStatus.PENDING"` / `"SubmissionStatus.COMPLETE"` / `"SubmissionStatus.ERROR"`** — fully-qualified, *not* bare. |
| `publicScore` | **str** | ⚠ **A STRING**, not a float (`"0.77511"`). **`""` when not yet scored / not applicable.** Parse with a guarded `float()`. |
| `privateScore` | **str** | Same. `""` while the private LB is withheld (the normal case during a live competition). |

**The full allowed field set is exactly these seven** — confirmed by triggering the CLI's own error:

```
$ kaggle competitions submissions titanic --format "json(ref,status,errorDescription)"
Unknown field in projection: 'errorDescription'. Allowed fields: date, description, fileName,
privateScore, publicScore, ref, status
```

### Status literals [VERIFIED: `kagglesdk/competitions/types/submission_status.py` + live output]

```python
class SubmissionStatus(enum.Enum):
    PENDING = 0
    COMPLETE = 1
    ERROR = 2
```

Serialization path (`get_json_serializable`, ~line 6712):
```python
val = getattr(i, self.camel_to_snake(f))
if isinstance(val, datetime): val = val.isoformat()
elif not isinstance(val, (int, float, bool, str)) and val is not None: val = str(val)   # <-- enum
```
`str(SubmissionStatus.COMPLETE)` → `"SubmissionStatus.COMPLETE"`. **There are exactly three terminal-ish
literals and no others.** This is precisely the `KernelWorkerStatus` trap `poll_kernel.py` already solved —
reuse its regex-anchored posture, do **not** substring-grep for `COMPLETE` (an `ERROR` row's fields could in
principle carry the word).

Recommended parse (mirrors `poll_kernel._STATUS_RE`):
```python
_SUB_STATUS_RE = re.compile(r"^(?:SubmissionStatus\.)?(PENDING|COMPLETE|ERROR)$")
```

Mapping to D-11's vocabulary: `PENDING → PENDING`, `COMPLETE → SCORED`, `ERROR → FAILED`.

### ⚠ CRITICAL: there is **NO** submission-quota command [VERIFIED-LIVE]

`kaggle quota` exists — and is **GPU/TPU hours only**:

```json
[ {"resource": "GPU", "used": "0.00h", "remaining": "30.00h", "total": "30.00h",
   "refreshAt": "2026-07-18T00:00:00"},
  {"resource": "TPU", ...} ]
```

There is **no** command, flag, or field anywhere in the CLI 2.2.3 surface that reports remaining daily
submissions. **D-04 must count rows.** This is answered plainly, as the research brief asked.

**The charged-count algorithm (D-04 + D-13):**
```
charged_today = count of rows where:
    parse_date(row["date"]).date() == today_utc          # UTC day boundary
    AND status(row) != ERROR                             # D-13: errors are not charged
# PENDING counts as charged — the slot was accepted and is being scored.
remaining = config.submission.daily_limit - charged_today
```
Fail closed (D-04): if `rc != 0`, the payload won't parse, or a `status`/`date` won't parse → **do not guess
a count**; block and tell the user.

### ⚠ The UTC trap (the #1 pitfall for D-04)

`date` has **no timezone suffix**. If the planner writes `datetime.fromisoformat(row["date"])` and compares
against `datetime.now()` (local), the budget will be **silently miscounted near the day boundary** — the exact
class of confident-but-wrong failure this project fails closed against.

**Rule:** treat the value as **UTC** and compare against `datetime.now(timezone.utc)`:
```python
ts = datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc)   # naive -> UTC-aware
today = datetime.now(timezone.utc).date()
```
**Confidence: MEDIUM [ASSUMED].** Kaggle's API convention is UTC and the SDK parses a wire timestamp, but I
could **not prove the tz** without making a submission and comparing to a known clock. **Planner: add a
`checkpoint:human-verify` at the first real submit** — record the submit wall-clock (UTC) and compare it to
the `date` that comes back. If they match, the assumption is confirmed and belongs in
`references/kaggle-cli-behavior.md`. Assumption **A1** below.

### Ordering & pagination [VERIFIED-LIVE + source]

- **Sort: newest-first.** `competition_submissions_cli` never passes `sort`/`group`, so the SDK defaults apply:
  `SubmissionSortBy.SUBMISSION_SORT_BY_DATE` and `SubmissionGroup.SUBMISSION_GROUP_ALL`. Live output confirms
  descending date. **`GROUP_ALL` means `ERROR` rows ARE returned** — which is what makes D-13 mechanizable.
- **`--page-size`: default 20, max 200.**
- ⚠ **`--page-token` is UNUSABLE.** `competition_submissions()` returns `response.submissions` and
  **discards `next_page_token`** — the CLI never prints it, so there is no token to pass back in. Verified in
  source; the live JSON is a bare list with no token key.
- **Consequence — is today truncated off page 1?** No. Sort is descending and daily limits are ≤ ~10, so
  today's rows are always at the head. **Use `--page-size 200` and read one page.** Do not attempt pagination.

### Is `competitions leaderboard` needed? **No.** [VERIFIED]

`submissions` already returns `publicScore` per submission — which is *our* LB score, the only thing SCORE-01
and SCORE-02 need. `competitions leaderboard` returns the **public standings of all teams** (rank/team/score),
which is a different question (our rank among others) that no requirement asks for. **Do not build it.**
Keeping the CLI surface to `submit` + `submissions` also halves the fixture/validation burden.

### Known-unknowns (honest)

- **The `ERROR` reason text is NOT retrievable via the CLI.** `ApiSubmission` has an `error_description`
  field, but it is not in `submission_fields`, and `_resolve_projection` can only **narrow** the fixed list
  (it raises `ValueError` on any other name — verified live, above). **D-13's "record the error" can only
  record `status=FAILED`, not the reason.** Write `error_description: null` and, in the message, point the
  user to the Kaggle submissions page. Do not fabricate a reason. [VERIFIED]
- **The submit success message string is server-authored** and could not be captured without spending a slot.
  Do not parse it. [UNVERIFIED — by design]

### Fixture entries for `references/kaggle-cli-behavior.md`

The phase must extend that doc (CONTEXT flags it as empty for submit/LB). Everything above is written to be
pasted in. The honest provenance line: *"Captured 2026-07-12 against CLI 2.2.3 in the project `.venv` by
(a) `--help`, (b) reading the installed package source, and (c) READ-ONLY `competitions submissions` /
`quota` calls against `titanic`. **`competitions submit` was never executed — no submission slot was spent.**
No credential value was read, printed, or recorded."*

---

## R3 — Extending `run_cv` to emit `submission.csv` (D-09)

> **Provenance:** direct read of `scripts/templates/experiment.py.tmpl` (229 lines) and
> `scripts/metric_registry.py`. **CONTEXT is correct: `submission.csv` does not exist today.** `run_cv` fits
> fold models, scores them, saves OOF, and never touches test.

### Current harness signature [VERIFIED: source]

```python
def run_cv(*, X, y, model_factory, preprocess_factory=None, feature_fn=None,
           metric, registry_entry, cv_scheme, n_splits=5, seed=DEFAULT_SEED,
           groups=None, splitter=None, exp_dir=".", prediction_type=None):
```

The fold loop (lines 125–140) is where every fold's `pp` (fitted preprocessor) and `model` already live:

```python
for tr, va in split.split(*split_args):
    Xtr, Xva, ytr = Xv[tr], Xv[va], yv[tr]
    if preprocess_factory is not None:
        pp = preprocess_factory()
        Xtr = pp.fit_transform(Xtr, ytr)   # fit on train fold only
        Xva = pp.transform(Xva)            # transform val fold — no leakage
    model = model_factory()
    model.fit(Xtr, ytr)
    if ptype == "proba":
        proba = model.predict_proba(Xva); pred = proba[:, 1] if proba.shape[1] == 2 else proba
    else:
        pred = model.predict(Xva)
    fold_scores.append(float(metric_fn(yv[va], pred)))
    ...
```

### The least-invasive seam

**Add optional keyword args** (all default `None` → fully backward-compatible, and D-09's
"optional/graceful" requirement is satisfied by construction):

```python
def run_cv(*, ..., X_test=None, test_ids=None, id_column=None,
           target_column=None, submission_agg=None):
```

**Inside the loop**, immediately after `model.fit(...)` — reusing **that same fold's fitted `pp`**, which is
what makes the anti-leakage contract hold for test too:

```python
if Xte_v is not None:
    Xte = pp.transform(Xte_v) if preprocess_factory is not None else Xte_v
    if ptype == "proba":
        p = model.predict_proba(Xte)
        test_preds.append(p[:, 1] if p.shape[1] == 2 else p)
    else:
        test_preds.append(model.predict(Xte))
```

**After the loop**, aggregate and write `Path(exp_dir)/"submission.csv"` (flat at the experiment root — see
the kernel note below). Write it with the **stdlib `csv` module** so `run_cv` stays pandas-free (it currently
imports only numpy).

### ⚠ THE CORRECTNESS TRAP: averaging hard labels is WRONG

`metric_registry.REGISTRY` carries `prediction_type ∈ {"label", "proba", "raw"}` [VERIFIED: source]:

| `prediction_type` | Metrics | Correct fold aggregation |
|-------------------|---------|--------------------------|
| `proba` | `roc_auc`, `logloss` | **Mean** across folds. A soft-voting ensemble — correct and standard. |
| `raw` | `rmse`, `mae`, `rmsle`, `mape`, `r2` | **Mean** across folds. Correct. |
| `label` | `accuracy`, `f1`, `f1_macro`, `precision`, `recall`, `qwk`, `mcc` | ⚠ **MEAN IS WRONG.** Averaging 5 folds' `0/1` labels yields `0.6` — not a label. Must **vote**. |

**This is not an edge case: titanic's metric is `accuracy` → `prediction_type == "label"`.** The default
competition hits the broken path. If the planner writes a naive `np.mean(test_preds, axis=0)`, the very first
end-to-end submission emits a column of `0.4`/`0.6` floats where Kaggle expects `0`/`1` — and D-02's own
pre-submit validator (which only checks blanks/NaN, headers, ids) would **pass it**, so the slot gets spent
on garbage.

**Recommended aggregation for `label`:** average **probabilities** across folds and `argmax` (strictly better
than hard voting — it's a calibrated soft ensemble, and every classifier that produces labels for these
metrics has `predict_proba`); fall back to a per-row **majority vote** when `predict_proba` is absent:

```python
def _aggregate(test_preds, ptype, proba_preds=None):
    if ptype in ("proba", "raw"):
        return np.mean(test_preds, axis=0)
    # ptype == "label"
    if proba_preds:                                   # soft-vote then argmax (preferred)
        return classes[np.argmax(np.mean(proba_preds, axis=0), axis=1)]
    stacked = np.vstack(test_preds)                   # majority vote (fallback)
    return np.apply_along_axis(
        lambda col: Counter(col).most_common(1)[0][0], axis=0, arr=stacked)
```

Expose `submission_agg=` as an explicit override so the AI can bypass it (the Phase 3 D-07 flexibility
tension) without editing the harness.

**Second trap (call it out in the docstring):** `prediction_type` describes what the **metric** consumes, not
necessarily what the **submission file** wants. They usually coincide (an AUC comp wants probabilities; an
accuracy comp wants labels), but not always. D-02's validation against the sample file is the backstop — and
`submission_agg` is the escape hatch. Flag in the harness docstring; do not try to auto-detect.

### Graceful degradation (D-09's explicit requirement)

- `X_test is None` → **no `submission.csv`, no error.** `result.json` is written exactly as today; a
  diagnostic experiment still records a valid CV result.
- Add `"submission_path": "submission.csv"` (or `null`) to `result.json` and append it to `artifacts`.
  ⚠ **Planner: confirm `record_experiment.py`'s result-schema gate tolerates the added key** (it reads named
  keys; an additive key should be fine — verify, don't assume).

### Kernel path — free, exactly as CONTEXT claims [VERIFIED: `pull_kernel.py`]

`pull_kernel.py` pulls kernel output as **FLAT files** into `experiments/exp-NNN/` ("result.json, oof.npy,
rendered .ipynb as FLAT files… kernel output is NOT a compressed archive"). So writing `submission.csv` at
`Path(exp_dir)/"submission.csv"` (**not** under `artifacts/`) means the kernel path lands it in exactly the
same place as the local path, with **zero changes to `pull_kernel.py`**. The `resolve_data_dir()` seam is
untouched — `X_test` is loaded from the same `data_dir` in the AI-edited block of `main()`.

### ⚠ `.gitignore` integration trap [VERIFIED: `scripts/templates/gitignore.tmpl`]

The workspace `.gitignore` **already contains `experiments/*/*.csv`** — so `submission.csv` is **ignored by
default**. CONTEXT flagged this as something to verify; it is real.

**Recommendation: leave it ignored.** A submission CSV can be large; it is a heavy artifact, consistent with
`data/`, `*.npy`, and `artifacts/`. Provenance is preserved *better* by the `file_sha256` in
`submissions.jsonl` (D-11 requires the hash anyway), and reproducibility is preserved by the **tracked**
`experiment.py` + `seed` + `git_commit`. Do **not** add a `!experiments/*/submission.csv` negation. The planner
should make this an explicit, stated decision rather than tripping over it.

`control/submissions.jsonl` is **tracked** by default — no `.gitignore` rule covers it (only
`control/raw/last-error.txt` is ignored). ✅ No change needed.

---

## R4 — Pre-submit validation against the sample file (D-02)

### Resolving the sample file [VERIFIED: `capture_competition.py` + `download_data.py`]

The Phase 2 heuristic to reuse (`classify_competition_type`, ~line 158):
```python
submission_csv = next(
    (n for n in names if "submission" in n.lower() and n.lower().endswith(".csv")), None)
```
It matches titanic's `gender_submission.csv` ✅. Its value is a **filename string or `None`**.

**Where it is persisted:** NOT in `config.json` — it is written to
**`control/raw/competition-type-signals.json`** under `signals.submission_csv_in_manifest` (line ~328). The
actual file is extracted by `download_data.py` into **`data/`**.

**Resolution ladder for `check_submission.py`:**
1. Read `control/raw/competition-type-signals.json` → `signals.submission_csv_in_manifest` → look for
   `data/<that name>`. *(This is "reuse it, don't re-derive it".)*
2. If absent/missing on disk → case-insensitive glob `data/*submission*.csv`.
3. If still none → **fallback (D-02's explicit fallback)**: derive the expected id set from `data/test.csv`'s
   **first column**, and take the header from the competition's own docs. Row count = `len(test)`.
4. If neither exists → **fail closed** with `EX_DATAERR` and a precise message. Never submit unvalidated.

**Known weakness (worth one line in the code comment):** the heuristic takes the **first** manifest match; a
competition shipping several `*submission*.csv` files could mis-pick. Low risk, but log which file was used —
the message must name it so a human can spot a wrong pick.

### The four checks, stdlib `csv` only

```python
import csv, math
with open(sample) as f:  sample_rows = list(csv.reader(f))
with open(ours)   as f:  our_rows    = list(csv.reader(f))

# 1. exact column headers (order-sensitive — Kaggle is)
sample_rows[0] == our_rows[0]
# 2. exact row count
len(our_rows) == len(sample_rows)
# 3. id SET equality, order-independent (id col = column 0 of the sample header)
{r[0] for r in our_rows[1:]} == {r[0] for r in sample_rows[1:]}
# 4. no blank / NaN in prediction columns (every column after the id)
BAD = {"", "nan", "NaN", "NA", "None", "null", "inf", "-inf"}
all(v.strip() not in BAD and not (is_float(v) and math.isnan(float(v)))
    for r in our_rows[1:] for v in r[1:])
```

Report the **exact** mismatch (D-02: "a precise message naming the exact mismatch") — e.g. *"row count 417 ≠
expected 418"*, *"header ['PassengerId','Prediction'] ≠ expected ['PassengerId','Survived']"*, *"3 ids in
sample are missing from your file (first: 1044)"*, *"12 blank values in column 'Survived' (first at row 88)"*.
Exit `EX_DATAERR (65)`.

**Bonus check worth adding (catches the R3 label trap):** if the sample file's prediction column is
all-integers and ours contains non-integral floats, **warn loudly** — that is the fold-averaged-hard-labels
bug. Cheap, stdlib, and it protects a real slot.

---

## R5 — The poller shape to reuse (D-03)

> **Provenance:** direct read of `scripts/poll_kernel.py` (339 lines).

### The reusable pieces [VERIFIED: source]

```python
BASE_DELAY = 10.0; BACKOFF_MULTIPLIER = 2.0; MAX_DELAY = 120.0
DEFAULT_BUDGET_S = 7200; DEFAULT_POLL_TIMEOUT = 60; MAX_CONSECUTIVE_ERRORS = 5

def compute_delay(attempt, rng=None) -> float:
    base = min(BASE_DELAY * (BACKOFF_MULTIPLIER ** attempt), MAX_DELAY)
    return base if rng is None else rng.uniform(0.0, base)   # FULL jitter, always <= cap

def poll_loop(status_fn, *, now, sleep, rng, budget_s, max_consecutive_errors, cancel_fn=None) -> dict:
    # returns {"terminal": bool, "status": str, "reason": "terminal"|"budget"|"transient", "last_out": str}
```

`poll_loop` is **structurally generic** (it takes an injected `status_fn` returning the `run_kaggle`
`(rc, combined)` shape, and injected `now`/`sleep`/`rng` for determinism), **but it is bound to the kernel
domain** by module-level `TERMINAL` / `IN_FLIGHT` / `classify_status`.

### Recommendation: import `compute_delay`, write a small LB loop — do NOT fork the constants, do NOT refactor `poll_kernel`

Phase 4 is complete and verified; refactoring `poll_loop` to take a `classify_fn` would touch a locked,
tested file and risk a regression for no functional gain. Instead:

- **Import `compute_delay` from `poll_kernel`** — the genuinely reusable, unit-tested backoff math
  (`tests/test_poll_kernel.py::test_backoff_budget` already pins it).
- Write a ~30-line LB poll loop in a shared helper that reuses the identical **structure**: bounded wall-clock
  budget checked *before* sleeping, full jitter, a consecutive-transient-error counter that resets on any
  clean parse, and **detach-not-cancel** on budget expiry.
- Define LB-local constants (Claude's discretion per CONTEXT — LB scoring is seconds-to-minutes, not hours):

| Constant | Kernel value | **Recommended LB value** | Why |
|----------|-------------|--------------------------|-----|
| `LB_BASE_DELAY` | 10.0s | **5.0s** | Most competitions score in well under a minute; a 10s first tick wastes the common case. |
| `LB_BACKOFF_MULTIPLIER` | 2.0 | **2.0** | Unchanged — proven. |
| `LB_MAX_DELAY` | 120.0s | **30.0s** | A 2-minute sleep is absurd against a 30-second scoring job. |
| `LB_BUDGET_S` | 7200 (2h) | **600 (10 min)** | Covers slow scorers without ever hanging the human. On expiry → DETACH. |
| `MAX_CONSECUTIVE_ERRORS` | 5 | **5** | Unchanged — proven. |
| poll timeout | 60 | **60** | Unchanged. |

### What `fetch_lb`-style detach/resume needs

`poll_kernel` resumes by re-reading the `kernel_run.json` handoff (`kernel_slug`). The LB analogue is
**cleaner** because the handoff already exists: **the `submissions.jsonl` row itself.** On detach, the row
stays `status: "PENDING"` with its `kaggle_ref`. `fetch_lb.py` finds all `PENDING` rows (or one via
`--exp-id`), re-reads `competitions submissions`, matches on `ref`, and **rewrites the row's status/score**.

⚠ **This means `submissions.jsonl` is append-only for *new attempts* but must support an in-place status
transition** (`PENDING → SCORED | FAILED`). Two clean options — the planner must pick one and state it:
- **(a) Rewrite-in-place:** load all rows, update the matching one, atomically rewrite (tempfile +
  `os.replace`, exactly `rebuild_ledger.py`'s pattern). Simple; the file stays one-row-per-submission.
  **Recommended.**
- (b) Strict append-only event log (append a second `SCORED` row for the same `ref`; last-write-wins on read).
  More faithful to "append-only" but every reader must now fold events, and the D-10/D-11 join gets harder.

(a) preserves "one row per submission" — which is what D-11's join and the divergence alarm actually want —
and the atomic-rewrite pattern is already established in this codebase.

**Bonus (mirrors `rebuild_ledger.py`):** give `fetch_lb.py` a `--reconcile` mode that back-fills
`submissions.jsonl` from Kaggle's authoritative list — recovering out-of-band submissions (which D-04 already
acknowledges exist). `exp_id` is recoverable from the `description` prefix; rows without one get
`exp_id: null`. This makes the canonical file **self-healing against the one source that outranks it.**

---

## R6 — Exit codes and the `exp_id` join

### The reserved exit-code table today [VERIFIED: source]

| Code | Name | Owner | Meaning |
|------|------|-------|---------|
| 77 | `UI_GATE` (EX_NOPERM) | `kaggle_gateway.py` | 403 UI gate (rules / phone / permission) |
| 78 | `LIMIT_NEEDS_USER` (EX_CONFIG) | `kaggle_gateway.py` | Daily-limit extraction failed → SKILL must ask the user |
| 124 | — | `kaggle_gateway.run_kaggle` | `TimeoutExpired` (GNU-timeout convention) |
| 127 | — | `kaggle_gateway.run_kaggle` | `kaggle` CLI not on PATH |
| 126, 128+ | — | bash-reserved | Never use |
| 0/2/3/4 | `EXIT_COMPLETE`/`TERMINAL_FAIL`/`DETACHED`/`TRANSIENT_FAIL` | `poll_kernel.py` | **Script-LOCAL** small codes for poll outcomes |

Note the established two-tier convention: **global sysexits codes (77/78) live in the gateway**; **small
script-local codes (2/3/4) express a single script's outcomes.** Follow both.

### Recommended new codes (non-colliding, sysexits-aligned)

| Code | Proposed name | Where | Meaning |
|------|--------------|-------|---------|
| **65** | `VALIDATION_FAILED` (EX_DATAERR — *"the input data was incorrect"*) | gateway (shared) | D-02 pre-submit validation failed. Perfect semantic fit. |
| **75** | `GATE_BLOCKED` (EX_TEMPFAIL — *"temporary failure; the user is invited to retry"*) | gateway (shared) | D-05's block-by-default state. Not an error — a **retryable-after-human-confirmation** state. Exactly the sysexits meaning. |
| **69** | `SUBMIT_UNSUPPORTED` (EX_UNAVAILABLE) | gateway (shared) | D-01 refusal: `competition.type ∈ {code, unknown}`. The CSV path is unavailable for this competition type. |
| 0/2/3/4 | local | `submit.py` / `fetch_lb.py` | 0 = SCORED; 2 = submission FAILED (Kaggle `ERROR`); 3 = DETACHED (PENDING, re-run `fetch_lb`); 4 = transient/fail-closed. Mirrors `poll_kernel` exactly. |

None collide with 77/78/124/126/127/128+. `check_submission.py` then signals the three D-14 states cleanly:
**0 = clear to submit**, **75 = gate-blocked (not recommended)**, **65 = validation failed**, **69 = wrong
competition type**.

### The `exp_id` join — shapes it must read (READ-ONLY) [VERIFIED: source]

`experiment_meta.LEDGER_ROW_KEYS` — the exact 11 keys of a `control/ledger.jsonl` row:
```
exp_id, status, idea, metric, greater_is_better, cv_mean, cv_std,
git_commit, seed, created, verdict_path
```
✅ **Everything D-06 and D-10 need is already on the ledger row** — `exp_id`, `cv_mean`, `cv_std`,
`greater_is_better`, and `status` (filter to `"SUCCESS"`). **The join never needs to open `meta.json` at
all.** Read `control/ledger.jsonl`, which `rebuild_ledger.py` guarantees is a pure function of the folders.

⚠ **`meta.json` gains NO LB field (D-11).** The experiment folder stays immutable after record.

### Recommended `submissions.jsonl` row schema

```json
{
  "schema_version": 1,
  "exp_id": "exp-007",
  "kaggle_ref": 46780678,
  "competition_slug": "titanic",
  "file": "experiments/exp-007/submission.csv",
  "file_sha256": "sha256:9f2b…",
  "message": "exp-007 | cv=0.841230",
  "submitted_at": "2026-07-12T14:03:11Z",
  "status": "PENDING",
  "public_score": null,
  "private_score": null,
  "scored_at": null,
  "override_reason": null,
  "error_description": null
}
```

**Deliberately EXCLUDED: `cv_mean` / `cv_std`.** They are joinable from `ledger.jsonl` on `exp_id`;
denormalizing them would create the second source of truth D-11 exists to prevent. `public_score` /
`private_score` are stored as **parsed floats or `null`** (never Kaggle's `""` string) — numbers are
tooling-written. `file_sha256` uses the same `"sha256:" + hexdigest` format as
`record_experiment.provenance.artifact_hash`.

---

## Standard Stack

### Core (all already present — this phase adds NO dependency)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `kaggle` CLI | **2.2.3** [VERIFIED: `kaggle --version`, live] | `competitions submit` / `competitions submissions` | CLAUDE.md: the sole Kaggle primitive. kagglehub **cannot submit**. |
| Python stdlib `csv` | 3.11+ | D-02 pre-submit validation | Keeps the plumbing tier pandas-free (CLAUDE.md hard rule). |
| Python stdlib `json`, `hashlib`, `datetime`, `re`, `time`, `random`, `argparse` | 3.11+ | jsonl I/O, file hash, UTC boundary, status parse, backoff | Already the convention across all 20 scripts. |
| `numpy` (ML tier only) | ≥1.26 | Fold-prediction aggregation inside `run_cv` | Already imported by `run_cv`. |
| `pytest` | ≥8.0 | Mock-backed unit tests + the `live` marker | Established (`pyproject.toml`). |

**No new packages. No `pip install`. No Package Legitimacy Audit section is required** — this phase installs
nothing.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `competitions submissions` for the LB score | `competitions leaderboard` | Answers a different question (all teams' standings). No requirement needs it. **Rejected** — extra CLI surface to validate for zero value. |
| Counting rows for the budget | A quota API | **Does not exist** (live-verified: `kaggle quota` is GPU/TPU only). Not a choice. |
| Rewrite-in-place `submissions.jsonl` | Strict append-only event log | Event log is purer but forces every reader to fold events; the D-10/D-11 join wants one row per submission. **Recommended: rewrite-in-place, atomically.** |
| Refactor `poll_kernel.poll_loop` to be generic | Import `compute_delay`, write a small LB loop | Refactoring touches a completed, verified phase. **Recommended: import the tested math, don't fork the constants, don't touch Phase 4.** |
| Mean-aggregate all fold test predictions | Type-aware aggregation | Mean is **wrong** for `prediction_type == "label"` (titanic's `accuracy`). **Must** be type-aware. |

---

## Architecture Patterns

### System Architecture Diagram

```
                       control/config.json                control/ledger.jsonl
              (slug, metric{name,greater_is_better},   (exp_id, cv_mean, cv_std,
               submission{daily_limit,limit_provenance},     greater_is_better)
               competition.type)                                    │
                       │                                            │
                       ▼                                            ▼
  experiments/exp-NNN/submission.csv ──┐              ┌─────────────────────────────┐
        ▲  (D-09: run_cv fold-avg)     ├────────────▶ │   check_submission.py       │  ★ FREE
        │                              │              │  ─────────────────────────  │  (spends
   [ run_cv extension ]                │              │ 1. competition.type == csv? │   nothing)
   fold models already                 │              │    else ──▶ exit 69         │
   trained; transform X_test           │              │ 2. D-02 validate vs sample  │
   with the SAME fold's pp             │              │    fail  ──▶ exit 65        │
        │                              │              │ 3. Kaggle-authoritative     │
   local run ──┐                       │              │    budget count (D-04) ─────┼──▶ kaggle_gateway
   kernel run ─┴─▶ pull_kernel.py (flat)                │ 4. D-06 noise-aware CV cmp │    run_kaggle(
                                       │              │ 5. D-08 assumed-limit warn  │     "competitions",
                                       │              │ 6. RENDER decision material │     "submissions",
                                       │              └──────────────┬──────────────┘     slug, "--format",
                                       │                  exit 0 = clear                  "json",
                                       │                  exit 75 = BLOCKED (D-05)        "--page-size","200")
                                       │                             │                          │
                                       │                    ┌────────▼────────┐                 │
                                       │                    │  SKILL.md holds │                 ▼
                                       │                    │  the HUMAN loop │        ┌────────────────┐
                                       │                    │  (never stdin)  │        │  Kaggle API    │
                                       │                    └────────┬────────┘        │ (authoritative)│
                                       │                    human confirms             └────────┬───────┘
                                       │                             │                          ▲
                                       │              ┌──────────────▼──────────────┐           │
                                       └─────────────▶│        submit.py            │───────────┘
                                                      │  ─────────────────────────  │  competitions submit
                                                      │  hash file → sha256         │   -f … -m "exp-NNN …"
                                                      │  ⚠ rc==0 is NOT proof       │
                                                      │  match fail-open literals   │
                                                      │  READ BACK to CONFIRM ──────┼──▶ (submissions)
                                                      │  → get real `ref` id        │
                                                      │  bounded poll (D-03/R5)     │
                                                      └──────┬───────────────┬──────┘
                                          scored (exit 0)    │               │  budget expired → DETACH (exit 3)
                                          ERROR   (exit 2)   │               │
                                                             ▼               ▼
                                              control/submissions.jsonl   [ PENDING row persists —
                                              (CANONICAL, git-tracked,      the slot is NEVER lost ]
                                               one row per submission)              │
                                                             │                      ▼
                                                             │            ┌──────────────────┐
                                                             │◀───────────│   fetch_lb.py    │ (re-runnable,
                                                             │            │  PENDING → SCORED│  --reconcile)
                                                             │            └──────────────────┘
                                                             ▼
                                             ┌───────────────────────────────────┐
                                             │  regen_strategy.py (extended)     │
                                             │  DERIVED join on exp_id:          │
                                             │   submissions.jsonl × ledger.jsonl│
                                             │   → CV→LB gap trend (SCORE-02)    │
                                             │   → D-10 rank-inversion ALARM     │
                                             └───────────────────────────────────┘
                                                             │
                                                             ▼  (meta.json is NEVER written — D-11)
                                                        strategy.md
```

### Recommended file layout

```
scripts/
├── check_submission.py     # NEW — validate + decide + render (FREE, never spends a slot)
├── submit.py               # NEW — spend the slot; confirm by read-back; bounded-poll
├── fetch_lb.py             # NEW — detach fallback; PENDING → SCORED; --reconcile
├── submissions_log.py      # NEW — the ONE submissions.jsonl schema/read/write module
│                           #        (mirrors experiment_meta.py: importable, no main(),
│                           #         no side effects — the single source of the row schema)
├── kaggle_gateway.py       # EXTEND — add VALIDATION_FAILED=65, GATE_BLOCKED=75,
│                           #          SUBMIT_UNSUPPORTED=69
├── regen_strategy.py       # EXTEND — add the CV→LB gap + divergence-alarm facts block
└── templates/
    └── experiment.py.tmpl  # EXTEND — run_cv emits fold-averaged submission.csv (D-09)
control/
└── submissions.jsonl       # NEW — canonical, git-tracked (already un-ignored ✅)
references/
└── kaggle-cli-behavior.md  # EXTEND — the §R1/§R2 fixture entries above
```

`submissions_log.py` is the direct analogue of `experiment_meta.py`: it holds the row schema, the
`PENDING/SCORED/FAILED` enum, the status-literal parse, and the read/atomic-rewrite helpers — so all three
entry points **plus** `regen_strategy.py` import one module and the schema lives in exactly one place.

### Pattern 1: Confirm-by-read-back (the answer to the fail-open submit)

```python
# submit.py — NEVER trust rc == 0.
FAIL_OPEN_LITERALS = ("Could not find competition", "Could not submit to competition")

started = datetime.now(timezone.utc)
rc, out = run_kaggle("competitions", "submit", slug, "-f", str(csv_path),
                     "-m", message, timeout=300)
if rc != 0:
    dump_last_error(ws, out)                      # never echo the buffer
    return _classify_failure(rc, out, slug)       # 403 -> classify_gate -> exit 77
if any(lit in out for lit in FAIL_OPEN_LITERALS):
    dump_last_error(ws, out)
    print("submit failed: Kaggle rejected the upload (the CLI exits 0 even on failure — "
          "the framework detected the failure by matching its output). No slot was spent.",
          file=sys.stderr)
    return EXIT_TRANSIENT_FAIL

# rc == 0 and no failure literal — STILL not proof. The read-back IS the proof.
row = _find_our_submission(slug, exp_id, since=started)   # first poll tick, doubles as confirmation
if row is None:
    # fail closed: we cannot prove the submission landed. Do NOT record it as spent,
    # and do NOT claim success. Tell the user to check the Kaggle submissions page.
    return EXIT_TRANSIENT_FAIL
```

`_find_our_submission` matches on `description.startswith(exp_id)` **and** `date >= started`, returning the
newest match — which yields the Kaggle `ref` the submit call never gave us.

### Pattern 2: Parse the status literal by anchored regex, never by substring

```python
# submissions_log.py — mirrors poll_kernel._STATUS_RE (the VERIFIED-enum posture).
_SUB_STATUS_RE = re.compile(r"^(?:SubmissionStatus\.)?(PENDING|COMPLETE|ERROR)$")
_TO_OURS = {"PENDING": "PENDING", "COMPLETE": "SCORED", "ERROR": "FAILED"}

def parse_status(raw) -> str | None:
    """Return PENDING|SCORED|FAILED, or None (unparseable => TRANSIENT, never a false terminal)."""
    if not isinstance(raw, str):
        return None
    m = _SUB_STATUS_RE.match(raw.strip())
    return _TO_OURS[m.group(1)] if m else None

def parse_score(raw) -> float | None:
    """Kaggle gives publicScore as a STRING; '' means not-yet-scored. Never fabricate a 0.0."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None
```

### Pattern 3: The D-04 budget count (UTC-safe, D-13-correct)

```python
def charged_today(rows, now_utc) -> int:
    """Count TODAY's CHARGED submissions from Kaggle's authoritative list.
    ERROR rows are NOT charged (D-13) — Kaggle simply never billed them, so no
    special-case arithmetic is needed anywhere else. PENDING IS charged.
    """
    today = now_utc.date()
    n = 0
    for r in rows:
        st = parse_status(r.get("status"))
        if st is None or st == "FAILED":       # unparseable -> caller fails closed; FAILED -> free
            continue
        ts = parse_utc(r.get("date"))          # naive ISO -> UTC-aware. NEVER datetime.now() (local).
        if ts is None:
            return -1                          # sentinel: cannot count -> FAIL CLOSED (D-04)
        if ts.date() == today:
            n += 1
    return n

def parse_utc(raw):
    """Kaggle's `date` is a NAIVE ISO string with no tz suffix. Treat it as UTC (assumption A1)."""
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
```

### Pattern 4: The D-10 rank-inversion alarm (scale-free, direction-aware)

```python
def rank_inversions(pairs, greater_is_better):
    """pairs: [(exp_id, cv_mean, lb_score)] for SCORED submissions only.
    Fires when CV ordering disagrees with LB ordering — i.e. CV has stopped predicting LB.
    Scale-free: works identically for AUC, RMSE, LogLoss. Needs >= 2 scored points (be honest
    about that; never fake a signal from one).
    """
    def better(x, y):                       # is x better than y under the metric's direction?
        return x > y if greater_is_better else x < y

    inversions = []
    for (a_id, a_cv, a_lb), (b_id, b_cv, b_lb) in itertools.combinations(pairs, 2):
        if better(b_cv, a_cv) and better(a_lb, b_lb):     # CV says B wins; LB says A wins
            inversions.append((b_id, a_id, b_cv - a_cv, b_lb - a_lb))
    return inversions
```
**Note the LB direction:** Kaggle's `publicScore` is reported **in the competition's own metric**, so the
same `greater_is_better` applies to both sides of the comparison. The gap itself (`lb - cv`) is still computed
and trended per experiment (SCORE-02 requires the trend); **inversion is what raises the alarm** (D-10).

### Pattern 5: The D-06 noise-aware gate + the `k` constant

```python
NOISE_K_DEFAULT = 1.0      # config.json -> submission.noise_k (configurable, per CONTEXT)

def is_meaningful(cand_cv, cand_std, best_cv, greater_is_better, k=NOISE_K_DEFAULT):
    """Beat the best ALREADY-SUBMITTED CV by more than k * fold-std (D-06)."""
    margin = (cand_cv - best_cv) if greater_is_better else (best_cv - cand_cv)
    return margin > k * cand_std
```

**Recommended `k = 1.0`, and state the reasoning wherever it is rendered:** `cv_std` from `run_cv` is
`pstdev(fold_scores)` — the **population std of the fold scores**, *not* the standard error of the mean
(which would be `std/√n`, ~2.2× smaller at 5 folds). Requiring the gain to exceed **one full fold-std** is
therefore a deliberately **conservative** bar. That is the right default when the resource being protected is
a scarce, irreversible daily slot: the cost of a false "submit" (a wasted slot) exceeds the cost of a false
"blocked" (the human overrides in one keystroke — D-05 guarantees they can). Make it
`config.json → submission.noise_k` so a user in a high-variance competition can loosen it.

**Baseline case:** with **no** prior submitted experiments, there is no `best_cv` — the first submission is
**clear to submit** (not blocked). State that explicitly; do not let an empty comparison set produce a
spurious block.

### Pattern 6: Extending `regen_strategy.py` (don't fork it)

`regen_strategy.py` already renders tooling-owned FACTS (`_current_best_body`, `_tried_list_body`) and splices
AI reasoning, then **fully overwrites atomically** (D-12). Add **one more facts renderer** —
`_lb_gap_body(sub_rows, ledger_rows, greater_is_better)` — spliced into `_render()` alongside the existing
two. It emits:
- a small CV→LB table (exp_id, cv_mean, lb_score, gap) for SCORED submissions,
- remaining-slots-today if cheaply available,
- **the D-10 alarm block**, or the honest line *"Divergence alarm: needs ≥2 scored submissions (have N)."*

Do **not** add a new script, and do **not** let the AI author these numbers — they are tooling FACTS, exactly
like current-best.

### Anti-Patterns to Avoid

- **Trusting `submit`'s exit code.** It exits **0** on a 404 and on a failed upload. Confirm by read-back.
- **Substring-grepping `COMPLETE` in the status field.** Use the anchored regex; the literal is
  `SubmissionStatus.COMPLETE`.
- **`float(row["publicScore"])` unguarded.** It is a **string** and is `""` for every unscored/private row —
  this raises `ValueError` on the very first PENDING poll.
- **`datetime.now()` for the day boundary.** Local time silently miscounts the budget near midnight.
- **`np.mean` over fold predictions for a `label` metric.** Produces `0.6` where Kaggle wants `0`/`1`. Titanic
  is exactly this case.
- **Reaching for `--sandbox` as a dry run.** It is a host/admin flag, not a test mode.
- **Trying to paginate `submissions`.** The next-page token is discarded by the CLI. Use `--page-size 200`.
- **Writing the LB score into `meta.json`.** Forbidden (D-11) — the experiment folder is immutable after record.
- **Building `competitions leaderboard`, final selection, or the code-comp submit path.** Out of scope
  (D-12/D-01).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Running the `kaggle` CLI | A bare `subprocess.run` | `kaggle_gateway.run_kaggle` | D-16: one no-echo, timeout-bounded, exit-code-only runner. Bypassing it can leak a token-shaped string. |
| 403 / gate messaging | A new gate classifier | `kaggle_gateway.classify_gate` + `UI_GATE (77)` | Already fail-closed and live-verified; submit hits the same 403. |
| Quarantining a failed CLI buffer | `print(out)` | `kaggle_gateway.dump_last_error` | The buffer may carry a secret. Never echo. |
| Backoff/jitter math | New constants + a new `compute_delay` | Import `poll_kernel.compute_delay` | Already unit-tested (`test_backoff_budget`); full-jitter is provably budget-safe. |
| Daily submission quota | A local counter in `submissions.jsonl` | **Kaggle's `competitions submissions`** | D-04: only Kaggle knows about out-of-band submissions and un-charged errors. A local count enforces a **wrong budget with false confidence**. |
| The sample-submission filename | A new `sample_submission.csv` guess | `control/raw/competition-type-signals.json` → `signals.submission_csv_in_manifest` | Phase 2 already captured it; titanic's is `gender_submission.csv`. |
| The ledger row schema | Re-deriving keys | `experiment_meta.LEDGER_ROW_KEYS` / read `ledger.jsonl` | `cv_mean`, `cv_std`, `greater_is_better`, `exp_id` are all already there. |
| Atomic file rewrite | `open(...,'w')` | tempfile + `os.replace` (see `rebuild_ledger.py`) | A crash mid-write must leave the previous file intact. |
| CSV parsing in a skill script | pandas | stdlib `csv` | CLAUDE.md: the plumbing tier is stdlib-only. |

**Key insight:** every hard problem in this phase already has a solved analogue in this codebase — the
fail-open submit is Phase 4's "COMPLETE but threw"; the status literal is `KernelWorkerStatus`; the poller is
`poll_kernel`; the canonical/derived split is `meta.json`/`ledger.jsonl`. **The phase is mostly a careful
re-application of existing postures to a new, irreversible surface.** The genuinely new thinking is only in
the gate policy (D-05/D-06) and the fold-averaged prediction (D-09).

---

## Common Pitfalls

### Pitfall 1: Concluding success from `submit`'s exit code
**What goes wrong:** A typo'd slug or a failed upload exits **0**. The framework records a spent slot and a
`PENDING` submission that will never score, then blocks the next submission against a budget it never spent.
**Why it happens:** `competition_submit_cli` catches its own 404 and prints instead of raising; a failed
upload returns a message object rather than an error.
**How to avoid:** Match the two client-hardcoded failure literals **and** confirm by read-back. Never parse
the (server-authored) success string.
**Warning signs:** A `PENDING` row that never transitions; `submissions` shows no matching `description`.

### Pitfall 2: The `SubmissionStatus.` prefix
**What goes wrong:** `row["status"] == "COMPLETE"` is **always False** — the literal is
`"SubmissionStatus.COMPLETE"`. The poller then never terminates and detaches on every submission.
**How to avoid:** Anchored regex tolerating both renders (as `poll_kernel` already does for the kernel enum).
**Warning signs:** Every submission detaches; `fetch_lb` never finds a SCORED row.

### Pitfall 3: `publicScore` is a string, and `""` when unscored
**What goes wrong:** `float(row["publicScore"])` raises `ValueError` on the first PENDING poll — or, worse, a
defensive `float(x or 0)` silently records an **LB score of 0.0**, poisoning the CV→LB gap and firing a
bogus divergence alarm.
**How to avoid:** `parse_score()` returns `None` on `""`. A `None` score is **never** written as a number.
**Warning signs:** LB scores of exactly `0.0`; a divergence alarm on the first two submissions.

### Pitfall 4: The UTC day boundary (the budget's silent failure)
**What goes wrong:** `date` is naive. Comparing against local time miscounts the day near midnight — the
framework refuses a submission the user is entitled to, or (worse) permits one over the limit.
**How to avoid:** `datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)` vs
`datetime.now(timezone.utc).date()`.
**Warning signs:** The count changes when the developer's TZ changes. Add a unit test that runs under
`TZ=Pacific/Kiritimati` (UTC+14) and `TZ=Pacific/Midway` (UTC-11) and asserts an identical count.

### Pitfall 5: Fold-averaging hard labels
**What goes wrong:** `submission.csv` contains `0.6` where Kaggle expects `0`/`1`. D-02's validator (headers,
row count, id set, no blanks) **passes it** — so a real slot is spent on a malformed file, and the LB score
comes back meaningless (or the submission errors).
**Why it happens:** `prediction_type == "label"` (accuracy/f1/qwk/mcc) is a *classification* path where the
mean of fold predictions is not a member of the label set. **Titanic's `accuracy` is this path.**
**How to avoid:** Type-aware aggregation (soft-vote-then-argmax, majority-vote fallback) + the integer-column
sanity warning in `check_submission.py`.
**Warning signs:** Non-integral values in a prediction column whose sample counterpart is all-integer.

### Pitfall 6: Losing a spent slot on a detach
**What goes wrong:** The LB poll budget expires, the script exits non-zero, and nothing is written — the slot
is spent but invisible. The budget count self-corrects (D-04 reads Kaggle), but the **provenance is gone**:
no `exp_id` ↔ `ref` link, so the CV→LB gap for that experiment can never be computed.
**How to avoid:** Write the `PENDING` row **before/immediately after** the submit is confirmed, and *then*
poll. Detach only flips status. D-03's "never lose a spent slot" is a **write-ordering** requirement.
**Warning signs:** A Kaggle submission with no corresponding `submissions.jsonl` row (catchable by
`fetch_lb --reconcile`).

### Pitfall 7: Re-running `submit.py` and double-spending
**What goes wrong:** D-14 requires idempotent entry points, but `submit` is inherently **not** idempotent —
re-running it spends a second slot.
**How to avoid:** `submit.py` must first check `submissions.jsonl` for an existing row with the same
`exp_id` **and** the same `file_sha256`. If found and not FAILED, **refuse** and point to `fetch_lb.py`.
Idempotence here means "re-running is safe", not "re-running re-submits". Require an explicit
`--resubmit` for a genuine second submission of the same file.
**Warning signs:** Two identical-hash rows for one `exp_id`.

---

## Code Examples

### Reading the authoritative submission list through the gateway

```python
# Source: live-verified CLI 2.2.3 surface (§R2) + scripts/kaggle_gateway.py (D-16)
from kaggle_gateway import run_kaggle, _parse_json_array, dump_last_error

def fetch_submissions(slug, timeout=60):
    """Return Kaggle's authoritative submission list (newest first), or None (=> FAIL CLOSED).

    --page-size 200 is the MAX and a single page always covers today (sort is date-desc and
    daily limits are <= ~10). --page-token is USELESS: the CLI discards next_page_token.
    """
    rc, out = run_kaggle("competitions", "submissions", slug,
                         "--format", "json", "--page-size", "200", timeout=timeout)
    if rc != 0:
        return None                       # includes 403 (gate) and 1 (auth) — caller classifies
    rows = _parse_json_array(out.strip()) # CLI 2.2.3 PRETTY-PRINTS json across many lines
    return rows if isinstance(rows, list) else None
```
Note the reuse of `_parse_json_array` — Phase 2 already learned (and pinned in
`references/kaggle-cli-behavior.md`) that `--format json` is **pretty-printed across many lines**, so a
last-line parse fails. The same is true here (live-confirmed: the array starts with `"[\n  {\n    \"ref\":"`).

### The D-09 harness extension (the seam, in context)

```python
# Source: scripts/templates/experiment.py.tmpl :: run_cv (lines 100-162), extended.
def run_cv(*, X, y, model_factory, preprocess_factory=None, feature_fn=None,
           metric, registry_entry, cv_scheme, n_splits=5, seed=DEFAULT_SEED,
           groups=None, splitter=None, exp_dir=".", prediction_type=None,
           # --- D-09 (all optional: absent => no submission.csv, CV still records) ---
           X_test=None, test_ids=None, id_column=None, target_column=None,
           submission_agg=None):
    import numpy as np
    ...
    Xte_v = None if X_test is None else np.asarray(feature_fn(X_test) if feature_fn else X_test)
    test_preds, test_probas = [], []

    for tr, va in split.split(*split_args):
        ...
        model = model_factory()
        model.fit(Xtr, ytr)
        ...  # existing val scoring, unchanged

        # --- D-09: predict test with THIS fold's model + THIS fold's fitted pp ---
        if Xte_v is not None:
            Xte = pp.transform(Xte_v) if preprocess_factory is not None else Xte_v
            if ptype == "proba":
                p = model.predict_proba(Xte)
                test_preds.append(p[:, 1] if p.shape[1] == 2 else p)
            elif ptype == "label" and hasattr(model, "predict_proba"):
                test_probas.append(model.predict_proba(Xte))   # soft-vote then argmax
                test_preds.append(model.predict(Xte))          # majority-vote fallback
            else:
                test_preds.append(model.predict(Xte))          # raw regression

    result = {... existing keys ...}
    result["submission_path"] = None

    if test_preds:
        agg = submission_agg or _default_agg          # AI escape hatch (Phase 3 D-07)
        final = agg(test_preds, ptype, test_probas, getattr(model, "classes_", None))
        sub_path = Path(exp_dir) / "submission.csv"   # FLAT — rides pull_kernel unchanged
        with open(sub_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([id_column, target_column])
            w.writerows(zip(test_ids, final))
        result["submission_path"] = "submission.csv"
        result["artifacts"] = result["artifacts"] + ["submission.csv"]

    (Path(exp_dir) / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
```

---

## State of the Art

| Old assumption | Verified reality (2026-07-12, CLI 2.2.3) | Impact |
|----------------|------------------------------------------|--------|
| `kaggle competitions submit` returns non-zero on failure | **Exits 0** on a 404 slug and on a failed upload | `submit.py` must confirm by read-back. **The single most important finding.** |
| The CLI gives you a submission id | It discards `.ref`, returning only `.message` | Correlate via the `-m` message → `description` round-trip. |
| CLAUDE.md Open Risk: *"code/notebook-only competition submission (MEDIUM) — the exact flow should be validated"* | **Resolved for v1 by scoping.** The flags are `-k <owner>/<slug> -v <version> -f <output-name>` and require **both** `-k` and `-v` (else `ValueError`). D-01 refuses this path. | The refusal message can be precise about *why* (it needs a pushed kernel version, not a CSV). No slot is ever spent to find out. |
| STATE.md: *"code-competition submission path needs validation; may need a competition-type flag"* | **Both halves closed:** Phase 2 D-14 captured `competition.type`; D-01 scopes the code path out. The CLI surface for it is now documented anyway (above). | The STATE.md blocker can be marked resolved. |
| `--format json` might be single-line | **Pretty-printed across many lines** (already pinned in Phase 2) | Reuse `_parse_json_array`, never a last-line parse. |
| A quota API might expose remaining submissions | **`kaggle quota` is GPU/TPU hours only** | D-04 must count rows. Settled. |

**Deprecated/absent:**
- `--page-token` on `submissions`: **functionally dead** — the CLI never emits the token to chain.
- `errorDescription` on a submission: exists in the API model, **not exposed** by the CLI (projection can only
  narrow the fixed 7-field list).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| **A1** | The `date` field returned by `competitions submissions` is **UTC** (it is a naive ISO string with no tz suffix). | §R2, Pattern 3 | **HIGH — the budget count is wrong near the day boundary.** Could refuse a legitimate submission or permit one over the limit. **Mitigation: `checkpoint:human-verify` at the first real submit** — record the UTC wall-clock at submit and compare it to the returned `date`. Then pin it in `references/kaggle-cli-behavior.md`. |
| **A2** | The `submit` **success** message is server-authored and must not be parsed. | §R1 | LOW — the design deliberately never depends on it (read-back is the proof). Recorded so no one is tempted to add a happy-path string match later. |
| **A3** | Kaggle does not charge a slot for `ERROR` submissions (from CLAUDE.md; unverifiable without deliberately submitting a broken file). | D-13, Pattern 3 | LOW — D-04's Kaggle-authoritative count makes this **self-correcting**: if Kaggle *did* charge it, Kaggle's own count would reflect that and the gate would still be right. The assumption only affects our *explanatory text*, not the arithmetic. This is a genuine design win of D-04. |
| **A4** | `record_experiment.py`'s result-schema gate tolerates the new additive `submission_path` key in `result.json`. | §R3 | MEDIUM — if the gate is strict-keys, every experiment records **FAILED**. **Planner: verify by reading the validator before writing the task.** Cheap to check, expensive to miss. |
| **A5** | A competition's submission file wants the same prediction form the metric consumes (`prediction_type`). | §R3 | MEDIUM — D-02's validation against the sample file is the backstop, and `submission_agg` is the escape hatch. Documented in the harness docstring rather than auto-detected. |

---

## Open Questions

1. **Is `submissions.date` really UTC?** (= A1)
   - *Known:* it is a naive ISO string; Kaggle's API convention is UTC; the SDK parses a wire timestamp.
   - *Unclear:* cannot be proven without making a submission and comparing to a known clock.
   - *Recommendation:* implement as UTC, and put a **`checkpoint:human-verify`** in the first plan that
     performs a real submission — capture the submit-time UTC clock and the returned `date`, then record the
     result in `references/kaggle-cli-behavior.md`. This is the one thing that genuinely requires a live slot,
     and it comes free with the first real end-to-end submission.

2. **How does the AI supply `X_test` / `test_ids` in the scaffold?**
   - *Known:* the AI edits the marked block of `main()` and already loads `train.csv` there.
   - *Unclear:* whether the scaffolded starter should pre-load `test.csv` (making the common path zero-effort)
     or leave it to the AI (keeping the diagnostic path clean).
   - *Recommendation:* **pre-load it in the template's AI-edited block, guarded** — `test_path = data_dir /
     "test.csv"; test = pd.read_csv(test_path) if test_path.exists() else None` — so the common case emits a
     submission automatically while a diagnostic experiment (or a competition with no `test.csv`) still runs.
     This satisfies D-09's "optional/graceful" without making the AI remember anything.

3. **What is the id column / target column name?**
   - *Known:* it is the sample file's header — which `check_submission.py` reads anyway.
   - *Unclear:* the *harness* (which writes the file) runs before validation and, on a kernel, has no access
     to `control/`.
   - *Recommendation:* have `scaffold_experiment.py` **render the sample header into the template** (the same
     way it already renders `registry_entry`, `SLUG`, `METRIC_NAME` as literals). This keeps the kernel-
     portability contract intact (the experiment imports no skill code) and means the harness writes a
     correctly-headed file by construction. If the header is unavailable at scaffold time, render `None` and
     the harness skips submission emission — graceful, per D-09.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `kaggle` CLI | submit + read-back | ✓ | **2.2.3** (`.venv/bin/kaggle`) | none needed |
| Kaggle credentials | all live calls | ✓ | `~/.kaggle/access_token`, mode 600 | none needed |
| Python | all scripts | ✓ | 3.13 (project floor 3.11) | — |
| `pytest` | validation | ✓ | ≥8.0 (`live` marker configured) | — |
| numpy / pandas / sklearn / lightgbm | ML tier only (`experiment.py`) | ✓ (workspace env) | per `uv.lock` | Harness degrades: `run_local.py` already errors clearly if the ML env is absent |
| `api.kaggle.com`, `storage.googleapis.com` egress | submission upload | ✓ | allowlisted (`references/egress-allowlist.md`) | none needed |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

**This phase adds zero new dependencies.**

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥8.0 |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]`, `testpaths = ["tests"]`, `addopts = "-m 'not live'"` |
| Quick run command | `uv run pytest tests/test_submit.py tests/test_check_submission.py -x -q` |
| Full suite command | `uv run pytest` (live suite excluded by default) |
| Live suite (opt-in) | `uv run pytest -m live` — **READ-ONLY calls only; see the hard rule below** |

### ⭐ How to test the submit path WITHOUT ever spending a slot

This is the phase's defining validation constraint — a real submission is **irreversible** and consumes a
scarce resource. Four layers, all using **conventions that already exist in this repo**:

1. **Mock-backed unit tests (the primary layer).** The established pattern is
   `monkeypatch.setattr(module, "run_kaggle", fake)` — see `tests/test_gateway.py::_fake_run_kaggle`. Every
   `submit.py` / `check_submission.py` / `fetch_lb.py` test injects a fake gateway. **No real CLI process is
   ever spawned.** Tests assert on the **argv** the fake receives — which is how we prove the exact command
   shape (including that `-k`/`-v`/`--sandbox` are **never** passed) without executing it.

2. **Recorded fixtures from THIS research.** Mirror the existing `tests/fixtures/status/*.txt` pattern with
   `tests/fixtures/submissions/*.json` containing the **live-captured shapes** documented in §R2:
   `complete.json` (SCORED, real `SubmissionStatus.COMPLETE` + string score), `pending.json`,
   `error.json`, `empty.json` (`No submissions found`), `unscored.json` (`publicScore: ""`),
   `submit_404.txt` / `submit_upload_failed.txt` (the two **fail-open** stdout literals).
   Phase 2 learned the hard way (recorded in `references/kaggle-cli-behavior.md`) that hand-built fixtures can
   miss the real shape — **these are transcribed from live output, not invented.**

3. **A source-level guard test (the irreversibility guarantee).** Following
   `test_poll_kernel.py::test_source_routes_through_gateway` (which greps the module source), add:
   ```python
   def test_no_live_test_ever_submits():
       """HARD RULE: no @pytest.mark.live test may invoke `competitions submit`.
       A live test that submits would spend a real, irreversible slot on every CI run."""
       for p in Path("tests").glob("test_*live*.py"):
           src = p.read_text()
           assert "competitions\", \"submit" not in src and "competitions submit" not in src
   ```
   Cheap, mechanical, and it makes the constraint **enforced rather than remembered**.

4. **A `--dry-run` flag on `submit.py`.** Prints the exact argv it *would* pass to the gateway and exits 0
   **without calling it**. Gives a human an inspectable pre-flight and gives tests a no-mock path.
   (This is distinct from `check_submission.py`, which answers *"should I?"*; `--dry-run` answers *"with
   exactly what command?"*.)

**Live tests may call ONLY `competitions submissions` (read-only).** One high-value live canary is worth
having: assert the seven JSON keys and the `SubmissionStatus.` prefix still hold — a **CLI-drift alarm** that
would catch Kaggle changing the shape out from under us. It spends nothing.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCORE-01 | `submit.py` builds the exact argv (`submit <slug> -f … -m "exp-NNN …"`), never `-k`/`-v`/`--sandbox` | unit (mock gw) | `uv run pytest tests/test_submit.py::test_argv_shape -x` | ❌ Wave 0 |
| SCORE-01 | **rc==0 + `Could not find competition` ⇒ FAILURE, not success** (fail-open guard) | unit | `uv run pytest tests/test_submit.py::test_fail_open_404_is_not_success -x` | ❌ Wave 0 |
| SCORE-01 | **rc==0 + `Could not submit to competition` ⇒ FAILURE** | unit | `uv run pytest tests/test_submit.py::test_fail_open_upload_is_not_success -x` | ❌ Wave 0 |
| SCORE-01 | rc==0 + read-back finds no matching row ⇒ fail closed (never claims success) | unit | `uv run pytest tests/test_submit.py::test_unconfirmed_submission_fails_closed -x` | ❌ Wave 0 |
| SCORE-01 | Read-back correlates on `description` prefix + `date >= started`, yields the Kaggle `ref` | unit | `uv run pytest tests/test_submit.py::test_correlates_by_exp_id -x` | ❌ Wave 0 |
| SCORE-01 | `"SubmissionStatus.COMPLETE"` → `SCORED`; bare `COMPLETE` also parses; garbage → `None` (never a false terminal) | unit | `uv run pytest tests/test_submissions_log.py::test_parse_status -x` | ❌ Wave 0 |
| SCORE-01 | `publicScore` `""` → `None` (never `0.0`); `"0.77511"` → `0.77511` | unit | `uv run pytest tests/test_submissions_log.py::test_parse_score -x` | ❌ Wave 0 |
| SCORE-01 | LB poll: bounded budget, full jitter ≤ cap, **DETACH on expiry** (row stays PENDING, slot not lost) | unit (injected clock) | `uv run pytest tests/test_fetch_lb.py::test_detach_preserves_pending -x` | ❌ Wave 0 |
| SCORE-01 | `fetch_lb.py` is re-runnable: PENDING → SCORED, idempotent on a second run | unit | `uv run pytest tests/test_fetch_lb.py::test_idempotent_resume -x` | ❌ Wave 0 |
| SCORE-01 | `submit.py` **refuses a duplicate** (same `exp_id` + `file_sha256`) without `--resubmit` | unit | `uv run pytest tests/test_submit.py::test_refuses_double_spend -x` | ❌ Wave 0 |
| SCORE-01 | `competition.type ∈ {code, unknown}` ⇒ exit 69, **gateway never called** | unit | `uv run pytest tests/test_check_submission.py::test_refuses_non_csv_type -x` | ❌ Wave 0 |
| SCORE-01 (D-09) | `run_cv` with `X_test` emits `submission.csv`; **without it, still records a valid CV result** | unit (tiny sklearn fixture) | `uv run pytest tests/test_run_cv.py::test_submission_optional -x` | ⚠ extend existing `tests/test_run_cv.py` |
| SCORE-01 (D-09) | **`label` metrics vote, never mean** (a 5-fold 0/1 aggregate contains only 0/1) | unit | `uv run pytest tests/test_run_cv.py::test_label_aggregation_is_not_mean -x` | ⚠ extend |
| SCORE-01 (D-09) | `proba`/`raw` metrics **mean** across folds; test preds use each fold's own fitted `pp` (no leakage) | unit | `uv run pytest tests/test_run_cv.py::test_test_preds_use_fold_preprocessor -x` | ⚠ extend |
| SCORE-02 | CV→LB gap computed per SCORED submission; unscored rows excluded | unit | `uv run pytest tests/test_lb_gap.py::test_gap_trend -x` | ❌ Wave 0 |
| SCORE-02 | **Rank-inversion alarm fires** on (CV better, LB worse), direction-aware for both `greater_is_better` values | unit | `uv run pytest tests/test_lb_gap.py::test_rank_inversion_alarm -x` | ❌ Wave 0 |
| SCORE-02 | Alarm is **honest with <2 scored** submissions (states it, never fabricates a signal) | unit | `uv run pytest tests/test_lb_gap.py::test_alarm_needs_two_points -x` | ❌ Wave 0 |
| SCORE-02 | `regen_strategy.py` renders the LB block from tooling facts; AI reasoning still spliced; full overwrite preserved | unit | `uv run pytest tests/test_regen_strategy.py::test_lb_block_rendered -x` | ⚠ extend |
| SCORE-02 | LB score is **never** written into `meta.json` (D-11 immutability) | unit | `uv run pytest tests/test_submit.py::test_meta_json_untouched -x` | ❌ Wave 0 |
| SCORE-03 | Budget counts **today's** rows, **excludes ERROR** (D-13), **includes PENDING** | unit | `uv run pytest tests/test_budget.py::test_charged_today -x` | ❌ Wave 0 |
| SCORE-03 | **UTC boundary**: identical count under `TZ=Pacific/Kiritimati` (+14) and `TZ=Pacific/Midway` (−11) | unit (TZ-parametrized) | `uv run pytest tests/test_budget.py::test_utc_day_boundary -x` | ❌ Wave 0 |
| SCORE-03 | Unfetchable/unparseable count ⇒ **fail closed** (block; never guess) | unit | `uv run pytest tests/test_budget.py::test_fails_closed_when_count_unavailable -x` | ❌ Wave 0 |
| SCORE-03 | D-06 gate: gain ≤ `k·cv_std` ⇒ **exit 75 BLOCKED**; gain > `k·cv_std` ⇒ exit 0 clear; **first-ever submission ⇒ clear** | unit | `uv run pytest tests/test_gate_policy.py -x` | ❌ Wave 0 |
| SCORE-03 | D-08: `limit_provenance == "assumed_default"` ⇒ warning **every time**; the **last** assumed slot ⇒ blocked pending confirmation | unit | `uv run pytest tests/test_gate_policy.py::test_assumed_limit_last_slot -x` | ❌ Wave 0 |
| SCORE-03 | `check_submission.py` **never calls `competitions submit`** (it is free) | unit (argv assertion) | `uv run pytest tests/test_check_submission.py::test_never_submits -x` | ❌ Wave 0 |
| D-02 | Validation catches each of: header mismatch, row-count mismatch, id-set mismatch, blank/NaN prediction — each with a precise message; exit 65 | unit | `uv run pytest tests/test_check_submission.py::test_validation_matrix -x` | ❌ Wave 0 |
| D-02 | Sample file resolved via `submission_csv_in_manifest` (**`gender_submission.csv`**), then glob, then `test.csv` fallback | unit | `uv run pytest tests/test_check_submission.py::test_sample_resolution_ladder -x` | ❌ Wave 0 |
| SECURITY | Raw CLI buffer is **never echoed**; a token-shaped string in submit output is quarantined, not printed | unit | `uv run pytest tests/test_no_credential_leak.py -x` | ⚠ extend |
| SAFETY | **No `live`-marked test invokes `competitions submit`** | source guard | `uv run pytest tests/test_submit.py::test_no_live_test_ever_submits -x` | ❌ Wave 0 |
| DRIFT | Live canary: `submissions --format json` still yields the 7 keys + `SubmissionStatus.` prefix | live (read-only) | `uv run pytest -m live tests/test_submission_live.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_submit.py tests/test_check_submission.py tests/test_budget.py -x -q`
- **Per wave merge:** `uv run pytest` (full mock suite; live excluded)
- **Phase gate:** full suite green + `uv run ruff check scripts/` before `/gsd:verify-work`
- **Live gate (once, human-supervised):** the first real end-to-end submission — which is also the
  **A1 UTC checkpoint** and the source of the `references/kaggle-cli-behavior.md` success-path entry.

### Wave 0 Gaps

- [ ] `tests/test_submissions_log.py` — status/score parse, row schema, atomic rewrite (SCORE-01/02)
- [ ] `tests/test_check_submission.py` — validation matrix, sample resolution, never-submits, type refusal (SCORE-01/03, D-02)
- [ ] `tests/test_submit.py` — argv shape, **fail-open guards**, read-back correlation, double-spend refusal, meta.json immutability, live-submit source guard (SCORE-01)
- [ ] `tests/test_fetch_lb.py` — detach/resume, idempotence, PENDING→SCORED (SCORE-01)
- [ ] `tests/test_budget.py` — charged-today, ERROR-excluded, **UTC boundary (TZ-parametrized)**, fail-closed (SCORE-03)
- [ ] `tests/test_gate_policy.py` — D-05/D-06/D-08 gate matrix (SCORE-03)
- [ ] `tests/test_lb_gap.py` — gap trend + rank-inversion alarm + <2-point honesty (SCORE-02)
- [ ] `tests/test_submission_live.py` — read-only CLI-drift canary (`-m live`)
- [ ] `tests/fixtures/submissions/*.json` + `submit_*.txt` — **live-captured** shapes from §R1/§R2
- [ ] Extend `tests/test_run_cv.py` — D-09 optional emission, label-vs-mean aggregation, fold-pp reuse
- [ ] Extend `tests/test_regen_strategy.py` — the LB/gap facts block
- [ ] Framework install: **none needed** (pytest ≥8.0 already configured with the `live` marker)

---

## Security Domain

`security_enforcement` is not disabled in `.planning/config.json`, so this section applies. This is a local
CLI skill (no server, no browser, no session) — most ASVS categories are N/A by construction.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | **yes** (delegated) | Kaggle API token, already validated by `check_credentials.py`. This phase adds **no new credential surface** — it reuses the gateway. |
| V3 Session Management | no | No sessions. |
| V4 Access Control | **yes** (remote) | Kaggle's own 403 gates (rules acceptance / phone verification). Already handled by `kaggle_gateway.classify_gate` → exit 77; submit hits the same 403. |
| V5 Input Validation | **yes** | `submission.csv` (ours) validated with stdlib `csv` (D-02). **Kaggle's response text is untrusted input** — see below. |
| V6 Cryptography | **yes** (hashing only) | `hashlib.sha256` for the submission-file hash. No hand-rolled crypto. |
| V7 Error Handling & Logging | **yes** | Raw CLI buffers are **never echoed** (they may carry a token-shaped string) — quarantined via `dump_last_error` to the gitignored `control/raw/last-error.txt`. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential leak via echoed CLI output | Information Disclosure | `run_kaggle` captures both streams and **never prints them** (D-16). Already enforced by `tests/test_no_credential_leak.py` — **extend it to the new scripts.** |
| **Untrusted Kaggle-authored text** (`description`, error messages) driving a path/command | Tampering / Injection | `description` is *our* text round-tripped, but must still be treated as **untrusted on read** (the `scripts/untrusted.py` posture). Match `exp_id` with a **strict anchored regex** (`^exp-\d{3}\b`); **never** derive a filesystem path or subprocess argv from it. |
| Committing a credential or a large artifact | Information Disclosure | `.gitignore` already covers `access_token`/`kaggle.json`/`.env` and `experiments/*/*.csv`; `leak_scan.py` pre-commit hook. `control/submissions.jsonl` is small provenance and is **correctly tracked** (no secret content). |
| **Spending an irreversible resource in an automated loop** | *(project-specific — the real threat here)* | **D-05's block-by-default gate + the human-in-the-loop confirmation is the control.** Reinforced by: `check_submission.py` never calling submit, the `--dry-run` flag, and the **source-guard test forbidding any live test from submitting.** |
| Path traversal via `--exp-dir` | Tampering | Known, deferred low-risk (IN-01, carried from Phase 3). **Do not regress it** — `submit.py` takes `--exp-id`/`--exp-dir` on the same footing; resolve and confine under `ws/experiments/`. |

---

## Sources

### Primary (HIGH confidence — live-verified in this session, 2026-07-12)

- **Installed `kaggle` CLI 2.2.3** (`/home/rjsins/Documents/Projects/Kaggle-skill/.venv/bin/kaggle`):
  - `kaggle competitions submit --help`, `kaggle competitions submissions --help`,
    `kaggle competitions leaderboard --help`, `kaggle quota --help`
  - **READ-ONLY live calls** (spent nothing): `kaggle competitions submissions titanic --format json`
    (+ `--page-size 200`, `-v` CSV, and a projection-error probe), `kaggle quota --format json`,
    error-path probes on a bogus slug and an un-entered competition.
  - **`kaggle competitions submit` was NEVER executed.**
- **Installed package source** (`.venv/lib/python3.13/site-packages/`):
  - `kaggle/api/kaggle_api_extended.py` — `competition_submit` (~1685), `competition_submit_cli` (~1743, the
    **fail-open 404 swallow**), `competition_submit_code` (~1637), `competition_submissions` (~1798),
    `competition_submissions_cli` (~1855), `submission_fields` (line 849), `_resolve_projection` (~1010),
    `get_json_serializable` (~6695, the **`str(enum)`** serialization).
  - `kaggle/cli.py::main` (line 35) — the exit-code contract (`error=True` only for `HTTPError` /
    `ApiException` / `ValueError`; **everything else exits 0**).
  - `kagglesdk/competitions/types/submission_status.py` — **`SubmissionStatus{PENDING=0, COMPLETE=1,
    ERROR=2}`**.
  - `kagglesdk/competitions/types/competition_api_service.py` — `ApiSubmission` fields (incl. the
    **unexposed** `error_description`), `SubmissionSortBy`, `SubmissionGroup`.
- **This project's own source** (read directly, not assumed): `scripts/kaggle_gateway.py`,
  `scripts/poll_kernel.py`, `scripts/pull_kernel.py`, `scripts/capture_competition.py`,
  `scripts/experiment_meta.py`, `scripts/rebuild_ledger.py`, `scripts/regen_strategy.py`,
  `scripts/metric_registry.py`, `scripts/record_experiment.py`, `scripts/templates/experiment.py.tmpl`,
  `scripts/templates/gitignore.tmpl`, `scripts/templates/strategy.md.tmpl`, `tests/conftest.py`,
  `tests/test_gateway.py`, `tests/test_poll_kernel.py`, `pyproject.toml`, `SKILL.md`.
- **Planning artifacts:** `05-CONTEXT.md`, `REQUIREMENTS.md` (§Scoring), `ROADMAP.md` (§Phase 5),
  `STATE.md` (§Blockers), `PROJECT.md` (§Out of Scope), `CLAUDE.md`,
  `references/kaggle-cli-behavior.md`, `references/egress-allowlist.md`.

### Secondary (MEDIUM confidence)

- `CLAUDE.md` §"Kaggle Integration — Concrete Command Surface" — daily limit ~5/day; failed submissions not
  charged (secondary source summarizing kaggle.com/docs; **A3** — and D-04's design makes it self-correcting).

### Tertiary (LOW confidence)

- None. **No claim in this document rests on WebSearch or on training data alone.** Every CLI fact was
  read from the installed source or observed live.

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|------|-------|--------|
| R1 — submit surface + **fail-open exit code** | **HIGH** | Read directly from the installed CLI source + live `--help`. The only gap (the server-authored success string) is one the design deliberately never depends on. |
| R2 — submissions read-back shape + status literals | **HIGH** | Live JSON captured; enum read from `kagglesdk`; the 7-field allow-list confirmed by triggering the CLI's own projection error. |
| R2 — **`date` is UTC** | **MEDIUM** [ASSUMED] | Naive ISO with no tz suffix. Unprovable without a real submission. **A1 — gate behind a human-verify checkpoint at first submit.** |
| R2 — no quota command | **HIGH** | `kaggle quota` live-run: GPU/TPU only. |
| R3 — `run_cv` seam + the label-aggregation trap | **HIGH** | Read the actual 229-line template + `metric_registry.REGISTRY`. Titanic's `accuracy` → `prediction_type == "label"` is verifiable from the registry table. |
| R4 — sample-file resolution | **HIGH** | Read `capture_competition.classify_competition_type` and the `control/raw/competition-type-signals.json` write. |
| R5 — poller shape + constants | **HIGH** (shape) / **MEDIUM** (constants) | Shape read from source. The LB constants are a reasoned recommendation (explicitly Claude's discretion per CONTEXT) — tune to observed behavior. |
| R6 — exit codes + join keys | **HIGH** | Read the gateway's reserved table and `experiment_meta.LEDGER_ROW_KEYS`. Proposed 65/75/69 are sysexits-aligned and provably non-colliding. |
| Validation architecture | **HIGH** | Built on the repo's existing, working conventions (`monkeypatch` the gateway; `tests/fixtures/status/` pattern; `-m live` exclusion). |

**Research date:** 2026-07-12
**Valid until:** ~2026-08-11 (30 days). The CLI surface is GA and stable, but the live drift-canary test
(`tests/test_submission_live.py`) exists precisely so a shape change is caught mechanically rather than by
re-reading this document.
