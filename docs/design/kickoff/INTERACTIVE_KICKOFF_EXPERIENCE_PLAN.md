# Interactive Visual Kickoff Experience — Implementation Plan

**Version:** 1.3 (Post-CRP R5–R6)
**Date:** 2026-06-25
**Status:** Draft
**Requirements:** `INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (v0.5)

> **Headline finding.** The v0.1 "dogfood the deterministic UI machinery" framing is materially
> broken at two layers, and survives only at one:
> - **Broken:** the **flows** primitive cannot capture or persist field values — it writes only a
>   step pointer to a draft DB row (`flow_generator.py:96-99,107-109`); per-step content is an empty
>   tolerant include seam (`flow_generator.py:135`). There is **no manifest-kind registry** to extend
>   the grammar through — each manifest parser is hand-wired into `extract_manifests`
>   (`extract.py:151-228`).
> - **Survives:** the **widget + theme** layer dogfoods cleanly —
>   `htmx_generator._form_input_html` (`htmx_generator.py:443`) and `presentation_polish` are directly
>   reusable.
> - **Blocked:** the agentic/conversational write framing collides with a deliberate read-only
>   dispatch floor (`handle_concierge_read`, `core.py:272-285`) that structurally refuses every
>   non-`survey`/`assess` action from the chat surface.

---

## Milestones

### M0 — Decisions (no code)
Resolve OQ-1/OQ-2/OQ-4 (done in planning; see Requirements §0). Deliverable = corrected requirements
(v0.2). Build order below is risk-ordered: read-only data spine first, write path last.

### M1 — Live extraction-state service (FR-5, FR-6, FR-10) — *build first*
- **Add** a fold over `ExtractionResult.records` → per-field rows
  (e.g. `field_states(result) -> list[FieldState]`). Source: `manifest_extraction/models.py:36-48`
  (`ExtractionRecord`), `report.py` (`report_to_json`).
- Reuses `extract_manifests(docs, live_schema_text=...)` (`extract.py:124`) **unchanged** — pure
  string parsing, `$0`, no LLM (`extract.py:42-43`). Same classification `cli_kickoff.py:_is_conformance_failure:45`
  already uses (`generator-gap` marker).
- **Status vocabulary is `EXTRACTED / NOT_EXTRACTED / DEFAULTED`** (`models.py:19-22`) — there is **no
  `ambiguous` status**; "ambiguity" is free-text in `reason` on `not_extracted` records
  (`entities.py:342,365,374`; `extractors.py:118,132`).
- **Canonical view-model (R1-S7):** define the **typed shared-state contract** M1 emits and **both** M4
  (web) and M5 (TUI) consume — e.g. `FieldState` / `StepState` / `ReadinessView` (fields: `step`, field
  `value`, `status` badge, `source` ref, `readiness`). Parity (FR-3) is then a property of **one
  serializer**, not two renderers; the derived "ambiguous" UI label is computed here once. *Validation:*
  snapshot test — one project state → serialize the view-model once → assert TUI render and web render are
  both pure functions of that snapshot.
- **Source inventory (R3-S4):** the M1 fold also emits a **source inventory** — which docs/files were
  inspected, which produced `ExtractionRecord`s, which expected kickoff inputs are missing, and which
  candidate sources were ignored as out-of-grammar (with reason). It reports **only** files/dirs the
  existing extraction/survey path already scans (no broadened read). Both M4/M5 render identical counts +
  ignored-source reasons. *Validation:* PRD + missing-inputs fixture → identical web/TUI inventory.
- **Depends on:** nothing. Data spine for both UIs and the conversation.

### M2 — Readiness surface (FR-7) — *nearly free*
- **Reuse** `concierge.core.build_assess` (`core.py:155-224`) verbatim — already returns `readiness`,
  `status_counts`, `blockers`, per-domain provisioning (`core.py:173-224`). No new logic.
- **Acceptance (R5–R6) — performance budgets (R5-S3):** define measurable budgets — initial
  extraction/readiness under a target threshold for typical packages, post-capture refresh under a smaller
  threshold, and a visible "large project" fallback if exceeded (spanning M1/M2/M4/M5). *Validation:* a
  performance test over a seeded small/medium/large fixture records extraction, readiness, render, and
  refresh timings; warnings fire above threshold.
- **Depends on:** nothing.

### M3 — Kickoff experience config + step model (FR-1) — *SDK-internal config, NOT a grammar kind*
- **Add** `src/startd8/kickoff_experience/manifest.py`: SDK-internal dataclass/YAML describing ordered
  steps, fields, each field's grammar `value_path` (the identity from `models.py:39-48`), widget hint,
  help prose, provenance default.
- `value_path` strings are the join key back to `ExtractionRecord.value_path` (M1) **and** to a
  concrete `inputs/*.yaml` file+key for write-back (M6) — this mapping table is new and load-bearing.
- **Config linter (R3-S2):** ship `startd8 kickoff lint-config` (or a unit test) that fails when any
  required field lacks a **unique** `value_path`, **exactly one** `inputs/*.yaml` write mapping, a
  supported widget, grammar help, allow-list membership (M6), or canonical view-model fixture coverage.
  Runs **before** M4/M5 so a typo cannot become a silent missing/unwritable field or parity drift.
- **Depends on:** M1 (value_paths must match real extraction identities).

### M4 — Web front-end generation (FR-2, FR-3, FR-4) — *partial dogfood*
- **Reuse** `htmx_generator._form_input_html` (`htmx_generator.py:443-499`) field→widget mapping and
  `presentation_polish` theming.
- **Do NOT** drive through `flow_generator.render_flows` for value capture (flows persist only a step
  pointer; `flow_generator.py:96-99`). The resumable step-state *shape* (FR-4) can mirror the flows
  router; **value capture + per-step POST handlers are new code**.
- **Add** a kickoff-specific FastAPI app generator (per-step form templates + capture handlers that
  call the M6 write path).
- **Post-write refresh (R1-S10):** after a capture handler's `apply_write_plan` succeeds, re-run M1
  extraction so the web UI badge flips `not_extracted → extracted` with the new `SourceRef` (no stale
  "missing" after a successful write). *(Shared with M5.)*
- **Capture preview (R2-S1):** before every M6 apply, render an HTMX field-scoped diff panel (target
  file, `value_path`, source/provenance change, old/new value) that matches the eventual `WritePlan`; no
  apply occurs until explicit confirm. *(Builds on `build_capture_plan` returning planned writes; shared
  with M5's Rich diff.)*
- **Incremental + debounced refresh (R2-S4, R3-S6):** after a capture/edit, re-run M1/M2 and update
  **only** affected field badges / readiness / gap list (display the `captured → extracted/defaulted/
  not_extracted` transition) without restart; debounce rapid edits, show a transient "checking grammar"
  state, and **discard stale results** if a newer edit landed. *(Shared with M5.)*
- **Fuzz/property parity test (R1-S9):** consume the M1 canonical view-model (R1-S7) and assert the web
  serializer is field-identical to the TUI serializer over **randomly generated partial project states**
  (mix of `extracted`/`defaulted`/`not_extracted`, blocking gaps present/absent) — a single golden state
  will not catch divergence in the `defaulted` badge (FR-NEW-5) or empty-gap/all-not-extracted edges.
  *(Property test spans M1/M4/M5.)*
- **Acceptance (R5–R6) — generated-app freshness fingerprint (R5-S1):** hash the FR-1 config, renderer
  version, template/theme assets, and relevant SDK version into the scratch/generated app metadata;
  `kickoff start` (M7 preflight) detects a fingerprint mismatch and **regenerates or refuses with a clear
  reason** rather than serving a stale app. *Validation:* change the FR-1 config/template → next `start`
  regenerates or prints a stable refusal. *(Pairs with M7 preflight.)*
- **Acceptance (R5–R6) — visual/text regression snapshots (R5-S4):** ship web screenshot + Rich text
  snapshots for the demo fixture across key states (missing, defaulted, conflict, final review, preflight
  failure); golden snapshots update only intentionally and CI compares web screenshots and Rich render
  text for the seeded fixture matrix — catching layout/label/clip/format drift the canonical-state parity
  test cannot. *(Shared with M5.)*
- **Acceptance (R5–R6) — capture rate-limit / token expiry (R6-S6):** the web capture handlers apply
  **per-session rate limiting** on capture POSTs and **session/CSRF token expiry** (regenerate on long
  idle), surfacing typed `rate_limited` / `session_expired` reason codes. *Validation:* burst POSTs return
  429 with the stable code; an expired token is rejected before `apply_write_plan`. *(Pairs with the M7
  trust boundary.)*
- **Depends on:** M1, M3, M6.

### M5 — TUI conversational driver (FR-3, FR-9, FR-10, FR-11)
- **Add** `build_kickoff_registry(project_root)` mirroring `concierge.chat.build_concierge_registry`
  (`chat.py:53-81`), registering `survey`/`assess`/`field_states` as **read** tools only.
- **Add** `KickoffChat` like `ConciergeChat` (`chat.py:84`) over `AgenticSession` (`agentic.py:368`).
- Wire into TUI by branching `mixin_enhancement_chain.py:443-451` (today builds a tool-less session via
  `make_chat_session`, `agentic_chat.py:39`).
- **Enforcement test (R1-S5):** ship a negative test asserting the kickoff `ToolRegistry` exposes
  **exactly** `{survey, assess, field_states}`, that a crafted tool-call for
  `instantiate-kickoff`/`log-friction`/`derive-contract` is **refused** at `handle_concierge_read`
  (`core.py:272-285`), and that `field_states` routes **through** that read floor (not a bypass path).
- **Post-write refresh (R1-S10):** after a successful `apply_write_plan` (M6), the session **re-runs M1
  extraction** so the captured field flips to `extracted` with its new `SourceRef` in the live UI — no
  stale `not_extracted`. *Validation:* capture a value, apply, assert the next `field_states` call reports
  it `extracted` with the new `SourceRef`. *(Capture handlers shared with M4.)*
- **Next-action ranking (R2-S3):** implement FR-11 as a deterministic ranking over M1/M2 state —
  readiness blockers first, then required `not_extracted` fields, then `defaulted` values needing review,
  then optional polish fields; tie-break by M3 step order. *Validation:* a mixed-state fixture returns the
  **same** top next action in TUI and web.
- **Depends on:** M1, M2.

### M6 — Value write-back path (FR-8, FR-NEW-1/2/3) — *riskiest new surface*
- **Add** `build_capture_plan(...)` in `concierge/writes.py` → a `WritePlan` editing
  `docs/kickoff/inputs/*.yaml`, applied only via `apply_write_plan` (`safe_write.py:200`) at CLI/human
  privilege.
- **Per-field round-trip gate (FR-8):** re-run `extract_manifests` on candidate text; reject if the
  captured `value_path` newly fails. The batch gate raises `RoundTripError` for the WHOLE manifest
  (`extract.py:233-239`), so a **per-field attribution wrapper is new work** (FR-NEW-3).
- **FR-C3a exception (FR-NEW-2):** per-field merge must READ existing `inputs/*.yaml`, which the current
  builders forbid by policy (`writes.py:5-8,75-78`). This exception must be authored explicitly.
- **Merge fidelity (R1-S1):** use a **comment/anchor/key-order-preserving** YAML merge (e.g.
  `ruamel.yaml` round-trip loader, or a targeted line-range splice) — **NOT** a load→dump cycle.
  `# provenance:`/author comments and key ordering must survive a single-field write. *Validation:*
  golden-file test — author a YAML with comments + non-alpha key order, capture one field, assert the
  byte-diff touches only the target key's value line(s).
- **Interaction failures (R1-S4):** the round-trip gate must handle the **cross-field** case — when a
  captured value re-parses alone but fails only in manifest context (a relationship to a not-yet-declared
  entity, an enum valid only with a sibling), the gate either (a) attributes to the captured `value_path`
  with a `"depends on <other path>"` message, or (b) classifies it as **deferred** validation — **not**
  a hard capture-time reject (which would deadlock entering a relationship before its target exists).
  *Validation:* capture a relationship value whose target entity is absent; assert the message names the
  missing dependency and does not hard-fail the whole capture.
- **Concurrency (R1-S6):** define behavior when the target `inputs/*.yaml` changed on disk between read
  (FR-NEW-2) and `apply_write_plan` — advisory file lock, mtime/hash precondition, or re-read-and-rebase —
  so a stale read→write does not clobber a concurrent external edit (a second kickoff session, the
  concierge CLI, or a human editor). *Validation:* read file, mutate it externally, attempt apply; assert
  the precondition fails rather than clobbering.
- **`value_path` allow-list (R1-S8):** constrain the captured `value_path` to the M3 server-side mapping;
  reject any `value_path` not in the mapping or containing traversal (`../`) **before** `apply_write_plan`,
  so a value from the web/agentic surface cannot redirect the write outside `docs/kickoff/inputs/`.
  *(Pairs with the M7 trust-boundary bullet.)*
- **Stale-write conflict recovery (R4-S1):** when the on-disk hash changed between read/preview and
  apply, do not just refuse — **preserve the proposed value**, re-read the target, show the new
  diff/conflict, and offer **reload field state / reapply-to-latest / discard**, so concurrent edits are
  recoverable without clobber. *Validation:* external edit between preview and apply → no write, proposed
  value retained, reapply-to-latest yields a fresh preview against the updated file. *(Extends R1-S6.)*
- **Typed failure reason codes (R4-S4):** capture/serve failures resolve to **stable codes**
  (`stale_hash`, `roundtrip_field`, `roundtrip_dependency`, `unsafe_value_path`, `csrf_refused`,
  `port_bind_failed`, `scratch_gc_failed`, `permission_denied`) each with short remediation text, shared
  by M6/M7 error handling and emitted as M8 OTel attributes. *Validation:* each simulated failure maps to
  its stable code + user-safe message + telemetry attribute.
- **Acceptance (R5–R6) — proactive external-edit detection (R6-S2):** during an active session,
  re-hash target `inputs/*.yaml` (periodically or on focus/apply) and surface a **non-blocking warning**
  when an external edit occurred since last read — *before* the user reaches the apply-time stale-hash
  refusal. *Validation:* an external edit mid-session triggers a warning naming the file path with
  "reload / keep editing" choices; no silent clobber. *(Extends R1-S6 to live detection.)*
- **Acceptance (R5–R6) — single-writer advisory lock (R6-S3):** one active write-capable session per
  project root (lock file in scratch); a second `kickoff start --write` or a concurrent concierge YAML
  write gets a **clear refusal naming the lock holder** (PID/session id). *Validation:* launch two
  write-enabled sessions → second receives a lock refusal; first teardown releases the lock. *(Pairs with
  M7 start/preflight; extends R1-S6 from stale-read to two-live-writers.)*
- **Acceptance (R5–R6) — headless `test-capture` harness (R6-S5):** add `startd8 kickoff test-capture`
  (or `kickoff check --capture-fixture`) — a headless CI command running `build_capture_plan` + the
  per-field round-trip gate against a checked-in fixture matrix **without serving web/TUI or opening a
  port**. *Validation:* exits 0 on pass and reports **per-field attribution** on failure; no port opened.
  *(Exposed via the M7 CLI.)*
- **Depends on:** M1 (round-trip), M3 (value_path → file/section map).

### M7 — CLI + MCP entry points (FR-13, FR-14)
- **Add** `startd8 kickoff start|continue` to `cli_kickoff.py` (today only `check`, `cli_kickoff.py:58`)
  — generates the front-end if needed, serves the web app and/or launches the TUI. Serving is **new
  plumbing**: `startd8 serve` (`cli.py:1352`) serves the *workflow* API, not generated apps; nothing
  in-SDK serves a generated FastAPI app (`assembler.py` only emits `(path,text)` pairs) (FR-NEW-4).
- **Serve lifecycle (R1-S3):** specify the teardown contract as a numbered lifecycle —
  1. **Port:** bind ephemeral `:0`, surface the chosen port to the caller (no fixed-port collision).
  2. **Process:** run uvicorn in a **supervised child** with `finally`/signal-handler teardown.
  3. **Scratch:** create the scratch dir under a known root; **GC stale dirs** from prior runs on the
     next `start`.
  4. **Signals:** explicit behavior on **Ctrl-C** and on **parent crash** — no orphaned listener, no
     zombie uvicorn.
  *Validation:* integration test — launch, SIGINT, assert port released + no child process + scratch
  removed; launch twice, assert the second run reclaims/cleans the first run's scratch.
- **Trust boundary (R1-S8):** the served app **binds loopback only**, requires a **same-origin/CSRF
  token** on capture POSTs (which drive `build_capture_plan` → `apply_write_plan` at human privilege),
  and rejects any path traversal in a captured `value_path` so no write escapes `docs/kickoff/inputs/`
  (pairs with the M6 `value_path` allow-list). *Validation:* cross-origin POST rejected; `value_path`
  containing `../` rejected before reaching `apply_write_plan`.
- **Preflight/doctor (R3-S3):** before serving, run a preflight that checks the input dir exists/writable,
  safe-writer confinement passes, stale scratch/session is recoverable, the selected port can bind,
  browser-open is optional, and a TUI fallback URL is printed — report actionable status and **exit before
  a partial serve**. *Validation:* simulate missing `docs/kickoff/inputs`, unwritable target, occupied
  port, stale scratch, no browser → preflight reports + avoids partial serve.
- **Inspect / dry-run JSON (R4-S3):** add `startd8 kickoff inspect --json` (or `start --dry-run --json`)
  that emits canonical state, source inventory, readiness, planned next action, and preflight status
  **without** serving web/TUI or generating a scratch app. *Validation:* deterministic JSON for the seeded
  fixture; no port opens, no scratch app, no writes.
- **Extend** MCP `startd8_concierge` (`startd8_mcp.py:3024`) with a read-only `kickoff-state` action (or
  a new tool). Must stay `readOnlyHint:True` (`startd8_mcp.py:3028`) — MCP (stdio) cannot serve/launch a
  local app or TUI.
- **Depends on:** M4, M5, M6.

### M8 — Observability (FR-15)
- **Reuse** `agentic.session/turn/tool_call` spans (`agentic.py:46-48`). **Add** kickoff events (step
  entered, field captured, gap closed, friction logged).
- **Funnel metrics (R2-S7):** emit, with stable names/attributes, the kickoff funnel — session started,
  first field captured, gap closed, defaulted value reviewed, write preview abandoned/applied, round-trip
  rejected, friction logged, serve teardown status — so a dashboard query can compute completion/dropoff
  and write-failure rates (carries the R4-S4 typed reason codes as attributes). *Validation:* trace
  fixture emits the funnel events; a query computes completion/dropoff.
- **Depends on:** M4, M5.

### Phase 2 (post-v1) — accepted, deferred milestones

> Accepted in CRP R2–R4 (gpt-5.5) but scope-expanding beyond the v1 milestones above. Tracked here so
> later reviewers do not re-propose them; **not** folded into M1–M8 v1 scope. (Mirrors Requirements §F.)

- **[Phase 2]** Session-scoped **undo/rollback** artifact for successful captures (pre-apply hash +
  reverse patch in scratch; "undo last capture" in both surfaces). *(Source: R2-S2; over M6 + M7 scratch.)*
- **[Phase 2]** Seeded **kickoff demo fixture** covering all statuses + derived ambiguous, a cross-field
  dependency, a readiness blocker, and a safe write preview; first-run tutorial + shared parity input.
  *(Source: R2-S5; over M1/M4/M5.)*
- **[Phase 2]** FR-1 config per-field **"why this matters / what this unlocks" help** text beyond grammar
  help. *(Source: R2-S6; over M3 config schema.)*
- **[Phase 2]** **Accessibility acceptance suite** for M4/M5 (programmatic labels, non-color status,
  keyboard + visible focus, live regions, 44px targets, 200% zoom). *(Source: R3-S1; over M4/M5.)*
- **[Phase 2]** Final **build-readiness review step** before `kickoff check` handoff (blockers, deferred
  validations, unreviewed defaults, last writes, exact next CLI command). *(Source: R3-S5; over M4/M5 +
  M2.)*
- **[Phase 2]** **Field dependency graph** in M3 config (`depends_on`/`unlocks`/`blocks_build_when_missing`)
  powering cross-field messages, next-action ranking, and final review. *(Source: R4-S2; over M3 + M1/M2.)*
- **[Phase 2]** Rollout **feature flags / modes** (read-only inspect, preview-only, write-enabled, demo;
  default read-only/preview until M6/M7 safety tests pass). *(Source: R4-S5; over M7 + M4/M5.)*
- **[Phase 2]** Final **handoff packet** (Markdown/JSON projection of captured values, blockers, reviewed
  defaults, ignored sources, friction, next commands; not a source of truth). *(Source: R4-S6; over
  M4/M5 + M7.)*
- **[Phase 2]** **Review queue / batch preview** — collect multiple missing/defaulted fields into a
  deterministic queue, preview several proposed captures, then apply each as separate safe-writer
  operations with per-field status. *(Source: R5-S2; over M4/M5 capture UX + M6 planner.)*
- **[Phase 2]** Deterministic **friction taxonomy prefill** — on skip / ignored-source / typed-failure,
  prefill `log-friction` with the candidate F-class + evidence, requiring human confirmation before
  durable append. *(Source: R5-S5; over M5/M4 friction capture + M8 events.)*
- **[Phase 2]** **Quick navigation / command palette** — keyboard (web) and TUI commands jumping to next
  blocker, next defaulted value, source inventory, final review, and capture preview. *(Source: R5-S6;
  over M4/M5 navigation layer.)*
- **[Phase 2]** **Session-scoped draft capture state** — persist unapplied field values, current step,
  and review-queue position in the M7 scratch area across browser refresh, TUI restart, and TUI↔web
  handoff until teardown or explicit discard. *(Source: R6-S1; over M4/M5 session layer + M7 scratch.)*
- **[Phase 2]** **Field search/filter** over the M3 step/field list (by name, `value_path`, status, step,
  blocker/deferred flags) — discoverability beyond the R5 command palette's known jump targets.
  *(Source: R6-S4; over M4/M5 navigation + M1 view-model.)*
- **[Phase 2]** **Round-trip reject escape hatch** — on per-field round-trip failure, offer a copyable
  field-scoped YAML snippet (with provenance comment) for manual paste + re-extraction; no auto-write.
  *(Source: R6-S7; over M6 error handling + M4/M5 UX.)*

---

## Dependency order

```
M1 (extraction-state) ─┬─> M3 (config) ─┬─> M4 (web) ──┐
                       │                 │   ^          ├─> M7 (CLI/MCP) ─> M8 (o11y)
M2 (readiness) ────────┴─> M5 (TUI) ─────┘   │          │
                          M6 (write-back) ───┴──────────┘
```

> **Edge fix (R1-S2):** M6 → **M4** (in addition to M6 → M7). M4's capture handlers genuinely call the
> M6 write path, so the graph now agrees with M4's "Depends on: M1, M3, M6" line — M4 cannot be built or
> tested as "capturing" before the write path exists, or it ships a form that silently no-ops.

Build M1+M2 first (read-only, `$0`, zero new policy surface). M6 last (the only durable-write,
policy-exception surface).

---

## Open questions still open

- **OQ-6 (TUI vs web parity) — RESOLVED (product decision, 2026-06-25) → full fidelity in both
  surfaces.** Both the TUI and the generated web app render the complete experience (FR-6 badges + FR-7
  readiness meter). Parity is enforced via the M1 canonical view-model (R1-S7) + the fuzz/property parity
  test (R1-S9); both surfaces are pure functions of one serialized view-model. No technical blocker
  remained; the decision eliminates "wrong surface" friction.

All OQs now resolved — see Requirements §0.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Comment/anchor/key-order-preserving YAML merge (round-trip loader or line-range splice), not load→dump. | R1 / claude-opus-4-8[1m] | Merged into **M6** as the "Merge fidelity" bullet. | 2026-06-25 |
| R1-S2 | Resolve dependency-graph vs M4 "Depends on" contradiction; route M6 → M4. | R1 / claude-opus-4-8[1m] | Fixed the **`## Dependency order`** ASCII graph (added M6 → M4 edge + edge-fix note); M4 "Depends on: M1, M3, M6" now agrees. | 2026-06-25 |
| R1-S3 | Numbered serve lifecycle: ephemeral port, supervised uvicorn child + teardown, scratch GC, Ctrl-C / parent-crash behavior. | R1 / claude-opus-4-8[1m] | Merged into **M7** as the "Serve lifecycle" numbered bullet. | 2026-06-25 |
| R1-S4 | Interaction-failure path in the round-trip gate (attribute-with-dependency-name or deferred, not hard reject). | R1 / claude-opus-4-8[1m] | Merged into **M6** as the "Interaction failures" bullet. | 2026-06-25 |
| R1-S5 | Negative enforcement test: registry exactly {survey, assess, field_states}; write actions refused at read floor. | R1 / claude-opus-4-8[1m] | Merged into **M5** as the "Enforcement test" deliverable bullet. | 2026-06-25 |
| R1-S6 | Concurrency: advisory lock / mtime-hash precondition / re-read-rebase so stale read→write does not clobber. | R1 / claude-opus-4-8[1m] | Merged into **M6** as the "Concurrency" bullet. | 2026-06-25 |
| R1-S7 | Canonical typed view-model (`FieldState`/`StepState`/`ReadinessView`) consumed by M4 and M5. | R1 / claude-opus-4-8[1m] | Merged into **M1** as the "Canonical view-model" deliverable. | 2026-06-25 |
| R1-S8 | Trust boundary: loopback-only bind, same-origin/CSRF on capture POSTs, `value_path` no-traversal. | R1 / claude-opus-4-8[1m] | Merged into **M7** ("Trust boundary") and **M6** ("`value_path` allow-list"). | 2026-06-25 |
| R1-S9 | Fuzz/property parity test over random partial project states; assert TUI/web view-models field-identical. | R1 / claude-opus-4-8[1m] | Merged into **M4** as the "Fuzz/property parity test" bullet (spans M1/M4/M5). | 2026-06-25 |
| R1-S10 | Post-write refresh: re-run M1 extraction after `apply_write_plan` so captured field flips to `extracted`. | R1 / claude-opus-4-8[1m] | Merged into **M4** and **M5** as the "Post-write refresh" bullets. | 2026-06-25 |
| R2-S1 | Capture preview (field-scoped diff, target file, value_path, provenance change) before every M6 apply. | R2 / gpt-5.5 | Merged into **M4** (and shared with M5) as the "Capture preview" Acceptance. | 2026-06-26 |
| R2-S2 | Session-scoped rollback/undo artifact for successful captures. | R2 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R2-S3 | Deterministic next-best-action ranking (blockers > required missing > defaulted > optional; step-order tie-break). | R2 / gpt-5.5 | Merged into **M5** as the "Next-action ranking" Acceptance. | 2026-06-26 |
| R2-S4 | Post-capture incremental refresh (update only affected badges/readiness/gap; show transition). | R2 / gpt-5.5 | Merged into **M4** (shared with M5) as the "Incremental + debounced refresh" Acceptance. | 2026-06-26 |
| R2-S5 | Seeded kickoff demo fixture covering all statuses, cross-field dependency, blocker, write preview. | R2 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R2-S6 | FR-1 config per-field "why this matters / what this unlocks" help. | R2 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R2-S7 | Kickoff funnel metrics for M8 (session/first-capture/gap/defaulted/preview/round-trip/teardown). | R2 / gpt-5.5 | Merged into **M8** as the "Funnel metrics" Acceptance. | 2026-06-26 |
| R3-S1 | Accessibility acceptance suite for M4/M5 generated forms. | R3 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R3-S2 | Config linter for M3 (unique value_path, one write mapping, widget/help, allow-list, fixture). | R3 / gpt-5.5 | Merged into **M3** as the "Config linter" Acceptance. | 2026-06-26 |
| R3-S3 | Kickoff preflight/doctor before M7 serves (inputs, confinement, scratch, port, browser fallback). | R3 / gpt-5.5 | Merged into **M7** as the "Preflight/doctor" Acceptance. | 2026-06-26 |
| R3-S4 | Source inventory view from M1 (inspected / produced-records / missing / ignored). | R3 / gpt-5.5 | Merged into **M1** as the "Source inventory" Acceptance. | 2026-06-26 |
| R3-S5 | Final build-readiness review step before `kickoff check` handoff. | R3 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R3-S6 | Debounced live refresh with "checking grammar" state + stale-result discard. | R3 / gpt-5.5 | Merged into **M4** (shared with M5) as the "Incremental + debounced refresh" Acceptance. | 2026-06-26 |
| R4-S1 | Stale-write conflict recovery flow (preserve value, re-read, new diff, reload/reapply/discard). | R4 / gpt-5.5 | Merged into **M6** as the "Stale-write conflict recovery" Acceptance. | 2026-06-26 |
| R4-S2 | Field dependency graph in M3 config (depends_on/unlocks/blocks_build_when_missing). | R4 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R4-S3 | `kickoff inspect --json` / dry-run JSON without serving web/TUI. | R4 / gpt-5.5 | Merged into **M7** as the "Inspect / dry-run JSON" Acceptance. | 2026-06-26 |
| R4-S4 | Typed failure reason codes for capture/serve flows with remediation text. | R4 / gpt-5.5 | Merged into **M6** (shared with M7/M8) as the "Typed failure reason codes" Acceptance. | 2026-06-26 |
| R4-S5 | Rollout feature flags / modes (read-only inspect, preview-only, write-enabled, demo). | R4 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R4-S6 | Final handoff packet artifact (Markdown/JSON projection, non-authoritative). | R4 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R5-S1 | Generated-app freshness fingerprint (FR-1 config + renderer/template/theme/SDK version); regenerate/refuse stale artifacts. | R5 / gpt-5.5 | Merged into **M4** as Acceptance (R5–R6) (pairs with M7 preflight). | 2026-06-26 |
| R5-S2 | Review queue / batch preview (multiple field diffs previewed, applied as separate safe writes). | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R5-S3 | Performance budgets (extraction/readiness/refresh thresholds + "large project" fallback). | R5 / gpt-5.5 | Merged into **M2** as Acceptance (R5–R6) (spans M1/M2/M4/M5). | 2026-06-26 |
| R5-S4 | Visual/text regression snapshots (web screenshots + Rich text) across the state matrix. | R5 / gpt-5.5 | Merged into **M4** as Acceptance (R5–R6) (shared with M5). | 2026-06-26 |
| R5-S5 | Deterministic friction taxonomy prefill from failure/skip/ignored-source reason, human-confirmed. | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R5-S6 | Quick navigation / command palette (jump to blocker/defaulted/inventory/review/preview). | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R6-S1 | Session-scoped draft capture state restored across refresh/restart/handoff until teardown/discard. | R6 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R6-S2 | Proactive external-edit detection (re-hash target during session; non-blocking warning before apply). | R6 / gpt-5.5 | Merged into **M6** as Acceptance (R5–R6). | 2026-06-26 |
| R6-S3 | Single-writer advisory lock (one write-capable session per project root; refusal names lock holder). | R6 / gpt-5.5 | Merged into **M6** as Acceptance (R5–R6) (pairs with M7). | 2026-06-26 |
| R6-S4 | Field search/filter over M3 step/field list (name, `value_path`, status, step, blocker/deferred). | R6 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |
| R6-S5 | Headless `startd8 kickoff test-capture` (build_capture_plan + round-trip, no serve/port). | R6 / gpt-5.5 | Merged into **M6** as Acceptance (R5–R6) (exposed via M7 CLI). | 2026-06-26 |
| R6-S6 | Capture POST rate limiting + session/CSRF token expiry (`rate_limited`/`session_expired` codes). | R6 / gpt-5.5 | Merged into **M4** as Acceptance (R5–R6) (pairs with M7 trust boundary). | 2026-06-26 |
| R6-S7 | Round-trip reject escape hatch (copyable field-scoped YAML snippet, no auto-write). | R6 / gpt-5.5 | Accepted — deferred to Phase 2 (Phase-2 milestones). | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-25

- **Reviewer**: claude-opus-4-8 (claude-opus-4-8[1m])
- **Date**: 2026-06-25 00:00:00 UTC
- **Scope**: Plan (S-prefix). Weighted to sponsor focus: M6 value-capture write path + FR-C3a exception, per-field round-trip attribution, M7 serve plumbing/teardown, M5 read-only allow-list boundary, FR-3 cross-surface parity. Adversarial pass included.

**Executive summary (top risks / gaps):**
- M6 is correctly sequenced last, but the merge-write into hand-authored YAML has no specified comment/anchor/ordering-preservation strategy — round-tripping through a standard YAML loader silently destroys provenance markers the friction log says authors rely on.
- The dependency graph in `## Dependency order` is inconsistent with the milestone bodies: M4 declares "Depends on: M1, M3, M6" but the ASCII graph routes M6 only into M7, so M4 can be built/tested before the write path exists — an untested capture handler.
- M7 serve plumbing (FR-NEW-4) names teardown only as a bullet; no spec for orphaned-port reclaim, zombie-uvicorn on crash/Ctrl-C, or scratch-dir GC across repeated `start` invocations — the sponsor's explicit #3 risk is unanswered in the plan.
- M6's per-field round-trip gate re-runs `extract_manifests` on candidate text, but nothing localizes a *cross-field* failure (relationship valid only if a sibling entity exists) to one `value_path` — FR-NEW-3 attribution may be underivable for interaction failures.
- M5 registers read tools by mirroring `build_concierge_registry`, but the plan never states an enforcement *test* that the kickoff registry can never dispatch a write — "structurally enforced" is asserted, not validated.
- No concurrency/locking story for M6 vs. a human editing the same `inputs/*.yaml` in another process (concierge CLI, editor, second kickoff session) — last-writer-wins clobber is unaddressed.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | critical | M6 must specify a **comment/anchor/key-order-preserving** YAML merge (e.g. ruamel.yaml round-trip loader or a targeted line-range splice), not a load→dump cycle. State explicitly that `# provenance:`/author comments and key ordering survive a single-field write. | Sponsor focus #1: merging into hand-authored YAML "risks dropping comments/provenance markers." PyYAML/std loaders discard comments and reorder keys; one capture would silently rewrite the whole file, defeating FR-NEW-2's "preserve sibling keys" intent and NR-2 provenance discipline. | M6 — add a "Merge fidelity" bullet under `build_capture_plan` | Golden-file test: author a YAML with comments + non-alpha key order, capture one field, assert byte-diff touches only the target key's value line(s). |
| R1-S2 | Architecture | high | Resolve the **dependency contradiction**: M4 body says "Depends on: M1, M3, M6" but the `## Dependency order` graph routes M6 → M7 only (not → M4). Pick one. If M4 capture handlers truly need M6, the graph must show M6 → M4; if M4 can ship with a stubbed/dry-run capture, say so. | A reviewer/implementer following the graph would build and "complete" M4's POST handlers before the write path exists, producing a web form that appears to capture but silently no-ops — exactly the false-capture failure mode. | `## Dependency order` ASCII graph + M4 "Depends on" line | Trace each milestone's "Depends on" against the graph; assert they agree (could be a doc-lint check). |
| R1-S3 | Ops | critical | M7 must specify the **serve lifecycle teardown contract**: deterministic port selection (bind :0 / ephemeral, surface chosen port), uvicorn run in a supervised child with a `finally`/signal-handler teardown, scratch-dir created under a known root with GC of stale dirs on next `start`, and explicit behavior on Ctrl-C and on parent crash (no orphaned listener). | Sponsor focus #3; FR-NEW-4 lists teardown as one word. Throwaway local apps that write to project docs are a trust + resource-leak surface; a zombie uvicorn holding a port blocks the next `start` and a stale scratch dir can leak captured-but-unapplied YAML. | M7 — expand the "Serving is new plumbing" bullet into a numbered lifecycle | Integration test: launch, SIGINT, assert port released + no child process + scratch dir removed; launch twice, assert second run reclaims/cleans first run's scratch. |
| R1-S4 | Validation | high | M6's round-trip gate needs a **cross-field / interaction failure path**: when a captured value re-parses individually but fails only in manifest context (relationship referencing a not-yet-declared entity, enum valid only with a sibling), the gate must either (a) attribute to the captured `value_path` with a "depends on <other path>" message, or (b) classify as a *deferred* validation, not a hard capture-time reject. | Sponsor focus #2: per-field attribution may be underivable for interactions. A blanket capture-time reject would block the author from entering a relationship before its target entity — a deadlock the flows-style multi-step flow makes easy to hit. | M6 — add an "Interaction failures" sub-bullet to the round-trip gate | Test: capture a relationship value whose target entity is absent; assert message names the missing dependency and does not hard-fail the whole capture. |
| R1-S5 | Security | high | M5 must add an explicit **negative enforcement test** to the milestone deliverables: assert the kickoff `ToolRegistry` exposes *exactly* `{survey, assess, field_states}` and that a crafted tool-call for `instantiate-kickoff`/`log-friction`/`derive-contract` is refused by `handle_concierge_read` (`core.py:272-285`) — and that the new `field_states` tool is covered by that floor, not bypassing it. | Sponsor focus #4: "propose-only must be airtight." The plan asserts structural enforcement but ships no test; `field_states` is new and could be wired through a different dispatch path that skips the read floor. | M5 — add a "Enforcement test" deliverable bullet | Unit test enumerating registry keys + a parametrized test feeding each write action name, asserting refusal at the dispatch floor. |
| R1-S6 | Risks | high | Add a **concurrent-edit / locking** decision to M6: define behavior when the target `inputs/*.yaml` changed on disk between read (FR-NEW-2) and `apply_write_plan` (advisory file lock, mtime/hash precondition check, or re-read-and-rebase). Today M6 reads then writes with no interlock. | Sponsor focus #1 "concurrent-edit / clobber safety against `apply_write_plan`." Multiple kickoff sessions, the concierge CLI, and a human editor can all touch the same file; a stale read → write silently reverts the other edit. | M6 — add a "Concurrency" bullet | Test: read file, mutate it externally, attempt apply; assert apply detects the change (precondition fails) rather than clobbering. |
| R1-S7 | Interfaces | medium | Define the **canonical shared-state contract** that M1 emits and both M4 (web) and M5 (TUI) consume, as a typed object (e.g. `FieldState`/`StepState`/`ReadinessView`) — name the fields so parity (FR-3) is a property of one serializer, not two renderers. The plan currently lets M4 read M1 and M5 read M1 independently with no shared view-model. | Sponsor focus #5 / FR-3: parity is only testable deterministically if both surfaces consume *one* canonical representation. Two independent reads invite drift (e.g. one surface derives the "ambiguous" UI label, the other doesn't). | M1 — add a "Canonical view-model" deliverable consumed by M4/M5 | Snapshot test: one project state → serialize view-model once → assert TUI render and web render are both pure functions of that snapshot (golden per surface). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Security | high | Adversarial: the local web app (M4/M7) accepts POSTs that drive `build_capture_plan` → `apply_write_plan`, a writer at *human privilege*. Specify that the served app **binds loopback only**, requires a same-origin/CSRF token on capture POSTs, and that no path traversal in a captured `value_path` can redirect the write outside `docs/kickoff/inputs/`. | A locally-served app that writes project docs is a confused-deputy surface: any local process or a malicious page making a cross-origin POST to the ephemeral port could trigger an authorized write. The plan grants the app the writer but never constrains its network/origin exposure. | M7 — add "Trust boundary" bullet to serve plumbing; M6 — `value_path` allow-list | Test: cross-origin POST rejected; `value_path` containing `../` rejected before reaching `apply_write_plan`. |
| R1-S9 | Validation | medium | Adversarial on parity (R1-S7): add a **fuzz/property parity test** that generates random partial project states (mix of extracted/defaulted/not_extracted, blocking gaps present/absent) and asserts the TUI and web view-models are field-identical. A single golden state will not catch divergence in the `defaulted` badge (FR-NEW-5) or empty-gap edge cases. | Sponsor focus #5: "where could they drift?" The most likely drift is in rarely-hit states (all-defaulted, zero-gap, all-not-extracted) that a single happy-path golden never exercises. | M1/M4/M5 — parity test bullet | Property test over generated FieldState lists; assert both serializers agree for every generated state. |
| R1-S10 | Ops | medium | Adversarial: define what `apply_write_plan` does to an **in-flight web/TUI session's cached extraction state** after a successful write — does the session re-run M1 extraction to reflect the new value, or show stale "not_extracted" until reload? Specify the post-write refresh so a captured field flips to `extracted` in the live UI. | Capture → write → stale UI is the most visible bug: the author fills a field, it persists, but the badge still says missing, so they re-enter it. The plan stops at "apply" and never closes the read-back loop. | M4/M5 — add "post-write refresh" to the capture handler spec | Test: capture a value, apply, assert the next `field_states` call reports it `extracted` with the new `SourceRef`. |

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to plan milestone(s). `Covered` = milestone fully addresses it; `Partial` = mentioned but a gap remains (see linked R1 suggestion); `Gap` = unaddressed by any milestone.

| Requirement | Plan Milestone(s) | Coverage | Notes / Gap (R1 suggestion) |
| ---- | ---- | ---- | ---- |
| FR-1 (experience config) | M3 | Covered | `value_path` mapping table called out as load-bearing. |
| FR-2 (deterministic UI gen) | M4 | Covered | Widget+theme reuse; new capture handlers scoped. |
| FR-3 (two front doors, full fidelity) | M4, M5 | Partial | No canonical shared view-model named; parity asserted not designed (R1-S7, R1-S9). |
| FR-4 (resumable progress) | M4 | Partial | Step-state shape mirrors flows; partial-answer persistence path vs. FR-8 write-back not sequenced. |
| FR-5 (pre-populate) | M1 | Covered | Fold over `ExtractionResult.records`. |
| FR-6 (per-field state) | M1 | Covered | 3-state vocabulary correct; `defaulted` flagged. |
| FR-7 (readiness) | M2 | Covered | `build_assess` reused verbatim. |
| FR-8 (round-trip safety) | M6 | Partial | Cross-field/interaction failure attribution undefined (R1-S4). |
| FR-9 (read-only agentic tools) | M5 | Partial | No negative enforcement test for the allow-list (R1-S5). |
| FR-10 (extraction-aware conversation) | M1, M5 | Covered | Grounded in `ExtractionRecord`s. |
| FR-11 (guided next-step) | M5 | Partial | Mentioned in M5 scope; selection logic for "highest-value unfilled field" unspecified. |
| FR-12 (friction capture in-flow) | (M5 implied) | Gap | No milestone explicitly wires propose-only `log-friction` from the loop/web; only named in M5 scope line. |
| FR-13 (MCP entry) | M7 | Covered | Read-only `kickoff-state` action; `readOnlyHint:True` preserved. |
| FR-14 (CLI entry) | M7 | Partial | Serve lifecycle/teardown underspecified (R1-S3, R1-S8). |
| FR-15 (observability) | M8 | Covered | Reuses agentic spans + kickoff events. |
| FR-NEW-1 (capture write builder) | M6 | Covered | `build_capture_plan` specified. |
| FR-NEW-2 (FR-C3a read exception) | M6 | Partial | Exception named; merge-fidelity (comments/order) + concurrency unaddressed (R1-S1, R1-S6). |
| FR-NEW-3 (per-field attribution) | M6 | Partial | Wrapper named; interaction-failure localization undefined (R1-S4). |
| FR-NEW-4 (local app-serving) | M7 | Partial | Teardown/port/scratch GC underspecified (R1-S3); trust boundary missing (R1-S8). |
| FR-NEW-5 (`defaulted` state) | M1 | Covered | Status vocabulary includes DEFAULTED; parity test risk noted (R1-S9). |
| FR-NEW-6 (`value_path`↔file mapping) | M3 | Covered | Join key to `inputs/*.yaml` file+key. |
| NR-1..NR-6 (non-requirements) | n/a | Covered | Plan respects (no new grammar, no new DB, CLI sole writer). |

#### Review Round R2 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:43:00 UTC
- **Scope**: Plan (S-prefix). Second-pass quick-win review weighted to robustness, end-user value, functional low-hanging fruit, and operational hardening. Avoids duplicating R1's core safety findings.

**Executive summary (R2 deltas):**
- R1 correctly calls out the high-risk safety gaps. R2's main additional opportunity is **user confidence around writes**: preview exactly what will change, explain why, and make rollback/retry understandable.
- The "guided next-step" value proposition is underspecified in the plan. A small deterministic ranking function would make the experience feel much smarter without LLM cost.
- M1/M2 are `$0` and synchronous, so the UI can provide immediate feedback after each capture; specify incremental refresh instead of requiring full reload/re-run mental overhead.
- A first-run demo/golden fixture can deliver both product value ("show me what good looks like") and parity/regression test coverage.
- Observability should measure funnel/value outcomes, not only emit spans: time to first captured field, gaps closed, defaulted values reviewed, and write failures by class.
- FR-1's config can carry "why this matters" help text per field, turning the surface from a grammar editor into a product coaching tool.

##### Focus answers (R2 delta)

1. **Value-capture write path + FR-C3a exception:** R1 covers preservation, stale hashes, and traversal. Add a user-facing preview/rollback contract so the bounded read exception is not only safe internally but legible to the author before apply.
2. **Per-field round-trip attribution:** R1 covers cross-field failures. Add a deterministic "repair hint" path: when attribution lands on a field/dependency, show the smallest next action that would make the value valid.
3. **Local serving plumbing/teardown:** R1 covers lifecycle leaks. Add a health/heartbeat check and "recover stale session" UX so a user sees how to reopen or clean up rather than only passing tests.
4. **Read-only agentic allow-list boundary:** R1 covers negative enforcement. Add UX copy constraints: the agent may say "I can prepare a write preview" but not "I saved it" unless the safe-writer result confirms durable write.
5. **Cross-surface parity:** R1 covers canonical view-model. Add a seeded fixture/demo that exercises every status and next-action branch in both surfaces.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | Add a **capture preview** step before every M6 apply: show a field-scoped diff, target file, `value_path`, source/provenance change, and the exact CLI/web action that will apply it. For TUI, render a Rich diff; for web, render an HTMX diff panel. | R1 focuses on safe merge mechanics, but end users also need confidence before allowing a local app to edit YAML. Preview is a low-lift value win because `build_capture_plan` already returns planned writes and bytes. | M4 capture handlers + M6 `build_capture_plan` | Golden diff test: one captured field produces a preview whose target file/value_path matches the eventual `WritePlan`; no apply occurs until explicit confirm. |
| R2-S2 | Risks | medium | Add a **session-scoped rollback/undo artifact** for successful captures: store the pre-apply file hash and a reverse patch/preimage in the local kickoff session scratch area until teardown, then expose "undo last capture" in both surfaces. | Atomic writes prevent partial files but do not help an author who accepted the wrong value. A temporary rollback artifact improves robustness without creating a new application persistence layer; captured docs remain the canonical store. | M6 + M7 scratch lifecycle | Apply a capture, invoke undo, assert the target file returns to the original hash and the next extraction state returns to its prior value. |
| R2-S3 | Interfaces | high | Define the deterministic **next-best-action ranking** for FR-11/M5: readiness blockers first, then `not_extracted` required fields, then `defaulted` values needing review, then optional polish fields; tie-break by step order from M3. | Requirements promise "highest-value unfilled field" but M5 only says `KickoffChat` can read state. This ranking is a cheap product win: the agent feels useful without generating content. | M5 and M1/M2 integration notes | Fixture with mixed blockers/defaulted/missing fields asserts the same top next action in TUI and web. |
| R2-S4 | Ops | medium | Specify **post-capture incremental refresh**: after a write, re-run M1/M2, update only affected field badges/readiness/gap list, and display "captured -> extracted/defaulted/not_extracted" transition. | R1-S10 identifies stale UI risk; the plan should turn that into an implementation contract. Immediate feedback is one of the highest-value quick wins for authors. | M4 capture handler + M5 chat loop | Capture a value; assert the next rendered state changes without restarting the app/TUI session. |
| R2-S5 | Validation | medium | Add a **seeded kickoff demo fixture** that covers all statuses (`extracted/defaulted/not_extracted` + derived ambiguous), at least one cross-field dependency, one readiness blocker, and one safe write preview. Use it as the first-run tutorial and as shared parity test input. | This is low-hanging fruit: one fixture simultaneously improves user onboarding, regression tests, and CRP parity confidence. | M1/M4/M5 validation deliverables | `startd8 kickoff start --demo` renders the fixture; web and TUI golden outputs derive from the same fixture state. |
| R2-S6 | Architecture | medium | Extend the FR-1 config with per-field **"why this matters" / "what this unlocks"** help text, not only grammar help prose. Example: "Defining entities unlocks backend models, CRUD, and relationship views." | The current plan exposes the grammar; the end-user value is understanding how each answer changes the generated app. This avoids bucket-4 content generation while improving author motivation and completion. | M3 config schema | Snapshot test verifies each required field has non-empty grammar help and value/unlocks help. |
| R2-S7 | Ops | medium | Make M8 define kickoff funnel metrics: session started, first field captured, gap closed, defaulted value reviewed, write preview abandoned/applied, round-trip rejected, serve teardown status. | M8 currently says "step entered, field captured, gap closed, friction logged" but not the operational questions that reveal whether the product is helping users finish kickoff. | M8 Observability | Trace/span fixture emits the funnel events with stable names and attributes; dashboard query can compute completion/dropoff. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Merge fidelity is the highest-risk data-preservation issue for hand-authored YAML.
- R1-S3: Serve lifecycle teardown must be explicit before a local writer app ships.
- R1-S5: Read-only enforcement tests are mandatory for the new `field_states` entry point.
- R1-S7: A canonical shared view-model is prerequisite for R2's next-action and demo fixture suggestions.
- R1-S8: Loopback/CSRF/value_path trust-boundary tests are required for any web write preview/apply path.
- R1-S10: Post-write refresh is core to user trust and should be implemented with R2-S4.

**Disagreements**:
- None.

---

## Requirements Coverage Matrix — R2

Analysis only (not triage). `Covered` = plan already fully maps it; `Partial` = plan maps it but R2 found a quick-win/operational gap; `Gap` = absent.

| Requirement | Plan Milestone(s) | Coverage | Notes / Gap (R2 suggestion) |
| ---- | ---- | ---- | ---- |
| FR-1 (experience config) | M3 | Partial | Add "why this matters / what this unlocks" help metadata (R2-S6). |
| FR-2 (deterministic UI gen) | M4 | Covered | Reuse and new capture handlers remain appropriately scoped. |
| FR-3 (two front doors, full fidelity) | M4, M5 | Partial | Needs demo/state fixture for parity branches beyond one happy path (R2-S5). |
| FR-4 (resumable progress) | M4 | Partial | Undo/rollback should be session-scoped and tied to scratch lifecycle (R2-S2). |
| FR-5 (pre-populate) | M1 | Covered | Existing extraction fold sufficient. |
| FR-6 (per-field state) | M1 | Partial | Incremental post-capture refresh should visibly update field state (R2-S4). |
| FR-7 (readiness) | M2 | Partial | Readiness should drive deterministic next-action ranking (R2-S3). |
| FR-8 (round-trip safety) | M6 | Partial | R1 covers attribution; R2 adds preview and repair-hint UX (R2-S1/R2-S3). |
| FR-9 (read-only agentic tools) | M5 | Partial | R1 covers enforcement; R2 adds wording/confirmed-write UX constraint. |
| FR-10 (extraction-aware conversation) | M1, M5 | Partial | Conversation should explain why a field matters, not only what is missing (R2-S6). |
| FR-11 (guided next-step) | M5 | Partial | Ranking algorithm unspecified (R2-S3). |
| FR-12 (friction capture in-flow) | M5/M6 implied | Partial | Preview/authorization UX should align with capture previews (R2-S1). |
| FR-13 (MCP entry) | M7 | Covered | R1 trust-boundary concerns remain. |
| FR-14 (CLI entry) | M7 | Partial | Demo mode and stale-session recovery improve first-run value (R2-S5). |
| FR-15 (observability) | M8 | Partial | Funnel metrics should be enumerated (R2-S7). |
| FR-NEW-1/2 (write builder/read exception) | M6 | Partial | R1 covers merge safety; R2 adds preview + undo affordances (R2-S1/R2-S2). |
| FR-NEW-3 (per-field attribution) | M6 | Partial | R1 covers interaction failures; R2 suggests repair hints tied to next action (R2-S3). |
| FR-NEW-4 (local app-serving) | M7 | Partial | R1 covers teardown; R2 adds user-visible recovery/demo flow (R2-S5). |
| FR-NEW-5 (`defaulted` state) | M1 | Partial | Defaulted review should feed next-action ranking and funnel metrics (R2-S3/R2-S7). |
| FR-NEW-6 (`value_path`↔file mapping) | M3 | Covered | R1 value_path allow-list remains important. |

#### Review Round R3 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:44:00 UTC
- **Scope**: Plan (S-prefix). Fresh pass for accessibility, config validation, preflight checks, source transparency, final review ergonomics, and low-cost performance improvements.

**Executive summary (R3 deltas):**
- R1 and R2 cover write safety and confidence UX; R3 focuses on making the experience resilient before the user starts and usable by more people once they do.
- The generated web/TUI forms should have explicit accessibility acceptance, not only inherit "WCAG-AA theming."
- The FR-1 config is load-bearing enough to need its own linter before M4/M5 are built.
- `startd8 kickoff start` should run a preflight/doctor check for writable inputs, dirty/stale session state, browser availability, and port/process constraints before serving.
- Authors need a "source inventory" panel that explains what files the grammar read and what it ignored, reducing mystery when expected PRD/model content does not pre-populate.
- A final build-readiness review step can turn `kickoff check` into a friendlier go/no-go handoff without replacing the authoritative checker.
- Live extraction is cheap, but repeated writes/keystrokes still need debounced refresh and visible "checking..." state to avoid flicker and race perception.

##### Focus answers (R3 delta)

1. **Value-capture write path + FR-C3a exception:** R1/R2 cover safe merge, preview, and undo. Add a start-time preflight and config linter so invalid `value_path` mappings or unwritable targets fail before the author starts filling forms.
2. **Per-field round-trip attribution:** R1 covers interaction failures. Add a final review step that groups deferred validations and dependencies so the author can resolve them intentionally before build.
3. **Local app-serving plumbing/teardown:** R1 covers teardown, R2 covers recovery/demo. Add a preflight/doctor mode that detects likely serve failures and offers TUI fallback or manual URL.
4. **Read-only allow-list boundary:** R1 covers enforcement. Add source-inventory transparency so the read-only tools disclose what they inspected, reducing temptation to grant write/read expansion to "find missing context."
5. **Cross-surface parity:** R1/R2 cover canonical state and fixture. Add accessibility parity: status, errors, and next-action recommendations must be perceivable without color and operable by keyboard in web and navigable in Rich.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Validation | high | Add an **accessibility acceptance suite** for M4/M5: every field has a programmatic label, required/error/defaulted/extracted states are not color-only, web controls are keyboard operable with visible focus, status updates use live regions where appropriate, touch targets are 44px+, and 200% zoom does not clip forms. | The plan says `presentation_polish` theming is reused, but this is a guided form workflow where labels, errors, focus, and status badges carry the product. Theming alone will not prove WCAG 2.2 AA behavior. | M4 and M5 validation deliverables | Axe/Lighthouse for web plus manual smoke: keyboard-only capture, screen-reader labels, grayscale status badges, 200% zoom, and Rich output preserving non-color status text. |
| R3-S2 | Validation | high | Add a **kickoff experience config linter** for M3: verify every `value_path` is unique, maps to exactly one `inputs/*.yaml` target, has widget/help metadata, is covered by the allow-list, and appears in the canonical view-model fixture. | M3's config is the join point between extraction, write-back, parity, and next-action ranking. A typo can become a silent missing field, unsafe write target, or parity drift. | M3 deliverables before M4/M5 | `startd8 kickoff lint-config` or unit test fails on duplicate value paths, missing write mapping, unsupported widget, absent value help, and unmapped required fields. |
| R3-S3 | Ops | medium | Add a **kickoff preflight/doctor** before M7 serves: check input directory exists/writable, safe-writer confinement passes, stale scratch/session state is recoverable, selected port can bind, browser-open is optional, and TUI fallback is printed. | Serve plumbing failures are predictable and cheap to detect before launching uvicorn. This improves robustness and gives users recovery instructions instead of stack traces. | M7 CLI entry point | Simulate missing `docs/kickoff/inputs`, unwritable target, occupied port, and no browser; preflight reports actionable status and exits before partial serve. |
| R3-S4 | Interfaces | medium | Add a **source inventory view** from M1: list which docs/files were inspected, which produced `ExtractionRecord`s, which expected kickoff inputs are missing, and which sources were ignored as out-of-grammar. | The problem statement says the grammar is closed and invisible. Showing "what I read" and "why this did not pre-populate" is a quick user-value win and keeps the agentic layer grounded in read-only facts. | M1 view-model + M4/M5 surfaces | Fixture with PRD + missing inputs renders an inventory; both TUI/web show identical source counts and ignored-source reasons. |
| R3-S5 | Interfaces | medium | Add a final **build-readiness review step** before handing off to `kickoff check`: summarize remaining blockers, deferred cross-field validations, defaulted values still unreviewed, last write preview/applies, and the exact next CLI command. | FR-7 surfaces readiness throughout, but authors benefit from a final go/no-go page that translates the grammar state into build confidence. This is not a replacement for `kickoff check`; it is a friendlier handoff. | M4/M5 completion step + M2 readiness surface | Fixture with blockers/defaulted/deferred validations produces a deterministic final review; no "ready" state unless authoritative `assess`/checker data agrees. |
| R3-S6 | Ops | low | Add **debounced live refresh** semantics: after field edits/previews, re-run M1/M2 after a short debounce, show a "checking grammar..." state, and discard stale extraction results if a newer edit landed. | OQ-5 says live extraction is cheap; cheap does not prevent flicker or stale-result races in an interactive UI. This is low effort and makes the surface feel reliable. | M4 capture handlers and M5 chat loop | Rapid-edit test triggers multiple refreshes; only the latest result updates badges/readiness, and the UI exposes an intermediate checking state. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S7: Canonical view-model remains prerequisite for source inventory, final review, accessibility parity, and debounced refresh.
- R1-S9: Property parity testing should include R3 accessibility/status variants.
- R1-S10 and R2-S4: Post-write refresh should include stale-result discard behavior from R3-S6.
- R2-S3: Deterministic next-action ranking should feed the final build-readiness review.
- R2-S5: The seeded demo fixture is the natural place to exercise accessibility and source inventory states.
- R2-S6: Field value/help metadata should be enforced by the M3 config linter.
- R2-S7: Funnel metrics should include preflight failures and final-review outcomes.

**Disagreements**:
- None.

---

## Requirements Coverage Matrix — R3

Analysis only (not triage). `Covered` = plan already fully maps it; `Partial` = plan maps it but R3 found a quick-win/operational gap; `Gap` = absent.

| Requirement | Plan Milestone(s) | Coverage | Notes / Gap (R3 suggestion) |
| ---- | ---- | ---- | ---- |
| FR-1 (experience config) | M3 | Partial | Needs config linter and accessibility/value metadata validation (R3-S1/R3-S2). |
| FR-2 (deterministic UI gen) | M4 | Partial | Needs explicit accessibility acceptance for generated form controls (R3-S1). |
| FR-3 (two front doors, full fidelity) | M4, M5 | Partial | Parity should include accessibility/status/source-inventory states (R3-S1/R3-S4). |
| FR-4 (resumable progress) | M4 | Partial | Preflight/stale-session behavior should be defined (R3-S3). |
| FR-5 (pre-populate) | M1 | Partial | Source inventory should expose inspected/missing/ignored sources (R3-S4). |
| FR-6 (per-field state) | M1 | Partial | Debounced refresh should avoid stale status updates (R3-S6). |
| FR-7 (readiness) | M2 | Partial | Final review should summarize readiness/deferred/defaulted state (R3-S5). |
| FR-8 (round-trip safety) | M6 | Partial | Final review should surface deferred validations before build handoff (R3-S5). |
| FR-9 (read-only agentic tools) | M5 | Covered | R1 enforcement remains central; source inventory stays read-only. |
| FR-10 (extraction-aware conversation) | M1, M5 | Partial | Conversation should be able to explain inspected/ignored sources (R3-S4). |
| FR-11 (guided next-step) | M5 | Partial | Final review should consume next-action/deferred validation logic (R3-S5). |
| FR-12 (friction capture in-flow) | M5/M6 implied | Partial | Final review and source inventory can suggest friction capture for ignored sources (R3-S4/R3-S5). |
| FR-13 (MCP entry) | M7 | Partial | Preflight/doctor should define MCP/IDE launch failure handoff (R3-S3). |
| FR-14 (CLI entry) | M7 | Partial | Needs kickoff preflight/doctor before serve (R3-S3). |
| FR-15 (observability) | M8 | Partial | Metrics should include preflight failures, accessibility smoke, final-review outcomes (R2-S7/R3-S3/R3-S5). |
| FR-NEW-1/2 (write builder/read exception) | M6 | Partial | Config linter should fail unsafe write mappings before runtime (R3-S2). |
| FR-NEW-3 (per-field attribution) | M6 | Partial | Deferred/cross-field validations should appear in final review (R3-S5). |
| FR-NEW-4 (local app-serving) | M7 | Partial | Needs preflight/doctor in addition to teardown/recovery (R3-S3). |
| FR-NEW-5 (`defaulted` state) | M1 | Partial | Accessibility and final review should make defaulted visible without color-only cues (R3-S1/R3-S5). |
| FR-NEW-6 (`value_path`↔file mapping) | M3 | Partial | Config linter should validate full mapping integrity (R3-S2). |

#### Review Round R4 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:46:00 UTC
- **Scope**: Plan (S-prefix). Fresh pass for conflict recovery, field dependencies, CI/dry-run integration, typed failure UX, feature flags, and operational rollout.

**Executive summary (R4 deltas):**
- Prior rounds cover safety, preview/undo, accessibility, and preflight. R4 adds "what happens next" behavior when those controls detect a problem.
- Stale-hash refusal is safe but not helpful by itself; users need a rebase/conflict-recovery path that preserves their typed value.
- The FR-1 field config can cheaply expose a dependency graph, making cross-field validations and guided next-step recommendations explainable.
- A machine-readable dry run gives CI/agents the same kickoff state without launching a local web app.
- Capture and serve failures should have stable reason codes with remediation text; this improves UI, tests, telemetry, and support.
- New surfaces should ship behind feature flags / explicit modes so users can keep current `kickoff check` and deterministic docs-only workflow while the experience matures.
- A compact "handoff packet" after final review would make the work valuable even if the user does not immediately run the build cascade.

##### Focus answers (R4 delta)

1. **Value-capture write path + FR-C3a exception:** R1/R2/R3 cover safe write, preview, undo, and preflight. Add stale-conflict recovery so hash refusal preserves the user's value and offers reload/reapply rather than a dead end.
2. **Per-field round-trip attribution:** R1 covers cross-field failures and R3 final review. Add a dependency graph in M3 so dependency messages are generated from declared relationships rather than prose heuristics.
3. **Local serving plumbing/teardown:** Add a non-serving dry-run JSON path for CI/agents and environments where launching a local app is inconvenient or blocked.
4. **Read-only allow-list boundary:** Feature-flag the write-capable web capture path separately from read-only state/preview so agent/IDE users can run assessment without enabling local writes.
5. **Cross-surface parity:** Use stable reason codes and dry-run snapshots as a parity oracle across TUI, web, MCP, and CI JSON.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Data | high | Add a **stale-write conflict recovery flow** to M6: when the on-disk hash changed, preserve the user's proposed value, re-read the target file, show the new diff/conflict, and offer "reload field state," "reapply to latest," or "discard." | R1 requires stale-hash refusal and R2 adds undo/preview, but refusal alone loses user momentum. A conflict recovery flow keeps clobber safety while making concurrent edits recoverable. | M6 capture apply flow + M4/M5 error handling | Simulate external edit between preview and apply; assert no write occurs, proposed value is retained, and reapply-to-latest produces a new preview against the updated file. |
| R4-S2 | Architecture | medium | Add a **field dependency graph** to the M3 config (`depends_on`, `unlocks`, `blocks_build_when_missing`) and use it to power cross-field validation messages, next-action ranking, and final review. | R1/R2 discuss cross-field failures and ranking, but the plan lacks a declared dependency source. Encoding dependencies once in M3 avoids each surface inventing its own relationship rules. | M3 config schema and M1/M2 view-model derivation | Config fixture declares relationship field depends on entity field; capture failure and next-action output both cite the same dependency path. |
| R4-S3 | Ops | medium | Add `startd8 kickoff inspect --json` (or `start --dry-run --json`) that emits the canonical state, source inventory, readiness, planned next action, and preflight status without serving web/TUI. | M7 assumes serving/launching, but CI, MCP callers, and agents often need machine-readable state without a browser or uvicorn lifecycle. This is low-hanging operational leverage from M1/M2/M3. | M7 CLI/MCP entry point | Command emits stable JSON for the seeded fixture; no port is opened and no scratch app is generated. |
| R4-S4 | Interfaces | medium | Define **typed failure reason codes** for capture/serve flows (`stale_hash`, `roundtrip_field`, `roundtrip_dependency`, `unsafe_value_path`, `csrf_refused`, `port_bind_failed`, `scratch_gc_failed`, `permission_denied`) with short remediation text. | Prior rounds add many safety checks; without stable codes, UI copy, tests, telemetry, and support will string-match ad hoc errors. | M6/M7/M8 shared error handling | Tests assert each simulated failure maps to a stable code, user-facing remediation, and OTel attribute. |
| R4-S5 | Risks | medium | Add rollout **feature flags / modes**: read-only inspect, preview-only capture, write-enabled local app, and demo mode. Default to read-only/preview until M6/M7 safety tests pass. | The feature spans read-only extraction and local writes. Mode separation lets users get value from state/readiness immediately while limiting blast radius of the write path. | M7 CLI flags + M4/M5 mode handling | In preview-only mode, capture produces a preview but `apply_write_plan` is unreachable; in write-enabled mode it requires explicit confirmation and CSRF/session token. |
| R4-S6 | Interfaces | low | Add a final **handoff packet** artifact (Markdown or JSON) summarizing captured values, remaining blockers, reviewed defaults, ignored sources, friction items, and next commands. It should be generated on demand and not become a new source of truth. | Users may pause after kickoff; a portable handoff improves value for teams and future agents without changing persistence. It is a low-cost projection from the canonical state. | M4/M5 final review + M7 CLI | Fixture generates handoff; it contains no raw secrets, includes timestamps/source refs, and regenerates deterministically from current docs. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1 and R2-S2: Preview and undo are prerequisites for R4's conflict recovery flow.
- R2-S3: Next-action ranking becomes more explainable when backed by R4's dependency graph.
- R2-S7: Funnel metrics should use R4 typed reason codes for write/serve failures.
- R3-S2: The config linter should validate dependency graph integrity as well as value-path mappings.
- R3-S3: Preflight/doctor pairs naturally with a dry-run JSON inspect mode.
- R3-S4 and R3-S5: Source inventory and final review are the core inputs for the handoff packet.

**Disagreements**:
- None.

---

## Requirements Coverage Matrix — R4

Analysis only (not triage). `Covered` = plan already fully maps it; `Partial` = plan maps it but R4 found a quick-win/operational gap; `Gap` = absent.

| Requirement | Plan Milestone(s) | Coverage | Notes / Gap (R4 suggestion) |
| ---- | ---- | ---- | ---- |
| FR-1 (experience config) | M3 | Partial | Add field dependency graph metadata (R4-S2). |
| FR-2 (deterministic UI gen) | M4 | Covered | No additional deterministic generation gap in R4. |
| FR-3 (two front doors, full fidelity) | M4, M5 | Partial | Parity should include typed failure states and mode flags (R4-S4/R4-S5). |
| FR-4 (resumable progress) | M4 | Partial | Conflict recovery should preserve in-progress user values after stale-write refusal (R4-S1). |
| FR-5 (pre-populate) | M1 | Covered | R3 source inventory remains the main improvement. |
| FR-6 (per-field state) | M1 | Partial | Field states should include dependency/reason codes where applicable (R4-S2/R4-S4). |
| FR-7 (readiness) | M2 | Partial | Dry-run JSON should expose readiness without serving (R4-S3). |
| FR-8 (round-trip safety) | M6 | Partial | Needs stale-conflict recovery and typed failure codes (R4-S1/R4-S4). |
| FR-9 (read-only agentic tools) | M5 | Partial | Mode flags should preserve read-only inspect independent of write-enabled local app (R4-S5). |
| FR-10 (extraction-aware conversation) | M1, M5 | Partial | Conversation can explain dependency graph and failure reason codes (R4-S2/R4-S4). |
| FR-11 (guided next-step) | M5 | Partial | Dependency graph should feed next-action ranking (R4-S2). |
| FR-12 (friction capture in-flow) | M5/M6 implied | Partial | Handoff packet can include friction items without becoming source of truth (R4-S6). |
| FR-13 (MCP entry) | M7 | Partial | MCP/agents benefit from dry-run JSON inspect mode (R4-S3). |
| FR-14 (CLI entry) | M7 | Partial | Add inspect/dry-run and feature modes (R4-S3/R4-S5). |
| FR-15 (observability) | M8 | Partial | Typed reason codes should become OTel attributes (R4-S4). |
| FR-NEW-1/2 (write builder/read exception) | M6 | Partial | Stale-write conflict recovery and mode flags are missing (R4-S1/R4-S5). |
| FR-NEW-3 (per-field attribution) | M6 | Partial | Dependency graph makes attribution/remediation explainable (R4-S2). |
| FR-NEW-4 (local app-serving) | M7 | Partial | Dry-run inspect avoids serving when unnecessary; typed serve errors improve recovery (R4-S3/R4-S4). |
| FR-NEW-5 (`defaulted` state) | M1 | Covered | R2/R3 already cover review, ranking, accessibility. |
| FR-NEW-6 (`value_path`↔file mapping) | M3 | Partial | Dependency metadata should be validated alongside mapping integrity (R4-S2). |

#### Review Round R5 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:48:00 UTC
- **Scope**: Plan (S-prefix). Late-pass quick wins for generated-artifact freshness, batch review ergonomics, performance budgets, visual regression, friction taxonomy, and navigation speed.

**Executive summary (R5 deltas):**
- R1-R4 cover safety, confidence, accessibility, and rollout. R5 focuses on small additions that make the experience feel polished and reliable under everyday use.
- The generated local app can drift from the FR-1 config, templates, or theme without users realizing; add a fingerprint and stale-artifact check.
- Per-field write safety is right, but reviewing each field one at a time can become tedious; add a deterministic review queue and batch preview while preserving per-field/per-file safety underneath.
- The plan should define performance budgets for extraction, readiness refresh, and initial serve so "live" remains true as input packages grow.
- Cross-surface parity needs layout/visual regression in addition to canonical state equality.
- Friction capture can be more valuable if the system pre-fills deterministic friction taxonomy from the failure/skip/source-inventory reason.
- Fast keyboard/command navigation to the next blocker is a low-effort value win for both power users and keyboard-only users.

##### Focus answers (R5 delta)

1. **Value-capture write path + FR-C3a exception:** Keep per-field safety, but add a batch review queue that previews multiple field changes while applying each through the same bounded writer.
2. **Per-field round-trip attribution:** Use typed reason/dependency codes from prior rounds to pre-fill friction taxonomy and remediation hints.
3. **Local app-serving plumbing/teardown:** Add generated-artifact fingerprinting so the served app cannot silently run stale templates/config.
4. **Read-only allow-list boundary:** Batch review and friction prefill stay deterministic/propose-only until a human confirms apply/log.
5. **Cross-surface parity:** Add screenshot/text visual regression over the seeded fixture so parity includes user-visible layout, not just state equality.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Ops | high | Add a **generated-app freshness fingerprint**: hash FR-1 config, renderer version, template/theme assets, and relevant SDK version into the scratch/generated app metadata; `kickoff start` refuses or regenerates stale artifacts. | M4/M7 generate and serve a throwaway app, but prior rounds only cover process/scratch lifecycle. A stale generated app can show old fields or unsafe handlers after config changes. | M4 generation + M7 start/preflight | Change the FR-1 config or template; next `kickoff start` detects fingerprint mismatch and regenerates or prints a clear refusal. |
| R5-S2 | Interfaces | medium | Add a **review queue / batch preview** mode: collect multiple missing/defaulted fields into a deterministic queue, let users review/edit several proposed captures, then apply each as separate safe-writer operations with per-field status. | Per-field capture is safe but can be slow. A batch preview increases end-user value without weakening atomic per-file apply, because confirmation can still fan out to individual `WritePlan`s. | M4/M5 capture UX + M6 planner | Fixture queues three fields; preview shows all diffs; apply writes independently and reports per-field success/failure. |
| R5-S3 | Ops | medium | Define **performance budgets**: initial extraction/readiness under a target threshold for typical kickoff packages, post-capture refresh under a smaller threshold, and visible "large project" fallback if exceeded. | OQ-5 says extraction is `$0` and synchronous, and R3 adds debounce, but no measurable budget says when "live" stops feeling live. | M1/M2/M4/M5 validation | Performance test over seeded small/medium/large fixture records extraction, readiness, render, and refresh timings; warnings fire above threshold. |
| R5-S4 | Validation | medium | Add **visual/text regression snapshots**: web screenshot snapshots and Rich text snapshots for the demo fixture across key states (missing, defaulted, conflict, final review, preflight failure). | Canonical state parity does not catch layout regressions, hidden labels, clipped mobile views, or Rich formatting drift. This complements R3 accessibility and parity suggestions. | M4/M5 validation deliverables | Golden snapshots update only intentionally; CI compares web screenshots and Rich render text for the seeded fixture matrix. |
| R5-S5 | Interfaces | medium | Add deterministic **friction taxonomy prefill**: when a user skips a next action, hits source-inventory ignored content, or encounters a typed failure code, prefill `log-friction` with the relevant F-class candidate and evidence, still requiring human confirmation. | FR-12 lets users log friction, but the richest evidence is already available at the moment of failure. Prefill turns operational telemetry into higher-quality human feedback without LLM-authored content. | M5/M4 friction capture + M8 events | Simulate ignored PRD section and stale-write conflict; friction preview contains candidate class, evidence, and no durable write before confirmation. |
| R5-S6 | Interfaces | low | Add **quick navigation / command palette**: jump to next blocker, next defaulted value, source inventory, final review, and capture preview via keyboard in web and commands in TUI. | This is a low-hanging UX improvement that also supports keyboard-only users and large kickoff packages. It builds on the canonical view-model and next-action ranking. | M4/M5 navigation layer | Keyboard/TUI command test moves focus/selection to the expected field without mouse interaction; focus remains visible. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1 and R2-S2: Preview and undo are necessary before batch review can be trustworthy.
- R2-S3 and R4-S2: Next-action ranking plus dependency graph are prerequisites for a useful review queue.
- R2-S5 and R3-S1: Demo fixtures and accessibility acceptance should feed visual/text regression coverage.
- R3-S3 and R4-S3: Preflight and dry-run JSON are the right places to expose generated-app freshness and performance status.
- R3-S4, R4-S4, and R4-S6: Source inventory, typed failures, and handoff packets make deterministic friction prefill practical.
- R4-S5: Feature modes should gate batch apply and keep preview-only paths available.

**Disagreements**:
- None.

---

## Requirements Coverage Matrix — R5

Analysis only (not triage). `Covered` = plan already fully maps it; `Partial` = plan maps it but R5 found a quick-win/operational gap; `Gap` = absent.

| Requirement | Plan Milestone(s) | Coverage | Notes / Gap (R5 suggestion) |
| ---- | ---- | ---- | ---- |
| FR-1 (experience config) | M3 | Partial | Config changes should invalidate generated app artifacts (R5-S1). |
| FR-2 (deterministic UI gen) | M4 | Partial | Generated app needs freshness fingerprint and visual regression (R5-S1/R5-S4). |
| FR-3 (two front doors, full fidelity) | M4, M5 | Partial | Add visual/text parity snapshots and quick navigation parity (R5-S4/R5-S6). |
| FR-4 (resumable progress) | M4 | Partial | Review queue should preserve per-field progress across sessions if resumed (R5-S2). |
| FR-5 (pre-populate) | M1 | Covered | R3 source inventory remains main improvement. |
| FR-6 (per-field state) | M1 | Partial | Review queue and command palette should navigate field states efficiently (R5-S2/R5-S6). |
| FR-7 (readiness) | M2 | Partial | Performance budgets should include readiness refresh timing (R5-S3). |
| FR-8 (round-trip safety) | M6 | Partial | Batch preview must preserve per-field round-trip attribution (R5-S2). |
| FR-9 (read-only agentic tools) | M5 | Covered | Batch/friction prefill remains propose-only until confirmation. |
| FR-10 (extraction-aware conversation) | M1, M5 | Partial | Conversation can use command/navigation and friction prefill (R5-S5/R5-S6). |
| FR-11 (guided next-step) | M5 | Partial | Review queue is a natural extension of next-action ranking (R5-S2). |
| FR-12 (friction capture in-flow) | M5/M6 implied | Partial | Deterministic taxonomy/evidence prefill improves friction quality (R5-S5). |
| FR-13 (MCP entry) | M7 | Partial | Inspect/dry-run JSON should include freshness/performance state (R5-S1/R5-S3). |
| FR-14 (CLI entry) | M7 | Partial | `kickoff start` should check stale generated app and expose performance warnings (R5-S1/R5-S3). |
| FR-15 (observability) | M8 | Partial | Add performance timings and friction-prefill outcomes (R5-S3/R5-S5). |
| FR-NEW-1/2 (write builder/read exception) | M6 | Partial | Batch preview must fan out to per-field safe writes (R5-S2). |
| FR-NEW-3 (per-field attribution) | M6 | Partial | Batch preview and friction prefill should preserve attribution (R5-S2/R5-S5). |
| FR-NEW-4 (local app-serving) | M7 | Partial | Stale generated app detection extends serve robustness (R5-S1). |
| FR-NEW-5 (`defaulted` state) | M1 | Partial | Review queue should prioritize defaulted values needing review (R5-S2). |
| FR-NEW-6 (`value_path`↔file mapping) | M3 | Partial | Fingerprint and config linter should include mapping changes (R5-S1). |

#### Review Round R6 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:50:00 UTC
- **Scope**: Plan (S-prefix). Fresh pass for session draft persistence, proactive external-edit detection, single-writer locking, large-package navigation, CI capture harness, and local-web abuse hardening.

**Executive summary (R6 deltas):**
- R1-R5 cover safe writes, preview/undo, rollout modes, and polish. R6 closes gaps in **session continuity** and **multi-process safety** that show up in real daily use.
- R2 undo covers post-apply rollback, but in-flight draft values can still be lost on refresh, crash, or surface switch — session-scoped draft capture state is a cheap FR-4 win.
- R1/R4 stale-hash checks are reactive at apply time; proactive detection when `inputs/*.yaml` changes externally during an active session prevents surprise conflicts.
- A single-writer advisory lock prevents two kickoff sessions or kickoff+concierge from clobbering the same inputs despite per-field safety.
- Large kickoff configs need field search/filter — distinct from R5 command palette (jump targets) and low effort.
- A headless `kickoff test-capture` harness lets CI validate M6 round-trip without browser/uvicorn — operational quick win.
- Loopback trust boundary needs basic rate limiting and session-token expiry on capture POSTs.

##### Focus answers (R6 delta)

1. **Value-capture write path + FR-C3a exception:** Add session draft persistence for unapplied captures and an export-YAML-snippet escape hatch when round-trip rejects, so users don't lose work or hit dead ends.
2. **Per-field round-trip attribution:** `test-capture` harness should assert per-field attribution messages in CI without the full UI.
3. **Local app-serving plumbing/teardown:** Single-writer lock + capture POST rate limits reduce zombie-session and confused-deputy risk beyond teardown alone.
4. **Read-only allow-list boundary:** Draft state and search stay read-only in agentic tools; only human-confirmed apply paths persist drafts to disk.
5. **Cross-surface parity:** Session draft state must serialize from the canonical view-model so TUI↔web handoff preserves in-progress values.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | Interfaces | high | Add **session-scoped draft capture state** in the M7 scratch area: persist in-progress (unapplied) field values, current step, and review-queue position across browser refresh, TUI restart, and TUI↔web handoff until teardown or explicit discard. | R2 undo covers post-apply rollback and R4 conflict recovery covers stale apply, but neither preserves typed-but-not-applied values. FR-4 resumability is incomplete without draft persistence. | M4/M5 session layer + M7 scratch lifecycle | Enter values without applying, restart session, assert drafts restore identically in web and TUI from the same scratch snapshot. |
| R6-S2 | Risks | medium | Add **proactive external-edit detection**: during an active session, periodically re-hash target `inputs/*.yaml` files (or on focus/apply) and surface a non-blocking warning when an external edit occurred since last read — before the user reaches apply-time stale-hash refusal. | R1/R4 handle stale hash at apply; users still waste effort filling fields against stale mental model. Proactive warning is cheap and improves robustness for editor+kickoff concurrent use. | M4/M5 + M6 precondition layer | External edit mid-session triggers warning with file path and "reload / keep editing" choices; no silent clobber. |
| R6-S3 | Ops | medium | Add a **single-writer advisory lock** for kickoff capture: one active write-capable session per project root (lock file in scratch); second `kickoff start --write` or concurrent concierge YAML write attempt gets a clear refusal with lock holder PID/session id. | R1-S6 covers stale read→write but not two live writers. Two sessions can interleave per-field applies and produce confusing partial state even when each apply is individually safe. | M6 + M7 start/preflight | Launch two write-enabled sessions; second receives lock refusal; first teardown releases lock. |
| R6-S4 | Interfaces | low | Add **field search/filter** over the M3 step/field list: filter by name, `value_path`, status (`extracted`/`defaulted`/`not_extracted`), step, and blocker/deferred flags. | R5 command palette jumps to known targets; large kickoff packages still need discoverability when users don't know the field name. Search is a low-lift UX win for real projects. | M4/M5 navigation + M1 view-model | Fixture with 20+ fields: search "entity" returns matching subset; status filter shows only `not_extracted` required fields. |
| R6-S5 | Validation | medium | Add **`startd8 kickoff test-capture`** (or `kickoff check --capture-fixture`): headless CI command that runs `build_capture_plan` + per-field round-trip gate against a checked-in fixture matrix without serving web/TUI or opening a port. | R4 inspect JSON covers read state; no headless write-path regression exists. This is operational leverage for M6 safety tests in CI without browser automation. | M6 validation + M7 CLI | Fixture matrix of value_path/value pairs; command exits 0 on pass, reports per-field attribution on failure; no port opened. |
| R6-S6 | Security | medium | Harden the local web capture surface with **per-session rate limiting** on capture POSTs and **session/CSRF token expiry** (regenerate on long idle), with typed `rate_limited` / `session_expired` reason codes. | R1-S8 defines loopback+CSRF but not abuse from a local script or stale tab replaying POSTs. Low-cost hardening for a human-privilege writer. | M7 trust boundary + M4 capture handlers | Burst POSTs return 429 with stable code; expired token rejected before `apply_write_plan`; remediation text shown in UI. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S7 | Interfaces | low | Add a **round-trip reject escape hatch**: when per-field round-trip fails, offer "copy proposed YAML snippet" (field-scoped, with provenance comment) so the author can manually paste into the target file and re-run extraction. | Some cross-field/deferred failures may not be auto-fixable in-session. Without an escape hatch, users hit dead ends despite safe refusal. | M6 error handling + M4/M5 UX | Simulated round-trip reject shows copyable snippet matching preview diff; no auto-write occurs. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S2 and R4-S1: Undo and conflict recovery pair with R6 draft persistence and proactive external-edit warnings.
- R2-S4 and R3-S6: Incremental refresh should rehydrate from session drafts after restart.
- R3-S3: Preflight should check single-writer lock availability before serve.
- R4-S3 and R4-S4: Inspect JSON and typed codes should expose lock holder, draft state, and `session_expired`/`rate_limited`.
- R4-S5: Draft persistence and test-capture should respect preview-only vs write-enabled modes.
- R5-S2 and R5-S5: Batch review queue and friction prefill benefit from draft state and search/filter.

**Disagreements**:
- None.

---

## Requirements Coverage Matrix — R6

Analysis only (not triage). `Covered` = plan already fully maps it; `Partial` = plan maps it but R6 found a quick-win/operational gap; `Gap` = absent.

| Requirement | Plan Milestone(s) | Coverage | Notes / Gap (R6 suggestion) |
| ---- | ---- | ---- | ---- |
| FR-1 (experience config) | M3 | Partial | Field search should index M3 metadata (R6-S4). |
| FR-2 (deterministic UI gen) | M4 | Partial | Capture handlers need rate limit and session expiry (R6-S6). |
| FR-3 (two front doors, full fidelity) | M4, M5 | Partial | Draft state and search must parity across surfaces (R6-S1/R6-S4). |
| FR-4 (resumable progress) | M4 | Partial | Session draft persistence is core resumability gap (R6-S1). |
| FR-5 (pre-populate) | M1 | Covered | No new R6 gap. |
| FR-6 (per-field state) | M1 | Partial | Search/filter operates on field state badges (R6-S4). |
| FR-7 (readiness) | M2 | Covered | No new R6 gap. |
| FR-8 (round-trip safety) | M6 | Partial | test-capture harness + YAML escape hatch (R6-S5/R6-S7). |
| FR-9 (read-only agentic tools) | M5 | Covered | Drafts remain propose-only for agentic layer. |
| FR-10 (extraction-aware conversation) | M1, M5 | Partial | Conversation can reference draft vs applied state (R6-S1). |
| FR-11 (guided next-step) | M5 | Partial | Search complements next-action navigation (R6-S4). |
| FR-12 (friction capture in-flow) | M5/M6 implied | Partial | Round-trip reject escape hatch may trigger friction prefill (R6-S7). |
| FR-13 (MCP entry) | M7 | Partial | Inspect JSON should expose draft/lock state (R6-S1/R6-S3). |
| FR-14 (CLI entry) | M7 | Partial | Add test-capture CI command (R6-S5). |
| FR-15 (observability) | M8 | Partial | Emit lock contention, draft restore, rate-limit events (R6-S3/R6-S6). |
| FR-NEW-1/2 (write builder/read exception) | M6 | Partial | Single-writer lock + proactive external-edit warnings (R6-S2/R6-S3). |
| FR-NEW-3 (per-field attribution) | M6 | Partial | test-capture asserts attribution in CI (R6-S5). |
| FR-NEW-4 (local app-serving) | M7 | Partial | Rate limit + session expiry extend trust boundary (R6-S6). |
| FR-NEW-5 (`defaulted` state) | M1 | Covered | Search can filter defaulted fields (R6-S4). |
| FR-NEW-6 (`value_path`↔file mapping) | M3 | Covered | No new R6 gap. |
