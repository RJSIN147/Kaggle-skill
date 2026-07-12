# Phase 5: Submission & Leaderboard Tracking - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Predictions reach the competition leaderboard under **mechanical CV-first discipline** — the
scarce daily submission budget is **gated and tracked**, and the CV→LB gap is **trended with a
divergence alarm**. This is the final v1 phase; it layers on top of the proven local loop
(Phase 3) and consumes Phase 4 kernel output when a kernel produced the predictions.

**In scope:** SCORE-01, SCORE-02, SCORE-03 — CSV submission via the Kaggle CLI, async LB
read-back into `submissions.jsonl` (exp id + file hash), pre-submit file validation that never
wastes a slot, the CV→LB gap trend with a rank-inversion divergence alarm, and a
submission-budget model (UTC-aware, Kaggle-authoritative) with a CV-improvement gate.

**One necessary extension into Phase 3's territory (D-09 — NOT scope creep, a discovered gap):**
Phase 3's `run_cv` harness computes cross-validation and emits `result.json` + artifacts — it does
**not** predict on test, so **`submission.csv` does not currently exist**. Phase 5 therefore
extends the Phase 3 scaffold/harness to emit test predictions. Without this, SCORE-01 has nothing
to submit. This is the direct analogue of Phase 3's D-08 `config.metric` gap.

**Explicitly NOT in this phase (boundary guards):**
- **Code-competition (notebook→submit) flow is OUT of v1** (D-01). Only the CSV path is built.
  `competition.type ∈ {code, unknown}` **refuses** with a clear instruction rather than spending a
  slot (honoring Phase 2 D-14).
- **Final-selection / nomination is OUT of v1** (D-12) — ⚠ **a deliberate deviation from roadmap
  plan 05-02**, which names a "CV-based final-selection rule". The user explicitly scoped it out.
  The planner must NOT build it. The ledger + LB history give the user what they need to nominate
  manually in the Kaggle UI.
- **The experiment representation, ledger schema, result contract, and strategy mechanics are
  LOCKED by Phase 3** and are extended here, never re-derived. Numbers stay tooling-written.
- **The experiment folder stays immutable after record** (Phase 3) — the LB score is never written
  back into `meta.json` (D-11).
- **No GPU-quota budget model.** Phase 4 deliberately stopped at a non-blocking heads-up (D-13);
  Phase 5 builds the *submission* budget only, not a GPU-hour budget.

</domain>

<decisions>
## Implementation Decisions

### Submit path & scope (SCORE-01, criterion 1)

- **D-01: CSV-only submit path for v1.** `05-01` targets
  `kaggle competitions submit -f submission.csv` for `competition.type == csv`. For
  `competition.type ∈ {code, unknown}` the submit path **refuses with a clear, framework-authored
  instruction and never spends a slot** (the Phase 2 D-14 contract). The code-competition
  (notebook-version) submission flow is a **distinct Kaggle mechanism** — not a CSV upload — and
  STATE.md flags it as unvalidated for the target competition type. Building both would double the
  CLI surface to research and validate, bloating the phase. NOT a combined CSV+code path.
  🔗 **Researcher:** confirm the exact `kaggle competitions submit` flags/output shape and the
  `competitions submissions` read-back shape against the live CLI 2.2.3 (no submit/leaderboard
  behavior is recorded in `references/kaggle-cli-behavior.md` yet — this is a genuine open item).

- **D-02: Pre-submit validation is referenced against `sample_submission.csv`** (criterion 4).
  Checks: **exact column headers**, **exact row count**, **id column present and the id SET matches
  order-independently**, and **no NaN/blank values in prediction columns**. All four are doable with
  the **stdlib `csv` module**, so validation stays in the stdlib-only plumbing tier (no pandas
  dependency in a skill script). Fail-closed with a **distinct reserved exit code** and a precise
  message naming the exact mismatch. ⚠ **The sample filename varies** (titanic's is
  `gender_submission.csv`, not `sample_submission.csv`) — Phase 2's `capture_competition.py` already
  captures a `submission_csv_in_manifest` heuristic; **reuse it, don't re-derive it**. Fall back to
  deriving expected ids from `test.csv`'s id column **only** when no sample file exists in the
  manifest.

