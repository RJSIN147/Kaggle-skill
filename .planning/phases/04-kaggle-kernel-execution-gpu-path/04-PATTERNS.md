# Phase 4: Kaggle Kernel Execution (GPU Path) - Pattern Map

**Mapped:** 2026-07-11
**Files analyzed:** 12 (4 new scripts, 1 new template, 1 new runtime provenance file, 3 modified files, tests+fixtures)
**Analogs found:** 12 / 12 (every new file has a strong in-repo analog — this phase is a "pure addition" that copies existing conventions)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/convert_notebook.py` | NEW script (build step) | transform (`.py`→`.ipynb` via `uv run`) | `scripts/run_local.py` | exact (both shell `uv run --no-sync`, exit-code-out) |
| `scripts/push_kernel.py` | NEW script (orchestrator) | request-response (metadata gen + CLI push + provenance write) | `scripts/scaffold_experiment.py` (template render + write) + `scripts/kaggle_gateway.py` (CLI) | role-match (render+write) + choke-point |
| `scripts/poll_kernel.py` | NEW script (poller) | event-driven / polling loop | `scripts/run_local.py` (timeout-bounded) + `scripts/kaggle_gateway.py` (`run_kaggle`) | role-match (bounded loop) + choke-point |
| `scripts/pull_kernel.py` | NEW script (fetcher) | file-I/O (CLI output → disk) | `scripts/download_data.py` + `scripts/kaggle_gateway.py` | role-match + choke-point |
| `scripts/templates/kernel-metadata.json.tmpl` | NEW template | config/data | `scripts/templates/meta.json.tmpl` + `config.json.tmpl` | exact (`${...}`/`__X__` placeholder JSON) |
| `experiments/exp-NNN/kernel_run.json` | NEW runtime provenance file | file-I/O (JSON write) | `meta.json` write in `record_experiment.py` (`json.dumps(..., indent=2)+"\n"`) | exact |
| `scripts/record_experiment.py` | MODIFIED (recorder) | CRUD / validation ladder | ITSELF — extend `FAILURE_REASONS` + `_validate_result` ladder | in-place extension |
| `scripts/templates/config.json.tmpl` | MODIFIED (template) | config | ITSELF — add internet toggle leaf | in-place extension |
| `scripts/templates/gitignore.tmpl` | MODIFIED (template) | config | ITSELF — add kernel artifact patterns | in-place extension |
| `SKILL.md` | MODIFIED (docs) | request-response | ITSELF — add scripts-table rows + sequencing | in-place extension |
| `tests/test_kernel_*.py` | NEW tests | test | `tests/test_run_local.py` + `tests/test_record_experiment.py` | exact (subprocess `run_script` fixture) |
| `tests/fixtures/kernel_logs/*`, `tests/fixtures/status/*` | NEW fixtures | test data | existing `tests/fixtures/` + `cv_fixtures.py` | role-match |

---

## Pattern Assignments

### `scripts/convert_notebook.py` (NEW — transform, `uv run` shell-out)

**Analog:** `scripts/run_local.py` (the skill's only other `uv run --no-sync` caller besides `analyze_data.py`).

**Copy the module docstring + portability posture verbatim** (`run_local.py:1-27`): stdlib-only, self-locating via `Path(__file__)`, `--workspace`-driven, argparse-in / exit-code-out, non-interactive.

**Copy the `uv`-absent + `--no-sync` remediation gate** (`run_local.py:106-135`) — this is the load-bearing "declare/validate/never-runtime-install" posture that must wrap the `jupytext` call:
```python
if shutil.which("uv") is None:
    print(
        "workspace ML env not synced — run `uv sync` (uv is not on PATH). "
        "Nothing was run and nothing was recorded.",
        file=sys.stderr,
    )
    return 1
cmd = ["uv", "run", "--no-sync", "python", ...]   # → replace with: uv run --no-sync jupytext --to notebook <exp.py> -o <exp.ipynb>
try:
    proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, timeout=args.timeout)
except subprocess.TimeoutExpired:
    ... return 1
except OSError as exc:
    ... return 1
```
The convert command becomes `uv run --no-sync jupytext --to notebook <exp.py> -o <exp.ipynb>` (RESEARCH Standard Stack). D-02 GUARD: convert must be **non-destructive/regenerable** — mirror `run_local`'s "produce an artifact, don't mutate the source"; jupytext regenerates the `.ipynb` from the unchanged `experiment.py` every call (this is what test `test_reconvert_idempotent` asserts).

**Argparse shape** (`run_local.py:61-79`): `--workspace` (default `Path.cwd()`), `--exp-dir` (required), `--timeout` (default int). Add nothing interactive.

**Exit-code contract:** missing `experiment.py` → clear message + `return 1` (`run_local.py:91-97`); success → `return 0` with a "next step" print naming the produced `.ipynb`.

---

### `scripts/push_kernel.py` (NEW — orchestrator: metadata gen + quota note + push + kernel_run.json)

**Primary analog:** `scripts/scaffold_experiment.py` (render a template with `repr()`/JSON-escaped literals, write it, then advance state). **Choke-point analog:** `scripts/kaggle_gateway.py`.

**Template-render helpers to REUSE (do not re-implement)** — import from `init_workspace` exactly as `scaffold_experiment.py:46-52` does:
```python
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from init_workspace import _render_text, create_if_absent, _iso_now  # noqa: E402
```
`_render_text(template_name, mapping)` (`init_workspace.py:95-102`) does `Template(raw).safe_substitute(mapping)` — the same `$X`/`${X}` substitution used for every template. Render `kernel-metadata.json.tmpl` with it.

**Slug/value hardening (CR-01 defense-in-depth), copy from `scaffold_experiment.py:41,149-158`:**
```python
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# a non-empty slug MUST match before it enters the kernel id (D-05); block, don't guess.
```
The kernel `id` = `<username>/<slug>-exp-NNN` is built ONLY from the config slug + the `config view` username + the exp-dir — never from Kaggle prose (V5 input-validation, Security Domain).

**Route EVERY kaggle call through the gateway** (`kaggle_gateway.py:69-96`) — import `run_kaggle`, `dump_last_error`:
```python
from kaggle_gateway import run_kaggle, dump_last_error
rc, out = run_kaggle("config", "view", timeout=30)          # username resolution (D-05) — never echo `out`
rc, out = run_kaggle("quota", "--format", "json", timeout=30)  # D-13 non-blocking heads-up; ignore failure, NEVER block push
rc, out = run_kaggle("kernels", "push", "-p", push_folder, timeout=...)  # the push
# rc==127 → CLI missing; rc==124 → timeout; on any rc!=0 → dump_last_error(ws, out) and fail-closed (never print `out`)
```
Reserved-exit-code branches (`kaggle_gateway.py:78-96`, `run_local.py` never prints buffers): `127` = CLI absent, `124` = timeout. Quarantine raw output via `dump_last_error(ws, combined)` (`kaggle_gateway.py:236-250`) — never echo a status/quota buffer (it can carry a token-shaped string; Security Domain V7).

**Config read (fail-clear), copy from `run_local._read_slug` (`run_local.py:39-58`) and `scaffold._read_control_json` (`scaffold_experiment.py:55-73`):** read `control/config.json` for `competition_slug`, `execution_target`, and the NEW internet toggle; on corrupt JSON print a fail-clear message and `return 1` with nothing written.

**Write `kernel_run.json`** using the canonical meta write style (`record_experiment.py:339`):
```python
(exp_dir / "kernel_run.json").write_text(json.dumps(kernel_run, indent=2) + "\n")
```
D-06 GUARD: the **effective** `enable_internet` value MUST be a field in `kernel_run.json` so an internet-on run is an auditable exception.

---

### `scripts/poll_kernel.py` (NEW — bounded backoff poller, detach-not-cancel)

**Analog:** `scripts/run_local.py` (timeout-bounded "our patience, never a hang" posture) + `scripts/kaggle_gateway.run_kaggle`.

**Read handoff state from `kernel_run.json`** (Pattern 2, D-01/D-03) — the slug/version are re-derived from the file, NEVER re-pushed. Use the same fail-clear JSON read as `record_experiment._read_json` (`record_experiment.py:67-78`).

**Status classification — copy the RESEARCH-verified enum parser (Code Examples), NOT a case-insensitive grep** (the shepsci anti-pattern, RESEARCH Anti-Patterns):
```python
TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"}
IN_FLIGHT = {"QUEUED", "RUNNING", "NEW_SCRIPT", "CANCEL_REQUESTED"}
_STATUS_RE = re.compile(r'status\s+"(?:KernelWorkerStatus\.)?([A-Z_]+)"')
def classify_status(combined: str) -> str | None:
    m = _STATUS_RE.search(combined)
    return m.group(1) if m else None   # None → transient/unparseable → retry (D-10)
```
`kaggle kernels status` has **no** `--format json` (RESEARCH Alternatives) — must parse the text line.

**Bounded loop with exponential backoff + jitter (D-08/D-10)** — mirror `run_local`'s single-shot `try/except subprocess.TimeoutExpired` bound but as a loop with an overall wall-clock budget (default ~2h, configurable via flag; use `time.monotonic()` + `random.uniform` jitter; stdlib `time`, `random`, `re`). Transient `run_kaggle` errors (rc!=0 or `classify_status`→None) are TOLERATED up to a consecutive-failure threshold; fail-closed only on threshold OR budget expiry (Pitfall 3). A single blip is never kernel death.

**Detach-not-cancel on our-side timeout (D-09):** on budget expiry with an IN_FLIGHT status, write `status="PENDING"`/detached back into `kernel_run.json` (same `json.dumps(..., indent=2)+"\n"` write) and `return` a distinct exit code — NEVER issue a cancel. Re-running `poll` reattaches. (Test: `test_detach_not_cancel` mocks `run_kaggle`.)

**Never echo the status/failure buffer** — same no-echo rule as the gateway; on persistent failure `dump_last_error(ws, out)`.

---

### `scripts/pull_kernel.py` (NEW — output + logs + image provenance)

**Analog:** `scripts/download_data.py` (CLI → files on disk) + `scripts/kaggle_gateway.run_kaggle`.

**Three gateway calls (RESEARCH Code Examples), each via `run_kaggle`:**
```python
run_kaggle("kernels", "output", slug, "-p", str(exp_dir), "--force")   # result.json, oof.npy, .ipynb (flat)
run_kaggle("kernels", "logs",   slug, ...)  # capture response → write exp_dir/kernel_log.txt (NEVER echo)
run_kaggle("kernels", "pull",   slug, "-m", "-p", tmp_meta)  # docker_image + machine_shape → merge into kernel_run.json (D-14)
```
**No `--unzip` step** — kernels output returns flat files, not a zip (RESEARCH State of the Art; contrast `download_data.py` which DOES unzip a competition archive — do NOT copy the unzip logic here).

**Untrusted-content posture (V5/V7):** the pulled log is Kaggle-sourced untrusted text — write it to `exp_dir/kernel_log.txt` and hand the PATH to the recorder; never print it, never derive an executed path/command from its content (mirror `kaggle_gateway`'s D-02 no-derive rule, module docstring `kaggle_gateway.py:22-27`).

**Merge image provenance into `kernel_run.json`** with the read-json → update dict → `json.dumps(..., indent=2)+"\n"` write (same as `push_kernel`), preserving existing keys.

---

### `scripts/templates/kernel-metadata.json.tmpl` (NEW template)

**Analog:** `scripts/templates/meta.json.tmpl` (uses `${EXP_ID}` etc.) and `config.json.tmpl` (uses `__SLUG__`/`__CREATED__`). Use `${...}` placeholders so `_render_text` → `Template.safe_substitute` fills them (`init_workspace.py:95-102`).

**Body — the RESEARCH-VERIFIED schema (`kaggle kernels init` output, RESEARCH Code Examples):**
```json
{
  "id": "${KERNEL_ID}",
  "title": "${TITLE}",
  "code_file": "experiment.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_tpu": false,
  "enable_internet": ${ENABLE_INTERNET},
  "competition_sources": ["${COMPETITION_SLUG}"],
  "dataset_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
```
GUARD (Pitfall 4): `enable_internet` MUST be rendered explicitly (default `false`) — the CLI's own `kernels init` writes `true` and the SDK defaults it True. GUARD (Pitfall 5): default `enable_gpu:true` (guaranteed valid); the exact `T4×2` accelerator string is unverified — expose `--accelerator NvidiaTeslaT4` as an override, not a hard default.

---

### `experiments/exp-NNN/kernel_run.json` (NEW runtime provenance file)

**Analog:** the canonical `meta.json` write in `record_experiment.py:339` and the `meta.json.tmpl` field-block shape. **Write style:** `json.dumps(obj, indent=2) + "\n"`. **D-03 named fields** (kernel slug, version, code_file, push time via `_iso_now()`, competition, accelerator, effective internet flag, detached/PENDING status); Claude's-discretion additional keys (image/version from D-14, pulled/completed state). Keep it small + git-diffable + co-located (it is TRACKED — see gitignore change).

---

### `scripts/record_experiment.py` (MODIFIED — D-11/D-12: add log-scan first rung + one reason)

**Analog:** ITSELF — extend, do NOT fork a second recorder.

**Add exactly one reason to the enum** (`record_experiment.py:59`):
```python
FAILURE_REASONS = ("missing_result", "schema_invalid", "non_finite", "out_of_range", "kernel_error")
```

**Add the log-scan helper (RESEARCH Code Examples, D-11):**
```python
_KERNEL_ERROR_MARKERS = (
    "Traceback (most recent call last)", "\nError:", "\nException:",
    "Your notebook tried to allocate more memory than is available",
    "Killed", "Notebook Exceeded",
)
def scan_kernel_log(log_text: str) -> bool:
    return any(marker in log_text for marker in _KERNEL_ERROR_MARKERS)
```
(pure pattern-match; never echo the log — V5 no-derive.)

**Wire it as the NEW FIRST RUNG in `main()`'s classification block (`record_experiment.py:278-294`)**, kernel path only, gated on a new optional flag (e.g. `--kernel-log <path>`): scan the log FIRST; a hit ⇒ `status="FAILED"`, `failure_reason="kernel_error"`, `valid_result=None` **before `result.json` is read**; otherwise fall through to the EXISTING `run_failed`/`_read_json`/`_validate_result` ladder unchanged. Missing/invalid kernel `result.json` continues to map to the EXISTING `missing_result`/`schema_invalid` reasons (no duplication, D-12). Everything downstream (`_build_provenance`, meta merge, `rebuild_ledger_file`, `_stage_provenance`, VERDICT stub) is reused untouched.

**Add a new argparse flag** following `--run-exit-code` (`record_experiment.py:225-227`): `--kernel-log` (optional path; absent = local path = existing behavior). Also record kernel provenance (backend marker, slug, internet-effective) into the meta — merge from `kernel_run.json`, mirroring how `--run-exit-code` pre-classification threads through.

---

### `scripts/templates/config.json.tmpl` (MODIFIED — D-06 internet toggle)

**Analog:** ITSELF (`config.json.tmpl:1-11`). Add a config-level internet leaf, e.g. inside a `kernel` block: `"kernel": { "enable_internet": false }`. Because `deep_merge_add_missing` only ADDS absent keys, an existing workspace is retrofitted by the merge — but a leaf that must be settable later uses `set_config_field` (`init_workspace.py:475+`), the same setter pattern `analyze_data`/`set_metric` use (enum/bool validated at the argparse `choices` boundary; tooling writes, AI never hand-edits).

---

### `scripts/templates/gitignore.tmpl` (MODIFIED — kernel artifacts ignored, provenance tracked)

**Analog:** ITSELF (`gitignore.tmpl:20-29`, the "Phase 3 experiment artifacts" block). Add: ignore pulled kernel artifacts + `kernel_log.txt`; KEEP `kernel_run.json` TRACKED (small provenance, D-03). The existing block already ignores `experiments/*/artifacts/` and un-ignores `!experiments/*/*.ipynb` + `!experiments/*/meta.json` — add `!experiments/*/kernel_run.json` and an ignore line for `experiments/*/kernel_log.txt` (RESEARCH Runtime State Inventory). NOTE: this is the WORKSPACE `gitignore.tmpl`, not the skill repo `.gitignore`. For an already-scaffolded workspace, retrofit the line via the `_append_line_if_absent` pattern (`kaggle_gateway.py:218-233`) if a script needs to guarantee it at runtime.

---

### `SKILL.md` (MODIFIED — entry-point sequencing + scripts table + D-13 note)

**Analog:** ITSELF. Add four rows to the "Scripts (progressive disclosure)" table (`SKILL.md:281-298`) in the established `| scripts/x.py | EXP-05/D-0N one-line purpose |` style. Add a kernel-path sequencing section mirroring the local loop section (`SKILL.md:217-259`): `convert → push → poll → pull → record`, each `python3 scripts/<x>.py --workspace <cwd> --exp-dir experiments/exp-NNN`, with the SKILL holding the human loop between poll re-runs (D-09 detach/resume). Surface the D-13 quota heads-up and the D-06 internet-effective note. Reuse the reserved-exit-code + gate-protocol prose conventions (`SKILL.md:169-176`).

---

### `tests/test_kernel_*.py` + fixtures (NEW)

**Analogs:** `tests/test_run_local.py` (subprocess invocation via the `run_script` conftest fixture, `uv` shim, seed-config helpers) and `tests/test_record_experiment.py` (recorder ladder assertions).

**Copy the subprocess-invocation pattern** (`test_run_local.py:14,52-64`): `SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"`, drive the script via the `run_script(name, "--workspace", ws, ...)` fixture, assert on `returncode` + absence of fabricated content in stdout. For `run_kaggle`-dependent scripts (poll/push/pull), mock the gateway — either a `kaggle` PATH shim like `_make_uv_shim` (`test_run_local.py:17-22`) or monkeypatch `run_kaggle` for in-process unit tests (backoff/detach are seeded + mocked-clock, RESEARCH Test Map).

