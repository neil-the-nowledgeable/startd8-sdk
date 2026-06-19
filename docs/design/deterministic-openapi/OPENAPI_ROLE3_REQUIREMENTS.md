# OpenAPI Role 3 — Inter-Context Seam (Requirements)

**Version:** 0.4 (M0–M5 + P2 + deferred D1–D5)
**Date:** 2026-06-19
**Status:** ✅ Shipped on `main` — continuation in `OPENAPI_ROLE3_NEXT_STEPS.md`
**Owner:** SDK / backend_codegen + integrations
**Motivated by:** `OPENAPI_LEVERAGE_ANALYSIS.md` Role 3 — promote the static contract into the
**cross-bounded-context** integration seam when a modular monolith splits
**Builds on:** Role 1 (`OPENAPI_ROLE1_REQUIREMENTS.md`, shipped) + Role 2 (`OPENAPI_ROLE2_REQUIREMENTS.md`, shipped)
**Paired plan:** `OPENAPI_ROLE3_PLAN.md`

---

## 0. Planning Context

Role 1 made `app/openapi_contract.py` the offline drift source of truth (`ROUTE_MANIFEST` +
`OPENAPI_SPEC`). Role 2 added `api.yaml` overlay merge. Role 3 answers: **when context A consumes
context B across a process/network boundary, what is the owned promotion path from in-process
Pydantic to served OpenAPI + typed consumer client?**

| Precondition (now shipped) | Role 3 builds on |
|---------------------------|------------------|
| Static `OPENAPI_SPEC` + `ROUTE_MANIFEST` | Served spec is a **conformance projection** of the owned module |
| `clients/http_client.py` (`ApiClient`) | Consumer-side typed escape hatch → **generated inter-context client** |
| `openapi_contract/schema_resolve.py` | Shared `$ref`/body synthesis for smoke + client gen |
| `boot_smoke` reads `ROUTE_MANIFEST` | Split contexts get **expected-route parity** across deploy smoke |
| Role 2 `api.yaml` overlay | Brownfield/adopted surface documented before split |

**Architectural anchor:** `IDEAL_TARGET_ARCHITECTURE` §6 (bounded-context split) + §4 (escape hatch).
Python-homogeneous services promote via OpenAPI; polyglot targets defer to gRPC/proto (`ProtoStubProvider`).

### 0.1 Planning Insights (reflective loop — closed)

| OQ | Resolution |
|----|------------|
| **OQ-1** | Standalone `prisma/contexts.yaml` + assembly-inputs catalog key `contexts` (same pattern as `api`, `imports`) |
| **OQ-2** | Per-producer `clients/{id}_client.py`; keep `clients/http_client.py` for local in-process spine |
| **OQ-3** | Default `routes: crud` — CRUD + overlay ops whose JSON bodies use Prisma DTO `$ref`s only; exclude HTML/AI/pages |
| **OQ-4** | Fail-closed `--check` via `schema-sha256` + `contexts-sha256` + `contract-sha256` (filtered producer spec) |
| **OQ-5** | OTel CLIENT spans on inter-context calls — span name ``context.outbound.<producer> <METHOD> <path>``; attrs ``io.startd8.context.producer_id``, ``io.startd8.context.outbound``, ``http.request.method``, ``url.path``; no-op without ``opentelemetry`` |

**Grammar (`contexts.yaml`):**

```yaml
outbound:
  - id: catalog              # alphanumeric/snake — drives clients/{id}_client.py
    local: true              # OR contract: openapi/catalog.json (relative to project root)
    base_url: "http://..."   # runtime doc comment only; override in __init__
    routes: crud             # crud | all_json
    schemas:                 # optional — explicit DTO allowlist (all_json / pinned contracts)
      - InvoiceRead
```

**M5 cross-repo (pinned `contract:`):** filtering uses producer OpenAPI paths/schemas directly;
the consumer Prisma schema is **not** required to share entity names. Use `routes: all_json` for
non-CRUD producer surfaces; optional `schemas:` restricts emitted component schemas.

---

## 1. Problem Statement

Today, integration across features stays **in-process** (`app.tables` Pydantic/SQLModel imports).
When a team extracts a service (payments, AI gateway, catalog), consumers need:

| Need | Current state | Gap |
|------|--------------|-----|
| Served API contract | Runtime `/openapi.json` only | No **promotion workflow** from owned static spec → served canonical URL |
| Typed consumer | `ApiClient` exists but is manual wiring | No **context-pair manifest** declaring producer/consumer + base URL |
| Drift across repos | Per-project `generate backend` | Consumer repo cannot detect **producer contract drift** |
| Smoke across contexts | `deploy_harness` in-process | No **cross-service smoke** using shared `select_crud_resource` + `ApiClient` |
| Polyglot | N/A in v1 OpenAPI path | Document boundary — Role 3 v1 is **Python↔Python OpenAPI** only |

---

## 2. Goals & Non-Goals

**Goals**
- Define an owned **inter-context manifest** (`prisma/contexts.yaml`) naming outbound producer contexts.
- Promote `OPENAPI_SPEC` to a **served contract artifact** (static module remains drift authority).
- Generate **per-producer consumer clients** from the **filtered** producer spec with stable import
  path and version pinning via `contract-sha256`.
