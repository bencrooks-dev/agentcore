"""The C++ core parses RuntimePlan JSON and serializes ExecutionTrace JSON
itself (its own dependency-free parser), including escapes and unicode."""
import json

import pytest

from marrow import _marrow as _c
from marrow.compiler import (
    AgentGraph,
    AgentNode,
    ProviderSpec,
    ToolSpec,
    ari_to_runtime_plan,
    compile_to_ari,
)


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


def test_runtime_plan_parsed_from_json_in_cpp():
    plan = echo_plan()
    native = _c.RuntimePlan.from_json(json.dumps(plan))
    assert native.runtime_plan_id == plan["runtime_plan_id"]
    assert native.graph_id == plan["graph_id"]
    assert native.entrypoint == "agent_1"
    assert native.node_count() == 1
    assert native.node("agent_1").provider == "mock"
    assert native.provider("mock").model == "mock-echo"
    assert native.tool("echo").timeout_ms == 1000


def test_from_json_preserves_nested_schema():
    native = _c.RuntimePlan.from_json(json.dumps(echo_plan()))
    schema = json.loads(native.tool("echo").input_schema_json)
    assert schema["type"] == "object"


def test_malformed_json_raises():
    with pytest.raises(Exception):  # noqa: B017 — any parse failure is acceptable
        _c.RuntimePlan.from_json("{not valid json")


def test_execution_trace_to_json_roundtrips_with_escapes():
    tr = _c.ExecutionTrace("tr_x", "rp_y")
    tr.set_input('he said "hi"\nthen left')  # quotes + newline must be escaped
    tr.add_event("agent_started", [("agent", "a")])
    tr.add_provider_call(_c.ProviderCall("a", "mock", "mock-echo", 3, 7))
    tr.set_final_status("completed")
    doc = json.loads(tr.to_json())
    assert doc["trace_id"] == "tr_x"
    assert doc["input"] == 'he said "hi"\nthen left'
    assert doc["events"][0] == {"type": "agent_started", "agent": "a"}
    assert doc["provider_calls"][0]["prompt_tokens"] == 3
    assert doc["final_status"] == "completed"


def test_unicode_escapes_roundtrip_through_cpp_parser():
    plan = echo_plan()
    # json.dumps emits \uXXXX escapes (and surrogate pairs for astral chars);
    # the C++ parser must decode them back to UTF-8.
    plan["nodes"][0]["system_prompt"] = "café — ünïcode ✓ 😀"
    native = _c.RuntimePlan.from_json(json.dumps(plan))
    assert native.node("agent_1").system_prompt == "café — ünïcode ✓ 😀"
