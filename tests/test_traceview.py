"""The flight recorder: HTML generation, escaping, and the CLI."""
from __future__ import annotations

import json
import subprocess
import sys

from marrow.compiler import AgentGraph, AgentNode, ProviderSpec, ToolSpec, compile_and_run
from marrow.traceview import render_html


def compiler_trace() -> dict:
    g = AgentGraph(name="view")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(ToolSpec(name="echo", description="Echo"))
    g.add_agent(AgentNode(id="a", name="A", provider="mock", tools=["echo"]))
    g.set_entrypoint("a")
    return compile_and_run(g, "hello")["trace"]


def test_render_embeds_the_trace():
    trace = compiler_trace()
    html = render_html(trace)
    assert "__MARROW_TRACE_JSON__" not in html
    assert trace["trace_id"] in html
    assert "Flight Recorder" in html


def test_render_escapes_script_breakout():
    # A hostile tool result must not be able to close the script tag.
    trace = {"trace_id": "tr_x", "final_status": "completed",
             "tool_calls": [{"tool": "t", "ok": True, "result": "</script><script>alert(1)"}]}
    html = render_html(trace)
    assert "</script><script>alert(1)" not in html
    assert "<\\/script>" in html


def test_standalone_page_has_drop_zone_and_no_data():
    html = render_html(None)
    assert "window.MARROW_TRACE = null" in html
    assert 'id="drop"' in html
    assert "nothing is uploaded" in html


def test_renders_gateway_trace_shape():
    trace = {
        "schema": "marrow.gateway_trace/0.1",
        "trace_id": "gw_abc",
        "gateway": "g",
        "upstream": {"command": ["x"], "server_info": {"name": "s", "version": "1"},
                     "protocol_version": "2025-06-18"},
        "started_at": 1, "completed_at": 2, "final_status": "completed",
        "tools_visible": ["echo"], "tools_hidden": ["rm"],
        "events": [{"type": "tool_called", "tool": "echo"}],
        "tool_calls": [{"tool": "echo", "ok": True, "arguments": "{}", "result": "hi",
                        "elapsed_ms": 3}],
        "policy_decisions": [], "errors": [],
        "budget": {"limits": {"max_calls": 5, "max_wall_ms": None},
                   "used": {"calls": 1, "denied": 0, "elapsed_ms": 4}},
    }
    html = render_html(trace)
    assert "gw_abc" in html


def test_cli_writes_html_next_to_trace(tmp_path):
    trace_file = tmp_path / "run.json"
    trace_file.write_text(json.dumps(compiler_trace()))
    proc = subprocess.run(
        [sys.executable, "-m", "marrow.traceview", str(trace_file)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    out = tmp_path / "run.html"
    assert out.exists()
    assert str(out) in proc.stdout
    assert "Flight Recorder" in out.read_text(encoding="utf-8")


def test_cli_rejects_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    proc = subprocess.run(
        [sys.executable, "-m", "marrow.traceview", str(bad)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "not valid JSON" in proc.stderr


def test_renders_a_crash_state_trace():
    # The flight recorder's whole point is surviving a crash — the surviving
    # artifact is final_status="running", completed_at=null, no calls yet.
    trace = {
        "schema": "marrow.gateway_trace/0.1",
        "trace_id": "gw_crash",
        "gateway": "g",
        "upstream": {"command": ["x"], "server_info": None, "protocol_version": None},
        "started_at": 1, "completed_at": None, "final_status": "running",
        "tools_visible": [], "tools_hidden": [],
        "events": [{"type": "gateway_started"}],
        "tool_calls": [], "policy_decisions": [], "errors": [],
        "budget": {"limits": {"max_calls": None, "max_wall_ms": None},
                   "used": {"calls": 0, "denied": 0, "elapsed_ms": 0}},
    }
    html = render_html(trace)
    assert "gw_crash" in html  # renders without a generator-side failure


def test_hosted_viewer_page_is_in_sync():
    # docs/trace-viewer.html is generated; regenerating must produce the same
    # bytes, or the committed page has drifted from the template.
    from pathlib import Path

    hosted = Path(__file__).parents[1] / "docs" / "trace-viewer.html"
    assert hosted.read_text(encoding="utf-8") == render_html(None), (
        "docs/trace-viewer.html is stale — regenerate with: "
        "python -m marrow.traceview --standalone -o docs/trace-viewer.html"
    )


def test_cli_standalone_to_stdout():
    proc = subprocess.run(
        [sys.executable, "-m", "marrow.traceview", "--standalone"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert 'id="drop"' in proc.stdout
