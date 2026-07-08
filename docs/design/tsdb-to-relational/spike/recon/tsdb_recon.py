#!/usr/bin/env python3
"""Read-only recon spike: inventory TSDB series reachable via the Grafana datasource proxy.

Rung 1 of the TSDB->relational maturation ladder. Writes nothing but /tmp artifacts.
"""
import json
import os
import sys
import urllib.request
import urllib.parse

GRAFANA = "http://localhost:3000"
TOKEN = os.environ.get("GRAFANA_API_TOKEN") or os.environ.get("GRAFANA_SA_TOKEN") or ""


def _get(path, params=None):
    url = f"{GRAFANA}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def list_datasources():
    ds = _get("/api/datasources")
    rows = []
    for x in ds:
        rows.append((x.get("id"), x.get("uid"), x.get("type"), x.get("name"), x.get("url")))
    return rows


def proxy(uid, ds_path, params=None):
    """Query a Prometheus-API datasource through the Grafana proxy by uid."""
    return _get(f"/api/datasources/proxy/uid/{uid}/{ds_path.lstrip('/')}", params)


def main():
    print("=== DATASOURCES ===")
    prom_uids = []
    for (did, uid, typ, name, url) in list_datasources():
        marker = ""
        if typ in ("prometheus", "loki", "tempo"):
            marker = "  <-- queryable"
        if typ == "prometheus":
            prom_uids.append((uid, name))
        print(f"  id={did}  uid={uid}  type={typ}  name={name}  url={url}{marker}")

    if not prom_uids:
        print("\nNo prometheus datasource found; cannot inventory series.")
        return

    for (uid, name) in prom_uids:
        print(f"\n=== METRIC NAMES on '{name}' (uid={uid}) ===")
        try:
            res = proxy(uid, "/api/v1/label/__name__/values")
            names = res.get("data", [])
            print(f"  total metric names: {len(names)}")
            # focus on our namespaces
            interesting = [n for n in names if any(
                n.startswith(p) for p in ("startd8", "contextcore", "security_prime", "task", "lesson", "benchmark", "gov_")
            )]
            print(f"  startd8/contextcore/etc namespace hits: {len(interesting)}")
            for n in sorted(interesting):
                print(f"    {n}")
            if not interesting:
                print("  (none in our namespaces) -- sample of what IS present:")
                for n in sorted(names)[:40]:
                    print(f"    {n}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR listing metric names: {e}")


if __name__ == "__main__":
    main()
