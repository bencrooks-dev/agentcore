"""Authoring types for the Marrow compiler frontend.

You describe an agent system in Python and the compiler lowers it. These types
are intentionally plain data (dataclasses) so the description is introspectable
and serialises cleanly to an ARI manifest — unlike ``marrow.Graph`` edge
conditions, which are arbitrary Python callables and cannot be serialised.

Example::

    from marrow.compiler import AgentGraph, AgentNode, ToolSpec, ProviderSpec

    graph = AgentGraph(name="echo_agent")
    graph.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    graph.add_tool(ToolSpec(name="echo", description="Echo input text"))
    graph.add_agent(AgentNode(id="agent_1", name="Echo Agent", provider="mock",
                              system_prompt="You are a test echo agent.",
                              tools=["echo"]))
    graph.set_entrypoint("agent_1")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderSpec:
    """A logical provider id bound to a concrete provider type/model."""

    id: str
    type: str
    model: str
    config_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "model": self.model,
            "config_ref": self.config_ref,
        }


@dataclass
class ToolSpec:
    """A tool contract: name, I/O schemas, and runtime properties."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    side_effects: bool = False
    timeout_ms: int = 1000
    requires_approval: bool = False
    tags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "side_effects": self.side_effects,
            "timeout_ms": self.timeout_ms,
            "requires_approval": self.requires_approval,
        }
        if self.tags is not None:
            out["tags"] = list(self.tags)
        return out


@dataclass
class AgentNode:
    """One named, stateful agent in the graph."""

    id: str
    name: str
    provider: str
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "system_prompt": self.system_prompt,
            "tools": list(self.tools),
            "state": self.state,
        }


@dataclass(frozen=True)
class Edge:
    """A directed edge with a serialisable, declarative condition.

    ``condition`` is ``{"type": "always"}`` or
    ``{"type": "contains", "value": "<text>"}`` — the latter fires when the
    producing agent's latest output contains ``value`` (mirrors the
    ``when=lambda s: "DRAFT" in s`` pattern in ``marrow.Graph``, but without an
    unserialisable lambda)."""

    source: str
    target: str
    condition: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.source, "to": self.target, "condition": self.condition}


def always() -> dict[str, Any]:
    return {"type": "always"}


def contains(value: str) -> dict[str, Any]:
    return {"type": "contains", "value": value}


@dataclass
class AgentGraph:
    """A declaratively-defined agent system: the compiler's input.

    The mutating builder methods return ``self`` so calls can be chained.
    """

    name: str
    version: str = "ari/v0.draft"
    providers: list[ProviderSpec] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    agents: list[AgentNode] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    entrypoint: str | None = None
    metadata: dict[str, Any] | None = None

    def add_provider(self, provider: ProviderSpec) -> AgentGraph:
        self.providers.append(provider)
        return self

    def add_tool(self, tool: ToolSpec) -> AgentGraph:
        self.tools.append(tool)
        return self

    def add_agent(self, agent: AgentNode) -> AgentGraph:
        self.agents.append(agent)
        return self

    def add_edge(
        self, source: str, target: str, *, when_contains: str | None = None
    ) -> AgentGraph:
        condition = contains(when_contains) if when_contains is not None else always()
        self.edges.append(Edge(source, target, condition))
        return self

    def set_entrypoint(self, agent_id: str) -> AgentGraph:
        self.entrypoint = agent_id
        return self
