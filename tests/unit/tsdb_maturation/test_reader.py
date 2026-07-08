"""M0 reader tests (FR-1) — driven by httpx.MockTransport, no live TSDB required.

Covers the CRP-hardened behaviors: the two-way empty classification (OQ-6 / R1-F6),
distinct 401 auth handling (R1-F11), happy-path vector parsing, family fan-out (R1-S5),
and endpoint URL construction for both the Grafana proxy and direct Mimir.
"""

from __future__ import annotations

import httpx
import pytest

from startd8.tsdb_maturation.reader import (
    AuthError,
    DirectMimirEndpoint,
    EmptyMaterialization,
    GrafanaProxyEndpoint,
    MetricNotFound,
    ReadResult,
    TsdbReader,
    _build_promql,
)


# --------------------------------------------------------------------------- #
# A configurable fake Prometheus HTTP API v1 backed by httpx.MockTransport.     #
# --------------------------------------------------------------------------- #
def make_client(
    *,
    vector=None,
    index_names=None,
    status_code=200,
    query_status="success",
):
    """Build an httpx.Client whose transport fakes /query and /label/__name__/values.

    ``vector`` is the instant-query result list; ``index_names`` is what the
    ``__name__`` label endpoint reports (drives the pruned-vs-absent split).
    """
    calls = {"query": 0, "names": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if status_code in (401, 403):
            return httpx.Response(status_code, text="forbidden")
        if path.endswith("/api/v1/query"):
            calls["query"] += 1
            body = {"status": query_status, "data": {"resultType": "vector", "result": vector or []}}
            if query_status != "success":
                body["error"] = "parse error"
            return httpx.Response(200, json=body)
        if path.endswith("/api/v1/label/__name__/values"):
            calls["names"] += 1
            return httpx.Response(200, json={"status": "success", "data": index_names or []})
        return httpx.Response(404, text=f"unhandled {path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client._spy_calls = calls  # type: ignore[attr-defined]
    return client


def _vec(labels: dict, value: str, ts: float = 1_700_000_000.0):
    return {"metric": {"__name__": "m", **labels}, "value": [ts, value]}


# --------------------------------------------------------------------------- #
# PromQL construction (NR-6 — a bounded last_over_time read).                    #
# --------------------------------------------------------------------------- #
def test_build_promql_bare_metric():
    assert _build_promql("gov_expenditure_amount", "3000d", None) == (
        "last_over_time(gov_expenditure_amount[3000d])"
    )


def test_build_promql_with_matchers_is_sorted():
    q = _build_promql("m", "30d", {"dept": "corrections", "fy": "2025"})
    assert q == 'last_over_time(m{dept="corrections",fy="2025"}[30d])'


# --------------------------------------------------------------------------- #
# Endpoint URL construction.                                                    #
# --------------------------------------------------------------------------- #
def test_grafana_proxy_url_shape():
    ep = GrafanaProxyEndpoint(base_url="http://localhost:3000/", datasource_uid="mimir")
    assert ep.api_url("query") == (
        "http://localhost:3000/api/datasources/proxy/uid/mimir/api/v1/query"
    )
    assert ep.api_url("label/__name__/values").endswith("/api/v1/label/__name__/values")


def test_direct_mimir_url_and_tenant_header():
    ep = DirectMimirEndpoint(base_url="http://mimir:9009", tenant="anonymous")
    assert ep.api_url("query") == "http://mimir:9009/prometheus/api/v1/query"
    assert ep.headers()["X-Scope-OrgID"] == "anonymous"


def test_direct_mimir_vanilla_prometheus_no_prefix():
    ep = DirectMimirEndpoint(base_url="http://prom:9090", prometheus_prefix="")
    assert ep.api_url("query") == "http://prom:9090/api/v1/query"


# --------------------------------------------------------------------------- #
# Happy path.                                                                   #
# --------------------------------------------------------------------------- #
def test_read_returns_parsed_series():
    vector = [
        _vec({"department": "corrections", "fiscal_year": "2025"}, "1000000.5"),
        _vec({"department": "health", "fiscal_year": "2026"}, "2000000.0"),
    ]
    client = make_client(vector=vector)
    reader = TsdbReader(GrafanaProxyEndpoint("http://x", "mimir"), client=client)
    result = reader.read("gov_expenditure_amount", lookback="3000d")

    assert isinstance(result, ReadResult)
    assert result.metric == "gov_expenditure_amount"
    assert result.lookback == "3000d"
    assert not result.is_empty
    assert len(result) == 2
    first = result.series[0]
    assert first.labels == {"department": "corrections", "fiscal_year": "2025"}
    assert first.value == pytest.approx(1000000.5)
    assert "__name__" not in first.labels
    # Non-empty read is a SINGLE request — the index lookup only fires on the empty path.
    assert client._spy_calls == {"query": 1, "names": 0}


def test_read_parses_real_recon_specimen_shape():
    """The preserved recon specimen (startd8_cost) is the fixture shape M1 will consume."""
    vector = [
        _vec({"job": "startd8-sdk", "provider": "anthropic", "model": "anthropic:claude-opus-4-8"}, "0.0"),
        _vec({"job": "startd8-sdk", "provider": "anthropic", "model": "anthropic:claude-sonnet-4-6"}, "0.175077"),
    ]
    client = make_client(vector=vector)
    reader = TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=client)
    result = reader.read("startd8_cost_USD_total")
    assert len(result) == 2
    assert sorted(s.value for s in result.series) == pytest.approx([0.0, 0.175077])


# --------------------------------------------------------------------------- #
# Empty-result classification (OQ-6 / R1-F6) — the load-bearing M0 split.        #
# --------------------------------------------------------------------------- #
def test_empty_but_in_index_refuses_as_empty_materialization():
    # Metric present in the __name__ index but no current samples → pruned → OQ-6 refuse.
    client = make_client(vector=[], index_names=["gov_expenditure_amount", "other"])
    reader = TsdbReader(GrafanaProxyEndpoint("http://x", "mimir"), client=client)
    with pytest.raises(EmptyMaterialization) as exc:
        reader.read("gov_expenditure_amount")
    assert "retention" in str(exc.value).lower() or "pruned" in str(exc.value).lower()
    # The index was consulted exactly once to make the determination.
    assert client._spy_calls == {"query": 1, "names": 1}


def test_empty_and_absent_from_index_is_metric_not_found():
    # Metric NOT in the index → a config/typo error, a DIFFERENT exception from the pruned case.
    client = make_client(vector=[], index_names=["some_other_metric"])
    reader = TsdbReader(GrafanaProxyEndpoint("http://x", "mimir"), client=client)
    with pytest.raises(MetricNotFound):
        reader.read("govv_expenditure_amont")  # deliberate typo


def test_pruned_and_absent_raise_distinct_types():
    """R1-F6: the two empty causes must never collapse to one signal."""
    assert not issubclass(EmptyMaterialization, MetricNotFound)
    assert not issubclass(MetricNotFound, EmptyMaterialization)


# --------------------------------------------------------------------------- #
# Auth (R1-F11) — 401/403 is distinct and never the empty path.                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("code", [401, 403])
def test_auth_error_is_distinct_and_short_circuits(code):
    client = make_client(status_code=code, index_names=["m"])
    reader = TsdbReader(GrafanaProxyEndpoint("http://x", "mimir"), client=client)
    with pytest.raises(AuthError):
        reader.read("m")
    # Crucially: an auth failure never reaches the index lookup / empty-materialization path.
    assert client._spy_calls["names"] == 0


def test_auth_error_not_confused_with_empty_materialization():
    assert not issubclass(AuthError, EmptyMaterialization)
    assert not issubclass(AuthError, MetricNotFound)


# --------------------------------------------------------------------------- #
# Token resolution comes from env, never a flag (R1-F11).                        #
# --------------------------------------------------------------------------- #
def test_token_resolved_from_env(monkeypatch):
    monkeypatch.setenv("GRAFANA_API_TOKEN", "secret-tok")
    ep = GrafanaProxyEndpoint("http://x", "mimir")
    assert ep.headers() == {"Authorization": "Bearer secret-tok"}


def test_no_token_means_no_auth_header(monkeypatch):
    monkeypatch.delenv("GRAFANA_API_TOKEN", raising=False)
    monkeypatch.delenv("GRAFANA_SA_TOKEN", raising=False)
    ep = GrafanaProxyEndpoint("http://x", "mimir")
    assert ep.headers() == {}


# --------------------------------------------------------------------------- #
# Family fan-out (FR-12 coupling, R1-S5) — one query per member.                 #
# --------------------------------------------------------------------------- #
def test_read_family_issues_one_query_per_member():
    vector = [_vec({"department": "corrections"}, "5")]
    client = make_client(vector=vector)
    reader = TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=client)
    out = reader.read_family(["gov_expenditure_amount", "gov_expenditure_count"])
    assert set(out) == {"gov_expenditure_amount", "gov_expenditure_count"}
    assert all(isinstance(r, ReadResult) for r in out.values())
    assert client._spy_calls["query"] == 2  # one per member


