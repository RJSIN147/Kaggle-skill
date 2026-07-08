<!-- GSD:project-start source:PROJECT.md -->
## Project

**Kaggle Experimentation Framework**

A standalone Claude Code skill that turns an empty folder into an AI-driven Kaggle
**competition** experimentation workspace. It connects to the user's Kaggle account via the
Kaggle CLI/API, scaffolds a structured workspace, and drives a well-documented experiment loop:
the AI proposes an idea, runs it (locally by default or pushed to a Kaggle Kernel for GPU),
captures the result and a written verdict, versions it in a ledger backed by git, and updates a
living strategy. Built first for a single practitioner competing on Kaggle through Claude Code.

**Core Value:** One clean end-to-end experiment cycle must work reliably — from an empty folder to an idea run,
its result and reasoning logged to the ledger, and the strategy doc updated. Everything else in
the framework exists to serve that loop.

### Constraints

- **Runtime**: Claude Code first — avoid hard dependencies that would block porting to opencode/other agents later.
- **Dependencies**: Kaggle CLI/API only; no dependency on external skills (standalone).
- **Compute**: Kaggle Kernels for GPU/heavy compute and official submissions; local execution for fast default iteration.
- **Kaggle limits**: Respect competition submission limits and kernel quotas; CV-first discipline conserves submission budget.
- **Security**: Requires a Kaggle API token; network egress scoped to Kaggle and standard package sources.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## TL;DR (the prescriptive answer)
## Recommended Stack
### Core Technologies
| Technology | Version (2026-07-09) | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Agent Skills format** (`SKILL.md`) | open standard (agentskills.io); Claude Code v2.1.x runtime | The delivery vehicle: frontmatter + instructions + bundled files | Native to Claude Code and portable across 35+ agents. Progressive disclosure keeps token cost near-zero until invoked. |
| **`kaggle` CLI / API** (PyPI `kaggle`) | **2.2.3** (GA, out of beta; requires Python ≥3.11) | Auth, competition data download, kernel push/status/output/pull, submissions, leaderboard | One tool covers the entire loop. Scriptable from any shell → agent-agnostic. GA means backwards-compatibility commitments (breaking changes only on major bumps). |
| **Python** | **3.11+** (3.12 present locally; target 3.11 as floor) | Runtime for all helper scripts and generated experiments | `kaggle` and `kagglehub` are Python packages, so Python is already a hard dependency — standardize on it rather than adding a second scripting language. 3.11 is the CLI's floor. |
| **uv** | **0.11.x** (0.11.14 present locally) | Environment/dependency management + `uv run` for scripts | 2026 standard Python package manager: fast, reproducible lockfiles, no global-state pip mess. Present in this environment. |
| **git** | 2.4x+ | Version the workspace: code diffs under the JSONL/markdown ledger | Required by the project's "structured ledger + git" decision; diffable experiment code history. |
### Kaggle Integration — Primitive Selection (the key decision)
| Concern | **Standardize on** | Also usable | Do NOT depend on |
|---------|--------------------|-------------|------------------|
| Auth / credential validation | `kaggle` CLI | kagglehub, MCP | MCP |
| Competition data download (local runs) | `kaggle competitions download` | `kagglehub.competition_download()` | MCP |
| Kernel push / run / poll / pull output | `kaggle kernels push/status/output/pull` | MCP notebook-session tools | — (kagglehub *cannot* do this) |
| Submission + LB read-back | `kaggle competitions submit` / `submissions` / `leaderboard` | MCP | — (kagglehub *cannot* submit) |
- **Completeness:** The CLI is the only one of the three that does *everything* the loop needs (kagglehub cannot push kernels or submit; MCP can but is optional wiring). Using one primitive avoids a split-brain integration.
- **Portability:** A shell-invokable CLI works identically under Claude Code, opencode, gemini-cli, Cursor, or a bare terminal. MCP requires the host to speak MCP and to be configured with `.mcp.json` — a Claude-Code-shaped dependency that fights the "port later" constraint.
- **Stability:** Per the reference skill's own live-server audits, MCP tool availability and behavior have drifted (tools flipping between PASS/KNOWN_FAIL/role-gated across dates). The CLI's command surface has been stable across the 1.x→2.x transition.
- **Auditability/security:** Shell commands are easy to allow-list (`Bash(kaggle *)`) and reason about for egress scoping.
### Supporting Libraries — Generated-Notebook ML Stack
| Library | Version (2026-07-09) | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pandas** | **3.0.3** | Tabular data wrangling | Default for CSV/parquet competition data. (See Version Compatibility — 3.0 is a breaking major.) |
| **numpy** | **2.5.1** (requires Python ≥3.12) | Array math, metrics | Universal dependency. |
| **scikit-learn** | **1.9.0** | **CV splitters** (`KFold`, `StratifiedKFold`, `GroupKFold`, `TimeSeriesSplit`), metrics, preprocessing, baselines | The CV-first backbone. Every experiment's cross-validation goes through `sklearn.model_selection`. |
| **lightgbm** | **4.6.0** | Gradient-boosted trees | **Default first model** for tabular competitions — fast, strong, low-tuning baseline. |
| **xgboost** | **3.3.0** | Gradient-boosted trees | Second GBDT for ensembling / when LightGBM underperforms. |
| **catboost** | **1.2.10** | Gradient-boosted trees | Best out-of-box on high-cardinality categorical data. |
| **optuna** | **4.9.0** | Hyperparameter search | Optional; only when an experiment's hypothesis *is* tuning. (Sweeps are explicitly out-of-scope for v1 as a first-class feature.) |
| **polars** | **1.42.1** | Fast DataFrames / lazy execution | When data is large enough that pandas is the bottleneck. |
| **pyarrow** | **24.0.0** | Parquet/Feather I/O, Arrow-backed strings | Fast columnar I/O; backs pandas 3.0 string dtype. |
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **kagglehub** | **1.0.2** (GA; requires Python ≥3.10) | Pythonic dataset/competition download with `KaggleDatasetAdapter.PANDAS` / `.POLARS` DataFrame adapters | Optional sugar inside a generated notebook. Not required — the CLI already downloads data. Install extras: `kagglehub[pandas-datasets]` / `[polars-datasets]`. |
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **jupytext** | 1.16+ | Lossless `.py` ⇄ `.ipynb` conversion | Keep experiments as diffable `.py` locally; convert to `.ipynb` at kernel-push time. Lightweight, pure-Python. |
| **papermill** | 2.6+ | Parameterized notebook execution + output capture | Only if you want *notebook-native* local execution instead of plain `python exp.py`. Adds the Jupyter stack — prefer plain `.py` runs unless notebook outputs are needed locally. |
### Experiment Ledger / Tracking — favor plain files
| Choice | Format | Purpose | Why |
|--------|--------|---------|-----|
| **Experiment ledger** | **append-only JSONL** (`ledger.jsonl`, one experiment per line: id, timestamp, hypothesis, model, CV score, LB score, artifact paths, verdict-file link) | Machine-queryable history the AI reasons over | Append-friendly (no rewrite races), merge/diff-friendly under git, trivially parseable with stdlib `json`, streamable. Superior to a single JSON blob for an append-heavy log. |
| **Per-experiment verdict** | **markdown** (`experiments/exp-NNN/VERDICT.md`) | Human + AI narrative: what/why/worked-or-not | Matches "written verdict" requirement; rich prose lives better in markdown than JSON. |
| **Static competition facts** | **markdown** (`COMPETITION.md`) | Schema, eval metric, rules, submission limits | Rarely-changing reference; captured once at setup. |
| **Living strategy** | **markdown** (`STRATEGY.md`) | Current best, hypothesis queue, next moves | Evolving doc the AI rewrites each cycle. |
| **Config** | **JSON or TOML** (`config.json`) | Execution target (local/kaggle), competition slug, CV scheme defaults | Small structured state; the reference skill uses JSON dicts for persisted state (good precedent). |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Install/run/lock the Python environment | `uv run scripts/foo.py`; `uv.lock` pins the local env for CV reproducibility. |
| **ruff** | Lint/format the skill's Python | The reference skill uses ruff (E,F,I,W). Zero-config, fast. |
| **pytest** | Test helper scripts (mock-backed unit; optional `--run-live` integration) | The reference skill's test taxonomy (unit / manifest / security / integration) is a strong model — especially a manifest test asserting SKILL.md frontmatter validity. |
| **skill-creator plugin** | Eval the skill (does it trigger? is output right?) | `/plugin install skill-creator@claude-plugins-official`. Automates with-skill vs without-skill A/B, description tuning. Use during hardening. |
| **`jq`** | Query the JSONL ledger from bash | Present locally; handy for quick ledger summaries in shell wrappers. |
## Skill Authoring Reference (verified against official docs, 2026-07-09)
### SKILL.md frontmatter (all fields optional; only `description` recommended)
| Field | Use for this project |
|-------|----------------------|
| `name` | Display label; command name derives from directory (or plugin `name` at plugin root). |
| `description` | **The trigger.** Put the key use case first — combined `description`+`when_to_use` is truncated at **1,536 chars** in the listing. Include natural keywords ("Kaggle competition", "experiment", "CV", "submit"). |
| `when_to_use` | Extra trigger phrases; counts toward the 1,536 cap. |
| `allowed-tools` | **Pre-approve** the tools the loop needs so Claude doesn't prompt each time, e.g. `Bash(kaggle *) Bash(uv run *) Bash(git *) Read Write Edit`. This grants without *restricting* — baseline permission settings still apply. |
| `disable-model-invocation` | Set `true` on side-effecting sub-skills you want the user to fire deliberately (e.g. a `submit` action) so Claude never auto-submits. |
| `argument-hint` / `arguments` | For invocations like `/kaggle-exp <hypothesis>`. |
| `${CLAUDE_SKILL_DIR}` | Substitution to reference bundled scripts regardless of cwd: `python3 ${CLAUDE_SKILL_DIR}/scripts/poll_kernel.py ...`. Requires Claude Code v2.1.196+. |
| `!\`command\`` (dynamic context) | Inject live state (e.g. current ledger tail, `kaggle competitions submissions`) into the prompt at invoke time. Preprocessing — Claude sees output, not the command. |
### Progressive disclosure (the token-cost model)
- **Always in context:** every skill's `name` + `description` (subject to the ~1% context-window listing budget).
- **On invoke:** the full `SKILL.md` body enters context and *persists for the session*. Keep it lean (<500 lines) — every line is a recurring cost.
- **On demand:** bundled `references/*.md` and `scripts/*` load only when the body points Claude to them. This is why heavy Kaggle knowledge (CLI reference, metric catalog, kernel-metadata spec) belongs in `references/`, not in `SKILL.md`.
### Directory shape (mirror the reference skill's exemplar, minus its breadth)
### Egress scoping (Claude-Code-specific, keep documented for portability)
## Kaggle Integration — Concrete Command Surface (kaggle CLI 2.x)
- `~/.kaggle/kaggle.json` `{"username":"...","key":"..."}` + `chmod 600` (universal, legacy but fully supported)
- `~/.kaggle/access_token` file (newer) or `KAGGLE_API_TOKEN` env var
- `KAGGLE_USERNAME` + `KAGGLE_KEY` env vars (legacy)
- Token from **kaggle.com/settings → "Generate New Token"**. 2.x adds OAuth flow + multiple named tokens, but token/`kaggle.json` remains the portable baseline.
- Validate cheaply: `kaggle competitions list` or `kaggle config view` (exit code + no secret leakage).
- Attach the competition data with `competition_sources`; it mounts at `/kaggle/input/`.
- GPU: set `enable_gpu` or push `--accelerator`. IDs: `NvidiaTeslaP100`, `NvidiaTeslaT4`, `NvidiaTeslaT4Highmem`, `NvidiaTeslaA100`, `NvidiaL4`, `NvidiaH100`, `TpuV38`, etc.
- Quotas to respect: **GPU 30h/week, TPU 20h/week, 12h max session, 20GB `/kaggle/working`**.
- Daily limit typically **5/day**; failed (processing-error) submissions do **not** count. Ration against CV signal; log the CV→LB gap.
## Installation
# Skill's own tooling (dev + runtime) via uv
# Generated-experiment ML stack (local execution env)
# Optional notebook bridge for the Kaggle-Kernel path
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `kaggle` CLI as sole primitive | **Kaggle MCP server** (`https://www.kaggle.com/mcp`, ~66 tools) | Only if you commit to Claude-Code/MCP hosts *and* want the agent to call Kaggle without shell access. Adds `.mcp.json` + Bearer-token wiring; historically drifting tool availability. Keep as optional enhancement, not a dependency. |
| `kaggle` CLI for download | **kagglehub** `dataset_download` / `competition_download` | Inside a generated notebook where you want a DataFrame directly via `KaggleDatasetAdapter.PANDAS`. Cannot push kernels or submit — never the loop's backbone. |
| JSONL + markdown ledger | **SQLite** | Only at large scale (thousands of experiments, complex cross-experiment queries). For a single practitioner it's a binary, non-diffable file that fights the "git-backed, AI-readable" decision. |
| JSONL + markdown ledger | **MLflow / Weights & Biases** | Only if you later need a hosted dashboard, artifact store, or team collaboration. Both add a server/daemon + heavy deps and violate "simplest thing the skill can own." |
| Plain `.py` local runs | **papermill / nbconvert notebook execution** | When you specifically want rich rendered notebook outputs locally, not just a CV number + artifacts. Adds the Jupyter stack. |
| LightGBM default | **PyTorch / TensorFlow / timm / transformers** | Deep-learning competitions (vision, NLP, audio). These pull GPU + large deps → push to Kaggle Kernels rather than local. Out of the tabular default path. |
| uv | **pip / conda** | pip works but is slower and lockfile-poor; conda is heavy. The reference skill used pip (`pip install kaggle ...`) — still valid, but uv is the current standard and is already installed here. |
| Python stdlib scripts | **Pure bash scripts** | Genuine one-line CLI pipes (download, single status call). Anything with loops, timeouts, JSON parsing, or error handling belongs in Python. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Depending on shepsci/kaggle-skill** | Project decision: build standalone; avoid coupling to another skill's surface/lifecycle and its broad non-loop features (badges, forums, benchmarks). | Reimplement only the ~6 Kaggle ops the loop needs, using the CLI. Study the reference skill as an *exemplar* of structure only. |
| **Kaggle MCP server as the integration backbone** | MCP host-dependent (fights opencode portability); tool availability has drifted across audits; duplicates CLI. | `kaggle` CLI; keep MCP as opt-in. |
| **kagglehub as the loop backbone** | Cannot push kernels or submit — download-only. | `kaggle` CLI for the full loop. |
| **SQLite / MLflow / W&B for the ledger** | Heavy or non-diffable; violates git-backed, AI-readable, skill-owned constraints. | Append-only JSONL + markdown. |
| **Bare `pip install` inside skill scripts at runtime** | Silent environment mutation is a security/repro smell; the reference skill's SessionStart hook explicitly avoids auto-`pip install`. | Declare deps; let `uv`/the user install; validate presence and instruct if missing. |
| **Blindly using latest pandas 3.0 / numpy 2.5 in generated Kaggle notebooks** | Code that runs locally on the newest stack may break on Kaggle's older pinned `kaggle/python` image (and vice-versa), poisoning CV→LB parity. | Target version *floors* compatible with Kaggle's image; or `!pip install` exact versions in-notebook when it matters. |
| **`enable_internet: true` on kernels by default** | Many code competitions forbid internet; leaving it on can invalidate submissions and widens egress. | Default `false`; only enable for a deliberate reason. |
| **Echoing/committing credentials** | `kaggle.json` / tokens are secrets. | `chmod 600`; `.gitignore` them; never print values; validate via exit codes. |
## Stack Patterns by Variant
- Data via `kaggle competitions download`; run `experiment.py` with `uv run`; CV via `sklearn.model_selection`; emit `result.json` (CV score + params) + artifacts into the experiment dir; append to `ledger.jsonl`.
- No Jupyter dependency required.
- AI authors a notebook (or convert `experiment.py` → `.ipynb` via jupytext); write `kernel-metadata.json` (`competition_sources`, `enable_gpu`); `kaggle kernels push`; poll with a **timeout-bounded** Python poller; `kaggle kernels output` to pull artifacts; parse CV score; append to ledger.
- LightGBM first, StratifiedKFold/GroupKFold per the target, optional CatBoost for categoricals. Optuna only when the hypothesis is tuning.
- Push to Kaggle Kernels for GPU; generated notebook uses PyTorch/transformers (Kaggle-preinstalled); local path is for orchestration/CV bookkeeping only.
- Keep `SKILL.md` standard-compliant; ensure scripts self-locate (`Path(__file__)`) and accept an explicit `--workspace` path rather than relying on `${CLAUDE_SKILL_DIR}`/`${CLAUDE_PROJECT_DIR}`; document egress requirements instead of hard-wiring `.claude/settings.json`.
## Version Compatibility
| Package | Latest (2026-07-09) | Recommended floor for generated code | Notes |
|---------|---------------------|--------------------------------------|-------|
| `kaggle` | 2.2.3 | ≥2.2 | GA; command surface stable vs 1.x. Requires Python ≥3.11. |
| `kagglehub` | 1.0.2 | ≥1.0 (optional) | GA; requires Python ≥3.10. `dataset_load()` adapters stabilized in 1.x (the 0.4.x `dataset_load` bug the reference skill warns about is fixed). |
| `pandas` | **3.0.3** | ≥2.2 | **3.0 is a breaking major** (Copy-on-Write default, PyArrow-backed strings). Kaggle's image may lag on 2.x — write code that works on both; don't rely on 3.0-only behavior in Kaggle notebooks. |
| `numpy` | 2.5.1 | ≥1.26 | 2.5.1 requires **Python ≥3.12**; keep the *skill's* floor at 3.11 (scripts are stdlib-only), but generated code using newest numpy needs 3.12. NumPy 2.x ABI differs from 1.x — match Kaggle's image. |
| `scikit-learn` | 1.9.0 | ≥1.5 | CV API is stable; safe across versions. |
| `lightgbm` / `xgboost` / `catboost` | 4.6.0 / 3.3.0 / 1.2.10 | 4.5 / 2.1 / 1.2 | XGBoost 3.x requires Python ≥3.12 for the newest wheels; 2.1 floor keeps 3.11 compatibility. |
| Local vs Kaggle image | — | — | **Primary parity risk.** The Kaggle Kernel runs against `kaggle/python` (its own pins), not your `uv.lock`. Keep local floors near Kaggle's image or `!pip install` exact versions in-notebook. This directly affects the CV→LB gap the project tracks. |
| Claude Code | 2.1.x | — | `${CLAUDE_SKILL_DIR}`/`${CLAUDE_PROJECT_DIR}` need v2.1.196+; nested-skill name qualification needs v2.1.203+. |
## Open Risks / Needs Implementation-Time Verification
- **Kernel `status` string parsing (MEDIUM):** The reference skill polls by grepping `kaggle kernels status` output for `complete`/`error`. The exact 2.x status strings/JSON shape weren't confirmable from docs today. Verify against a live run and prefer parsing structured output if the 2.x CLI offers it; always bound the poll with a timeout.
- **`competitions download --unzip` (MEDIUM):** Reference skill notes `--unzip` is unreliable/absent for competitions on CLI ≥1.8. Plan to unzip manually.
- **Code/notebook-only competition submission (MEDIUM):** 2.x added code-competition submission support; the exact kernel→submission flow (`--kernel`/`--version` on submit, or `create_code_competition_submission`) should be validated for the specific competition type at implementation.
- **Kaggle image version pins (MEDIUM):** Confirm the current `kaggle/python` versions of pandas/numpy/sklearn at build time to set safe generated-code floors.
## Sources
- **Claude Code — Agent Skills** (official, fetched 2026-07-09): https://code.claude.com/docs/en/skills — frontmatter fields + 1,536-char description cap, progressive disclosure model, `allowed-tools`/`disable-model-invocation`/`user-invocable`, `${CLAUDE_SKILL_DIR}`, dynamic context injection, supporting-file conventions, skill-creator evals. **Confidence: HIGH.**
- **Agent Skills open standard:** agentskills.io (referenced by official docs) — portability basis. **Confidence: HIGH.**
- **Kaggle CLI on PyPI** (fetched 2026-07-09): latest **2.2.3**, requires Python ≥3.11; GA/out-of-beta. **Confidence: HIGH.**
- **Kaggle CLI GitHub + product announcements** (fetched 2026-07-09): https://github.com/Kaggle/kaggle-cli , https://github.com/Kaggle/kaggle-cli/blob/main/CHANGELOG.md , "Kaggle CLI & kagglehub out of beta" — 2.0 rewrite, backwards-compat commitment, OAuth + multiple tokens, code-competition submission, subcommand aliases. **Confidence: HIGH** (narrative), **MEDIUM** (exact status strings / submit flags not quoted).
- **kagglehub on PyPI** (fetched 2026-07-09): latest **1.0.2**, Python ≥3.10; download-only for our purposes. **Confidence: HIGH.**
- **PyPI live versions** (fetched 2026-07-09): pandas 3.0.3, numpy 2.5.1, scikit-learn 1.9.0, xgboost 3.3.0, lightgbm 4.6.0, catboost 1.2.10, polars 1.42.1, optuna 4.9.0, pyarrow 24.0.0. **Confidence: HIGH.**
- **Reference exemplar — shepsci/kaggle-skill 2.3.0** (read locally at `~/.claude/plugins/cache/shepsci/kaggle-skill/2.3.0`): SKILL.md structure, `.claude/settings.json` egress allowlist + SessionStart hook, `.mcp.json`, `pyproject.toml`, `modules/kllm/references/cli-reference.md`, `kaggle-knowledge.md`, `mcp-reference.md`, `poll_kernel.sh`, `cli_execute.sh`, `cli_competition.sh`, `check_credentials.py`, `badge_tracker.py`, `kernel-metadata.json`. Used for structure/command-surface exemplar only (no dependency). **Confidence: HIGH** for structure; its version-specific caveats (kagglehub 0.4.x bugs, CLI ≥1.8 notes) predate the 1.0/2.x GA releases and were re-verified against current PyPI.
- **Kaggle platform facts** (via reference `kaggle-knowledge.md`, sourced from https://www.kaggle.com/docs): submission limits (~5/day), GPU/TPU quotas (30h/20h weekly, 12h session), `/kaggle/input` + `/kaggle/working`, accelerator IDs, kernel-metadata schema. **Confidence: MEDIUM-HIGH** (secondary source summarizing official docs).
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