### LB read-back & budget source of truth (SCORE-01, SCORE-03, criterion 1, 3)

- **D-03: Bounded-poll then DETACH for LB read-back** — reuse the **proven Phase 4 poller shape**
  (D-08/D-09/D-10). After submit, poll `kaggle competitions submissions` with a **bounded wait
  budget + exponential backoff + jitter** until the score appears. Most competitions score in
  seconds-to-minutes, so the common case captures the LB score in one shot. If the wait budget
  expires, **DETACH** — record the submission as `PENDING` (never lose a spent slot) and let the
  user re-run a discrete **`fetch_lb`** step later to record the score. Transient poll errors are
  tolerated (back off + retry); fail-closed only on persistent errors or budget expiry. NOT an
  unbounded poll (never hang); NOT always-detach (needless friction on the fast common case).

- **D-04: The BLOCKING budget gate reconciles against KAGGLE's authoritative submission count**, not
  our local records. At submit-time, query `kaggle competitions submissions` (a call the read-back
  path already needs) to derive the true count used today. **Rationale — only Kaggle knows the
  truth:** processing-error submissions are **not charged**, and submissions made out-of-band (the
  website, another machine, a prior session) are invisible to a purely local counter. A local count
  would enforce a **wrong budget with false confidence** — the exact silent-failure class this
  project fails closed against everywhere else. `submissions.jsonl` remains our **local provenance
  record**, NOT the gate's source of truth. **Fail-closed** if the authoritative count cannot be
  fetched. The UTC-aware daily reset is **Kaggle's own boundary**, which is precisely why deferring
  to Kaggle avoids re-implementing (and mis-implementing) it.
  🔗 **Researcher:** confirm `competitions submissions` exposes the timestamp/status fields needed to
  count today's *charged* submissions, and whether it exposes remaining quota directly.

### Submission gate policy (SCORE-03, criterion 3)

- **D-05: BLOCK-BY-DEFAULT with an informed human override — the framework never auto-submits and
  never silently hard-refuses.** ⚠ **This decision reshapes criterion 3 and is load-bearing; the
  planner must hold it.** The framework **takes a position**, it is not neutral:
  - It **computes and presents the decision material**: this experiment's CV vs the best
    already-submitted CV, whether the gain is **beyond fold-noise**, the CV→LB history/divergence
    state, and **remaining slots today**.
  - When CV improvement **is** meaningful → recommendation is **submit**.
  - When it **is not** (no improvement, or within noise) → the default state is **BLOCKED /
    "not recommended"**, and the human must **consciously confirm** to proceed.
  - **The human always makes the final call** — this directly serves PROJECT.md's
    *"human-in-the-loop reasoning is the point; opaque budget-burning agents are the anti-pattern."*
  NOT a hard mechanical wall (would fight the human-in-the-loop principle); NOT pure advisory with
  no blocked state (criterion 3 requires the gate to actually block by default).

- **D-06: "Meaningful improvement" = beats the best already-submitted CV by MORE THAN FOLD-NOISE.**
  The signal driving the D-05 recommendation is: `cv_mean` beats the best submitted `cv_mean` by a
  margin exceeding a noise bound derived from **fold std** (e.g. `> k · cv_std`), respecting the
  metric's direction (`greater_is_better`, from `config.metric`). **This is exactly why Phase 3's
  D-04 preserved per-fold scores + std rather than a lone mean scalar** — that variance was kept
  *for this decision*. Rejected: "strictly beats best CV" (a +0.0001 gain within fold jitter passes,
  spending a slot on noise — the exact waste the gate exists to prevent). Rejected: a fixed
  absolute/relative threshold (metric-scale-dependent — the same margin means different things for
  AUC vs RMSE vs LogLoss, and needs per-competition tuning).
  *Planner: `k` is a concrete constant to choose and state; keep it configurable.*

