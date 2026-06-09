# python_to_ari_compile

The compiler MVP end to end: a Python-defined agent graph is compiled to an ARI
manifest, lowered to a RuntimePlan, executed through the native runtime, and the
run is recorded as an ExecutionTrace — using a **mock provider** and **no API
keys**.

```
build_graph()  ->  ARI manifest  ->  RuntimePlan  ->  execute (C++ runtime)  ->  ExecutionTrace
```

## Files

| File | What it is |
|---|---|
| `build_graph.py` | Defines the echo-agent graph (`build_graph()`) |
| `compile_to_ari.py` | Compiles the graph to an ARI manifest and prints it |
| `run_runtime_plan.py` | Full pipeline + the seven proof checks (exits non-zero on failure) |
| `expected_ari.json` | Golden ARI manifest |
| `expected_runtime_plan.json` | Golden RuntimePlan (deterministic ids) |
| `expected_trace.json` | Golden ExecutionTrace (wall-clock timestamps nulled) |

## Run

```bash
python examples/python_to_ari_compile/compile_to_ari.py     # print the ARI manifest
python examples/python_to_ari_compile/run_runtime_plan.py   # full pipeline + proof
```

## What it proves

1. A Python-defined agent graph can be created.
2. The graph can compile to ARI.
3. ARI can compile to a RuntimePlan.
4. The RuntimePlan executes through Marrow.
5. An ExecutionTrace is emitted.
6. The RuntimePlan is portable JSON.
7. No external API key is required.

The `graph_id`, `runtime_plan_id`, and `trace_id` are content-addressed hashes,
so the golden files are reproducible; only the trace's `started_at`/`completed_at`
are wall-clock (nulled in `expected_trace.json`). See
[`docs/compiler_architecture.md`](../../docs/compiler_architecture.md).
