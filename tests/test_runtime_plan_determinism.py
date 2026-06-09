"""RuntimePlan ids are deterministic, content-addressed, and self-consistent."""
from marrow.compiler import (
    AgentGraph,
    AgentNode,
    ProviderSpec,
    ToolSpec,
    ari_to_runtime_plan,
    canonical_json,
    compile_to_ari,
    runtime_plan_id,
)


def test_canonical_json_folds_integral_floats_for_cross_language_parity():
    # Integral floats fold to ints so Python and the TS frontend agree (JS has no
    # 1.0-vs-1 distinction); non-integral floats and bools are unchanged.
    assert canonical_json({"x": 1.0}) == '{"x":1}'
    assert canonical_json({"x": 0.0}) == '{"x":0}'
    assert canonical_json({"x": 1.5}) == '{"x":1.5}'
    assert canonical_json({"a": True, "b": False}) == '{"a":true,"b":false}'


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


def test_same_graph_same_plan_id():
    a = ari_to_runtime_plan(compile_to_ari(echo_graph()))
    b = ari_to_runtime_plan(compile_to_ari(echo_graph()))
    assert a["runtime_plan_id"] == b["runtime_plan_id"]
    assert a["graph_id"] == b["graph_id"]


def test_trivial_change_changes_plan_id():
    base = ari_to_runtime_plan(compile_to_ari(echo_graph()))
    g2 = echo_graph()
    g2.agents[0].system_prompt = "A different prompt."
    changed = ari_to_runtime_plan(compile_to_ari(g2))
    assert base["runtime_plan_id"] != changed["runtime_plan_id"]


def test_plan_id_is_self_consistent():
    plan = ari_to_runtime_plan(compile_to_ari(echo_graph()))
    # Recomputing the id over the plan (minus the id) reproduces it exactly.
    assert runtime_plan_id(plan) == plan["runtime_plan_id"]


def test_plan_id_independent_of_key_order():
    plan = ari_to_runtime_plan(compile_to_ari(echo_graph()))
    shuffled = dict(reversed(list(plan.items())))
    assert runtime_plan_id(shuffled) == plan["runtime_plan_id"]
