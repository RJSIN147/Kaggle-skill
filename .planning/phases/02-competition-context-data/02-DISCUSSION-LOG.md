# Phase 2: Competition Context & Data - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-10
**Phase:** 2-Competition Context & Data
**Areas discussed:** Untrusted-content boundary, CV scheme + adversarial validation, 403 UI-gate flow, Competition-facts scope

---

## Untrusted-content boundary

### Q1 — Where should raw Kaggle-authored page text physically live, and what does the agent read?

| Option | Description | Selected |
|--------|-------------|----------|
| Quarantine raw, curate the doc | Raw payload to `control/raw/` (never auto-loaded). `competition.md` is a curated summary; verbatim prose kept in it is fenced with source attribution. | ✓ |
| Wrap in place, keep everything | `competition.md` embeds full Kaggle page text inline inside markers. One file, nothing lost — but the full payload is re-read every experiment cycle forever. | |
| Wrap at the boundary, persist nothing raw | Gateway prints wrapped text to stdout at capture time only; nothing raw touches disk. | |

**User's choice:** Quarantine raw, curate the doc
**Notes:** Chosen because `competition.md` enters agent context on every cycle from Phase 3 onward — an embedded injection payload would be re-read forever as trusted project documentation.

### Q2 — What is the mechanical defense behind the markers?

| Option | Description | Selected |
|--------|-------------|----------|
| Escape fences + no-derived-execution invariant | `escape_markers()` on ingest so the fence cannot be broken from inside; structural invariant that executed paths/commands come only from `config.json` + argv. Both unit-tested. | ✓ |
| Above + aggressive sanitization | Additionally strip URLs, code fences, imperative lines from curated prose. | |
| Markers only | Wrap + instruct the agent that fenced text is data. | |

**User's choice:** Escape fences + no-derived-execution invariant
**Notes:** Criterion 2 asserts a directive *cannot* drive a path/command/fetch — a convention cannot deliver that, so the guarantee had to be testable. Sanitization rejected: it mangles legitimate content (a real rules URL, an RMSLE formula in a code fence) and creates a redaction ruleset to maintain. Explicitly agreed the defense does **not** claim to stop the model from reading an instruction — only from that instruction reaching an executor.

### Q3 — Should `control/raw/` be tracked in git or gitignored?

| Option | Description | Selected |
|--------|-------------|----------|
| Tracked | `git diff` becomes the "Kaggle amended the rules mid-competition" alarm. Public text, not secret; pre-commit leak guard already scans staged content. | ✓ |
| Gitignored | Local re-fetchable cache; nothing Kaggle-authored enters history. No provenance diff. | |
| Tracked hash manifest, raw ignored | Tracked sha256 + timestamp per page; raw body ignored. See *that* it changed, not *what*. | |

**User's choice:** Tracked
**Notes:** Follow-up finding (recorded in CONTEXT.md, not asked as a question): the tracked/ignored line likely runs *inside* `control/raw/` — provenance artifacts tracked, transient error dumps (`last-error.txt`) gitignored, since those may contain the token-shaped strings that motivated the no-echo rule and would make the leak guard block the next commit.

### Q4 — What happens when `capture_competition` is re-run?

| Option | Description | Selected |
|--------|-------------|----------|
| Safe-merge, mirror init (D-02) | Never overwrites curated edits; re-fetches raw; reports a diff when Kaggle's text changed. | ✓ |
| Refetch and regenerate | Rewrites ingested sections from fresh Kaggle text; destroys hand-written curation. | |
| Refuse if already captured | One-shot unless `--force`. | |

**User's choice:** Safe-merge, mirror init (D-02)
**Notes:** Consistent with the D-02 idempotency contract the whole framework already follows. Combines well with tracked raw — `git diff` on `control/raw/` *is* the change signal.

---

## CV scheme + adversarial validation

### Q1 — Who decides the CV scheme, and who writes it into `config.json`?

| Option | Description | Selected |
|--------|-------------|----------|
| Tooling recommends, AI reasons, tooling writes | Stdlib script emits structural evidence + mechanical recommendation; AI commits to a scheme with rationale; tooling writes the enum-validated field. | ✓ |
| Fully mechanical | Rule table writes `config.json` and the doc; no AI. Deterministic, but mis-splits novel structures silently. | |
| AI decides from a data sample | AI reads the head and writes the field itself. No evidence trail, non-deterministic. | |

**User's choice:** Tooling recommends, AI reasons, tooling writes
**Notes:** Mirrors Phase 3's "numeric fields are written only by tooling, never hand-written by the AI," applied one phase early to a structural fact.

