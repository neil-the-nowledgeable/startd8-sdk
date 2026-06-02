# Polish-Stage Observability Input — Implementation Plan

**Date:** 2026-06-02
**Status:** Plan v0.1 (paired with `OBSERVABILITY_POLISH_INPUT_REQUIREMENTS.md` v0.3)
**Scope:** startd8 only — `src/startd8/observability/artifact_generator.py` (+ a small config seam).
The gather flow, manifest schema, and input validation are **delegated** (reqs §2.2) and out of scope.
**Branch:** `feat/obs-cat5-impl` (or a fresh branch off it).

---

## Guiding principle

The reflective passes shrank this to **one idea**: the ContextCore manifest already carries the
delivery inputs; the generator just doesn't read four of them and fabricates placeholders. So this is
**consumption wiring + graceful fallback**, not new machinery — expect a small, mostly-additive diff
with a byte-identity golden for the absent-everything path.

```
Phase 0  Confirm field shapes (prerequisite — don't guess the manifest)
Phase 1  Read the 4 fields into BusinessContext / per-target hints      FR-CONS-1
Phase 2  Wire notification_policy (alertChannels + owners)              FR-CONS-1
Phase 3  Wire service_monitor + loki_rule (metricsInterval + targets)   FR-CONS-1
Phase 4  Wire runbook escalation (owners)                               FR-CONS-1
Phase 5  Runbook base + datasource (env/config defaults)                FR-CONS-2/3  [gated on OQ-8]
Phase 6  Backward-compat + parameter-classification fallback + golden   FR-CONS-4
```

---

## Phase 0 — Confirm field shapes (prerequisite)

