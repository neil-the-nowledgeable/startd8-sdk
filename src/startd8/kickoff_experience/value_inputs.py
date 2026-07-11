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

#: Recognized "intentionally not applicable" values — a first-class way for a project to say a
#: convention doesn't apply to it (e.g. a money-less app declaring ``money: not-applicable``). An N/A
#: value is a *decision*, so it reads as ``ok`` (satisfied), never ``blocked`` (required) or ``review``
#: (awaiting) — but with a distinct ``not_applicable`` status so it renders as "N/A", not a real value.
_NOT_APPLICABLE = frozenset({"n/a", "na", "n.a.", "none", "not applicable", "not-applicable", "-"})


def is_not_applicable(value: object) -> bool:
    """True iff *value* is a recognized "intentionally N/A" marker (case-insensitive)."""
    return value is not None and str(value).strip().lower() in _NOT_APPLICABLE


def value_input_field_states(project_root: str | Path) -> List[FieldState]:
    """Derive :class:`FieldState`\\ s from the value-input / ``confirmed.yaml`` layout.

    Attention mapping (parity with ``assess``'s confirmed/awaiting buckets, plus FR-2's blocked case):
    * **confirmed** (a ledger entry that is not an audience-default) → ``ok``;
    * **awaiting** (no ledger entry) or an **audience-default** (a machine default the human hasn't
      ratified) → ``review`` — never ``ok``, so readiness can't over-report un-confirmed defaults;
    * a **required, non-defaulted** value-input (``required=True`` with an ``authored`` provenance — a
      non-derivable value a project MUST provide, e.g. ``conventions.yaml#/language``) whose on-disk
      value is **absent** (domain file / key missing, or an unfilled ``<…>`` placeholder) → ``blocked``
      (author-actionable, gates activation); a required value that IS provided → ``ok``. These are the
      fields ``confirmable_fields()`` deliberately excludes (no safe default to ratify), so without this
      branch a project missing a required input read "review/ready" instead of blocked (FR-2);
    * an **optional authored** convention (``required=False``, non-defaulted — e.g.
      ``conventions.yaml#/data_model.money``, which many apps don't use) → tracked as ``ok`` only when
      the project DECLARES it; when absent it is simply omitted, so an optional convention never gates
      readiness (it is neither a review nor a blocker);
    * an explicit **N/A** value (``not-applicable`` / ``n/a`` — see :func:`is_not_applicable`) on ANY of
      the above → ``ok`` with a distinct ``not_applicable`` status: a project's *decision* that a
      convention doesn't apply to it, so it reads as done, never blocked or awaiting.

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
            _is_placeholder,
            confirmable_fields,
            field_current_value,
            is_audience_default,
            load_ledger,
        )
        from .manifest import default_config

        ledger = load_ledger(project_root)
        out: List[FieldState] = []

        # (1) Confirmable (DEFAULTED, writable) fields — a human ratifies an estimate/config-default.
        #     confirmed → ok; awaiting / audience-default → review (never ok, so readiness can't
        #     over-report an un-ratified default).
        for f in confirmable_fields():
            vp = f["value_path"]
            entry = ledger.get(vp)
            confirmed = entry is not None and not is_audience_default(entry)
            value = entry.get("value") if entry else None
            na = confirmed and is_not_applicable(value)  # confirmed as "not applicable" → still ok
            out.append(
                FieldState(
                    manifest=f.get("domain", ""),
                    value_path=vp,
                    status=("not_applicable" if na else "extracted") if confirmed else "defaulted",
                    attention=Attention.OK if confirmed else Attention.REVIEW,
                    ambiguity=Ambiguity.NONE,
                    value=str(value) if value is not None else None,
                    source_doc=f.get("domain"),
                )
            )

        # (2) REQUIRED (writable, NON-defaulted) fields — FR-2's blocked case. These are the
        #     non-derivable values a project MUST provide (e.g. conventions.yaml#/language): they carry
        #     ``required=True`` with an ``authored`` provenance, so they are NOT confirmable (there is no
        #     safe default to ratify) and ``confirmable_fields()`` above never yields them. When the
        #     on-disk value is absent (domain file missing / key missing / an unfilled ``<…>``
        #     placeholder) the input is required-but-unprovided → ``blocked`` (author-actionable, gates
        #     activation). When a real value is present → ``ok``. Value_paths already emitted by (1) are
        #     skipped so a field can't be double-counted (defaulted+required is not a real combination,
        #     but the guard keeps identities unique).
        emitted = {fs.value_path for fs in out}
        confirmable_vps = {f["value_path"] for f in confirmable_fields()}

        def _domain(fdef) -> str:
            wt = fdef.write_target
            return (wt.file[:-5] if wt and wt.file.endswith(".yaml") else (wt.file if wt else "")) or ""

        for fdef in default_config().writable_fields():
            if fdef.value_path in confirmable_vps or fdef.value_path in emitted:
                continue
            # Only authored conventions participate here (required + optional). Arbitrary writables and
            # the confirmable/defaulted set are handled above; this keeps the value-input surface to the
            # human-authored conventions a project declares.
            if getattr(fdef, "provenance_default", None) != "authored":
                continue
            current = field_current_value(project_root, fdef.value_path)
            na = is_not_applicable(current)
            provided = current is not None and not _is_placeholder(current)  # N/A counts as provided
            domain = _domain(fdef)

            if fdef.required:
                # (2) REQUIRED authored field (e.g. conventions.yaml#/language) — FR-2's blocked case:
                #     absent/placeholder → blocked (author-actionable, gates activation); a real value or
                #     an explicit N/A decision → ok.
                status = "not_applicable" if na else ("extracted" if provided else "not_extracted")
                out.append(
                    FieldState(
                        manifest=domain,
                        value_path=fdef.value_path,
                        status=status,
                        attention=Attention.OK if provided else Attention.BLOCKED,
                        ambiguity=Ambiguity.NONE if provided else Ambiguity.MALFORMED_BLOCK,
                        value=str(current) if provided else None,
                        reason=None if provided else "required value-input absent (unprovided)",
                        source_doc=domain or None,
                    )
                )
            elif provided:
                # (3) OPTIONAL authored convention (e.g. conventions.yaml#/data_model.money) — tracked
                #     only when the project DECLARES it (a real value or an explicit N/A) → ok; when
                #     absent it is simply omitted, so an optional convention never gates readiness.
                out.append(
                    FieldState(
                        manifest=domain,
                        value_path=fdef.value_path,
                        status="not_applicable" if na else "extracted",
                        attention=Attention.OK,
                        ambiguity=Ambiguity.NONE,
                        value=str(current),
                        source_doc=domain or None,
                    )
                )
        return out
    except Exception:  # pragma: no cover - value-input coverage never breaks the oracle
        return []
