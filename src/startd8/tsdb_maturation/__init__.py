"""TSDB → relational maturation (front-half of the relational generation story).

Turns observed time-series metrics into a generated relational app by **inferring a
``schema.prisma``** from metric label structure, then reusing the SDK's shipped ``$0``
back-half (``generate backend`` + importer). See
``docs/design/tsdb-to-relational/`` for the requirements (v0.5) and plan (v1.1).

Milestones (PLAN §5):

* **M0 — reader** (:mod:`startd8.tsdb_maturation.reader`) — FR-1. A bounded Prometheus/Mimir
  reader over ``last_over_time(<metric>[<lookback>])``.
* **M1 — specimen** (:mod:`startd8.tsdb_maturation.specimen`) — FR-2/FR-9. Flattens a read
  into a durable, raw, grain-labeled specimen file.
* **M2 — inference core** (:mod:`startd8.tsdb_maturation.infer`) — FR-3/FR-4/FR-11. Projects a
  raw specimen into an ``EntityGraph`` and renders ``schema.prisma`` via the real emitter.
* **M2.5 — confirmation gate** (:mod:`startd8.tsdb_maturation.confirmation`) — FR-4/R1-F7/R1-S6.
  A committed-ledger gate: an inferred identity key must be human-confirmed before promotion.
* **M3 — imports.yaml writer** (:mod:`startd8.tsdb_maturation.imports_writer`) — FR-14. Serializes
  the inferred identity into an ``imports.yaml`` the importer dedups on (R1-F3 round-trip).
* **M4 — gate wiring** (:mod:`startd8.tsdb_maturation.gate`) — FR-7. Reuses ``emit_schema_draft`` →
  ``promote_schema``, enforces the M2.5 confirmation, refuses empty/unrenderable.
* M5 — backend + backfill · M6 — CLI · M7 — histograms. (FR-5 reduction + FR-12 family grouper are
  the remaining M2 sub-tasks.)

M0–M4 (reader → specimen → inference → confirmation → imports writer → gate) are implemented.
"""

from __future__ import annotations

from .reader import (
    AuthError,
    DirectMimirEndpoint,
    Endpoint,
    EmptyMaterialization,
    GrafanaProxyEndpoint,
    MetricNotFound,
    ReadResult,
    Series,
    TsdbReader,
    TsdbReaderError,
)
from .specimen import (
    Grain,
    Specimen,
    SpecimenError,
    SpecimenSummary,
    flatten_series,
    load_specimen,
    summarize,
    write_specimen,
)
from .infer import (
    InferenceError,
    InferenceResult,
    infer_identity,
    infer_scalar_type,
    infer_schema,
)
from .confirmation import (
    ConfirmationError,
    ConfirmationRecord,
    ConfirmationRequired,
    ConfirmationStatus,
    confirm_inference,
    confirmation_status,
    is_confirmed,
    record_confirmation,
    render_confirmation_surface,
    require_confirmation,
)
from .imports_writer import (
    build_import_entry,
    generate_imports_yaml,
    inferred_identity_key,
    write_imports_yaml,
)
from .gate import PromotionResult, gate_and_promote

__all__ = [
    # M0 — reader
    "AuthError",
    "DirectMimirEndpoint",
    "Endpoint",
    "EmptyMaterialization",
    "GrafanaProxyEndpoint",
    "MetricNotFound",
    "ReadResult",
    "Series",
    "TsdbReader",
    "TsdbReaderError",
    # M1 — specimen
    "Grain",
    "Specimen",
    "SpecimenError",
    "SpecimenSummary",
    "flatten_series",
    "load_specimen",
    "summarize",
    "write_specimen",
    # M2 — inference core
    "InferenceError",
    "InferenceResult",
    "infer_identity",
    "infer_scalar_type",
    "infer_schema",
    # M2.5 — confirmation gate
    "ConfirmationError",
    "ConfirmationRecord",
    "ConfirmationRequired",
    "ConfirmationStatus",
    "confirm_inference",
    "confirmation_status",
    "is_confirmed",
    "record_confirmation",
    "render_confirmation_surface",
    "require_confirmation",
    # M3 — imports.yaml writer
    "build_import_entry",
    "generate_imports_yaml",
    "inferred_identity_key",
    "write_imports_yaml",
    # M4 — gate wiring
    "PromotionResult",
    "gate_and_promote",
]
