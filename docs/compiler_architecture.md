# Marrow Compiler Architecture

> How Marrow lowers a declaratively-defined agent system into something the
> native runtime can execute, and how it records what happened. This document
> defines the **Marrow Compile** pipeline and its intermediate objects.
>
> Status: **draft**. The MVP implements a small, mock-only slice of this design
> (marked **[MVP]** below); the rest is specified so the slice has a target to
> grow into. See [`compiler_audit.md`](./compiler_audit.md) for what exists today
> and [`marrow_compiler_positioning.md`](./marrow_compiler_positioning.md) for
> what may and may not be claimed.

---

## 1. The thesis in one line

Developers describe an agent system declaratively (in Python today, other
frontends later); Marrow **compiles** that description through a stable
intermediate representation (**ARI manifests**) into a **RuntimePlan** that the
**C++ runtime** executes, emitting a portable **ExecutionTrace**.

```
frontend (Python)  ──►  ARI manifest (JSON)  ──►  RuntimePlan (JSON)  ──►  C++ runtime  ──►  ExecutionTrace (JSON)
   author the graph       portable, validated      lowered + bound          executes          evidence of the run
```

This is **not** a general-purpose compiler. It does not compile arbitrary
Python. It compiles **agent graphs, tool contracts, provider contracts, and
runtime policy** into an execution plan. The frontend is just the most
convenient place to *author* that description; the description, not the Python,
is the input to the compiler.

### Relationship to ARI / MCP / A2A

ARI (`ARI-SPEC.md`) standardizes the runtime *interface* — how a turn runs. The
**ARI manifests** defined here are a new, additive, **draft** layer: a
*declarative description* of an agent system that targets that interface. They
do not modify the normative interface spec. MCP (tools/context exchange) and A2A
(agent-to-agent messaging) sit above this layer and are out of scope.

---

## 2. The Marrow Compile pipeline

Thirteen logical stages. The **[MVP]** stages are implemented now; the others
are defined for completeness and validated structurally where cheap.

| # | Stage | What it does | MVP |
|---|---|---|---|
| 1 | **Source frontend** | Author an `AgentGraph` in Python (`marrow.compiler`) | **[MVP]** |
| 2 | **Graph extraction** | Normalize the authored graph into plain data | **[MVP]** |
| 3 | **ARI manifest generation** | Emit the `agent_graph` ARI manifest (JSON) | **[MVP]** |
| 4 | **ARI validation** | Validate the manifest against `ari/schemas/*` | **[MVP]** |
| 5 | **Tool contract validation** | Every referenced tool resolves to a `ToolSpec` | **[MVP]** |
| 6 | **Provider contract validation** | Every referenced provider resolves to a `ProviderSpec` | **[MVP]** |
| 7 | **Policy and budget planning** | Resolve policy checkpoints + budgets | partial (empty plan) |
| 8 | **State and memory layout planning** | Resolve per-agent state/memory layout | partial (pass-through) |
| 9 | **Optimization passes** | Canonicalize, dedupe, deterministic ordering | **[MVP]** (canonicalize) |
| 10 | **RuntimePlan generation** | Lower ARI → `runtime_plan` with bindings + deterministic id | **[MVP]** |
| 11 | **C++ runtime execution** | Load a native C++ `RuntimePlan`; the executor reads it and runs the turns through the C++ engine | **[MVP]** |
| 12 | **ExecutionTrace emission** | Record events/calls/status into a C++ `ExecutionTrace` → JSON | **[MVP]** |
| 13 | **Replay support** | Re-run from a RuntimePlan + recorded inputs | partial (deterministic ids) |

The MVP proves stages 1–6 and 9–12 end-to-end for a single mock-provider agent.
Stages 7, 8, 13 are present in shape (schemas/fields) but not exercised as
behavior; they are the documented growth path, not claims.

---

## 3. Intermediate objects

Each object below lists **purpose**, **required fields**, **optional fields**, a
**JSON example**, and **C++ mapping**. The seven that have a JSON Schema in
`ari/schemas/` are noted. Field names are canonical and are the single source of
truth shared by the schemas, the Python types, and the C++ structs.

Canonical conventions:
- `version` strings are `"ari/v0.draft"` for manifests and `"runtime_plan/v0.draft"` for plans.
- Deterministic ids: `graph_id = "g_" + sha256(canonical(agent_graph))[:16]`,
  `runtime_plan_id = "rp_" + sha256(canonical(runtime_plan \ {runtime_plan_id}))[:16]`,
  `trace_id = "tr_" + sha256(runtime_plan_id + "|" + initial_input)[:16]`, where
  `canonical(x) = json.dumps(x, sort_keys=True, separators=(",",":"))`.

