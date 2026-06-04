# Service Assistant — Triage Artifact Schema

**Version:** 1.0 (draft)
**Date:** 2026-06-03
**Status:** Interface contract — pre-implementation
**Tracks:** `SERVICE_ASSISTANT_REQUIREMENTS.md` v0.2 (FR-7), resolves **OQ-9**

---

## Why this document exists

FR-7 makes `service-assistant-triage.json` the **authoritative project↔SDK bridge** (the
EventBus events are supplementary, since the bus has no guaranteed consumer). Everything
else in the component is mechanical once this contract is fixed. This doc pins:

1. the **JSON Schema** for the artifact,
2. a **worked example**,
3. the **`CAUSE_TO_OPERATIONAL_ACTION`** mapping for all 19 `RootCause` values (OQ-9),
4. the **event payload** contract for FR-6.

### OQ-9 resolution

`RootCause` has **19 members** (18 concrete + `UNKNOWN`); `PipelineStage` has **11**. That's
small enough to map **exhaustively** — a curated subset would create silent gaps where an
unmapped cause reads as "no recommendation," which the requirements explicitly warn against.
Decision: **map all 19**, with `UNKNOWN` → `manual_review`. A unit test (`test_operational_
action_coverage`) asserts every `RootCause` member resolves to an action, so future enum
additions fail loudly instead of falling through silently.

---

## 1. Controlled vocabularies

### `run.status`
`completed` · `partial` · `aborted` · `in_progress`

### `verdict.aggregate_verdict`
`PASS` · `PARTIAL` · `FAIL` · `ABORTED` · `UNKNOWN`
(`PASS`/`PARTIAL`/`FAIL` mirror the post-mortem; `ABORTED` is SA-derived via FR-13;
`UNKNOWN` = run sentinel present but verdict unresolvable.)

### `severity`
`critical` · `high` · `medium` · `low`

### `recommended_action.re_run_strategy`
| Strategy | Meaning |
|----------|---------|
| `retry_as_is` | Transient/infra failure — re-run the same element unchanged. |
| `reduce_scope` | Element too large — split into fewer lines per generation. |
| `split_element_or_increase_tier` | Complexity under-budgeted — decompose or raise tier. |
| `re_run_prior_stage` | A predecessor stage (e.g. skeleton/plan-ingestion) failed — re-run it first. |
| `from_latest_producer` | Cross-file contract drift — re-run from the feature that owns the contract, sync exports. |
| `unblock_dependency` | Upstream feature must succeed first. |
| `regenerate_clean` | Corrupted/duplicated/stub output — force a clean regeneration. |
| `fix_repair_routing` | Repair pipeline misrouted/exhausted — config/routing fix, not a re-run. |
| `fix_deterministic_generator` | **$0 deterministic failure (FR-14)** — a plain re-run is idempotent and reproduces the defect; fix the generator/splicer/template or escalate the element off the deterministic path. |
| `align_types` | Type/contract mismatch — re-run with consumer types pinned. |
| `manual_review` | No deterministic strategy — human/agent inspects. |

---

