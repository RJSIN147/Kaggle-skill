# Phase 4: Kaggle Kernel Execution (GPU Path) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 4-Kaggle Kernel Execution (GPU Path)
**Areas discussed:** Kernel loop shape, kernel-metadata defaults, Polling policy, Silent-failure scan, GPU quota awareness, Environment/version parity

---

## Kernel loop shape

**Loop decomposition**

| Option | Description | Selected |
|--------|-------------|----------|
| Discrete push/poll/pull | Separate re-runnable scripts; resume poll/pull without re-pushing/re-burning GPU. Reuse record_experiment. | ✓ |
| Combined run_kernel | One script does push+poll+pull; fewer scripts but interrupted poll means re-pushing. | |
| You decide | — | |

**Handoff state location**

| Option | Description | Selected |
|--------|-------------|----------|
| In the experiment folder | kernel_run.json in experiments/exp-NNN/; git-diffable, co-located, matches meta.json-canonical. | ✓ |
| In control/state.json | Central, but mixes transient per-run state into global control; one in-flight kernel only. | |
| You decide | — | |

**.py→.ipynb conversion**

| Option | Description | Selected |
|--------|-------------|----------|
| Inside push, 1:1 faithful | push_kernel converts just before upload; .ipynb is a build artifact. | |
| Separate convert step | Standalone convert before push; inspectable before it goes up. | ✓ |
| You decide | — | |

**User's choice:** Discrete push/poll/pull; handoff in the experiment folder (kernel_run.json); separate convert step.
**Notes:** Applied a guard to the separate-convert choice — convert stays mechanical/regenerated from experiment.py so the "same experiment, untouched" seam holds; a deliberate notebook tweak is an intentional, provenance-captured deviation, not the default.

---

## kernel-metadata defaults

**Accelerator**

| Option | Description | Selected |
|--------|-------------|----------|
| T4×2 | Modern most-provisioned tier; same 30h/week cost as P100. | ✓ |
| P100 | Classic single-GPU. | |
| GPU T4 (single) | Lowest footprint. | |
| You decide | — | |

**Kernel id/slug + re-push**

| Option | Description | Selected |
|--------|-------------|----------|
| Stable slug, versioned re-push | Deterministic <username>/<comp-slug>-exp-NNN; re-push updates same kernel (auto-versions). | ✓ |
| Unique slug per push | New slug each push; scatters retries, breaks mapping. | |
| You decide | — | |

**Internet flag**

| Option | Description | Selected |
|--------|-------------|----------|
| Off, explicit opt-in per exp | Always false; on requires deliberate per-experiment override recorded in provenance. | |
| Off, config-level toggle | Default off, flippable globally in config.json. | ✓ |
| You decide | — | |

**Privacy + competition_sources**

| Option | Description | Selected |
|--------|-------------|----------|
| Private + slug from config | is_private=true always; competition_sources from config.json.competition_slug. | ✓ |
| Private, prompt for sources | Private but confirm source each push (friction, slug already in config). | |
| You decide | — | |

**User's choice:** T4×2; stable slug with versioned re-push; internet-off via config-level toggle; private + competition_sources from config slug.
**Notes:** Added a guard to the config-level internet toggle — the effective per-run internet value must be recorded in provenance so an internet-on run stays auditable (a global on-switch is easier to leave on by accident).

---

## Polling policy

**Our-side wait budget**

| Option | Description | Selected |
|--------|-------------|----------|
| ~30 min default, configurable | Covers most GPU experiments; longer needs explicit budget. | |
| ~2 hr default, configurable | More generous for heavier training, still bounded/overridable. | ✓ |
| Match kernel max (~12h) | Effectively unbounded block; fights timeout-bounded posture. | |
| You decide | — | |

**On our-side timeout (kernel still running)**

| Option | Description | Selected |
|--------|-------------|----------|
| Detach, record PENDING, resumable | Leave kernel running, record PENDING, re-run poll to reattach + pull. | ✓ |
| Cancel the kernel | Active remote stop; frees quota but throws away progress. | |
| You decide | — | |

**Backoff shape**

| Option | Description | Selected |
|--------|-------------|----------|
| Exponential w/ cap + jitter | ~10s start, grow to ~60–120s cap, jitter; safest over 2hr. | ✓ |
| Fixed interval | Simple but more 429-prone (tight) or wasteful (loose). | |
| You decide | — | |

