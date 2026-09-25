"""Placeholder until its phase lands."""

from kx.util import KxError


def _todo(*_a, **_k):
    raise KxError("invalid", "not implemented yet", errors=["not_implemented"])


cmd_submit = cmd_lb = cmd_research = cmd_ensemble = _todo
