# Service Assistant — Implementation Plan

**Version:** 0.2 (post-reflection, paired with requirements v0.2)
**Date:** 2026-06-03
**Status:** Plan — pre-implementation
**Tracks:** `SERVICE_ASSISTANT_REQUIREMENTS.md` v0.2

---

## Design summary

The Service Assistant (SA) is a **thin, one-shot orchestration + synthesis layer** over
artifacts that already exist. It detects newly-produced run/post-mortem artifacts on the
filesystem, emits supplementary EventBus signals, and writes an authoritative triage
artifact that turns a failed run into a project-contextualized recommended action — without
executing it. Almost all heavy lifting (classification, batch progression) is *read*, not
*recomputed*.

```
cap-dev-pipe run (Prime Contractor)
   └─ run-prime-contractor.sh
        ├─ run_prime_workflow.py        → prime-result*.json [+ .prime_contractor_state.json]
        ├─ (post-run step, line 534)    → prime-postmortem-report.json, kaizen-*.json, batch-ledger.json
        └─ ▶ NEW: scripts/service-assistant.py  ← SA inserts here (after 534, before TS gate)
                 └─ startd8 assist scan <output-dir>
                       1. detect (FR-1,2,4,13) + cursor (FR-3)
                       2. load project context (FR-5)
                       3. read postmortem classification (FR-8) + batch (FR-9)
                       4. map operational action (FR-10)
                       5. emit events (FR-6) + write triage artifact (FR-7)
```

## Module layout

| New artifact | Purpose | Maps to |
|--------------|---------|---------|
| `src/startd8/service_assistant/__init__.py` | Package + `ServiceAssistant` facade | all |
| `src/startd8/service_assistant/detector.py` | Filesystem detection + hard-abort + cursor | FR-1,2,3,4,13 |
| `src/startd8/service_assistant/context.py` | Project-context enrichment (ContextCore + manifest) | FR-5 |
| `src/startd8/service_assistant/triage.py` | Read postmortem/batch, synthesize triage record | FR-7,8,9 |
| `src/startd8/service_assistant/operational_actions.py` | `CAUSE_TO_OPERATIONAL_ACTION` mapping | FR-10 |
| `src/startd8/service_assistant/notify.py` | EventBus emission | FR-6 |
| `src/startd8/cli_assist.py` → `app.add_typer(assist_app, "assist")` | CLI surface | FR-11 |
| `scripts/service-assistant.py` | Thin shim the `.sh` calls | FR-11 |
| `events/types.py` (+3 enum values) | `RUN_DETECTED`, `POSTMORTEM_AVAILABLE`, `RUN_FAILED` | FR-6 |

## Step-by-step

1. **EventBus types** — add 3 `EventType` enum values (`events/types.py:12–81`). Emit via
   `EventBus.emit(Event(..., priority=EventPriority.HIGH))` (`events/bus.py:125`). *(FR-6)*

2. **Detector + cursor** — scan `<output-dir>` for `prime-result*.json` /
   `prime-postmortem-report.json`; resolve `run_id` reusing the logic of
   `run_prime_postmortem.py:_resolve_run_id()`; read/write `service-assistant-cursor.json`
   (separate file, not `kaizen-index.json`). Hard-abort branch keys off
   `.prime_contractor_state.json` staleness. *(FR-1,2,3,4,13 / OQ-6,8)*

3. **Context enrichment** — load ContextCore state (`integrations/contextcore.py`,
   `~/.contextcore/state/<project>/`), `.contextcore.yaml`, forward manifest; attach
   `{project_id, task_ids, requirement_refs}`. *(FR-5)*

4. **Triage synthesis** — read `prime-postmortem-report.json` (`aggregate_verdict`,
   per-feature `RootCause`/`PipelineStage`, `cross_feature_patterns`); read batch
   progression (`batch-postmortem-report.json` / ledger) for persistent-failure flags.
   *Fallback:* invoke `RootCauseClassifier` only if report absent but result present.
   *(FR-8,9)*

5. **Operational action mapping** — new `CAUSE_TO_OPERATIONAL_ACTION: Dict[RootCause,
   {severity, action, re_run_strategy}]`; curated subset + generic "manual review"
   fallback for unmapped causes (OQ-9). *(FR-10)*

6. **Emit + write** — emit supplementary events; write `service-assistant-triage.json`
   and `.md` to the output dir as the authoritative bridge artifact. *(FR-6,7)*

7. **CLI + hook** — `assist scan <output-dir>` sub-app mirroring `manifest generate`;
   `scripts/service-assistant.py` shim; insert call in `run-prime-contractor.sh` after
   line 534, `set +e` guarded so it never blocks the pipeline. *(FR-11)*

8. **Extension point** — define an `IssueDetector` protocol the detector iterates over,
   with Prime-run detection as the first implementation; no other detectors in v1.
   *(FR-12 / NR-7)*

## Reuse map (don't reinvent)

| Need | Existing component |
|------|--------------------|
| Classification taxonomy | `RootCause`, `PipelineStage`, `RootCauseClassifier` (`prime_postmortem.py`) |
| Cross-run progression | `BatchLedger`, `BatchPostMortemReport` (`batch_postmortem.py`) |
| Pub/sub | `EventBus` (`events/bus.py`) |
| `run_id` resolution | `_resolve_run_id()` (`run_prime_postmortem.py`) |
| Project context | `ContextCoreTaskSource` (`integrations/contextcore.py`) |

## Risks / watch-items

- **Empty bridge** — events are no-ops without a subscriber; the triage *artifact* must be
  treated as the real deliverable (FR-7), not the events.
- **Cursor collision** across projects (OQ-8) — key carefully.
- **Operational-action drift** — `CAUSE_TO_OPERATIONAL_ACTION` must stay in sync with the
  `RootCause` enum; add a unit test asserting every enum value is mapped or explicitly
  falls back.
- **Out-of-repo `prime-post-run.py`** — depend only on its on-disk outputs (NR-4).

## Verification

- [ ] Every FR (1–13) has a step above; every step traces to an FR.
- [ ] Idempotency test: second `assist scan` on the same dir produces no new events/artifact churn.
- [ ] Hard-abort test: state file present, result absent → `RUN_FAILED status=aborted`.
- [ ] Coverage test: each `RootCause` value resolves to an operational action or fallback.
