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

> Marrow is the native compiler/runtime layer agents run on, below MCP and A2A.

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

Be precise. The compiler is **feature-complete but early** — the full pipeline
works; it is not yet battle-tested.

- **Built and tested:** Python `AgentGraph` → ARI manifest → RuntimePlan
  (deterministic ids; parsed natively by the C++ JSON parser) → execution through
  the native runtime → ExecutionTrace (serialized natively). Concretely:
  **real, pluggable providers** (mock default; OpenAI/Anthropic/Ollama built in;
  bring-your-own via a factory); a **policy-gated tool-use loop** (agents invoke
  tools through the C++ ToolRegistry, gated by `tool:` policies); **full failure
  semantics** (provider/tool errors honor abort / record-and-continue);
  **governance** — policy checkpoints (allow / deny / require-approval, with
  evidence), budgets (steps / tokens / cost / wall-clock), rollback, deterministic
  replay, and deployment-manifest generation; and a **TypeScript frontend** that
  emits byte-identical ARI. Each with runnable examples and tests, plus a
  TS↔Python parity check.
- **Not yet:** production maturity — no soak testing at scale, no security audit,
  and real providers aren't exercised in CI (they need keys). Native tool-call
  extraction for hosted providers, a per-call timeout kill, and WASM/Rust/Go
  frontends remain follow-ons. These are maturity/breadth items, not missing core
  features.

## Avoid

- Claiming Marrow is *production-hardened* or *battle-tested* — it is early,
  pre-production software.
- Saying Marrow replaces MCP.
- Saying Marrow replaces A2A.
- Saying Marrow compiles arbitrary Python — it compiles agent graphs and their
  tool/provider/policy contracts.
- Generic AI marketing language.

## Honest status line

> Marrow is an AI-aware native runtime and a **feature-complete but early**
> AI-aware compiler/runtime: the Python→ARI→RuntimePlan→execute→trace→replay
> chain works and is tested end-to-end, with real pluggable providers, a
> policy-gated tool-use loop, governance (policy, budgets, evidence, rollback),
> native JSON, and a TypeScript frontend. What remains is production hardening
> (scale, security, hosted-provider CI), not core features.
