# Phase 1: Workspace, Credentials & Egress Guardrails - Research

**Researched:** 2026-07-09
**Domain:** Claude Code Skill scaffolding + Kaggle CLI 2.x credential handling + OS-level network-egress sandboxing + git hygiene/leak-guards
**Confidence:** MEDIUM-HIGH (egress mechanism HIGH; Kaggle exit-code specifics MEDIUM — `kaggle` CLI not installed locally so no live exit-code observation)

## Summary

The single most consequential finding for this phase corrects the exemplar: **Claude Code enforces network egress for shell subprocesses (`kaggle`, `uv`, `pip`, `git`) through `sandbox.network.allowedDomains`, NOT through `permissions.allow: WebFetch(domain:…)`.** The `WebFetch(domain:…)` permission rule governs only Claude's own WebFetch *tool*; it does nothing to constrain what the `kaggle` CLI can reach. The shepsci exemplar's `.claude/settings.json` uses only the `WebFetch` permission form — copying it verbatim would produce a workspace that *looks* egress-scoped but actually leaves the CLI's network wide open. Success criterion 5 ("off-allowlist fetch refused, not silently allowed") is satisfied by the sandbox layer, so Phase 1 must write a `sandbox` block. `[VERIFIED: code.claude.com/docs/en/sandboxing]`

Second: the phase is almost entirely **stdlib-Python + bash-glue + JSON/TOML files** — no external runtime dependency except the `kaggle` CLI itself, and even that is deferred by D-07 (scaffold-anyway-flag-creds). Credential handling maps cleanly onto the CLI 2.x precedence (env vars beat `kaggle.json`), which validates D-04's "env vars canonical." The exemplar's `check_all_credentials.py` and `setup_env.sh` are excellent *structure* references (token-type detection, chmod-600 self-heal, masked output, priority-ordered source detection) and should be reimplemented independently.

Third: two live environment gaps materially shape the plan. `kaggle` CLI is **not installed** on this machine (the "command-not-found" remediation branch of success criterion 3 is a real, reachable path — and it means no live exit-code verification was possible). `socat` is **not installed** — on Linux the sandbox network proxy requires both `bubblewrap` (present) *and* `socat` (missing); without `socat` the sandbox silently falls back to unsandboxed execution and egress is NOT enforced. Both need explicit handling.

