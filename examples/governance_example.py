"""Governance: policy enforcement, budgets, evidence, and rollback — mock only.

The same governed graph is run twice: once with no approver (the provider call
needs approval, so the policy fails closed, the run is denied, and the agent's
state is rolled back), and once with an approver that grants it (the run
completes, the approval is recorded as evidence, and the budget is tracked). A
DeploymentManifest is produced from the compiled plan.

Run:  python examples/governance_example.py
"""
import json

from marrow.compiler import (
    AgentGraph,
    AgentNode,
    BudgetSpec,
    PolicySpec,
    ProviderSpec,
    ToolSpec,
    compile_and_run,
    make_deployment_manifest,
)


def build_graph() -> AgentGraph:
    g = AgentGraph(name="governed_agent")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(ToolSpec(name="echo", description="Echo input text"))
    g.add_agent(
        AgentNode(
            id="agent_1",
            name="Echo Agent",
            provider="mock",
            system_prompt="You are a governed echo agent.",
            tools=["echo"],
        )
    )
    g.set_entrypoint("agent_1")
    g.add_policy(
        PolicySpec(
            id="approve_provider",
            action="provider:mock",
            decision="require_approval",
            evidence_required=True,
        )
    )
    g.set_budget(BudgetSpec(max_steps=4, max_tokens=10_000, max_cost_usd=1.0))
    g.add_rollback_step("agent_1", "clear_state")
    return g


def main() -> int:
    graph = build_graph()

    print("=== Run WITHOUT an approver (policy fails closed) ===")
    denied = compile_and_run(graph, "transfer funds")["trace"]
    denied_events = [e["type"] for e in denied["events"]]
    print(f"final_status : {denied['final_status']}")
    print(f"policy       : {json.dumps(denied['policy_decisions'])}")
    print(f"rolled back  : {'rollback_started' in denied_events}")

    print("\n=== Run WITH an approver that grants ===")
    out = compile_and_run(graph, "summarize the report", approver=lambda action, cp: True)
    trace = out["trace"]
    print(f"final_status : {trace['final_status']}")
    print(f"policy       : {json.dumps(trace['policy_decisions'])}")
    print(f"budget_usage : {json.dumps(trace['budget_usage'])}")

    print("\n=== DeploymentManifest ===")
    manifest = make_deployment_manifest(out["runtime_plan"], target="edge", replicas=2)
    print(json.dumps(manifest, indent=2))

    checks = {
        "policy denies without approver": denied["final_status"] == "denied",
        "rollback ran on denial": "rollback_started" in denied_events,
        "approver allows the run": trace["final_status"] == "completed",
        "evidence recorded": any(
            d["action"] == "provider:mock" for d in trace["policy_decisions"]
        ),
        "budget tracked": trace["budget_usage"]["steps"] >= 1,
        "deployment references the plan": manifest["runtime_plan_id"]
        == out["runtime_plan"]["runtime_plan_id"],
        "no API key required": all(
            b["type"] == "mock" for b in out["runtime_plan"]["provider_bindings"].values()
        ),
    }
    print("\n=== Proof ===")
    ok = True
    for label, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
