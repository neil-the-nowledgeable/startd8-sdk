## Startd8 MCP Observability (Alloy + Mimir + Loki + Tempo)

This repo supports MCP-safe observability for a **stdio-based** MCP server (never write logs to stdout). This guide covers:

- **Metrics**: Startd8 MCP → Prometheus scrape → Alloy → **Mimir**
- **Logs**: Startd8 MCP JSONL events → Alloy → **Loki**
- **Traces**: (optional) OTLP → Alloy → **Tempo**

---

## Prereqs
- Docker Desktop running (if you choose the Docker-based paths below).
- A running LGTM backend stack (Grafana + Mimir + Loki + Tempo). Two common options:
  - **Option A (recommended)**: Use the stack in `~/Documents/tools/Grafana/` (Grafana OSS lab stack we set up earlier).
  - **Option B**: Use your own compose/K8s deployment of Mimir/Loki/Tempo.

This doc assumes **MCP server runs on macOS as a local process**, and **Alloy runs in Docker**.

## What was added/changed in the MCP server
File: `startd8_mcp.py`

### Structured events (JSONL)
Every emitted event now includes stable identity fields:
- `service` (default: `startd8-mcp`) via `STARTD8_MCP_SERVICE`
- `env` (default: `local`) via `STARTD8_MCP_ENV`
- `version` (default: `0.1.0`) via `STARTD8_MCP_VERSION`

These are appended automatically inside `_emit_event()`.

### Prometheus metrics (side-channel HTTP server)
The server already supported `STARTD8_MCP_METRICS_PORT`. It now additionally exports:

- **Tool-level**
  - `startd8_mcp_tool_inflight{tool}` (gauge)
  - `startd8_mcp_tool_errors_total{tool,category}` (counter; category is normalized to keep cardinality low)
  - `startd8_mcp_tool_requests_total{tool,status}` (counter; status defaults to `ok` if missing)
  - `startd8_mcp_tool_duration_seconds{tool}` (histogram)

- **Skill discovery**
  - `startd8_mcp_skill_discovery_seconds{cached}` (histogram)

- **LLM call timing for `startd8_use_skill`**
  - `startd8_mcp_skill_llm_call_seconds{mode,status}` (histogram)
    - `mode` is `sdk` or `anthropic`

- **Task runner internal timings** (histograms)
  - `startd8_mcp_tasks_plan_seconds`
  - `startd8_mcp_tasks_prompt_build_seconds`
  - `startd8_mcp_tasks_agent_generate_seconds`
  - `startd8_mcp_tasks_action_parse_seconds`
  - `startd8_mcp_tasks_apply_actions_seconds{mode}` (`dry_run` or `apply`)

- **Runtime/process metrics**
  - Prometheus client collectors for process/platform/gc (best-effort)
  - `startd8_mcp_up` (gauge)
  - `startd8_mcp_build_info{...}` (info)

### Dependency note
File: `requirements-server.txt`

- Added `prometheus-client>=0.20.0` (required if you enable metrics via `STARTD8_MCP_METRICS_PORT`).

---

## Enable metrics + JSON event log for the MCP process
Set these env vars for the MCP server process:

```bash
# Metrics endpoint
export STARTD8_MCP_METRICS_PORT=9464
export STARTD8_MCP_METRICS_ADDR=0.0.0.0

# JSONL event log for Loki ingestion
export STARTD8_MCP_EVENT_LOG_FILE=./logs/mcp-events.jsonl

# Stable identity labels
export STARTD8_MCP_SERVICE=startd8-mcp
export STARTD8_MCP_ENV=local
export STARTD8_MCP_VERSION=0.1.0

# Optional: traces (Tempo) via Alloy OTLP receiver
export STARTD8_MCP_TRACING=1
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
```

Install the optional metrics dependency (in the MCP server env):

```bash
pip install prometheus-client
```

---

## Grafana Alloy config
File created: `alloy/startd8_mcp.alloy`

It supports both connectivity modes:
- **If Alloy runs in the same Docker network as your backends** (single compose):
  - **Mimir remote write**: `http://mimir:9009/api/v1/push`
  - **Loki write**: `http://loki:3100/loki/api/v1/push`
  - **Tempo OTLP/gRPC**: `tempo:4317`
- **If your backends are exposed on your Mac** (e.g. `~/Documents/tools/Grafana/docker-compose.yml` publishes ports):
  - **Mimir remote write**: `http://host.docker.internal:9009/api/v1/push`
  - **Loki write**: `http://host.docker.internal:3100/loki/api/v1/push`
  - **Tempo OTLP/gRPC**: `host.docker.internal:4317` (if you publish it)

### Scrape target you must verify
In `alloy/startd8_mcp.alloy`, the default scrape target is:

- `host.docker.internal:9464`

If your MCP server runs in Docker on the same network as Alloy, switch it to:
- `startd8-mcp:9464`

---

## Typical docker-compose service for Alloy
Mount the Alloy config and mount the MCP logs directory so Alloy can read `mcp-events.jsonl`.

