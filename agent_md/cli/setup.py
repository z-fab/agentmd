"""Setup wizard, config display, and update commands for Agent.md."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
import typer
from rich.prompt import Confirm, Prompt
from rich.table import Table

from agent_md.cli import app
from agent_md.cli.theme import console, make_panel, print_error, print_success

PROVIDERS = {
    "google": {"env_var": "GOOGLE_API_KEY", "default_model": "gemini-2.5-flash"},
    "openai": {"env_var": "OPENAI_API_KEY", "default_model": "gpt-4o"},
    "anthropic": {"env_var": "ANTHROPIC_API_KEY", "default_model": "claude-sonnet-4-20250514"},
    "ollama": {"env_var": None, "default_model": "llama3"},
}


def _default_workspace() -> Path:
    """Return default workspace path (always ~/agentmd)."""
    return Path.home() / "agentmd"


def _get_config_dir() -> Path:
    """Get the config directory (~/.config/agentmd)."""
    config_dir = Path.home() / ".config" / "agentmd"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _write_config_yaml(workspace: Path, provider: str, model: str, defaults: dict | None = None):
    """Write config.yaml to ~/.config/agentmd/config.yaml."""
    config = {
        "workspace": str(workspace),
        "agents_dir": "agents",
        "defaults": {
            "provider": provider,
            "model": model,
        },
        "log_level": "INFO",
    }
    if defaults:
        config["defaults"].update(defaults)

    config_path = _get_config_dir() / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


def _build_env_content(api_key: str | None, env_var: str | None) -> str:
    """Build .env file content."""
    lines = ["# Agent.md — API Keys"]
    if api_key and env_var:
        lines.append(f"{env_var}={api_key}")
    else:
        lines.append("# GOOGLE_API_KEY=...")
        lines.append("# OPENAI_API_KEY=sk-...")
        lines.append("# ANTHROPIC_API_KEY=sk-ant-...")
    return "\n".join(lines) + "\n"


def _write_env_file(workspace: Path, api_key: str | None, env_var: str | None):
    """Write .env to both workspace _config and global config dir."""
    content = _build_env_content(api_key, env_var)

    # Workspace-specific
    ws_env = workspace / "agents" / "_config" / ".env"
    ws_env.parent.mkdir(parents=True, exist_ok=True)
    ws_env.write_text(content)

    # Global fallback
    global_env = _get_config_dir() / ".env"
    global_env.write_text(content)

    return ws_env, global_env


def _create_workspace(workspace: Path, provider: str, model: str):
    """Create workspace directory structure, hello-world agent, and MCP config."""
    agents_dir = workspace / "agents"
    config_dir = agents_dir / "_config"
    tools_dir = config_dir / "tools"
    skills_dir = config_dir / "skills"

    for d in (agents_dir, config_dir, tools_dir, skills_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Hello-world agent
    hello = agents_dir / "hello-world.md"
    if not hello.exists():
        hello.write_text(
            "---\n"
            "name: hello-world\n"
            "description: A friendly greeting agent\n"
            "paths:\n"
            "  output: output\n"
            "---\n"
            "\n"
            "You are a friendly assistant. Write a creative greeting\n"
            "and save it to {output}/greeting.txt using file_write.\n"
        )

    # Empty MCP config
    mcp = config_dir / "mcp-servers.json"
    if not mcp.exists():
        mcp.write_text("{}\n")


def _build_config_panel():
    """Build a Rich Panel showing the current effective configuration."""
    from agent_md.config.settings import Settings, _ensure_default_config, _find_env_files

    config_yaml = _ensure_default_config()
    env_files = _find_env_files()
    env_file = env_files[-1] if env_files else None

    # Reload settings fresh
    current = Settings()

    workspace = current.workspace or str(Path.home() / "agentmd")
    ws_path = Path(workspace).expanduser().resolve()

    # Detect which providers have keys
    providers = []
    if current.GOOGLE_API_KEY:
        providers.append("google")
    if current.OPENAI_API_KEY:
        providers.append("openai")
    if current.ANTHROPIC_API_KEY:
        providers.append("anthropic")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Config file", str(config_yaml) if config_yaml else "[yellow]not found[/]")
    table.add_row("Env file", str(Path(env_file).resolve()) if env_file else "[yellow]not found[/]")
    table.add_row("Workspace", str(ws_path))
    table.add_row("Default model", f"{current.defaults_provider} / {current.defaults_model}")
    table.add_row("API keys", ", ".join(providers) if providers else "[yellow]none configured[/]")

    return make_panel(table, title="Agent.md Configuration")


@app.command(name="info")
def info():
    """Show current effective configuration."""
    from agent_md import __version__
    from agent_md.cli.theme import print_banner

    console.print()
    print_banner(__version__)
    console.print()
    console.print(_build_config_panel())
    console.print()


@app.command()
def setup(
    reconfigure: bool = typer.Option(False, "--reconfigure", "-r", help="Force reconfiguration even if already set up"),
):
    """Interactive setup wizard for Agent.md."""
    from agent_md import __version__
    from agent_md.config.settings import _get_config_path

    console.print()
    console.print(
        make_panel(
            f"[bold]Agent.md[/bold] v{__version__}\nMarkdown-first agent runtime",
            title="Setup Wizard",
        )
    )

    # Check for existing setup
    existing_config = _get_config_path().exists()
    if existing_config and not reconfigure:
        console.print(f"\n[green]Existing configuration found:[/] {_get_config_path()}")
        if not Confirm.ask("Do you want to reconfigure?", default=False):
            console.print("\n[green]Setup complete![/] Your configuration is already in place.")
            raise typer.Exit()

    # 1. Workspace
    console.print("\n  [bold]1/4 · Workspace[/bold]")
    default_ws = _default_workspace()
    workspace_input = Prompt.ask("  Workspace directory", default=str(default_ws))
    workspace = Path(workspace_input).expanduser().resolve()

    # 2. Provider + Model
    console.print("\n  [bold]2/4 · Model[/bold]")
    provider = Prompt.ask(
        "  LLM Provider",
        choices=list(PROVIDERS.keys()),
        default="google",
    )

    default_model = PROVIDERS[provider]["default_model"]
    model = Prompt.ask("  Model", default=default_model)

    # 3. API Key
    console.print("\n  [bold]3/4 · API Key[/bold]")
    api_key = None
    env_var = PROVIDERS[provider]["env_var"]
    if env_var:
        existing_key = os.environ.get(env_var, "")
        if existing_key:
            masked = existing_key[:4] + "..." + existing_key[-4:] if len(existing_key) > 8 else "****"
            console.print(f"  Found existing {env_var}: {masked}")
            if not Confirm.ask("  Use this key?", default=True):
                api_key = Prompt.ask(f"  {env_var}", password=True)
            else:
                api_key = existing_key
        else:
            api_key = Prompt.ask(f"  {env_var}", password=True)
    else:
        console.print("  No API key needed for ollama")

    # 4. Defaults (optional)
    console.print("\n  [bold]4/4 · Defaults[/bold] [dim](press Enter to keep defaults)[/dim]")

    console.print("  [dim]LLM settings[/dim]")
    temperature_str = Prompt.ask("  Temperature", default="0.7")
    max_tokens_str = Prompt.ask("  Max tokens per response", default="4096")

    console.print("  [dim]Execution limits[/dim]")
    timeout_str = Prompt.ask("  Timeout (seconds)", default="300")
    max_tool_calls_str = Prompt.ask("  Max tool calls per run", default="50")
    max_exec_tokens_str = Prompt.ask("  Max total tokens per run", default="500000")
    max_cost_str = Prompt.ask("  Max cost per run (USD, empty=no limit)", default="")
    loop_detection_str = Prompt.ask("  Loop detection", choices=["true", "false"], default="true")

    console.print("  [dim]Agent defaults[/dim]")
    history_str = Prompt.ask("  History level", choices=["low", "medium", "high", "off"], default="low")

    extra_defaults = {}

    def _set_if_changed(key, value_str, default, converter=int):
        try:
            val = converter(value_str)
            if val != default:
                extra_defaults[key] = val
        except (ValueError, TypeError):
            pass

    _set_if_changed("temperature", temperature_str, 0.7, float)
    _set_if_changed("max_tokens", max_tokens_str, 4096, int)
    _set_if_changed("timeout", timeout_str, 300, int)
    _set_if_changed("max_tool_calls", max_tool_calls_str, 50, int)
    _set_if_changed("max_execution_tokens", max_exec_tokens_str, 500_000, int)

    if max_cost_str.strip():
        try:
            extra_defaults["max_cost_usd"] = float(max_cost_str)
        except ValueError:
            pass

    if loop_detection_str == "false":
        extra_defaults["loop_detection"] = False

    if history_str != "low":
        extra_defaults["history"] = history_str

    # --- Apply configuration ---
    console.print("\n[bold]Applying configuration...[/]\n")

    # Create workspace structure
    _create_workspace(workspace, provider, model)
    console.print(f"  Workspace created at {workspace}")

    # Write config.yaml
    _write_config_yaml(workspace, provider, model, extra_defaults or None)
    config_path = _get_config_dir() / "config.yaml"
    console.print(f"  Config written to {config_path}")

    # Write .env (secrets to both locations)
    ws_env, global_env = _write_env_file(workspace, api_key, env_var)
    console.print(f"  Secrets written to {ws_env}")

    # Summary
    console.print(
        make_panel(
            "\n".join(
                [
                    f"[bold]Workspace:[/]     {workspace}",
                    f"[bold]Provider:[/]      {provider}",
                    f"[bold]Model:[/]         {model}",
                    f"[bold]Config:[/]        {config_path}",
                    f"[bold]Secrets:[/]       {ws_env}",
                    "",
                    "[bold]Next steps:[/]",
                    "  agentmd new my-first-agent  — Create your first agent",
                    "  agentmd start               — Start the backend",
                    "  agentmd info                — Show current configuration",
                ]
            ),
            title="Setup Complete",
        )
    )


@app.command()
def update():
    """Update Agent.md to the latest version."""
    from agent_md import __version__

    console.print(f"\n[bold]Current version:[/] {__version__}\n")

    REPO = "https://github.com/z-fab/agentmd.git"

    if shutil.which("uv"):
        console.print("Updating via uv...")
        result = subprocess.run(
            ["uv", "tool", "install", f"agentmd[all] @ git+{REPO}", "--force", "--python", "3.13"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print_success(result.stdout.strip() or "Update complete!")
        else:
            print_error(f"Update failed: {result.stderr.strip()}")
            raise typer.Exit(1)
    elif shutil.which("pip"):
        console.print("uv not found, trying pip...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "agentmd[all]"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print_success("Update complete!")
        else:
            print_error(f"Update failed: {result.stderr.strip()}")
            raise typer.Exit(1)
    else:
        print_error("Neither uv nor pip found.", "Install uv: https://docs.astral.sh/uv/")
        raise typer.Exit(1)