### Q2 — Adversarial validation needs a classifier, but D-14 locks skill scripts to stdlib

| Option | Description | Selected |
|--------|-------------|----------|
| Declare ML floor now, degrade gracefully | Plumbing stays stdlib; analysis step declares pandas+sklearn in the workspace pyproject and runs under `uv run`. ML env absent → stdlib marginal-shift report + `SKIPPED`, exit 0 (D-07 posture). | ✓ |
| Stdlib marginal-shift report only | Per-column KS/PSI. Respects D-14 exactly, but cannot see joint shift — the thing AV exists to catch. | |
| Hand-roll AV in pure Python | ~200 lines of logistic regression + AUC to own and test, in a project that imports sklearn one phase later. | |
| Defer AV to Phase 3 | Roadmap amendment; criterion 1 names an AV finding explicitly. | |

**User's choice:** Declare ML floor now, degrade gracefully
**Notes:** **Amends Phase 1's D-14 — its timing, not its principle.** Skill plumbing remains stdlib-only; only the data-analysis step reaches the workspace ML env. Consequence flagged and accepted: the Kaggle-image version-parity risk (CLAUDE.md's primary CV→LB parity risk) arrives one phase earlier than the roadmap assumed, so floors must be chosen against the `kaggle/python` image rather than newest PyPI majors. The AV-vs-marginal-shift distinction (joint vs marginal) was the deciding argument.

### Q3 — Capture needs data for half its job and no data for the other half

| Option | Description | Selected |
|--------|-------------|----------|
| Split capture into two stages | Three idempotent entry points: capture (no data) → download (needs creds) → analyze (needs data). | ✓ |
| One orchestrator over the same three stages | Same split, single `setup_competition` command chaining them; must handle partial failure. | |
| Reorder: download first, then capture once | Simplest, but a 403 or a 20 GB dataset leaves `competition.md` empty despite metric/rules being freely readable. | |

**User's choice:** Split capture into two stages
**Notes:** Corrects the roadmap's suggested plan order (02-02 before 02-03). No orchestrator wrapper. A 403 on download never costs the metric and rules.

---

## 403 UI-gate flow

### Q1 — Where does the waiting happen?

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct exit code; the skill holds the human loop | Cheap preflight probe; on a gate, print URL + exit reserved code (77). SKILL.md has Claude surface the URL, wait for confirmation, re-invoke. The re-invocation's probe *is* the verification. | ✓ |
| Script prompts on stdin and probes once | Breaks the non-interactive contract; hangs under non-TTY; needs stdin mocking to test. | |
| Bounded poll with backoff | Criterion 3 says never busy-loop; burns authenticated calls against an absent user. | |

**User's choice:** Distinct exit code; the skill holds the human loop
**Notes:** Preserves the Phase 1 contract that every script is argparse-in / exit-code-out. Nothing polls; nothing blocks on stdin; the agent is the only thing that ever waits.

### Q2 — What does the framework do with the Kaggle CLI's failure output?

| Option | Description | Selected |
|--------|-------------|----------|
| Classify, author our own message, quarantine the raw | Match signatures (the `branch_remediation` pattern), print framework-authored secret-free instruction, write raw to `control/raw/` for audit. | ✓ |
| Classify and author; discard the raw | Provably leak-free, but an unclassified 403 leaves nothing to debug with. | |
| Echo the CLI text, wrapped in untrusted markers | Best diagnostics; reopens the leak vector Phase 1 closed (CLI prints auth guidance to stdout). | |

**User's choice:** Classify, author our own message, quarantine the raw
**Notes:** One mechanism honors both Phase 1's no-echo invariant and this phase's quarantine boundary. Prompted the `last-error.txt` tracked-vs-ignored finding above.

### Q3 — A 403 arrives that matches no known signature

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed, name both gates | State that classification failed; print both the rules URL and the phone-verification URL; note it may be a genuine permission error. | ✓ |
| Assume rules acceptance | Right most of the time; sends phone-unverified users to the wrong page and mislabels real permission errors. | |
| Treat as a hard failure, no instruction | Never misleads, but offers no path forward on an unrecorded gate variant. | |

**User's choice:** Fail closed, name both gates
**Notes:** Mirrors `check_credentials.py`'s honest fall-through branch.

---

## Competition-facts scope

### Q1 — The daily submission limit exists only in rules prose. What if it cannot be extracted?

