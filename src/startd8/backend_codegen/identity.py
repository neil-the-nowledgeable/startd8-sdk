"""FR-IMP-2: one identity-key declaration, shared by the AI persist path and the import path.

A row's *identity* is what makes two rows "the same row" for dedup / upsert. Today the AI layer
carries two ad-hoc, independently-grown keys on a pass — ``source_binding`` (source-scope) and
``dedup_by`` (single field, F-11) — and the new ``from_json`` import path (FR-IMP-1) needs the *same*
notion so import and AI-extraction agree on row identity instead of each inventing its own rule.

This module is the single source of truth: a small :class:`IdentityKey` value object plus
:func:`resolve_identity` that turns a manifest declaration (or the legacy keys) into one normalized
key. It is **pure** — no SQLModel, no I/O, no dependency on ``ai_layer`` — so it can be unit-tested
standalone and consumed by both call sites without coupling them (the "one declaration,
mode-specific application" seam, 2026-06-15).

The *application* of the key stays mode-specific and lives elsewhere:
  * ``name`` / ``field`` / ``composite`` → a per-row dedup query (``ai_layer._PERSIST_HELPER``).
  * ``source``                          → a once-per-run source-scope pre-clear in the harness body.
  * ``id``                              → the import upsert path (``app/import.py``).
This module only *names* the key; it does not emit persist code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence, Tuple, Union

IdentityKind = Literal["id", "field", "composite", "source", "name", "none"]

#: Kinds that dedup against a column value on the row itself (per-row application).
_ROW_KINDS = frozenset({"id", "field", "composite", "name"})


@dataclass(frozen=True)
class IdentityKey:
    """A normalized statement of what makes two rows the same row.

    ``kind``        one of :data:`IdentityKind`.
    ``fields``      the column(s) the key is over — empty for ``none``; one entry for
                    ``field``/``name`` and (when known) ``id``; >=1 for ``composite``.
    ``provenance``  for ``kind == "source"`` only: the server-stamped provenance field that
                    carries the ``source_id`` (e.g. ``Capability.sourceProofPointId``).
    """

    kind: IdentityKind
    fields: Tuple[str, ...] = ()
    provenance: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind == "source":
            if not self.provenance:
                raise ValueError("IdentityKey(kind='source') requires a provenance field")
            if self.fields:
                raise ValueError("IdentityKey(kind='source') keys on provenance, not `fields`")
        elif self.kind == "none":
            if self.fields or self.provenance:
                raise ValueError("IdentityKey(kind='none') carries no fields/provenance")
        elif self.kind == "composite":
            if len(self.fields) < 2:
                raise ValueError("IdentityKey(kind='composite') requires >= 2 fields")
            if self.provenance:
                raise ValueError("only kind='source' carries a provenance field")
        else:  # id | field | name
            if self.provenance:
                raise ValueError("only kind='source' carries a provenance field")
            # `id` may have its field unresolved (no schema given); field/name must name one column.
            if self.kind in ("field", "name") and len(self.fields) != 1:
                raise ValueError(f"IdentityKey(kind={self.kind!r}) requires exactly one field")
            if self.kind == "id" and len(self.fields) > 1:
                raise ValueError("IdentityKey(kind='id') resolves to a single primary-key field")

    # -- introspection used by both call sites ------------------------------- #

    @property
    def is_row_dedup(self) -> bool:
        """True when the key dedups against a column on the row (per-row application)."""
        return self.kind in _ROW_KINDS

    @property
    def is_source_scope(self) -> bool:
        """True when the key dedups at the whole-source layer (harness pre-clear)."""
        return self.kind == "source"

    @property
    def dedup_field(self) -> Optional[str]:
        """The single column a row-dedup keys on (``None`` for composite/source/none/unresolved)."""
        if self.kind in ("field", "name", "id") and len(self.fields) == 1:
            return self.fields[0]
        return None

    def describe(self) -> str:
        """A stable one-line label for headers / diagnostics (deterministic)."""
        if self.kind == "source":
            return f"source:{self.provenance}"
        if self.kind == "composite":
            return "composite:" + ",".join(self.fields)
        if self.fields:
            return f"{self.kind}:{self.fields[0]}"
        return self.kind


# Module-level singletons for the keyless kinds (stable identity, cheap).
NAME_KEY = IdentityKey(kind="name", fields=("name",))
NONE_KEY = IdentityKey(kind="none")


def _norm_fields(value: Union[str, Sequence[str]]) -> Tuple[str, ...]:
    """Normalize a declared field list: split a comma string, strip, drop blanks, preserve order."""
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = list(value)
    out = tuple(str(p).strip() for p in parts if str(p).strip())
    return out


def parse_declared_identity(
    declared: Union[str, Sequence[str], None],
    *,
    id_field: Optional[str] = None,
    where: str = "identity",
) -> Optional[IdentityKey]:
    """Parse an explicit ``identity:`` manifest value into an :class:`IdentityKey`, or ``None``.

    Accepted forms (the closed vocabulary):
      * ``"id"``                 → primary-key upsert (``id_field`` fills the column when known).
      * ``"name"``               → dedup on the ``name`` column (today's default).
      * ``"none"``               → no dedup (insert always).
      * ``"source:<field>"``     → source-scope, ``<field>`` stamped with the source id.
      * ``["a", "b"]`` / ``"a,b"`` → composite dedup over >= 2 columns.
      * any other single token   → ``field`` dedup on that column.

    ``None``/empty ``declared`` returns ``None`` (caller falls back to the legacy keys / default),
    so this never *invents* a key. Raises ``ValueError`` on a malformed declaration (fail-loud).
    """
    if declared is None:
        return None
    if isinstance(declared, str):
        token = declared.strip()
        if not token:
            return None
        low = token.lower()
        if low == "id":
            return IdentityKey(kind="id", fields=(id_field,) if id_field else ())
        if low == "name":
            return NAME_KEY
        if low == "none":
            return NONE_KEY
        if low.startswith("source:") or low == "source":
            field = token[len("source:"):].strip() if ":" in token else ""
            if not field:
                raise ValueError(
                    f"{where}: `source` identity requires a field — write `source:<field>`"
                )
            return IdentityKey(kind="source", provenance=field)
        if "," in token:
            fields = _norm_fields(token)
            return _composite_or_single(fields, where)
        return IdentityKey(kind="field", fields=(token,))
    # sequence form
    fields = _norm_fields(declared)
    if not fields:
        return None
    return _composite_or_single(fields, where)


def _composite_or_single(fields: Tuple[str, ...], where: str) -> IdentityKey:
    if not fields:
        raise ValueError(f"{where}: empty identity field list")
    if len(fields) == 1:
        return IdentityKey(kind="field", fields=fields)
    return IdentityKey(kind="composite", fields=fields)


def resolve_identity(
    *,
    declared: Union[str, Sequence[str], None] = None,
    source_binding: Optional[str] = None,
    dedup_by: Optional[str] = None,
    id_field: Optional[str] = None,
    where: str = "identity",
) -> IdentityKey:
    """Resolve the one identity key for a pass / import entry, applying declared > legacy > default.

    Precedence (R1-F1 dual-key precedence — deterministic, fail-loud on an explicit conflict):

      1. ``declared`` — an explicit ``identity:`` manifest value always wins.
      2. ``source_binding`` — the *effective* provenance field (caller passes
         ``effective_source_binding(...)`` so the explicit / schema-derived / ``none`` states are
         already collapsed). A non-empty value → ``source`` kind.
      3. ``dedup_by`` — the F-11 single-field key → ``field`` kind.
      4. default → ``name`` (today's behavior; the name-based ``_PERSIST_HELPER`` degrades to
         insert-always when the model has no ``name`` column).

    Passing *both* ``source_binding`` and ``dedup_by`` is a manifest conflict (each declares a
    different identity) → ``ValueError``. ``declared`` overrides both without conflict.
    """
    explicit = parse_declared_identity(declared, id_field=id_field, where=where)
    if explicit is not None:
        return explicit
    sb = source_binding.strip() if isinstance(source_binding, str) else source_binding
    db = dedup_by.strip() if isinstance(dedup_by, str) else dedup_by
    if sb and db:
        raise ValueError(
            f"{where}: a pass cannot declare both `source_binding` ({sb!r}) and `dedup_by` ({db!r}) "
            "— they are two different identities; pick one (or an explicit `identity:`)"
        )
    if sb:
        return IdentityKey(kind="source", provenance=sb)
    if db:
        return IdentityKey(kind="field", fields=(db,))
    return NAME_KEY
