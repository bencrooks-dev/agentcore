"""ARI manifest -> RuntimePlan lowering and its validations."""
import pytest

from marrow.compiler import (
    AgentGraph,
    AgentNode,
    CompileError,
    ProviderSpec,
    ToolSpec,
    ari_to_runtime_plan,
    compile_to_ari,
)
from marrow.compiler.validate import validate


def echo_graph() -> AgentGraph:
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
    return g


def echo_ari() -> dict:
    return compile_to_ari(echo_graph())


def test_runtime_plan_structure():
    plan = ari_to_runtime_plan(echo_ari())
    assert plan["version"] == "runtime_plan/v0.draft"
    assert plan["graph_id"].startswith("g_")
    assert plan["runtime_plan_id"].startswith("rp_")
    assert plan["entrypoint"] == "agent_1"
    assert plan["nodes"][0]["id"] == "agent_1"
    assert plan["provider_bindings"]["mock"] == {
        "type": "mock",
        "model": "mock-echo",
        "config_ref": None,
    }
    assert plan["tool_bindings"]["echo"]["timeout_ms"] == 1000
    assert plan["policy_checkpoints"] == []
    assert plan["evidence_plan"]["record_provider_calls"] is True


def test_runtime_plan_validates_against_schema():
    plan = ari_to_runtime_plan(echo_ari())
    validate(plan, "runtime_plan.schema.json")  # must not raise


def test_dangling_provider_reference_raises():
    ari = echo_ari()
    ari["agents"][0]["provider"] = "ghost"
    with pytest.raises(CompileError, match="unknown provider"):
        ari_to_runtime_plan(ari)


def test_dangling_tool_reference_raises():
    ari = echo_ari()
    ari["agents"][0]["tools"] = ["ghost"]
    with pytest.raises(CompileError, match="unknown tool"):
        ari_to_runtime_plan(ari)


def test_bad_entrypoint_raises():
    ari = echo_ari()
    ari["entrypoint"] = "ghost"
    with pytest.raises(CompileError, match="entrypoint"):
        ari_to_runtime_plan(ari)


def test_multi_node_plan_carries_edges():
    g = echo_graph()
    g.add_agent(AgentNode(id="agent_2", name="Second", provider="mock"))
    g.add_edge("agent_1", "agent_2", when_contains="DRAFT")
    plan = ari_to_runtime_plan(compile_to_ari(g))
    assert {n["id"] for n in plan["nodes"]} == {"agent_1", "agent_2"}
    assert plan["edges"][0]["condition"] == {"type": "contains", "value": "DRAFT"}
