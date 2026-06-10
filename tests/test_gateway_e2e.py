"""End-to-end: a real ``python -m marrow.gateway`` subprocess proxying a real
fake MCP server, driven over NDJSON exactly as an MCP client would."""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).parent
FAKE_SERVER = str(HERE / "fake_mcp_server.py")
TIMEOUT = 15


class GatewaySession:
    """Drives a gateway subprocess like an MCP client (with timeouts)."""

    def __init__(self, config_path: str):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "marrow.gateway", config_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # inherit: an unread stderr pipe could fill and wedge
        )
        self._lines: queue.Queue[bytes] = queue.Queue()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        self._next_id = 0

    def _pump(self):
        for line in self.proc.stdout:
            self._lines.put(line)

    def request(self, method, params=None):
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg).encode() + b"\n")
        self.proc.stdin.flush()
        reply = json.loads(self._lines.get(timeout=TIMEOUT))
        assert reply["id"] == self._next_id
        return reply

    def notify(self, method):
        self.proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": method}).encode() + b"\n"
        )
        self.proc.stdin.flush()

    def close(self) -> int:
        try:
            self.proc.stdin.close()
            return self.proc.wait(timeout=TIMEOUT)
        finally:
            if self.proc.poll() is None:
                self.proc.kill()


@pytest.fixture
def session(tmp_path):
    trace_path = tmp_path / "trace.json"
    config = {
        "upstream": [sys.executable, FAKE_SERVER],
        "name": "test-gateway",
        "allowed_tools": ["echo", "boom", "delete_everything"],
        "policies": [
            {"id": "no-delete", "action": "tool:delete_everything", "decision": "deny"}
        ],
        "budget": {"max_calls": 10},
        "trace_path": str(trace_path),
    }
    config_path = tmp_path / "gateway.json"
    config_path.write_text(json.dumps(config))
    s = GatewaySession(str(config_path))
    yield s, trace_path
    s.close()


def test_full_session_through_the_gateway(session):
    s, trace_path = session

    # initialize handshake passes through; serverInfo comes from the real server
    init = s.request(
        "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}},
    )
    assert init["result"]["serverInfo"]["name"] == "fake-mcp-server"
    s.notify("notifications/initialized")

    # the denied tool is hidden from discovery
    listed = s.request("tools/list")
    names = [t["name"] for t in listed["result"]["tools"]]
    assert "echo" in names and "delete_everything" not in names

    # an allowed call round-trips to the real server
    ok = s.request("tools/call", {"name": "echo", "arguments": {"text": "hi"}})
    assert ok["result"]["isError"] is False
    assert ok["result"]["content"][0]["text"] == "echo: hi"

    # the denied call is blocked at the gateway — the server never sees it
    denied = s.request("tools/call", {"name": "delete_everything", "arguments": {}})
    assert denied["result"]["isError"] is True
    assert "blocked" in denied["result"]["content"][0]["text"]

    # a failing tool's error result is recorded faithfully
    boom = s.request("tools/call", {"name": "boom", "arguments": {}})
    assert boom["result"]["isError"] is True

    code = s.close()
    assert code == 0

    # flight recorder: the whole session is on disk, valid against the schema
    trace = json.loads(trace_path.read_text())
    from marrow.compiler.validate import validate

    validate(trace, "gateway_trace.schema.json")
    assert trace["schema"].startswith("marrow.gateway_trace/")
    assert trace["final_status"] == "completed"
    assert trace["upstream"]["server_info"]["name"] == "fake-mcp-server"
    assert trace["tools_hidden"] == ["delete_everything"]
    calls = {(c["tool"], c["ok"]) for c in trace["tool_calls"]}
    assert ("echo", True) in calls and ("boom", False) in calls
    assert ("delete_everything", True) not in calls  # never executed
    assert any(
        d["action"] == "tool:delete_everything" and d["allowed"] is False
        for d in trace["policy_decisions"]
    )
    assert trace["budget"]["used"]["calls"] == 2  # echo + boom; the deny costs nothing
    assert trace["budget"]["used"]["denied"] == 1
    types = [e["type"] for e in trace["events"]]
    assert "tool_denied" in types and "tool_called" in types and "client_eof" in types


def test_transparent_gateway_changes_nothing(tmp_path):
    # The cautious first run: upstream + trace only, no governance config.
    # The session must behave exactly as without the gateway.
    trace_path = tmp_path / "trace.json"
    config_path = tmp_path / "gateway.json"
    config_path.write_text(
        json.dumps({"upstream": [sys.executable, FAKE_SERVER], "trace_path": str(trace_path)})
    )
    s = GatewaySession(str(config_path))
    try:
        s.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "t"}})
        listed = s.request("tools/list")
        assert [t["name"] for t in listed["result"]["tools"]] == [
            "echo", "boom", "delete_everything"
        ]
        ok = s.request("tools/call", {"name": "delete_everything", "arguments": {}})
        assert ok["result"]["isError"] is False  # nothing configured -> nothing blocked
    finally:
        code = s.close()
    assert code == 0
    trace = json.loads(trace_path.read_text())
    assert trace["tools_hidden"] == []
    assert trace["policy_decisions"] == []
    assert trace["budget"]["limits"] == {"max_calls": None, "max_wall_ms": None}


def test_upstream_exit_propagates_cleanly_while_client_stays_connected(tmp_path):
    # Real MCP clients keep the gateway's stdin open for the whole session. When
    # the upstream exits first, the gateway must exit with the upstream's code —
    # not abort in interpreter shutdown over the still-blocked stdin reader.
    config_path = tmp_path / "gateway.json"
    config_path.write_text(
        json.dumps({"upstream": [sys.executable, "-c", "pass"],
                    "trace_path": str(tmp_path / "t.json")})
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "marrow.gateway", str(config_path)],
        stdin=subprocess.PIPE,   # held open — the upstream dies first
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, err = proc.communicate(timeout=TIMEOUT)  # waits for exit, drains pipes
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0
    assert b"Fatal Python error" not in err


def test_eof_ignoring_upstream_is_terminated_on_client_disconnect(tmp_path):
    # A server that ignores stdin EOF must not leak forever after the client
    # disconnects; the gateway bounds the grace period and terminates it.
    trace_path = tmp_path / "t.json"
    config_path = tmp_path / "gateway.json"
    config_path.write_text(
        json.dumps({
            "upstream": [sys.executable, "-c", "import time; time.sleep(120)"],
            "trace_path": str(trace_path),
        })
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "marrow.gateway", str(config_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
    )
    proc.stdin.close()  # client disconnects immediately
    try:
        proc.wait(timeout=TIMEOUT)  # well under the 120s the upstream wants
    finally:
        if proc.poll() is None:
            proc.kill()
    trace = json.loads(trace_path.read_text())
    assert trace["final_status"] != "running"  # the record was finalized


def test_gateway_rejects_bad_config(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"policies": []}))  # no upstream
    proc = subprocess.run(
        [sys.executable, "-m", "marrow.gateway", str(bad)],
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode == 2
    assert b"upstream" in proc.stderr
