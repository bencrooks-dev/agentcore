# Flight recorder

A Marrow trace is evidence: every provider call, tool call, policy decision,
budget tick, and error from a run. The flight recorder turns that JSON into a
report you can read, share, and audit — one self-contained HTML file, no server,
no build step, nothing uploaded anywhere.

It renders both trace kinds:

- the compiler's **ExecutionTrace** (`compile_and_run(...)["trace"]`,
  `run_runtime_plan(...)`), and
- the **MCP gateway's** session trace.

## From the command line

```console
$ marrow-trace run_trace.json            # writes run_trace.html next to it
$ marrow-trace run_trace.json --open     # ...and opens it
$ marrow-trace gateway_trace.json -o report.html
```

## From Python

```python
from marrow.traceview import render_html

out = compile_and_run(graph, "input")
html = render_html(out["trace"])
Path("report.html").write_text(html)
```

## In the browser

The [hosted viewer](../trace-viewer.html) is the same page with a drop zone:
drag any trace JSON onto it. Rendering happens entirely in your browser — the
file never leaves your machine.

## What it shows

| Section | Compiler trace | Gateway trace |
|---|---|---|
| Status + duration | ✓ | ✓ |
| Summary cards | steps · tokens · cost | calls allowed/denied · tools visible/hidden |
| Budget | usage | usage **vs limits**, with bars |
| Policy decisions | ✓ (allowed/blocked, flags) | ✓ |
| Tool calls | outcome + result | outcome + arguments/result + elapsed |
| Provider calls | agent · model · tokens | — (the gateway sees only tool traffic) |
| Timeline | every recorded event, color-coded | ✓ |
| Errors | ✓ | ✓ |

Trace content is treated as untrusted input — the viewer builds the page with
`textContent`, never `innerHTML`, so a hostile tool result can't script the
report.
