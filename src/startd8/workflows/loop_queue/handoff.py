# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""VASI Drain Hand-off writers — JSON + optional markdown card (OQ-11)."""

from __future__ import annotations

from pathlib import Path

from .models import DrainHandoff
from .storage import LoopQueueStorage


def render_handoff_markdown(handoff: DrainHandoff) -> str:
    """Short human card for chat-paste vendors (OQ-11 settled: JSON + markdown)."""
    sources = "\n".join(f"- `{p}`" for p in handoff.source_paths)
    criteria = "\n".join(
        f"- `{key}`: {value}" for key, value in sorted(handoff.success_criteria.items())
    )
    warning = ""
    if handoff.budget_warning:
        warning = f"\n**Budget warning:** {handoff.budget_warning}\n"
    return (
        f"# WLQ Drain Hand-off — `{handoff.job_id}`\n\n"
        f"**Surface:** `{handoff.surface_id}`  \n"
        f"**Loop:** `{handoff.loop_id}`  \n"
        f"**Round:** R{handoff.round_number}\n"
        f"{warning}\n"
        f"## Do this\n\n"
        f"1. Open `{handoff.bundle_path}` and follow it with filesystem write tools.\n"
        f"2. Write only the source paths listed below.\n"
        f"3. Write confirmation JSON to `{handoff.status_writeback_path}`.\n"
        f"4. Run `startd8 wloop run-next --job-id {handoff.job_id}`.\n\n"
        f"## Source paths\n\n{sources}\n\n"
        f"## Success criteria\n\n{criteria}\n\n"
        f"Chat/UI reply should be a short confirmation only.\n"
    )


def persist_drain_handoff(
    storage: LoopQueueStorage,
    job_id: str,
    handoff: DrainHandoff,
) -> DrainHandoff:
    """Write JSON hand-off + markdown card; return hand-off with card path set."""
    artifact_dir = storage.artifact_dir(job_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    card_path = artifact_dir / "drain-handoff.md"
    card_path.write_text(render_handoff_markdown(handoff), encoding="utf-8")
    updated = handoff.model_copy(
        update={"markdown_card_path": str(card_path.resolve())}
    )
    storage.write_json_artifact(
        job_id, "drain-handoff.json", updated.model_dump(mode="json")
    )
    return updated
