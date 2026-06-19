#!/usr/bin/env python3
"""Tier 0 — S5.5 API-shape probe (BLOCKING gate before the S6 verifier/adapters).

Resolves OQ-5 (backend query-API stability) by recording the ACTUAL Jaeger + Prometheus
query shapes of the pinned OTel Demo (v2.2.0) *before* any adapter code is committed — you
cannot version-gate an adapter you haven't designed (CRP R1-S3). The output
``api-shape-decision.json`` is the contract the §4 acceptance table and the FR-6 adapters are
written against.

Stdlib only (urllib) — mirrors scripts/otel_smoke_test.py; no new deps.

Exit codes (repo convention):
  0  both backends probed; decision record written
  1  reached a backend but an expected shape was missing (records partial + flags it)
  2  infrastructure/connection error (a backend unreachable)

Usage:
  python3 scripts/otel_demo/probe_api_shapes.py \
      --jaeger http://localhost:16686 \
      --prometheus http://localhost:9090 \
      --out docs/design/otel-demo-corpus/api-shape-decision.json

Endpoint defaults are best-effort for a local compose bring-up; the OTel Demo routes UIs through
frontend-proxy (:8080) but the query APIs are commonly reachable on their own ports. Override with
flags if your bring-up differs (record the working values in reference-env.md).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

REQUEST_TIMEOUT = 10

# Metric names the §4 acceptance rows reference (expected v2.2.0); the probe confirms which exist.
EXPECTED_METRIC_HINTS = [
    "rpc_server_duration",          # §2 metrics / §5.3 gRPC
    "http_server_request_duration",  # §2 metrics (HTTP)
    "traces_span_metrics",          # §7.1 span-metrics connector
]
# Span attribute keys the §5 pattern rows look for.
EXPECTED_SPAN_ATTRS = ["rpc.system", "db.system", "messaging.system", "feature_flag.key"]


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read())


def probe_jaeger(base: str) -> dict[str, Any]:
    """Record Jaeger query-API shapes: services list + a sample trace's process/span structure."""
    out: dict[str, Any] = {
        "base": base,
        "reachable": False,
        "services_endpoint": "/api/services",
        "traces_endpoint": "/api/traces?service=<svc>&limit=<n>&lookback=<window>",
        "services": [],
        "language_path_observed": None,
        "span_attr_keys_seen": [],
        "errors": [],
    }
    try:
        data = _get_json(f"{base.rstrip('/')}/api/services")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        out["errors"].append(f"services: {e}")
        return out
    out["reachable"] = True
    services = data.get("data") or []
    out["services"] = services[:50]

    # Sample one service's traces to learn where telemetry.sdk.language + span attrs live.
    if services:
        svc = urllib.parse.quote(services[0])
        try:
            tr = _get_json(f"{base.rstrip('/')}/api/traces?service={svc}&limit=1&lookback=1h")
            batches = tr.get("data") or []
            attr_keys: set[str] = set()
            lang_path: Optional[str] = None
            for trace in batches:
                for p in (trace.get("processes") or {}).values():
                    for tag in p.get("tags") or []:
                        k = tag.get("key", "")
                        attr_keys.add(k)
                        if k == "telemetry.sdk.language":
                            lang_path = "processes[*].tags[key=telemetry.sdk.language].value"
                for span in trace.get("spans") or []:
                    for tag in span.get("tags") or []:
                        attr_keys.add(tag.get("key", ""))
            out["language_path_observed"] = lang_path
            out["span_attr_keys_seen"] = sorted(k for k in attr_keys if k)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            out["errors"].append(f"traces: {e}")
    return out


def probe_prometheus(base: str) -> dict[str, Any]:
    """Record Prometheus query-API shapes + which expected metric names actually exist."""
    out: dict[str, Any] = {
        "base": base,
        "reachable": False,
        "names_endpoint": "/api/v1/label/__name__/values",
        "query_endpoint": "/api/v1/query?query=<promql>",
        "matched_metric_names": {},
        "errors": [],
    }
    try:
        data = _get_json(f"{base.rstrip('/')}/api/v1/label/__name__/values")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        out["errors"].append(f"names: {e}")
        return out
    out["reachable"] = True
    names = data.get("data") or []
    for hint in EXPECTED_METRIC_HINTS:
        out["matched_metric_names"][hint] = sorted(n for n in names if hint in n)[:10]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jaeger", default="http://localhost:16686", help="Jaeger query-API base URL")
    ap.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus base URL")
    ap.add_argument("--out", default="docs/design/otel-demo-corpus/api-shape-decision.json",
                    help="decision-record output path")
    args = ap.parse_args(argv)

    jaeger = probe_jaeger(args.jaeger)
    prom = probe_prometheus(args.prometheus)

    # Verdict: missing expected shapes -> exit 1; an unreachable backend -> exit 2.
    missing: list[str] = []
    if jaeger["reachable"] and not jaeger.get("language_path_observed"):
        missing.append("jaeger: telemetry.sdk.language path not observed (generate traffic, retry)")
    if prom["reachable"] and not any(prom["matched_metric_names"].values()):
        missing.append("prometheus: none of the expected metric-name hints matched")

    if not jaeger["reachable"] or not prom["reachable"]:
        status, code = "unreachable", 2
    elif missing:
        status, code = "partial", 1
    else:
        status, code = "ok", 0

    decision = {
        "schema_version": "1.0",
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "expected_span_attrs": EXPECTED_SPAN_ATTRS,
        "jaeger": jaeger,
        "prometheus": prom,
        "missing": missing,
        "note": (
            "Decision record for the §4 acceptance queries and the FR-6 (S6) adapters. "
            "If status != ok, generate load (loadgenerator) and re-run, or update the §4 table "
            "to match the names actually observed here."
        ),
    }

    out_path = args.out
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(decision, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"[{status}] wrote {out_path}")
    print(f"  jaeger: reachable={jaeger['reachable']} services={len(jaeger['services'])} "
          f"lang_path={'yes' if jaeger.get('language_path_observed') else 'no'}")
    print(f"  prometheus: reachable={prom['reachable']} "
          f"matched={[k for k, v in prom['matched_metric_names'].items() if v]}")
    for m in missing:
        print(f"  MISSING: {m}")
    if code == 2:
        print("  Backends unreachable — is the demo up? (scripts/otel_demo/bring_up.sh)")
    return code


if __name__ == "__main__":
    sys.exit(main())
