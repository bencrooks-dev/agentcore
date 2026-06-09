"""Frontend authoring + ARI manifest emission, including clear failures for
invalid graphs / missing providers / missing tools."""
import pytest

from marrow.compiler import (
    AgentGraph,
    AgentNode,
    CompileError,
    ProviderSpec,
    ToolSpec,
    compile_to_ari,
    graph_id,
)


def echo_graph() -> AgentGraph:
    g = AgentGraph(name="echo_agent")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(
        ToolSpec(
            name="echo",
            description="Echo input text",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            output_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            side_effects=False,
            timeout_ms=1000,
            requires_approval=False,
        )
    )
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


def test_compile_to_ari_structure():
    ari = compile_to_ari(echo_graph())
    assert ari["version"] == "ari/v0.draft"
    assert ari["name"] == "echo_agent"
    assert ari["entrypoint"] == "agent_1"
    assert [p["id"] for p in ari["providers"]] == ["mock"]
    assert [t["name"] for t in ari["tools"]] == ["echo"]
    assert ari["agents"][0]["id"] == "agent_1"
    assert ari["edges"] == []


def test_graph_id_is_deterministic_and_stable():
    a = compile_to_ari(echo_graph())
    b = compile_to_ari(echo_graph())
    assert graph_id(a) == graph_id(b)
    assert graph_id(a).startswith("g_")
    assert len(graph_id(a)) == len("g_") + 16


def test_graph_id_changes_with_content():
    base = compile_to_ari(echo_graph())
    changed_graph = echo_graph()
    changed_graph.agents[0].system_prompt = "Different prompt."
    changed = compile_to_ari(changed_graph)
    assert graph_id(base) != graph_id(changed)


def test_missing_entrypoint_raises():
    g = echo_graph()
    g.entrypoint = None
    with pytest.raises(CompileError, match="entrypoint"):
        compile_to_ari(g)


def test_entrypoint_referencing_unknown_agent_raises():
    g = echo_graph()
    g.set_entrypoint("ghost")
    with pytest.raises(CompileError, match="entrypoint"):
        compile_to_ari(g)


def test_missing_provider_raises():
    g = AgentGraph(name="bad")
    g.add_agent(AgentNode(id="a", name="A", provider="nope"))
    g.set_entrypoint("a")
    with pytest.raises(CompileError, match="unknown provider"):
        compile_to_ari(g)


def test_missing_tool_raises():
    g = AgentGraph(name="bad")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_agent(AgentNode(id="a", name="A", provider="mock", tools=["ghost"]))
    g.set_entrypoint("a")
    with pytest.raises(CompileError, match="unknown tool"):
        compile_to_ari(g)


def test_duplicate_agent_id_raises():
    g = AgentGraph(name="dup")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_agent(AgentNode(id="a", name="A", provider="mock"))
    g.add_agent(AgentNode(id="a", name="A2", provider="mock"))
    g.set_entrypoint("a")
    with pytest.raises(CompileError, match="duplicate agent id"):
        compile_to_ari(g)


def test_edge_with_condition_serialises():
    g = echo_graph()
    g.add_agent(AgentNode(id="agent_2", name="Second", provider="mock"))
    g.add_edge("agent_1", "agent_2", when_contains="DRAFT")
    ari = compile_to_ari(g)
    assert ari["edges"][0] == {
        "from": "agent_1",
        "to": "agent_2",
        "condition": {"type": "contains", "value": "DRAFT"},
    }


def test_edge_to_unknown_agent_raises():
    g = echo_graph()
    g.add_edge("agent_1", "ghost")
    with pytest.raises(CompileError, match="unknown target agent"):
        compile_to_ari(g)
