"""Command-line entry point: ``marrow-trace <trace.json>`` → an HTML report."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import render_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="marrow-trace",
        description="Render a Marrow trace (compiler or gateway) as a flight-recorder page.",
    )
    parser.add_argument("trace", nargs="?", help="path to a trace JSON file")
    parser.add_argument("-o", "--output", help="output HTML path (default: alongside the trace)")
    parser.add_argument("--open", action="store_true", help="open the report in a browser")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="emit the drop-zone page (no embedded trace) to --output or stdout",
    )
    args = parser.parse_args(argv)

    if args.standalone:
        html = render_html(None)
        if args.output:
            Path(args.output).write_text(html, encoding="utf-8")
            print(args.output)
        else:
            sys.stdout.write(html)
        return 0

    if not args.trace:
        parser.error("a trace file is required (or use --standalone)")
    trace_path = Path(args.trace)
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"marrow-trace: cannot read {trace_path}: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"marrow-trace: {trace_path} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    out = Path(args.output) if args.output else trace_path.with_suffix(".html")
    out.write_text(render_html(trace), encoding="utf-8")
    print(out)
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
