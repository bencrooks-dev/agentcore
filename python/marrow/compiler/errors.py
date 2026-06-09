"""Compiler error type.

The compiler favors precise, human-readable diagnostics over stack traces: every
validation failure raises :class:`CompileError` with a message that says what was
wrong and where.
"""
from __future__ import annotations


class CompileError(Exception):
    """Raised when a graph, ARI manifest, or RuntimePlan is invalid."""
