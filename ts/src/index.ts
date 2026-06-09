/**
 * TypeScript frontend for the Marrow compiler.
 *
 * You describe an agent system with the builder API in this module and
 * {@link compileToAri} lowers it to an ARI manifest. The manifest is
 * byte-for-byte identical to the one the Python frontend
 * (`marrow.compiler.compile_to_ari`) emits for the same graph, and so produces
 * the same content-addressed {@link graphId}. That parity is the point: ARI is
 * the interchange format, and a language frontend's only job is to emit it.
 *
 * Zero runtime dependencies — only Node built-ins (`node:crypto`).
 *
 * @example
 * ```ts
 * import { AgentGraph, ProviderSpec, ToolSpec, AgentNode, compileToAri, graphId } from "@marrow/ari";
 *
 * const graph = new AgentGraph("echo_agent")
 *   .addProvider(new ProviderSpec("mock", "mock", "mock-echo"))
 *   .addTool(new ToolSpec("echo", { description: "Echo input text" }))
 *   .addAgent(new AgentNode("agent_1", "Echo Agent", "mock", {
 *     systemPrompt: "You are a test echo agent.",
 *     tools: ["echo"],
 *   }))
 *   .setEntrypoint("agent_1");
 *
 * const ari = compileToAri(graph);
 * graphId(ari); // "g_2f9642c30328f2ae"
 * ```
 *
 * @packageDocumentation
 */
import { createHash } from "node:crypto";

/** A JSON-serialisable value. */
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

/** A JSON object. */
export type JsonObject = { [key: string]: JsonValue };

/**
 * Raised when a graph or ARI manifest is invalid. Mirrors the Python
 * `marrow.compiler.CompileError`.
 */
export class CompileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CompileError";
    // Restore prototype chain for instanceof across transpilation targets.
    Object.setPrototypeOf(this, CompileError.prototype);
  }
}

const POLICY_DECISIONS = ["allow", "deny", "require_approval"] as const;
/** The valid {@link PolicySpec.decision} values. */
export type PolicyDecision = (typeof POLICY_DECISIONS)[number];

/** A serialisable edge condition: `{type:"always"}` or `{type:"contains",value}`. */
export type EdgeCondition =
  | { type: "always" }
  | { type: "contains"; value: string };

function always(): EdgeCondition {
  return { type: "always" };
}

function contains(value: string): EdgeCondition {
  return { type: "contains", value };
}

/** A logical provider id bound to a concrete provider type/model. */
export class ProviderSpec {
  id: string;
  type: string;
  model: string;
  configRef: string | null;

  constructor(
    id: string,
    type: string,
    model: string,
    configRef: string | null = null,
  ) {
    this.id = id;
    this.type = type;
    this.model = model;
    this.configRef = configRef;
  }

  toDict(): JsonObject {
    return {
      id: this.id,
      type: this.type,
      model: this.model,
      config_ref: this.configRef,
    };
  }
}

/** Options accepted by the {@link ToolSpec} constructor. */
export interface ToolSpecOptions {
  description?: string;
  inputSchema?: JsonObject;
  outputSchema?: JsonObject;
  sideEffects?: boolean;
  timeoutMs?: number;
  requiresApproval?: boolean;
  tags?: string[] | null;
}

/** A tool contract: name, I/O schemas, and runtime properties. */
export class ToolSpec {
  name: string;
  description: string;
  inputSchema: JsonObject;
  outputSchema: JsonObject;
  sideEffects: boolean;
  timeoutMs: number;
  requiresApproval: boolean;
  tags: string[] | null;

  constructor(name: string, options: ToolSpecOptions = {}) {
    this.name = name;
    this.description = options.description ?? "";
    this.inputSchema = options.inputSchema ?? { type: "object" };
    this.outputSchema = options.outputSchema ?? { type: "object" };
    this.sideEffects = options.sideEffects ?? false;
    this.timeoutMs = options.timeoutMs ?? 1000;
    this.requiresApproval = options.requiresApproval ?? false;
    this.tags = options.tags ?? null;
  }

  toDict(): JsonObject {
    const out: JsonObject = {
      name: this.name,
      description: this.description,
      input_schema: this.inputSchema,
      output_schema: this.outputSchema,
      side_effects: this.sideEffects,
      timeout_ms: this.timeoutMs,
      requires_approval: this.requiresApproval,
    };
    if (this.tags !== null) {
      out["tags"] = [...this.tags];
    }
    return out;
  }
}

