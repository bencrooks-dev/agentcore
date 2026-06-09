"""Policy and budget enforcement primitives.

These are pure, side-effect-free objects so they can be unit-tested without the
runtime. The executor (``execute.py``) drives them: it asks the
:class:`PolicyEngine` whether each action is allowed and feeds provider usage to
the :class:`BudgetMeter`, halting and recording evidence when a policy denies an
action or a budget is exceeded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_MAX_STEPS = 16

# An approver decides whether a ``require_approval`` / ``approval_required``
# action may proceed. It receives (action, checkpoint) and returns a bool.
Approver = Callable[[str, dict], bool]


@dataclass(frozen=True)
class Decision:
    """The outcome of evaluating one policy checkpoint against an action."""

    action: str
    decision: str
    allowed: bool
    approval_required: bool
    evidence_required: bool


class PolicyEngine:
    """Evaluates an action against a plan's policy checkpoints.

    A checkpoint matches an action by exact string or the wildcard ``"*"``.
    ``decision`` of ``"deny"`` blocks the action; ``"require_approval"`` (or
    ``approval_required=True``) blocks it unless an ``approver`` grants it;
    ``"allow"`` permits it. With no approver, any action needing approval is
    denied (fail-closed).
    """

    def __init__(self, checkpoints: list[dict], approver: Approver | None = None) -> None:
        self._by_action: dict[str, list[dict]] = {}
        for checkpoint in checkpoints:
            self._by_action.setdefault(checkpoint["action"], []).append(checkpoint)
        self._approver = approver

    def has_checkpoints(self) -> bool:
        return bool(self._by_action)

    def evaluate(self, action: str) -> list[Decision]:
        matches = list(self._by_action.get(action, []))
        if action != "*":
            matches.extend(self._by_action.get("*", []))

        decisions: list[Decision] = []
        for checkpoint in matches:
            verdict = checkpoint["decision"]
            approval_required = bool(checkpoint.get("approval_required", False))
            needs_approval = verdict == "require_approval" or approval_required
            if verdict == "deny":
                allowed = False
            elif needs_approval:
                allowed = (
                    bool(self._approver(action, checkpoint))
                    if self._approver is not None
                    else False
                )
            else:
                allowed = True
            decisions.append(
                Decision(
                    action=action,
                    decision=verdict,
                    allowed=allowed,
                    approval_required=approval_required,
                    evidence_required=bool(checkpoint.get("evidence_required", False)),
                )
            )
        return decisions


class BudgetMeter:
    """Tracks step / token / cost consumption against a plan budget.

    A ``None`` budget bounds the loop at :data:`DEFAULT_MAX_STEPS` with no token
    or cost cap. ``pricing`` maps a model name to ``(prompt_rate, completion_rate)``
    per token; models absent from it contribute zero cost (the mock provider has
    no price).
    """

    def __init__(
        self,
        budget: dict[str, Any] | None,
        pricing: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.max_steps = budget["max_steps"] if budget else DEFAULT_MAX_STEPS
        self.max_tokens = budget.get("max_tokens") if budget else None
        self.max_cost_usd = budget.get("max_cost_usd") if budget else None
        self._pricing = pricing if pricing is not None else {}
        self.steps = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0

    def can_start_step(self) -> bool:
        return self.steps < self.max_steps

    def record_step(self) -> None:
        self.steps += 1

    def record_provider_usage(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        rate = self._pricing.get(model)
        if rate is not None:
            prompt_rate, completion_rate = rate
            self.cost_usd += prompt_tokens * prompt_rate
            self.cost_usd += completion_tokens * completion_rate

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def over_tokens(self) -> bool:
        return self.max_tokens is not None and self.total_tokens > self.max_tokens

    def over_cost(self) -> bool:
        return self.max_cost_usd is not None and self.cost_usd > self.max_cost_usd

    def usage(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 10),
        }
