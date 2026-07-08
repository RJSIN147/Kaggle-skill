# Phase 1: Workspace, Credentials & Egress Guardrails - Context

**Gathered:** 2026-07-09
**Status:** Ready for planning

<domain>
## Phase Boundary

A single `init` (invoked as a skill in Claude Code, backed by a scaffolder script) turns an empty
folder into a valid, git-tracked experiment **workspace** with:
- the full workspace layout (control-plane `config.json`/`state.json`/`ledger.jsonl`, context-file
  stubs, `.gitignore`, `.env` stub, initialized git repo);
- an execution-target setting (local default / kernel) recorded in `config.json`, changeable later;
- a live-validated Kaggle credential connection with clear pass/fail and per-failure remediation;
- secure credential handling (never echoed/committed; leak check); and
- a deny-by-default network egress allowlist.

**The workspace IS the user's competition folder** (the skill is installed globally and operates on
the cwd). The skill package is separate from the workspace it scaffolds.

**In scope:** SETUP-01, SETUP-02, SETUP-03, SETUP-04 — workspace scaffold, execution-target
selection, credential connect+validate, credential security + egress scoping.

**Explicitly NOT in this phase (boundary guards):**
- `init` records the competition **slug** into `config.json`, but capturing the competition
  "constitution" (`competition.md`: metric, schema, rules, CV scheme) and **downloading data** are
  Phase 2 (COMP-01/02/03). Phase 1 only writes an empty `competition.md` stub.
- The full ML dependency list and the local runner are Phase 3. Phase 1 lays only a minimal
  `pyproject.toml` stub.
- The **per-experiment** execution-target override mechanism is a Phase 3 detail (experiments don't
  exist yet). Phase 1 owns only the **global** default in `config.json`.
</domain>

<decisions>
## Implementation Decisions

### Init interaction model
- **D-01:** **Guided, then scaffold.** `init` first asks the few key choices (competition slug,
  execution target), confirms, and only THEN scaffolds. Nothing is created until the user has
  answered. (Not scaffold-first, not a flags-only one-shot.)
- **D-02:** **Safe-merge on a non-empty folder.** `init` only creates files that don't already
  exist; it never overwrites. This makes `init` idempotent and re-runnable to repair/top-up a
  partial workspace. (Not "refuse unless forced"; not "refuse on conflict".)

### Credential posture
- **D-03:** **Auto-fix with consent.** When the check finds a fixable problem, show the EXACT fix
  and apply only after the user confirms — never silent. Honors CLAUDE.md's "no silent environment
  mutation" posture. (Silent auto-fix is rejected.)
- **D-04:** **Env vars are canonical** — `KAGGLE_USERNAME`/`KAGGLE_KEY` (or `KAGGLE_API_TOKEN`).
  The skill detects other sources (`kaggle.json`, `access_token`) and maps/normalizes toward env
  vars rather than treating them as the source of truth.
- **D-05:** **Canonical env vars persist in a gitignored workspace `.env`.** `init` writes a `.env`
  **stub** (placeholder keys, no real values); the runner sources `.env` to set `KAGGLE_*` per run.
  This reconciles "env vars canonical" + "nothing scattered in home/shell" + cross-session
  persistence, and matches SETUP-04's `.env` mention.
- **D-06 (reconciliation):** With env vars canonical, the "auto-fix with consent" surface is:
  (a) if a fallback `kaggle.json` exists and isn't `chmod 600`, offer to chmod it; (b) if a
  `kaggle.json` exists but `.env`/env vars are unset, offer (with consent) to populate `.env` from
  it; (c) if nothing is set, instruct how to set the env vars / fill `.env`. The skill still
  validates whatever the CLI can use (env vars OR a `kaggle.json`), but recommends and normalizes
  toward env vars in `.env`.

### Credential-failure behavior at init
- **D-07:** **Scaffold anyway, flag creds.** If the live validation FAILS, `init` still completes
  the workspace scaffold (useful offline), records credential status as **UNVALIDATED** (in
  `state.json` / init output), and prints exact remediation. Only credential-dependent operations
  (data download, submit) are blocked downstream. Re-running `init` (safe-merge) or a validate step
  after fixing clears the flag. (Not "abort until valid".)