- **D-07: The override reason is OPTIONAL, and recorded to provenance when supplied.** Overriding a
  not-recommended submission requires **explicit human confirmation** but **not** a mandatory reason
  string. When a reason **is** given (e.g. "calibrating the CV→LB gap", "leaderboard probe"), it is
  written into the `submissions.jsonl` row so the history explains *why* a slot was spent against CV
  advice. Do not force the user to type a justification to proceed.

- **D-08: On `limit_provenance == "assumed_default"` — WARN every time, and never spend the FINAL
  assumed slot without explicit confirmation.** This closes the policy question **Phase 2 D-13
  explicitly deferred to Phase 5** ("whether Phase 5 warns on every submission or refuses to spend
  the last slot on an assumed budget is Phase 5's decision"). Every submission decision surfaces
  *"budget is ASSUMED (5/day — not confirmed against the rules page)"*, and the **last** assumed slot
  is gated behind an explicit confirmation, because **if the real limit is lower, that slot may not
  exist at all**. Consistent with the D-05 block-by-default + informed-override shape. NOT
  warn-only (trusts a number Phase 2 says may be fabricated); NOT refuse-until-confirmed (would
  hard-block the loop over a fact the user may not have handy — Phase 2 chose the 5/day fallback
  precisely to avoid that).

### submission.csv production — the cross-phase gap (SCORE-01, criterion 1)

- **D-09: Phase 5 EXTENDS the Phase 3 scaffold/harness so an experiment emits test predictions to
  `experiments/exp-NNN/submission.csv`.** ⚠ **Discovered gap, not scope creep:** Phase 3's `run_cv`
  harness runs cross-validation and emits `result.json` — it never fits and predicts on test, so
  **there is currently no `submission.csv` for SCORE-01 to submit.** Without this extension the phase
  cannot meet criterion 1. (Direct analogue of the Phase 3 D-08 `config.metric` gap.)
  **Mechanism — reuse the CV fold models:** average the per-fold models' test predictions rather
  than refitting on full train. This is **free** (the models are already trained inside the harness),
  is a **mild ensemble** (conventionally at least as strong as a single full-train refit), and every
  contributing model **was actually CV-scored**. Rejected: a separate full-train refit step (costs a
  second training run — real GPU time on the kernel path — and you would submit a model that was
  never validated). Rejected: leaving it to ad-hoc AI code per experiment (nothing guarantees the
  file exists or has the right shape until pre-submit validation rejects it; re-derives the contract
  every cycle).
  ✅ **Free integration win:** because this lives in `experiment.py`/the harness, `submission.csv`
  becomes a first-class **hashed experiment artifact** that flows back through the **Phase 4
  `pull_kernel` path unchanged** — the kernel path gets submission support with no extra work, and
  the "same experiment runs local or on kernel" seam (Phase 3 D-03) stays intact.
  ⚠ **Planner:** test-prediction emission must be **optional/graceful** — a pure-diagnostic
  experiment that doesn't produce predictions must still record a valid CV result, not fail.

### Divergence alarm & the submissions ledger (SCORE-02, criterion 2)

- **D-10: The divergence alarm fires on RANK INVERSION — CV says better, LB says worse.** Formally:
  experiment B has a better CV than experiment A, but scores worse on the leaderboard. **Scale-free**
  — works identically for AUC, RMSE, and LogLoss with **no per-competition tuning** — and it catches
  the failure that actually matters: **CV has stopped being a trustworthy decision metric.**
  Requires ≥2 scored submissions before it can fire, which is honest (state that plainly rather than
  faking a signal from one point). Rejected: an absolute `|CV − LB|` gap threshold — a large *stable*
  offset between CV and LB is usually **benign** (different data, different split); what matters is
  whether the gap is stable, not its size. And a fixed threshold is metric-scale-dependent.
  *The CV→LB gap is still **computed and trended per experiment** (criterion 2 requires the trend);
  rank inversion is what raises the **alarm**.*

- **D-11: `submissions.jsonl` is the CANONICAL LB record; per-experiment CV→LB views are DERIVED by
  joining on `exp_id`.** Row shape (at minimum): `exp_id`, **submission file hash**, UTC timestamp,
  `status ∈ {PENDING, SCORED, FAILED}`, LB score, and the optional D-07 override reason. **The LB
  score is NEVER written back into `meta.json`** — that would mutate a folder Phase 3 treats as
  **immutable after record** and would create **two sources of truth** to keep in sync. Any
  per-experiment CV→LB view (the `strategy.md` trend, the D-10 alarm) is **derived by joining
  `submissions.jsonl` to the ledger on `exp_id`** — rebuildable, exactly the derived-view philosophy
  `ledger.jsonl` already uses (Phase 3 D-10). This also **naturally handles many-submissions-per-
  experiment**, which a single `meta.json` field cannot.

- **D-12: Final selection / nomination is OUT of v1.** ⚠ **This is a deliberate, user-directed
  deviation from roadmap plan `05-02`,** which names a "CV-based final-selection rule". Kaggle lets
  you nominate a limited number of submissions (typically 2) for final private-LB scoring; the user
  **explicitly scoped this out**. **The planner must NOT build it** — not the advisory recommendation,
  not a CLI nomination. The `submissions.jsonl` history + the D-10 alarm give the user everything
  needed to nominate manually in the Kaggle UI. Rejected (for a future revisit): CLI nomination —
  an irreversible, competition-deciding action on a CLI surface that is unconfirmed to exist.

- **D-13: A FAILED submission is RECORDED but NOT COUNTED.** Kaggle does **not charge a slot** for
  processing-error submissions. Write the failed attempt to `submissions.jsonl` with `status=FAILED`
  + the error, so the attempt is **never invisible** (a repeatedly-failing submission file must show
  up in history). The budget arithmetic then comes **free from D-04's Kaggle-authoritative
  reconciliation** — Kaggle simply never charged it, so "remaining" stays correct **with no
  special-case arithmetic on our side**. Rejected: counting it (factually wrong — would refuse a
  submission the user is entitled to make, wasting real budget). Rejected: not recording it (hides
  that an attempt happened at all).

### Entry-point shape (all criteria)

- **D-14: Three DISCRETE, idempotent entry points — `check_submission` → `submit` → `fetch_lb`** —
  mirroring the established `scaffold→run→record` (Phase 3 D-02) and `convert→push→poll→pull`
  (Phase 4 D-01) pattern. Each is stdlib-only, self-locating, `--workspace`-driven, argparse-in /
  exit-code-out; **SKILL.md sequences them and holds the human submit/don't-submit loop** (the Phase
  2 D-10 gate protocol — scripts never block on stdin).
  - **`check_submission.py`** — validates the file (D-02) **AND** renders the full decision material
    (D-05: CV vs best, the D-06 noise read, remaining slots, the D-08 assumed-budget warning, the
    gate recommendation). **Exit code signals gate-blocked vs clear vs validation-failed.**
    **Crucially: this is FREE — it never spends a slot**, so "should I submit?" is answerable
    without touching the budget.
  - **`submit.py`** — spends the slot **only when explicitly invoked** (carrying the human's
    confirmation and the optional D-07 reason), then bounded-polls per D-03.
  - **`fetch_lb.py`** — the D-03 detach fallback; re-runnable, records a `PENDING` submission's score.
  Rejected: folding validation + gate into `submit.py` behind a `--force` flag — the dry-run "show me
  the decision material without doing anything" capability disappears, forcing you to invoke the
  thing that spends the slot just to learn whether you should.
  *Planner: new reserved exit codes follow the existing sysexits-aligned convention in
  `scripts/kaggle_gateway.py` (77 = UI_GATE, 78 = LIMIT_NEEDS_USER already taken; 124/126/127/128+
  are reserved — do not reuse).*

