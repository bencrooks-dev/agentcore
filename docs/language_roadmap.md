# Language Roadmap

> How additional authoring languages reach the Marrow runtime. The principle:
> **language frontends emit ARI; ARI is the stable target; Marrow compiles ARI
> into a RuntimePlan.** We do not build a general multi-language compiler.

```
frontend (any language)  ──►  ARI manifest (JSON/YAML)  ──►  RuntimePlan  ──►  native runtime
        emits ARI                  the stable contract        Marrow compiles
```

## V1 — Python frontend (current)

- Python frontend (`marrow.compiler`: `AgentGraph` / `AgentNode` / `ToolSpec` /
  `ProviderSpec`).
- JSON ARI manifests (YAML is an equivalent surface over the same schemas).

## V2 — TypeScript

- A TypeScript SDK / exporter that emits the same ARI manifests. No runtime
  rewrite: TS authors a graph, exports ARI, Marrow compiles and runs it.

## V3 — WASM

- A WASM plugin/tool target so tools (and later frontends) authored in other
  languages can run in a sandbox the runtime drives.

## Later

- Rust SDK / exporter.
- Go SDK / exporter.
- Java enterprise SDK / exporter.
- C++ native authoring support (author a graph directly against the core).

## The principle (why this shape)

- **Do not** build support for arbitrary multi-language *compilation* now.
- The right model is **language frontends that emit ARI**.
- **ARI is the stable target.** Frontends compete on ergonomics; they converge on
  the same manifest schemas.
- **Marrow compiles ARI into a RuntimePlan** and executes it natively. Adding a
  language means adding an ARI emitter, not a new runtime.

This keeps the surface small: one runtime, one intermediate representation, many
thin frontends.
