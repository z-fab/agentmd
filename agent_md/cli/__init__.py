"""Agent.md CLI — Typer application entry-point."""

import typer

app = typer.Typer(
    name="agentmd",
    help="Agent.md — Markdown-first agent runtime.",
    no_args_is_help=True,
)

# Register commands (side-effect import)
import agent_md.cli.commands  # noqa: F401, E402
import agent_md.cli.setup  # noqa: F401, E402
