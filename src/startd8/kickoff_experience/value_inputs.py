"""Value-input field source for the single oracle — the ``confirmed.yaml`` layout as ``FieldState``s.

The oracle's markdown-extraction path (``build_kickoff_state`` ← ``load_kickoff_docs``) reads authoring
markdown only, so it is blind to the ``docs/kickoff/inputs/*.yaml`` + ``docs/kickoff/confirmed.yaml``
**value-input layout** that every instantiated kickoff package (and the benchmark portal) actually uses
— reporting a fully-kicked-off app as "no inputs, 0 fields". This module derives the *same* field-level
state ``kickoff assess`` reports, as :class:`FieldState`\\ s, so the ONE oracle reflects value-input-driven
projects too.

**One source of truth (not a mirror).** It reuses ``assess``'s exact readers —
``concierge.confirmation.{confirmable_fields, load_ledger, is_audience_default}`` — so the oracle and
``assess`` can never disagree about which inputs are confirmed. A confirmable field's ``value_path``
(``<file>#/<dotted-key>``) is already the exact :attr:`FieldState.value_path` identity, so the join needs
no translation. Import posture matches the existing ``kickoff_experience → concierge.confirmation``
dependency (``portal_spec_v2``/``portal_build`` already do it); ``confirmation`` defers its own
``kickoff_experience`` imports, so there is no import cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .state import Ambiguity, Attention, FieldState


def value_input_field_states(project_root: str | Path) -> List[FieldState]:
    """Derive :class:`FieldState`\\ s from the value-input / ``confirmed.yaml`` layout.

    Attention mapping (parity with ``assess``'s confirmed/awaiting buckets):
    * **confirmed** (a ledger entry that is not an audience-default) → ``ok``;
    * **awaiting** (no ledger entry) or an **audience-default** (a machine default the human hasn't
      ratified) → ``review`` — never ``ok``, so readiness can't over-report un-confirmed defaults.

    ``$0``, read-only, degrade-not-fail (returns ``[]`` if the value-input model is unavailable).

    **Gated on the layout actually being present.** ``confirmable_fields()`` is the SDK *template* (the
    fields a human *could* confirm) and is always non-empty — so we return ``[]`` unless this project
    actually uses the value-input layout (a ``docs/kickoff/inputs/`` dir or a ``confirmed.yaml``).
    Without this gate the template would leak phantom ``review`` fields into a bare or markdown-only
    project, regressing its "no inputs" state (FR-4)."""
    root = Path(project_root)
    if not (root / "docs" / "kickoff" / "inputs").is_dir() and not (
        root / "docs" / "kickoff" / "confirmed.yaml"
    ).is_file():
        return []
    try:
        from ..concierge.confirmation import (
            confirmable_fields,
            is_audience_default,
            load_ledger,
        )

        ledger = load_ledger(project_root)
        out: List[FieldState] = []
        for f in confirmable_fields():
            vp = f["value_path"]
            entry = ledger.get(vp)
            confirmed = entry is not None and not is_audience_default(entry)
            value = entry.get("value") if entry else None
            out.append(
                FieldState(
                    manifest=f.get("domain", ""),
                    value_path=vp,
                    status="extracted" if confirmed else "defaulted",
                    attention=Attention.OK if confirmed else Attention.REVIEW,
                    ambiguity=Ambiguity.NONE,
                    value=str(value) if value is not None else None,
                    source_doc=f.get("domain"),
                )
            )
        return out
    except Exception:  # pragma: no cover - value-input coverage never breaks the oracle
        return []
