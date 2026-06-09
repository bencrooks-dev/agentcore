"""Bring-your-own provider + tool: a custom provider drives a policy-gated tool
call through the compiler, with no API key.

A scripted provider (standing in for a real model) requests the `uppercase`
tool; the compiler gates the call on a require-approval policy, invokes your tool
implementation through the native runtime, records it as evidence, and feeds the
result back for a final answer.

Run:  python examples/tool_use_example.py
"""
import json

from marrow import GenerationResponse, PyProviderBase
from marrow.compiler import (
    AgentGraph,
    AgentNode,
    PolicySpec,
    ProviderSpec,
    ToolSpec,
    compile_and_run,
)


class ScriptedProvider(PyProviderBase):
    """Stands in for a real model: asks for the tool, then answers."""

    def __init__(self) -> None:
        super().__init__()
        self._n = 0

    def name(self) -> str:
        return "scripted"

    def generate(self, req):  # noqa: ARG002
        resp = GenerationResponse()
        resp.prompt_tokens = 2
        resp.completion_tokens = 3
        if self._n == 0:
            resp.content = json.dumps(
                {"tool_call": {"name": "uppercase", "arguments": {"text": "hello"}}}
            )
        else:
            resp.content = "Done — the tool uppercased the text."
        self._n += 1
        return resp


def uppercase(text: str) -> str:
    return text.upper()


def build_graph() -> AgentGraph:
    g = AgentGraph(name="byo_agent")
    g.add_provider(ProviderSpec(id="house", type="house-llm", model="house-1"))
    g.add_tool(
        ToolSpec(
            name="uppercase",
            description="Uppercase the input text",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
    )
    g.add_agent(
        AgentNode(
            id="agent_1",
            name="Worker",
            provider="house",
            system_prompt="Use tools when helpful.",
            tools=["uppercase"],
        )
    )
    g.set_entrypoint("agent_1")
    g.add_policy(
        PolicySpec(
            id="approve_tool",
            action="tool:uppercase",
            decision="require_approval",
            evidence_required=True,
        )
    )
    return g


def main() -> int:
    out = compile_and_run(
        build_graph(),
        "uppercase 'hello'",
        providers={"house-llm": lambda binding: ScriptedProvider()},  # BYO provider
        tools={"uppercase": uppercase},                                # BYO tool
        approver=lambda action, checkpoint: True,                      # grant approval
    )
    trace = out["trace"]
    print(json.dumps(trace, indent=2))

    checks = {
        "custom provider executed": any(
            c["provider"] == "house" for c in trace["provider_calls"]
        ),
        "custom tool was invoked": any(
            c["tool"] == "uppercase" and c["ok"] for c in trace["tool_calls"]
        ),
        "tool returned HELLO": any("HELLO" in c["result"] for c in trace["tool_calls"]),
        "tool approval recorded": any(
            d["action"] == "tool:uppercase" for d in trace["policy_decisions"]
        ),
        "run completed": trace["final_status"] == "completed",
        "no API key required": True,
    }
    print("\n=== Proof ===")
    ok = True
    for label, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