### Claude's Discretion

- **The noise constant `k` in D-06** (`improvement > k · cv_std`) — pick a concrete, defensible
  default and make it configurable; state it wherever the recommendation is rendered.
- **D-03 poll constants** — initial interval, multiplier, cap, jitter, and the default LB wait
  budget. LB scoring is typically far faster than a kernel run, so the Phase 4 constants are a
  starting point, not a mandate; tune to observed behavior.
- **`submissions.jsonl` full row schema** beyond the D-11 named fields (e.g. Kaggle's own submission
  id, the public/private LB split if exposed, message string, competition slug) — keep it small,
  append-only, git-diffable, and rebuildable.
- **Exact reserved exit-code numbering** for gate-blocked / validation-failed, following the
  `kaggle_gateway.py` convention.
- **How the fold-averaged test prediction is exposed in the harness signature** (D-09) — e.g. an
  optional `predict_fn` / a `test_df` argument / collecting fold-model predictions automatically.
  Must satisfy the Phase 3 D-07 tension: flexible enough that the AI rarely needs to bypass it.
- **How the D-05 decision material is rendered** (the exact report `check_submission.py` prints) and
  where the submit flow surfaces in `SKILL.md`'s scripts table + gate protocol.
- **Whether `strategy.md`'s regenerated mechanical sections gain an LB/gap block** (D-10/D-11 make
  the data available; Phase 3 D-11/D-12 own the regen contract — extend it, don't fork it).
