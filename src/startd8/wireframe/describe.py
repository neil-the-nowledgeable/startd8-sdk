"""Descriptive-layer composer for `startd8 wireframe` (FR-DL-1/5/8/9).

Reads the authored ``descriptive.yaml`` manifest and composes the what/why/do narration for one
:class:`WireframeSection`, filling ``{{count}}`` / ``{{status}}`` placeholders from the *live*
section. Deterministic, no-LLM (Hitsuzen, FR-DL-8): the output is a pure function of
(authored record × live plan). One source — this manifest — behind the section narration; the
renderer holds no narration strings (FR-DL-5).

Mirrors the proven attorney-portal composer (``work/legal/attorney-portal/app/descriptive.py``):
a cached YAML load, a per-key record lookup, and a template-fill returning a plain dict.

Scope (M-DL0/M-DL1/M-DL2/M-DL4/M-DL5): what/why/do/next per section + the aggregate `summary`
record (FR-DL-12, the header's meaning). Not yet built — audience variants (FR-DL-1 optional),
workflow-position inference (M-DL3/FR-DL-4), or the 3-axis facets (FR-DL-11).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from .descriptive_schema import SECTION_SCHEMA, field_order
from .plan import WireframePlan, WireframeSection

_PATH = Path(__file__).parent / "descriptive.yaml"

# AR-1: the section record's fields come from the ONE declared schema (SECTION_SCHEMA), not a hardcoded
# list here — so the resolver and the FR-SHC coverage guard can never drift apart (KM-27 / CL-17 L4 gate).
_SECTION_FIELDS = field_order(SECTION_SCHEMA)  # e.g. what/why/do/next/title/wont/need

# Placeholder vocabulary (subset of the FR-DL-5 fill table used by the MVP): each resolves from a
# validated attribute of the live section. An unfillable placeholder is a typed error (CCbC), never
# silent blank text.
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


class DescribeError(ValueError):
    """A placeholder in a record had no fill source on the live section (CCbC, FR-DL-5)."""


@lru_cache(maxsize=1)
def _records() -> dict:
    data = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
    return data.get("records", {})


def _fills(section: WireframeSection) -> dict:
    """The validated fill sources for the MVP placeholder set (FR-DL-5)."""
    return {
        "count": str(len(section.items)),   # {{count}} ← len(section.items)
        "status": section.status,           # {{status}} ← section.status
    }


def _fill(text: str, fills: dict, *, section_key: str) -> str:
    """Substitute ``{{name}}`` placeholders; an unknown placeholder is a typed error (CCbC)."""
    def repl(m: "re.Match[str]") -> str:
        name = m.group(1)
        if name not in fills:
            raise DescribeError(
                f"descriptive.yaml[{section_key}]: no fill source for placeholder "
                f"{{{{{name}}}}} (known: {', '.join(sorted(fills))})"
            )
        return fills[name]

    return _PLACEHOLDER_RE.sub(repl, text)


def _variant(rec: dict, role: str, fluency: str):
    """Return a per-field picker resolving the (role × fluency) audience variant (FR-AUD-1 / EC-4).

    Resolution ``(role, fluency)`` → ``(role, ·)`` → [kit's base voice] → base, with one rule that closes
    the architect-leak (R1-F3): an **authored base voice** variant is *self-contained* — a field it doesn't
    provide resolves to ``None`` (empty), NOT to the architect base — so a partial ``end_user`` variant can
    never leak the technical voice into one field.

    EC-4 delivery kits are the one exception: a kit (e.g. ``pm``, base ``end_user``) is an **overlay** on
    its base voice, so an unauthored kit field falls through to that base voice's authored variant (plain
    vs technical) rather than to the architect root — a PM inherits the plain voice, a backend-dev the
    technical one, with zero authoring. The default ``("architect", "intermediate")`` has no
    ``audience.architect`` variant and no base voice ⇒ resolves to base verbatim ⇒ byte-identical (FR-AUD-2).
    """
    from .delivery_roles import base_voice

    aud = rec.get("audience") or {}
    role_v = aud.get(role) or {}
    fluency_v = (role_v.get("fluency") or {}).get(fluency) or {}
    role_authored = bool(role_v)

    base = base_voice(role)                       # EC-4: the voice a kit overlays (None for a base voice)
    base_v = (aud.get(base) or {}) if base else {}
    base_fluency_v = (base_v.get("fluency") or {}).get(fluency) or {}

    def pick(field: str):
        for src in (fluency_v, role_v):           # the role's own authored overrides (fluency → role)
            val = src.get(field)
            if val is not None:
                return val
        if base:                                  # EC-4 kit overlay → inherit its base voice…
            for src in (base_fluency_v, base_v):
                val = src.get(field)
                if val is not None:
                    return val
            # …then mirror that base voice's own self-containment: fall to the architect root ONLY when the
            # base voice is itself un-authored (backend-dev→architect shows `why`; pm→end_user does not leak it).
            return rec.get(field) if not bool(base_v) else None
        return rec.get(field) if not role_authored else None  # base voice: self-contained (anti-leak)

    return pick


def describe(
    section: WireframeSection,
    plan: WireframePlan,
    *,
    role: str = "architect",
    fluency: str = "intermediate",
) -> Optional[dict]:
    """Compose the authored what/why/do/next narration for ``section`` (FR-DL-1 / FR-AUD-1).

    Returns ``{"key", "what", "why", "do", "next"}`` with placeholders filled from the live section,
    or ``None`` when no record is authored for ``section.key``. The ``role``/``fluency`` select an
    audience variant (FR-AUD): the default ``("architect", "intermediate")`` resolves to the record's
    base fields, byte-identical to the pre-audience output. Deterministic (FR-DL-8); provenance by
    construction (FR-DL-9).
    """
    rec = _records().get(section.key)
    if not rec:
        return None
    fills = _fills(section)
    pick = _variant(rec, role, fluency)
    # AR-1: resolve exactly the fields the declared SECTION_SCHEMA lists (single source). An un-authored
    # field is "" (falsy) — `title` absent ⇒ "" ⇒ the renderer falls back to the section's own title;
    # `wont`/`need` absent ⇒ "" ⇒ not rendered (the DOES/WON'T/NEED framing only shows where authored).
    out = {"key": section.key}  # provenance-by-construction (FR-DL-9)
    for name in _SECTION_FIELDS:
        out[name] = _fill((pick(name) or "").strip(), fills, section_key=section.key)
    return out


def describe_summary(
    plan: WireframePlan, *, role: str = "architect", fluency: str = "intermediate"
) -> Optional[dict]:
    """Compose the aggregate `summary` record's narration (FR-DL-12) — the *meaning* of the
    Status/Shape/Content/Cascade header, routed through the descriptive layer. Authored without live
    placeholders (the figures live in the header lines); returns ``{"why", "do"}`` or ``None``. The
    ``role``/``fluency`` select an audience variant (FR-AUD); default resolves to base. Deterministic."""
    rec = _records().get("summary")
    if not rec:
        return None
    pick = _variant(rec, role, fluency)
    result: dict = {}
    for field in ("why", "do", "headline", "lead", "closing"):  # scalar intro fields (FR-AUD-C4)
        val = pick(field)
        if val:
            result[field] = _fill(val.strip(), {}, section_key="summary")
    meta = pick("meta")  # architect tool-level intro; a list of lines
    if meta is not None:
        result["meta"] = list(meta)
    steps = pick("steps")  # the end_user actionable "what to do" list (R2-F2)
    if steps is not None:
        result["steps"] = [_fill(str(s).strip(), {}, section_key="summary") for s in steps]
    return result


def all_keys() -> list[str]:
    """The section keys the manifest authors a record for (FR-DL-9 coverage surface)."""
    return list(_records().keys())
