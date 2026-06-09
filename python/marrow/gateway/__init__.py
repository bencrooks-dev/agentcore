"""MCP governance gateway.

A transparent stdio proxy that sits between any MCP client and an MCP tool
server and applies Marrow's governance to the traffic — no change to the agent
or the server. The client launches ``marrow-gateway <config.json>`` instead of
the real server; the gateway launches the real server as a subprocess, forwards
JSON-RPC both ways, and intercepts exactly two things:

- ``tools/call`` — gated by the same :class:`~marrow.compiler.governance.PolicyEngine`
  the compiler uses (``tool:<name>`` actions, allow / deny / require_approval),
  an optional tool allowlist (least privilege), and a call/wall-clock budget.
  Blocked calls never reach the server; the client receives a normal tool-error
  result explaining why.
- ``tools/list`` — tools outside the allowlist (or statically denied by policy)
  are removed from the listing, so the agent never sees what it may not call.

Every decision, call, and result lands in a flight-recorder trace (JSON),
rewritten after each event so it survives a crash. View it with ``marrow-trace``.
"""
from __future__ import annotations

from .config import GatewayConfig, GatewayError, load_config
from .proxy import Gateway

__all__ = ["Gateway", "GatewayConfig", "GatewayError", "load_config"]
