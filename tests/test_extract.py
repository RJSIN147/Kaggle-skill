"""Zip-slip reject-and-raise contract for scripts/safe_extract.py (COMP-03 / C4).

stdlib ``zipfile`` has NO ``filter=`` param (only ``tarfile`` got PEP 706) and its
internal member extraction SILENTLY DROPS ``..``/absolute components — so a
"silently sanitized" extractor is indistinguishable from a vulnerable one. This
phase therefore REJECTS every zip-slip vector with a raised ``UnsafeArchiveMember``
and validates ALL members BEFORE writing anything, so refusal is assertable and a
malicious archive leaves the filesystem untouched (T-02-PATH-01).

The module is imported INSIDE each test (via ``_se()``) so collection never
crashes while ``scripts/safe_extract.py`` is absent (RED) — the tests fail cleanly
(ModuleNotFoundError) instead of aborting collection, matching the conftest
"never import a not-yet-built script at module top" rule.
"""

import importlib
import os
import zipfile
from zipfile import ZipInfo

import pytest


def _se():
    """Import scripts/safe_extract.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("safe_extract")


# --------------------------------------------------------------------------- #
# Malicious-member builders — each returns a callable that writes ONE zip-slip
# vector into a fresh ZipFile. Kept as separate archives so each vector's refusal
# (and the no-file-escaped guarantee) is asserted in isolation.
# --------------------------------------------------------------------------- #
def _build_parent_traversal(zf):
    """Classic zip-slip: a ``..`` component climbing out of dest."""
    zf.writestr("../../evil.txt", "pwned")


def _build_absolute(zf):
    """An absolute member path — extracts to ``/etc`` on a naive extractor."""
    zf.writestr("/etc/evil.txt", "pwned")


def _build_symlink(zf):
    """A symlink member (mode stored in the high 16 bits of external_attr)."""
    zi = ZipInfo("link")
    zi.external_attr = (0o120777 << 16)  # S_IFLNK | 0777
    zf.writestr(zi, "/etc/passwd")


def _build_nested_traversal(zf):
    """A deeply-nested path that normalizes out of dest via repeated ``..``."""
    zf.writestr("a/b/../../../../evil", "pwned")


_MALICIOUS = {
    "parent_traversal": _build_parent_traversal,
    "absolute": _build_absolute,
    "symlink": _build_symlink,
    "nested_traversal": _build_nested_traversal,
}


def _write_zip(path, build):
    with zipfile.ZipFile(path, "w") as zf:
        build(zf)
    return path


@pytest.mark.parametrize("vector", sorted(_MALICIOUS))
def test_malicious_member_is_rejected(tmp_path, vector):
    """Each zip-slip vector raises UnsafeArchiveMember and writes nothing outside dest."""
    se = _se()
    dest = tmp_path / "dest"
    dest.mkdir()
    sibling = tmp_path / "sibling"  # a peer of dest that MUST stay empty
    sibling.mkdir()
    zpath = _write_zip(tmp_path / f"{vector}.zip", _MALICIOUS[vector])

    with pytest.raises(se.UnsafeArchiveMember):
        se.safe_extract(str(zpath), str(dest))

    # No file escaped: dest is empty (validate-before-write) and the sibling — a
    # peer dir the traversal could have reached — is untouched.
    assert os.listdir(dest) == []
    assert os.listdir(sibling) == []
    # And the specific escape target never materialized above dest.
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "evil").exists()


def test_no_file_escapes_across_all_vectors(tmp_path):
    """C4 aggregate: after attempting every malicious archive, the tree stays clean."""
    se = _se()
    dest = tmp_path / "dest"
    dest.mkdir()
    for vector, build in _MALICIOUS.items():
        zpath = _write_zip(tmp_path / f"{vector}.zip", build)
        with pytest.raises(se.UnsafeArchiveMember):
            se.safe_extract(str(zpath), str(dest))
    # Nothing extracted anywhere under dest, and no escape artifact beside it.
    assert os.listdir(dest) == []
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "evil").exists()


def test_benign_archive_extracts_cleanly(tmp_path):
    """A well-formed archive (flat + nested members) extracts and returns its names."""
    se = _se()
    dest = tmp_path / "dest"

    def _benign(zf):
        zf.writestr("train.csv", "a,b\n1,2\n")
        zf.writestr("sub/dir/test.csv", "a\n1\n")

    zpath = _write_zip(tmp_path / "benign.zip", _benign)

    members = se.safe_extract(str(zpath), str(dest))

    assert set(members) >= {"train.csv", "sub/dir/test.csv"}
    assert (dest / "train.csv").read_text() == "a,b\n1,2\n"
    assert (dest / "sub" / "dir" / "test.csv").is_file()


def test_module_is_stdlib_and_avoids_unpack_archive():
    """safe_extract uses zipfile/os/stat and NEVER shutil.unpack_archive (no reject hook)."""
    se = _se()
    src = __import__("inspect").getsource(se)
    assert "shutil.unpack_archive" not in src
    for mod in ("zipfile", "os", "stat"):
        assert mod in src
