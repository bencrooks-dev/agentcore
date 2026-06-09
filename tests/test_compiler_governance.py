"""Governance authoring (policies, budget, failure semantics, rollback) compiles
into a valid ARI manifest, with clear errors on misuse."""
import pytest

from marrow.compiler import (
    AgentGraph,
    AgentNode,
    BudgetSpec,
    CompileError,
    FailureSemantics,
    PolicySpec,
    ProviderSpec,
    ToolSpec,
    compile_to_ari,
)
from marrow.compiler.validate import validate


def base_graph() -> AgentGraph:
    g = AgentGraph(name="governed")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(ToolSpec(name="echo", description="Echo"))
    g.add_agent(AgentNode(id="agent_1", name="A", provider="mock", tools=["echo"]))
    g.set_entrypoint("agent_1")
    return g


def governed_graph() -> AgentGraph:
    g = base_graph()
    g.add_policy(
        PolicySpec(
            id="p_provider",
            action="provider:mock",
            decision="allow",
            evidence_required=True,
        )
    )
    g.set_budget(BudgetSpec(max_steps=8, max_tokens=10_000, max_cost_usd=1.0))
    g.set_failure_semantics(FailureSemantics(on_provider_error="abort"))
    g.add_rollback_step("agent_1", "clear_state")
    return g


def test_governance_compiles_to_valid_ari():
    ari = compile_to_ari(governed_graph())
    validate(ari, "agent_graph.schema.json")  # must not raise
    assert ari["policies"][0]["action"] == "provider:mock"
    assert ari["policies"][0]["evidence_required"] is True
    assert ari["budget"] == {
        "id": "budget",
        "max_tokens": 10000,
        "max_cost_usd": 1.0,
        "max_steps": 8,
    }
    assert ari["failure_semantics"]["on_provider_error"] == "abort"
    assert ari["rollback"]["steps"] == [{"on": "agent_1", "action": "clear_state"}]


def test_plain_graph_omits_governance_keys():
    ari = compile_to_ari(base_graph())
    for key in ("policies", "budget", "failure_semantics", "rollback"):
        assert key not in ari


def test_invalid_policy_decision_rejected():
    g = base_graph()
    g.add_policy(PolicySpec(id="p", action="provider:mock", decision="maybe"))
    with pytest.raises(CompileError, match="invalid decision"):
        compile_to_ari(g)


def test_duplicate_policy_id_rejected():
    g = base_graph()
    g.add_policy(PolicySpec(id="dup", action="agent:agent_1"))
    g.add_policy(PolicySpec(id="dup", action="provider:mock"))
    with pytest.raises(CompileError, match="duplicate policy id"):
        compile_to_ari(g)


def test_empty_policy_action_rejected():
    g = base_graph()
    g.add_policy(PolicySpec(id="p", action=""))
    with pytest.raises(CompileError, match="empty action"):
        compile_to_ari(g)


def test_bad_budget_max_steps_rejected():
    g = base_graph()
    g.set_budget(BudgetSpec(max_steps=0))
    with pytest.raises(CompileError, match="max_steps"):
        compile_to_ari(g)


def test_negative_budget_tokens_rejected():
    g = base_graph()
    g.set_budget(BudgetSpec(max_steps=4, max_tokens=-1))
    with pytest.raises(CompileError, match="max_tokens"):
        compile_to_ari(g)


def test_rollback_unknown_agent_rejected():
    g = base_graph()
    g.add_rollback_step("ghost")
    with pytest.raises(CompileError, match="unknown agent"):
        compile_to_ari(g)
