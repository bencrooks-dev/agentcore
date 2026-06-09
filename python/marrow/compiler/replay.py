"""Deterministic replay of a RuntimePlan.

Because ids are content-addressed and the mock provider is deterministic, a given
``(runtime_plan, initial_input, approver, pricing)`` always produces the same
trace except for wall-clock timestamps. ``replay`` re-executes a plan;
``traces_equivalent`` compares two traces ignoring those timestamps.
"""
from __future__ import annotations

from typing import Any

from .execute import run_runtime_plan

_VOLATILE_FIELDS = ("started_at", "completed_at")


def replay(runtime_plan: dict[str, Any], initial_input: str, **run_kwargs: Any) -> dict[str, Any]:
    """Re-execute ``runtime_plan`` and return a fresh ExecutionTrace."""
    return run_runtime_plan(runtime_plan, initial_input, **run_kwargs)


def normalize_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``trace`` with non-reproducible timestamps nulled."""
    out = dict(trace)
    for field in _VOLATILE_FIELDS:
        out[field] = None
    return out


def traces_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """True if two traces are identical once wall-clock timestamps are removed."""
    return normalize_trace(first) == normalize_trace(second)
