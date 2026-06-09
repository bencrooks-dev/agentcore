"""End-to-end convenience over the compiler stages.

``compile_graph`` runs a graph through frontend -> ARI -> RuntimePlan;
``compile_and_run`` additionally executes the plan and returns the trace. Both
are thin wrappers over the per-stage functions so callers can use one call or
drive the stages individually.
"""
from __future__ import annotations

from typing import Any

from .ari_emit import compile_to_ari
from .execute import run_runtime_plan
from .graph import AgentGraph
from .runtime_plan import ari_to_runtime_plan


def compile_graph(graph: AgentGraph) -> dict[str, Any]:
    """Compile ``graph`` to ``{"ari": <manifest>, "runtime_plan": <plan>}``."""
    ari = compile_to_ari(graph)
    plan = ari_to_runtime_plan(ari)
    return {"ari": ari, "runtime_plan": plan}


def compile_and_run(graph: AgentGraph, initial_input: str, **run_kwargs: Any) -> dict[str, Any]:
    """Compile ``graph`` and execute it, returning
    ``{"ari": ..., "runtime_plan": ..., "trace": ...}``.

    ``run_kwargs`` (e.g. ``approver=``, ``pricing=``) are forwarded to
    :func:`run_runtime_plan`."""
    result = compile_graph(graph)
    result["trace"] = run_runtime_plan(result["runtime_plan"], initial_input, **run_kwargs)
    return result
