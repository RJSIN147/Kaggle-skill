"""CORE-01: every kx invocation prints exactly one JSON envelope on stdout."""

import json
import subprocess
import sys

from conftest import REPO_ROOT, _base_env, kx

from kx import cli
from kx.envelope import STATUSES


def _run_module(cwd, *args, home=None):
    return subprocess.run([sys.executable, "-m", "kx", *args], cwd=str(cwd), capture_output=True,
                          text=True, env=_base_env(home=home))


def _one_envelope(stdout: str) -> dict:
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, stdout
    env = json.loads(lines[0])
    assert env["status"] in STATUSES
    assert "next_action" in env and env["next_action"]["kind"] in ("run", "edit", "ask_user", "done")
    return env


def test_status_in_empty_folder_is_one_envelope(tmp_path):
    res = _run_module(tmp_path, "status")
    env = _one_envelope(res.stdout)
    assert res.returncode == 0
    assert env["next_action"]["command"] == "kx init"


def test_help_and_usage_errors_are_envelopes(tmp_path):
    env = _one_envelope(_run_module(tmp_path, "--help").stdout)
    assert env["status"] == "ok" and "usage" in env["data"]
    res = _run_module(tmp_path, "run")  # missing exp_id
    env = _one_envelope(res.stdout)
    assert env["status"] == "invalid" and res.returncode == 1
    env = _one_envelope(_run_module(tmp_path, "no-such-command").stdout)
    assert env["status"] == "invalid"


def test_init_without_credential_needs_user_and_never_prompts(tmp_path, hermetic):
    res = subprocess.run([sys.executable, "-m", "kx", "init"], cwd=str(tmp_path),
                         capture_output=True, text=True, stdin=subprocess.DEVNULL,
                         env=_base_env(home=hermetic), timeout=60)
    env = _one_envelope(res.stdout)
    assert env["status"] == "needs_user"
    assert env["next_action"]["kind"] == "ask_user"
    assert "Traceback" not in res.stdout + res.stderr


def test_stray_prints_and_child_output_never_reach_stdout(tmp_path, capfd, fake):
    class Noisy(type(fake)):
        def validate(self):
            print("chatter on stdout")
            subprocess.run(["echo", "child stdout"])
            return super().validate()

    ws = tmp_path / "ws"
    (tmp_path / "home").mkdir()
    rc = cli.main(["status"], ws=ws, adapter=Noisy())
    out = capfd.readouterr().out
    assert rc == 0
    _one_envelope(out)


def test_internal_errors_become_error_envelopes(tmp_path, capfd, fake, monkeypatch):
    from kx import commands

    def boom(ws, args, adapter):
        raise ZeroDivisionError("secret-ish detail")

    monkeypatch.setattr(commands, "cmd_status", boom)
    rc = cli.main(["status"], ws=tmp_path, adapter=fake)
    env = _one_envelope(capfd.readouterr().out)
    assert rc == 1 and env["status"] == "error"
    assert "secret-ish" not in json.dumps(env)
    assert env["errors"] == ["internal:ZeroDivisionError"]


def test_importing_kx_never_imports_kaggle(tmp_path, hermetic):
    code = ("import sys, kx.cli, kx.commands, kx.adapter, kx.kernel, kx.record, kx.profile, "
            "kx.submit, kx.research, kx.ensemble; "
            "assert not any(m == 'kaggle' or m.startswith('kaggle.') for m in sys.modules), "
            "[m for m in sys.modules if m.startswith('kaggle')]")
    res = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), capture_output=True,
                         text=True, env=_base_env(home=hermetic))
    assert res.returncode == 0, res.stderr


def test_every_command_returns_an_envelope_on_a_fresh_folder(tmp_path, fake):
    for argv in (["status"], ["sync", "titanic"], ["confirm"], ["metric", "accuracy"],
                 ["new", "--idea", "x", "--hypothesis", "y"], ["run", "exp-001"],
                 ["strategy", "--reasoning-file", "r.md"], ["lb"], ["submit", "exp-001"],
                 ["research"], ["ensemble", "exp-001", "exp-002"]):
        env = kx(tmp_path, fake, *argv)
        assert env["status"] in STATUSES, argv
        assert env["next_action"], argv


def test_console_script_is_declared():
    text = (REPO_ROOT / "pyproject.toml").read_text()
    assert 'kx = "kx.cli:main"' in text
    assert '"kaggle==2.2.3"' in text


def test_every_documented_flag_exists_on_its_parser():
    """A `kx <command> --flag` written in a doc must be a real flag of that command."""
    import re

    from conftest import REPO_ROOT

    from kx.cli import build_parser

    sub = next(a for a in build_parser()._actions
               if a.__class__.__name__ == "_SubParsersAction")
    flags = {n: {o for a in sp._actions for o in a.option_strings} for n, sp in sub.choices.items()}
    docs = [REPO_ROOT / "SKILL.md", REPO_ROOT / "README.md", REPO_ROOT / "CLAUDE.md",
            *sorted((REPO_ROOT / "references").rglob("*.md"))]
    missing, seen = [], 0
    for doc in docs:
        for n, line in enumerate(doc.read_text().splitlines(), 1):
            for m in re.finditer(r"\bkx ([a-z]+)([^`|]*)", line):
                cmd = m.group(1)
                if cmd not in flags:  # prose ("kx refuses ..."), not a command
                    continue
                for f in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", m.group(2)):
                    seen += 1
                    if f not in flags[cmd]:
                        missing.append(f"{doc.name}:{n}: kx {cmd} {f}")
    assert seen > 30 and missing == [], missing
    for f in ("--parent", "--expect", "--expect-delta", "--cv-check", "--evidence"):
        assert f in flags["new"], f


def test_bare_wait_means_540_seconds():
    p = cli.build_parser()
    assert p.parse_args(["run", "exp-001", "--wait"]).wait == 540.0
    assert p.parse_args(["run", "exp-001"]).wait == 90.0
    assert p.parse_args(["lb", "--wait"]).wait == 540.0
