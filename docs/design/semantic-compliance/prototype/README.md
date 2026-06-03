# Semantic Compliance Reviewer — Prototype (dev-footprint sketch)

**Status:** Design prototype — **NOT shipped code.** These files live under `docs/design/` precisely
so they are *not* imported by the SDK or collected by pytest. They exist to make the dev footprint
concrete before implementation. Pairs with REQUIREMENTS v0.3 / PLAN v0.3 / REPORT_SCHEMA v1.0.

## What's here

| Prototype file | Fidelity | Becomes (shipped) |
|----------------|----------|-------------------|
| `models.py` | **Full** dataclasses (the data contract) | `src/startd8/semantic_compliance/models.py` |
| `orchestrator.py` | Typed signatures, stub bodies | `…/orchestrator.py` |
| `reviewer.py` | Control flow sketched, 2 boundaries TODO | `…/reviewer.py` |
| `prompts/review_rubric.md` | **Full** prompt template | `…/prompts/review_rubric.py` |
| `examples/semantic-compliance-report.example.json` | **Full** worked false-PASS artifact | runtime output |

The report `.md` render and the Kaizen emission payload shapes are in `../SEMANTIC_COMPLIANCE_REPORT_SCHEMA.md` §4–§5.

## Intended package layout (shipped)

```
src/startd8/semantic_compliance/
├── __init__.py            # SemanticComplianceReviewer facade export
├── models.py              # data contract  ← prototype: models.py
├── orchestrator.py        # detect→load→triage→review→score→report→feedback  ← orchestrator.py
├── requirement_loader.py  # FR-1  (seed join + corroboration + multi-seed precedence)
├── triage.py              # FR-4/5/5a  (suspicion ranking + reserved PASS quota)
├── reviewer.py            # FR-6/15  ← reviewer.py  (tiered Haiku→Sonnet)
├── prompts/review_rubric.py  # FR-7  ← prompts/review_rubric.md
├── scoring.py             # FR-8  (deterministic score; inconclusive excluded)
├── report.py              # FR-9  (atomic write, round-trip-safe, raw-code stripped)
├── feedback.py            # FR-10/11  (structured Kaizen dict, cross-feature patterns, prune-on-pass)
└── cache.py               # S-R1-2  (verdict cache by run_id+feature_id+code_checksum)
```

## Invocation surface (decided design)

```bash
# Primary: the Service Assistant LAUNCHES it detached after a run (never blocks the post-run hook, S-R1-1).
#   SA writes status:pending → reconciles on SEMANTIC_REVIEW_COMPLETE.

# Standalone CLI (mirrors `startd8 assist scan`):
startd8 assist semantic-review <run-dir> [--max-escalations N] [--threshold 0.5] [--no-emit]

# Output (added to the run dir):
#   semantic-compliance-report.json   (authoritative, schema v1.0)
#   semantic-compliance-report.md     (human render)
#   + appends structured records to kaizen-suggestions.json
#   + the SA folds the report summary into service-assistant-triage.json
```

## Integration points (existing SDK code this touches)

| Existing surface | Interaction | Suggestion |
|------------------|-------------|------------|
| `micro_prime/models.py` `SemanticVerificationResult` (K-7) | **consume** as the verdict contract (first producer) | FR-6 |
| `MicroPrimeConfig.semantic_verification_{enabled,agent_spec,fn}` | the Phase-2 in-run home (reuse the config names) | FR-13 |
| `prime-context-seed*.json` / `seeds/models.py SeedTask` | read requirement text | FR-1 |
| `prime-postmortem-report.json` `FeaturePostMortem` | read triage signals | FR-4 |
| `prime_postmortem.CrossFeaturePattern` | reuse for patterns | R2-S6 |
| `generate_kaizen_suggestions` / `kaizen-suggestions.json` | emit structured dicts | FR-10 / R1-S2 |
| `model_catalog.Models.{SEMANTIC_VALIDATOR,CODE_REVIEW}` | tier selection | FR-15 |
| `costs/ CostTracker` / `CostSummary` | debit reviews, reconcile cost | R2-S2 |
| `events/types.py` | **edit**: add `SEMANTIC_REVIEW_COMPLETE` | R1-S3 |
| `service_assistant/` | **edit**: launch detached, fold, reconcile | FR-12 |
| `security.py` | redact before prompt assembly | F-R1-5 |

## Rough dev footprint

- **~11 new files** in `semantic_compliance/` (+ `SEMANTIC_COMPLIANCE_REPORT_SCHEMA.md` already drafted).
- **3 edits** to existing modules: `events/types.py` (1 enum member), `prime_postmortem.py`
  (1 `CAUSE_TO_SUGGESTION` entry), `service_assistant/` (detached launch + fold).
- **No new dependencies** — reuses providers, model_catalog, CostTracker, events, OTel bridge.
- **Cost posture:** zero LLM cost on a clean PASS-heavy run except the small reserved PASS sample;
  agent spend scales with suspect count, capped by `max_escalations` (FR-5). Cheap tier is Haiku;
  Sonnet only on fail/low-confidence.
- **Test surface:** the PLAN Verification checklist (10 items) — notably the run-018 replay, the
  false-PASS detection case (the example artifact here), idempotency cache, wrong-join guard,
  and the detached/`pending` race.

## Open before coding
- **OQ-9** review altitude (feature vs element) — prototype assumes `feature` granularity with a
  synthetic `feature:<id>` `element_fqn`.
- **OQ-10** whether structural cross-feature grouping moves to the post-mortem (would thin `feedback.py`).
- **Success-metric thresholds** (§2 X/Y) — need the labeled false-PASS replay set.
