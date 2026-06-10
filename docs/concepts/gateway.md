# MCP gateway

The gateway applies Marrow's governance to **any MCP server, with zero changes
to your agent or the server**. It is a transparent stdio proxy: your MCP client
launches `marrow-gateway` instead of the real server, the gateway launches the
real server, and traffic flows through with its meaning intact — except that
tool use is governed and recorded.

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
  [`PolicyEngine`](compiler.md#governance) the compiler uses (`tool:<name>`
  actions; `allow` / `deny` / `require_approval`), an optional tool
  **allowlist**, and a **budget** (max calls, wall-clock). A blocked call never
  reaches the server; the client receives an ordinary tool-error result
  explaining why (a blocked id-less *notification* call has no reply to carry
  the reason — it is dropped and recorded).
- **`tools/list`** — tools outside the allowlist, or statically denied by
  policy, are removed from the listing; approval-gated tools stay listed
  because an approval may grant them at call time. Whatever the listing shows,
  every call is re-checked at call time (defense in depth).

Everything else — initialize, notifications, resources, prompts, server-initiated
requests — passes through unmodified in meaning. (Client messages are forwarded
re-encoded from the parsed JSON, so the gateway and the server can never
disagree about what a message says.)

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
  "budget": {"max_calls": 100},
  "trace_path": "gateway_trace.json"
}
```

A relative `trace_path` is resolved against the config file's directory (MCP
clients launch servers from arbitrary working directories). `max_wall_ms` is a
**session-lifetime** budget: the clock starts when the gateway launches and
includes idle time, which suits one-shot or batch sessions — for a long-lived
desktop client, prefer `max_calls`. Unknown config keys are rejected at startup,
so a typo can't silently weaken governance.

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
