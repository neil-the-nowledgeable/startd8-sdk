# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Increment 2 — LLM field-mapping (OQ-9, the one PAID step).

The heuristic :mod:`.extract` finds *items*; this maps the small subset that are concrete
**kickoff-input field edits** (a budget ceiling, a target, a deadline) to a ``{value_path, value}``
the host can ``capture``. It is bounded by the host **allow-list**: the model is only shown the
allow-listed value_paths and its output is validated against them — a value_path the host does not
allow-list is dropped (it could never pass ``build_proposal``'s FR-4 gate anyway).

Keiyaku A2A contract (SDK micro-prime rule — JSON in/out, defined before the call):

    OUT: [ { "value_path": <one of the allow-listed paths>,
             "value":      <string>,
             "rationale":  <short string> } ]   # [] when nothing maps

The model boundary is a ``mapper`` callable ``(prompt:str) -> str`` so tests inject a deterministic
double; the default builds a real agent. **`$0` unless a real mapper runs** — with an empty allow-list
(the brownfield norm) this returns ``[]`` without spending.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

Mapper = Callable[[str], str]


def _build_prompt(synthesis_text: str, allowed: List[str]) -> str:
    paths = "\n".join(f"  - {p}" for p in allowed)
    return (
        "You extract concrete kickoff-input field edits from a stakeholder-panel synthesis.\n\n"
        "ONLY these value_paths may be set (ignore everything else — governance, schema, and "
        "narrative items are out of scope here):\n"
        f"{paths}\n\n"
        "Return a JSON array. Each element: "
        '{\"value_path\": <one of the paths above>, \"value\": <string>, \"rationale\": <short>}. '
        "Include an item ONLY if the synthesis states a concrete value for that field (a number, "
        "amount, date, or explicit setting). If nothing maps, return []. Output JSON only.\n\n"
        "=== SYNTHESIS ===\n"
        f"{synthesis_text[:12000]}\n"
    )


def _parse_and_validate(raw: str, allowed: List[str]) -> List[Dict[str, Any]]:
    """Parse the model's JSON and keep only well-formed, allow-listed, non-empty mappings."""
    allowed_set = set(allowed)
    try:
        data = json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        vp = str(item.get("value_path", "")).strip()
        val = str(item.get("value", "")).strip()
        if vp in allowed_set and val:
            out.append({"value_path": vp, "value": val, "rationale": str(item.get("rationale", "")).strip()})
    return out


def _strip_fences(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _default_mapper(model_spec: Optional[str]) -> Mapper:
    """Build a real agent-backed mapper (the paid path). Imported lazily to keep the module $0-safe."""

    def mapper(prompt: str) -> str:
        import asyncio

        from startd8.utils.agent_resolution import resolve_agent_spec

        spec = model_spec or "anthropic:claude-sonnet-4-6"
        agent = resolve_agent_spec(spec)
        result = asyncio.run(agent.agenerate(prompt))
        return getattr(result, "text", "") or ""

    return mapper


def extract_field_mappings(
    synthesis_text: str,
    allowed_value_paths: Any,
    *,
    mapper: Optional[Mapper] = None,
    model_spec: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Map a synthesis to allow-listed ``{value_path, value, rationale}`` mappings (OQ-9).

    ``$0`` and no model call when the allow-list is empty or the synthesis is blank.
    """
    allowed = sorted({str(p) for p in (allowed_value_paths or ())})
    if not allowed or not (synthesis_text or "").strip():
        return []
    run = mapper or _default_mapper(model_spec)
    return _parse_and_validate(run(_build_prompt(synthesis_text, allowed)), allowed)
