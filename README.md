# kaggle-exp

An agent skill (Claude Code, OpenCode and other Agent Skills harnesses) that runs a Kaggle
competition as a CV-first experiment loop. Point your agent at an empty folder and a
competition. It:
1. profiles the competition from Kaggle's API;
2. diagnoses the data (how test differs from train) so the CV split mirrors it;
3. runs each idea on a Kaggle kernel (or locally) and records a machine-checked CV score,
   compared fold by fold with the experiment it builds on, plus a written verdict;
4. keeps a git-backed ledger and a living strategy;
5. submits only when you say yes.

Everything goes through one CLI, `kx`. Each command prints one JSON object whose
`next_action` tells the AI what to do next.

```
kx init → kx sync <comp> → kx confirm → kx metric → kx diagnose → kx new → kx run → kx strategy ─┐
                                                                    ↑___________________________│
                                             kx submit (you confirm) → kx lb (score read back)  ←┘
```

## What it handles

| Competition type | How |
|---|---|
| Tabular, time series | LightGBM-first templates with an AI-written CV split; local runs for small data |
| Image, text (deep learning) | PyTorch template on a GPU kernel, with mixed precision, per-epoch checkpoints, time-budgeted resume and pretrained weights from Kaggle Models |
| Code competitions (incl. API-served `kaggle_evaluation`) | Train on a GPU, then an internet-off inference stage that Kaggle reruns on the hidden test set |
| Simulations (e.g. ConnectX) | A single-file agent, self-play validated locally; the ladder rating and W/L/D are read back from replays |
| Writeups | A checklist from the evaluation criteria; you submit it on the website |
| Anything else (segmentation, detection, LLMs, audio, ARC-style tasks, artifacts) | A bring-your-own-pipeline template whose harness only enforces the output contract |

## Design choices

- **Profiles from structured API facts.** `kx sync` classifies the competition (submission
  mode, data type, metric) from Kaggle's API fields and file tree. You confirm the profile
  before anything uses it.
- **Fail-closed records.** A kernel that throws, times out, or writes an invalid result is
  recorded FAILED with no score.
  - `experiments/*/meta.json` is the source of truth;
  - `control/ledger.jsonl` is rebuilt from it;
  - `strategy.md` is regenerated each cycle.
- **A research loop, not just a run loop.**
  - `kx diagnose` checks the data before any model: adversarial validation (can a model tell
    train from test?), time order, repeating entities and single-feature leaks. Its findings
    set the CV scheme, and hypotheses cite its facts with values kx reads, never typed ones.
  - Every experiment has a parent and a pre-registered prediction (better / worse / same).
    kx compares it with its parent fold by fold (a corrected paired t-test) and records
    whether the prediction held, so `strategy.md` shows how well-calibrated the agent is.
  - A validation status turns suspect on a strong train/test shift or when CV and the
    leaderboard rank submissions differently. kx warns (it never blocks) and steers to a
    diagnosis or a CV-scheme check; the decision is recorded with a note, and adopting a CV
    scheme makes kx rank experiments only against others on the same folds.
- **Submissions need your yes.** `kx submit` checks a candidate:
  - the file or kernel version, and its shape;
  - the daily slots left;
  - whether its CV beats your best submission on the same CV folds.

  It then shows you exactly what would be submitted. Only after you confirm does it submit,
  once, and `kx lb` reads the score back next to CV with a divergence alarm.
- **Kernels are private, internet off by default.** They may turn internet on to fetch
  weights only where the rules allow it.
- **Research and blending.** `kx research` turns top discussions, public notebooks and the
  host's metric into untrusted, summarized notes. `kx ensemble` blends out-of-fold
  predictions into a new experiment and compares it with its best member.

## Install

It is an [Agent Skills](https://agentskills.io) skill, so it runs in any agent that loads
`SKILL.md` folders. Tested in **Claude Code** and **OpenCode**.

You need [uv](https://docs.astral.sh/uv/), git, Python 3.11+ (uv can fetch it) and a Kaggle
account. Clone the repo into your agent's skills folder; the folder must be named
`kaggle-exp`:

| Agent | Skills folder |
|---|---|
| Claude Code | `~/.claude/skills/kaggle-exp` (OpenCode reads this one too) |
| OpenCode | `~/.config/opencode/skills/kaggle-exp` |

```
SKILL_DIR=~/.config/opencode/skills/kaggle-exp     # or ~/.claude/skills/kaggle-exp
git clone https://github.com/RJSIN147/Kaggle-skill.git "$SKILL_DIR"
uv sync --project "$SKILL_DIR"                     # kx + kaggle==2.2.3
uv sync --project "$SKILL_DIR" --extra local       # optional: local runs
```

Update later with `git -C "$SKILL_DIR" pull && uv sync --project "$SKILL_DIR" --inexact`.

Kaggle credential: create a token at kaggle.com → Settings → API. Use any one of:
- `~/.kaggle/access_token` (`chmod 600`);
- `KAGGLE_API_TOKEN`;
- the legacy `~/.kaggle/kaggle.json` or `KAGGLE_USERNAME` + `KAGGLE_KEY`.

kx never prints or commits it.

## Use

Open your agent in an empty folder and ask, for example, "start a Kaggle workspace for
titanic" (in Claude Code you can also run `/kaggle-exp`). The agent handles the rest. A few
steps are yours:
- **Join the competition** (accept its rules) in the browser. kx tells you when it is needed.
- **Confirm the competition profile** the agent shows you.
- **Answer yes or no** to each submission proposal. Nothing is submitted without your yes.

The agent runs `uv` and `git` commands and reads the skill's guides outside the workspace
folder, so it may ask permission for those; allow them.

## Development

```
uv sync --extra local                                     # once: kx + the local ML stack
uv run pytest -q                                          # offline suite, no Kaggle calls
uv run --with torch pytest tests/test_deep_template.py    # deep template (needs torch)
uv run pytest -q -m live                                  # real Kaggle profile checks only
uvx ruff check src tests                                  # lint
```

Layout:
- `SKILL.md` — the skill;
- `src/kx/` — the CLI and templates;
- `references/` — the command reference and per-type guides;
- `tests/` — the test suite.

See `CLAUDE.md` for the developer notes.
