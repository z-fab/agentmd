"""Setup wizard, config display, and update commands for Agent.md."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import textwrap
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

SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=Agent.md Runtime
After=network.target

[Service]
Type=simple
ExecStart={agentmd_path} start
Restart=on-failure

[Install]
WantedBy=default.target
"""

LAUNCHD_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>me.zfab.agentmd</string>
    <key>ProgramArguments</key>
    <array>
        <string>{agentmd_path}</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
</dict>
</plist>
"""


def _default_workspace() -> Path:
    """Return default workspace path (always ~/agentmd)."""
    return Path.home() / "agentmd"


def _get_config_dir() -> Path:
    """Get the config directory (~/.config/agentmd)."""
    config_dir = Path.home() / ".config" / "agentmd"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _write_config_yaml(workspace: Path, provider: str, model: str):
    """Write config.yaml to ~/.config/agentmd/config.yaml."""
    config = {
        "workspace": str(workspace),
        "agents_dir": "agents",
        "db_path": "data/agentmd.db",
        "mcp_config": "agents/mcp-servers.json",
        "defaults": {
            "provider": provider,
            "model": model,
        },
        "log_level": "INFO",
    }
    config_path = _get_config_dir() / "config.yaml"
    config_path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


def _write_env_file(path: Path, api_key: str | None, env_var: str | None):
    """Write .env with API keys only."""
    lines = ["# Agent.md — API Keys"]
    if api_key and env_var:
        lines.append(f"{env_var}={api_key}")
    else:
        lines.append("# GOOGLE_API_KEY=...")
        lines.append("# OPENAI_API_KEY=sk-...")
        lines.append("# ANTHROPIC_API_KEY=sk-ant-...")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _create_workspace(workspace: Path, provider: str, model: str):
    """Create workspace directory structure, hello-world agent, and MCP config."""
    agents_dir = workspace / "agents"
    tools_dir = agents_dir / "tools"
    data_dir = workspace / "data"

    for d in (agents_dir, tools_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Hello-world agent (no model — uses default from config.yaml)
    hello_world = agents_dir / "hello-world.md"
    if not hello_world.exists():
        hello_world.write_text(
            textwrap.dedent("""\
                ---
                name: hello-world
                ---

                You are a friendly assistant. When asked to execute your task,
                write a creative greeting and save it to 'greeting.txt'.
            """)
        )

    # Empty MCP servers config
    mcp_config = agents_dir / "mcp-servers.json"
    if not mcp_config.exists():
        mcp_config.write_text("{}\n")


def _setup_autostart() -> bool:
    """Configure auto-start based on platform. Returns True if configured."""
    agentmd_path = shutil.which("agentmd")
    if not agentmd_path:
        console.print("  [yellow]Could not find agentmd in PATH, skipping auto-start.[/]")
        return False

    system = platform.system()

    if system == "Linux":
        systemd_dir = Path.home() / ".config" / "systemd" / "user"
        if not Path("/run/systemd/system").exists():
            console.print("  [yellow]systemd not available, skipping auto-start.[/]")
            return False

        systemd_dir.mkdir(parents=True, exist_ok=True)
        unit_path = systemd_dir / "agentmd.service"
        unit_path.write_text(SYSTEMD_UNIT_TEMPLATE.format(agentmd_path=agentmd_path))
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", "agentmd.service"], check=True, capture_output=True)
        console.print("  Created and enabled systemd user service")
        return True

    elif system == "Darwin":
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_path = plist_dir / "me.zfab.agentmd.plist"
        plist_path.write_text(LAUNCHD_PLIST_TEMPLATE.format(agentmd_path=agentmd_path))
        console.print(f"  Created Launch Agent at {plist_path}")
        return True

    elif system == "Windows":
        try:
            subprocess.run(
                [
                    "schtasks",
                    "/create",
                    "/tn",
                    "AgentMD",
                    "/tr",
                    f'"{agentmd_path}" start',
                    "/sc",
                    "onlogon",
                    "/f",
                ],
                check=True,
                capture_output=True,
            )
            console.print("  Created Windows scheduled task 'AgentMD'")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("  [yellow]Could not create scheduled task, skipping auto-start.[/]")
            return False

    console.print("  [yellow]Auto-start not supported on this platform.[/]")
    return False


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


@app.command()
def config():
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
    default_ws = _default_workspace()
    workspace_input = Prompt.ask("\nWorkspace directory", default=str(default_ws))
    workspace = Path(workspace_input).expanduser().resolve()

    # 2. Provider
    provider = Prompt.ask(
        "\nLLM Provider",
        choices=list(PROVIDERS.keys()),
        default="google",
    )

    # 3. Model
    default_model = PROVIDERS[provider]["default_model"]
    model = Prompt.ask("\nModel", default=default_model)

    # 4. API Key
    api_key = None
    env_var = PROVIDERS[provider]["env_var"]
    if env_var:
        existing_key = os.environ.get(env_var, "")
        if existing_key:
            masked = existing_key[:4] + "..." + existing_key[-4:] if len(existing_key) > 8 else "****"
            console.print(f"\nFound existing {env_var}: {masked}")
            if not Confirm.ask("Use this key?", default=True):
                api_key = Prompt.ask(f"\n{env_var}", password=True)
            else:
                api_key = existing_key
        else:
            api_key = Prompt.ask(f"\n{env_var}", password=True)
    else:
        console.print("\nNo API key needed for ollama")

    # 5. Auto-start
    autostart = Confirm.ask("\nEnable auto-start on login?", default=False)

    # --- Apply configuration ---
    console.print("\n[bold]Applying configuration...[/]\n")

    # Create workspace structure
    _create_workspace(workspace, provider, model)
    console.print(f"  Workspace created at {workspace}")

    # Write config.yaml
    _write_config_yaml(workspace, provider, model)
    config_path = _get_config_dir() / "config.yaml"
    console.print(f"  Config written to {config_path}")

    # Write .env (secrets only)
    env_path = workspace / ".env"
    _write_env_file(env_path, api_key, env_var)
    console.print(f"  Secrets written to {env_path}")

    # Auto-start
    if autostart:
        _setup_autostart()

    # Summary
    console.print(
        make_panel(
            "\n".join(
                [
                    f"[bold]Workspace:[/]     {workspace}",
                    f"[bold]Provider:[/]      {provider}",
                    f"[bold]Model:[/]         {model}",
                    f"[bold]Config:[/]        {config_path}",
                    f"[bold]Secrets:[/]       {env_path}",
                    f"[bold]Auto-start:[/]    {'enabled' if autostart else 'disabled'}",
                    "",
                    "[bold]Next steps:[/]",
                    "  agentmd start           — Start the runtime",
                    "  agentmd run hello-world — Run the sample agent",
                    "  agentmd config          — Show current configuration",
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
