#!/usr/bin/env bash
# PROTOTYPE — assemble the docker build contexts for the 2-service fleet by REUSING the SDK's
# behavioral provisioning sources (no hand-copied stubs). Mirrors provision.setup_go_stubs (vendored
# Go stubs + synthesized localmod go.mod) and the Python demo_pb2 co-location convention, and writes
# the harness-owned ground-truth products.json from catalog_suite.products_json().
#
# Idempotent: safe to re-run. Generated artifacts (_stubs/, demo_pb2*.py, products.json) are gitignored.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../.." && pwd)"
BEHAVIORAL="$REPO_ROOT/src/startd8/benchmark_matrix/behavioral"
GO_STUBS="$BEHAVIORAL/go_stubs/hipstershop"
STUB_MODULE="github.com/GoogleCloudPlatform/microservices-demo/hipstershop"

echo "[prepare] repo root: $REPO_ROOT"

# --- productcatalogservice (Go): vendor stubs as a local module (mirror setup_go_stubs) -----------
PC="$HERE/productcatalogservice"
mkdir -p "$PC/_stubs"
cp "$GO_STUBS/demo.pb.go" "$GO_STUBS/demo_grpc.pb.go" "$PC/_stubs/"
# Synthesize the localmod go.mod exactly as provision.setup_go_stubs does (module = the stub import
# path so the service's `replace ... => ./_stubs` resolves with no subpath gymnastics).
cat > "$PC/_stubs/go.mod" <<EOF
module $STUB_MODULE

go 1.21

require (
	google.golang.org/grpc v1.81.1
	google.golang.org/protobuf v1.36.11
)
EOF
echo "[prepare] productcatalogservice: vendored Go stubs -> _stubs/ (+ localmod go.mod)"

# --- recommendationservice (Python): co-locate demo_pb2 stubs (the OB Python convention) ----------
REC="$HERE/recommendationservice"
cp "$BEHAVIORAL/demo_pb2.py" "$BEHAVIORAL/demo_pb2_grpc.py" "$REC/"
echo "[prepare] recommendationservice: co-located demo_pb2 / demo_pb2_grpc"

# --- harness-owned ground-truth products.json (from catalog_suite.products_json()) ----------------
# NOTE: recommendation's oracle universe is recommendation_ground_truth() (5 products). We serve that
# 5-product catalog so the recommendation suite's catalog_ids match what productcatalog returns.
PYTHONPATH="$REPO_ROOT/src" python3 - "$PC/products.json" <<'PY'
import json, sys
from startd8.benchmark_matrix.behavioral.recommendation_stubs import recommendation_ground_truth
gt = recommendation_ground_truth()
# Emit upstream-OB products.json shape from the recommendation oracle's fixed catalog.
products = []
for p in gt.catalog.values():
    products.append({
        "id": p.id,
        "name": p.name,
        "description": p.name,
        "picture": f"/static/img/products/{p.id}.jpg",
        "priceUsd": {"currencyCode": "USD", "units": p.price_units, "nanos": p.price_nanos},
        "categories": ["prototype"],
    })
with open(sys.argv[1], "w") as fh:
    json.dump({"products": products}, fh, indent=2)
print(f"[prepare] productcatalogservice: wrote {len(products)} ground-truth products -> products.json")
PY

echo "[prepare] build contexts ready."
