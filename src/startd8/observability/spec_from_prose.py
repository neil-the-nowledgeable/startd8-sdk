# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""extract_observability — prose (§2.12 ``## Observability``) → ObservabilitySpec (M5a, Slice 1).

The "communicate by formatting" front door: a project authors thresholds + receivers in a
reviewable ``docs/kickoff/authoring/observability.md`` and this turns it into the **same**
``ObservabilitySpec`` that ``from_observability_yaml`` produces from the YAML (FR-OTP-4 — one model,
two front doors, no dual logic). So the full seam closes: **prose → spec → alert renderer → active
rule**.

~90% assembly of existing ``manifest_extraction.grammar`` primitives (FR-OTP-3 — no new parsing
engine): ``parse_sections`` + ``md_tables`` (multi-table-aware) + ``key_lines``. **Slice 1** = the
``#### Thresholds`` + ``#### Receivers`` tables (the alert path); Slices 2–3 (service-levels,
runbook) follow the identical shape.
"""

from __future__ import annotations

from typing import List, Union

from ..manifest_extraction.grammar import find_section, key_lines, md_tables, parse_sections
from .spec import ObservabilitySpec, Receiver, Signal, Threshold

Number = Union[int, float]


def _num(raw: str) -> Number:
    """``"0"`` → int 0, ``"0.05"`` → float 0.05 (preserves type for round-trip with the YAML)."""
    s = raw.strip()
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError as exc:
            raise ValueError(f"threshold value {raw!r} is not a number") from exc


def secret_safe(target: str) -> bool:
    """FR-OTP-7 (reusable across value-input parsers): a contact/URL is secret-safe when it is
    env-indirected (``${VAR}``), empty, or obviously-fictional (``.test``); a **literal** URL or
    email is NOT safe (it must use env indirection so a real secret never extracts as ``authored``).
    A plain token (e.g. a ``#slack-channel``) is fine."""
    v = (target or "").strip()
    if not v or v.startswith("${") or ".test" in v:
        return True
    if v.startswith(("http://", "https://")) or "@" in v:
        return False
    return True


def _thresholds(sections) -> List[Signal]:
    sec = find_section(sections, "Thresholds")
    if sec is None:
        return []
    out: List[Signal] = []
    for table in md_tables(sec.body):
        if not {"metric", "op", "value"} <= set(table.headers):
            continue  # not the thresholds table
        for row in table.dicts():
            metric = row["metric"].strip()
            if not metric:
                continue
            out.append(
                Signal(
                    name=metric,
                    threshold=Threshold(
                        op=row["op"].strip(),
                        value=_num(row["value"]),
                        severity=(row.get("severity") or "warning").strip() or "warning",
                        for_=(row.get("for") or "0m").strip() or "0m",
                        unit=(row.get("unit") or "").strip(),
                    ),
                    origin="declared",
                )
            )
    return out


def _receivers(sections) -> List[Receiver]:
    sec = find_section(sections, "Receivers")
    if sec is None:
        return []
    out: List[Receiver] = []
    for table in md_tables(sec.body):
        if "name" not in set(table.headers):
            continue
        for row in table.dicts():
            name = row["name"].strip()
            if not name:
                continue
            target = (row.get("target") or "").strip()
            if not secret_safe(target):
                raise ValueError(
                    f"receiver {name!r} target {target!r} is a literal secret; use ${{VAR}} "
                    "env-indirection (FR-OTP-7 secret safety — a secret must never extract as authored)"
                )
            sev = (row.get("severities") or "").strip()
            out.append(
                Receiver(
                    name=name,
                    type=(row.get("type") or "").strip(),
                    target=target,
                    severities=[s.strip() for s in sev.split(",") if s.strip()],
                )
            )
    return out


def extract_observability(doc: str) -> ObservabilitySpec:
    """Prose ``## Observability`` (§2.12, Slice 1) → :class:`ObservabilitySpec`.

    An absent ``## Observability`` section yields an empty spec (the section is optional). Malformed
    rows loud-fail (bad ``op`` via ``Threshold``, non-numeric ``value``, literal-secret target),
    matching the strict-parser philosophy; the soft ``kickoff check`` flag report is P2 (FR-OTP-11).
    """
    sections = parse_sections(doc)
    obs = find_section(sections, "Observability")
    if obs is None:
        return ObservabilitySpec()
    kv, _ = key_lines(obs.body)
    kv_lower = {k.lower(): v for k, v in kv.items()}
    return ObservabilitySpec(
        signals=_thresholds(sections),
        receivers=_receivers(sections),
        provenance_default=kv_lower.get("provenance default", ""),
        industry_dataset=kv_lower.get("industry dataset", ""),
        domain="observability",
    )
