# Phase 4: Kaggle Kernel Execution (GPU Path) - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

The **same** experiment that already runs locally can run on **Kaggle GPU compute** as a
**pure addition** to the proven loop — **convert → push → poll → pull → record** — **reusing
(never re-deriving)** the Phase 3 machine-checked result contract, with **silent kernel failure
caught** (a kernel that reports `complete` but actually threw is recorded FAILED, never a
success).

**In scope:** EXP-05 — kernel-metadata generation from a validated template (competition_sources,
accelerator, internet-off), `kaggle kernels push`, timeout-bounded status polling with backoff
(no 429 storm), `kaggle kernels output`/pull into the **same** `artifacts/` + `result.json`
contract the local runner uses, and a run-log traceback scan that **extends** the D-06
fail-closed result contract before any score is recorded.

**Explicitly NOT in this phase (boundary guards):**
- **Submission, LB read-back, CV→LB gap, submission-budget gating are Phase 5 (SCORE-*).** Phase 4
  produces kernel-run CV numbers into the same ledger; it never submits. Phase 5 *consumes* Phase 4
  kernel output when a kernel produced the submission.
- **GPU-quota budgeting/gating is NOT built here.** Phase 4 only does a lightweight, non-blocking
  quota heads-up (D-13). A tracking/gating budget system is Phase-5-shaped discipline.
- **The result contract is EXTENDED, never re-derived.** Phase 3's `record_experiment.py` D-06
  ladder (`missing_result`/`schema_invalid`/`non_finite`/`out_of_range`) is reused unchanged; Phase 4
  adds exactly one rung + one reason (D-11/D-12).
- **Env/version pinning to match the kaggle/python image is NOT done here** (D-14) — that's a
  Phase-5 CV→LB parity concern. Phase 4 documents + records the image, doesn't force parity.
- **No new experiment representation, ledger schema, or strategy mechanics** — those are locked in
  Phase 3. The kernel path plugs into the existing scaffold/record/ledger/strategy machinery.

</domain>

<decisions>
## Implementation Decisions

### Kernel loop shape & re-runnability (criterion 1, 2)

- **D-01: The kernel path decomposes into DISCRETE, idempotent entry points — `convert → push →
  poll → pull` — mirroring Phase 3's D-02 (`scaffold → run → record`), then reuses the existing
  `record_experiment.py`.** NOT a combined `run_kernel` that does push+poll+pull in one shot. The
  driving requirement: if polling dies (network drop, Ctrl-C, our-side timeout), the user resumes
  `poll`/`pull` **without re-pushing** — never re-burning GPU time already spent. Each step stays
  argparse-in / exit-code-out, stdlib-only, self-locating, `--workspace`-driven (the Phase 2/3
  script contract), with the SKILL sequencing them and holding any human loop.

- **D-02: The convert step (`.py → .ipynb` via jupytext) is a SEPARATE step before push**, so the
  notebook can be inspected before it goes up. ⚠ **GUARD (load-bearing):** convert stays
  **mechanical/deterministic — regenerated from the scaffold-minted `experiment.py`, not
  hand-edited.** The `.ipynb` is a build artifact, not a maintained second source. This preserves
  the EXP-05 "same experiment, untouched" seam (`resolve_data_dir()` auto-selects `/kaggle/input`
  on the kernel). If the user *deliberately* tweaks the notebook, that is an intentional deviation
  and must be captured in provenance — it is not the default path. Planner: keep convert
  re-runnable and non-destructive so a re-convert always reproduces from `experiment.py`.

- **D-03: The push→poll→pull handoff state lives in the EXPERIMENT FOLDER — a small
  `experiments/exp-NNN/kernel_run.json`** (kernel slug, kernel version, code_file, push time,
  competition, accelerator, effective internet flag, detached/PENDING status). NOT
  `control/state.json`. Rationale: co-located with the experiment, git-diffable, matches the
  Phase 3 "`meta.json` per experiment is canonical" pattern, and supports multiple experiments
  without a single-in-flight bottleneck. `poll`/`pull` read this file to know which kernel/version
  to act on without re-deriving it.

### kernel-metadata.json defaults (criterion 1)

- **D-04: Default accelerator is `T4×2`** (the modern, most-provisioned Kaggle GPU tier; same
  30h/week quota cost as P100), **overridable per experiment**. The metadata is generated from a
  validated template, not hand-authored.

