# Compiler / Runtime Audit

> Pre-implementation audit for the "AI-aware compiler/runtime" direction. This
> document records what is actually here, what is missing, what must not move,
> and the smallest credible MVP. Nothing in this file changes behavior.

**Repository state at audit:** branch `main` at `fe05bdd`, 120 tracked files.
**Verified baseline (this machine):** clean `.venv`, `pip install -e ".[test]"`
builds the `_marrow` extension; **94 unit tests pass**, **31 ARI-conformance
tests pass**, `ruff` clean. This is the regression bar every change below must
hold.

---

## 0. Framing: what "compiler" may and may not mean here

Today Marrow is an **AI-aware native runtime** — a thread-safe C++ core
(`src/core/engine.{hpp,cpp}`, 591 lines) with a Python SDK
(`python/marrow/`, ~1.1k lines) and an `_marrow` pybind11 module. It is the
reference implementation of **ARI**, the Agent Runtime Interface
(`ARI-SPEC.md`).

The target is a thin **compiler layer** on top of that runtime:

```
Python agent graph  ->  ARI manifest JSON  ->  RuntimePlan JSON  ->  execute through the C++ runtime  ->  ExecutionTrace JSON
```

One framing correction the rest of this audit depends on:

> **ARI 0.1 is a runtime *interface* spec, not a graph/manifest format.**
> `ARI-SPEC.md` standardizes message, provider, agent-state, tool, routing,
> lifecycle, persistence, and observability *behavior* (§2–§10). It does **not**
> define an `AgentGraph`, `RuntimePlan`, `ExecutionTrace`, `Policy`, `Budget`,
> or `DeploymentManifest` document schema.

So "ARI JSON" here is really a **new, additive ARI *manifest* layer** —
a declarative description of an agent system — that sits beside the existing
behavioral spec. The MVP must introduce it as clearly-marked **draft** schemas
and must not silently rewrite or contradict the normative interface spec
(`ARI-SPEC.md §11` forbids non-additive changes within a major version).

---

## 1. What already supports the compiler/runtime thesis

| Brief concept | Already in the repo | Where | Closeness |
|---|---|---|---|
| Mock provider, no API keys | `MockProvider` (C++), bound to Python; deterministic `"[mock:<name>] <last user>"` echo | `engine.hpp:94`, `bindings.cpp:114`, exported as `marrow.MockProvider` | **Direct** |
| Agent graph frontend | `Graph` fluent builder + immutable `FrozenGraph`; `run_graph` driver | `python/marrow/graph.py` | **Partial** — topology only |
| Tool contract | `ToolRegistry` (JSON-in/JSON-out), `@tool`/`ToolBox`, JSON-schema autogen, result envelope, size caps, redaction | `engine.hpp:222`, `python/marrow/tools.py`, `ARI-SPEC.md §5` | **Partial** — richer than needed for dispatch, thinner than the manifest |
| Provider contract | `Provider` base + pybind trampoline; `name()/generate()/generate_stream()` | `engine.hpp:79`, `bindings.cpp:105` | **Partial** |
| Policy | `RetryPolicy`, `RateLimiter` | `python/marrow/policy.py` | **Partial** — runtime policy, not a checkpoint manifest |
| Budget / usage | `UsageTracker`, token + cost accounting | `python/marrow/usage.py` | **Partial** |
| Evidence / trace | `TraceSink` (Null/Print/OTel), span protocol | `python/marrow/tracing.py`, `ARI-SPEC.md §9` | **Partial** — spans, not a serializable trace doc |
| State / memory | `AgentState`, `MemoryCache` (C++); `StateStore` (InMemory/SQLite) | `engine.hpp:109/133`, `python/marrow/state_store.py` | **Partial** |
| Runtime execution path | `Runtime` + `Agent.step()` drive the C++ engine via a `Provider` | `python/marrow/sdk.py` | **Direct** — this is what a RuntimePlan executes through |
| Native embeddability | `marrow_core` static lib builds and runs without Python | `examples/embed_cpp/`, `CMakeLists.txt` | **Direct** |
| Falsifiable conformance | ARI Conformance Kit, wired as a hard CI gate | `ari-conformance/`, `.github/workflows/ci.yml:65` | **Direct** |

Two facts make the MVP cheap:

1. **The frontend seam already exists and was anticipated.** `graph.py`'s own
   module docstring says the frozen plan is *"introspectable, serialisable, and
   (later) compilable to a C++ plan structure for high-throughput execution."*
   The compiler is the realization of an intent already written into the code.
2. **The execution substrate already exists.** A RuntimePlan does not need a new
   executor — it needs to be lowered onto `Runtime` + `Agent` + `MockProvider` +
   the existing `run_graph` driver, which already work and are tested.

