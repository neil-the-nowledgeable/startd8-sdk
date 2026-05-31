# Known Limitation: notification_policy artifacts are per-service fragments

**Date:** 2026-05-31
**Status:** BY DESIGN — hardening DEFERRED (product decision, not a bug)
**Component:** `src/startd8/observability/artifact_generator.py` → `generate_notification_policy`
**Introduced by:** Closure 3B (commit `6d44f806`)

---

## Problem

`generate_notification_policy` runs once **per service** and emits a standalone
file at `notifications/{service}-notification-policy.yaml`. Each file is a
*complete* Alertmanager document with its own top-level `route` and `receivers`
keys:

```yaml
route:
  routes:
    - matchers: ["service = checkout-api"]
      receiver: checkout-api-critical
      ...
receivers:
  - name: checkout-api-critical
    webhook_configs: [{ url: REPLACE_WITH_WEBHOOK_URL }]
```

Alertmanager expects **one** config with a single top-level `route` and a single
`receivers` list. Concatenating the per-service fragments produces duplicate
top-level keys, so the generated files are **not directly deployable as a single
Alertmanager config** — an operator must merge them.

## Why it is this way (not a defect)

This mirrors the rest of the observability generator's **per-service artifact
model**: alerts, dashboards, and SLOs are all emitted per service. A per-service
notification fragment is internally consistent with that model and keeps each
service's routing self-describing and reviewable in isolation. The shortfall is
only at *assembly* time, and it is surfaced honestly (the file is a fragment,
not advertised as a turnkey Alertmanager config).

## Resolution path (if/when pursued)

Pick one, per demonstrated need:

1. **Merge step (recommended).** Add a project-level assembler that folds the
   per-service fragments into a single Alertmanager config — one `route` with a
   sub-route per service and a de-duplicated `receivers` list. Keeps the
   per-service authoring model; produces one deployable artifact.
2. **Project-level generator.** Replace the per-service generator with a single
   `generate_notification_policy(services, business, report)` that emits one
   config covering all services. Simpler output, loses per-service isolation.

Either way, also resolve the placeholder receiver (see
[OBSERVABILITY_LIMITATION_GENERATOR_SCAFFOLD_TODOS.md](OBSERVABILITY_LIMITATION_GENERATOR_SCAFFOLD_TODOS.md)).

## Evidence

| Item | Reference |
|------|-----------|
| Generator | `artifact_generator.py:1430` (`generate_notification_policy`) |
| Top-level `route` / `receivers` per file | `artifact_generator.py:1439`, `:1450` |
| Output path (one per service) | `notifications/{service}-notification-policy.yaml` |
| Contract-driven (only when declared) | `_EXTENDED_PER_SERVICE_GENERATORS` |
| Test (per-service routing) | `tests/unit/observability/test_artifact_generator.py::TestExtendedGenerators::test_notification_policy_routes_by_service` |
| Commit | `6d44f806` (Closure 3B) |
