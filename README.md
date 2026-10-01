# kaggle-exp

A Claude Code skill that runs a Kaggle competition as a CV-first experiment loop. Point
Claude at an empty folder and a competition. It:
1. profiles the competition from Kaggle's API;
2. runs each idea on a Kaggle kernel (or locally) and records a machine-checked CV score with
   a written verdict;
3. keeps a git-backed ledger and a living strategy;
4. submits only when you say yes.

Everything goes through one CLI, `kx`. Each command prints one JSON object whose
`next_action` tells the AI what to do next.

```
kx init → kx sync <comp> → kx confirm → kx metric → kx new → kx run → kx strategy ─┐
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

## Design choices

- **Profiles from structured API facts.** `kx sync` classifies the competition (submission
  mode, data type, metric) from Kaggle's API fields and file tree. You confirm the profile
  before anything uses it.
- **Fail-closed records.** A kernel that throws, times out, or writes an invalid result is
  recorded FAILED with no score.
  - `experiments/*/meta.json` is the source of truth;
  - `control/ledger.jsonl` is rebuilt from it;
  - `strategy.md` is regenerated each cycle.
- **Submissions need your yes.** `kx submit` checks a candidate:
  - the file or kernel version, and its shape;
  - the daily slots left;
  - whether its CV beats your best submission.

  It then shows you exactly what would be submitted. Only after you confirm does it submit,
  once, and `kx lb` reads the score back next to CV with a divergence alarm.
- **Kernels are private, internet off by default.** They may turn internet on to fetch
  weights only where the rules allow it.
- **Research and blending.** `kx research` turns top discussions, public notebooks and the
  host's metric into untrusted, summarized notes. `kx ensemble` blends out-of-fold
  predictions into a new experiment.

## Install

You need Claude Code, [uv](https://docs.astral.sh/uv/), Python 3.11+ and a Kaggle account.

```
git clone https://github.com/RJSIN147/Kaggle-skill.git ~/.claude/skills/kaggle-exp
uv sync --project ~/.claude/skills/kaggle-exp                 # kx + kaggle==2.2.3
uv sync --project ~/.claude/skills/kaggle-exp --extra local   # optional: local runs
```

Kaggle credential: create a token at kaggle.com → Settings → API. Use any one of:
- `~/.kaggle/access_token` (`chmod 600`);
- `KAGGLE_API_TOKEN`;
- the legacy `~/.kaggle/kaggle.json` or `KAGGLE_USERNAME` + `KAGGLE_KEY`.

kx never prints or commits it.

## Use

Open Claude Code in an empty folder and ask, for example, "start a Kaggle workspace for
titanic", or run `/kaggle-exp`. Claude handles the rest. A few steps are yours:
- **Join the competition** (accept its rules) in the browser. kx tells you when it is needed.
- **Confirm the competition profile** Claude shows you.
- **Answer yes or no** to each submission proposal.

## Development

```
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
