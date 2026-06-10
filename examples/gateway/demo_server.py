"""A small MCP server over stdio with file-flavoured tools, for the gateway demo.

Tools: ``read_file`` and ``list_dir`` (harmless, simulated) and ``delete_file``
(the destructive one the gateway is configured to deny). Stdlib only.
"""
import json
import sys

FILES = {
    "notes.txt": "Q3 renewal terms agreed; binder due Friday.",
    "summary.md": "# Pipeline\nTwelve submissions in review.",
}

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a (simulated) file",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": "List the (simulated) directory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_file",
        "description": "Delete a (simulated) file — destructive",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]


def text_result(msg_id, text, is_error=False):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method, msg_id = msg.get("method"), msg.get("id")
        if method == "initialize":
            reply = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "demo-file-server", "version": "0.1"},
                },
            }
        elif method == "tools/list":
            reply = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "read_file":
                content = FILES.get(args.get("path"))
                reply = (
                    text_result(msg_id, content)
                    if content is not None
                    else text_result(msg_id, "no such file", is_error=True)
                )
            elif name == "list_dir":
                reply = text_result(msg_id, "\n".join(sorted(FILES)))
            elif name == "delete_file":
                FILES.pop(args.get("path"), None)
                reply = text_result(msg_id, f"deleted {args.get('path')}")
            else:
                reply = text_result(msg_id, f"unknown tool {name}", is_error=True)
        elif msg_id is not None:
            reply = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"unknown method {method}"},
            }
        else:
            continue  # notification
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
