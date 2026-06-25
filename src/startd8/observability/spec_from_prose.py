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

import re
from typing import List, Union

from ..manifest_extraction.grammar import find_section, key_lines, md_tables, parse_sections
from .spec import ObservabilitySpec, Receiver, Signal, Threshold

Number = Union[int, float]

# The reserved ``.test`` TLD as a HOST-BOUNDARY token (followed by a path/port/query/end), so a
# real host that merely contains the substring ``.test`` (e.g. ``api.test.evil.com``) is NOT
# treated as fictional.
_TEST_TLD = re.compile(r"\.test(?=[/:?#]|$)")


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
    if not v or v.startswith("${"):
        return True
    if _TEST_TLD.search(v):  # obviously-fictional reserved TLD (boundary-checked, not a substring)
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


# --------------------------------------------------------------------------- #
# Slices 2-3: the non-alert surface → context (service-levels / collection /
# channels / runbook). Mirrors from_observability_yaml's context shape so the
# prose and YAML front doors produce the SAME spec over the whole doc (FR-OTP-4).
# --------------------------------------------------------------------------- #
def _snake(label: str) -> str:
    """``Latency p99`` → ``latency_p99`` (a key-line label → a context key)."""
    return re.sub(r"[^0-9a-z]+", "_", label.strip().lower()).strip("_")


def _bullets(body: str) -> List[str]:
    """``- item`` lines (whole content after the dash) — Channels/Procedures are free-text bullets,
    distinct from ``- Key: value`` key-lines, so they are parsed by section, never ambiguously."""
    return [s[2:].strip() for s in (ln.strip() for ln in body.splitlines()) if s.startswith("- ")]


def _kv_section(scoped: List, title: str) -> dict:
    sec = find_section(scoped, title)
    if sec is None:
        return {}
    kv, _ = key_lines(sec.body)
    return {_snake(k): v for k, v in kv.items()}


def _service_levels(scoped: List) -> dict:
    sl = _kv_section(scoped, "Service levels")
    per_sec = find_section(scoped, "Per service")
    if per_sec is not None:
        for table in md_tables(per_sec.body):
            if "service" not in set(table.headers):
                continue
            ps = {
                row["service"].strip(): {_snake(h): row[h] for h in table.headers if h != "service"}
                for row in table.dicts() if row.get("service", "").strip()
            }
            if ps:
                sl["per_service"] = ps
    return sl


def _channels(scoped: List) -> List[str]:
    sec = find_section(scoped, "Channels")
    return _bullets(sec.body) if sec is not None else []


def _runbook(scoped: List) -> dict:
    rb: dict = _kv_section(scoped, "Runbook")  # overview / escalation key-lines
    risks_sec = find_section(scoped, "Risks")
    if risks_sec is not None:
        rows = [dict(row) for table in md_tables(risks_sec.body)
                if "type" in set(table.headers) for row in table.dicts()]
        if rows:
            rb["risks"] = rows
    procs_sec = find_section(scoped, "Procedures")
    if procs_sec is not None:
        procs = _bullets(procs_sec.body)
        if procs:
            rb["procedures"] = procs
    return rb


def extract_observability(doc: str) -> ObservabilitySpec:
    """Prose ``## Observability`` (§2.12, Slices 1-3) → :class:`ObservabilitySpec`.

    Slice 1 = Thresholds + Receivers (signals/receivers); Slices 2-3 = Service-levels/Collection/
    Channels/Runbook (``context``). An absent ``## Observability`` section yields an empty spec.
    Malformed rows loud-fail (bad ``op`` via ``Threshold``, non-numeric ``value``, literal-secret
    target), matching the strict-parser philosophy; the soft ``kickoff check`` flag report is P2.
    """
    sections = parse_sections(doc)
    obs = find_section(sections, "Observability")
    if obs is None:
        return ObservabilitySpec()
    # Scope subsection lookups to the Observability subtree: a same-named "Thresholds"/"Receivers"
    # heading elsewhere in the doc must not be misread as observability config (robustness).
    scoped = [s for s in sections if "Observability" in s.heading_path]
    kv, _ = key_lines(obs.body)
    kv_lower = {k.lower(): v for k, v in kv.items()}

    # Slices 2-3 → context, in from_observability_yaml's shape (so prose ≡ YAML over the whole doc).
    context: dict = {}
    if (sl := _service_levels(scoped)):
        context["service_levels"] = sl
    if (col := _kv_section(scoped, "Collection")):
        context["collection"] = col
    if (channels := _channels(scoped)):
        context.setdefault("alerting", {})["channels"] = channels
    if (rb := _runbook(scoped)):
        context["runbook"] = rb

    return ObservabilitySpec(
        signals=_thresholds(scoped),
        receivers=_receivers(scoped),
        context=context,
        provenance_default=kv_lower.get("provenance default", ""),
        industry_dataset=kv_lower.get("industry dataset", ""),
        domain="observability",
    )
