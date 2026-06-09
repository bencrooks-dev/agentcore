"""Execute a RuntimePlan through the native runtime and emit an ExecutionTrace.

The plan is first loaded into the native C++ ``RuntimePlan`` (``load_runtime_plan``);
execution then reads its nodes, edges, and bindings *from that native object* and
materialises them as a :class:`marrow.Runtime` with :class:`marrow.Agent` nodes
bound to the native ``MockProvider``, driving the same step/handoff loop
``run_graph`` uses and recording each agent/provider event into a native
``ExecutionTrace``. No new executor is added — the C++ engine runs the turns.

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
from .runtime_plan import load_runtime_plan
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
    execution still runs through the C++ engine and the C++ mock.

    The delegation re-enters the engine's GIL-released ``MockProvider`` path;
    pybind's GIL guards nest safely, so this is intentional, not a bug."""

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


def _edge_matches(edge: Any, output: str) -> bool:
    if edge.condition_type == "always":
        return True
    if edge.condition_type == "contains":
        return edge.condition_value in output
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

    # Load the plan into the native C++ RuntimePlan, then drive execution from
    # that object — the plan genuinely reaches and is read out of the native
    # layer, not just the validated dict.
    native = load_runtime_plan(plan)

    providers: dict[str, _RecordingProvider] = {}
    for provider_id in native.provider_ids():
        binding = native.provider(provider_id)
        if binding.type != "mock":
            raise CompileError(
                f"provider {provider_id!r} has unsupported type {binding.type!r}; "
                "the MVP executes mock providers only (no API keys required)"
            )
        providers[provider_id] = _RecordingProvider(_c.MockProvider(provider_id), provider_id)

    runtime = Runtime()
    nodes: dict[str, Any] = {}
    agents: dict[str, Any] = {}
    for node in native.nodes():
        if not native.has_provider(node.provider):
            raise CompileError(
                f"node {node.id!r} references unbound provider {node.provider!r}"
            )
        nodes[node.id] = node
        agents[node.id] = runtime.add(
            Agent(
                name=node.id,
                provider=providers[node.provider],
                system_prompt=node.system_prompt,
            )
        )

    edges = native.edges()
    trace = _c.ExecutionTrace(
        _trace_id(native.runtime_plan_id, initial_input),
        native.runtime_plan_id,
    )
    trace.set_input(initial_input)
    trace.set_started_at(_now_ms())

    current = native.entrypoint
    runtime.router.set_active(current)
    runtime.send(frm="<user>", to=current, text=initial_input)
    payload = initial_input
    final_status = "completed"

    try:
        for _ in range(MAX_STEPS):
            node = nodes[current]
            model = native.provider(node.provider).model

            _event(trace, "agent_started", agent=current)
            runtime.deliver(agents[current])
            payload = agents[current].step(model=model)
            resp = providers[node.provider].last
            _event(trace, "provider_called", agent=current, provider=node.provider)
            trace.add_provider_call(
                _c.ProviderCall(
                    current,
                    node.provider,
                    model,
                    int(getattr(resp, "prompt_tokens", 0) or 0),
                    int(getattr(resp, "completion_tokens", 0) or 0),
                )
            )
            _event(trace, "agent_completed", agent=current)

            next_node = None
            for edge in edges:
                if edge.from_ == current and _edge_matches(edge, payload):
                    next_node = edge.to
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
