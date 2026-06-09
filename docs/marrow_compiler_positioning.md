# Marrow Compiler Positioning

> How to describe the compiler direction accurately. Read alongside
> [`compiler_audit.md`](./compiler_audit.md) (what exists) and
> [`compiler_architecture.md`](./compiler_architecture.md) (the design).

## Current state

Marrow is an **AI-aware native runtime**: a thread-safe C++ core with a Python
SDK, the reference implementation of [ARI](../ARI-SPEC.md).

## Target state

Marrow is becoming an **AI-aware compiler/runtime** — it additionally compiles a
declaratively-defined agent system into a portable, executable plan and runs it
natively.

## One-liner

> Marrow is the native compiler/runtime layer for production agents, below MCP
> and A2A.

## Three-sentence description

1. Marrow lets developers define agent workflows in Python, lower them into ARI,
   compile them into native RuntimePlans, and execute them through a C++ runtime.
2. MCP standardizes how agents access tools and context, while A2A standardizes
   how agents communicate across systems.
3. ARI standardizes the missing runtime layer: how agent graphs are planned,
   governed, executed, traced, and replayed.

## Why this matters

- Python-first agent frameworks are useful but deployment-constrained.
- MCP does not define the internal agent runtime.
- A2A does not define local execution semantics.
- Enterprises need native execution, evidence, replay, budgets, policy
  checkpoints, and deployment manifests.
- Edge, robotics, trading systems, native apps, and governed enterprise agents
  need a runtime *below* the application-framework layer.

## What is actually built today

Be precise. The compiler is an **early MVP**, not the full vision:

- **Built and tested:** Python `AgentGraph` → ARI manifest → RuntimePlan (with
  deterministic ids) → execution through the native runtime → ExecutionTrace, on
  a mock provider, with a runnable
  [example](../examples/python_to_ari_compile/) and tests.
- **Specified but not yet built:** policy/budget enforcement, rollback and
  deployment execution, optimization passes, replay, and non-mock providers —
  these have schemas/fields but no runtime behavior.

## Avoid

- Claiming Marrow is already a *full* compiler — it is an early one.
- Saying Marrow replaces MCP.
- Saying Marrow replaces A2A.
- Saying Marrow compiles arbitrary Python — it compiles agent graphs and their
  tool/provider/policy contracts.
- Generic AI marketing language.

## Honest status line

> Marrow is an AI-aware native runtime, and an **early** AI-aware
> compiler/runtime: the Python→ARI→RuntimePlan→execute→trace chain works and is
> tested; most governance and optimization stages are specified but not yet
> built.
