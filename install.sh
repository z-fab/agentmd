#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/z-fab/agentmd.git"

header() { printf "\n\033[1;32m%s\033[0m\n\n" "$1"; }
warn()   { printf "\033[0;33m⚠ %s\033[0m\n" "$1"; }

header "🤖 Agent.md — Installer"

# Install uv if needed
if ! command -v uv &>/dev/null; then
    header "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install agentmd globally
header "Installing agentmd..."
uv tool install "agentmd[all] @ git+${REPO}" --force --python 3.13

# Ensure PATH includes ~/.local/bin
LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    SHELL_NAME="$(basename "$SHELL")"
    case "$SHELL_NAME" in
        zsh)  PROFILE="$HOME/.zshrc" ;;
        bash) PROFILE="$HOME/.bashrc" ;;
        *)    PROFILE="$HOME/.profile" ;;
    esac
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$PROFILE"
    export PATH="$LOCAL_BIN:$PATH"
    warn "Added ~/.local/bin to PATH in $PROFILE"
fi

# Run setup wizard
header "Running setup wizard..."
agentmd setup
