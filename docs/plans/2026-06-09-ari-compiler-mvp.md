# ARI Compiler MVP — Execution Plan

> Plan ID: `ari-compiler-mvp` · Branch: `feat/ari-compiler-mvp`
> Design: [`docs/compiler_architecture.md`](../compiler_architecture.md) ·
> Audit: [`docs/compiler_audit.md`](../compiler_audit.md)

**Goal:** Add the smallest credible, fully additive compiler slice that proves
`Python agent graph → ARI JSON → RuntimePlan JSON → C++ runtime execution →
ExecutionTrace JSON` for a single mock-provider agent, with no new API keys and
no changes to existing public APIs, tests, or the normative ARI spec.

**Approach:** New surface only — `ari/schemas/`, `python/marrow/compiler/`, two
new C++ files + additive bindings, `examples/python_to_ari_compile/`, new tests,
new docs. The RuntimePlan executes through the existing `Runtime`/`Agent`/
`MockProvider`/`run_graph` path; the C++ `RuntimePlan`/`ExecutionTrace` are
constructed across the pybind boundary (no JSON parser linked into C++).

**Tech:** Python 3.9-compatible (`from __future__ import annotations`), stdlib
only (no `jsonschema` dep — a small focused validator); C++17, no new C++ deps;
`scikit-build-core` + `pybind11` build unchanged in shape.

---

## Invariants (every wave)

- **Green bar:** after each wave run the **verification gate** and it must pass:
  ```bash
  .venv/bin/ruff check python/ tests/ examples/
  .venv/bin/python -m pytest -q            # >= 94, growing; never red
  .venv/bin/python -m pytest ari-conformance/ -q   # stays 31, hard gate
  ```
  After any C++/bindings change, rebuild first: `.venv/bin/python -m pip install -e . -q`.
- **TDD:** write the test(s) for the wave, watch them fail, implement, watch them pass.
- **Atomic commits:** one focused commit per wave, conventional-commit style
  (`feat:`, `test:`, `docs:`, `build:`), **no AI/co-author trailer, no plan/wave
  tags** — match the existing clean history.
- **Never edit** existing `tests/`, `ari-conformance/`, `src/core/engine.*`, the
  public `python/marrow/__init__.py` `__all__` semantics (additive exports only),
  or normative `ARI-SPEC.md`.

---

## File manifest (all new unless noted)

```
ari/schemas/{agent_graph,tool_spec,provider_spec,policy_spec,runtime_plan,execution_trace,deployment_manifest}.schema.json
ari/spec/README.md
ari/examples/{echo_agent.ari.json,echo_agent.runtime_plan.json}
python/marrow/compiler/{__init__,graph,ari_emit,validate,runtime_plan,execute,errors,compile}.py
src/{runtime_plan,execution_trace}.{h,cpp}
src/bindings/bindings.cpp            (MODIFY: additive bindings)
CMakeLists.txt                       (MODIFY: add new sources to marrow_core)
examples/python_to_ari_compile/{README.md,build_graph.py,compile_to_ari.py,run_runtime_plan.py,expected_ari.json,expected_runtime_plan.json,expected_trace.json}
tests/{test_compiler_frontend,test_ari_schema,test_ari_to_runtime_plan,test_runtime_plan_determinism,test_runtime_plan_cpp,test_execution_trace,test_compiler_e2e}.py
docs/{compiler_audit,compiler_architecture,marrow_compiler_positioning,language_roadmap}.md   (audit+arch already written)
python/marrow/__init__.py            (MODIFY: additive `from . import compiler`)
```

---

## Waves

### Wave 0 — Research & design ✅ (done)
`docs/compiler_audit.md`, `docs/compiler_architecture.md`, verified green baseline
(94 unit + 31 conformance, ruff clean).

### Wave 1 — Schemas + validation foundation
- **Files:** `ari/schemas/*.json` (7), `ari/spec/README.md`,
  `python/marrow/compiler/errors.py`, `python/marrow/compiler/validate.py`.
- **Validator:** stdlib-only; supports `type` (incl. type arrays + `null`),
  `properties`, `required`, `items`, `enum`, `const`, `additionalProperties:false`,
  `minItems`. Raises `CompileError` with a clear path + reason.
- **Test:** `tests/test_ari_schema.py` — every schema file is valid JSON; the
  validator accepts the §3.1 echo manifest and rejects (missing required field,
  wrong type, unknown property) with a clear message.
- **Gate + commit:** `feat: add ARI manifest JSON schemas + stdlib validator`.

