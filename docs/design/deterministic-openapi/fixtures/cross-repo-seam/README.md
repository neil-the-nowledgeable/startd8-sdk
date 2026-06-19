# Role 3 M5 — Cross-Repo Inter-Context Seam Fixture

Producer and consumer **Prisma schemas diverge** (no shared `Note` entity). The consumer pins
the producer's exported OpenAPI contract; client generation uses **pinned-contract filtering**
(producer paths/schemas) instead of consumer Prisma overlap.

## Layout

| Path | Role |
|------|------|
| `producer/schema.prisma` | Catalog producer (`Note`) |
| `consumer/schema.prisma` | Unrelated consumer (`DashboardJob` only) |
| `consumer/contexts.yaml` | Pins `openapi/catalog.json`, `routes: crud` |

## Publish contract (producer CI)

From repo root after generating the producer app:

```bash
./scripts/openapi_role3_publish_contract.sh \
  /tmp/role3-m5-producer catalog
```

Writes `openapi/catalog.json` and prints `contract-sha256` for pinning in consumer CI.

## Consumer regen workflow

1. Copy or receive `openapi/catalog.json` (+ optional hash annotation in CI log).
2. Set `prisma/contexts.yaml` → `contract: openapi/catalog.json`.
3. Run `startd8 generate backend --schema prisma/schema.prisma --contexts prisma/contexts.yaml --out .`
4. Drift guard: `startd8 generate backend ... --check` (exit 1 on `contract-sha256` stale).

## One-command smoke ($0)

```bash
./scripts/openapi_role3_m5_smoke.sh
```

## What M5 proves

| Step | Evidence |
|------|----------|
| Pinned filter | `/note/` paths kept though consumer has no `Note` model |
| Client gen | `CatalogClient` with `list_note` / `create_note` using `dict` bodies (no `app.tables` import) |
| Remote smoke | `run_outbound_context_smokes` list+create against live producer HTTP |

## `routes: all_json` + `schemas:`

For non-CRUD producer APIs, use `routes: all_json` and optionally restrict DTOs:

```yaml
outbound:
  - id: billing
    contract: openapi/billing.json
    routes: all_json
    schemas:
      - InvoiceRead
      - InvoiceCreate
```
