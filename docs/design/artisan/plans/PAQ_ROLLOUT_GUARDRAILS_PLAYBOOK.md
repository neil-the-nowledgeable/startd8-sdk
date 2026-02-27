# Prime-Parity Rollout Guardrails Playbook

**Version:** 1.0.0  
**Created:** 2026-02-27  
**Scope:** REQ-PAQ-701

## Guardrail Flags

Use these runtime flags to control rollout without code edits:

1. `STARTD8_QUALITY_GATE_MODE` (`skip|warn|block`)  
   Controls DESIGN/TEST/REVIEW runtime quality-gate enforcement mode.
2. `STARTD8_FORCE_CANONICAL_DESIGN_ROUTE` (`true|false`)  
   Forces all DESIGN tasks through canonical route (`v1`).
3. `artisan.enforce_post_revision_rereview` (`true|false`)  
   HandlerConfig/ENV-backed toggle to require post-revision dual re-review.

Defaults are safe:
- quality gate mode defaults to `warn`
- canonical routing defaults to enabled behavior (`v1` unless modular opt-in)
- post-revision re-review defaults to `true`

## Canary Rollout Plan

1. **Stage A (Canary, 10% runs):**
   - `STARTD8_QUALITY_GATE_MODE=warn`
   - `STARTD8_FORCE_CANONICAL_DESIGN_ROUTE=true`
   - `artisan.enforce_post_revision_rereview=true`
2. **Stage B (Expanded, 50% runs):**
   - Keep canonical forced
   - Promote quality gate to `block` for DESIGN only cohorts where agreement rate is stable
3. **Stage C (General availability):**
   - Default policy remains `warn` unless SLO confirms `block` readiness
   - Allow modular route only for approved low-risk cohorts

## Rollback Triggers

Rollback immediately if any trigger is observed in two consecutive runs:

1. DESIGN agreement rate drops below `0.70`.
2. Design failure rate increases by `>20%` versus 7-day baseline.
3. Quality gate violations spike by `>2x` baseline.
4. Variant path (`v2`) underperforms canonical (`v1`) by `>0.15` agreement-rate delta.

## Rollback Actions

1. Set `STARTD8_FORCE_CANONICAL_DESIGN_ROUTE=true`.
2. Set `STARTD8_QUALITY_GATE_MODE=warn` (or `skip` during incident mitigation only).
3. Set `artisan.enforce_post_revision_rereview=true`.
4. Re-run parity benchmark and compare against last known good report.
