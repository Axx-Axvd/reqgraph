"""Terminal output -> SVG for the README (rich is installed with typer; no new dependency).

    uv run python scripts/terminal_svg.py <text file> <out.svg> --title "reqgraph run"

The text is the real output of a command saved to a file; nothing is drawn by hand.
"""

import argparse
import io
from pathlib import Path

from rich.console import Console
from rich.text import Text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--title", default="reqgraph")
    parser.add_argument("--width", type=int, default=104)
    args = parser.parse_args()
    console = Console(record=True, width=args.width, file=io.StringIO())
    for line in args.source.read_text(encoding="utf-8").splitlines():
        style = "bold cyan" if line.startswith("→") else "green" if line.startswith("$") else ""
        console.print(Text(line, style=style))
    svg = console.export_svg(title=args.title)
    lines = (line.rstrip() for line in svg.splitlines())  # rich pads lines; pre-commit trims them
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"записано: {args.out}")


if __name__ == "__main__":
    main()
