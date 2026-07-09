# Walking Skeleton — Kaggle Experimentation Framework

**Phase:** 1
**Generated:** 2026-07-09
**Revised:** 2026-07-09 (cross-AI review — settings.json deep-merge, mechanical D-01 slug gate, scaffold-scoped git staging, content-scanning leak guard)

## Capability Proven End-to-End

Running `init` on an empty folder produces a valid, git-tracked experiment workspace (control-plane + human docs + `.gitignore` + git repo on `main` with a scanned initial commit) whose Kaggle credential is validated with a live API call (clear pass/fail + per-failure remediation) and whose network egress is scoped by a deny-by-default allowlist in the workspace `.claude/settings.json`.

This IS the whole of Phase 1: the framework's walking skeleton is "empty folder → secure, ready workspace" — the foundation every later slice (competition context, experiment loop, kernels, submission) builds on without renegotiating it.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Delivery form | A Claude Code **skill** (`SKILL.md` + `scripts/` + `references/` at the repo root) that scaffolds and then operates on the user's cwd competition folder | Native to Claude Code, portable to other agents; the skill package is separate from the workspace it creates |
| Scaffolder | Self-locating **stdlib-only** Python (`scripts/init_workspace.py`), `Path(__file__)` for templates, explicit `--workspace` arg | CLAUDE.md portability constraint — no reliance on `${CLAUDE_SKILL_DIR}`/`${CLAUDE_PROJECT_DIR}`; ports to opencode/other agents |
| Init interaction | **Guided-then-scaffold** (D-01): SKILL asks slug + execution target, confirms, THEN runs the scaffolder; the scaffolder ALSO refuses to create a fresh workspace without `--slug` (mechanical D-01 gate — a direct script call cannot bypass the prompt-first contract) | Nothing created before the user answers — enforced by the script, not just SKILL convention |
| Idempotency | **Safe-merge** (D-02): create-if-absent for flat files; **deep-merge for control-plane JSON AND `.claude/settings.json`** (add missing keys/hosts, preserve user edits, union allowlist entries); a malformed pre-existing JSON is left untouched with a clear error (fail-clear, never clobbered); only `--set-execution-target` may overwrite one key | `init` is a re-runnable repair/top-up tool that never silently skips the allowlist and never destroys or clobbers user files |
| Workspace layout (D-10) | Human docs at root (`competition.md`, `strategy.md`, `README.md`); machine state under `control/`; `data/`; `experiments/exp-NNN/` | Docs read constantly by user+AI; machine state tucked away |
| Control-plane formats | `control/config.json` (workspace_version, competition_slug, `execution_target` enum, cv, created); `control/state.json` (credentials, next_exp_id); `control/ledger.jsonl` (append-only, one experiment/line) | JSON for small structured state; JSONL for append-heavy, diff-friendly history (CLAUDE.md ledger decision) |
| Execution target (SETUP-02) | Enum `local` (default) \| `kernel` in config.json; changed via `--set-execution-target`; Phase 1 owns the GLOBAL default only; a plain re-run never overwrites a manually-changed target | Fast local iteration by default; per-experiment override deferred to Phase 3 |
| Experiment ids (D-11) | Zero-padded sequential `exp-NNN`; `state.json.next_exp_id` is the cursor | Sorts lexically; matches CLAUDE.md convention |
| Credential model (D-04/D-05) | **Env vars canonical** (`KAGGLE_USERNAME`/`KAGGLE_KEY` or `KAGGLE_API_TOKEN`), persisted in a **gitignored workspace `.env`**; other sources (`kaggle.json`, `access_token`) detected and normalized toward env vars with consent | Aligns with kaggle CLI 2.x precedence (env beats file); nothing scattered in home/shell; cross-session persistence |
| Credential fixes (D-03/D-06) | chmod-600 self-heal and `.env` population are **consent-gated** via a `--yes` flag the SKILL passes only after asking; without consent, fixes are reported, not applied | No silent environment mutation (CLAUDE.md posture) |
| Live credential validation | `kaggle competitions list` — authenticated call, **exit-code-based**, prints no secret; captured subprocess stdout/stderr is never surfaced raw; observed exit-codes/precedence recorded in `references/kaggle-cli-behavior.md`; `kaggle config view` is local-only and NOT used as the validator | Only a real network call confirms the credential works; grounded in observed CLI behavior, not tribal memory |
| Credential-failure posture (D-07) | **Scaffold-anyway-flag-creds**: on failure the workspace stands, `state.json.credentials=UNVALIDATED`, remediation printed; only credential-dependent ops blocked downstream | Useful offline; re-run clears the flag |
| Egress enforcement (D-08/D-09) | Workspace `.claude/settings.json` **`sandbox.network.allowedDomains`** (OS-level bubblewrap+socat proxy over ALL Bash subprocesses), **DEEP-MERGED** into any pre-existing settings.json (union allowlist + preserve user keys — never create-if-absent) — NOT `permissions.allow: WebFetch(...)`, which governs only Claude's own WebFetch tool | The sandbox block is the only layer that constrains the `kaggle`/`uv`/`git` CLIs; merging (not create-if-absent) guarantees the allowlist is installed even when a settings.json already exists |
| Egress verification | Two deliverables: **generated settings correct** (automated tests) vs **host enforcement verified** (checkpoint, needs socat installed). Criterion 5 is fully met only when the socat-installed off-list refusal is observed | Generated files alone cannot prove refusal — socat is missing on this host and the sandbox silently degrades without it |
| Allowlist hosts (D-08) | `www.kaggle.com`, `kaggle.com`, **`storage.googleapis.com`** (+ `*.`), `pypi.org`, `files.pythonhosted.org`, `github.com`, `raw.githubusercontent.com`, `codeload.github.com`, conda channels. Hugging Face / model CDNs EXCLUDED | GCS backend is mandatory or `kaggle competitions download` silently breaks (302 to signed GCS URLs); model CDNs added in Phase 4 when weights are needed |
| Leak guard (D-15) | Defense in depth: `.gitignore` asserts secret coverage AND a **stdlib regex pre-commit scanner** (`scripts/leak_scan.py`) that scans **staged CONTENT** (via `git show :path`, not only diff lines) with broadened dotenv patterns (export/quoted/spaced/lowercase), wired via `git config core.hooksPath .githooks` (tracked, portable) — NOT `detect-secrets`/`pre-commit` framework; documented `git commit --no-verify` override | Standalone + stdlib-only + portable; content-scan catches secrets diff-only scanning would miss; initial commit made AFTER hook install so the baseline is itself scanned |
| Git init + initial commit | `git init -b main` with a portable fallback for older git; the initial `chore: scaffold workspace` commit stages **only scaffold-owned paths** (`git add -- <path>`, never `git add -A`) and is **idempotent** (no second scaffold commit on re-run) | Portable across git versions; a re-run on a non-empty workspace never sweeps unrelated user files into the scaffold commit |
| Git track vs ignore (D-12/D-13) | **Track:** `control/`, docs, experiment code, `meta.json`. **Ignore:** `.env`, `kaggle.json`, `access_token`, `data/`, model artifacts, `__pycache__/`, `.venv/`, and Phase 3 artifact patterns under `experiments/*/` (declared now) | Diffable code+ledger history; secrets and heavy artifacts never committed; `.gitignore` not rewritten later |
| Python env (D-14) | Minimal `pyproject.toml` stub in the workspace (from `pyproject.toml.tmpl`; Python ≥3.11 floor, uv config; NO ML deps) — **distinct from the skill's OWN repo-root `pyproject.toml`** (which carries pytest config). Full ML deps declared in Phase 3. Skill's own scripts stay stdlib-only | Env contract exists without pinning ML versions before they are exercised; no confusion between the two pyproject files |
| Test framework | pytest with a `live` marker in the skill's `pyproject.toml`; Nyquist per-task sampling per `01-VALIDATION.md`; the RED suite pins the locked decisions (D-01 slug gate, D-02 deep-merge/malformed, D-09 settings merge, D-03/D-06 consent, scaffold-commit scope) | Machine-verifiable acceptance; a decision without a test is a decision the later plans aren't forced to honor |

