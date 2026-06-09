# Compiler

The compiler turns a declaratively-defined **agent graph** into a portable,
content-addressed **RuntimePlan** and executes it through the native runtime,
emitting an **ExecutionTrace**. It compiles agent graphs and their
tool/provider/policy contracts — not arbitrary Python.

```
AgentGraph  →  ARI manifest (JSON)  →  RuntimePlan (JSON)  →  native runtime  →  ExecutionTrace (JSON)
```

## Author a graph

```python
from marrow.compiler import AgentGraph, AgentNode, ProviderSpec, ToolSpec

graph = AgentGraph(name="echo_agent")
graph.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
graph.add_tool(ToolSpec(name="echo", description="Echo input text"))
graph.add_agent(AgentNode(id="agent_1", name="Echo Agent", provider="mock",
                          system_prompt="You are a test echo agent.", tools=["echo"]))
graph.set_entrypoint("agent_1")
```

## Compile and run

`compile_and_run` runs the whole pipeline; `run_runtime_plan` is the executor.

```python
from marrow.compiler import compile_and_run

out = compile_and_run(graph, "Hello, Marrow.")
out["ari"]           # the ARI manifest
out["runtime_plan"]  # the lowered, deterministic plan
out["trace"]         # the ExecutionTrace
```

The mock provider needs no API key. `run_runtime_plan` takes optional keyword
arguments:

- **`providers={type: factory}`** — register a provider type. Built in:
  `mock`/`echo` (keyless default), `openai`/`anthropic`/`ollama` (need their SDK +
  key). Bring your own with a factory taking a binding dict.
- **`tools={name: callable}`** — supply tool implementations. When an agent emits
  `{"tool_call": {"name", "arguments"}}`, the call is gated by a `tool:<name>`
  policy, restricted to the agent's declared tools, invoked through the native
  ToolRegistry, recorded, and its result fed back.
- **`approver=fn`** — grant `require_approval` / `approval_required` policy
  actions (default: fail-closed).
- **`pricing={model: (prompt_rate, completion_rate)}`** — for cost budgets.

## Governance

Attach policy checkpoints and a budget to the graph; they are enforced at runtime
and recorded as evidence in the trace.

```python
from marrow.compiler import PolicySpec, BudgetSpec

graph.add_policy(PolicySpec(id="p", action="provider:mock",
                            decision="require_approval", evidence_required=True))
graph.set_budget(BudgetSpec(max_steps=8, max_tokens=10_000, max_wall_ms=5_000))
graph.add_rollback_step("agent_1", "clear_state")
```

A denied action halts the run (`final_status="denied"`); a budget breach halts it
(`"exhausted"` / `"over_budget"`); on any abnormal termination the rollback steps
run.

## Replay and deploy

```python
from marrow.compiler import replay, traces_equivalent, make_deployment_manifest

trace2 = replay(out["runtime_plan"], "Hello, Marrow.")
assert traces_equivalent(out["trace"], trace2)            # deterministic

manifest = make_deployment_manifest(out["runtime_plan"], target="edge")
```

## Other frontends

A graph can be authored in any language that emits the same ARI manifest — the
[TypeScript frontend](https://github.com/bencrooks-dev/marrow/tree/main/ts)
produces byte-identical manifests and the same `graph_id`. The full design is in
`docs/compiler_architecture.md` in the repository.
