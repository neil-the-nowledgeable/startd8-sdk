# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""#308 P3 — link-aware cross-trace freshness (the trace-native alternative to the synthetic probe).

Mastodon's fan-out is cross-trace (`propagation_style: :link`): `FeedInsertWorker` runs in its OWN trace
with a span *link* back to the enqueue — so freshness (create → feed-visible) is NOT a single-trace
duration and a span-metrics connector (#307) can't produce it. This module is the **pure delta-compute
core** (FR-P3-1): given the two linked spans, compute `t(feed-visible) − t(created)`.

Pure/no-I/O and unit-tested on synthetic `SpanLite` inputs. The live proof (FR-P3-3) is trace-gated: a
Tempo-file adapter (OQ-3) maps real trace JSON → `SpanLite`; that live validation is external and is NOT
claimed from these unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class SpanLink:
    """A span link target (the minimal identity needed to follow a `:link` edge)."""

    trace_id: str
    span_id: str


@dataclass(frozen=True)
class SpanLite:
    """The minimal span shape the delta core needs (FR-P3-1 declared contract). Timestamps in
    NANOSECONDS (OTLP native). A Tempo-file adapter maps real trace JSON onto this."""

    trace_id: str
    span_id: str
    start_ns: int
    end_ns: int
    name: str = ""
    links: List[SpanLink] = field(default_factory=list)


@dataclass(frozen=True)
class FreshnessResult:
    """The outcome of a link-aware freshness computation. ``status`` is one of:
    ``ok`` (``delta_seconds`` set, ≥ 0), ``unlinkable`` (the worker span does not link the enqueue span),
    ``error`` (malformed input, e.g. reversed timestamps) — never a silent negative/zero."""

    status: str
    delta_seconds: Optional[float] = None
    detail: str = ""


def _links_to(worker: SpanLite, enqueue: SpanLite) -> bool:
    """True iff *worker* carries a span link to *enqueue* (the `:link` fan-out edge)."""
    return any(lk.trace_id == enqueue.trace_id and lk.span_id == enqueue.span_id
               for lk in worker.links)


def compute_fanout_freshness(enqueue: SpanLite, worker: SpanLite) -> FreshnessResult:
    """Compute fan-out freshness = t(feed-visible) − t(created) from the enqueue span (the write that
    created the status) and the linked worker span (`FeedInsertWorker`, feed-visible on its end).

    Convention: ``created`` = ``enqueue.start_ns``; ``feed-visible`` = ``worker.end_ns``; delta in seconds,
    MUST be ≥ 0. Errors are typed, never a silent negative/zero (FR-P3-1):
    - the worker span must LINK the enqueue span → else ``unlinkable``;
    - each span's ``end_ns`` must be ≥ its ``start_ns`` → else ``error``;
    - ``worker.end_ns`` must be ≥ ``enqueue.start_ns`` → else ``error`` (clock skew / wrong pairing)."""
    if enqueue.end_ns < enqueue.start_ns or worker.end_ns < worker.start_ns:
        return FreshnessResult(status="error", detail="a span end precedes its start")
    if not _links_to(worker, enqueue):
        return FreshnessResult(
            status="unlinkable",
            detail=f"worker span {worker.span_id!r} carries no link to enqueue {enqueue.span_id!r}")
    delta_ns = worker.end_ns - enqueue.start_ns
    if delta_ns < 0:
        return FreshnessResult(status="error", detail="feed-visible precedes creation (skew/mispairing)")
    return FreshnessResult(status="ok", delta_seconds=delta_ns / 1e9)