/** Options accepted by the {@link AgentNode} constructor. */
export interface AgentNodeOptions {
  systemPrompt?: string;
  tools?: string[];
  state?: JsonObject;
}

/** One named, stateful agent in the graph. */
export class AgentNode {
  id: string;
  name: string;
  provider: string;
  systemPrompt: string;
  tools: string[];
  state: JsonObject;

  constructor(
    id: string,
    name: string,
    provider: string,
    options: AgentNodeOptions = {},
  ) {
    this.id = id;
    this.name = name;
    this.provider = provider;
    this.systemPrompt = options.systemPrompt ?? "";
    this.tools = options.tools ?? [];
    this.state = options.state ?? {};
  }

  toDict(): JsonObject {
    return {
      id: this.id,
      name: this.name,
      provider: this.provider,
      system_prompt: this.systemPrompt,
      tools: [...this.tools],
      state: this.state,
    };
  }
}

/** A directed edge with a serialisable, declarative condition. */
class Edge {
  source: string;
  target: string;
  condition: EdgeCondition;

  constructor(source: string, target: string, condition: EdgeCondition) {
    this.source = source;
    this.target = target;
    this.condition = condition;
  }

  toDict(): JsonObject {
    return {
      from: this.source,
      to: this.target,
      condition: this.condition as unknown as JsonObject,
    };
  }
}

/** Options accepted by the {@link PolicySpec} constructor. */
export interface PolicySpecOptions {
  decision?: PolicyDecision;
  approvalRequired?: boolean;
  evidenceRequired?: boolean;
  description?: string;
}

/** A governance checkpoint on an action. */
export class PolicySpec {
  id: string;
  action: string;
  decision: string;
  approvalRequired: boolean;
  evidenceRequired: boolean;
  description: string;

  constructor(id: string, action: string, options: PolicySpecOptions = {}) {
    this.id = id;
    this.action = action;
    this.decision = options.decision ?? "allow";
    this.approvalRequired = options.approvalRequired ?? false;
    this.evidenceRequired = options.evidenceRequired ?? false;
    this.description = options.description ?? "";
  }

  toDict(): JsonObject {
    const out: JsonObject = {
      id: this.id,
      action: this.action,
      decision: this.decision,
      approval_required: this.approvalRequired,
      evidence_required: this.evidenceRequired,
    };
    if (this.description) {
      out["description"] = this.description;
    }
    return out;
  }
}

/** Options accepted by the {@link BudgetSpec} constructor. */
export interface BudgetSpecOptions {
  maxSteps?: number;
  maxTokens?: number | null;
  maxCostUsd?: number | null;
  id?: string;
  currency?: string | null;
}

/**
 * An execution budget. `null` limits mean unlimited; `maxSteps` always bounds
 * the loop.
 */
export class BudgetSpec {
  maxSteps: number;
  maxTokens: number | null;
  maxCostUsd: number | null;
  id: string;
  currency: string | null;

  constructor(options: BudgetSpecOptions = {}) {
    this.maxSteps = options.maxSteps ?? 16;
    this.maxTokens = options.maxTokens ?? null;
    this.maxCostUsd = options.maxCostUsd ?? null;
    this.id = options.id ?? "budget";
    this.currency = options.currency ?? null;
  }

  toDict(): JsonObject {
    const out: JsonObject = {
      id: this.id,
      max_tokens: this.maxTokens,
      max_cost_usd: this.maxCostUsd,
      max_steps: this.maxSteps,
    };
    if (this.currency !== null) {
      out["currency"] = this.currency;
    }
    return out;
  }
}

/** Options accepted by the {@link FailureSemantics} constructor. */
export interface FailureSemanticsOptions {
  onToolError?: "abort" | "record_and_continue";
  onProviderError?: "abort" | "record_and_continue";
  onTimeout?: "abort" | "record_and_continue";
  onCancel?: "abort" | "record_and_continue" | null;
}

/** How the runtime should react to failures. */
export class FailureSemantics {
  onToolError: string;
  onProviderError: string;
  onTimeout: string;
  onCancel: string | null;

  constructor(options: FailureSemanticsOptions = {}) {
    this.onToolError = options.onToolError ?? "record_and_continue";
    this.onProviderError = options.onProviderError ?? "abort";
    this.onTimeout = options.onTimeout ?? "abort";
    this.onCancel = options.onCancel ?? null;
  }