- **Where a `sample_submission.csv` is located/resolved** for D-02 given the varying filename.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent, scope, and success criteria
- `.planning/ROADMAP.md` §"Phase 5: Submission & Leaderboard Tracking" — the fixed phase goal and
  the 4 success criteria. ⚠ **Note the deliberate deviation:** its suggested plan `05-02` names a
  "CV-based final-selection rule" — the user scoped final selection **OUT of v1** (D-12). Do not
  build it.
- `.planning/REQUIREMENTS.md` §Scoring — **SCORE-01, SCORE-02, SCORE-03** authoritative text. This is
  the **final v1 phase**; all other requirements are already mapped and complete.
- `.planning/PROJECT.md` §"Core Value", §Constraints, §"Key Decisions", **§"Out of Scope"** — the
  locked decisions this phase must honor: **"CV-first scoring; ration submissions"**, "Kaggle limits:
  respect competition submission limits", and critically **§Out of Scope: "Fully autonomous
  unsupervised optimization — human-in-the-loop reasoning is the point; opaque budget-burning agents
  are the anti-pattern"** — the principle that **directly drives D-05's block-by-default-with-human-
  override gate**.
- `.planning/STATE.md` §Blockers/Concerns — carries the Phase-5 flag *"code-competition submission
  path needs validation… may need a competition-type flag captured in Phase 2"*. **Resolved two
  ways:** Phase 2 D-14 captured `competition.type`, and D-01 here scopes the code path out of v1.

### Prior-phase decisions this phase EXTENDS (READ — the contracts are locked, do not re-derive)
- `.planning/phases/03-local-experiment-loop-ledger-strategy/03-CONTEXT.md` — **the contract Phase 5
  extends.** Load-bearing: **D-04** (`result.json` carries per-fold scores + mean + **std** — the
  variance kept *specifically* for D-06's noise-aware gate and this phase's gap tracking), **D-05/D-06**
  (tooling validates-then-persists; numbers are never AI-typed — the **LB score is a machine number**),
  **D-07** (the `run_cv` harness D-09 extends, and its flexibility tension), **D-08** (`config.metric` =
  `{name, greater_is_better}` — the direction D-06's comparison needs), **D-10** (`meta.json` canonical /
  `ledger.jsonl` derived + rebuildable — the philosophy D-11 mirrors; **immutable experiment folder**),
  **D-11/D-12** (`strategy.md` = tooling facts + AI reasoning, fully overwritten each cycle).
- `.planning/phases/04-kaggle-kernel-execution-gpu-path/04-CONTEXT.md` — **D-01** (discrete, idempotent,
  re-runnable entry points — the pattern D-14 mirrors), **D-08/D-09/D-10** (**the bounded-poll +
  backoff/jitter + detach-not-cancel poller shape D-03 reuses**), D-13 (quota heads-up is
  non-blocking; the *submission* budget built here is the real budget model).