**Primary recommendation:** Write a `sandbox.network.allowedDomains` allowlist (plus `sandbox.enabled: true`) as the real egress control, keep the `WebFetch(domain:…)` permission rules as a complementary second layer for Claude's own fetches, document the allowlist in a portability reference doc (D-09), detect+instruct (never silently install) for both `kaggle` and `socat`, and implement all guards as self-locating stdlib-Python scripts driven by a `--workspace` argument.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (build ON these — do not re-litigate)
- **D-01** Guided-then-scaffold: ask slug + execution target, confirm, THEN create. Nothing created before answers.
- **D-02** Safe-merge on non-empty folder: only create files that don't exist; never overwrite. `init` is idempotent/re-runnable.
- **D-03** Auto-fix with consent: show exact fix, apply only after user confirms. No silent mutation.
- **D-04** Env vars canonical (`KAGGLE_USERNAME`/`KAGGLE_KEY` or `KAGGLE_API_TOKEN`); detect other sources and normalize toward env vars.
- **D-05** Canonical env vars persist in a gitignored workspace `.env`; `init` writes a `.env` **stub** (placeholders, no real values); the runner sources `.env` per run.
- **D-06** Auto-fix surface: (a) chmod 600 a fallback `kaggle.json`; (b) offer to populate `.env` from `kaggle.json`; (c) instruct if nothing set. Validate whatever the CLI can use; recommend env-vars-in-`.env`.
- **D-07** Scaffold-anyway-flag-creds: if live validation FAILS, still complete scaffold, record credential status UNVALIDATED, print remediation. Only credential-dependent ops blocked downstream. Re-run clears the flag.
- **D-08** Default allowlist = `kaggle.com`/`www.kaggle.com` + Kaggle GCS backend (`storage.googleapis.com`) + PyPI (`pypi.org`, `files.pythonhosted.org`) + `github.com`/`raw.githubusercontent.com` + conda channels. **Hugging Face deliberately excluded** (Phase 4). GCS host is mandatory or downloads silently break.
- **D-09** Write/merge allowlist into **workspace** `.claude/settings.json` (concrete deny-by-default) AND document it in a reference doc for opencode/other-runtime portability.
- **D-10** Layout: docs at root (`competition.md`, `strategy.md`, `README.md`), `.gitignore`, `.env`, `.claude/settings.json`, `pyproject.toml`; machine control-plane under `control/` (`config.json`, `state.json`, `ledger.jsonl`); `data/`; `experiments/exp-001/`.
- **D-11** Zero-padded sequential experiment ids `exp-NNN`.
- **D-12** Track code+ledger+docs (`control/`, docs, experiment code, `meta.json`); ignore secrets (`.env`, `kaggle.json`, `access_token`), `data/`, model artifacts, `__pycache__/`, `.venv/`.
- **D-13** `.gitignore` written now must anticipate Phase 3 experiment artifacts (ignore artifact patterns under `experiments/*/` now, don't rewrite later).
- **D-14** Minimal `pyproject.toml` stub now (metadata, Python ≥3.11 floor, uv config). Full ML deps deferred to Phase 3. Skill's own scripts stay stdlib-only.
- **D-15** Defense in depth: (a) assert `.gitignore` covers secret files AND (b) install a pre-commit content-scan guard (Kaggle key/token regexes) that blocks commits on a hit.

### Claude's Discretion
- Initial commit `chore: scaffold workspace` **after** the pre-commit guard is installed (so the baseline is itself scanned). Adjust if planning finds a reason not to auto-commit.
- Git init specifics (default branch name, whether to set local `user`/`email`) — planner/executor discretion.
- Exact live-validation command (`kaggle competitions list` vs `kaggle config view`) — researcher/planner choice; must be exit-code-based, must not leak secrets. **→ Resolved in this doc: use `kaggle competitions list`.**
- Exact allowlist host syntax/format for `.claude/settings.json` — researcher to verify. **→ Resolved in this doc: `sandbox.network.allowedDomains` array of bare hostnames + `*.` wildcards.**

### Deferred Ideas (OUT OF SCOPE for Phase 1)
- Hugging Face / model-CDN egress hosts (Phase 4).
- Per-experiment execution-target override (Phase 3).
- Full ML dependency declaration + `uv.lock` (Phase 3).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETUP-01 | Initialize workspace in empty folder (layout, config, git init, context stubs) | Layout is D-10; scaffolder is a self-locating stdlib `init_workspace.py --workspace`; safe-merge (D-02) via per-file "create-if-absent"; `git init` (set `-b main`); `.gitignore` from D-12/D-13. See Architecture Patterns / Code Examples. |
| SETUP-02 | Choose execution target (local default / kernel) at init; changeable later | `config.json` `execution_target` field (enum `local`/`kernel`, default `local`). Phase 1 owns the global default only; per-experiment override is Phase 3 (deferred). Guided prompt (D-01) captures it. See config.json schema. |
| SETUP-03 | Connect Kaggle account via CLI; validate with a live call, clear pass/fail + per-failure remediation | CLI 2.x credential precedence + `kaggle competitions list` as exit-code live-validator + four remediation branches (wrong env var, missing chmod 600, 401, command-not-found). D-07 flag-on-fail. See Credential Validation section. |
| SETUP-04 | Store credentials securely, never echoed; egress scoped to Kaggle + package sources | chmod 600 + never-echo (masking + no-echo test) + `.gitignore` covers secrets + pre-commit content scan (D-15) + `sandbox.network.allowedDomains` egress (D-08/D-09). See Egress and Leak-Guard sections. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Workspace scaffold (dirs, files, git init) | Skill script (stdlib Python, `--workspace`) | SKILL.md orchestration | Deterministic filesystem work with loops/JSON → Python, not bash (CLAUDE.md rule). |
| Guided prompts (slug, target) + consent gates | SKILL.md (agent) | Skill script | Interaction is the agent's job; the script consumes already-decided values as args/flags. |
| Credential detection + normalization + chmod | Skill script (stdlib Python) | — | Priority-ordered source detection, masking, self-heal chmod — logic-heavy → Python. |
| Live credential validation | `kaggle` CLI (via bash one-liner) | Skill script (parse exit code) | The live call is a single CLI invocation; exit code is the signal. |
| Network egress enforcement | Claude Code **sandbox** (OS-level proxy) | `.claude/settings.json` `sandbox` block | Enforced by bubblewrap+socat proxy on all Bash child processes — the only layer that constrains the `kaggle` CLI. |
| Claude WebFetch scoping | `.claude/settings.json` `permissions` | — | Governs Claude's own WebFetch tool only; complementary, not the CLI egress control. |
| Leak prevention | git (`.gitignore` + `core.hooksPath` pre-commit) | Skill script (regex scan) | git is the enforcement point; the scan is stdlib regex over staged content. |
| Egress portability doc | Reference markdown (D-09) | — | So an opencode/other-runtime port can reproduce the allowlist without Claude-Code settings. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`json`, `os`, `pathlib`, `re`, `subprocess`, `argparse`, `stat`, `tomllib`) | 3.11+ (3.12.3 present) | All skill scripts | CLAUDE.md mandates stdlib-only for the skill's own scripts. `tomllib` is read-only (3.11+); for *writing* `pyproject.toml` emit text (no stdlib TOML writer). `[CITED: CLAUDE.md §Stack Patterns]` |
| `kaggle` CLI | 2.2.3 (GA; requires Python ≥3.11) | Live credential validation only in Phase 1 | The single Kaggle integration primitive (CLAUDE.md). NOT installed locally → command-not-found path is live. `[CITED: CLAUDE.md]` `[ASSUMED: version 2.2.3 — from CLAUDE.md prior research; not re-verified this session]` |
| `git` | 2.43.0 (present) | `git init`, `.gitignore`, `core.hooksPath` pre-commit | `core.hooksPath` supported since git 2.9. `[VERIFIED: git --version]` |
| `uv` | 0.11.14 (present) | Env/dependency management; `pyproject.toml` consumer | CLAUDE.md standard. Phase 1 only writes a stub `pyproject.toml`. `[VERIFIED: uv --version]` |

### Supporting (dev/test only — NOT runtime deps)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | ≥8.0 | Validation tests (see Validation Architecture) | NOT installed → Wave 0 install via `uv`. `[ASSUMED]` |
| `ruff` | ≥0.8 | Lint/format skill Python | NOT installed; optional for Phase 1. `[ASSUMED]` |

