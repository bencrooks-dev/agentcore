import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import {
  AgentGraph,
  AgentNode,
  BudgetSpec,
  CompileError,
  PolicySpec,
  ProviderSpec,
  ToolSpec,
  compileToAri,
  canonicalJson,
  graphId,
  type JsonObject,
} from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
// dist/index.test.js -> repo root is two levels up from dist/ (ts/ -> marrow/).
const GOLDEN_PATH = resolve(
  HERE,
  "..",
  "..",
  "ari",
  "examples",
  "echo_agent.ari.json",
);
const GOLDEN_GRAPH_ID = "g_2f9642c30328f2ae";

/** Build the canonical "echo_agent" graph that the golden manifest describes. */
function buildEchoGraph(): AgentGraph {
  return new AgentGraph("echo_agent")
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
}

test("parity: TS emits the exact golden ARI manifest for the echo graph", () => {
  const golden = JSON.parse(readFileSync(GOLDEN_PATH, "utf8")) as JsonObject;
  const ari = compileToAri(buildEchoGraph());
  assert.deepStrictEqual(ari, golden);
});

test("parity: graphId matches the Python frontend's graph_id for the echo graph", () => {
  const ari = compileToAri(buildEchoGraph());
  assert.equal(graphId(ari), GOLDEN_GRAPH_ID);
});

test("parity: graphId of the golden file on disk also matches", () => {
  const golden = JSON.parse(readFileSync(GOLDEN_PATH, "utf8")) as JsonObject;
  assert.equal(graphId(golden), GOLDEN_GRAPH_ID);
});

test("canonicalJson sorts keys recursively with no whitespace", () => {
  const out = canonicalJson({ b: 1, a: { d: 2, c: 3 } });
  assert.equal(out, '{"a":{"c":3,"d":2},"b":1}');
});

test("canonicalJson keeps array order and preserves UTF-8 literally", () => {
  const out = canonicalJson({ z: ["b", "a"], name: "café" });
  assert.equal(out, '{"name":"café","z":["b","a"]}');
});

test("compileToAri throws CompileError for an unknown provider reference", () => {
  const graph = new AgentGraph("g")
    .addAgent(new AgentNode("a1", "A1", "missing"))
    .setEntrypoint("a1");
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /unknown provider/);
    return true;
  });
});

test("compileToAri throws CompileError for an unknown tool reference", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p", { tools: ["nope"] }))
    .setEntrypoint("a1");
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /unknown tool/);
    return true;
  });
});

test("compileToAri throws CompileError when entrypoint is missing", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"));
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /no entrypoint/);
    return true;
  });
});

test("compileToAri throws CompileError when entrypoint is not an agent", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"))
    .setEntrypoint("ghost");
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /is not an agent/);
    return true;
  });
});

test("compileToAri throws CompileError for a duplicate agent id", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"))
    .addAgent(new AgentNode("a1", "A1 again", "p"))
    .setEntrypoint("a1");
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /duplicate agent id/);
    return true;
  });
});

test("compileToAri throws CompileError for an invalid policy decision", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"))
    .setEntrypoint("a1")
    // Force an invalid decision past the typed builder to exercise the check.
    .addPolicy(
      new PolicySpec("pol1", "tool:echo", {
        decision: "maybe" as never,
      }),
    );
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /invalid decision/);
    return true;
  });
});

test("compileToAri throws CompileError for an empty policy action", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"))
    .setEntrypoint("a1")
    .addPolicy(new PolicySpec("pol1", ""));
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /empty action/);
    return true;
  });
});

test("compileToAri throws CompileError for a bad budget (max_steps < 1)", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"))
    .setEntrypoint("a1")
    .setBudget(new BudgetSpec({ maxSteps: 0 }));
  assert.throws(() => compileToAri(graph), (err: unknown) => {
    assert.ok(err instanceof CompileError);
    assert.match((err as CompileError).message, /max_steps must be >= 1/);
    return true;
  });
});

test("an edge with whenContains emits the contains condition", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"))
    .addAgent(new AgentNode("a2", "A2", "p"))
    .setEntrypoint("a1")
    .addEdge("a1", "a2", { whenContains: "DRAFT" });
  const ari = compileToAri(graph);
  assert.deepStrictEqual(ari["edges"], [
    { from: "a1", to: "a2", condition: { type: "contains", value: "DRAFT" } },
  ]);
});

test("an edge without whenContains emits the always condition", () => {
  const graph = new AgentGraph("g")
    .addProvider(new ProviderSpec("p", "mock", "m"))
    .addAgent(new AgentNode("a1", "A1", "p"))
    .addAgent(new AgentNode("a2", "A2", "p"))
    .setEntrypoint("a1")
    .addEdge("a1", "a2");
  const ari = compileToAri(graph);
  assert.deepStrictEqual(ari["edges"], [
    { from: "a1", to: "a2", condition: { type: "always" } },
  ]);
});

test("optional keys are omitted when the graph is ungoverned", () => {
  const ari = compileToAri(buildEchoGraph());
  for (const key of [
    "metadata",
    "policies",
    "budget",
    "failure_semantics",
    "rollback",
  ]) {
    assert.ok(
      !(key in ari),
      `expected ungoverned manifest to omit optional key '${key}'`,
    );
  }
});

test("a governed graph emits policies and budget with the right shape", () => {
  const graph = buildEchoGraph()
    .addPolicy(
      new PolicySpec("pol_echo", "tool:echo", {
        decision: "require_approval",
        approvalRequired: true,
        evidenceRequired: true,
        description: "Approve before echoing.",
      }),
    )
    .setBudget(new BudgetSpec({ maxSteps: 8, maxTokens: 1000, currency: "USD" }));
  const ari = compileToAri(graph);

  assert.ok("policies" in ari, "governed manifest must emit policies");
  assert.ok("budget" in ari, "governed manifest must emit budget");
  assert.ok(!("metadata" in ari));
  assert.ok(!("failure_semantics" in ari));
  assert.ok(!("rollback" in ari));

  assert.deepStrictEqual(ari["policies"], [
    {
      id: "pol_echo",
      action: "tool:echo",
      decision: "require_approval",
      approval_required: true,
      evidence_required: true,
      description: "Approve before echoing.",
    },
  ]);
  assert.deepStrictEqual(ari["budget"], {
    id: "budget",
    max_tokens: 1000,
    max_cost_usd: null,
    max_steps: 8,
    currency: "USD",
  });
});
