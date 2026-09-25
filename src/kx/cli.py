"""kx entry point: parse, dispatch, print exactly one JSON envelope.

fd 1 points at /dev/null for the whole command, so a stray print, a child
process or the kaggle library can never corrupt the envelope; the envelope is
written on the saved descriptor at the end. Usage errors and --help are
envelopes too. An unexpected exception becomes status=error with its type
only; the traceback goes to control/raw/last-error.txt (gitignored).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from kx import envelope as E
from kx.adapter import CredentialUnavailable, KaggleAdapter
from kx.credentials import NO_CREDENTIAL_INSTRUCTIONS
from kx.util import KxError


class UsageError(Exception):
    pass


class HelpRequested(Exception):
    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


class KxParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)

    def print_help(self, file=None):
        raise HelpRequested(self.format_help())

    def exit(self, status=0, message=None):
        raise UsageError(message or f"exit {status}")


def build_parser() -> KxParser:
    p = KxParser(prog="kx", description="Kaggle experiment loop. Every command prints one JSON "
                                        "object; follow its next_action.")
    sub = p.add_subparsers(dest="command", parser_class=KxParser)

    s = sub.add_parser("init", help="set up this folder as a workspace and validate the credential")
    s.add_argument("competition", nargs="?")

    sub.add_parser("status", help="where the loop is, and the next action")

    s = sub.add_parser("sync", help="profile a competition from structured API facts")
    s.add_argument("competition", nargs="?")
    s.add_argument("--download", action="store_true",
                   help="also download the data bundle (joined + locally feasible only)")
    s.add_argument("--force-download", action="store_true",
                   help="download even when the profile marks local runs as infeasible")
    s.add_argument("--files", nargs="+",
                   help="download only these files (e.g. train.csv test.csv) instead of the bundle")

    s = sub.add_parser("confirm", help="record the user's confirmation of the profile")
    s.add_argument("--mode")
    s.add_argument("--modality")
    s.add_argument("--expected-output")
    s.add_argument("--note")

    s = sub.add_parser("metric", help="set the evaluation metric")
    s.add_argument("name")
    s.add_argument("--direction", choices=("higher", "lower"))
    s.add_argument("--range", nargs=2, type=float, metavar=("LO", "HI"))
    s.add_argument("--prediction-type", choices=("proba", "label", "raw"))

    s = sub.add_parser("new", help="scaffold the next experiment")
    s.add_argument("--idea")
    s.add_argument("--hypothesis")
    s.add_argument("--template")
    s.add_argument("--template-reason")
    s.add_argument("--folds", type=int, default=5)
    s.add_argument("--accelerator")
    s.add_argument("--limit", type=int, help="kernel runtime limit in seconds")
    s.add_argument("--local", action="store_true", help="run on this machine instead of a kernel")
    s.add_argument("--subsample", type=float, help="local runs: fraction of train rows")
    s.add_argument("--from-idea", type=int, help="run research idea #N (marks it tried)")
    s.add_argument("--after", action="append", help="upstream experiment whose kernel output "
                                                    "this one reads (repeatable)")

    s = sub.add_parser("run", help="push, poll, pull and record an experiment")
    s.add_argument("exp_id")
    s.add_argument("--wait", type=float, default=90.0,
                   help="seconds to poll before returning status=running (default 90)")
    s.add_argument("--wait-local", type=float, default=3000.0,
                   help="local runs: timeout in seconds")
    s.add_argument("--rerun", action="store_true", help="push a new version even if recorded")
    s.add_argument("--resume", action="store_true",
                   help="continue a run that stopped at its time budget from its checkpoints")

    s = sub.add_parser("strategy", help="regenerate strategy.md from the ledger + reasoning")
    s.add_argument("--reasoning-file", required=True)

    s = sub.add_parser("submit", help="validate a candidate and hand over the submit command")
    s.add_argument("exp_id", nargs="?")
    s.add_argument("--writeup", action="store_true")
    s.add_argument("--file", help="csv_upload: the file to submit (default: the experiment's)")
    s.add_argument("--message")
    s.add_argument("--force-cv", action="store_true",
                   help="allow a candidate whose CV is not better than the best submitted")

    s = sub.add_parser("lb", help="read back submissions and show LB next to CV")
    s.add_argument("--wait", type=float, default=90.0)

    s = sub.add_parser("research", help="discussions, public notebooks and metric kernels")
    s.add_argument("what", nargs="?", default="all",
                   choices=("all", "pages", "discussions", "notebooks", "metric", "idea"))
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--idea")
    s.add_argument("--source")
    s.add_argument("--use-metric", help="owner/slug of a metric kernel to adopt for CV")

    sub.add_parser("env", help="kernel image + library versions of each run vs this machine")

    s = sub.add_parser("ensemble", help="blend saved OOF predictions into a new experiment")
    s.add_argument("exp_ids", nargs="+")
    s.add_argument("--method", choices=("hill", "weights"), default="hill")
    s.add_argument("--idea")
    return p


def dispatch(argv, ws: Path, adapter) -> dict:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except HelpRequested as h:
        return E.make("help", "ok", "kx usage", data={"usage": h.text},
                      next_action=E.run("kx status"))
    if not args.command:
        return E.make("help", "ok", "kx usage", data={"usage": parser.format_help()},
                      next_action=E.run("kx status"))
    from kx import commands, ensemble, envinfo, research, submit

    handlers = {
        "init": commands.cmd_init, "status": commands.cmd_status, "sync": commands.cmd_sync,
        "confirm": commands.cmd_confirm, "metric": commands.cmd_metric, "new": commands.cmd_new,
        "run": commands.cmd_run, "strategy": commands.cmd_strategy,
        "submit": submit.cmd_submit, "lb": submit.cmd_lb,
        "research": research.cmd_research, "ensemble": ensemble.cmd_ensemble,
        "env": envinfo.cmd_env,
    }
    try:
        return handlers[args.command](ws, args, adapter)
    except KxError as exc:
        if exc.quarantine and (ws / "control").is_dir():
            raw = ws / "control" / "raw"
            raw.mkdir(exist_ok=True)
            (raw / "last-error.txt").write_text(exc.quarantine + "\n")
        return E.make(args.command, exc.status, exc.summary, data=exc.data, errors=exc.errors,
                      next_action=exc.next_action or E.run("kx status"))
    except CredentialUnavailable:
        return E.make(args.command, "needs_user", "no valid Kaggle credential",
                      errors=["no_credential"],
                      next_action=E.ask_user(NO_CREDENTIAL_INSTRUCTIONS, then="kx init"))


def _internal_error(ws: Path, exc: BaseException) -> dict:
    if (ws / "control").is_dir():
        raw = ws / "control" / "raw"
        raw.mkdir(exist_ok=True)
        (raw / "last-error.txt").write_text("".join(traceback.format_exception(exc)))
    return E.make("unknown", "error", f"internal error ({type(exc).__name__}); details in "
                                      "control/raw/last-error.txt",
                  errors=[f"internal:{type(exc).__name__}"])


def main(argv=None, *, ws: Path | None = None, adapter=None) -> int:
    ws = Path(ws or os.getcwd())
    adapter = adapter if adapter is not None else KaggleAdapter()
    sys.stdout.flush()
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    try:
        try:
            env = dispatch(sys.argv[1:] if argv is None else argv, ws, adapter)
        except UsageError as exc:
            env = E.make("usage", "invalid", f"usage error: {exc}", errors=["usage"],
                         next_action=E.run("kx --help"))
        except Exception as exc:  # noqa: BLE001 - never a traceback on stdout
            env = _internal_error(ws, exc)
        finally:
            sys.stdout.flush()
    finally:
        os.dup2(saved, 1)
        os.close(saved)
        os.close(devnull)
    os.write(1, (json.dumps(env, ensure_ascii=False) + "\n").encode())
    return 0 if env["status"] in ("ok", "running") else 1
