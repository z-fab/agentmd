"""Deterministic agent icon resolution.

Mirrors the Obsidian plugin's `src/ui/agent-emoji.ts` (same palette + FNV-1a
hash) so the API, the CLI, and the plugin all show the same emoji for an agent
that doesn't declare an explicit `icon`.
"""

from __future__ import annotations

# Must stay byte-identical (and in the same order) to the plugin palette.
AGENT_EMOJI_PALETTE: tuple[str, ...] = (
    "📅",
    "😄",
    "📥",
    "📊",
    "🧹",
    "🔔",
    "📝",
    "🔎",
    "🗂️",
    "📌",
    "💡",
    "⚙️",
    "🚀",
    "🧠",
    "📈",
    "📰",
    "🛰️",
    "🧩",
    "🔧",
    "📦",
    "🗒️",
    "🪄",
    "🎯",
    "🧪",
    "🔐",
    "🌐",
    "📮",
    "🧭",
    "⏰",
    "🗞️",
    "🪙",
    "🔖",
    "📤",
    "🧮",
    "🛎️",
    "📚",
    "🧰",
    "🪛",
    "🎲",
    "🧵",
    "🗳️",
    "📡",
    "🧯",
    "🔋",
    "🪪",
    "🧾",
    "🗺️",
    "🎛️",
)


def _hash_name(name: str) -> int:
    """FNV-1a (32-bit), matching the plugin's hashName (Math.imul + >>>0)."""
    h = 2166136261
    for ch in name:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def resolve_agent_icon(name: str, icon: str | None) -> str:
    """Return the explicit icon if set, else a stable name-derived palette emoji."""
    if icon and icon.strip():
        return icon
    return AGENT_EMOJI_PALETTE[_hash_name(name) % len(AGENT_EMOJI_PALETTE)]
