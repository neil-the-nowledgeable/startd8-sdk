# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``startd8 consult`` CLI — multi-model consultation, headless (M3.5 / FR-MMC-13).

A thin front door over the **same** ``ConsultationService`` the TUI drives (no logic fork):
send one prompt + up to 2 images to N models in parallel, persist a ``ConsultationSession``,
and follow up with all-or-one routing. Everything non-interactive (image selection + trust
boundary, roster building, fan-out, rendering) lives in the ``consultation`` package and is
shared byte-for-byte with the TUI.

Exit codes: 0 ok; 2 bad input (image/selection/roster error).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from .cli_shared import console

consult_app = typer.Typer(
    name="consult",
    help="Ask N models one prompt (+ up to 2 images) in parallel; compare and follow up.",
)

_EXIT_BAD_INPUT = 2


def _base_dir() -> str:
    return ".startd8"


def _resolve_images_or_exit(images: Optional[List[Path]], image_dir: Optional[Path]):
    from .consultation import resolve_images
    from .consultation.selection import ImageSelectionError

    try:
        return resolve_images(
            paths=[str(p) for p in images] if images else None,
            image_dir=str(image_dir) if image_dir else None,
        )
    except (ImageSelectionError, Exception) as exc:  # noqa: BLE001 — surface as bad input
        console.print(f"[red]consult:[/red] image selection failed — {exc}")
        raise typer.Exit(_EXIT_BAD_INPUT)


def _build_roster_or_exit(models: Optional[List[str]], *, require_vision: bool):
    from .consultation import build_roster

    roster, unavailable = build_roster(models or None, require_vision=require_vision)
    for spec, reason in unavailable:
        console.print(f"[yellow]skipping {spec}[/yellow] — {reason}")
    if not roster:
        console.print("[red]consult:[/red] no available models (check specs / API keys).")
        raise typer.Exit(_EXIT_BAD_INPUT)
    return roster


@consult_app.command("run")
def consult_run(
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="The prompt text."),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file", help="Read the prompt from a file."),
    image: Optional[List[Path]] = typer.Option(None, "--image", help="Image path (repeatable, max 2)."),
    image_dir: Optional[Path] = typer.Option(None, "--image-dir", help="Folder to auto-select up to 2 images from."),
    models: Optional[List[str]] = typer.Option(None, "--models", "-m", help="Model spec (repeatable); default = cross-vendor council."),
    json_out: bool = typer.Option(False, "--json", help="Emit the session JSON to stdout."),
) -> None:
    """Start a consultation: fan the prompt (+ images) out to the roster in parallel."""
    from .consultation import ConsultationService, comparison_text

    if prompt_file:
        prompt = prompt_file.read_text(encoding="utf-8")
    if not prompt:
        console.print("[red]consult:[/red] provide --prompt or --prompt-file.")
        raise typer.Exit(_EXIT_BAD_INPUT)
    if image and image_dir:
        console.print("[red]consult:[/red] use --image OR --image-dir, not both.")
        raise typer.Exit(_EXIT_BAD_INPUT)

    imgs = _resolve_images_or_exit(image, image_dir)
    roster = _build_roster_or_exit(models, require_vision=bool(imgs))

    service = ConsultationService(base_dir=_base_dir())
    console.print(f"[dim]consulting {len(roster)} model(s)"
                  + (f" with {len(imgs)} image(s)" if imgs else "") + "…[/dim]")
    session = service.start(prompt, imgs, roster)

    if json_out:
        console.print(session.model_dump_json(indent=2))
    else:
        console.print(comparison_text(session))
    console.print(f"[green]session:[/green] {session.id}")


@consult_app.command("reply")
def consult_reply(
    session_id: str = typer.Argument(..., help="Session id from a prior `consult run`."),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Follow-up prompt text."),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file", help="Read the follow-up from a file."),
    to: str = typer.Option("all", "--to", help="Route to 'all' models or a single model id."),
    image: Optional[List[Path]] = typer.Option(None, "--image", help="Image path (repeatable, max 2)."),
    image_dir: Optional[Path] = typer.Option(None, "--image-dir", help="Folder to auto-select images from."),
    json_out: bool = typer.Option(False, "--json", help="Emit the session JSON to stdout."),
) -> None:
    """Follow up on a saved session, routed to ALL models or a single one (FR-MMC-8)."""
    from .consultation import ConsultationService, comparison_text

    if prompt_file:
        prompt = prompt_file.read_text(encoding="utf-8")
    if not prompt:
        console.print("[red]consult:[/red] provide --prompt or --prompt-file.")
        raise typer.Exit(_EXIT_BAD_INPUT)
    if image and image_dir:
        console.print("[red]consult:[/red] use --image OR --image-dir, not both.")
        raise typer.Exit(_EXIT_BAD_INPUT)

    service = ConsultationService(base_dir=_base_dir())
    try:
        session = service.load(session_id)
    except FileNotFoundError:
        console.print(f"[red]consult:[/red] no such session: {session_id}")
        raise typer.Exit(_EXIT_BAD_INPUT)

    imgs = _resolve_images_or_exit(image, image_dir)
    # Rebuild the roster from the session's model list so threads continue.
    roster = _build_roster_or_exit(list(session.roster), require_vision=bool(imgs))

    if to != "all" and to not in session.roster:
        console.print(f"[red]consult:[/red] {to} is not in this session's roster: {', '.join(session.roster)}")
        raise typer.Exit(_EXIT_BAD_INPUT)

    session = service.follow_up(session, roster, prompt, target=to, images=imgs)
    if json_out:
        console.print(session.model_dump_json(indent=2))
    else:
        console.print(comparison_text(session))


@consult_app.command("show")
def consult_show(
    session_id: str = typer.Argument(..., help="Session id to display."),
    json_out: bool = typer.Option(False, "--json", help="Emit the raw session JSON."),
) -> None:
    """Show a saved consultation's side-by-side comparison."""
    from .consultation import ConsultationService, comparison_text

    service = ConsultationService(base_dir=_base_dir())
    try:
        session = service.load(session_id)
    except FileNotFoundError:
        console.print(f"[red]consult:[/red] no such session: {session_id}")
        raise typer.Exit(_EXIT_BAD_INPUT)
    console.print(session.model_dump_json(indent=2) if json_out else comparison_text(session))


@consult_app.command("list")
def consult_list() -> None:
    """List saved consultation session ids."""
    from .consultation import ConsultationService

    service = ConsultationService(base_dir=_base_dir())
    ids = service.list_sessions()
    if not ids:
        console.print("[dim]no consultations yet.[/dim]")
        return
    for sid in ids:
        console.print(sid)
