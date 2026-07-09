# Observed `kaggle` CLI behavior (credential validation)

> Checked-in fixture for `scripts/check_credentials.py`. Records the **real,
> live-observed** exit codes / output signatures / source precedence of the
> `kaggle` CLI so the checker's remediation branches are grounded in fact, not
> tribal memory (01-04 Task 2 / 01-RESEARCH Open Q1).
>
> **How captured (honest provenance):** the `kaggle` CLI (approved for install at
> the 01-01 Task 1 gate) was installed into a **throwaway venv** — never the
> project `.venv` — and run against `kaggle competitions list` with a **fabricated
> token** in an **isolated temp `HOME`**. No real Kaggle credential was read,
> invoked, or recorded. The fabricated values were stripped from every capture
> before it was written here. The success path (exit 0) requires a real token and
> is therefore **UNVERIFIED** here — it is confirmed only at the 01-04 Task 3
> human-verify checkpoint.

## Environment

| Fact | Value |
|------|-------|
| CLI version | `Kaggle CLI 2.2.3` (`kaggle --version`) |
| Validation command | `kaggle competitions list` (authenticated GET → `www.kaggle.com/api/v1/competitions/list`; prints competition titles, no secrets) |
| Endpoint reachable? | **Yes** — unauthenticated `curl` to the endpoint returned **HTTP 401** (server-side), i.e. off-list egress was not blocking the call in the capture environment |
| Captured on | 2026-07-10, Linux, Python 3.13 throwaway venv |

## Observed exit codes + signatures

| Scenario | How triggered (fabricated / isolated) | Exit code | Where the message lands | Signature string (sanitized) |
|----------|----------------------------------------|-----------|-------------------------|------------------------------|
| **Auth failure — legacy env pair** | `KAGGLE_USERNAME`/`KAGGLE_KEY` = fabricated 32-hex, empty `HOME/.kaggle` | **1** | **stdout** (stderr empty, 0 bytes) | `Authentication required to call the Kaggle API.` |
| **Auth failure — `KAGGLE_API_TOKEN`** | `KAGGLE_API_TOKEN` = fabricated `kagat_…` | **1** | **stdout** (stderr empty) | `Authentication required to call the Kaggle API.` |
| **Auth failure — `access_token` file** | `~/.kaggle/access_token` = fabricated `kagat_…`, chmod 600 | **1** | **stdout** (stderr empty) | `Authentication required to call the Kaggle API.` |
| **Command-not-found** | `kaggle` binary absent from `PATH` | **127** (shell) | stderr | `env: 'kaggle': No such file or directory` |
| **Success (valid token)** | real token | **0** (expected) | stdout: competition titles | **UNVERIFIED — Task 3 checkpoint** |

### Key finding — remediation must scan **stdout**, not just stderr

For every fabricated-credential shape, CLI 2.2.3 writes its human "authentication
required" guidance to **stdout** and leaves **stderr empty**, exiting **1**. A
remediation matcher that inspects only stderr would see nothing. `check_credentials.py`
therefore captures **both** streams and matches the **combined** text (while never
echoing it). The `test_subprocess_output_no_secret` unit test additionally pins the
inverse shape (a stub that writes `401 Unauthorized …` to **stderr**), so the
combined-buffer match covers both landing spots.

### Server vs. client rejection

An unauthenticated `curl` to the same endpoint returns **HTTP 401**, so the wire
protocol does surface a 401. With a *fabricated* token the CLI reports the friendly
"Authentication required" guidance (exit 1) rather than a raw `401` string — i.e.
whether the failure is a client-side pre-flight rejection or the CLI's handling of a
server 401 was **not distinguishable** from these captures. Both map to the same
remediation (supply/regenerate a valid token). The checker matches `401` /
`Unauthorized` / `Forbidden` / `authentication required` (case-insensitive) so it
catches either shape.

## Observed source precedence (refines 01-RESEARCH)

The CLI's own auth-required guidance enumerates the accepted credential inputs as:

1. **OAuth** — `kaggle auth login` (web flow; "credentials are cached locally");
2. **`KAGGLE_API_TOKEN`** env var;
3. **`~/.kaggle/access_token`** file.

It does **not** mention the legacy `KAGGLE_USERNAME` + `KAGGLE_KEY` pair in that
guidance. 01-RESEARCH cited precedence `access_token → env(KAGGLE_USERNAME/KAGGLE_KEY
or KAGGLE_API_TOKEN) → kaggle.json → OAuth`. Observation **refines** this: CLI 2.2.3
foregrounds `KAGGLE_API_TOKEN` / `access_token` / OAuth. Whether a **real** legacy
`KAGGLE_USERNAME`/`KAGGLE_KEY` pair still validates end-to-end is **UNVERIFIED** with a
fabricated key (it failed auth like every other fabricated input) — settle it at the
Task 3 real-token checkpoint. `check_credentials.py` keeps detecting the legacy pair
(D-04 env-canonical, and the unit contract exercises it) but the live truth source is
the exit code, not the source label.

## How `check_credentials.py` uses these facts

- `shutil.which("kaggle") is None` → skip the call; write `credentials=UNVALIDATED`;
  print the `uv pip install kaggle` remediation (the exit-127 case, guarded so the
  checker never crashes — D-07).
- Otherwise run `kaggle competitions list`, capture **both** streams, decide by
  **exit code only** (exit 0 → `VALIDATED`; else `UNVALIDATED`).
- On non-zero, `branch_remediation()` matches the **combined** buffer against the
  signatures above and prints one of four secret-free remediations
  (wrong/missing env var · readable credential file · 401 · unknown). The captured
  buffer is **never** printed, so a token-shaped string inside it cannot leak.

## Sanitization guarantee

Every capture above was produced with a **fabricated** token
(`0123…`-style 32-hex / `kagat_ZZ…`) in a throwaway `HOME`. Fabricated values were
replaced with placeholders before recording. No real credential value appears in this
file, and none was ever surfaced to a log during capture.
