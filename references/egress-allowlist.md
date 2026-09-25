# Egress allowlist (opt-in)

kx does **not** write any network policy into a workspace. If you want Claude Code's
sandbox to scope network egress for a competition folder, add the snippet below to
that folder's `.claude/settings.json` yourself.

> **Enforcement is UNVERIFIED.** In v1's live probes (2026-07-10), an off-allowlist
> host (`example.com`) was reached while auto-accept mode was on, and why auto-accept
> approved that host but not others was never explained (the "01-03 example.com
> anomaly"). A later probe with auto-accept off showed every off-list host prompting.
> Treat the allowlist as a convenience, not a security boundary, and never as an
> exfiltration control.

## Snippet

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "network": {
      "allowedDomains": [
        "api.kaggle.com", "www.kaggle.com", "kaggle.com",
        "storage.googleapis.com", "*.storage.googleapis.com",
        "pypi.org", "files.pythonhosted.org"
      ]
    }
  }
}
```

## Why each host

| Host | Needed for |
|------|------------|
| `api.kaggle.com` | Every kx call: kagglesdk builds `https://api.kaggle.com/v1/{service}/{request}`. |
| `www.kaggle.com`, `kaggle.com` | Web URLs and OAuth login. |
| `storage.googleapis.com`, `*.storage.googleapis.com` | Data bundles and kernel outputs are served from signed GCS URLs. |
| `pypi.org`, `files.pythonhosted.org` | `uv sync` of the skill environment. |

`kx research` summaries of public notebooks and discussions go through `api.kaggle.com`
too. Add model hubs (e.g. Hugging Face) only for a deliberate reason; kernels themselves
run with internet off by default and do not use this host list.

## Caveats

- Enforcement for an off-list host is an **approval prompt**. Auto-accept mode answers
  it, which turns deny-by-default into allow-by-default.
- `bubblewrap` and `socat` must be installed for the sandbox to run;
  `failIfUnavailable: true` makes a missing sandbox fail closed.

## Leak guard override

`kx init` installs a pre-commit hook (`.githooks/pre-commit`) that blocks commits
containing Kaggle credential patterns. For a genuine false positive, use
`git commit --no-verify` for that one commit. Prefer fixing the flagged content.
