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


def test_duplicate_agent_id_in_ari_rejected():
    # A hand-built ARI (bypassing the frontend) with two agents sharing an id
    # must be rejected here, not silently deduped at execution time.
    ari = echo_ari()
    ari["agents"] = [ari["agents"][0], dict(ari["agents"][0])]
    with pytest.raises(CompileError, match="duplicate agent id"):
        ari_to_runtime_plan(ari)


def test_plan_is_standalone_of_source_ari():
    ari = echo_ari()
    plan = ari_to_runtime_plan(ari)
    plan_id = plan["runtime_plan_id"]
    # Mutating the source ARI after compiling must not change the plan.
    ari["tools"][0]["input_schema"]["injected"] = 999
    assert "injected" not in plan["tool_bindings"]["echo"]["input_schema"]
    assert plan["runtime_plan_id"] == plan_id


def test_plan_edge_condition_is_standalone():
    g = echo_graph()
    g.add_agent(AgentNode(id="agent_2", name="Second", provider="mock"))
    g.add_edge("agent_1", "agent_2", when_contains="X")
    ari = compile_to_ari(g)
    plan = ari_to_runtime_plan(ari)
    ari["edges"][0]["condition"]["value"] = "MUTATED"
    assert plan["edges"][0]["condition"]["value"] == "X"


def test_multi_node_plan_carries_edges():
    g = echo_graph()
    g.add_agent(AgentNode(id="agent_2", name="Second", provider="mock"))
    g.add_edge("agent_1", "agent_2", when_contains="DRAFT")
    plan = ari_to_runtime_plan(compile_to_ari(g))
    assert {n["id"] for n in plan["nodes"]} == {"agent_1", "agent_2"}
    assert plan["edges"][0]["condition"] == {"type": "contains", "value": "DRAFT"}
