"""The compiled RuntimePlan loads into, and is inspectable from, the native
C++ layer; the native ExecutionTrace records events and calls."""
import pytest

from marrow import _marrow as _c
from marrow.compiler import (
    AgentGraph,
    AgentNode,
    ProviderSpec,
    ToolSpec,
    ari_to_runtime_plan,
    compile_to_ari,
    load_runtime_plan,
)


def echo_plan() -> dict:
    g = AgentGraph(name="echo_agent")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(ToolSpec(name="echo", description="Echo input text", timeout_ms=1000))
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


def test_plan_loads_into_native_runtime():
    native = load_runtime_plan(echo_plan())
    assert isinstance(native, _c.RuntimePlan)
    assert native.version == "runtime_plan/v0.draft"
    assert native.graph_id.startswith("g_")
    assert native.runtime_plan_id.startswith("rp_")
    assert native.entrypoint == "agent_1"
    assert native.node_count() == 1
    assert native.edge_count() == 0


def test_native_plan_is_inspectable():
    native = load_runtime_plan(echo_plan())
    assert native.has_node("agent_1")
    node = native.node("agent_1")
    assert node.provider == "mock"
    assert node.tools == ["echo"]

    assert native.has_provider("mock")
    provider = native.provider("mock")
    assert provider.model == "mock-echo"
    assert provider.config_ref is None

    assert native.has_tool("echo")
    assert native.tool("echo").timeout_ms == 1000

    assert native.node_ids() == ["agent_1"]
    assert native.provider_ids() == ["mock"]
    assert native.tool_names() == ["echo"]


def test_native_plan_unknown_lookup_raises():
    native = load_runtime_plan(echo_plan())
    assert not native.has_node("ghost")
    with pytest.raises((IndexError, KeyError, RuntimeError)):
        native.node("ghost")


def test_native_execution_trace_records():
    tr = _c.ExecutionTrace("tr_abc", "rp_def")
    tr.set_input("hello")
    tr.set_started_at(1000)
    tr.set_completed_at(1005)
    tr.set_final_status("completed")
    tr.add_event("agent_started", [("agent", "agent_1")])
    tr.add_provider_call(_c.ProviderCall("agent_1", "mock", "mock-echo", 3, 7))

    assert tr.trace_id == "tr_abc"
    assert tr.runtime_plan_id == "rp_def"
    assert tr.has_input and tr.input == "hello"
    assert tr.started_at == 1000 and tr.completed_at == 1005
    assert tr.final_status == "completed"

    events = tr.events()
    assert events[0].type == "agent_started"
    assert list(events[0].attributes) == [("agent", "agent_1")]

    calls = tr.provider_calls()
    assert calls[0].model == "mock-echo"
    assert calls[0].prompt_tokens == 3 and calls[0].completion_tokens == 7


def test_native_id_accessors_are_sorted():
    g = AgentGraph(name="multi")
    g.add_provider(ProviderSpec(id="zeta", type="mock", model="m"))
    g.add_provider(ProviderSpec(id="alpha", type="mock", model="m"))
    g.add_tool(ToolSpec(name="zoo"))
    g.add_tool(ToolSpec(name="ant"))
    g.add_agent(AgentNode(id="a", name="A", provider="alpha", tools=["ant", "zoo"]))
    g.set_entrypoint("a")
    native = load_runtime_plan(ari_to_runtime_plan(compile_to_ari(g)))
    # Map-backed accessors return a deterministic (sorted) order across platforms.
    assert native.provider_ids() == ["alpha", "zeta"]
    assert native.tool_names() == ["ant", "zoo"]


def test_default_trace_status_is_completed():
    tr = _c.ExecutionTrace()
    assert tr.final_status == "completed"
    assert tr.events() == []