- `.planning/phases/02-competition-context-data/02-CONTEXT.md` — **D-13** (`submission.daily_limit` +
  **`limit_provenance`** — and the policy question it **explicitly deferred to Phase 5**, now answered by
  **D-08**), **D-14** (`competition.type ∈ {csv, code, unknown}`; **on `unknown` the CSV path must refuse
  rather than spend a slot** — honored by D-01), **D-10** (reserved-exit-code gate protocol; the SKILL
  holds the human loop), **D-16** (the one Kaggle Gateway owns every CLI call).
- `.planning/phases/01-workspace-credentials-egress-guardrails/01-CONTEXT.md` — workspace layout,
  `control/` vs experiment folders, `.gitignore` posture, egress allowlist mechanism.

### Existing skill code the new scripts sit beside / extend (reuse the conventions)
- `scripts/kaggle_gateway.py` — **`run_kaggle(*argv, timeout)`: the ONE timeout-bounded, no-echo,
  exit-code CLI runner** every `competitions submit` / `competitions submissions` call MUST route
  through. **Its reserved-exit-code table (77 = `UI_GATE`, 78 = `LIMIT_NEEDS_USER`, sysexits-aligned;
  124/126/127/128+ reserved) is the convention D-14's new exit codes extend.**
- `scripts/capture_competition.py` — already writes `submission.daily_limit` + `limit_provenance` and
  the `submission_csv_in_manifest` heuristic **D-02 must reuse** (note its own comment that the
  heuristic is *weak* — titanic's file is `gender_submission.csv`).
- `scripts/templates/experiment.py.tmpl` — **the harness D-09 extends** to emit fold-averaged test
  predictions; carries `resolve_data_dir()` (the local/kernel seam) and the `run_cv` harness.
- `scripts/record_experiment.py` + `scripts/experiment_meta.py` — the fail-closed recorder, the
  `FAILURE_REASONS` enum, and the `meta.json` shape the D-11 join reads (**do not add an LB field**).
- `scripts/rebuild_ledger.py` — the canonical/derived rebuild pattern `submissions.jsonl` + the
  derived CV→LB view should mirror.
- `scripts/regen_strategy.py` + `scripts/templates/strategy.md.tmpl` — the strategy regen contract to
  **extend** (its stub already declares *"Discipline: CV-first. Track the CV→LB gap; ration
  submissions against CV signal"* — this phase makes that real).
- `scripts/pull_kernel.py` — pulls kernel artifacts into the same experiment folder; **`submission.csv`
  from D-09 rides this path for free.**
- `scripts/metric_registry.py` / `scripts/set_metric.py` — `config.metric` `{name, greater_is_better}`;
  D-06's direction-aware comparison reads it.
- `SKILL.md` — entry-point sequencing, the exit-77 gate protocol, and the "Scripts (progressive
  disclosure)" table that gains the D-14 rows.

### Technology stack, Kaggle command surface, and known risks (MANDATORY)
- `CLAUDE.md` — the prescriptive stack. For Phase 5 specifically: §"Kaggle Integration — Concrete
  Command Surface" (**daily limit typically 5/day; failed (processing-error) submissions do NOT count
  — the fact D-13 relies on**; ration against CV signal; log the CV→LB gap), §"Kaggle Integration —
  Primitive Selection" (`kaggle competitions submit` / `submissions` / `leaderboard` — **the CLI is
  the sole primitive; kagglehub cannot submit**), §"Open Risks / Needs Implementation-Time
  Verification" (**code/notebook-only competition submission — MEDIUM, the exact flow needs validation;
  scoped out by D-01**), §"What NOT to Use" (no credential echo; no runtime pip install).
- `references/kaggle-cli-behavior.md` — the checked-in live-CLI-behavior fixture doc. ⚠ **It currently
  contains NO submit/leaderboard entries** — Phase 5 must **extend it** with the observed
  `competitions submit` and `competitions submissions` shapes (exit codes, output format, timestamp/
  status fields, whether remaining quota is exposed). This is a real open research item, not a
  formality.
- `references/egress-allowlist.md` — confirms `api.kaggle.com` + `storage.googleapis.com` are already
  allowlisted; submission upload routes here.

