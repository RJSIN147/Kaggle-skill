# Spike Conventions

Patterns and stack choices established across spike sessions. New spikes follow these unless the
question requires otherwise.

## Stack

- **Python + the `kaggle` package (CLI 2.2.3)** from the repo's `uv` env (`.venv/bin/kaggle`).
- **CLI for actions** (push, status, output, submit, episodes, replay, logs, topics list, kernels
  list/pull); **SDK (`kagglesdk`, same package) for structured reads the CLI hides**
  (`get_competition`, `get_competition_data_files_summary`, `list_data_tree_files`,
  `list_topic_messages(page_size=-1)`) — via `KaggleApi().build_kaggle_client()`.
- Heavy/optional deps (e.g. `kaggle-environments`, 117 packages) run ephemerally:
  `uv run --no-project --with <pkg> python ...` — never installed into the repo env.

## Structure

- `.planning/spikes/NNN-name/` holds the spike's code, kernel folders (`a/`, `b/`… each with
  `kernel-metadata.json` + one code file), pulled evidence in `out/` or `raw/`, and `README.md`.
- Shared helpers at `.planning/spikes/`: `kwait.py` (wait for kernels), `subs.py` (read back
  submissions), `subwait.py` (poll submissions until scored).

## Patterns

- **Kernels:** private, CPU (`enable_gpu: false`), internet off, `kernel_type: "script"`, slug
  `kx-spike-NNN-<variant>` under the user's account; one print marker per fact
  (`SPIKENNN_<WHAT>=<json>`) so logs are grep-able.
- **Data paths:** competition data under `/kaggle/input/competitions/<canonical-slug>/` (case as
  the API reports it); kernel outputs under `/kaggle/input/notebooks/<owner>/<slug>/`.
- **Submissions are human actions:** Claude prepares and validates; the user runs the exact
  `kaggle competitions submit ...` with `!`; Claude confirms by read-back only (never trusts
  submit's exit code/stdout).
- **Live-check targets:** closed competitions that still accept late submissions
  (`submissions_disabled=False`) or perpetual sandboxes (Titanic, ConnectX) — never a competition
  the user is actively competing in. The user joins via the browser when a spike needs it.
- **Parse CLI JSON defensively:** decode the leading JSON value (`JSONDecoder().raw_decode`) —
  some commands append a prose hint after the JSON.
- **Never commit third-party content** (other users' notebook code, forum posts, replays with
  other players' names, host `kaggle_evaluation` code) — read it live, commit listings/metadata
  and our own findings only. Never log credentials or signed download URLs.
- **Commands in a worktree session use literal absolute paths** (no shell variables / computed
  command names — the sandbox refuses them).

## Tools & Libraries

- `kaggle` 2.2.3 (CLI + `kagglesdk`), Python 3.13 locally; Kaggle kernel image runs Python 3.12.
- `kaggle-environments` (ephemeral) for simulation competitions.
- Avoid: CLI `competitions topics show` for thread bodies (drops the original post) — use the SDK.
