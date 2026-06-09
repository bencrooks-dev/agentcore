"""Govern an MCP server without touching it: drive a session through the
gateway and show the destructive tool being fenced off.

The "client" below is this script speaking NDJSON, exactly as Claude Desktop or
any MCP client would. The gateway launches ``demo_server.py``, forwards traffic,
denies ``delete_file`` per ``gateway.json``, and records a flight-recorder trace.

Run from the repo root:  python examples/gateway/demo.py
Then view the trace:     marrow-trace gateway_trace.json --open
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    config = json.loads((ROOT / "examples/gateway/gateway.json").read_text())
    config["upstream"] = [sys.executable, str(ROOT / "examples/gateway/demo_server.py")]
    trace_path = ROOT / "gateway_trace.json"
    config["trace_path"] = str(trace_path)
    config_path = ROOT / "examples/gateway/_resolved_gateway.json"
    config_path.write_text(json.dumps(config))

    proc = subprocess.Popen(
        [sys.executable, "-m", "marrow.gateway", str(config_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    replies = {}

    def rpc(msg_id, method, params=None):
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            msg["params"] = params
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()
        replies[msg_id] = json.loads(proc.stdout.readline())
        return replies[msg_id]

    rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "demo-client", "version": "0"}})
    listed = rpc(2, "tools/list")
    read = rpc(3, "tools/call", {"name": "read_file", "arguments": {"path": "notes.txt"}})
    denied = rpc(4, "tools/call", {"name": "delete_file", "arguments": {"path": "notes.txt"}})
    again = rpc(5, "tools/call", {"name": "read_file", "arguments": {"path": "notes.txt"}})
    proc.stdin.close()
    proc.wait(timeout=15)
    config_path.unlink()

    trace = json.loads(trace_path.read_text())
    tool_names = [t["name"] for t in listed["result"]["tools"]]
    checks = {
        "session ran through the gateway": trace["gateway"] == "demo-file-gateway",
        "reads pass through": read["result"]["isError"] is False,
        "delete blocked by policy": denied["result"]["isError"] is True
        and "blocked" in denied["result"]["content"][0]["text"],
        "file still there (server never saw the delete)": again["result"]["isError"] is False
        and "binder" in again["result"]["content"][0]["text"],
        "deny recorded as evidence": any(
            d["action"] == "tool:delete_file" and not d["allowed"]
            for d in trace["policy_decisions"]
        ),
        "trace written for marrow-trace": trace["final_status"] == "completed",
        "denied tool hidden from discovery": "delete_file" not in tool_names
        and "delete_file" in trace["tools_hidden"],
    }

    print(f"trace: {trace_path}")
    ok = True
    for label, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
