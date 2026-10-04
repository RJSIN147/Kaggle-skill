# kaggle-exp — developer notes

An Agent Skills skill (`SKILL.md` at the repo root; tested in Claude Code and OpenCode) plus
the `kx` Python CLI it drives. It runs a
Kaggle competition as a CV-first experiment loop:
- profile the competition from Kaggle's API;
- diagnose the data (`kx diagnose`: adversarial validation, time, entities, leaks) so the CV
  scheme mirrors how test differs from train;
- scaffold an experiment from its parent with a pre-registered prediction, run it on a Kaggle
  kernel (or locally), record a machine-checked CV and compare it with the parent fold by fold;
- write a verdict to a git-backed ledger, then submit (after the user confirms) and read the
  leaderboard back; a CV-vs-LB rank inversion makes the validation status suspect.

This file is for working ON the skill. Users clone it into their agent's skills folder as
`kaggle-exp` (Claude Code `~/.claude/skills/`, OpenCode `~/.config/opencode/skills/`) and run
`uv sync --project <that folder>`; see README.

## Layout

| Path | What |
|---|---|
| `SKILL.md` | The skill the agent loads. Keep it ≤150 lines (a test enforces this); detail goes in `references/`. Harness-neutral: see the rule below. |
| `references/kx-reference.md` | Envelope, every command and flag, `experiment.json` keys, the parent comparison, `kx-facts/1`, the validation status, the custom harness API, the `kx-preds/1` format. |
| `references/types/*.md` | One guide per competition type: tabular, timeseries, deep-learning, code-competition, simulation, writeup, custom (bring-your-own), other (mode unknown). |
| `src/kx/cli.py` | Argument parsing and dispatch. Stdout is guarded so the JSON envelope is the only output. |
| `src/kx/envelope.py` | `{kx, command, status, summary, data, warnings, errors, next_action}` |
| `src/kx/adapter.py` | The only module that talks to Kaggle (the in-process SDK `kaggle==2.2.3`/kagglesdk); see "Kaggle calls" below. |
| `src/kx/commands.py` | init / sync / confirm / metric / new / run / strategy / status |
| `src/kx/compare.py` | Fold hash and the paired parent comparison; prediction outcome. |
| `src/kx/diagnose.py`, `validation.py` | `kx diagnose` (facts.json, findings, evidence refs) and the warn-only validation status. |
| `src/kx/profile.py`, `metrics.py` | Competition profile (submission mode, modality, metric) and the metric registry. |
| `src/kx/kernel.py`, `record.py`, `pipeline.py` | Push and read back, bounded poll, pull, the fail-closed recorder, upstream chaining. |
| `src/kx/submit.py`, `subs.py`, `lb_gap.py` | Propose, then confirm and submit, read back, and the CV→LB gap with its divergence alarm. |
| `src/kx/research.py`, `ensemble.py`, `local.py`, `agent_eval.py` | Research ingestion, OOF blending, local runs, the simulation-agent evaluator. |
| `src/kx/datasets.py` | `kx dataset push`: a private dataset from a folder (credential refusal, read-back of an interrupted upload). |
| `src/kx/experiment.py`, `templates_registry.py`, `workspace.py` | `experiment.json` schema and validation, template selection and rendering, the workspace layout and scaffold. |
| `src/kx/ledger.py`, `strategy.py`, `preds.py` | The ledger rebuilt from `meta.json`, `strategy.md` rendering, the `kx-preds/1` validator. |
| `src/kx/credentials.py`, `leak_scan.py`, `untrusted.py`, `safe_extract.py`, `data.py`, `envinfo.py`, `util.py` | Masked credential discovery, the pre-commit leak hook, untrusted-text fences, zip-slip-safe extraction, data downloads, `kx env`, shared helpers. |
| `src/kx/templates/` | tabular, timeseries, deep (also deep-infer), inference, agent, custom (bring-your-own, stdlib harness), diagnose; `common/paths.py.tmpl` (stdlib path resolvers, used by all) + `common/harness.py.tmpl` (pandas helpers). |
| `tests/` | Offline suite with a `FakeAdapter` (`conftest.py`); `tests/live/` holds the opt-in real-Kaggle checks. |

## Commands