**Source-invariant tests** (copy `test_run_local.py:107-117` style): assert `record_experiment.py` source contains `kernel_error` and never echoes the log; assert scripts contain `--no-sync` / route through `run_kaggle`.

**Wave 0 fixtures** (RESEARCH Wave 0 Gaps): `tests/fixtures/kernel_logs/{complete_but_threw,clean,oom,nonzero}.txt`, `tests/fixtures/status/*.txt` (one per enum token), `tests/fixtures/kernel-metadata.golden.json`. Place under existing `tests/fixtures/`.

---

## Shared Patterns

### Route every kaggle CLI call through the gateway (no-echo, timeout, exit-code)
**Source:** `scripts/kaggle_gateway.py:69-96` (`run_kaggle`) + `:236-250` (`dump_last_error`).
**Apply to:** `push_kernel.py`, `poll_kernel.py`, `pull_kernel.py` (all push/status/logs/output/pull/quota calls).
```python
rc, out = run_kaggle("kernels", "status", slug, timeout=60)
# rc==127 → CLI missing; rc==124 → timeout; else parse `out` (NEVER print it).
# on failure worth keeping: dump_last_error(ws, out)  → control/raw/last-error.txt (gitignored)
```

### Self-locating, stdlib-only, --workspace, argparse-in/exit-code-out
**Source:** `scripts/run_local.py:29-79`, `scripts/scaffold_experiment.py:27-52,81-94`.
**Apply to:** all four new scripts.
```python
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
# argparse: --workspace (default Path.cwd()), --exp-dir (required), + step flags
def main(argv=None) -> int: ...
if __name__ == "__main__":
    raise SystemExit(main())
```

