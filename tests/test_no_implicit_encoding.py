"""No module may open a text file without naming its encoding.

Without an explicit encoding, Python uses the machine's locale — UTF-8 on the
developers' macOS and on CI's Linux, cp1252 on a Brazilian Windows console. The
bytes on disk then depend on who ran the command, while every reader in this
codebase asks for UTF-8. That is how ``agentmd setup`` came to write a ``.env``
it could not read back, crashing every subsequent command at import time.

A grep would miss binary-mode opens and flag them wrongly; this walks the AST so
``open(p, "rb")`` stays legal and ``open(p)`` does not.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "agent_md"

TEXT_METHODS = {"read_text", "write_text"}


def _binary_mode(call: ast.Call) -> bool:
    """True when the call names a binary mode, where encoding is meaningless."""
    modes = [a for a in call.args[1:2] if isinstance(a, ast.Constant)]
    modes += [k.value for k in call.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)]
    return any(isinstance(m.value, str) and "b" in m.value for m in modes)


def _has_encoding(call: ast.Call) -> bool:
    return any(k.arg == "encoding" for k in call.keywords)


def _offenders(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Attribute) and node.func.attr in TEXT_METHODS:
            if not _has_encoding(node):
                found.append((node.lineno, f"{node.func.attr}()"))

        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            if not _has_encoding(node) and not _binary_mode(node):
                found.append((node.lineno, "open()"))

    return found


def test_no_text_file_is_opened_with_the_locale_encoding():
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, what in _offenders(tree):
            offenders.append(f"{path.relative_to(PACKAGE.parent)}:{lineno}: {what}")

    assert not offenders, 'add encoding="utf-8" (or open in binary mode):\n' + "\n".join(offenders)
