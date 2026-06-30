# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""VIPP orchestrator — ties negotiation to idempotency, the label gate, and events.

``run_vipp_negotiate`` reads a host proposal envelope (the FR-15 inbox), adjudicates each proposal
against project ground truth deterministically (`$0`), writes a source-labeled disposition report
under ``.startd8/vipp/``, and (optionally) appends an opt-in LLM narrative. One-shot and idempotent
(FR-18): a re-invocation on an unchanged inbox (same content modulo ``generated_at``/``envelope_seq``)
+ unchanged ground truth + SDK version is a no-op that returns the existing report.

Mirrors the FDE skeleton (``fde/assistant.py``): ``ensure_posting`` → fingerprint short-circuit →
deterministic core + opt-in narrative (re-gated by ``assert_all_labeled``) → write + record + notify.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..fde import deterministic_compose
from ..logging_config import get_logger
from . import compose, context, evaluate, notify
from .ground_truth import build_oracle
from .models import PROTOCOL_VERSION, ProposalEnvelope, VippReport, protocol_is_future

logger = get_logger(__name__)

DISPOSITIONS_MD = "dispositions.md"
DISPOSITIONS_JSON = "dispositions.json"


def _sdk_version() -> str:
    try:
        from .. import __version__

        return str(__version__)
    except Exception:  # pragma: no cover
        return "0.0.0"


@dataclass
class NegotiateOutcome:
    report: VippReport
    report_path: Path
    skipped: bool = False  # idempotent no-op


def run_vipp_negotiate(
    inbox_path: Path,
    *,
    project_root: Optional[Path] = None,
    narrative: bool = False,
    agent: Any = None,
    max_cost_usd: Optional[float] = None,
    emit: bool = True,
    write: bool = True,
    force: bool = False,
) -> NegotiateOutcome:
    """Adjudicate a host proposal envelope into a source-labeled disposition report (FR-3/4/6/18)."""
    inbox_path = Path(inbox_path)
    project_root = Path(project_root) if project_root else Path.cwd()
    sdk_version = _sdk_version()
    context.ensure_posting(project_root, sdk_version=sdk_version)

    envelope = ProposalEnvelope.from_json(inbox_path.read_text(encoding="utf-8"))
    if protocol_is_future(envelope.protocol_version):
        raise ValueError(
            f"VIPP cannot read a future envelope protocol "
            f"{envelope.protocol_version!r} (ours {PROTOCOL_VERSION}) — upgrade the SDK"
        )

    # Idempotency key (FR-18): inbox content EXCLUDING the volatile generated_at/envelope_seq, so a
    # re-serialize of unchanged proposals is a no-op (B-S1) + ground-truth checksum + SDK version.
    parts = {
        "inbox": context.checksum_json_excluding(
            inbox_path, exclude_keys=("generated_at", "envelope_seq")
        ),
        "ground_truth": context.ground_truth_checksum(project_root),
        "sdk_version": sdk_version,
        "narrative": str(bool(narrative and agent is not None)),
    }
    fp = context.fingerprint(parts)
    key = f"negotiate:{envelope.project_id}"
    out_dir = context.vipp_dir(project_root)
    report_path = out_dir / DISPOSITIONS_MD
    json_path = out_dir / DISPOSITIONS_JSON

    if (
        not force
        and report_path.exists()
        and json_path.exists()
        and context.already_processed(project_root, key, fp)
    ):
        logger.info("VIPP negotiate: inbox unchanged since last run — no-op")
        existing = VippReport.from_json(json_path.read_text(encoding="utf-8"))
        # Content-identical re-serialize with a bumped envelope_seq: re-stamp the CURRENT seq (without
        # re-evaluating) so a downstream applier's FR-18 stale-check matches the live inbox. The
        # fingerprint excludes envelope_seq, so the decisions are unchanged — only the seq advances
        # (code-review M3). Dispositions are frozen → rebuild via dataclasses.replace.
        if existing.envelope_seq != envelope.envelope_seq:
            existing.envelope_seq = envelope.envelope_seq
            existing.dispositions = [
                dataclasses.replace(d, envelope_seq=envelope.envelope_seq)
                for d in existing.dispositions
            ]
            if write:
                json_path.write_text(
                    json.dumps(existing.to_dict(), indent=2), encoding="utf-8"
                )
                report_path.write_text(existing.to_markdown(), encoding="utf-8")
        return NegotiateOutcome(existing, report_path, skipped=True)

    # Deterministic core ($0, no LLM).
    oracle = build_oracle(project_root)
    dispositions = evaluate.evaluate_envelope(envelope, oracle)
    evidence_available = any(
        c.source.startswith("sapper:") for d in dispositions for c in d.claims
    )
    report = VippReport(
        project_id=envelope.project_id,
        generated_at=context.utcnow(),
        envelope_seq=envelope.envelope_seq,
        dispositions=dispositions,
        evidence_available=evidence_available,
        sdk_version=sdk_version,
    )
    md = compose.render_dispositions(report)
    deterministic_compose.assert_all_labeled(md)  # FR-21 gate

    if narrative and agent is not None:
        md, cost, used = compose.enhance_narrative(
            md, envelope, agent=agent, max_cost_usd=max_cost_usd
        )
        report.cost_usd = cost
        report.llm_used = used
        deterministic_compose.assert_all_labeled(md)  # re-gate the narrative

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        report_path.write_text(md, encoding="utf-8")
        context.record_processed(project_root, key, fp, parts)

    if emit:
        notify.emit_negotiate_complete(
            envelope.project_id,
            str(report_path),
            counts=report.counts(),
            envelope_seq=report.envelope_seq,
            cost_usd=report.cost_usd,
            llm_used=report.llm_used,
        )
    return NegotiateOutcome(report, report_path, skipped=False)
