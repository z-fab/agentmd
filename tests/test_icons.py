from agent_md.config.icons import resolve_agent_icon, AGENT_EMOJI_PALETTE


def test_explicit_icon_wins():
    assert resolve_agent_icon("daily-processor", "📅") == "📅"


def test_blank_icon_falls_back():
    assert resolve_agent_icon("daily-processor", "") in AGENT_EMOJI_PALETTE
    assert resolve_agent_icon("daily-processor", "   ") in AGENT_EMOJI_PALETTE
    assert resolve_agent_icon("daily-processor", None) in AGENT_EMOJI_PALETTE


def test_deterministic():
    a = resolve_agent_icon("inbox-triage", None)
    b = resolve_agent_icon("inbox-triage", None)
    assert a == b


def test_palette_has_48_unique_entries():
    assert len(AGENT_EMOJI_PALETTE) == 48


def test_different_names_distribute():
    # Not a strict guarantee, but a smoke check that names map across the palette.
    got = {resolve_agent_icon(n, None) for n in ["a", "b", "c", "daily", "hello", "weekly-report", "inbox"]}
    assert len(got) >= 3


def test_display_icon_forces_emoji_presentation():
    from agent_md.cli.theme import display_icon

    # Bare BMP symbols default to a 1-cell text glyph; we append U+FE0F so
    # terminals render them 2 cells wide and table columns stay aligned.
    assert display_icon("☀") == "☀️"  # ☀ -> ☀️
    assert display_icon("⚙") == "⚙️"  # ⚙ -> ⚙️


def test_display_icon_leaves_wide_emoji_untouched():
    from agent_md.cli.theme import display_icon

    assert display_icon("\U0001f4c5") == "\U0001f4c5"  # 📅 (supplementary plane)
    assert display_icon("\U0001f5c2️") == "\U0001f5c2️"  # 🗂️ (already qualified)
    assert display_icon("☀️") == "☀️"  # ☀️ already has selector
