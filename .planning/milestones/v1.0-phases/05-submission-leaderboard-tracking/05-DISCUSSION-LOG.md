# Phase 5: Submission & Leaderboard Tracking - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 5-Submission & Leaderboard Tracking
**Areas discussed:** Submit-path scope, LB read-back & budget truth, Submission gate policy, Divergence alarm & ledger, submission.csv production, Final-selection rule, Failed submission handling, SKILL.md entry-point shape

---

## Submit-path scope

**Q: CSV-only submit path for v1, or also the code-competition (notebook→submit) flow?**

| Option | Description | Selected |
|--------|-------------|----------|
| CSV-only | `kaggle competitions submit -f`; refuse-and-instruct on type ∈ {code, unknown}. Cleanest MVP slice; the code path is a distinct mechanism and STATE.md flags it unvalidated. | ✓ |
| CSV + code-competition | Also build the notebook-version flow consuming Phase 4 kernel output. Doubles the CLI surface to research/validate. | |
| You decide | Claude's discretion. | |

**User's choice:** CSV-only
**Notes:** Becomes D-01. The code path is deferred past v1 (not just to a later plan). `competition.type` is already captured in Phase 2, so a future phase can add it without re-deriving the flag.

---

**Q: What does pre-submit validation validate against, and how strict?**

| Option | Description | Selected |
|--------|-------------|----------|
| sample_submission.csv | Exact headers, exact row count, id-set alignment (order-independent), no NaN/blank predictions. Stdlib `csv` — stays in the plumbing tier. Filename varies (titanic = gender_submission.csv). | ✓ |
| test.csv id column | Derive expected ids from test.csv. Works with no sample file, but can't validate the expected header/format. | |
| You decide | Claude's discretion. | |

**User's choice:** sample_submission.csv
**Notes:** Becomes D-02. Reuses Phase 2's existing `submission_csv_in_manifest` heuristic rather than re-deriving it; test.csv ids are the fallback only when no sample file exists.

---

## LB read-back & budget truth

**Q: How should the framework read the LB score back after submitting (Kaggle scores async)?**

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded-poll then detach | Reuse the Phase 4 poller shape: bounded wait + backoff + jitter, then detach to a re-runnable `fetch-lb` step. Captures the fast common case in one shot; never hangs, never loses a spent slot. | ✓ |
| Always detach | Record PENDING immediately; always require a second invocation. Simpler, but adds friction to the common fast case. | |
| You decide | Claude's discretion. | |

**User's choice:** Bounded-poll then detach
**Notes:** Becomes D-03. Explicitly mirrors Phase 4 D-08/D-09/D-10 — do not reinvent the poller.

---

**Q: What is the authoritative source of the count that actually gates a submission?**

| Option | Description | Selected |
|--------|-------------|----------|
| Reconcile with Kaggle | Query `competitions submissions` at submit-time for the true count. Failed submits aren't charged; out-of-band submissions are otherwise invisible. Fail-closed if unavailable. UTC reset is Kaggle's own boundary. | ✓ |
| Derive from submissions.jsonl | Count local rows in the current UTC day. No extra call, offline-friendly — but drifts from reality and can enforce a wrong budget with false confidence. | |
| You decide | Claude's discretion. | |

**User's choice:** Reconcile with Kaggle
**Notes:** Becomes D-04. `submissions.jsonl` stays as local provenance, not the gate's source of truth. This choice also makes D-13 (failed submissions not counted) free — no special-case arithmetic.

---

## Submission gate policy

**Q: How should "meaningful CV improvement" be defined by default?**

| Option | Description | Selected |
|--------|-------------|----------|
| Beats best by > noise | Beat best submitted CV by more than a fold-std-derived margin. Uses the variance Phase 3 D-04 preserved for exactly this. | (became the signal) |
| Strictly beats best CV | Any improvement passes — a +0.0001 gain within jitter spends a slot on noise. | |
| Fixed threshold | Configured absolute/relative margin. Metric-scale-dependent; needs per-competition tuning. | |
| **Other (free text)** | **"can we make the user decide if they want to submit this or try other things?"** | ✓ |

