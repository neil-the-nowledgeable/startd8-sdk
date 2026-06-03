# Semantic Compliance Report — Schema

**Version:** 1.0 (draft)
**Date:** 2026-06-03
**Status:** Interface contract — pre-implementation
**Tracks:** `SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md` v0.3 (FR-9), `…_PLAN.md` v0.3 (Step 7)

---

## Why this document exists

FR-9 makes `semantic-compliance-report.json` the durable output of the Semantic Compliance
Reviewer (SCR). It is consumed by the **Service Assistant** (FR-12, folded into its triage
artifact) and by a **future `STARTD8_SEMANTIC_GATE`** (FR-14), so the contract must be pinned —
the same way the SA's `TRIAGE_SCHEMA.md` v1.0 pinned its bridge artifact. This doc fixes:

1. the **controlled vocabularies**,
2. the **JSON Schema**,
3. a **worked example** (the false-PASS case the spec demands as its acceptance anchor),
4. the **`.md` render** shape,
5. the **Kaizen emission payload** the SCR writes into `kaizen-suggestions.json`.

CRP-triaged invariants baked into this schema:
- **Top-level `status: pending|complete`** so the detached SCR (S-R1-1) never lets the SA fold
  read a half-written report; written via atomic rename (R2-S3).
- **No raw code** — `generated_files` carries paths + bounded excerpts only (R4-S3).
- **Round-trip-safe** — verdict/confidence/issues live where `SemanticVerificationResult.from_json`
  reads them, so a reloaded report does not silently degrade to `inconclusive` (R1-S1).
- **`review_granularity` + `element_fqn`** are explicit so post-run (feature) and Phase-2 in-run
  (element) verdicts are comparable (R1-S4/S-R1-5/OQ-9).

---

## 1. Controlled vocabularies

### top-level `status`
`pending` · `complete`  — `pending` while a detached review is in flight; the SA fold treats a
`pending` report as not-yet-ready.

### `features[].verdict.verdict`
`pass` · `fail` · `inconclusive`  (the `SemanticVerificationResult` K-7 enum)

### `features[].verdict.inconclusive_reason`
`requirement_text_unavailable` · `requirement_join_ambiguous` · `language_unsupported` ·
`postmortem_unavailable` · `parse_failure` · `input_truncated` · `code_unavailable`

### `features[].selection.tier`
`cheap` (Haiku first pass) · `escalated` (Sonnet re-review)

### `features[].selection.reason`
`suspect` (above suspicion threshold) · `pass_sample` (reserved false-PASS quota) ·
`not_reviewed` (budget-skipped — `not_reviewed_reason` set)

### `features[].review_granularity`
`feature` · `element`

### `severity` (issues, patterns)
`critical` · `high` · `medium` · `low`

---

