#!/usr/bin/env python3
"""Rung 1->2: query_range over a wide window to LOCATE + MATERIALIZE real samples,
then flatten one metric to a specimen file. Read-only against Mimir."""
import json
import os
import time
import urllib.request
import urllib.parse

GRAFANA = "http://localhost:3000"
TOKEN = os.environ.get("GRAFANA_API_TOKEN") or os.environ.get("GRAFANA_SA_TOKEN") or ""
UID = "mimir"

CANDIDATES = [
    "gov_vendor_payment_amount",
    "gov_department_expenditure",
    "gov_program_amount",
    "gov_payment_amount",
    "gov_expenditure_amount",
    "gov_jail_population",
    "startd8_cost_USD_total",
    "startd8_events_total",
]

NOW = int(time.time())
WINDOW = 365 * 24 * 3600  # 1 year back
START = NOW - WINDOW


def proxy(ds_path, params=None):
    url = f"{GRAFANA}/api/datasources/proxy/uid/{UID}/{ds_path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def range_query(metric, step):
    res = proxy("/api/v1/query_range", {
        "query": metric, "start": START, "end": NOW, "step": step,
    })
    return res.get("data", {}).get("result", [])


best = None
for metric in CANDIDATES:
    try:
        series = range_query(metric, step=6 * 3600)  # 6h step to locate
    except Exception as e:  # noqa: BLE001
        print(f"{metric}: ERROR {e}")
        continue
    n_series = len(series)
    n_samples = sum(len(s.get("values", [])) for s in series)
    # find the time span of samples
    ts = [float(v[0]) for s in series for v in s.get("values", [])]
    span = ""
    if ts:
        lo, hi = min(ts), max(ts)
        span = f"  data span: {time.strftime('%Y-%m-%d', time.gmtime(lo))} .. {time.strftime('%Y-%m-%d', time.gmtime(hi))}"
    label_keys = set()
    for s in series:
        label_keys.update(k for k in s["metric"] if k != "__name__")
    print(f"{metric}: {n_series} series, {n_samples} samples, labels={sorted(label_keys)}{span}")
    if n_series and (best is None or n_series > best[1]):
        best = (metric, n_series, series)

if not best:
    print("\nNo samples found in the last year for any candidate.")
    raise SystemExit(0)

metric, n_series, series = best
print(f"\n=== SPECIMEN: {metric} ({n_series} series) ===")

# Flatten to specimen records: one row per (label-set + latest sample)
records = []
for s in series:
    labels = {k: v for k, v in s["metric"].items() if k != "__name__"}
    vals = s.get("values", [])
    if not vals:
        continue
    last_ts, last_val = vals[-1]
    rec = dict(labels)
    rec["value"] = float(last_val)
    rec["observed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(last_ts)))
    records.append(rec)

specimen_path = f"/tmp/specimen-{metric}.json"
with open(specimen_path, "w") as f:
    json.dump({"metric": metric, "n_records": len(records), "records": records}, f, indent=2)
print(f"wrote {len(records)} records -> {specimen_path}")
print("first 3 records:")
for r in records[:3]:
    print(f"  {json.dumps(r)}")
