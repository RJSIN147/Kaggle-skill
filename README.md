# kaggle-exp

A Claude Code skill that runs a Kaggle competition as a CV-first experiment loop through
one CLI, `kx`. Each command prints one JSON object whose `next_action` tells the AI what
to do next.

```
empty folder → kx init → kx sync <comp> → kx confirm → kx metric → kx new → kx run → kx strategy
                                                     ↑__________________________________|
```

- **Kernel-first.** `kx run` pushes a private Kaggle script kernel (internet off), polls
  with a bound, pulls the outputs and records a machine-checked CV score. Local runs are
  an option for small data (`kx new --local`).
- **Profiles from structured API facts.** `kx sync` classifies the competition
  (csv_upload / code_kernel / API-served / agent / writeup) from Kaggle's API fields,
  data-file summary and file tree. The user confirms it; nothing is scraped from prose.
- **Fail-closed records.** A kernel that throws, times out, or writes an invalid result
  is recorded FAILED with no score. `experiments/*/meta.json` is canonical;
  `control/ledger.jsonl` is rebuilt from it; `strategy.md` is regenerated each cycle.
- **Submissions need a human yes.** `kx submit` validates a candidate and shows what will
  be submitted; only after the user confirms does `kx submit … --confirm <token>` submit
  it (re-checked, once, never retried); `kx lb` confirms by read-back.
- **Research and blending.** `kx research` ingests discussions, public notebooks and the
  host's metric kernel as untrusted, summarized notes; `kx ensemble` blends OOF
  predictions (the shared `kx-preds/1` format) into a new experiment.

## Install

```
git clone <this repo> ~/.claude/skills/kaggle-exp
uv sync --project ~/.claude/skills/kaggle-exp          # kx + kaggle==2.2.3
uv sync --project ~/.claude/skills/kaggle-exp --extra local   # optional: local runs
```

A Kaggle API token in `~/.kaggle/access_token` (mode 600) or `KAGGLE_API_TOKEN`.

## Layout

```
SKILL.md                 the skill (loaded by Claude Code)
src/kx/                  the CLI: commands, Kaggle adapter, recorder, templates
references/              kx-reference.md, per-type guides (types/*.md), egress opt-in
tests/                   offline suite (`uv run pytest`); live checks: `-m live`
```

## Development

```
uv run pytest -q              # offline, no Kaggle calls
uv run pytest -q -m live      # real Kaggle: CPU kernels only, never submits
```
