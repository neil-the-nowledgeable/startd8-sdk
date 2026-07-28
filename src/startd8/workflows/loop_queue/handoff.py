# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""VASI Drain Hand-off writers — JSON + optional markdown card (OQ-11)."""

from __future__ import annotations

from typing import Dict

from .models import DrainHandoff
from .prompt_loader import load_prompt_text, substitute_slots
from .storage import LoopQueueStorage


def render_handoff_markdown(handoff: DrainHandoff) -> str:
    """Short human card for chat-paste vendors (OQ-11 settled: JSON + markdown).

    Templates live under ``loop_queue/prompts/drain-handoff*.md`` (override via
    ``$STARTD8_WLQ_HANDOFF_*`` env vars — see ``prompt_loader.PROMPT_ENV``).
    Unknown ``{{slot}}`` names fail closed (``ValueError``).
    """
    sources = "\n".join(f"- `{p}`" for p in handoff.source_paths)
    criteria = "\n".join(
        f"- `{key}`: {value}" for key, value in sorted(handoff.success_criteria.items())
    )
    budget_warning = ""
    if handoff.budget_warning:
        budget_warning = f"\n**Budget warning:** {handoff.budget_warning}\n"

    base_slots: Dict[str, str] = {
        "job_id": handoff.job_id,
        "surface_id": handoff.surface_id,
        "loop_id": handoff.loop_id,
        "round_number": str(handoff.round_number),
        "bundle_path": handoff.bundle_path,
        "status_writeback_path": handoff.status_writeback_path,
        "source_paths": sources,
        "success_criteria": criteria,
        "budget_warning": budget_warning,
    }

    reviewer = handoff.assigned_reviewer
    if reviewer and reviewer.mode == "blind_rotate" and reviewer.model:
        do_slots = {
            **base_slots,
            "reviewer_model": reviewer.model,
            "roster_index": (
                "" if reviewer.roster_index is None else str(reviewer.roster_index)
            ),
        }
        do_this = substitute_slots(
            load_prompt_text("drain-handoff-do-this-blind-rotate.md"),
            do_slots,
            label="drain-handoff-do-this-blind-rotate.md",
        )
        reviewer_block = substitute_slots(
            load_prompt_text("drain-handoff-reviewer-block.md"),
            {
                "reviewer_model": reviewer.model,
                "reviewer_roster": ", ".join(f"`{m}`" for m in reviewer.roster),
            },
            label="drain-handoff-reviewer-block.md",
        )
    else:
        do_this = substitute_slots(
            load_prompt_text("drain-handoff-do-this-current.md"),
            base_slots,
            label="drain-handoff-do-this-current.md",
        )
        reviewer_block = ""

    return substitute_slots(
        load_prompt_text("drain-handoff.md"),
        {
            **base_slots,
            "do_this": do_this.rstrip() + "\n",
            "reviewer_block": (
                reviewer_block.rstrip() + "\n" if reviewer_block else ""
            ),
        },
        label="drain-handoff.md",
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
    try:
        card_path.write_text(render_handoff_markdown(handoff), encoding="utf-8")
    except (ValueError, FileNotFoundError, OSError, UnicodeDecodeError) as e:
        raise RuntimeError(
            f"failed to render drain hand-off markdown for {job_id!r}: {e}"
        ) from e
    updated = handoff.model_copy(
        update={"markdown_card_path": str(card_path.resolve())}
    )
    storage.write_json_artifact(
        job_id, "drain-handoff.json", updated.model_dump(mode="json")
    )
    return updated
