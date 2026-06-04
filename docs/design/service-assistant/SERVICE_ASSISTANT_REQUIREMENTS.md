# Service Assistant Requirements

**Version:** 0.3 (Field-driven — run-028: cost-aware remediation, FR-14)
**Date:** 2026-06-03
**Status:** Draft
**Owner:** neil-the-nowledgable

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass mapped each requirement to real seams in the SDK and revealed 5 material
> corrections, resolving all 7 open questions.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| "Notify the SDK" implies an SDK-side consumer waiting on events | `EventBus` is **fire-and-forget with no resident subscriber**; events only persist in an in-memory history (HIGH/CRITICAL) unless `enable_persistence()` is called (`events/bus.py:125–182`). The SDK is a *library*, not a service. | **FR-6 reframed.** The *primary* bridge is the on-disk triage artifact (FR-7), which a human/agent reads. EventBus emission is *supplementary* (for optional in-process subscribers + persisted history). The requirement no longer assumes a listener. |
| Service Assistant runs `RootCauseClassifier` itself (FR-8) | The post-mortem path **already** runs `RootCauseClassifier` and writes per-feature root causes + `cross_feature_patterns` into `prime-postmortem-report.json` (`prime_postmortem.py`). | **FR-8 narrowed (overspecified).** SA *consumes* the already-classified root causes from the report — it does not re-classify. Removes double work; SA is thinner. |
| `CAUSE_TO_SUGGESTION` is the source for "recommended action" (FR-10) | `CAUSE_TO_SUGGESTION` entries are `{phase, hint}` **prompt hints for the next LLM generation**, not operator-facing. `repair/routing.py` is deterministic *code-transform* steps, not strategic recommendations. Neither answers "what should the operator do." | **FR-10 expanded (underspecified).** A **new** `CAUSE_TO_OPERATIONAL_ACTION` mapping (`{severity, action, re_run_strategy}`) is required to turn a classified cause into an operator-facing recommendation. |
| Detection keys solely off `prime-result.json` (FR-1) | `prime-result.json` is **only written on normal completion**. `.prime_contractor_state.json` is written *before* the generation loop and **survives hard aborts** (OOM, timeout, Ctrl-C). | **New FR-13.** Hard-abort detection: state-file present + result absent + staleness ⇒ "run attempted, crashed." Distinguishes "aborted run" from "no run." |
| Unclear where the post-run seam and cursor live (OQ-1/3/4/6) | Clean seam at `run-prime-contractor.sh:534` (post-run step runs **unconditionally, even on workflow exit 1**), *before* the TS gate. `run_id` is already resolved via `_resolve_run_id()` (arg → `run-metadata.json` → env → parent dir). `kaizen-index.json` tracks runs idempotently but is shared. | **FR-3/FR-11 sharpened.** SA inserts as a new step *after* line 534; logic lives in a `startd8 assist` Typer sub-app (mirroring `manifest`/`queue`), invoked by a thin `scripts/` shim. Idempotency uses a **separate** `service-assistant-cursor.json` keyed by the existing `run_id` (don't mutate shared `kaizen-index.json`). |

**Resolved open questions:**
- **OQ-1 → SA runs *after* the existing post-run step, consuming its artifacts.** It does not wrap or replace post-mortem generation. Seam: new step after `run-prime-contractor.sh:534`. (Note: `prime-post-run.py` is referenced by the shell script but appears to be an out-of-repo wrapper over `run_prime_postmortem.py` — SA must not depend on its internals, only on the *artifacts* it leaves behind.)
- **OQ-2 → "Notify the SDK" = write the triage artifact (primary) + emit EventBus events (supplementary).** No resident consumer is assumed; events serve optional in-process subscribers and the persisted history. See FR-6/FR-7.
- **OQ-3 → Separate `service-assistant-cursor.json`** keyed by `run_id` + artifact checksum. Do not mutate the shared `kaizen-index.json`.
- **OQ-4 → Both, layered.** Logic in a `startd8 assist` Typer sub-app (`cli.py` `add_typer`, mirroring `manifest generate`); a thin `scripts/service-assistant.py` shim is what the cap-dev-pipe `.sh` calls. CLI is the source of truth.
- **OQ-5 → New `CAUSE_TO_OPERATIONAL_ACTION` mapping** (FR-10). `CAUSE_TO_SUGGESTION` (prompt hints) and `repair/routing.py` (code transforms) are both the wrong layer for operator recommendations.
- **OQ-6 → `.prime_contractor_state.json` is the earliest sentinel** (survives hard abort). New FR-13 formalizes abort detection.
- **OQ-7 → FR-12 stays as an extension *point* only.** Concrete non-Prime checks are explicitly deferred (NR-7); the seam ships in v1, the checks do not.

---

## 1. Problem Statement

When an end user builds a project **with** the startd8 SDK, they run the cap-dev-pipe
pipeline — which orchestrates the **Prime Contractor** workflow — and then run a
**post-mortem** over the result. Today this loop is **manual and disconnected**:

- The human (or their agent) has to *know* a run finished, *find* the output dir,
  *invoke* the post-mortem script, *read* the report, *interpret* failures, and
  *decide* what to do next.
- The SDK has rich diagnostic machinery (`RootCauseClassifier`, `CAUSE_TO_SUGGESTION`,
  `BatchLedger` progression tracking, Kaizen suggestions) but **nothing wires the
  "a run just happened" signal to that machinery automatically**.
- There is no single component whose job is to sit *between the project and the SDK*
  and act as a bridge — detecting lifecycle events and relaying them, with project
  context attached, into the SDK's triage surfaces.

The **Service Assistant** is that bridge. It is the "bus boy" of the SDK: it clears
the table after each run — noticing what was produced, relaying it to the right place,
and flagging what needs attention — so the human/agent doesn't have to babysit the loop.

### Gap table

| Component | Current State | Gap |
|-----------|--------------|-----|
| Run completion signal | `prime-result*.json` written; exit code set | No watcher relays "a new run completed" to the SDK |
| Post-mortem availability | `prime-postmortem-report.json` emitted by `prime-post-run.py` | No component detects "a new post-mortem is available" and reacts |
| Failure classification | `RootCauseClassifier` exists, runs *inside* post-mortem | Not invoked as an automatic triage step keyed off detection |
| Recommended remediation | `CAUSE_TO_SUGGESTION` maps causes→hints | No surface turns a failed run into an actionable, project-contextualized recommendation |
| Cross-run progression | `BatchLedger` / `BatchPostMortemReport` track persistent failures | Not surfaced as a triage signal at the moment a run completes |
| Project context | ContextCore state + `.contextcore.yaml` + forward manifest | Not attached to the failure signal to make triage project-aware |

---

## 2. Goals & Non-Goals (summary)

**Goal:** A one-shot, idempotent **Service Assistant** that, when invoked after a
cap-dev-pipe Prime Contractor run, (a) detects newly-produced run + post-mortem
artifacts via the filesystem, (b) relays a structured "run/post-mortem available"
signal to the SDK, and (c) for failed runs, produces a project-contextualized
**triage report with a recommended action** — without executing that action.

**Not a goal (v1):** auto-remediation, a long-running daemon, new failure-classification
logic, or generating the post-mortem itself.

---

## 3. Requirements

### Detection (filesystem-based, idempotent)

- **FR-1 — Completed-run detection.** The Service Assistant SHALL scan the cap-dev-pipe
  output tree (`pipeline-output/<project>/…`) for the **run completion sentinel**
  (`prime-result.json` / `prime-result-<task-id>.json`) and treat its presence as
  "a Prime Contractor run completed." It SHALL read `success`, `failed`, `processed`,
  and `total_cost_usd` from that artifact.

- **FR-2 — Post-mortem availability detection.** The Service Assistant SHALL detect the
  **post-mortem sentinel** (`prime-postmortem-report.json`) and read its
  `aggregate_verdict` (`PASS` / `PARTIAL` / `FAIL`), failed-feature list, and root-cause
  attribution.

- **FR-3 — Idempotent processed-state cursor.** The Service Assistant SHALL persist a
  record of which run/post-mortem artifacts it has already processed (keyed by run id +
  artifact checksum) so that **re-invocation does not re-trigger** notification or triage
  for an already-handled run. Only *new* artifacts since the last invocation are acted on.

- **FR-4 — Run-vs-post-mortem ordering tolerance.** The Service Assistant SHALL handle
  the case where the run sentinel exists but the post-mortem is not yet present (and vice
  versa), emitting a partial signal and completing the triage on a later invocation when
  the second artifact appears.

- **FR-13 — Hard-abort detection.** The Service Assistant SHALL detect a run that was
  *attempted but crashed before writing `prime-result.json`* by keying off the earlier
  sentinel `.prime_contractor_state.json` (written before the generation loop, survives
  hard aborts). Heuristic: state file present **and** `prime-result.json` absent **and**
  state file mtime older than a staleness threshold ⇒ emit a `RUN_FAILED` signal with
  `status="aborted"` and the count of features attempted (from the state file `order`).
  This distinguishes "a run crashed" from "no run happened" (state file absent).

### Project context

- **FR-5 — Project-context enrichment.** The Service Assistant SHALL load the project's
  context (ContextCore state under `~/.contextcore/state/<project>/`, `.contextcore.yaml`,
  and the forward manifest) and attach relevant context (project id, task ids, requirement
  text) to the relayed signal and triage report, so SDK-side triage is project-aware.

### Notification / relay to the SDK

- **FR-6 — SDK notification (artifact-primary, event-supplementary).** On detecting a new
  completed run and/or post-mortem, the Service Assistant SHALL notify the SDK by emitting
  events on the existing `EventBus` (new event types `RUN_DETECTED`, `POSTMORTEM_AVAILABLE`,
  `RUN_FAILED`) carrying a structured payload (run id, verdict, output dir, project context
  ref). Because the `EventBus` is fire-and-forget with **no guaranteed resident consumer**,
  these events are **supplementary**; the authoritative "notification" is the on-disk triage
  artifact (FR-7). Emitted failure/run events SHALL use `EventPriority.HIGH` so they enter
  the persisted in-memory history.

- **FR-7 — Triage artifact emission (authoritative bridge).** The Service Assistant SHALL
  write a structured triage record to the run output dir (`service-assistant-triage.json`
  + a human-readable `service-assistant-triage.md`) that **synthesizes** (a) detection
  results, (b) the post-mortem `aggregate_verdict` and per-feature root causes read from
  `prime-postmortem-report.json`, (c) batch persistent-failure flags (FR-9), and (d) the
  recommended operational action per failure (FR-10). This artifact is the primary,
  durable channel by which the project↔SDK bridge is realized.

### Triage (classify + recommend; no execute)

- **FR-8 — Failure classification (consume, don't re-derive).** For a failed/partial run,
  the Service Assistant SHALL read the **already-computed** per-feature root causes
  (`RootCause`, `PipelineStage`) and `cross_feature_patterns` from
  `prime-postmortem-report.json`. It SHALL NOT re-run `RootCauseClassifier` itself.
  *Fallback:* only if the report is absent but `prime-result.json` exists may SA invoke
  `RootCauseClassifier` directly to recover classification.

- **FR-9 — Cross-run correlation.** The Service Assistant SHALL cross-reference the
  `BatchLedger` / `batch-postmortem-report.json` to flag **persistent failures** (tasks
  failing across ≥2 runs) and force-regenerated tasks, elevating their triage severity.

- **FR-10 — Recommended-action generation (operational mapping).** For each classified
  failure, the Service Assistant SHALL produce a **concrete operator-facing recommendation**
  via a **new** `CAUSE_TO_OPERATIONAL_ACTION` mapping of `RootCause → {severity, action,
  re_run_strategy}` — e.g. "re-run from latest contract producer," "split element or
  increase tier," "re-run plan-ingestion (skeleton missing)." This mapping is distinct from
  `CAUSE_TO_SUGGESTION` (which produces *prompt hints for the next generation*, not operator
  guidance) and from `repair/routing.py` (deterministic code transforms). SA SHALL NOT
  execute the recommended action (NR-1).

- **FR-14 — Cost-aware remediation (deterministic-failure idempotency).** *Field-driven by
  run-028: `PI-001` failed with `total_cost_usd == 0.0` on a Ruff **F811** (`resolve_matches`
  imported at line 8 and redefined at line 30); the default `duplicate_import → regenerate_clean`
  action told the operator to "regenerate on the next pass" — but a **deterministic** re-run is
  idempotent and reproduces the identical defect.* The Service Assistant SHALL incorporate the
  failed feature's **generation cost** into its recommendation. When a failed feature has **zero
  generation cost** (the `$0` deterministic path — template / MicroPrime / `backend_codegen`,
  read from the post-mortem feature `cost_usd == 0`, corroborated by `total_cost_usd == 0`), the
  SA SHALL:
  1. mark the failure **`deterministic: true`** in the triage artifact so the operator knows a
     plain re-run is futile;
  2. **override** the default `re_run_strategy` to **`fix_deterministic_generator`** — recommend
     fixing the deterministic generator/splicer/template (or escalating the element off the
     deterministic path), **not** "regenerate next pass";
  3. for `duplicate_import` specifically, the recommendation SHALL name the real fix — *remove
     either the import or the local redefinition* (the F811 import-vs-local-definition collision)
     — rather than the coarse "dedupe imports."

  This is an overlay on FR-10's mapping (cost is the discriminator), not a new `RootCause`
  (NR-3). Cost is already available to the SA via the post-mortem it consumes (FR-8).

### Invocation surface

- **FR-11 — One-shot invocation.** The Service Assistant SHALL be invocable as a single
  command (CLI subcommand and/or post-run hook script) that runs to completion and exits,
  with no persistent process. It SHALL be wireable as a post-run step in the cap-dev-pipe
  scripts so it fires automatically after each Prime Contractor run, **including on run
  failure (exit code 1).**

- **FR-12 — Other SDK-related project issues (extensible).** The Service Assistant SHALL
  expose an extension point for detecting non-Prime SDK-related project issues (e.g.
  toolchain/validation gate failures, missing manifests), routing them through the same
  notify+triage path. (Concrete checks beyond Prime runs are out of scope for v1; the
  hook point is in scope.)

---

## 4. Non-Requirements

- **NR-1.** No auto-remediation / no execution of recommended actions in v1 (classify +
  recommend only).
- **NR-2.** No long-running daemon, file-system inotify watcher, or background service —
  detection is a filesystem *scan* performed at one-shot invocation time.
- **NR-3.** No new failure-classification taxonomy — reuse `RootCause`, `PipelineStage`.
  SA *reads* classification from the post-mortem report (FR-8); it does not re-derive it.
  (The *new* `CAUSE_TO_OPERATIONAL_ACTION` mapping in FR-10 is an operator-recommendation
  layer over the existing taxonomy, not a new taxonomy.)
- **NR-4.** Does not generate the post-mortem itself — it runs *after* the existing
  post-run step and *consumes* the artifacts it produces. SA must not depend on the
  internals of the out-of-repo `prime-post-run.py` wrapper, only on the artifacts on disk.
- **NR-5.** No external/3rd-party notification channels (Slack, email, webhooks) in v1 —
  notification means on-disk triage artifact (primary) + EventBus events (supplementary).
- **NR-6.** Not a replacement for the human/agent decision — it recommends, it does not
  decide or act.
- **NR-7.** No concrete non-Prime issue checks in v1 (FR-12 ships the *extension point*
  only; specific checks like toolchain-gate or manifest validation are deferred).

---

## 5. Open Questions

> All seven v0.1 open questions were resolved by the planning pass — see §0 "Resolved open
> questions." They are retained here in condensed form for traceability.

- **OQ-1 → RESOLVED.** SA runs *after* the existing post-run step (`run-prime-contractor.sh:534`),
  consuming its artifacts; does not wrap or replace post-mortem generation.
- **OQ-2 → RESOLVED.** No resident consumer; triage artifact is authoritative, events supplementary.
- **OQ-3 → RESOLVED.** Separate `service-assistant-cursor.json` keyed by `run_id` + checksum.
- **OQ-4 → RESOLVED.** `startd8 assist` Typer sub-app (logic) + thin `scripts/` shim (hook).
- **OQ-5 → RESOLVED.** New `CAUSE_TO_OPERATIONAL_ACTION` mapping (FR-10).
- **OQ-6 → RESOLVED.** `.prime_contractor_state.json` earliest sentinel; formalized as FR-13.
- **OQ-7 → RESOLVED.** FR-12 ships the extension point only; concrete checks deferred (NR-7).

### New open questions surfaced during planning

- **OQ-8 — Cursor scope across projects.** Should the cursor be per-project (under
  `.startd8/state/`) or per-pipeline-output-base? Multi-project users may run several
  pipelines; the cursor key must not collide. (Leaning: per-output-base, since `run_id`
  is unique within a base.)
- **OQ-9 → RESOLVED.** Map **all 19** `RootCause` values (18 concrete + `UNKNOWN`), with a
  loud fallback for future enum additions, enforced by a coverage unit test. Full mapping +
  the FR-7 artifact contract are pinned in
  [`SERVICE_ASSISTANT_TRIAGE_SCHEMA.md`](SERVICE_ASSISTANT_TRIAGE_SCHEMA.md).

---

*v0.2 — Post-planning self-reflective update. 3 requirements revised (FR-6 reframed, FR-8
narrowed, FR-10 expanded), 1 added (FR-13), 1 non-requirement added (NR-7), 7 open
questions resolved, 2 new open questions surfaced. Ready for optional Convergent Review.*