- Cross-context smoke: generated `tests/test_cross_context_smoke.py` exercises each **local**
  outbound client via in-process `TestClient` shim + `run_context_client_smoke` (M2); **remote**
  producers via deploy harness `context_smoke` stage + env `STARTD8_CONTEXT_<ID>_BASE_URL` (M2c).

**Non-Goals (v1)**
- gRPC/proto promotion (separate `ProtoStubProvider` track).
- TypeScript client generation (escape hatch; Python-first).
- Service mesh / API gateway codegen.
- Auth middleware generation (declare schemes in spec only, same as Role 2).
- Multi-region federation.

---

## 3. Requirements

### Manifest & promotion
- **FR-1** Accept optional `prisma/contexts.yaml` (CLI `--contexts`, wireframe catalog key `contexts`).
- **FR-2** **Producer promotion:** `--export-openapi` writes `openapi.json` as a canonical JSON dump
  of owned `OPENAPI_SPEC` (no second editor; drift authority remains `app/openapi_contract.py`).
- **FR-3** **Consumer client gen:** emit `clients/{id}_client.py` per outbound entry from the
  producer's **filtered** spec; methods mirror Role 1 CRUD + Role 2 overlay ops with Prisma `$ref`s.

### Drift & versioning
- **FR-4** Consumer client header carries `schema-sha256`, `contexts-sha256`, and
  `contract-sha256` (hash of canonical JSON of the filtered producer spec).
- **FR-5** `owned_file_in_sync` threads `contexts.yaml` + `project_root` through provider skip-hook
  (FR-ED-16 precedent); drift kind `python-context-client` with `startd8-entity: {producer_id}`.

### Verification
- **FR-6** Cross-context smoke: emit `tests/test_cross_context_smoke.py` per **local** outbound
  context (in-process TestClient shim) and per **remote** context (live base URL when configured).
  Deploy harness `context_smoke` stage runs `run_outbound_context_smokes` after local smoke.
- **FR-7** Unit tests assert consumer method paths ⊆ producer `ROUTE_MANIFEST` (filtered subset).

### CLI / UX
- **FR-8** `startd8 generate backend --contexts <file>` drives consumer client emission; absent → SOTTO.
- **FR-9** `startd8 generate backend --export-openapi` remains the producer-side promotion command.

### Cross-repo contracts (M5)
- **FR-12** Pinned `contract:` entries filter the producer spec **without** consumer Prisma entity
  overlap (`pinned_contract` path in `filter_spec_for_client`).
- **FR-13** Optional `schemas:` list in `contexts.yaml` restricts emitted component schemas for
  `routes: all_json` or pinned CRUD contracts.
- **FR-14** Pinned clients emit spec-driven methods (`dict[str, object]` bodies) when consumer
  DTOs are absent — no `app.tables` imports for remote-only entities.

### Deferred follow-through (v0.4)
- **FR-15** Optional `auth: {scheme, env, header}` on outbound entries — env-sourced credentials.
- **FR-16** `emit_languages: [typescript]` emits `clients/{id}_client.ts`.
- **FR-17** `openapi/context-graph.json` machine-readable outbound dependency graph.
- **FR-18** `protocol: grpc` + `grpc_service` emits `clients/{id}_grpc_client.py`.
- **FR-19** Grafana dashboard template for `io.startd8.context.*` span metrics.

- **FR-10** Emit ``clients/_context_otel.py`` when contexts manifest present; each generated
  ``clients/{id}_client.py`` wraps HTTP via ``_request()`` → ``trace_outbound_request``.
- **FR-11** Span naming: ``context.outbound.<producer_id> <METHOD> <path>`` (CLIENT kind).
  Attributes: ``io.startd8.context.producer_id``, ``io.startd8.context.outbound``,
  ``http.request.method``, ``url.path``, ``http.response.status_code`` when available.
  Optional OTel — no-op when ``opentelemetry`` is not installed.

---

## 4. Open Questions — Closed

All five open questions resolved in §0.1. M0–M5 + P2 shipped on `main`.

---

## 5. Success Metrics

| Metric | Target | Milestone |
|--------|--------|-----------|
| Producer `openapi.json` matches owned `OPENAPI_SPEC` (canonical JSON) | ✅ | M0 |
| Consumer `clients/{id}_client.py` emitted with typed CRUD methods | ✅ | M1 |
| Producer contract edit → consumer `--check` stale | ✅ | M1 |
| Local outbound context list+create smoke (TestClient shim) | ✅ | M2 |
| Remote producer smoke via deploy harness | ✅ | M2c |
| Assembly-inputs template documents `contexts` | ✅ | M3 |
| Cross-repo pinned contract without consumer entity overlap | ✅ | M5 |
| Prime bucket-3 integration prompt wiring | ✅ | P2 |
| Two-app + cross-repo fixture smoke | ✅ | M4/M5 |

---

*v0.3 — shipped on `main`. Deferred tracks: `OPENAPI_ROLE3_NEXT_STEPS.md` §Deferred.*
