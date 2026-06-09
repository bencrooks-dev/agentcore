"""Replay determinism and deployment-manifest generation."""
import subprocess
import sys
from pathlib import Path

import pytest

from marrow.compiler import (
    AgentGraph,
    AgentNode,
    CompileError,
    ProviderSpec,
    ToolSpec,
    ari_to_runtime_plan,
    compile_and_run,
    compile_graph,
    compile_to_ari,
    make_deployment_manifest,
    replay,
    traces_equivalent,
)
from marrow.compiler.validate import validate


def echo_graph() -> AgentGraph:
    g = AgentGraph(name="echo_agent")
    g.add_provider(ProviderSpec(id="mock", type="mock", model="mock-echo"))
    g.add_tool(ToolSpec(name="echo", description="Echo"))
    g.add_agent(AgentNode(id="agent_1", name="A", provider="mock", tools=["echo"]))
    g.set_entrypoint("agent_1")
    return g


def echo_plan() -> dict:
    return ari_to_runtime_plan(compile_to_ari(echo_graph()))


# --- replay ------------------------------------------------------------------


def test_replay_reproduces_trace():
    first = compile_and_run(echo_graph(), "same input")["trace"]
    second = replay(echo_plan(), "same input")
    assert first["trace_id"] == second["trace_id"]
    assert traces_equivalent(first, second)


def test_replay_differs_for_different_input():
    a = replay(echo_plan(), "one")
    b = replay(echo_plan(), "two")
    assert not traces_equivalent(a, b)
    assert a["trace_id"] != b["trace_id"]


# --- deployment manifest -----------------------------------------------------


def test_deployment_manifest_from_plan():
    plan = compile_graph(echo_graph())["runtime_plan"]
    manifest = make_deployment_manifest(plan, target="edge", replicas=3)
    validate(manifest, "deployment_manifest.schema.json")
    assert manifest["runtime_plan_id"] == plan["runtime_plan_id"]
    assert manifest["target"] == "edge"
    assert manifest["replicas"] == 3
    assert manifest["name"] == "echo_agent"


def test_deployment_manifest_defaults():
    manifest = make_deployment_manifest(compile_graph(echo_graph())["runtime_plan"])
    assert manifest["target"] == "local"
    assert "replicas" not in manifest


def test_deployment_manifest_requires_plan_id():
    with pytest.raises(CompileError, match="runtime_plan_id"):
        make_deployment_manifest({"name": "x"})


# --- governance example ------------------------------------------------------


def test_governance_example_runs_and_passes():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo / "examples" / "governance_example.py")],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[FAIL]" not in result.stdout
    assert result.stdout.count("[PASS]") == 7
