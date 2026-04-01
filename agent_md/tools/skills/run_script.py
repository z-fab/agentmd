"""Tool: skill_run_script — Execute scripts from a skill directory."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from agent_md.tools.skills._validation import is_within, validate_skill_access


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
        _, error = validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        skill_dir = (skills_dir / skill_name).resolve()
        scripts_dir = skill_dir / "scripts"

        if not scripts_dir.is_dir():
            return f"Skill '{skill_name}' has no scripts/ directory"

        script_path = (scripts_dir / script_name).resolve()

        # Security: resolved path must be within scripts/ directory
        if not is_within(script_path, scripts_dir):
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
