"""Wireframe rendering + serialization + persistence (FR-W9, FR-W10, FR-W12).

JSON contract (FR-W10): integer ``schema_version``; canonical body is byte-identical for the
same inputs (FR-W2 — stable key order, project-relative forward-slash paths); audit metadata
lives in ``_meta`` and is excluded from the canonical body, the determinism tests, and the
``inputs_fingerprint`` (R5-F1/R5-S1).

Stability policy (R1-F2): renaming/removing any non-``_meta`` field, or changing its type,
bumps ``SCHEMA_VERSION``; additive optional fields do not.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.tree import Tree

from ..logging_config import get_logger
from .plan import Status, WireframePlan, WireframeSection

logger = get_logger(__name__)

SCHEMA_VERSION = 1

_STATUS_STYLE = {
    Status.PLANNED: "green",
    Status.DEFAULTS: "cyan",
    Status.PLACEHOLDER: "yellow",
    Status.NOT_DEFINED: "dim",
    Status.INVALID: "red",
}

_STATUS_LABEL = {
    Status.PLANNED: "planned",
    Status.DEFAULTS: "defaults",
    Status.PLACEHOLDER: "placeholder",
    Status.NOT_DEFINED: "not defined",
    Status.INVALID: "INVALID",
}


# --------------------------------------------------------------------------- #
# JSON (FR-W10, FR-W12)
# --------------------------------------------------------------------------- #

def _inputs_fingerprint(plan: WireframePlan) -> str:
    """Stable hash over each catalog entry's resolved path + content SHA-256 (R3-F2).

    Deterministic across hosts: paths are project-relative posix; absent files hash as
    ``absent``. Excludes ``_meta`` by construction.
    """
    root = Path(plan.project_root)
    parts: List[str] = []
    for key in sorted(plan.input_provenance):
        rel = plan.input_provenance[key]["resolved_path"]
        target = root / rel
        if target.is_file():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        else:
            digest = "absent"
        parts.append(f"{key}:{rel}:{digest}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def plan_body(plan: WireframePlan) -> dict:
    """The canonical (deterministic, ``_meta``-free) JSON body (FR-W2)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "input_provenance": plan.input_provenance,
        "merge_warnings": list(plan.merge_warnings),
        "sections": [asdict(s) for s in plan.sections],
        "shape": plan.shape,
        "readiness": plan.readiness,
        "status_counts": plan.status_counts,
        "claimed_paths": list(plan.claimed_paths),
        "inputs_fingerprint": _inputs_fingerprint(plan),
    }


def plan_to_json(plan: WireframePlan, *, emit_context: str = "cli") -> str:
    """Full JSON: canonical body + ``_meta`` audit object (excluded from determinism)."""
    body = plan_body(plan)
    body["_meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "startd8_version": _sdk_version(),
        "emit_context": emit_context,
        "project_root": plan.project_root,
    }
    return json.dumps(body, sort_keys=True, indent=2) + "\n"


def canonical_json(plan: WireframePlan) -> str:
    """The byte-identical-across-runs serialization (FR-W2 acceptance surface)."""
    return json.dumps(plan_body(plan), sort_keys=True, indent=2) + "\n"


def _sdk_version() -> str:
    try:
        from importlib.metadata import version

        return version("startd8")
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------- #
# Rich rendering (FR-W9)
# --------------------------------------------------------------------------- #

def _status_tag(status: str) -> str:
    return f"[{_STATUS_STYLE[status]}]\\[{_STATUS_LABEL[status]}][/{_STATUS_STYLE[status]}]"


def _section_node(tree: Tree, section: WireframeSection, *, max_items: int) -> None:
    node = tree.add(f"[bold]{section.title}[/bold] {_status_tag(section.status)}")
    if section.consequence:
        node.add(f"[italic]→ {section.consequence}[/italic]")
    if section.error:
        suffix = " …(truncated)" if section.error_truncated else ""
        node.add(f"[red]{section.error}{suffix}[/red]")
    items = section.items
    shown = items if max_items <= 0 else items[:max_items]
    for item in shown:
        line = f"{item.label} {_status_tag(item.status)}"
        if item.detail:
            line += f" — {item.detail}"
        node.add(line)
    if max_items > 0 and len(items) > max_items:
        node.add(f"[dim]… and {len(items) - max_items} more[/dim]")


