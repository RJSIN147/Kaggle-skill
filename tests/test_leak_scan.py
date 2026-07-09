"""SETUP-04 (D-15) pre-commit content scanner: blocks staged secrets, passes clean.

leak_scan.py is invoked from inside a git repo and scans staged content
(`git diff --cached`). GREEN target: 01-03. RED now (leak_scan.py does not exist).
"""

HEX32 = "0123456789abcdef" * 2  # a 32-char hex string


def test_blocks_staged_token(git_repo, run_script):
    """A staged env-var assignment with a value is blocked (exit 1)."""
    git_repo.stage("secret.txt", f"KAGGLE_KEY={'a' * 32}\n")
    res = run_script("leak_scan.py", cwd=git_repo.path)
    assert res.returncode == 1


def test_passes_clean_content(git_repo, run_script):
    """Clean staged content passes (exit 0)."""
    git_repo.stage("clean.py", "print('hello world')\n")
    res = run_script("leak_scan.py", cwd=git_repo.path)
    assert res.returncode == 0


def test_blocks_export_quoted_dotenv(git_repo, run_script):
    """D-15 broadened dotenv patterns: export / quoted / spaced / lowercase are all blocked."""
    variants = [
        f'export KAGGLE_KEY="{"d" * 32}"\n',   # export + quoted
        f"KAGGLE_KEY = {'d' * 32}\n",          # spaced
        f"kaggle_key={'d' * 32}\n",            # lowercase
    ]
    for content in variants:
        git_repo.stage("leaky.env", content)
        res = run_script("leak_scan.py", cwd=git_repo.path)
        assert res.returncode == 1, f"not blocked: {content!r}"


def test_ignores_unrelated_32hex_json(git_repo, run_script):
    """Bare 32-hex NOT inside a `"key":` JSON field must not false-positive (allowed, exit 0)."""
    git_repo.stage("meta.json", f'{{"hash": "{HEX32}", "commit": "{HEX32}"}}\n')
    res = run_script("leak_scan.py", cwd=git_repo.path)
    assert res.returncode == 0


# --------------------------------------------------------------------------- #
# CR-01 regression: the guard must FAIL CLOSED, and must scan staged blobs whose
# NAMES are non-ASCII / contain a space / contain a newline (git's default
# core.quotePath=true C-quotes those, breaking a naive `git show :<path>` and
# letting the secret through unscanned). These tests FAIL against the pre-fix
# scanner (which enumerated text-mode `--name-only` and mapped any `git show`
# error to "" — a silent skip / fail-open) and PASS after the NUL-separated,
# quotePath=false, error-propagating rewrite.
# --------------------------------------------------------------------------- #
def test_blocks_non_ascii_filename(git_repo, run_script):
    """CR-01: a Kaggle key in a non-ASCII-named file (café.env) must be blocked (exit 1)."""
    git_repo.stage("café.env", f"KAGGLE_KEY={'a' * 32}\n")
    res = run_script("leak_scan.py", cwd=git_repo.path)
    assert res.returncode == 1, "non-ASCII-named staged secret was NOT scanned (fail-open)"


def test_blocks_space_in_filename(git_repo, run_script):
    """CR-01: a secret in a filename containing a SPACE is still scanned + blocked."""
    git_repo.stage("my secret.env", f"KAGGLE_KEY={'a' * 32}\n")
    res = run_script("leak_scan.py", cwd=git_repo.path)
    assert res.returncode == 1, "space-named staged secret was NOT scanned"


def test_blocks_newline_in_filename(git_repo, run_script):
    """CR-01: a secret in a filename containing a NEWLINE is still scanned + blocked.

    A newline is a control char, so core.quotePath C-quotes it -> the pre-fix
    text-mode enumeration produced an unusable pathspec and skipped the blob.
    """
    git_repo.stage("has\nnewline.env", f"KAGGLE_KEY={'a' * 32}\n")
    res = run_script("leak_scan.py", cwd=git_repo.path)
    assert res.returncode == 1, "newline-named staged secret was NOT scanned"


def test_fails_closed_outside_git_repo(tmp_path, run_script):
    """CR-01: a git enumeration error must FAIL CLOSED (non-zero), never exit 0.

    Run in a directory that is NOT a git repo: `git diff --cached` fails, and the
    pre-fix scanner ignored the return code, returned no files, and exited 0
    (treating its own failure as "clean"). The hardened scanner must block.
    """
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    res = run_script(
        "leak_scan.py",
        cwd=non_repo,
        # GIT_DIR at a bogus path guarantees a git error regardless of where the
        # pytest tmp tree happens to live (no accidental repo discovery upward).
        extra_env={"GIT_DIR": str(tmp_path / "nonexistent.git")},
    )
    assert res.returncode != 0, "git enumeration error was treated as 'clean' (fail-open)"


def test_binary_non_utf8_blob_does_not_crash(git_repo, run_script):
    """CR-01: a binary / non-UTF-8 staged blob must not crash the scanner.

    The embedded ASCII `KAGGLE_KEY=` assignment must still be caught through the
    errors='replace' decode (proves no-crash AND that decoding stays scan-honest).
    """
    blob = b"\xff\xfe\x00\x01" + b"KAGGLE_KEY=" + b"a" * 32 + b"\n" + b"\x80\x81\x82"
    git_repo.stage("weird.bin", blob)
    res = run_script("leak_scan.py", cwd=git_repo.path)
    assert res.returncode == 1, "binary blob with an embedded secret was not blocked / crashed"
