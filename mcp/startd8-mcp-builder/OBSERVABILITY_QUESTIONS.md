## Goal
Configure **Grafana Alloy** to ingest this MCP server’s telemetry locally (metrics first, optionally logs/traces), and apply best-practice observability to the MCP server without breaking MCP stdio.

---

## 1) How should metrics flow into Grafana?
Grafana is a UI; it needs a metrics backend (Prometheus/Mimir/etc.).

- **Metrics backend** (pick one):
  - [ ] **Prometheus**
  - [x] **Mimir**
  - [ ] **Other** (name it): ________

- **Backend URL** (the one Alloy should write to):
  - Answer: `http://mimir:9009/api/v1/push` (Docker network)

- **If Prometheus**: will you enable the remote-write receiver?
  - (Prometheus needs `--web.enable-remote-write-receiver` for Alloy remote_write → Prometheus)
  - [x] Yes
  - [ ] No (then Alloy should not remote_write to Prometheus; we’ll scrape from Prometheus instead)

---

## 2) Where is Alloy running?
This determines how Alloy reaches `localhost`.

- **Alloy runtime**:
  - [ ] Native process on macOS
  - [x] Docker container
  - [ ] Kubernetes

- If Docker/K8s: what should Alloy use to reach services on your Mac?
  - [ ] `host.docker.internal`
  - [x] Something else: `docker service DNS names on the compose network (e.g. mimir, loki, tempo, pyroscope)`

---

## 3) How will the MCP server expose Prometheus metrics?
The server already supports a Prometheus endpoint when enabled via env vars.

- Which port do you want to use for `/metrics`?
  - Default suggestion: `9464`
  - Answer: `9464`

- Bind address for the metrics HTTP server:
  - [ ] `127.0.0.1` (only local host)
  - [x] `0.0.0.0` (needed if Alloy is in Docker/K8s and scrapes from outside host network namespace)
  - Answer: `0.0.0.0`

- Is `prometheus-client` installed in the MCP server environment?
  - [ ] Yes
  - [ ] No
  - [x] Not sure

---

## 4) Logs: do you want Alloy → Loki?
This repo already emits JSONL events (good for Loki).

- Do you have **Loki** locally?
  - [x] Yes
  - [ ] No

- If yes: Loki write endpoint Alloy should use:
  - Answer: `http://loki:3100/loki/api/v1/push` (Docker network)

- Where should Alloy read MCP event logs from?
  - Default in MCP-client mode: `./logs/mcp-events.jsonl` (relative to project root)
  - Answer: `./logs/mcp-events.jsonl`

---

## 5) Traces: do you want OpenTelemetry → Tempo?
Traces are optional but helpful if you want request/tool spans and latency breakdowns.

- Do you have **Tempo** locally?
  - [x] Yes
  - [ ] No

- If yes: Tempo/OTLP endpoint Alloy should write to:
  - Answer: `tempo:4317` (OTLP/gRPC, Docker network)

---

## 6) Best-practices scope (what you want me to implement in code)
Pick what you want beyond the existing `/metrics` endpoint.

- **Metrics**:
  - [x] Add per-tool **inflight gauge**
  - [x] Add **error counter** with normalized reason/category (avoid high-cardinality)
  - [x] Add latency histograms for key internal operations (skill discovery, skill execution, task runner)
  - [x] Add **process/runtime** metrics (CPU/mem) (via Prometheus client process collector)

- **Logs**:
  - [x] Ensure all structured events include a stable `service`, `env`, and `version`
  - [x] Add log correlation fields (request/tool correlation id) without exploding cardinality

- **Traces**:
  - [ ] Add spans for tool calls and major sub-steps
  - [ ] Propagate correlation ids into logs + metrics exemplars (if supported)

- **Dashboards/alerts** (generated guidance, not necessarily committed files):
  - [x] Suggested Grafana dashboards (RED for tool calls)
  - [x] Suggested alert rules (error rate, latency, no-scrape)

---

## 7) Names/labels (to avoid surprises later)
- What do you want as the **service name** in labels?
  - Answer (default `startd8-mcp`): `startd8-mcp`

- Environment label?
  - Answer (default `local`): `local`
