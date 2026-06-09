"""Unit tests for gateway config validation and message gating (no subprocess)."""
from __future__ import annotations

import json

import pytest

from marrow.gateway import Gateway, GatewayError
from marrow.gateway.config import parse_config


def make_config(**overrides):
    raw = {"upstream": ["true"], "trace_path": None}
    raw.update(overrides)
    return parse_config(raw)


def gw(**overrides) -> Gateway:
    import io

    return Gateway(make_config(**overrides), client_in=io.BytesIO(), client_out=io.BytesIO())


def call_line(msg_id, name, arguments=None):
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    ).encode() + b"\n"


# --- config validation -------------------------------------------------------


def test_config_requires_upstream():
    with pytest.raises(GatewayError, match="upstream"):
        parse_config({})


def test_config_rejects_unknown_decision():
    with pytest.raises(GatewayError, match="decision"):
        parse_config({"upstream": ["x"], "policies": [{"action": "tool:a", "decision": "block"}]})


def test_config_fills_policy_defaults():
    cfg = parse_config({"upstream": ["x"], "policies": [{"action": "tool:a", "decision": "deny"}]})
    assert cfg.policies[0]["approval_required"] is False
    assert cfg.policies[0]["evidence_required"] is False
    assert cfg.policies[0]["id"] == "policy_0"


def test_config_rejects_negative_budget():
    with pytest.raises(GatewayError, match="max_calls"):
        parse_config({"upstream": ["x"], "budget": {"max_calls": -1}})


# --- tools/call gating ---------------------------------------------------------


def test_call_outside_allowlist_is_answered_not_forwarded():
    g = gw(allowed_tools=["echo"])
    [(dest, line)] = g.handle_client_line(call_line(1, "delete_everything"))
    assert dest == "client"
    reply = json.loads(line)
    assert reply["id"] == 1 and reply["result"]["isError"] is True
    assert "allowlist" in reply["result"]["content"][0]["text"]


def test_denied_policy_blocks_call():
    g = gw(policies=[{"action": "tool:rm", "decision": "deny"}])
    [(dest, line)] = g.handle_client_line(call_line(2, "rm"))
    assert dest == "client"
    assert json.loads(line)["result"]["isError"] is True
    assert any(d["allowed"] is False for d in g._trace["policy_decisions"])


def test_require_approval_without_approval_fails_closed():
    g = gw(policies=[{"action": "tool:wire", "decision": "require_approval"}])
    [(dest, _)] = g.handle_client_line(call_line(3, "wire"))
    assert dest == "client"


def test_require_approval_with_static_approval_forwards():
    g = gw(
        policies=[{"action": "tool:wire", "decision": "require_approval"}],
        approvals=["tool:wire"],
    )
    [(dest, _)] = g.handle_client_line(call_line(4, "wire"))
    assert dest == "server"


def test_allowed_call_is_forwarded_and_budgeted():
    g = gw()
    [(dest, _)] = g.handle_client_line(call_line(5, "echo", {"text": "hi"}))
    assert dest == "server"
    assert g._trace["budget"]["used"]["calls"] == 1
    assert 5 in g._pending_calls


def test_call_budget_exhaustion_blocks():
    g = gw(budget={"max_calls": 1})
    [(d1, _)] = g.handle_client_line(call_line(6, "echo"))
    [(d2, line)] = g.handle_client_line(call_line(7, "echo"))
    assert (d1, d2) == ("server", "client")
    assert "budget exhausted" in json.loads(line)["result"]["content"][0]["text"]


def test_batch_requests_are_rejected():
    g = gw()
    batch = json.dumps(
        [{"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "echo"}}]
    ).encode()
    [(dest, line)] = g.handle_client_line(batch)
    assert dest == "client"
    assert json.loads(line)["error"]["code"] == -32600


def test_invalid_client_json_is_dropped(capsys):
    g = gw()
    assert g.handle_client_line(b"{nope\n") == []
    assert any(e["type"] == "invalid_client_json" for e in g._trace["events"])


def test_non_tool_traffic_passes_through():
    g = gw(policies=[{"action": "*", "decision": "deny"}])
    line = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "resources/list"}).encode()
    [(dest, _)] = g.handle_client_line(line)
    assert dest == "server"  # only tools/* is governed; the rest is transparent


# --- tools/list filtering ----------------------------------------------------------


def list_response(msg_id, names):
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": [{"name": n, "description": n} for n in names]},
        }
    ).encode() + b"\n"


def test_tools_list_filters_denied_and_unlisted():
    g = gw(
        allowed_tools=["echo", "wire"],
        policies=[{"action": "tool:wire", "decision": "deny"}],
    )
    g.handle_client_line(json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list"}).encode())
    out = g.handle_server_line(list_response(10, ["echo", "wire", "delete_everything"]))
    tools = json.loads(out)["result"]["tools"]
    assert [t["name"] for t in tools] == ["echo"]
    assert g._trace["tools_hidden"] == ["wire", "delete_everything"]


def test_approval_gated_tools_stay_listed():
    g = gw(policies=[{"action": "tool:wire", "decision": "require_approval"}])
    g.handle_client_line(json.dumps({"jsonrpc": "2.0", "id": 11, "method": "tools/list"}).encode())
    out = g.handle_server_line(list_response(11, ["wire"]))
    assert [t["name"] for t in json.loads(out)["result"]["tools"]] == ["wire"]


# --- result recording -----------------------------------------------------------------


def test_tool_result_is_recorded_with_redaction():
    g = gw()
    g.handle_client_line(call_line(12, "echo", {"text": "x"}))
    response = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "result": {
                "content": [{"type": "text", "text": "key sk-ant-abcdefgh12345678ijkl"}],
                "isError": False,
            },
        }
    ).encode()
    g.handle_server_line(response)
    [call] = g._trace["tool_calls"]
    assert call["tool"] == "echo" and call["ok"] is True
    assert "sk-ant-" not in call["result"] and "REDACTED" in call["result"]


def test_long_results_are_truncated():
    g = gw(max_record_bytes=64)
    g.handle_client_line(call_line(13, "echo"))
    response = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "result": {"content": [{"type": "text", "text": "x" * 5000}], "isError": False},
        }
    ).encode()
    g.handle_server_line(response)
    [call] = g._trace["tool_calls"]
    assert len(call["result"]) < 100 and call["result"].endswith("[truncated]")