| Option | Description | Selected |
|--------|-------------|----------|
| Never guess; UNKNOWN is a first-class value | Write `null`; Phase 5's budget gate refuses to submit until a human sets it. | |
| Default to 5/day, overridable | Zero friction; Phase 5 rations against a fabricated number, silently. | |
| Ask the user at capture time | Distinct exit code; the skill asks the user to read the rules page and supply the number. | ✓ |

**User's choice:** Ask the user at capture time
**Notes:** Uses the same reserved-exit-code mechanism as the 403 gate (scripts never block on stdin). Opened a follow-up gap — what if the user can't answer — asked as Q3 below.

### Q2 — Should Phase 2 capture the code-competition type flag Phase 5 needs?

| Option | Description | Selected |
|--------|-------------|----------|
| Capture now; UNKNOWN blocks the CSV path | `config.json` enum `competition.type ∈ {csv, code, unknown}`, AI-classified from rules text + files listing, tooling-written. | ✓ |
| Capture opportunistically, never block | Phase 5 discovers the truth at submit time — at the cost of a submission attempt. | |
| Defer entirely to Phase 5 | Phase 5 must then re-solve this phase's untrusted-ingest problem without capture machinery. | |

**User's choice:** Capture now; UNKNOWN blocks the CSV path
**Notes:** Closes the hook STATE.md flagged: *"Phase 5: code-competition submission path … may need a competition-type flag captured in Phase 2."*

### Q3 — The user doesn't know the limit, declines, or the script runs non-interactively

| Option | Description | Selected |
|--------|-------------|----------|
| Write null, record UNKNOWN, Phase 5 refuses | Best-effort ask, not a precondition; `capture_competition` exits 0 (D-07 posture). | |
| Block capture until answered | One unparseable line of prose blocks the metric, schema, and CV scheme too. | |
| Fall back to 5/day | Setup always completes with a usable number; `config.json` holds a fabricated integer Phase 5 rations against. | ✓ |

**User's choice:** Fall back to 5/day
**Notes:** The composed policy is **extract → ask the human → assume 5/day** — the default now sits *behind* a human gate rather than in front of one, which is meaningfully different from the rejected Q1 option. Claude flagged the residual risk: a fabricated `5` is byte-identical to an extracted `5`, so Phase 5 would enforce a fabricated budget with full confidence. Mitigation recorded as **non-negotiable** in CONTEXT.md D-13: `limit_provenance ∈ {extracted, user-supplied, assumed_default}` must accompany the value, and `competition.md` must render an assumed value as *"5/day (assumed — not confirmed against the rules page)"*. Phase 5's policy response to an assumed budget is correctly deferred to Phase 5.

---

## Claude's Discretion

- Data-download behavior — size guard before a large pull, keep-or-delete the zip, re-run semantics when `data/` is populated.
- Zip-slip implementation details (member path resolution, absolute paths, `..` traversal, symlink members) — must be tested with a malicious-archive fixture.
- The exact cheap gate-probe command.
- The AUC threshold that makes an AV finding actionable (~0.7–0.8 conventionally).
- Row-sampling caps for `cv_evidence.py` / AV on large datasets.
- Reserved exit-code numbering (77 is a suggestion).
- Schema capture depth (dtypes, row counts, null rates, cardinality).

## Deferred Ideas

- Hugging Face / model-CDN egress hosts — Phase 4's GPU/DL path (carried forward from Phase 1).
- Phase 5's policy response to `limit_provenance == "assumed_default"` — warn, refuse the last slot, or demand confirmation. Phase 2 only records the provenance truthfully.
- Adversarial-validation-driven CV strategy (fold reweighting, test-mimicking validation sets) — Phase 3+ experiment design.
- Migrating an already-scaffolded workspace's `.gitignore`, given Phase 1's create-if-absent semantics.
- Kaggle-image version-parity verification — made newly urgent by the D-06 amendment, but the full check belongs with Phase 4's kernel path.

## Live CLI findings recorded during discussion

Verified against `Kaggle CLI 2.2.3` on 2026-07-10 (local `--help` inspection, no network):

- `kaggle competitions pages --content --page-name {description,rules,evaluation} --format json` **exists** — competition prose is reachable through the CLI, so no web scraping is needed and CLAUDE.md's "CLI as sole primitive" holds.
- `kaggle competitions download` has **no `--unzip` flag** (only `-f/-p/-w/-o/-q`). This resolves the STATE.md open concern *"`competitions download --unzip` reliability on CLI 2.x needs direct verification"* — it does not exist, so manual extraction is mandatory, which is exactly why criterion 4 demands zip-slip protection.
