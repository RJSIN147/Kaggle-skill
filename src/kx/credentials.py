"""Credential discovery and masking for `kx init`.

kx never writes, copies, chmods or prompts for a credential. It reports which
source the Kaggle SDK will use, a masked form of it, and a warning with the
exact fix when a credential file is readable by other users.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path


def mask(value: str | None, prefix: int = 0) -> str:
    """First ``prefix`` chars + stars + last 4; short values collapse to ****."""
    if not value or len(value) <= prefix + 4:
        return "****"
    return value[:prefix] + "*" * (len(value) - prefix - 4) + value[-4:]


def token_type(tok: str) -> str:
    if tok.startswith("kagat_"):
        return "OAuth access token"
    if tok.startswith("kagrt_"):
        return "OAuth refresh token"
    if tok.startswith("KGAT_"):
        return "scoped API token"
    if len(tok) == 32 and all(c in "0123456789abcdef" for c in tok.lower()):
        return "legacy API key (32-hex)"
    return "API token"


def _known_prefix(tok: str) -> int:
    """Show only a token's public type prefix (e.g. KGAT_), never secret characters."""
    for p in ("kagat_", "kagrt_", "KGAT_"):
        if tok.startswith(p):
            return len(p)
    return 0


def _config_dir(env) -> Path:
    if env.get("KAGGLE_CONFIG_DIR"):
        return Path(env["KAGGLE_CONFIG_DIR"])
    home = Path(env.get("HOME") or Path.home())
    return home / ".kaggle"


def detect_source(env=None) -> dict:
    """Which credential the SDK will pick up, masked. Never returns a raw secret."""
    env = os.environ if env is None else env
    cfg = _config_dir(env)
    if env.get("KAGGLE_API_TOKEN"):
        tok = env["KAGGLE_API_TOKEN"]
        return {"source": "env:KAGGLE_API_TOKEN", "type": token_type(tok), "masked": mask(tok, _known_prefix(tok))}
    if env.get("KAGGLE_USERNAME") and env.get("KAGGLE_KEY"):
        tok = env["KAGGLE_KEY"]
        return {"source": "env:KAGGLE_USERNAME+KAGGLE_KEY", "type": token_type(tok), "masked": mask(tok)}
    at = cfg / "access_token"
    if at.is_file() and at.stat().st_size > 0:
        try:
            tok = at.read_text().strip()
        except OSError:
            tok = ""
        return {"source": str(at), "type": token_type(tok) if tok else "API token",
                "masked": mask(tok, _known_prefix(tok))}
    kj = cfg / "kaggle.json"
    if kj.is_file():
        try:
            key = str(json.loads(kj.read_text()).get("key") or "")
        except (OSError, json.JSONDecodeError, AttributeError):
            key = ""
        return {"source": str(kj), "type": token_type(key) if key else "API key", "masked": mask(key)}
    return {"source": None, "type": None, "masked": None}


def permission_warnings(env=None) -> list[str]:
    """A warning (with the exact fix) per credential file readable by group/other."""
    env = os.environ if env is None else env
    out = []
    for p in (_config_dir(env) / "access_token", _config_dir(env) / "kaggle.json"):
        try:
            mode = p.stat().st_mode
        except OSError:
            continue
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            out.append(f"{p} is readable by other users; fix with: chmod 600 {p}")
    return out


NO_CREDENTIAL_INSTRUCTIONS = (
    "No valid Kaggle credential was found. Ask the user to create a token at "
    "https://www.kaggle.com/settings (API -> Create New Token), save it to "
    "~/.kaggle/access_token (or set KAGGLE_API_TOKEN), run `chmod 600 ~/.kaggle/access_token`, "
    "then re-run `kx init`. Never paste the token into the chat."
)
