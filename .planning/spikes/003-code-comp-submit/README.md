---
spike: 003
name: code-comp-submit
type: comparison
validates: "Given a closed code competition that accepts late submissions, when a kernel version is submitted with `kaggle competitions submit -k -v -f`, then it is accepted, re-run on the hidden test and scored — for a script kernel, a notebook kernel, and an API-served (kaggle_evaluation) competition"
verdict: VALIDATED
related: [001, 002]
tags: [code-competition, submission, script-kernel, kaggle-evaluation, api-served]
---

# Spike 003: Code-competition submission (script vs notebook, + API-served)

## What This Validates

Given a closed code competition that still accepts late submissions (spike 001:
`submissions_disabled=False`), when a kernel version is submitted with
`kaggle competitions submit <comp> -k <owner/slug> -v <N> -f <output-file> -m <msg>`, then it is
accepted, re-run on the hidden test set and scored. Compared: **003a script kernel** vs **003b
notebook kernel** (same code) on `equity-post-HCT-survival-predictions` (tabular, CSV output), plus
**003c** an **API-served** competition (`um-game-playing-strength-of-mcts-variants`,
`kaggle_evaluation` gateway, `submission.parquet`).

## Research

- CLI: `competitions submit [-f FILE] [-k KERNEL] [-v VERSION] -m MSG` — `-f` is "the name of the
  output file produced by a kernel (for code competitions)". SDK: `ApiCreateCodeSubmissionRequest
  {competition_name, kernel_owner, kernel_slug, kernel_version, file_name, submission_description}`.
- API-served comps ship `kaggle_evaluation/` inside the competition data: participant code builds
  `<Comp>InferenceServer(predict)`; on the scoring rerun (`KAGGLE_IS_COMPETITION_RERUN` set) it must
  `serve()`; otherwise `run_local_gateway(data_paths)` exercises the host gateway locally.
  `base_gateway.write_submission` writes **`submission.parquet`** to the cwd. The server must start
  within a startup limit ("Start the server before performing any time consuming steps").

| Approach | Pros | Cons | Status |
|---|---|---|---|
| 003a script kernel (`kernel_type: script`) | runs the `.py` as-is (spike 002) | unknown whether code comps accept scripts | tested |
| 003b notebook kernel (`kernel_type: notebook`) | the documented/common path | needs kernelspec + papermill quirks | tested |
| 003c API-served script kernel | covers `kaggle_evaluation` comps | host gateway defaults to old mount path | tested |

## How to Run

```bash
K=.venv/bin/kaggle
python .planning/spikes/003-code-comp-submit/make_notebook.py        # builds b-notebook from a-script
$K kernels push -p .planning/spikes/003-code-comp-submit/a-script     # (and b-notebook, c-api-served)
python .planning/spikes/kwait.py ravijotsinha/kx-spike-003-script     # wait COMPLETE
# the SUBMIT is a human action (it spends a slot) — the user ran it with `! <cmd>`:
$K competitions submit equity-post-HCT-survival-predictions -k ravijotsinha/kx-spike-003-script -v 1 -f submission.csv -m "..."
python .planning/spikes/subwait.py equity-post-HCT-survival-predictions:<ref> ...   # read-back until scored
```

## Investigation Trail

1. **Joining:** the user joined via the browser rules page. The joined-list ref is the canonical
   **`equity-post-HCT-survival-predictions`** (capitals) though every command also accepted the
   lowercase slug — a profile must store the canonical ref from the API.
2. **Kernels (CPU, internet off):** script + notebook both COMPLETE; data mounted at
   `/kaggle/input/competitions/equity-post-HCT-survival-predictions/` (canonical case, spike-002
   layout); both wrote a 3-row `submission.csv` (`ID,prediction`) from the public test.
3. **Submitting is a human action:** Claude Code's auto-mode classifier **denied**
   `kaggle competitions submit` ("Real-World Transactions"). The user ran the four submit commands
   themselves with `!`. This matches the v2 principle (never submit without an explicit human
   go-ahead) and is the natural shape for `kx submit`: prepare + validate, then hand the exact
   command to the human.
4. **Silent success:** a code-competition submit (`-k -v -f`) printed **nothing** (exit 0);
   a file-upload submit (ConnectX `-f main.py`) printed an upload bar + `Successfully submitted to
   Connect X`. → Success MUST be confirmed by read-back (`competitions submissions`), as v1 learned.
5. **Read-back:** all four rows appeared immediately as `SubmissionStatus.PENDING` with
   `description` and `fileName` (`submission.csv` / `submission.parquet` / `main.py`).
6. **Bonus — Phase 5 A1 CONFIRMED:** 003a's read-back `date` was `2026-09-25T00:56:32.697000`;
   `date -u` read `00:56:52`, local `06:26:52+0530` → `submissions.date` is **UTC** (recorded in
   `references/kaggle-cli-behavior.md` and `05-HUMAN-UAT.md`).
7. **Scoring latency (equity):** both 003a and 003b went PENDING → `COMPLETE` within ~3 min
   (first poll at 00:59:33) with **public 0.64754 / private 0.65377 — identical** for script and
   notebook (same deterministic code).
8. **API-served (003c):** the kernel ran the host gateway locally inside a *script* kernel
   (`SPIKE003C_LOCAL_GATEWAY_DONE {"exists": true, "rows": 3}`). Surprise: the host gateway's
   DEFAULT data paths are `/kaggle/input/<slug>/…` — the old mount — so the local run must pass
   `data_paths` explicitly on today's layout. Scoring result: see Results.

9. **API-served scoring (003c):** PENDING → `COMPLETE` at 01:17:40 (~20 min after submit — ~7×
   the tabular comp; the rerun streams the hidden test through the gRPC gateway in batches of 100)
   with **public 0.57164 / private 0.57683** — the expected RMSE for a constant-zero predictor on a
   `utility_agent1` target in [-1, 1]. The same script's `KAGGLE_IS_COMPETITION_RERUN` branch
   (`serve()`) ran against Kaggle's hidden-test gateway without modification.

## Results

**Verdict: VALIDATED** — all three variants were accepted, re-run on the hidden test and scored.

| Variant | Kernel type | Output file | Submit → scored | Public / Private |
|---|---|---|---|---|
| 003a equity (tabular) | **script** | `submission.csv` | ≤ 3 min | 0.64754 / 0.65377 |
| 003b equity (tabular) | notebook | `submission.csv` | ≤ 3 min | 0.64754 / 0.65377 |
| 003c MCTS (API-served) | **script** | `submission.parquet` | ~20 min | 0.57164 / 0.57683 |

**Comparison verdict (script vs notebook): script WINS** — identical scores, no conversion step,
none of the papermill workarounds (spike 002), and it works for API-served comps too.

**Signal for the build (`code_kernel` submission mode):**

- One flow for every code competition: push script kernel (internet off, CPU/GPU per profile) →
  wait COMPLETE → verify the expected output file exists in the kernel output (name from the
  profile's sample file: `submission.csv` / `.parquet` / `.json`) → **hand the exact
  `competitions submit <canonical-ref> -k <owner/slug> -v <version> -f <file> -m <msg>` to the
  human** → confirm by read-back only (submit prints nothing) → poll to COMPLETE (minutes for
  tabular, tens of minutes for API-served).
- API-served template: import `kaggle_evaluation` from the competition dir; start the server
  immediately (startup limit); `serve()` when `KAGGLE_IS_COMPETITION_RERUN` is set, else
  `run_local_gateway(explicit data_paths)` — host gateway defaults point at the retired
  `/kaggle/input/<slug>/` mount.
- Store the competition's **canonical ref** (e.g. `equity-post-HCT-…`) from the API; the data dir
  on disk uses it.
- A kernel-version submission is reproducible by construction (Kaggle reruns *that* version) —
  record `(kernel slug, version, output file, ref)` as the submission's provenance.
- Bonus: Phase 5 A1 confirmed (`submissions.date` is UTC).