### 3.1 AgentGraphIR — `ari/schemas/agent_graph.schema.json` **[MVP]**

- **Purpose:** the declarative description of an agent system; the compiler's input.
- **Required:** `version`, `name`, `agents`, `edges`, `tools`, `providers`, `entrypoint`.
- **Optional:** `metadata`.
- **JSON:**
  ```json
  {
    "version": "ari/v0.draft",
    "name": "echo_agent",
    "providers": [{"id": "mock", "type": "mock", "model": "mock-echo", "config_ref": null}],
    "tools": [{"name": "echo", "description": "Echo input text",
               "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
               "output_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
               "side_effects": false, "timeout_ms": 1000, "requires_approval": false}],
    "agents": [{"id": "agent_1", "name": "Echo Agent", "provider": "mock",
                "system_prompt": "You are a test echo agent.", "tools": ["echo"], "state": {}}],
    "edges": [],
    "entrypoint": "agent_1"
  }
  ```
- **C++ mapping:** not represented in C++ directly; it is the *source* manifest.
  It lowers to `RuntimePlan` (§3.6), which is the C++-facing object. A node with
  no satisfiable outgoing edge is terminal (mirrors `run_graph` today).

### 3.2 AgentNode (within AgentGraph) **[MVP]**

- **Purpose:** one named, stateful agent in the graph.
- **Required:** `id`, `name`, `provider`, `system_prompt`, `tools`, `state`.
- **Optional:** `metadata`.
- **JSON:** `{"id":"agent_1","name":"Echo Agent","provider":"mock","system_prompt":"...","tools":["echo"],"state":{}}`
- **C++ mapping:** → `RuntimeNode` (`src/runtime_plan.h`): `id, name, provider_id, system_prompt, tool_names`.

### 3.3 ToolSpecIR — `ari/schemas/tool_spec.schema.json` **[MVP]**

- **Purpose:** the manifest-level tool contract (richer than the runtime's
  `ToolRegistry` descriptor, which stores a single `schema_json`).
- **Required:** `name`, `description`, `input_schema`, `output_schema`, `side_effects`, `timeout_ms`, `requires_approval`.
- **Optional:** `tags`.
- **JSON:** see `tools[]` in §3.1.
- **C++ mapping:** → `ToolBinding` (`src/runtime_plan.h`): `name, timeout_ms, side_effects, requires_approval` (schemas kept as opaque strings, consistent with `ToolRegistry::schema_json`).

### 3.4 ProviderSpecIR — `ari/schemas/provider_spec.schema.json` **[MVP]**

- **Purpose:** how to obtain a model completion; binds a logical provider id to a concrete provider type/model.
- **Required:** `id`, `type`, `model`, `config_ref`.
- **Optional:** none.
- **JSON:** `{"id":"mock","type":"mock","model":"mock-echo","config_ref":null}`
- **C++ mapping:** → `ProviderBinding` (`src/runtime_plan.h`): `id, type, model, config_ref`. `type:"mock"` resolves to the existing C++ `MockProvider`.

### 3.5 PolicySpecIR — `ari/schemas/policy_spec.schema.json`

- **Purpose:** a governance checkpoint (approval/evidence gate) on an action.
- **Required:** `id`, `action`, `decision`, `approval_required`, `evidence_required`.
- **Optional:** `description`.
- **JSON:** `{"id":"p1","action":"tool:echo","decision":"allow","approval_required":false,"evidence_required":true}`
- **C++ mapping:** → `PolicyCheckpoint` (struct present; not enforced in MVP). MVP RuntimePlans carry `policy_checkpoints: []`.

### 3.6 RuntimePlanIR — `ari/schemas/runtime_plan.schema.json` **[MVP]**

- **Purpose:** the lowered, fully-bound, executable plan. The C++-facing object.
- **Required:** `version`, `graph_id`, `entrypoint`, `nodes`, `edges`, `tool_bindings`, `provider_bindings`, `policy_checkpoints`, `timeout_plan`, `retry_plan`, `evidence_plan`.
- **Optional (additive):** `runtime_plan_id` (deterministic; required by Phase 5 and referenced by traces), `name`.
- **JSON:**
  ```json
  {
    "version": "runtime_plan/v0.draft",
    "runtime_plan_id": "rp_0123456789abcdef",
    "graph_id": "g_fedcba9876543210",
    "name": "echo_agent",
    "entrypoint": "agent_1",
    "nodes": [{"id":"agent_1","name":"Echo Agent","provider":"mock","system_prompt":"...","tools":["echo"]}],
    "edges": [],
    "tool_bindings": {"echo": {"timeout_ms":1000,"side_effects":false,"requires_approval":false,
                               "input_schema":{"...":"..."},"output_schema":{"...":"..."}}},
    "provider_bindings": {"mock": {"type":"mock","model":"mock-echo","config_ref":null}},
    "policy_checkpoints": [],
    "timeout_plan": {"default_timeout_ms": 0},
    "retry_plan": {"default": {"attempts": 1}},
    "evidence_plan": {"record_tool_calls": true, "record_provider_calls": true, "record_policy_decisions": true}
  }
  ```