## 2. JSON Schema (`semantic-compliance-report.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://startd8/schemas/semantic-compliance-report-1.0.json",
  "title": "SemanticComplianceReport",
  "type": "object",
  "required": ["schema_version", "status", "generated_at", "scr_version", "run", "config", "summary", "features"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "1.0" },
    "status": { "enum": ["pending", "complete"] },
    "generated_at": { "type": "string", "format": "date-time" },
    "scr_version": { "type": "string" },

    "run": {
      "type": "object",
      "required": ["run_id", "output_dir"],
      "additionalProperties": false,
      "properties": {
        "run_id": { "type": "string" },
        "output_dir": { "type": "string" },
        "language": { "type": ["string", "null"], "description": "dominant run language; v1 expects python" }
      }
    },

    "config": {
      "type": "object",
      "description": "Resolved knobs, echoed for reproducibility + cost audit (FR-5/6/15).",
      "additionalProperties": false,
      "properties": {
        "suspicion_threshold": { "type": "number" },
        "max_escalations": { "type": "integer" },
        "reserved_pass_quota": { "type": "integer" },
        "model_cheap": { "type": "string" },
        "model_escalation": { "type": "string" },
        "theta": { "type": ["number", "null"], "description": "gate confidence default (FR-14)" },
        "max_input_tokens": { "type": "integer" },
        "max_output_tokens": { "type": "integer" },
        "deterministic": { "type": "boolean" }
      }
    },

    "summary": {
      "type": "object",
      "required": ["total_features", "reviewed", "pass", "fail", "inconclusive"],
      "additionalProperties": false,
      "properties": {
        "total_features": { "type": "integer", "minimum": 0 },
        "escalated": { "type": "integer", "minimum": 0 },
        "reviewed": { "type": "integer", "minimum": 0 },
        "not_reviewed": { "type": "integer", "minimum": 0 },
        "pass": { "type": "integer", "minimum": 0 },
        "fail": { "type": "integer", "minimum": 0 },
        "inconclusive": { "type": "integer", "minimum": 0 },
        "semantic_compliance_aggregate": { "type": ["number", "null"], "minimum": 0, "maximum": 1,
          "description": "mean over CONCLUSIVE features only (FR-8)" },
        "inconclusive_rate": { "type": "number", "minimum": 0, "maximum": 1 },
        "inconclusive_rate_exceeded": { "type": "boolean", "description": "true → SYSTEM_WARNING emitted (FR-14/R4-F1)" },
        "cost_usd": { "type": ["number", "null"], "minimum": 0, "description": "reconciles with CostSummary (FR-16/R2-S2)" }
      }
    },

    "features": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["feature_id", "language", "review_granularity", "selection", "verdict"],
        "additionalProperties": false,
        "properties": {
          "feature_id": { "type": "string" },
          "language": { "type": "string" },
          "review_granularity": { "enum": ["feature", "element"] },
          "element_fqn": { "type": "string", "description": "synthetic feature:<id> at feature granularity (R1-S4)" },

          "requirement": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "seed_task_id": { "type": ["string", "null"] },
              "text_excerpt": { "type": ["string", "null"], "description": "bounded; never full file" },
              "join_corroborated": { "type": "boolean", "description": "target_files∩generated_files overlap (S-R1-4)" }
            }
          },

          "selection": {
            "type": "object",
            "required": ["suspicion_score", "tier", "reason"],
            "additionalProperties": false,
            "properties": {
              "suspicion_score": { "type": "number" },
              "tier": { "enum": ["cheap", "escalated"] },
              "reason": { "enum": ["suspect", "pass_sample", "not_reviewed"] },
              "not_reviewed_reason": { "type": ["string", "null"] }
            }
          },

          "verdict": {
            "type": "object",
            "required": ["verdict", "confidence"],
            "additionalProperties": false,
            "properties": {
              "verdict": { "enum": ["pass", "fail", "inconclusive"] },
              "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
              "inconclusive_reason": {
                "enum": ["requirement_text_unavailable", "requirement_join_ambiguous",
                         "language_unsupported", "postmortem_unavailable", "parse_failure",
                         "input_truncated", "code_unavailable", null]
              }
            }
          },

          "issues": {
            "type": "array",
            "description": "requirement-intent findings only; deduped vs disk_compliance.semantic_issues (OQ-5)",
            "items": {
              "type": "object",
              "required": ["severity", "category", "description"],
              "additionalProperties": false,
              "properties": {
                "severity": { "enum": ["critical", "high", "medium", "low"] },
                "category": { "type": "string" },
                "description": { "type": "string" },
                "line_hint": { "type": ["integer", "null"] },
                "suggested_fix": { "type": ["string", "null"] }
              }
            }
          },

          "semantic_compliance_score": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "reviewed_files": { "type": "array", "items": { "type": "string" }, "description": "paths only (no raw code, R4-S3)" },
          "review_status": { "enum": ["complete", "pending", "error"] }
        }
      }
    },

    "cross_feature_patterns": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["pattern_type", "grouping_key", "affected_features", "severity"],
        "additionalProperties": false,
        "properties": {
          "pattern_type": { "type": "string" },
          "grouping_key": { "type": "string", "description": "category | contract_id | seed_task_id (R1-F5)" },
          "description": { "type": "string" },
          "affected_features": { "type": "array", "items": { "type": "string" } },
          "severity": { "enum": ["critical", "high", "medium", "low"] }
        }
      }
    },

    "kaizen_emitted": {
      "type": "array",
      "description": "structured suggestion records written to kaizen-suggestions.json (FR-10)",
      "items": { "type": "string", "description": "suggestion id / config_key reference" }
    }
  }
}
```

---

## 3. Worked example — the false-PASS case (the spec's acceptance anchor)

A run where the structural pipeline said **PASS** but the SCR catches a feature that does not do
what the requirement asked (`Metric.value` is computed by AI rather than provided — violating the
app's FR-6 "AI never writes Metric.value"). This is the capability's *unique* value (§1).

```json
{
  "schema_version": "1.0",
  "status": "complete",
  "generated_at": "2026-06-03T19:20:11Z",
  "scr_version": "0.1.0",
  "run": { "run_id": "run-027", "output_dir": "pipeline-output/strtd8/run-027/plan-ingestion", "language": "python" },
  "config": {
    "suspicion_threshold": 0.5, "max_escalations": 10, "reserved_pass_quota": 2,
    "model_cheap": "anthropic:claude-haiku-4-5", "model_escalation": "anthropic:claude-sonnet-4-6",
    "theta": 0.7, "max_input_tokens": 12000, "max_output_tokens": 1024, "deterministic": true
  },
  "summary": {
    "total_features": 8, "escalated": 3, "reviewed": 5, "not_reviewed": 0,
    "pass": 3, "fail": 1, "inconclusive": 1,
    "semantic_compliance_aggregate": 0.81, "inconclusive_rate": 0.2,
    "inconclusive_rate_exceeded": false, "cost_usd": 0.0143
  },
  "features": [
    {
      "feature_id": "metric-ingest",
      "language": "python",
      "review_granularity": "feature",
      "element_fqn": "feature:metric-ingest",
      "requirement": {
        "seed_task_id": "PI-004",
        "text_excerpt": "Ingest metric rows. The AI must NEVER compute Metric.value — it is provided by the caller …",
        "join_corroborated": true
      },
      "selection": { "suspicion_score": 0.35, "tier": "escalated", "reason": "pass_sample", "not_reviewed_reason": null },
      "verdict": { "verdict": "fail", "confidence": 0.86, "inconclusive_reason": null },
      "issues": [
        {
          "severity": "critical",
          "category": "requirement_violation",
          "description": "Generated code computes Metric.value = sum(samples)/len(samples); the requirement forbids the AI computing this field — it must be passed through from the caller.",
          "line_hint": 42,
          "suggested_fix": "Remove the aggregation; assign Metric.value from the input DTO field unchanged."
        }
      ],
      "semantic_compliance_score": 0.10,
      "reviewed_files": ["src/app/services/metric_ingest.py"],
      "review_status": "complete"
    },
    {
      "feature_id": "export-router",
      "language": "python",
      "review_granularity": "feature",
      "element_fqn": "feature:export-router",
      "requirement": { "seed_task_id": "PI-002", "text_excerpt": "Expose CSV + JSON export …", "join_corroborated": true },
      "selection": { "suspicion_score": 0.72, "tier": "cheap", "reason": "suspect", "not_reviewed_reason": null },
      "verdict": { "verdict": "inconclusive", "confidence": 0.4, "inconclusive_reason": "requirement_join_ambiguous" },
      "issues": [],
      "semantic_compliance_score": null,
      "reviewed_files": ["src/app/web/export_router.py"],
      "review_status": "complete"
    }
  ],
  "cross_feature_patterns": [
    {
      "pattern_type": "requirement_authority_violation",
      "grouping_key": "category:requirement_violation",
      "description": "2 features compute fields the requirements mark as caller-provided (AI-authored authority fields).",
      "affected_features": ["metric-ingest", "rollup-job"],
      "severity": "high"
    }
  ],
  "kaizen_emitted": ["requirement_semantic_gap:metric-ingest", "requirement_semantic_gap:rollup-job"]
}
```

The headline: a **structurally-PASS run** still produced a **critical requirement violation** the
deterministic checks could not see — exactly the gap the SCR exists to close.

---

## 4. `.md` render shape (`semantic-compliance-report.md`)

Human render of the same data (source of truth is the JSON):

```markdown
# Semantic Compliance Report — run-027

