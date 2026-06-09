"""The gateway proxy: a transparent NDJSON JSON-RPC pipe with two interceptors.

Message flow (stdio transport, one JSON object per line):

    MCP client  ──stdin──▶  Gateway  ──pipe──▶  upstream MCP server
                ◀─stdout──           ◀─pipe──

Everything is forwarded untouched — initialize, notifications, resources,
prompts, server-initiated requests — except:

- client ``tools/call`` requests are gated (allowlist, policy, budget). A
  blocked call is answered directly with a tool-error result and never reaches
  the server.
- server ``tools/list`` responses are filtered to the tools the agent is
  actually allowed to see.

Fail-closed choices: a client line that is not valid JSON is dropped (not
forwarded), and JSON-RPC batch arrays are rejected — a batch could smuggle a
``tools/call`` past per-message inspection. Both are recorded in the trace.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from typing import Any, BinaryIO

from ..compiler.governance import BudgetMeter, PolicyEngine
from ..tools import _scrub_secrets
from .config import GatewayConfig

# BudgetMeter requires a numeric step bound; "no call limit" is modelled as a
# bound no real session reaches.
_UNLIMITED_CALLS = 10**9


def _now_ms() -> int:
    return int(time.time() * 1000)


class Gateway:
    """One gateway instance: governance state, trace state, and the pumps."""

    def __init__(
        self,
        config: GatewayConfig,
        client_in: BinaryIO | None = None,
        client_out: BinaryIO | None = None,
    ) -> None:
        self._cfg = config
        self._client_in = client_in if client_in is not None else sys.stdin.buffer
        self._client_out = client_out if client_out is not None else sys.stdout.buffer
        approver = (
            (lambda action, checkpoint: action in config.approvals)
            if config.approvals
            else None
        )
        self._policy = PolicyEngine(config.policies, approver=approver)
        self._budget = BudgetMeter(
            {
                "max_steps": config.max_calls if config.max_calls is not None else _UNLIMITED_CALLS,
                "max_tokens": None,
                "max_cost_usd": None,
                "max_wall_ms": config.max_wall_ms,
            }
        )
        self._child: subprocess.Popen | None = None
        self._out_lock = threading.Lock()
        self._trace_lock = threading.Lock()
        self._pending_calls: dict[Any, dict] = {}
        self._list_request_ids: set[Any] = set()
        self._initialize_ids: set[Any] = set()
        self._denied = 0
        started = _now_ms()
        seed = f"{config.name}:{started}:{os.getpid()}".encode()
        self._trace: dict[str, Any] = {
            "schema": "marrow.gateway_trace/0.1",
            "trace_id": "gw_" + hashlib.sha256(seed).hexdigest()[:16],
            "gateway": config.name,
            "upstream": {"command": list(config.upstream), "server_info": None,
                         "protocol_version": None},
            "started_at": started,
            "completed_at": None,
            "final_status": "running",
            "tools_visible": [],
            "tools_hidden": [],
            "events": [],
            "tool_calls": [],
            "policy_decisions": [],
            "budget": {
                "limits": {"max_calls": config.max_calls, "max_wall_ms": config.max_wall_ms},
                "used": {"calls": 0, "denied": 0, "elapsed_ms": 0},
            },
            "errors": [],
        }
        self._event("gateway_started")

    # ----- trace recording ----------------------------------------------------

    def _record(self, mutate) -> None:
        with self._trace_lock:
            mutate(self._trace)
            self._trace["budget"]["used"] = {
                "calls": self._budget.steps,
                "denied": self._denied,
                "elapsed_ms": self._budget.elapsed_ms(),
            }
            self._flush_trace_locked()

    def _flush_trace_locked(self) -> None:
        if not self._cfg.trace_path:
            return
        tmp = self._cfg.trace_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._trace, f, indent=2)
            os.replace(tmp, self._cfg.trace_path)
        except OSError as exc:  # tracing must never take the proxy down
            print(f"marrow-gateway: cannot write trace: {exc}", file=sys.stderr)

    def _event(self, type_: str, **fields: str) -> None:
        entry = {"type": type_, **{k: str(v) for k, v in fields.items()}}
        self._record(lambda t: t["events"].append(entry))

    def _preview(self, value: Any) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if self._cfg.redact:
            text = _scrub_secrets(text)
        data = text.encode("utf-8")
        if len(data) <= self._cfg.max_record_bytes:
            return text
        clipped = data[: self._cfg.max_record_bytes].decode("utf-8", errors="ignore")
        return clipped + "…[truncated]"

    # ----- gating ---------------------------------------------------------------

    def gate_tool_call(self, name: str) -> tuple[bool, str | None]:
        """Decide whether a tools/call may proceed. Returns (allowed, reason)."""
        action = f"tool:{name}"

        if self._cfg.allowed_tools is not None and name not in self._cfg.allowed_tools:
            return False, f"tool {name!r} is not in this gateway's allowlist"

        decisions = self._policy.evaluate(action)
        if decisions:
            recorded = [asdict(d) for d in decisions]
            self._record(lambda t: t["policy_decisions"].extend(recorded))
        for d in decisions:
            if not d.allowed:
                return False, f"call to {action!r} denied by policy (decision: {d.decision})"

        if self._budget.over_wall():
            return False, (
                f"wall-clock budget exceeded ({self._cfg.max_wall_ms} ms)"
            )
        if not self._budget.can_start_step():
            return False, f"call budget exhausted (max_calls={self._cfg.max_calls})"
        return True, None

    def list_visible_tools(self, tools: list[dict]) -> tuple[list[dict], list[str]]:
        """Filter a tools/list result: drop allowlist misses and static denies."""
        visible, hidden = [], []
        for tool in tools:
            name = tool.get("name", "")
            allowed = self._cfg.allowed_tools is None or name in self._cfg.allowed_tools
            if allowed:
                # Hide only unconditional denies; approval-gated tools stay
                # listed because an approval may grant them at call time.
                allowed = not any(
                    d.decision == "deny" for d in self._policy.evaluate(f"tool:{name}")
                )
            (visible if allowed else hidden).append(tool if allowed else name)
        return visible, hidden

    # ----- message handling -----------------------------------------------------

    def handle_client_line(self, raw: bytes) -> list[tuple[str, bytes]]:
        """Route one line from the client. Returns [(destination, line), ...]
        where destination is "server" (forward) or "client" (answer directly)."""
        stripped = raw.strip()
        if not stripped:
            return []
        try:
            msg = json.loads(stripped)
        except ValueError:
            self._event("invalid_client_json")
            print("marrow-gateway: dropped non-JSON client line", file=sys.stderr)
            return []

        if isinstance(msg, list):
            # A batch could smuggle a tools/call past inspection — reject it.
            self._event("batch_rejected")
            replies = [
                _error_response(m["id"], -32600, "marrow-gateway does not accept batch requests")
                for m in msg
                if isinstance(m, dict) and "id" in m and "method" in m
            ]
            return [("client", _encode(r)) for r in replies]

        if not isinstance(msg, dict):
            self._event("invalid_client_json")
            return []

        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "tools/call":
            params = msg.get("params") or {}
            name = str(params.get("name", ""))
            allowed, reason = self.gate_tool_call(name)
            if not allowed:
                self._denied += 1
                self._event("tool_denied", tool=name, reason=reason or "")
                if msg_id is None:
                    # A notification can't be answered; dropping it is the only
                    # fail-closed option (and gates the no-id smuggling path).
                    return []
                return [("client", _encode(_deny_response(msg_id, name, reason or "denied")))]
            self._budget.record_step()
            if msg_id is not None:
                self._pending_calls[msg_id] = {
                    "tool": name,
                    "arguments": self._preview(params.get("arguments", {})),
                    "t0": time.monotonic(),
                }
            self._event("tool_call_forwarded", tool=name)
            return [("server", _encode(msg))]

        if method == "tools/list" and msg_id is not None:
            self._list_request_ids.add(msg_id)
        elif method == "initialize" and msg_id is not None:
            self._initialize_ids.add(msg_id)
        # Forward the *parsed* message re-encoded, not the raw bytes: the
        # gateway and the server must never disagree about what a message says
        # (e.g. duplicate JSON keys parsing differently across implementations).
        return [("server", _encode(msg))]

    def handle_server_line(self, raw: bytes) -> bytes:
        """Inspect one line from the server; returns the line to send the client."""
        stripped = raw.strip()
        if not stripped:
            return raw
        try:
            msg = json.loads(stripped)
        except ValueError:
            return raw  # information flows toward the client only; forward as-is
        if not isinstance(msg, dict):
            return raw

        if "method" in msg:
            # A server -> client REQUEST or notification (roots/list, sampling,
            # elicitation, ...). Its id space is independent of the client's —
            # never confuse it with a response to a tracked client request.
            return raw

        msg_id = msg.get("id")
        if msg_id is None:
            return raw

        if msg_id in self._initialize_ids:
            self._initialize_ids.discard(msg_id)
            result = msg.get("result") or {}
            info = result.get("serverInfo")
            proto = result.get("protocolVersion")

            def _set(t: dict) -> None:
                t["upstream"]["server_info"] = info
                t["upstream"]["protocol_version"] = proto

            self._record(_set)
            self._event("upstream_initialized")
            return raw

        if msg_id in self._list_request_ids:
            self._list_request_ids.discard(msg_id)
            result = msg.get("result")
            if isinstance(result, dict) and isinstance(result.get("tools"), list):
                visible, hidden = self.list_visible_tools(result["tools"])
                result["tools"] = visible
                names = [t.get("name", "") for t in visible]

                def _set(t: dict) -> None:
                    # Merge: a paginated or repeated tools/list must accumulate,
                    # not overwrite the record of earlier pages.
                    t["tools_visible"] = sorted(set(t.get("tools_visible", [])) | set(names))
                    t["tools_hidden"] = sorted(set(t.get("tools_hidden", [])) | set(hidden))

                self._record(_set)
                self._event(
                    "tools_listed", visible=str(len(visible)), hidden=str(len(hidden))
                )
                return _encode(msg)
            return raw

        pending = self._pending_calls.pop(msg_id, None)
        if pending is not None:
            elapsed = int((time.monotonic() - pending["t0"]) * 1000)
            ok, preview = _summarize_tool_result(msg)
            entry = {
                "tool": pending["tool"],
                "ok": ok,
                "arguments": pending["arguments"],
                "result": self._preview(preview),
                "elapsed_ms": elapsed,
            }
            self._record(lambda t: t["tool_calls"].append(entry))
            self._event("tool_called" if ok else "tool_error", tool=pending["tool"])
        return raw

    # ----- the pumps --------------------------------------------------------------

    def _write_client(self, line: bytes) -> None:
        with self._out_lock:
            self._client_out.write(line if line.endswith(b"\n") else line + b"\n")
            self._client_out.flush()

    def run(self) -> int:
        """Run the proxy until the client disconnects or the server exits."""
        self._child = subprocess.Popen(  # noqa: S603 — the operator's configured server
            self._cfg.upstream,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # inherit: upstream logs stay visible
        )
        assert self._child.stdin is not None and self._child.stdout is not None

        def pump_client_to_server() -> None:
            try:
                for raw in self._client_in:
                    for destination, line in self.handle_client_line(raw):
                        if destination == "server":
                            self._child.stdin.write(line if line.endswith(b"\n") else line + b"\n")
                            self._child.stdin.flush()
                        else:
                            self._write_client(line)
            except (BrokenPipeError, OSError):
                pass
            finally:
                self._event("client_eof")
                with contextlib.suppress(OSError):
                    self._child.stdin.close()

        def pump_server_to_client() -> None:
            try:
                for raw in self._child.stdout:
                    self._write_client(self.handle_server_line(raw))
            except (BrokenPipeError, OSError):
                pass

        t_in = threading.Thread(target=pump_client_to_server, daemon=True)
        t_out = threading.Thread(target=pump_server_to_client, daemon=True)
        t_in.start()
        t_out.start()
        code = self._child.wait()
        t_out.join(timeout=5)

        def _finish(t: dict) -> None:
            t["completed_at"] = _now_ms()
            t["final_status"] = "completed" if code == 0 else "upstream_exited"
            if code != 0:
                t["errors"].append(
                    {"kind": "UpstreamExited", "message": f"upstream exited with code {code}"}
                )

        self._record(_finish)
        return code


# ----- pure helpers ------------------------------------------------------------------


def _encode(msg: dict) -> bytes:
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def _deny_response(msg_id: Any, tool: str, reason: str) -> dict:
    text = f"marrow-gateway blocked tool {tool!r}: {reason}"
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": True},
    }


def _error_response(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _summarize_tool_result(msg: dict) -> tuple[bool, str]:
    """Extract (ok, text preview) from a tools/call response."""
    if "error" in msg:
        err = msg["error"] or {}
        return False, f"jsonrpc error {err.get('code')}: {err.get('message', '')}"
    result = msg.get("result") or {}
    ok = not bool(result.get("isError", False))
    parts = [
        block.get("text", "")
        for block in result.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return ok, " ".join(p for p in parts if p)
