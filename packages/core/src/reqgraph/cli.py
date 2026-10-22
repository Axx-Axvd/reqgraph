"""Command-line entry point: ``reqgraph``."""

from typing import Annotated

import typer

from reqgraph import __version__

app = typer.Typer(name="reqgraph", no_args_is_help=True, add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"reqgraph {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """reqgraph: interview -> requirements -> models as code -> CI -> SRS and TZ."""


if __name__ == "__main__":
    app()
