"""Agent.md — Markdown-first agent runtime."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agentmd")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