**Don't guess the manifest.** Before wiring, confirm the exact shape of each field against a **real
`.contextcore.yaml`** from a pipeline run (or ContextCore's manifest schema):

| Field | Assumed shape (verify) |
|-------|------------------------|
| `spec.observability.alertChannels` | list of channel identifiers (e.g. `["#alerts", "#oncall"]`) — or `{severity: channel}`? |
| `metadata.owners` | list of `{name, email?, team?}` or a map? (REQ-CDP-INT-002 validates plausibility) |
| `spec.targets[]` | list of `{name, namespace}` |
| `spec.observability.metricsInterval` | duration string (`"30s"`) |

**Validation:** a sample manifest is checked into `tests/` fixtures with the confirmed shapes; the rest
of the plan codes against *that*, not an assumption. (This is the step that caught the `spec.delivery`
mistake — keep it.)

---

## Phase 1 — Read the 4 fields (FR-CONS-1)

| Step | Change | Files |
|------|--------|-------|
| 1.1 | Extend `load_business_context` (artifact_generator.py:~555) to read `spec.observability.alertChannels`, `metadata.owners`, `spec.observability.metricsInterval` into `BusinessContext` (new optional fields, default `None`/`[]`) | artifact_generator.py |
| 1.2 | Map `spec.targets[]` (`name`,`namespace`) onto the per-service hints used by service_monitor/loki/dashboard (today derived from `service_id`) | artifact_generator.py (ServiceHints / extract_service_hints) |

**Validation:** unit test — a fixture manifest with all 4 fields populates the context/hints; an empty
manifest leaves them at defaults.

---

## Phase 2 — notification_policy (FR-CONS-1)

| Step | Change | Files |
|------|--------|-------|
| 2.1 | In `generate_notification_policy` (~:1640–1680), route by `alertChannels` (severity-mapped via existing `_CRITICALITY_TO_SEVERITY`) and set owner from `metadata.owners`; **remove the `REPLACE_WITH_WEBHOOK_URL` fabrication** when channels are present | artifact_generator.py:1671 |

**Validation:** fixture with `alertChannels` + `owners` → policy routes to those channels/owner, no
`REPLACE_WITH_WEBHOOK_URL`; fixture without → required-param-unresolved path (Phase 6), not a fake URL.

---

## Phase 3 — service_monitor + loki_rule (FR-CONS-1)

| Step | Change | Files |
|------|--------|-------|
| 3.1 | `generate_service_monitor` (~:1388): scrape interval from `metricsInterval` (default `"30s"`); selector/namespace from `spec.targets[]` (default `app={service_id}`) | artifact_generator.py:1606,1618 |
| 3.2 | `generate_loki_rule` (~:1479): log selector from `spec.targets[].name` | artifact_generator.py:1699 |

**Validation:** fixture with `metricsInterval="15s"` + a target namespace → ServiceMonitor reflects
both; absent → today's defaults (golden-stable).

---

## Phase 4 — runbook escalation (FR-CONS-1)

| Step | Change | Files |
|------|--------|-------|
| 4.1 | `generate_runbook` (~:1525): escalation contacts from `metadata.owners` (replaces the `TODO`/owner placeholder at :1782) | artifact_generator.py:1782 |

**Validation:** fixture with owners → runbook escalation lists them; absent → "owner not set" note (not
a fabricated contact).

---

## Phase 5 — runbook base + datasource (FR-CONS-2/3) — gated on OQ-8

| Step | Change | Files |
|------|--------|-------|
| 5.1 | Runbook URL base: read `spec.observability.runbookBase` **if ContextCore adds it** (OQ-8), else env `OBS_RUNBOOK_BASE`, else **omit** the `runbook_url` annotation rather than emit `runbooks.example.com` | artifact_generator.py:820 |
| 5.2 | Datasource name: env/config default (`OBS_PROM_DATASOURCE`, default `"prometheus"`) instead of the literal | artifact_generator.py:1007 |

**Decision gate:** resolve **OQ-8** (does ContextCore add `runbookBase`/`datasource` fields, or are
they env/config?) before coding 5.1/5.2. Recommendation: env/config now; propose ContextCore fields
only if they become per-project intent.

**Validation:** with no base configured, no dead `runbooks.example.com` URL appears; datasource
override flows into dashboard targets.

---

## Phase 6 — backward-compat + parameter classification (FR-CONS-4)

| Step | Change | Files |
|------|--------|-------|
| 6.1 | Absent field → today's default; **required** delivery params missing (e.g. `alertChannels`) surface as *unresolved* (Gate-1 visible per REQ-CDP-INT-007), **not** a fabricated placeholder; optional ones default silently | artifact_generator.py + the existing unresolved-param/coverage path |
| 6.2 | Golden test: an onboarding-metadata/manifest with **no** delivery fields produces artifacts **byte-identical to today** EXCEPT placeholders are no longer fabricated (the policy/runbook omit rather than stub) | tests/ |

**Validation:** the golden proves no silent regression; the required-missing case is observable, not
hidden.

---

## Traceability (requirement → phase)

| FR | Phase |
|----|-------|
| FR-CONS-1 (consume alertChannels/owners/targets/metricsInterval) | 1, 2, 3, 4 |
| FR-CONS-2 (runbook base) | 5.1 (gated OQ-8) |
| FR-CONS-3 (datasource) | 5.2 |
| FR-CONS-4 (backward-compat + param classification) | 6 |
| Delegated (gather/schema/validation/$50-$100) | — (cap-dev-pipe / ContextCore / separate self-fix) |

## Before-code checklist

- [ ] Phase 0 done: real `.contextcore.yaml` field shapes confirmed + fixture checked in (no guessing).
- [ ] OQ-8 decided before Phase 5.
- [ ] Every changed generator path keeps an absent-field default (golden byte-identity, Phase 6.2).
- [ ] No new manifest field authored by startd8 (schema is ContextCore's).
- [ ] `REPLACE_WITH_WEBHOOK_URL` and `runbooks.example.com` no longer appear in any generated artifact.

---

*Plan v0.1 — paired with requirements v0.3. Net: a small consumption-wiring change to
`artifact_generator.py` (read 4 existing manifest fields + 2 config defaults), guarded by a byte-identity
golden. Phase 0 (confirm shapes) and the OQ-8 decision are the two prerequisites; everything else is
additive and unblocked.*