### Egress allowlist breadth
- **D-08:** **Standard package sources** on the default allowlist:
  `kaggle.com` / `www.kaggle.com` + **Kaggle's GCS data backend** (`storage.googleapis.com`) +
  PyPI (`pypi.org`, `files.pythonhosted.org`) + `github.com` / `raw.githubusercontent.com` +
  conda channels. **Model CDNs (Hugging Face) are deliberately NOT included by default** — they get
  added explicitly when the Phase 4 GPU/DL path needs weights.
  - **Gotcha (must not be lost):** Kaggle data downloads redirect to Google Cloud Storage. An
    allowlist of just `kaggle.com` silently breaks `kaggle competitions download`. The GCS backend
    host is mandatory in the minimal working set.
- **D-09:** **Written to workspace settings + documented.** `init` writes/merges the allowlist into
  the **workspace** `.claude/settings.json` (concrete deny-by-default enforcement in Claude Code —
  off-allowlist fetch refused, per success criterion 5) AND documents the egress requirement in a
  reference doc so an opencode/other-runtime port can reproduce it. (Not shipped inside the skill
  package; not workspace-only-undocumented.)

### Workspace layout & naming
- **D-10:** **Docs at root, control-plane tucked away.** Target layout:
  ```
  workspace/
    competition.md   strategy.md   README.md      # human docs, at root, tracked
    .gitignore   .env                              # .env gitignored
    .claude/settings.json                          # egress allowlist
    pyproject.toml                                 # minimal stub (D-14)
    control/
      config.json  state.json  ledger.jsonl        # machine control-plane, tracked
    data/                                          # gitignored (D-13)
    experiments/
      exp-001/                                     # per-experiment (Phase 3+)
  ```
  Human-readable docs live at root (read constantly by user + AI); machine state lives under
  `control/`. (Not flat-root; not everything-under-one-hidden-dir.)
- **D-11:** **Zero-padded sequential experiment ids** — `exp-001`, `exp-002`, …; ledger id =
  `exp-NNN`. Sorts lexically, matches the CLAUDE.md convention. (Not slug-suffixed; not
  date-prefixed.)

### Git tracks vs. ignores
- **D-12:** **Track code + ledger + docs; ignore data + heavy artifacts.**
  - **Tracked:** `control/` (config.json, state.json, ledger.jsonl), the docs, experiment
    code/notebooks, per-experiment `meta.json` (Phase 3).
  - **Ignored:** secrets (`.env`, `kaggle.json`, `access_token`), `data/`, large model artifacts,
    `__pycache__/`, `.venv/`.
- **D-13:** `.gitignore` is written in Phase 1 but must **anticipate Phase 3 experiment artifacts**
  so it isn't rewritten later (ignore artifact patterns under `experiments/*/` now).

### Python env scaffolding
- **D-14:** **Minimal `pyproject.toml` stub now.** `init` writes a bare `pyproject.toml` (project
  metadata, Python **≥3.11** floor, uv config) so the env contract exists. The full ML dependency
  list (lightgbm/sklearn/pandas/…) is declared in **Phase 3** when the loop needs it, to avoid
  pinning versions before they're exercised. The skill's OWN scripts remain stdlib-only.

### Leak-check strength
- **D-15:** **Defense in depth — `.gitignore` assertion + pre-commit content scan.** The leak check
  (success criterion 4) both (a) verifies `.gitignore` covers the secret files AND (b) installs a
  **pre-commit guard** that scans staged content for credential/token patterns (Kaggle key regex,
  `KAGGLE_KEY=`, etc.) and blocks the commit on a hit.

### Claude's Discretion
- **Initial commit:** `init` makes one initial commit `chore: scaffold workspace` **after** the
  pre-commit guard is installed, so the baseline is itself scanned. (Flagged as discretion — adjust
  if planning finds a reason not to auto-commit.)
- Git init specifics (default branch name, whether to set `user`/`email` locally) — planner/executor
  discretion; not user-facing.
- The exact live-validation command (`kaggle competitions list` vs `kaggle config view`) — a
  researcher/planner choice; must be exit-code-based and must not leak secrets to stdout.
- Exact allowlist host syntax/format for `.claude/settings.json` — researcher to verify against the
  current Claude Code settings schema.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent, scope, and success criteria
