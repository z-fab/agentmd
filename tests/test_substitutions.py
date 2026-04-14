from agent_md.config.substitutions import apply_substitutions


def test_arguments_full_string():
    """Single string arg — $ARGUMENTS returns the string as-is."""
    assert apply_substitutions("hello $ARGUMENTS", arguments="world") == "hello world"


def test_arguments_full_list():
    """List args — $ARGUMENTS joins with newline."""
    out = apply_substitutions("hello $ARGUMENTS", arguments=["a", "b"])
    assert out == "hello a\nb"


def test_arguments_indexed_list():
    """List args — $ARGUMENTS[N] accesses by index."""
    out = apply_substitutions("$ARGUMENTS[0] then $ARGUMENTS[1]", arguments=["a", "b", "c"])
    assert out == "a then b"


def test_arguments_shorthand_list():
    """List args — $0..$9 accesses by index."""
    out = apply_substitutions("first $0 second $1", arguments=["x", "y", "z"])
    assert out == "first x second y"


def test_arguments_indexed_string():
    """Single string arg — $0 returns the whole string."""
    out = apply_substitutions("a=$0 b=$1", arguments="hello")
    assert out == "a=hello b="


def test_arguments_missing_index_is_empty():
    out = apply_substitutions("a=$0 b=$5", arguments=["x"])
    assert out == "a=x b="


def test_arguments_with_spaces_in_values():
    """List args with spaces — each value is preserved as a single arg."""
    out = apply_substitutions("$0 and $1", arguments=["arquivo 1.md", "arquivo 2.md"])
    assert out == "arquivo 1.md and arquivo 2.md"


def test_arguments_empty_list():
    out = apply_substitutions("hello $ARGUMENTS end", arguments=[])
    assert out == "hello  end"


def test_arguments_empty_string():
    out = apply_substitutions("hello $ARGUMENTS end", arguments="")
    assert out == "hello  end"


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
