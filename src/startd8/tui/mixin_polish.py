"""TUI flow for `startd8 polish` (FR-2) — apply the deterministic design system to a target project.

Thin interactive wrapper over ``presentation_polish.apply_polish`` (the same engine the CLI drives),
mirroring the CapDevPipe mixin idiom: prompt for the target + theme, run, render the outcome. The
heavy lifting stays in the engine — this is presentation only.
"""

from __future__ import annotations

from pathlib import Path

import questionary

from ..presentation_polish import PolishConfig, apply_polish, get_theme, theme_names
from ..presentation_polish.engine import DEFAULT_THEME


class PolishMixin:
    """Adds the 'Polish App UI' project-setup flow to the TUI."""

    def run_polish_flow(self) -> None:
        """Prompt for a target project + theme, apply the polish design system, render the result."""
        project = questionary.path(
            "Target project root (contains app/):", default=str(Path.cwd())
        ).ask()
        if not project:
            return
        theme = questionary.select(
            "Theme:",
            choices=[
                questionary.Choice(
                    f"{name}{'  (default)' if name == DEFAULT_THEME else ''} — {get_theme(name).label}",
                    value=name,
                )
                for name in theme_names()
            ],
        ).ask()
        if not theme:
            return

        try:
            result = apply_polish(PolishConfig(project_root=Path(project), theme=theme))
        except (NotADirectoryError, KeyError) as exc:
            self.console.print(f"[red]Polish failed:[/red] {exc}")
            return

        for relpath, status in result.files:
            self.console.print(f"  [cyan]{status.value}[/cyan]: {relpath}")
        for skipped in result.skipped_user_owned:
            self.console.print(
                f"[yellow]kept your edits[/yellow]: {skipped} (no polish marker)"
            )
        self.console.print(
            f"[green]✓ Applied theme '{theme}'[/green] (cost=$0.00). "
            "Re-run `generate backend` first if the stylesheet isn't loading."
        )
