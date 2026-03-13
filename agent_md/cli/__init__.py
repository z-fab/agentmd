"""Agent.md CLI — Typer application entry-point."""

import logging

import typer
from rich.logging import RichHandler

app = typer.Typer(
    name="agentmd",
    help="Agent.md — Markdown-first agent runtime.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)


@app.callback()
def _cli_main(
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output except errors", is_eager=True),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug output", is_eager=True),
) -> None:
    """Agent.md — Markdown-first agent runtime."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )


# Register commands (side-effect import)
import agent_md.cli.commands  # noqa: F401, E402
import agent_md.cli.setup  # noqa: F401, E402
