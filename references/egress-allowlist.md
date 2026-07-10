# Egress Allowlist — Deny-by-Default Network Scoping (D-08 / D-09)

This document is the **portable specification** of the network egress allowlist that
`init_workspace.py` writes into the scaffolded workspace's `.claude/settings.json`. It
exists so the same deny-by-default posture can be reproduced under opencode, gemini-cli,
a bare shell, or any other runtime that does not read Claude Code settings.

> **The crux (do not get this wrong):** egress for the `kaggle` / `uv` / `pip` / `git`
> CLIs is enforced ONLY by **`sandbox.network.allowedDomains`**. The
> `permissions.allow: WebFetch(domain:…)` rules govern *Claude's own WebFetch tool* and
> do **NOT** constrain what a shell subprocess can reach. A workspace that scopes egress
> with WebFetch permissions alone *looks* protected but leaves the CLI network wide open.

## The two layers written to `.claude/settings.json`

| Layer | Key | What it actually constrains |
|-------|-----|-----------------------------|
| **Primary — OS-level egress** | `sandbox.network.allowedDomains` | Every Bash child process (`kaggle`, `uv`, `pip`, `git`, `curl`). This is the real deny-by-default control that satisfies the "off-allowlist fetch refused" criterion. |
| **Second layer — Claude WebFetch** | `permissions.allow: WebFetch(domain:…)` | Claude's own WebFetch tool only. Complementary; never the CLI egress control. |

`sandbox.enabled` is forced `true` so the sandbox is actually active, and
`sandbox.failIfUnavailable` is set `true` (fail-closed) so that when the sandbox
back-ends (`bubblewrap` + `socat`) are missing, sandboxed commands **fail hard**
instead of falling back to unsandboxed with egress silently open. Both are set on
a fresh workspace and re-applied by the deep-merge into a pre-existing
`.claude/settings.json`.

