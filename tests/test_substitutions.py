from agent_md.config.substitutions import apply_substitutions


def test_arguments_full():
    assert apply_substitutions("hello $ARGUMENTS", arguments="world") == "hello world"


def test_arguments_indexed():
    out = apply_substitutions("$ARGUMENTS[0] then $ARGUMENTS[1]", arguments="a\nb\nc")
    assert out == "a then b"


def test_arguments_shorthand():
    out = apply_substitutions("first $0 second $1", arguments="x\ny\nz")
    assert out == "first x second y"


def test_arguments_missing_index_is_empty():
    out = apply_substitutions("a=$0 b=$5", arguments="x")
    assert out == "a=x b="


def test_arguments_single_no_newline():
    """Single arg (no newline) works as before."""
    out = apply_substitutions("hello $ARGUMENTS and $0", arguments="world")
    assert out == "hello world and world"


def test_arguments_with_spaces_in_values():
    """Args with spaces are preserved when split by newline."""
    out = apply_substitutions("$0 and $1", arguments="arquivo 1.md\narquivo 2.md")
    assert out == "arquivo 1.md and arquivo 2.md"


def test_extra_vars_substitution():
    out = apply_substitutions(
        "${SKILL_DIR}/foo and ${MY_VAR}",
        extra_vars={"SKILL_DIR": "/skills/x", "MY_VAR": "value"},
    )
    assert out == "/skills/x/foo and value"


def test_command_injection(tmp_path):
    out = apply_substitutions("date is !`echo 2026-04-08`", cwd=str(tmp_path))
    assert "2026-04-08" in out


def test_command_injection_uses_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("hello")
    out = apply_substitutions("file: !`ls marker.txt`", cwd=str(tmp_path))
    assert "marker.txt" in out


def test_command_injection_timeout_is_handled():
    # 11s sleep > 10s timeout — should not hang
    out = apply_substitutions("done: !`sleep 11`", cwd=".")
    assert "timed out" in out.lower()
