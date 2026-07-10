# Observed `kaggle` CLI behavior (credential validation)

> Checked-in fixture for `scripts/check_credentials.py`. Records the **real,
> live-observed** exit codes / output signatures / source precedence of the
> `kaggle` CLI so the checker's remediation branches are grounded in fact, not
> tribal memory (01-04 Task 2 / 01-RESEARCH Open Q1).
>
> **How captured (honest provenance):** the FAILURE-path signatures below were
> captured by installing the `kaggle` CLI (approved for install at the 01-01 Task 1
> gate) into a **throwaway venv** — never the project `.venv` — and running
> `kaggle competitions list` with a **fabricated token** in an **isolated temp
> `HOME`**. No real Kaggle credential was read for those captures; the fabricated
> values were stripped from every capture before it was written here.
>
> The SUCCESS path (exit 0) was subsequently **confirmed at the 01-04 Task 3
> human-verify checkpoint** (2026-07-10), performed with the user's explicit
> consent: the `kaggle` CLI was installed into the project `.venv`, a real
> `~/.kaggle/access_token` (file source, mode 600) was validated end-to-end, and
> `state.json` flipped to `VALIDATED`. Per the security contract, **no credential
> value was read, printed, or recorded** during that checkpoint — validation is by
> exit code only, and a leak check confirmed the raw token (and any ≥32-char
> token-shaped run) is absent from the transcript.

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
| **Success (valid token)** | real `~/.kaggle/access_token` (file source, mode 600), CLI in project `.venv` | **0** — **VERIFIED** (2026-07-10, 01-04 Task 3 checkpoint) | stdout: competition titles (no secret) | exit **0**; `state.json.credentials` → `VALIDATED`; leak check PASS (no token value / no ≥32-char token-shaped run in transcript) |

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
foregrounds `KAGGLE_API_TOKEN` / `access_token` / OAuth.

**CONFIRMED at the 01-04 Task 3 checkpoint (2026-07-10):** the real-token run used
the **`~/.kaggle/access_token` FILE source** (mode 600) and validated **end-to-end
(exit 0)** — so CLI 2.2.3 provably **honors `~/.kaggle/access_token`**, matching the
precedence chain the checker ranks first. Because a real credential was present in the
`access_token` file, the env sources and `kaggle.json` were not exercised on the
success path (precedence stopped at the file). Whether a **real** legacy
`KAGGLE_USERNAME`/`KAGGLE_KEY` pair still validates end-to-end therefore remains
**UNVERIFIED** — it was never tested with a real pair (the fabricated key failed auth
like every other fabricated input). `check_credentials.py` keeps detecting the legacy
pair (D-04 env-canonical, and the unit contract exercises it) but the live truth source
is the exit code, not the source label.

**Checker `detect_source` ordering (WR-03).** `check_credentials.py` now ranks the
sources `KAGGLE_API_TOKEN` env → `KAGGLE_USERNAME`/`KAGGLE_KEY` env →
`~/.kaggle/access_token` → `~/.kaggle/kaggle.json`, i.e. **env ahead of the
`access_token` file**. This matches the CLI's own guidance for `KAGGLE_API_TOKEN`
(foregrounded above `access_token`, **VERIFIED**) and keeps the module's
"env-canonical (D-04)" label honest; the pre-fix order ranked the `access_token`
file *first* and could mis-report the ACTIVE source when both a file and env vars
were present. **Caveat (honest):** the legacy `USERNAME`/`KEY` pair's precedence
*relative to the `access_token` file* is **UNVERIFIED** — the CLI's guidance never
lists the pair — so for a user who has BOTH a real `access_token` file AND a real
env pair, the reported source label is a best-effort guess; validation itself is by
**exit code only** and is unaffected.

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

## Phase 2 — observed competition-op signatures (CLI 2.2.3, 2026-07-10)

> **How captured (honest provenance):** the competition-op signatures below were
> captured VERIFIED-LIVE against the installed CLI `Kaggle CLI 2.2.3` (project `.venv`,
> Python 3.13) during the Phase 2 research pass. The 403 gate signature was triggered by
> attempting `kaggle competitions download <slug>` for competitions the test account had
> **not** entered (`spaceship-titanic`, `gemini-3`, both `userHasEntered=False`); the
> success/manifest shapes were read from entered competitions. Consistent with the
> sanitization guarantee above, **no credential value was read, printed, or recorded** —
> classification is by exit code + generic (secret-free) signature only. `scripts/kaggle_gateway.py`
> (D-16) consumes these facts the way `check_credentials.py` consumes the credential
> signatures: MATCH the combined buffer, never echo it.

### Observed 403 UI-gate signature (the `classify_gate` table for Phase 2)

| Gate | How detected | Where the message lands / exit | Signature (sanitized) | Confidence |
|------|--------------|-------------------------------|-----------------------|------------|
| **Rules not accepted (preflight)** | `competitions list --search <slug> --format json` → exact-slug `userHasEntered == false` | probe **exit 0**, boolean field | JSON row `{"ref": ".../<slug>", "userHasEntered": false}` | **VERIFIED-LIVE / HIGH** |
| **Rules not accepted (download attempted)** | `competitions download <un-entered-slug>` | **stderr**, **exit 1**, no files pulled | `403 Client Error: Forbidden for url: https://api.kaggle.com/v1/competitions.CompetitionApiService/DownloadDataFiles` | **VERIFIED-LIVE / HIGH** |
| **Phone verification required** | Could not trigger live (test account already verified) → presumed the SAME generic 403; **not distinguishable from the message alone** | stderr `403 …` (assumed) | identical generic `403 … DownloadDataFiles` | **UNVERIFIED / LOW** |
| **Genuine permission / private comp** | Also a generic 403; **not distinguishable** | stderr `403 …` | identical generic `403 … DownloadDataFiles` | **INFERRED / MEDIUM** |

**Load-bearing consequence (D-12 fail-closed):** the download 403 message is **generic** —
it never names *which* gate. So `classify_gate()` positively classifies ONLY the rules gate
(via the cheap `userHasEntered` preflight, which never 403s and never busy-loops). Any 403
that survives an entered / `userHasEntered == true` (or indeterminate `None`) state is
**unclassifiable** → fail closed: exit `UI_GATE` (77), name BOTH
`https://www.kaggle.com/competitions/<slug>/rules` and `https://www.kaggle.com/settings/phone`,
and note it may be a genuine permission error. Never pattern-match "phone" into the 403 string —
it isn't there. The raw combined buffer is quarantined to the **gitignored**
`control/raw/last-error.txt` (D-11), never the terminal.

### Two live-verified CLI facts (2026-07-10, CLI 2.2.3)

| Fact | Observation | Consequence |
|------|-------------|-------------|
| `competitions pages --content` **exists** | `kaggle competitions pages --content --page-name {description,rules,evaluation} --format json` returns full page content | Competition prose is reachable via the CLI (D-15) — no web scraping; `capture_competition.py` ingests it as untrusted content (D-01/D-02). |
| `competitions download` has **NO `--unzip`** | CLI 2.2.3 `download` flags are only `-f/-p/-w/-o/-q`; the artifact on disk is a single `<slug>.zip` | `download_data.py` MUST extract manually with a zip-slip guard (COMP-03) — resolving the CLAUDE.md Open Risk that `--unzip` was "unreliable"; it is simply **absent**. |

Both facts were read from the installed CLI 2.2.3 with the same sanitized-capture posture as
the credential signatures above (no credential value read or recorded).
