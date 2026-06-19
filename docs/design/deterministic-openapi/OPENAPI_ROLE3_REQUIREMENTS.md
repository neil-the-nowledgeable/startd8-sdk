# OpenAPI Role 3 — Inter-Context Seam (Requirements)

**Version:** 0.1 (Pre-planning — post Role 1+2 merge)
**Date:** 2026-06-19
**Status:** Planned — ready for reflective requirements / CRP
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
- Define an owned **inter-context manifest** (`contexts.yaml` or assembly-inputs extension) naming
  producer context, consumer context, and promoted route subset.
- Promote `OPENAPI_SPEC` to a **served contract artifact** (static module remains drift authority).
- Generate **consumer `ApiClient`** (or sibling package) from the **merged** producer spec with
  stable import path and version pinning via content hash.
- Wire **deploy smoke** to call producer via `ApiClient` using `select_crud_resource` ground truth.
- Reuse Role 1+2 drift patterns — no parallel contract file.

**Non-Goals (v1)**
- gRPC/proto promotion (separate `ProtoStubProvider` track).
- TypeScript client generation (escape hatch; Python-first).
- Service mesh / API gateway codegen.
- Auth middleware generation (declare schemes in spec only, same as Role 2).
- Multi-region federation.

---

## 3. Requirements (draft)

### Manifest & promotion
- **FR-1** Accept an optional **inter-context manifest** declaring named contexts and HTTP base URLs
  (installed: loopback; deployed: operator-supplied).
- **FR-2** **Producer promotion:** `OPENAPI_SPEC` exported to `openapi.json` (or served route) is a
  **lossless JSON dump** of the owned module — no second editor.
- **FR-3** **Consumer client gen:** emit `clients/{producer}_client.py` (or configured name) from
  producer's merged spec; methods mirror Role 1 CRUD + Role 2 overlay ops with Prisma `$ref`s.

### Drift & versioning
- **FR-4** Consumer client header carries **producer contract hash** (`contract-sha256` or
  `schema-sha256` + `api-sha256` composite) for fail-closed stale detection.
- **FR-5** `owned_file_in_sync` threads inter-context manifest through provider skip-hook (FR-ED-16
  precedent).

### Verification
- **FR-6** Cross-context smoke test template: `ApiClient` list+create round-trip against producer
  `select_crud_resource` path (reuses `schema_resolve` + deploy harness patterns).
- **FR-7** Contract tests assert consumer method paths ⊆ producer `ROUTE_MANIFEST`.

### CLI / UX
- **FR-8** `startd8 generate backend --contexts <file>` (or wireframe slot) drives consumer client
  emission when consumer context is current project.
- **FR-9** `startd8 generate backend --export-openapi` remains the producer-side promotion command.

---

## 4. Open Questions

- **OQ-1:** Manifest shape — extend `assembly-inputs.yaml` vs standalone `contexts.yaml`?
- **OQ-2:** Consumer client package layout — `clients/http_client.py` monolith vs per-producer modules?
- **OQ-3:** How much of producer `ROUTE_MANIFEST` is promoted — CRUD-only default vs full conditional surface?
- **OQ-4:** Version pinning — block consumer regen on producer hash mismatch vs warn-only in installed mode?
- **OQ-5:** Relationship to ContextCore OTel — span naming on `ApiClient` calls part of Role 3 or observability track?

---

## 5. Success Metrics

| Metric | Target |
|--------|--------|
| Producer `openapi.json` matches owned `OPENAPI_SPEC` byte-for-byte (modulo formatting) | M0 |
| Consumer `ApiClient` round-trip list+create in cross-context smoke | M1 |
| Producer contract edit → consumer `--check` stale | M1 |
| $0 LLM; deterministic skip-hook recognition | M1 |

---

*v0.1 — Initial Role 3 requirements scaffold post Role 1+2 merge. Run reflective-requirements loop before implementation.*