def test_read_family_empty_member_list_raises():
    reader = TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=make_client())
    with pytest.raises(ValueError):
        reader.read_family([])


# --------------------------------------------------------------------------- #
# Query-level error surfaces distinctly (bad PromQL / range).                    #
# --------------------------------------------------------------------------- #
def test_non_success_status_raises_query_error():
    from startd8.tsdb_maturation.reader import TsdbQueryError

    client = make_client(query_status="error")
    reader = TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=client)
    with pytest.raises(TsdbQueryError):
        reader.read("m")


# --------------------------------------------------------------------------- #
# Transport failures are wrapped as TsdbReaderError (the CLI's catch contract). #
# --------------------------------------------------------------------------- #
def test_connection_error_wrapped_as_reader_error():
    from startd8.tsdb_maturation.reader import TsdbReaderError

    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reader = TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=client)
    with pytest.raises(TsdbReaderError, match="cannot reach"):
        reader.read("m")


def test_http_500_wrapped_as_reader_error():
    from startd8.tsdb_maturation.reader import TsdbReaderError

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    reader = TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=client)
    with pytest.raises(TsdbReaderError, match="HTTP 500"):
        reader.read("m")


def test_non_json_body_wrapped_as_reader_error():
    from startd8.tsdb_maturation.reader import TsdbReaderError

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>proxy</html>")))
    reader = TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=client)
    with pytest.raises(TsdbReaderError, match="non-JSON"):
        reader.read("m")


# --------------------------------------------------------------------------- #
# Context-manager lifecycle closes an owned client.                             #
# --------------------------------------------------------------------------- #
def test_context_manager_uses_injected_client():
    client = make_client(vector=[_vec({"a": "b"}, "1")])
    with TsdbReader(DirectMimirEndpoint("http://mimir:9009"), client=client) as reader:
        assert len(reader.read("m")) == 1