  toDict(): JsonObject {
    const out: JsonObject = {
      on_tool_error: this.onToolError,
      on_provider_error: this.onProviderError,
      on_timeout: this.onTimeout,
    };
    if (this.onCancel !== null) {
      out["on_cancel"] = this.onCancel;
    }
    return out;
  }
}

/** A compensating action to run on failure. */
class RollbackStep {
  on: string;
  action: string;

  constructor(on: string, action = "clear_state") {
    this.on = on;
    this.action = action;
  }

  toDict(): JsonObject {
    return { on: this.on, action: this.action };
  }
}

/** Options accepted by {@link AgentGraph.addEdge}. */
export interface AddEdgeOptions {
  whenContains?: string;
}

/**
 * A declaratively-defined agent system: the compiler's input.
 *
 * The mutating builder methods return `this` so calls can be chained.
 */
export class AgentGraph {
  name: string;
  version: string;
  providers: ProviderSpec[] = [];
  tools: ToolSpec[] = [];
  agents: AgentNode[] = [];
  edges: Edge[] = [];
  entrypoint: string | null = null;
  metadata: JsonObject | null = null;
  policies: PolicySpec[] = [];
  budget: BudgetSpec | null = null;
  failureSemantics: FailureSemantics | null = null;
  rollback: RollbackStep[] = [];

  constructor(name: string, version = "ari/v0.draft") {
    this.name = name;
    this.version = version;
  }

  addProvider(provider: ProviderSpec): this {
    this.providers.push(provider);
    return this;
  }

  addTool(tool: ToolSpec): this {
    this.tools.push(tool);
    return this;
  }

  addAgent(agent: AgentNode): this {
    this.agents.push(agent);
    return this;
  }

  addEdge(source: string, target: string, options: AddEdgeOptions = {}): this {
    const condition =
      options.whenContains !== undefined
        ? contains(options.whenContains)
        : always();
    this.edges.push(new Edge(source, target, condition));
    return this;
  }

  setEntrypoint(agentId: string): this {
    this.entrypoint = agentId;
    return this;
  }

  addPolicy(policy: PolicySpec): this {
    this.policies.push(policy);
    return this;
  }

  setBudget(budget: BudgetSpec): this {
    this.budget = budget;
    return this;
  }

  setFailureSemantics(failureSemantics: FailureSemantics): this {
    this.failureSemantics = failureSemantics;
    return this;
  }

  setMetadata(metadata: JsonObject): this {
    this.metadata = metadata;
    return this;
  }

  addRollbackStep(on: string, action = "clear_state"): this {
    this.rollback.push(new RollbackStep(on, action));
    return this;
  }
}

function checkUnique(label: string, ids: string[]): void {
  const seen = new Set<string>();
  for (const i of ids) {
    if (seen.has(i)) {
      throw new CompileError(`duplicate ${label}: ${JSON.stringify(i)}`);
    }
    seen.add(i);
  }
}

function validateGraph(graph: AgentGraph): void {
  if (!graph.name) {
    throw new CompileError("graph has no name");
  }
  if (graph.agents.length === 0) {
    throw new CompileError("graph has no agents");
  }

  const providerIds = graph.providers.map((p) => p.id);
  const toolNames = graph.tools.map((t) => t.name);
  const agentIds = graph.agents.map((a) => a.id);
  checkUnique("provider id", providerIds);
  checkUnique("tool name", toolNames);
  checkUnique("agent id", agentIds);

  const providerSet = new Set(providerIds);
  const toolSet = new Set(toolNames);
  const agentSet = new Set(agentIds);

  for (const agent of graph.agents) {
    if (!providerSet.has(agent.provider)) {
      throw new CompileError(
        `agent ${JSON.stringify(agent.id)} references unknown provider ${JSON.stringify(agent.provider)}`,
      );
    }
    for (const toolName of agent.tools) {
      if (!toolSet.has(toolName)) {
        throw new CompileError(
          `agent ${JSON.stringify(agent.id)} references unknown tool ${JSON.stringify(toolName)}`,
        );
      }
    }
  }

  for (const edge of graph.edges) {
    if (!agentSet.has(edge.source)) {
      throw new CompileError(
        `edge references unknown source agent ${JSON.stringify(edge.source)}`,
      );
    }
    if (!agentSet.has(edge.target)) {
      throw new CompileError(
        `edge references unknown target agent ${JSON.stringify(edge.target)}`,
      );
    }
  }

  if (!graph.entrypoint) {
    throw new CompileError(
      "graph has no entrypoint; call setEntrypoint(agentId)",
    );
  }
  if (!agentSet.has(graph.entrypoint)) {
    throw new CompileError(
      `entrypoint ${JSON.stringify(graph.entrypoint)} is not an agent in the graph`,
    );
  }

  checkUnique(
    "policy id",
    graph.policies.map((p) => p.id),
  );
  for (const policy of graph.policies) {
    if (!policy.action) {
      throw new CompileError(
        `policy ${JSON.stringify(policy.id)} has an empty action`,
      );
    }
    if (!(POLICY_DECISIONS as readonly string[]).includes(policy.decision)) {
      throw new CompileError(
        `policy ${JSON.stringify(policy.id)} has invalid decision ${JSON.stringify(policy.decision)} ` +
          `(expected one of ${JSON.stringify([...POLICY_DECISIONS].sort())})`,
      );
    }
  }

  if (graph.budget !== null) {
    if (graph.budget.maxSteps < 1) {
      throw new CompileError("budget max_steps must be >= 1");
    }
    if (graph.budget.maxTokens !== null && graph.budget.maxTokens < 0) {
      throw new CompileError("budget max_tokens must be >= 0");
    }
    if (graph.budget.maxCostUsd !== null && graph.budget.maxCostUsd < 0) {
      throw new CompileError("budget max_cost_usd must be >= 0");
    }
  }

  for (const step of graph.rollback) {
    if (!agentSet.has(step.on)) {
      throw new CompileError(
        `rollback step targets unknown agent ${JSON.stringify(step.on)}`,
      );
    }
  }
}