### External structure-only exemplar (NOT a dependency — do not import or couple to it)
- `~/.claude/plugins/cache/shepsci/kaggle-skill/2.3.0/` — its submission helpers are a
  structure/command-surface exemplar **only**. PROJECT.md forbids depending on it. Reimplement
  independently in Python (stdlib + the gateway).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`scripts/kaggle_gateway.py` → `run_kaggle()`** — the single timeout-bounded, no-echo, exit-code
  CLI runner; all `competitions submit` / `competitions submissions` calls route through it. Its
  sysexits-aligned reserved-exit-code table is the convention for D-14's new codes.
- **`control/config.json`** — **already carries every field this phase needs**:
  `submission.daily_limit` + `submission.limit_provenance` (Phase 2 D-13), `competition.type`
  (Phase 2 D-14), `metric` `{name, greater_is_better}` (Phase 3 D-08), `competition_slug`. **No new
  config fields are strictly required** beyond any tunables the planner adds (e.g. the D-06 `k`).
- **`scripts/capture_competition.py`** — the `submission_csv_in_manifest` detection D-02 reuses, and
  the `set_config_field` write pattern.
- **`scripts/poll_kernel.py`** — the **bounded-poll + backoff + jitter + detach** implementation D-03
  mirrors for LB read-back. Do not reinvent the poller; follow its shape.
- **`scripts/rebuild_ledger.py` / `scripts/experiment_meta.py`** — the canonical-file → derived-index
  rebuild pattern `submissions.jsonl` and the derived CV→LB join follow.
- **`scripts/templates/experiment.py.tmpl` + `run_cv`** — the harness D-09 extends; its per-fold
  models are already trained, making fold-averaged test prediction nearly free.
- **`scripts/safe_extract.py` / `scripts/untrusted.py`** — the fail-closed + untrusted-boundary
  posture to imitate for any Kaggle-returned text (LB/submission messages are Kaggle-authored text).

### Established Patterns
- **Scripts are stdlib-only, self-locating (`Path(__file__)`), `--workspace`-driven, argparse-in /
  exit-code-out, never interactive; SKILL.md sequences them and holds the human loop** (Phase 2 D-10).
  D-14's three entry points follow this exactly — and D-05's human submit/don't-submit decision is
  held **by the SKILL**, never by a blocking `input()` in a script.
- **Fail-closed everywhere** — D-04's unavailable-count and D-02's validation failure both fail closed.
- **Numbers are tooling-written from machine-checked output, never AI-typed** — the LB score is
  recorded by tooling from CLI output, exactly like the CV score.
- **Discrete, idempotent, re-runnable steps** (Phase 3 D-02, Phase 4 D-01) — never a monolithic
  orchestrator.
- **Derived views rebuild from canonical files** (Phase 3 D-10) — D-11's CV→LB join is derived.
- **CLAUDE.md is the stack/version/security authority.**

### Integration Points
- **`control/submissions.jsonl`** — **NEW**, the canonical append-only submission record (D-11).
  Must be **git-tracked** (it is small provenance, like `control/raw/` artifacts per Phase 2 D-03).
- **`experiments/exp-NNN/submission.csv`** — **NEW artifact** produced by the D-09 harness extension;
  hashed into the `submissions.jsonl` row; flows back through `pull_kernel.py` on the kernel path.
- **`control/config.json`** — read for `submission.daily_limit` / `limit_provenance` /
  `competition.type` / `metric` / `competition_slug`. (Gains only planner-chosen tunables.)
- **`control/ledger.jsonl` + `experiments/exp-NNN/meta.json`** — **read-only** for the D-11 join
  (`exp_id`, `cv_mean`, `cv_std`). ⚠ **`meta.json` is NOT written to** — immutability preserved.
- **`strategy.md` / `scripts/regen_strategy.py`** — gains the CV→LB gap trend + divergence alarm in
  its tooling-rendered mechanical sections (extend the Phase 3 D-11/D-12 regen contract).
- **`SKILL.md`** — new gate protocol for the submit decision, new reserved exit codes, three new rows
  in the scripts table.
- **`scripts/templates/experiment.py.tmpl`** — the D-09 harness extension (test-prediction emission).
- **`.gitignore`** — verify `submission.csv` under `experiments/*/` is not swept up by the existing
  artifact-ignore patterns if it must be hashed/tracked, and that `control/submissions.jsonl` is tracked.