---

## 2. What is missing

Nothing of the compiler layer exists yet. Concretely:

- **No compiler package.** There is no `marrow.compiler`, no `AgentGraph` /
  `AgentNode` / `ToolSpec` / `ProviderSpec` authoring types, no `compile_to_ari`.
- **No ARI manifest schemas.** There is no `ari/` directory and no JSON Schemas
  for `agent_graph`, `tool_spec`, `provider_spec`, `policy_spec`,
  `runtime_plan`, `execution_trace`, or `deployment_manifest`.
- **No RuntimePlan.** `FrozenGraph` is close in spirit but is **not
  JSON-serializable** — its edge conditions are Python `Callable`s
  (`graph.py:29`) and it carries no `version`, `graph_id`, `tool_bindings`,
  `provider_bindings`, or `policy_checkpoints`.
- **No ExecutionTrace document.** `TraceSink` emits live spans (text / OTel); it
  does **not** produce a structured `{trace_id, runtime_plan_id, events,
  tool_calls, provider_calls, policy_decisions, errors, final_status}` record.
- **No stored tool I/O contract.** Tool schemas are generated *at invoke time*
  (`tools.py:_schema_for`) and stored only as a single `schema_json` string;
  there is no separate `input_schema` / `output_schema`, and `side_effects`,
  `timeout_ms`, `requires_approval` are not captured anywhere.
- **No C++ RuntimePlan / ExecutionTrace types.** The C++ core has no notion of a
  plan or a trace, and **no JSON parser** is linked into it today.
- **Out of scope entirely (and should stay so for the MVP):**
  `MemorySpecIR`, `BudgetSpecIR`, `EvidenceSpecIR`, `FailureSemanticsIR`,
  `RollbackPlanIR`, `DeploymentManifestIR` as *executable* features.

---

## 3. What must NOT be changed

These are load-bearing. Changes here are out of scope and would break the
regression bar or the project's honesty.

- **The normative spec.** `ARI-SPEC.md` §2–§11. Manifests are additive draft
  artifacts; the interface spec's MUST/REQUIRED set does not move.
- **The public Python API.** Everything in `python/marrow/__init__.py` `__all__`
  (`Agent`, `Runtime`, `MockProvider`, `Graph`, `run_graph`, `tool`, `ToolBox`,
  `StateStore` family, `TraceSink` family, `UsageTracker`, `RetryPolicy`,
  `RateLimiter`, …). The compiler is **new, parallel surface**, not a rewrite.
- **The C++ engine API** (`engine.hpp`) and its pybind bindings. New C++ files
  may be added; existing classes are not modified.
- **All existing tests.** 10 files / 94 unit tests under `tests/`, plus the
  **ARI Conformance Kit** (`ari-conformance/`, 31 tests) which is a **hard CI
  gate** (`ci.yml:65`). "Do not remove or weaken existing tests."
- **The existing examples** — `ci.yml` runs `main.py`, `tools_example.py`,
  `graph_example.py`, `streaming_example.py`, `async_example.py` as a smoke
  step; they must keep running.
- **Build shape.** `scikit-build-core` + `pybind11`, `CMakeLists.txt` producing
  `marrow_core` (static) + `_marrow` (module). Additions extend this; they do
  not replace it.
- **Positioning.** README/ROADMAP/deck describe a *runtime* (a PoC, pre-alpha).
  The roadmap has embeddability and WASM/TS as future items but **no
  "compiler"** — so the new work is genuinely additive and must be labeled as an
  *early* compiler layer, not a finished one.

---

## 4. The smallest credible compiler MVP

A single end-to-end thread, all additive, mock-only, no API keys:

```
AgentGraph (new marrow.compiler types)
   -> compile_to_ari()      -> ARI manifest JSON   (validated vs ari/schemas/*)
   -> compile_to_runtime_plan() -> RuntimePlan JSON (validated; deterministic graph_id/plan id)
   -> run through Runtime + Agent + MockProvider via the existing driver
   -> ExecutionTrace JSON   (validated vs schema)
```

**New surface only (nothing existing is edited beyond additive exports/CMake):**

- `python/marrow/compiler/` — `AgentGraph`, `AgentNode`, `ToolSpec`,
  `ProviderSpec` authoring types; `compile_to_ari`; `ari_to_runtime_plan`;
  validation; deterministic IDs; a `run_runtime_plan` lowering onto `Runtime`.
- `ari/schemas/*.json` — minimal JSON Schemas for the seven manifest documents
  the seven manifest documents; `ari/spec/` note marking them **draft, non-normative**.
