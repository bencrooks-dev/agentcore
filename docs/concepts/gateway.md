# MCP gateway

The gateway applies Marrow's governance to **any MCP server, with zero changes
to your agent or the server**. It is a transparent stdio proxy: your MCP client
launches `marrow-gateway` instead of the real server, the gateway launches the
real server, and traffic flows through untouched — except that tool use is
governed and recorded.

```
MCP client (Claude Desktop, Claude Code, any agent)
        │  stdio (JSON-RPC)
        ▼
  marrow-gateway          policy · least privilege · budgets · flight recorder
        │  stdio (JSON-RPC)
        ▼
  your MCP server         (unchanged)
```

Two interceptions, nothing else:

- **`tools/call`** — gated by the same
  [`PolicyEngine`](../api/compiler.md) the compiler uses (`tool:<name>` actions;
  `allow` / `deny` / `require_approval`), an optional tool **allowlist**, and a
  **budget** (max calls, wall-clock). A blocked call never reaches the server;
  the client receives an ordinary tool-error result explaining why.
- **`tools/list`** — tools outside the allowlist, or statically denied by
  policy, are removed from the listing. The agent never sees what it may not
  call; if it calls one anyway, the call-time gate blocks it (defense in depth).

Everything else — initialize, notifications, resources, prompts, server-initiated
requests — passes through transparently.

## Configure

One JSON file per upstream server:

```json
{
  "name": "files-gateway",
  "upstream": ["python", "my_file_server.py"],
  "allowed_tools": ["read_file", "list_dir", "delete_file"],
  "policies": [
    {"id": "no-deletes", "action": "tool:delete_file", "decision": "deny"},
    {"id": "log-reads",  "action": "tool:read_file",  "decision": "allow", "evidence_required": true}
  ],
  "budget": {"max_calls": 100, "max_wall_ms": 600000},
  "trace_path": "gateway_trace.json"
}
```

Then point your MCP client at the gateway instead of the server:

```json
{"command": "marrow-gateway", "args": ["/path/to/gateway.json"]}
```

`require_approval` policies are fail-closed: with no matching entry in the
config's `approvals` list, the call is denied. (A static approvals list is
deliberate for v1 — an interactive approver can't share the protocol's stdio.)

## The flight recorder

Every decision, call, result, and budget tick is written to `trace_path` —
rewritten after each event, so the record survives a crash. Render it with
[`marrow-trace`](flight-recorder.md):

```console
$ marrow-trace gateway_trace.json --open
```

## Failure semantics (honest edition)

- The gateway governs **tool traffic on one stdio server per instance**. It does
  not (yet) aggregate multiple servers, speak the HTTP transport, or inspect
  resources/prompts.
- JSON-RPC **batch arrays are rejected** (fail closed) — a batch could smuggle a
  `tools/call` past per-message inspection. Current MCP revisions don't use
  batching.
- A client line that isn't valid JSON is **dropped**, not forwarded.
- Recorded arguments/results are **redacted** (secret-looking tokens scrubbed)
  and size-capped before they touch disk; raw traffic still flows to the
  client unmodified.

Try it end to end with no setup:

```console
$ python examples/gateway/demo.py
```
