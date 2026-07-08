#!/usr/bin/env python3
"""Rung 2 recon: inspect label structure + cardinality of candidate metrics."""
import json
import os
import urllib.request
import urllib.parse

GRAFANA = "http://localhost:3000"
TOKEN = os.environ.get("GRAFANA_API_TOKEN") or os.environ.get("GRAFANA_SA_TOKEN") or ""
UID = "mimir"

CANDIDATES = [
    "gov_vendor_payment_amount",
    "gov_department_expenditure",
    "gov_program_amount",
    "gov_autism_program_spending_amount",
    "gov_jail_population",
    "startd8_cost_USD_total",
]


def proxy(ds_path, params=None):
    url = f"{GRAFANA}/api/datasources/proxy/uid/{UID}/{ds_path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


for metric in CANDIDATES:
    print(f"\n=== {metric} ===")
    try:
        res = proxy("/api/v1/query", {"query": metric})
        series = res.get("data", {}).get("result", [])
        print(f"  series count (instant): {len(series)}")
        if not series:
            print("  (no current series — may be stale/retention-pruned)")
            continue
        # union of label keys across series
        label_keys = set()
        for s in series:
            label_keys.update(k for k in s["metric"].keys() if k != "__name__")
        print(f"  label keys ({len(label_keys)}): {sorted(label_keys)}")
        # cardinality per label key
        for k in sorted(label_keys):
            vals = sorted({s['metric'].get(k, '') for s in series})
            shown = vals[:6]
            more = f" …(+{len(vals)-6})" if len(vals) > 6 else ""
            print(f"    {k}: {len(vals)} distinct -> {shown}{more}")
        # sample 2 full series
        print("  sample series:")
        for s in series[:2]:
            labels = {k: v for k, v in s["metric"].items() if k != "__name__"}
            print(f"    labels={json.dumps(labels)}  value={s['value'][1]}")
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {e}")
