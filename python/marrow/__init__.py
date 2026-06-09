"""marrow — lightweight C++ core for AI agent orchestration."""

from . import _marrow as _c
from . import compiler, logging_config, policy, providers, state_store, tracing, usage
from .asyncio_bridge import AsyncAgent, AsyncRuntime, to_thread
from .graph import Graph, GraphExhausted, GraphResult
from .graph import run as run_graph
from .policy import RateLimiter, RetryPolicy
from .sdk import Agent, CancelToken, MockProvider, OverflowPolicy, PyProviderBase, Runtime
from .state_store import InMemoryStateStore, SQLiteStateStore, StateStore, restore_into
from .tools import ToolBox, tool
from .tracing import NullTraceSink, OpenTelemetryTraceSink, PrintTraceSink, TraceSink
from .usage import UsageRecord, UsageTracker

Role = _c.Role
Message = _c.Message
GenerationRequest = _c.GenerationRequest
GenerationResponse = _c.GenerationResponse

__all__ = [
    # core
    "Agent",
    "Runtime",
    "MockProvider",
    "PyProviderBase",
    "Role",
    "Message",
    "GenerationRequest",
    "GenerationResponse",
    "CancelToken",
    "OverflowPolicy",
    # tools
    "tool",
    "ToolBox",
    # graphs
    "Graph",
    "GraphResult",
    "GraphExhausted",
    "run_graph",
    # async
    "AsyncAgent",
    "AsyncRuntime",
    "to_thread",
    # policy
    "RateLimiter",
    "RetryPolicy",
    # persistence
    "StateStore",
    "InMemoryStateStore",
    "SQLiteStateStore",
    "restore_into",
    # tracing
    "TraceSink",
    "NullTraceSink",
    "PrintTraceSink",
    "OpenTelemetryTraceSink",
    # usage
    "UsageRecord",
    "UsageTracker",
    # submodules
    "providers",
    "logging_config",
    "policy",
    "state_store",
    "tracing",
    "usage",
    "compiler",
]

__version__ = "0.1.0rc1"
