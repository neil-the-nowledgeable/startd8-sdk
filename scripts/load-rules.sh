#!/usr/bin/env bash
# =============================================================================
# Load startd8-sdk observability rules into Mimir and Loki.
#
# This is Path 2 — hot-loads rules without pod restarts.
# Path 1 (ConfigMap) lives in wayfinder/k8s/observability/configs.yaml.
# Path 3 (standalone files) lives in startd8-sdk/rules/.
#
# Loading strategies (determined by backend capabilities):
#   Mimir: ruler API (one group per POST) — supports SetRuleGroup
#   Loki:  kubectl cp to pod filesystem  — local storage is read-only via API
#
# Usage:
#   ./scripts/load-rules.sh                    # defaults: localhost
#   ./scripts/load-rules.sh --mimir-url http://mimir:9009 --loki-url http://loki:3100
#   ./scripts/load-rules.sh --dry-run          # show what would be pushed
#   ./scripts/load-rules.sh --delete           # remove rules from rulers
#   ./scripts/load-rules.sh --verify           # verify after loading
#
# Prerequisites:
#   - curl, python3, PyYAML
#   - Mimir running with ruler API enabled (enable_api: true)
#   - kubectl access to the observability namespace (for Loki)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
MIMIR_URL="${MIMIR_URL:-http://localhost:9009}"
LOKI_URL="${LOKI_URL:-http://localhost:3100}"
DRY_RUN=false
DELETE=false
VERIFY=false
MIMIR_NAMESPACE="startd8"   # Mimir ruler tenant (custom namespace)
LOKI_NAMESPACE="fake"       # Loki ruler tenant (default single-tenant name)
LOKI_K8S_NAMESPACE="observability"
LOKI_LABEL="app=loki"
LOKI_CONTAINER="loki"
LOKI_RULES_DIR="/loki/rules/${LOKI_NAMESPACE}"

# Rule file paths (standalone files — Path 3)
MIMIR_RECORDING_RULES="$REPO_ROOT/rules/mimir/startd8-recording-rules.yaml"
MIMIR_ALERT_RULES="$REPO_ROOT/rules/mimir/startd8-alerts.yaml"
LOKI_RULES="$REPO_ROOT/rules/loki/startd8-loki-rules.yaml"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --mimir-url URL   Mimir base URL (default: \$MIMIR_URL or http://localhost:9009)"
    echo "  --loki-url URL    Loki base URL (default: \$LOKI_URL or http://localhost:3100)"
    echo "  --dry-run         Show what would be pushed without actually pushing"
    echo "  --delete          Remove startd8 rules from rulers"
    echo "  --verify          Verify rules are loaded after pushing"
    echo "  -h, --help        Show this help"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mimir-url) MIMIR_URL="$2"; shift 2 ;;
        --loki-url) LOKI_URL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --delete) DELETE=true; shift ;;
        --verify) VERIFY=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# ── Helpers ──

log() { echo "[load-rules] $*"; }

check_file() {
    if [[ ! -f "$1" ]]; then
        echo "ERROR: Rule file not found: $1" >&2
        exit 1
    fi
}

# Resolve the current Loki pod name. Returns empty string if not found.
get_loki_pod() {
    kubectl get pods -n "$LOKI_K8S_NAMESPACE" -l "$LOKI_LABEL" \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
}

# ── Mimir: ruler API (one group per POST) ──

# Post each rule group from a file individually to the Mimir ruler API.
# Args: $1=file $2=label
push_mimir_groups() {
    local file="$1"
    local label="$2"

    check_file "$file"

    local group_count=0
    local ok_count=0
    local fail_count=0

    # Split groups and POST each one
    while IFS= read -r -d '' group_yaml; do
        local group_name
        group_name=$(echo "$group_yaml" | python3 -c "import yaml,sys; d=yaml.safe_load(sys.stdin); print(d.get('name','?'))" 2>/dev/null || echo "?")
        local rule_count
        rule_count=$(echo "$group_yaml" | python3 -c "import yaml,sys; d=yaml.safe_load(sys.stdin); print(len(d.get('rules',[])))" 2>/dev/null || echo "?")

        group_count=$((group_count + 1))
        local url="${MIMIR_URL}/prometheus/config/v1/rules/${MIMIR_NAMESPACE}"

        if $DRY_RUN; then
            log "  [dry-run] Would POST group '$group_name' ($rule_count rules) to $url"
            ok_count=$((ok_count + 1))
            continue
        fi

        local response
        local http_code
        response=$(curl -s -w "\n%{http_code}" \
            -X POST "$url" \
            -H "Content-Type: application/yaml" \
            -d "$group_yaml")

        http_code=$(echo "$response" | tail -1)
        local body
        body=$(echo "$response" | sed '$d')

        if [[ "$http_code" == "202" || "$http_code" == "200" ]]; then
            log "  OK ($http_code) — $group_name ($rule_count rules)"
            ok_count=$((ok_count + 1))
        else
            log "  FAIL ($http_code) — $group_name: $body"
            fail_count=$((fail_count + 1))
        fi
    done < <(
        python3 -c "
import yaml, sys
with open('$file') as f:
    data = yaml.safe_load(f)
for group in data.get('groups', []):
    sys.stdout.write(yaml.dump(group, default_flow_style=False))
    sys.stdout.write('\0')
    sys.stdout.flush()
"
    )

    log "  $label: $ok_count/$group_count groups loaded"
    if [[ $fail_count -gt 0 ]]; then
        return 1
    fi
}