> **Read this before trusting the allowlist:** the sections below record what was
> **observed** on a live host alongside what the official docs say. After a
> discriminating live probe (2026-07-10) the two now **agree**: an off-allowlist
> host **prompts for approval**, and there is **no undocumented baseline allowlist**
> for the local CLI sandbox. An earlier revision of this file asserted the opposite
> (a silent timeout with "no prompt path"); that was **wrong** and has been
> corrected — see [Correction history](#correction-history) at the end. See also the
> [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing.md).
>
> **⚠️ One thing you must internalize before relying on this:** because enforcement
> for a non-allowlisted host is an **approval prompt**, running this workspace under
> **auto-accept / auto-approve mode silently converts the allowlist from
> deny-by-default to allow-by-default.** See
> [Auto-accept defeats the allowlist](#auto-accept-mode-defeats-the-egress-allowlist).

## Allowed hosts and why each is on the list

| Host | Why it is required |
|------|--------------------|
| `www.kaggle.com` | OAuth / web-flow login and human-facing web URLs (competition pages, the `/competitions/<slug>/rules` acceptance page, the `/settings` phone-verification page). Historically also documented as the `…/api/v1` REST base, but CLI 2.2.3 (kagglesdk) routes its RPC calls to `api.kaggle.com` — see the `api.kaggle.com` row below and [Correction history](#correction-history). |
| `kaggle.com` | Apex host for redirects / web URLs. |
| `api.kaggle.com` | **The CLI 2.2.3 API endpoint host — mandatory for Phase 2.** kagglesdk's `KaggleEnv.PROD` builds `https://api.kaggle.com/v1/{service}/{request}`, so `competitions pages`, `competitions files`, `competitions list`, and `competitions download` (before its 302 → `storage.googleapis.com`) all target this host. VERIFIED-LIVE against CLI 2.2.3 by forcing a proxy failure (`https_proxy=http://127.0.0.1:9`) and reading the target host per command, and confirmed in source (`kagglesdk/kaggle_env.py`). Missing it, a properly sandboxed workspace blocks/prompts every Phase 2 CLI call. |
| `storage.googleapis.com` | **The GCS-backend gotcha (mandatory).** `kaggle competitions download` 302-redirects to signed Google Cloud Storage URLs. An allowlist of just `kaggle.com` silently breaks every competition data download. |
| `*.storage.googleapis.com` | Covers any virtual-hosted-style (`<bucket>.storage.googleapis.com`) GCS variant in addition to the path-style host above. |
| `pypi.org` | Python package index metadata (`uv` / `pip` installs). |
| `files.pythonhosted.org` | The PyPI package **download** backend (wheels/sdists). Both PyPI hosts are needed for an install to complete. |
| `github.com` | Source installs / references pulled from GitHub. |
| `raw.githubusercontent.com` | Raw file fetches from GitHub. |
| `codeload.github.com` | GitHub archive (tarball/zip) downloads. |
| `repo.anaconda.com`, `conda.anaconda.org` | Conda channel package sources (for environments that use conda alongside uv). |

**Deliberately excluded:** Hugging Face / model CDNs. These are added *explicitly* only
when the Phase 4 GPU/DL path needs model weights (see Deferred Ideas) — keeping the
Phase 1 blast radius narrow.

## Wildcard note (`*.` prefix)

`allowedDomains` accepts bare hostnames (`pypi.org`) and `*.`-prefixed wildcards
(`*.storage.googleapis.com`). A wildcard matches **subdomains only, not the apex** — so
when both the apex and its subdomains are used, include both (as done for
`storage.googleapis.com` + `*.storage.googleapis.com`). The automated test asserts exact
required-host membership; runtime wildcard **enforcement** is confirmed by the Task 3
human-verify checkpoint, not by the unit test.

## Enforcement caveats (must be understood before trusting the allowlist)

1. **`socat` and `bubblewrap` are required on Linux.** `bubblewrap` is the unprivileged
   sandboxing tool that enforces filesystem isolation; `socat` is the relay that routes
   network traffic through the sandbox proxy. The network allowlist is only active when
   BOTH are present. When either is missing, Claude Code shows a **WARNING** and (by
   default) runs commands **WITHOUT sandboxing** — so `sandbox.network.allowedDomains` is
   INERT and egress is unenforced. This is a *warned* fallback, **not** a silent one.
   The scaffolded `sandbox.failIfUnavailable: true` converts that fallback into a **hard
   failure**, so a missing back-end surfaces loudly instead of leaving egress open. `init`
   also detects the gap via `shutil.which("socat")` and prints `sudo apt-get install socat`
   (consent-based; it never installs anything). Verify real enforcement after installing
   socat (Task 3). Source: https://code.claude.com/docs/en/sandboxing.md.

2. **Denial mechanism (OBSERVED): an off-allowlist host prompts for approval.** On a live
   host (socat 1.8.0.0 + bubblewrap 0.9.0 present), all Bash-initiated egress traverses an
   authenticated HTTP proxy at `localhost:3128` (via `https_proxy`/`HTTP_PROXY`). When a
   Bash subprocess reaches for a host that is **not** on `allowedDomains`, Claude Code
   **prompts for approval**. Declining denies the request. This matches the official docs:
   for the local CLI Bash sandbox "no domains are pre-allowed. The first time a command
   needs a new domain, Claude Code prompts for approval" — and an approved host is then
   remembered for the rest of the session (since v2.1.191).
   Source: https://code.claude.com/docs/en/sandboxing.md.

   **A stalled proxy CONNECT that times out ("Proxy CONNECT aborted due to timeout") is a
   DENY, not a bypass.** It is what a Bash-initiated fetch looks like when its approval
   prompt goes unanswered: the proxy holds the CONNECT while awaiting the decision, and the
   client eventually gives up. The failure mode is **conservative (fail-safe)** — traffic is
   dropped, not forwarded.

   **There is NO silent-allow path and NO undocumented baseline allowlist for the local CLI
   sandbox.** Off-allowlist traffic reaches its origin only via an **explicit approval**.
   (The large ~100-domain default allowlist that does exist is documented for **Claude Code
   on the web** only, not the local CLI.) Confirmed by the 2026-07-10 discriminating probe —
   see [Empirical enforcement evidence](#empirical-enforcement-evidence).

3. **A true no-prompt hard block needs managed/org settings — NOT enabled here.**
   `sandbox.network.allowManagedDomainsOnly` hard-blocks every non-allowed domain WITHOUT
   prompting, but it only takes effect in **managed/org** settings, not a workspace-level
   `.claude/settings.json` (out of Phase 1 scope, D-09). `allowUnsandboxedCommands: false`
   removes the escape hatch that lets a command opt out of the sandbox. Neither is set by
   the scaffold; they are documented here as the path to a stricter posture. Other related
   settings that exist: `sandbox.network.deniedDomains`,
   `sandbox.network.httpProxyPort` / `socksProxyPort`, and the fail-closed
   `sandbox.failIfUnavailable: true` (which the scaffold DOES set).

## Auto-accept mode defeats the egress allowlist

**This is the single most important operational caveat in this document.**

Enforcement for a non-allowlisted host **is an approval prompt** (see caveat 2). Therefore
any mode that answers prompts automatically — auto-accept / auto-approve / "don't ask
again" — **silently converts the allowlist from deny-by-default to allow-by-default.**

The mechanism, end to end:

1. A Bash subprocess reaches for an off-allowlist host.
2. Claude Code raises a domain-approval prompt.
3. Auto-accept answers it **yes**, without surfacing a decision to you.
4. The approved host is **remembered for the rest of the session** (v2.1.191+), so every
   later fetch to it passes without any further signal.

The allowlist is not bypassed here — it is *consented away*, one prompt at a time, invisibly.
Neither Anthropic's docs nor this project's threat model originally called this out; it was
found empirically (see [Correction history](#correction-history)).

**Mitigations, in order of strength:**

| Control | Effect | Available where |
|---------|--------|-----------------|
| **Do not run this workspace under auto-accept** when egress scoping matters | Restores the prompt as a real decision point | Always — this is the practical guidance |
| `sandbox.network.allowManagedDomainsOnly` | **Hard-blocks** non-allowed domains **without prompting** — immune to auto-accept | **Managed/org settings only.** NOT honored in a workspace `.claude/settings.json`, so the scaffold cannot set it |
| `sandbox.network.deniedDomains` | Explicit denylist; merges across settings scopes | Workspace settings |
| `allowUnsandboxedCommands: false` | Removes the escape hatch that lets a command opt out of the sandbox entirely | Workspace settings (not set by the scaffold) |

Treat "the allowlist is enforced" as true **only** for a session where prompts are actually
being answered by a human.

## This is NOT an exfiltration boundary

The allowlist reduces blast radius. It does **not** stop a determined or compromised
process from leaking data. Treat it as a mitigation, never as containment.

> **Anthropic, verbatim:** "Sandbox isolation reduces the impact of a breach, but it does
> not eliminate risk. Any approach that allows network egress can still leak data the agent
> can read." (https://code.claude.com/docs/en/sandboxing.md)

- **TLS is not terminated by default → domain fronting.** The proxy allow-decides on the
  client-supplied hostname without inspecting the TLS session, so a request can front an
  allowed hostname while reaching a different origin. The experimental
  `sandbox.network.tlsTerminate` (v2.1.199+) can terminate TLS, but even then the proxy
  does **not** inspect payload content. Data can still leave.
- **Our own broad entries are themselves exfiltration paths.** `github.com` (and
  `raw.githubusercontent.com`, `codeload.github.com`) are on the allowlist for legitimate
  installs, but a broad host like `github.com` is a writable, attacker-reachable channel:
  anything the agent can read can be pushed to an attacker-controlled repo/gist under that
  allowed host. Keep such entries as narrow as the use case allows.
- **Net:** the allowlist is a **blast-radius reducer**, not a data-exfiltration boundary.
  This residual risk is accepted (threat T-01-04b).

## Empirical enforcement evidence

Both runs below were made in a Claude Code session rooted at a scaffolded workspace, with
socat + bubblewrap present. All egress went through the `localhost:3128` proxy.

### Run 1 (2026-07-10) — auto-accept mode **ON**

| Host | On declared allowlist? | Result |
|------|------------------------|--------|
| `pypi.org` | yes | HTTP 200 — **allowed** |
| `example.com` | **NO** | HTTP 200, genuine origin content (`cf-ray`, real "Example Domain" body) — **allowed** |
| `neverssl.com` | **NO** | **denied** — "Proxy CONNECT aborted due to timeout" |
| `icanhazip.com` | **NO** | **denied** — "Proxy CONNECT aborted due to timeout" |

At the time, the `example.com` row looked like an allowlist bypass and was recorded as an
UNVERIFIED anomaly.

### Run 2 (2026-07-10) — discriminating probe, auto-accept **OFF**, every prompt **declined**

| Host | On declared allowlist? | Result |
|------|------------------------|--------|
| `example.org` | **NO** | **PROMPTED** for approval |
| `example.net` | **NO** | **PROMPTED** |
| `wikipedia.org` | **NO** | **PROMPTED** |
| `google.com` | **NO** | **PROMPTED** |
| `httpbin.org` | **NO** | **PROMPTED** |

**All five off-allowlist hosts prompted.** None was silently allowed.

### Resolution

Run 2 settles Run 1. There is **no undocumented baseline allowlist** — the docs' "no domains
are pre-allowed" is correct. `example.com` was not a bypass: it was an approval **prompt that
auto-accept answered**, after which the host was remembered for the session (v2.1.191+).
Enforcement was working correctly the whole time.

Conclusions, stated precisely:

- **Deny-by-default holds.** Off-allowlist hosts prompt; declining denies; an unanswered
  prompt stalls the CONNECT and times out (a deny). There is **no silent-allow path**.
- **The only route to an off-list origin is an explicit approval** — which is exactly why
  [auto-accept defeats the allowlist](#auto-accept-mode-defeats-the-egress-allowlist).
- Success criterion 5's host-enforcement half is therefore **MET** ("refused or prompted,
  never silently allowed").

**Residual, UNVERIFIED, non-blocking:** in Run 1, why auto-accept approved `example.com`'s
prompt but did *not* approve `neverssl.com` / `icanhazip.com` (which stalled instead) is
**unknown**. It does not affect the security conclusion, because that divergence fails in the
**conservative** direction (deny), never the permissive one.

## Correction history

This file is a security reference; when it has been wrong, that is recorded rather than
quietly overwritten.

| Date | Claim that was wrong | What overturned it |
|------|----------------------|--------------------|
| 2026-07-10 | An earlier revision asserted the sandbox "silently degrades to unsandboxed" when `socat` is missing. | Official docs: Claude Code emits a **warning** and falls back — visible, not silent. `sandbox.failIfUnavailable: true` was then added to fail closed. |
| 2026-07-10 | A later revision asserted, as an observed finding, that denial "manifests as a stalled CONNECT, **NOT** a prompt" and that there is "no prompt path for Bash-initiated calls." | The Run 2 discriminating probe: **all five** off-allowlist hosts prompted. The earlier session's missing prompts were being consumed by **auto-accept mode**. One session's behavior had been mistaken for the mechanism. |
| 2026-07-10 | The `example.com` result was recorded as an UNVERIFIED anomaly possibly indicating an undocumented pre-allowed host set. | Run 2 showed no baseline exists; `example.com` was an auto-accepted prompt, not a bypass. |
| 2026-07-10 | The `www.kaggle.com` row asserted the API endpoint is `https://www.kaggle.com/api/v1` and that the `api.kaggle.com` host was "stale for the 2.x CLI" and should not be allowlisted. | VERIFIED WRONG for **CLI 2.2.3**: a proxy-failure host probe (`https_proxy=http://127.0.0.1:9`) showed `competitions pages` / `files` / `list` / `download` all target `host='api.kaggle.com'`, confirmed in source (`kagglesdk/kaggle_env.py`: `KaggleEnv.PROD → "https://api.kaggle.com"`; `kaggle_http_client._get_request_url()` builds `https://api.kaggle.com/v1/{service}/{request}`). `api.kaggle.com` was added to the allowlist template and given its own host row; `www.kaggle.com`/`kaggle.com` remain for OAuth + web URLs. Because `write_settings_json` unions `allowedDomains`, re-running `init` retrofits the host onto an existing workspace. |

## Leak-guard override (the documented escape hatch)

`init` installs a pre-commit credential-leak guard (`leak_scan.py` copied to
`.githooks/pre-commit`, wired via `git config core.hooksPath .githooks`). It scans STAGED
content (`git show :<path>`) for Kaggle credential patterns and blocks the commit on a hit.

If you must commit content that legitimately trips the scanner (a false positive), the
documented, non-normalizing override is:

```bash
git commit --no-verify
```

The hook itself never bakes in a bypass — `--no-verify` is the single, explicit,
per-commit escape hatch. Prefer fixing the flagged content over routinely using it.

## Reproducing the allowlist under another runtime (portability)

The allowlist is a **workspace** artifact, not shipped inside the skill package. To
reproduce deny-by-default egress where Claude Code settings are unavailable:

- **opencode / other agents:** apply the same host set to that runtime's network policy /
  proxy configuration (the host list above is the source of truth).
- **Bare shell / CI:** front the `kaggle` / `uv` / `git` calls with an egress proxy
  (e.g. an allowlisting forward proxy) configured with exactly these hosts, or run them
  inside a network namespace that only routes to them.
- **Leak guard:** the guard is plain stdlib Python. Wire it in any git clone with
  `git config core.hooksPath .githooks` (the hook is the copied `leak_scan.py`), or invoke
  `python3 scripts/leak_scan.py` from a shell pre-commit shim (`pre-commit.tmpl`).

The key invariant across runtimes: **the CLI subprocess egress — not just the agent's own
fetch tool — must be constrained to this host set.**