- **D-05: Kernel id/slug is DETERMINISTIC and STABLE per experiment** — e.g.
  `<username>/<competition-slug>-exp-NNN` — and **re-pushing updates the SAME kernel** (Kaggle
  auto-versions). One clean `exp-NNN ↔ kernel` mapping; retry history lives on one kernel page;
  `kernel_run.json` tracks the current version. NOT a unique/timestamped slug per push (scatters
  retries, breaks the mapping). 🔗 **Researcher must confirm** how `kaggle kernels push` handles
  id collisions/versioning and how the username is obtained for the slug.

- **D-06: `enable_internet` defaults to `false`, controlled by a CONFIG-LEVEL toggle** (per
  criterion 1 and CLAUDE.md "internet-off by default"). ⚠ **GUARD:** because a global toggle is
  easier to leave on by accident, the **effective per-run internet value MUST be recorded in
  provenance** (`kernel_run.json` → `meta.json`) so an internet-on run is a visible, auditable
  exception — never a silent widening of egress that could invalidate a code-competition run.

- **D-07: The kernel is ALWAYS private (`is_private: true`)** and **`competition_sources` is
  populated mechanically from `config.json.competition_slug`** (mounts data at
  `/kaggle/input/<slug>/`, exactly what `resolve_data_dir()` already expects). No re-prompting for
  the source — the slug is already in config.

### Polling policy (criterion 2)

