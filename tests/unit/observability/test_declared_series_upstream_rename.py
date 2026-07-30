"""FR-2 identity correction: mixin-harvested stale compact deletion-marker family.

derivation_0_compact_5_dead_slis_live_binding_0.6556 — upstream Thanos renamed
``thanos_compact_blocks_marked_for_deletion_total`` →
``thanos_compact_blocks_marked_total{marker}`` (CHANGELOG PR #3410). Harvest still
banks the stale mixin name; the parse boundary rewrites it so declared-base SLOs
emit the live PromQL (R2-S2: preserve deletion-marker label semantics).
"""

from startd8.observability.artifact_generator_context import (
    _apply_declared_series_upstream_rename,
    _parse_declared_series,
)
from startd8.observability.artifact_generator_generators import generate_declared_base_slos
from startd8.observability.artifact_generator_models import BusinessContext, ServiceHints


def test_rename_helper_injects_deletion_marker_label():
    name, labels = _apply_declared_series_upstream_rename(
        "thanos_compact_blocks_marked_for_deletion_total", {}
    )
    assert name == "thanos_compact_blocks_marked_total"
    assert labels == {"marker": "deletion-mark.json"}


def test_rename_helper_author_labels_win():
    name, labels = _apply_declared_series_upstream_rename(
        "thanos_compact_blocks_marked_for_deletion_total",
        {"marker": "custom.json", "reason": "manual"},
    )
    assert name == "thanos_compact_blocks_marked_total"
    assert labels == {"marker": "custom.json", "reason": "manual"}


def test_rename_helper_passthrough_unknown():
    name, labels = _apply_declared_series_upstream_rename(
        "thanos_compact_downsample_total", {"resolution": "5m"}
    )
    assert name == "thanos_compact_downsample_total"
    assert labels == {"resolution": "5m"}


def test_parse_rewrites_stale_compact_deletion_marker():
    parsed = _parse_declared_series(
        [
            {
                "name": "thanos_compact_blocks_marked_for_deletion_total",
                "type": "counter",
                "covers": ["throughput"],
            }
        ]
    )
    assert len(parsed) == 1
    assert parsed[0].name == "thanos_compact_blocks_marked_total"
    assert parsed[0].labels == {"marker": "deletion-mark.json"}
    assert "thanos_compact_blocks_marked_for_deletion_total" not in parsed[0].name


def test_declared_base_slo_emits_live_family_with_marker_selector():
    """R2-S2: emitted PromQL must select marker=deletion-mark.json, not bare family."""
    service = ServiceHints(
        service_id="compact",
        transport="http",
        declared_emitted_series=_parse_declared_series(
            [
                {
                    "name": "thanos_compact_blocks_marked_for_deletion_total",
                    "type": "counter",
                    "covers": ["throughput"],
                }
            ]
        ),
    )
    result = generate_declared_base_slos(service, BusinessContext())
    assert result.status == "generated"
    body = result.content or ""
    assert "thanos_compact_blocks_marked_total" in body
    assert 'marker="deletion-mark.json"' in body
    assert "thanos_compact_blocks_marked_for_deletion_total" not in body