### Deliberately NOT used in Phase 1
| Rejected | Why | Use Instead |
|----------|-----|-------------|
| `python-dotenv` | External dep; violates stdlib-only. D-05's runner sources `.env` in **bash** (`set -a; source .env; set +a`), not Python. | Bash `source` for `.env`; stdlib `os.environ` in Python. |
| `detect-secrets` + `pre-commit` framework (exemplar's `.pre-commit-config.yaml`) | External deps + framework install; violates standalone/stdlib/portability constraints (D-15 wants a portable guard). | Stdlib-Python regex scanner wired via `git config core.hooksPath`. |
| `permissions.allow: WebFetch(domain:…)` as the egress control | Governs only Claude's WebFetch tool, not the `kaggle` CLI subprocess. Would give false confidence. | `sandbox.network.allowedDomains` (primary) + keep WebFetch rules as a second layer. |
| `api.kaggle.com` in the allowlist | CLI 2.x default endpoint is `https://www.kaggle.com/api/v1`, not `api.kaggle.com` (exemplar's host is stale for the CLI). | `www.kaggle.com`. |

**Installation (Phase 1 needs only these; ML stack is Phase 3 / D-14):**
```bash
# Runtime (only for the credential-validation step; D-07 lets scaffold proceed without it)
uv pip install kaggle            # or: pip install --user kaggle   (NEVER silent — instruct, get consent)
# Dev/test
uv pip install pytest ruff
# Sandbox network proxy dependency (Linux) — see Environment Availability
sudo apt-get install socat       # bubblewrap already present
```

**Version verification note:** `pip index versions` returned no output in this session (no package-registry network from the research sandbox), and the `kaggle` CLI is not installed, so versions below are carried from CLAUDE.md's 2026-07-09 registry check, not re-verified here. The planner should re-confirm `kaggle` on PyPI at implementation time.

## Package Legitimacy Audit

> slopcheck could not be installed in this session (no network to the package registry). Per the graceful-degradation rule, packages are tagged `[ASSUMED]` and the planner should gate each install behind a `checkpoint:human-verify` task. Note: all three are canonical, authoritatively-sourced packages (Kaggle's own CLI, pytest, astral-sh/ruff) previously version-verified in CLAUDE.md — the checkpoint is a formality, not a red flag.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `kaggle` | PyPI | ~8 yrs | very high | github.com/Kaggle/kaggle-cli | unavailable | Approved (gate: human-verify) |
| `pytest` | PyPI | ~15 yrs | very high | github.com/pytest-dev/pytest | unavailable | Approved (gate: human-verify) |
| `ruff` | PyPI | ~3 yrs | very high | github.com/astral-sh/ruff | unavailable | Approved (gate: human-verify) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    user runs skill in an empty (or partial) competition folder
                                          │
                                          ▼
                    ┌──────────────────────────────────────────┐
                    │  SKILL.md (agent orchestration)            │
                    │  D-01 guided prompts: slug, exec target     │
                    │  D-03 consent gates for any fix             │
                    └───────────────┬─────────────┬──────────────┘
                                    │             │
              (confirmed values)   │             │  (consent to fix)
                                    ▼             ▼
        ┌───────────────────────────────┐   ┌──────────────────────────────────┐
        │ init_workspace.py --workspace  │   │ check_credentials.py --workspace  │
        │ (stdlib, self-locating)        │   │ (stdlib, self-locating)           │
        │  • safe-merge create-if-absent │   │  • detect source (env>json>token) │
        │  • control/{config,state,ledgr}│   │  • chmod 600 self-heal (consent)  │
        │  • docs stubs, .env stub       │   │  • normalize → .env (consent)     │
        │  • .gitignore (D-12/13)        │   │  • mask output, never echo        │
        │  • .claude/settings.json (D-09)│   └───────────────┬───────────────────┘
        │  • pyproject.toml stub (D-14)  │                   │ exit code
        │  • git init -b main            │                   ▼
        │  • core.hooksPath pre-commit   │        ┌────────────────────────────┐
        └───────────────┬────────────────┘        │ kaggle competitions list    │
                        │                          │ (live call → www.kaggle.com)│
                        ▼                          │ exit 0 = valid / ≠0 = fail  │
        ┌───────────────────────────────┐         └───────────────┬─────────────┘
        │ git commit chore: scaffold      │                        │
        │ (pre-commit scan runs on it)    │        pass │          │ fail (D-07)
        └────────────────────────────────┘             ▼          ▼
                                              state.json:      state.json:
                                              creds=VALIDATED  creds=UNVALIDATED
                                                               + remediation printed
                                          │
   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
   OS-level egress boundary (Claude Code sandbox proxy: bubblewrap + socat)
   sandbox.network.allowedDomains gates ALL Bash child processes (kaggle, uv, pip, git):
       www.kaggle.com · storage.googleapis.com · pypi.org · files.pythonhosted.org
       · github.com · raw.githubusercontent.com · conda channels   → off-list = refused/prompt
```

### Recommended Project Structure (the SKILL package, not the scaffolded workspace)

```
kaggle-exp-skill/                 # the skill package (separate from the workspace it creates)
├── SKILL.md                      # frontmatter + lean body (<500 lines), points to scripts/refs
├── scripts/
│   ├── init_workspace.py         # SETUP-01/02: scaffolder (stdlib, --workspace)
│   ├── check_credentials.py      # SETUP-03: detect/normalize/validate creds (stdlib, --workspace)
│   ├── leak_scan.py              # SETUP-04: pre-commit content scanner (stdlib; also the hook target)
│   └── templates/                # text templates copied into the workspace
│       ├── gitignore.tmpl        # D-12/D-13 (anticipates Phase 3 artifacts)
│       ├── settings.json.tmpl    # D-09 sandbox + permissions
│       ├── config.json.tmpl      # D-10 control-plane schema (execution_target)
│       ├── pyproject.toml.tmpl   # D-14 minimal stub
│       └── *.md.tmpl             # competition/strategy/README stubs
└── references/
    └── egress-allowlist.md       # D-09 portability doc (hosts + why + non-Claude reproduction)
```

### Pattern 1: Self-locating, `--workspace`-driven stdlib script
**What:** Every script resolves its own dir via `Path(__file__)` for template access and takes `--workspace` for its target, never relying on `${CLAUDE_SKILL_DIR}`/`${CLAUDE_PROJECT_DIR}`.
**When to use:** All Phase 1 scripts (portability constraint).
```python
# Source: pattern derived from CLAUDE.md §"Stack Patterns by Variant" portability note
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES = SCRIPT_DIR / "templates"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path.cwd())
    args = ap.parse_args()
    ws = args.workspace.resolve()
    ...
```

### Pattern 2: Safe-merge create-if-absent (D-02, idempotent `init`)
**What:** Never overwrite; only create missing files. Makes `init` a repair/top-up tool.
```python
def create_if_absent(path: Path, content: str) -> str:
    if path.exists():
        return "skip"            # existing files are never clobbered
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return "create"
# For JSON control-plane files, prefer a deep-merge that adds missing keys
# without discarding user edits, so re-running init tops up a partial config.
```

### Pattern 3: Egress via sandbox (the correct D-09 enforcement)
**What:** `.claude/settings.json` carries a `sandbox` block (real CLI egress) plus `permissions` (Claude's WebFetch). See Code Examples for the full file.

### Anti-Patterns to Avoid
- **Egress via WebFetch permissions only** (exemplar's approach): does not constrain the `kaggle` CLI. Use `sandbox.network.allowedDomains`.
- **Allowlisting `kaggle.com` without `storage.googleapis.com`** (D-08 gotcha): `kaggle competitions download` 302-redirects to signed GCS URLs; downloads silently fail. GCS host is mandatory.
- **`echo`/`print` of any credential value**: mask (first-5 + last-4) or reference the env-var *name* only. A no-echo regex test enforces this.
- **Silent `pip install`** of `kaggle`/`socat`: detect, print the exact command, act only on consent (D-03, CLAUDE.md §What NOT to Use).
- **Assuming sandbox is enforcing** when `socat` is missing on Linux: it silently degrades to unsandboxed. Detect and warn.
- **`git init` leaving default branch `master`**: git 2.43 defaults to `master`; use `git init -b main` (discretion, but be explicit).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Network egress enforcement | A custom proxy / iptables / DNS filter | Claude Code `sandbox.network.allowedDomains` | OS-level (bubblewrap+socat), covers all child processes, already built in. `[VERIFIED: docs]` |
| Kaggle auth resolution | Re-parsing tokens / re-implementing precedence | The `kaggle` CLI's own precedence + a thin detector | CLI already resolves access_token→env→kaggle.json→OAuth; only *detect+normalize+validate*, don't re-auth. |
| TOML reading | Hand-parse | stdlib `tomllib` (read) | 3.11+ stdlib. (Writing = emit templated text; no stdlib writer.) |
| Secret scanning framework | Adopt `detect-secrets`/`pre-commit` | Stdlib regex scanner on `git diff --cached` via `core.hooksPath` | Standalone + portable (D-15); no external deps. |
| Credential masking | Ad-hoc slicing everywhere | One `_mask(value, prefix_len)` helper | Consistent, testable, matches exemplar. |

**Key insight:** The whole phase is "wire up primitives that already exist" (sandbox, git hooks, kaggle CLI) with thin stdlib glue — the failure mode is *choosing the wrong primitive* (WebFetch vs sandbox), not building too little.

## Common Pitfalls

### Pitfall 1: WebFetch-permission egress theater
**What goes wrong:** Workspace ships `permissions.allow: WebFetch(domain:kaggle.com)` and the team believes egress is scoped; the `kaggle` CLI still reaches anywhere.
**Why it happens:** The shepsci exemplar (the study reference) uses exactly this shape; it predates/ignores the sandbox network layer.
**How to avoid:** Put the real allowlist in `sandbox.network.allowedDomains` with `sandbox.enabled: true`. Keep WebFetch rules as a documented second layer only.
**Warning signs:** An off-allowlist `curl`/`kaggle` call succeeds without a prompt while sandbox is "configured."

### Pitfall 2: Missing GCS host breaks downloads later (D-08)
**What goes wrong:** Phase 2 `kaggle competitions download` fails with connection/redirect errors though `kaggle.com` is allowlisted.
**Why it happens:** Competition data is served via signed `storage.googleapis.com/<bucket>/…` URLs (path-style). `[VERIFIED: multiple sources incl. GH Kaggle/kaggle-cli issues]`
**How to avoid:** Include `storage.googleapis.com` now; also add `*.storage.googleapis.com` to cover any virtual-hosted-style variant.
**Warning signs:** `MaxRetryError`/`SSL`/timeout to `storage.googleapis.com:443` in a Phase-2 download.

### Pitfall 3: Sandbox silently disabled (Linux dep missing)
**What goes wrong:** `sandbox.enabled: true` is written but egress isn't enforced.
**Why it happens:** On Linux the proxy needs `bubblewrap` (present) **and** `socat` (MISSING here). If a dep is missing, default behavior is a warning + unsandboxed fallback.
**How to avoid:** Detect `socat`; instruct `sudo apt-get install socat`; consider documenting `sandbox.failIfUnavailable: true` for users who want a hard gate. Verify via `/sandbox` panel or a probe `curl` to an off-list host.
**Warning signs:** No first-domain prompt on the first `kaggle` call; `/doctor` or `/sandbox` shows missing dependency.

### Pitfall 4: TLS not inspected → broad domains are exfil paths
**What goes wrong:** Allowlisting `github.com`/`*.githubusercontent.com` widens the blast radius (domain fronting).
**Why it happens:** The built-in proxy allow-decides on client-supplied hostname without TLS termination (default). `[VERIFIED: docs §Security limitations]`
**How to avoid:** Keep GitHub entries as narrow as the use case allows; document the residual risk in the egress reference; note that hard TLS-aware isolation requires a custom proxy (out of scope).
**Warning signs:** n/a (design-time consideration).

### Pitfall 5: `kaggle` command-not-found treated as a crash
**What goes wrong:** Validation errors out instead of giving the install remediation (success criterion 3 explicitly lists this failure).
**Why it happens:** `kaggle` isn't installed by default (confirmed MISSING here).
**How to avoid:** `command -v kaggle` (or `shutil.which("kaggle")`) *before* the live call; on absence, print the install command and set creds=UNVALIDATED (D-07). Never auto-install.
**Warning signs:** `FileNotFoundError`/`command not found` bubbling up from the validator.

### Pitfall 6: chmod 600 both a security AND a functional requirement
**What goes wrong:** A world/group-readable `~/.kaggle/kaggle.json` triggers a CLI warning/refusal, and is a real leak.
**Why it happens:** The Kaggle CLI checks file mode and warns when the key is readable by others.
**How to avoid:** Self-heal to 600 on detect (with consent per D-03/D-06a); the exemplar's `_ensure_mode_600` is the pattern.
**Warning signs:** "Your Kaggle API key is readable by others" on stderr.

## Code Examples

### `.claude/settings.json` — egress + WebFetch (the D-08/D-09 core artifact)
```jsonc
// Source: composed from code.claude.com/docs/en/sandbox-settings + examples/settings/settings-bash-sandbox.json
// [VERIFIED: docs] for schema; hosts per D-08.
{
  "sandbox": {
    "enabled": true,
    "network": {
      "allowedDomains": [
        "www.kaggle.com",
        "kaggle.com",
        "storage.googleapis.com",
        "*.storage.googleapis.com",
        "pypi.org",
        "files.pythonhosted.org",
        "github.com",
        "raw.githubusercontent.com",
        "codeload.github.com",
        "repo.anaconda.com",
        "conda.anaconda.org"
      ]
    }
  },
  "permissions": {
    "allow": [
      "WebFetch(domain:www.kaggle.com)",
      "WebFetch(domain:kaggle.com)",
      "Bash(kaggle *)",
      "Bash(uv run *)",
      "Bash(git *)"
    ]
  }
}
```
Notes: `allowedDomains` accepts bare hostnames (`pypi.org`) and `*.`-prefixed wildcards (`*.storage.googleapis.com`); a wildcard matches subdomains only, not the apex (include both when both are used). Off-list access **prompts** in a normal project (not silently allowed → satisfies criterion 5); a hard *block* without prompt needs `allowManagedDomainsOnly: true` in **managed** settings (org-level, out of a project file's reach). `[VERIFIED: docs]`

### Live credential validation (exit-code-based, no secret leak)
```bash
# Source: kaggle CLI 2.x default endpoint https://www.kaggle.com/api/v1 [VERIFIED: kaggle docs/GH]
if ! command -v kaggle >/dev/null 2>&1; then
  echo "[UNVALIDATED] kaggle CLI not found. Install:  uv pip install kaggle"   # remediation: command-not-found
  exit 3
fi
# competitions list = authenticated GET to www.kaggle.com/api/v1/competitions/list.
# Prints competition titles (NO secrets); non-zero exit on 401/auth failure.
if kaggle competitions list >/dev/null 2>err.txt; then
  echo "[VALIDATED]"
else
  case "$(cat err.txt)" in
    *401*|*Unauthorized*) echo "[FAIL] 401 — token invalid/expired. Regenerate at kaggle.com/settings" ;;
    *)                    echo "[FAIL] see remediation" ;;
  esac
