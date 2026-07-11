"""test_poll_kernel.py — RED (Wave 0). Pins the status-classify + bounded-backoff +
detach-not-cancel contract for EXP-05 (D-08/09/10).

`poll_kernel.py` does NOT exist yet — imports live INSIDE the test bodies so collection never
crashes; the module raises ModuleNotFoundError now (RED) until plan 04-02 builds it.

Pinned contract:
  * ``classify_status(text) -> str | None`` extracts the KernelWorkerStatus token from the CLI's
    ``has status "KernelWorkerStatus.<TOKEN>"`` line and NEVER a substring inside a
    ``Failure message:`` body (Pitfall 2). ``TERMINAL`` / ``IN_FLIGHT`` are the authoritative
    token sets.
  * ``compute_delay(attempt, rng=None) -> float`` — exponential (``compute_delay(1) >
    compute_delay(0)``), capped at ``MAX_DELAY``, and jittered within ``(0, base]`` when an RNG
    is supplied (full-jitter, so a sleep can never exceed the cap → budget-safe).
  * ``poll_loop(status_fn, *, now, sleep, rng, budget_s, max_consecutive_errors,
    cancel_fn=None) -> dict`` — tolerates transient ``status_fn`` errors up to a threshold, stops
    at the wall-clock budget, and on our-side timeout with the kernel still RUNNING returns a
    non-terminal DETACHED result WITHOUT ever calling ``cancel_fn`` (D-09).
"""

import random
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _status(name: str) -> str:
    return (FIXTURES / "status" / f"{name}.txt").read_text()


def _sequence(items):
    """A status_fn stand-in: yields each item in turn, then repeats the last forever
    (so an over-eager poll loop can never raise StopIteration)."""
    it = iter(items)
    last = {"v": items[-1]}

    def _next():
        try:
            last["v"] = next(it)
        except StopIteration:
            pass
        return last["v"]

    return _next


class _FakeClock:
    """A monotonic clock advanced only by the injected sleep — deterministic, no real waiting."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def test_status_classify():
    import poll_kernel

    classify = poll_kernel.classify_status
    assert classify(_status("queued")) == "QUEUED"
    assert classify(_status("running")) == "RUNNING"
    assert classify(_status("complete")) == "COMPLETE"
    assert classify(_status("cancel_acknowledged")) == "CANCEL_ACKNOWLEDGED"
    # error.txt embeds COMPLETE and RUNNING inside its `Failure message:` body — the parser
    # MUST return the STATUS token (ERROR), never a body substring (Pitfall 2 / DETACH safety).
    assert classify(_status("error")) == "ERROR"

    assert {"QUEUED", "RUNNING"} <= poll_kernel.IN_FLIGHT
    assert {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"} <= poll_kernel.TERMINAL
    # A garbage / transient-blip buffer is unparseable → None → retry (D-10), never a false token.
    assert classify("connection reset by peer") is None


def test_backoff_budget():
    import poll_kernel

    # Exponential + capped (deterministic base with rng=None).
    d0 = poll_kernel.compute_delay(0)
    d1 = poll_kernel.compute_delay(1)
    assert d1 > d0, "backoff must grow exponentially"
    assert poll_kernel.compute_delay(100) == poll_kernel.MAX_DELAY, "backoff must cap"

    # Jitter: within (0, base] (full-jitter → never exceeds the cap), and decorrelated.
    base5 = poll_kernel.compute_delay(5)
    j = poll_kernel.compute_delay(5, rng=random.Random(1))
    k = poll_kernel.compute_delay(5, rng=random.Random(2))
    assert 0 < j <= base5 and 0 < k <= base5
    assert j != k, "jitter must decorrelate independent RNG states"
    assert poll_kernel.compute_delay(100, rng=random.Random(9)) <= poll_kernel.MAX_DELAY

    # Transient-error tolerance: a couple of rc!=0 blips are absorbed, then COMPLETE ⇒ terminal.
    clock = _FakeClock()
    status_fn = _sequence(
        [(1, "blip"), (1, "blip"), (0, _status("running")), (0, _status("complete"))]
    )
    result = poll_kernel.poll_loop(
        status_fn,
        now=clock.now, sleep=clock.sleep, rng=random.Random(7),
        budget_s=10_000, max_consecutive_errors=5,
    )
    assert result["terminal"] is True
    assert result["status"] == "COMPLETE"
    # Every backoff sleep respected the cap (jittered, budget-safe).
    assert clock.sleeps and all(s <= poll_kernel.MAX_DELAY for s in clock.sleeps)


def test_detach_not_cancel():
    import poll_kernel

    clock = _FakeClock()
    cancel_calls = []
    result = poll_kernel.poll_loop(
        _sequence([(0, _status("running"))]),  # never reaches a terminal state
        now=clock.now, sleep=clock.sleep, rng=random.Random(0),
        budget_s=100, max_consecutive_errors=5,
        cancel_fn=lambda: cancel_calls.append(1),
    )
    # Our-side budget expired with the kernel still running ⇒ DETACH, not cancel (D-09).
    assert result["terminal"] is False
    assert result["status"] in ("DETACHED", "PENDING")
    assert cancel_calls == [], "poll must NEVER cancel the kernel (detach-not-cancel)"
    assert clock.now() >= 100, "loop must run until the wall-clock budget"


def test_source_routes_through_gateway():
    """Source-invariant (goes GREEN in 04-02): status polling routes through run_kaggle,
    never a bare subprocess nor a printed raw status buffer."""
    src = (SCRIPTS_DIR / "poll_kernel.py").read_text()
    assert "run_kaggle" in src
