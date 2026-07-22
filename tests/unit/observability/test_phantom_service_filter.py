"""#241 — filter the project umbrella-stem entry the producer sometimes emits.

A producer (cap-dev-pipe/ContextCore) can emit an instrumentation hint for the
workspace/repo ROOT (the composite project_id's umbrella stem, e.g. project
"mastodon-status-fanout" → stem "mastodon") that is structurally identical to a real
service and would otherwise get a full, wrong (HTTP-shaped) artifact set. The stem is
now filtered; a single-word project name that IS a service is preserved.
"""

from startd8.observability.artifact_generator_context import (
    _is_non_service_entry,
    extract_service_hints,
)

_HTTP_HINT = {
    "transport": "http",
    "metrics": {"convention_based": [
        {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"}
    ]},
}


def _meta(project_id, hints):
    return {"project_id": project_id, "instrumentation_hints": hints}


class TestUmbrellaStemFilter:
    def test_umbrella_stem_is_filtered(self):
        # The #241 case (correctly-spelled): project "mastodon-status-fanout",
        # a phantom "mastodon" (workspace root) alongside the real services.
        svcs = extract_service_hints(_meta("mastodon-status-fanout", {
            "mastodon": dict(_HTTP_HINT, service_id="mastodon"),           # phantom (stem)
            "mastodonweb": dict(_HTTP_HINT, service_id="mastodonweb"),
            "mastodonsidekiq": dict(_HTTP_HINT, service_id="mastodonsidekiq"),
        }))
        ids = {s.service_id for s in svcs}
        assert ids == {"mastodonweb", "mastodonsidekiq"}
        assert "mastodon" not in ids

    def test_full_project_id_still_filtered(self):
        # Pre-existing behavior preserved: the project_id itself is a non-service.
        assert _is_non_service_entry(
            "mastodon-status-fanout", _HTTP_HINT, _meta("mastodon-status-fanout", {})
        )

    def test_stem_filter_only_exact_match_not_near_stem(self):
        # Guard against over-filtering: for project "payment-gateway" (stem "payment"),
        # a service "payments" (near, not equal to the stem) must be preserved; only an
        # exact "payment" would be dropped.
        svcs = extract_service_hints(_meta("payment-gateway", {
            "payments": dict(_HTTP_HINT, service_id="payments"),
            "payment-worker": dict(_HTTP_HINT, service_id="payment-worker"),
        }))
        assert {s.service_id for s in svcs} == {"payments", "payment-worker"}
        # ...but the exact stem IS the umbrella and gets filtered:
        assert _is_non_service_entry("payment", _HTTP_HINT, _meta("payment-gateway", {}))

    def test_real_service_sharing_stem_prefix_preserved(self):
        # Only an EXACT stem match is filtered — "mastodonweb" (stem-prefixed) stays.
        assert not _is_non_service_entry(
            "mastodonweb", _HTTP_HINT, _meta("mastodon-status-fanout", {})
        )

    def test_typo_residual_is_documented_not_caught(self):
        # Honest limit (producer bug): a workspace basename that does NOT stem-match
        # (typo "mastadon" vs stem "mastodon") is structurally indistinguishable and is
        # NOT filtered here — visibility log is the defense. This test pins the known
        # residual so a future "why isn't this caught" is answered in-place.
        assert not _is_non_service_entry(
            "mastadon", _HTTP_HINT, _meta("mastodon-status-fanout", {})
        )
