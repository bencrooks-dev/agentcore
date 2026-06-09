"""Lower an ARI agent-graph manifest into a RuntimePlan.

The core compiler step: validate required fields, graph edges, provider
references, and tool references; resolve provider/tool bindings; and emit a
RuntimePlan with a deterministic ``runtime_plan_id``. The output validates
against ``ari/schemas/runtime_plan.schema.json``.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .ari_emit import canonical_json, graph_id
from .errors import CompileError
from .validate import validate

PLAN_VERSION = "runtime_plan/v0.draft"


def runtime_plan_id(plan: dict[str, Any]) -> str:
    """Deterministic id of a RuntimePlan, computed over every field except the
    id itself (so it is stable and self-consistent)."""
    body = {k: v for k, v in plan.items() if k != "runtime_plan_id"}
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return "rp_" + digest[:16]


def _check_unique(label: str, ids: list[str]) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise CompileError(f"duplicate {label}: {i!r}")
        seen.add(i)


def _check_ari_refs(ari: dict[str, Any]) -> None:
    # ``ari`` may be any dict (not just frontend output), so re-establish the
    # uniqueness invariants the frontend guarantees before resolving references.
    _check_unique("provider id", [p["id"] for p in ari["providers"]])
    _check_unique("tool name", [t["name"] for t in ari["tools"]])
    _check_unique("agent id", [a["id"] for a in ari["agents"]])

    provider_ids = {p["id"] for p in ari["providers"]}
    tool_names = {t["name"] for t in ari["tools"]}
    agent_ids = {a["id"] for a in ari["agents"]}

    for agent in ari["agents"]:
        if agent["provider"] not in provider_ids:
            raise CompileError(
                f"agent {agent['id']!r} references unknown provider {agent['provider']!r}"
            )
        for tool_name in agent["tools"]:
            if tool_name not in tool_names:
                raise CompileError(
                    f"agent {agent['id']!r} references unknown tool {tool_name!r}"
                )
    for edge in ari["edges"]:
        if edge["from"] not in agent_ids:
            raise CompileError(f"edge references unknown source agent {edge['from']!r}")
        if edge["to"] not in agent_ids:
            raise CompileError(f"edge references unknown target agent {edge['to']!r}")
    if ari["entrypoint"] not in agent_ids:
        raise CompileError(
            f"entrypoint {ari['entrypoint']!r} is not an agent in the graph"
        )

    # Policy decisions are constrained by the schema's enum; uniqueness of ids is
    # not (JSON Schema uniqueItems is unused here), so check it explicitly.
    _check_unique("policy id", [p["id"] for p in ari.get("policies", [])])
    rollback = ari.get("rollback")
    if rollback:
        for step in rollback["steps"]:
            if step["on"] not in agent_ids:
                raise CompileError(
                    f"rollback step targets unknown agent {step['on']!r}"
                )


def ari_to_runtime_plan(ari: dict[str, Any]) -> dict[str, Any]:
    """Compile an ARI agent-graph manifest into a RuntimePlan dict.

    ``ari`` may be any dict; it is validated against the agent-graph schema and
    its references are checked before lowering. Raises :class:`CompileError`
    with a clear message on any problem.
    """
    validate(ari, "agent_graph.schema.json")
    _check_ari_refs(ari)

    nodes = [
        {
            "id": a["id"],
            "name": a["name"],
            "provider": a["provider"],
            "system_prompt": a["system_prompt"],
            "tools": list(a["tools"]),
        }
        for a in ari["agents"]
    ]

    # Deep-copy the nested schemas so the plan is a standalone artifact: mutating
    # the source ARI afterwards must not silently alter the plan (which would
    # break its content-addressed runtime_plan_id).
    tool_bindings = {
        t["name"]: {
            "input_schema": copy.deepcopy(t["input_schema"]),
            "output_schema": copy.deepcopy(t["output_schema"]),
            "side_effects": t["side_effects"],
            "timeout_ms": t["timeout_ms"],
            "requires_approval": t["requires_approval"],
        }
        for t in ari["tools"]
    }

    provider_bindings = {
        p["id"]: {
            "type": p["type"],
            "model": p["model"],
            "config_ref": p["config_ref"],
        }
        for p in ari["providers"]
    }

    plan: dict[str, Any] = {
        "version": PLAN_VERSION,
        "graph_id": graph_id(ari),
        "name": ari["name"],
        "entrypoint": ari["entrypoint"],
        "nodes": nodes,
        "edges": [{**e, "condition": dict(e["condition"])} for e in ari["edges"]],
        "tool_bindings": tool_bindings,
        "provider_bindings": provider_bindings,
        "policy_checkpoints": [copy.deepcopy(p) for p in ari.get("policies", [])],
        "timeout_plan": {"default_timeout_ms": 0},
        "retry_plan": {"default": {"attempts": 1}},
        "evidence_plan": {
            "record_tool_calls": True,
            "record_provider_calls": True,
            "record_policy_decisions": True,
        },
    }
    # Governance is optional: only carry these when the graph specified them.
    if "budget" in ari:
        plan["budget"] = copy.deepcopy(ari["budget"])
    if "failure_semantics" in ari:
        plan["failure_semantics"] = copy.deepcopy(ari["failure_semantics"])
    if "rollback" in ari:
        plan["rollback_plan"] = copy.deepcopy(ari["rollback"])

    plan["runtime_plan_id"] = runtime_plan_id(plan)

    validate(plan, "runtime_plan.schema.json")
    return plan


def load_runtime_plan(plan: dict[str, Any]):
    """Parse a plan into a native ``RuntimePlan`` (from the C++ core).

    The plan is serialized to JSON and parsed by the core's own dependency-free
    JSON parser — a real native load, not a field-by-field marshal across the
    pybind boundary. This is where a compiled plan genuinely reaches, and becomes
    inspectable by, the native runtime layer. Returns a ``marrow._marrow.RuntimePlan``.
    """
    from .. import _marrow as _c

    return _c.RuntimePlan.from_json(json.dumps(plan))
