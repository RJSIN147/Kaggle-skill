---
name: kaggle-exp
description: >-
  Turn an empty folder into an AI-driven Kaggle competition experiment workspace.
  Use for "init" / setup of a Kaggle competition project: connect and live-validate
  the Kaggle account, scaffold a git-backed workspace (control-plane config/state/ledger,
  competition & strategy docs, .env, .gitignore, egress allowlist), and drive the
  CV-first experiment loop — propose an idea, run it, log the CV score and a written
  verdict to the ledger, and update the living strategy. Keywords: Kaggle competition,
  experiment workspace, init, scaffold, credentials, CV, cross-validation, submit,
  leaderboard, kernel, egress.
when_to_use: >-
  When the user wants to start or work in a Kaggle competition folder, set up / validate
  Kaggle credentials, scaffold the experiment workspace, choose local vs kernel execution,
  run a cross-validated experiment, or submit. Trigger on "Kaggle", "competition",
  "experiment", "init workspace", "CV", "submit".
allowed-tools: Bash(kaggle *) Bash(uv run *) Bash(git *) Bash(python3 scripts/*) Read Write Edit
---

# kaggle-exp — Kaggle Competition Experiment Workspace

Turn the current folder into a git-backed Kaggle **competition** experiment workspace and
drive one clean CV-first experiment cycle: propose → run → log result + verdict → update
strategy. The skill is installed globally and operates on the **current working directory**
— that cwd *is* the user's competition workspace (distinct from this skill package).

All heavy lifting lives in self-locating, stdlib-only helper scripts under `scripts/`
(each takes `--workspace <dir>`, never relies on `${CLAUDE_SKILL_DIR}`/`${CLAUDE_PROJECT_DIR}`).
Load `references/*` on demand for the Kaggle CLI surface and egress details.

---

## Guided init (D-01: guided, then scaffold)

`init` is **guided-then-scaffold**: ask the key choices, confirm, and only THEN create files.
**Nothing is created before the user has answered.** Never scaffold-first.

1. **Ask the competition slug.** (e.g. `titanic`, `home-data-for-ml-course`.) Required —
   there is no default. The workspace records this slug in `control/config.json`.
2. **Ask the execution target:** `local` (default, fast CV iteration) or `kernel` (Kaggle
   GPU / official runs). Recorded in `control/config.json`; changeable later.
3. **Confirm** both answers with the user.
4. Only after confirmation, run the scaffolder — passing `--slug` **only** once the user has
   answered:

   ```bash
   python3 scripts/init_workspace.py --workspace <cwd> --slug <slug> --execution-target <target>
   ```

   `--slug` is **required for a fresh workspace**: the script itself refuses to create anything
   without it (mechanical D-01 gate), so even a direct script call cannot bypass the
   prompt-first contract. To change the target later (SETUP-02) without re-prompting:

   ```bash
   python3 scripts/init_workspace.py --workspace <cwd> --set-execution-target <local|kernel>
   ```

The scaffolder is **safe-merge / idempotent** (D-02): it only creates files that don't exist
and never overwrites user edits, so `init` can be re-run to repair or top-up a partial
workspace. It stages only scaffold-owned paths (never `git add -A`) and makes one initial
`chore: scaffold workspace` commit on branch `main`.

### Workspace layout it produces (D-10)

```
<cwd>/
  competition.md  strategy.md  README.md      # human docs, at root, tracked
  .gitignore  .env                            # .env is gitignored (secrets)
  .claude/settings.json                       # egress allowlist (merged, not clobbered)
  pyproject.toml                              # minimal workspace stub (D-14)
  control/
    config.json  state.json  ledger.jsonl     # machine control-plane, tracked
  data/                                       # gitignored
  experiments/                                # per-experiment dirs (later phases)
```

---

## Credential validation (D-03 consent, D-07 flag-on-fail)

After scaffolding completes, validate the Kaggle connection. `init_workspace.py` (scaffold +
git commit) always runs **before** `check_credentials.py` (which flips the credential status
in `control/state.json`), so the two never race on git/state.

```bash
python3 scripts/check_credentials.py --workspace <cwd>
```

- **Env vars are canonical** (D-04): `KAGGLE_USERNAME` / `KAGGLE_KEY` (or `KAGGLE_API_TOKEN`).
  The checker detects other sources (`kaggle.json`, `access_token`), normalizes toward the
  workspace `.env`, and validates with a cheap, exit-code-based live call — **never printing a
  secret value**.
- **Auto-fix only with explicit consent** (D-03): every fix is shown first and applied only
  after the user confirms — **never silent**. Pass `--yes` to carry that consent:

  ```bash
  python3 scripts/check_credentials.py --workspace <cwd> --yes
  ```

  Consent-gated fixes include: `chmod 600` a group/world-readable `kaggle.json`; populate the
  workspace `.env` from an existing `kaggle.json`; install a missing `kaggle` CLI or `socat`.
  Ask the user *before* passing `--yes`.
- **Flag on failure, don't abort** (D-07): the scaffold is already done. If live validation
  FAILS, keep the workspace, leave `control/state.json` `credentials = "UNVALIDATED"`, and
  print exact remediation. Only credential-dependent operations (data download, submit) are
  blocked downstream; re-running `check_credentials.py` after fixing clears the flag.

---

## Security & egress (SETUP-04)

- **Never echo, log, or commit credential values.** The scripts mask output and the pre-commit
  guard (`scripts/leak_scan.py`, wired via `core.hooksPath`) blocks a commit that stages a
  token-shaped secret.
- **Deny-by-default network egress.** `init` writes/merges a `sandbox.network.allowedDomains`
  allowlist into the workspace `.claude/settings.json` (the layer that actually scopes the
  `kaggle` CLI subprocess) and documents it in `references/egress-allowlist.md` for portability.
  See that reference for the exact host set and the GCS-backend gotcha.

---

## Scripts (progressive disclosure)

| Script | Purpose |
|--------|---------|
| `scripts/init_workspace.py` | SETUP-01/02 scaffolder (layout, control-plane, git, `.gitignore`, settings) |
| `scripts/check_credentials.py` | SETUP-03 credential detect / normalize / consent-gated fix / live-validate |
| `scripts/leak_scan.py` | SETUP-04 stdlib pre-commit content scanner (git hook target) |

Read `references/egress-allowlist.md` (egress hosts + portability) and
`references/kaggle-cli-behavior.md` (observed CLI exit-codes / precedence) only when needed.
