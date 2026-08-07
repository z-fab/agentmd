"""One-shot workspace identity migration: display-name keys → filename stems.

Never rewrites agent ``.md`` files. Safe to re-run; supports ``dry_run``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_md.config.models import AgentConfig


@dataclass
class MigrateItem:
    """A single planned or performed migrate step / notice."""

    kind: str  # rekey | rename_memory | allowlist | skip | collision | ambiguous
    agent_id: str
    message: str
    level: str = "action"  # action | warning | error | info


@dataclass
class MigrateReport:
    """Aggregate result of ``migrate_workspace``."""

    items: list[MigrateItem] = field(default_factory=list)
    dry_run: bool = False

    @property
    def actions(self) -> list[MigrateItem]:
        return [i for i in self.items if i.level == "action"]

    @property
    def warnings(self) -> list[MigrateItem]:
        return [i for i in self.items if i.level == "warning"]

    @property
    def errors(self) -> list[MigrateItem]:
        return [i for i in self.items if i.level == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _display_to_stems(agents: list[AgentConfig]) -> dict[str, list[str]]:
    """Map display name → stems of agents that use that display name."""
    mapping: dict[str, list[str]] = {}
    for cfg in agents:
        mapping.setdefault(cfg.name, []).append(cfg.id)
    return mapping


def _plan_agent(
    config: AgentConfig,
    *,
    agents_dir: Path,
    id_set: set[str],
    display_to_stems: dict[str, list[str]],
    execution_counts: dict[str, int],
) -> list[MigrateItem]:
    items: list[MigrateItem] = []
    stem = config.id
    old_name = config.name

    # --- executions.agent_id + memory ---
    if old_name != stem:
        stems_sharing_name = sorted(display_to_stems.get(old_name, [stem]))
        # Duplicate display names: legacy agent_id / memory key is ambiguous —
        # never rekey or rename for any of the competing stems.
        if len(stems_sharing_name) > 1:
            count = execution_counts.get(old_name, 0)
            mem_exists = (agents_dir / f"{old_name}.memory.md").exists()
            detail_parts = []
            if count:
                detail_parts.append(f"{count} execution(s)")
            if mem_exists:
                detail_parts.append(f"memory file {old_name}.memory.md")
            detail = f" ({', '.join(detail_parts)} left untouched)" if detail_parts else ""
            items.append(
                MigrateItem(
                    kind="ambiguous",
                    agent_id=stem,
                    level="error",
                    message=(
                        f"cannot rekey/rename display name {old_name!r} → {stem!r}: "
                        f"shared by ids {', '.join(stems_sharing_name)}; "
                        f"resolve ownership manually{detail}"
                    ),
                )
            )
        # If another agent already owns this string as its id, legacy rows
        # keyed by old_name are ambiguous with that agent's current rows.
        elif old_name in id_set:
            count = execution_counts.get(old_name, 0)
            if count:
                items.append(
                    MigrateItem(
                        kind="ambiguous",
                        agent_id=stem,
                        level="error",
                        message=(
                            f"cannot rekey {count} execution(s) from agent_id={old_name!r} "
                            f"→ {stem!r}: {old_name!r} is also another agent's canonical id"
                        ),
                    )
                )
            else:
                items.append(
                    MigrateItem(
                        kind="skip",
                        agent_id=stem,
                        level="info",
                        message=(
                            f"skip execution rekey {old_name!r} → {stem!r}: "
                            f"no rows and {old_name!r} is another agent's id"
                        ),
                    )
                )
            old_mem = agents_dir / f"{old_name}.memory.md"
            new_mem = agents_dir / f"{stem}.memory.md"
            if old_mem.exists():
                items.append(
                    MigrateItem(
                        kind="ambiguous",
                        agent_id=stem,
                        level="warning",
                        message=(
                            f"skip memory rename {old_mem.name} → {new_mem.name}: "
                            f"{old_name!r} is another agent's id (file may belong to them)"
                        ),
                    )
                )
        else:
            count = execution_counts.get(old_name, 0)
            if count:
                items.append(
                    MigrateItem(
                        kind="rekey",
                        agent_id=stem,
                        level="action",
                        message=f"rekey {count} execution(s): agent_id {old_name!r} → {stem!r}",
                    )
                )

            old_mem = agents_dir / f"{old_name}.memory.md"
            new_mem = agents_dir / f"{stem}.memory.md"
            if old_mem.exists():
                if new_mem.exists():
                    items.append(
                        MigrateItem(
                            kind="collision",
                            agent_id=stem,
                            level="error",
                            message=(
                                f"memory collision: both {old_mem.name} and {new_mem.name} exist; refusing to overwrite"
                            ),
                        )
                    )
                else:
                    items.append(
                        MigrateItem(
                            kind="rename_memory",
                            agent_id=stem,
                            level="action",
                            message=f"rename memory {old_mem.name} → {new_mem.name}",
                        )
                    )

    # --- allowlist agents: still using display names ---
    for peer in config.agents:
        if peer in id_set:
            continue
        stems = display_to_stems.get(peer, [])
        # Only flag when peer matches a display name that is not already a stem.
        distinct = [s for s in stems if s != peer]
        if len(distinct) == 1:
            items.append(
                MigrateItem(
                    kind="allowlist",
                    agent_id=stem,
                    level="warning",
                    message=(
                        f"{stem}.md allowlist agents: refers to display name {peer!r}; "
                        f"edit manually to canonical id {distinct[0]!r} "
                        "(agent .md files are never modified by migrate)"
                    ),
                )
            )
        elif len(distinct) > 1:
            items.append(
                MigrateItem(
                    kind="allowlist",
                    agent_id=stem,
                    level="warning",
                    message=(
                        f"{stem}.md allowlist agents: refers to display name {peer!r} "
                        f"shared by ids {', '.join(sorted(distinct))}; edit manually"
                    ),
                )
            )

    return items


async def migrate_workspace(
    workspace: Path | None = None,
    *,
    dry_run: bool = False,
) -> MigrateReport:
    """Migrate historical identity keys in DB + memory files for a workspace.

    - Updates ``executions.agent_id`` from legacy display name → stem
    - Renames ``{display}.memory.md`` → ``{stem}.memory.md`` when safe
    - Reports allowlist entries that still use display names (never edits ``.md``)
    """
    from agent_md.workspace.bootstrap import bootstrap

    report = MigrateReport(dry_run=dry_run)
    rt = await bootstrap(workspace, readonly=dry_run)
    try:
        agents = rt.registry.all()
        agents_dir = rt.path_context.agents_dir
        id_set = {cfg.id for cfg in agents}
        display_to_stems = _display_to_stems(agents)

        # Prefetch counts for all candidate old names in one pass.
        old_names = {cfg.name for cfg in agents if cfg.name != cfg.id}
        execution_counts: dict[str, int] = {}
        for name in old_names:
            execution_counts[name] = await rt.db.count_executions_by_agent_id(name)

        planned: list[MigrateItem] = []
        for cfg in sorted(agents, key=lambda c: c.id):
            planned.extend(
                _plan_agent(
                    cfg,
                    agents_dir=agents_dir,
                    id_set=id_set,
                    display_to_stems=display_to_stems,
                    execution_counts=execution_counts,
                )
            )

        report.items.extend(planned)

        if dry_run:
            return report

        for item in planned:
            if item.level != "action":
                continue

            cfg = rt.registry.get(item.agent_id)
            if cfg is None:
                continue

            if item.kind == "rekey":
                await rt.db.rekey_agent_id(cfg.name, cfg.id)
            elif item.kind == "rename_memory":
                old_mem = agents_dir / f"{cfg.name}.memory.md"
                new_mem = agents_dir / f"{cfg.id}.memory.md"
                if old_mem.exists() and not new_mem.exists():
                    old_mem.rename(new_mem)

        return report
    finally:
        await rt.aclose()


def format_migrate_report(report: MigrateReport) -> list[str]:
    """Human-readable lines for CLI output."""
    lines: list[str] = []
    prefix = "would " if report.dry_run else ""

    if not report.items:
        lines.append("Nothing to migrate — workspace already uses canonical ids.")
        return lines

    for item in report.items:
        if item.level == "action":
            lines.append(f"  {prefix}{item.message}")
        elif item.level == "warning":
            lines.append(f"  warning: {item.message}")
        elif item.level == "error":
            lines.append(f"  error: {item.message}")
        else:
            lines.append(f"  {item.message}")

    summary_parts = []
    n_actions = len(report.actions)
    n_warn = len(report.warnings)
    n_err = len(report.errors)
    if n_actions:
        summary_parts.append(f"{n_actions} action{'s' if n_actions != 1 else ''}")
    if n_warn:
        summary_parts.append(f"{n_warn} warning{'s' if n_warn != 1 else ''}")
    if n_err:
        summary_parts.append(f"{n_err} error{'s' if n_err != 1 else ''}")
    if summary_parts:
        mode = "dry-run: " if report.dry_run else ""
        lines.append(f"\n  {mode}{', '.join(summary_parts)}")
    return lines
