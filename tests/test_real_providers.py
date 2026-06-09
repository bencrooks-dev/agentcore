"""Contract tests for the built-in real providers, using injected fake clients —
no network, no API key. They verify each provider maps its SDK's response shape
(content + token counts) into a GenerationResponse. Skipped when the SDK is absent."""
import types

import pytest

from marrow import GenerationRequest, Message, Role


def _req(text: str = "hi") -> GenerationRequest:
    req = GenerationRequest()
    req.messages = [Message.make(Role.User, text)]
    return req


def test_openai_provider_maps_response():
    pytest.importorskip("openai")
    from marrow.providers import OpenAIProvider

    captured: dict = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = types.SimpleNamespace(content="hello from openai")
            choice = types.SimpleNamespace(message=message)
            usage = types.SimpleNamespace(prompt_tokens=11, completion_tokens=7)
            return types.SimpleNamespace(choices=[choice], usage=usage)

    fake = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_Completions())
    )
    provider = OpenAIProvider(model="gpt-4o-mini", client=fake)
    resp = provider.generate(_req())
    assert resp.content == "hello from openai"
    assert (resp.prompt_tokens, resp.completion_tokens) == (11, 7)
    assert captured["model"] == "gpt-4o-mini"
    assert provider.name() == "openai:gpt-4o-mini"


def test_anthropic_provider_maps_response():
    pytest.importorskip("anthropic")
    from marrow.providers import AnthropicProvider

    class _Messages:
        def create(self, **kwargs):
            block = types.SimpleNamespace(type="text", text="hello from claude")
            usage = types.SimpleNamespace(input_tokens=13, output_tokens=5)
            return types.SimpleNamespace(content=[block], usage=usage)

    fake = types.SimpleNamespace(messages=_Messages())
    provider = AnthropicProvider(model="claude-sonnet-4-6", client=fake)
    resp = provider.generate(_req())
    assert resp.content == "hello from claude"
    assert (resp.prompt_tokens, resp.completion_tokens) == (13, 5)
    assert provider.name() == "anthropic:claude-sonnet-4-6"


def test_ollama_provider_maps_response():
    pytest.importorskip("httpx")
    from marrow.providers import OllamaProvider

    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {"content": "hello from ollama"},
                "prompt_eval_count": 9,
                "eval_count": 4,
            }

    class _Client:
        def post(self, url, **kwargs):  # noqa: ARG002
            return _Response()

    provider = OllamaProvider(model="llama3.2")
    provider._client = _Client()
    resp = provider.generate(_req())
    assert resp.content == "hello from ollama"
    assert (resp.prompt_tokens, resp.completion_tokens) == (9, 4)
    assert provider.name() == "ollama:llama3.2"
