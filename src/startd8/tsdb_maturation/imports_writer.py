"""M3 — ``imports.yaml`` generator (FR-14) — the first programmatic manifest writer in the SDK.

Without this, ``generate backend`` emits **no importer** (it is emitted only when ``imports.yaml``
is present — ``assembler.py:148``), so TSDB rows — which have **no stable ``id``** — would dedup by
``id`` and infinitely duplicate on every backfill. This serializes the inferred identity into an
``imports.yaml`` that:

* ``parse_imports`` accepts (it is the round-trip oracle — ``imports_manifest.py``); and
* carries the inferred :class:`~startd8.backend_codegen.identity.IdentityKey` **semantically**, so
  the generated importer's ``_find_existing`` dedups on **exactly** those columns.

**R1-F3 semantic round-trip contract** — not merely "``parse_imports`` accepts", but
``parse_imports(generate(key)).identity == key`` on kind + ordered columns. A manifest that parses
but drifts (wrong column order / kind) would silently re-introduce duplication; the contract test
(``test_imports_writer.py``) asserts the fixed point over sampled keys.

The measure column and ``observed_at`` are ordinary payload fields (coerced free by the importer's
``_COERCE`` — Decimal/DateTime round-trip with no new code); only the **identity** must be declared.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence, Union

import yaml

from startd8.backend_codegen.identity import IdentityKey
from startd8.backend_codegen.imports_manifest import FORMATS, parse_imports
from startd8.logging_config import get_logger

from .infer import InferenceError, InferenceResult

logger = get_logger(__name__)

#: TSDB backfill is a lossless structured export (the specimen's flattened records → JSON), so the
#: import format is ``json`` (the ``from_json`` path). ``text`` (AI-extracted) is not the TSDB shape.
DEFAULT_FORMAT = "json"


def inferred_identity_key(result: InferenceResult) -> IdentityKey:
    """The :class:`IdentityKey` the emitted manifest MUST round-trip to (the R1-F3 target).

    Uses the emitted field names (``result.identity_fields``) — the columns the generated
    importer keys on (``getattr(model, k)``). One field → ``kind='field'``; two or more →
    ``kind='composite'``.
    """
    fields = tuple(result.identity_fields)
    return _key_from_fields(fields, where=result.entity)


def _key_from_fields(fields: Sequence[str], *, where: str) -> IdentityKey:
    fields = tuple(f for f in fields if f)
    if not fields:
        raise InferenceError(f"{where}: cannot build an import identity from an empty key")
    if len(fields) == 1:
        return IdentityKey(kind="field", fields=fields)
    return IdentityKey(kind="composite", fields=fields)


def build_import_entry(
    result: InferenceResult,
    *,
    fmt: str = DEFAULT_FORMAT,
    surface: bool = False,
) -> dict:
    """The ``imports.yaml`` ``imports:`` entry body for one inferred entity.

    Emits ``identity`` as a list of the emitted key columns (a 1-element list → ``field`` kind, a
    multi-element list → ``composite`` — resolved identically by ``parse_imports``).
    """
    if fmt not in FORMATS:
        raise InferenceError(f"unknown import format {fmt!r} (one of {sorted(FORMATS)})")
    key = inferred_identity_key(result)
    entry: dict = {"format": fmt, "identity": list(key.fields)}
    if surface:
        entry["surface"] = True
    return entry


def generate_imports_yaml(
    results: Sequence[InferenceResult],
    *,
    fmt: str = DEFAULT_FORMAT,
    surface: bool = False,
) -> str:
    """Serialize inferred entities into ``imports.yaml`` text that ``parse_imports`` accepts.

    Deterministic (entities sorted); self-validates by parsing its own output before returning, so
    a malformed manifest is a loud bug here, never a silent flag downstream.
    """
    if not results:
        raise InferenceError("generate_imports_yaml requires at least one inference result")
    entities = {}
    for result in results:
        if result.entity in entities:
            raise InferenceError(f"duplicate entity {result.entity!r} in imports generation")
        entities[result.entity] = build_import_entry(result, fmt=fmt, surface=surface)

    payload = {"imports": {name: entities[name] for name in sorted(entities)}}
    text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)

    # Self-check: our own output must parse, and each entity's parsed identity must match the
    # inferred key semantically (R1-F3). Fail loud here rather than emit a drifting manifest.
    _assert_round_trip(text, results)
    return text


def _assert_round_trip(text: str, results: Sequence[InferenceResult]) -> None:
    """R1-F3: ``parse_imports(generate(key)).identity == key`` for every emitted entity."""
    specs = {s.entity: s for s in parse_imports(text)}
    for result in results:
        spec = specs.get(result.entity)
        if spec is None:
            raise InferenceError(f"round-trip failure: {result.entity!r} not parsed back")
        expected = inferred_identity_key(result)
        if spec.identity != expected:
            raise InferenceError(
                f"R1-F3 round-trip drift for {result.entity!r}: emitted identity "
                f"{expected!r} but parsed back {spec.identity!r} (would dedup differently)"
            )


def write_imports_yaml(text: str, path: Union[str, Path]) -> Path:
    """Atomically write ``imports.yaml`` text to ``path``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    logger.debug("wrote imports.yaml: %s", path)
    return path
