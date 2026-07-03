"""Side-by-side comparison rendering for a consultation (M3.3 / FR-MMC-10).

Two renderers over the same data so the TUI and CLI stay consistent:
* :func:`comparison_text` — plain text (CLI + tests), no rich dependency.
* :func:`comparison_table` — a ``rich.table.Table`` (TUI).

Both show the **latest** assistant answer per model with its status and per-turn token/latency
signal (image-token cost is included since it flows the cost hook, M2.5).
"""

from __future__ import annotations

from typing import Optional

from .models import ConsultationSession, Turn, TurnRole, TurnStatus


def _latest_assistant(session: ConsultationSession, model_id: str) -> Optional[Turn]:
    for turn in reversed(session.turns_by_model.get(model_id, [])):
        if turn.role == TurnRole.assistant:
            return turn
    return None


def _usage(turn: Optional[Turn]) -> str:
    if turn is None:
        return ""
    bits = []
    if turn.input_tokens is not None:
        bits.append(f"in={turn.input_tokens}")
    if turn.output_tokens is not None:
        bits.append(f"out={turn.output_tokens}")
    if turn.time_ms is not None:
        bits.append(f"{turn.time_ms}ms")
    return " ".join(bits)


def _answer(turn: Optional[Turn]) -> str:
    if turn is None:
        return "(untried)"
    if turn.status == TurnStatus.ok:
        return turn.text
    if turn.status == TurnStatus.skipped_non_vision:
        return "(skipped — model is not vision-capable)"
    err = turn.error
    detail = f"{err.type}" + (f" [{err.code}]" if err and err.code else "") if err else ""
    return f"(failed: {detail} {err.message if err else ''})".strip()


def comparison_text(session: ConsultationSession, *, max_chars: int = 2000) -> str:
    """Plain-text side-by-side of the latest answer per model."""
    lines = [f"Consultation {session.id} — {len(session.roster)} model(s)", ""]
    for model_id in session.roster:
        turn = _latest_assistant(session, model_id)
        status = turn.status.value if turn else "untried"
        usage = _usage(turn)
        header = f"── {model_id} [{status}]" + (f"  ({usage})" if usage else "")
        lines.append(header)
        body = _answer(turn)
        if len(body) > max_chars:
            body = body[:max_chars] + " …[truncated]"
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


def comparison_table(session: ConsultationSession, *, max_chars: int = 600):
    """A ``rich.table.Table`` comparing the latest answer per model (TUI)."""
    from rich.table import Table

    table = Table(title=f"Consultation {session.id}", show_lines=True)
    table.add_column("Model", style="cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Usage", no_wrap=True)
    table.add_column("Answer")

    status_style = {
        TurnStatus.ok: "green",
        TurnStatus.failed: "red",
        TurnStatus.skipped_non_vision: "yellow",
        TurnStatus.pending: "dim",
    }
    for model_id in session.roster:
        turn = _latest_assistant(session, model_id)
        status = turn.status if turn else None
        status_label = status.value if status else "untried"
        style = status_style.get(status, "dim")
        body = _answer(turn)
        if len(body) > max_chars:
            body = body[:max_chars] + " …"
        table.add_row(model_id, f"[{style}]{status_label}[/{style}]", _usage(turn), body)
    return table
