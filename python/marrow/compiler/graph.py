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
    """A logical provider id bound to a concrete provider type/model.

    ``config_ref`` is opaque metadata: the built-in providers
    (``openai``/``anthropic``/``ollama``) read keys/URLs from the environment and
    ignore it. A custom provider factory (``run_runtime_plan(..., providers=...)``)
    may interpret ``config_ref`` however it likes (e.g. as a config key)."""

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
class PolicySpec:
    """A governance checkpoint on an action.

    ``action`` is matched against ``"provider:<id>"``, ``"agent:<id>"``,
    ``"tool:<name>"``, or the wildcard ``"*"``. ``decision`` is ``"allow"``,
    ``"deny"``, or ``"require_approval"``; ``approval_required`` additionally
    gates the action on an approver; ``evidence_required`` forces the decision to
    be recorded in the trace.
    """

    id: str
    action: str
    decision: str = "allow"
    approval_required: bool = False
    evidence_required: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "action": self.action,
            "decision": self.decision,
            "approval_required": self.approval_required,
            "evidence_required": self.evidence_required,
        }
        if self.description:
            out["description"] = self.description
        return out


@dataclass
class BudgetSpec:
    """An execution budget. ``None`` limits mean unlimited; ``max_steps`` always
    bounds the loop."""

    max_steps: int = 16
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_wall_ms: int | None = None
    id: str = "budget"
    currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_steps": self.max_steps,
        }
        if self.max_wall_ms is not None:
            out["max_wall_ms"] = self.max_wall_ms
        if self.currency is not None:
            out["currency"] = self.currency
        return out


@dataclass
class FailureSemantics:
    """How the runtime reacts to failures. Each value is ``"abort"`` or
    ``"record_and_continue"``.

    ``on_provider_error`` and ``on_tool_error`` are honored by the executor:
    ``abort`` records the error and halts the run (triggering rollback);
    ``record_and_continue`` records it and proceeds (a provider failure yields an
    empty turn; a tool failure feeds an ``{"ok": false, ...}`` result back to the
    agent). ``on_timeout`` is reserved — the wall-clock *budget* bounds total run
    time, but a per-call timeout kill is not yet wired."""

    on_tool_error: str = "record_and_continue"
    on_provider_error: str = "abort"
    on_timeout: str = "abort"
    on_cancel: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "on_tool_error": self.on_tool_error,
            "on_provider_error": self.on_provider_error,
            "on_timeout": self.on_timeout,
        }
        if self.on_cancel is not None:
            out["on_cancel"] = self.on_cancel
        return out


@dataclass(frozen=True)
class RollbackStep:
    """A compensating action to run on failure (currently ``"clear_state"`` on a
    named agent)."""

    on: str
    action: str = "clear_state"

    def to_dict(self) -> dict[str, Any]:
        return {"on": self.on, "action": self.action}


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
    policies: list[PolicySpec] = field(default_factory=list)
    budget: BudgetSpec | None = None
    failure_semantics: FailureSemantics | None = None
    rollback: list[RollbackStep] = field(default_factory=list)

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

    def set_metadata(self, metadata: dict[str, Any]) -> AgentGraph:
        self.metadata = metadata
        return self

    def add_policy(self, policy: PolicySpec) -> AgentGraph:
        self.policies.append(policy)
        return self

    def set_budget(self, budget: BudgetSpec) -> AgentGraph:
        self.budget = budget
        return self

    def set_failure_semantics(self, failure_semantics: FailureSemantics) -> AgentGraph:
        self.failure_semantics = failure_semantics
        return self

    def add_rollback_step(self, on: str, action: str = "clear_state") -> AgentGraph:
        self.rollback.append(RollbackStep(on, action))
        return self