def footer_lines(plan: WireframePlan) -> Tuple[str, str, str]:
    """The three footer lines (FR-W9): counts, shape summary, cascade readiness."""
    c = plan.status_counts
    counts = (
        f"{c.get(Status.PLANNED, 0)} planned / {c.get(Status.DEFAULTS, 0)} defaults / "
        f"{c.get(Status.PLACEHOLDER, 0)} placeholder / {c.get(Status.NOT_DEFINED, 0)} not defined / "
        f"{c.get(Status.INVALID, 0)} invalid"
    )
    s = plan.shape
    shape = (
        f"Entities: {s['entities']} | CRUD routes: {s['crud_routes']} | Pages: {s['pages']} | "
        f"Views: {s['views']} | AI passes: {s['ai_passes']}"
    )
    readiness = " | ".join(f"{k}: {v}" for k, v in plan.readiness.items())
    return counts, shape, readiness


def render_plan(
    plan: WireframePlan,
    console: Optional[Console] = None,
    *,
    only_issues: bool = False,
    max_items: int = 25,
) -> None:
    """Render the Rich tree + footer (FR-W9). ``only_issues`` hides `planned` sections; the
    footer always reports full-plan totals (R2-F4)."""
    console = console or Console()
    tree = Tree(f"[bold]Wireframe[/bold] — {plan.project_root}")
    for section in plan.sections:
        if only_issues and section.status == Status.PLANNED:
            continue
        _section_node(tree, section, max_items=max_items)
    console.print(tree)
    counts, shape, readiness = footer_lines(plan)
    console.print(f"\n[bold]Status:[/bold]  {counts}")
    console.print(f"[bold]Shape:[/bold]   {shape}")
    console.print(f"[bold]Cascade:[/bold] {readiness}")
    for w in plan.merge_warnings:
        console.print(f"[yellow]warning:[/yellow] {_warning_text(w)}")


def _warning_text(w: Dict[str, str]) -> str:
    """One line for either warning shape: inputs-merge overwrite or override/disk conflict."""
    if "message" in w:
        return w["message"]
    return f"`{w['key']}` {w['previous_path']} → {w['new_path']} ({w['source_file']})"


def plan_to_markdown(plan: WireframePlan) -> str:
    """Human-readable summary for pipeline output (R1-S3)."""
    lines: List[str] = [f"# Wireframe — {plan.project_root}", ""]
    for section in plan.sections:
        lines.append(f"## {section.title} `[{_STATUS_LABEL[section.status]}]`")
        if section.consequence:
            lines.append(f"> {section.consequence}")
        if section.error:
            lines.append(f"> ERROR: {section.error}{' …(truncated)' if section.error_truncated else ''}")
        for item in section.items:
            detail = f" — {item.detail}" if item.detail else ""
            lines.append(f"- {item.label} `[{_STATUS_LABEL[item.status]}]`{detail}")
        lines.append("")
    counts, shape, readiness = footer_lines(plan)
    lines.extend([f"**Status:** {counts}", f"**Shape:** {shape}", f"**Cascade:** {readiness}"])
    for w in plan.merge_warnings:
        lines.append(f"- WARNING: {_warning_text(w)}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Persistence (FR-W12 — atomic, advisory)
# --------------------------------------------------------------------------- #

def _atomic_write(target: Path, content: str) -> None:
    """Temp file + ``os.replace`` in the target dir — never a partial file on disk (R6-F4)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def persist_plan(
    plan: WireframePlan,
    target_dir: Path,
    *,
    emit_context: str = "cli",
    with_markdown: bool = False,
) -> Dict[str, Optional[Path]]:
    """Persist ``wireframe-plan.json`` (+ optional ``wireframe-summary.md``) atomically.

    Advisory contract (FR-W12): an unwritable target degrades to a warning — never raises.
    Returns the written paths (values ``None`` when a write was skipped).
    """
    out: Dict[str, Optional[Path]] = {"json": None, "markdown": None}
    json_path = target_dir / "wireframe-plan.json"
    try:
        _atomic_write(json_path, plan_to_json(plan, emit_context=emit_context))
        out["json"] = json_path
    except OSError as exc:
        logger.warning("wireframe: could not persist %s (%s) — continuing", json_path, exc)
    if with_markdown:
        md_path = target_dir / "wireframe-summary.md"
        try:
            _atomic_write(md_path, plan_to_markdown(plan))
            out["markdown"] = md_path
        except OSError as exc:
            logger.warning("wireframe: could not persist %s (%s) — continuing", md_path, exc)
    return out
