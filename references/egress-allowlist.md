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
> **observed** on a live host as well as what the official docs say — and they do
> **not** fully agree. Where they diverge, the divergence is flagged **UNVERIFIED**
> rather than smoothed over. See
> [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing.md).

## Allowed hosts and why each is on the list

| Host | Why it is required |
|------|--------------------|
| `www.kaggle.com` | The Kaggle API endpoint is `https://www.kaggle.com/api/v1` (CLI 2.x). Auth, competition metadata, submissions. **Not** `api.kaggle.com` (that host is stale for the 2.x CLI). |
| `kaggle.com` | Apex host for redirects / web URLs. |
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

2. **Denial mechanism (OBSERVED): a stalled proxy CONNECT that times out — no prompt was
   seen.** On a live host (socat 1.8.0.0 + bubblewrap 0.9.0 present), all Bash-initiated
   egress traversed an authenticated HTTP proxy at `localhost:3128` (via
   `https_proxy`/`HTTP_PROXY`). An off-allowlist host was denied by the proxy **stalling
   the CONNECT until the client timed out** ("Proxy CONNECT aborted due to timeout") —
   **not** a fast `403`, and **no interactive permission prompt appeared** for
   Bash-initiated calls. See the empirical table below.

   > **UNVERIFIED — docs vs. observation contradiction.** The official docs state that for
   > the local CLI Bash sandbox "no domains are pre-allowed. The first time a command needs
   > a new domain, Claude Code prompts for approval" (an approved host is then remembered
   > for the rest of the session, since v2.1.191). We did **not** observe a prompt for
   > Bash subprocess egress; denial was a silent timeout. The reason for the discrepancy is
   > **unknown** and is recorded here as UNVERIFIED rather than explained away. (The large
   > ~100-domain default allowlist that exists is documented for **Claude Code on the web**
   > only, not the local CLI — so it does not account for the anomaly below either.)

3. **A true no-prompt hard block needs managed/org settings — NOT enabled here.**
   `sandbox.network.allowManagedDomainsOnly` hard-blocks every non-allowed domain WITHOUT
   prompting, but it only takes effect in **managed/org** settings, not a workspace-level
   `.claude/settings.json` (out of Phase 1 scope, D-09). `allowUnsandboxedCommands: false`
   removes the escape hatch that lets a command opt out of the sandbox. Neither is set by
   the scaffold; they are documented here as the path to a stricter posture. Other related
   settings that exist: `sandbox.network.deniedDomains`,
   `sandbox.network.httpProxyPort` / `socksProxyPort`, and the fail-closed
   `sandbox.failIfUnavailable: true` (which the scaffold DOES set).

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

## Empirical enforcement evidence (live host, socat + bubblewrap present)

Observed in a Claude Code session rooted at a scaffolded workspace (auto-accept mode was ON
in that session). All egress went through the `localhost:3128` proxy.

| Host | On declared allowlist? | Result |
|------|------------------------|--------|
| `pypi.org` | yes | HTTP 200 — **allowed** |
| `example.com` | **NO** | HTTP 200 with genuine origin content (`cf-ray`, real "Example Domain" body) — **ALLOWED** (anomaly) |
| `neverssl.com` | **NO** | **denied** — "Proxy CONNECT aborted due to timeout" |
| `icanhazip.com` | **NO** | **denied** — "Proxy CONNECT aborted due to timeout" |

**Interpretation.** The enforcement path provably works: two off-allowlist hosts were denied
at the proxy while an on-allowlist host was allowed. **But `example.com`, which is NOT on the
declared allowlist, reached its real origin — cause UNKNOWN.** Auto-accept being ON does
*not* explain it, because auto-accept would equally have approved `neverssl.com` and
`icanhazip.com`, which were denied. This is recorded as an **UNVERIFIED anomaly**, not
rationalized.

**Follow-up that would settle it (discriminating probe — NOT yet run):** fetch
`example.org`, `example.net`, `wikipedia.org`, `google.com`, and `httpbin.org` (declining
every prompt) to determine whether an **undocumented pre-allowed set** exists for the local
CLI sandbox, or whether the `example.com` result was a one-off. Until that probe runs, the
host-enforcement half of success criterion 5 is **partially demonstrated, not fully met**.

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