/**
 * Validate `graph` and emit its ARI agent-graph manifest (a plain object).
 *
 * Throws {@link CompileError} with a clear message on any structural problem:
 * unknown provider/tool/agent references, a missing or invalid entrypoint,
 * duplicate ids, an empty action or invalid policy decision, or a bad budget.
 *
 * Optional keys (`metadata`, `policies`, `budget`, `failure_semantics`,
 * `rollback`) are omitted entirely when absent, exactly as the Python frontend
 * does, so the emitted manifest is deep-equal and canonicalises identically.
 */
export function compileToAri(graph: AgentGraph): JsonObject {
  validateGraph(graph);

  const manifest: JsonObject = {
    version: graph.version,
    name: graph.name,
    providers: graph.providers.map((p) => p.toDict()),
    tools: graph.tools.map((t) => t.toDict()),
    agents: graph.agents.map((a) => a.toDict()),
    edges: graph.edges.map((e) => e.toDict()),
    entrypoint: graph.entrypoint as string,
  };
  if (graph.metadata !== null) {
    manifest["metadata"] = graph.metadata;
  }
  if (graph.policies.length > 0) {
    manifest["policies"] = graph.policies.map((p) => p.toDict());
  }
  if (graph.budget !== null) {
    manifest["budget"] = graph.budget.toDict();
  }
  if (graph.failureSemantics !== null) {
    manifest["failure_semantics"] = graph.failureSemantics.toDict();
  }
  if (graph.rollback.length > 0) {
    manifest["rollback"] = {
      id: "rollback",
      steps: graph.rollback.map((s) => s.toDict()),
    };
  }

  return manifest;
}

/**
 * Stable serialisation used for content-addressed ids: object keys sorted
 * recursively, arrays kept in order, no insignificant whitespace, UTF-8
 * preserved (non-ASCII characters are emitted literally, not `\u`-escaped).
 *
 * Equivalent to Python's
 * `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
 */
export function canonicalJson(obj: JsonValue): string {
  if (obj === null || typeof obj !== "object") {
    // JSON.stringify already emits non-ASCII literally (ensure_ascii=False)
    // and uses the same number/string formatting as Python's json for the
    // primitive values an ARI manifest contains.
    return JSON.stringify(obj);
  }
  if (Array.isArray(obj)) {
    return "[" + obj.map((item) => canonicalJson(item)).join(",") + "]";
  }
  const keys = Object.keys(obj).sort();
  const parts = keys.map(
    (key) => JSON.stringify(key) + ":" + canonicalJson(obj[key] as JsonValue),
  );
  return "{" + parts.join(",") + "}";
}

/**
 * Deterministic content-addressed id of an ARI agent-graph manifest:
 * `"g_" + sha256_hex(canonicalJson(ari)).slice(0, 16)`. Identical to the
 * Python frontend's `graph_id`.
 */
export function graphId(ari: JsonValue): string {
  const digest = createHash("sha256")
    .update(canonicalJson(ari), "utf8")
    .digest("hex");
  return "g_" + digest.slice(0, 16);
}
