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
`https://www.kaggle.com/competitions/<slug>/rules` and `https://www.kaggle.com/settings`
(the phone-verification settings page — see the confirmed-URL note below),
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

### `--format json` is PRETTY-PRINTED, not single-line (2026-07-10, CLI 2.2.3) — VERIFIED-LIVE (02-05)

| Fact | Observation | Consequence |
|------|-------------|-------------|
| `competitions list --search <slug> --format json` **pretty-prints** the array | A live `--search titanic` result is **162 lines**: `[` on line 1, one field per line, `]` on the last line (NOT a single JSON line, and no leading/trailing banner) | A last-line-only parse (`json.loads(out.splitlines()[-1])`) parses just the closing `]` and raises, wrongly returning `None` for **every** slug — silently defeating the entire `preflight_entered` rules-gate classifier (D-10). `kaggle_gateway.preflight_entered` MUST parse the **full** payload. **Fixed in 02-05** (`_parse_json_array`, banner-tolerant); re-pinned by `tests/test_competition_live.py::test_list_search_exposes_user_has_entered`. |

Observed during 02-05's live verification against the read-only `titanic` slug (account already
entered), same sanitized-capture posture (no credential value read or recorded). The 02-01 mock
tests used a **compact** `json.dumps(rows)` stub, so this multi-line shape only surfaced under a
real call — a reminder to pin observed CLI shapes live, not just against a hand-built fixture.

### Phone-verification settings URL (assumption A3) — HUMAN-CONFIRMED (2026-07-10), A3 RESOLVED

**Confirmed at the 02-05 human-action checkpoint (2026-07-10), performed with the user's
explicit consent in a browser:** `https://www.kaggle.com/settings/phone` **returns 404**. The
working phone-verification settings page is **`https://www.kaggle.com/settings`**. The framework
constant is therefore `kaggle_gateway._PHONE_URL = "https://www.kaggle.com/settings"`.

This URL is named — alongside the rules URL — in the D-12 fail-closed message for an
unclassifiable 403, so it is user-facing and must not be a dead link. Assumption A3 (the exact
phone-settings URL, deferred by design because it cannot be produced from a verified account, see
T-02-A1) is now **RESOLVED**. Provenance: human-verified in a browser — no API exists for phone
verification (that is the whole point of the UI-only gate); no credential value was read or
recorded during the check.

## Phase 5 — observed submission / leaderboard signatures (CLI 2.2.3, 2026-07-12)

> **How captured (honest provenance):** Captured 2026-07-12 against CLI 2.2.3 in the project
> `.venv` by (a) `--help`, (b) reading the installed package source
> (`kaggle/cli.py`, `kaggle/api/kaggle_api_extended.py`,
> `kagglesdk/competitions/types/submission_status.py`), and (c) READ-ONLY
> `competitions submissions` / `quota` calls against `titanic`.
> **`competitions submit` was never executed — no submission slot was spent.**
> No credential value was read, printed, or recorded.

### `kaggle competitions submit`

**Invocation shape** [VERIFIED: `--help` + source]

```bash
kaggle competitions submit <slug> -f experiments/exp-007/submission.csv -m "exp-007 | cv=0.84123"
```

| Fact | Observation | Consequence |
|------|-------------|-------------|
| `<slug>` is **POSITIONAL** | Not `-c/--competition` | `submit.py` builds the argv positionally. |
| `-m/--message` is **REQUIRED** | The text **round-trips into `description`** on read-back | ⭐ It is the **ONLY** exp_id↔Kaggle correlation channel, because the CLI **DISCARDS the submission `ref`** the API returns (`competition_submit_cli` returns only `.message`). Put `exp-NNN` in it. |
| `-k/--kernel`, `-v/--version` | Code-competition only; the CLI raises `ValueError` if only one of the pair is given | D-01 refuses the code path → **never passed**. |
| `--sandbox` | ⚠ **TRAP — it is NOT a dry run.** Source + help: *competition hosts/admins only* | **Never** reach for it as a safe test mode. `submit.py --dry-run` (framework-side, prints the argv and calls nothing) is the real dry run. |
| Does submit block until scored? | **No** [VERIFIED: source] — `competition_submit` returns the response immediately; the row appears **PENDING** and is scored asynchronously | The D-03 poller (`fetch_lb.py`) is genuinely needed. |

