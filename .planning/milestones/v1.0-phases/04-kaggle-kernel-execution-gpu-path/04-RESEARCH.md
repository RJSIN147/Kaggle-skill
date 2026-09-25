# Phase 4: Kaggle Kernel Execution (GPU Path) - Research

**Researched:** 2026-07-11
**Domain:** Kaggle CLI 2.x kernel lifecycle (push → poll → pull) as a pure addition to the local experiment loop; silent-kernel-failure detection extending the Phase 3 machine-checked result contract.
**Confidence:** HIGH (nearly every open item verified live against the installed `kaggle` 2.2.3 CLI + its bundled `kagglesdk` source; residual UNKNOWNs are precisely the 4 that genuinely require a live GPU push).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Kernel path decomposes into DISCRETE, idempotent entry points — `convert → push → poll → pull` — then reuses existing `record_experiment.py`. NOT a combined `run_kernel`. If polling dies, user resumes `poll`/`pull` **without re-pushing**. Each step argparse-in / exit-code-out, stdlib-only, self-locating, `--workspace`-driven; SKILL sequences them.
- **D-02:** Convert step (`.py → .ipynb` via jupytext) is a SEPARATE step before push. GUARD: convert stays **mechanical/deterministic — regenerated from the scaffold-minted `experiment.py`, not hand-edited**. The `.ipynb` is a build artifact. Preserves the EXP-05 "same experiment, untouched" seam (`resolve_data_dir()`). Deliberate notebook tweaks = intentional deviation captured in provenance, not the default. Keep convert re-runnable and non-destructive.
- **D-03:** Push→poll→pull handoff state lives in `experiments/exp-NNN/kernel_run.json` (kernel slug, version, code_file, push time, competition, accelerator, effective internet flag, detached/PENDING status). NOT `control/state.json`. Co-located, git-diffable, multi-experiment safe.
- **D-04:** Default accelerator `T4×2` (same 30h/week cost as P100), overridable per experiment. Generated from a validated template.
- **D-05:** Kernel id/slug DETERMINISTIC and STABLE per experiment — `<username>/<competition-slug>-exp-NNN` — re-pushing updates the SAME kernel (Kaggle auto-versions). `kernel_run.json` tracks current version. Researcher confirms push id-collision/versioning + username resolution.
- **D-06:** `enable_internet` defaults `false`, config-level toggle. GUARD: effective per-run internet value MUST be recorded in provenance (`kernel_run.json` → `meta.json`).
- **D-07:** Kernel ALWAYS private (`is_private: true`); `competition_sources` populated mechanically from `config.json.competition_slug` (mounts `/kaggle/input/<slug>/`). No re-prompting.
- **D-08:** OUR-side poll wait budget defaults ~2 hours, configurable. Poller stays bounded (never a kernel kill).
- **D-09:** On OUR-side timeout with kernel still running, DETACH — do not cancel. Leave kernel running, record PENDING/detached in `kernel_run.json`, user re-runs `poll` later to reattach and `pull`.
- **D-10:** Backoff EXPONENTIAL with cap + jitter (start ~10s, cap ~60–120s). Poll-call errors (transient network / 429 / status-parse bugs #473/#509) tolerated as transient: back off + retry within budget; fail-closed only if errors persist past threshold or budget expires. A transient blip is NEVER misread as kernel failure. Researcher confirms exact status output shape.
- **D-11:** Pulled run log scanned for TRACEBACK signatures AND error markers (Python traceback, `Error:`/uncaught-exception, non-zero-exit/process-killed/OOM). A hit ⇒ FAILED even if status said `complete` and even if `result.json` exists. Researcher confirms actual kernel-log format.
- **D-12:** Scan lives INSIDE `record_experiment.py` as a NEW FIRST RUNG of the D-06 ladder (kernel path only); enum REUSES existing reasons + adds exactly one `kernel_error`. Order: scan log → hit ⇒ `FAILED(kernel_error)` BEFORE `result.json` is trusted; else fall through to existing `missing_result`/`schema_invalid`/`non_finite`/`out_of_range`. One recorder, one ladder.
- **D-13:** Lightweight, NON-BLOCKING GPU-quota heads-up before push. Never block. Full tracking/gating is Phase 5. Researcher checks whether CLI exposes remaining GPU quota.
- **D-14:** Document + record kernel image/version; do NOT pin to match local. Record image in provenance when the log exposes it. NOT in-notebook `!pip install` pinning.

### Claude's Discretion
- `kernel_run.json` full schema beyond the D-03 named fields; detached/PENDING vs completed/pulled state representation.
- Exact kernel-metadata template shape (`kernel-metadata.json.tmpl`) — kernel type, language, `code_file` naming.
- Precise backoff constants (initial, multiplier, cap, jitter) + persistent-error threshold.
- Exact traceback/error pattern set for D-11.
- Where the D-13 quota note and D-02 convert step surface in SKILL.md.
- How `<username>` is resolved for the D-05 slug.

### Deferred Ideas (OUT OF SCOPE)
- GPU-hour tracking + push gating over a budget (Phase 5).
- In-notebook version pinning to match kaggle/python image (Phase 5 CV→LB parity).
- Active remote kernel cancel on timeout (rejected — detach-not-cancel preserves GPU time).
- Submission FROM kernel output (code-competition notebook→submission) — Phase 5.
- First-class "author a kernel-only notebook" flow (deliberate per-experiment notebook edits allowed only as a provenance-captured deviation).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXP-05 | User can push a notebook to a Kaggle Kernel, run it on Kaggle compute (GPU), poll to completion, and pull results/artifacts back — with silent-failure (traceback-in-log) detection | Full CLI surface verified live: `kernels push` (metadata schema + `--accelerator`), `kernels status` (authoritative `KernelWorkerStatus` enum), `kernels logs` (log-scan source for silent failure), `kernels output` (artifact pull into the same contract), `kernels pull -m` (image provenance), `quota` (heads-up). See Standard Stack + Code Examples. |
</phase_requirements>

## Summary

Phase 4 is a **pure orchestration addition**: the same `experiment.py` that runs locally
runs on a Kaggle GPU kernel, and the pulled `result.json` flows through the **unchanged**
Phase 3 recorder — with exactly one new failure rung added for silent kernel failure. The
entire Kaggle command surface needed for the loop is present and was verified live against
the installed `kaggle 2.2.3` CLI and its bundled `kagglesdk` source. Almost every open item
the CONTEXT flagged is now resolved from an authoritative source (the CLI source code /
bundled enum), not inference.

The headline correctness property — a kernel that reports `COMPLETE` but actually threw must
be recorded `FAILED` — hinges on `kaggle kernels logs`, which returns the full execution log
as a string. Kaggle reports notebook *session* completion (`COMPLETE`) independently of
whether a *cell* raised, so status alone is insufficient; the log scan (D-11) is load-bearing
and is the reason the recorder's fail-closed ladder must scan the log **before** trusting
`result.json`. This is testable without a live GPU using synthetic fixture logs.

**Primary recommendation:** Build four thin stdlib scripts (`convert_notebook.py`,
`push_kernel.py`, `poll_kernel.py`, `pull_kernel.py`) that each route their `kaggle` calls
through the existing `kaggle_gateway.run_kaggle()` choke point, persist handoff state in
`experiments/exp-NNN/kernel_run.json`, and hand the pulled `result.json` **plus the pulled
log path** to an extended `record_experiment.py` whose new first rung scans the log for
tracebacks/OOM/error markers and classifies `kernel_error` before the existing D-06 ladder
runs. Default the accelerator via `enable_gpu: true` (guaranteed-valid) with a verified
`NvidiaTeslaT4` override; treat the exact **T4×2** string as the one item needing a live push
to confirm (GitHub issue #821 confirms it is undocumented). Poll by parsing the CLI's
`has status "…"` line against the authoritative `KernelWorkerStatus` enum
`{QUEUED, RUNNING, COMPLETE, ERROR, CANCEL_REQUESTED, CANCEL_ACKNOWLEDGED, NEW_SCRIPT}`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `.py → .ipynb` conversion | Skill script (`convert_notebook.py`) via `uv run jupytext` | — | Deterministic build step; jupytext is a workspace ML-env dep, shelled like `run_local` shells `uv run` |
| Kernel-metadata generation | Skill script (`push_kernel.py`) + `kernel-metadata.json.tmpl` | `control/config.json` | Slug/accelerator/internet/competition_sources all derive from config + minted per push |
| Push / run on GPU | Kaggle platform | `kaggle_gateway.run_kaggle()` | CLI is the only primitive that pushes kernels (kagglehub cannot); gateway is the no-echo/timeout choke point |
| Status polling | Skill script (`poll_kernel.py`) | `kaggle_gateway.run_kaggle()` | Loop/timeout/backoff/JSON parsing → Python (CLAUDE.md rule); our-side patience, not a kernel kill |
| Result validation + silent-failure classification | `record_experiment.py` (extended) | pulled log + `result.json` | D-12: one recorder, one ladder; the contract is extended, never re-derived |
| Handoff/provenance state | `experiments/exp-NNN/kernel_run.json` | `meta.json` | Co-located, git-diffable, multi-experiment safe (D-03) |
| Image/version provenance | `kaggle kernels pull -m` → `kernel_run.json`/`meta.json` | — | Server metadata carries the exact `docker_image` sha256 + `machine_shape` used (D-14) |
| GPU-quota heads-up | `kaggle quota` (non-blocking) | `push_kernel.py` | CLI exposes remaining hours live (D-13) — a real read, not a static reminder |

## Standard Stack

### Core
| Library / Tool | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| `kaggle` CLI | 2.2.3 (installed, verified) `[VERIFIED: kaggle --version, live]` | All kernel ops (push/status/logs/output/pull/quota) | Only primitive that can push kernels + submit; CLAUDE.md mandates it as the sole backbone |
| `jupytext` | 1.16+ `[CITED: CLAUDE.md §Supporting Libraries]` | `.py ⇄ .ipynb` lossless convert (D-02) | CLAUDE.md's declared convert tool; pure-Python, runs under `uv run` |
| `uv` | 0.11.x `[CITED: CLAUDE.md]` | `uv run --no-sync jupytext …` (convert host) | Mirrors `run_local.py`'s `uv run --no-sync` posture exactly |
| Python stdlib | 3.11+ | The 4 new scripts (argparse, json, subprocess, random, time, re) | Skill scripts stay stdlib-only + self-locating (Phase 2/3 contract) |

### Supporting (existing skill code the scripts sit beside / route through)
| Module | Purpose | When to Use |
|--------|---------|-------------|
| `scripts/kaggle_gateway.py → run_kaggle(*argv, timeout)` | The ONE timeout-bounded, no-echo, exit-code CLI runner | Every `kaggle kernels …`/`quota` call MUST route through it (reuse rc==127/rc==124 + `dump_last_error`) |
| `scripts/record_experiment.py` | Recorder Phase 4 EXTENDS (D-12) | Add the log-scan rung + `kernel_error`; do not fork a second recorder |
| `scripts/run_local.py` | Runner posture the push/poll/pull parallel (`--no-sync`, timeout-bounded, exit-code-out) | Copy its `uv run --no-sync` + missing-tool remediation pattern for `convert_notebook.py` |
| `scripts/init_workspace.py → _render_text / create_if_absent / set_config_field` | Template render (`$`-substitution, `safe_substitute`) + idempotent write + config setter | Render `kernel-metadata.json`, write `kernel_run.json`, add a config internet toggle |
| `scripts/templates/experiment.py.tmpl → resolve_data_dir()` | The `/kaggle/input/<slug>` seam | The convert step reuses this file UNCHANGED — the whole point of EXP-05 portability |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `kernel_type: "notebook"` + jupytext convert (D-02, LOCKED) | `kernel_type: "script"` pushing `experiment.py` directly (no convert, no jupytext dep) | Simpler and dependency-free, BUT D-02 explicitly locks the inspectable-notebook path; script-type loses the pre-push inspection seam. Honor D-02; noted only for completeness. |
| Parse `kernels status` text | `kaggle kernels status` has **no** `--format`/JSON | Must parse the `has status "…"` line — see Code Examples. `kernels logs`/`output`/`files`/`quota` DO support `--format json`, but `status` does not (VERIFIED). |
| `enable_gpu: true` (default single GPU) | `--accelerator NvidiaTeslaT4` / `NvidiaTeslaP100` | Explicit accelerator wins over `enable_gpu`. Use `enable_gpu:true` as the guaranteed-valid floor; T4×2 exact string is unverified (see Assumptions Log A1). |

**Installation (workspace ML env — jupytext floor added to the pyproject template, mirroring 03-01's ML floors):**
```bash
# Added to the scaffolded workspace pyproject.toml ML deps (NOT the skill's stdlib scripts):
uv add jupytext>=1.16
```

**Version verification:** `kaggle 2.2.3` verified via `kaggle --version` (live). jupytext version is CLAUDE.md-cited, not re-verified against PyPI this session — planner should `pip index versions jupytext` at implementation time to confirm the current floor.

## Package Legitimacy Audit

No **new external packages** are introduced by the skill's own scripts (stdlib-only). The one
workspace-env dependency is `jupytext`, already sanctioned in CLAUDE.md's verified stack.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| jupytext | PyPI | mature (1.16.x) | high (millions/mo) | github.com/mwouts/jupytext | not run (offline; CLAUDE.md-vetted) | Approved (CLAUDE.md verified stack) `[CITED: CLAUDE.md]` |
| kaggle | PyPI | GA 2.2.3 | high | github.com/Kaggle/kaggle-cli | already installed + live-verified | Approved `[VERIFIED: live]` |

**Packages removed due to slopcheck [SLOP]:** none. **Flagged [SUS]:** none.
*slopcheck was not run (sandboxed/offline). jupytext + kaggle are both from the CLAUDE.md HIGH-confidence verified stack with well-known source repos, so they are treated as CITED, not ASSUMED. The planner should still gate the `uv add jupytext` behind the normal declare/validate/never-runtime-install posture (Phase 2/3).*

## Architecture Patterns

### System Architecture Diagram

```
control/config.json ──(slug, competition.type, internet toggle, execution_target)──┐
                                                                                    │
experiments/exp-NNN/experiment.py  (UNCHANGED from Phase 3 scaffold)                │
        │                                                                           │
        ▼  convert_notebook.py  (uv run --no-sync jupytext --to notebook)           │
experiments/exp-NNN/experiment.ipynb  (build artifact, regenerable)                 │
        │                                                                           │
        ▼  push_kernel.py ◄──────────────────────────────────────────────────────┐ │
   ┌────────────────────────────────────────────────────────────┐                │ │
   │ resolve <username> via `kaggle config view`                 │                │ │
   │ render kernel-metadata.json (id=<username>/<slug>-exp-NNN,  │◄───────────────┼─┘
   │   is_private=true, enable_internet=<config toggle>,         │                │
   │   competition_sources=[<slug>], accelerator=T4/enable_gpu)  │                │
   │ [D-13] kaggle quota  → non-blocking heads-up (never blocks) │                │
   │ kaggle kernels push -p <push-folder>   (run_kaggle)         │                │
   │ write experiments/exp-NNN/kernel_run.json (status=PENDING)  │                │
   └────────────────────────────────────────────────────────────┘                │
        │  (push may fail → fail-closed via gateway rc)                           │
        ▼  poll_kernel.py  (reads kernel_run.json for slug/version)               │
   ┌────────────────────────────────────────────────────────────┐                │
   │ loop: kaggle kernels status <slug>   (run_kaggle)           │                │
   │   parse `has status "KernelWorkerStatus.<NAME>"`            │                │
   │   RUNNING/QUEUED/NEW_SCRIPT/CANCEL_REQUESTED → backoff+retry │                │
   │   COMPLETE/ERROR/CANCEL_ACKNOWLEDGED → terminal, stop        │                │
   │   transient CLI error → tolerate up to threshold            │                │
   │   our-side budget (~2h) expires & still running → DETACH ───┼── re-run poll ─┘
   │     (kernel_run.json.status=PENDING/detached; leave running)│
   └────────────────────────────────────────────────────────────┘
        │  (terminal)
        ▼  pull_kernel.py
   ┌────────────────────────────────────────────────────────────┐
   │ kaggle kernels output <slug> -p exp-dir  → result.json +    │
   │      artifacts/oof.npy + rendered .ipynb (flat files)       │
   │ kaggle kernels logs <slug>  → save to exp-dir/kernel_log.txt│
   │ kaggle kernels pull <slug> -m → docker_image + machine_shape│
   │      → merge into kernel_run.json (D-14 image provenance)   │
   └────────────────────────────────────────────────────────────┘
        │
        ▼  record_experiment.py  (EXTENDED — D-12)
   ┌────────────────────────────────────────────────────────────┐
   │ NEW FIRST RUNG (kernel path): scan kernel_log.txt for       │
   │   Traceback / OOM / process-killed / error markers          │
   │   → hit ⇒ FAILED(kernel_error) BEFORE result.json trusted   │
   │ else → existing D-06 ladder unchanged                       │
   │   (missing_result/schema_invalid/non_finite/out_of_range)   │
   └────────────────────────────────────────────────────────────┘
        │
        ▼  meta.json (canonical) + ledger.jsonl (derived) + VERDICT.md
           + kernel provenance (backend, slug, version, image, internet-effective)
```
*File-to-implementation mapping is in Standard Stack; the diagram shows data flow.*

### Recommended new files
```
scripts/
├── convert_notebook.py          # D-02 .py→.ipynb (uv run jupytext), re-runnable
├── push_kernel.py               # D-04/05/06/07 metadata gen + quota note + push + kernel_run.json
├── poll_kernel.py               # D-08/09/10 bounded backoff poll + detach-not-cancel
├── pull_kernel.py               # output + logs + pull -m (image provenance)
├── record_experiment.py         # EXTENDED (D-11/D-12): +log-scan rung, +kernel_error
└── templates/
    └── kernel-metadata.json.tmpl  # generated per push
```

### Pattern 1: Route every kernel CLI call through the gateway (no-echo, timeout, exit-code)
**What:** `run_kaggle("kernels", "status", slug, timeout=60)` returns `(rc, combined)`. Never echo `combined` (a kernel log / status line can carry competition data or a token-shaped string). Match/parse, then quarantine raw output to `control/raw/` via `dump_last_error` if needed.
**When to use:** All of push/status/logs/output/pull/quota.
```python
# Source: scripts/kaggle_gateway.py (existing) — VERIFIED
rc, out = run_kaggle("kernels", "status", slug, timeout=60)
# rc==127 → CLI missing; rc==124 → timeout; else parse `out` (never print it)
```

### Pattern 2: Discrete idempotent steps with folder-local handoff state (D-01/D-03)
**What:** Each script reads/writes `experiments/exp-NNN/kernel_run.json`; `poll`/`pull` re-derive the kernel slug/version from it, never re-push. Mirrors Phase 3's `scaffold → run → record`.

### Pattern 3: Parse the status enum robustly (no JSON on `status`)
**What:** `kaggle kernels status <slug>` prints `<slug> has status "KernelWorkerStatus.<NAME>"`. Regex-extract the token and map against the authoritative enum. See Code Examples.

### Anti-Patterns to Avoid
- **Grepping case-insensitively for "complete"/"error" (the shepsci exemplar's approach):** brittle — `CANCEL_ACKNOWLEDGED` and a `failure_message` body can contain substrings; match the exact enum token set instead.
- **Trusting `status == COMPLETE` as success:** the silent-failure case. A notebook cell can raise while the session still reports `COMPLETE`. The log scan (D-11) is mandatory.
- **Echoing the pulled log to the terminal:** it's Kaggle-sourced untrusted text and may be large / token-shaped. Save to a file, scan the file, never print raw (mirror `classify_gate`/`dump_last_error`).
- **Deriving an executed path/command from log content:** the D-11 scan is pure pattern-matching (Phase 2 D-02 untrusted-content posture).
- **`enable_internet` left at the CLI template default:** `kaggle kernels init` writes `"enable_internet": "true"` and the SDK `get_bool` defaults it True — you MUST set it `false` explicitly (D-06).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| `.py → .ipynb` conversion | A hand-rolled nbformat cell builder | `jupytext --to notebook` via `uv run` | Lossless, canonical, one line; nbformat hand-assembly reinvents jupytext badly |
| Kernel image/version capture | Regex-scraping the run log for a version banner | `kaggle kernels pull -m` → `docker_image` + `machine_shape` from server metadata | Authoritative exact `gcr.io/kaggle-images/python@sha256:…` pin (VERIFIED in source) — D-14 provenance for free |
| GPU quota read | A static "30h/week" reminder string | `kaggle quota` (live remaining hours + refresh time) | The CLI exposes it (VERIFIED-LIVE) — D-13 can be a real number, not a guess |
| Kernel slug username | Prompting the user / parsing kaggle.json | `kaggle config view` → `username: …` | No-secret, exit-code-clean; the CLI itself prefixes `kernels init` ids with this username (VERIFIED) |
| CLI subprocess plumbing | New subprocess wrappers | `kaggle_gateway.run_kaggle()` | The no-echo/timeout/rc-127/rc-124 contract already exists in one place |
| Result validation on the kernel path | A second recorder | Extend `record_experiment.py` (D-12) | One ladder, one enum — the literal realization of "extend, never re-derive" |

**Key insight:** Almost everything Phase 4 needs already exists as a verified CLI subcommand or an existing skill module. The new code is thin orchestration + one new failure rung.

## Runtime State Inventory

> Phase 4 is a pure code/config addition (new scripts + one config toggle + one template). It creates no rename/migration of existing runtime state, but it DOES introduce new on-Kaggle and on-disk state whose lifecycle the planner must handle.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **On Kaggle:** each pushed kernel is a persistent private notebook `<username>/<slug>-exp-NNN` with auto-versioned history. Re-push updates the same kernel (D-05). | None to migrate; document that abandoned/detached kernels accumulate on the account (deferred: active cancel is out of scope). |
| Live service config | None. `competition_sources` + accelerator + internet flag are all generated per-push from `control/config.json`; nothing lives in a Kaggle UI that git doesn't already drive. | None. |
| OS-registered state | None. | None — verified: no scheduler/daemon registration in the skill. |
| Secrets/env vars | Kaggle credential unchanged (Phase 1 `~/.kaggle/access_token`). `kaggle config view` reads the **username** (non-secret) — never the key. | None; keep no-echo posture. |
| Build artifacts | NEW per experiment: `experiment.ipynb` (from convert), pulled `result.json` + `artifacts/oof.npy` + rendered `.ipynb`, `kernel_log.txt`, `kernel_run.json`. | Planner MUST update the **workspace** `gitignore.tmpl` (NOT the repo `.gitignore`) so pulled artifacts + `kernel_log.txt` are ignored while `kernel_run.json` (small provenance) stays TRACKED. Verify `experiments/*/artifacts/` is already covered. |

**Canonical question answer:** After a push, the only persistent runtime state outside git is the private kernel on Kaggle (tracked by slug+version in `kernel_run.json`) and the weekly GPU quota consumed (readable via `kaggle quota`). Both are recorded, neither needs migration.

## Common Pitfalls

### Pitfall 1: `COMPLETE` status masks a thrown cell (the headline)
**What goes wrong:** Kernel session finishes → status `COMPLETE`, `result.json` may even exist (stale or partial), but a cell raised.
**Why it happens:** Kaggle reports notebook *session* completion independently of *cell* success. Confirmed design premise (CLAUDE.md Open Risk + STATE.md blocker); the `status` object also carries `failure_message`, but only for `ERROR`, not for a cell-raise-under-COMPLETE.
**How to avoid:** D-11/D-12 — scan `kaggle kernels logs` output FIRST; a traceback/OOM/error marker ⇒ `FAILED(kernel_error)` regardless of status or `result.json`.
**Warning signs:** `result.json` present but log contains `Traceback (most recent call last)`.

### Pitfall 2: Status has no structured output; naive substring grep misclassifies
**What goes wrong:** `kaggle kernels status` prints only text; grepping "complete"/"error" catches false substrings or the enum-repr prefix.
**Why it happens:** No `--format` on `status` (VERIFIED). `%s` on the enum renders `KernelWorkerStatus.COMPLETE`.
**How to avoid:** Regex-extract the quoted token, strip a leading `KernelWorkerStatus.`, and map against the exact enum set. Terminal = `{COMPLETE, ERROR, CANCEL_ACKNOWLEDGED}`; in-flight = `{QUEUED, RUNNING, NEW_SCRIPT, CANCEL_REQUESTED}`.
**Warning signs:** Poller exits on a substring match inside a `Failure message: "…"` body.

### Pitfall 3: Transient poll error read as failure (bugs #473/#509)
**What goes wrong:** A 429 / network blip / status-parse hiccup mid-poll is treated as kernel death.
**How to avoid:** D-10 — tolerate transient `run_kaggle` errors (rc!=0 or unparseable) as retryable; only fail-closed after N consecutive failures OR budget expiry. A single blip never terminates the poll.

### Pitfall 4: `enable_internet` defaults true → code-competition invalidation / egress widening
**What goes wrong:** Kernel runs with internet on; a code competition rejects it, or egress silently widens.
**How to avoid:** Set `enable_internet: false` explicitly (D-06); record the effective value in `kernel_run.json` → `meta.json` so an internet-on run is an auditable exception.

### Pitfall 5: T4×2 accelerator string is undocumented
**What goes wrong:** Pushing `--accelerator NvidiaTeslaT4x2` (guessed) is rejected or silently downgrades.
**How to avoid:** Default `enable_gpu: true` (guaranteed valid); expose `--accelerator NvidiaTeslaT4`/`NvidiaTeslaP100` (verified strings). Confirm the exact multi-GPU string with ONE live push before making T4×2 the hard default (Assumptions Log A1).

### Pitfall 6: Pulled output is paginated
**What goes wrong:** A kernel writing >20 output files pulls only the first page.
**Why it happens:** `kernels output` default `page_size=20` (max 200); the API method auto-follows `next_page_token` when `page_token is None` (VERIFIED in source), so the CLI already pages — but a `--file-pattern` or explicit page token changes this.
**How to avoid:** Rely on the default auto-paging; our runs emit few files (`result.json`, `oof.npy`, `.ipynb`), so this is low-risk. Document it.

## Code Examples

### Resolve the username for the D-05 slug (no secret)
```bash
# Source: kaggle 2.2.3 `kaggle config view` — VERIFIED-LIVE
kaggle config view
# → prints:  - username: <username>   (auth_method, path, proxy, competition; NO key)
```
```python
# Parse via run_kaggle; match the `- username: X` line, never echo the buffer.
rc, out = run_kaggle("config", "view", timeout=30)
# username = <the value after "username:">   (kernels init also prefixes ids with it)
```

### kernel-metadata.json (VERIFIED schema from `kaggle kernels init`)
```json
{
  "id": "<username>/<competition-slug>-exp-NNN",
  "title": "<competition-slug>-exp-NNN",
  "code_file": "experiment.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_tpu": false,
  "enable_internet": false,
  "competition_sources": ["<competition-slug>"],
  "dataset_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
```
*`language` ∈ {python,r,rmarkdown}; `kernel_type` ∈ {script,notebook} (VERIFIED). `machine_shape` (optional) or `--accelerator` flag overrides `enable_gpu`/`enable_tpu`.*

### Push with an accelerator + server-side run cap
```bash
# Source: `kaggle kernels push --help` — VERIFIED-LIVE
kaggle kernels push -p <push-folder> --accelerator NvidiaTeslaT4 -t 43200
# -p folder must contain kernel-metadata.json + the code_file (experiment.ipynb)
# -t/--timeout bounds the KERNEL run server-side (distinct from our poll budget, D-08)
```

### Parse status against the authoritative enum
```python
# KernelWorkerStatus (VERIFIED in bundled kagglesdk/kernels/types/kernels_enums.py):
#   QUEUED=0 RUNNING=1 COMPLETE=2 ERROR=3 CANCEL_REQUESTED=4 CANCEL_ACKNOWLEDGED=5 NEW_SCRIPT=6
import re
TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"}
IN_FLIGHT = {"QUEUED", "RUNNING", "NEW_SCRIPT", "CANCEL_REQUESTED"}
_STATUS_RE = re.compile(r'status\s+"(?:KernelWorkerStatus\.)?([A-Z_]+)"')

def classify_status(combined: str) -> str | None:
    m = _STATUS_RE.search(combined)
    return m.group(1) if m else None      # None → transient/unparseable → retry (D-10)
# CLI prints:  <slug> has status "KernelWorkerStatus.COMPLETE"
#   and, on ERROR:  Failure message: "<msg>"
```

### Pull output + log + image provenance
```bash
# Source: kaggle 2.2.3 kernels output/logs/pull --help — VERIFIED-LIVE
kaggle kernels output <slug> -p experiments/exp-NNN --force   # result.json, oof.npy, .ipynb (flat)
kaggle kernels logs   <slug> > experiments/exp-NNN/kernel_log.txt   # full execution log string
kaggle kernels pull   <slug> -m -p /tmp/meta   # regenerates metadata incl. docker_image + machine_shape
```
*`kernels pull -m` server metadata includes `docker_image` (exact `gcr.io/kaggle-images/python@sha256:…`) and `machine_shape` (accelerator used) — VERIFIED in `kaggle_api_extended.py` — the D-14 provenance source.*

### GPU-quota heads-up (D-13, non-blocking)
```bash
# Source: `kaggle quota` — VERIFIED-LIVE (returned GPU 0.00h/30.00h, TPU 0.00h/20.00h, refreshAt ISO)
kaggle quota --format json    # {resource, used, remaining, total, refreshAt}
```

### The D-11 log-scan rung (extends record_experiment.py)
```python
# NEW first rung, kernel path only (D-12). Pure pattern-match; never echo the log.
_KERNEL_ERROR_MARKERS = (
    "Traceback (most recent call last)",   # Python exception
    "\nError:", "\nException:",            # generic runtime error lines
    "Your notebook tried to allocate more memory than is available",  # Kaggle OOM
    "Killed",                              # process-killed / OOM kill
    "Notebook Exceeded",                   # Kaggle resource-limit banner
)
def scan_kernel_log(log_text: str) -> bool:
    return any(marker in log_text for marker in _KERNEL_ERROR_MARKERS)
# hit ⇒ FAILED(kernel_error) BEFORE result.json is read; else fall through to the D-06 ladder.
```
*Exact marker set must be finalized against a real kernel log (Assumptions Log A3) — the log's plain-text-vs-JSON shape is the one format detail needing a live run.*

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Poll by grepping `status` for "complete" (shepsci exemplar) | Match the authoritative `KernelWorkerStatus` enum token | kaggle 2.x | Robust terminal/in-flight classification; resolves STATE.md blocker #473/#509 |
| Parse run log for image banner | `kaggle kernels pull -m` → `docker_image` sha256 | kaggle 2.x | Exact reproducible image pin for D-14 provenance |
| "30h/week" static reminder | `kaggle quota` live remaining hours | kaggle 2.x (`quota` subcommand) | D-13 becomes a real read |

**Deprecated/outdated:**
- The CLAUDE.md "kernel `status` string parsing — exact 2.x strings unconfirmed" Open Risk is now **RESOLVED** by the bundled enum (VERIFIED).
- `--unzip` concern is **N/A** for kernels: `kernels output`/`logs` return individual files/strings, not a zip (VERIFIED — no unzip step needed on the kernel path).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact **T4×2** accelerator string for `--accelerator`/`machine_shape` is undocumented; SDK lists only `NvidiaTeslaT4`/`NvidiaTeslaP100`/`Tpu1VmV38` (single-GPU). D-04's "T4×2 default" cannot be satisfied with a verified string. `[VERIFIED: bundled kagglesdk + GitHub issue #821 — the value is genuinely undocumented]` | Standard Stack / Pitfall 5 | Push rejected or silently single-GPU. Mitigation: default `enable_gpu:true`, confirm T4×2 string via ONE live push before hard-defaulting. **Needs user/live confirmation.** |
| A2 | `kaggle kernels status` renders the enum as `KernelWorkerStatus.<NAME>` under `%s`. `[ASSUMED — from Python enum str() semantics + source; not confirmed against a live kernel]` | Code Examples | Parser misses the token. Mitigation: the regex tolerates both `KernelWorkerStatus.NAME` and bare `NAME`. |
| A3 | `kaggle kernels logs` returns plain text containing `Traceback (most recent call last)` on a cell raise. `[ASSUMED — the API field is `response.log`; exact shape (plain text vs JSON array of {stream_name,data}) unconfirmed without a live run]` | Code Examples / D-11 | Marker scan misses tracebacks. Mitigation: scan should parse-JSON-if-possible then scan concatenated `data`, else scan as text; finalize marker set on first live run. |
| A4 | A notebook cell that raises still yields session status `COMPLETE` (the silent-failure premise). `[CITED: CLAUDE.md Open Risk + STATE.md blocker; ASSUMED at the exact-behavior level]` | Pitfall 1 | If false, D-11 is redundant (harmless); if true, D-11 is essential. Low risk either way. |
| A5 | Kernel CLI ops (push/output/logs/pull) route to `api.kaggle.com` (+ `storage.googleapis.com` for output downloads), both already allowlisted. `[VERIFIED: references/egress-allowlist.md host analysis of CLI 2.2.3 + kagglesdk kaggle_env.py]` | Environment Availability | If a kernel endpoint used a new host, a sandboxed push would prompt/stall. Low risk — same RPC base as Phase 2. |

## Open Questions

1. **Exact T4×2 accelerator string (A1).**
   - What we know: single-GPU strings `NvidiaTeslaT4`/`NvidiaTeslaP100` are SDK-listed; push comment says the full allowed enum "is not currently included in kagglesdk"; GitHub issue #821 asks this exact question, unanswered.
   - What's unclear: the literal for 2×T4.
   - Recommendation: ship `enable_gpu:true` default + `--accelerator NvidiaTeslaT4` override; add a `checkpoint:human-verify` live-push task to discover the T4×2 string, then set it as the D-04 default.

2. **Kernel log format (A3).**
   - What we know: `kaggle kernels logs` returns `response.log` (a string).
   - What's unclear: plain text vs JSON array of log entries.
   - Recommendation: write the scan to handle both; pin the real shape into `kaggle-cli-behavior.md` on the first live run and finalize the D-11 marker set then.

3. **Does `result.json` survive a `COMPLETE`-but-threw run?**
   - What we know: `/kaggle/working` output is pulled regardless of cell success.
   - What's unclear: whether a partial/stale `result.json` is present.
   - Recommendation: irrelevant to correctness — D-12 scans the log FIRST, so `result.json` is never trusted when a traceback is found.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `kaggle` CLI | all kernel ops | ✓ | 2.2.3 | — (blocking; already validated Phase 1) |
| `kaggle` credential | push/status/output | ✓ | access_token (Phase 1 VALIDATED) | — |
| `kaggle quota` | D-13 heads-up | ✓ | live (GPU 30h/TPU 20h) | static reminder if a future CLI drops it |
| `uv` | convert host | ✓ | 0.11.x `[CITED: CLAUDE.md]` | print `uv sync` remediation (like run_local) |
| `jupytext` (workspace env) | convert (D-02) | ✗ (not yet a workspace dep) | 1.16+ target | add to pyproject ML floors; `--no-sync` fails clean with `uv sync` remediation |
| `api.kaggle.com` egress | push/status/output/pull | ✓ allowlisted | — | — |
| `storage.googleapis.com` egress | output download | ✓ allowlisted | — | — |

**Missing dependencies with no fallback:** none (credentials + CLI already validated).
**Missing dependencies with fallback:** `jupytext` — declare in the workspace pyproject ML floors (mirror 03-01); never runtime-install (CLAUDE.md).

## Validation Architecture

> nyquist_validation assumed enabled (no `.planning/config.json` override found for `false`). The headline correctness property — a `COMPLETE`-but-threw kernel is recorded FAILED — is fully testable WITHOUT a live GPU using synthetic fixture logs.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (dev dependency-group, uv.lock committed — Phase 1 01-01) |
| Config file | `pyproject.toml` (skill repo) + existing `tests/` |
| Quick run command | `uv run pytest tests/test_kernel_*.py -x -q` |
| Full suite command | `uv run pytest -q` |
| Live-only marker | reuse the Phase 1/2 live marker (e.g. `-m live --run-live`) for a real push — OUT of the default suite |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXP-05 | `COMPLETE`-but-threw ⇒ FAILED(kernel_error) even with a valid `result.json` | unit (fixture log) | `pytest tests/test_record_kernel.py::test_traceback_beats_valid_result -x` | ❌ Wave 0 |
| EXP-05 | Clean log + valid result ⇒ SUCCESS on kernel path | unit | `pytest tests/test_record_kernel.py::test_clean_log_success -x` | ❌ Wave 0 |
| EXP-05 | OOM / process-killed log ⇒ kernel_error | unit | `pytest tests/test_record_kernel.py::test_oom_marker -x` | ❌ Wave 0 |
| EXP-05 | Status parser maps each enum token → in-flight/terminal | unit | `pytest tests/test_poll_kernel.py::test_status_classify -x` | ❌ Wave 0 |
| EXP-05 | Backoff is exponential+capped, jittered, budget-bounded; transient errors tolerated to threshold | unit (seeded, mocked clock) | `pytest tests/test_poll_kernel.py::test_backoff_budget -x` | ❌ Wave 0 |
| EXP-05 | Our-side timeout with RUNNING ⇒ DETACH (kernel_run.json PENDING), never cancel | unit (mock run_kaggle) | `pytest tests/test_poll_kernel.py::test_detach_not_cancel -x` | ❌ Wave 0 |
| EXP-05 | kernel-metadata gen: internet=false, private=true, competition_sources=[slug], id well-formed | unit (golden) | `pytest tests/test_push_kernel.py::test_metadata_golden -x` | ❌ Wave 0 |
| EXP-05 | Effective internet flag recorded in kernel_run.json → meta (D-06 guard) | unit | `pytest tests/test_push_kernel.py::test_internet_provenance -x` | ❌ Wave 0 |
| EXP-05 | convert is non-destructive/regenerable from experiment.py (D-02) | unit (mock uv) | `pytest tests/test_convert_notebook.py::test_reconvert_idempotent -x` | ❌ Wave 0 |
| EXP-05 | Full push→poll→pull→record loop against a real kernel | integration | `pytest -m live --run-live tests/test_kernel_live.py` | ❌ (opt-in, live) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_kernel_*.py -x -q` (all mocked, < 30s).
- **Per wave merge:** `uv run pytest -q` (full suite green).
- **Phase gate:** full suite green before `/gsd:verify-work`; one opt-in live push run at a human-verify checkpoint to (a) confirm the T4×2 string, (b) pin the real log format + marker set, (c) confirm the status render.

### Wave 0 Gaps
- [ ] `tests/fixtures/kernel_logs/complete_but_threw.txt` — contains `Traceback (most recent call last)`
- [ ] `tests/fixtures/kernel_logs/clean.txt` — no error markers
- [ ] `tests/fixtures/kernel_logs/oom.txt` — Kaggle OOM / `Killed`
- [ ] `tests/fixtures/kernel_logs/nonzero.txt` — process exit / `Notebook Exceeded`
- [ ] `tests/fixtures/status/*.txt` — one capture per enum token (`has status "…"`)
- [ ] `tests/fixtures/kernel-metadata.golden.json` — expected generated metadata
- [ ] `tests/test_record_kernel.py`, `test_poll_kernel.py`, `test_push_kernel.py`, `test_convert_notebook.py`
- [ ] Framework: already present (pytest) — no install needed

## Security Domain

> `security_enforcement` assumed enabled (no config override found). Phase 4 handles Kaggle-sourced text (kernel logs) and network egress, so this is in scope.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Kaggle credential unchanged (Phase 1); `config view` reads username only |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | **yes** | Kernel log + status output are untrusted Kaggle text → pattern-match only, never derive an executed path/command (Phase 2 D-02); slug validated by existing `_SLUG_RE` before it enters the kernel id |
| V6 Cryptography | no | — (no crypto introduced) |
| V7 Error/Logging | **yes** | No-echo: route CLI output through `run_kaggle`, quarantine raw to `control/raw/` (never terminal); leak guard already scans staged content |
| V12 File/Resource | **yes** | Pulled kernel files land under `experiments/exp-NNN/`; keep artifacts gitignored, provenance tracked; explicit-path `git add` (never blanket) so `control/raw/` never staged |

### Known Threat Patterns for the kernel path
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token-shaped string in kernel log/status echoed to terminal | Information Disclosure | `run_kaggle` no-echo + file-quarantine; never print raw log |
| Malicious directive embedded in a kernel log / competition data | Tampering / EoP | D-11 scan is pure pattern-match; no path/command derived from log content |
| `enable_internet: true` widening egress / invalidating a code comp | Tampering | Default false (D-06); effective value recorded as an auditable exception |
| Off-allowlist egress on push | Info Disclosure | `api.kaggle.com` + `storage.googleapis.com` only (both allowlisted); no new host |
| Auto-accept silently approving an off-list prompt | EoP | Documented operational caveat (egress-allowlist.md) — not run under auto-accept when egress matters |
| Blanket `git add` sweeping `control/raw/last-error.txt` | Info Disclosure | Explicit-path staging (existing recorder pattern) |

## Sources

### Primary (HIGH confidence — VERIFIED live this session)
- `kaggle 2.2.3` CLI, installed in project `.venv` — `kernels {push,status,logs,output,pull,init,list,files} --help`, `config view`, `quota`, `quota --help` (all run live).
- Bundled `kagglesdk/kernels/types/kernels_enums.py` — `KernelWorkerStatus` enum values (authoritative).
- Bundled `kagglesdk/kernels/types/kernels_api_service.py` — `machine_shape` supported values (`NvidiaTeslaT4`/`NvidiaTeslaP100`/`Tpu1VmV38`), docstrings.
- Bundled `kaggle/api/kaggle_api_extended.py` — `kernels_status_cli` (`has status "…"` + `Failure message`), `kernels_logs` (`response.log`), `kernels_output` (flat files + auto-paging), `kernels_pull` metadata (`docker_image` + `machine_shape`), `quota_view_cli`, push `enable_internet` default True, `--accelerator → machine_shape` override.
- `kaggle kernels init` generated template — exact kernel-metadata.json field set.
- `references/kaggle-cli-behavior.md`, `references/egress-allowlist.md` — CLI 2.2.3 behavior + allowlisted hosts (`api.kaggle.com`, `storage.googleapis.com`).
- Existing skill code: `kaggle_gateway.py`, `record_experiment.py`, `run_local.py`, `scaffold_experiment.py`, `init_workspace.py`, `templates/experiment.py.tmpl`, `templates/config.json.tmpl`.

### Secondary (MEDIUM confidence)
- CLAUDE.md — stack/version authority (jupytext floor, quotas, accelerator IDs, parity caveats).
- shepsci/kaggle-skill 2.3.0 `poll_kernel.sh` + `kernel-metadata.json` — STRUCTURE-ONLY exemplar (its case-insensitive grep is the anti-pattern we improve on).

### Tertiary (LOW confidence — flagged for live confirmation)
- WebSearch: Kaggle CLI docs / GitHub issue #821 "How to enable GPU T4 x 2 in API?" — confirms the multi-GPU accelerator string is undocumented (A1). https://github.com/Kaggle/kaggle-cli/issues/821 , https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all CLI subcommands + the metadata schema verified live; jupytext CITED from CLAUDE.md.
- Architecture: HIGH — maps directly onto existing Phase 3 patterns + verified CLI surface.
- Pitfalls: HIGH — status enum, no-JSON-on-status, internet default, and pagination all verified in source; silent-failure premise CITED.
- Open items (T4×2 string, exact log shape, status render): MEDIUM/LOW — the precise 3 that require a live GPU push, scoped to a single human-verify checkpoint.

**Research date:** 2026-07-11
**Valid until:** 2026-08-10 (kaggle CLI is GA/stable; re-verify if the CLI minor version bumps).
