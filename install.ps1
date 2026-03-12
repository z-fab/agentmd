#Requires -Version 5.1
$ErrorActionPreference = "Stop"

Write-Host "`n🤖 Agent.md — Installer`n" -ForegroundColor Green

# Install uv if needed
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Cyan
    irm https://astral.sh/uv/install.ps1 | iex
    # Refresh PATH for current session
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
}

# Install agentmd
Write-Host "Installing agentmd..." -ForegroundColor Cyan
uv tool install "agentmd[all] @ git+https://github.com/z-fab/agentmd.git" --force --python 3.13

# Run setup wizard
Write-Host "`nRunning setup wizard..." -ForegroundColor Cyan
agentmd setup
