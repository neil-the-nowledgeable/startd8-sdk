"""``imports.yaml`` — the per-entity import declaration (FR-IMP-3), the 7th assembly manifest.

Mirrors the proven manifest pattern (``## section`` → extractor → this parser → round-trip gate)
the FR-PE emitter paved. One entry per importable entity declares HOW rows arrive (paste JSON / paste
or upload text → an AI pass), WHAT makes a row the same row on import (the FR-IMP-2 identity key), and
whether to generate a paste/upload SURFACE. The generated owned-kind is ``app/import.py`` (Phase 3);
the surface is ``app/web/import.py`` (Phase 4).

Closed grammar (the markdown columns the extractor reads): **Entity | Format | Identity | Provenance |
Extract via | Surface**. This parser is the *round-trip oracle*: an emitted ``imports.yaml`` must parse
here or extraction raises ``RoundTripError`` (a bug, never a silent flag). Strict: unknown keys,
duplicate entities, bad format, unknown cross-refs → loud at parse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

import yaml

from .identity import IdentityKey, resolve_identity

#: The closed format vocabulary. ``json`` = paste a lossless export (the ``to_json`` inverse);
#: ``text`` = paste/upload free text routed through an AI ``extract_via`` pass.
FORMATS = frozenset({"json", "text"})

_REQUIRED = ("format",)
_OPTIONAL = ("identity", "provenance", "extract_via", "surface")
_KEYS = frozenset(_REQUIRED + _OPTIONAL)


@dataclass(frozen=True)
class ImportSpec:
    """One importable entity's contract."""

    entity: str
    format: str                              # ∈ FORMATS
    identity: IdentityKey                    # how a row dedups/upserts on import (FR-IMP-2)
    provenance: Optional[str] = None         # human-owned field import must never clobber (FR-IMP-5)
    extract_via: Optional[str] = None        # ai_passes.yaml pass name (text format only)
    surface: bool = False                    # generate the paste/upload screen (Phase 4)

    @property
    def is_text(self) -> bool:
        return self.format == "text"


def _default_identity(fmt: str) -> str:
    """The identity an entry assumes when it declares none.

    ``json`` round-trips a lossless export (which carries ``id``) → upsert by primary key.
    ``text`` synthesizes fresh rows → ``name`` dedup (the AI-layer default), degrading to
    insert-always when the entity has no ``name`` column.
    """
    return "id" if fmt == "json" else "name"


def parse_imports(
    text: Optional[str],
    *,
    known_entities: FrozenSet[str] = frozenset(),
    known_passes: FrozenSet[str] = frozenset(),
    known_provenance: FrozenSet[Tuple[str, str]] = frozenset(),
) -> Tuple[ImportSpec, ...]:
    """Parse ``imports.yaml`` → ImportSpecs. Tolerant of absence; strict on content.

    Cross-references are validated only when the corresponding ``known_*`` set is supplied (the
    extractor passes them; a bare unit-test call can omit them). ``known_provenance`` is the set of
    ``(entity, field)`` human-owned fields (``human_inputs`` shape).
    """
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict) or "imports" not in data:
        return ()
    raw = data["imports"] or {}
    if not isinstance(raw, dict):
        raise ValueError("imports.yaml: `imports` must be a mapping of entity -> spec")

    out: list[ImportSpec] = []
    seen: set[str] = set()
    for entity, spec in raw.items():
        entity = str(entity)
        if entity in seen:
            raise ValueError(f"imports.yaml: duplicate import entity {entity!r}")
        seen.add(entity)
        if not isinstance(spec, dict):
            raise ValueError(f"imports.yaml: import {entity!r} must be a mapping")
        unknown = set(spec) - _KEYS
        if unknown:
            raise ValueError(f"imports.yaml: import {entity!r} has unknown keys {sorted(unknown)}")
        for req in _REQUIRED:
            if not spec.get(req):
                raise ValueError(f"imports.yaml: import {entity!r} missing required `{req}`")

        if known_entities and entity not in known_entities:
            raise ValueError(f"imports.yaml: import references unknown entity {entity!r}")

        fmt = str(spec["format"]).strip().lower()
        if fmt not in FORMATS:
            raise ValueError(
                f"imports.yaml: import {entity!r} has unknown format {fmt!r} (one of {sorted(FORMATS)})"
            )

        provenance = spec.get("provenance")
        provenance = str(provenance).strip() if provenance not in (None, "") else None
        if provenance and "." in provenance:
            # tolerate a qualified "Entity.field" — must name THIS entity
            ent_q, _, fld_q = provenance.partition(".")
            if ent_q != entity:
                raise ValueError(
                    f"imports.yaml: import {entity!r} provenance {provenance!r} names a different entity"
                )
            provenance = fld_q
        if provenance and known_provenance and (entity, provenance) not in known_provenance:
            raise ValueError(
                f"imports.yaml: import {entity!r} provenance field {provenance!r} is not a declared "
                "human-owned field (human_inputs.yaml)"
            )

        extract_via = spec.get("extract_via")
        extract_via = str(extract_via).strip() if extract_via not in (None, "") else None
        if extract_via and known_passes and extract_via not in known_passes:
            raise ValueError(
                f"imports.yaml: import {entity!r} extract_via {extract_via!r} is not a declared AI "
                "pass (ai_passes.yaml)"
            )
        if extract_via and fmt != "text":
            raise ValueError(
                f"imports.yaml: import {entity!r} declares extract_via but format is {fmt!r} "
                "(extract_via routes TEXT through an AI pass — use format: text)"
            )
        if fmt == "text" and not extract_via:
            raise ValueError(
                f"imports.yaml: import {entity!r} format: text requires an `extract_via` AI pass"
            )

        # -- identity (FR-IMP-2) -------------------------------------------- #
        declared = spec.get("identity")
        declared_norm = str(declared).strip().lower() if isinstance(declared, str) else declared
        if declared_norm == "source":
            # bare `source` pairs with the Provenance column to name the stamped field (OQ-IMP-5).
            if not provenance:
                raise ValueError(
                    f"imports.yaml: import {entity!r} identity `source` requires a Provenance field "
                    "(the source-stamped column) — OQ-IMP-5"
                )
            identity: IdentityKey = IdentityKey(kind="source", provenance=provenance)
        else:
            if declared in (None, ""):
                declared = _default_identity(fmt)
            identity = resolve_identity(
                declared=declared, where=f"imports.yaml import {entity!r}"
            )
            if identity.kind == "source" and not provenance:
                raise ValueError(
                    f"imports.yaml: import {entity!r} identity is source-scoped but no Provenance "
                    "field is declared — OQ-IMP-5"
                )

        out.append(
            ImportSpec(
                entity=entity,
                format=fmt,
                identity=identity,
                provenance=provenance,
                extract_via=extract_via,
                surface=bool(spec.get("surface", False)),
            )
        )
    return tuple(out)