- **C++ mapping:** → `marrow.RuntimePlan` (`src/runtime_plan.{h,cpp}`), built across
  the pybind boundary by `marrow.compiler.load_runtime_plan(plan_dict)`. Holds
  `version, runtime_plan_id, graph_id, name, entrypoint, nodes[], edges[],
  tool_bindings, provider_bindings` and exposes inspection
  (`node_count(), entrypoint(), node(id), provider(id), ...`). **No JSON parser is
  linked into C++**; Python marshals the already-validated dict into the struct.
  "Load" here means "construct and inspect in C++," stated plainly. The executor
  (stage 11) builds this object via `load_runtime_plan` and reads its
  nodes/edges/bindings *out of it* to drive the run — the plan genuinely reaches
  the native layer, it is not just a Python dict.

### 3.7 ExecutionTraceIR — `ari/schemas/execution_trace.schema.json` **[MVP]**

- **Purpose:** portable evidence of one execution.
- **Required:** `trace_id`, `runtime_plan_id`, `started_at`, `completed_at`, `events`, `tool_calls`, `provider_calls`, `policy_decisions`, `errors`, `final_status`.
- **Optional:** `input`.
- **JSON:**
  ```json
  {
    "trace_id": "tr_abc123def456",
    "runtime_plan_id": "rp_0123456789abcdef",
    "started_at": 1733760000000, "completed_at": 1733760000005,
    "events": [{"type":"agent_started","agent":"agent_1"},
               {"type":"provider_called","agent":"agent_1","provider":"mock"},
               {"type":"agent_completed","agent":"agent_1"}],
    "tool_calls": [],
    "provider_calls": [{"agent":"agent_1","provider":"mock","model":"mock-echo",
                        "prompt_tokens":3,"completion_tokens":7}],
    "policy_decisions": [],
    "errors": [],
    "final_status": "completed"
  }
  ```
- **C++ mapping:** → `marrow.ExecutionTrace` (`src/execution_trace.{h,cpp}`). The
  executor records events/calls into this C++ object during the run; Python
  serializes it to JSON. Timestamps are real (non-deterministic); golden-file
  comparisons normalize them (see §5).

### 3.8 StateSpecIR / MemorySpecIR

- **Purpose:** per-agent conversation state and memory layout.
- **Required (StateSpec):** `agent_id`, `initial_messages`, `system_prompt`.
- **Required (MemorySpec):** `agent_id`, `capacity`.
- **Optional:** `metadata`.
- **JSON:** `{"agent_id":"agent_1","initial_messages":[],"system_prompt":"..."}`
- **C++ mapping:** already realized by `AgentState` and `MemoryCache` in the
  engine. MVP passes state through unchanged (`state: {}`); no new behavior.

### 3.9 BudgetSpecIR

- **Purpose:** spend/usage ceilings for a run.
- **Required:** `id`, `max_tokens`, `max_cost_usd`, `max_steps`.
- **Optional:** `currency`.
- **JSON:** `{"id":"b1","max_tokens":100000,"max_cost_usd":1.0,"max_steps":16}`
- **C++ mapping:** corresponds to the existing `UsageTracker` (Python) and the
  `max_steps` bound in `run_graph`. Not enforced as a compiled budget in MVP.

### 3.10 EvidenceSpecIR

- **Purpose:** what to record as evidence during execution.
- **Required:** `record_tool_calls`, `record_provider_calls`, `record_policy_decisions`.
- **Optional:** `redact_errors`.
- **JSON:** `{"record_tool_calls":true,"record_provider_calls":true,"record_policy_decisions":true}`
- **C++ mapping:** consumed by the executor as `runtime_plan.evidence_plan`; drives what the `ExecutionTrace` captures. **[MVP]** (drives trace contents).

### 3.11 FailureSemanticsIR