fi
```
- Do **not** use `kaggle config view` as the *live* validator: it prints local config (`competition`, `path`, `proxy`, and username) and makes **no network call**, so it cannot confirm the credential actually works. Use it only for a "what's configured" non-live check. `[ASSUMED: config view is local-only — inferred from CLI config subcommand semantics; not observed live this session]`
- `kaggle` was not installable/runnable here, so exact exit codes are `[ASSUMED]` (CLI raises → exit 1 on auth failure per general CLI behavior). Confirm live during implementation.

### Credential source detection + precedence (D-04/D-06)
```python
# Source: structure from shepsci check_all_credentials.py (reimplement, not import);
# precedence [VERIFIED: kaggle docs/DeepWiki] — access_token → env(KAGGLE_USERNAME/KAGGLE_KEY) → kaggle.json → OAuth.
# Token-type detection [CITED: shepsci check_all_credentials.py]:
def detect_token_type(tok: str) -> str:
    if tok.startswith("kagat_"): return "OAuth access token (~3h expiry)"
    if tok.startswith("kagrt_"): return "OAuth refresh token"
    if tok.startswith("KGAT_"):  return "Legacy scoped API token"
    if len(tok) == 32 and all(c in "0123456789abcdef" for c in tok): return "Legacy API key"
    return "API token"

