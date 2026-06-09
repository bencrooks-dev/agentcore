"""Provider construction for the executor.

Maps a ProviderSpec ``type`` to a concrete provider. ``mock``/``echo`` are the
keyless default; ``openai`` / ``anthropic`` / ``ollama`` are the built-in real
providers (constructed lazily, so importing the compiler never requires their
SDKs); and callers can register their own types via the ``providers=`` argument
to :func:`run_runtime_plan` — the extension point for bringing your own model.
"""
from __future__ import annotations

from typing import Any, Callable

from .. import _marrow as _c
from .errors import CompileError

# A factory builds a provider from a binding dict {id, type, model, config_ref}.
ProviderFactory = Callable[[dict], Any]


def _build_mock(binding: dict) -> Any:
    return _c.MockProvider(binding["id"])


def _build_openai(binding: dict) -> Any:
    from .. import providers as _providers

    return _providers.OpenAIProvider(model=binding["model"])


def _build_anthropic(binding: dict) -> Any:
    from .. import providers as _providers

    return _providers.AnthropicProvider(model=binding["model"])


def _build_ollama(binding: dict) -> Any:
    from .. import providers as _providers

    return _providers.OllamaProvider(model=binding["model"])


_BUILTIN: dict[str, ProviderFactory] = {
    "mock": _build_mock,
    "echo": _build_mock,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "ollama": _build_ollama,
}


def build_provider(binding: dict, extra: dict[str, ProviderFactory] | None = None) -> Any:
    """Construct a provider for ``binding``.

    ``extra`` maps custom type names to factories and overrides the built-ins.
    Raises :class:`CompileError` for an unknown type or an unavailable built-in
    (e.g. a real provider whose SDK is not installed), with an actionable message.
    """
    factories = dict(_BUILTIN)
    if extra:
        factories.update(extra)

    provider_type = binding["type"]
    factory = factories.get(provider_type)
    if factory is None:
        raise CompileError(
            f"unknown provider type {provider_type!r} for provider {binding['id']!r}; "
            f"known types: {sorted(factories)} "
            "(pass providers={type: factory} to register a custom one)"
        )
    try:
        return factory(binding)
    except ImportError as exc:
        raise CompileError(
            f"provider {binding['id']!r} of type {provider_type!r} is unavailable: {exc}"
        ) from exc
