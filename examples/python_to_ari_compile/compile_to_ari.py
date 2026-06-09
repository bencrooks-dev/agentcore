"""Compile the echo graph to an ARI manifest and print it as JSON."""
import json

from build_graph import build_graph

import marrow.compiler as mc


def main() -> None:
    ari = mc.compile_to_ari(build_graph())
    print(json.dumps(ari, indent=2))


if __name__ == "__main__":
    main()
