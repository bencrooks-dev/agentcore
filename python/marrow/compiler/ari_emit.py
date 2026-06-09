"""Lower an :class:`AgentGraph` to an ARI manifest and identify it.

``compile_to_ari`` validates the graph (structure, tool contracts, provider
contracts) with clear errors, then emits a manifest that is validated against
``ari/schemas/agent_graph.schema.json``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import CompileError
from .graph import AgentGraph
from .validate import validate

_POLICY_DECISIONS = {"allow", "deny", "require_approval"}


def _canonicalize(obj: Any) -> Any:
    """Normalize values so the canonical form is identical across languages.

    The one cross-language hazard is integral floats: Python serializes ``1.0``
    as ``"1.0"`` while JavaScript serializes it as ``"1"``. We fold integral
    floats to ints so content-addressed ids match whichever frontend emitted the
    manifest. (Non-integral floats already serialize identically.)
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, dict):
        return {k: _canonicalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_canonicalize(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """Stable serialisation used for content-addressed ids: keys sorted, no
    insignificant whitespace, UTF-8 preserved, integral floats folded to ints
    (so Python and the TypeScript frontend produce identical ids)."""
    return json.dumps(
        _canonicalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def graph_id(ari: dict[str, Any]) -> str:
    """Deterministic id of an ARI agent-graph manifest."""
    digest = hashlib.sha256(canonical_json(ari).encode("utf-8")).hexdigest()
    return "g_" + digest[:16]


def _check_unique(label: str, ids: list[str]) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise CompileError(f"duplicate {label}: {i!r}")
        seen.add(i)


def _validate_graph(graph: AgentGraph) -> None:
    if not graph.name:
        raise CompileError("graph has no name")
    if not graph.agents:
        raise CompileError("graph has no agents")

    provider_ids = [p.id for p in graph.providers]
    tool_names = [t.name for t in graph.tools]
    agent_ids = [a.id for a in graph.agents]
    _check_unique("provider id", provider_ids)
    _check_unique("tool name", tool_names)
    _check_unique("agent id", agent_ids)

    provider_set = set(provider_ids)
    tool_set = set(tool_names)
    agent_set = set(agent_ids)

    for agent in graph.agents:
        if agent.provider not in provider_set:
            raise CompileError(
                f"agent {agent.id!r} references unknown provider {agent.provider!r}"
            )
        for tool_name in agent.tools:
            if tool_name not in tool_set:
                raise CompileError(
                    f"agent {agent.id!r} references unknown tool {tool_name!r}"
                )

    for edge in graph.edges:
        if edge.source not in agent_set:
            raise CompileError(f"edge references unknown source agent {edge.source!r}")
        if edge.target not in agent_set:
            raise CompileError(f"edge references unknown target agent {edge.target!r}")

    if not graph.entrypoint:
        raise CompileError("graph has no entrypoint; call set_entrypoint(agent_id)")
    if graph.entrypoint not in agent_set:
        raise CompileError(
            f"entrypoint {graph.entrypoint!r} is not an agent in the graph"
        )

    _check_unique("policy id", [p.id for p in graph.policies])
    for policy in graph.policies:
        if not policy.action:
            raise CompileError(f"policy {policy.id!r} has an empty action")
        if policy.decision not in _POLICY_DECISIONS:
            raise CompileError(
                f"policy {policy.id!r} has invalid decision {policy.decision!r} "
                f"(expected one of {sorted(_POLICY_DECISIONS)})"
            )

    if graph.budget is not None:
        if graph.budget.max_steps < 1:
            raise CompileError("budget max_steps must be >= 1")
        if graph.budget.max_tokens is not None and graph.budget.max_tokens < 0:
            raise CompileError("budget max_tokens must be >= 0")
        if graph.budget.max_cost_usd is not None and graph.budget.max_cost_usd < 0:
            raise CompileError("budget max_cost_usd must be >= 0")

    for step in graph.rollback:
        if step.on not in agent_set:
            raise CompileError(f"rollback step targets unknown agent {step.on!r}")


def compile_to_ari(graph: AgentGraph) -> dict[str, Any]:
    """Validate ``graph`` and emit its ARI agent-graph manifest (a dict).

    Raises :class:`CompileError` with a clear message on any structural problem.
    The returned manifest is guaranteed to validate against
    ``agent_graph.schema.json``.
    """
    _validate_graph(graph)

    manifest: dict[str, Any] = {
        "version": graph.version,
        "name": graph.name,
        "providers": [p.to_dict() for p in graph.providers],
        "tools": [t.to_dict() for t in graph.tools],
        "agents": [a.to_dict() for a in graph.agents],
        "edges": [e.to_dict() for e in graph.edges],
        "entrypoint": graph.entrypoint,
    }
    if graph.metadata is not None:
        manifest["metadata"] = graph.metadata
    if graph.policies:
        manifest["policies"] = [p.to_dict() for p in graph.policies]
    if graph.budget is not None:
        manifest["budget"] = graph.budget.to_dict()
    if graph.failure_semantics is not None:
        manifest["failure_semantics"] = graph.failure_semantics.to_dict()
    if graph.rollback:
        manifest["rollback"] = {
            "id": "rollback",
            "steps": [s.to_dict() for s in graph.rollback],
        }

    validate(manifest, "agent_graph.schema.json")
    return manifest
