# SDK Handoff — First-Class WorkItem `task.*` Carry (REQ-CCL-109 continuation)

**From:** ContextCore (work-item / issue tracking feature)
**To:** startd8-sdk team
**Status:** ContextCore side implemented (Inc-0…Inc-8) on branch `feat/wit-inc0-semconv-contract`; **SDK side DONE 2026-07-25** (branch `feat/workitem-task-carry-sdk-side`) — see §SDK Response below.
**Paired docs (ContextCore repo):** `docs/design/CONTEXTCORE_WORK_ITEM_TRACKING_{REQUIREMENTS,PLAN}.md`, `docs/design/weaver/WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md` (REQ-CCL-109 / ContextCore #58).

---

## SDK Response (2026-07-25)

Handoff **verified against the real branch before acting** (a handoff is a belief artifact —
grounded per the cross-repo-grounding rule). The producer branch `feat/wit-inc0-semconv-contract`
is real and substantial (4,249 insertions, full `src/contextcore/workitems/` package + Inc-1…Inc-8
tests). Grounding corrected two prose details and caught **one real drift**:

- **Builder name:** the SDK builder is `_build_state_file` (not `_build_state_dict`); public entry
  `emit_task_tracking_artifacts`. `_SCHEMA_VERSION == 2` at `task_tracking_emitter.py:44`; reader keys
  confirmed at `integrations/contextcore.py:1052/948/1041`. All accurate.
- **DRIFT FOUND (this is why T3 exists):** ContextCore's hand-authored stand-in
  `tests/fixtures/workitem_sdk_golden.json` does **not** match the real emitter — it carries
  `task.assignee`, `task.percent_complete`, `agent.id`, `status_description`, `created_at`, and a
  `task.id` inside the `task.created` event, **none** of which `_build_state_file` emits. The FR-13
  parity job was comparing against a fiction. **T3 fixes this** — see below.

**SDK deliverables (done, branch `feat/workitem-task-carry-sdk-side`):**

- **T3 (decided → option (a)):** exposed a stable, deterministic
  **`startd8.workflows.builtin.task_tracking_emitter.emit_canonical_fixture()`** — routes through the
  real `_build_state_file` (no hand-authored dict), byte-stable. **ContextCore: import this in
  `scripts/generate_workitem_sdk_fixture.py`** (replace the `TODO(Inc-0 parity job)` stand-in) so the
  golden fixture is the real emitter shape. Optional-dependency safe (importorskip on the CC side).
- **T1:** reader-tolerance tests — `ContextCoreTaskSource.get_task_by_id` / `get_pending_tasks` /
  status-filter are byte-unaffected by an additive `attributes["contextcore.workitem"]` overlay +
  `task.resolution` / `task.external_ref.*` / `task.relation.*` keys (`test_workitem_task_carry.py`).
- **T2:** guard tests — `_SCHEMA_VERSION` pinned at 2, terminal-status mapping unchanged; emitter does
  not emit the `contextcore.workitem` overlay (that stays CC-owned).
- **T4:** a `task.*` semconv parity guard — `emit_canonical_fixture()`'s `task.status`/`task.type` MUST
  be members of ContextCore's `TaskStatus`/`TaskType` enums (skips when CC absent; **verified passing
  with CC importable**). Mirrors the existing `tests/unit/observability/test_vocabulary_parity_contextcore.py`,
  which is the SDK's established cross-repo parity pattern — extend that for the full registry parity in CI.
- **T5:** noted — no SDK emitter code changed, so per FR-9 **no SDK release is required**; this PR is
  verification + the `emit_canonical_fixture` helper only.