def mask(v: str, prefix: int = 0) -> str:
    if not v or len(v) <= prefix + 4: return "****"
    return v[:prefix] + "*" * (len(v) - prefix - 4) + v[-4:]
```

### Pre-commit leak guard (D-15) — stdlib, portable, self-locating
```python
#!/usr/bin/env python3
# Installed by init; wired via:  git -C <ws> config core.hooksPath .githooks
# (.githooks/pre-commit is tracked; portable across clones once core.hooksPath is set.)
import re, subprocess, sys
PATTERNS = [
    re.compile(r"\bkag(a|r)t_[A-Za-z0-9]+"),          # OAuth access/refresh tokens
    re.compile(r"\bKGAT_[A-Za-z0-9]+"),               # legacy scoped token
    re.compile(r"KAGGLE_(KEY|API_TOKEN)\s*=\s*\S+"),  # env-var assignment with a value
    re.compile(r'"key"\s*:\s*"[0-9a-f]{32}"'),        # kaggle.json legacy key
]
# staged content only:
diff = subprocess.run(["git", "diff", "--cached", "--unified=0"],
                      capture_output=True, text=True).stdout
hits = [p.pattern for p in PATTERNS if p.search(diff)]
if hits:
    print(f"[BLOCKED] possible Kaggle credential in staged content: {hits}", file=sys.stderr)
    sys.exit(1)
