# HOWTO — Affordance-map biased generate

> Operator recipe for REQ/PLAN v0.4 — **shipped** on `main` @ `deaa7fbb` (2026-07-28).

## Goal

After a ContextCore Observability Audit emits `affordance_map`, re-run startd8 generate for **only** the live `gen.*` repairs — merging index/quality so untouched services stay intact.

## End-to-end recipe

```bash
# 0) Prerequisites: onboarding metadata + prior full generate under OUT
ONB=path/to/onboarding-metadata.json
OUT=path/to/observability-out
SCORECARD=path/to/scorecard.json   # CC audit output

# 1) Audit (ContextCore) — produces scorecard-json with affordance_map
contextcore observability audit … -o "$SCORECARD"

# 2) Extract slim map (optional; generator also accepts the scorecard object)
jq '.affordance_map' "$SCORECARD" > affordance_map.json

#    Or pass the scorecard as-is:
#    --affordance-map "$SCORECARD"

# 3) Dry-run plan (stdout only — no files written, including no sidecar)
python3 scripts/generate_observability_artifacts.py \
  --onboarding-metadata "$ONB" \
  --output-dir "$OUT" \
  --affordance-map affordance_map.json \
  --dry-run
# Expect: "AffordanceMap action plan:" + optional SKIP lines for advisory ids

# 4) Apply targeted repairs (merges manifest/quality; writes sidecar)
python3 scripts/generate_observability_artifacts.py \
  --onboarding-metadata "$ONB" \
  --output-dir "$OUT" \
  --affordance-map affordance_map.json

# 5) Inspect sidecar
jq '{summary, all_skipped, source_truncated, source_provenance}' \
  "$OUT/affordance_actions.json"
jq '.applied[] | {service_id, affordance_id, content_hash_before, content_hash_after, rendered_hash_after}' \
  "$OUT/affordance_actions.json"
jq '.skipped[] | {service_id, affordance_id, reason, unmapped_reason}' \
  "$OUT/affordance_actions.json"
```

Optional service filter (intersection with map):

```bash
python3 scripts/generate_observability_artifacts.py \
  --onboarding-metadata "$ONB" \
  --output-dir "$OUT" \
  --affordance-map affordance_map.json \
  --services store,query-frontend
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | ≥1 `applied` / `applied_no_change`, or empty map / empty `--services` ∩ map |
| 2 | Malformed / unreadable map |
| 3 | Non-empty map, every row skipped (`all_skipped: true` in sidecar) |

## Sidecar — `affordance_actions.json` (FR-B7)

Written on apply (and on empty-intersect no-op). **Not** written on `--dry-run`.

| Field | Meaning |
|-------|---------|
| `schema_version` | `1` |
| `dry_run` | always `false` when file is written |
| `source_truncated` | map from history-capped / trimmed scorecard |
| `source_shape` | `array` \| `scorecard` |
| `source_provenance` | unique `provenance` strings from map rows |
| `all_skipped` | true when every row was skipped |
| `summary` | counts: planned / applied / applied_no_change / skipped |
| `planned` | residual planned rows (normally empty after apply) |
| `applied` | rows that changed artifacts (+ content hashes) |
| `applied_no_change` | action ran, bytes unchanged (e.g. freshness-only RED) |
| `skipped` | reasons + echoed `unmapped_reason` when present |
| `written_paths` | relative paths written this run |

Per-row durability fields (when touched): `content_hash_before` / `content_hash_after` (dashboard spec); shrink also sets `rendered_hash_before` / `rendered_hash_after` for Grafana JSON when present.

## Join table (`element_id` → `ServiceHints.service_id`)

ENV_FORM (`^[A-Z][A-Z0-9_]*(?:_SERVICE)?$`): strip trailing `_SERVICE` → delete `_` → lowercase → append `service` if the slug does not already end with it.

| Map `element_id` | Normalized | Typical hint id | Match |
|------------------|------------|-----------------|-------|
| `PRODUCT_CATALOG` | `productcatalogservice` | `productcatalogservice` | ladder step 2 |
| `PRODUCT_CATALOG_SERVICE` | `productcatalogservice` | `productcatalogservice` | ladder step 2 |
| `store` | `store` | `store` | exact |
| `query-frontend` | `query-frontend` | `query-frontend` | exact |

Match ladder: (1) exact → (2) normalized equals hint → (3) `(?:service)?$`-insensitive equivalence. Unknown → skip (exit 3 if all rows skip).

## Known gen set (live vs skip)

| Affordance | Mode |
|------------|------|
| `gen.emit_red_panels` | live |
| `gen.complete_triplet` | live |
| `gen.shrink_dashboard_lines` | live (spec → re-render; refuse if no render / RED regress) |
| `gen.improve_metric_coverage` | **advisory** → `skipped` / `no_deterministic_lever` |
| `gen.enrich_runbook` | **live** — retrofit pre-FR-B5 runbooks (rename/inject Overview·Risks·Procedures; keep Escalation) |

## Notes

- Map mode **replaces** full-tree generate; refuse `--check` and `--min-*-coverage` with a map.
- Do not `import contextcore` from startd8; pass JSON only (AC-G7).
- Quality SSOT remains `observability-quality.json` (merged, not a second scorer).
- Manifest merge **upserts by `(type, service)`** — a dashboard-only repair must not drop that service’s alert/SLO rows.
- Shrink durability is content-hash in the sidecar — not `--check` (which does not compare dashboard bytes).