```yaml
alloy:
  image: grafana/alloy:v1.9.1
  command: ["run", "/etc/alloy/config.alloy", "--server.http.listen-addr=0.0.0.0:12345"]
  volumes:
    - ./alloy/startd8_mcp.alloy:/etc/alloy/config.alloy:ro
    - ./logs:/var/log/startd8-mcp:ro
  ports:
    - "4317:4317"
    - "4318:4318"
    - "12346:12345"
```

In the Alloy config, logs are read from:
- `/var/log/startd8-mcp/mcp-events.jsonl`

---

## Run it end-to-end (local MCP on macOS + Docker backends)

### 1) Start the LGTM backends (Grafana/Mimir/Loki/Tempo)
If you’re using the stack in `~/Documents/tools/Grafana/`:

```bash
docker compose -f "$HOME/Documents/tools/Grafana/docker-compose.yml" up -d
```

### 2) Run Startd8 MCP with metrics + JSONL event log enabled
From this repo root:

```bash
mkdir -p ./logs

export STARTD8_MCP_METRICS_PORT=9464
export STARTD8_MCP_METRICS_ADDR=0.0.0.0
export STARTD8_MCP_EVENT_LOG_FILE=./logs/mcp-events.jsonl
export STARTD8_MCP_SERVICE=startd8-mcp
export STARTD8_MCP_ENV=local
export STARTD8_MCP_VERSION=0.1.0

# Optional: traces (Tempo) via Alloy OTLP receiver
export STARTD8_MCP_TRACING=1
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
```

### 3) Start Alloy (this repo) to ship telemetry to your backends
You can either add the Alloy service to your compose, or run it directly:

```bash
docker run -d --name startd8-alloy \\
  -p 4317:4317 -p 4318:4318 -p 12346:12345 \\
  -v \"$(pwd)/alloy/startd8_mcp.alloy:/etc/alloy/config.alloy:ro\" \\
  -v \"$(pwd)/logs:/var/log/startd8-mcp:ro\" \\
  grafana/alloy:v1.9.1 \\
  run /etc/alloy/config.alloy --server.http.listen-addr=0.0.0.0:12345
```

At this point:
- Metrics should appear in Grafana via the Mimir datasource.
- Logs should appear in Explore via the Loki datasource.
- Traces are optional; when enabled, tool calls become spans in Tempo. JSONL events will include `trace_id`/`span_id` for log↔trace correlation.

---

## Quick verification + troubleshooting

### Verify the MCP metrics endpoint (host)
From your Mac:

```bash
curl -sS http://localhost:9464/metrics | head
```

You should see metrics like `startd8_mcp_up` and `startd8_mcp_tool_requests_total`.

### Verify Alloy is running
If you started Alloy with the `--server.http.listen-addr=0.0.0.0:12345` flag and mapped `12346:12345`, open:
- `http://localhost:12346`

### Verify traces (optional)
If `STARTD8_MCP_TRACING=1` is enabled and Alloy is listening on `4318`:
- You should see a `tracing.started` event in `./logs/mcp-events.jsonl`.
- After at least one MCP tool call, JSONL events should include `trace_id` and `span_id`.
- In Grafana Explore (Tempo), search by **service name**: `startd8-mcp`.

### Common issues
- **Alloy can’t scrape MCP metrics**
  - Ensure MCP is bound to `0.0.0.0` (`STARTD8_MCP_METRICS_ADDR=0.0.0.0`), not `127.0.0.1`.
  - Ensure Docker can reach the host as `host.docker.internal` (Docker Desktop on macOS supports this).

- **Mimir/Loki rejects writes (401/403/400)**
  - Your backend may require a tenant header.
  - In `alloy/startd8_mcp.alloy`, uncomment the `X-Scope-OrgID` header (and/or `tenant_id` for Loki) and set it to the tenant your stack expects (often `anonymous` in local stacks).

## Suggested Grafana queries (dashboards/alerts)
Use these against your Mimir/Prometheus-compatible datasource.

### RED-style dashboard
- **Request rate (by tool/status)**
  - `sum by (tool, status) (rate(startd8_mcp_tool_requests_total[5m]))`

- **p95 tool latency**
  - `histogram_quantile(0.95, sum by (le, tool) (rate(startd8_mcp_tool_duration_seconds_bucket[5m])))`

- **Error rate (by tool/category)**
  - `sum by (tool, category) (rate(startd8_mcp_tool_errors_total[5m]))`

- **Inflight (by tool)**
  - `sum by (tool) (startd8_mcp_tool_inflight)`

### Basic alerts
- **No scrape / exporter missing**
  - `absent(startd8_mcp_up)`

- **High error rate (example threshold)**
  - `sum(rate(startd8_mcp_tool_errors_total[5m])) > 0.1`

---

## Notes on cardinality (important)
- Metrics labels intentionally avoid high-cardinality values.
- Do **not** label `request_id` or `run_id` in metrics or Loki labels.
  - Those should remain searchable in log body fields, not as labels.
