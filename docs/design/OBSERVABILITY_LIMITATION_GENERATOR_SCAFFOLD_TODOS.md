# Known Limitation: extended generators emit scaffolds with placeholder values

**Date:** 2026-05-31
**Status:** INTENTIONAL SCAFFOLDING — enrichment DEFERRED (not defects)
**Component:** `src/startd8/observability/artifact_generator.py` (Closure 3B generators)
**Introduced by:** Closure 3B (commit `6d44f806`)

---

## Problem

The five native extended generators (`service_monitor`, `notification_policy`,
`loki_rule`, `runbook`, `capability_index`) produce **deployable scaffolds**, not
turnkey artifacts. Several fields carry placeholder / assumed values that an
operator must confirm or replace before production use:

| Artifact | Placeholder / assumption | Location |
|----------|--------------------------|----------|
| `notification_policy` | receiver target `url: REPLACE_WITH_WEBHOOK_URL` | `artifact_generator.py:1454` |
| `service_monitor` | scrape endpoint assumed `port: metrics`, `path: /metrics` | `artifact_generator.py:1403` |
| `loki_rule` | generic error filter `\|= "error"` (not service-specific) | `artifact_generator.py:1560` |
| `runbook` | `Owner: TODO: set manifest.spec.business.owner` when owner absent | `artifact_generator.py:1565` |

## Why this is intentional (not a defect)

These markers are deliberate and follow the generator's **TODO-when-absent
policy**: when the manifest does not supply a value, emit a clearly-marked
placeholder rather than silently inventing a wrong one or omitting the field.
Every placeholder is greppable (`REPLACE_WITH_`, `TODO:`) so a deploy step can
detect un-filled scaffolds. This is the same posture used for domain-metric
alert thresholds (Gap 1) and is preferable to fabricating plausible-but-wrong
config that fails silently in production.

## Resolution path (if/when pursued)

Source each value from richer manifest fields **when available**, keeping the
TODO fallback when absent:

- **notification_policy receiver** ← `manifest.spec.observability.notifications`
  (webhook/email/slack target) if declared.
- **service_monitor port/path** ← `manifest.spec.observability.scrape`
  (`port`, `path`) or instrumentation hints, if present.
- **loki_rule filter** ← a service/log-format-aware error pattern derived from
  `instrumentation_hints` (e.g. structured-log `level=error`) instead of the
  generic substring.
- **runbook owner** ← already wired to `manifest.spec.business.owner`; the TODO
  only appears when that field is unset.

None of these block deployment today; they raise the quality of the generated
artifact when the manifest is richer.

## Evidence

| Item | Reference |
|------|-----------|
| Generators | `generate_service_monitor`, `generate_notification_policy`, `generate_loki_rule`, `generate_runbook` |
| Placeholder markers | see table above (all greppable: `REPLACE_WITH_`, `TODO:`) |
| TODO-when-absent precedent | domain-metric alert stubs, `_domain_alert_todo_block` (Gap 1) |
| Tests (shape/round-trip) | `tests/unit/observability/test_artifact_generator.py::TestExtendedGenerators` |
| Commit | `6d44f806` (Closure 3B) |