# ── Loki: ConfigMap-based loading ──
# Loki's local ruler storage is read-only via API. Rules are loaded from the
# filesystem at /loki/rules/<tenant>/ which is backed by the loki-rules ConfigMap.
# The ConfigMap is maintained in wayfinder/k8s/observability/configs.yaml (Path 1).
#
# This function verifies Loki has the rules loaded (via ConfigMap) rather than
# trying to push them. If rules are missing, it advises updating the ConfigMap.

push_loki_rules() {
    local file="$1"
    local label="$2"

    check_file "$file"

    local filename
    filename=$(basename "$file")

    # Count groups/rules for logging
    local group_count rule_count
    group_count=$(python3 -c "
import yaml, sys
with open('$file') as f:
    data = yaml.safe_load(f)
print(len(data.get('groups', [])))
" 2>/dev/null || echo "?")
    rule_count=$(python3 -c "
import yaml, sys
with open('$file') as f:
    data = yaml.safe_load(f)
print(sum(len(g.get('rules', [])) for g in data.get('groups', [])))
" 2>/dev/null || echo "?")

    if $DRY_RUN; then
        log "  [dry-run] Would verify $filename ($group_count groups, $rule_count rules) in Loki"
        return 0
    fi

    # Check if Loki already has these rules via ConfigMap
    local tmpfile="/tmp/_loki_rules_check_$$.yaml"
    curl -s "${LOKI_URL}/loki/api/v1/rules" > "$tmpfile" 2>/dev/null

    local loaded_groups
    loaded_groups=$(python3 -c "
import yaml, sys
try:
    with open('$tmpfile') as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict):
        for k in data:
            if 'startd8' in k:
                groups = data[k] if isinstance(data[k], list) else []
                print(len(groups))
                sys.exit(0)
    print(0)
except Exception:
    print(0)
" 2>/dev/null || echo "0")
    rm -f "$tmpfile"

    if [[ "$loaded_groups" -gt 0 ]]; then
        log "  OK — $filename ($loaded_groups groups, $rule_count rules) loaded via ConfigMap"
        log "  $label: $loaded_groups/$group_count groups loaded"
    else
        log "  WARN — $filename not found in Loki ruler"
        log "  Loki uses ConfigMap-based loading. Add rules to:"
        log "    wayfinder/k8s/observability/configs.yaml (loki-rules ConfigMap)"
        log "  Then: kubectl apply -f k8s/observability/configs.yaml"
        return 1
    fi
}

# ── Delete ──

delete_rules() {
    if $DRY_RUN; then
        log "[dry-run] Would delete all startd8 rule groups from Mimir and Loki"
        return
    fi

    log "Deleting startd8 rules from Mimir..."
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X DELETE "${MIMIR_URL}/prometheus/config/v1/rules/${MIMIR_NAMESPACE}")
    log "  Mimir: $http_code"

    log "Deleting startd8 rules from Loki..."
    log "  Loki uses ConfigMap-based loading. To remove startd8 rules:"
    log "    1. Remove startd8-rules.yaml key from loki-rules ConfigMap"
    log "    2. kubectl apply -f wayfinder/k8s/observability/configs.yaml"
}

# ── Verify ──

verify_rules() {
    log ""
    log "Verifying loaded rules..."

    log "Mimir rule groups:"
    curl -s "${MIMIR_URL}/prometheus/config/v1/rules" 2>/dev/null | \
        python3 -c "
import sys, yaml, json

raw = sys.stdin.read().strip()
if not raw or raw == '{}':
    print('  (no rules loaded)')
    sys.exit(0)

try:
    data = yaml.safe_load(raw)
except:
    data = json.loads(raw)

if isinstance(data, dict):
    for ns, content in data.items():
        if isinstance(content, str):
            parsed = yaml.safe_load(content)
        elif isinstance(content, list):
            parsed = {'groups': content}
        else:
            parsed = content
        for g in parsed.get('groups', []) if isinstance(parsed, dict) else []:
            name = g.get('name', '?')
            rules = g.get('rules', [])
            print(f'  {ns}/{name}: {len(rules)} rules')
" 2>/dev/null || log "  (could not query Mimir ruler)"

    log "Loki rule groups:"
    curl -s "${LOKI_URL}/loki/api/v1/rules" 2>/dev/null > /tmp/_loki_rules_verify.yaml
    python3 -c "
import yaml, sys, json

with open('/tmp/_loki_rules_verify.yaml') as f:
    raw = f.read().strip()
if not raw:
    print('  (no rules loaded)')
    sys.exit(0)

# Loki returns YAML keyed by filename when using local storage,
# or JSON with status/data when using configdb storage.
try:
    data = json.loads(raw)
    # JSON response (configdb storage)
    if data.get('status') == 'success':
        groups = data.get('data', {}).get('groups', [])
        if not groups:
            print('  (no rules loaded)')
        else:
            for g in groups:
                print(f'  {g.get(\"name\", \"?\")}: {len(g.get(\"rules\", []))} rules')
        sys.exit(0)
except (json.JSONDecodeError, ValueError):
    pass

# YAML response (local storage) — {filename: [groups]}
try:
    data = yaml.safe_load(raw)
    if isinstance(data, dict):
        for filename, groups in data.items():
            if isinstance(groups, list):
                for g in groups:
                    name = g.get('name', '?')
                    rules = g.get('rules', [])
                    print(f'  {filename}/{name}: {len(rules)} rules')
    elif isinstance(data, str) and 'error' in data.lower():
        print(f'  (error: {data[:120]})')
    else:
        print('  (unexpected format)')
except Exception as e:
    print(f'  (parse error: {e})')
" 2>/dev/null || log "  (could not query Loki ruler)"
    rm -f /tmp/_loki_rules_verify.yaml
}

# ── Main ──

if $DELETE; then
    delete_rules
    exit 0
fi

log "Loading startd8-sdk rules"
log "  Mimir: $MIMIR_URL (ruler API)"
log "  Loki:  kubectl cp to pod (local storage)"
log ""

ERRORS=0

# Push Mimir recording rules (one group per POST via ruler API)
log "Mimir recording rules:"
push_mimir_groups "$MIMIR_RECORDING_RULES" "Recording" || ERRORS=$((ERRORS + 1))

# Push Mimir alert rules (one group per POST via ruler API)
log "Mimir alert rules:"
push_mimir_groups "$MIMIR_ALERT_RULES" "Alerts" || ERRORS=$((ERRORS + 1))

# Copy Loki rules to pod filesystem (local storage doesn't support ruler API writes)
log "Loki recording rules:"
push_loki_rules "$LOKI_RULES" "Loki" || ERRORS=$((ERRORS + 1))

log ""
if [[ $ERRORS -eq 0 ]]; then
    log "Done. All rules loaded."
    log "  Mimir: evaluation starts on next ruler interval (default: 1m)"
    log "  Loki:  evaluation starts on next ruler interval (default: 1m)"
else
    log "Done with $ERRORS error(s). Check output above."
fi

if $VERIFY; then
    verify_rules
fi

# Also apply K8s manifests if kubectl is available
if command -v kubectl &>/dev/null && ! $DRY_RUN; then
    log ""
    log "Applying K8s manifests..."
    if kubectl apply -f "$REPO_ROOT/k8s/startd8-service-monitor.yaml" 2>/dev/null; then
        log "  OK — ServiceMonitor applied"
    else
        log "  SKIP — ServiceMonitor (cluster not reachable or CRD not installed)"
    fi
    if kubectl apply -f "$REPO_ROOT/k8s/startd8-notification-policy.yaml" 2>/dev/null; then
        log "  OK — AlertmanagerConfig applied"
    else
        log "  SKIP — AlertmanagerConfig (cluster not reachable or CRD not installed)"
    fi
fi

exit $ERRORS