**Status:** complete · **Aggregate compliance:** 0.81 · **Cost:** $0.0143
Reviewed 5/8 features (3 escalated). pass 3 · fail 1 · inconclusive 1.

> ⚠️ Critical: `metric-ingest` (PI-004) FAILS its requirement — AI computes `Metric.value`,
> which the spec forbids. Confidence 0.86.

## Failed / low-compliance features
| Feature | Verdict | Conf | Score | Requirement violation |
|---------|---------|------|-------|-----------------------|
| `metric-ingest` | fail | 0.86 | 0.10 | Computes Metric.value (forbidden); pass it through from the DTO. |

## Inconclusive
| Feature | Reason |
|---------|--------|
| `export-router` | requirement_join_ambiguous |

## Cross-feature patterns
- **requirement_authority_violation** (high): 2 features compute caller-provided fields — `metric-ingest`, `rollup-job`.

_Advisory — fed to Kaizen for the next run; no run blocked._
```

---

## 5. Kaizen emission payload (into `kaizen-suggestions.json`)

FR-10: the SCR emits the **structured suggestion-dict** the existing loop consumes — not bare
strings. One record per confirmed (confidence-gated) semantic gap:

```json
{
  "pattern_type": "requirement_semantic_gap",
  "suggested_action": "Do not compute Metric.value in metric-ingest; assign it unchanged from the input DTO (requirement PI-004 forbids AI-authored value).",
  "config_key": "prompt_hints",
  "phase": "draft",
  "confidence": 0.86,
  "auto_applicable": false,
  "source": "semantic_compliance_reviewer",
  "feature_id": "metric-ingest",
  "advisory": true
}
```

`advisory: true` + `auto_applicable: false` instruct the next generation to **validate the hint
syntactically** rather than inject it blindly (R3-F2); the record is **pruned/tombstoned** once the
feature earns a `pass` in a later run (R3-S2).

---

*Schema v1.0 — pins the FR-9 report contract + the FR-10 Kaizen payload. Pairs with requirements
v0.3 / plan v0.3 and mirrors the Service Assistant `TRIAGE_SCHEMA.md` v1.0.*