## 2. JSON Schema (`service-assistant-triage.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://startd8/schemas/service-assistant-triage-1.0.json",
  "title": "ServiceAssistantTriage",
  "type": "object",
  "required": ["schema_version", "generated_at", "assistant_version", "run", "detection", "verdict", "failures"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "1.0" },
    "generated_at": { "type": "string", "format": "date-time" },
    "assistant_version": { "type": "string" },

    "run": {
      "type": "object",
      "required": ["run_id", "output_dir", "status"],
      "additionalProperties": false,
      "properties": {
        "run_id": { "type": "string" },
        "output_dir": { "type": "string" },
        "status": { "enum": ["completed", "partial", "aborted", "in_progress"] },
        "detected_at": { "type": "string", "format": "date-time" }
      }
    },

    "detection": {
      "type": "object",
      "required": ["run_sentinel_present", "postmortem_present", "state_file_present", "hard_abort"],
      "additionalProperties": false,
      "properties": {
        "run_sentinel_present": { "type": "boolean", "description": "prime-result*.json found (FR-1)" },
        "postmortem_present": { "type": "boolean", "description": "prime-postmortem-report.json found (FR-2)" },
        "state_file_present": { "type": "boolean", "description": ".prime_contractor_state.json found (FR-13)" },
        "hard_abort": { "type": "boolean", "description": "state present + result absent + stale (FR-13)" },
        "features_attempted": { "type": ["integer", "null"], "description": "len(state.order) when hard_abort" },
        "aux_signals": {
          "type": ["object", "null"],
          "description": "Auxiliary error stores beyond the sentinels (HOWL prior art; FR-12 extension point)",
          "additionalProperties": false,
          "properties": {
            "failed_checkpoints": { "type": "integer", "minimum": 0 },
            "task_errors": { "type": "integer", "minimum": 0 },
            "pi_errors": { "type": "integer", "minimum": 0 },
            "sources": { "type": "array", "items": { "type": "string" } }
          }
        }
      }
    },

    "verdict": {
      "type": "object",
      "required": ["aggregate_verdict", "total_features", "succeeded", "failed"],
      "additionalProperties": false,
      "properties": {
        "aggregate_verdict": { "enum": ["PASS", "PARTIAL", "FAIL", "ABORTED", "UNKNOWN"] },
        "total_features": { "type": "integer", "minimum": 0 },
        "succeeded": { "type": "integer", "minimum": 0 },
        "failed": { "type": "integer", "minimum": 0 },
        "total_cost_usd": { "type": ["number", "null"], "minimum": 0 }
      }
    },

    "project_context": {
      "type": ["object", "null"],
      "additionalProperties": false,
      "properties": {
        "project_id": { "type": ["string", "null"] },
        "task_ids": { "type": "array", "items": { "type": "string" } },
        "requirement_refs": { "type": "array", "items": { "type": "string" } },
        "contextcore_state_path": { "type": ["string", "null"] },
        "source": { "enum": ["contextcore", "contextcore_yaml", "forward_manifest", "none"] }
      }
    },

    "failures": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["feature_id", "root_cause", "pipeline_stage", "severity", "recommended_action"],
        "additionalProperties": false,
        "properties": {
          "feature_id": { "type": "string" },
          "element_id": { "type": ["string", "null"] },
          "file": { "type": ["string", "null"] },
          "root_cause": {
            "enum": ["duplicate_import","unfilled_stub","scope_corruption","phantom_import",
                     "skeleton_missing","ollama_timeout","ollama_empty_response","ollama_circuit_breaker",
                     "repair_exhausted","splicer_mismatch","tier_escalation","ast_failure","size_regression",
                     "generation_error","dependency_blocked","repair_language_mismatch","cross_file_contract",
                     "type_class_mismatch","unknown"]
          },
          "pipeline_stage": {
            "enum": ["skeleton","classification","template","ollama_generation","repair","splicer",
                     "fallback","integration","cross_feature_contract","typecheck","unknown"]
          },
          "severity": { "enum": ["critical", "high", "medium", "low"] },
          "actionable": {
            "type": "boolean",
            "description": "Skip-filter (Coyote prior art): false for environmental/transient causes with no operator code/spec fix. Non-actionable failures never become the headline recommendation when an actionable one exists."
          },
          "recommended_action": {
            "type": "object",
            "required": ["action", "re_run_strategy"],
            "additionalProperties": false,
            "properties": {
              "action": { "type": "string", "description": "Operator-facing sentence (FR-10)" },
              "re_run_strategy": {
                "enum": ["retry_as_is","reduce_scope","split_element_or_increase_tier","re_run_prior_stage",
                         "from_latest_producer","unblock_dependency","regenerate_clean","fix_repair_routing",
                         "fix_deterministic_generator","align_types","manual_review"]
              },
              "rationale": { "type": ["string", "null"] },
              "source_classification": { "enum": ["postmortem_report", "fallback_classifier"], "description": "FR-8" }
            }
          },
          "deterministic": { "type": "boolean", "description": "failed feature had $0 generation cost — a plain re-run is idempotent (FR-14)" },
          "persistent": { "type": "boolean", "description": "failed in >=2 runs (FR-9)" },
          "occurrences": { "type": "integer", "minimum": 1, "description": "runs failed in this batch (FR-9)" },
          "force_regenerated": { "type": "boolean" }
        }
      }
    },

    "cross_feature_patterns": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["pattern_type", "description", "affected_features", "severity"],
        "additionalProperties": false,
        "properties": {
          "pattern_type": { "type": "string" },
          "description": { "type": "string" },
          "affected_features": { "type": "array", "items": { "type": "string" } },
          "severity": { "enum": ["critical", "high", "medium", "low"] }
        }
      }
    },

    "batch": {
      "type": ["object", "null"],
      "additionalProperties": false,
      "properties": {
        "batch_id": { "type": "string" },
        "runs_in_batch": { "type": "integer", "minimum": 1 },
        "persistent_failure_count": { "type": "integer", "minimum": 0 },
        "velocity_trend": { "enum": ["accelerating", "stable", "decelerating", "unknown"] }
      }
    },

    "events_emitted": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "priority"],
        "additionalProperties": false,
        "properties": {
          "type": { "enum": ["RUN_DETECTED", "POSTMORTEM_AVAILABLE", "RUN_FAILED"] },
          "priority": { "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"] },
          "at": { "type": "string", "format": "date-time" }
        }
      }
    },

    "cursor": {
      "type": "object",
      "required": ["cursor_path", "previously_processed"],
      "additionalProperties": false,
      "properties": {
        "cursor_path": { "type": "string" },
        "previously_processed": { "type": "boolean", "description": "true => idempotent no-op re-run (FR-3)" },
        "run_checksum": { "type": ["string", "null"] }
      }
    },

    "summary": {
      "type": "object",
      "required": ["headline"],
      "additionalProperties": false,
      "properties": {
        "headline": { "type": "string" },
        "top_recommendation": { "type": ["string", "null"] }
      }
    }
  }
}
```

### Notes on field provenance
- `generated_at` is stamped by the SA process at write time (the SDK forbids `Date.now()`/
  `datetime.now()` in some contexts — here it's a normal runtime script, so `datetime.now(
  timezone.utc).isoformat()` is fine).
- `failures[].root_cause` / `pipeline_stage` are **read from** `prime-postmortem-report.json`
  (FR-8); `source_classification: "fallback_classifier"` marks the rare path where SA had
  to classify itself because the report was absent.
- `persistent` / `occurrences` / `force_regenerated` come from the batch ledger (FR-9).
- The `.md` sibling (`service-assistant-triage.md`) is a human render of this same data;
  the JSON is the source of truth.

---

## 3. Worked example

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-03T18:42:11Z",
  "assistant_version": "0.1.0",
  "run": {
    "run_id": "run-024",
    "output_dir": "pipeline-output/strtd8/run-024/plan-ingestion",
    "status": "partial",
    "detected_at": "2026-06-03T18:42:10Z"
  },
  "detection": {
    "run_sentinel_present": true,
    "postmortem_present": true,
    "state_file_present": true,
    "hard_abort": false,
    "features_attempted": null
  },
  "verdict": {
    "aggregate_verdict": "PARTIAL",
    "total_features": 8,
    "succeeded": 6,
    "failed": 2,
    "total_cost_usd": 1.83
  },
  "project_context": {
    "project_id": "strtd8",
    "task_ids": ["T-metric-model", "T-export-router"],
    "requirement_refs": ["FR-6"],
    "contextcore_state_path": "~/.contextcore/state/strtd8/",
    "source": "contextcore"
  },
  "failures": [
    {
      "feature_id": "export-router",
      "element_id": "ExportRouter.to_csv",
      "file": "src/app/web/export_router.py",
      "root_cause": "cross_file_contract",
      "pipeline_stage": "cross_feature_contract",
      "severity": "critical",
      "recommended_action": {
        "action": "Re-run from the feature that owns the export contract and re-sync its exported schema before regenerating this consumer.",
        "re_run_strategy": "from_latest_producer",
        "rationale": "Consumer references a field the producing feature renamed this run.",
        "source_classification": "postmortem_report"
      },
      "persistent": true,
      "occurrences": 2,
      "force_regenerated": false
    },
    {
      "feature_id": "metric-model",
      "element_id": "Metric.aggregate",
      "file": "src/app/models/metric.py",
      "root_cause": "tier_escalation",
      "pipeline_stage": "ollama_generation",
      "severity": "medium",
      "recommended_action": {
        "action": "Decompose Metric.aggregate into smaller elements or raise its tier allocation; the element exceeded the cheap-tier budget.",
        "re_run_strategy": "split_element_or_increase_tier",
        "rationale": "Element escalated past the local tier without resolving.",
        "source_classification": "postmortem_report"
      },
      "persistent": false,
      "occurrences": 1,
      "force_regenerated": false
    }
  ],
  "cross_feature_patterns": [
    {
      "pattern_type": "schema_divergence",
      "description": "Two features disagree on the Export DTO field set.",
      "affected_features": ["export-router", "report-builder"],
      "severity": "high"
    }
  ],
  "batch": {
    "batch_id": "a91f…",
    "runs_in_batch": 3,
    "persistent_failure_count": 1,
    "velocity_trend": "stable"
  },
  "events_emitted": [
    { "type": "POSTMORTEM_AVAILABLE", "priority": "HIGH", "at": "2026-06-03T18:42:11Z" },
    { "type": "RUN_FAILED", "priority": "HIGH", "at": "2026-06-03T18:42:11Z" }
  ],
  "cursor": {
    "cursor_path": "pipeline-output/strtd8/service-assistant-cursor.json",
    "previously_processed": false,
    "run_checksum": "sha256:7d2e…"
  },
  "summary": {
    "headline": "run-024 PARTIAL: 6/8 features passed ($1.83). 2 failures, 1 persistent across the batch.",
    "top_recommendation": "Fix the export contract first (critical, persistent): re-run from the producer and sync the DTO schema."
  }
}
```

