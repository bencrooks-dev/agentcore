"""The tool-use loop: agents request tools, calls are policy-gated, invoked
through the C++ ToolRegistry, recorded, and their results fed back."""
import json
import time

from marrow import GenerationResponse, PyProviderBase
from marrow.compiler import (
    AgentGraph,
    AgentNode,
    BudgetSpec,
    FailureSemantics,
    PolicySpec,
    ProviderSpec,
    ToolSpec,
    compile_and_run,
)


class _ScriptedProvider(PyProviderBase):
    """Emits a tool_call on the first turn, then a final answer."""

    def __init__(self, tool_name: str, args: dict, final: str) -> None:
        super().__init__()
        self._n = 0
        self._tool = tool_name
        self._args = args
        self._final = final

    def name(self) -> str:
        return "scripted"

    def generate(self, req):  # noqa: ARG002
        resp = GenerationResponse()
        resp.prompt_tokens = 1
        resp.completion_tokens = 1
        if self._n == 0:
            resp.content = json.dumps(
                {"tool_call": {"name": self._tool, "arguments": self._args}}
            )
        else:
            resp.content = self._final
        self._n += 1
        return resp


def _graph(*, policy: PolicySpec | None = None, failure: FailureSemantics | None = None):
    g = AgentGraph(name="toolagent")
    g.add_provider(ProviderSpec(id="s", type="scripted", model="s1"))
    g.add_tool(
        ToolSpec(
            name="echo",
            description="echo",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
    )
    g.add_agent(AgentNode(id="a", name="A", provider="s", tools=["echo"]))
    g.set_entrypoint("a")
    if policy is not None:
        g.add_policy(policy)
    if failure is not None:
        g.set_failure_semantics(failure)
    return g


def _with(provider):
    return {"providers": {"scripted": lambda b: provider}}


def test_tool_use_loop_invokes_tool_and_returns_final():
    provider = _ScriptedProvider("echo", {"text": "hi"}, "final answer")
    trace = compile_and_run(
        _graph(), "go", tools={"echo": lambda text: f"echoed:{text}"}, **_with(provider)
    )["trace"]
    assert trace["final_status"] == "completed"
    assert len(trace["tool_calls"]) == 1
    call = trace["tool_calls"][0]
    assert call["tool"] == "echo" and call["ok"] is True
    assert "echoed:hi" in call["result"]
    assert len(trace["provider_calls"]) == 2  # tool turn + final turn
    assert "tool_called" in [e["type"] for e in trace["events"]]


def test_tool_policy_now_blocks_a_tool_call():
    provider = _ScriptedProvider("echo", {"text": "hi"}, "never reached")
    g = _graph(policy=PolicySpec(id="block", action="tool:echo", decision="deny"))
    trace = compile_and_run(
        g, "go", tools={"echo": lambda text: text}, **_with(provider)
    )["trace"]
    assert trace["final_status"] == "denied"
    assert trace["tool_calls"] == []  # the tool never ran
    blocked = [d for d in trace["policy_decisions"] if d["action"] == "tool:echo"]
    assert blocked and blocked[0]["allowed"] is False


def test_tool_require_approval_without_approver_denies():
    g = _graph(policy=PolicySpec(id="ap", action="tool:echo", decision="require_approval"))
    trace = compile_and_run(
        g,
        "go",
        tools={"echo": lambda text: text},
        **_with(_ScriptedProvider("echo", {"text": "hi"}, "done")),
    )["trace"]
    assert trace["final_status"] == "denied"


def test_tool_require_approval_with_approver_completes():
    g = _graph(policy=PolicySpec(id="ap", action="tool:echo", decision="require_approval"))
    trace = compile_and_run(
        g,
        "go",
        approver=lambda action, cp: True,
        tools={"echo": lambda text: text},
        **_with(_ScriptedProvider("echo", {"text": "hi"}, "done")),
    )["trace"]
    assert trace["final_status"] == "completed"
    assert len(trace["tool_calls"]) == 1


def test_unknown_tool_records_and_continues_by_default():
    provider = _ScriptedProvider("ghost", {}, "final after missing tool")
    trace = compile_and_run(_graph(), "go", tools={}, **_with(provider))["trace"]
    assert trace["final_status"] == "completed"
    assert any(e["kind"] == "UnknownTool" for e in trace["errors"])


def test_unknown_tool_aborts_when_configured():
    provider = _ScriptedProvider("ghost", {}, "unused")
    g = _graph(failure=FailureSemantics(on_tool_error="abort"))
    trace = compile_and_run(g, "go", tools={}, **_with(provider))["trace"]
    assert trace["final_status"] == "error"


def test_failing_tool_records_and_continues_by_default():
    def boom(text):
        raise ValueError("kaboom")

    provider = _ScriptedProvider("echo", {"text": "x"}, "final after failing tool")
    trace = compile_and_run(_graph(), "go", tools={"echo": boom}, **_with(provider))["trace"]
    assert trace["final_status"] == "completed"
    assert trace["tool_calls"][0]["ok"] is False


def test_failing_tool_aborts_when_configured():
    def boom(text):
        raise ValueError("kaboom")

    g = _graph(failure=FailureSemantics(on_tool_error="abort"))
    trace = compile_and_run(
        g, "go", tools={"echo": boom}, **_with(_ScriptedProvider("echo", {"text": "x"}, "z"))
    )["trace"]
    assert trace["final_status"] == "error"


class _RaisingProvider(PyProviderBase):
    """A provider whose generate always raises (simulates a real provider down)."""

    def name(self) -> str:
        return "boom"

    def generate(self, req):  # noqa: ARG002
        raise RuntimeError("provider down")


def test_provider_error_aborts_by_default():
    trace = compile_and_run(_graph(), "go", tools={}, **_with(_RaisingProvider()))["trace"]
    assert trace["final_status"] == "error"
    assert any(e["kind"] == "RuntimeError" for e in trace["errors"])
    assert "provider_error" in [e["type"] for e in trace["events"]]


def test_provider_error_record_and_continue():
    g = _graph(failure=FailureSemantics(on_provider_error="record_and_continue"))
    trace = compile_and_run(g, "go", tools={}, **_with(_RaisingProvider()))["trace"]
    # The run continues past the provider failure rather than aborting.
    assert trace["final_status"] == "completed"
    assert any(e["kind"] == "RuntimeError" for e in trace["errors"])


def test_wall_clock_budget_halts_a_slow_tool():
    def slow(text):
        time.sleep(0.05)
        return text

    g = _graph()
    g.set_budget(BudgetSpec(max_steps=4, max_wall_ms=1))
    trace = compile_and_run(
        g, "go", tools={"echo": slow}, **_with(_ScriptedProvider("echo", {"text": "x"}, "final"))
    )["trace"]
    assert trace["final_status"] == "over_budget"