**User's choice:** Free-text reframe — the human should make the submit-vs-keep-experimenting call.
**Notes:** This was the sharpest steer of the discussion and reshaped the whole area. Reconciled with criterion 3 ("gated… blocked otherwise") as **block-by-default with an informed human override** (D-05): the framework computes and presents the decision material and takes a position, but never auto-submits and never silently hard-refuses. The beats-best-by-more-than-noise math survives as the **signal driving the recommendation** (D-06), not as an absolute wall. Directly serves PROJECT.md §Out of Scope: *"human-in-the-loop reasoning is the point; opaque budget-burning agents are the anti-pattern."*

**Follow-up (plain text):** Confirmed (1) block-by-default is the right shape (not pure advisory), and (2) the override reason should be **optional**, not required → D-07.

---

**Q: How should the budget gate respond when `limit_provenance == "assumed_default"`?**

| Option | Description | Selected |
|--------|-------------|----------|
| Warn + never spend last slot | Warn on every decision; gate the FINAL assumed slot behind explicit confirmation — if the real limit is lower, that slot may not exist. | ✓ |
| Warn only | Warn but treat the number as real, including the last slot. Trusts a number Phase 2 says may be fabricated. | |
| Refuse until confirmed | Block all submissions until the real limit is confirmed. Safest, but hard-blocks the loop. | |

**User's choice:** Warn + never spend last slot
**Notes:** Becomes D-08. Answers the policy question **Phase 2 D-13 explicitly deferred to Phase 5**.

---

## Divergence alarm & ledger

**Q: How should CV/LB "disagreement" be defined?**

| Option | Description | Selected |
|--------|-------------|----------|
| Rank inversion | B has better CV than A but worse LB. Scale-free (AUC/RMSE/LogLoss alike), no tuning; catches CV ceasing to be a trustworthy decision metric. Needs ≥2 scored submissions. | ✓ |
| Absolute gap threshold | Alarm on \|CV − LB\| > margin. Fires on the first submission, but a large *stable* offset is usually benign; metric-scale-dependent. | |
| Both: gap trend + inversion | Rank inversion plus a shift in the gap relative to its own trend. Richer, more to implement/tune. | |

**User's choice:** Rank inversion
**Notes:** Becomes D-10. The CV→LB gap is still computed and trended per experiment (criterion 2 requires the trend); rank inversion is what raises the **alarm**.

---

**Q: Where do the LB score and CV→LB gap live?**

| Option | Description | Selected |
|--------|-------------|----------|
| submissions.jsonl canonical, join on exp_id | Append-only canonical record; LB never written back to meta.json (preserves Phase 3 folder immutability, avoids two sources of truth). Views derived by joining on exp_id. Handles many-submissions-per-experiment. | ✓ |
| Write LB back into meta.json | One complete file per experiment, but mutates an immutable folder and creates a second source of truth. Awkward for repeat submissions. | |
| You decide | Claude's discretion. | |

**User's choice:** submissions.jsonl canonical, join on exp_id
**Notes:** Becomes D-11. Mirrors the Phase 3 D-10 canonical/derived-rebuildable philosophy.

---

## submission.csv production *(new area — surfaced mid-discussion)*

**Q: Phase 3's harness is CV-only and never predicts test, so `submission.csv` may not exist. Who produces it?**

| Option | Description | Selected |
|--------|-------------|----------|
| Extend the harness to emit it | Reuse the already-trained CV fold models and average their test predictions → `experiments/exp-NNN/submission.csv`. Free, mildly ensembled, every model actually CV-scored. Rides the Phase 4 pull path for free. | ✓ |
| Refit on full train, separate step | Refit on all data in a distinct step. Costs a second training run (real GPU on the kernel path), and the refit model is never CV-validated. | |
| AI writes it ad-hoc | No scaffold support; maximum flexibility, but nothing guarantees the file exists or has the right shape, and it re-derives the contract every cycle. | |

**User's choice:** Extend the harness to emit it
**Notes:** Becomes D-09. **This was a genuine discovered gap, not in the roadmap** — the direct analogue of Phase 3's D-08 `config.metric` gap. Without it, SCORE-01 has nothing to submit. Planner must keep emission optional/graceful so a pure-diagnostic experiment still records a valid CV result.

---

## Final-selection rule *(new area)*

**Q: Kaggle lets you nominate a limited number of submissions for final scoring. What should the framework do?**