### Wave 2 — Frontend + ARI emit
- **Files:** `compiler/graph.py` (`AgentGraph`, `AgentNode`, `ToolSpec`,
  `ProviderSpec`, declarative `Edge`), `compiler/ari_emit.py`
  (`compile_to_ari(graph) -> dict`, canonicalization, `graph_id`),
  `compiler/__init__.py` (initial exports).
- **Test:** `tests/test_compiler_frontend.py` — build the echo graph; `compile_to_ari`
  output validates against `agent_graph.schema.json`; `graph_id` deterministic &
  stable; missing provider / missing tool / unknown entrypoint raise `CompileError`.
- **Gate + commit:** `feat: add Python compiler frontend and ARI manifest emit`.

### Wave 3 — ARI → RuntimePlan
- **Files:** `compiler/runtime_plan.py` (`ari_to_runtime_plan(ari) -> dict`:
  nodes, edges, tool_bindings, provider_bindings, empty policy/timeout/retry/
  evidence plans, deterministic `runtime_plan_id`).
- **Tests:** `tests/test_ari_to_runtime_plan.py` (validates vs `runtime_plan.schema.json`;
  bindings resolve; validation errors for dangling provider/tool refs) +
  `tests/test_runtime_plan_determinism.py` (same graph → same `runtime_plan_id`;
  trivial change → different id).
- **Gate + commit:** `feat: compile ARI manifests to deterministic RuntimePlans`.

### Wave 4 — C++ RuntimePlan + ExecutionTrace (+ bindings)
- **Files:** `src/runtime_plan.{h,cpp}`, `src/execution_trace.{h,cpp}`,
  `src/bindings/bindings.cpp` (additive), `CMakeLists.txt` (add sources),
  `compiler/runtime_plan.py` (add `load_runtime_plan(plan_dict) -> marrow.RuntimePlan`).
- **Rebuild required.** New C++ must compile `-Wall -Wextra -Wpedantic` clean.
- **Test:** `tests/test_runtime_plan_cpp.py` — `load_runtime_plan` builds a
  `marrow.RuntimePlan`; `node_count()/entrypoint()/provider()/node()` inspect
  correctly; `marrow.ExecutionTrace` accepts events and reports `final_status`.
- **Gate + commit:** `feat: add native RuntimePlan and ExecutionTrace types`.

### Wave 5 — Execution + trace emission
- **Files:** `compiler/execute.py` (`run_runtime_plan(plan_dict, initial_input)
  -> dict`): build `Runtime`+`Agent`(`MockProvider`) from bindings, drive via the
  existing step/edge loop, record into a `marrow.ExecutionTrace`, return the
  trace dict (validates vs `execution_trace.schema.json`).
- **Test:** `tests/test_execution_trace.py` — run the echo plan; trace has all
  required fields, `final_status=="completed"`, `provider_calls` recorded, events
  ordered; structure deterministic with timestamps normalized.
- **Gate + commit:** `feat: execute RuntimePlans and emit ExecutionTraces`.

### Wave 6 — End-to-end convenience + example + e2e test
- **Files:** `compiler/compile.py` (`compile(graph)`,
  `compile_and_run(graph, initial_input)`), `compiler/__init__.py` (final exports),
  `python/marrow/__init__.py` (additive `from . import compiler`),
  `ari/examples/*.json`, `examples/python_to_ari_compile/*`.
- **Test:** `tests/test_compiler_e2e.py` — runs the example pipeline; asserts the
  emitted ARI / RuntimePlan / trace match `expected_*.json` (timestamps
  normalized); proves no API key needed; the seven brief proof-points hold.
- **Gate + commit:** `feat: add python_to_ari_compile end-to-end example`.

### Wave 7 — Positioning + roadmap docs
- **Files:** `docs/marrow_compiler_positioning.md`, `docs/language_roadmap.md`;
  additive note in `README.md` + `CHANGELOG.md` (careful, no overclaiming).
- **Gate + commit:** `docs: add compiler positioning and language roadmap`.

### Wave 8 — Verification + honest report
- Full gate + run every example (existing + new). Adversarial review pass.
- Produce the brief's strict Phase 13 final report (files added/modified, what
  the MVP proves, tests passed/failed, what's next, and the honest verdict on
  what Marrow may now be called).

---

## Acceptance (definition of done)

- Existing 94 unit + 31 conformance tests still pass; ruff clean.
- New tests cover: graph→ARI, schema validation, invalid-graph/missing-provider/
  missing-tool, ARI→RuntimePlan, deterministic id, C++ plan load+inspect,
  ExecutionTrace emission, end-to-end example. (Brief Phase 9 list.)
- `examples/python_to_ari_compile` runs with no API key and matches `expected_*`.
- Docs: audit, architecture, positioning, language roadmap — no overclaiming.