```
Two-part defense (D-15): (a) the scaffolder asserts `.gitignore` contains `.env`, `kaggle.json`, `access_token` lines; (b) this content scanner blocks on a pattern hit. Bare 32-hex is intentionally scanned only inside the `"key":` JSON context to avoid false positives on commit SHAs.

### `.gitignore` (D-12/D-13 — anticipates Phase 3 artifacts)
```gitignore
# Secrets — CRITICAL (D-12)
.env
*.env
.env.*
!.env.example
kaggle.json
**/kaggle.json
access_token
**/access_token
# Data + heavy artifacts (D-12)
data/
# Phase 3 experiment artifacts — declared now so .gitignore isn't rewritten later (D-13)
experiments/*/artifacts/
experiments/*/*.csv
experiments/*/*.zip
experiments/*/*.pkl
experiments/*/*.parquet
# Tracked-but-anticipated exceptions: keep experiment code + meta.json (Phase 3)
!experiments/*/*.py
!experiments/*/*.ipynb
!experiments/*/meta.json
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
```

### `config.json` control-plane schema (SETUP-02, D-10)
```jsonc
{
  "workspace_version": 1,
  "competition_slug": "<from guided prompt>",
  "execution_target": "local",          // enum: "local" (default) | "kernel"  (SETUP-02)
  "cv": { "scheme": null },              // populated Phase 2
  "created": "<iso8601>"
}
// state.json (separate, D-10):  { "credentials": "UNVALIDATED"|"VALIDATED", "next_exp_id": 1, ... }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `WebFetch(domain:…)` permission as "egress control" | `sandbox.network.allowedDomains` (OS-level proxy over all Bash subprocesses) | Claude Code sandbox GA in 2.1.x; session-persist domain-allow v2.1.191 | The only mechanism that scopes the `kaggle` CLI. `[VERIFIED: docs]` |
| Kaggle API host `api.kaggle.com` | `https://www.kaggle.com/api/v1` (override via `KAGGLE_API_ENDPOINT`) | Kaggle CLI 2.x | Allowlist must include `www.kaggle.com`, not `api.kaggle.com`. `[VERIFIED: kaggle docs/GH]` |
| `kaggle.json` as primary credential | API token (`~/.kaggle/access_token` / `KAGGLE_API_TOKEN`) primary; OAuth `kaggle auth login`; `kaggle.json` legacy | Kaggle CLI/kagglehub GA (1.0/2.x) | Env-var-canonical (D-04) aligns with CLI precedence (env beats file). `[VERIFIED]` |
| `detect-secrets` + pre-commit framework | Stdlib regex hook via `core.hooksPath` | project constraint (standalone/stdlib) | No external dep; portable to other runtimes. `[CITED: CLAUDE.md]` |

**Deprecated/outdated:**
- Exemplar's `.pre-commit-config.yaml` (detect-secrets) — do not adopt; violates standalone constraint.
- Exemplar's `api.kaggle.com` allowlist host — stale for CLI 2.x.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `kaggle competitions list` exits non-zero on 401 and prints no secrets | Credential validation | If it exits 0 on failure, validation gives false-pass. Verify live (kaggle not installed this session). MEDIUM. |
| A2 | `kaggle config view` is local-only (no network) and does not print the key | Credential validation | If it prints the key, it would leak; don't use it as validator regardless. LOW risk given it's not the chosen validator. |
| A3 | `kaggle` version 2.2.3 current | Standard Stack | Version drift only; behavior stable across 2.x. LOW. |
| A4 | Off-list domain in a project `.claude/settings.json` **prompts** (not hard-block) unless `allowManagedDomainsOnly` in managed settings | Egress | If the user expects silent hard-block from a project file, criterion 5 wording ("refused, not silently allowed") is still met (prompt ≠ silent-allow), but "refused" is prompt-gated. MEDIUM — call out in plan. |
| A5 | `storage.googleapis.com` (path-style) is the sole GCS host for competition downloads | Egress | Regional/virtual-hosted variant would need `*.storage.googleapis.com` (already included as belt-and-suspenders). LOW. |
| A6 | `deniedDomains` support may be incomplete/under-development | Egress | Don't rely on it; allowlist-only design is unaffected. LOW. |
| A7 | pytest/ruff not needed at runtime; stdlib-only scripts suffice | Stack | If a script needs a non-stdlib lib, the stdlib-only constraint is violated — design must avoid. LOW. |

## Open Questions (RESOLVED)

All three questions below are operationalized by the Phase 1 plans; each carries a pointer to the plan/task that closes it. No question remains open as a blocker to execution.

1. **Exact `kaggle` CLI exit code + stderr text on 401 vs command-not-found vs perms warning.**
   - Known: CLI raises on auth failure; endpoint is `www.kaggle.com/api/v1`.
   - Unclear: precise exit codes / message strings (kaggle not installed this session).
   - Recommendation: install `kaggle` in a throwaway env and capture real outputs to harden the remediation `case` branches; keep the branch structure but treat string matches as best-effort.
   - **RESOLVED: captured live during 01-04 Task 2** (executor installs kaggle with consent, triggers a real 401 + command-not-found, and hardens the branch matches with the real exit codes/stderr; branch structure kept, string matches best-effort).

