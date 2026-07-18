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

from .plan import WireframePlan, WireframeSection

_PATH = Path(__file__).parent / "descriptive.yaml"

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
    """Return a per-field picker resolving the (role × fluency) audience variant (FR-AUD-1).

    Sparse + degrading: each field falls back ``(role, fluency)`` → ``(role, ·)`` → **base** (the
    record's top-level fields = architect/intermediate). An absent cell is never an error, and the
    default ``("architect", "intermediate")`` returns base verbatim ⇒ byte-identical (FR-AUD-2).
    """
    aud = rec.get("audience") or {}
    role_v = aud.get(role) or {}
    fluency_v = (role_v.get("fluency") or {}).get(fluency) or {}

    def pick(field: str):
        for src in (fluency_v, role_v, rec):  # most-specific → base
            val = src.get(field)
            if val is not None:
                return val
        return None

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
    title = pick("title")  # optional audience-friendly section title (FR-AUD gap-3); base ⇒ None
    return {
        "key": section.key,  # provenance-by-construction (FR-DL-9)
        "title": _fill(title.strip(), fills, section_key=section.key) if title else None,
        "what": _fill((pick("what") or "").strip(), fills, section_key=section.key),
        "why": _fill((pick("why") or "").strip(), fills, section_key=section.key),
        "do": _fill((pick("do") or "").strip(), fills, section_key=section.key),
        "next": _fill((pick("next") or "").strip(), fills, section_key=section.key),  # FR-DL-3 drill hint
        # FR-AUD-C2 — the DOES / WON'T / NEED framing: `what` is DOES; these two are the expectation-set
        # + the author's to-do. Empty for the architect base (never authored there) ⇒ not rendered.
        "wont": _fill((pick("wont") or "").strip(), fills, section_key=section.key),
        "need": _fill((pick("need") or "").strip(), fills, section_key=section.key),
    }


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
    result = {
        "why": _fill((pick("why") or "").strip(), {}, section_key="summary"),
        "do": _fill((pick("do") or "").strip(), {}, section_key="summary"),
    }
    meta = pick("meta")  # optional audience-keyed tool-level intro (FR-AUD-C4); a list of lines
    if meta is not None:
        result["meta"] = list(meta)
    return result


def all_keys() -> list[str]:
    """The section keys the manifest authors a record for (FR-DL-9 coverage surface)."""
    return list(_records().keys())
