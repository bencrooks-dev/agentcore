"""Policy and budget enforcement during execution: denials halt and roll back,
budgets bound the run, and evidence is recorded in the trace."""
from marrow.compiler import (
    AgentGraph,
    AgentNode,
    BudgetSpec,
    PolicySpec,
    ProviderSpec,
    ToolSpec,
    compile_and_run,
    compile_graph,
    run_runtime_plan,
)


def single_agent(budget: BudgetSpec | None = None) -> AgentGraph:
    g = AgentGraph(name="one")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(ToolSpec(name="echo", description="Echo"))
    g.add_agent(AgentNode(id="agent_1", name="A", provider="mock", tools=["echo"]))
    g.set_entrypoint("agent_1")
    if budget is not None:
        g.set_budget(budget)
    return g


def two_agent() -> AgentGraph:
    g = AgentGraph(name="pipe")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_agent(AgentNode(id="a", name="A", provider="mock"))
    g.add_agent(AgentNode(id="b", name="B", provider="mock"))
    g.add_edge("a", "b")
    g.set_entrypoint("a")
    return g


# --- policy enforcement ------------------------------------------------------


def test_deny_policy_halts_and_rolls_back():
    g = single_agent()
    g.add_policy(PolicySpec(id="block", action="provider:mock", decision="deny"))
    g.add_rollback_step("agent_1", "clear_state")
    trace = compile_and_run(g, "hi")["trace"]
    assert trace["final_status"] == "denied"
    assert any(e["kind"] == "PolicyDenied" for e in trace["errors"])
    blocked = [d for d in trace["policy_decisions"] if d["action"] == "provider:mock"]
    assert blocked and blocked[0]["allowed"] is False
    # The provider never ran (policy is checked before the step).
    assert trace["provider_calls"] == []
    types = [e["type"] for e in trace["events"]]
    assert "rollback_started" in types and "rollback_step" in types


def test_require_approval_without_approver_is_denied():
    g = single_agent()
    g.add_policy(PolicySpec(id="appr", action="provider:mock", decision="require_approval"))
    trace = compile_and_run(g, "hi")["trace"]
    assert trace["final_status"] == "denied"


def test_require_approval_with_approver_completes():
    g = single_agent()
    g.add_policy(PolicySpec(id="appr", action="provider:mock", decision="require_approval"))
    trace = compile_and_run(g, "hi", approver=lambda action, cp: True)["trace"]
    assert trace["final_status"] == "completed"
    assert trace["provider_calls"][0]["provider"] == "mock"


def test_allow_policy_records_evidence():
    g = single_agent()
    g.add_policy(
        PolicySpec(id="ok", action="provider:mock", decision="allow", evidence_required=True)
    )
    trace = compile_and_run(g, "hi")["trace"]
    assert trace["final_status"] == "completed"
    recorded = [d for d in trace["policy_decisions"] if d["action"] == "provider:mock"]
    assert recorded and recorded[0]["allowed"] is True
    assert recorded[0]["evidence_required"] is True


def test_no_policies_means_no_decisions():
    trace = compile_and_run(single_agent(), "hi")["trace"]
    assert trace["final_status"] == "completed"
    assert trace["policy_decisions"] == []


# --- budget enforcement ------------------------------------------------------


def test_step_budget_exhausts_pipeline():
    g = two_agent()
    g.set_budget(BudgetSpec(max_steps=1))
    trace = compile_and_run(g, "go")["trace"]
    assert trace["final_status"] == "exhausted"
    assert trace["budget_usage"]["steps"] == 1
    assert len(trace["provider_calls"]) == 1  # only the first agent ran
    assert "max_steps_reached" in [e["type"] for e in trace["events"]]


def test_token_budget_over():
    g = single_agent(BudgetSpec(max_steps=4, max_tokens=1))
    trace = compile_and_run(g, "hello world")["trace"]
    assert trace["final_status"] == "over_budget"
    assert any(e["kind"] == "BudgetExceeded" for e in trace["errors"])
    assert trace["budget_usage"]["total_tokens"] > 1


def test_budget_usage_present_on_happy_path():
    trace = compile_and_run(single_agent(), "hi")["trace"]
    usage = trace["budget_usage"]
    assert usage["steps"] == 1
    assert usage["cost_usd"] == 0.0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_cost_budget_over_with_pricing():
    g = single_agent(BudgetSpec(max_steps=4, max_cost_usd=0.0))
    # Any positive price makes the mock run exceed a zero-dollar budget.
    trace = compile_and_run(g, "spend", pricing={"mock-echo": (1.0, 1.0)})["trace"]
    assert trace["final_status"] == "over_budget"


def test_generous_budget_completes():
    g = single_agent(BudgetSpec(max_steps=8, max_tokens=100000, max_cost_usd=10.0))
    trace = compile_and_run(g, "hi")["trace"]
    assert trace["final_status"] == "completed"


# --- documented limitations & evidence gating -------------------------------


def test_tool_action_policy_is_not_triggered_by_the_mock_loop():
    # Documented limitation: the mock provider never invokes tools, so a
    # tool:<name> policy is only evaluated by the PolicyEngine (see
    # test_governance_engine), not during a mock run. A "*" policy gates
    # everything; this test pins the current (intentional) behavior.
    g = single_agent()
    g.add_policy(PolicySpec(id="t", action="tool:echo", decision="deny"))
    trace = compile_and_run(g, "hi")["trace"]
    assert trace["final_status"] == "completed"
    assert trace["policy_decisions"] == []


def test_wildcard_policy_does_gate_the_run():
    g = single_agent()
    g.add_policy(PolicySpec(id="all", action="*", decision="deny"))
    trace = compile_and_run(g, "hi")["trace"]
    assert trace["final_status"] == "denied"


def test_record_provider_calls_can_be_disabled():
    plan = compile_graph(single_agent())["runtime_plan"]
    plan["evidence_plan"]["record_provider_calls"] = False
    trace = run_runtime_plan(plan, "hi")
    assert trace["final_status"] == "completed"
    assert trace["provider_calls"] == []
    # Budget is still metered even when provider-call evidence is off.
    assert trace["budget_usage"]["steps"] == 1
