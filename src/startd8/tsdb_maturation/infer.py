"""M2 — Inference core (FR-3, FR-4, FR-11) — THE load-bearing milestone.

Productionizes the GREEN spike (`docs/design/tsdb-to-relational/spike/spike_inference.py`): a
raw :class:`~startd8.tsdb_maturation.specimen.Specimen` is projected into an ``EntityGraph`` and
rendered to a valid ``schema.prisma`` via the **real** emitter (``render_prisma_schema``) — the
back-half is reused verbatim, only the front-half (inference) is new.

The load-bearing risk is a **wrong inferred identity key** (silent production data corruption),
so identity inference is deterministic and guarded, and the golden test asserts it against the
michigan ``CONFLICT_COLUMNS`` (see ``tests/unit/tsdb_maturation/test_infer_golden.py``).

CRP-hardened behaviors:

* **FR-3 type inference** — all-integral → ``Int``, any-decimal → ``Decimal``, ISO-8601 →
  ``DateTime``, else ``String``. Labels stay ``String`` (enums OFF, OQ-10). The **measure is
  forced ``Decimal``** (OQ-9, financial fidelity).
* **R1-F8 measure-name collision** — the measure name derived from the metric is disambiguated
  (suffixed) if it collides with a label column.
* **FR-4 identity** — minimal label subset unique per raw series; deterministic tie-break
  (R1-F1: fewest columns, then golden-match, then lexicographic); display columns excluded
  (R1-F2); **raw-specimen input only** (R1-F9, via ``Specimen.assert_raw``).
* **FR-11 bookkeeping-collision rename** — a label colliding with the emitter's reserved set
  (read via the **public accessor** ``reserved_field_names``, R1-S7) is renamed ``x``→``dataX``;
  the rename is itself collision-checked (R1-F10).
* **R1-S8 direct-graph invariants** — the directly-built graph is asserted against the
  post-conditions the prose ``extract_entities`` path guarantees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Mapping, Optional, Sequence

from startd8.logging_config import get_logger
from startd8.manifest_extraction.entities import DocEntity, DocField, EntityGraph
from startd8.manifest_extraction.prisma_emitter import (
    PrismaSchemaResult,
    render_prisma_schema,
    reserved_field_names,
)

from .specimen import RESERVED_RECORD_KEYS, Specimen

logger = get_logger(__name__)

# The scalar Prisma types this inference emits (the emitted-type vocab the R1-S8 invariant
# checks against — distinct from entities.PLAIN_TYPES, which keys the *prose* path).
PRISMA_SCALAR_TYPES = frozenset({"String", "Int", "Decimal", "DateTime", "Boolean", "Float"})

# The single TSDB-specific field inference adds; the metric's measure value column is the other
# non-label column. Everything else (id/source/…) is emitter-injected bookkeeping.
OBSERVED_AT_FIELD = "observedAt"

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_INT = re.compile(r"-?\d+")


class InferenceError(RuntimeError):
    """Inference could not produce a valid schema (collision, invariant breach, empty input)."""


# --------------------------------------------------------------------------- #
# Primitives (the rung-3 novelty).                                              #
# --------------------------------------------------------------------------- #
def infer_scalar_type(values: Sequence[object]) -> str:
    """FR-3: type a column by inspecting its (stringified) values. Enums OFF (OQ-10)."""
    vals = [str(v) for v in values if v not in (None, "")]
    if not vals:
        return "String"
    if all(_INT.fullmatch(v) for v in vals):
        return "Int"

    def _is_dec(v: str) -> bool:
        try:
            Decimal(v)
            return True
        except InvalidOperation:
            return False

    if all(_is_dec(v) for v in vals) and any("." in v for v in vals):
        return "Decimal"
    if all(_ISO.match(v) for v in vals):
        return "DateTime"
    return "String"


def camel(snake: str) -> str:
    """``fiscal_year`` → ``fiscalYear`` (the emitter's field-name convention)."""
    parts = [p for p in snake.split("_") if p != ""]
    if not parts:
        return snake
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def is_display_column(col: str, all_cols: Sequence[str]) -> bool:
    """R1-F2: a ``x_display`` column whose slug sibling ``x`` exists is a dimension, never key-eligible."""
    return col.endswith("_display") and col[: -len("_display")] in set(all_cols)


def rename_if_reserved(col: str, reserved: frozenset) -> str:
    """FR-11 / R1-F10: rename a label colliding with the emitter's bookkeeping set.

    ``source`` → ``dataSource``. The rename target is itself collision-checked: if it is also
    reserved, fail loudly rather than silently clobber or double-rename.
    """
    cc = camel(col)
    if cc in reserved:
        renamed = "data" + cc[:1].upper() + cc[1:]  # source -> dataSource
        if renamed in reserved:
            raise InferenceError(
                f"cannot rename reserved label {col!r}: target {renamed!r} is also reserved "
                "(extend the rename rule)"
            )
        logger.info("FR-11: renamed reserved label %r → %r", col, renamed)
        return renamed
    return cc


def derive_measure_name(metric: str, taken: Sequence[str]) -> str:
    """FR-3 / R1-F8: derive the measure column name from the metric, disambiguated on collision.

    The measure name is the metric's last ``_``-delimited token (``gov_expenditure_amount`` →
    ``amount``). If that collides with an already-taken (emitted) column name, a deterministic
    numeric suffix is appended (``amount`` → ``amount2``) so two metrics stripping to the same
    name — or a metric colliding with a label already named ``amount`` — get distinct names.
    """
    base = camel(metric.split("_")[-1]) or "value"
    taken_set = set(taken)
    if base not in taken_set:
        return base
    i = 2
    while f"{base}{i}" in taken_set:
        i += 1
    logger.info("R1-F8: measure name %r collides; using %r", base, f"{base}{i}")
    return f"{base}{i}"


def infer_identity(
    records: Sequence[Mapping[str, object]],
    labels: Sequence[str],
    golden: Optional[Sequence[str]] = None,
) -> list[str]:
    """FR-4: the minimal label subset unique per raw series.

    Deterministic tie-break (R1-F1): fewest columns first; among equally-minimal subsets, prefer
    (a) the golden ``CONFLICT_COLUMNS`` if supplied, else (b) lexicographic label order. Display
    columns are excluded (R1-F2). Reads the RAW records (R1-F9) — one row per series.
    """
    n = len(records)
    if n == 0:
        raise InferenceError("cannot infer identity from an empty specimen")
    cands = [c for c in labels if not is_display_column(c, labels)]
    for size in range(1, len(cands) + 1):
        unique = [
            combo
            for combo in combinations(cands, size)
            if len({tuple(r.get(c) for c in combo) for r in records}) == n
        ]
        if not unique:
            continue
        if golden:  # tie-break (a): match the golden if it is among the equally-minimal subsets
            gset = set(golden)
            for combo in unique:
                if set(combo) == gset:
                    return list(combo)
        return list(sorted(unique, key=lambda s: sorted(s))[0])  # (b): lexicographic
    # No unique subset even using every candidate → the sampled series are not distinguishable.
    return list(cands)


# --------------------------------------------------------------------------- #
# Direct EntityGraph construction (the graph_from_prisma way, not extract_      #
# entities) + R1-S8 invariant replication.                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InferenceResult:
    """The product of inference: the graph, the rendered schema, and the identity provenance."""

    entity: str
    graph: EntityGraph
    schema: PrismaSchemaResult
    identity_labels: tuple[str, ...]  # raw specimen label names
    identity_fields: tuple[str, ...]  # emitted (camelCased/renamed) field names
    colmap: Mapping[str, str]  # raw label -> emitted field name
    measure_field: str

    @property
    def schema_text(self) -> str:
        return self.schema.text


def _default_entity_name(metric: str) -> str:
    """A mechanical PascalCase entity name from the metric (callers/CLI may override)."""
    tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", metric) if t]
    return "".join(t[:1].upper() + t[1:] for t in tokens) or "Series"


def assert_graph_invariants(graph: EntityGraph, entity: str, result: PrismaSchemaResult) -> None:
    """R1-S8: the directly-built graph must satisfy the post-conditions ``extract_entities`` gives.

    Enumerated + enforced here (rather than trusting the direct builder), and pinned by a
    contract test against the prose path's guarantees:

    1. the entity exists in the graph;
    2. every field's ``prisma_type`` is in the emitted-type vocabulary (never ``None`` /
       out-of-vocab — the prose path flags those unrenderable);
    3. no field name collides with the emitter's reserved bookkeeping set;
    4. field names are unique within the model;
    5. every ``@@unique`` column references a declared field;
    6. the emitter itself reports **no structural errors and nothing unrenderable** — the
       load-bearing agreement that the graph renders cleanly.
    """
    reserved = frozenset(reserved_field_names())
    ent = graph.entities.get(entity)
    if ent is None:
        raise InferenceError(f"R1-S8: entity {entity!r} missing from graph")

    names = [f.name for f in ent.fields]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise InferenceError(f"R1-S8: duplicate field name(s) {dupes} on {entity!r}")

    for f in ent.fields:
        if f.prisma_type not in PRISMA_SCALAR_TYPES:
            raise InferenceError(
                f"R1-S8: field {entity}.{f.name} has out-of-vocab prisma_type {f.prisma_type!r}"
            )
        if f.name in reserved:
            raise InferenceError(
                f"R1-S8/FR-11: field {entity}.{f.name} collides with a reserved bookkeeping name"
            )

    declared = set(names)
    for cols in graph.uniques.get(entity, []):
        missing = [c for c in cols if c not in declared]
        if missing:
            raise InferenceError(
                f"R1-S8: @@unique on {entity!r} references undeclared column(s) {missing}"
            )

    if result.errors:
        raise InferenceError(f"R1-S8: emitter reported structural errors: {list(result.errors)}")
    if result.unrenderable:
        raise InferenceError(f"R1-S8: emitter flagged unrenderable fields: {list(result.unrenderable)}")


# --------------------------------------------------------------------------- #
# Top-level inference.                                                           #
# --------------------------------------------------------------------------- #
def infer_schema(
    specimen: Specimen,
    *,
    entity_name: Optional[str] = None,
    identity: Optional[Sequence[str]] = None,
    golden_key: Optional[Sequence[str]] = None,
) -> InferenceResult:
    """Infer a ``schema.prisma`` from a raw specimen (FR-3/FR-4/FR-11) and render it.

    ``entity_name`` — the model name (defaults to a mechanical PascalCase of the metric).
    ``identity`` — an explicit ``--identity a,b,c`` that always wins (FR-4). ``golden_key`` — a
    known ``CONFLICT_COLUMNS`` used only as the R1-F1 tie-break (test/known-schema path).
    """
    specimen.assert_raw()  # R1-F9: identity inference reads the raw, un-collapsed specimen
    records = specimen.records
    labels = specimen.label_keys()
    if not labels:
        raise InferenceError(f"specimen for {specimen.metric!r} has no label columns to infer from")

    entity = entity_name or _default_entity_name(specimen.metric)
    reserved = frozenset(reserved_field_names())

    # 1. Types + emitted names for every label column.
    col_type = {c: infer_scalar_type([r.get(c) for r in records]) for c in labels}
    colmap = {c: rename_if_reserved(c, reserved) for c in labels}
    _guard_emitted_name_collisions(colmap)

    fields: list[DocField] = []
    for i, c in enumerate(labels):
        fields.append(
            DocField(
                name=colmap[c], plain_type=col_type[c], prisma_type=col_type[c],
                required=True, notes="", human_only=False, row_index=i,
            )
        )

    # 2. The measure column — forced Decimal (OQ-9), name derived from the metric (R1-F8).
    taken = [colmap[c] for c in labels]
    measure_field = derive_measure_name(specimen.metric, taken)
    fields.append(
        DocField(
            name=measure_field, plain_type="Decimal", prisma_type="Decimal",
            required=True, notes="", human_only=False, row_index=len(labels),
        )
    )

    # 3. observed_at — the one added TSDB-specific field (FR-3).
    fields.append(
        DocField(
            name=OBSERVED_AT_FIELD, plain_type="DateTime", prisma_type="DateTime",
            required=True, notes="", human_only=False, row_index=len(labels) + 1,
        )
    )

    graph = EntityGraph()
    graph.entities[entity] = DocEntity(name=entity, fields=tuple(fields), heading_path=())

    # 4. Identity → composite @@unique.
    if identity:
        id_labels = _validate_declared_identity(identity, labels)
    else:
        id_labels = infer_identity(records, labels, golden=golden_key)
    id_fields = tuple(colmap[c] for c in id_labels)
    graph.uniques[entity] = [id_fields]

    # 5. Render via the REAL emitter, then assert the R1-S8 invariants on the rendered result.
    result = render_prisma_schema(graph)
    assert_graph_invariants(graph, entity, result)

    logger.info(
        "inferred %s: %d labels, measure=%s, identity=%s",
        entity, len(labels), measure_field, list(id_fields),
    )
    return InferenceResult(
        entity=entity, graph=graph, schema=result,
        identity_labels=tuple(id_labels), identity_fields=id_fields,
        colmap=colmap, measure_field=measure_field,
    )


def _guard_emitted_name_collisions(colmap: Mapping[str, str]) -> None:
    """Two distinct labels camelCasing to the same emitted name would silently shadow (FR-3)."""
    seen: dict[str, str] = {}
    for raw, emitted in colmap.items():
        if emitted in seen:
            raise InferenceError(
                f"labels {seen[emitted]!r} and {raw!r} both map to emitted field {emitted!r} "
                "(would collide); disambiguate upstream"
            )
        seen[emitted] = raw


def _validate_declared_identity(identity: Sequence[str], labels: Sequence[str]) -> list[str]:
    """A declared ``--identity`` must reference real, non-reserved label columns (FR-4)."""
    unknown = [c for c in identity if c not in set(labels)]
    if unknown:
        raise InferenceError(
            f"--identity references unknown label column(s) {unknown}; "
            f"available: {sorted(labels)}"
        )
    if any(c in RESERVED_RECORD_KEYS for c in identity):
        raise InferenceError("--identity cannot include the reserved record keys value/observed_at")
    return list(identity)
