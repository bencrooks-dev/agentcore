"""Provider factory: built-in mock, custom (bring-your-own) types, and clear
errors for unknown/unavailable providers."""
import pytest

from marrow import GenerationResponse, PyProviderBase
from marrow.compiler import (
    AgentGraph,
    AgentNode,
    CompileError,
    ProviderSpec,
    compile_and_run,
)
from marrow.compiler.providers import build_provider


def _binding(provider_type: str) -> dict:
    return {"id": "p", "type": provider_type, "model": "m", "config_ref": None}


def test_build_mock_provider():
    provider = build_provider(_binding("mock"))
    assert provider.name() == "p"


def test_build_provider_custom_factory():
    sentinel = object()
    provider = build_provider(_binding("vllm"), {"vllm": lambda b: sentinel})
    assert provider is sentinel


def test_unknown_provider_type_raises():
    with pytest.raises(CompileError, match="unknown provider type"):
        build_provider(_binding("nope"))


def test_unavailable_provider_sdk_is_reported_clearly():
    def boom(_binding):
        raise ImportError("install with: pip install foo")

    with pytest.raises(CompileError, match="unavailable"):
        build_provider(_binding("foo"), {"foo": boom})


class _FixedProvider(PyProviderBase):
    """A trivial real (non-mock) provider for testing the pluggable path."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def name(self) -> str:
        return "fixed"

    def generate(self, req):  # noqa: ARG002
        resp = GenerationResponse()
        resp.content = self._text
        resp.prompt_tokens = 1
        resp.completion_tokens = 2
        return resp


def test_custom_provider_executes_end_to_end():
    g = AgentGraph(name="custom")
    g.add_provider(ProviderSpec(id="house", type="house-llm", model="h1"))
    g.add_agent(AgentNode(id="a", name="A", provider="house"))
    g.set_entrypoint("a")
    trace = compile_and_run(
        g, "hi", providers={"house-llm": lambda b: _FixedProvider("from the house model")}
    )["trace"]
    assert trace["final_status"] == "completed"
    call = trace["provider_calls"][0]
    assert call["provider"] == "house"
    assert (call["prompt_tokens"], call["completion_tokens"]) == (1, 2)
