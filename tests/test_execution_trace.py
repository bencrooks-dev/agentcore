"""Executing a RuntimePlan emits a well-formed, deterministic ExecutionTrace."""
import pytest

from marrow.compiler import (
    AgentGraph,
    AgentNode,
    CompileError,
    ProviderSpec,
    ToolSpec,
    ari_to_runtime_plan,
    compile_to_ari,
    run_runtime_plan,
)
from marrow.compiler.validate import validate

REQUIRED_TRACE_FIELDS = {
    "trace_id",
    "runtime_plan_id",
    "started_at",
    "completed_at",
    "events",
    "tool_calls",
    "provider_calls",
    "policy_decisions",
    "errors",
    "final_status",
}


def echo_plan() -> dict:
    g = AgentGraph(name="echo_agent")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(ToolSpec(name="echo", description="Echo input text"))
    g.add_agent(
        AgentNode(
            id="agent_1",
            name="Echo Agent",
            provider="mock",
            system_prompt="You are a test echo agent.",
            tools=["echo"],
        )
    )
    g.set_entrypoint("agent_1")
    return ari_to_runtime_plan(compile_to_ari(g))


def two_node_plan() -> dict:
    g = AgentGraph(name="pipeline")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_agent(AgentNode(id="researcher", name="Researcher", provider="mock"))
    g.add_agent(AgentNode(id="writer", name="Writer", provider="mock"))
    g.add_edge("researcher", "writer")
    g.set_entrypoint("researcher")
    return ari_to_runtime_plan(compile_to_ari(g))


def _strip_timestamps(trace: dict) -> dict:
    out = dict(trace)
    out["started_at"] = None
    out["completed_at"] = None
    return out


def test_trace_has_all_required_fields():
    trace = run_runtime_plan(echo_plan(), "Hello, Marrow.")
    assert set(trace) >= REQUIRED_TRACE_FIELDS
    validate(trace, "execution_trace.schema.json")


def test_trace_completed_status_and_provider_call():
    trace = run_runtime_plan(echo_plan(), "Hello, Marrow.")
    assert trace["final_status"] == "completed"
    assert trace["errors"] == []
    assert len(trace["provider_calls"]) == 1
    call = trace["provider_calls"][0]
    assert call["provider"] == "mock"
    assert call["model"] == "mock-echo"
    assert call["agent"] == "agent_1"
    assert call["completion_tokens"] >= 0


def test_trace_event_order():
    trace = run_runtime_plan(echo_plan(), "Hello, Marrow.")
    types = [e["type"] for e in trace["events"]]
    assert types == ["agent_started", "provider_called", "agent_completed"]


def test_trace_id_is_deterministic():
    a = run_runtime_plan(echo_plan(), "same input")
    b = run_runtime_plan(echo_plan(), "same input")
    assert a["trace_id"] == b["trace_id"]
    assert a["trace_id"].startswith("tr_")
    # Whole trace is identical once wall-clock timestamps are normalised out.
    assert _strip_timestamps(a) == _strip_timestamps(b)


def test_trace_id_changes_with_input():
    a = run_runtime_plan(echo_plan(), "input one")
    b = run_runtime_plan(echo_plan(), "input two")
    assert a["trace_id"] != b["trace_id"]


def test_two_node_plan_runs_both_agents():
    trace = run_runtime_plan(two_node_plan(), "go")
    assert trace["final_status"] == "completed"
    agents_seen = [c["agent"] for c in trace["provider_calls"]]
    assert agents_seen == ["researcher", "writer"]


def test_unknown_provider_type_is_rejected():
    plan = echo_plan()
    plan["provider_bindings"]["mock"]["type"] = "does-not-exist"
    with pytest.raises(CompileError, match="unknown provider type"):
        run_runtime_plan(plan, "hi")
