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

Be precise. The compiler is **early** — functional, but not the full vision:

- **Built and tested:** Python `AgentGraph` → ARI manifest → RuntimePlan (with
  deterministic ids) → execution through the native runtime → ExecutionTrace, on
  a mock provider. Governance is enforced, not just described: **policy
  checkpoints** (allow / deny / require-approval, with evidence), **budgets**
  (steps / tokens / cost), **rollback** on abnormal termination, **deterministic
  replay**, and **deployment-manifest** generation — each with a runnable
  example ([compile](../examples/python_to_ari_compile/),
  [governance](../examples/governance_example.py)) and tests.
- **Not yet built:** non-mock providers (real LLM execution needs API keys);
  non-Python frontends (TypeScript, WASM, …); an automatic tool-use loop (so
  tool-call policies fire on real tool calls); `FailureSemantics` branching
  beyond abort; and a native JSON parser (plans are constructed across the pybind
  boundary). These are deliberate future work, not claims.

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
> tested, with policy enforcement, budgets, evidence, rollback, replay, and
> deployment manifests. What remains for a *full* compiler/runtime is non-mock
> execution and non-Python frontends.
