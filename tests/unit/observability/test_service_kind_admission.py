"""#226 Phase 2a — FR-14: relax the transport-required drop for kind-declaring services.

The CRP's load-bearing finding: the ∅-coverage path (FR-9/FR-12) is dead code while
`extract_service_hints` hard-drops any hint with no `transport`. FR-14 admits a
non-request workload that declares a `kind`, while preserving byte-parity for every
existing http/grpc service (drop still fires when BOTH transport and kind are absent).
"""

from startd8.observability.artifact_generator_context import extract_service_hints


def _meta(hints):
    return {"project_id": "t", "instrumentation_hints": hints}


class TestTransportlessKindAdmission:
    def test_worker_with_kind_no_transport_is_admitted(self):
        # The core FR-14 case: a Sidekiq-style worker with no listen transport but a
        # declared kind must survive to reach the resolver (was dropped pre-#226).
        svcs = extract_service_hints(
            _meta({"mailer": {"service_id": "mailer", "kind": "async_worker"}})
        )
        assert [s.service_id for s in svcs] == ["mailer"]
        assert svcs[0].transport == ""
        assert svcs[0].kinds == ["async_worker"]

    def test_no_transport_and_no_kind_still_skipped(self):
        # Byte-parity guard: nothing to determine ⇒ preserve pre-#226 drop.
        svcs = extract_service_hints(_meta({"ghost": {"service_id": "ghost"}}))
        assert svcs == []

    def test_http_service_unchanged(self):
        # Existing request-server path is untouched (transport present, no kind).
        svcs = extract_service_hints(
            _meta({"api": {"service_id": "api", "transport": "http"}})
        )
        assert len(svcs) == 1
        assert svcs[0].transport == "http"
        assert svcs[0].kinds == []

    def test_kind_list_normalized_and_deduped(self):
        # FR-12b: hybrid services carry more than one kind; accept a list, de-dupe,
        # preserve order.
        svcs = extract_service_hints(
            _meta(
                {
                    "web": {
                        "service_id": "web",
                        "transport": "http",
                        "kind": ["http_server", "async_worker", "http_server"],
                    }
                }
            )
        )
        assert svcs[0].kinds == ["http_server", "async_worker"]

    def test_blank_kind_string_ignored(self):
        svcs = extract_service_hints(
            _meta({"x": {"service_id": "x", "transport": "grpc", "kind": "  "}})
        )
        assert svcs[0].kinds == []
