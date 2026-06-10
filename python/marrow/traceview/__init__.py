"""Flight recorder: render a Marrow trace as a self-contained HTML page.

Works on both trace kinds — the compiler's ``ExecutionTrace`` and the MCP
gateway's trace. ``render_html(trace)`` embeds the data; ``render_html(None)``
produces the standalone drop-zone page (everything renders locally in the
browser; nothing is uploaded anywhere).
"""
from __future__ import annotations

import json
from typing import Any

from .template import TEMPLATE

_PLACEHOLDER = "__MARROW_TRACE_JSON__"


def render_html(trace: dict[str, Any] | None) -> str:
    """Return the flight-recorder page with ``trace`` embedded (or the
    drop-zone page when ``trace`` is None)."""
    if trace is None:
        payload = "null"
    else:
        # "</" must not appear inside a <script> block; escape it in strings.
        payload = json.dumps(trace, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace(_PLACEHOLDER, payload, 1)


__all__ = ["render_html"]