- **D-08: OUR-side poll wait budget defaults to ~2 hours, configurable via flag/config.** Kernels
  can run up to 12h, but the poller must stay bounded (the `run_local`/gateway "timeout-bounded,
  never hang" posture). A known-long run just supplies a larger explicit budget. This is our
  patience, NOT a kernel kill.

- **D-09: On OUR-side timeout with the kernel still running, DETACH — do not cancel.** Stop
  polling, **leave the kernel running on Kaggle** (never throw away GPU time already spent), record
  a `PENDING`/detached status in `kernel_run.json`, and let the user **re-run `poll` later to
  reattach and `pull`** when it finishes. Fits the discrete-steps + resume design (D-01). NOT an
  active remote cancel.

- **D-10: Backoff is EXPONENTIAL with a cap + jitter** — start short (~10s), grow multiplicatively
  to a cap (~60–120s), small random jitter to avoid synchronized retries — satisfying criterion 2's
  "no 429 storm" over the ~2h window. Poll-call errors (transient network / 429 / the known
  status-parse bugs #473/#509) are **tolerated as transient**: back off and retry within the
  budget; **fail-closed with a clear error only if errors persist past a threshold or the budget
  expires.** A transient blip is NEVER misread as kernel failure. 🔗 **Researcher must confirm the
  exact `kaggle kernels status` output shape against a live run** before finalizing status parsing
  (STATE.md blocker; API bugs #473/#509) — always prefer structured output if the CLI offers it.

### Silent-failure detection — extending the D-06 result contract (criterion 3)

- **D-11: The pulled run log is scanned for TRACEBACK signatures AND error markers** — Python
  traceback (`Traceback (most recent call last)`), `Error:`/uncaught-exception markers, and any
  non-zero-exit / process-killed / OOM indicators the CLI/log exposes. A hit ⇒ **FAILED even if
  status said `complete` and even if `result.json` exists.** Targeted, low-false-positive. NOT
  traceback-only (misses killed-process / OOM / non-Python failures). 🔗 **Researcher confirms the
  actual kernel-log format** against a live run to finalize the pattern set.

- **D-12: The scan lives INSIDE `record_experiment.py` as a NEW FIRST RUNG of the D-06 fail-closed
  ladder (kernel path only), and the enum REUSES existing reasons + adds exactly one new
  `kernel_error`.** Order: scan log → if a traceback/error is found, `FAILED(kernel_error)` **before
  `result.json` is even trusted**; otherwise fall through to the existing
  `missing_result`/`schema_invalid`/`non_finite`/`out_of_range` checks unchanged. Missing/invalid
  `result.json` on the kernel path maps to the EXISTING reasons (no duplication). This keeps the
  failure contract in **one place** (one recorder, one ladder) — the literal realization of
  Phase 3's "Phase 4 extends the contract, never re-derives it." NOT a scan split into `pull` with a
  separate pass/fail signal; NOT a proliferation of kernel-specific reasons
  (`kernel_traceback`/`kernel_timeout`/`kernel_no_output`/…).

### GPU quota & environment parity (scope-boundary decisions)

- **D-13: Lightweight, NON-BLOCKING GPU-quota heads-up before push.** Surface a best-effort
  informational note (the 30h/week cap; remaining hours if the CLI exposes it) but **NEVER block the
  push.** Full GPU-hour tracking + gating is deliberately NOT built here — that is Phase-5-shaped
  budget discipline and would be scope creep. 🔗 Researcher: check whether the CLI exposes remaining
  GPU quota at all; if not, the note is a static reminder.

- **D-14: Document + record the kernel image/version; do NOT pin to match local.** Phase 4 does not
  force the `kaggle/python` image to match the local `uv.lock` (the pandas 3.0 / numpy 2.5 parity
  traps CLAUDE.md flags). Instead: document the parity risk in a reference doc, and **record the
  kernel image/version in provenance** (`kernel_run.json`/`meta.json`) when the log exposes it, so a
  future CV→LB divergence can be traced to an env diff. NOT in-notebook `!pip install` version
  pinning (fragile, needs internet-on which conflicts with D-06, slows every run). Pinning is a
  Phase-5 CV→LB concern.

### Claude's Discretion
- **`kernel_run.json` full schema** beyond the D-03 named fields — exact keys, and how
  detached/PENDING vs completed/pulled states are represented (planner's call; keep it a small,
  git-diffable JSON co-located with the experiment).
- **Exact kernel-metadata template shape** (`kernel-metadata.json.tmpl`) — kernel type
  (notebook vs script), language, `code_file` naming — following the existing `scripts/templates/`
  convention. Notebook + Python are the obvious defaults; researcher confirms required fields.
- **Precise backoff constants** (initial interval, multiplier, cap, jitter range) and the
  persistent-error threshold for D-10 — pick concrete values; researcher tunes against observed CLI
  behavior.
- **Exact traceback/error pattern set** for D-11 — finalize against the live kernel-log format.
- **Where the D-13 quota note and D-02 convert step surface in SKILL.md** — following the existing
  entry-point-sequencing + reserved-exit-code + gate-protocol conventions.
- **How `<username>` is resolved for the D-05 slug** (from `kaggle config view` / credential / a
  captured field) — researcher's open item.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent, scope, and success criteria
- `.planning/ROADMAP.md` §"Phase 4: Kaggle Kernel Execution (GPU Path)" — the fixed phase goal,
  the 3 success criteria, and the 2 suggested plans (04-01 kernel-metadata generation + push;
  04-02 timeout-bounded polling with backoff + output/pull + run-log traceback scan extending the
  result contract).
- `.planning/REQUIREMENTS.md` §Experiment **EXP-05** — the authoritative requirement text (push →
  run on GPU → poll to completion → pull results/artifacts, with silent-failure/traceback-in-log
  detection). Note SCORE-* (submission/LB) is Phase 5 — out of this phase.
- `.planning/PROJECT.md` §"Core Value", §Constraints, §"Key Decisions" — the locked decisions this
  phase must honor: "Local-first default, Kaggle Kernels for GPU/submissions; execution target set
  at init and changeable anytime", "CV-first scoring", "the same experiment runs local or on a
  kernel", the standalone (no shepsci dependency) constraint, and the Kaggle-limits constraint.

### Prior-phase decisions this phase EXTENDS (READ — the contracts are already locked)
- `.planning/phases/03-local-experiment-loop-ledger-strategy/03-CONTEXT.md` — **the contract Phase 4
  extends, never re-derives.** Specifically D-01 (`.py` local source, jupytext `.ipynb` at
  kernel-push time), **D-03 (`resolve_data_dir()` prefers `/kaggle/input/<slug>/` — the backend seam
  Phase 4 reuses)**, D-04 (`result.json` = per-fold + mean + std + metric + n_folds), **D-05/D-06
  (the recorder validates-then-persists; the fail-closed ladder; `FAILURE_REASONS` enum Phase 4 adds
  `kernel_error` to)**, D-10 (`meta.json` canonical / `ledger.jsonl` derived; provenance = run id,
  artifact hash, git commit, seed).
- `.planning/phases/02-competition-context-data/02-CONTEXT.md` — the Kaggle Gateway pattern
  (fail-closed 403 / exit-code / no-echo / timeout), the `config.json` shape
  (`competition_slug`, `competition.type`, `cv.scheme`), and the "declare / validate / never runtime
  pip install / degrade-don't-abort" posture the kernel tooling mirrors.
- `.planning/phases/01-workspace-credentials-egress-guardrails/01-CONTEXT.md` — D-10 workspace
  layout (`control/`, `experiments/exp-NNN/`, docs at root), `execution_target: local|kernel` set at
  init and overridable, the egress allowlist mechanism, `.gitignore` artifact patterns.

### Existing skill code the new scripts sit beside / extend (reuse the conventions)
- `scripts/kaggle_gateway.py` — **`run_kaggle(*argv, timeout)`: the ONE timeout-bounded, no-echo,
  exit-code CLI runner** every `kaggle kernels push/status/output` call MUST route through.
  Reuse its fail-closed / reserved-exit-code / `dump_last_error` patterns.
- `scripts/record_experiment.py` — **the recorder Phase 4 EXTENDS** (D-12): `FAILURE_REASONS`
  tuple, the D-06 validation ladder, `--run-exit-code` pre-classification, provenance staging. Add
  the log-scan rung + `kernel_error` here; do not fork a second recorder.
- `scripts/run_local.py` — the local runner Phase 4's `push/poll/pull` parallel (`--no-sync`,
  timeout-bounded, exit-code-out, stdlib-only, self-locating). Same posture, kernel backend.
- `scripts/templates/experiment.py.tmpl` — carries `resolve_data_dir()` (the `/kaggle/input` seam)
  and the `run_cv` harness; the convert step (D-02) turns THIS unchanged into the pushed notebook.
- `scripts/templates/config.json.tmpl` — `execution_target`, `competition_slug`, `competition.type`
  the kernel path reads; any internet toggle (D-06) is added here.
- `scripts/scaffold_experiment.py` / `scripts/init_workspace.py` — the self-locating, `--workspace`,
  section-safe-merge, template-writing conventions for the new `push/poll/pull/convert` scripts and
  the new `kernel-metadata.json.tmpl`.
- `SKILL.md` — entry-point sequencing, reserved-exit-code, and gate-protocol conventions the new
  kernel steps extend; the "Scripts (progressive disclosure)" table gains new rows.

### Technology stack, Kaggle command surface, and known risks (MANDATORY)
- `CLAUDE.md` — the prescriptive stack. For Phase 4 specifically:
  §"Kaggle Integration — Concrete Command Surface" (kernel-metadata schema, `competition_sources`,
  `enable_gpu`/`--accelerator`, accelerator IDs incl. `NvidiaTeslaT4`, GPU 30h/week + 12h-session +
  20GB `/kaggle/working` quotas, `enable_internet: false` default), §"Stack Patterns by Variant"
  (kernel path: author notebook / jupytext-convert, write `kernel-metadata.json`, `kaggle kernels
  push`, timeout-bounded Python poller, `kaggle kernels output` to pull, parse CV, append to
  ledger), §"Version Compatibility" + §"What NOT to Use" (Kaggle-image parity floors, internet-off
  default, no runtime pip install), §"Open Risks / Needs Implementation-Time Verification" (kernel
  `status` string parsing MEDIUM; `--unzip` MEDIUM; code-competition submission MEDIUM; image pins
  MEDIUM).
- `references/kaggle-cli-behavior.md` — the verified live CLI-behavior log to extend with kernel
  push/status/output findings.
- `references/egress-allowlist.md` — confirms `api.kaggle.com` + `storage.googleapis.com` are
  already allowlisted (kernel push/output route here); the auto-accept-defeats-allowlist caveat.

### External structure-only exemplar (NOT a dependency — do not import or couple to it)
- `~/.claude/plugins/cache/shepsci/kaggle-skill/2.3.0/` — its `poll_kernel.sh` and
  `kernel-metadata.json` are structure/command-surface exemplars ONLY. PROJECT.md forbids depending
  on it. Reimplement independently in Python (stdlib + the gateway), per the "loops/timeouts/JSON
  parsing belong in Python" rule.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`scripts/kaggle_gateway.py` → `run_kaggle()`** — the single timeout-bounded, no-echo,
  exit-code CLI runner. Every `kaggle kernels push/status/output` call goes through it; reuse its
  reserved-exit-code branches (rc==127 missing CLI, rc==124 timeout) and `dump_last_error`.
- **`scripts/record_experiment.py`** — the anti-lie recorder with `FAILURE_REASONS` +
  the D-06 ladder + `--run-exit-code`. Phase 4 adds the log-scan rung + `kernel_error` INTO it
  (D-12) — one recorder, one contract.
- **`scripts/run_local.py`** — the runner posture (`--no-sync`, timeout-bounded, exit-code-out,
  stdlib-only, self-locating) the kernel `push/poll/pull` scripts parallel.
- **`scripts/templates/experiment.py.tmpl`** — `resolve_data_dir()` already prefers `/kaggle/input/`
  and the `run_cv` harness already emits `result.json`; the convert step (D-02) reuses this
  UNCHANGED, so the same experiment runs on the kernel.
- **`control/config.json`** (`execution_target`, `competition_slug`, `competition.type`) and
  per-experiment `experiments/exp-NNN/` folders — the kernel path reads config and writes
  `kernel_run.json` + pulled artifacts into the existing folder structure.
- **`.gitignore`** — already anticipates `experiments/*/` artifact patterns; verify it covers pulled
  kernel artifacts and that `kernel_run.json` (small provenance, want it tracked) is NOT ignored.

### Established Patterns
- **Scripts are stdlib-only, self-locating (`Path(__file__)`), take `--workspace`, argparse-in /
  exit-code-out; the SKILL sequences them and holds any human loop** (Phase 2 D-10). New
  `convert/push/poll/pull` scripts follow this exactly.
- **Fail-closed + degrade-don't-abort** (Phase 2/3): reserved exit codes, `--no-sync` never
  silently installs, missing env prints `uv sync` remediation. Kernel tooling mirrors it.
- **Numbers are tooling-written from a machine-checked `result.json`, never AI-typed** (D-05/D-06) —
  the kernel path pulls `result.json` and routes it through the SAME recorder.
- **CLAUDE.md is the stack/version/security authority.**

### Integration Points
- `control/config.json` — read for `execution_target`, `competition_slug`, `competition.type`;
  gains an internet toggle (D-06) if config-level.
- `experiments/exp-NNN/kernel_run.json` — NEW: the push→poll→pull handoff + kernel provenance
  (slug, version, accelerator, effective internet flag, image/version, detached/PENDING status).
- `experiments/exp-NNN/result.json` + `artifacts/` — pulled kernel output lands in the SAME contract
  the local runner produces; `record_experiment.py` validates it identically (+ log scan).
- `control/ledger.jsonl` + `meta.json` — kernel runs record into the SAME MEM-01 ledger with
  provenance; a kernel-source marker distinguishes backend.
- `kaggle_gateway.run_kaggle()` — the choke point for all kernel CLI calls.
- New `scripts/templates/kernel-metadata.json.tmpl` — generated per push (accelerator, internet,
  is_private, competition_sources, id/code_file).

</code_context>

<specifics>
## Specific Ideas

- The kernel loop is **`convert → push → poll → pull → record`** with **discrete re-runnable
  steps** — the user explicitly wants to resume `poll`/`pull` after an interruption **without
  re-pushing / re-burning GPU time** (D-01, D-09).
- The `.ipynb` convert is a **separate, inspectable step** but must stay **mechanical/regenerated
  from `experiment.py`** — a build artifact, not a hand-maintained source (D-02 guard).
- Handoff + kernel provenance lives in **`experiments/exp-NNN/kernel_run.json`**, co-located and
  git-tracked (D-03).
- Defaults: **T4×2** accelerator, **stable `<username>/<comp-slug>-exp-NNN` slug with versioned
  re-push**, **private**, **internet-off (config toggle, effective value recorded in provenance)**,
  **competition_sources from config slug** (D-04..D-07).
- Poller: **~2h bounded default (configurable)**, **exponential backoff + cap + jitter**, **tolerate
  transient poll errors / fail-closed on persistent**, **detach-not-cancel on timeout** (D-08..D-10).
- Silent-failure is the headline: scan pulled log for **traceback + error markers**, a hit ⇒ FAILED
  even if `complete`; wired as a **first rung in `record_experiment.py`** adding exactly one
  `kernel_error` reason, reusing the rest of the D-06 enum (D-11, D-12).
- Quota: **non-blocking heads-up only** (D-13). Parity: **document + record image, don't pin**
  (D-14).

</specifics>

<deferred>
## Deferred Ideas

- **GPU-hour tracking + push gating over a budget** — Phase 5-shaped budget discipline (SCORE-*).
  Phase 4 stops at a non-blocking heads-up (D-13). Add a real GPU-budget model only alongside the
  submission-budget model.
- **In-notebook version pinning to match the kaggle/python image** — deferred as a Phase-5 CV→LB
  parity concern (D-14). Revisit if an observed CV→LB divergence is traced to an env diff; conflicts
  with the internet-off default until then.
- **Active remote kernel cancel on timeout** — rejected for D-09 (detach-not-cancel preserves GPU
  time). Could revisit if abandoned-kernel accumulation becomes a real problem.
- **Submission FROM kernel output** (code-competition notebook→submission flow) — Phase 5 (SCORE-*);
  STATE.md already flags the code-competition submission path as needing validation for the target
  competition type.
- **Deliberate per-experiment notebook edits** beyond the mechanical convert — allowed as an
  intentional, provenance-captured deviation (D-02), but the default is untouched-from-`experiment.py`;
  a first-class "author a kernel-only notebook" flow is not in v1.

### Reviewed Todos (not folded)
None — no pending todos matched Phase 4 scope.

</deferred>

---

*Phase: 4-Kaggle Kernel Execution (GPU Path)*
*Context gathered: 2026-07-11*
