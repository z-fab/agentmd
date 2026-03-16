"""Built-in tools for skill interaction — skill_use, skill_read_file, skill_run_script."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from agent_md.skills.loader import apply_substitutions
from agent_md.skills.parser import parse_skill_full


def _validate_skill_access(skill_name: str, agent_config, skills_dir: Path) -> tuple[Path | None, str | None]:
    """Validate that the agent has access to a skill and it exists.

    Returns:
        (skill_path, None) on success, or (None, error_message) on failure.
    """
    if skill_name not in agent_config.skills:
        available = ", ".join(agent_config.skills) if agent_config.skills else "none"
        return None, f"Skill '{skill_name}' is not enabled for this agent. Available: {available}"

    skill_path = skills_dir / skill_name / "SKILL.md"
    if not skill_path.exists():
        return None, f"Skill '{skill_name}' not found at {skill_path}"

    return skill_path, None


def _is_within(path: Path, directory: Path) -> bool:
    """Check if a resolved path is within a directory (safe against traversal)."""
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def create_skill_use_tool(agent_config, skills_dir: Path):
    """Create skill_use tool for loading skill instructions on-demand."""

    @tool
    def skill_use(skill_name: str, arguments: str = "") -> str:
        """Load a skill's instructions with variable substitutions applied.

        Use this to activate a skill and receive its detailed instructions.
        The system prompt lists available skills — call this tool to load one.

        Args:
            skill_name: Name of the skill to use.
            arguments: Optional arguments to pass to the skill (replaces $ARGUMENTS).

        Returns:
            The skill's processed instructions ready to follow.
        """
        skill_path, error = _validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        try:
            definition = parse_skill_full(skill_path)
        except (OSError, ValueError) as e:
            return f"Error loading skill '{skill_name}': {e}"

        # Apply substitutions
        processed = apply_substitutions(
            definition.instructions,
            arguments=arguments,
            skill_dir=definition.skill_dir,
        )

        # Build response with context
        parts = [f"# Skill: {definition.name}"]
        if definition.description:
            parts.append(f"\n{definition.description}\n")
        parts.append(f"\n{processed}")

        if definition.has_scripts:
            scripts_path = Path(definition.skill_dir) / "scripts"
            scripts = [f.name for f in scripts_path.iterdir() if f.is_file()]
            if scripts:
                parts.append(f"\n\nAvailable scripts: {', '.join(scripts)}")
                parts.append("Use skill_run_script to execute them.")

        if definition.has_references:
            refs_path = Path(definition.skill_dir) / "references"
            refs = [f.name for f in refs_path.iterdir() if f.is_file()]
            if refs:
                parts.append(f"\n\nAvailable references: {', '.join(refs)}")
                parts.append("Use skill_read_file to read them.")

        return "\n".join(parts)

    return skill_use


def create_skill_read_file_tool(agent_config, skills_dir: Path):
    """Create skill_read_file tool for reading supporting files from a skill."""

    @tool
    def skill_read_file(skill_name: str, file_path: str) -> str:
        """Read a file from a skill's directory (references, scripts, etc.).

        Args:
            skill_name: Name of the skill.
            file_path: Relative path within the skill directory (e.g., 'references/api-docs.md').

        Returns:
            File contents or error message.
        """
        _, error = _validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        skill_dir = (skills_dir / skill_name).resolve()
        target = (skill_dir / file_path).resolve()

        # Security: resolved path must be within skill directory
        if not _is_within(target, skill_dir):
            return f"Access denied: '{file_path}' is outside skill directory"

        if not target.exists():
            return f"File not found: '{file_path}' in skill '{skill_name}'"

        if not target.is_file():
            return f"Not a file: '{file_path}'"

        try:
            return target.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error reading file: {e}"

    return skill_read_file


def create_skill_run_script_tool(agent_config, skills_dir: Path):
    """Create skill_run_script tool for executing scripts from a skill."""

    @tool
    def skill_run_script(skill_name: str, script_name: str, script_args: str = "") -> str:
        """Execute a script from a skill's scripts/ directory.

        Args:
            skill_name: Name of the skill.
            script_name: Script filename (must be in the skill's scripts/ directory).
            script_args: Optional arguments to pass to the script.

        Returns:
            Script output (stdout + stderr) or error message.
        """
        _, error = _validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        skill_dir = (skills_dir / skill_name).resolve()
        scripts_dir = skill_dir / "scripts"

        if not scripts_dir.is_dir():
            return f"Skill '{skill_name}' has no scripts/ directory"

        script_path = (scripts_dir / script_name).resolve()

        # Security: resolved path must be within scripts/ directory
        if not _is_within(script_path, scripts_dir):
            return f"Access denied: '{script_name}' is outside scripts/ directory"

        if not script_path.exists():
            available = [f.name for f in scripts_dir.iterdir() if f.is_file()]
            return f"Script not found: '{script_name}'. Available: {', '.join(available) or 'none'}"

        if not script_path.is_file():
            return f"Not a file: '{script_name}'"

        # Build command based on file extension
        ext = script_path.suffix.lower()
        if ext == ".py":
            cmd = ["python", str(script_path)]
        elif ext in (".sh", ".bash"):
            cmd = ["bash", str(script_path)]
        elif ext == ".js":
            cmd = ["node", str(script_path)]
        else:
            cmd = [str(script_path)]

        if script_args:
            cmd.extend(shlex.split(script_args))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(skill_dir),
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output.strip() or "[no output]"
        except subprocess.TimeoutExpired:
            return f"Script timed out after 30s: {script_name}"
        except FileNotFoundError:
            return f"Cannot execute '{script_name}': interpreter not found or file not executable"
        except OSError as e:
            return f"Error running script: {e}"

    return skill_run_script
