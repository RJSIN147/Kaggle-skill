"""SETUP-04 (T-cred-commit): generated .gitignore covers the secret files.

GREEN target: 01-03. RED now (init_workspace.py does not exist yet).
"""

import subprocess


def test_secrets_ignored(tmp_workspace, run_script):
    """.gitignore names .env / kaggle.json / access_token, and git actually ignores .env."""
    ws = tmp_workspace
    res = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert res.returncode == 0, res.stderr

    gitignore = (ws / ".gitignore").read_text()
    for secret in (".env", "kaggle.json", "access_token"):
        assert secret in gitignore, f"missing .gitignore entry for {secret}"

    # functional check: a real .env is actually ignored by git
    (ws / ".env").write_text("KAGGLE_KEY=placeholder\n")
    checked = subprocess.run(
        ["git", "check-ignore", ".env"], cwd=ws, capture_output=True, text=True
    )
    assert checked.returncode == 0, "git does not ignore .env"
