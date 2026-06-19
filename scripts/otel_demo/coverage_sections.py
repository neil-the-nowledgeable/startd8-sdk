"""§4 landscape coverage sections — shared by attest_coverage.py and verify_coverage.py."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "1.0"
SUPPORTED_MAJOR = 1


@dataclass(frozen=True)
class CoverageSection:
    section_id: str
    landscape_ref: str
    signal: str
    backend: str
    check_type: str
    query: str
    threshold: int
    window: str
    tier_required: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)


def default_sections(*, include_profiles: bool = False) -> list[CoverageSection]:
    """Return the §4 acceptance rows from TIER0_REFERENCE_ENV_REQUIREMENTS.md."""
    sections = [
        CoverageSection(
            section_id="2-traces",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#2-telemetry-signals",
            signal="traces",
            backend="jaeger",
            check_type="jaeger_services_with_traces",
            query="GET /api/services → GET /api/traces?service=<svc>",
            threshold=1,
            window="5m",
        ),
        CoverageSection(
            section_id="2-metrics",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#2-telemetry-signals",
            signal="metrics",
            backend="prometheus",
            check_type="prometheus_metric_patterns",
            query=(
                "count(rpc_server_duration_milliseconds_count) + "
                "count(http_server_request_duration_seconds_count)"
            ),
            threshold=1,
            window="instant",
            params={
                "patterns": [
                    "rpc_server_duration",
                    "http_server_request_duration",
                ],
            },
        ),
        CoverageSection(
            section_id="3.1-languages",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#31-first-class-language-sdks",
            signal="traces",
            backend="jaeger",
            check_type="jaeger_distinct_process_tag",
            query='distinct process.tags["telemetry.sdk.language"]',
            threshold=5,
            window="15m",
            params={"tag_key": "telemetry.sdk.language"},
        ),
        CoverageSection(
            section_id="4.1-otlp",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#41-otlp--primary-telemetry-wire-protocol",
            signal="traces",
            backend="collector",
            check_type="collector_otlp_receivers",
            query="parse otel-config: receivers.otlp.protocols has grpc and http",
            threshold=2,
            window="n/a",
            params={"required": ["grpc", "http"]},
        ),
        CoverageSection(
            section_id="5.3-grpc",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#53-rpc-including-grpc",
            signal="traces",
            backend="jaeger",
            check_type="jaeger_span_tag",
            query='spans where tag rpc.system="grpc"',
            threshold=1,
            window="5m",
            params={"tag_key": "rpc.system", "tag_value": "grpc"},
        ),
        CoverageSection(
            section_id="5.4-messaging",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#54-messaging",
            signal="traces",
            backend="jaeger",
            check_type="jaeger_messaging_kafka",
            query='messaging.system="kafka" and kind in (PRODUCER,CONSUMER)',
            threshold=1,
            window="15m",
            params={
                "messaging_key": "messaging.system",
                "messaging_value": "kafka",
                "observed_names": ["messaging.system", "messaging.destination.name"],
            },
        ),
        CoverageSection(
            section_id="5.5-database",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#55-database",
            signal="traces",
            backend="jaeger",
            check_type="jaeger_span_tag_any",
            query='db.system in {postgresql,valkey,redis}',
            threshold=1,
            window="15m",
            params={
                "tag_key": "db.system",
                "tag_values": ["postgresql", "valkey", "redis"],
                "observed_names": ["db.system"],
            },
        ),
        CoverageSection(
            section_id="5.6-feature-flags",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#56-graphql-faas-feature-flags-genai",
            signal="traces",
            backend="jaeger",
            check_type="jaeger_span_tag",
            query="spans/events with tag feature_flag.key",
            threshold=1,
            window="15m",
            params={"tag_key": "feature_flag.key", "observed_names": ["feature_flag.key"]},
        ),
        CoverageSection(
            section_id="7.1-connector",
            landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#71-pipeline-model",
            signal="metrics",
            backend="prometheus",
            check_type="prometheus_metric_patterns",
            query='count({__name__=~"traces_span_metrics_.*"})',
            threshold=1,
            window="instant",
            params={"patterns": ["traces_span_metrics"], "observed_names": ["traces_span_metrics"]},
        ),
    ]
    if include_profiles:
        sections.insert(
            2,
            CoverageSection(
                section_id="2-profiles",
                landscape_ref="OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md#2-telemetry-signals",
                signal="profiles",
                backend="pyroscope",
                check_type="pyroscope_apps",
                query="profile series for any service label",
                threshold=1,
                window="5m",
                tier_required="profile",
            ),
        )
    return sections


def validate_schema_version(raw: str) -> None:
    """Reject attestations whose major schema_version we do not understand (FR-5a)."""
    parts = raw.split(".", 1)
    if not parts or not parts[0].isdigit():
        raise ValueError(f"invalid schema_version: {raw!r}")
    major = int(parts[0])
    if major != SUPPORTED_MAJOR:
        raise ValueError(f"unsupported schema_version major {major} (supported: {SUPPORTED_MAJOR})")
