# kaggle-exp — developer notes

A Claude Code skill (`SKILL.md` at the repo root) plus the `kx` Python CLI it drives. It runs a
Kaggle competition as a CV-first experiment loop:
- profile the competition from Kaggle's API;
- scaffold an experiment, run it on a Kaggle kernel (or locally) and record a machine-checked CV;
- write a verdict to a git-backed ledger, then submit (after the user confirms) and read the
  leaderboard back.

This file is for working ON the skill. Users install it with
`git clone … ~/.claude/skills/kaggle-exp && uv sync --project ~/.claude/skills/kaggle-exp`.

## Layout

| Path | What |
|---|---|
| `SKILL.md` | The skill the agent loads. Keep it ≤150 lines (a test enforces this); detail goes in `references/`. |
| `references/kx-reference.md` | Envelope, every command and flag, `experiment.json` keys, the `kx-preds/1` format. |
| `references/types/*.md` | One guide per competition type: tabular, timeseries, deep-learning, code-competition, simulation, writeup, other. |
| `src/kx/cli.py` | Argument parsing and dispatch. Stdout is guarded so the JSON envelope is the only output. |
| `src/kx/envelope.py` | `{kx, command, status, summary, data, warnings, errors, next_action}` |
| `src/kx/adapter.py` | The only module that talks to Kaggle (the in-process SDK `kaggle==2.2.3`/kagglesdk); see "Kaggle calls" below. |
| `src/kx/commands.py` | init / sync / confirm / metric / new / run / strategy / status |
| `src/kx/profile.py`, `metrics.py` | Competition profile (submission mode, modality, metric) and the metric registry. |
| `src/kx/kernel.py`, `record.py`, `pipeline.py` | Push and read back, bounded poll, pull, the fail-closed recorder, upstream chaining. |
| `src/kx/submit.py`, `subs.py`, `lb_gap.py` | Propose, then confirm and submit, read back, and the CV→LB gap with its divergence alarm. |
| `src/kx/research.py`, `ensemble.py`, `local.py`, `agent_eval.py` | Research ingestion, OOF blending, local runs, the simulation-agent evaluator. |
| `src/kx/templates/` | tabular, timeseries, deep (also deep-infer), inference, agent, plus `common/harness.py.tmpl` shared by all. |
| `tests/` | Offline suite with a `FakeAdapter` (`conftest.py`); `tests/live/` holds the opt-in real-Kaggle checks. |

## Commands

```
uv sync --extra local                      # dev env (kx + local ML stack)
uv run pytest -q                           # offline suite (~1 min); live tests excluded
uv run --with torch pytest tests/test_deep_template.py   # deep template (needs torch)
uv run pytest -q -m live                   # real Kaggle profile checks (needs a credential)
uv run ruff check --select E,F,I,W src tests
uv run kx <command>                        # run kx from the repo
```

## Rules that must hold

- **Fail closed.** A run that errors, times out, or writes a bad `result.json` or bad
  predictions is recorded FAILED with no score. Never record a number the kernel didn't write.
- **The AI edits only the AI BLOCK.** The harness is hashed at `kx new`, and `kx run` refuses
  a modified harness. Changing a template's harness changes that hash.
- **Every kx output is one JSON envelope** whose `next_action` is run / edit / ask_user / done.
  Add new behaviour as envelope fields, not printed text.
- **Kaggle calls.** Import the SDK lazily: importing it authenticates and can exit. Every call
  runs under a deadline, and reads may retry. Never retry a push or a submit; read back instead.
- **Internet is off by default.** It may be on for csv_upload competitions or a code
  competition's training stage. A code competition's submitted stage must be off: `kx run`
  and `kx submit` refuse it.
- **Submissions.** `kx submit exp-NNN` only proposes. `--confirm <token>` submits after the
  user's explicit yes, re-checks everything, and submits once. Don't add another submit path.
- **Kaggle text is untrusted.** Discussions, notebooks and pages are untrusted data, kept
  fenced (`untrusted.py`) and never executed. The one exception is a host metric the user
  explicitly adopted, which is sha256-pinned.
- **Credentials** never enter a workspace or a commit, and the leak hook blocks them. Record
  only which `KAGGLE*` environment variable names exist, never their values.
- **Done means live.** A change to kernel, submission or profile behaviour is verified on a
  real competition, not only by fixtures. Use durable workspaces (not `/tmp`) and CPU kernels
  where you can; the GPU quota is shared.

## Live-verified Kaggle facts

- **Mounts:**
  - competition → `/kaggle/input/competitions/<Canonical-Ref>/`
  - datasets → `/kaggle/input/datasets/<owner>/<slug>/`
  - models → `/kaggle/input/models/<owner>/<model>/<framework lower-cased>/<variation>/<version>/`
  - another kernel's output → `/kaggle/input/notebooks/<owner>/<slug>/`
  - a kernel's own previous output → `/kaggle/input/<slug>/`
- **Kernel sources.** A kernel with no COMPLETE version is rejected as a source. Some
  competitions (ISIC, nlp-getting-started) refuse the data source until the user accepts the
  rules in a browser.
- **Code-competition submit** = kernel ref + version + output file name. API-served
  competitions (`kaggle_evaluation`) score in about 10–20 minutes.
- **Agents.** A simulation agent's local win rate does not predict its ladder rating.