#### ⚠ THE LOAD-BEARING FINDING: `submit` is **FAIL-OPEN** on its exit code [VERIFIED: installed source]

`kaggle/cli.py::main` sets `error = True` (→ `exit(1)`) for **only** `HTTPError`, `ApiException`
and `ValueError`. Everything else exits **0** — and `competition_submit_cli` **swallows its own
failures before they can propagate**:

| Failure mode | Exit code | Detectable by (verbatim literal, client-hardcoded) |
|--------------|-----------|---------------------------------------------------|
| **Bad/closed competition slug (404)** | **0** ⚠ | stdout literal `Could not find competition` |
| **Upload failed** | **0** ⚠ | stdout literal `Could not submit to competition` |
| Auth failure (401) | 1 | `HTTPError` → stderr |
| Gate / 403 (rules not accepted) | 1 | `403 Client Error: Forbidden` → `classify_gate` → `UI_GATE` (77) |
| Code-comp flags half-given | 1 | `ValueError` |
| **Success** | 0 | a **SERVER-AUTHORED** message string — **UNVERIFIED by design; DO NOT PARSE** |

**Consequence (the posture `submit.py` implements):** `rc == 0` is **NOT proof** that the
submission landed.

1. `rc != 0` → hard failure (classify via the gateway; a 403 → `classify_gate`).
2. `rc == 0` **AND** stdout carries `Could not find competition` or `Could not submit to
   competition` → **failure** (a fail-open lie). Nothing is recorded as spent.
3. Otherwise → **do not assume success.** **CONFIRM BY READ-BACK**: require a NEW
   `competitions submissions` row whose `description` carries our `exp-NNN` and whose `date` is at
   or after the submit start. That row is simultaneously (a) the proof, (b) the only channel that
   yields the Kaggle `ref`, and (c) the first tick of the LB poll.

Structurally identical to Phase 4's "a kernel can report COMPLETE and still have lied" — the same
instinct, reused. The raw buffer is **MATCHED, never echoed** (it can carry a token-shaped string);
it is quarantined to the gitignored `control/raw/last-error.txt`.

### `kaggle competitions submissions <slug> --format json --page-size 200`

| Field | Type in JSON | Notes — all **VERIFIED-LIVE** (2026-07-12, read-only against `titanic`) |
|-------|--------------|--------------------------------------------------------------------------|
| `ref` | **int** | The Kaggle submission id. Recovered here (submit discards it); stored in `control/submissions.jsonl`. |
| `fileName` | str | Basename only (`submission.csv`) — a weak correlator; every experiment uploads the same basename. |
| `date` | str, ISO-8601 | ⚠ **NAIVE — no timezone suffix** (`"2025-09-10T11:29:01.560000"`). See the A1 entry below. |
| `description` | str | ⭐ The `-m/--message` text, round-tripped. **The exp_id correlation channel.** `""` when no message was given. |
| `status` | str | ⚠ **FULLY QUALIFIED**: `SubmissionStatus.PENDING` / `SubmissionStatus.COMPLETE` / `SubmissionStatus.ERROR` — **never bare**. Same trap `poll_kernel.py` solved for `KernelWorkerStatus`: anchor a regex, do not substring-grep. Maps to D-11's vocabulary `PENDING → PENDING`, `COMPLETE → SCORED`, `ERROR → FAILED`. |
| `publicScore` | **str** | ⚠ **A STRING**, not a float (`"0.77511"`), and **`""` when unscored / withheld**. Parse with a guarded `float()`; **never fabricate `0.0`**. |
| `privateScore` | **str** | Same. `""` while the private LB is withheld (the normal case during a live competition). |

**The allow-list is EXACTLY these seven fields** — confirmed by triggering the CLI's own projection error:

```
$ kaggle competitions submissions titanic --format "json(ref,status,errorDescription)"
Unknown field in projection: 'errorDescription'. Allowed fields: date, description, fileName,
privateScore, publicScore, ref, status
```

