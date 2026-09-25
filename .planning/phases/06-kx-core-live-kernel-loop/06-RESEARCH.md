# Phase 6: kx Core & Live Kernel Loop - Research

**Researched:** 2026-09-25
**Domain:** Python CLI packaging (uv), in-process Kaggle SDK (`kaggle` 2.2.3 / `kagglesdk` 0.1.33), Kaggle script kernels, fail-closed experiment recording
**Confidence:** HIGH for the Kaggle API surface and the v1 inventory (both read from installed source and the repo). MEDIUM for the new design contracts (envelope, `experiment.json`, prediction format): they are recommendations, and the live run in this phase has to confirm them.

## Summary

Phase 6 turns 29 stdlib scripts (9,445 LOC, 40 test modules, 354 collected test nodes, 341 passing offline) into one installable `kx` package. The package runs the core-value loop live on Titanic. The v1 loop logic that matters is already good and live-proven: the fail-closed recorder ladder, the byte-stable ledger rebuild, the strategy regeneration, the bounded detach-not-cancel poller and the leak-scan hook. **Port it; don't rewrite it.** What changes is the plumbing around it:
- one `kx` entry point that prints one JSON envelope per call
- an in-process Kaggle adapter on `kaggle.api`/`kagglesdk`, replacing the shell-and-regex CLI gateway
- script kernels instead of jupytext notebooks
- an `experiment.json` spec
- a standard prediction format that the recorder checks

Reading the installed `kaggle` 2.2.3 source turned up four facts the planner must design around. None of them is in the spike notes:
1. **`import kaggle` (and even `from kaggle.api.kaggle_api_extended import KaggleApi`) runs `api.authenticate()` at import time.** With no credential it prints auth help to **stdout** and calls `exit(1)`. Verified live in this session.
2. **`kernels_push` defaults a missing `enable_internet` key to `True`**, even though the docs say `false`. The CLI's push wrapper also **exits 0 on a server-side push error**, and on invalid competition sources it only prints a line.
3. **The SDK's HTTP calls have no timeout.**
4. **`kernels_output` in 2.2.3 writes server-supplied file names with no path check.** The upstream "Next" changelog fixes this; the fix is not released.

All four have known mitigations: a lazy guarded import, explicit metadata, a `SIGALRM` deadline (verified in this session) and our own safe-path output download.

Packaging was verified empirically. A `uv_build` project with `[project.scripts] kx = "kx.cli:main"` is installed editable by `uv sync --project <skill-dir>` run from an empty workspace folder. After that, `uv run --project <skill-dir> kx …` runs with **cwd = the workspace** and prints only the envelope on stdout. That satisfies CORE-06 with the lock controlling `kaggle==2.2.3`.

**Primary recommendation:** build `src/kx/` as a uv-packaged CLI:
- an argparse dispatcher that emits a JSON envelope and guards stdout at the file-descriptor level
- one injectable `KaggleAdapter` (in-process SDK, lazy guarded import, deadline-bounded)
- ported v1 loop modules, whose tests carry over with only import changes

Slice the work as a walking skeleton (`uv sync` + `kx init` live) followed by `sync` → `new` → `run` (live Titanic) → `strategy`, plus the failure-path proofs and the CORE-07 deletions.

## Project Constraints (from CLAUDE.md)

CLAUDE.md is authoritative, except where the v2 decisions in REQUIREMENTS, ROADMAP, PROJECT or the spike findings explicitly supersede it. Those cases are marked **SUPERSEDED**.

