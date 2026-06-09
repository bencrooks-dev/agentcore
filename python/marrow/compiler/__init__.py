"""Marrow compiler: lower a declaratively-defined agent system to a RuntimePlan.

The compiler turns an :class:`AgentGraph` (authored in Python) into an ARI
manifest, lowers that into a deterministic RuntimePlan, and executes the plan
through the existing native runtime, emitting a portable ExecutionTrace. It
compiles agent graphs and their tool/provider/policy contracts — not arbitrary
Python.

See ``docs/compiler_architecture.md`` for the design. This is a draft layer;
the ARI manifests it produces are not normative ARI 0.1 (see
``ari/spec/README.md``).
"""
from __future__ import annotations

from .ari_emit import canonical_json, compile_to_ari, graph_id
from .compile import compile_and_run, compile_graph
from .deploy import make_deployment_manifest
from .errors import CompileError
from .execute import run_runtime_plan
from .governance import Approver
from .graph import (
    AgentGraph,
    AgentNode,
    BudgetSpec,
    Edge,
    FailureSemantics,
    PolicySpec,
    ProviderSpec,
    RollbackStep,
    ToolSpec,
    always,
    contains,
)
from .providers import ProviderFactory
from .replay import normalize_trace, replay, traces_equivalent
from .runtime_plan import ari_to_runtime_plan, load_runtime_plan, runtime_plan_id

__all__ = [
    "AgentGraph",
    "AgentNode",
    "ToolSpec",
    "ProviderSpec",
    "Edge",
    "PolicySpec",
    "BudgetSpec",
    "FailureSemantics",
    "RollbackStep",
    "always",
    "contains",
    "compile_to_ari",
    "graph_id",
    "canonical_json",
    "ari_to_runtime_plan",
    "runtime_plan_id",
    "load_runtime_plan",
    "run_runtime_plan",
    "compile_graph",
    "compile_and_run",
    "replay",
    "traces_equivalent",
    "normalize_trace",
    "make_deployment_manifest",
    "Approver",
    "ProviderFactory",
    "CompileError",
]
