# Role 3 M4 — Two-App Inter-Context Seam Fixture

End-to-end proof that **producer export → consumer contract pin → drift → remote smoke** works
outside isolated unit mocks.

## Layout

| Path | Role |
|------|------|
| `producer/schema.prisma` | Catalog (producer) bounded context |
| `consumer/schema.prisma` | Same `Note` entity — shared DTO namespace for `routes: crud` filter |
| `consumer/contexts.yaml` | Pins `openapi/catalog.json` (exported producer contract) |

## One-command smoke ($0)

From repo root:

```bash
./scripts/openapi_role3_m4_smoke.sh
```

Or directly:

```bash
PYTHONPATH=src pytest tests/unit/backend_codegen/test_openapi_role3_m4_fixture.py -q
```

## Manual workflow

### 1. Producer — generate + export

```bash
PROD=/tmp/role3-m4-producer
mkdir -p "$PROD/prisma"
cp docs/design/deterministic-openapi/fixtures/two-app-seam/producer/schema.prisma "$PROD/prisma/"

startd8 generate backend --schema "$PROD/prisma/schema.prisma" --out "$PROD"
startd8 generate backend --schema "$PROD/prisma/schema.prisma" --out "$PROD" --export-openapi

mkdir -p "$PROD/openapi"
cp "$PROD/openapi.json" "$PROD/openapi/catalog.json"
```

### 2. Consumer — pin contract + generate client

```bash
CON=/tmp/role3-m4-consumer
mkdir -p "$CON/prisma" "$CON/openapi"
cp docs/design/deterministic-openapi/fixtures/two-app-seam/consumer/schema.prisma "$CON/prisma/"
cp docs/design/deterministic-openapi/fixtures/two-app-seam/consumer/contexts.yaml "$CON/prisma/"
cp "$PROD/openapi/catalog.json" "$CON/openapi/catalog.json"

startd8 generate backend \
  --schema "$CON/prisma/schema.prisma" \
  --contexts "$CON/prisma/contexts.yaml" \
  --out "$CON"
```

Emits `clients/catalog_client.py`, `clients/_context_otel.py`, and `tests/test_cross_context_smoke.py`.

### 3. Drift — tamper contract

Edit `$CON/openapi/catalog.json` (e.g. add a path) then:

```bash
startd8 generate backend --schema "$CON/prisma/schema.prisma" \
  --contexts "$CON/prisma/contexts.yaml" --out "$CON" --check
```

Expect exit **1** — `contract-sha256` stale on `clients/catalog_client.py`.

### 4. Remote smoke — live producer

Boot the producer (installed mode, SQLite in CWD):

```bash
cd "$PROD"
export DATABASE_URL="sqlite:///./data/app.db"
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In another shell, point the consumer harness at the live catalog:

```bash
export STARTD8_CONTEXT_CATALOG_BASE_URL="http://127.0.0.1:8001"
# deploy harness context_smoke stage (or pytest M4 remote test) exercises list+create
```

## What M4 proves

| Step | Evidence |
|------|----------|
| Producer export | `openapi/catalog.json` ≡ canonical `OPENAPI_SPEC` |
| Consumer client | `CatalogClient` methods ⊆ pinned contract paths |
| Drift | Contract edit → `--check` fails closed |
| Remote smoke | `run_outbound_context_smokes` list+create against live HTTP |

## See also

- `OPENAPI_ROLE3_NEXT_STEPS.md` — M4 marked complete when this fixture lands
- `OPENAPI_ROLE3_REQUIREMENTS.md` — FR-2, FR-4, FR-6