---

## 4. `CAUSE_TO_OPERATIONAL_ACTION` — all 19 `RootCause` values (FR-10 / OQ-9)

> Distinct from `CAUSE_TO_SUGGESTION` (prompt hints for the next generation) and
> `repair/routing.py` (deterministic code transforms). This layer answers **"what should
> the operator do?"** Each entry is `{severity, re_run_strategy, action}`.

| RootCause | severity | re_run_strategy | action (operator-facing) |
|-----------|----------|-----------------|--------------------------|
| `skeleton_missing` | critical | `re_run_prior_stage` | Re-run plan-ingestion/skeleton generation — the scaffold for this feature was never produced. |
| `cross_file_contract` | critical | `from_latest_producer` | Re-run from the feature that owns the contract; re-sync its exported schema before the consumer. |
| `scope_corruption` | critical | `regenerate_clean` | Force a clean regeneration — generated scope leaked/corrupted across element boundaries. |
| `dependency_blocked` | high | `unblock_dependency` | Resolve the upstream feature first; this one cannot generate until its dependency passes. |
| `unfilled_stub` | high | `regenerate_clean` | Regenerate — the element was left as an unfilled stub; check the draft prompt budget. |
| `ast_failure` | high | `regenerate_clean` | Regenerate — output failed to parse; if it recurs, reduce element scope. |
| `splicer_mismatch` | high | `regenerate_clean` | Regenerate the element — splicer could not place the body; verify the target signature. |
| `repair_exhausted` | high | `fix_repair_routing` | Inspect repair routing — automatic repair ran out of attempts; the failure class may be misrouted. |
| `repair_language_mismatch` | high | `fix_repair_routing` | Fix repair routing — a repair step for the wrong language was applied; check `resolve_language`. |
| `type_class_mismatch` | high | `align_types` | Re-run with the consumer's types pinned — generated values don't match their consumers. |
| `ollama_circuit_breaker` | high | `retry_as_is` | Check Ollama availability/health, then re-run — the circuit breaker tripped on the local model. |
| `phantom_import` | medium | `regenerate_clean` | Regenerate — code imports a module that doesn't exist; constrain imports to real modules. |
| `duplicate_import` | medium | `regenerate_clean` | Regenerate — duplicate imports detected; dedupe on the next pass. |
| `tier_escalation` | medium | `split_element_or_increase_tier` | Decompose the element or raise its tier — it escalated past the cheap tier unresolved. |
| `size_regression` | medium | `reduce_scope` | Reduce element scope (fewer lines/generation) — output shrank vs. the expected size. |
| `ollama_timeout` | medium | `reduce_scope` | Reduce element scope and/or check Ollama latency, then re-run — generation timed out. |
| `ollama_empty_response` | medium | `retry_as_is` | Re-run — the local model returned empty; if persistent, fall back to a hosted tier. |
| `generation_error` | medium | `retry_as_is` | Re-run — a transient generation error occurred; escalate to manual review if it persists. |
| `unknown` | low | `manual_review` | Manual review — the failure did not match a known root cause. |

