#!/usr/bin/env bash
# Upsert the StartD8 stakeholders datasource via the Grafana HTTP API — NO restart, survives token
# rotation (re-run with a fresh token). Operator-run: it mutates a (possibly shared) Grafana instance.
#
# The datasource proxies /api/datasources/proxy/uid/<uid>/stakeholders/* → <ENDPOINT_URL>/stakeholders/*
# and injects `Authorization: Bearer <token>` via Grafana's core custom-header mechanism, so the token
# is never in the dashboard JSON or the browser (FR-2 / S-3). The panel adds its own X-Nonce.
#
# Usage:
#   GRAFANA_URL=http://localhost:3000 \
#   STAKEHOLDER_TOKEN=<token printed by `startd8 kickoff stakeholders serve`> \
#   ENDPOINT_URL=http://host.docker.internal:8710 \
#   ./provision-datasource.sh
#
# Grafana auth is picked up from the env automatically, in order: GRAFANA_TOKEN, GRAFANA_SA_TOKEN,
# GRAFANA_API_TOKEN, then GRAFANA_USER + GRAFANA_PASS.
#
# Requires: curl, jq. Neither token is ever echoed.
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
ENDPOINT_URL="${ENDPOINT_URL:-http://host.docker.internal:8710}"
DS_UID="${DS_UID:-startd8-stakeholders}"
DS_NAME="${DS_NAME:-StartD8 Stakeholders Endpoint}"
DS_TYPE="${DS_TYPE:-yesoreyeram-infinity-datasource}"

: "${STAKEHOLDER_TOKEN:?set STAKEHOLDER_TOKEN (from \`startd8 kickoff stakeholders serve\`)}"

# Auth to Grafana: a bearer token (service account / API) from the env, or basic admin creds.
graf_token="${GRAFANA_TOKEN:-${GRAFANA_SA_TOKEN:-${GRAFANA_API_TOKEN:-}}}"
auth=()
if [[ -n "$graf_token" ]]; then
  auth=(-H "Authorization: Bearer ${graf_token}")
elif [[ -n "${GRAFANA_USER:-}" && -n "${GRAFANA_PASS:-}" ]]; then
  auth=(-u "${GRAFANA_USER}:${GRAFANA_PASS}")
else
  echo "error: set GRAFANA_TOKEN / GRAFANA_SA_TOKEN / GRAFANA_API_TOKEN, or GRAFANA_USER + GRAFANA_PASS" >&2
  exit 2
fi

payload="$(jq -n \
  --arg uid "$DS_UID" --arg name "$DS_NAME" --arg type "$DS_TYPE" \
  --arg url "$ENDPOINT_URL" --arg bearer "Bearer ${STAKEHOLDER_TOKEN}" '{
    uid: $uid, name: $name, type: $type, access: "proxy", url: $url, isDefault: false,
    jsonData: { httpHeaderName1: "Authorization" },
    secureJsonData: { httpHeaderValue1: $bearer }
  }')"

# Update by UID if it exists, else create. (PUT /api/datasources/uid/:uid is supported on Grafana 9+.)
if curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/datasources/uid/${DS_UID}" >/dev/null 2>&1; then
  echo "updating datasource uid=${DS_UID} …"
  curl -fsS -X PUT "${auth[@]}" -H "Content-Type: application/json" \
    "${GRAFANA_URL}/api/datasources/uid/${DS_UID}" -d "$payload" | jq '{uid: .datasource.uid, name: .datasource.name, message}'
else
  echo "creating datasource uid=${DS_UID} …"
  curl -fsS -X POST "${auth[@]}" -H "Content-Type: application/json" \
    "${GRAFANA_URL}/api/datasources" -d "$payload" | jq '{uid: .datasource.uid, name: .datasource.name, message}'
fi

echo "done — set the panel option 'Run datasource UID' to: ${DS_UID}"
