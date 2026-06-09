"""Execute a RuntimePlan through the native runtime and emit an ExecutionTrace.

The plan is first loaded into the native C++ ``RuntimePlan`` (``load_runtime_plan``);
execution then reads its nodes, edges, and bindings *from that native object* and
materialises them as a :class:`marrow.Runtime` with :class:`marrow.Agent` nodes
bound to the native ``MockProvider``, driving the same step/handoff loop
``run_graph`` uses and recording each agent/provider event into a native
``ExecutionTrace``. No new executor is added — the C++ engine runs the turns.

Governance is enforced as the run proceeds: before each agent/provider action the
:class:`PolicyEngine` is consulted (a denied action halts the run with
``final_status="denied"``), and a :class:`BudgetMeter` bounds steps/tokens/cost
(``"exhausted"`` / ``"over_budget"``). Policy decisions and budget consumption are
recorded in the trace, and on any abnormal termination the plan's rollback steps
run. The MVP executes mock providers only — no provider that needs an API key.
The trace's timestamps are wall-clock and therefore not reproducible; everything
else is deterministic for a given (plan, input, approver, pricing).
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable

from .. import _marrow as _c
from .errors import CompileError
from .governance import Approver, BudgetMeter, PolicyEngine
from .providers import ProviderFactory, build_provider
from .runtime_plan import load_runtime_plan
from .validate import validate


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


MAX_TOOL_ITERATIONS = 8


def _edge_matches(edge: Any, output: str) -> bool:
    if edge.condition_type == "always":
        return True
    if edge.condition_type == "contains":
        return edge.condition_value in output
    return False


def _parse_tool_call(text: str) -> tuple[str, dict] | None:
    """Detect a tool-call request in a provider's output.

    A tool call is the JSON object ``{"tool_call": {"name": ..., "arguments":
    {...}}}``. Any other output is a final answer. This text convention works
    with any provider (the mock, a scripted test provider, or a real model
    prompted to emit it); native tool-call extraction for hosted providers is
    future work.
    """
    stripped = text.strip()
    if not (stripped.startswith("{") and '"tool_call"' in stripped):
        return None
    try:
        obj = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    call = obj.get("tool_call") if isinstance(obj, dict) else None
    if isinstance(call, dict) and isinstance(call.get("name"), str):
        args = call.get("arguments", {})
        return call["name"], args if isinstance(args, dict) else {}
    return None


def _tool_ok(result_json: str) -> bool:
    try:
        return bool(json.loads(result_json).get("ok", False))
    except (ValueError, TypeError, AttributeError):
        return False


def _event(trace: Any, event_type: str, **attrs: str) -> None:
    trace.add_event(event_type, [(k, v) for k, v in attrs.items()])


def _enforce_policy(
    engine: PolicyEngine, trace: Any, action: str, record_decisions: bool
) -> bool:
    """Evaluate ``action``; record each decision (when evidence calls for it) and
    a ``policy_checked`` event; return ``True`` only if every decision allows it."""
    allowed = True
    for decision in engine.evaluate(action):
        if record_decisions or decision.evidence_required:
            trace.add_policy_decision(
                _c.PolicyDecision(
                    decision.action,
                    decision.decision,
                    decision.allowed,
                    decision.approval_required,
                    decision.evidence_required,
                )
            )
        _event(
            trace,
            "policy_checked",
            action=decision.action,
            decision=decision.decision,
            allowed=str(decision.allowed).lower(),
        )
        if not decision.allowed:
            allowed = False
    return allowed


def _run_rollback(trace: Any, rollback_plan: dict[str, Any], agents: dict[str, Any]) -> None:
    steps = rollback_plan.get("steps", [])
    _event(trace, "rollback_started", steps=str(len(steps)))
    for step in steps:
        target = step["on"]
        action = step["action"]
        if action == "clear_state" and target in agents:
            agents[target]._state.clear()
        _event(trace, "rollback_step", agent=target, action=action)


def _trace_to_dict(trace: Any) -> dict[str, Any]:
    events = []
    for e in trace.events():
        item = {"type": e.type}
        item.update({k: v for k, v in e.attributes})
        events.append(item)
    result: dict[str, Any] = {
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
        "policy_decisions": [
            {
                "action": d.action,
                "decision": d.decision,
                "allowed": d.allowed,
                "approval_required": d.approval_required,
                "evidence_required": d.evidence_required,
            }
            for d in trace.policy_decisions()
        ],
        "errors": [
            {"agent": e.agent, "kind": e.kind, "message": e.message}
            for e in trace.errors()
        ],
        "final_status": trace.final_status,
    }
    if trace.has_budget_usage:
        u = trace.budget_usage()
        result["budget_usage"] = {
            "steps": u.steps,
            "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens,
            "total_tokens": u.prompt_tokens + u.completion_tokens,
            "cost_usd": u.cost_usd,
        }
    return result


def run_runtime_plan(
    plan: dict[str, Any],
    initial_input: str,
    *,
    approver: Approver | None = None,
    pricing: dict[str, tuple[float, float]] | None = None,
    providers: dict[str, ProviderFactory] | None = None,
    tools: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    """Execute ``plan`` with ``initial_input`` and return an ExecutionTrace dict.

    ``approver`` decides whether ``require_approval`` / ``approval_required``
    policy actions may proceed (default: fail-closed). ``pricing`` maps a model
    to ``(prompt_rate, completion_rate)`` per token for cost budgets (the mock
    model costs nothing). ``providers`` registers custom provider types (type ->
    factory) and overrides the built-ins (``mock``/``openai``/``anthropic``/
    ``ollama``). ``tools`` supplies tool implementations (name -> callable); when
    an agent requests a tool, the call is policy-gated, invoked through the C++
    ToolRegistry, recorded, and its result fed back. Raises :class:`CompileError`
    if the plan is malformed or a provider is unknown/unavailable. The returned
    trace validates against ``execution_trace.schema.json``.
    """
    # Imported lazily so importing the compiler does not pull in the full SDK
    # until an execution is actually requested (and to avoid an import cycle
    # when ``marrow`` imports ``marrow.compiler``).
    from .. import Agent, Runtime
    from ..tools import ToolBox, ToolDef

    validate(plan, "runtime_plan.schema.json")

    # Load the plan into the native C++ RuntimePlan, then drive execution from
    # that object — the plan genuinely reaches and is read out of the native
    # layer, not just the validated dict.
    native = load_runtime_plan(plan)

    provider_instances: dict[str, _RecordingProvider] = {}
    for provider_id in native.provider_ids():
        binding = native.provider(provider_id)
        spec = {
            "id": provider_id,
            "type": binding.type,
            "model": binding.model,
            "config_ref": binding.config_ref,
        }
        provider_instances[provider_id] = _RecordingProvider(
            build_provider(spec, providers), provider_id
        )

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
                provider=provider_instances[node.provider],
                system_prompt=node.system_prompt,
            )
        )

    # Governance config is read from the validated plan dict; decisions and usage
    # are recorded in the native trace.
    policy = PolicyEngine(plan.get("policy_checkpoints", []), approver)
    budget = BudgetMeter(plan.get("budget"), pricing)
    evidence_plan = plan.get("evidence_plan", {})
    record_policy = bool(evidence_plan.get("record_policy_decisions", True))
    record_provider = bool(evidence_plan.get("record_provider_calls", True))
    rollback_plan = plan.get("rollback_plan", {"steps": []})
    failure_semantics = plan.get("failure_semantics", {})
    on_tool_error = failure_semantics.get("on_tool_error", "record_and_continue")

    # Register supplied tool implementations into the C++ ToolRegistry; the
    # manifest declares the contract (schemas), the caller supplies the body.
    if tools:
        box = ToolBox()
        for tool_name, tool_fn in tools.items():
            schema: dict[str, Any] = {}
            if native.has_tool(tool_name):
                raw = native.tool(tool_name).input_schema_json
                if raw:
                    try:
                        schema = json.loads(raw)
                    except (ValueError, TypeError):
                        schema = {}
            box.add(ToolDef(name=tool_name, description="", schema=schema, fn=tool_fn))
        box.bind(runtime)

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
        while True:
            if not budget.can_start_step():
                final_status = "exhausted"
                _event(trace, "max_steps_reached", agent=current)
                break
            budget.record_step()
            node = nodes[current]

            denied = False
            for action in (f"agent:{current}", f"provider:{node.provider}"):
                if not _enforce_policy(policy, trace, action, record_policy):
                    denied = True
            if denied:
                final_status = "denied"
                trace.add_error(
                    _c.TraceError(current, "PolicyDenied", "action denied by policy")
                )
                _event(trace, "denied", agent=current)
                break

            model = native.provider(node.provider).model
            _event(trace, "agent_started", agent=current)
            runtime.deliver(agents[current])

            # Agent turn: generate, and while the output requests a tool, gate it
            # by policy, invoke it, record it, and feed the result back.
            turn_status = None
            for _ in range(MAX_TOOL_ITERATIONS + 1):
                payload = agents[current].step(model=model)
                resp = provider_instances[node.provider].last
                prompt_tokens = int(getattr(resp, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(resp, "completion_tokens", 0) or 0)
                budget.record_provider_usage(model, prompt_tokens, completion_tokens)
                _event(trace, "provider_called", agent=current, provider=node.provider)
                if record_provider:
                    trace.add_provider_call(
                        _c.ProviderCall(
                            current, node.provider, model, prompt_tokens, completion_tokens
                        )
                    )
                if budget.over_tokens() or budget.over_cost():
                    turn_status = "over_budget"
                    break

                call = _parse_tool_call(payload)
                if call is None:
                    break  # final answer for this node

                tool_name, tool_args = call
                if not _enforce_policy(policy, trace, f"tool:{tool_name}", record_policy):
                    turn_status = "denied"
                    break
                if not runtime.tools.has(tool_name):
                    trace.add_error(
                        _c.TraceError(current, "UnknownTool", f"tool {tool_name!r} not provided")
                    )
                    _event(trace, "tool_error", agent=current, tool=tool_name)
                    if on_tool_error == "abort":
                        turn_status = "error"
                        break
                    agents[current].append_tool(
                        tool_name, json.dumps({"ok": False, "error": "unknown tool"})
                    )
                    continue

                args_json = json.dumps(tool_args)
                try:
                    result_json = runtime.tools.invoke(tool_name, args_json)
                except Exception as exc:  # noqa: BLE001 — surface tool failures as evidence
                    result_json = json.dumps({"ok": False, "error": str(exc)[:200]})
                ok = _tool_ok(result_json)
                trace.add_tool_call(
                    _c.ToolCall(current, tool_name, args_json, result_json, ok)
                )
                _event(trace, "tool_called", agent=current, tool=tool_name, ok=str(ok).lower())
                if not ok and on_tool_error == "abort":
                    trace.add_error(
                        _c.TraceError(current, "ToolError", f"tool {tool_name!r} failed")
                    )
                    turn_status = "error"
                    break
                agents[current].append_tool(tool_name, result_json)
            else:
                trace.add_error(
                    _c.TraceError(current, "ToolLoopExhausted", "max tool iterations reached")
                )
                turn_status = "error"

            if turn_status == "over_budget":
                final_status = "over_budget"
                trace.add_error(
                    _c.TraceError(current, "BudgetExceeded", "token or cost budget exceeded")
                )
                _event(trace, "budget_exceeded", agent=current)
                break
            if turn_status == "denied":
                final_status = "denied"
                trace.add_error(
                    _c.TraceError(current, "PolicyDenied", "tool action denied by policy")
                )
                _event(trace, "denied", agent=current)
                break
            if turn_status == "error":
                final_status = "error"
                _event(trace, "error", agent=current, kind="tool")
                break

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
    except Exception as exc:  # noqa: BLE001 — record any failure as evidence
        # The abort path is realized; the configured mode is surfaced for evidence.
        mode = failure_semantics.get("on_provider_error", "abort")
        final_status = "error"
        trace.add_error(_c.TraceError(current, type(exc).__name__, str(exc)[:200]))
        _event(trace, "error", agent=current, kind=type(exc).__name__, mode=mode)

    usage = budget.usage()
    trace.set_budget_usage(
        _c.BudgetUsage(
            usage["steps"],
            usage["prompt_tokens"],
            usage["completion_tokens"],
            usage["cost_usd"],
        )
    )
    if final_status != "completed" and rollback_plan.get("steps"):
        _run_rollback(trace, rollback_plan, agents)

    trace.set_completed_at(_now_ms())
    trace.set_final_status(final_status)

    result = _trace_to_dict(trace)
    validate(result, "execution_trace.schema.json")
    return result
