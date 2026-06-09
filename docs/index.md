---
hide:
  - navigation
  - toc
---

<div class="mw-hero" markdown>

# Marrow

<img class="mw-hero-logo mw-logo-dark" src="assets/marrow-logo.png" alt="Marrow" />
<img class="mw-hero-logo mw-logo-light" src="assets/marrow-logo-light.png" alt="Marrow" />

<p class="mw-eyebrow">Agent Runtime Interface · reference implementation</p>

<p class="mw-tagline">The native runtime — and compiler — that runs an agent, below MCP and A2A.</p>

<p class="mw-sub">Author an agent graph in Python or TypeScript. Marrow compiles it into a portable, governed plan and runs it on a thread-safe C++ core.</p>

<div class="mw-cta" markdown>
[Get started](getting-started.md){ .md-button .md-button--primary }
[The compiler](concepts/compiler.md){ .md-button }
[GitHub](https://github.com/bencrooks-dev/marrow){ .md-button }
</div>

</div>

<p class="mw-center"><strong>The agent stack — and where Marrow sits.</strong> ARI is the runtime layer <em>beneath</em> the protocols; it complements MCP and A2A, it does not compete with them.</p>

<div class="mw-stack">
  <div class="mw-layer"><b>A2A</b> <span>agent-to-agent messaging</span></div>
  <div class="mw-layer"><b>MCP</b> <span>tool / context exchange</span></div>
  <div class="mw-layer mw-layer--ari"><b>ARI — Marrow</b> <span>state · provider · tools · routing</span></div>
  <div class="mw-layer"><b>Model provider</b> <span>OpenAI · Anthropic · Ollama · local</span></div>
</div>

<p class="mw-center" style="margin-top:1.6rem"><strong>And the compiler lowers an authored graph onto that runtime.</strong></p>

<div class="mw-pipeline">
  <span class="mw-node">AgentGraph</span><span class="mw-arrow">→</span>
  <span class="mw-node">ARI manifest</span><span class="mw-arrow">→</span>
  <span class="mw-node">RuntimePlan</span><span class="mw-arrow">→</span>
  <span class="mw-node mw-node--accent">native runtime</span><span class="mw-arrow">→</span>
  <span class="mw-node">ExecutionTrace</span>
</div>

## What you get

<div class="grid cards" markdown>

-   __AI-aware compiler__

    ---

    Author an `AgentGraph`, compile to an ARI manifest → a deterministic
    `RuntimePlan` → execute → a portable `ExecutionTrace`. Content-addressed ids
    make the whole chain reproducible and replayable.

    [The compiler →](concepts/compiler.md)

-   __Governance, enforced__

    ---

    Policy checkpoints (`allow` / `deny` / `require_approval`, with an approver
    and evidence), budgets (steps / tokens / cost / wall-clock), rollback on
    failure, and deterministic replay — all recorded in the trace.

    [Compiler concept →](concepts/compiler.md)

-   __Policy-gated tool use__

    ---

    Agents request tools; the call is gated by `tool:` policy and restricted to
    the agent's declared tools, invoked through the C++ registry, recorded, and
    its result fed back. Bring your own tools.

    [Tools →](concepts/tools.md)

-   __Pluggable providers__

    ---

    `mock` (keyless default), `openai` / `anthropic` / `ollama` built in, or
    bring-your-own via a factory — the same plan runs on any of them.

    [Providers →](concepts/providers.md)

-   __MCP gateway — govern any agent__

    ---

    A transparent proxy in front of any MCP server: policy-gate every tool
    call, hide what the agent may not use, bound calls and wall-clock — **zero
    changes to your agent or server**.

    [MCP gateway →](concepts/gateway.md)

-   __Flight recorder__

    ---

    Every run leaves evidence: provider calls, tool calls, policy decisions,
    budget burn. `marrow-trace` renders it as a self-contained report — or
    [drop a trace in your browser](trace-viewer.html), nothing uploaded.

    [Flight recorder →](concepts/flight-recorder.md)

-   __Native, embeddable core__

    ---

    Message state, routing, and tool dispatch run in C++17 with the GIL released,
    `std::shared_mutex` for read-heavy paths, and no third-party C++ deps. The
    core compiles as a standalone library — embed it without shipping Python.

    [Architecture →](architecture.md)

-   __Two frontends, one manifest__

    ---

    A Python frontend and a TypeScript frontend that emits **byte-identical**
    ARI — verified by a cross-language parity test on the `graph_id`. More
    languages emit ARI the same way.

    [TypeScript frontend →](https://github.com/bencrooks-dev/marrow/tree/main/ts)

</div>

## Compile, govern, and run — in a few lines

```python
from marrow.compiler import (
    AgentGraph, AgentNode, ProviderSpec, ToolSpec, PolicySpec, BudgetSpec, compile_and_run,
)

graph = AgentGraph(name="assistant")
graph.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))  # keyless
graph.add_tool(ToolSpec(name="search", description="Search the web"))
graph.add_agent(AgentNode(id="agent_1", name="Assistant", provider="mock", tools=["search"]))
graph.set_entrypoint("agent_1")

# Govern it: require approval before tools, bound the spend, roll back on failure.
graph.add_policy(PolicySpec(id="p", action="tool:search", decision="require_approval", evidence_required=True))
graph.set_budget(BudgetSpec(max_steps=8, max_tokens=10_000, max_wall_ms=5_000))
graph.add_rollback_step("agent_1", "clear_state")

out = compile_and_run(graph, "Find three facts about graph databases.", approver=lambda a, c: True)
print(out["runtime_plan"]["runtime_plan_id"])  # deterministic, content-addressed
print(out["trace"]["final_status"])            # "completed", with full evidence in out["trace"]
```

No API key required to try it — the `mock` provider runs the whole pipeline. Swap
in `openai` / `anthropic` / `ollama`, or your own provider, when you're ready.

## Why a runtime *and* a compiler

The mature Python frameworks (LangGraph, CrewAI, AutoGen) are excellent for
server apps, but they're Python-locked, and there's no neutral contract for what
an agent *runtime* must expose. Embodied, edge, native-app, and **governed
enterprise** agents need a runtime below the application-framework layer — and a
way to compile a portable, auditable plan they can deploy, replay, and reason
about. That's what ARI standardizes and Marrow implements.

!!! warning "Status: early / draft"
    Marrow is **pre-production** software. The ARI spec is a draft (0.1), and the
    compiler is feature-complete but not soak-tested at scale or
    security-audited. Real providers are wired and contract-tested but not
    exercised against live APIs in CI. Treat it as a green light to experiment, a
    yellow light to prototype, and not yet a red-light-free choice for
    mission-critical systems. See the [stability policy](stability.md) and
    [roadmap](roadmap.md).

## Next steps

<div class="grid cards" markdown>

-   __[Getting started](getting-started.md)__ — install, build, run the examples.
-   __[Compiler](concepts/compiler.md)__ — author → compile → govern → run → replay.
-   __[Architecture](architecture.md)__ — what lives in C++ vs Python, and why.
-   __[ARI spec](https://github.com/bencrooks-dev/marrow/blob/main/ARI-SPEC.md)__ — the language-neutral runtime contract.
-   __[Conformance](https://github.com/bencrooks-dev/marrow/blob/main/CONFORMANCE.md)__ — the falsifiable ARI conformance kit.
-   __[Roadmap](roadmap.md)__ — what's next.

</div>
