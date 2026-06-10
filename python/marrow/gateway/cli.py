"""Command-line entry point: ``marrow-gateway <config.json>``.

Point an MCP client's server command at this instead of the real server:

    {"command": "marrow-gateway", "args": ["/path/to/gateway.json"]}

The config names the real server command; the gateway launches it, governs
``tools/call`` traffic, and records a flight-recorder trace.
"""
from __future__ import annotations

import argparse
import os
import sys

from .config import GatewayError, load_config
from .proxy import Gateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="marrow-gateway",
        description="Govern an MCP tool server: policy, budgets, and a flight-recorder trace.",
    )
    parser.add_argument("config", help="path to the gateway config JSON")
    parser.add_argument(
        "--trace", help="override the trace output path from the config", default=None
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except GatewayError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.trace:
        config.trace_path = args.trace
    code = Gateway(config).run()
    # Real MCP clients keep our stdin open for the whole session, so when the
    # upstream exits first the stdin pump thread is still blocked in a read,
    # holding the BufferedReader's lock. Normal interpreter finalization then
    # aborts ("Fatal Python error: _enter_buffered_busy", SIGABRT) instead of
    # propagating the upstream's exit code. The trace is already durably
    # flushed (atomic os.replace) and every client line is flushed at write
    # time, so a hard exit loses nothing.
    if os.name == "posix":
        code &= 0xFF  # exit() semantics: low byte (a signal -N wraps to 256-N)
    elif code >= 1 << 31:
        code -= 1 << 32  # Windows NTSTATUS codes (e.g. 0xC0000005) as a C int
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    raise SystemExit(main())