- **Purpose:** how the runtime classifies and surfaces failures (timeout, cancel, tool error, provider error).
- **Required:** `on_tool_error`, `on_provider_error`, `on_timeout`.
- **Optional:** `on_cancel`.
- **JSON:** `{"on_tool_error":"record_and_continue","on_provider_error":"abort","on_timeout":"abort"}`
- **C++ mapping:** the engine already distinguishes errors (cancellation,
  timeouts, tool result envelope `{"ok":false}`). MVP records errors into the
  trace and sets `final_status:"error"`; it does not yet branch on policy.

### 3.12 RollbackPlanIR

- **Purpose:** compensating actions if a run fails partway.
- **Required:** `id`, `steps`.
- **Optional:** `description`.
- **JSON:** `{"id":"rb1","steps":[{"on":"agent_1","action":"clear_state"}]}`
- **C++ mapping:** none yet. Documented as future; not in MVP.

### 3.13 DeploymentManifestIR — `ari/schemas/deployment_manifest.schema.json`

- **Purpose:** how/where a RuntimePlan is deployed.
- **Required:** `version`, `name`, `runtime_plan_id`, `target`.
- **Optional:** `replicas`, `env`.
- **JSON:** `{"version":"ari/v0.draft","name":"echo_agent","runtime_plan_id":"rp_0123456789abcdef","target":"local"}`
- **C++ mapping:** none yet. Schema only; documented as future.

---

## 4. Module layout

```
ari/
  schemas/   agent_graph, tool_spec, provider_spec, policy_spec,
             runtime_plan, execution_trace, deployment_manifest  (*.schema.json)
  examples/  echo_agent.ari.json, echo_agent.runtime_plan.json
  spec/      README.md  (draft note: manifests are non-normative vs ARI 0.1)

python/marrow/compiler/
  __init__.py     public API: AgentGraph, AgentNode, ToolSpec, ProviderSpec,
                  compile_to_ari, ari_to_runtime_plan, compile, run_runtime_plan,
                  load_runtime_plan, CompileError
  graph.py        authoring types (AgentGraph/AgentNode/ToolSpec/ProviderSpec)
  ari_emit.py     graph -> ARI manifest dict (+ canonicalization, graph_id)
  validate.py     JSON-schema validation against ari/schemas/* (stdlib only)
  runtime_plan.py ARI -> RuntimePlan dict (bindings, deterministic runtime_plan_id)
  execute.py      RuntimePlan -> run through Runtime/Agent/MockProvider -> ExecutionTrace
  errors.py       CompileError + structured, clear messages
  compile.py      end-to-end convenience: graph -> trace

src/
  runtime_plan.{h,cpp}     C++ RuntimePlan + RuntimeNode/Edge/ToolBinding/ProviderBinding
  execution_trace.{h,cpp}  C++ ExecutionTrace + events
  bindings/bindings.cpp    (additive) expose RuntimePlan + ExecutionTrace

examples/python_to_ari_compile/
  README.md, build_graph.py, compile_to_ari.py, run_runtime_plan.py,
  expected_ari.json, expected_runtime_plan.json, expected_trace.json
```

The compiler package depends on the existing runtime (`marrow.Runtime`,
`marrow.Agent`, `marrow.MockProvider`, `marrow.Graph`/`run_graph`) and adds no
third-party Python dependency — schema validation is a small stdlib validator
sufficient for the seven schemas, not a full JSON-Schema engine.

---

## 5. Determinism and replay

- **graph_id / runtime_plan_id** are content hashes over canonical JSON, so the
  same graph always compiles to the same plan id — the basis for replay (stage 13).
- **trace_id** is derived from `runtime_plan_id` + the initial input, so a given
  (plan, input) yields a stable trace identity.
- **Timestamps** (`started_at`, `completed_at`) are wall-clock and therefore not
  reproducible. Golden fixtures (`expected_trace.json`) store them as `null`, and
  the e2e test compares the trace with timestamps normalized out. Everything else
  in the trace is deterministic for a mock provider.

---

## 6. What the MVP deliberately does not do

- Compile arbitrary Python (only the declared graph/specs).
- Enforce budgets or run a policy engine (schemas + empty plans only).
- Execute rollback or deployment manifests (schemas/structs only).
- Use any non-mock provider or require any API key.
- Serialize arbitrary lambda edge conditions — edges use a small declarative
  condition form (`{"type":"always"}` or `{"type":"contains","value":"..."}`).
- Replace `ARI-SPEC.md` or claim the manifests are normative ARI 0.1.

After the MVP lands, Marrow can be described as an **early** AI-aware
compiler/runtime: the compile→plan→execute→trace chain is real and tested, while
most governance/optimization stages remain specified-but-not-yet-built.
