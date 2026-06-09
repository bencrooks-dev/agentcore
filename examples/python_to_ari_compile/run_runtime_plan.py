"""End-to-end compile + run, with the seven properties this proves.

Pipeline:  Python agent graph -> ARI manifest -> RuntimePlan -> execute through
the native runtime -> ExecutionTrace. Mock provider only; no API key.

Run:  python examples/python_to_ari_compile/run_runtime_plan.py
Exits non-zero if any proof check fails.
"""
import json

from build_graph import build_graph

import marrow.compiler as mc

INPUT = "Hello, Marrow."


def main() -> int:
    graph = build_graph()                       # 1. Python agent graph
    ari = mc.compile_to_ari(graph)              # 2. graph -> ARI
    plan = mc.ari_to_runtime_plan(ari)          # 3. ARI -> RuntimePlan
    trace = mc.run_runtime_plan(plan, INPUT)    # 4./5. execute -> ExecutionTrace

    print("=== ARI manifest ===")
    print(json.dumps(ari, indent=2))
    print("\n=== RuntimePlan ===")
    print(json.dumps(plan, indent=2))
    print("\n=== ExecutionTrace ===")
    print(json.dumps(trace, indent=2))

    checks = {
        "1. a Python-defined agent graph can be created":
            graph.name == "echo_agent" and len(graph.agents) == 1,
        "2. the graph can compile to ARI":
            ari["version"].startswith("ari/") and ari["entrypoint"] == "agent_1",
        "3. ARI can compile to a RuntimePlan":
            plan["runtime_plan_id"].startswith("rp_"),
        "4. the RuntimePlan executes through Marrow":
            trace["runtime_plan_id"] == plan["runtime_plan_id"],
        "5. an ExecutionTrace is emitted":
            trace["final_status"] == "completed" and len(trace["events"]) >= 1,
        "6. the RuntimePlan is portable JSON":
            json.loads(json.dumps(plan)) == plan,
        "7. no external API key is required":
            all(b["type"] == "mock" for b in plan["provider_bindings"].values()),
    }

    print("\n=== Proof ===")
    ok = True
    for label, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
