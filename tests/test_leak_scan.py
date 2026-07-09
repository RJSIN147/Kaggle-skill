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
