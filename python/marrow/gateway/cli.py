"""Command-line entry point: ``marrow-gateway <config.json>``.

Point an MCP client's server command at this instead of the real server:

    {"command": "marrow-gateway", "args": ["/path/to/gateway.json"]}

The config names the real server command; the gateway launches it, governs
``tools/call`` traffic, and records a flight-recorder trace.
"""
from __future__ import annotations

import argparse
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
    return Gateway(config).run()


if __name__ == "__main__":
    raise SystemExit(main())
