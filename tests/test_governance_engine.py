"""Unit tests for the PolicyEngine and BudgetMeter (no runtime needed)."""
import time

from marrow.compiler.governance import BudgetMeter, PolicyEngine


def cp(action, decision="allow", approval_required=False, evidence_required=False):
    return {
        "id": "p",
        "action": action,
        "decision": decision,
        "approval_required": approval_required,
        "evidence_required": evidence_required,
    }


# --- PolicyEngine ------------------------------------------------------------


def test_allow_decision():
    eng = PolicyEngine([cp("provider:mock", "allow")])
    [d] = eng.evaluate("provider:mock")
    assert d.allowed is True and d.decision == "allow"


def test_deny_decision_blocks():
    eng = PolicyEngine([cp("tool:dangerous", "deny")])
    [d] = eng.evaluate("tool:dangerous")
    assert d.allowed is False


def test_require_approval_without_approver_is_denied():
    eng = PolicyEngine([cp("tool:wire_funds", "require_approval")])
    [d] = eng.evaluate("tool:wire_funds")
    assert d.allowed is False  # fail-closed


def test_require_approval_with_granting_approver():
    eng = PolicyEngine([cp("tool:wire_funds", "require_approval")], approver=lambda a, c: True)
    [d] = eng.evaluate("tool:wire_funds")
    assert d.allowed is True


def test_approval_required_flag_gates_even_when_decision_allow():
    eng = PolicyEngine([cp("agent:a", "allow", approval_required=True)])
    [d] = eng.evaluate("agent:a")
    assert d.allowed is False


def test_wildcard_matches_any_action():
    eng = PolicyEngine([cp("*", "deny")])
    assert eng.evaluate("provider:mock")[0].allowed is False
    assert eng.evaluate("tool:anything")[0].allowed is False


def test_unmatched_action_yields_no_decisions():
    eng = PolicyEngine([cp("provider:mock")])
    assert eng.evaluate("tool:echo") == []


def test_unknown_decision_fails_closed():
    # A malformed verdict (the validated pipeline forbids this) must not pass.
    eng = PolicyEngine([cp("provider:mock", "block")])
    [d] = eng.evaluate("provider:mock")
    assert d.allowed is False


def test_evidence_required_flag_is_surfaced():
    eng = PolicyEngine([cp("provider:mock", "allow", evidence_required=True)])
    [d] = eng.evaluate("provider:mock")
    assert d.evidence_required is True


# --- BudgetMeter -------------------------------------------------------------


def test_default_budget_bounds_steps():
    meter = BudgetMeter(None)
    assert meter.max_steps == 16
    assert meter.max_tokens is None


def test_step_limit():
    meter = BudgetMeter({"max_steps": 2, "max_tokens": None, "max_cost_usd": None})
    assert meter.can_start_step()
    meter.record_step()
    meter.record_step()
    assert not meter.can_start_step()


def test_token_cap():
    meter = BudgetMeter({"max_steps": 10, "max_tokens": 5, "max_cost_usd": None})
    meter.record_provider_usage("mock-echo", 3, 1)
    assert not meter.over_tokens()
    meter.record_provider_usage("mock-echo", 2, 0)
    assert meter.over_tokens()


def test_cost_cap_with_pricing():
    pricing = {"gpt": (0.001, 0.002)}  # per token
    meter = BudgetMeter(
        {"max_steps": 10, "max_tokens": None, "max_cost_usd": 0.01}, pricing=pricing
    )
    meter.record_provider_usage("gpt", 10, 0)  # 0.01 — at limit, not over
    assert not meter.over_cost()
    meter.record_provider_usage("gpt", 1, 0)  # now 0.011 — over
    assert meter.over_cost()


def test_mock_model_has_zero_cost():
    meter = BudgetMeter({"max_steps": 10, "max_tokens": None, "max_cost_usd": 0.0})
    meter.record_provider_usage("mock-echo", 100, 100)
    assert meter.cost_usd == 0.0
    assert not meter.over_cost()


def test_wall_clock_budget_trips():
    meter = BudgetMeter(
        {"max_steps": 10, "max_tokens": None, "max_cost_usd": None, "max_wall_ms": 1}
    )
    assert not meter.over_wall()  # not yet
    time.sleep(0.01)  # 10ms > 1ms
    assert meter.over_wall()


def test_no_wall_budget_is_never_over():
    meter = BudgetMeter(None)
    assert meter.max_wall_ms is None
    assert not meter.over_wall()


def test_usage_dict_shape():
    meter = BudgetMeter(None)
    meter.record_step()
    meter.record_provider_usage("mock-echo", 3, 7)
    usage = meter.usage()
    assert usage == {
        "steps": 1,
        "prompt_tokens": 3,
        "completion_tokens": 7,
        "total_tokens": 10,
        "cost_usd": 0.0,
    }