### Fail-clear control-JSON reads (never mutate a corrupt file)
**Source:** `scripts/scaffold_experiment.py:55-73` (`_read_control_json`), `scripts/run_local.py:39-58` (`_read_slug`), `record_experiment.py:67-78` (`_read_json`).
**Apply to:** every config/`kernel_run.json` read in the new scripts — corrupt/missing → clear message + non-zero exit + nothing written.

### Template render + create-if-absent + JSON write
**Source:** `scripts/init_workspace.py:95-111` (`_render_text`, `create_if_absent`), `record_experiment.py:339` (canonical `json.dumps(obj, indent=2)+"\n"`), `set_config_field` `init_workspace.py:475+`.
**Apply to:** `kernel-metadata.json.tmpl` render (push), `kernel_run.json` writes (push/poll/pull), config internet-toggle set.

### Explicit-path git staging (never blanket `git add`)
**Source:** `record_experiment.py:172-187` (`_stage_provenance`), `init_workspace.py:47-58` (`SCAFFOLD_COMMIT_PATHS`).
**Apply to:** if any new script stages provenance, stage `kernel_run.json` by explicit path — never `-A` (keeps `control/raw/last-error.txt` unstaged; Security Domain V12).

### Untrusted-content no-derive (V5/V7)
**Source:** `kaggle_gateway.py:22-27` module docstring (never derive an executed path/command/URL from Kaggle text).
**Apply to:** the D-11 log scan (pure pattern-match), status parsing (regex only), kernel id (built from config slug + validated username only).

## No Analog Found

None. Every Phase 4 file maps onto an existing in-repo convention. The only genuinely NEW mechanics (exponential backoff loop, status-enum parsing, log-marker scan) are thin additions inside scripts whose *structure* is fully templated by `run_local.py` / `record_experiment.py` / `kaggle_gateway.py`. The three items needing a live GPU push (T4×2 string, exact log shape, status render) are RESEARCH Assumptions A1/A3/A2 — verified at a single human-verify checkpoint, not blockers for building against the analogs.

## Metadata

**Analog search scope:** `scripts/`, `scripts/templates/`, `tests/`, `SKILL.md`
**Files scanned (read in full or targeted):** `run_local.py`, `kaggle_gateway.py`, `record_experiment.py`, `scaffold_experiment.py`, `init_workspace.py` (helpers), `templates/{config.json,meta.json,gitignore}.tmpl`, `tests/test_run_local.py`, `SKILL.md` (scripts table + sequencing)
**Pattern extraction date:** 2026-07-11
