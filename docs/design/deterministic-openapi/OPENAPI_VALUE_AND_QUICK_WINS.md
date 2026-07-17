# OpenAPI Stack — Value, Quick Wins, and Operational Enhancements

**Status:** Advisory (post PR #91)  
**Audience:** SDK developers, FDEs, commissioning teams  
**Scope:** End-user value, functional/architectural quick wins, operational improvements

---

## Context — What Is Shipped

The deterministic OpenAPI stack on `main` (merged via [PR #91](https://github.com/neil-the-ownershipable/startd8-sdk/pull/91)) includes:

| Layer | Capability | Entry point |
|-------|------------|-------------|
| **Role 1** | Static contract from Prisma | `startd8 generate backend` → `app/openapi_contract.py` |
| **Role 2** | Surface overlay (`api.yaml`) | `startd8 generate backend --api` |
| **Role 2 brownfield** | OpenAPI → overlay ingest | `startd8 openapi normalize <openapi.json> --out api.yaml [--schema]` |
| **Role 3** | Inter-context contracts | `contexts.yaml` + context client/contract renderers |
| **Schema unification** | Single Prisma→JSON-Schema source | `src/startd8/schema_contract/prisma_json_schema.py` |
| **Tier-1 cascade** | Scaffold, proto, events, migrations, OTel | `$0` deterministic providers |

**Not a formal “Phase 3” in the Role 2 plan** — that plan’s four steps are complete. Remaining work is deferred items (handler gen, TS client, auth middleware from `securitySchemes`, capability-index FR-X5, polyglot Role 3 leftovers).

---

## Highest Value to the End User

These are changes a commissioning developer or FDE would feel immediately.

### 1. Wire the brownfield story into concierge + wireframe (not just CLI)

Today `startd8 openapi normalize` exists, but **concierge `assess` / wireframe do not mention it**. A brownfield user still has to discover the command independently.

**Quick win:** When `survey` detects an existing `openapi.json` / FastAPI live spec and no `prisma/api.yaml`, surface guidance such as:

```bash
startd8 openapi normalize ext.json --schema prisma/schema.prisma --out prisma/api.yaml
# review, then:
startd8 generate backend --api prisma/api.yaml
```

Link to [`examples/api.yaml.example`](examples/api.yaml.example).

**Value:** Turns Phase 2 from a power-user CLI into an onboarding path — aligns with kickoff’s `prisma/api.yaml` row in [`ASSEMBLY_INPUTS_TEMPLATE.md`](../kickoff/ASSEMBLY_INPUTS_TEMPLATE.md).

### 2. One-command “overlay smoke” script (mirror Role 3)

Role 3 has `scripts/openapi_role3_m4_smoke.sh`. Role 2 has no equivalent.

**Quick win:** Add `scripts/openapi_role2_overlay_smoke.sh`:

```bash
# normalize (optional) → generate backend --api → --check → --export-openapi → --gate
```

**Value:** Operators and CI get a copy-paste proof that overlay + client + contract drift work together.

### 3. Extend FR-X4 cascade test to include OpenAPI overlay

[`tests/unit/test_tier1_cascade.py`](../../tests/unit/test_tier1_cascade.py) covers scaffold + proto + events but **not** `--api` overlay merge or `openapi normalize`.

**Quick win:** Add a ~30-line segment: copy `api.yaml.example` → `generate backend --api` → assert `clients/http_client.py` has overlay method + `# api-sha256:`.

**Value:** Regressions in the path users care about (custom routes + typed client) get caught in the same $0 gate as other Tier-1 providers.

### 4. Wireframe should show overlay impact, not just “schema-only contract”

Wireframe already validates `api.yaml` via `parse_api_overlay`, but the catalog blurb is static: *“schema-only OpenAPI contract (no api.yaml overlay merge)”* when absent.

**Quick win:** When `api` is `planned`/`authored`, show merged route count, validation-only warnings, and whether overlay client methods would emit (Prisma `$ref` ops vs inline-only).

**Value:** Pre-generation summary becomes truthful for Role 2 — users see *why* `api.yaml` matters before spending on integration.

---

## Functional Quick Wins

Low effort, high leverage.

| Item | What | Why |
|------|------|-----|
| **`openapi normalize --dry-run`** | Print kept/stripped paths + warnings; do not write | Safe brownfield triage in concierge/CI |
| **`openapi validate api.yaml`** | Run `parse_api_overlay` + `reconcile_overlay` against schema; exit 0/1/2 | Same pattern as `polish check` — $0 pre-commit hook |
| **Dev dep for `--gate`** | Document or add `[dev]` extra: `openapi-spec-validator` | Fixes recurring env failure when `--gate` runs; gate becomes trustworthy locally |
| **Update Role 2 req table** | FR-12 / brownfield rows still say “deferred to Phase 2” in §0 insight table | Doc hygiene — reduces “is this shipped?” confusion |
| **Capability index (FR-X5)** | Add `startd8.openapi.normalize`, `startd8.codegen.openapi_role2_overlay`, `startd8.schema_contract` entries | Discoverability via agent card / MCP / harbor tour |
| **`assembly-inputs.yaml` example** | Include `api: { path, status }` in wireframe output when overlay planned | Closes kickoff ↔ wireframe gap for the 8th manifest |

---

## Architectural Quick Wins

### 5. Close the brownfield loop: export → normalize → regenerate

Document (or automate) the round-trip:

```bash
startd8 generate backend --export-openapi openapi.json   # live/conformance export
startd8 openapi normalize openapi.json --schema prisma/schema.prisma --out prisma/api.yaml
# human review
startd8 generate backend --api prisma/api.yaml --check
```

**Value:** Gives brownfield teams **deterministic contract discipline** without hand-maintaining two sources of truth.

### 6. Shared path normalization → wireframe + normalize + generate

Trailing-slash policy is unified via `rewrite_overlay_path_keys`. **Next:** expose path-normalization warnings in wireframe `assess` JSON so UI/TUI/concierge can show them before `generate backend` fails with `ReconcileError`.

### 7. Extend `schema_contract` to events + harness (Tier-1 exit metric)

Unification landed for OpenAPI. **Quick win:** Point events payload validation and any remaining harness JSON Schema resolution at `schema_contract` only — grep for duplicate scalar/type projection logic elsewhere.

### 8. Prime / bucket-3 prompt for overlay routes

Role 3 has `context_integration` prompt injection. **Quick win:** When `api.yaml` adds paths, inject a one-liner into Prime integration pass: *“Implement handlers in `user_routers.py` for: …”* (provenance from merged `ROUTE_MANIFEST`, not LLM-invented paths).

**Value:** Closes the biggest functional gap users still hit: contract says the route exists, but nothing tells bucket 3 to wire it.

---

## Operational Enhancements

### 9. CI matrix slice for OpenAPI overlay

Add a job (or extend existing unit job):

```bash
pytest tests/unit/backend_codegen/test_openapi_normalize.py \
       tests/unit/backend_codegen/test_api_overlay.py \
       tests/unit/backend_codegen/test_openapi_client_renderer.py \
       -q
```

Cheap; protects the Phase 2 investment.

### 10. Pre-commit / `startd8 generate backend --check` in cap-dev-pipe

If cap-dev-pipe projects include `prisma/api.yaml`, thread `--api` through the deterministic spine check (same as `--imports`, `--views`).

### 11. Observability: overlay merge warnings in OTel/logs

`apply_api_overlay` already returns validation-only warnings. **Quick win:** Emit them at INFO during `generate backend` (like migration hints) so Loki shows *“validation-only: /ai/extract declared but not in base”* without reading stderr in CI logs.

### 12. Operator hygiene + “where to start” doc

- Remove stale worktree `startd8-openapi-phase2` if no longer needed.
- Add a short “OpenAPI deterministic stack” decision tree to [`OPENAPI_LEVERAGE_ANALYSIS.md`](OPENAPI_LEVERAGE_ANALYSIS.md):

| Situation | Path |
|-----------|------|
| Schema-only API | Role 1 — `generate backend` |
| Custom routes / ops | Role 2 — `prisma/api.yaml` + `--api` |
| Brownfield ingest | `startd8 openapi normalize` → review → `--api` |
| Split bounded contexts | Role 3 — `contexts.yaml` |

---

## Deprioritize (Diminishing Returns)

| Item | Rationale |
|------|-----------|
| TS overlay client, mock servers, OpenAPI 3.1 | Explicitly out of scope |
| Auto-generating `user_routers.py` handlers | Bucket 3 / Prime territory; high scope |
| Concierge closed-grammar `api.yaml` extractor | Wireframe + example + `validate` command gets ~80% |
| Service mesh / polyglot Role 3 extensions | Role 3 Python seam is complete |

---

## Suggested 2-Week “Value Pack”

If picking three items to implement next:

| Priority | Deliverable | User-visible outcome |
|----------|-------------|----------------------|
| **P0** | Concierge/wireframe brownfield hint + `openapi validate` | Brownfield users find the path without reading design docs |
| **P1** | `openapi_role2_overlay_smoke.sh` + cascade test extension | Operators trust overlay in CI |
| **P2** | Capability index + Prime overlay route hint | Agents/docs discover it; bucket 3 wires custom routes |

**Recommended next increment:** P0 (concierge/wireframe + `openapi validate`) — connects shipped codegen to human bookends (survey/assess/kickoff) without new codegen surface area.

---

## Related Documents

- [`OPENAPI_ROLE1_REQUIREMENTS.md`](OPENAPI_ROLE1_REQUIREMENTS.md)
- [`OPENAPI_ROLE2_REQUIREMENTS.md`](OPENAPI_ROLE2_REQUIREMENTS.md)
- [`OPENAPI_ROLE2_PLAN.md`](OPENAPI_ROLE2_PLAN.md)
- [`OPENAPI_ROLE3_NEXT_STEPS.md`](OPENAPI_ROLE3_NEXT_STEPS.md)
- [`examples/api.yaml.example`](examples/api.yaml.example)
- [`../kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`](../kickoff/ASSEMBLY_INPUTS_TEMPLATE.md)
