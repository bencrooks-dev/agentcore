# ARI Manifests (draft, non-normative)

The JSON Schemas in [`ari/schemas/`](../schemas/) describe **ARI manifests** —
a declarative way to describe an agent system (its graph, tools, providers,
policies) and the artifacts the Marrow compiler produces from it (RuntimePlan,
ExecutionTrace, DeploymentManifest).

## These are NOT normative ARI 0.1

[`ARI-SPEC.md`](../../ARI-SPEC.md) is the normative specification. It defines a
runtime **interface** — the behavior a conformant runtime must implement
(message model, provider/generate, agent state, tool invocation, routing,
lifecycle, persistence, observability). It does **not** define a manifest or
document format.

The manifests here are a **separate, additive, experimental layer** that sits
*beside* the interface spec: a description of *what to run*, which the Marrow
compiler lowers into a RuntimePlan that executes *through* an ARI-conformant
runtime. They are versioned independently (`"ari/v0.draft"`), are not covered by
the ARI Conformance Kit, and make no stability promise yet.

Per `ARI-SPEC.md` §11, the normative interface only changes additively within a
major version; nothing in this directory changes it.

## Schemas

| File | Purpose | MVP |
|---|---|---|
| `agent_graph.schema.json` | The authored agent system (compiler input) | yes |
| `tool_spec.schema.json` | Tool contract (in/out schema, side effects, timeout, approval) | yes |
| `provider_spec.schema.json` | Logical provider id → type/model | yes |
| `policy_spec.schema.json` | Governance checkpoint | schema only |
| `runtime_plan.schema.json` | Lowered, bound, executable plan | yes |
| `execution_trace.schema.json` | Portable record of one run | yes |
| `deployment_manifest.schema.json` | Where/how a plan is deployed | schema only |

See [`docs/compiler_architecture.md`](../../docs/compiler_architecture.md) for
the field-by-field design and the compile pipeline.
