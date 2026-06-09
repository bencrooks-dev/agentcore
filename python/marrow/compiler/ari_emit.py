"""Lower an :class:`AgentGraph` to an ARI manifest and identify it.

``compile_to_ari`` performs the structural checks the brief's pipeline calls for
(graph validation, tool-contract validation, provider-contract validation) with
clear errors, then emits a manifest that is validated against
``ari/schemas/agent_graph.schema.json``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import CompileError
from .graph import AgentGraph
from .validate import validate


def canonical_json(obj: Any) -> str:
    """Stable serialisation used for content-addressed ids: keys sorted, no
    insignificant whitespace, UTF-8 preserved."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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

    validate(manifest, "agent_graph.schema.json")
    return manifest
