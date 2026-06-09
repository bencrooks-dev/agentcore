"""End-to-end: the example's graph compiles + runs to the committed goldens,
proving the full chain with no API key."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO / "examples" / "python_to_ari_compile"


def _load_build_graph():
    spec = importlib.util.spec_from_file_location(
        "_e2e_build_graph", EXAMPLE_DIR / "build_graph.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_graph


def _golden(name: str) -> dict:
    return json.loads((EXAMPLE_DIR / name).read_text(encoding="utf-8"))


def test_ari_matches_golden():
    import marrow.compiler as mc

    ari = mc.compile_to_ari(_load_build_graph()())
    assert ari == _golden("expected_ari.json")


def test_runtime_plan_matches_golden():
    import marrow.compiler as mc

    out = mc.compile_graph(_load_build_graph()())
    assert out["runtime_plan"] == _golden("expected_runtime_plan.json")


def test_trace_matches_golden_modulo_timestamps():
    import marrow.compiler as mc

    out = mc.compile_and_run(_load_build_graph()(), "Hello, Marrow.")
    trace = dict(out["trace"])
    trace["started_at"] = None
    trace["completed_at"] = None
    assert trace == _golden("expected_trace.json")


def test_example_script_runs_and_passes_all_proofs():
    # Run exactly as a user would; no API key in the environment is needed.
    result = subprocess.run(
        [sys.executable, str(EXAMPLE_DIR / "run_runtime_plan.py")],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[FAIL]" not in result.stdout
    assert result.stdout.count("[PASS]") == 7


def test_runtime_plan_is_portable_json():
    plan = _golden("expected_runtime_plan.json")
    # Round-trips through JSON unchanged -> portable across processes/languages.
    assert json.loads(json.dumps(plan)) == plan
