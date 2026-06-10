# Changelog

All notable changes to `marrow` are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/) once it reaches 1.0; until then, API breaks may happen at any 0.x bump.

## [Unreleased]

### Added — MCP gateway + flight recorder

- **MCP governance gateway** — `marrow-gateway` (also `python -m marrow.gateway`):
  a transparent stdio proxy that governs any MCP server with no changes to the
  agent or server. `tools/call` is gated by the compiler's `PolicyEngine`
  (`tool:<name>` actions), a tool allowlist, and call/wall-clock budgets;
  `tools/list` hides allowlist misses and statically denied tools; blocked calls
  never reach the server. Fail-closed handling for batch requests and invalid
  client JSON. Recorded arguments/results are redacted and size-capped.
- **Flight recorder** — `marrow-trace` (also `python -m marrow.traceview`):
  renders a compiler `ExecutionTrace` or gateway trace as one self-contained
  HTML report (status, budget bars, policy decisions, tool calls, timeline).
  A drop-zone variant is hosted on the docs site; rendering is fully local.
- **Gateway trace schema** — `ari/schemas/gateway_trace.schema.json` (draft,
  non-normative), validated in the gateway end-to-end test.
- **Demo** — [`examples/gateway/`](https://github.com/bencrooks-dev/marrow/tree/main/examples/gateway): a small MCP file server,
  a gateway config that denies the destructive tool, and a client that proves
  the deny (and that the server never saw the call).

### Added — compiler completion (real providers, tools, native JSON, TS)

- **Pluggable providers** — the executor builds providers by type: `mock`/`echo`
  (keyless default), `openai`/`anthropic`/`ollama` (built-in), or a caller-supplied
  factory (`run_runtime_plan(..., providers={type: factory})`) for bring-your-own
  models.
- **Tool-use loop** — agents request tools (a portable `{"tool_call": …}`
  convention); each call is policy-gated (`tool:<name>`), invoked through the C++
  `ToolRegistry`, recorded, and its result fed back. Supply implementations via
  `run_runtime_plan(..., tools={name: callable})`.
- **Full failure semantics** — `on_provider_error` / `on_tool_error` honor
  `abort` vs `record_and_continue` (tested with failing providers/tools).
- **Native C++ JSON** — a dependency-free parser (`src/json.hpp`):
  `RuntimePlan.from_json` parses plans, `ExecutionTrace.to_json` serializes traces.
  The plan is now loaded by parsing JSON in C++, not marshalled field-by-field.
- **Wall-clock budgets** — `BudgetSpec(max_wall_ms=…)` bounds total run time
  (pre-emptive, alongside `max_steps`).
- **TypeScript frontend** — [`ts/`](https://github.com/bencrooks-dev/marrow/tree/main/ts) emits ARI manifests identical to the
  Python frontend (parity test on `graph_id` + the manifest). CI builds and tests it.

### Added — compiler governance (experimental)

- **Policy enforcement** — `PolicySpec` checkpoints (allow / deny /
  require-approval, with an optional approver and evidence) are enforced by the
  executor's `PolicyEngine`; a denied action halts the run and rolls back. Each
  decision is recorded in the native `ExecutionTrace.policy_decisions`.
- **Budgets** — `BudgetSpec` (max steps / tokens / cost) is metered each turn by
  `BudgetMeter`; a breach halts with `final_status` `"exhausted"` / `"over_budget"`,
  and consumption is recorded in `ExecutionTrace.budget_usage`.
- **Rollback** — `RollbackPlan` compensating steps (e.g. `clear_state`) run on any
  abnormal termination.
- **Replay** — `replay()` / `traces_equivalent()` re-execute a plan deterministically.
- **Deployment manifests** — `make_deployment_manifest()` produces a validated
  `DeploymentManifest` from a RuntimePlan.
- New draft schemas `budget_spec`, `failure_semantics`, `rollback_plan`; the
  executor now drives execution from the loaded native `RuntimePlan`. New
  `examples/governance_example.py`. All additive; existing APIs and tests
  unchanged.

### Added — early compiler layer (experimental)

- **`marrow.compiler`** — a Python frontend (`AgentGraph` / `AgentNode` /
  `ToolSpec` / `ProviderSpec`) that compiles a declaratively-defined agent graph
  to an **ARI manifest**, lowers it to a **RuntimePlan** with deterministic ids,
  executes it through the existing native runtime, and emits an **ExecutionTrace**.
  Mock provider only; no API key. Additive — existing runtime APIs and tests are
  unchanged.
- **`ari/schemas/`** — draft, non-normative JSON Schemas for the manifest layer
  (`agent_graph`, `tool_spec`, `provider_spec`, `policy_spec`, `runtime_plan`,
  `execution_trace`, `deployment_manifest`) with a stdlib validator. These are
  **not** part of normative ARI 0.1 (see `ari/spec/README.md`).
- **`src/runtime_plan.{h,cpp}`, `src/execution_trace.{h,cpp}`** — native types
  that hold and inspect a RuntimePlan and record an ExecutionTrace, bound to
  Python. The core still links no JSON parser; plans are constructed across the
  binding boundary.
- **`examples/python_to_ari_compile/`** — runnable end-to-end example
  (Python graph → ARI → RuntimePlan → execute → trace) with golden fixtures.
- **`docs/compiler_audit.md`, `docs/compiler_architecture.md`,
  `docs/marrow_compiler_positioning.md`, `docs/language_roadmap.md`** — design,
  positioning (no overclaiming), and the frontends-emit-ARI language roadmap.

## [0.1.0rc1] — 2026-05-28

First release candidate published to PyPI (as `marrow-rt`). Bundles the
`agentcore` → `marrow` rename and the ARI standardization work on top of the
0.1.0 production-primitives baseline below. The ARI conformance kit is a hard CI
gate as of this candidate.

### Changed — project renamed

- **Renamed `agentcore` → `marrow`** to avoid a head-on collision with Amazon
  Bedrock AgentCore (AWS, GA 2025-10-13). Import package is `marrow`; the published
  distribution is **`marrow-rt`** (`pip install marrow-rt`). C++ namespace, the
  `_marrow` extension module, and the GitHub repo move with it. **ARI** (the
  standard) is unchanged. This is a breaking rename — update imports `agentcore` →
  `marrow`.

### Added — ARI standard

- **`ARI-SPEC.md`** — the Agent Runtime Interface, a language-neutral spec for the agent runtime layer, with three conformance profiles (Core, Embedded, Server). marrow is its reference implementation.
- **`ari-conformance/`** — executable conformance kit mapping each ARI requirement to a test; wired into CI (`conformance` job). Structural ARI-Embedded checks run without a build.
- **`docs/ari-strategy.md`, `GOVERNANCE.md`, `CONFORMANCE.md`, `docs/ari-rfc-process.md`** — adoption strategy, governance + path to neutral stewardship, conformance registry, and the spec RFC process.
- **`THREAT-MODEL.md`** — STRIDE threat model over the real attack surface with severities, trust boundaries, and an ARI-Embedded security profile.
- **`docs/pitch/`** — pitch deck (Marp) and one-pager. Market figures cited in `docs/market-research.md`.
- **`.github/workflows/security.yml`** — CodeQL (Python) + `pip-audit`.
- **`.github/workflows/docs-pdf.yml`** + **`scripts/render-pdfs.sh`** — render the doc set + deck to PDF and commit them to `docs/pdf/`.
- **`tests/test_security.py`** — adversarial/abuse tests tied to threat-model findings.

### Changed — security hardening

- **Cancellation + timeouts are now enforced** (previously plumbed but ignored): `Agent.step`/`stream` honor a pre-call `CancelToken`, and the OpenAI/Anthropic/Ollama providers pass `timeout_ms` through as a per-request wall-clock timeout and re-check cancellation between stream chunks. New helpers: `marrow.sdk.raise_if_cancelled`, `request_timeout_seconds`.
- **`Message.content` cap can no longer be bypassed** by direct assignment — the binding validates against `kMaxContentBytes` on set (matching `Message.make`).
- **Tool-error redaction hardened** — default redactor scrubs more secret shapes (AWS/GCP/GitHub/Slack/JWT/Bearer/cred-URLs) and filesystem paths; new `ToolBox(strict=True)` returns the exception type only. New `strict_error_redactor`.
- **`RetryPolicy` guidance** — default retry set unchanged; documented how to narrow `retry_on` / widen `skip` for non-transient provider errors (4xx/auth) you don't want retried.

### Fixed

- **`StateStore` persistence dropped `Message.metadata`** on load — round-trip is now lossless (ARI §2.2/§8).

## [0.1.0] — 2026-05-26

The first **production-primitives release**. Five "gates" from PoC to product closed in one pass.

### Added

#### Production primitives

- **`CancelToken`** (C++) — cooperative cancellation. Pass via `GenerationRequest.cancel_token`; providers and tools check `cancelled()` at yield points.
- **`GenerationRequest.timeout_ms`** — wall-clock timeout providers should honor.
- **Bounded inboxes** on `AgentRouter` — `set_inbox_limit(agent_id, max_size, policy)` with `OverflowPolicy.{Reject, DropOldest, DropNewest}`.
- **`Engine.shutdown()`** — graceful stop. Blocks new `create_agent` calls; in-flight work on existing agents continues.
- **`Message.kMaxContentBytes`** — 4 MiB hard cap on message content; `Message.make` throws if exceeded.
- **`RetryPolicy`** — exponential backoff with jitter; configurable retryable / skip exception sets.
- **`RateLimiter`** — token-bucket, thread-safe; `try_acquire` and blocking `acquire(timeout)`.

#### Observability + persistence

- **`StateStore` Protocol** with two impls:
  - `InMemoryStateStore` — drop-in for tests.
  - `SQLiteStateStore` — durable, WAL mode, per-thread connections.
- **`restore_into(runtime, agent_id, store)`** — rehydrate history + system prompt on restart.
- **`TraceSink` Protocol** with three sinks:
  - `NullTraceSink` (default, zero overhead).
  - `PrintTraceSink` (development).
  - `OpenTelemetryTraceSink` (production; wraps an OTel tracer).
- **`UsageTracker`** + **`UsageRecord`** — token counts per agent/model + estimated cost via configurable pricing tables.
- **`marrow.logging_config.configure_json`** — opt-in JSON-line structured logs on the `marrow` logger.

#### Distribution + stability

- **`STABILITY.md`** — semver policy, public-API tiers (stable / experimental / internal), deprecation flow.
- **`ROADMAP.md`** — committed v0.1–v1.0 milestones with stretch goals.
- **PyPI publishing workflow** — `wheels.yml` now publishes to TestPyPI on `rc/a/b` tags and to PyPI on GitHub releases via trusted publishing (no token needed in secrets).
- **`docs.yml`** workflow — builds the mkdocs site on every push to main and deploys to GitHub Pages.

#### Docs

- **mkdocs-material site** at `docs/` with concept pages (agents, providers, tools, graphs, async, persistence, observability), API reference auto-generated via mkdocstrings, plus mirror pages for STABILITY/SECURITY/CHANGELOG/CONTRIBUTING/ROADMAP via pymdownx snippets.
- **Real example app** at `examples/apps/research_agent/` — 3-agent pipeline with real provider toggling, tools, tracing, usage tracking, and SQLite persistence. Resumes on restart.

#### Benchmarks

- **`benchmarks/`** suite: micro (`AgentState.append`, cache, router, tools), e2e (3-agent pipeline), comparison against LangGraph (separately installable via `[bench]` extra).
- Numbers on first run (M-series Mac, Python 3.12): ~1.4M `append`/s, ~672K router send+drain/s, ~64K full 3-agent pipeline iters/s. See `benchmarks/README.md` for the full table and reproducibility notes.

### Changed

- **Bumped to 0.1.0.** This is a real release; install extras stabilized.
- **`Runtime(...)` accepts new keyword args:** `rate_limiter`, `retry_policy`, `trace_sink`, `usage`. All optional with sensible defaults.
- **Provider GIL release made consistent** — `Provider::generate` and `generate_stream` both release the GIL on the base binding (previously only `MockProvider` did).
- **Tool error redaction** now optional via `ToolBox(error_redactor=...)`; default strips paths + `sk-` / `Bearer ` prefixes.
- **Schema generator** handles `Optional`, `Union`, `list[X]`, `dict`, `Literal[...]`.
- **`Agent.step()` and `Agent.stream()` accept `temperature`, `timeout_ms`, `cancel_token`.**
- **`Graph.run` returns `GraphResult`** and raises `GraphExhausted` on `max_steps` instead of silently truncating.

### Fixed

(Cumulative; see prior versions for individual entries.)

### Fixed

- **Critical: GIL race in `ToolRegistry::invoke`.** The Pybind11 binding previously declared `py::call_guard<py::gil_scoped_release>` while the C++ implementation copies a `std::function` that captures a `py::function`. The copy increments a `PyObject` refcount, which is undefined behavior in CPython without the GIL held. Removed the `call_guard`; the GIL is now held through invocation (which is correct since tools run Python anyway).
- **Critical: TOCTOU race in `Engine::create_agent`.** The engine previously released its mutex before calling `router_.register_agent`, opening a window where another thread could observe the agent in the engine map but get "unknown recipient" when sending to it. The engine lock is now held across both operations. Safe because `AgentRouter` never calls into `Engine`, so there's no inverse lock order.

### Added

- `tests/test_concurrency.py` — four contention tests that would have detected both bugs above. Covers concurrent create+send, concurrent tool invocation, cache contention, and history append/read races.
- `SECURITY.md` — vulnerability disclosure policy, threat model, and known security-relevant limitations.
- `CHANGELOG.md` (this file).
- `CODEOWNERS`, issue templates, PR template, Dependabot config — standard OSS hygiene.

### Changed

- `README.md` — toned down unbenchmarked "fast" claims pending real measurements; added a "Known limitations" callout near the top.

---

## [0.0.2] — 2026-05-26

### Added

- Streaming through the C++ core: `Provider::generate_stream(req, on_chunk)`, `Agent.stream(on_chunk=...)`. Pybind11 trampoline supports Python subclasses overriding `generate_stream`.
- Real provider implementations under `marrow.providers`:
  - `OpenAIProvider` — Chat Completions API with streaming.
  - `AnthropicProvider` — Messages API with `cache_control: ephemeral` on system prompts (prompt caching).
  - `OllamaProvider` — local daemon at `http://localhost:11434`, no API key.
- Optional install extras: `marrow-rt[openai]`, `marrow-rt[anthropic]`, `marrow-rt[ollama]`, `marrow-rt[all]`.
- GitHub Actions workflows:
  - `ci.yml` — pytest matrix on Linux / macOS / Windows × Python 3.9–3.12, plus example smoke runs.
  - `wheels.yml` — `cibuildwheel` on `v*` tags or manual dispatch.

### Fixed

- Windows CI failed under cp1252 codec when example output contained Unicode (`→`). Added `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` to all CI jobs.

---

## [0.0.1] — 2026-05-26

### Added

- Initial proof-of-concept release.
- C++17 core (`src/core/engine.{hpp,cpp}`):
  - `Message`, `AgentState` (shared_mutex), `MemoryCache` (LRU), `AgentRouter` (registry + inboxes + handoff), `ToolRegistry` (type-erased dispatch), `Engine` (top-level handle), `Provider` interface with `MockProvider`.
- Pybind11 bindings exposing the full core to Python.
- Python SDK:
  - `Agent` / `Runtime` ergonomic wrappers.
  - `@tool` decorator + `ToolBox` with auto-generated JSON schemas.
  - `Graph` fluent builder for multi-agent workflows.
  - `AsyncRuntime` / `AsyncAgent` for concurrent steps over `ThreadPoolExecutor`.
- Four examples (two-agent pipeline, tools, graph, async).
- Eleven pytest tests covering smoke, router, tools.
- Apache 2.0 license; design notes documenting deliberate trade-offs.
