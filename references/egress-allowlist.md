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

`sandbox.enabled` is forced `true` so the sandbox is actually active.

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

1. **`socat` is required on Linux.** The sandbox network proxy needs both `bubblewrap`
   (usually present) AND `socat`. If `socat` is missing, the sandbox **silently degrades
   to unsandboxed** and the allowlist is INERT — egress is not enforced. `init` detects
   this via `shutil.which("socat")` and prints `sudo apt-get install socat` (consent-based;
   it never installs anything). Verify real enforcement after installing socat (Task 3).

2. **Project settings PROMPT; they do not hard-block.** A workspace-level
   `.claude/settings.json` deny-by-default causes an off-allowlist fetch to be
   **refused/prompted** (not silently allowed) — which satisfies the "refused, not
   silently allowed" criterion. A true *no-prompt* hard block requires
   `allowManagedDomainsOnly` in **managed/org** settings, which is out of Phase 1 scope
   (D-09 locks the workspace-level choice).

3. **TLS is not terminated → residual domain-fronting risk.** The proxy allow-decides on
   the client-supplied hostname without inspecting TLS. Broad hosts (e.g.
   `raw.githubusercontent.com`) therefore widen the blast radius via domain fronting.
   Keep GitHub entries as narrow as the use case allows; hard TLS-aware isolation needs a
   custom proxy and is out of scope. This residual risk is accepted (threat T-01-04b).

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