**Result:** 8 tests (7 + 1 CC-optional), 29 passed across emitter suites, ruff clean on new code.
**ContextCore action remaining:** wire `emit_canonical_fixture()` into the generator and regenerate the
golden fixture (it will change — the stand-in was drifted); then the Inc-0 parity job is comparing real
shapes. (Pre-existing unused-import lint at `task_tracking_emitter.py:26/37` left untouched — not this
change's scope.)

---

## TL;DR

ContextCore added first-class WorkItems as an **additive overlay** on the `task.*` span state files the SDK already emits. **No SDK emitter change is required** — the carry is designed to be consume-only (ContextCore never mutates SDK spans; NR-6). Your part is **verification + parity**, not new features:

1. Confirm the SDK reader tolerates the new additive attributes (it should — it reads by key).
2. Pull the updated semconv registry and run Weaver/parity in the SDK release gate.
3. Bless the canonical emitter fixture so ContextCore's cross-repo parity job compares against *real* emitter output (today it uses a hand-authored stand-in).
4. Hold `_SCHEMA_VERSION = 2` — do **not** bump it.

If nothing in the emitter changes, there is **no SDK release required** (FR-9: "SDK release only if carry code changes").

---

## What changed on the ContextCore side (context)

New, additive `task.*` semconv (all `requirement_level: opt_in`, `stability: experimental`, 0.1.0):

- Attributes: `task.resolution`, `task.external_ref.{system,id,url}`, `task.relation.{type,target}`.
- Events (`event.task.*`): `reopened`, `promoted`, `sync.conflict`, `sync.error`, `comment_tombstoned`, `authorization_failed`.
- A mutable overlay nested under **`attributes["contextcore.workitem"]`** (never a top-level `SpanState` field, never a `schema_version` bump).

Canonical Python enums added to `contextcore.contracts.types`: `TaskResolution`, `RelationType`, `ExternalSystem`; new `EventType` members in `contextcore.contracts.metrics`.

The invariant that protects you: **`SCHEMA_VERSION` stays 2** and the overlay lives *inside* `attributes`, so a file ContextCore has overlaid is still a valid SpanState v2 the SDK reads unchanged.

---

## SDK tasks

### T1 — Reader tolerance test (should already pass; make it explicit)
The SDK reader keys off specific fields — e.g. `src/startd8/integrations/contextcore.py:1052`
(`data.get("attributes", {}).get("task.status", "unknown")`) and `get_task_by_id`
(`:948`). Additive attributes (`contextcore.workitem`, `task.resolution`,
`task.external_ref.*`, `task.relation.*`) are ignored by key-based reads.

- [ ] Add a unit test: load a state file that includes `attributes["contextcore.workitem"]`
      + the new `task.*` keys, and assert `get_task_by_id` / status-filter
      (`_matches_status_filter`, `:1041`) behave exactly as before. Proves additive tolerance.

### T2 — Emitter stays put (no change; assert it)
`src/startd8/workflows/builtin/task_tracking_emitter.py` writes `_SCHEMA_VERSION = 2`
(`:44`) and `task.type`/`task.status` (`:142-143`).

- [ ] Do **not** bump `_SCHEMA_VERSION` (bumping to 3 breaks the ContextCore reader — R4-F6).
- [ ] Do **not** start emitting `contextcore.workitem` — that overlay is ContextCore-owned.
- [ ] Confirm no test asserts an exact/closed attribute allowlist that would fail when a
      consumer adds keys.

### T3 — Bless the canonical emitter fixture (the one real deliverable)
ContextCore's cross-repo parity job (Inc-0, R1-S10) needs a **golden fixture generated
from the real SDK emitter**. Today ContextCore ships a hand-authored stand-in at
`tests/fixtures/workitem_sdk_golden.json` with `scripts/generate_workitem_sdk_fixture.py`
(there is a `TODO(Inc-0 parity job)` there). Pick one:

- **(a) Preferred:** expose a stable, importable "emit one canonical task span → dict"
  helper in the SDK (e.g. `task_tracking_emitter.emit_canonical_fixture()`), so
  ContextCore's generator imports the *real* emitter. Name it, keep it stable.
- **(b) Alternative:** commit a canonical fixture in the SDK repo (e.g.
  `tests/fixtures/contextcore_task_span_golden.json`) that the SDK's own tests keep in
  sync with the emitter; ContextCore mirrors it and diffs.

- [ ] Decide (a) or (b) and tell ContextCore the import path / fixture path so the parity
      job can be wired (it is currently stubbed).

### T4 — Weaver parity in the SDK release gate (FR-12)
Once ContextCore merges the semconv registry (Inc-0), the SDK's `task.*` emission must
still validate against it.

- [ ] Pull the updated `semconv/registry/task.yaml` + `task_events.yaml` (or the published
      registry) and run `weaver`/parity as part of the SDK's checks. Additive-only ⇒ green
      with no emitter change.

### T5 — Respect the release order (FR-9)
`semconv merge → ContextCore release → Weaver green → SDK release (only if carry code changes)`.
If parity fails post-merge: block the ContextCore consumer release; the semconv revert **or**
the fixture forward-fix ships as a **paired PR** (never a one-sided registry change).

---

## Acceptance (SDK side)

- [ ] T1 tolerance test green.
- [ ] `_SCHEMA_VERSION` unchanged (== 2); emitter unchanged.
- [ ] Canonical fixture path/helper decided and communicated to ContextCore.
- [ ] Weaver/parity green against the new registry.
- [ ] No SDK release unless emitter carry code actually changes.

## Non-goals (SDK does NOT do these)
- Emitting or reading the `contextcore.workitem` overlay (ContextCore-owned).
- Comment/relation/sync logic (ContextCore-owned; comments never cross the boundary — R3-S9).
- Bumping the schema version.

---

## Pointers
- ContextCore emitter-shape mirror + generator: `scripts/generate_workitem_sdk_fixture.py`,
  `tests/fixtures/workitem_sdk_golden.json`.
- ContextCore consumers manifest (what every new field/event feeds):
  `docs/design/workitem_consumers_manifest.yaml`.
- Semconv contract: `semconv/registry/task.yaml`, `semconv/events/task_events.yaml`.
- Cross-repo alignment: `docs/design/weaver/WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md`.
