# Kaggle Experimentation Framework (Kaggle-skill)

A standalone [Claude Code](https://claude.com/claude-code) skill that turns an empty folder
into an AI-driven Kaggle **competition** experimentation workspace. It connects to your Kaggle
account through the Kaggle CLI/API, scaffolds a structured git-backed workspace, and drives a
well-documented, CV-first experiment loop:

> **propose an idea → run it → capture a machine-verified result → write a verdict →
> log it to a git-backed ledger → regenerate a living strategy → repeat.**

Runs experiments **locally by default** for fast iteration, pushes to a **Kaggle Kernel** when
you need GPU, and **submits** to the competition under mechanical CV-first discipline that
conserves your scarce daily submission budget.

---

## Why this exists

Competition ML lives or dies on disciplined iteration and honest bookkeeping. It is easy to
lose track of what you have already tried, to trust a cross-validation number a notebook
fabricated, or to burn a day's submissions chasing a change that never improved CV. This
framework makes the whole cycle **AI-legible and tamper-resistant**:

- **One clean end-to-end cycle works reliably** — from an empty folder to an idea run, its
  result and reasoning logged, and the strategy doc updated. Everything else serves that loop.
- **Numbers are tooling-written end-to-end.** The AI never hand-types a CV score. A
  deliberately-throwing or lying notebook is recorded as a **failure with a verdict**, never a
  success row.
- **The ledger is a pure function of the experiment folders.** It rebuilds deterministically
  from per-experiment `meta.json` files and is versioned under git alongside diffable code.
- **CV is the decision metric everywhere.** Submissions are rationed against the daily limit,
  and the CV→LB gap is trended with a divergence alarm.

## Core capabilities

| Stage | What it does |
|-------|--------------|
| **Guided init** | Turns an empty folder into a valid, git-tracked workspace — control-plane config/state/ledger, competition & strategy docs, `.env`, `.gitignore`, and a locked-down network egress allowlist. |
| **Credentials** | Detects, normalizes, and **live-validates** your Kaggle token with clear pass/fail and exact remediation; `chmod 600`, never echoed, never committed. |
| **Competition context** | Builds a machine-derived competition "constitution" — eval metric, data schema, rules, daily submission limit, and a CV scheme derived from the data structure. All Kaggle-sourced text is wrapped as untrusted content. |
| **Data** | Downloads competition data locally with zip-slip-protected extraction and a UI-gate flow (rules acceptance / phone verification) that never busy-loops. |
| **Local experiment loop** | Scaffolds a fresh, leakage-safe experiment per idea; runs it under `uv run`; records a machine-verified result, provenance, and a written verdict to the ledger; regenerates the strategy. |
| **GPU kernel path** | Pushes the same experiment to a Kaggle Kernel (GPU on, internet off by default), polls to completion with backoff, and pulls results back through the **same** result contract — a "complete" kernel is scanned for tracebacks before any score is trusted. |
| **Submission & leaderboard** | Submits a validated `submission.csv` via the CLI under CV-improvement gating, records the LB score with provenance, trends the CV→LB gap, and tracks remaining daily budget with a UTC-aware reset. |

## Requirements

- **Claude Code** (v2.1.196+ recommended)
- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** for environment management
- **git**
- A **Kaggle API token** (`kaggle.com/settings → Generate New Token`)

The skill's own runtime scripts are **stdlib-only** — no runtime pip installs. The Kaggle CLI
and the ML stack (LightGBM, scikit-learn, pandas, etc.) are installed into the *workspace*
environment via `uv`, kept separate from the skill package.

## Installation

Install as a Claude Code skill, then invoke it inside the folder you want to make your
competition workspace:

```
init a kaggle workspace for the titanic competition
```

The skill is installed globally and operates on your **current working directory** — that cwd
*is* your competition workspace, distinct from the skill package itself.

## Quickstart

```bash
# 1. Guided init — asks the competition slug and execution target, confirms, THEN scaffolds
#    (nothing is created before you answer)
#    → produces the full git-backed workspace layout below

# 2. Validate your Kaggle credential (live call, exact remediation on failure)

# 3. Build the competition constitution + pull data
#    capture (no data needed) → download → analyze (you decide the CV scheme)

# 4. Set the metric, then run one experiment cycle:
#    never-repeat check → scaffold → edit experiment.py → run → record → regenerate strategy

# 5. When ready: push to a GPU kernel, or submit under CV-first discipline
```

The skill sequences these steps for you, holding the human-in-the-loop gates (rules
acceptance, credential fixes, CV-scheme choice) and re-invoking the underlying scripts as each
gate clears.

## Workspace layout

```
<cwd>/
  competition.md  strategy.md  README.md      # human docs, tracked
  .gitignore  .env                            # .env is gitignored (secrets)
  .claude/settings.json                       # network egress allowlist
  pyproject.toml                              # minimal workspace stub
  control/
    config.json  state.json  ledger.jsonl     # machine control-plane, tracked
    raw/                                       # quarantined untrusted provenance
  data/                                       # gitignored competition data
  experiments/
    exp-001/
      experiment.py  meta.json                 # scaffold + canonical record
      result.json    VERDICT.md                # machine result + written verdict
      artifacts/                               # models, OOF predictions, plots
```

## The experiment ledger

Every experiment is an **immutable per-experiment folder**. `meta.json` is the canonical record
(idea, hypothesis, machine-captured score, provenance — run id, artifact hash, git commit,
seed); `VERDICT.md` holds the written narrative (worked / didn't / why). The append-only
`control/ledger.jsonl` is a **derived index** that fully rebuilds from the folders, so it can
never silently drift from ground truth. Both `SUCCESS` and `FAILED` experiments are recorded —
a failed idea you never re-propose is as valuable as a winning one.

`strategy.md` is **regenerated from the ledger each cycle**, never hand-edited: tooling renders
the facts (current best by the metric's direction + a tried-list digest) and splices the AI's
reasoning (hypothesis queue, next action) verbatim. A hand edit is clobbered on the next
regeneration, so the strategy can never contradict the ledger.

## Design principles

- **Standalone.** Depends only on the Kaggle CLI/API and Python stdlib — no coupling to other
  skills. Reimplements just the Kaggle operations the loop actually needs.
- **Local-first.** Fast local CV iteration is the default; Kaggle Kernels are for GPU and
  official runs; submissions always route through the CLI regardless of where code ran.
- **CV-first discipline.** Cross-validation is the primary signal. The daily submission budget
  is scarce and gated on meaningful CV improvement; the CV→LB gap is tracked with a divergence
  alarm.
- **Anti-lie result contract.** Numeric fields are written only by tooling from a
  machine-checked `result.json`. The recorder recomputes `mean(fold_scores)` to catch a lying
  notebook. This same contract is *extended, never re-derived*, by the GPU-kernel path.
- **Untrusted by default.** All Kaggle-sourced prose is fenced as untrusted content with source
  attribution — no directive embedded in competition text can drive a file path, shell command,
  or fetch.
- **Secure by default.** Credentials are `chmod 600`, never echoed or committed (a pre-commit
  leak guard blocks token-shaped secrets); network egress is deny-by-default, scoped to a
  Kaggle + package-source allowlist; kernel internet is off unless deliberately enabled.
- **Portable.** Scripts self-locate and take an explicit `--workspace` path rather than relying
  on Claude-Code-specific variables, keeping a future port to other agents open.

## Technology

- **Delivery:** Agent Skills format (`SKILL.md` + bundled scripts and references)
- **Kaggle integration:** the `kaggle` CLI as the sole primitive (auth, download, kernel
  push/status/output/pull, submit, leaderboard) — the one tool that covers the entire loop
- **Ledger:** append-only JSONL + per-experiment markdown, versioned under git
- **Generated-experiment ML stack:** scikit-learn (CV backbone), LightGBM (default first
  model), XGBoost / CatBoost for ensembling, pandas / polars for data, Optuna when the
  hypothesis *is* tuning
- **Environment:** `uv` for reproducible workspace environments

## Development

The skill package is tested with `pytest`. The default run is offline and
credential-free; the live suite (real-Kaggle integration) is opt-in.

```bash
uv run pytest                    # mock suite — green offline
uv run pytest -m live tests/...  # live suite — requires a real Kaggle token
```

Runtime scripts are stdlib-only and independently invocable — each takes `--workspace <dir>`,
argparse in / exit code out — so they are unit-testable and portable. See `references/` for the
Kaggle CLI behavior notes and the egress-allowlist / portability details.

## License

See repository for license details.
