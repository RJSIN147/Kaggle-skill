# Walking Skeleton — Kaggle Experimentation Framework

**Phase:** 1
**Generated:** 2026-07-09

## Capability Proven End-to-End

Running `init` on an empty folder produces a valid, git-tracked experiment workspace (control-plane + human docs + `.gitignore` + git repo on `main` with a scanned initial commit) whose Kaggle credential is validated with a live API call (clear pass/fail + per-failure remediation) and whose network egress is scoped by a deny-by-default allowlist in the workspace `.claude/settings.json`.

This IS the whole of Phase 1: the framework's walking skeleton is "empty folder → secure, ready workspace" — the foundation every later slice (competition context, experiment loop, kernels, submission) builds on without renegotiating it.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Delivery form | A Claude Code **skill** (`SKILL.md` + `scripts/` + `references/` at the repo root) that scaffolds and then operates on the user's cwd competition folder | Native to Claude Code, portable to other agents; the skill package is separate from the workspace it creates |
| Scaffolder | Self-locating **stdlib-only** Python (`scripts/init_workspace.py`), `Path(__file__)` for templates, explicit `--workspace` arg | CLAUDE.md portability constraint — no reliance on `${CLAUDE_SKILL_DIR}`/`${CLAUDE_PROJECT_DIR}`; ports to opencode/other agents |
| Init interaction | **Guided-then-scaffold** (D-01): SKILL asks slug + execution target, confirms, THEN runs the scaffolder | Nothing created before the user answers |
| Idempotency | **Safe-merge** (D-02): create-if-absent for files, deep-merge for control-plane JSON; only `--set-execution-target` may overwrite one key | `init` is a re-runnable repair/top-up tool |
| Workspace layout (D-10) | Human docs at root (`competition.md`, `strategy.md`, `README.md`); machine state under `control/`; `data/`; `experiments/exp-NNN/` | Docs read constantly by user+AI; machine state tucked away |
| Control-plane formats | `control/config.json` (workspace_version, competition_slug, `execution_target` enum, cv, created); `control/state.json` (credentials, next_exp_id); `control/ledger.jsonl` (append-only, one experiment/line) | JSON for small structured state; JSONL for append-heavy, diff-friendly history (CLAUDE.md ledger decision) |
| Execution target (SETUP-02) | Enum `local` (default) \| `kernel` in config.json; changed via `--set-execution-target`; Phase 1 owns the GLOBAL default only | Fast local iteration by default; per-experiment override deferred to Phase 3 |
| Experiment ids (D-11) | Zero-padded sequential `exp-NNN`; `state.json.next_exp_id` is the cursor | Sorts lexically; matches CLAUDE.md convention |
| Credential model (D-04/D-05) | **Env vars canonical** (`KAGGLE_USERNAME`/`KAGGLE_KEY` or `KAGGLE_API_TOKEN`), persisted in a **gitignored workspace `.env`**; other sources (`kaggle.json`, `access_token`) detected and normalized toward env vars with consent | Aligns with kaggle CLI 2.x precedence (env beats file); nothing scattered in home/shell; cross-session persistence |
| Live credential validation | `kaggle competitions list` — authenticated call, **exit-code-based**, prints no secret; `kaggle config view` is local-only and NOT used as the validator | Only a real network call confirms the credential works |
| Credential-failure posture (D-07) | **Scaffold-anyway-flag-creds**: on failure the workspace stands, `state.json.credentials=UNVALIDATED`, remediation printed; only credential-dependent ops blocked downstream | Useful offline; re-run clears the flag |
| Egress enforcement (D-08/D-09) | Workspace `.claude/settings.json` **`sandbox.network.allowedDomains`** (OS-level bubblewrap+socat proxy over ALL Bash subprocesses) — NOT `permissions.allow: WebFetch(...)`, which governs only Claude's own WebFetch tool | The sandbox block is the only layer that constrains the `kaggle`/`uv`/`git` CLIs; WebFetch permission is a documented second layer |
| Allowlist hosts (D-08) | `www.kaggle.com`, `kaggle.com`, **`storage.googleapis.com`** (+ `*.`), `pypi.org`, `files.pythonhosted.org`, `github.com`, `raw.githubusercontent.com`, `codeload.github.com`, conda channels. Hugging Face / model CDNs EXCLUDED | GCS backend is mandatory or `kaggle competitions download` silently breaks (302 to signed GCS URLs); model CDNs added in Phase 4 when weights are needed |
| Leak guard (D-15) | Defense in depth: `.gitignore` asserts secret coverage AND a **stdlib regex pre-commit scanner** (`scripts/leak_scan.py`) wired via `git config core.hooksPath .githooks` (tracked, portable) — NOT `detect-secrets`/`pre-commit` framework | Standalone + stdlib-only + portable; initial commit made AFTER hook install so the baseline is itself scanned |
| Git track vs ignore (D-12/D-13) | **Track:** `control/`, docs, experiment code, `meta.json`. **Ignore:** `.env`, `kaggle.json`, `access_token`, `data/`, model artifacts, `__pycache__/`, `.venv/`, and Phase 3 artifact patterns under `experiments/*/` (declared now) | Diffable code+ledger history; secrets and heavy artifacts never committed; `.gitignore` not rewritten later |
| Python env (D-14) | Minimal `pyproject.toml` stub in the workspace (Python ≥3.11 floor, uv config); full ML deps declared in Phase 3. Skill's OWN scripts stay stdlib-only | Env contract exists without pinning ML versions before they are exercised |
| Test framework | pytest with a `live` marker in the skill's `pyproject.toml`; Nyquist per-task sampling per `01-VALIDATION.md` | Machine-verifiable acceptance; live credential test gated behind `-m live` |

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
