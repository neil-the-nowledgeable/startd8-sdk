"""Side-by-side comparison rendering for a consultation (M3.3 / FR-MMC-10).

Two renderers over the same data so the TUI and CLI stay consistent:
* :func:`comparison_text` — plain text (CLI + tests), no rich dependency.
* :func:`comparison_table` — a ``rich.table.Table`` (TUI).

Both show the **latest** assistant answer per model with its status and per-turn token/latency
signal (image-token cost is included since it flows the cost hook, M2.5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import ConsultationSession, Turn, TurnRole, TurnStatus
from ._webview_template import WEBVIEW_TEMPLATE


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


# ── Web view (FR-WUI) ─────────────────────────────────────────────────────────
def _safe_image(ref) -> dict:
    """Persist-safe image indicator: **basename only** (never the absolute path, FR-WUI-9)."""
    filename = Path(ref.source_path).name if ref.source_path else "(pasted image)"
    return {"filename": filename, "sha256_short": (ref.sha256 or "")[:8], "mime_type": ref.mime_type}


def _turn_payload(turn: Turn) -> dict:
    """Serialize one Turn to the client renderer's shape (only the fields it reads)."""
    d: dict = {"role": turn.role.value, "status": turn.status.value}
    if turn.text:
        d["text"] = turn.text
    if turn.images:
        d["images"] = len(turn.images)
    if turn.error is not None:
        d["error"] = {"type": turn.error.type, "code": turn.error.code, "message": turn.error.message}
    for field in ("input_tokens", "output_tokens", "time_ms"):
        val = getattr(turn, field, None)
        if val is not None:
            d[field] = val
    return d


def _session_payload(session: ConsultationSession) -> dict:
    return {
        "id": session.id,
        "prompt": session.prompt,
        "roster": list(session.roster),
        "images": [_safe_image(i) for i in session.images],
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "turns_by_model": {
            model_id: [_turn_payload(t) for t in session.turns_by_model.get(model_id, [])]
            for model_id in session.roster
        },
    }


def _embed_json(obj) -> str:
    """JSON safe to embed in a ``<script type=application/json>`` block (escape ``<``)."""
    return json.dumps(obj, ensure_ascii=True).replace("<", "\\u003c")


def render_html(session: ConsultationSession, serve: Optional[dict] = None, csp_nonce: str = "") -> str:
    """Render a standalone HTML view of a consultation (FR-WUI + FR-SRV-2/10).

    A sibling of :func:`comparison_text`/:func:`comparison_table` (same data, third surface).
    The client-side template escapes untrusted model text before rendering markdown (FR-WUI-9);
    here we additionally neutralize ``<`` in the **embedded JSON** so a ``</script>`` inside any
    answer cannot terminate the ``<script type="application/json">`` container. Image refs carry
    basename only, never the absolute source path.

    ``serve`` (FR-SRV): when a serve-config dict is passed (token + endpoints + nonce), an interactive
    ``#serve-config`` block is injected and the CSP nonce is stamped onto the executable ``<script>``
    so the served page can run under a strict `script-src 'nonce-…'` policy. When ``serve is None`` the
    output is **byte-identical** to the static file (FR-SRV-10) — no token, endpoint, or nonce leaks in.
    """
    html = WEBVIEW_TEMPLATE.replace("__SESSION_JSON__", _embed_json(_session_payload(session)))
    if serve is None:
        return html  # static path — unchanged (byte-identity guarantee)

    # Interactive: inject the serve-config data block just before the session data.
    cfg_block = (
        '<script type="application/json" id="serve-config">\n'
        + _embed_json(serve)
        + "\n</script>\n"
    )
    html = html.replace(
        '<script type="application/json" id="session-data">',
        cfg_block + '<script type="application/json" id="session-data">',
        1,
    )
    # Stamp the CSP nonce onto the executable script (the JSON data blocks are non-executable and
    # need no nonce under script-src). Leaves everything else untouched.
    if csp_nonce:
        html = html.replace("<script>\n(function(){", f'<script nonce="{csp_nonce}">\n(function(){{', 1)
    return html
