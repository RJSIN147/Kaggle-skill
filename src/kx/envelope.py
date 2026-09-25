"""The one JSON object every kx command prints.

status: ok | running | needs_user | invalid | error
  ok          the command did its job (a run recorded FAILED is still ok;
              the outcome is in data.result)
  running     a kernel is still in flight: re-run the same command to resume
  needs_user  a human step (credential, joining a competition, a submit)
  invalid     the input was refused; nothing was pushed or mutated
  error       transient or unexpected; safe to retry
next_action.kind: run | edit | ask_user | done
"""

from __future__ import annotations

from kx import __version__

STATUSES = ("ok", "running", "needs_user", "invalid", "error")


def make(command: str, status: str, summary: str, *, data=None, next_action=None,
         warnings=None, errors=None) -> dict:
    assert status in STATUSES, status
    return {
        "kx": __version__,
        "command": command,
        "status": status,
        "summary": summary,
        "data": data or {},
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "next_action": next_action or {"kind": "run", "command": "kx status"},
    }


def run(command: str, instruction: str | None = None) -> dict:
    na = {"kind": "run", "command": command}
    if instruction:
        na["instruction"] = instruction
    return na


def edit(instruction: str, then: str) -> dict:
    return {"kind": "edit", "instruction": instruction, "then": then}


def ask_user(instruction: str, then: str | None = None) -> dict:
    na = {"kind": "ask_user", "instruction": instruction}
    if then:
        na["then"] = then
    return na


def done(instruction: str) -> dict:
    return {"kind": "done", "instruction": instruction}
