"""Gateway configuration: a small JSON file, validated fail-fast at startup."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DECISIONS = ("allow", "deny", "require_approval")

# A typo'd key must not silently weaken governance ("alowed_tools" would start
# an ungoverned gateway). Unknown keys are rejected, at every level.
_KNOWN_KEYS = {
    "upstream", "name", "allowed_tools", "policies", "approvals",
    "budget", "trace_path", "max_record_bytes", "redact",
}
_KNOWN_BUDGET_KEYS = {"max_calls", "max_wall_ms"}
_KNOWN_POLICY_KEYS = {
    "id", "action", "decision", "approval_required", "evidence_required", "description",
}


class GatewayError(ValueError):
    """Raised for invalid gateway configuration or protocol misuse."""


@dataclass
class GatewayConfig:
    """Configuration for one gateway instance (one upstream MCP server).

    ``policies`` use the same checkpoint shape as the compiler's PolicySpec
    (``action`` like ``tool:<name>`` or ``*``, ``decision`` of allow / deny /
    require_approval). ``approvals`` is a static list of actions that are
    considered approved when a ``require_approval`` checkpoint fires — with no
    entry, approval-gated actions are denied (fail closed), matching the
    compiler's approver semantics.
    """

    upstream: list[str]
    name: str = "marrow-gateway"
    allowed_tools: list[str] | None = None
    policies: list[dict] = field(default_factory=list)
    approvals: list[str] = field(default_factory=list)
    max_calls: int | None = None
    max_wall_ms: int | None = None
    trace_path: str | None = None
    max_record_bytes: int = 2048
    redact: bool = True


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise GatewayError(f"gateway config: {message}")


def parse_config(raw: dict[str, Any], base_dir: Path | None = None) -> GatewayConfig:
    """Validate a raw config dict and return a :class:`GatewayConfig`.

    ``base_dir`` anchors a relative ``trace_path`` (the config file's directory
    when loaded from disk) — MCP clients launch servers from arbitrary working
    directories, so a cwd-relative trace would silently land elsewhere or fail.
    """
    _require(isinstance(raw, dict), "top level must be an object")
    unknown = set(raw) - _KNOWN_KEYS
    _require(not unknown, f"unknown key(s) {sorted(unknown)} — refusing to start")
    upstream = raw.get("upstream")
    _require(
        isinstance(upstream, list) and upstream and all(isinstance(s, str) for s in upstream),
        "'upstream' must be a non-empty list of command arguments",
    )

    allowed = raw.get("allowed_tools")
    if allowed is not None:
        _require(
            isinstance(allowed, list) and all(isinstance(t, str) for t in allowed),
            "'allowed_tools' must be a list of tool names",
        )

    policies = raw.get("policies", [])
    _require(isinstance(policies, list), "'policies' must be a list")
    normalized = []
    for i, p in enumerate(policies):
        _require(isinstance(p, dict), f"policies[{i}] must be an object")
        bad = set(p) - _KNOWN_POLICY_KEYS
        _require(not bad, f"policies[{i}]: unknown key(s) {sorted(bad)}")
        action = p.get("action")
        _require(isinstance(action, str) and action, f"policies[{i}].action is required")
        decision = p.get("decision", "allow")
        _require(
            decision in _DECISIONS,
            f"policies[{i}].decision must be one of {_DECISIONS}, got {decision!r}",
        )
        normalized.append(
            {
                "id": p.get("id", f"policy_{i}"),
                "action": action,
                "decision": decision,
                "approval_required": bool(p.get("approval_required", False)),
                "evidence_required": bool(p.get("evidence_required", False)),
            }
        )

    approvals = raw.get("approvals", [])
    _require(
        isinstance(approvals, list) and all(isinstance(a, str) for a in approvals),
        "'approvals' must be a list of action strings",
    )

    budget = raw.get("budget", {}) or {}
    _require(isinstance(budget, dict), "'budget' must be an object")
    bad_budget = set(budget) - _KNOWN_BUDGET_KEYS
    _require(not bad_budget, f"budget: unknown key(s) {sorted(bad_budget)}")
    max_calls = budget.get("max_calls")
    max_wall_ms = budget.get("max_wall_ms")
    for label, value in (("max_calls", max_calls), ("max_wall_ms", max_wall_ms)):
        _require(
            value is None or (isinstance(value, int) and value >= 0),
            f"budget.{label} must be a non-negative integer",
        )

    max_record = raw.get("max_record_bytes", 2048)
    _require(
        isinstance(max_record, int) and max_record > 0,
        "'max_record_bytes' must be a positive integer",
    )

    trace_path = raw.get("trace_path")
    if trace_path is not None:
        _require(isinstance(trace_path, str) and trace_path, "'trace_path' must be a string")
        resolved = Path(trace_path)
        if base_dir is not None and not resolved.is_absolute():
            resolved = base_dir / resolved
        trace_path = str(resolved)

    return GatewayConfig(
        upstream=list(upstream),
        name=str(raw.get("name", "marrow-gateway")),
        allowed_tools=list(allowed) if allowed is not None else None,
        policies=normalized,
        approvals=list(approvals),
        max_calls=max_calls,
        max_wall_ms=max_wall_ms,
        trace_path=trace_path,
        max_record_bytes=max_record,
        redact=bool(raw.get("redact", True)),
    )


def load_config(path: str | Path) -> GatewayConfig:
    """Load and validate a gateway config file. A relative ``trace_path`` is
    resolved against the config file's directory."""
    config_path = Path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GatewayError(f"gateway config: cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise GatewayError(f"gateway config: {path} is not valid JSON: {exc}") from exc
    return parse_config(raw, base_dir=config_path.resolve().parent)
