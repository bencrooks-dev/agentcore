"""A minimal MCP server over stdio (NDJSON JSON-RPC) for gateway tests.

Tools: ``echo`` (returns its text), ``boom`` (always a tool error), and
``delete_everything`` (returns a marker — tests deny it via policy and assert
it never runs). Stdlib only so the test matrix needs nothing extra.
"""
import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the input text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "boom",
        "description": "Always fails",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_everything",
        "description": "Destructive tool the gateway should fence off",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def respond(msg_id, result):
    out = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            respond(
                msg_id,
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp-server", "version": "1.0"},
                },
            )
        elif method == "tools/list":
            respond(msg_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            if name == "echo":
                text = (params.get("arguments") or {}).get("text", "")
                respond(
                    msg_id,
                    {"content": [{"type": "text", "text": f"echo: {text}"}], "isError": False},
                )
            elif name == "delete_everything":
                respond(
                    msg_id,
                    {"content": [{"type": "text", "text": "EVERYTHING DELETED"}], "isError": False},
                )
            else:
                respond(
                    msg_id,
                    {"content": [{"type": "text", "text": "kaboom"}], "isError": True},
                )
        elif msg_id is not None:
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32601, "message": f"unknown method {method}"},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
        # notifications (no id) are ignored


if __name__ == "__main__":
    main()
