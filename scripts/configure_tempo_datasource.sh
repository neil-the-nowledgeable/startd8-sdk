#!/usr/bin/env bash
# Configure Tempo datasource in Grafana (idempotent).
# Extends the existing Loki stack (docker-compose.loki-stack.yml) with trace visibility.
# Prerequisites: Full LGTM stack running in kind cluster.
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_AUTH="${GRAFANA_AUTH:-admin:adminadminadmin}"

# Check if Tempo datasource already exists
if curl -sf -u "$GRAFANA_AUTH" "$GRAFANA_URL/api/datasources/name/Tempo" >/dev/null 2>&1; then
    echo "Tempo datasource already configured"
    exit 0
fi

curl -sf -X POST -u "$GRAFANA_AUTH" "$GRAFANA_URL/api/datasources" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Tempo",
    "type": "tempo",
    "url": "http://tempo:3200",
    "access": "proxy",
    "jsonData": {
      "nodeGraph": { "enabled": true }
    }
  }'
echo ""
echo "Tempo datasource created"
