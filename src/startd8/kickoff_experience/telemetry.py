"""M8 — kickoff observability: OTel spans + the kickoff funnel events (FR-15).

Dependency-tolerant, mirroring ``agents/agentic_otel``: instrumentation is unconditional; export
only happens when a real ``TracerProvider`` is configured. When OpenTelemetry is absent every call
is a cheap no-op.

Span tree::

    kickoff.session
      ├── kickoff.step          (step entered)
      └── kickoff.capture       (a capture attempt → field_captured | capture_failed | gap_closed)

The funnel (R2-F7) is the set of named events below — a dashboard counts them to compute
completion / dropoff and write-failure rates. Capture failures carry the M6 typed reason code
(R4-F4) as an attribute, so telemetry, UI copy, and tests share one vocabulary.

In addition to OTel span events, every event is fanned out to registered :data:`_SINKS`, which makes
the funnel directly testable without a collector (see :func:`record_events`).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List

try:
    from opentelemetry import trace as _trace

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover
    _OTEL_AVAILABLE = False

_TRACER_NAME = "startd8.kickoff_experience"

# The kickoff funnel event names (R2-F7).
EV_SESSION_STARTED = "session_started"
EV_STEP_ENTERED = "step_entered"
EV_PREVIEW_BUILT = "preview_built"
EV_FIELD_CAPTURED = "field_captured"
EV_GAP_CLOSED = "gap_closed"
EV_CAPTURE_FAILED = "capture_failed"
EV_FRICTION_LOGGED = "friction_logged"
# Concierge mode (M-CM5)
EV_SURVEY_VIEWED = "survey_viewed"
EV_KICKOFF_INSTANTIATED = "kickoff_instantiated"
EV_CONCIERGE_WRITE_REFUSED = "concierge_write_refused"
# Agentic Concierge (proposals)
EV_PROPOSAL_MADE = "proposal_made"
EV_PROPOSAL_CONFIRMED = "proposal_confirmed"
EV_PROPOSAL_DISCARDED = "proposal_discarded"
# Welcome Mat 2.0 — template download (FR-WM2-14).
EV_TEMPLATE_DOWNLOADED = "template_downloaded"
EV_TEMPLATE_BUNDLE_DOWNLOADED = "template_bundle_downloaded"
# Welcome Mat 2.0 — agentic chat (FR-WM2-14a). One success event + one refusal event; the specific
# refusal reason (rate_limited / budget_exceeded / session_expired / busy / message_too_long /
# preview_only / chat_<stop_reason> / error) rides the bounded `code` attribute (mirrors
# concierge_write_refused), so the funnel vocabulary stays small. NEVER carries message text.
EV_CHAT_TURN = "chat_turn"
EV_CHAT_REFUSED = "chat_refused"
# Red Carpet Treatment — the staged build funnel (FR-RCT-14). The per-input propose/apply events are
# already covered by proposal_made/confirmed; these add the STAGE-level progress the conductor drives.
EV_RED_CARPET_STARTED = "red_carpet_started"
EV_RED_CARPET_STAGE = "red_carpet_stage"             # attrs: stage, status (next | done)
EV_RED_CARPET_CASCADE_OFFERED = "red_carpet_cascade_offered"
EV_RED_CARPET_ADVICE = "red_carpet_advice"           # FR-RCA-16 — numeric counts only, never text/paths

FUNNEL_EVENTS = (
    EV_SESSION_STARTED,
    EV_STEP_ENTERED,
    EV_PREVIEW_BUILT,
    EV_FIELD_CAPTURED,
    EV_GAP_CLOSED,
    EV_CAPTURE_FAILED,
    EV_FRICTION_LOGGED,
    EV_SURVEY_VIEWED,
    EV_KICKOFF_INSTANTIATED,
    EV_CONCIERGE_WRITE_REFUSED,
    EV_PROPOSAL_MADE,
    EV_PROPOSAL_CONFIRMED,
    EV_PROPOSAL_DISCARDED,
    EV_TEMPLATE_DOWNLOADED,
    EV_TEMPLATE_BUNDLE_DOWNLOADED,
    EV_CHAT_TURN,
    EV_CHAT_REFUSED,
    EV_RED_CARPET_STARTED,
    EV_RED_CARPET_STAGE,
    EV_RED_CARPET_CASCADE_OFFERED,
    EV_RED_CARPET_ADVICE,
)

# Attribute allowlist for Concierge events (R2-F4 privacy): NEVER emit free-text friction fields or
# raw filesystem paths — only these bounded keys are permitted on Concierge funnel events.
CONCIERGE_EVENT_ATTR_ALLOWLIST = frozenset(
    {"action", "code", "posture", "with_authoring", "written_count", "skipped_count", "mode", "source"}
)

# Attribute allowlist for Welcome Mat 2.0 events (FR-WM2-14, R3-S3): bounded slugs only — the manifest
# `key`/`group` are closed-vocabulary slugs, never raw filesystem paths; no message text is ever emitted.
WM2_EVENT_ATTR_ALLOWLIST = frozenset(
    {"key", "group", "posture", "with_authoring", "count", "code", "mode",
     # chat_turn numeric telemetry (FR-WM2-14a) — never the user message text
     "turns", "tokens", "cost_usd", "stop_reason",
     # Red Carpet stage funnel (FR-RCT-14) — bounded stage slugs, never interview text or paths
     "stage", "status",
     # Red Carpet advisory summary (FR-RCA-16) — NUMERIC COUNTS ONLY, never advisory text/values/paths.
     # Severity counts + n_next_steps + a fixed per-kind count (kinds are a closed vocabulary).
     "n_advisories", "n_error", "n_warn", "n_info", "n_next_steps",
     "n_schema_shape", "n_input_gap", "n_input_invalid", "n_cascade_blocker",
     "n_provenance_review", "n_stakeholder"}
)


@dataclass(frozen=True)
class KickoffEvent:
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)


_SINKS: List[Callable[[KickoffEvent], None]] = []


def add_sink(sink: Callable[[KickoffEvent], None]) -> None:
    _SINKS.append(sink)


def remove_sink(sink: Callable[[KickoffEvent], None]) -> None:
    try:
        _SINKS.remove(sink)
    except ValueError:
        pass


class _NoopSpan:
    def set_attribute(self, *a: Any, **k: Any) -> None: ...
    def add_event(self, *a: Any, **k: Any) -> None: ...
    def record_exception(self, *a: Any, **k: Any) -> None: ...


@contextmanager
def kickoff_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Start a kickoff span as current; no-op when OTel is unavailable."""
    if not _OTEL_AVAILABLE:
        yield _NoopSpan()
        return
    tracer = _trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name) as span:
        for k, v in attributes.items():
            if v is not None:
                span.set_attribute(f"kickoff.{k}", v)
        yield span


def emit(name: str, **attributes: Any) -> None:
    """Record a funnel event: as an OTel event on the current span AND to every sink."""
    attrs = {k: v for k, v in attributes.items() if v is not None}
    if _OTEL_AVAILABLE:
        span = _trace.get_current_span()
        if span is not None and getattr(span, "is_recording", lambda: False)():
            span.add_event(
                f"kickoff.{name}",
                attributes={k: str(v) for k, v in attrs.items()},
            )
    event = KickoffEvent(name=name, attributes=attrs)
    for sink in list(_SINKS):
        try:
            sink(event)
        except Exception:  # a sink must never break the experience
            continue


@contextmanager
def record_events() -> Iterator[List[KickoffEvent]]:
    """Test/inspection helper: collect every emitted event for the duration of the block."""
    collected: List[KickoffEvent] = []
    sink = collected.append
    add_sink(sink)
    try:
        yield collected
    finally:
        remove_sink(sink)
