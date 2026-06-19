#!/usr/bin/env bash
# Publish a producer OpenAPI contract for cross-repo consumer pinning (Role 3 M5).
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <producer-project-root> <producer-id>" >&2
  echo "Example: $0 /tmp/catalog-producer catalog" >&2
  exit 2
fi

ROOT="$1"
ID="$2"
OUT_DIR="${ROOT}/openapi"
OUT_FILE="${OUT_DIR}/${ID}.json"

if [[ ! -f "${ROOT}/prisma/schema.prisma" ]]; then
  echo "Missing ${ROOT}/prisma/schema.prisma" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"
PYTHONPATH="${PYTHONPATH:-}:$(cd "$(dirname "$0")/.." && pwd)/src" \
  startd8 generate backend \
  --schema "${ROOT}/prisma/schema.prisma" \
  --out "${ROOT}" \
  --export-openapi "${OUT_FILE}"

PYTHONPATH="${PYTHONPATH:-}:$(cd "$(dirname "$0")/.." && pwd)/src" \
  python3 - <<PY
import json
import sys
from pathlib import Path
from startd8.backend_codegen.context_manifest import contract_sha256

path = Path("${OUT_FILE}")
spec = json.loads(path.read_text(encoding="utf-8"))
print(f"Published: {path}")
print(f"contract-sha256: {contract_sha256(spec)}")
PY
