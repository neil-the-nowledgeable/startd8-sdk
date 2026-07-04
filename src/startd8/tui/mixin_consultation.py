"""ConsultationMixin — Multi-Model Consultation workflow in the TUI (M3 / FR-MMC-9).

Thin interactive glue over the tested ``consultation`` core: prompt entry → image pick
(≤2, validated, trust boundary) → roster select (vision-only) → parallel run → side-by-side
comparison → follow-up loop (ALL vs one model, modelled on ``step2_distribute_prompt``).

All non-interactive logic lives in ``consultation/`` (selection, roster, engine, view) so it
is unit-tested and shared byte-for-byte with the ``startd8 consult`` CLI (no logic fork).
"""

from ._shared import *  # noqa: F401,F403

from ..consultation import (
    ALL,
    ConsultationService,
    DEFAULT_COUNCIL,
    build_roster,
    comparison_table,
    resolve_images,
)
from ..consultation.selection import ImageSelectionError


class ConsultationMixin:
    def consultation_menu(self):
        """Interactive entry point for the multi-model consultation workflow."""
        self.show_header("Multi-Model Consultation")
        self.console.print(Panel(
            "[bold cyan]Multi-Model Consultation[/bold cyan]\n\n"
            "Ask one question — optionally with up to 2 images — of several models at once,\n"
            "compare their answers side by side, then follow up with all of them or just one.\n\n"
            "[dim]Inspired by (not part of) the Summer 2026 benchmark. Answers are saved under\n"
            ".startd8/consultations/ for later comparison.[/dim]",
            title="🗣️  Consultation",
            border_style="cyan",
        ))
        if not questionary.confirm("Start a consultation?", default=True, style=custom_style).ask():
            return

        # Step 1 — prompt
        self.console.print("\n[bold cyan]Step 1 of 4: Your question[/bold cyan]")
        prompt = self._get_text_or_file_input("Enter your prompt (or a file path)")
        if not prompt:
            self.console.print("[yellow]No prompt entered. Cancelled.[/yellow]")
            return

        # Step 2 — images (optional, ≤2)
        self.console.print("\n[bold cyan]Step 2 of 4: Images (optional, up to 2)[/bold cyan]")
        images = self._consultation_pick_images()
        if images is None:  # validation error already reported
            return

        # Step 3 — roster
        self.console.print("\n[bold cyan]Step 3 of 4: Choose models[/bold cyan]")
        roster = self._consultation_pick_roster(require_vision=bool(images))
        if not roster:
            self.console.print("[yellow]No available models selected. Cancelled.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return

        # Step 4 — confirm + run
        self.console.print(
            f"\n[bold cyan]Step 4 of 4:[/bold cyan] sending to "
            f"[bold]{len(roster)}[/bold] model(s): {', '.join(roster)}"
            + (f" with [bold]{len(images)}[/bold] image(s)" if images else "")
        )
        if not questionary.confirm("Run consultation?", default=True, style=custom_style).ask():
            return

        service = ConsultationService(base_dir=str(self._consultation_base_dir()))
        session = self._consultation_run(
            lambda: service.start(prompt, images, roster), "Consulting models…"
        )
        if session is None:
            return
        self.console.print(f"[green]Saved session:[/green] {session.id}")
        self._consultation_show(session)

        # Follow-up loop
        self._consultation_followup_loop(service, session, roster)

    # ── steps (delegating to the tested core) ─────────────────────────────────
    def _consultation_pick_images(self):
        """Return a list[ImageInput] (possibly empty), or None on a validation error."""
        choice = questionary.select(
            "Attach images?",
            choices=["No images", "Pick specific file(s)", "Pick from a folder"],
            style=custom_style,
        ).ask()
        try:
            if choice == "Pick specific file(s)":
                raw = questionary.text(
                    "Image path(s), comma-separated (max 2)", style=custom_style
                ).ask()
                paths = [p.strip() for p in (raw or "").split(",") if p.strip()]
                return resolve_images(paths=paths) if paths else []
            if choice == "Pick from a folder":
                folder = self._safe_path_input("Folder containing the image(s)")
                if not folder:
                    return []
                images = resolve_images(image_dir=folder)
                if not images:
                    self.console.print("[yellow]No valid images found in that folder.[/yellow]")
                return images
            return []
        except ImageSelectionError as e:
            self.console.print(f"[red]Image selection failed:[/red] {e}")
            questionary.press_any_key_to_continue().ask()
            return None

    def _consultation_pick_roster(self, *, require_vision: bool):
        """Let the user pick the roster; returns {model_id: agent} (may be empty)."""
        use_default = questionary.confirm(
            f"Use the default council ({', '.join(DEFAULT_COUNCIL)})?",
            default=True,
            style=custom_style,
        ).ask()
        specs = None
        if not use_default:
            raw = questionary.text(
                "Model specs, comma-separated (e.g. anthropic:claude-opus-4-8, openai:gpt-5.5)",
                style=custom_style,
            ).ask()
            specs = [s.strip() for s in (raw or "").split(",") if s.strip()] or None

        roster, unavailable = build_roster(specs, require_vision=require_vision)
        for spec, reason in unavailable:
            self.console.print(f"[yellow]skipping {spec}[/yellow] — {reason}")
        return roster

    def _consultation_followup_loop(self, service, session, roster):
        while True:
            action = questionary.select(
                "What next?",
                choices=[
                    "Follow up with ALL models",
                    "Follow up with ONE model",
                    "Retry failed models",
                    "View comparison again",
                    "Done",
                ],
                style=custom_style,
            ).ask()
            if action in (None, "Done"):
                return
            if action == "View comparison again":
                self._consultation_show(session)
                continue
            if action == "Retry failed models":
                if not session.failed_models():
                    self.console.print("[dim]No failed models to retry.[/dim]")
                    continue
                session = self._consultation_run(
                    lambda: service.retry_failed(session, roster), "Retrying failed models…"
                ) or session
                self._consultation_show(session)
                continue

            target = ALL
            if action == "Follow up with ONE model":
                target = questionary.select(
                    "Which model?", choices=list(session.roster), style=custom_style
                ).ask()
                if not target:
                    continue

            follow_prompt = self._get_text_or_file_input("Follow-up prompt (or file path)")
            if not follow_prompt:
                continue
            session = self._consultation_run(
                lambda: service.follow_up(session, roster, follow_prompt, target),
                f"Sending follow-up to {'all models' if target == ALL else target}…",
            ) or session
            self._consultation_show(session)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _consultation_run(self, thunk, message: str):
        """Run a (blocking) consultation call under a spinner; report errors gracefully."""
        try:
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                console=self.console, transient=True,
            ) as progress:
                progress.add_task(message, total=None)
                return thunk()
        except Exception as e:  # noqa: BLE001
            self.console.print(f"[red]Consultation error:[/red] {e}")
            questionary.press_any_key_to_continue().ask()
            return None

    def _consultation_show(self, session):
        self.console.print(comparison_table(session))

    def _consultation_base_dir(self):
        """Storage root for consultations — the active framework's storage dir if available."""
        framework = getattr(self, "framework", None)
        base = getattr(framework, "storage_dir", None) if framework else None
        return Path(base) if base else Path(".startd8")