## Stack Touched in Phase 1

- [x] Project scaffold — skill package (`SKILL.md`, `scripts/`, `references/`, `tests/`, `pyproject.toml`) + pytest test runner
- [x] "Routing" (skill analogue) — the `init` invocation contract in `SKILL.md` driving `init_workspace.py` and `check_credentials.py`
- [x] "Database" (control-plane analogue) — one real write + read-back of `control/config.json` + `control/state.json` (machine state plane round-trips)
- [x] "UI interaction wired to backend" (skill analogue) — the guided `init` invocation running the real scaffolder + a real live `kaggle` credential check (real happy path)
- [x] "Deployment" (run command analogue) — documented full-stack run: `python3 scripts/init_workspace.py --workspace <dir> --slug <slug> --execution-target local` then `python3 scripts/check_credentials.py --workspace <dir>`, exercising empty-folder → validated-workspace end to end

## Out of Scope (Deferred to Later Slices)

- **Competition "constitution"** (`competition.md` populated with metric, schema, rules, CV scheme, adversarial validation) and **data download** — Phase 2. Phase 1 writes only an empty `competition.md` stub and records the slug.
- **Per-experiment execution-target override** — Phase 3 (experiments do not exist yet). Phase 1 owns the global default only.
- **Full ML dependency declaration + `uv.lock`** and the **local runner** — Phase 3. Phase 1 writes only a minimal `pyproject.toml` stub.
- **Untrusted-content wrapping / zip-slip-protected extraction** — Phase 2.
- **Hugging Face / model-CDN egress hosts** — added deliberately when the Phase 4 GPU/DL path needs weights.
- **Kernel push/poll/pull and submission/leaderboard** — Phases 4 and 5.
- **Hard no-prompt egress block** — requires managed/org settings; Phase 1 delivers deny-by-default at the workspace level (off-list refused/prompted), with the residual TLS-not-terminated caveat documented.

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2 — Competition Context & Data:** capture the machine-derived competition constitution into `competition.md` (metric, schema, rules, submission limit, CV scheme, adversarial validation) with untrusted-content wrapping; preflight UI-only Kaggle 403 gates; download + zip-slip-safe extract competition data locally.
- **Phase 3 — Local Experiment Loop, Ledger & Strategy (core value):** author a fresh notebook per experiment from a scaffold (backend-agnostic path + result contract), run locally to a CV score + artifacts, record idea/hypothesis/machine-checked result/verdict into an immutable `experiments/exp-NNN/` folder, land every run in the git-backed ledger (`meta.json` canonical + derived `ledger.jsonl`, provenance fields), and regenerate `strategy.md` from the ledger each cycle.
- **Phase 4 — Kaggle Kernel Execution (GPU path):** push an experiment to a Kaggle Kernel with valid kernel-metadata (competition_sources, GPU on, internet off by default), poll to completion with backoff, pull results into the same artifact/result contract, and scan the run log for tracebacks (silent-failure detection). Adds model-CDN egress hosts as needed.
- **Phase 5 — Submission & Leaderboard Tracking:** submit a validated `submission.csv` via the Kaggle CLI, record the LB score with provenance, compute/trend the CV→LB gap with a divergence alarm, and gate submissions on CV improvement within a UTC-aware daily budget.
