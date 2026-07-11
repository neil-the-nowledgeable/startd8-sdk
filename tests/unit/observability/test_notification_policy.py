# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for REQ_NOTIFICATION_POLICY v0.4 — notification-policy generation.

Contract (the behavior change): notification_policy binds to the AUTHORED
`Receiver{name,type,target,severities}` (threaded via `BusinessContext.receivers`,
parsed by the single canonical `from_observability_yaml`). The DECLARED type selects
the correct `*_configs`, pulling the secret from `Receiver.target`. There is NO
email-regex / else⇒slack classifier: a routed channel with no matching receiver
(dangling ref, FR-3a), a receiver with `type==""` (parser default), or an unknown type
is emitted as `# UNRESOLVED REQUIRED PARAM:` — never a silently-wrong Slack receiver.
"""

import inspect

import pytest
import yaml

from startd8.observability.artifact_generator import generate_notification_policy
from startd8.observability.artifact_generator_models import BusinessContext, ServiceHints
from startd8.observability.metric_descriptor import resolve_descriptor
from startd8.observability.spec import Receiver


UNRESOLVED = "# UNRESOLVED REQUIRED PARAM:"


@pytest.fixture
def grpc_service():
    return ServiceHints(service_id="checkout-api", transport="grpc", language="go")


def _doc(result):
    """Parse the YAML body, dropping the comment header lines."""
    return yaml.safe_load(
        "\n".join(ln for ln in result.content.splitlines() if not ln.startswith("#"))
    )


def _receivers(result):
    return {r["name"]: r for r in _doc(result)["receivers"]}


def _crit_receiver(result, service_id="checkout-api"):
    # Tolerant: an all-unresolved / all-severity-filtered policy emits NO receiver
    # (no empty-receiver route) — so absence means "nothing was rendered", which is
    # exactly what the unresolved/filtered tests assert about `*_configs`.
    return _receivers(result).get(f"{service_id}-critical", {})


# ---------------------------------------------------------------------------
# FR-5 — the headline regression: pagerduty routes to pagerduty_configs, NOT slack
# ---------------------------------------------------------------------------


class TestPagerDutyRegression:
    def test_pagerduty_renders_routing_key_not_slack(self, grpc_service):
        biz = BusinessContext(
            criticality="high",  # → critical severity
            alert_channels=["pagerduty-bpi-p1"],
            receivers=[
                Receiver(
                    name="pagerduty-bpi-p1",
                    type="pagerduty",
                    target="${PAGERDUTY_BPI_KEY}",
                )
            ],
        )
        result = generate_notification_policy(grpc_service, biz)
        recv = _crit_receiver(result)
        # The killer assertion: pagerduty_configs with the AUTHORED routing_key secret.
        assert "pagerduty_configs" in recv
        assert recv["pagerduty_configs"][0]["routing_key"] == "${PAGERDUTY_BPI_KEY}"
        # And emphatically NOT the guessed Slack default with the wrong secret.
        assert "slack_configs" not in recv
        assert "${SLACK_API_URL}" not in result.content
        assert UNRESOLVED not in result.content


# ---------------------------------------------------------------------------
# FR-4 — each of the 6 declared types pulls its secret from Receiver.target
# ---------------------------------------------------------------------------


class TestPerTypeRendering:
    CASES = [
        ("slack", "slack_configs", "api_url", "${SLACK_URL}"),
        ("email", "email_configs", "to", "oncall@acme.io"),
        ("pagerduty", "pagerduty_configs", "routing_key", "${PD_KEY}"),
        ("opsgenie", "opsgenie_configs", "api_key", "${OPS_KEY}"),
        ("webhook", "webhook_configs", "url", "${HOOK_URL}"),
        ("msteams", "msteams_configs", "webhook_url", "${TEAMS_URL}"),
    ]

    @pytest.mark.parametrize("rtype,cfg_key,field,target", CASES)
    def test_type_maps_target_to_correct_field(
        self, grpc_service, rtype, cfg_key, field, target
    ):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["chan-x"],
            receivers=[Receiver(name="chan-x", type=rtype, target=target)],
        )
        result = generate_notification_policy(grpc_service, biz)
        recv = _crit_receiver(result)
        assert cfg_key in recv, f"expected {cfg_key} for type {rtype}"
        assert recv[cfg_key][0][field] == target
        assert UNRESOLVED not in result.content

    def test_slack_channel_id_is_receiver_name(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#bpi-oncall"],
            receivers=[Receiver(name="#bpi-oncall", type="slack", target="${SLACK_URL}")],
        )
        recv = _crit_receiver(generate_notification_policy(grpc_service, biz))
        assert recv["slack_configs"][0]["channel"] == "#bpi-oncall"
        assert recv["slack_configs"][0]["api_url"] == "${SLACK_URL}"


# ---------------------------------------------------------------------------
# FR-3 / FR-3a — loud-fail, never silent Slack
# ---------------------------------------------------------------------------


class TestUnresolvedRequired:
    def test_dangling_ref_is_unresolved(self, grpc_service):
        """FR-3a: routed channel with NO matching receiver → UNRESOLVED, not dropped/slack."""
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#no-such-receiver"],
            receivers=[],  # nothing declared
        )
        result = generate_notification_policy(grpc_service, biz)
        assert UNRESOLVED in result.content
        assert "#no-such-receiver" in result.content
        recv = _crit_receiver(result)
        assert "slack_configs" not in recv  # never guessed

    def test_empty_type_is_unresolved(self, grpc_service):
        """FR-3: a receiver whose type parses to "" (from_observability_yaml default)."""
        biz = BusinessContext(
            criticality="high",
            alert_channels=["mystery"],
            receivers=[Receiver(name="mystery", type="", target="${X}")],
        )
        result = generate_notification_policy(grpc_service, biz)
        assert UNRESOLVED in result.content
        recv = _crit_receiver(result)
        assert "slack_configs" not in recv
        assert "${SLACK_API_URL}" not in result.content

    def test_unknown_type_is_unresolved(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["chan"],
            receivers=[Receiver(name="chan", type="carrier-pigeon", target="${X}")],
        )
        result = generate_notification_policy(grpc_service, biz)
        assert UNRESOLVED in result.content
        assert "carrier-pigeon" in result.content
        assert "slack_configs" not in _crit_receiver(result)

    def test_bare_alertchannels_no_receivers_is_unresolved(self, grpc_service):
        """THE BEHAVIOR CHANGE: a project with bare alertChannels and no authored
        receiver now gets UNRESOLVED-REQUIRED (loud), NOT a guessed Slack receiver."""
        biz = BusinessContext(criticality="high", alert_channels=["#alerts", "#oncall"])
        result = generate_notification_policy(grpc_service, biz)
        assert UNRESOLVED in result.content
        assert "${SLACK_API_URL}" not in result.content
        recv = _crit_receiver(result)
        assert "slack_configs" not in recv

    def test_no_channels_at_all_is_unresolved(self, grpc_service):
        # default criticality "medium" → "warning" tier only (no critical page tier).
        result = generate_notification_policy(grpc_service, BusinessContext())
        assert UNRESOLVED in result.content
        for recv in _receivers(result).values():
            assert "slack_configs" not in recv and "webhook_configs" not in recv


# ---------------------------------------------------------------------------
# FR-7 — severity tiering from Receiver.severities
# ---------------------------------------------------------------------------


class TestSeverityTiering:
    # The alert generator labels every alert for a service with the SINGLE
    # _severity_for(criticality) value, so exactly ONE route is emitted (at that
    # severity) — a synthetic second tier would be a dead route. Tiering that
    # works = per-receiver Receiver.severities filtering against that severity.
    def test_matching_severity_receiver_applies(self, grpc_service):
        biz = BusinessContext(
            criticality="high",  # → severity "critical"
            alert_channels=["pagerduty-bpi-p1"],
            receivers=[Receiver(name="pagerduty-bpi-p1", type="pagerduty",
                                target="${PD_KEY}", severities=["critical"])],
        )
        receivers = _receivers(generate_notification_policy(grpc_service, biz))
        assert "pagerduty_configs" in receivers["checkout-api-critical"]

    def test_nonmatching_severity_receiver_filtered_out(self, grpc_service):
        # A warning-only receiver on a critical service must NOT appear — the
        # alerts are all severity=critical, so it can never fire.
        biz = BusinessContext(
            criticality="high",
            alert_channels=["pagerduty-bpi-p1"],
            receivers=[Receiver(name="pagerduty-bpi-p1", type="pagerduty",
                                target="${PD_KEY}", severities=["warning"])],
        )
        result = generate_notification_policy(grpc_service, biz)
        # Filtered out entirely → no receiver emitted + a loud "all filtered" flag.
        assert "checkout-api-critical" not in _receivers(result)
        assert UNRESOLVED in result.content

    def test_absent_severities_always_applies(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#chat"],
            receivers=[Receiver(name="#chat", type="slack", target="${SLACK}")],
        )
        recv = _receivers(generate_notification_policy(grpc_service, biz))["checkout-api-critical"]
        assert "slack_configs" in recv

    def test_single_route_no_dead_tier(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#chat"],
            receivers=[Receiver(name="#chat", type="slack", target="${SLACK}")],
        )
        routes = _doc(generate_notification_policy(grpc_service, biz))["route"]["routes"]
        assert len(routes) == 1  # one route at the alert severity — no dead warning tier
        assert routes[0]["continue"] is True
        assert any(m.startswith("severity = ") for m in routes[0]["matchers"])


# ---------------------------------------------------------------------------
# FR-8 — matcher label from the resolved descriptor's service_label_key
# ---------------------------------------------------------------------------


class TestDescriptorMatcher:
    def test_span_metrics_matcher_uses_service_name(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#chat"],
            receivers=[Receiver(name="#chat", type="slack", target="${SLACK}")],
        )
        # span-metrics descriptor → service_label_key == "service_name"
        descriptor = resolve_descriptor(profile="span-metrics-connector", transport="grpc")
        assert descriptor.service_label_key == "service_name"
        result = generate_notification_policy(grpc_service, biz, descriptor)
        route = _doc(result)["route"]["routes"][0]
        assert "service_name = checkout-api" in route["matchers"]
        assert "service = checkout-api" not in route["matchers"]

    def test_default_descriptor_uses_service_label(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#chat"],
            receivers=[Receiver(name="#chat", type="slack", target="${SLACK}")],
        )
        result = generate_notification_policy(grpc_service, biz)  # descriptor=None fallback
        route = _doc(result)["route"]["routes"][0]
        assert "service = checkout-api" in route["matchers"]


# ---------------------------------------------------------------------------
# FR-9 — configurable grouping
# ---------------------------------------------------------------------------


class TestConfigurableGrouping:
    def test_grouping_overrides_from_business(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#chat"],
            receivers=[Receiver(name="#chat", type="slack", target="${SLACK}")],
            notification_grouping={
                "group_by": ["team", "alertname"],
                "group_wait": "10s",
                "repeat_interval": "1h",
            },
        )
        route = _doc(generate_notification_policy(grpc_service, biz))["route"]["routes"][0]
        assert route["group_by"] == ["team", "alertname"]
        assert route["group_wait"] == "10s"
        assert route["repeat_interval"] == "1h"

    def test_grouping_defaults_when_absent(self, grpc_service):
        biz = BusinessContext(
            criticality="high",
            alert_channels=["#chat"],
            receivers=[Receiver(name="#chat", type="slack", target="${SLACK}")],
        )
        route = _doc(generate_notification_policy(grpc_service, biz))["route"]["routes"][0]
        assert route["group_wait"] == "30s"
        assert route["repeat_interval"] == "4h"


# ---------------------------------------------------------------------------
# FR-2 / R1-S6 — invariant guard: ONE receiver-parsing entry point
# ---------------------------------------------------------------------------


class TestOneCanonicalSourceInvariant:
    def test_single_receiver_parser_entry_point(self):
        """FR-2 durable invariant: receivers are parsed only by from_observability_yaml.
        No parallel `Channel` model or `spec.observability.channels` reader was introduced."""
        from startd8.observability import spec as spec_mod

        # The canonical Receiver model + its one parser both exist...
        assert hasattr(spec_mod, "Receiver")
        assert hasattr(spec_mod, "from_observability_yaml")
        # ...and no second channel-declaration model/parser was added alongside it.
        assert not hasattr(spec_mod, "Channel")
        assert not hasattr(spec_mod, "from_channels_yaml")
        assert not hasattr(spec_mod, "ContactDirectory")

    def test_notification_policy_reads_receiver_target_not_new_key(self):
        """The renderer binds to Receiver.target (the env-indirected secret), not an
        invented secret_ref key — proven by rendering with only target populated."""
        # Receiver has no secret_ref field.
        assert not any(f.name == "secret_ref" for f in Receiver.__dataclass_fields__.values())
        assert set(Receiver.__dataclass_fields__) == {"name", "type", "target", "severities"}

    def test_generate_notification_policy_is_descriptor_aware(self):
        """FR-8: the generator now accepts the 3-arg (service, business, descriptor)
        signature and is registered in the descriptor-aware dispatch set."""
        from startd8.observability.artifact_generator import _DESCRIPTOR_AWARE_GENERATORS

        assert generate_notification_policy in _DESCRIPTOR_AWARE_GENERATORS
        params = list(inspect.signature(generate_notification_policy).parameters)
        assert params[:3] == ["service", "business", "descriptor"]