</code_context>

<specifics>
## Specific Ideas

- **The gate's shape is the user's sharpest steer, and it came as a correction:** asked how to define
  "meaningful CV improvement", the user reframed the question — *"can we make the user decide if they
  want to submit this or try other things?"* The framework must **compute and present** the decision
  material and **take a position** (block-by-default when the gain is within noise), but **the human
  always makes the final call**. This is PROJECT.md's anti-"opaque budget-burning agent" principle
  made mechanical. A hard mechanical wall is wrong; a neutral advisory with no blocked state is also
  wrong (D-05).
- **The override reason is optional, not mandatory** (D-07) — the user explicitly did not want to be
  forced to type a justification to spend their own slot. Record it when given; never demand it.
- **Rank inversion over gap-threshold** (D-10) was chosen because a large *stable* CV↔LB offset is
  usually benign; what breaks a competition run is CV **ordering** ceasing to predict LB ordering.
  Scale-free, no per-competition tuning, honest about needing ≥2 scored submissions.
- **`submission.csv` genuinely does not exist yet** (D-09). This was surfaced during discussion, not
  in the roadmap — Phase 3's harness is CV-only. **The planner must not assume a submission file is
  lying around.** Fold-averaged test predictions from the already-trained CV models is the chosen
  mechanism (free, mildly ensembled, every model actually validated).
- **`check_submission.py` being free (never spends a slot) is the point of the three-step split**
  (D-14) — the user must be able to ask "should I submit this?" and get the full decision material
  without touching the budget.
- **Final selection is deliberately out** (D-12) — a conscious deviation from roadmap 05-02. The
  planner should not quietly reintroduce it.

</specifics>

<deferred>
## Deferred Ideas

- **Code-competition (notebook→submit) submission flow** — scoped out of v1 by D-01. A distinct
  Kaggle mechanism (submit a notebook version, not a CSV) that STATE.md flags as unvalidated. Phase 4
  already deferred "submission FROM kernel output" here; it is now deferred past v1. `competition.type`
  is already captured, so a later phase can add the path without re-deriving the flag. **v1 refuses
  cleanly rather than spending a slot.**
- **Final-selection / nomination rule** (which submissions to nominate for final scoring; Kaggle
  typically allows 2) — **explicitly scoped out of v1 by the user (D-12)**, despite roadmap 05-02
  naming it. Revisit if the manual nomination proves painful. When revisited: CV-first says nominate
  best-CV, with best-LB as a hedge **only** when the D-10 divergence alarm has fired.
- **Nominating via the CLI** — rejected even if final selection returns: it is an irreversible,
  competition-deciding action, and it is unconfirmed that the CLI even exposes it.
- **GPU-hour budget model + push gating** — still deferred (carried from Phase 4 D-13). Phase 5 builds
  the *submission* budget only. If a GPU budget is ever built, it should mirror this phase's
  authoritative-source + block-by-default-with-override shape.
- **In-notebook version pinning to match the `kaggle/python` image** — Phase 4 D-14 deferred this to
  Phase 5 as a "CV→LB parity concern". **Still deferred:** D-10's divergence alarm is the *detector*;
  pinning is a *remedy* to apply only once an observed divergence is actually traced to an env diff
  (and it conflicts with the internet-off default). The alarm makes this diagnosable, which is enough
  for v1.
- **Adversarial-validation-driven CV strategy** (reweighting folds / mimicking test when AV AUC is
  high) — carried from Phase 2's deferred list. Phase 2 produced the finding; acting on it is
  experiment design, not submission tracking.
- **Semantic idea dedup (ANLY-01), ledger comparison views (ANLY-02), evidence-ranked strategy
  synthesis (ANLY-03)** — v2, explicitly out of the v1 roadmap.

### Reviewed Todos (not folded)
None — `todo.match-phase 5` returned zero matches.

</deferred>

---

*Phase: 5-Submission & Leaderboard Tracking*
*Context gathered: 2026-07-12*
