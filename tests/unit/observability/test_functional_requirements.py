"""#226 Phase 2b — FR-4/FR-5: consume spec.requirements.functional[].

The consumption plumbing: the generator now reads the plan's per-FR observability
intents (id/signal_kind/target/service) into BusinessContext, and those signal_kinds
feed the determination (resolve_sli_kinds). Inert until CR-1 ships functional[]
upstream; absent ⇒ empty ⇒ byte-identical pre-#226 path.
"""

import textwrap

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext,
    FunctionalRequirement,
    load_business_context,
)
from startd8.observability.metric_descriptor import resolve_sli_kinds


def _manifest(tmp_path, body: str):
    p = tmp_path / ".contextcore.yaml"
    p.write_text(textwrap.dedent(body))
    return p


class TestFunctionalConsumption:
    def test_functional_requirements_parsed(self, tmp_path):
        mf = _manifest(
            tmp_path,
            """
            apiVersion: contextcore.io/v1alpha2
            kind: ContextManifest
            spec:
              business: {criticality: high}
              requirements:
                availability: "99.9"
                functional:
                  - {id: FR-006, signal_kind: queue_depth, description: backpressure, target: "1000"}
                  - {id: FR-007, signal_kind: freshness, service: mastodonsidekiq}
            """,
        )
        ctx = load_business_context(mf, {})
        assert [f.id for f in ctx.functional_requirements] == ["FR-006", "FR-007"]
        assert ctx.functional_requirements[0].signal_kind == "queue_depth"
        assert ctx.functional_requirements[0].target == "1000"
        assert ctx.functional_requirements[1].service == "mastodonsidekiq"

    def test_absent_functional_is_empty_list(self, tmp_path):
        mf = _manifest(
            tmp_path,
            """
            spec:
              requirements: {availability: "99"}
            """,
        )
        assert load_business_context(mf, {}).functional_requirements == []

    def test_non_dict_functional_entries_ignored(self, tmp_path):
        mf = _manifest(
            tmp_path,
            """
            spec:
              requirements:
                functional: ["not-a-dict", {id: FR-1, signal_kind: latency}]
            """,
        )
        frs = load_business_context(mf, {}).functional_requirements
        assert [f.id for f in frs] == ["FR-1"]

    def test_declared_signal_kinds_reach_the_resolver(self):
        # The end the plumbing serves: a declared signal_kind enters the SLI set,
        # additive to a request service's RED base (OQ-6).
        frs = [FunctionalRequirement(id="FR-006", signal_kind="queue_depth")]
        sli = resolve_sli_kinds(
            transport="http",
            signal_kinds=[f.signal_kind for f in frs],
        )
        assert "queue_depth" in sli
        assert {"latency", "availability", "throughput"} <= sli