| Fact | Observation | Consequence |
|------|-------------|-------------|
| **Sort** | Newest-first (`SUBMISSION_SORT_BY_DATE`), and the default group is `SUBMISSION_GROUP_ALL` → **`ERROR` rows ARE returned** | This is what makes D-13's "errors are not charged" rule mechanizable — we can see them and exclude them. |
| **`--page-size`** | default **20**, max **200** | Use `--page-size 200`. |
| ⚠ **`--page-token`** | **UNUSABLE**: `competition_submissions()` returns `response.submissions` and **discards `next_page_token`** — the CLI never prints it, so there is no token to chain | Do **not** attempt pagination. Sort is descending and daily limits are ≤ ~10, so **one page of 200 always covers today**. |
| ⚠ **`errorDescription`** | Exists in the API model but is **NOT exposed** by the CLI (see the projection error above) | A FAILED submission's **reason is not retrievable**. Record `status=FAILED` + `error_description: null` and point the user at the Kaggle submissions page. **Do not fabricate a reason.** |
| ⚠ **NO submission-quota command** | **VERIFIED-LIVE**: `kaggle quota` exists but is **GPU/TPU HOURS ONLY** (`{"resource": "GPU", "remaining": "30.00h", …}`). Nothing anywhere in the CLI 2.2.3 surface reports remaining daily submissions | **The daily submission budget MUST be derived by COUNTING ROWS** (D-04): rows whose `date` falls on today (UTC) and whose status is not `ERROR`. `PENDING` **counts as charged** — the slot was accepted. Fail closed: an unfetchable or unparseable count **blocks**; it is never guessed. |

**`competitions leaderboard` is NOT used.** `submissions` already returns `publicScore` per submission —
which is *our* LB score, the only thing SCORE-01/02 need. `competitions leaderboard` answers a different
question (the public standings of all teams) that no requirement asks. It is deliberately not built.

### Reading the submissions list — one argv, one reader (WR-01, resolved 2026-07-12)

**The argv lives once:** `submissions_log.submissions_argv(slug)` returns the seven live-verified
tokens (`competitions submissions <slug> --format json --page-size 200`). Every caller imports it;
nobody re-types it. `tests/test_submissions_log.py::test_the_submissions_argv_has_exactly_one_home`
enforces that mechanically by grepping `scripts/`.

**The reader is injectable:** `fetch_lb.read_submissions(slug, *, timeout, runner=…)` takes the
gateway as an **argument**.

⚠ **The footgun that made this necessary (kept as a warning, not as code).** `submissions_log.py`
once carried its own `fetch_submissions()` which resolved `run_kaggle` from **its own module
globals** — so a caller who monkeypatched `run_kaggle` in *their* namespace was **silently bypassed
and the real CLI shelled out**, from inside a supposedly-mocked test, against a surface where a
mistake spends an irreversible slot. It accumulated **zero callers** precisely because two
independent plans (05-04, 05-05) each hit the rake and routed around it. It has been **deleted**.
When a Kaggle call needs a seam, **pass the gateway in** — never resolve it from a module global
that the caller cannot reach.

### Assumption A1 — is `submissions.date` UTC? ⏳ **UNRESOLVED — awaiting the first real submission**

<!-- PLACEHOLDER (05-07 Task 3, blocking human-verify checkpoint). Fill from the first real,
     human-supervised submission. Two things go here and NOWHERE else:
       1. THE A1 VERDICT. `date` is a NAIVE ISO string with no tz suffix. The budget model
          (check_submission.py) treats it as UTC and compares against datetime.now(timezone.utc).
          Method: note `date -u` immediately before `submit.py --confirm`, then compare that UTC
          wall-clock to the `date` the read-back returns.
            - MATCH (within submission latency) => `date` IS UTC => **A1 CONFIRMED**.
            - Differs by the local UTC offset  => `date` is LOCAL => **A1 REFUTED** => the budget's
              day boundary is WRONG near midnight (the framework could refuse a submission the user
              is entitled to, or permit one over the limit) => a BLOCKER for correction, not a
              footnote.
          Record: the observed submit-time UTC clock, the returned `date` value, and CONFIRMED/REFUTED.
       2. The `competitions submit` SUCCESS-PATH output (server-authored; deliberately NEVER parsed
          by the code — recorded for this fixture only). Record its SHAPE, not a raw buffer.
     Confidence today: MEDIUM [ASSUMED]. Kaggle's API convention is UTC and the SDK parses a wire
     timestamp, but the tz cannot be proven without spending one real, irreversible slot. -->

**Status:** the framework **assumes UTC** (`datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc)`).
This is the one fact in Phase 5 that **cannot** be established without spending a real submission slot, so it
is gated behind the 05-07 Task 3 human-verify checkpoint and is **not** claimed as verified here.
