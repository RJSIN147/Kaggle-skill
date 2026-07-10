#!/usr/bin/env python3
"""download_data.py — credential gate → rules-gate preflight → download → safe extract.

The second of Phase 2's three idempotent entry points (D-09). It downloads the
competition data locally and extracts it into ``data/`` with zip-slip protection
(COMP-03), after clearing the UI-only rules gate (COMP-02) — or failing closed
without EVER busy-looping (criterion 3).

Flow (each step gates the next):

  1. **Credential gate (Phase 1 D-07).** Data download is credential-dependent; it
     refuses unless ``control/state.json.credentials == "VALIDATED"``. A corrupt
     state.json fails clear via :class:`MalformedStateJSON` (never silently
     rewritten — that would reset ``next_exp_id``).
  2. **Slug from config/argv ONLY (D-02).** The competition slug comes from
     ``control/config.json.competition_slug`` (or ``--slug``), NEVER from
     competition text — no executed/printed path or URL is derived from Kaggle
     prose.
  3. **Cheap rules-gate preflight (D-10).** A single
     ``kaggle_gateway.preflight_entered(slug)`` BEFORE any download. On ``False``
     (positively-classified rules gate) it prints the exact rules URL and exits
     ``UI_GATE`` (77). There is NO poll, NO backoff, NO blocking read — the probe
     runs exactly once and the SKILL holds the human loop; the re-invocation's
     preflight IS the verification.
  4. **Download + fail-closed 403 handling (D-11/D-12).** On ``True``/``None`` it
     downloads via the gateway. CLI 2.2.3 has no ``--unzip``, so it pulls a single
     ``<slug>.zip``. A 403 that survives an entered/indeterminate state is
     UNCLASSIFIABLE → fail closed via ``classify_gate`` (names BOTH the rules and
     phone URLs), quarantine the raw CLI output to the gitignored
     ``control/raw/last-error.txt`` (never echoed), and exit ``UI_GATE``.
  5. **Safe extract.** ``safe_extract`` refuses any zip-slip member and writes the
     data into ``data/``.

Portability + safety: stdlib-only, self-locating (``Path(__file__)``),
``--workspace`` argparse in / exit-code out, and NON-INTERACTIVE (no polling, no
blocking reads). Every Kaggle CLI call routes through the D-16 gateway — this
module never forks the subprocess / no-echo / timeout / exit-code contract. It
never runs ``git add -A`` / ``git add control/raw/`` (that would sweep the
quarantined error dump into a commit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import kaggle_gateway as gw  # noqa: E402  (self-locating sys.path insert above)
from check_credentials import MalformedStateJSON  # noqa: E402
from safe_extract import UnsafeArchiveMember, safe_extract  # noqa: E402


# --------------------------------------------------------------------------- #
# Control-plane reads — fail-clear, mirroring how check_credentials writes state.
# --------------------------------------------------------------------------- #
def read_credentials(ws: Path) -> str | None:
    """Return ``control/state.json.credentials`` — fail-clear on corrupt state.

    Reads the same fail-clear way ``check_credentials.write_credentials_state``
    writes: an unparseable/unreadable state.json raises
    :class:`MalformedStateJSON` (the corrupt bytes are preserved and
    ``next_exp_id`` is never reset), never a silent rewrite. A missing file or
    missing key returns ``None`` (→ the caller refuses with remediation).
    """
    state_path = ws / "control" / "state.json"
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise MalformedStateJSON(state_path, exc) from exc
    if not isinstance(data, dict):
        return None
    return data.get("credentials")


def read_slug(ws: Path, override: str | None) -> str | None:
    """Return the competition slug from ``--slug`` or ``control/config.json``.

    The slug is the ONLY variable in the framework-built gate URLs (D-02); it comes
    from argv or config — never from competition text. A missing/corrupt config
    returns ``None`` so the caller refuses cleanly rather than guessing.
    """
    if override:
        return override
    cfg_path = ws / "control" / "config.json"
    if not cfg_path.exists():
        return None
    try:
        data = json.loads(cfg_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict):
        return data.get("competition_slug")
    return None


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def _parse_args(argv):
    ap = argparse.ArgumentParser(
        description="Download + safely extract Kaggle competition data into data/."
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="workspace root holding control/ and data/")
    ap.add_argument("--slug", default=None,
                    help="competition slug override (else control/config.json.competition_slug)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    ws = args.workspace.resolve()

    # 1) Credential gate (Phase 1 D-07): data download is credential-dependent.
    try:
        creds = read_credentials(ws)
    except MalformedStateJSON as err:
        print(
            f"[BLOCKED] {err.path} is not valid JSON and was left untouched "
            f"(fail-clear): {err.exc}. The download was NOT attempted and no state "
            "was rewritten. Fix or remove the file and re-run.",
            file=sys.stderr,
        )
        return 1
    if creds != "VALIDATED":
        print(
            "[BLOCKED] Kaggle credentials are not VALIDATED "
            f"(control/state.json.credentials == {creds!r}). Data download is a "
            "credential-dependent op — run check_credentials.py first, then re-run.",
            file=sys.stderr,
        )
        return 1

    # 2) Slug from config/argv ONLY (never from competition text, D-02).
    slug = read_slug(ws, args.slug)
    if not slug:
        print(
            "[BLOCKED] no competition_slug in control/config.json (and no --slug "
            "given). Set the slug and re-run.",
            file=sys.stderr,
        )
        return 1

    data_dir = ws / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    rules_url = f"https://www.kaggle.com/competitions/{slug}/rules"

    # 3) Cheap rules-gate preflight BEFORE downloading (D-10). ONE probe, no poll,
    #    no backoff, no blocking read — the re-invocation's preflight IS the check.
    entered = gw.preflight_entered(slug)
    if entered is False:
        print(f"[UI_GATE] You have NOT accepted the competition rules for '{slug}'.")
        print(
            f"  Open {rules_url} in a browser, accept the rules, then re-run this "
            "command. The preflight probe on re-run is the verification — nothing "
            "polls or waits here."
        )
        return gw.UI_GATE

    # 4) entered (True) or indeterminate (None) → attempt the download. CLI 2.2.3
    #    has no --unzip, so this pulls a single <slug>.zip.
    rc, combined = gw.run_kaggle("competitions", "download", slug, "-p", str(data_dir))
    if rc != 0:
        # A 403 that survives an entered/indeterminate state is UNCLASSIFIABLE →
        # fail closed (D-12): name BOTH gates, quarantine the raw output (D-11).
        dump_path = gw.dump_last_error(ws, combined)
        print(gw.classify_gate(combined, slug))
        print(
            f"  (raw CLI output quarantined to {dump_path.relative_to(ws)} — "
            "withheld from the terminal to avoid leaking a secret)"
        )
        return gw.UI_GATE

    # 5) Extract the single <slug>.zip safely into data/.
    zip_path = data_dir / f"{slug}.zip"
    if not zip_path.is_file():
        # Fallback: some competitions may name the archive differently — take the
        # sole *.zip if there is exactly one.
        zips = sorted(data_dir.glob("*.zip"))
        if not zips:
            print(
                "[BLOCKED] the download reported success but no .zip archive "
                f"appeared in {data_dir}. Re-run, or inspect the competition "
                "manually.",
                file=sys.stderr,
            )
            return 1
        zip_path = zips[0]

    try:
        members = safe_extract(str(zip_path), str(data_dir))
    except UnsafeArchiveMember as exc:
        print(
            f"[BLOCKED] refused to extract '{zip_path.name}': {exc}. An archive "
            "member tried to escape data/ (zip-slip) — nothing was extracted.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[OK] '{slug}': downloaded and safely extracted {len(members)} file(s) "
        f"into {data_dir.relative_to(ws)}/."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
