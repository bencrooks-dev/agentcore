"""Execute a RuntimePlan through the native runtime and emit an ExecutionTrace.

This is the runtime-execution + trace-emission step (brief Phases 6-7). It does
NOT add a new executor: it materialises the plan as a :class:`marrow.Runtime`
with :class:`marrow.Agent` nodes bound to the native ``MockProvider``, then
drives the same step/handoff loop ``run_graph`` uses, recording each
agent/provider event into a native ``ExecutionTrace``.

The MVP executes mock providers only — no provider that needs an API key. The
trace's timestamps are wall-clock and therefore not reproducible; everything
else is deterministic for a given (plan, input).
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from .. import _marrow as _c
from .errors import CompileError
from .validate import validate

MAX_STEPS = 16


def _now_ms() -> int:
    return int(time.time() * 1000)


def _trace_id(runtime_plan_id: str, initial_input: str) -> str:
    digest = hashlib.sha256(
        (runtime_plan_id + "|" + initial_input).encode("utf-8")
    ).hexdigest()
    return "tr_" + digest[:16]


class _RecordingProvider(_c.Provider):
    """A Python provider that delegates to the native ``MockProvider`` and
    remembers the last response, so the executor can record token usage while
    execution still runs through the C++ engine and the C++ mock."""

    def __init__(self, inner: Any, provider_id: str) -> None:
        super().__init__()
        self._inner = inner
        self._id = provider_id
        self.last: Any = None

    def name(self) -> str:
        return self._id

    def generate(self, req: Any) -> Any:
        resp = self._inner.generate(req)
        self.last = resp
        return resp


def _build_provider(binding: dict[str, Any], provider_id: str) -> _RecordingProvider:
    if binding["type"] != "mock":
        raise CompileError(
            f"provider {provider_id!r} has unsupported type {binding['type']!r}; "
            "the MVP executes mock providers only (no API keys required)"
        )
    return _RecordingProvider(_c.MockProvider(provider_id), provider_id)


def _edge_matches(condition: dict[str, Any], output: str) -> bool:
    kind = condition.get("type")
    if kind == "always":
        return True
    if kind == "contains":
        return condition.get("value", "") in output
    return False


def _event(trace: Any, event_type: str, **attrs: str) -> None:
    trace.add_event(event_type, [(k, v) for k, v in attrs.items()])


def _trace_to_dict(trace: Any) -> dict[str, Any]:
    events = []
    for e in trace.events():
        item = {"type": e.type}
        item.update({k: v for k, v in e.attributes})
        events.append(item)
    return {
        "trace_id": trace.trace_id,
        "runtime_plan_id": trace.runtime_plan_id,
        "input": trace.input if trace.has_input else None,
        "started_at": trace.started_at,
        "completed_at": trace.completed_at,
        "events": events,
        "tool_calls": [
            {
                "agent": c.agent,
                "tool": c.tool,
                "args": c.args_json,
                "result": c.result_json,
                "ok": c.ok,
            }
            for c in trace.tool_calls()
        ],
        "provider_calls": [
            {
                "agent": c.agent,
                "provider": c.provider,
                "model": c.model,
                "prompt_tokens": c.prompt_tokens,
                "completion_tokens": c.completion_tokens,
            }
            for c in trace.provider_calls()
        ],
        "policy_decisions": [],
        "errors": [
            {"agent": e.agent, "kind": e.kind, "message": e.message}
            for e in trace.errors()
        ],
        "final_status": trace.final_status,
    }


def run_runtime_plan(plan: dict[str, Any], initial_input: str) -> dict[str, Any]:
    """Execute ``plan`` with ``initial_input`` and return an ExecutionTrace dict.

    Raises :class:`CompileError` if the plan is malformed or references a
    provider type the MVP cannot execute. The returned trace validates against
    ``execution_trace.schema.json``.
    """
    # Imported lazily so importing the compiler does not pull in the full SDK
    # until an execution is actually requested (and to avoid an import cycle
    # when ``marrow`` imports ``marrow.compiler``).
    from .. import Agent, Runtime

    validate(plan, "runtime_plan.schema.json")

    nodes = {n["id"]: n for n in plan["nodes"]}
    provider_bindings = plan["provider_bindings"]
    if plan["entrypoint"] not in nodes:
        raise CompileError(f"entrypoint {plan['entrypoint']!r} is not a node in the plan")

    providers = {
        pid: _build_provider(binding, pid)
        for pid, binding in provider_bindings.items()
    }
    runtime = Runtime()
    agents: dict[str, Any] = {}
    for node_id, node in nodes.items():
        if node["provider"] not in providers:
            raise CompileError(
                f"node {node_id!r} references unbound provider {node['provider']!r}"
            )
        agents[node_id] = runtime.add(
            Agent(
                name=node_id,
                provider=providers[node["provider"]],
                system_prompt=node["system_prompt"],
            )
        )

    trace = _c.ExecutionTrace(
        _trace_id(plan.get("runtime_plan_id", ""), initial_input),
        plan.get("runtime_plan_id", ""),
    )
    trace.set_input(initial_input)
    trace.set_started_at(_now_ms())

    current = plan["entrypoint"]
    runtime.router.set_active(current)
    runtime.send(frm="<user>", to=current, text=initial_input)
    payload = initial_input
    final_status = "completed"

    try:
        for _ in range(MAX_STEPS):
            node = nodes[current]
            provider_id = node["provider"]
            model = provider_bindings[provider_id]["model"]

            _event(trace, "agent_started", agent=current)
            runtime.deliver(agents[current])
            payload = agents[current].step(model=model)
            resp = providers[provider_id].last
            _event(trace, "provider_called", agent=current, provider=provider_id)
            trace.add_provider_call(
                _c.ProviderCall(
                    current,
                    provider_id,
                    model,
                    int(getattr(resp, "prompt_tokens", 0) or 0),
                    int(getattr(resp, "completion_tokens", 0) or 0),
                )
            )
            _event(trace, "agent_completed", agent=current)

            next_node = None
            for edge in plan["edges"]:
                if edge["from"] == current and _edge_matches(edge["condition"], payload):
                    next_node = edge["to"]
                    break
            if next_node is None:
                break
            runtime.handoff(frm=current, to=next_node, text=payload)
            current = next_node
            runtime.router.set_active(current)
        else:
            final_status = "exhausted"
            _event(trace, "max_steps_reached", agent=current)
    except Exception as exc:  # noqa: BLE001 — record any failure as evidence
        final_status = "error"
        trace.add_error(_c.TraceError(current, type(exc).__name__, str(exc)[:200]))
        _event(trace, "error", agent=current, kind=type(exc).__name__)

    trace.set_completed_at(_now_ms())
    trace.set_final_status(final_status)

    result = _trace_to_dict(trace)
    validate(result, "execution_trace.schema.json")
    return result