| Option | Description | Selected |
|--------|-------------|----------|
| Advise only, CV-first | Recommend the nomination (best CV, with best-LB as a hedge when the divergence alarm fired); human nominates in the UI. | |
| Advise and nominate via CLI | Also perform the nomination. Irreversible, competition-deciding; unclear the CLI exposes it. | |
| Out of scope for v1 | Skip entirely; ledger + LB history suffice for manual nomination. | ✓ |

**User's choice:** Out of scope for v1
**Notes:** Becomes D-12. ⚠ **A deliberate deviation from roadmap plan 05-02**, which names a "CV-based final-selection rule". Flagged loudly in CONTEXT.md so the planner does not silently build it.

---

## Failed submission handling *(new area)*

**Q: Kaggle doesn't charge a slot for processing-error submissions. How is a failed submission handled?**

| Option | Description | Selected |
|--------|-------------|----------|
| Record it, don't count it | `status=FAILED` in submissions.jsonl so the attempt is never invisible; budget stays correct for free via the Kaggle-authoritative reconciliation. | ✓ |
| Record and count it | Conservative, but factually wrong — would refuse a submission the user is entitled to make. | |
| Don't record it | Cleaner ledger, but hides that an attempt happened; a repeatedly-failing file becomes invisible. | |

**User's choice:** Record it, don't count it
**Notes:** Becomes D-13. Falls out of D-04 with no special-case arithmetic.

---

## SKILL.md entry-point shape *(new area)*

**Q: How should the submit flow surface as entry points?**

| Option | Description | Selected |
|--------|-------------|----------|
| Discrete: check → submit → fetch-lb | Mirrors convert/push/poll/pull. `check_submission.py` validates AND renders the decision material — **free, never spends a slot**. `submit.py` spends the slot only when explicitly invoked. `fetch_lb.py` is the detach fallback. | ✓ |
| Two steps: submit → fetch-lb | Fold validation + gate into submit.py behind `--force`. Fewer scripts, but the dry-run "should I submit?" capability disappears. | |
| You decide | Claude's discretion. | |

**User's choice:** Discrete: check → submit → fetch-lb
**Notes:** Becomes D-14. The free `check_submission.py` step is the point of the split — "should I submit?" must be answerable without touching the budget.

---

## Claude's Discretion

Explicitly left to the planner (captured in CONTEXT.md `### Claude's Discretion`):

- The noise constant `k` in D-06 (`improvement > k · cv_std`) — pick a defensible, configurable default.
- D-03 poll constants (initial interval, multiplier, cap, jitter, default LB wait budget) — LB scoring is far faster than a kernel run, so Phase 4's constants are a starting point, not a mandate.
- `submissions.jsonl` full row schema beyond the D-11 named fields.
- Exact reserved exit-code numbering for gate-blocked / validation-failed (following `kaggle_gateway.py`'s sysexits-aligned convention; 77/78/124/126/127/128+ are taken).
- How fold-averaged test prediction is exposed in the harness signature (D-09), satisfying the Phase 3 D-07 flexibility tension.
- How the D-05 decision material is rendered, and where the submit flow surfaces in SKILL.md.
- Whether `strategy.md`'s regenerated mechanical sections gain an LB/gap block.
- How a `sample_submission.csv` is located given the varying filename.

## Deferred Ideas

- **Code-competition (notebook→submit) flow** — out of v1 (D-01); v1 refuses cleanly rather than spending a slot.
- **Final-selection / nomination rule** — out of v1 (D-12), despite roadmap 05-02 naming it. CLI nomination rejected even on revisit (irreversible, unconfirmed surface).
- **GPU-hour budget model + push gating** — still deferred (carried from Phase 4 D-13); Phase 5 builds the *submission* budget only.
- **In-notebook version pinning to match the `kaggle/python` image** — Phase 4 D-14 deferred this here as a CV→LB parity concern; **still deferred**. D-10's alarm is the *detector*; pinning is a *remedy* to apply only once a divergence is actually traced to an env diff.
- **Adversarial-validation-driven CV strategy** — carried from Phase 2; acting on the AV finding is experiment design, not submission tracking.
- **Semantic idea dedup (ANLY-01), ledger comparison views (ANLY-02), evidence-ranked strategy synthesis (ANLY-03)** — v2, explicitly out of the v1 roadmap.
