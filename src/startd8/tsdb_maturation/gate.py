"""M4 — Gate wiring (FR-7).

Validates an inferred graph through the **reused** emit gate (``emit_schema_draft`` →
``promote_schema``) and flips ``prisma/schema.prisma`` only on pass. Everything structural here is
already-gated machinery; M4 adds three TSDB-specific policies:

* **Empty materialization → refuse** (OQ-6): a specimen with no records never promotes.
* **M2.5 confirmation enforced**: the inferred identity must be human-confirmed (or STALE after a
  key change) before promotion — the safeguard against a wrong key silently overwriting on backfill.
* **Greenfield vs re-promote gate**: greenfield (no live contract) → round-trip + non-empty +
  no-unrenderable; a re-promote against an existing contract additionally computes **parity drift**
  (schema evolution). An un-typeable label surfaces as ``UnrenderableField`` — never silently dropped.

Returns a :class:`PromotionResult` for every policy outcome (never raises on a refusal) so a CLI
can render the reason and map it to an exit code uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from startd8.logging_config import get_logger
from startd8.manifest_extraction.prisma_emitter import (
    EmitGateResult,
    emit_schema_draft,
    promote_schema,
)

from .confirmation import ConfirmationStatus, confirmation_status, render_confirmation_surface
from .infer import InferenceResult
from .specimen import Specimen

logger = get_logger(__name__)

DEFAULT_SCHEMA_REL = "prisma/schema.prisma"


@dataclass(frozen=True)
class PromotionResult:
    """The outcome of a gate-and-promote attempt."""

    promoted: bool
    reason: str                                   # "promoted" or why it was refused
    confirmation: ConfirmationStatus
    gate: Optional[EmitGateResult]                # None when refused before the emit gate ran
    schema_path: Optional[str] = None             # the flipped contract path, when promoted
    surface: str = ""                             # the human-facing identity/gate surface

    @property
    def refused(self) -> bool:
        return not self.promoted


def _read_live(schema_path: Path) -> Optional[str]:
    """The existing contract text (re-promote parity source), or None for greenfield."""
    if schema_path.is_file():
        return schema_path.read_text(encoding="utf-8")
    return None


def gate_and_promote(
    result: InferenceResult,
    specimen: Specimen,
    *,
    metric: str,
    project_root: Union[str, Path],
    run_dir: Union[str, Path],
    schema_rel: str = DEFAULT_SCHEMA_REL,
    require_confirmed: bool = True,
) -> PromotionResult:
    """Gate the inferred schema and, on pass, flip ``prisma/schema.prisma`` (FR-7).

    ``run_dir`` is where the gated draft is emitted (never the project tree until promote).
    ``require_confirmed`` gates on the M2.5 confirmation ledger (default on; a ``--force`` caller
    may disable it, but the surface still reports the status).
    """
    project_root = Path(project_root)
    schema_path = project_root / schema_rel
    status = confirmation_status(project_root, metric, result.identity_fields)
    surface = render_confirmation_surface(result, status=status)

    # 1. Refuse empty materialization (OQ-6) — before any gate/confirmation work.
    if specimen.n_records == 0:
        return PromotionResult(
            promoted=False,
            reason=f"empty materialization for {metric!r} — refusing to promote (OQ-6)",
            confirmation=status, gate=None, surface=surface,
        )

    # 2. Enforce the M2.5 confirmation gate (unless explicitly disabled).
    if require_confirmed and status is not ConfirmationStatus.CONFIRMED:
        detail = (
            "identity changed since it was confirmed — re-confirm before promoting"
            if status is ConfirmationStatus.STALE
            else "inferred identity is not confirmed — review and confirm before promoting"
        )
        return PromotionResult(
            promoted=False,
            reason=f"confirmation required ({status.value}): {detail}",
            confirmation=status, gate=None, surface=surface,
        )

    # 3. The reused emit gate — greenfield (None) or re-promote parity (live_text).
    live_text = _read_live(schema_path)
    gate = emit_schema_draft(
        result.graph, str(run_dir), live_text=live_text, source_file=schema_rel
    )
    if not gate.ok:
        return PromotionResult(
            promoted=False,
            reason=_refusal_reason(gate),
            confirmation=status, gate=gate, surface=surface,
        )

    # 4. Promote — the human-triggered flip of the project contract.
    promoted_path = promote_schema(str(run_dir), str(schema_path))
    logger.info("promoted tsdb schema for %s → %s", metric, promoted_path)
    return PromotionResult(
        promoted=True, reason="promoted", confirmation=status, gate=gate,
        schema_path=promoted_path, surface=surface,
    )


def _refusal_reason(gate: EmitGateResult) -> str:
    """Explain a failed emit gate (unrenderable / structural errors / parity drift)."""
    if gate.unrenderable:
        cols = ", ".join(f"{u.entity}.{u.field}" for u in gate.unrenderable)
        return f"un-typeable field(s) [{cols}] — refusing (never silently dropped, FR-7)"
    if gate.errors:
        return f"structural error(s): {list(gate.errors)}"
    if not gate.round_trips:
        return "schema did not round-trip — refusing to promote"
    if gate.parity_drift:
        return f"parity drift vs the existing contract (re-promote): {list(gate.parity_drift)}"
    return "emit gate refused promotion"