```
uv sync --extra local                      # dev env (kx + local ML stack); without it the
                                           # template tests fail at import (numpy)
uv run pytest -q                           # offline suite (~2 min); live tests excluded
uv run --with torch pytest tests/test_deep_template.py   # deep template (needs torch)
uv run pytest -q -m live                   # real Kaggle profile checks (needs a credential)
uvx ruff check src tests                   # lint (config in pyproject.toml)
uv run kx <command>                        # run kx from the repo
```

Clean OpenCode check (a fresh user's install; none of your own skills or plugins load):
clone the branch into `<fake home>/.config/opencode/skills/kaggle-exp`, `uv sync --project`
it, symlink `~/.kaggle` into the fake home, then run `opencode run --format json "start a
Kaggle workspace for titanic" </dev/null` from an empty workspace with `HOME` and
`OPENCODE_TEST_HOME` set to the fake home, `OPENCODE_DISABLE_CLAUDE_CODE=1`,
`OPENCODE_DISABLE_EXTERNAL_SKILLS=1`, and `XDG_DATA_HOME` left at the real one (the OpenCode
login). Continue with `--session <id>`. Without `</dev/null`, `opencode run` waits on stdin.

## Rules that must hold

- **Fail closed.** A run that errors, times out, or writes a bad `result.json` or bad
  predictions is recorded FAILED with no score. Never record a number the kernel didn't write.
- **The AI edits only the AI BLOCK.** The harness is hashed at `kx new`, and `kx run` refuses
  a modified harness. Changing a template's harness changes that hash.
- **Numbers come from kx.** Comparisons, findings and evidence values are computed by kx
  and rendered into envelopes, verdict stubs and `strategy.md`; the AI never types one.
  The parent comparison and the validation status inform and warn; they never refuse.
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
- **Harness-neutral skill.** SKILL.md calls its folder `<skill>` (the base directory the
  harness reports on load), never `${CLAUDE_SKILL_DIR}` or another harness variable (a test
  forbids `${`), and names no harness-specific tool. Envelopes name skill files by absolute
  path (`util.skill_path()`). After changing SKILL.md, re-run the clean OpenCode check below.
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
  competitions (ISIC, nlp-getting-started, ARC-AGI-2) refuse the data source until the user
  accepts the rules in a browser; others mount while `user_has_entered` is false
  (store-sales, digit-recognizer, 2026-10-02).
- **Code-competition submit** = kernel ref + version + output file name. API-served
  competitions (`kaggle_evaluation`) score in about 10–20 minutes.
- **Agents.** A simulation agent's local win rate does not predict its ladder rating.
- **Images (2026-10-04).** Kaggle's latest image moved from Python 3.12.13 to 3.13.15 on
  2026-10-03. `docker_image` on push pins any earlier digest (read back exactly; the run
  reports that Python). CPU images are `gcr.io/kaggle-images/python`, GPU images
  `gcr.io/kaggle-private-byod/python`; a CPU image on a T4 runs without an NVIDIA driver. A
  public notebook's metadata can report the CPU image even when it ran on a GPU.
- **GPU limits.** `get_accelerator_quota_statistics` gives the weekly quota (30 h GPU, 20 h
  TPU on this account). At most 2 GPU batch sessions run at once; a third push is refused
  ("Maximum batch GPU session count of 2").
- **Missing resources.** `get_kernel` and `dataset_status` answer HTTP 403 (not 404) for a kernel or dataset that does not
  exist; `dataset_list(mine=True)` includes private ones. `dataset_create_new(public=False)`
  then `dataset_create_version` work on the same folder (2026-10-04).

## Harness facts (OpenCode 1.18, 2026-10-02)

- OpenCode loads skills from `~/.config/opencode/skills/`, `~/.claude/skills/` and
  `~/.agents/skills/` (and the same folders under the project, walking up from the cwd to
  the git root, or to `/` without one). It finds every `SKILL.md` below them, so a git
  worktree inside the repo shows up as a duplicate `kaggle-exp`. The `name` must equal the
  folder name.
- Its skill tool states "Base directory for this skill: …" and leaves `${…}` unexpanded.
- Verified on deepseek-v4-flash in a clean install: the full Titanic loop, and the submit
  gate (it proposed, asked yes/no, and honoured "no").
