# StartD8 Kickoff Stakeholders — Grafana panel (Phase 2 M1)

Runs the stakeholder panel from the **Digital Project Workbook** and renders the answers, driving the
SDK's secured run endpoint (`src/startd8/kickoff_experience/stakeholder_run_server.py`).

**Flow:** type a question (+ optional cap) → **Preview cost** (dry-run, no spend → honest estimate +
`run_key`) → **confirm modal** shows the estimate → **Run** POSTs the confirm **echoing the dry-run's
`run_key`** (so the spent run is provably the previewed one, FR-11) → per-persona answers render with a
persistent **SYNTHETIC & UNRATIFIED** banner. A `deduped` status means the `run_key` already ran (not
re-charged).

## Security — the token is NOT in this panel (FR-2 / S-3)

The bearer token would be **world-readable in the dashboard JSON** if it were a panel option, so it is
not. Requests route through a Grafana **datasource proxy** whose `secureJsonData` holds the token and
adds it server-side. The panel only takes a **datasource UID**.

### Datasource setup (once)

The panel POSTs to `/api/datasources/proxy/uid/<uid>/stakeholders/<...>`. Grafana's **core datasource
proxy** forwards `<url>/stakeholders/<...>` and injects `Authorization: Bearer <token>` via the
`httpHeaderName1` / `httpHeaderValue1` pair — so the **token is added server-side**, never in the
dashboard JSON or the browser (FR-2 / S-3). Two ways to provision (both under `provisioning/`):

- **No-restart API upsert (preferred on shared Grafana):** `provisioning/provision-datasource.sh`.
  Survives token rotation (re-run with a fresh token); no Grafana restart. Operator-run — it mutates a
  possibly shared instance.
  ```bash
  GRAFANA_URL=http://localhost:3000 GRAFANA_TOKEN=<grafana-sa-token> \
  STAKEHOLDER_TOKEN=<from `serve`> ENDPOINT_URL=http://host.docker.internal:8710 \
    provisioning/provision-datasource.sh
  ```
- **Declarative:** `provisioning/datasources/stakeholders.yaml` — env-interpolated token
  (`$__env{STARTD8_STAKEHOLDER_TOKEN}`), so rotation needs a provisioning reload/restart (NR-10 blast
  radius on the shared `o11y-dev` — prefer the script).

Type is `yesoreyeram-infinity-datasource` (installed on `o11y-dev`); the custom-header pair is applied
by Grafana core, so any HTTP datasource type works. Then set the panel option **Run datasource UID** to
the datasource's UID (default `startd8-stakeholders`).

**Strict mode + the apply gate.** The FR-R7 apply gate mandates `--strict` (Origin allow-list + replay
nonce). Through the proxy the browser Origin is not the upstream Origin, so **run `serve` with no
`--allowed-origin`** (the endpoint skips the Origin check when the allow-list is empty) and rely on the
replay nonce: the panel sends a fresh **`X-Nonce`** per request, which the proxy forwards upstream. So
`serve --enable-apply --strict` (no `--allowed-origin`) is the proxy-compatible apply posture.

## Build

```bash
npm install
npm run typecheck
npm run build      # -> dist/ (module.js + plugin.json)
```

## Provisioning — UNSIGNED plugin on a SHARED Grafana (⚠ NR-10)

This is unsigned. Loading it requires an allow-list entry **and a Grafana restart**. On the shared KinD
`o11y-dev` Grafana that also hosts the `cc-portal-online-boutique` dashboards, a restart has **blast
radius** — this is an **operator decision**, not automated.

1. Confirm/extend the allow-list: `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=…,startd8-stakeholders-panel`.
2. Mount `dist/` at `/var/lib/grafana/plugins/startd8-stakeholders-panel` (ConfigMap/PVC/hostPath).
3. Restart Grafana (coordinate — shared instance).
4. Add the panel to the Workbook dashboard; set **Run datasource UID**.
5. Start the endpoint: `startd8 kickoff stakeholders serve --daily-ceiling 5` (prints the token → put it
   in the datasource `secureJsonData`).

## Fork provenance

Forked from ContextCore owl `contextcore-workflow-panel` (build scaffold reused). Rewritten `src/`:
input capture (question + cap), the dry-run→confirm-with-`run_key` integrity fix (the base re-POSTed
fresh, ignoring the dry-run), a per-persona answer render (base rendered run-steps), and datasource-
proxy token routing (base sent no credentials).