**Fallback rule:** any `RootCause` not present in the mapping (i.e. a future enum addition)
⇒ `{severity: "low", re_run_strategy: "manual_review", action: "Manual review — unmapped
root cause <value>; update CAUSE_TO_OPERATIONAL_ACTION."}`. The coverage unit test prevents
this path from shipping silently.

**Skip-filter (`actionable`) — Coyote prior art.** Each action also carries an
`actionable` flag. Three causes are **non-actionable** (environmental/transient, no operator
code/spec fix): `ollama_circuit_breaker`, `ollama_empty_response`, `generation_error`. They
are still recorded and recommended ("re-run / check health"), but the triage summary ranks
actionable failures above them, so an infra hiccup never becomes the headline when a real
code fix is available. This mirrors Coyote's skip/allow error evaluation without adopting its
heavyweight fix-pipeline.

---

## 5. EventBus payload contract (FR-6, supplementary)

Each emitted `Event.data` carries a **subset** of the triage artifact (events are
ephemeral; the artifact is authoritative). Minimum payload:

```python
{
  "run_id": str,
  "output_dir": str,
  "status": str,                 # run.status
  "aggregate_verdict": str,      # verdict.aggregate_verdict (None for RUN_DETECTED pre-postmortem)
  "failed": int,
  "triage_artifact_path": str,   # pointer to the authoritative JSON
  "project_id": str | None,
}
```

- `RUN_DETECTED` — emitted on first detection of `prime-result*.json` (verdict may be null).
- `POSTMORTEM_AVAILABLE` — emitted when `prime-postmortem-report.json` is first seen.
- `RUN_FAILED` — emitted when `aggregate_verdict ∈ {FAIL, ABORTED}` (or `status == aborted`).
- All three use `EventPriority.HIGH` so they enter the persisted in-memory history.

---

*Schema v1.0 — pins the FR-7 bridge contract and the FR-10 mapping. Resolves OQ-9 (map all
19 causes, fail loudly on gaps). Pairs with requirements v0.2 and plan v0.2.*