- `.planning/ROADMAP.md` §"Phase 1" — the fixed phase goal, 5 success criteria, and the two
  suggested plans (01-01 skill skeleton/egress/credentials; 01-02 workspace scaffolder/config).
- `.planning/REQUIREMENTS.md` §Setup — SETUP-01..04, the authoritative requirement text.
- `.planning/PROJECT.md` §Constraints, §Key Decisions — standalone (no shepsci dependency),
  local-first default, git-backed ledger, security posture.

### Technology stack, skill authoring, and Kaggle command surface (MANDATORY)
- `CLAUDE.md` — the full prescriptive stack. Specifically relevant to Phase 1:
  - §"Skill Authoring Reference" — SKILL.md frontmatter, `allowed-tools`
    (`Bash(kaggle *) Bash(uv run *) Bash(git *) Read Write Edit`), 1,536-char description cap,
    progressive disclosure, `${CLAUDE_SKILL_DIR}`, directory shape.
  - §"Kaggle Integration — Concrete Command Surface" — credential sources
    (`kaggle.json` / `access_token` / env vars), `chmod 600`, cheap validation calls, token origin.
  - §"Egress scoping", §"Stack Patterns by Variant" (portability note: scripts self-locate via
    `Path(__file__)`, accept explicit `--workspace`; document egress rather than hard-wiring).
  - §"What NOT to Use" — no silent `pip install`, no credential echo/commit, `enable_internet:false`
    default on kernels.

### External structure-only exemplar (NOT a dependency — do not import or couple to it)
- `~/.claude/plugins/cache/shepsci/kaggle-skill/2.3.0/` — study for structure/command-surface only:
  `.claude/settings.json` egress allowlist shape, `check_credentials.py`, `cli_*.sh`,
  `pyproject.toml`, SKILL.md layout. Reimplement independently; PROJECT.md forbids depending on it.

No user-referenced ADRs/specs surfaced during discussion beyond the above.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **None in this repo** — greenfield. Repo currently holds only `CLAUDE.md`, `.planning/`,
  `README.md`, and `.claude/settings.local.json`. Phase 1 creates the first framework code.

### Established Patterns
- **CLAUDE.md is the pattern authority** for this project (stack, versions, skill authoring,
  security posture). Treat it as the de-facto conventions doc until code-level conventions emerge.
- **Portability constraint (from CLAUDE.md):** helper scripts must self-locate (`Path(__file__)`),
  take an explicit `--workspace` path rather than relying on `${CLAUDE_SKILL_DIR}`/
  `${CLAUDE_PROJECT_DIR}`, and be stdlib-only. Bash only for genuine one-line CLI pipes; anything
  with loops/timeouts/JSON parsing/error handling → Python.

### Integration Points
- `.claude/settings.json` in the **workspace** — where the egress allowlist is enforced (distinct
  from the existing `.claude/settings.local.json` in the skill-dev repo).
- `config.json` execution-target field — must be honored by whatever runner exists; the runner
  itself arrives in Phase 3 (local) / Phase 4 (kernel).
</code_context>

<specifics>
## Specific Ideas

- The layout preview in D-10 is the concrete target the user selected (docs at root, `control/`
  subdir, `data/`, `experiments/exp-001/`).
- Egress GCS-backend gotcha (D-08) is a hard, non-obvious requirement — the researcher should verify
  the exact GCS host(s) Kaggle downloads currently redirect to.
</specifics>

<deferred>
## Deferred Ideas

- **Hugging Face / model-CDN egress hosts** — add to the allowlist deliberately when the Phase 4
  GPU/DL path needs model weights. Not in the Phase 1 default.
- **Per-experiment execution-target override** — the mechanism for overriding the global target on a
  single experiment belongs in Phase 3 (experiments don't exist until then). Phase 1 only sets the
  global default in `config.json`.
- **Full ML dependency declaration + `uv.lock`** — Phase 3, alongside the local runner (D-14).

None of the above are scope creep — they are correctly-scoped later-phase work surfaced during
discussion so they aren't lost.
</deferred>

---

*Phase: 1-Workspace, Credentials & Egress Guardrails*
*Context gathered: 2026-07-09*