**Poll-call errors**

| Option | Description | Selected |
|--------|-------------|----------|
| Tolerate transient, fail-closed on persistent | Retry within budget; give up only if errors persist or budget expires. | ✓ |
| Fail immediately on any poll error | Brittle; single blip aborts a healthy run. | |
| You decide | — | |

**User's choice:** ~2 hr bounded default (configurable); detach-not-cancel on timeout (record PENDING, resumable); exponential backoff + cap + jitter; tolerate transient poll errors, fail-closed on persistent.
**Notes:** Researcher must confirm exact `kaggle kernels status` output shape against a live run (STATE.md blocker; API bugs #473/#509) and prefer structured output.

---

## Silent-failure scan

**Scan depth**

| Option | Description | Selected |
|--------|-------------|----------|
| Traceback + error markers | Python traceback signatures AND error/non-zero-exit/OOM markers; hit ⇒ FAILED even if complete. | ✓ |
| Traceback only | Simplest; misses killed-process/OOM/non-Python failures. | |
| You decide | — | |

**Failure-enum mapping**

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse + add kernel_error | Reuse existing D-06 reasons; add one kernel_error for the silent-failure case. | ✓ |
| Add several kernel-specific reasons | kernel_traceback/kernel_timeout/kernel_no_output/push_rejected; expands enum, overlaps existing. | |
| You decide | — | |

**Scan wiring / ordering**

| Option | Description | Selected |
|--------|-------------|----------|
| Extend record_experiment, scan first | Log scan as new first rung of the D-06 ladder (kernel path); one recorder, one contract. | ✓ |
| Scan in pull_kernel, record consumes verdict | Splits the failure contract across two scripts. | |
| You decide | — | |

**User's choice:** Traceback + error markers; reuse the D-06 enum + add one `kernel_error`; scan lives in record_experiment.py as a first rung (scan → if error FAILED(kernel_error) before result.json is trusted, else the existing ladder).
**Notes:** Researcher confirms actual kernel-log format to finalize the pattern set. This is the literal realization of Phase 3's "extend the contract, never re-derive it."

---

## GPU quota awareness

| Option | Description | Selected |
|--------|-------------|----------|
| Lightweight warn, non-blocking | Best-effort heads-up (30h/week, remaining if exposed); never block the push. | ✓ |
| Nothing in Phase 4 | Ignore quota; all budgeting in Phase 5. | |
| Track + gate now | Build GPU-hour tracking + block over budget (scope creep into Phase 5). | |
| You decide | — | |

**User's choice:** Lightweight, non-blocking heads-up.
**Notes:** Full GPU-budget model deferred to Phase-5-shaped discipline. Researcher checks whether the CLI exposes remaining GPU quota.

---

## Environment/version parity

| Option | Description | Selected |
|--------|-------------|----------|
| Document + record image, don't pin | Document the parity risk; record kernel image/version in provenance so a CV→LB gap can be traced to an env diff. | ✓ |
| Pin versions in-notebook | Inject exact-version installs; fragile, needs internet-on (conflicts with default), slows runs. | |
| You decide | — | |

**User's choice:** Document + record the kernel image/version; do not pin.
**Notes:** Pinning is a Phase-5 CV→LB parity concern; conflicts with the internet-off default until then.

---

## Claude's Discretion

- `kernel_run.json` full schema and detached/PENDING vs completed/pulled state representation.
- Exact `kernel-metadata.json.tmpl` shape (kernel type, language, code_file naming).
- Precise backoff constants (initial/multiplier/cap/jitter) and the persistent-error threshold.
- Exact traceback/error pattern set (finalized against the live kernel-log format).
- Where the quota note and convert step surface in SKILL.md.
- How `<username>` is resolved for the kernel slug.

## Deferred Ideas

- GPU-hour tracking + push gating over a budget — Phase 5 (SCORE-*).
- In-notebook version pinning to match the kaggle/python image — Phase-5 CV→LB parity concern.
- Active remote kernel cancel on timeout — rejected (detach preserves GPU time); revisit if abandoned kernels accumulate.
- Submission from kernel output (code-competition notebook→submission flow) — Phase 5.
- A first-class "author a kernel-only notebook" flow beyond the mechanical convert — not in v1.
