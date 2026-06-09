# @marrow/ari

A TypeScript frontend for the [Marrow](../README.md) compiler. You author an
agent system with a small builder API and it emits an **ARI manifest** — the
interchange format the Marrow compiler consumes.

This package exists to demonstrate Marrow's central thesis: _language frontends
emit ARI_. The manifest this TypeScript frontend produces for a given graph is
**byte-for-byte identical** to the one the Python frontend
(`marrow.compiler.compile_to_ari`) produces for the equivalent graph, and so
carries the same content-addressed `graph_id`. Different authoring languages,
one manifest.

- Zero runtime dependencies — only Node built-ins (`node:crypto`).
- Strict TypeScript, ES2022, `nodenext` modules.
- Tests run on Node's built-in test runner (`node --test`) — no vitest/jest.

## Install

```bash
npm install
```

## Build

```bash
npm run build   # tsc -> dist/
```

## Test

```bash
npm test        # node --test (runs the compiled dist/*.test.js)
```

The suite includes a **parity test** that builds the `echo_agent` graph, compiles
it, and asserts the result is deep-equal to the golden manifest at
`ari/examples/echo_agent.ari.json` and that its `graphId` equals
`g_2f9642c30328f2ae` — the same id the Python frontend computes.

## Usage

```ts
import {
  AgentGraph,
  AgentNode,
  ProviderSpec,
  ToolSpec,
  compileToAri,
  graphId,
} from "@marrow/ari";

const graph = new AgentGraph("echo_agent")
  .addProvider(new ProviderSpec("mock", "mock", "mock-echo"))
  .addTool(
    new ToolSpec("echo", {
      description: "Echo input text",
      inputSchema: {
        type: "object",
        properties: { text: { type: "string" } },
        required: ["text"],
      },
      outputSchema: {
        type: "object",
        properties: { text: { type: "string" } },
        required: ["text"],
      },
    }),
  )
  .addAgent(
    new AgentNode("agent_1", "Echo Agent", "mock", {
      systemPrompt: "You are a test echo agent.",
      tools: ["echo"],
    }),
  )
  .setEntrypoint("agent_1");

const ari = compileToAri(graph);
console.log(graphId(ari)); // "g_2f9642c30328f2ae"
```

### Governance, budgets, and edges

The builder mirrors the Python authoring API. Methods are chainable and return
the graph.

```ts
import { BudgetSpec, PolicySpec } from "@marrow/ari";

graph
  .addAgent(new AgentNode("reviewer", "Reviewer", "mock"))
  // Edge that only fires when the source agent's output contains "DRAFT".
  .addEdge("agent_1", "reviewer", { whenContains: "DRAFT" })
  .addPolicy(
    new PolicySpec("approve_echo", "tool:echo", {
      decision: "require_approval",
      approvalRequired: true,
      evidenceRequired: true,
    }),
  )
  .setBudget(new BudgetSpec({ maxSteps: 8, maxTokens: 1000, currency: "USD" }));
```

`compileToAri` validates the graph before emitting — unknown provider/tool
references, a missing or invalid entrypoint, duplicate ids, an empty policy
action or invalid decision, and bad budgets all raise a `CompileError` with a
clear message. Optional manifest keys (`metadata`, `policies`, `budget`,
`failure_semantics`, `rollback`) are omitted entirely when unset, exactly as the
Python frontend does, so the canonical JSON and `graph_id` stay identical across
frontends.

## API

| Export | Description |
| --- | --- |
| `AgentGraph` | The authoring root; chainable builder methods. |
| `ProviderSpec`, `ToolSpec`, `AgentNode`, `PolicySpec`, `BudgetSpec`, `FailureSemantics` | Authoring types mirroring the Python dataclasses (same fields/defaults). |
| `compileToAri(graph)` | Validates and emits the ARI manifest object. |
| `graphId(ari)` | `"g_" + sha256(canonicalJson(ari)).slice(0,16)`. |
| `canonicalJson(obj)` | Stable serialisation: keys sorted recursively, no whitespace, UTF-8 preserved. |
| `CompileError` | Thrown on any validation failure. |

## License

Apache-2.0.
