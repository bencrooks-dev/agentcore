"""Build the echo-agent graph compiled by this example.

A single mock-provider agent with one tool — the smallest graph that still
exercises providers, tools, agents, and an entrypoint.
"""
from marrow.compiler import AgentGraph, AgentNode, ProviderSpec, ToolSpec


def build_graph() -> AgentGraph:
    graph = AgentGraph(name="echo_agent")
    graph.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    graph.add_tool(
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
    graph.add_agent(
        AgentNode(
            id="agent_1",
            name="Echo Agent",
            provider="mock",
            system_prompt="You are a test echo agent.",
            tools=["echo"],
        )
    )
    graph.set_entrypoint("agent_1")
    return graph


if __name__ == "__main__":
    g = build_graph()
    print(f"built graph {g.name!r}: {len(g.agents)} agent(s), {len(g.tools)} tool(s)")
