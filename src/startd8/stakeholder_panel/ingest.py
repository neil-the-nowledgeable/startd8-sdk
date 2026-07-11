# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""External persona-format ingestion (FR-3/FR-6/FR-7, OQ-7) — one-way (external → roster).

``ingest`` runs a named adapter and then **round-trip-gates** its output: serialize the adapter's
:class:`Roster` → reparse via the strict :func:`parse_roster` + :func:`validate_roster` → accept. So a
buggy adapter fails loudly at *import* time, not later at panel-load time. A gate failure is an
*adapter* fault (:class:`IngestGateError`, an :class:`AdapterError`), never a user-roster ``RosterError``
(the FR-9 taxonomy). The result carries the roster, the ``yaml_text`` to write (with an advisory
provenance header, FR-7), and the adapter's ``warnings``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

from startd8.stakeholder_panel.adapters import AdapterError, get_adapter
from startd8.stakeholder_panel.models import Roster
from startd8.stakeholder_panel.roster import RosterError, parse_roster, validate_roster

__all__ = [
    "IngestResult",
    "IngestGateError",
    "GENERATED_MARKER",
    "ingest",
    "looks_generated",
]

# The advisory header (FR-7) that marks an ingested roster. Advisory only: it is a YAML comment, so it
# is stripped by ``yaml.safe_load`` and invisible to programmatic consumers — a human breadcrumb, not
# machine lineage. The CLI's clobber guard checks for it to avoid overwriting a hand-authored roster.
GENERATED_MARKER = "# GENERATED"


class IngestGateError(AdapterError):
    """The adapter emitted a roster that fails the round-trip gate — an adapter bug (R2-S2)."""


@dataclass(frozen=True)
class IngestResult:
    roster: Roster
    yaml_text: str  # the bytes to write — provenance header + serialized roster body
    warnings: List[str] = field(default_factory=list)


def looks_generated(text: str) -> bool:
    """True iff *text* begins with the generated-provenance marker (i.e. not hand-authored)."""
    return text.lstrip().startswith(GENERATED_MARKER)


def _provenance_header(source: str, format_name: str) -> str:
    # Basename only (R1-S5): the roster *body* stays byte-identical across machines / working dirs.
    # ``or "<input>"`` also covers a root-ish source ("/", ".") whose basename is empty.
    token = Path(source).name or "<input>"
    return (
        f"{GENERATED_MARKER} from {token} via {format_name} adapter "
        f"— edit the source, re-run import\n"
    )


def ingest(format_name: str, source_text: str, *, source: str = "") -> IngestResult:
    """Adapt *source_text* with the named adapter and round-trip-gate the result (OQ-7).

    Raises :class:`AdapterError` for an unknown format or a malformed source, and
    :class:`IngestGateError` if the adapter emits a roster that fails strict parse / validation.
    """
    adapter = get_adapter(format_name)  # AdapterError if the format is unknown
    try:
        result = adapter.adapt(source_text)  # AdapterError on a malformed source
    except (
        RosterError
    ) as exc:  # a misbehaving adapter must not leak a user-facing RosterError
        raise AdapterError(
            f"adapter {format_name!r} failed on the source: {exc}"
        ) from exc

    body = yaml.safe_dump(
        result.roster.to_dict(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    try:
        reparsed = parse_roster(body)
    except (
        RosterError
    ) as exc:  # adapter emitted structurally-invalid YAML → adapter bug, not user's
        raise IngestGateError(
            f"adapter {format_name!r} emitted a roster that fails strict parse: {exc}"
        ) from exc
    issues = validate_roster(reparsed)
    if issues:
        raise IngestGateError(
            f"adapter {format_name!r} emitted an invalid roster: {'; '.join(issues)}"
        )

    return IngestResult(
        roster=reparsed,
        yaml_text=_provenance_header(source, format_name) + body,
        warnings=list(result.warnings),
    )
