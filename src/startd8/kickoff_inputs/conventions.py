"""``conventions.yaml`` — the technology-conventions value input (FR-VIP, the proving slice).

The conventions sheet is the documented highest-leverage kickoff input: when generation does not know
the stack/layout/naming it *invents* them (the run-028 Flask-where-FastAPI failure class). This module
is the strict round-trip authority (FR-VIP-2): ``parse_conventions`` loud-fails on a malformed sheet so
the prose extractor (``manifest_extraction.extract_conventions``) can gate every emitted
``conventions.yaml`` against it (FR-VIP-3), and any future convention-injection consumer shares one
parser.

Shape (FR-VIP §4): ``domain == "conventions"``, a required ``language``, ``stack``/``module_paths``/
``naming`` open str→str maps, an optional ``data_model`` representation block (FR-F6: 5 enum scalars +
``computed_fields``/``deferred`` free-text lists), ``architecture_notes`` (the load-bearing invariants,
verbatim), and optional ``field_authorship``/``provenance_default``. Unknown top-level keys are rejected
(typo guard); ``stack``/``naming`` sub-keys are open vocabulary (D-VIP-3). Project-agnostic — household's
sheet is a fixture, never a built-in (FR-VIP-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

# Controlled enums for the FR-F6 data-model representation block (the how-to mapping table). A value
# outside its set is a loud parse error here (and a `not_extracted(bad-enum)` flag at extraction).
_DATA_MODEL_ENUMS: Dict[str, frozenset] = {
    "money": frozenset({"cents", "float"}),
    "datetime": frozenset({"utc", "local"}),
    "recurrence": frozenset({"structured", "rrule", "none"}),
    "references": frozenset({"fk-only", "loose-allowed"}),
    "weekday": frozenset({"iso", "us"}),
}
_DATA_MODEL_LISTS = ("computed_fields", "deferred")
_TOP_LEVEL_KEYS = frozenset({
    "domain", "provenance_default", "language", "stack", "module_paths",
    "naming", "data_model", "field_authorship", "architecture_notes",
})


@dataclass(frozen=True)
class DataModelConventions:
    """The FR-F6 data-model representation block (DM-1..7): how money/time/recurrence/refs are shaped."""

    money: Optional[str] = None
    datetime: Optional[str] = None
    recurrence: Optional[str] = None
    references: Optional[str] = None
    weekday: Optional[str] = None
    computed_fields: List[str] = field(default_factory=list)
    deferred: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConventionsManifest:
    """A parsed, validated ``conventions.yaml`` — the stack/layout/naming a project's code must follow."""

    language: str
    domain: str = "conventions"
    provenance_default: Optional[str] = None
    stack: Dict[str, str] = field(default_factory=dict)
    module_paths: Dict[str, str] = field(default_factory=dict)
    naming: Dict[str, str] = field(default_factory=dict)
    data_model: Optional[DataModelConventions] = None
    field_authorship: Optional[str] = None
    architecture_notes: List[str] = field(default_factory=list)


def _str_map(value: object, key: str) -> Dict[str, str]:
    """Validate an open str→str map (``stack``/``module_paths``/``naming``). Loud-fails on a non-mapping
    or a non-string value; sub-keys are open vocabulary (D-VIP-3)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"conventions.yaml: `{key}` must be a mapping of name -> value")
    out: Dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            raise ValueError(f"conventions.yaml: `{key}.{k}` must be a string value")
        out[str(k)] = str(v)
    return out


def _data_model(value: object) -> Optional[DataModelConventions]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("conventions.yaml: `data_model` must be a mapping")
    unknown = set(value) - (set(_DATA_MODEL_ENUMS) | set(_DATA_MODEL_LISTS))
    if unknown:
        raise ValueError(
            f"conventions.yaml: `data_model` has unknown keys {sorted(unknown)} "
            f"(allowed: {sorted(set(_DATA_MODEL_ENUMS) | set(_DATA_MODEL_LISTS))})"
        )
    scalars: Dict[str, Optional[str]] = {}
    for key, allowed in _DATA_MODEL_ENUMS.items():
        val = value.get(key)
        if val is None:
            scalars[key] = None
            continue
        if not isinstance(val, str) or val not in allowed:
            raise ValueError(
                f"conventions.yaml: `data_model.{key}` must be one of {sorted(allowed)}, got {val!r}"
            )
        scalars[key] = val
    lists: Dict[str, List[str]] = {}
    for key in _DATA_MODEL_LISTS:
        val = value.get(key, [])
        if val is None:
            val = []
        if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
            raise ValueError(f"conventions.yaml: `data_model.{key}` must be a list of strings")
        lists[key] = list(val)
    return DataModelConventions(**scalars, **lists)


def parse_conventions(text: Optional[str]) -> ConventionsManifest:
    """Parse + **strictly** validate ``conventions.yaml`` → :class:`ConventionsManifest`.

    Loud-fails (``ValueError``) on: a non-mapping root, an unknown top-level key (typo guard), a wrong
    ``domain``, a missing/empty ``language``, a non-string-map ``stack``/``module_paths``/``naming``, a
    bad ``data_model`` enum, or a non-string ``architecture_notes`` entry. The canonical authority for
    the value YAML (FR-VIP-2) — the round-trip gate and any future consumer share it.
    """
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("conventions.yaml must be a mapping")
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(
            f"conventions.yaml: unknown top-level keys {sorted(unknown)} "
            f"(allowed: {sorted(_TOP_LEVEL_KEYS)})"
        )
    domain = data.get("domain", "conventions")
    if domain != "conventions":
        raise ValueError(f"conventions.yaml: `domain` must be 'conventions', got {domain!r}")
    language = data.get("language")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("conventions.yaml: `language` is required (a non-empty string)")

    notes = data.get("architecture_notes", []) or []
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        raise ValueError("conventions.yaml: `architecture_notes` must be a list of strings")
    for opt in ("provenance_default", "field_authorship"):
        val = data.get(opt)
        if val is not None and not isinstance(val, str):
            raise ValueError(f"conventions.yaml: `{opt}` must be a string")

    return ConventionsManifest(
        language=language,
        domain=domain,
        provenance_default=data.get("provenance_default"),
        stack=_str_map(data.get("stack"), "stack"),
        module_paths=_str_map(data.get("module_paths"), "module_paths"),
        naming=_str_map(data.get("naming"), "naming"),
        data_model=_data_model(data.get("data_model")),
        field_authorship=data.get("field_authorship"),
        architecture_notes=list(notes),
    )
