#!/usr/bin/env python3
"""safe_extract.py — zip-slip-protected extraction (reject-and-raise) for COMP-03.

CLI 2.2.3's ``competitions download`` has NO ``--unzip`` flag (VERIFIED-LIVE) — it
pulls a single ``<slug>.zip`` whose members are attacker-controllable — so
``download_data.py`` MUST extract manually. stdlib ``zipfile`` has NO ``filter=``
parameter (only ``tarfile`` gained PEP 706's ``data_filter`` in 3.12) and its
internal member extraction SILENTLY DROPS ``..``/absolute components; a
silently-sanitizing extractor is therefore indistinguishable from a vulnerable one
and impossible to assert refusal against.

This module instead REJECTS every zip-slip vector with a raised
:class:`UnsafeArchiveMember`, and validates EVERY member BEFORE extracting
anything — so a malicious archive leaves the filesystem untouched (nothing is
written outside ``dest``; T-02-PATH-01). ``shutil.unpack_archive`` is deliberately
NOT used: it has no per-member reject hook, so it cannot make refusal observable.

Portability + safety: stdlib-only (``os``, ``stat``, ``zipfile``), self-locating,
and import-safe (a library — importing it has no side effects).
"""

from __future__ import annotations

import os
import stat
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


class UnsafeArchiveMember(Exception):
    """An archive member tried to escape ``dest`` (absolute / ``..`` / symlink / out-of-tree).

    Raised BEFORE any member is written, so a rejection leaves the destination —
    and every sibling directory — untouched. ``download_data.py`` translates this
    into a blocked download rather than a partial, poisoned ``data/``.
    """


def safe_extract(zip_path: str, dest: str) -> list[str]:
    """Extract ``zip_path`` into ``dest``, refusing any member that could escape it.

    Every member is validated FIRST; only once ALL members pass does a single
    :meth:`zipfile.ZipFile.extractall` run — so a malicious archive writes NOTHING
    (a sibling directory stays empty). Rejection rules, each raising
    :class:`UnsafeArchiveMember`:

      1. absolute paths / drive letters (``/etc/evil``, ``C:\\evil``);
      2. a ``..`` path component (classic zip-slip traversal);
      3. symlink members — the mode lives in the high 16 bits of
         ``external_attr``; ``stat.S_ISLNK`` on it detects a symlink entry;
      4. realpath-containment — the member's resolved path must equal ``dest`` or
         live under ``dest`` + separator (defeats normalization tricks rules 1–3
         might miss).

    Returns the list of extracted member names (``ZipFile.namelist()``).
    """
    dest_real = os.path.realpath(dest)
    os.makedirs(dest_real, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            # 1) reject absolute paths / drive letters.
            if name.startswith(("/", "\\")) or os.path.splitdrive(name)[0]:
                raise UnsafeArchiveMember(f"absolute path: {name!r}")
            # 2) reject explicit parent traversal.
            if ".." in name.replace("\\", "/").split("/"):
                raise UnsafeArchiveMember(f"parent traversal: {name!r}")
            # 3) reject symlink members (mode in the high 16 bits of external_attr).
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise UnsafeArchiveMember(f"symlink member: {name!r}")
            # 4) realpath-containment check (defeats normalization tricks).
            target = os.path.realpath(os.path.join(dest_real, name))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                raise UnsafeArchiveMember(f"escapes dest: {name!r}")

        # Safe: every member was pre-validated before a single byte is written.
        zf.extractall(dest_real)
        return zf.namelist()