2. **Hard-block vs prompt for off-allowlist egress in a non-managed workspace.**
   - Known: managed `allowManagedDomainsOnly: true` hard-blocks; a project file prompts.
   - Unclear: whether the user wants a hard gate (would need managed settings or `failIfUnavailable`) or is satisfied with prompt-not-silent.
   - Recommendation: implement allowlist + `sandbox.enabled: true`; document that a true hard-block is an org/managed-settings concern.
   - **RESOLVED: documented as the residual caveat in 01-03 Task 3** (workspace-level `.claude/settings.json` deny-by-default *refuses/prompts* off-allowlist — satisfies criterion 5's "refused, not silently allowed"; a true no-prompt hard block is an org/managed-settings concern and out of Phase 1 scope, consistent with D-09's locked workspace-level choice).

3. **`socat` install as a plan step vs documented prerequisite.**
   - Known: Linux sandbox proxy needs socat (missing here); without it egress isn't enforced.
   - Recommendation: `init` detects socat and, on absence, prints the install command + a warning that egress is unenforced until installed (consent-based, never silent).
   - **RESOLVED: detect + instruct (consent-based) in 01-03 Task 1** (`init` detects socat; on absence prints the install command and warns that egress is unenforced until installed — never silent).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3 | all skill scripts | ✓ | 3.12.3 | — |
| uv | pyproject/env, install cmds | ✓ | 0.11.14 | pip |
| git | init, gitignore, hooks | ✓ | 2.43.0 | — |
| jq | optional ledger/JSON shell peeks | ✓ | 1.7 | Python `json` |
| bubblewrap (`bwrap`) | sandbox filesystem/network isolation (Linux) | ✓ | 0.9.0 | — |
| ripgrep (`rg`) | sandbox dep (bundled w/ claude) | ✓ | 14.1.0 | — |
| Claude Code | sandbox + settings runtime | ✓ | 2.1.205 | — (supports ${CLAUDE_SKILL_DIR} ≥2.1.196, mask ≥2.1.199) |
| **socat** | **sandbox network proxy (Linux)** | **✗** | — | `sudo apt-get install socat`; until then egress NOT enforced (sandbox degrades to unsandboxed with warning) |
| **kaggle CLI** | **live credential validation (SETUP-03)** | **✗** | — | `uv pip install kaggle`; D-07 allows scaffold to proceed & flag creds UNVALIDATED; drives the command-not-found remediation branch |
| pytest | Validation tests | ✗ | — | `uv pip install pytest` (Wave 0) |
| ruff | lint (optional) | ✗ | — | `uv pip install ruff` (optional) |
| AppArmor userns restriction | bubblewrap on Ubuntu 24.04+ | n/a | `=0` (unrestricted) | — (no profile needed) |