- `src/runtime_plan.{h,cpp}` + `src/execution_trace.{h,cpp}` — the *smallest*
  C++ types that can **represent and inspect** a RuntimePlan and hold an
  ExecutionTrace, bound to Python, proving the plan reaches the native layer.
  (Depth of "load" — full JSON parsing in C++ vs. constructed across the pybind
  boundary — is the main open design decision; see §5.)
- `examples/python_to_ari_compile/` — the end-to-end example with
  `expected_ari.json` / `expected_runtime_plan.json` / `expected_trace.json`.
- `tests/test_compiler_*.py` — graph→ARI, schema validation, invalid-graph /
  missing-provider / missing-tool failures, ARI→RuntimePlan, deterministic ID,
  trace emission, end-to-end, and a guard that existing runtime behavior is
  unchanged.
- `docs/compiler_architecture.md`, `docs/marrow_compiler_positioning.md`,
  `docs/language_roadmap.md`.

**Deliberately deferred** (documented in schemas/architecture as future, not
built): rollback execution, deployment-manifest execution, budget enforcement,
a policy *engine*, condition expressions beyond a small declarative set, and any
non-mock provider.

---

## 5. Risks

1. **C++ "load" depth (primary design decision).** The C++ core links no JSON
   library today. Options: (a) construct the C++ `RuntimePlan` across the pybind
   boundary from Python-parsed fields — smallest, dependency-free, but "load"
   means "construct"; (b) vendor a single-header JSON parser so C++ literally
   loads RuntimePlan JSON — more faithful, adds a dependency and code. The MVP
   should pick one explicitly and state the limitation honestly.
2. **Determinism.** `runtime_plan_id` must be a stable hash of canonicalized
   ARI; `ExecutionTrace` carries timestamps that are not reproducible. The
   `expected_*.json` fixtures and tests must normalize/exclude volatile fields or
   assert on structure, or they will be flaky.
3. **Non-serializable conditions.** `Graph` edges hold Python lambdas. The
   manifest must use a small **declarative** edge-condition form (e.g. "always"
   / a named predicate / a string match), not arbitrary callables. Do not try to
   serialize lambdas.
4. **ARI naming honesty.** Calling the manifests "ARI JSON" risks implying they
   are normative ARI 0.1. They are not. Mark them draft and cross-reference the
   interface spec; do not edit `ARI-SPEC.md`'s normative content.
5. **Toolchain.** `cmake`/`ninja` are not preinstalled on a clean machine;
   resolved by installing them into the build venv (verified). New C++ must build
   on the py3.9–3.12 × {linux,macos,windows} matrix, so keep it C++17 and
   dependency-light.
6. **Python version floor.** `requires-python = ">=3.9"`. New Python must avoid
   3.10+-only syntax in shipped modules (the existing code uses
   `from __future__ import annotations` for this reason).
7. **Scope creep.** The design lists 13 IR objects; only a subset is executable
   in the MVP. The rest are schema-only or documented-as-future. Resist building
   the unreferenced ones.
8. **CI smoke coverage.** A new example only runs in CI if added to the smoke
   list (or covered by a pytest test). Prefer a pytest test that imports and runs
   the example so coverage is automatic and cross-platform.

---

## 6. Correct build and test process (verified)

Authoritative source: `.github/workflows/ci.yml`, `pyproject.toml`,
`CMakeLists.txt`, `ruff.toml`. Confirmed locally on this machine.

**Toolchain:** C++17 compiler, CMake ≥ 3.18, `pybind11` ≥ 3.0.4,
`scikit-build-core` ≥ 0.12.2. The `_marrow` extension **must compile before
`import marrow` works** — there is no pure-Python fallback.

```bash
# one-time, clean environment
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install cmake ninja pybind11 scikit-build-core   # CI installs cmake+pybind11+scikit-build-core

# build + install (compiles the C++ extension)
pip install -e ".[test]"

# gates (all currently green)
ruff check python/ tests/ examples/        # lint
pytest -v --cov=marrow --cov-report=term-missing   # 94 unit tests
pytest ari-conformance/ -v                 # 31 conformance tests — HARD GATE
```

CI also runs the example smoke step and an informational ThreadSanitizer pass on
`tests/test_concurrency.py`. Matrix: `{ubuntu, macos, windows}` ×
`py{3.9,3.10,3.11,3.12}`. New code must keep all of the above green and must not
require any provider API key.

---

## 7. Verdict

The repository is a solid, honestly-scoped **native runtime** with the exact
seams the compiler thesis needs: a serializable-by-intent graph frontend, a
keyless mock provider, a tested execution path, and a falsifiable ARI
conformance gate. The compiler layer does not exist yet and should be built as a
**small, additive, mock-only** slice that proves the full chain end to end
without touching the existing runtime, tests, or normative spec. After that
slice lands, Marrow may honestly be called an **early** AI-aware
compiler/runtime — not before.
