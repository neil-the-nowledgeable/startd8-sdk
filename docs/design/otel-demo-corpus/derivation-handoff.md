# Tier 1 — Derivation handoff & pattern-coverage cross-reference (FR-4 / FR-7)

**Status:** handoff doc (ContextCore extension out of scope here — NR-5)  
**Requirements:** [TIER1_CORPUS_REQUIREMENTS.md](./TIER1_CORPUS_REQUIREMENTS.md)  
**Tier 0 evidence:** `coverage-attestation.json` (produced by `scripts/otel_demo/attest_coverage.py`)

---

## Pattern coverage = verify Tier 0, not rebuild (FR-4)

Landscape sections §5.4 (messaging), §5.5 (database), and §5.6 (feature flags) are **evidenced live**
by Tier 0's §4 acceptance rows — not by new benchmark cells.

| Landscape § | Tier 0 attestation `section_id` | Backend | Query (summary) |
| --- | --- | --- | --- |
| §5.4 Messaging | `5.4-messaging` | Jaeger | `messaging.system=kafka`, PRODUCER/CONSUMER kinds |
| §5.5 Database | `5.5-database` | Jaeger | `db.system` ∈ {postgresql, valkey, redis} |
| §5.6 Feature flags | `5.6-feature-flags` | Jaeger | span tag `feature_flag.key` |

**Tier 1 acceptance (A7):** re-run `make tier0-attest` (or read the latest
`coverage-attestation.json`) and confirm those three sections have `evidence_status: pass`. No
OTel seed or matrix cell is required for these patterns (NR-2: Kafka is not an RPC benchmark cell).

---

## ContextCore derivation handoff (FR-7 / NR-5)

The sibling **ContextCore** repo owns `_PROTOCOL_METRICS`, `_OTEL_SDK_MAP`, and
`_DATABASE_IMPORT_PATTERNS`. Tier 1 does **not** extend those tables here — it emits the **input
contract** from Tier 0 attestation `observed_names` fields.

After a successful Tier 0 attestation, copy from `coverage-attestation.json`:

```json
{
  "messaging": {
    "section_id": "5.4-messaging",
    "observed_names": ["messaging.system", "messaging.destination.name"]
  },
  "database": {
    "section_id": "5.5-database",
    "observed_names": ["db.system"]
  },
  "feature_flags": {
    "section_id": "5.6-feature-flags",
    "observed_names": ["feature_flag.key"]
  },
  "span_metrics_connector": {
    "section_id": "7.1-connector",
    "observed_names": ["traces_span_metrics"]
  }
}
```

Populate `observed_names` from the live attestation rows (values may include concrete enum strings
observed in Jaeger/Prometheus, e.g. `postgresql`, `kafka`).

### ContextCore TODO (cross-repo)

1. Extend `_PROTOCOL_METRICS` with messaging + span-metrics connector names from attestation.
2. Extend `_DATABASE_IMPORT_PATTERNS` with `db.system` values observed (`postgresql`, `valkey`, `redis`).
3. Add feature-flag semantic imports keyed on `feature_flag.key`.
4. Pin attestation `demo_ref` + `git_sha` in the ContextCore derivation manifest for reproducibility.

---

## OTel structural corpus (FR-1)

Benchmark cells for language coverage live in `docs/design/model-benchmark/seeds-otel/` (7 services).
Pattern coverage does **not** add cells — it cross-references this attestation.

**Handoff complete when:** A7 + A8 acceptance rows are satisfied alongside `gen_otel_benchmark_seeds.py --check`.
