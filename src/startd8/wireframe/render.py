"""Wireframe rendering + serialization + persistence (FR-W9, FR-W10, FR-W12).

JSON contract (FR-W10): integer ``schema_version``; canonical body is byte-identical for the
same inputs (FR-W2 — stable key order, project-relative forward-slash paths); audit metadata
lives in ``_meta`` and is excluded from the canonical body, the determinism tests, and the
``inputs_fingerprint`` (R5-F1/R5-S1).

Stability policy (R1-F2): renaming/removing any non-``_meta`` field, or changing its type,
bumps ``SCHEMA_VERSION``; additive optional fields do not.

History: v2 adds the always-present ``content_completeness`` rollup (FR-WCI-2) — a new top-level
canonical field that every consumer now sees, so it bumps the version (not a conditional/optional add).
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

SCHEMA_VERSION = 3  # v3: content_completeness gains `form_help` (FR-FH-9), changing the `overall` rollup

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

# FR-SV-13: tool-level meta header — single-sourced for both the Rich and markdown renderers.
# What the wireframe IS, why it's the cheapest correction point, and how it's produced.
WIREFRAME_META = (
    "Previews the deterministic $0 generation your manifests will produce — before any code is written.",
    "Why: approve the shape here (the DATA MODEL bookend) — the cheapest correction; a wrong contract is the most expensive to fix.",
    "How: deterministic projection from the contract + conventions. No LLM.",
)


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
        "content_completeness": plan.content_coverage.as_dict(),   # FR-WCI-2
        "claimed_paths": list(plan.claimed_paths),
        "inputs_fingerprint": _inputs_fingerprint(plan),
        "delivery_inventory": delivery_inventory(plan),
    }


def run_linkage(run_dir: Path) -> Optional[Dict[str, object]]:
    """FR-WPI-7 linkage block for ``--from-run`` mode: prose → extraction → manifest →
    wireframe, traceable end to end. Reads the extraction REPORT (which carries the kickoff-doc
    checksums) — never the seed's JSON body; the seed is hashed as an opaque file (the
    no-seed-coupling non-requirement stands)."""
    run_dir = Path(run_dir)
    report_path = run_dir / "manifest-extraction-report.json"
    if not report_path.is_file():
        return None
    report_bytes = report_path.read_bytes()
    out: Dict[str, object] = {
        "run_dir": str(run_dir),
        "extraction_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
    }
    try:
        out["source_doc_checksums"] = json.loads(report_bytes).get("source_docs", {})
    except json.JSONDecodeError:
        out["source_doc_checksums"] = {}
    manifests_dir = run_dir / "manifests"
    if manifests_dir.is_dir():
        out["manifest_sha256s"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(manifests_dir.iterdir()) if p.is_file()
        }
    seed = run_dir / "prime-context-seed.json"
    if seed.is_file():
        out["seed_sha256"] = hashlib.sha256(seed.read_bytes()).hexdigest()
    return out


def plan_to_json(
    plan: WireframePlan,
    *,
    emit_context: str = "cli",
    linkage: Optional[Dict[str, object]] = None,
) -> str:
    """Full JSON: canonical body + ``_meta`` audit object (excluded from determinism).

    *linkage* (FR-WPI-7, ``--from-run`` mode) joins the canonical body — it is deterministic
    for identical run inputs, so it participates in byte-identity; additive, ``schema_version``
    stays 1."""
    body = plan_body(plan)
    if linkage:
        body["run_linkage"] = linkage
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


# FR-AUD terminal narration order + labels. Only non-empty fields render, so the architect voice
# (what/why/do/next) is byte-identical to the pre-audience output and the end_user voice shows its own
# DOES/WON'T/NEED framing. Spacing aligns the values to a common column.
_DESCRIBE_FIELD_LABELS = (
    ("what", "WHAT: "),
    ("why", "WHY:  "),
    ("wont", "WON'T: "),
    ("need", "NEED:  "),
    ("do", "DO:   "),
    ("next", "NEXT: "),
)


def _section_node(
    tree: Tree, section: WireframeSection, *, max_items: int, described: Optional[dict] = None
) -> None:
    node = tree.add(f"[bold]{section.title}[/bold] {_status_tag(section.status)}")
    # FR-DL-6/7: the authored WHAT · WHY · DO narration (opt-in --describe), single-sourced from
    # descriptive.yaml — printed under the section header, BEFORE items, in one consistent shape.
    if described:
        # Voice-aware (FR-AUD): render whichever authored fields the audience actually carries, in a
        # fixed order. The architect base authors what/why/do/next (wont/need empty ⇒ skipped) ⇒ output is
        # byte-identical to before this became audience-aware; the end_user voice authors what/wont/need/do.
        for field, label in _DESCRIBE_FIELD_LABELS:
            val = described.get(field)
            if val:
                node.add(f"[dim italic]{label}{val}[/dim italic]")
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


# FR-WPI-9: static section→iteration map (planning finding: manifests carry no phase tags and
# don't need them). AI-layer items within Services belong to iteration ③ (integration+content).
_ITERATION_BY_SECTION = {
    "scaffold": 1, "services": 1, "entities": 1, "deployment": 1,  # ① framework + persistence
    "forms": 2, "pages": 2, "views": 2, "display": 2, "completeness": 2,  # ② display + business logic
    "content": 3,                                           # ③ integration + content
}
_ITERATION_TITLES = {
    1: "① framework + persistence",
    2: "② display + business logic",
    3: "③ integration + content",
}


def _item_iteration(section_key: str, item_label: str) -> int:
    if section_key == "services" and item_label.startswith("AI "):
        return 3
    return _ITERATION_BY_SECTION.get(section_key, 2)


def delivery_inventory(plan: WireframePlan) -> List[dict]:
    """FR-WPI-9: the walkthrough artifact — what will be delivered, per iteration phase."""
    groups: Dict[int, List[dict]] = {1: [], 2: [], 3: []}
    for section in plan.sections:
        for item in section.items:
            groups[_item_iteration(section.key, item.label)].append({
                "label": item.label,
                "status": item.status,
                "section": section.key,
                "detail": item.detail,
            })
    return [
        {"iteration": i, "title": _ITERATION_TITLES[i], "items": groups[i]}
        for i in (1, 2, 3)
    ]


def render_delivery_inventory(plan: WireframePlan, console: Console, *, max_items: int = 25) -> None:
    tree = Tree("[bold]Delivery inventory[/bold] (walk per iteration — FR-WPI-9)")
    for group in delivery_inventory(plan):
        node = tree.add(f"[bold]{group['title']}[/bold]")
        items = group["items"]
        shown = items if max_items <= 0 else items[:max_items]
        for item in shown:
            line = f"{item['label']} {_status_tag(item['status'])}"
            if item["detail"]:
                line += f" — {item['detail']}"
            node.add(line)
        if max_items > 0 and len(items) > max_items:
            node.add(f"[dim]… and {len(items) - max_items} more[/dim]")
    console.print(tree)


def _content_line(plan: WireframePlan) -> str:
    """FR-WCI-2 glance signal: overall authored-% + per-surface authored/total. Honest-skip —
    surfaces with ``total == 0`` are omitted; an all-empty plan reads ``n/a`` (no divide-by-zero)."""
    cc = plan.content_coverage
    surfaces = (
        ("pages", cc.page_bodies),
        ("view-copy", cc.view_copy),
        ("prompts", cc.ai_prompts),
        ("form-help", cc.form_help),
    )
    parts = [f"{label} {st.authored}/{st.total}" for label, st in surfaces if st.total > 0]
    overall = cc.overall
    if overall.total == 0:
        return "n/a"
    return f"{round(overall.ratio * 100)}% authored — " + " · ".join(parts)


def footer_lines(plan: WireframePlan) -> Tuple[str, str, str, str]:
    """The four footer lines (FR-W9, FR-WCI-2): counts, shape summary, content coverage, cascade."""
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
    content = _content_line(plan)
    readiness = " | ".join(f"{k}: {v}" for k, v in plan.readiness.items())
    return counts, shape, content, readiness


def render_plan(
    plan: WireframePlan,
    console: Optional[Console] = None,
    *,
    only_issues: bool = False,
    max_items: int = 25,
    describe: bool = False,
    role: str = "architect",
    fluency: str = "intermediate",
) -> None:
    """Render the inverted pyramid (FR-SV-12): title → tool-meta (FR-SV-13) → summary block →
    detail tree. ``only_issues`` hides `planned` sections; the summary always reports full-plan
    totals (R2-F4).

    ``describe`` (opt-in, FR-DL-*) augments each section with its authored narration from
    ``descriptive.yaml``. ``role``/``fluency`` (FR-AUD) select the voice — the default
    ``(architect, intermediate)`` is byte-identical to before either flag existed; ``end_user`` and the
    delivery-role kits render their own plain / lensed narration on the terminal tree, not just ``--html``."""
    console = console or Console()
    # Title + tool-level meta header (FR-SV-13) — what this is, up top. The WIREFRAME_META lines are
    # architect tool-process framing ($0/no-LLM/deterministic) — the exact FR-AUD-C1b process-meta the
    # plain voices must not see (R2-F1); shown for the architect voice only, mirroring compose().
    console.print(f"[bold]Wireframe[/bold] — {plan.project_root}")
    if role == "architect":
        for line in WIREFRAME_META:
            console.print(f"[dim italic]{line}[/dim italic]")
    # Summary block first (FR-SV-12) — counts, shape, content, readiness before the details.
    counts, shape, content, readiness = footer_lines(plan)
    console.print(f"\n[bold]Status:[/bold]  {counts}")
    console.print(f"[bold]Shape:[/bold]   {shape}")
    console.print(f"[bold]Content:[/bold] {content}")
    console.print(f"[bold]Cascade:[/bold] {readiness}")
    if describe:  # FR-DL-12: route the summary header through the descriptive layer — the counts' meaning
        from .delivery_roles import lens_for
        from .describe import describe_summary
        lens = lens_for(role)  # FR-AUD/EC-4: a delivery-role kit's focus lens, shown on the terminal too
        if lens:
            console.print(f"[dim italic]FOCUS ({role}): {lens}[/dim italic]")
        _s = describe_summary(plan, role=role, fluency=fluency)
        if _s:
            # Voice-aware: the architect base authors why/do (byte-identical); the end_user voice authors
            # a headline/lead intro instead — render whichever the selected voice actually carries.
            if _s.get("why"):
                console.print(f"[dim italic]WHY:  {_s['why']}[/dim italic]")
            if _s.get("do"):
                console.print(f"[dim italic]DO:   {_s['do']}[/dim italic]")
            if _s.get("headline"):
                console.print(f"[dim italic]{_s['headline']}[/dim italic]")
            if _s.get("lead"):
                console.print(f"[dim italic]{_s['lead']}[/dim italic]")
    for w in plan.merge_warnings:
        console.print(f"[yellow]warning:[/yellow] {_warning_text(w)}")
    # Detail tree below the summary, behind a visual separator.
    console.print()
    tree = Tree("[bold]Details ▾[/bold] [dim](per-section shape)[/dim]")
    described_by_key = _describe_sections(plan, role=role, fluency=fluency) if describe else {}
    for section in plan.sections:
        if only_issues and section.status == Status.PLANNED:
            continue
        _section_node(
            tree, section, max_items=max_items,
            described=described_by_key.get(section.key),
        )
    console.print(tree)


def _describe_sections(
    plan: WireframePlan, *, role: str = "architect", fluency: str = "intermediate"
) -> Dict[str, dict]:
    """FR-DL-*: compose the authored narration for every section, keyed by section key, in the FR-AUD
    ``role``/``fluency`` voice (default architect ⇒ byte-identical to the pre-audience output).

    Deterministic, no-LLM (the composer is pure). Imported lazily so the descriptive layer is a
    strictly opt-in dependency of the ``--describe`` path — the default render never loads it."""
    from .describe import describe as describe_section

    out: Dict[str, dict] = {}
    for section in plan.sections:
        composed = describe_section(section, plan, role=role, fluency=fluency)
        if composed is not None:
            out[section.key] = composed
    return out


def _warning_text(w: Dict[str, str]) -> str:
    """One line for either warning shape: inputs-merge overwrite or override/disk conflict."""
    if "message" in w:
        return w["message"]
    return f"`{w['key']}` {w['previous_path']} → {w['new_path']} ({w['source_file']})"


def plan_to_markdown(plan: WireframePlan) -> str:
    """Human-readable summary for pipeline output (R1-S3). Inverted pyramid (FR-SV-12): meta
    header + summary first, section detail below."""
    lines: List[str] = [f"# Wireframe — {plan.project_root}", ""]
    # Tool-level meta header (FR-SV-13) — single-sourced from WIREFRAME_META.
    for line in WIREFRAME_META:
        lines.append(f"_{line}_")
    lines.append("")
    # Summary block first (FR-SV-12).
    counts, shape, content, readiness = footer_lines(plan)
    lines.extend([
        f"**Status:** {counts}", f"**Shape:** {shape}",
        f"**Content:** {content}", f"**Cascade:** {readiness}",
    ])
    for w in plan.merge_warnings:
        lines.append(f"- WARNING: {_warning_text(w)}")
    lines.append("")
    lines.append("## Delivery inventory (per iteration — the walkthrough)")
    lines.append("")
    for group in delivery_inventory(plan):
        lines.append(f"### {group['title']}")
        for item in group["items"]:
            detail = f" — {item['detail']}" if item["detail"] else ""
            lines.append(f"- {item['label']} `[{_STATUS_LABEL[item['status']]}]`{detail}")
        lines.append("")
    lines.append("## Sections")
    lines.append("")
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
    linkage: Optional[Dict[str, object]] = None,
) -> Dict[str, Optional[Path]]:
    """Persist ``wireframe-plan.json`` (+ optional ``wireframe-summary.md``) atomically.

    Advisory contract (FR-W12): an unwritable target degrades to a warning — never raises.
    Returns the written paths (values ``None`` when a write was skipped).
    """
    out: Dict[str, Optional[Path]] = {"json": None, "markdown": None}
    json_path = target_dir / "wireframe-plan.json"
    try:
        _atomic_write(json_path, plan_to_json(plan, emit_context=emit_context, linkage=linkage))
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