| Directive (CLAUDE.md) | Status for Phase 6 |
|---|---|
| Claude Code first; avoid hard deps that block porting to opencode/other agents | Applies. Keep `kx` a plain console script that takes `--workspace` (default cwd); nothing requires `${CLAUDE_SKILL_DIR}` at runtime. |
| Kaggle CLI/API only, no dependency on external skills (no shepsci/kaggle-skill) | Applies. PROJECT.md narrows it: "**The `kaggle` package only** (CLI + its bundled `kagglesdk`)". So there are no new runtime deps: no pydantic, pyarrow, numpy or pandas in the skill env. `requests` comes in transitively with `kaggle`. |
| Stdlib-only helper scripts | **SUPERSEDED** (PROJECT Key Decisions, spike requirements): the skill may import `kaggle.api`/`kagglesdk`. |
| Standardize on the `kaggle` CLI for push/status/output/submit; MCP optional | **Refined** by PROJECT.md: "A Kaggle adapter built on `kaggle.api`/`kagglesdk`". See §Kaggle API surface for why the adapter uses in-process SDK calls. |
| jupytext `.py`→`.ipynb` at kernel push | **SUPERSEDED** (CORE-07, spikes 002/003): script kernels, no conversion. |
| Local-first default | **SUPERSEDED**: a kernel is the default runtime; local runs are Phase 8 (RUN-06). |
| `enable_internet: true` NOT by default | Applies, with extra force: kaggle 2.2.3 defaults a *missing* key to `True` (see Pitfall 2). |
| Never echo/commit credentials; `chmod 600`; gitignore; validate via exit codes | Applies. "Validate via exit codes" becomes "validate via a live SDK call, never echoing". `chmod` is now *reported*, never applied (the consent flows are removed, CORE-07). |
| No bare `pip install` at runtime; declare deps, let uv install | Applies. `uv sync` is the only install step (CORE-06). |
| Respect submission limits / kernel quotas | Applies. Phase 6 never submits. Live checks run CPU kernels only. |
| GSD workflow enforcement (edits only through GSD commands) | Applies to execution. |
| Use `ruff`/`pytest`; manifest test for SKILL.md frontmatter | pytest 9.1.1 is present. ruff is not installed; it is optional (Planner's discretion). |
| Kernel status parsing MEDIUM risk; always bound the poll | RESOLVED: use the SDK enum `KernelWorkerStatus.<NAME>.name` (verified in source). Always bound it. |
| `competitions download --unzip` unreliable | Not Phase 6 (download is PROF-05, Phase 7). |

<user_constraints>
## User Constraints (no CONTEXT.md — contract from ROADMAP + REQUIREMENTS + spike findings)

No `/gsd-discuss-phase` was run. Per the orchestrator, the locked contract is:
- the ROADMAP Phase 6 success criteria (quoted in `<phase_requirements>` below)
- REQUIREMENTS.md
- the VALIDATED spike findings in `.claude/skills/spike-findings-kaggle-skill/`

### Locked Decisions (from ROADMAP / REQUIREMENTS / spike requirements)
- One `kx` CLI; every subcommand prints **exactly one JSON object** with `status` and `next_action`. It replaces the 28 scripts and the exit-code protocol.
- One `uv sync` on the skill's locked environment installs everything, `kaggle` (CLI + SDK) included.
- `kx init`: workspace + live credential validation in one step, masked, never echoed, no consent prompts.
- `experiment.json` holds: idea, hypothesis, template, runtime target, data/kernel/model sources, accelerator, runtime limit. kx validates it and refuses an invalid one before any push.
- `kx sync <comp>` → `profile.json` from **structured API facts only**:
  - competition fields incl. canonical ref, `evaluation_metric`, `max_daily_submissions`, code-only flag
  - the data-files summary
  - the root listing
- The tabular template's CV scheme is **AI-written code**, with its reasoning recorded. This replaces the 4-option CV enum.
- `kx run`: private **script** kernel, internet off, CPU, no notebook conversion, bounded poll, pull, record.
- One standard OOF + test prediction format that the recorder validates (ENS-01).
- The v1 fail-closed contract, ledger, never-repeat digest and regenerated strategy keep working.
- CORE-07 removals, each with its tests:
  - rules-prose scraping, exit-78 and "assumed 5/day"
  - jupytext conversion
  - the credential consent flows
  - the default egress allowlist (now a documented opt-in whose enforcement is **unverified**)
  - the fold-noise margin
- Spike rules:
  - the data resolver checks `/kaggle/input/competitions/<canonical>` first
  - record `KAGGLE*` env **keys only**
  - read the version back, never guess it
  - accept only live-verified accelerator IDs (CPU; T4)
  - whitelist the benign mistune/nbconvert warnings
  - never submit; live checks on Titanic or Playground only
- "Done" = a LIVE run on a real competition, recorded in the phase verification.

### Claude's Discretion (flagged below as "Planner's discretion — recommended: X")
- Envelope field names and status vocabulary; subcommand set beyond init/sync/new/run
- Workspace file layout details; the kernel slug naming scheme
- Validation library for `experiment.json` (recommended: stdlib)
- The concrete prediction file format (recommended: stdlib-readable CSV `kx-preds/1`)
- How much of v1's dormant submission code survives until Phase 9

### Deferred Ideas (OUT OF SCOPE for Phase 6)
- PROF-02..05: mode classification, user confirmation, pass-2 nested listing, data download
- CORE-05: the ~150-line budget and `references/types/*.md` (Phase 7)
- TMPL-02..06, RUN-02..07, SUB-*, RES-*, ENS-02
- `kx select`, dataset-version pinning, `docker_image` pinning, T4×2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | One `kx` CLI; every subcommand prints one JSON object with `status` + `next_action` | §Pattern 1 (envelope + fd-level stdout guard + JSON argparse errors); contract test in §Validation |
| CORE-02 | `kx init`: workspace + live credential validation, masked, never echoed, no consent prompts | §Pattern 3 (guarded `load_api`), §Kaggle API surface A, port of `init_workspace.py` helpers + `check_credentials._mask/detect_source` |
| CORE-03 | `experiment.json` validated before any run | §experiment.json schema (stdlib validator, strict keys, placeholders refused) |
| CORE-04 | Fail-closed contract, ledger, never-repeat digest, strategy keep working under kx | §Carry-over (port `record_experiment`, `experiment_meta`, `rebuild_ledger`, `regen_strategy`, `lb_gap`, `submissions_log` with their tests) |
| CORE-06 | One `uv sync` installs everything incl. `kaggle` | §Packaging (verified `uv sync --project` + `[project.scripts]`) |
| CORE-07 | Remove superseded v1 paths + tests | §v1 Inventory (exact file/test lists per path) |
| PROF-01 | `kx sync` → `profile.json` from structured API facts only | §Kaggle API surface B (spike-001 calls, field allow-list, canonical ref from `ref` URL) |
| RUN-01 | Private script kernel, internet off, bounded poll, pull, record, no conversion | §Kaggle API surface C/D/E, §Script kernel packaging |
| TMPL-01 | Tabular template with AI-written CV code + recorded reasoning | §Tabular template (the `assign_folds` AI block + `cv.reasoning` in `experiment.json`) |
| ENS-01 | One standard OOF + test prediction format, validated by the recorder | §Standard prediction format `kx-preds/1` (stdlib CSV validator) |

**Success criteria (verbatim, ROADMAP Phase 6):**
1. From an empty folder, one `uv sync` installs everything the skill needs (including the `kaggle` CLI and SDK), and `kx init` sets up the workspace and validates the user's Kaggle credential live in one step: masked, never echoed, no consent prompts.
2. Every `kx` subcommand prints exactly one JSON object with a `status` and a `next_action`, and the AI completes the loop by following `next_action` alone; each experiment is declared in an `experiment.json` (idea, hypothesis, template, runtime target, sources, accelerator, runtime limit) that kx validates, refusing an invalid one before anything is pushed.
3. LIVE: `kx sync titanic` writes a `profile.json` built only from structured Kaggle API facts (competition fields including the canonical ref, `evaluation_metric`, `max_daily_submissions` and the code-only flag; the data-files summary; the root file listing), with nothing scraped from prose.
4. LIVE core-value cycle on Titanic (or a Playground Series competition): `kx new` scaffolds the tabular template with AI-written CV code and records the reasoning behind it; `kx run` pushes it as a private CPU script kernel with internet off and no notebook conversion, polls with a bound, pulls the outputs and records a machine-checked CV score, with OOF and test predictions in the one standard format that the recorder validates; the verdict lands in the ledger and the strategy doc is regenerated.
5. LIVE: v1's fail-closed contract holds under `kx`: a kernel run that throws, or writes an invalid `result.json`, is recorded FAILED and never with a score, and the never-repeat digest lists the ideas already tried. The superseded v1 paths are gone along with their tests: rules-prose scraping, exit-78 and "assumed 5/day"; jupytext conversion; the credential consent flows; the default egress allowlist (now a documented opt-in); the fold-noise margin.
</phase_requirements>

## Architectural Responsibility Map

This is not a web app. The "tiers" are: the AI (following SKILL.md), the local `kx` process, the workspace files, the Kaggle API, and the Kaggle kernel runtime.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Deciding the idea, hypothesis, CV code, features, model, verdict prose and strategy reasoning | AI (SKILL.md + `next_action`) | — | "AI decides, tooling writes": the AI authors prose and code, never numbers |
| Command dispatch, JSON envelope, `next_action` chain | `kx` CLI (local process) | — | A single entry point (CORE-01) |
| Credential detection / masking / live validation | `kx` CLI → Kaggle API (SDK introspect / authenticated call) | — | The secret never leaves the process; only a masked form is printed |
| Competition facts (`profile.json`) | Kaggle API (SDK `get_competition`, files summary, root tree) | Workspace files (`control/profile.json`) | Structured facts only (PROF-01) |
| `experiment.json` validation | `kx` CLI (stdlib validator) | — | Must refuse before any network side effect |
| Training, CV folds, OOF/test predictions, `result.json` | Kaggle kernel runtime (script kernel, Python 3.12.13, Kaggle image) | — | Kernel-first runtime; the local env has no ML stack in Phase 6 |
| Push / poll / pull / version read-back / image provenance | `kx` CLI → Kaggle API (SDK `save_kernel`, `get_kernel_session_status`, `list_kernel_session_output`, `get_kernel`) | — | Structured responses; no prose regex |
| Fail-closed scoring (status rung, log scan, `result.json` ladder, preds validation) | `kx` CLI (recorder) | Workspace files (`meta.json`, `ledger.jsonl`) | Tooling writes every number (v1 D-05/D-06) |
| Ledger / never-repeat digest / strategy | Workspace files (git-backed JSON/JSONL/markdown) | `kx` CLI renders them | Pure functions of `meta.json` folders + the AI reasoning file |

## Standard Stack

### Core
| Library / Tool | Version | Purpose | Why Standard |
|---|---|---|---|
| `kaggle` (CLI + `kaggle.api`) | **2.2.3, pinned exactly** (2.2.4 exists, released 2026-07-23) | Auth, competition facts, kernel push/status/output/metadata | The only dependency PROJECT.md allows. Every spike and live signature was verified on 2.2.3 [VERIFIED: uv.lock + PyPI JSON]. Upgrading to 2.2.4 is a deliberate re-verification task, not part of Phase 6. |
| `kagglesdk` | 0.1.33 (transitive via lock; 0.1.37 latest) | Typed request/response objects (`ApiGetCompetitionRequest`, `ApiSaveKernelResponse`, `KernelWorkerStatus`) | It ships with `kaggle`; not a new dependency [VERIFIED: uv.lock] |
| Python (skill env) | ≥3.11 floor; local 3.13.13 | Runs `kx` | `kaggle` requires ≥3.11 [VERIFIED: PyPI] |
| uv | 0.11.14 local | `uv sync --project <skill>`, `uv run --project <skill> kx` | Verified end to end in this session [VERIFIED: local probe] |
| `uv_build` build backend | `uv_build>=0.11,<0.12` (matches local uv; docs now show `>=0.12.19,<0.13` for uv 0.12) | Builds and installs the `kx` console script editable | Verified: produced `.venv/bin/kx` and a `.pth` editable install [VERIFIED: local probe] |
| git | 2.43.0 | Workspace versioning, leak-scan hook | v1 contract (MEM-01) |

### Supporting
| Library | Version | Purpose | When to Use |
|---|---|---|---|
| pytest | 9.1.1 (dev group, locked) | Unit + contract + live tests | Always (`uv run pytest`) |
| `requests` | transitive via `kaggle` | Streaming kernel-output downloads with a timeout in kx's own safe-path loop | `pull_output` only |
| pandas / numpy / scikit-learn / lightgbm | **Kaggle image versions on the kernel**; locally only in an optional, non-default dependency group | The tabular template runs *on the kernel*. The local group exists only to unit-test the template harness. | Group `template-test` (Planner's discretion — recommended), run with `uv run --group template-test pytest tests/template` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|---|---|---|
| In-process SDK adapter | Subprocess `python -m kaggle kernels push/status/output` (the v1 gateway pattern) | Push/status signatures are live-verified. But the push wrapper is fail-open (prints `Kernel push error: …` and exits 0; invalid sources only print), and the version has to be regex-scraped. Use it only if the SDK path shows a blocker live. |
| stdlib `experiment.json` validator | pydantic v2 (2.13.5) / jsonschema (transitive via jupytext→nbformat) | Better messages and schema export, but it breaks the "kaggle package only" constraint, or leans on a transitive dependency. |
| CSV `kx-preds/1` | Parquet (pyarrow) / `.npy` | Parquet is typed and compact but needs pyarrow in the skill env (constraint). `.npy` has no ids, so blending across experiments can misalign rows. |
| `src/kx` layout | flat `kx/` at the repo root (`module-root = ""`) | Either works with uv_build. `src/` is the uv default and is verified. |

**Installation (skill; what the AI runs once, from the empty workspace):**
```bash
uv sync --project ${CLAUDE_SKILL_DIR}              # creates ${CLAUDE_SKILL_DIR}/.venv, installs kaggle==2.2.3 + kx (editable)
uv run --project ${CLAUDE_SKILL_DIR} kx init       # cwd stays the workspace (verified)
```

**Version verification:** `kaggle` 2.2.4 is the latest on PyPI (2026-07-23), and the lock holds 2.2.3 (2026-06-25). `kagglesdk` 0.1.37 is the latest, and the lock holds 0.1.33. The 2.2.4 changelog touches auth ("avoid skipping auth for programmatic imports", #1117), paging and competition limits (#1144). **Stay on 2.2.3 for Phase 6** [VERIFIED: PyPI JSON API + GitHub CHANGELOG].

## Package Legitimacy Audit

slopcheck could not be installed in this environment (`pip install slopcheck` failed silently). Each package below was checked against the PyPI JSON API (age and source repo). No new *runtime* package is introduced: `kaggle` is already locked. Per protocol, the entries are tagged by provenance.

| Package | Registry | Age (first upload) | Source Repo | slopcheck | Disposition |
|---|---|---|---|---|---|
| kaggle | PyPI | 2018-01-30 | github.com/Kaggle/kaggle-cli | unavailable | Approved: already locked 2.2.3, official Kaggle project (CLAUDE.md sources) |
| uv-build | PyPI | 2025-02-12 | github.com/astral-sh/uv | unavailable | Approved: official Astral backend, cited from docs.astral.sh; verified working locally |
| pytest | PyPI | 2010-11-25 | github.com/pytest-dev/pytest | unavailable | Approved: already locked |
| pandas / numpy / scikit-learn / lightgbm | PyPI | 2009 / 2006 / 2011 / 2017 | (well-known) | unavailable | **[ASSUMED]**: only if the planner adopts the optional `template-test` group. Human-verify before adding. |

**Packages removed due to a [SLOP] verdict:** none. **Packages flagged [SUS]:** none. Because slopcheck was unavailable, the planner should gate any *new* package (only the optional template-test group) behind `checkpoint:human-verify`.

## v1 Codebase Inventory & Disposition (Research Q1)

**Counts:**
- 29 `.py` scripts in `scripts/` (9,445 LOC) and 14 templates in `scripts/templates/` (729 LOC)
- 40 test modules plus `conftest.py` and `cv_fixtures.py` (9,607 LOC)
- 354 collected nodes: 341 passed, 1 skipped (`test_run_cv`, no numpy) and 12 `live` deselected; the offline run takes 12.4 s

All of this was [VERIFIED: repo, `pytest --collect-only`].

**Disposition legend:**
- **PORT**: moved into `src/kx/` with logic unchanged; only the imports change.
- **ADAPT**: moved, then reworked.
- **DELETE**: removed along with its tests.
- **DORMANT**: kept in `kx` but not wired to any subcommand until a later phase.

**Totals: 9 PORT, 10 ADAPT (1 of them DORMANT), 10 DELETE (5 of them are the CORE-07 paths).**

### Scripts

| v1 script (LOC) | Disposition | kx destination / reason | v1 tests (nodes) → fate |
|---|---|---|---|
| `experiment_meta.py` (125) | PORT | `kx/ledger.py` (`to_ledger_row`, `validate_meta`, `LEDGER_ROW_KEYS`, 11-key row unchanged) | `test_experiment_meta` (12) → port |
| `rebuild_ledger.py` (131) | PORT | `kx/ledger.py` (`rebuild_ledger_file`, atomic) | `test_rebuild_ledger` (6) → port |
| `regen_strategy.py` (304) | PORT | `kx/strategy.py` + `kx strategy --reasoning-file` | `test_regen_strategy` (14) → port |
| `lb_gap.py` (237) | PORT | `kx/lb_gap.py` (strategy's CV→LB section; Phase 9) | `test_lb_gap` (4) → port |
| `submissions_log.py` (565) | PORT | `kx/submissions_log.py` (strategy reads it; Phase 9). Drop the exit-78 wording in docstrings | `test_submissions_log` (9), `test_budget` (7) → port |
| `metric_registry.py` (44) | PORT | `kx/metrics.py` (`REGISTRY`). Optionally add `mse` | `test_metric_registry` (23) → port |
| `leak_scan.py` (139) | PORT | `kx/leak_scan.py`, still copied verbatim into the workspace `.githooks/pre-commit`. **Must stay stdlib-only**: the hook runs under the system `python3`, not the skill venv | `test_leak_scan` (9) → port |
| `safe_extract.py` (82) | PORT | `kx/safe_extract.py` (Phase 7 bundle download). Its member-path check pattern is reused for the output pull | `test_extract` (7) → port |
| `untrusted.py` (72) | PORT (dormant) | `kx/untrusted.py` (Phase 10 research notes) | `test_untrusted` (4) → port 3; **delete** `test_no_competition_text_reaches_subprocess` (it imports `capture_competition`) |
| `record_experiment.py` (498) | ADAPT | `kx/record.py`: keep the status rung (CR-01), the log-scan rung (D-11/WR-03), the ladder and the anti-lie mean. **Add** a `predictions_invalid` rung (ENS-01). Carry fields forward from `experiment.json` (no meta stub). `artifact_hash` = sha256(`train.py`). Read result/preds from `output/` | `test_record_experiment` (14), `test_record_kernel` (13) → adapt (keep the benign-noise fixtures) |
| `init_workspace.py` (584) | ADAPT | `kx/workspace.py` + `kx init`. Keep `create_if_absent`, `write_control_json`, `deep_merge_add_missing`, `set_config_field`, git init/leak hook/scaffold commit. **Drop** `merge_settings`, `write_settings_json`, `_union_list`, `warn_if_socat_missing`, the `.env`/pyproject/competition.md templates and `execution_target` | `test_init_workspace` (7) adapt (drop the settings assertions); `test_gitignore` (1) adapt; `test_config` (2) delete (execution_target is gone) |
| `check_credentials.py` (483) | ADAPT (partial) | `kx/credentials.py`: keep `_mask`, `_detect_token_type`, `detect_source`. **Delete** `handle_chmod`, `handle_env_population`, `_populate_env_file`, `--yes`, `state.json` credential writes via subprocess list | `test_credentials` (7): delete `test_chmod_600`, `test_chmod_600_requires_consent`, `test_env_population_requires_consent` (CORE-07); adapt the other 4. `test_credentials_live` (1) → `kx init` live |
| `kaggle_gateway.py` (264) | ADAPT | `kx/kaggle_adapter.py` (SDK-first). Keep a `run_kaggle` subprocess runner (via `sys.executable -m kaggle`, no-echo, timeout) for any remaining CLI use, plus `dump_last_error`. **Delete** exit constants 65/69/75/77/**78**, `preflight_entered` and `classify_gate` (Phase 7 will use SDK `user_has_entered`) | `test_gateway` (7): delete the preflight/classify/exit-code tests; keep a no-echo runner test |
| `poll_kernel.py` (354) | ADAPT | `kx/kernel.py`: keep `poll_loop`, `compute_delay`, `TERMINAL`/`IN_FLIGHT`, detach-not-cancel. The status source becomes the SDK enum `.name` (the `classify_status` regex is kept only as a CLI fallback) | `test_poll_kernel` (4) → adapt |
| `push_kernel.py` (305) | ADAPT | `kx/kernel.py`: script metadata builder, SDK push, version read-back, accelerator enum (drop the **retired `NvidiaTeslaP100`**) | `test_push_kernel` (4) → rewrite; replace `fixtures/kernel-metadata.golden.json` with a script golden |
| `pull_kernel.py` (242) | ADAPT | `kx/kernel.py`: own safe-path download loop over `list_kernel_session_output`, log from `response.log`, provenance from `get_kernel` metadata | (no dedicated test) → new tests |
| `scaffold_experiment.py` (338) | ADAPT | `kx new`: mint `exp-NNN`, render `train.py` from the tabular template with `repr()` literals (keep the CR-01 injection guard), write the `experiment.json` draft. **Drop** the CV enum and local sample-file lookup | `test_scaffold_experiment` (9) adapt; `test_resolve_data_dir` (15): **delete** the 7 ipykernel/papermill tests (`parse_known_args`, `_finish`, flat-exp-dir) and adapt the resolver tests to canonical-mount-first; `test_run_cv` (6) → move to `template-test` |
| `set_metric.py` (84) | ADAPT | `kx metric <name> [--greater-is-better/--no-greater-is-better]`. **Drop** `METRIC_NOT_CAPTURED = LIMIT_NEEDS_USER` (exit 78) | `test_set_metric` (9) adapt |
| `submission_gate.py` (355) | ADAPT → DORMANT | `kx/submission_gate.py`: **remove** `NOISE_K_DEFAULT`, `is_meaningful`, the `k` param (fold-noise margin, CORE-07), `ASSUMED_PROVENANCE` and rule 4 ("assumed 5/day"). Keep the pure budget/CV-readability rules for Phase 9 | `test_gate_policy` (14): delete the noise/assumed tests, keep the rest |
| `capture_competition.py` (414) | **DELETE** (CORE-07: prose regex, `_LIMIT_RE`, `_CODE_MARKERS`, `DEFAULT_ASSUMED_LIMIT=5`, exit 78) | replaced by `kx sync` → `profile.json` | `test_capture` (5), `test_limit_regex` (7), `fixtures/pages_all.json` → delete |
| `competition_doc.py` (61) | DELETE | `competition.md` section-merge; `profile.json` replaces the static competition file | (covered via `test_capture`) → delete |
| `convert_notebook.py` (170) | **DELETE** (CORE-07 jupytext) | script kernels | `test_convert_notebook` (4) → delete |
| `analyze_data.py` (500) | DELETE (superseded by TMPL-01: 4-option CV enum + local AV; no local data in Phase 6) | — | (no dedicated tests) |
| `cv_evidence.py` (479) | DELETE (same) | — | `test_cv_evidence` (19) + `cv_fixtures.py` → delete |
| `download_data.py` (238) | DELETE (Phase 7 PROF-05 rebuilds it on the SDK; keep `safe_extract`) | — | `test_gate` (7), `test_competition_live` (7, v1 CLI shapes) → delete |
| `run_local.py` (162) | DELETE (Phase 8 RUN-06 rebuilds `kx run --local`) | — | `test_run_local` (6) → delete |
| `check_submission.py` (845) | DELETE (Planner's discretion — recommended; it depends on the deleted `competition.type`/type-signals/exit-code protocol) | Phase 9 rebuilds `kx submit` on the kept `submission_gate` + `submissions_log` | `test_check_submission` (27) → delete |
| `submit.py` (750) | DELETE (v2 rule: **kx never runs `competitions submit`**) | — | `test_submit` (49), `test_submission_live` (3) → delete |
| `fetch_lb.py` (620) | DELETE (Phase 9 rebuilds the read-back on `submissions_log`) | — | `test_fetch_lb` (4) → delete; `test_no_credential_leak` (6) → rewrite for kx |

`tests/test_kernel_live.py` (1, always skipped) is replaced by a real `kx` live test. `tests/test_settings.py` (3) and `tests/test_egress_allowlist.py` (3) are **deleted** (CORE-07 default egress allowlist).

### Templates

| Template | Fate |
|---|---|
| `strategy.md` / `VERDICT.md` / `meta.json` | keep (`meta.json.tmpl` becomes code, since the recorder builds meta in code) |
| `pre-commit.tmpl` | keep |
| `competition.md` / `env` / `settings.json` / `pyproject.toml` (lists **jupytext**) | delete |
| `config.json` | drop `cv`, `submission.noise_k`, `limit_provenance`, `competition.type`, `execution_target`, `kernel.enable_internet`; add `workspace_version: 2`, `competition`, `metric` |
| `state.json` | keep `next_exp_id`; store `credentials` as `{status, username, source, validated_at}` |
| `gitignore` | adapt: drop `!experiments/*/*.ipynb`; add `experiments/*/output/*.csv`, `*.log` |
| `kernel-metadata.json` | replace with a code builder (script type) |
| `experiment.py` | replace with `templates/tabular/train.py.tmpl` |
| `README.md` | adapt |

**Superseded-path checklist (CORE-07, for grep-based tests):**
- **Prose regex:** `_LIMIT_RE`, `_CODE_MARKERS`, `extract_daily_limit`, `classify_competition_type`, `strip_html`
- **exit-78 / assumed limit:** `LIMIT_NEEDS_USER`, `78`, `DEFAULT_ASSUMED_LIMIT`, `assumed_default`, `ASSUMED_PROVENANCE`, `limit_provenance`
- **jupytext:** `jupytext`, `convert_notebook`, `.ipynb`, `kernelspec`, `ipykernel` workarounds (`_finish`, `parse_known_args` comment)
- **Consent:** `--yes`, `handle_chmod`, `handle_env_population`, `.env` template
- **Egress:** `settings.json.tmpl`, `allowedDomains` written by init, `socat` warning
- **Noise:** `noise_k`, `NOISE_K_DEFAULT`, `is_meaningful`

Note: `kaggle` 2.2.3 itself **depends on jupytext** (uv.lock). The CORE-07 test must assert that *kx code* never imports or invokes jupytext, not that jupytext is absent from the lock [VERIFIED: uv.lock].

## Packaging & the `kx` Entry Point (Research Q2 / CORE-06)

**Verified in this session** (probe project in `/tmp/kxprobe`, uv 0.11.14):
- `uv sync --project /tmp/kxprobe/skill`, run from an **empty** `/tmp/kxprobe/ws`, created `skill/.venv` and `skill/uv.lock`, built the project and installed it **editable** (a `kaggle_exp.pth` pointing at `skill/src`).
- The workspace stayed empty.
- `uv run --project /tmp/kxprobe/skill kx init --flag` printed `{"status":"ok","cwd":"/tmp/kxprobe/ws",…}`: **cwd is the workspace**. uv's own messages go to stderr.
- `skill/.venv/bin/kx` also works directly. The generated entry script does `sys.exit(main())`, so the return value of `main()` becomes the process exit code.

[VERIFIED: local probe]

**Recommended `pyproject.toml` (skill root = repo root, next to SKILL.md):**
```toml
[project]
name = "kaggle-exp"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = ["kaggle==2.2.3"]          # CLI + kagglesdk; exact pin = the spike-verified surface

[project.scripts]
kx = "kx.cli:main"

[build-system]
requires = ["uv_build>=0.11,<0.12"]        # verified with local uv 0.11.14
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "kx"                          # src/kx/

[dependency-groups]
dev = ["pytest>=8.0"]
# template-test = ["pandas>=2.2", "numpy>=1.26", "scikit-learn>=1.5", "lightgbm>=4.5"]   # optional, non-default

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not live'"
markers = ["live: real Kaggle calls (excluded by default)"]
```
Remove `[tool.uv] package = false`. The workspace gets **no** `pyproject.toml` in Phase 6: nothing runs locally, and the v1 workspace pyproject existed only for local ML plus jupytext.

**How the AI invokes kx:** `uv run --project ${CLAUDE_SKILL_DIR} kx <subcommand> …`. `${CLAUDE_SKILL_DIR}` is substituted into SKILL.md by Claude Code, so the model sees a literal path; the spike conventions say the sandbox refuses shell variables. The equivalent `${CLAUDE_SKILL_DIR}/.venv/bin/kx` avoids uv's per-call sync check.

**SKILL.md `allowed-tools`:** `Bash(uv sync *) Bash(uv run *) Bash(git *) Read Write Edit`. **Drop `Bash(kaggle *)`**: kx calls the SDK in-process, and not pre-approving raw `kaggle` makes an accidental `kaggle competitions submit` impossible without a prompt. (Planner's discretion — recommended.)

**Resolving the `kaggle` binary if any CLI call remains:** use `[sys.executable, "-m", "kaggle", …]`. `kaggle/__main__.py` exists [VERIFIED: installed source]. This guarantees the venv's 2.2.3, whereas v1 used `shutil.which("kaggle")`, which depends on PATH.

## Architecture Patterns

### System Architecture Diagram

```
 AI (SKILL.md) ──invokes──▶ uv run --project <skill> kx <cmd> [args]   (cwd = workspace)
                                   │
                                   ▼
                     ┌──────── kx.cli.main ────────┐
                     │ fd-1 → /dev/null guard       │   any stray print / child stdout discarded
                     │ JSON argparse (errors→JSON)  │
                     └─────────────┬───────────────┘
                                   ▼ dispatch(cmd) → Envelope
      ┌──────────────┬─────────────┼──────────────┬──────────────────┬──────────────┐
      ▼              ▼             ▼              ▼                  ▼              ▼
   init           sync          metric          new                run           strategy / status
 workspace.py   profile.py     metrics.py    experiment.py     experiment.validate   strategy.py
 credentials    (whitelist)    set_config    template render    │ refuse invalid ──▶ Envelope(invalid) [no push]
      │              │                            │              ▼
      ▼              ▼                            ▼        kernel.build_metadata (script, private, internet=false)
  KaggleAdapter ◀────┴──────────── (injectable; FakeAdapter in tests) ───────────┐
  (lazy guarded import, quiet(), deadline())                                      │
      │  authenticate / get_competition / files_summary / list_data_tree_files   │
      │  kernels_push → ApiSaveKernelResponse{version_number,error,invalid_*}     │
      │  get_kernel_session_status → KernelWorkerStatus.<NAME>                    │
      │  list_kernel_session_output → files[{file_name,url}] + log                │
      │  get_kernel → metadata{current_version_number, docker_image, ...}         │
      ▼                                                                           │
  Kaggle API (api.kaggle.com)  ──runs──▶  Script kernel (/kaggle/src/script.py)   │
                                           reads /kaggle/input/competitions/<Ref>/│
                                           writes /kaggle/working/{result.json,   │
                                           oof.csv, test_preds.csv, submission.csv,
                                           kx_manifest.json}                      │
                                                                                  ▼
   run: push → kernel_run.json(PENDING) → poll_loop(bounded) ──terminal──▶ pull → output/
        └─ budget expiry ─▶ Envelope(status=running, next_action="kx run exp-NNN" = resume, no re-push)
   record (fail-closed): status rung → log-scan rung → result.json ladder → preds rung
        → meta.json (canonical) → rebuild ledger.jsonl → VERDICT.md stub
        → Envelope(next_action: write VERDICT.md + reasoning → kx strategy --reasoning-file …)
   strategy: ledger (FACTS) + reasoning file → strategy.md (atomic) → optional cycle commit
```

### Recommended Project Structure
```
SKILL.md                     # rewritten around kx (lean; the ≤150-line budget is Phase 7)
pyproject.toml  uv.lock      # packaged project, kaggle==2.2.3
references/
  kx-reference.md            # envelope, subcommands, experiment.json, kx-preds/1 (loaded on demand)
  egress-allowlist.md        # opt-in snippet + "enforcement UNVERIFIED (01-03 example.com anomaly)"
  kaggle-cli-behavior.md     # historic v1 facts + new SDK facts (append)
src/kx/
  __init__.py  __main__.py   # __version__; `python -m kx`
  cli.py                     # argparse (JSON errors), dispatch, fd guard, print envelope, exit code
  envelope.py                # make(status, next_action, data, warnings, errors)
  workspace.py               # layout, safe-merge helpers, git init + leak hook + commits
  credentials.py             # detect_source, mask, token type (no consent flows)
  kaggle_adapter.py          # KaggleAdapter (real) + deadline() + quiet() + to_plain() + safe_join()
  profile.py                 # build_profile(facts) → profile.json (allow-listed fields)
  metrics.py                 # REGISTRY (ported)
  experiment.py              # experiment.json schema + validate_experiment()
  preds.py                   # kx-preds/1 constants + stdlib CSV validator
  kernel.py                  # build_metadata, push/poll/pull orchestration, poll_loop (ported)
  record.py                  # fail-closed recorder (ported + preds rung)
  ledger.py                  # to_ledger_row / validate_meta / rebuild_ledger_file (ported)
  strategy.py  lb_gap.py  submissions_log.py  submission_gate.py(dormant)
  leak_scan.py  safe_extract.py  untrusted.py
  templates/ tabular/train.py.tmpl  strategy.md.tmpl  VERDICT.md.tmpl  gitignore.tmpl
             pre-commit.tmpl  config.json.tmpl  state.json.tmpl  README.md.tmpl
tests/                       # new kx tests (+ ported v1 tests); v1 tests deleted in the cleanup plan
```
**Workspace layout produced by kx** (Planner's discretion — recommended; keeps v1's `control/` paths for CORE-04):
```
<ws>/.gitignore  .githooks/pre-commit  README.md  strategy.md
<ws>/control/config.json  state.json  profile.json  ledger.jsonl  raw/last-error.txt(ignored)
<ws>/experiments/exp-001/experiment.json  train.py  kernel-metadata.json  kernel_run.json
                          meta.json  VERDICT.md  reasoning.md
                          output/{result.json, kx_manifest.json, oof.csv*, test_preds.csv*,
                                  submission.csv*, <kernel-slug>.log*}      (* gitignored)
```

### Pattern 1: One JSON envelope, guarded at the file-descriptor level (CORE-01)
**What:** `main()` points fd 1 at `/dev/null` for the whole command, then writes the envelope on the saved fd. Python-level `redirect_stdout` alone is **not enough**. It does not catch child processes (git, `python -m kaggle`) or C extensions, and `kaggle` prints auth help, title-slug warnings and push-error lines on stdout [VERIFIED: installed source].

**Envelope (Planner's discretion — recommended):**
```json
{"kx": "0.2.0", "command": "run", "status": "ok",
 "summary": "exp-001 recorded SUCCESS: accuracy 0.8305 ± 0.0148 (5 folds)",
 "data": {"exp_id": "exp-001", "result": "SUCCESS", "cv_mean": 0.8305, "kernel": "user/kx-titanic-exp-001", "kernel_version": 1},
 "warnings": [], "errors": [],
 "next_action": {"kind": "edit",
                 "instruction": "Write the verdict in experiments/exp-001/VERDICT.md and a reasoning fragment in experiments/exp-001/reasoning.md",
                 "then": "kx strategy --reasoning-file experiments/exp-001/reasoning.md"}}
```
- **`status` values** ∈ {`ok`, `running`, `needs_user`, `invalid`, `error`}:
  - `ok`: the command did its job. This includes "recorded FAILED"; the outcome is in `data.result`.
  - `running`: a kernel is in flight. Re-run to resume; never re-push.
  - `needs_user`: a browser or credential step.
  - `invalid`: input was refused and nothing was mutated or pushed.
  - `error`: transient or unexpected; safe to retry.
- **`next_action.kind`** ∈ {`run`, `edit`, `ask_user`, `done`}.
- **Exit code:** 0 iff `status ∈ {ok, running}`, else 1. The AI still reads `status`.
- **Help and usage errors:** argparse must not print usage. Subclass `ArgumentParser.error()` to raise, and catch the help `SystemExit(0)`. Both are returned as envelopes (`status=invalid` / `ok` with `data.usage`).
- **Uncaught exceptions:** return `status=error` with the exception *type* only. The traceback goes to the gitignored `control/raw/last-error.txt`, never to stdout.

### Pattern 2: Injectable adapter, so tests never hit Kaggle
Every subcommand is `cmd_x(ws: Path, args, adapter) -> dict`. `cli.main` builds the real `KaggleAdapter` lazily, only for commands that need it. Tests pass a `FakeAdapter`, following the v1 lesson in `kaggle-cli-behavior.md` §WR-01: "pass the gateway in — never resolve it from a module global".

### Pattern 3: Lazy, guarded, deadline-bounded SDK access
**What:** never import `kaggle` at module top. The import runs `KaggleApi().authenticate()`. With no credential it prints 667 bytes of auth help to stdout and `exit(1)`s, and it does a live token-introspect call when a token exists. Wrap the import and `authenticate()` in `quiet()` and `deadline()`, and catch `SystemExit`. [VERIFIED: probe in this session: `from kaggle.api.kaggle_api_extended import KaggleApi` in an empty HOME → rc 1, stdout "Authentication required to call the Kaggle API."]

The SDK's `requests.Session.send` carries **no timeout** [VERIFIED: `kagglesdk/kaggle_http_client.py`]. A `SIGALRM` deadline interrupts a blocking socket read (PEP 475) [VERIFIED: probe `alarm_probe.py`: blocked `recv` interrupted at 0.51 s with the deadline set to 0.5 s]. It is POSIX-only and main-thread-only; kx is a single-threaded CLI on Linux or macOS.

### Pattern 4: Bounded foreground poll sized to the agent's tool timeout
The Claude Code Bash tool's default timeout is **120 s**, and the maximum is 600 s [VERIFIED: tool description in this session]. A `kx run` that polls longer than the caller's tool timeout gets killed mid-poll.
- **Recommended:** `kx run --wait <s>`, default ~90 s. On expiry it returns `status=running` with `next_action` `kx run exp-NNN`, which resumes polling from `kernel_run.json` without re-pushing.
- SKILL.md tells the AI to pass Bash `timeout: 600000` and `--wait 540` for longer kernels.
- Write `kernel_run.json` **atomically, right after the push**, before polling.

This is v1's detach-not-cancel design. Cross-session resume (RUN-02) is the same mechanism, proven live in Phase 8.

### Pattern 5: "AI decides, tooling writes", with an explicit `next_action` chain
The happy path, read from the envelopes (Planner's discretion — recommended):

| Step | Command | `next_action` it returns |
|---|---|---|
| 1 | `kx init` | `kx sync <competition>` (or `ask_user` for the credential) |
| 2 | `kx sync titanic` | `kx metric <suggested>`. Suggestion from an exact-match map of structured `evaluation_metric` names, e.g. 'Categorization Accuracy'→`accuracy`, 'Roc Auc Score'→`roc_auc`. The AI confirms. |
| 3 | `kx metric accuracy` | `kx new --idea … --hypothesis …` |
| 4 | `kx new` | `edit`: `experiments/exp-001/train.py` AI block + `experiment.json` `cv.reasoning`; then `kx run exp-001`. `data.tried` lists the never-repeat digest lines. |
| 5 | `kx run exp-001` | `edit`: `VERDICT.md` + `reasoning.md`; then `kx strategy --reasoning-file …` |
| 6 | `kx strategy …` | `kx new` (the next idea), or `done` |

`kx strategy` refuses (`invalid`) while the latest recorded experiment's `VERDICT.md` still holds the template placeholders. That puts the verdict in place before the strategy regenerates.

`kx status` (local-only) recomputes `next_action` from the workspace state. It is the resume anchor that SKILL.md points to ("when unsure, run `kx status`").

### Anti-Patterns to Avoid
- **Top-level `import kaggle` or `from kaggle.api… import` in any kx module:** it breaks every credential-less command and the JSON contract.
- **Relying on `kernel-metadata.json` defaults:** `enable_internet` defaults to **True** in 2.2.3 code [VERIFIED: `kernels_push`: `self.get_bool(meta_data, "enable_internet", True)`]. Write every flag explicitly and read it back from `get_kernel` metadata after the push.
- **Trusting the CLI push exit code:** `kernels_push_cli` prints `Kernel push error: …` or `The following are not valid competition sources…` and exits 0 [VERIFIED: installed source]. v1's `push_kernel.py` has this latent bug.
- **Pulling output with `api.kernels_output(...)`:** 2.2.3 does `os.path.join(target_dir, item.file_name)` with no traversal check. Upstream "Next" adds "Refuse to write a `kaggle kernels output` file whose server-supplied name resolves outside the requested `--path`" [VERIFIED: installed source + CHANGELOG]. Iterate `list_kernel_session_output` yourself and use `safe_join`.
- **Flat pulls into the experiment dir:** a kernel file named `train.py` or `experiment.json` would overwrite the local source. Pull into `output/`.
- **Echoing exception text:** `HTTPError` messages carry URLs, and download errors can carry **signed GCS URLs**. Map exceptions to `{error: "http_403", op: "get_competition"}`.
- **A meta.json "pending" stub** (v1): `validate_meta` rejects `status=pending`, so the rebuild warns about every unrun experiment. Carry the fields forward from `experiment.json` instead.

## Kaggle API Surface (Research Q3), exact calls

The quotes marked [CITED] come from `.claude/skills/spike-findings-kaggle-skill/references/*.md`. Those marked [VERIFIED] were read from the installed `kaggle` 2.2.3 / `kagglesdk` 0.1.33 source in `.venv`.

**A. Credential validation (`kx init`)**
- Load with Pattern 3: `api = KaggleApi(); api.authenticate()`. The order is access token (env `KAGGLE_API_TOKEN` / `~/.kaggle/access_token`, validated live by `introspect_token`), then legacy key (`KAGGLE_USERNAME`/`KAGGLE_KEY` env or `kaggle.json`; **no network call**), then OAuth creds. On failure: `print_auth_help(); exit(1)` [VERIFIED].
- Username: `api.get_config_value("username")`, set from introspect for tokens and from config for legacy keys [VERIFIED].
- A legacy key is **not** validated by `authenticate()`, so kx must make one authenticated live call. Recommended: `api.competitions_list(search=<slug or "titanic">, page_size=1)`, the in-process equivalent of v1's live-verified `kaggle competitions list` check. Any exception means `needs_user`.
- Print only: source label, token type (`kagat_`/`KGAT_`/32-hex via `_detect_token_type`), masked value (`_mask`: first N + `*` + last 4), username.
- `~/.kaggle/kaggle.json` group/world-readable → **warning** with the exact `chmod 600` command. Never auto-fix it and never prompt (CORE-07 consent removal).
- Local facts: `~/.kaggle/access_token` and `kaggle.json` both exist with mode 600; no `KAGGLE*` env is set [VERIFIED: `ls -la ~/.kaggle`, names and permissions only].

**B. Competition profile facts (`kx sync`, PROF-01)**, quoted from spike 001:
> ```python
> api = KaggleApi(); api.authenticate()
> with api.build_kaggle_client() as client:
>     cc = client.competitions.competition_api_client
>     r = ApiGetCompetitionRequest(); r.competition_name = slug
>     comp = cc.get_competition(r)                               # flags, metric, tags, limits
>     r = ApiGetCompetitionDataFilesSummaryRequest(); r.competition_name = slug
>     summary = cc.get_competition_data_files_summary(r)         # sizes by extension
>     r = ApiListDataTreeFilesRequest(); r.competition_name = slug; r.page_size = 200
>     root = cc.list_data_tree_files(r)                          # root files[] + directories[]
> ```
> "SDK objects are `KaggleObject`s. Convert them to plain JSON by walking `_fields`, as `plain()` does"

[CITED: competition-profile.md]

- **Canonical ref:** `comp.ref` is a **URL**, e.g. `https://www.kaggle.com/competitions/equity-post-HCT-survival-predictions`. Canonical ref = `ref.rstrip('/').rsplit('/', 1)[-1]` [VERIFIED: spike raw JSON for all 20 comps].
- **`get_competition` keys available:**
  - `awards_points`, `category`, `date_created`, `deadline`, `description`, `enabled_date`, `evaluation_metric`, `host_name`, `id`
  - `is_kernels_submissions_only`, `kernel_count`, `max_daily_submissions`, `max_team_size`, `merger_deadline`, `new_entrant_deadline`
  - `organization_name`, `organization_ref`, `ref`, `reward`, `submissions_disabled`, `tags`, `team_count`, `thumbnail_image_url`, `title`, `url`
  - `user_has_entered`, `user_rank`

  [VERIFIED: `raw/titanic.json`]
- **Allow-list** for `profile.json` (PROF-01): `canonical_ref`, `title`, `category`, `evaluation_metric`, `max_daily_submissions`, `is_kernels_submissions_only`, `submissions_disabled`, `deadline`, `max_team_size`, `host_name`, `tags[].name`, `user_has_entered`.
- **Excluded prose:** `description`, per-file `description`, `thumbnail_image_url`, `url`.
- **Files summary:** `file_summary_info.total_file_count`, `file_types[{extension, file_count, total_size}]` [CITED].
- **Root listing:** `files[{name, total_bytes}]`, `directories[{name}]`. Page on `next_page_token` if needed.
- Titanic facts: metric `'Categorization Accuracy'`, daily 10, code-only False, 3 csv files / 93,081 bytes, sample file **`gender_submission.csv`** (not `sample_submission.csv`) [VERIFIED: spike raw].
- All three calls work before joining. The depth-1 listing returns 403 until the user joins (Phase 7) [CITED].

**C. Push (RUN-01)**: use `api.kernels_push(folder, timeout=<limit_s>)`, which returns `ApiSaveKernelResponse` [VERIFIED].
- Response fields: `ref`, `url`, `version_number` (alias `versionNumber`), `error`, `invalid_tags`, `invalid_dataset_sources`, `invalid_competition_sources`, `invalid_kernel_sources`, `invalid_model_sources`, `kernel_id`.
- `timeout` maps to `session_timeout_seconds`. Spike: "`push -t 60` on a 300-second script ends in **`CANCEL_ACKNOWLEDGED`** at about 70 seconds" [CITED: script-kernels.md].
- `kernels_push` validates the metadata before any network call: title ≥5 chars; `language ∈ {python,…}`; `kernel_type ∈ {script, notebook}`; the `id` slug has no version; a title-slug mismatch **prints** a warning to stdout. It also raises `ValueError` on a missing folder, metadata or code file [VERIFIED].
- Kernel titles must be **≤50 chars** (longer gives an opaque server 500) [CITED: github.com/Kaggle/kaggle-cli/pull/179, MEDIUM]. Cap the title to 50 characters.
- Fail closed when `resp.error` is set or any `invalid_*_sources` list is non-empty.
- **Version:** use `resp.version_number`. If it is `None` ("Kernel version successfully pushed" with no number: "Shouldn't happen but didn't test exhaustively" [VERIFIED: source comment]), **read it back** via `get_kernel` (item E). Never guess.
- Spike quote: "The CLI can also print the line with no number. In that case, don't guess the version; read it back." [CITED]

**D. Poll**: `api.kernels_status("<owner>/<slug>")` returns `ApiGetKernelSessionStatusResponse{status: KernelWorkerStatus, failure_message}`.
- Enum values: `QUEUED, RUNNING, COMPLETE, ERROR, CANCEL_REQUESTED, CANCEL_ACKNOWLEDGED, NEW_SCRIPT`. Use `resp.status.name` [VERIFIED].
- 2.2.3 status and output always act on the **latest** version; the version suffix is honored only in the unreleased "Next" [VERIFIED: CHANGELOG].
- Terminal sets differ between sources: spike `kwait.py` counts `CANCEL_REQUESTED` as terminal, and v1 `poll_kernel` counts it as in-flight. **Recommended:** keep v1 (`TERMINAL = {COMPLETE, ERROR, CANCEL_ACKNOWLEDGED}`), bounded by the budget.
- Reuse v1's `poll_loop(status_fn, now, sleep, rng, budget_s, max_consecutive_errors)`: exponential 10 s→120 s cap, full jitter, 5 transient errors → fail closed, budget → DETACHED, never cancel [VERIFIED: `poll_kernel.py`].

**E. Pull + provenance**: `client.kernels.kernels_api_client.list_kernel_session_output(ApiListKernelSessionOutputRequest{user_name, kernel_slug, page_size, page_token})` returns `files[{file_name, url}]`, `log`, `next_page_token` [VERIFIED].
- Download each `url` with `requests.get(url, stream=True, timeout=(15,120))` after `safe_join(output_dir, file_name)`.
- Write `resp.log` (a JSON array of `{stream_name, time, data}` [CITED]) to `output/<kernel-slug>.log`.
- Provenance: `client.kernels.kernels_api_client.get_kernel(ApiGetKernelRequest{user_name, kernel_slug})` returns `.metadata` with `current_version_number`, `docker_image`, `machine_shape`, `enable_internet`, `is_private`, `competition_data_sources`. This is the same call `kaggle kernels pull -m` makes [VERIFIED: `kernels_pull` source].
- Before recording, verify `current_version_number == kernel_run.kernel_version`. If a newer version exists, the outputs belong to another run: fail closed.

**F. Accelerator IDs** (live-verified only):
- `cpu` → `enable_gpu: false` (spikes 002/003).
- `NvidiaTeslaT4` → `enable_gpu: true` with **no** `machine_shape`. v1's live GPU run landed on `machine_shape NvidiaTeslaT4` [CITED: kaggle-cli-behavior.md A1].
- **Reject** `NvidiaTeslaP100`: CLI "Next" warns that P100 is **retired** [VERIFIED: CHANGELOG].
- The current docs call `machine_shape: NvidiaTeslaT4` "GPU T4 ×2". The single vs ×2 semantics are unverified (RUN-F3).

## `experiment.json` Schema & Validation (Research Q4 / CORE-03)

**Decision (Planner's discretion — recommended): a stdlib validator** `validate_experiment(spec, *, profile, exp_dir) -> list[str]`, mirroring v1's `validate_meta` style.
- There is no new dependency ("kaggle package only").
- The errors map directly to envelope `errors[]`.
- Reject unknown keys (catches AI typos such as `"acclerator"`), and reject the literal placeholder `"<TODO>"` anywhere.

```json
{
  "schema_version": 1,
  "exp_id": "exp-001",
  "created": "2026-09-25T10:00:00Z",
  "idea": "LightGBM baseline on Sex/Pclass/Age/Fare/Embarked",
  "hypothesis": "A GBDT on the core demographic features reaches ≥0.80 CV accuracy",
  "template": "tabular",
  "runtime": {"target": "kernel", "accelerator": "cpu", "limit_s": 1800, "internet": false},
  "sources": {"competition": "titanic", "datasets": [], "kernels": [], "models": []},
  "cv": {"n_folds": 5, "reasoning": "Passengers are iid rows; Survived is 38% positive → stratify on it, 5 folds…"},
  "code_file": "train.py"
}
```

| Field | Rule (Phase 6) |
|---|---|
| `exp_id` | `^exp-\d{3}$` and equal to the folder name |
| `idea`, `hypothesis` | non-empty strings, not a placeholder |
| `template` | ∈ {`tabular`} (Phase 7 adds more) |
| `runtime.target` | ∈ {`kernel`}. `local` → `invalid` with "local runs arrive in Phase 8 (RUN-06)" |
| `runtime.accelerator` | ∈ {`cpu`, `NvidiaTeslaT4`} (live-verified only) |
| `runtime.limit_s` | int, 60 ≤ x ≤ 43200 (12 h platform maximum [CITED]) |
| `runtime.internet` | bool. `true` is allowed but becomes a **warning** and an auditable field in `meta.kernel` (v1 D-06) |
| `sources.competition` | equal to `profile.json` `slug`. The canonical case is used for the mount path |
| `sources.datasets` / `models` | format regex (`owner/slug`; `owner/model/framework/variation/version`). Pass through with a warning that the mounts are unverified (Phase 8 frontier) |
| `sources.kernels` | **must be empty** in Phase 6 (pipelines need the upstream-COMPLETE wait, RUN-05/Phase 8) |
| `cv.n_folds` | int ≥ 2 |
| `cv.reasoning` | non-empty, not a placeholder (TMPL-01 "reasoning recorded"). Carried into `meta.json` as `cv_reasoning` (not into the 11-key ledger row) |
| `code_file` | `train.py`, and it must exist and `ast.parse` cleanly (catches syntax errors before burning a push) |

`kx new` writes the draft with `"<TODO>"` in `cv.reasoning` and the defaults elsewhere. `kx run` validates it **before** any adapter call. The contract test asserts that the `FakeAdapter`'s `push` was never called on an invalid spec.

## Standard Prediction Format `kx-preds/1` (ENS-01)

**Decision (Planner's discretion — recommended): CSV, readable with stdlib `csv`.** The kernel writes it with pandas; the recorder validates it locally with no new dependency. ENS-02 (Phase 10) blends it with no row misalignment, because ids plus target travel with the predictions.

| File (in `/kaggle/working`, pulled to `output/`) | Columns | Rows |
|---|---|---|
| `oof.csv` | `row_id, fold, target, pred` (binary: P(positive); regression: raw value) or `row_id, fold, target, pred_0 … pred_{K-1}` (multiclass, class order in `result.json.predictions.classes`) | one per train row; `fold` ∈ [0, n_folds) or `-1` = never validated (walk-forward, Phase 7) |
| `test_preds.csv` | `row_id, <same pred columns as oof.csv>` | one per test row |

- `row_id` is the competition id column, e.g. `PassengerId`, or the 0-based row index when there is none.
- Store **continuous** scores (probabilities), not hard labels, so blends work. The harness applies the metric's decision rule (threshold / argmax) only when scoring label metrics and when writing `submission.csv`. Keep v1's hard-won `_default_agg` note: never average hard labels.

`result.json` (kernel-written) gains a `predictions` block:
```json
"predictions": {"format": "kx-preds/1", "oof": "oof.csv", "test": "test_preds.csv",
                "pred_columns": ["pred"], "classes": null, "n_oof": 891, "n_test": 418,
                "id_column": "PassengerId", "target_column": "Survived", "prediction_type": "proba"}
```

**Recorder rung `predictions_invalid`** (new `FAILURE_REASONS` member, added after the v1 ladder passes). Fail closed if any of these holds:
- a declared path is not a plain filename inside `output/`, or the file is missing
- the headers are wrong
- the row counts are not equal to `n_oof`/`n_test`, or are 0
- the `row_id` values are not unique
- a `fold` is not an int in {-1}∪[0,n_folds)
- the set of used folds is not equal to `range(n_folds)`, or `len(fold_scores) != n_folds`
- a pred value is not a finite float, among rows with fold ≥ 0 and among all test rows
- the pred columns differ between the two files

Streaming validation of ~1M rows is a few seconds in pure Python [ASSUMED]. Recomputing fold scores from OOF is a stronger anti-lie check, but it needs a local metric implementation. **Recommended: defer** to Phase 10 (RES-04 exact metric).

## Script Kernel Packaging & the Tabular Template (Research Q5 / TMPL-01 / RUN-01)

**kernel-metadata.json** (built in code and written into `experiments/exp-NNN/`, overwritten on each push):
```json
{"id": "<username>/kx-titanic-exp-001", "title": "kx-titanic-exp-001", "code_file": "train.py",
 "language": "python", "kernel_type": "script", "is_private": true,
 "enable_gpu": false, "enable_tpu": false, "enable_internet": false,
 "competition_sources": ["titanic"], "dataset_sources": [], "kernel_sources": [], "model_sources": []}
```
- `competition_sources`: use the **lowercase slug**, which spike 003 verified live: `equity-post-hct-…` mounted at the canonical-case `/kaggle/input/competitions/equity-post-HCT-survival-predictions/` [CITED: spike 003 README]. The canonical case is unverified in this field.
- Kernel slug (Planner's discretion — recommended): `kx-<slug-lower>-<exp_id>`, truncated to ≤50 chars. Consider a short workspace id, e.g. `kx-titanic-a1b2-exp-001`, so two workspaces on the same competition never version each other's kernels.
- Username: from `api.get_config_value("username")`, validated `^[A-Za-z0-9][A-Za-z0-9_-]*$` (v1 `_USERNAME_RE`).

**Kernel runtime facts** (spike 002, live):
> "`argv=['/kaggle/src/script.py']`, and `__file__` is set. cwd is `/kaggle/working`. Python 3.12.13 (local is 3.13, a parity note). `ipykernel` is NOT loaded, so `SystemExit` is fine. `KAGGLE_KERNEL_RUN_TYPE=Batch`."

[CITED: script-kernels.md]

**Data resolver** (quoted from spike 003; use it directly; the unified resolver is RUN-03/Phase 8):
> ```python
> CANDIDATES = [Path(f"/kaggle/input/competitions/{SLUG}"),   # current mount (canonical case)
>               Path(f"/kaggle/input/{SLUG}")]                  # legacy mount seen in older notebooks
> base = next((p for p in CANDIDATES if p.is_dir()), None)
> if base is None:  # case-insensitive fallback: canonical refs carry capitals (equity-post-HCT-...)
>     base = next((p.parent for p in Path("/kaggle/input").rglob("sample_submission.csv")
>                  if p.parent.name.lower() == SLUG.lower()), None)
> ```

[CITED: script-kernels.md]

For Titanic, render the sample file name from the profile (`gender_submission.csv`) instead of hard-coding `sample_submission.csv` in the fallback.

**Template shape** (`templates/tabular/train.py.tmpl`, rendered by `kx new` with `repr()` literals, per v1 CR-01):
- **Header literals:**
  - `EXP_ID`, `COMPETITION_REF` (canonical), `SAMPLE_SUBMISSION` (from the profile root listing: first file containing "submission")
  - `METRIC`, `REGISTRY_ENTRY` (a snapshot of `kx/metrics.py`), `N_FOLDS`, `SEED=42`
  - `TARGET=None` / `ID_COL=None`. `None` means read the column names from the sample file at runtime: `sample.columns[0]` = id, `sample.columns[1]` = target, as spike 003a did.
- **`# === AI BLOCK ===`**:
  - `assign_folds(train, y) -> np.ndarray[int]`: the **AI-written CV scheme** (TMPL-01). It replaces the enum.
  - `build_features(train, test) -> (X, X_test)`
  - `make_model(seed)`
  - an optional `preprocess_factory()` (unfitted, per fold; keep v1's anti-leakage contract)
- **`# === KX HARNESS (do not edit) ===`**:
  - the resolver
  - the fold loop: fit on `fold != k`, predict val and test
  - metric via `sklearn.metrics.<REGISTRY_ENTRY["sklearn_callable"]>`
  - writes `result.json` (the v1 schema plus the `predictions` block), `oof.csv`, `test_preds.csv`, `submission.csv` (sample columns; label rule applied) and `kx_manifest.json` (exp_id, created UTC, python + pandas/numpy/sklearn/lightgbm versions, `KAGGLE*` **env keys only**)
  - it **does not catch exceptions**: a throw must surface as status `ERROR`
- **Parity:** use APIs that work on both pandas 2.2 and 3.0 and on Python 3.12 (no `copy_on_write`-dependent tricks, no 3.13 syntax). Print the library versions into the log/manifest so the live run records the Kaggle image pins.
- Optional hardening (Planner's discretion): hash the harness section at `kx new`, store it in `experiment.json`, and have `kx run` refuse a modified harness. This stops the AI from "fixing" the scorer.

**Failure-mode facts for criterion 5** (spike 002, live):
> "A raised exception ends in **`ERROR`**, with a clean `Traceback` in stderr." "Both keep partial outputs written before the stop."

[CITED: script-kernels.md]

The recorder therefore gets three signals:
- status `ERROR` → rung 1 → `FAILED(kernel_error)`
- a traceback in the log → rung 2
- a missing or invalid `result.json` → `missing_result` / `schema_invalid` / `non_finite` / `out_of_range`

The benign mistune/nbconvert `SyntaxWarning`s hit no marker [CITED: kaggle-cli-behavior.md A3; fixture `tests/fixtures/kernel_logs/benign_warnings.json`].

## Carry-over of record / verdict / ledger / strategy (Research Q6 / CORE-04)

| v1 behavior | Phase 6 | Interface change |
|---|---|---|
| Recorder ladder: status rung (ERROR/CANCEL_ACKNOWLEDGED) → log scan (6 markers) → WR-03 unreadable log fails closed → `result.json` keys/types/finite/anti-lie mean (`<1e-6`)/metric match/range | **Unchanged logic** | Inputs come from `output/` and `kernel_run.json`. The `run_exit_code` path is local-only and not used in Phase 6. A `predictions_invalid` rung is added. |
| `meta.json` canonical; FAILED keeps idea/hypothesis, `cv_mean=null` | Unchanged | Carry-forward source = `experiment.json` (plus `cv_reasoning`, `template`, `runtime`). `meta.kernel` gains `kernel_version` (read back), `docker_image`, `machine_shape`, `enable_internet` (read back). |
| `ledger.jsonl` = pure function of the `meta.json` folders, 11 keys, byte-stable, atomic | **Unchanged** (`to_ledger_row`, `rebuild_ledger_file`) | none |
| Never-repeat digest (`_tried_list_body`: one line per row incl. FAILED) | Unchanged | `kx new` also returns `data.tried` so the AI sees the digest before choosing an idea |
| `strategy.md` = header + current best (direction from `config.metric.greater_is_better`) + digest + CV→LB section + verbatim reasoning; atomic overwrite; blocks without a reasoning file | Unchanged | Invoked as `kx strategy --reasoning-file <path>`. Reads `control/config.json` `metric`, which `kx metric` writes. |
| `VERDICT.md` stub via `create_if_absent` | Unchanged | `kx strategy` refuses while placeholders remain |
| Provenance staging by explicit path (never `git add -A`) | Unchanged | Recommended: `kx run` commits `experiment.json` + `train.py` + `kernel-metadata.json` **before** the push, so `provenance.git_commit` names the exact pushed code; `kx strategy` commits `meta.json`/`VERDICT.md`/ledger/strategy (explicit paths; the leak hook guards it) |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Kernel status parsing | a regex over CLI prose | `api.kernels_status(ref).status.name` (SDK enum) | Structured and verified in source; no false tokens |
| Push version number | a regex `Kernel version (\d+)` | `ApiSaveKernelResponse.version_number`, else a `get_kernel().metadata.current_version_number` read-back | The CLI can print no number; read back, never guess |
| Backoff / poll loop | a new poller (or promoting spike `kwait.py`) | v1 `poll_loop` + `compute_delay` | Live-proven: jitter, transient tolerance, detach-not-cancel, deterministic tests |
| Competition metadata | page scraping / `competitions pages` | SDK `get_competition` / files summary / tree | PROF-01 forbids prose; 19/20 accuracy (spike 001) |
| KaggleObject → JSON | ad-hoc `vars()` | spike-001 `plain()` walker over `_fields`, then an allow-list | `KaggleObject`s are frozen and use private fields |
| Zip / path traversal | `os.path.join` + hope | port `safe_extract` checks → `safe_join()` | Rejects absolute paths, `..`, backslashes, NUL |
| Credential masking / leak guard | new masking | v1 `_mask`, `_detect_token_type`, `leak_scan.py` hook | Live-verified; tests exist |
| Ledger/strategy | new renderers | ported `experiment_meta`/`rebuild_ledger`/`regen_strategy` | CORE-04 says "unchanged" |
| Packaging / entry point | shell wrappers, PATH hacks | `[project.scripts]` + `uv_build` + `uv sync --project` | Verified in this session |

**Key insight:** every Kaggle fact that v1 regex-parsed from prose (status, version, type, daily limit) has a typed field in `kagglesdk`. The work is guarding the SDK's import-time and printing behavior, not parsing text.

## Runtime State Inventory

This is a refactor/migration phase: v1 scripts become the kx package.

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | v1 workspaces (throwaway Titanic workspaces from the v1 live runs) have `control/config.json` with v1 keys: `cv.scheme`, `submission.{daily_limit,limit_provenance,noise_k}`, `competition.type`, `execution_target`, `kernel.enable_internet`, `workspace_version: 1`. No committed user workspace exists in this repo. | **Code:** kx writes `workspace_version: 2` and refuses a v1 workspace (`status=invalid`, "create a fresh workspace") rather than migrating. No data migration is planned. [ASSUMED: no v1 workspace worth migrating; confirm with the user] |
| Live service config | Private kernels on the user's Kaggle account from v1 (`<user>/titanic-exp-001`). Spike kernels `kx-spike-*` were **deleted** (memory note). The new kx slugs `kx-<slug>-exp-NNN` do not collide with `titanic-exp-001`. | None required. The user can optionally delete the v1 kernel in the browser. |
| OS-registered state | None: no daemons or cron. The per-workspace git `core.hooksPath=.githooks` lives in each workspace's `.git/config`. | None |
| Secrets / env vars | `~/.kaggle/access_token` (600) and `~/.kaggle/kaggle.json` (600) exist; no `KAGGLE*` env set. v1 workspaces may hold a `.env` stub (`KAGGLE_USERNAME=`/`KAGGLE_KEY=`). | None. The credential names are unchanged. kx never reads or writes a workspace `.env`, but keeps the `.env`/`kaggle.json`/`access_token` gitignore lines as defense in depth. |
| Build artifacts / installed packages | The repo `.venv` was built with `[tool.uv] package = false` (kaggle in the dev group only). `uv.lock` is shaped for a virtual project. `__pycache__` for `scripts/`. | **Re-lock and re-sync:** `uv lock && uv sync` after the pyproject changes. This moves `kaggle` to runtime deps and adds the editable `kaggle-exp` project. Stale `scripts/__pycache__` goes away with `scripts/`. |

## Common Pitfalls

### Pitfall 1: importing `kaggle` kills the process and pollutes stdout
**What goes wrong:** `kx init` in a credential-less environment prints Kaggle's auth help and exits 1 before kx can emit JSON.
**Why it happens:** `kaggle/__init__.py` runs `api = KaggleApi(); api.authenticate()` at import. `authenticate()` ends in `print_auth_help(); exit(1)`. Even `from kaggle.api.kaggle_api_extended import KaggleApi` triggers the package `__init__` [VERIFIED: source + probe rc=1].
**How to avoid:** Pattern 3: import only inside `load_api()`, under `quiet()` + `deadline()`, catching `SystemExit`. Add a unit test that imports every `kx` module with no creds and checks that `sys.modules` contains no `kaggle`.
**Warning signs:** any `import kaggle` / `from kaggle` at module level; `kx --help` failing in CI.

### Pitfall 2: an internet-on kernel by omission
**What goes wrong:** a kernel runs with internet ON even though "internet off by default" was intended.
**Why it happens:** 2.2.3 `kernels_push` sets `request.enable_internet = get_bool(meta, "enable_internet", True)`, the opposite of the docs' "If not specified, will be `false`" [VERIFIED: source; CITED: kernels_metadata.md].
**How to avoid:** always write `enable_internet: false` explicitly, and after the push assert that `get_kernel().metadata.enable_internet is False`, recording it in `meta.kernel`.

### Pitfall 3: fail-open push
**What goes wrong:** a rejected push is treated as success, and kx polls a stale version.
**Why it happens:** the CLI wrapper prints `Kernel push error: …` or the invalid-sources lines and returns normally (exit 0) [VERIFIED].
**How to avoid:** SDK path: check `resp.error` and the `invalid_*_sources` lists, then verify the version by read-back.

### Pitfall 4: hung SDK call
**What goes wrong:** a network stall hangs kx forever, and the agent's Bash call times out with no envelope.
**Why it happens:** the kagglesdk HTTP client sends with no timeout. `requests.get(item.url)` in output download also has none [VERIFIED].
**How to avoid:** `deadline()` around every adapter call (SIGALRM, verified), plus explicit `timeout=` on our own `requests` calls. Map a timeout to `status=error`, `errors=["kaggle_timeout:<op>"]`.

### Pitfall 5: the Bash tool timeout vs a long poll
**What goes wrong:** the agent's Bash call dies at 120 s (the default) mid-poll.
**How to avoid:** Pattern 4: default `--wait ≈ 90 s`, `status=running`, resume via re-run. Write `kernel_run.json` right after the push.

### Pitfall 6: stdout contamination from children and libraries
**What goes wrong:** "exactly one JSON object" breaks because `git init` output, a kaggle warning or a `print()` lands on stdout.
**How to avoid:** the fd-level redirect (Pattern 1). Every `subprocess.run` uses `capture_output=True`. The contract test runs the real console script and asserts `json.loads(stdout)` with exactly one line.

### Pitfall 7: lowercasing the canonical ref for paths
**What goes wrong:** the kernel can't find its data for mixed-case refs such as `equity-post-HCT-survival-predictions`.
**How to avoid:** store `canonical_ref` from the `ref` URL. Use it for mount paths, and use the lowercase slug for `competition_sources` and kernel ids. v1's `_SLUG_RE = ^[a-z0-9][a-z0-9-]*$` rejects valid canonical refs, so allow `[A-Za-z0-9-]` for the ref [CITED: competition-profile.md; VERIFIED: v1 source].

### Pitfall 8: wrong-version outputs
**What goes wrong:** status and output in 2.2.3 always read the **latest** version. A second push (a rerun, or another session) makes kx record someone else's outputs.
**How to avoid:** read back `current_version_number` before recording and fail closed on a mismatch [VERIFIED: CHANGELOG "Next"].

### Pitfall 9: secrets inside the kernel
**What goes wrong:** the template dumps `os.environ` into the manifest or log, leaking `KAGGLE_USER_SECRETS_TOKEN`.
**How to avoid:** record `KAGGLE*` **keys only** (the spike-002 pattern). Add a unit test that the rendered template contains no `os.environ[...]` value dump [CITED: script-kernels.md].

### Pitfall 10: the leak hook runs under the system Python
**What goes wrong:** `leak_scan.py` gains a kx import or a third-party dependency and the pre-commit hook breaks. The hook runs as `.githooks/pre-commit` under the system `python3`, not the skill venv.
**How to avoid:** keep `kx/leak_scan.py` stdlib-only and self-contained (the existing `test_module_is_stdlib…`-style test).

### Pitfall 11: a live workspace inside the worktree
**What goes wrong:** the executor runs the live Titanic loop in a folder inside this git worktree. `kx init` then creates a nested `.git`, and the session sandbox refuses git commands it cannot attribute to the worktree. This session saw refusals for commands that set `HOME` or mix `git` with complex shell.
**How to avoid:** run the live workspace in a scratch dir outside the worktree, e.g. `/tmp/kx-live/titanic`. Have kx do its own git work internally, and verify through kx envelopes plus `Read` of files.

## Code Examples

### Guarded SDK loading + deadline (kx/kaggle_adapter.py)
```python
# Sources: kaggle/api/kaggle_api_extended.py (authenticate, get_config_value) [VERIFIED];
# PEP 475 SIGALRM behavior verified by /tmp/kxprobe/alarm_probe.py this session.
import contextlib, io, signal

class KxTimeout(Exception): ...
class CredentialUnavailable(Exception): ...

@contextlib.contextmanager
def deadline(seconds: float):
    def _raise(signum, frame):
        raise KxTimeout(f"deadline {seconds}s")
    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)

@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield

def load_api(timeout: float = 60):
    try:
        with quiet(), deadline(timeout):
            from kaggle.api.kaggle_api_extended import KaggleApi  # runs kaggle/__init__ → authenticate()
            api = KaggleApi()
            api.authenticate()
    except SystemExit as exc:            # print_auth_help(); exit(1)
        raise CredentialUnavailable("no_valid_credential") from exc
    return api, api.get_config_value("username")
```

### Push with read-back (kx/kernel.py)
```python
# Sources: kernels_push → ApiSaveKernelResponse fields; get_kernel metadata [VERIFIED: installed source]
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest   # kagglesdk import has no auth side effect

def push(api, kernel_dir, owner, slug, limit_s):
    with quiet(), deadline(120):
        resp = api.kernels_push(str(kernel_dir), timeout=str(limit_s))
    if resp is None or resp.error:
        return {"ok": False, "reason": "push_error"}            # quarantine resp.error; never echo it
    bad = [*resp.invalid_competition_sources, *resp.invalid_dataset_sources,
           *resp.invalid_kernel_sources, *resp.invalid_model_sources]
    if bad:
        return {"ok": False, "reason": "invalid_sources", "sources": bad}   # our own slugs → safe to show
    md = read_back(api, owner, slug)
    version = resp.version_number or md["current_version_number"]           # never guess
    if not md["is_private"] or md["enable_internet"]:
        return {"ok": False, "reason": "server_flags_mismatch"}             # fail closed (Pitfall 2)
    return {"ok": True, "version": version, **md}

def read_back(api, owner, slug):
    with quiet(), deadline(60), api.build_kaggle_client() as client:
        r = ApiGetKernelRequest(); r.user_name = owner; r.kernel_slug = slug
        m = client.kernels.kernels_api_client.get_kernel(r).metadata
    return {"current_version_number": m.current_version_number, "docker_image": m.docker_image,
            "machine_shape": m.machine_shape, "enable_internet": m.enable_internet, "is_private": m.is_private}
```

### Safe output pull
```python
# Source: kernels_output implementation [VERIFIED]; path check adapted from scripts/safe_extract.py
import requests
from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest

def safe_join(root: Path, name: str) -> Path:
    if not name or "\x00" in name or "\\" in name or Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError("unsafe output file name")
    p = (root / name).resolve()
    if root.resolve() not in p.parents:
        raise ValueError("unsafe output file name")
    return p

def pull(api, owner, slug, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    log, token, files = None, None, []
    with api.build_kaggle_client() as client:
        while True:
            req = ApiListKernelSessionOutputRequest(); req.user_name = owner; req.kernel_slug = slug
            req.page_size = 100
            if token: req.page_token = token
            with quiet(), deadline(60):
                resp = client.kernels.kernels_api_client.list_kernel_session_output(req)
            log = log if log is not None else resp.log
            for f in resp.files or []:
                dest = safe_join(out, f.file_name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with deadline(600), requests.get(f.url, stream=True, timeout=(15, 120)) as r:   # never log f.url
                    r.raise_for_status()
                    with open(dest, "wb") as fh:
                        for chunk in r.iter_content(1 << 20): fh.write(chunk)
                files.append(dest)
            token = resp.next_page_token
            if not token: break
    return files, log
```

### CLI main with fd guard and JSON argparse errors (kx/cli.py)
```python
import argparse, json, os, sys

class UsageError(Exception): ...
class KxParser(argparse.ArgumentParser):
    def error(self, message):            # argparse would print usage to stderr and exit(2)
        raise UsageError(message)

def main(argv=None) -> int:
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    sys.stdout.flush(); os.dup2(devnull, 1)           # children + C code + prints → /dev/null
    try:
        try:
            env = dispatch(argv)                       # returns an envelope dict; never prints
        except UsageError as exc:
            env = envelope.make("invalid", errors=[str(exc)], next_action={"kind": "run", "then": "kx --help"})
        except Exception as exc:                       # never a traceback on stdout
            env = envelope.internal_error(exc)         # type name only; traceback → control/raw/last-error.txt
        finally:
            sys.stdout.flush()
    finally:
        os.dup2(saved, 1); os.close(saved); os.close(devnull)
    os.write(1, (json.dumps(env, ensure_ascii=False) + "\n").encode())
    return 0 if env["status"] in ("ok", "running") else 1
```

### Profile allow-list (kx/profile.py)
```python
# Source: spike 001 probe.py/classify.py [CITED]; field names from raw/titanic.json [VERIFIED]
COMP_FIELDS = ("title", "category", "evaluation_metric", "max_daily_submissions",
               "is_kernels_submissions_only", "submissions_disabled", "deadline",
               "max_team_size", "host_name", "user_has_entered")   # NO description/url/thumbnail

def build_profile(slug, comp, summary, root) -> dict:
    canonical = str(comp["ref"]).rstrip("/").rsplit("/", 1)[-1]      # 'equity-post-HCT-survival-predictions'
    fsi = (summary or {}).get("file_summary_info") or {}
    return {"schema_version": 1, "slug": slug.lower(), "canonical_ref": canonical,
            "competition": {k: comp.get(k) for k in COMP_FIELDS} | {"tags": [t.get("name") for t in comp.get("tags") or []]},
            "files_summary": {"total_file_count": fsi.get("total_file_count"),
                              "total_bytes": sum(int(t.get("total_size") or 0) for t in fsi.get("file_types") or []),
                              "file_types": [{k: t.get(k) for k in ("extension", "file_count", "total_size")}
                                             for t in fsi.get("file_types") or []]},
            "root_listing": {"files": [{"name": f.get("name"), "total_bytes": f.get("total_bytes")} for f in root.get("files") or []],
                             "directories": [d.get("name") for d in root.get("directories") or []]},
            "provenance": {"source": "kagglesdk get_competition + data_files_summary + list_data_tree_files(root)"}}
```

## State of the Art

| Old Approach (v1) | Current Approach (v2 Phase 6) | When Changed | Impact |
|---|---|---|---|
| 29 scripts, exit codes 65/69/75/77/78 | one `kx` + a JSON envelope with `next_action` | CORE-01 | SKILL.md shrinks; the AI follows `next_action` |
| `kaggle` CLI subprocess + regex (status/version/limit/type) | in-process `kagglesdk` typed responses | spikes 001–003, 2026-09-25 | Removes the prose scraping and the fail-open push |
| jupytext `.py`→`.ipynb` notebook kernels (4 live bugs) | `kernel_type: "script"` | spike 002/003 | No kernelspec, argv or SystemExit hacks |
| Data at `/kaggle/input/<slug>` | `/kaggle/input/competitions/<Canonical>` first | observed live, spike 002 | The resolver order is fixed |
| 4-option CV enum (`cv.scheme`) | AI-written `assign_folds()` + recorded reasoning | TMPL-01 | Arbitrary CV (group, time, custom) |
| `oof.npy` without ids | `kx-preds/1` CSV with `row_id, fold, target` | ENS-01 | Blendable across experiments |
| stdlib-only, `package = false` | a uv-packaged editable project, `kaggle==2.2.3` runtime dep | v2 decision | `uv sync` is the install |

**Deprecated/outdated:**
- `NvidiaTeslaP100` (retired, per CLI changelog)
- `kaggle kernels status`/`output` ignoring the version suffix (fixed only in the unreleased "Next")
- the v1 `--accelerator` P100 choice

## Recommended Plan Slicing (Research Q8, MVP vertical slices)

This is not a web app. "UI" = a `kx` invocation, "DB" = workspace JSON/JSONL, and "deploy" = `uv sync` plus a live `kx` run. Each slice ends with something the user can *do*.

| Plan | Wave | Slice (user can…) | Requirements | Depends on | Live check inside the plan |
|---|---|---|---|---|---|
| **06-01 Walking skeleton** | 1 | `uv sync` → `kx init` → `kx status`: set up a workspace and validate the credential. Contents: pyproject/uv_build/`[project.scripts]`, `cli.py` + envelope + fd guard + JSON argparse, `workspace.py` (ported helpers, no egress/consent/.env), `credentials.py`, `kaggle_adapter.load_api` + `deadline`/`quiet`, FakeAdapter + contract test. Writes SKELETON.md. | CORE-01, CORE-02, CORE-06 | — | `uv sync --project` from an empty `/tmp` folder; `kx init` with the real `access_token` → VALIDATED, masked, no token in the transcript |
| **06-02 Profile a competition** | 2 | `kx sync titanic` → `control/profile.json`; `kx metric accuracy` | PROF-01 (+ metric part of CORE-04) | 06-01 | `kx sync titanic` live; optionally also `equity-post-HCT-…` to prove canonical-case extraction |
| **06-03 Declare an experiment** | 2 (parallel with 06-02; tests use a fixture `profile.json` in the contract shape defined here) | `kx new --idea … --hypothesis …` → `experiment.json` draft + rendered tabular `train.py` (AI block, `kx-preds/1` writer, manifest); `validate_experiment`; `preds.py` validator | CORE-03, TMPL-01, ENS-01 (format + validator) | 06-01 | local only; optional `template-test` group runs the harness on a synthetic Titanic-shaped frame and validates its outputs with `preds.py` |
| **06-04 Run on Kaggle and record** | 3 | `kx run exp-001` → private CPU script kernel → bounded poll (`--wait`) → safe pull → fail-closed record (ported ladder + preds rung) → `meta.json` + ledger rebuild | RUN-01, CORE-04 (recorder/ledger), ENS-01 (recorder side), TMPL-01 live | 06-02, 06-03 | **LIVE Titanic happy path**: SUCCESS, machine-checked CV, OOF + test in `kx-preds/1`, version read back, internet false read back |
| **06-05 Close the loop** | 4 | verdict gate → `kx strategy` (port regen_strategy/lb_gap/submissions_log) → cycle commit; `kx new` shows the digest; SKILL.md rewritten around kx (lean); `references/kx-reference.md` | CORE-04 (strategy/digest), CORE-01 (the AI follows `next_action` alone) | 06-04 | **LIVE criterion 5**: (a) a throwing kernel → FAILED(kernel_error), no score; (b) a kernel writing a lying/invalid `result.json` → FAILED(schema_invalid); digest lists all 3 ideas; one full cycle driven only by `next_action` (transcript in VERIFICATION) |
| **06-06 Retire v1** | 4 (parallel with 06-05; disjoint files) | Delete superseded scripts/tests/templates (tables above); port dormant `submission_gate` without the noise margin or "assumed"; egress doc → opt-in snippet + "**enforcement UNVERIFIED** (01-03 example.com anomaly)"; README; grep-based CORE-07 test | CORE-07 | 06-04 (the ports must exist first) | `uv run pytest` green with `scripts/` gone; the grep test finds no superseded tokens in `src/` or `SKILL.md` |

**Ordering notes:**
- 06-02..05 add *new* files under `src/kx/` and `tests/` and leave `scripts/` untouched. That avoids cross-plan file conflicts, and the v1 suite stays green until 06-06 deletes it.
- The ported tests import `from kx import …`. There are no bare-name imports, because `conftest.py` puts `scripts/` on `sys.path` until 06-06.
- Budget: each live CPU run takes about 30–90 s [CITED: "A trivial CPU script kernel reaches COMPLETE in about 30 s, including queueing"]. Phase 6 needs about 4–6 kernel runs and **zero GPU**.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | A wrong legacy `KAGGLE_KEY` gets a 401 on `competitions_list`. Kaggle rejects bad basic auth even on public endpoints. | API surface A | `kx init` could report VALIDATED for a bad legacy key. Mitigation: the first `kx sync` would then fail. Needs a live negative check if a legacy key is in use (the user uses `access_token`). |
| A2 | `list_kernel_session_output` returns all files as soon as status is COMPLETE. No eventual-consistency gap. | API surface E | A false `missing_result` FAILED. Mitigation: retry the listing 2–3× with short backoff when COMPLETE and empty. |
| A3 | Kernel titles and slugs are limited to 50 chars. | Kernel packaging | Long slugs give an opaque 500. Truncation with a hash suffix is harmless either way. |
| A4 | Streaming stdlib validation of ~1M-row CSVs is fast enough (seconds). | Prediction format | A slow record on huge comps; irrelevant for Titanic. |
| A5 | No v1 workspace needs migrating to v2 (kx refuses `workspace_version: 1`). | Runtime State | The user loses a v1 workspace's continuity. Confirm with the user. |
| A6 | Deleting v1 `check_submission.py`/`submit.py`/`fetch_lb.py` (rather than keeping them dormant) is acceptable. Phase 9 rebuilds on the kept pure modules. | v1 Inventory | Phase 9 re-derives code from git history (low cost). |
| A7 | The optional `template-test` group (pandas/numpy/sklearn/lightgbm) is acceptable as a *dev-only, non-default* group despite "kaggle package only". | Standard Stack | If rejected, template harness tests run only live or via `uv run --no-project --with …` ephemerally. |
| A8 | The SIGALRM deadline is acceptable (POSIX-only). | Pattern 3 | Windows users would lack the timeout guard. The project is Linux-first. |

## Open Questions

1. **Metric mapping UX**
   - What we know: `evaluation_metric` holds display names ('Categorization Accuracy', 'Roc Auc Score', 'eefs_concordance_index'). v1's registry uses keys (`accuracy`, `roc_auc`) and lacks `mse`.
   - What's unclear: whether Phase 6 should ship a suggestion map at all, or leave it to the AI.
   - Recommendation: `kx sync` returns `data.metric_suggestion` from an exact-match map (unknown → null). The AI runs `kx metric <key>`. Add `mse` to the registry.
2. **Kaggle image package pins**
   - What we know: Python 3.12.13 on the kernel.
   - What's unclear: the exact pandas/sklearn/lightgbm versions.
   - Recommendation: the template prints them into `kx_manifest.json` and the log. The first live run records them in VERIFICATION, which also informs the optional local `template-test` floors.
3. **Where the live workspace lives**
   - What we know: the session sandbox refuses git commands it cannot attribute to the worktree.
   - Recommendation: `/tmp/kx-live/<name>`, driven only through `uv run --project <worktree> kx …`, with inspection via `Read`. If kx's internal `git` is blocked, fall back to a gitignored scratch dir and note it.
4. **`CANCEL_REQUESTED` terminal-or-not**
   - What we know: the spike and v1 disagree.
   - Recommendation: v1 semantics (in-flight) within the bounded wait. Phase 8 (RUN-04) finalizes the runtime-limit handling.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| uv | CORE-06 install, `uv run` | ✓ | 0.11.14 | — |
| Python (skill env) | kx | ✓ | 3.13.13 (≥3.11 required) | — |
| `kaggle` package | adapter | ✓ (in repo `.venv`) | 2.2.3 (lock) | — |
| git | workspace, leak hook | ✓ | 2.43.0 | — |
| Kaggle credential | init/sync/run live checks | ✓ | `~/.kaggle/access_token` (600), `kaggle.json` (600) | — |
| Network to api.kaggle.com + GCS | live checks | ✓ (spikes ran today) | — | — |
| Kaggle CPU kernel quota | RUN-01 live | assumed ✓ | — | none; blocking if exhausted |
| bubblewrap / socat | opt-in egress only | ✓ | present | not needed (the allowlist is opt-in) |
| jq | optional ledger inspection | ✓ | — | — |
| slopcheck | package audit | ✗ | — | registry checks via the PyPI JSON API (done) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** slopcheck (registry verification was used instead).

## Validation Architecture

### Test Framework
| Property | Value |
|---|---|
| Framework | pytest 9.1.1 (dev group, locked) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths `tests`, `addopts = -m 'not live'`, marker `live`) |
| Quick run command | `uv run pytest -q -x` (today 12.4 s for 341 tests; a kx-only subset: `uv run pytest -q tests/kx`) |
| Full suite command | `uv run pytest -q` + (optional) `uv run --group template-test pytest -q tests/template` |
| Live command | `uv run pytest -m live -q tests/live` (real Kaggle; CPU kernels; never submits) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| CORE-01 | Every subcommand (init/sync/metric/new/run/strategy/status/help/bad-usage) prints exactly one JSON object with `status` + `next_action`; a stray print or child stdout never leaks; exit 0 iff ok/running | unit (in-process, FakeAdapter) + subprocess (`python -m kx`, console script) | `uv run pytest -q tests/kx/test_cli_contract.py` | ❌ Wave 0 |
| CORE-01 | The AI completes the loop from `next_action` alone | LIVE (manual transcript in VERIFICATION) | executor follows envelopes from `kx init` to `kx strategy` | n/a |
| CORE-02 | init layout + git + leak hook; no settings.json/.env/pyproject; credential masked; fabricated token never appears in stdout/stderr; missing creds → `needs_user` (no traceback, no prompt, no `input()`) | unit | `uv run pytest -q tests/kx/test_init.py tests/kx/test_credentials.py tests/kx/test_adapter_guard.py` | ❌ Wave 0 |
| CORE-02 | Real credential validates live | LIVE | `uv run pytest -m live tests/live/test_live_init.py` | ❌ Wave 0 |
| CORE-03 | Validator matrix (each field missing/invalid/placeholder/unknown key/local target/kernel sources/P100) + `kx run` refuses before `adapter.push` is called | unit | `uv run pytest -q tests/kx/test_experiment_spec.py tests/kx/test_run_refuses_invalid.py` | ❌ Wave 0 |
| CORE-04 | Recorder ladder, ledger byte-stability, strategy facts, digest incl. FAILED rows | unit (ported v1 tests) | `uv run pytest -q tests/kx/test_record.py tests/kx/test_ledger.py tests/kx/test_strategy.py tests/kx/test_lb_gap.py tests/kx/test_submissions_log.py` | ❌ Wave 0 (port from `tests/test_record_*.py` etc.) |
| CORE-04 | Throwing kernel / invalid `result.json` → FAILED, null score; digest lists ideas | LIVE | `uv run pytest -m live tests/live/test_live_failures.py` | ❌ Wave 0 |
| CORE-06 | `uv sync --project <repo>` from an empty tmp dir → `kx status` JSON; pyproject pins `kaggle==2.2.3` and declares `kx` | smoke (subprocess; needs network for the first build) | `uv run pytest -q tests/kx/test_packaging.py` | ❌ Wave 0 |
| CORE-07 | No superseded tokens in `src/`, `SKILL.md` or templates; deleted files absent; egress doc says "unverified"; kx never imports jupytext | static (grep/AST) | `uv run pytest -q tests/kx/test_core07_removals.py` | ❌ Wave 0 |
| PROF-01 | `build_profile` from spike-001 raw fixtures (prose fields stripped): allow-listed keys only, canonical ref from URL (equity mixed case), no `description` anywhere | unit | `uv run pytest -q tests/kx/test_profile.py` | ❌ Wave 0 (fixtures: copy `.planning/spikes/001-*/raw/{titanic,equity-post-hct-survival-predictions}.json` minus prose) |
| PROF-01 | `kx sync titanic` live | LIVE | `uv run pytest -m live tests/live/test_live_sync.py` | ❌ Wave 0 |
| RUN-01 | metadata builder golden (script, private, `enable_internet:false` explicit, lowercase `competition_sources`, ≤50-char title); push error/invalid sources → fail; missing version → read-back; server-flag mismatch → fail; poll bounded → `running`; `safe_join` rejects `../`, absolute, backslash; version mismatch → fail | unit (FakeAdapter) | `uv run pytest -q tests/kx/test_kernel.py tests/kx/test_pull_safe.py tests/kx/test_poll.py` | ❌ Wave 0 |
| RUN-01 / TMPL-01 / ENS-01 | Titanic cycle live | LIVE | `uv run pytest -m live tests/live/test_live_titanic_cycle.py` | ❌ Wave 0 |
| TMPL-01 | Rendered template: `ast.parse` OK, no kx imports, AI-block markers present, `repr()`-injection safe, env keys only | unit | `uv run pytest -q tests/kx/test_template_render.py` | ❌ Wave 0 |
| TMPL-01 / ENS-01 | Harness on a synthetic frame writes files that pass `preds.validate` | unit (optional ML group) | `uv run --group template-test pytest -q tests/template` | ❌ Wave 0 |
| ENS-01 | `kx-preds/1` validator matrix (headers, counts, folds, NaN/inf, dup ids, column mismatch, path escape) | unit | `uv run pytest -q tests/kx/test_preds.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q -x tests/kx` (under 15 s)
- **Per wave merge:** `uv run pytest -q` (the whole offline suite, v1 tests included until 06-06)
- **Phase gate:** full offline suite green, **plus** the live checks run in-phase (06-01 init, 06-02 sync, 06-04 Titanic cycle, 06-05 failure paths plus the `next_action`-only transcript), recorded in VERIFICATION before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/kx/conftest.py`: `FakeAdapter` (records calls; scripted responses; can raise and print to stdout), `tmp_ws` fixture, fabricated-token env fixture
- [ ] `tests/kx/fixtures/`: stripped spike-001 raw JSON (titanic, equity), sample `kernel_run.json`, sample pulled `output/` sets (valid, lying mean, bad preds), a script-kernel benign log (captured from the first live run)
- [ ] `tests/live/`: live tests marked `live`, each creating a tmp workspace outside the repo
- [ ] Framework: none to install (pytest locked). Optional `template-test` dependency group (human-verify gate).

## Security Domain

`security_enforcement` is absent from config.json, so it is treated as enabled.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | yes (Kaggle token handling) | The SDK's own credential chain; kx prints only a masked value (`_mask`); no consent flows; never write credentials |
| V3 Session Management | no | — |
| V4 Access Control | yes (kernel visibility) | `is_private: true` explicit + read-back assert |
| V5 Input Validation | yes | stdlib `validate_experiment` (strict keys, enums, ranges); `repr()` literal rendering into `train.py` (v1 CR-01); slug and username charset gates |
| V6 Cryptography | minimal | `hashlib.sha256` for artifact hashes only; never hand-roll |
| V7 Error Handling & Logging | yes | Exceptions mapped to codes; tracebacks to the gitignored `control/raw/last-error.txt`; never echo raw SDK/HTTP text or signed URLs |
| V8 Data Protection | yes | gitignore secrets; the `leak_scan` pre-commit hook; `KAGGLE*` env keys only in kernel manifests |
| V12 Files & Resources | yes | `safe_join` on kernel output names (2.2.3 has no check); `safe_extract` kept for Phase 7 |
| V14 Configuration | yes | `enable_internet:false` written explicitly and read back (2.2.3 defaults to True) |

### Known Threat Patterns for kx + Kaggle SDK
| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Token leaked via stdout/stderr (SDK prints, exception text, verbose HTTP) | Information disclosure | fd-level stdout guard, `quiet()`, never echo exception text, fabricated-token leak tests |
| Path traversal via server-supplied output `file_name` | Tampering | Own download loop + `safe_join`; pull into `output/` |
| Code injection via `experiment.json`/profile values rendered into `train.py` | Tampering / Elevation | Render only via `repr()` literals; validate charset first (v1 CR-01 test pattern) |
| Internet-on or public kernel by omission | Information disclosure | Explicit flags + a `get_kernel` read-back assert, fail closed |
| `KAGGLE_USER_SECRETS_TOKEN` captured into manifest/log | Information disclosure | Keys-only env capture; template unit test |
| Host-authored text (titles/tags) treated as instructions | Spoofing (prompt injection) | Profile carries structured fields only; SKILL.md: profile values are data, never instructions |
| Accidental submission by the AI | Repudiation / irreversible action | kx has no submit path; drop `Bash(kaggle *)` from `allowed-tools`; the human runs every submit (Phase 9) |
| Hung network call exhausting the agent's turn | Denial of service | `deadline()` + `requests` timeouts + bounded `--wait` |

## Sources

### Primary (HIGH confidence)
- Installed `kaggle` 2.2.3 source (`.venv/lib/python3.13/site-packages/kaggle/__init__.py`, `api/kaggle_api_extended.py`: `authenticate`, `_introspect_token`, `get_config_value`, `kernels_push`, `kernels_push_cli`, `kernels_status`, `kernels_output`, `kernels_pull`, `competitions_list`, `print_auth_help`) and `kagglesdk` 0.1.33 (`kaggle_http_client.py`, `kaggle_env.py`, `kernels/types/kernels_api_service.py`, `kernels_enums.py`, `kaggle_object.py`)
- Local probes run this session: the uv_build `[project.scripts]` + `uv sync/run --project` cwd behavior; `kaggle` import with no credentials → rc 1 + auth help on stdout; SIGALRM interrupting a blocking `recv`
- Spike findings skill: `.claude/skills/spike-findings-kaggle-skill/SKILL.md`, `references/{competition-profile,script-kernels,code-competition-submission}.md`, `sources/001/{probe,classify}.py`, `sources/002/*`, `sources/003/*`, `sources/_shared/kwait.py`; `.planning/spikes/001-*/raw/*.json`, `results.md`
- Repo: `scripts/*.py`, `scripts/templates/*`, `tests/*`, `references/kaggle-cli-behavior.md`, `references/egress-allowlist.md`, `SKILL.md`, `pyproject.toml`, `uv.lock`; `pytest --collect-only`
- `.planning/{REQUIREMENTS,ROADMAP,STATE,PROJECT}.md`, `.planning/spikes/{WRAP-UP-SUMMARY,CONVENTIONS}.md`
- PyPI JSON API (versions, upload dates, source repos for kaggle, kagglesdk, uv-build, pytest, pandas, numpy, scikit-learn, lightgbm, pydantic, ruff)
- Kaggle CLI CHANGELOG (raw.githubusercontent.com/Kaggle/kaggle-cli/main/CHANGELOG.md): 2.2.4 + "Next" entries

### Secondary (MEDIUM confidence)
- https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md: field docs (contradicted by the 2.2.3 code on the `enable_internet` default)
- https://docs.astral.sh/uv/concepts/build-backend/: uv_build requires/bounds, `src/<name>` default, `module-name`
- https://github.com/Kaggle/kaggle-cli/pull/179: kernel title ≤50 chars (an old PR; treat as MEDIUM)

### Tertiary (LOW confidence)
- Web search for the current Kaggle docker image pins was inconclusive, so they are recorded as an Open Question (the live run will print them)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. The lock, PyPI and the packaging probe were all verified here.
- Kaggle API surface: HIGH. Read from the installed source and cross-checked with the live spike findings. The in-process push/pull path itself runs live for the first time in 06-04 (the CLI wrappers over the same functions are live-verified).
- Architecture/contracts (envelope, `experiment.json`, `kx-preds/1`, slicing): MEDIUM. They are sound recommendations under the locked constraints and still need the in-phase live run.
- Pitfalls: HIGH for 1–4 and 6–9 (verified in source or by probe). MEDIUM for 5 (tool-timeout sizing) and 11 (sandbox behavior observed this session).

**Research date:** 2026-09-25
**Valid until:** 2026-10-25, or until `kaggle` is upgraded past 2.2.3, whichever comes first. The "Next" changelog changes the output/version semantics.
