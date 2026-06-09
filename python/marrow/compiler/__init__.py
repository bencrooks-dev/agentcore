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

from .errors import CompileError

__all__ = ["CompileError"]
