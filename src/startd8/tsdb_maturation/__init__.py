"""TSDB → relational maturation (front-half of the relational generation story).

Turns observed time-series metrics into a generated relational app by **inferring a
``schema.prisma``** from metric label structure, then reusing the SDK's shipped ``$0``
back-half (``generate backend`` + importer). See
``docs/design/tsdb-to-relational/`` for the requirements (v0.5) and plan (v1.1).

Milestones (PLAN §5):

* **M0 — reader** (:mod:`startd8.tsdb_maturation.reader`) — FR-1, this module. A bounded
  Prometheus/Mimir reader over ``last_over_time(<metric>[<lookback>])``.
* M1 — specimen · M2 — inference core · M2.5 — confirmation gate · M3 — ``imports.yaml``
  generator · M4 — gate wiring · M5 — backend + backfill · M6 — CLI · M7 — histograms.

Only M0 is implemented so far.
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

__all__ = [
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
]