**Missing dependencies with no fallback:** none absolutely blocking scaffold (D-07 design).
**Missing dependencies with fallback:**
- `socat` — without it, criterion 5's egress enforcement is inert on this Linux host. Plan must detect + instruct (consent-based). This is the single biggest execution risk for the egress success criterion.
- `kaggle` — validation degrades to UNVALIDATED (by design, D-07) with an install remediation.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest ≥8.0 (NOT installed — Wave 0) |
| Config file | none yet — add `[tool.pytest.ini_options]` to the skill's `pyproject.toml` (Wave 0) |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SETUP-01 | `init` on empty dir creates full layout (control/, docs, .gitignore, git repo) | unit (tmp_path) | `uv run pytest tests/test_init_workspace.py::test_full_layout -x` | ❌ Wave 0 |
| SETUP-01 | Safe-merge: re-run doesn't overwrite existing files (D-02 idempotency) | unit | `uv run pytest tests/test_init_workspace.py::test_safe_merge_idempotent -x` | ❌ Wave 0 |
| SETUP-01 | `git init` produces repo on `main` with initial commit | unit | `uv run pytest tests/test_init_workspace.py::test_git_init -x` | ❌ Wave 0 |
| SETUP-02 | `config.json` has `execution_target=local` default; setter changes it; enum-validated | unit | `uv run pytest tests/test_config.py::test_execution_target -x` | ❌ Wave 0 |
| SETUP-03 | Credential source detection + precedence (env > kaggle.json); token-type detection | unit (monkeypatch env/tmp files) | `uv run pytest tests/test_credentials.py::test_precedence -x` | ❌ Wave 0 |
| SETUP-03 | command-not-found path sets UNVALIDATED + prints install remediation | unit (mock `which`) | `uv run pytest tests/test_credentials.py::test_kaggle_missing -x` | ❌ Wave 0 |
| SETUP-03 | Live validation against real Kaggle (pass/fail) | integration / manual | `uv run pytest tests/test_credentials_live.py -m live` (needs real token) | ❌ Wave 0 |
| SETUP-04 | chmod 600 self-heal on group/world-readable kaggle.json | unit (tmp file mode) | `uv run pytest tests/test_credentials.py::test_chmod_600 -x` | ❌ Wave 0 |
| SETUP-04 | No script echoes a credential value (regex over *.py/*.sh) | security unit | `uv run pytest tests/test_no_credential_leak.py -x` | ❌ Wave 0 |
| SETUP-04 | `.gitignore` covers .env/kaggle.json/access_token | unit | `uv run pytest tests/test_gitignore.py::test_secrets_ignored -x` | ❌ Wave 0 |
| SETUP-04 | Pre-commit scanner blocks a staged fake token; passes clean content | unit (subprocess git repo in tmp) | `uv run pytest tests/test_leak_scan.py -x` | ❌ Wave 0 |
| SETUP-04 | `settings.json` is valid JSON with sandbox.network.allowedDomains ⊇ required hosts | unit | `uv run pytest tests/test_settings.py::test_egress_allowlist -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q` (all unit/security; excludes `-m live`)
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** full unit+security suite green; live credential test run once manually with a real token before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/conftest.py` — tmp-workspace fixture, monkeypatched HOME/env fixtures
- [ ] `tests/test_init_workspace.py` — SETUP-01/02 layout + idempotency + git
- [ ] `tests/test_config.py` — execution_target schema
- [ ] `tests/test_credentials.py` — SETUP-03 precedence, chmod, command-not-found
- [ ] `tests/test_credentials_live.py` — `-m live` integration (real token)
- [ ] `tests/test_no_credential_leak.py` — SETUP-04 no-echo scan (port exemplar's pattern)
- [ ] `tests/test_gitignore.py` / `tests/test_settings.py` / `tests/test_leak_scan.py`
- [ ] Framework install: `uv pip install pytest` + `[tool.pytest.ini_options]` with a `live` marker

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Kaggle API token; never persist real values in git; env-var-canonical |
| V3 Session Management | no | No sessions in Phase 1 |
| V4 Access Control | no | Single-practitioner local tool |
| V5 Input Validation | partial | Validate competition slug format; enum-validate `execution_target`; reject malformed `kaggle.json` |
| V6 Cryptography | no | No custom crypto; rely on TLS + Kaggle-issued tokens (never hand-roll) |
| V7 Error/Logging | yes | Mask credentials in all output; no-echo test; remediation messages must not print token values |
| V8 Data Protection | yes | chmod 600 secrets; `.gitignore` + pre-commit scan; secrets never leave the machine |
| V14 Config | yes | Deny-by-default egress allowlist; sandbox enabled; document residual TLS caveat |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential committed to git | Information Disclosure | `.gitignore` + stdlib pre-commit content scan (D-15); commit-after-hook-install |
| Credential echoed to logs/transcript | Information Disclosure | Masking helper + no-echo regex test over *.py/*.sh |
| World-readable token file | Information Disclosure | chmod 600 self-heal (consent) |
| Data exfiltration via off-allowlist host | Exfiltration | `sandbox.network.allowedDomains` (deny-by-default); narrow GitHub scope; document domain-fronting caveat (TLS not terminated) |
| Silent env mutation / auto-install | Tampering | Detect + instruct + consent (D-03); never silent `pip install` |
| Untrusted directive in competition text | Tampering/Elevation | Out of Phase 1 (Phase 2 untrusted-content wrapping) — noted so egress/creds design doesn't assume trusted input later |

## Sources

### Primary (HIGH confidence)
- code.claude.com/docs/en/sandboxing — sandbox network isolation, `sandbox.network.allowedDomains`, proxy (bubblewrap+socat), deny-by-default prompt behavior, `allowManagedDomainsOnly`, TLS-not-terminated caveat, `failIfUnavailable`, credentials block.
- code.claude.com/docs/en/settings + github.com/anthropics/claude-code/examples/settings/{settings-bash-sandbox.json, settings-strict.json} — exact `sandbox` JSON shape (`network.allowedDomains` array).
- Local exemplar `~/.claude/plugins/cache/shepsci/kaggle-skill/2.3.0/` — SKILL.md frontmatter, `check_all_credentials.py` (token-type detection, masking, chmod self-heal, precedence), `setup_env.sh`, `.gitignore`, `test_no_credential_leakage.py` (structure only; not a dependency).
- Local environment probes — python 3.12.3, uv 0.11.14, git 2.43.0, jq 1.7, bwrap 0.9.0, rg 14.1.0, claude 2.1.205; kaggle/socat/pytest/ruff MISSING; apparmor userns=0.
- CLAUDE.md — stack versions, skill authoring, egress scoping, What-NOT-to-Use.

### Secondary (MEDIUM confidence)
- Kaggle CLI 2.x default endpoint `https://www.kaggle.com/api/v1`, `KAGGLE_API_ENDPOINT` override; credential precedence env>kaggle.json — GitHub Kaggle/kaggle-cli docs + DeepWiki authentication page + product-announcement (v2.2.0 OAuth).
- storage.googleapis.com as competition-download backend — multiple community sources + GH Kaggle/kaggle-cli issues.
- Claude Code sandbox `allowedDomains` wildcard syntax (`*.example.com`) — sandboxing docs mask example + community writeups.

### Tertiary (LOW confidence — flagged for live validation)
- Exact `kaggle` CLI exit codes / stderr strings on 401 and command-not-found (kaggle not installed this session).
- `kaggle config view` local-only / no-key-print behavior (inferred).

## Metadata

**Confidence breakdown:**
- Egress mechanism & schema: HIGH — official docs + example files + local dep probe.
- Credential precedence & handling: HIGH — CLI docs + exemplar + CLAUDE.md align.
- Live-validation exit codes: MEDIUM — kaggle not installed; branch structure sound, string matches best-effort.
- Egress hard-block vs prompt semantics: MEDIUM — depends on managed vs project settings; called out.
- Layout/config/gitignore/pyproject: HIGH — locked by D-10..D-14, standard patterns.
- Leak-guard approach: HIGH (design) — stdlib git-hook pattern is well established.

**Research date:** 2026-07-09
**Valid until:** ~2026-08-09 (30 days; re-check Claude Code sandbox schema and kaggle CLI version, both fast-moving)
</content>
</invoke>
