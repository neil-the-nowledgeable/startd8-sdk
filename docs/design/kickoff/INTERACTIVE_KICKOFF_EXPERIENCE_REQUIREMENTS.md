# Interactive Visual Kickoff Experience — Requirements

**Version:** 0.5 (Post-CRP R5–R6)
**Date:** 2026-06-25
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `INTERACTIVE_KICKOFF_EXPERIENCE_PLAN.md` (v1.0)
**Related:** `CONCIERGE_MCP_REQUIREMENTS.md` (v0.4), `KICKOFF_AUTHORING_CONTRACT.md`, `KICKOFF_INPUT_PACKAGE_GUIDE.md`, `CONCIERGE_FRICTION_LOG_NAVIG8.md`

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass read the real code (not the v0.1 summaries) and revealed **10 discoveries**, resolving
> 7 of 8 open questions and surfacing 6 missing requirements. The "dogfood the deterministic UI
> machinery" framing was **materially wrong at two layers** and survives only at the widget/theme layer.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **FR-2/P5:** the **flows** primitive is "the spine" that captures kickoff field values per step. | A flow writes ONLY the `step_field` column on a draft DB row (`flow_generator.py:96-99,107-109`); per-step content is an empty tolerant include (`flow_generator.py:135`). Flows give *resumable step state only* — **no value capture, no write-back**. | **Reframed FR-2.** Value capture is new code. Dogfood survives only at `htmx_generator._form_input_html` widgets (`htmx_generator.py:443`) + `presentation_polish` theming. |
| **FR-1:** the kickoff manifest could be "a new manifest *kind* the grammar knows" so flows/forms render it unchanged (true dogfood). | No manifest-kind registry exists — every parser is hand-wired into `extract_manifests` (`extract.py:151-228`). Adding a kind = new parser + extractor + round-trip + generator wiring. | **Reframed FR-1 → SDK-internal config** (OQ-1 resolved). The grammar-layer dogfood claim is false. |
| **FR-6:** render `extracted` / `not_extracted` / **`ambiguous`** states. | The real status vocabulary is `EXTRACTED / NOT_EXTRACTED / **DEFAULTED**` (`models.py:19-22`). There is **no `ambiguous` status**; ambiguity is free-text in `reason` (`entities.py:342,365`). `defaulted` (provenance-critical) was omitted. | **Narrowed + added** (FR-6 rewritten; added FR-NEW-5 for `defaulted`). |
| **FR-9/FR-12:** wire `instantiate-kickoff` and `log-friction` into the agentic `ToolRegistry` so the loop can instantiate / log friction. | A read-only dispatch floor refuses every non-`survey`/`assess` action from the chat surface (`handle_concierge_read`, `core.py:272-285`; `chat.py:7-12`). | **Reframed FR-9/FR-12 to read/propose-only** (OQ-8 resolved). Writes stay CLI-applied. |
| **FR-8:** "write captured values back into kickoff docs" assumes a write path exists. | Only `build_instantiate_plan` (whole-template projection) and `build_friction_entry` (jsonl append) exist (`writes.py:81,126`); neither edits a field into `inputs/*.yaml`. And writes.py **never reads existing consumer content by policy** (FR-C3a, `writes.py:5-8`) — but a per-field merge must read+rewrite the YAML. | **Added FR-NEW-1/2/3.** New write builder + an explicit FR-C3a read-disclosure exception + per-field round-trip attribution. |
| **FR-3/FR-14:** the web app is "served locally," consistent with shared concierge logic. | `startd8 serve` serves the *workflow* API, not generated apps (`cli.py:1352`); `assembler.py` only emits `(path,text)` pairs; nothing in-SDK serves a generated FastAPI app. | **Added FR-NEW-4** (app-serving plumbing; OQ-3 resolved → throwaway local app). |
| **FR-7:** surface `build_assess` readiness. | Exactly correct and already built (`core.py:155-224`). | **Resolved — FR-7 is essentially free.** |
| **OQ-5:** extraction may need per-session caching for cost. | Extraction is pure string parsing, `$0`, synchronous (`extract.py:42-43`). | **Resolved — live per-capture is fine;** caching is an optional optimization. |

**Resolved open questions:**
- **OQ-1 → SDK-internal config.** No manifest-kind registry; FR-1 is SDK-internal data, not a grammar extension.
- **OQ-2 → flows give step-state only.** Value capture is new code (not the flows router).
- **OQ-3 → throwaway local app + new serve plumbing.** MCP (stdio) cannot serve/launch.
- **OQ-4 → safe-writer at human privilege, with a required FR-C3a exception** for reading existing YAML to merge.
- **OQ-5 → live extraction is fine** (`$0`, synchronous).
- **OQ-7 → wrap-then-guide; CLI is sole writer.** The experience runs after/around `instantiate-kickoff`.
- **OQ-8 → read-only agentic allow-list** (`survey`, `assess`, new `field_states`); structurally enforced.
- **OQ-6 → STILL OPEN** (product decision): TUI = conversational-primary vs full-fidelity in both surfaces.

---

## 1. Problem Statement

Today the project kickoff process is **document authoring**. A user (or the concierge) instantiates
a kickoff package (`docs/kickoff/` — intro, 4 input-domain YAMLs, optional REQUIREMENTS/PLAN/TEST_USERS
templates), then **hand-edits markdown and YAML** to declare entities, pages, views, observability,
conventions, and build preferences. The manifest-extraction grammar
(`src/startd8/manifest_extraction/`) then deterministically reads those documents into structured
manifests, which drive the `$0` codegen cascade.

This works, but the authoring surface is **raw text against a closed grammar the author cannot see**.
The friction log (`CONCIERGE_FRICTION_LOG_NAVIG8.md`) records the cost: existing PRDs don't match the
extraction headings (F-4), authors squeeze domain invariants into the wrong fields (F-6), and the
"is this complete enough to build?" question is answered only by running `startd8 kickoff check` and
reading a CLI report. There is **no guided, visual, conversational way to do a kickoff** — no surface
that shows the author what the grammar already understood, what is still missing, and what to type next.

Meanwhile the SDK already owns every piece needed to build that surface:

| Component | Current State | Gap for an interactive kickoff |
|-----------|--------------|-------------------------------|
| **Manifest extraction** (`manifest_extraction/`) | Deterministically parses prose → manifests; per-value traceability (`ExtractionRecord`/`SourceRef`); round-trip gated; reports `extracted` / `not_extracted` status | Records are computed for a *batch* and read by the CLI checker. Nothing renders them as a live, per-field "known / missing / ambiguous" view that a UI can drive. |
| **Concierge** (`concierge/`) | `survey`/`assess` shipped (read-only $0); `instantiate-kickoff`/`log-friction`/`derive-contract` write path; MCP tool + CLI | Returns JSON dicts. No human-facing visual/conversational front-end; the "experience" is a tool call + a terminal dump. |
| **Deterministic UI gen** (`backend_codegen/`, `flow_generator.py`, `presentation_polish/`) | Generates HTMX/Jinja2 CRUD, multi-step **flows** (state machine over a draft entity), pages, WCAG-AA themes — all `$0` from a manifest | Never pointed at the kickoff process itself. The SDK does not generate its *own* front-end for kickoff. |
| **Agentic capabilities** (`agents/agentic.py`, `tui/agentic_chat.py`, MCP server) | `AgenticSession` tool-use loop + `ToolRegistry`; TUI agentic chat (opt-in); MCP exposes ~18 tools incl. `startd8_concierge`; streaming; OTel spans | The agentic loop has an **empty** tool registry in the TUI (conversation only). Concierge/extraction/kickoff operations are not wired as tools the loop can call to *drive* a kickoff conversation. |

**What should exist:** a **conversational, visual kickoff experience** that (a) extracts what the
grammar already understands from whatever inputs exist, (b) **deterministically generates the SDK's
own front-end** for kickoff (web + TUI) using the same `$0` UI machinery the SDK ships for customer
apps, and (c) lets the agentic loop + concierge **guide** the author turn-by-turn — explaining inputs,
surfacing gaps, proposing values, and logging friction — until the kickoff is build-ready.

---

## 2. Guiding Principles (inherited)

- **P1 — Determinism first.** The kickoff UI is a *pure function* of a kickoff manifest + the current
  extraction state. No LLM is required to render it. (Bucket-1 discipline; `$0` to build the surface.)
- **P2 — The grammar is the source of truth.** The experience *exposes* the closed manifest grammar;
  it never invents a parallel one. Every field the UI shows maps to a grammar value path.
- **P3 — Extraction is read-only; writes are CLI-privileged.** Per `FR-C3`, the conversational/visual
  layer may *propose* edits but durable writes to the consuming project go through the concierge
  safe-writer at human privilege. The agentic loop's kickoff tools are read/propose by default.
- **P4 — Translate, don't invent (F-4/F-9).** When inputs already exist (PRDs, Pydantic models,
  fixtures), the experience reformats/maps them into the grammar; it does not ask the author to
  retype what is already on disk.
- **P5 — Dogfood.** The kickoff front-end is generated by the *same* deterministic UI machinery the
  SDK uses for customer apps (`flow_generator`, `htmx_generator`, `presentation_polish`). If the
  kickoff UI needs a capability the machinery lacks, that is a gap in the machinery, fixed once.

---

## 3. Requirements

### A. Kickoff as a generated artifact (deterministic UI)

- **FR-1 — Kickoff experience config** *(reframed v0.2: SDK-internal config, NOT a grammar kind)*.
  Define an **SDK-internal** declarative config (`src/startd8/kickoff_experience/manifest.py`) that
  describes the kickoff *experience* as data: the ordered steps (one per input domain +
  entities/relationships + completeness), the fields per step, each field's grammar `value_path`,
  type/widget hint, help prose, and provenance default. This is consumed only by the kickoff generator;
  it is **not** a new manifest kind the extraction grammar parses (no manifest-kind registry exists —
  `extract.py:151-228`). Per-field help prose + provenance live here, since no manifest expresses them.
  - **Acceptance (R2–R4) — config lint (R3-F2):** The FR-1 config is linted before M4/M5 build: every
    required field must have a **unique** `value_path`, **exactly one** `inputs/*.yaml` write mapping
    (FR-NEW-6), a supported widget type, grammar help, allow-list membership, and canonical view-model
    fixture coverage. The linter **fails** on duplicate value paths, missing target file/key, unsupported
    widget, absent help, or unmapped required fields.
- **FR-2 — Deterministic kickoff UI generation** *(reframed v0.2: partial dogfood)*. Generate the
  kickoff front-end deterministically (`$0`, no LLM) from the FR-1 config. **Reuse** the field→widget
  mapping (`htmx_generator._form_input_html`) and `presentation_polish` WCAG-AA theming directly. The
  resumable multi-step *shape* mirrors the flows router, but **value capture and per-step POST handlers
  are new code** — the flows primitive persists only a step pointer, not field values
  (`flow_generator.py:96-99`). Flows are not the value-capture spine.
  - **Acceptance (R5–R6) — generated-app freshness (R5-F1):** The generated kickoff app's metadata
    carries a **fingerprint** of the FR-1 config + renderer/template/theme versions + SDK version; on
    next start a mismatch must cause **regeneration or refusal-with-stable-reason-code** before serving,
    never serving stale fields/handlers. Changing the FR-1 config/template and restarting triggers
    detected regenerate/refuse. *(Cross-ref FR-NEW-4.)*
- **FR-3 — Two front doors, full fidelity in both** *(OQ-6 resolved 2026-06-25)*. The same kickoff
  experience is reachable from (a) the **web** front-end (a throwaway local FastAPI/HTMX app the CLI
  generates + serves — see FR-NEW-4) and (b) the **TUI** (`startd8 tui` conversational mode). **Both
  surfaces render the complete experience** — the same steps, extraction-state badges (FR-6), and
  readiness meter (FR-7) — sharing the M1 extraction-state service and M2 readiness data. They differ
  only in rendering (Rich vs HTMX/Jinja2). **Cross-surface parity is a test requirement:** a given
  project state must produce equivalent step/field/status/readiness output in both surfaces.
  - **Acceptance (R1) — Canonical state representation:** Name a typed shared view-model (fields:
    `step`, field `value`, `status` badge, `source` ref, `readiness`) that BOTH surfaces consume. The
    parity test asserts both surfaces are **pure functions of one serialized instance** of this
    view-model across a state matrix — it is the defined oracle for "equivalent output." The derived
    "ambiguous" UI label is computed on this view-model (single derivation point; see FR-6/FR-NEW-5).
  - **Acceptance (R5–R6) — visual/text regression (R5-F4):** Parity coverage includes **golden
    web-screenshot and Rich text snapshots** for the missing/defaulted/error/conflict/final-review/
    preflight-failure states — so a render that clips, hides labels, or formats a status differently is
    caught even when state-level data parity passes. Snapshots compare web and TUI for the seeded fixture
    state matrix. *(Cross-ref FR-6/FR-7.)*
- **FR-4 — Resumable progress.** Kickoff is a multi-step flow with server-side step state. The author
  can leave and resume; the current step persists. *(The flows router shape is reusable for step
  state; partial-answer persistence rides the FR-8 write-back path, not the flows draft row.)*

### B. Grammar-driven value extraction & pre-population

- **FR-5 — Pre-populate from existing inputs.** On entry, run manifest extraction against whatever
  kickoff inputs/requirements already exist in the project. For every field in the FR-1 manifest,
  show its current value if the grammar extracted one, sourced via `SourceRef` (doc/heading/row).
  - **Acceptance (R2–R4) — source inventory (R3-F4):** The experience shows which documents/files were
    inspected, which produced `ExtractionRecord`s, which expected kickoff inputs are missing, and which
    candidate sources were ignored as out-of-grammar (with reason) — so an author can see *why* expected
    existing content did not pre-populate. Both surfaces render identical source counts and ignored-source
    reasons.
  - **Acceptance (R2–R4) — no hidden broad read (R3-F7):** The source inventory reports **only** the
    files/directories the existing extraction/survey path already scans; it does **not** expand reads
    beyond the configured kickoff/source roots. Against a project with unrelated files, the inventory
    excludes that unrelated content and records only the configured scan roots. *(Cross-ref FR-10.)*
- **FR-6 — Per-field extraction state** *(narrowed v0.2 to the real 3-state model)*. Render each
  field's extraction status using the actual `Status` vocabulary — `extracted` (with source + value),
  `defaulted` (a value the grammar filled in, provenance-critical; see FR-NEW-5), or `not_extracted`
  (missing — needs input) — per `models.py:19-22`. "Ambiguous" is a **derived UI label** over the
  free-text `reason` on `not_extracted` records (slug collision, unknown enum, unparseable verb —
  `entities.py:342,365`), not a first-class status; reasons are not a closed vocabulary. The UI's job
  is to make the gap list and the "why" legible.
  - **Acceptance (R1) — single derivation point:** The derived "ambiguous" UI label over free-text
    `reason` is computed in **ONE** place — the FR-3 canonical view-model — so both surfaces classify
    identically (no per-surface, independent `reason` pattern-matching, which would be nondeterministic
    across surfaces). The recognized `reason` patterns (slug collision, unknown enum, unparseable verb)
    vs. the catch-all are defined at that single point. *(See FR-NEW-5.)*
  - **Acceptance (R2–R4) — incremental post-capture refresh (R2-F6):** After a field-capture apply, the
    experience re-runs extraction/readiness and updates the affected field state, gap list, and readiness
    meter **in the same session** without restart/reload — no stale "missing" badge after a successful
    capture.
  - **Acceptance (R2–R4) — debounced refresh / stale-result discard (R3-F6):** After rapid edits,
    previews, or applies, extraction/readiness updates are **debounced**, show a transient "checking
    grammar" state, and **discard stale results** if a newer edit arrives — only the latest result updates
    the canonical state and both surfaces.
- **FR-7 — Build-readiness surface.** Surface the `assess` readiness report (`build_assess`,
  wireframe-backed) as a live progress indicator: which input domains are provisioned, the readiness
  score, and the blocking gaps — updated as the author fills steps.
  - **Acceptance (R5–R6) — performance budgets (R5-F3):** Initial extraction/readiness, post-capture
    refresh, and first render have defined **performance budgets**; when exceeded, the UI shows a
    "large project / still checking" state rather than stale or frozen output. A performance fixture
    records timings for small/medium/large input packages and asserts a warning/telemetry signal above
    threshold. *(Cross-ref FR-5, FR-15.)*
- **FR-8 — Round-trip safety** *(narrowed v0.2: per-field attribution is new work)*. Any value the
  experience captures and writes back into kickoff docs must re-parse cleanly through the grammar (the
  `FR-WPI-4` round-trip gate). A captured value that would fail extraction is rejected at capture time,
  not at build time. *Note:* the existing gate raises `RoundTripError` for the **whole** emitted
  manifest (`extract.py:233-239`), so a per-field capture wrapper that attributes the failure to the
  single offending `value_path` is required (FR-NEW-3).
  - **Acceptance (R1) — cross-field / interaction failures:** When a captured value re-parses cleanly
    **alone** but fails only in manifest context (a relationship to an undeclared entity, an enum that
    needs a sibling value), the capture is **not** a hard whole-capture reject. The spec is to either
    (a) attribute with a `"depends on <other value_path>"` message, or (b) classify as **deferred
    validation** (re-checked at build time). A blanket capture-time reject would deadlock the author
    from entering a relationship before its target entity exists.

### C. Conversational / agentic layer

- **FR-9 — Concierge read operations as agentic tools** *(reframed v0.2: read/propose-only)*. Wire the
  **read-only** concierge actions (`survey`, `assess`) plus the new read-only `field_states` (FR-5/FR-6)
  into the `AgenticSession` `ToolRegistry` so the agentic loop can *drive* a kickoff conversation:
  survey the project, assess readiness, and report what the grammar understands. The read-only dispatch
  floor (`handle_concierge_read`, `core.py:272-285`) **structurally refuses** every other action from
  the chat surface, so `instantiate-kickoff`/`log-friction`/`derive-contract` are **not** agentic tools
  — the loop may at most *propose* them; the human applies via CLI (P3/FR-C3, OQ-8).
  - **Acceptance (R1) — enforcement:** The new `field_states` tool is itself enforced by the read-only
    floor (`handle_concierge_read`), not wired through a path that bypasses it. The kickoff registry's
    tool set is **exactly** `{survey, assess, field_states}`, and **no write action is reachable** —
    each write action name (`instantiate-kickoff`/`log-friction`/`derive-contract`) is refused at the
    dispatch floor.
- **FR-10 — Extraction-aware conversation.** The conversational layer can answer "what does the grammar
  understand about X?", "what's missing to build?", and "what should I type for field Y?" by reading
  the live extraction records (FR-5/FR-6) — grounded in actual `ExtractionRecord`s, not free-form
  speculation.
- **FR-11 — Guided next-step.** At each step the experience proposes the next action (the highest-value
  unfilled field or the blocking gap from FR-7), so the author is never staring at a blank grammar.
  - **Acceptance (R2–R4) — deterministic next-action ranking (R2-F3):** "Highest-value" is a defined,
    testable ranking: **readiness blockers first**, required `not_extracted` fields second, `defaulted`
    values needing human review third, optional fields last; tie-break by FR-1 step order. A fixture with
    mixed blockers/missing/defaulted fields returns **one** expected top recommendation, identical in both
    surfaces.
- **FR-12 — Friction capture in-flow** *(reframed v0.2: propose-only over agentic; apply via CLI/web)*.
  When the author hits a mismatch the grammar can't take (the F-1..F-10 friction class), the experience
  offers to log it via `log-friction`. The durable append happens at human/CLI privilege (or the local
  web app's safe-writer), never as an unattended agentic-loop write.
  - **Acceptance (R1) — web-apply authorization:** A **foreground, same-origin human POST with a
    session/CSRF token IS the authorization event** for a web-surface friction/value apply. An
    unauthenticated or cross-origin POST does **not** durably write — so the web app cannot become the
    write bypass the read-only floor was designed to prevent. *(Cross-ref FR-NEW-1.)*
  - **Acceptance (R2–R4) — confirmed-write wording (R2-F8):** The agentic/chat layer may say
    "I prepared a preview" or "you can apply this," but may say **"saved/captured" only after** a
    safe-writer (`apply_write_plan`) result confirms a durable write. A conversation snapshot test asserts
    no "saved" wording appears before apply success. *(Applies to FR-9 propose-only as well.)*
  - **Acceptance (R2–R4) — secret/path redaction (R4-F7):** Failure reason codes, previews, source
    inventory, and any handoff artifact **redact local secrets and absolute paths** where possible while
    keeping enough relative path / source-ref detail for debugging — a fixture with `.env`-like values and
    absolute paths produces a redacted external artifact with relative safe references. *(Cross-ref FR-10,
    FR-15.)*

### D. Surfacing & orchestration

- **FR-13 — MCP entry point.** Expose starting/continuing the interactive kickoff via the MCP server
  (a tool or an extension of `startd8_concierge`) so an IDE/agent harness can launch the experience
  and drive it programmatically, consistent with the existing concierge MCP surface and its annotations
  (`readOnlyHint`/`destructiveHint`/`idempotentHint`).
- **FR-14 — CLI entry point.** A CLI command launches the interactive kickoff (generates the front-end
  if needed, serves it / opens the TUI), consistent with the `two-front-doors` concierge pattern
  (`handle_concierge_tool` shared logic).
  - **Acceptance (R2–R4) — preflight/doctor (R3-F3):** Before serving, a preflight phase verifies
    `docs/kickoff/inputs` exists or can be instantiated, target files are writable/confined, stale scratch
    is recoverable, port binding is possible, and browser launch has a TUI/manual-URL fallback. Simulated
    missing inputs / unwritable dir / occupied port / stale scratch / no browser each produce an actionable
    message and **avoid a partial serve**.
  - **Acceptance (R2–R4) — machine-readable inspect/dry-run (R4-F3):** `startd8 kickoff inspect --json`
    (or `start --dry-run --json`) emits canonical state, source inventory, readiness, planned next action,
    and preflight status **without serving web/TUI or writing files** — no port opens, no scratch app is
    generated, no writes occur; output is deterministic for the demo fixture.
  - **Acceptance (R2–R4) — inspect JSON compatibility promise (R4-F8):** The inspect/dry-run JSON includes
    a `schema_version` and tolerates **additive** fields, so IDE/MCP agents consuming it are not broken by
    later additions; a schema test validates `schema_version` and old consumers ignore unknown fields.
    *(Cross-ref FR-13.)*
  - **Acceptance (R5–R6) — headless test-capture (R6-F5):** A headless `startd8 kickoff test-capture`
    (or equivalent) exercises `build_capture_plan` and per-field round-trip against a **fixture matrix
    without serving UI or opening ports** — giving CI a write-path regression that complements the
    read-path inspect/dry-run. The fixture matrix passes/fails with **per-field attribution** output and
    **no port is opened**. *(Cross-ref FR-8.)*
- **FR-15 — Observability.** The kickoff experience emits OTel spans consistent with the agentic-loop
  conventions already in place (`agentic.session`/`turn`/`tool_call`) plus kickoff-specific events
  (step entered, field captured, gap closed, friction logged) for a kickoff funnel/dropoff view.
  - **Acceptance (R2–R4) — kickoff funnel metrics (R2-F7):** FR-15 emits, with stable event names and
    attributes, the funnel: session started, first field captured, next-action accepted/skipped,
    defaulted value reviewed, write preview abandoned/applied, round-trip rejected, friction logged, and
    teardown status — so a dashboard query can compute completion/dropoff and write-failure rates.

### E. Requirements surfaced by planning (new in v0.2)

- **FR-NEW-1 — Value-capture write builder.** Add a concierge write builder (e.g.
  `build_capture_plan(...)` in `writes.py`) that produces a `WritePlan` editing
  `docs/kickoff/inputs/*.yaml` for a single captured field, applied only via `apply_write_plan`
  (`safe_write.py:200`) at CLI/human privilege. No such per-field write path exists today
  (`writes.py` only does whole-template projection + jsonl append).
  - **Acceptance (R1) — allow-list / confused-deputy guard:** The captured `value_path` is constrained
    to a **server-side allow-list** derived from the FR-1 config (the FR-NEW-6 mapping). A `value_path`
    not in the mapping, or containing traversal (`../`), is **rejected before `apply_write_plan`** —
    a value_path from the web/agentic surface cannot redirect the merge-write outside
    `docs/kickoff/inputs/`.
  - **Acceptance (R2–R4) — pre-apply capture preview (R2-F1):** Before any write is applied, both web
    and TUI render a preview showing target file, `value_path`, old value, new value, provenance/default
    status change, and a field-scoped diff; the preview matches the eventual `WritePlan` and no file
    changes until explicit confirmation.
  - **Acceptance (R2–R4) — typed failure reason codes (R4-F4):** Capture failures map to **stable reason
    codes** (`stale_hash`, `roundtrip_field`, `roundtrip_dependency`, `unsafe_value_path`, `csrf_refused`,
    `port_bind_failed`, `scratch_gc_failed`, `permission_denied`) each carrying user-safe remediation text
    and an OTel attribute; the same code/text is used across surfaces and telemetry.
- **FR-NEW-2 — FR-C3a read-disclosure exception.** Per-field merge requires READING the existing
  `inputs/*.yaml` (to preserve sibling keys), which the current write builders forbid by policy
  (`writes.py:5-8`). This exception must be explicitly authorized and bounded: the writer may read the
  *target kickoff input file only*, for the sole purpose of merge-write, never broader consumer content.
  - **Acceptance (R1):**
    - (a) The read-then-merge writer reads **only** the single target `inputs/<domain>.yaml`; no other
      consumer file is read.
    - (b) All sibling keys **and their comments/ordering** are preserved byte-for-byte; only the captured
      key's value changes.
    - (c) The write **refuses** if the target file's on-disk hash changed since it was read (stale-read
      precondition).
  - **Acceptance (R2–R4) — stale-write conflict recovery (R4-F1):** When the target file hash changes
    between preview/read and apply, the experience **preserves the proposed value**, re-reads the latest
    file, shows an updated diff, and offers **reload / reapply-to-latest / discard** — a stale apply
    refuses the write *and* generates a new preview against the updated file rather than discarding the
    author's effort.
  - **Acceptance (R5–R6) — proactive external-edit warning (R6-F2):** When a target `inputs/*.yaml`
    hash changes **during an active session** (not only at apply time), the experience surfaces a
    **non-blocking warning** with reload / keep-editing choices before apply; the user can reload the
    latest file state without clobber. A mid-session external edit triggers the warning. *(Cross-ref
    FR-8; complements the apply-time stale-read refusal above.)*
- **FR-NEW-3 — Per-field round-trip attribution.** Wrap the batch `RoundTripError` (`extract.py:233`)
  so a captured value's failure is attributed to its single `value_path`, enabling FR-8's
  capture-time (not build-time) rejection with an actionable field-level message.
  - **Acceptance (R1) — cross-field / interaction failures:** Per FR-8's interaction clause, when no
    single offending `value_path` exists (the failure is genuinely relational), attribution falls back
    to a `"depends on <other value_path>"` message OR the capture is classified as **deferred
    validation** — never a hard whole-capture reject that deadlocks entering a relationship before its
    target exists.
- **FR-NEW-4 — Local app-serving plumbing.** Generating + serving a throwaway local FastAPI app
  (scratch dir, uvicorn lifecycle, port selection, teardown) is unspecified and has no precedent
  (`startd8 serve` serves the workflow API, not generated apps — `cli.py:1352`). Specify the serve
  lifecycle for FR-3/FR-14, including teardown on session end.
  - **Acceptance (R1) — teardown / leak:**
    - On session end, **Ctrl-C**, and **parent crash**, the served app releases its port and leaves
      **no child process** (no orphaned listener, no zombie uvicorn).
    - The scratch dir is **removed** on teardown.
    - **Stale scratch** from a prior crashed run is GC'd on the next launch.
  - **Acceptance (R5–R6) — generated-artifact cleanup policy (R5-F8):** Because freshness fingerprinting
    (R5-F1) creates more scratch variants, preflight enforces a cleanup policy — keep only the latest N
    scratch/generated versions, or remove all stale versions — and emits a **cleanup count** in telemetry.
    Creating multiple stale fingerprints then running preflight removes/reports them per policy.
  - **Acceptance (R5–R6) — single-writer lock (R6-F3):** At most **one write-capable kickoff session per
    project root**; a concurrent write-capable session is refused with a clear message **naming the lock
    holder**, and the lock is released on teardown. *(Cross-ref FR-NEW-1/2, FR-14.)*
  - **Acceptance (R5–R6) — capture rate limiting / token expiry (R6-F6):** The local web capture surface
    applies **POST rate limiting** and **session/CSRF token expiry**, each with stable reason codes
    (`rate_limited`, `session_expired`) and remediation text — closing stale-tab replay and local-script
    burst-POST gaps that loopback+CSRF (FR-12) alone does not. Burst POSTs are rejected with the stable
    code; an expired token cannot apply. *(Cross-ref FR-12 authorization acceptance, FR-NEW-1 reason
    codes.)*
- **FR-NEW-5 — `defaulted` state in the UI.** FR-6 must render the real `DEFAULTED` status
  (`models.py:21`) distinctly. It is provenance-critical: a defaulted value is an estimate that must be
  visibly distinguishable so it is never silently promoted (NR-2 discipline).
  - **Acceptance (R1) — single derivation point:** The derived "ambiguous" UI label (over free-text
    `reason`) is computed in **one** place (the FR-3 canonical view-model), so both surfaces classify
    identically. The recognized `reason` patterns (slug collision, unknown enum, unparseable verb) vs.
    the catch-all are defined there; no surface pattern-matches `reason` independently. *(See FR-6.)*
- **FR-NEW-6 — `value_path` ↔ inputs-file mapping.** FR-1's per-field `value_path` must map to a
  concrete `inputs/*.yaml` file + key for write-back. This mapping table is new, lives in the FR-1
  config, and is load-bearing for FR-NEW-1.
  - **Acceptance (R1) — allow-list / traversal guard:** The captured `value_path` is constrained to a
    **server-side allow-list** derived from this mapping (the FR-1 config). A `value_path` not present
    in the mapping, or containing traversal (`../`), is **rejected before `apply_write_plan`** — it
    cannot redirect the merge-write outside `docs/kickoff/inputs/`. *(See FR-NEW-1.)*

### F. Phased / Later-Phase Requirements (post-v1, accepted but deferred)

> Accepted in CRP R2–R4 as valuable, but scope-expanding beyond the v1 surface. Tracked here so later
> reviewers do not re-propose them; **not** inlined into the v1 FRs above.

- **[Phase 2 — Should-have]** Session-scoped **undo/rollback** for captured field writes: restore the
  immediately previous file content/hash for a capture until session teardown (no new durable DB).
  *(Source: R2-F2; relates to FR-8 / FR-NEW-4.)*
- **[Phase 2 — Should-have]** Per-field **value/"what this unlocks" help** in the FR-1 config (in
  addition to grammar "what to type" help), to motivate completion. *(Source: R2-F4; relates to FR-1.)*
- **[Phase 2 — Should-have]** A seeded **demo/parity fixture** covering every field status
  (`extracted/defaulted/not_extracted` + derived ambiguous), a readiness blocker, a cross-field
  dependency, and one write preview — usable as onboarding and as broad parity-test input.
  *(Source: R2-F5; relates to FR-3 / FR-6 / FR-7.)*
- **[Phase 2 — Should-have]** A **no-progress-loop guard** for guided next-step: if the same
  recommendation is skipped/rejected repeatedly, offer friction logging or a different field.
  *(Source: R2-F9; relates to FR-11 / FR-12.)*
- **[Phase 2 — Should-have]** A full **WCAG 2.2 AA accessibility suite** for the generated forms:
  programmatic labels, visible focus, keyboard-only operation, non-color-only status/error/defaulted
  indicators, 44px touch targets, 200% zoom without clipping, mobile viewport zoom not disabled.
  *(Source: R3-F1; relates to FR-2 / FR-3.)*
- **[Phase 2 — Should-have]** A final **build-readiness review step** before handoff to `kickoff check`:
  summarize remaining blockers, deferred cross-field validations, unreviewed defaulted values, latest
  applied/prepared writes, and the exact next CLI command (does not replace the authoritative checker).
  *(Source: R3-F5; relates to FR-7 / FR-8 / NR-6.)*
- **[Phase 2 — Should-have]** An **accessibility fixture state** exercising a required-field error, a
  `defaulted` badge, an ambiguous-derived label, and a disabled/unavailable next action with explanatory
  text — to cover the error/disabled/status states where accessibility failures hide.
  *(Source: R3-F8; relates to FR-3 / FR-6 / FR-11.)*
- **[Phase 2 — Should-have]** A **field dependency graph** in the FR-1 config (`depends_on`, `unlocks`,
  `blocks_build_when_missing`) as the single source feeding attribution, next-action ranking, final
  review, and "what this unlocks" help. *(Source: R4-F2; relates to FR-1 / FR-7 / FR-8.)*
- **[Phase 2 — Should-have]** Explicit **feature modes** — read-only inspect, preview-only capture,
  write-enabled local app, and demo — defaulting to read-only/preview until write/serve safety tests
  pass, for staged rollout. *(Source: R4-F5; relates to FR-9 / FR-12 / FR-13 / FR-14.)*
- **[Phase 2 — Should-have]** An optional **handoff packet** (Markdown/JSON) summarizing captured values,
  remaining blockers, reviewed defaults, ignored sources, friction items, and next commands — a
  deterministic projection only, clearly marked non-authoritative. *(Source: R4-F6; relates to FR-7 /
  FR-8 / FR-12 / NR-3 / NR-6.)*
- **[Phase 2 — Should-have]** A **batch review queue**: review multiple missing/defaulted fields and
  their previews together, while apply still executes as separate per-field/per-file safe writes with
  individual success/failure status. *(Source: R5-F2; relates to FR-8 / FR-11 / FR-NEW-1.)*
- **[Phase 2 — Should-have]** **Deterministic friction prefill**: when a next action is skipped, a source
  is ignored, or a typed failure occurs, pre-populate a friction-log preview (candidate class, evidence,
  implication) requiring human confirmation before durable append. *(Source: R5-F5; relates to FR-12 /
  FR-15.)*
- **[Phase 2 — Should-have]** **Quick navigation** — web keyboard shortcuts/command palette and TUI
  commands that jump to next blocker, next defaulted value, source inventory, final review, and capture
  preview with visible focus/selection. *(Source: R5-F6; relates to FR-3 / FR-11.)*
- **[Phase 2 — Should-have]** **Batch graceful degradation**: if one field in a batch fails round-trip,
  stale-hash, or authorization, other fields report independent status and no successful write is rolled
  back unless the user explicitly requests undo. *(Source: R5-F7; relates to FR-8 / FR-NEW-1.)*
- **[Phase 2 — Should-have]** **Session draft persistence**: unapplied field values, current step, and
  review-queue position stored in the M7 scratch area and restored across browser refresh, TUI restart,
  and surface handoff until teardown or explicit discard. *(Source: R6-F1; relates to FR-4 / FR-NEW-4.)*
- **[Phase 2 — Should-have]** **Field search/filter** over steps and fields by name, `value_path`,
  status, and blocker/deferred flags, for large-package discoverability beyond guided next-step.
  *(Source: R6-F4; relates to FR-1 / FR-11.)*
- **[Phase 2 — Should-have]** A **round-trip reject escape hatch**: on per-field round-trip failure,
  offer a copyable field-scoped YAML snippet (with provenance comment) for manual paste, with no
  automatic write. *(Source: R6-F7; relates to FR-8 / FR-NEW-3.)*
- **[Phase 2 — Should-have]** Surface **draft-persistence and single-writer-lock state** in inspect/
  dry-run JSON (`draft_fields`, `lock_holder`, `lock_age`) for agents and support tooling.
  *(Source: R6-F8; relates to FR-13 / FR-14.)*

---

## 4. Non-Requirements

- **NR-1 — Not a new grammar.** This does not define a second authoring grammar or change the manifest
  grammar. It is a *surface over* the existing grammar.
- **NR-2 — Not LLM-authored content.** The experience does not generate the *real* kickoff content
  (bucket 4). It captures human/authored values and pre-populates from existing inputs. AI proposals
  (if any) are estimates that are never silently promoted (provenance discipline).
- **NR-3 — No new persistence layer beyond captured values** *(clarified v0.2)*. Captured field values
  persist into the kickoff docs themselves (`docs/kickoff/inputs/*.yaml`) via the FR-8 write-back path —
  the docs ARE the store. Step-position state may reuse the flows router shape. Do not introduce a
  separate kickoff database. *(v0.1 wrongly assumed the flows draft entity persists answers; it persists
  only a step pointer — see §0.)*
- **NR-4 — Not a rewrite of the TUI.** Extend the existing TUI agentic chat and concierge; do not
  build a new TUI framework.
- **NR-5 — `derive-contract` not gated on this.** PRD→Prisma derivation (F-5) is its own track
  (`CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md`); this experience *consumes* it where available but
  does not block on it.
- **NR-6 — Not a replacement for `kickoff check`.** The CLI checker remains the authoritative gate;
  the experience is a friendlier path to the same conformant docs.

---

## 5. Open Questions

*7 of 8 resolved by the planning pass — see §0 for rationale and citations. Retained here for the record.*

- **OQ-1 — RESOLVED → SDK-internal config.** No manifest-kind registry exists (`extract.py:151-228`);
  FR-1 is SDK-internal data, not a grammar kind. Grammar-layer dogfood does not hold.
- **OQ-2 — RESOLVED → flows give step-state only.** A flow writes only the `step_field` pointer
  (`flow_generator.py:96-99`); value capture + write-back is new code.
- **OQ-3 — RESOLVED → throwaway local app + new serve plumbing** (FR-NEW-4). MCP (stdio) cannot
  serve/launch.
- **OQ-4 — RESOLVED → safe-writer at human privilege, with a required FR-C3a exception** (FR-NEW-2)
  to read the target input file for merge.
- **OQ-5 — RESOLVED → live per-capture extraction is fine** (`$0`, synchronous; `extract.py:42-43`).
  Caching is an optional optimization.
- **OQ-6 — RESOLVED (product decision, 2026-06-25) → full fidelity in both surfaces.** Both the TUI and
  the generated web app render the complete experience, including visual extraction-state (FR-6 badges)
  and the readiness meter (FR-7). Rich expresses badges/meters in the terminal; the web app renders them
  in HTMX/Jinja2. This requires parity testing across surfaces (see FR-3) but eliminates "wrong surface"
  friction. Both surfaces share the M1 extraction-state service and M2 readiness data, so fidelity is a
  rendering concern, not a data-divergence one.
- **OQ-7 — RESOLVED → wrap-then-guide; CLI is sole writer.** The experience runs after/around
  `instantiate-kickoff` as the fill-in layer (`core.py:28-30`).
- **OQ-8 — RESOLVED → read-only agentic allow-list** (`survey`, `assess`, new `field_states`),
  structurally enforced by `handle_concierge_read` (`core.py:272-285`).

---

*v0.2 — Post-planning self-reflective update. 4 requirements reframed (FR-1/FR-2/FR-9/FR-12), 3
narrowed (FR-6/FR-8 + NR-3 clarified), 6 added (FR-NEW-1..6), all 8 open questions resolved (OQ-6 settled
by product decision 2026-06-25 → full fidelity in both surfaces). The "dogfood the deterministic UI
machinery" framing was corrected from "flows are the spine" to "widget + theme reuse; new value-capture +
serve code." Entering CRP review (dual-document) before implementation.*

*v0.3 — CRP R1 applied: 8 F-suggestions accepted and merged as testable acceptance criteria (see
Appendix A); Appendix C R1 round retained as cross-model memory.*

*v0.4 — CRP R2–R4 (gpt-5.5) triaged under "accept all, phase the scope-expanders." 15 Group-1
"tightening" suggestions merged as **Acceptance (R2–R4)** criteria on the named FRs; 10 Group-2
"scope-expanding" suggestions accepted but **phased to §F (post-v1)** rather than inlined into v1 FRs.
Nothing rejected (Appendix B stays empty). Appendix C rounds and the R1 acceptance bullets/rows are
retained verbatim. (Rounds R5–R6 remain untriaged in Appendix C.)*

*v0.5 — CRP R5–R6 (gpt-5.5) triaged under the same "accept all, phase the scope-expanders" policy. 8
Group-1 "tightening" suggestions (R5-F1/F3/F4/F8, R6-F2/F3/F5/F6) merged as **Acceptance (R5–R6)**
criteria on the named FRs; 8 Group-2 "scope-expanding" suggestions (R5-F2/F5/F6/F7, R6-F1/F4/F7/F8)
accepted but **phased to §F (post-v1)**. Nothing rejected (Appendix B stays empty). Appendix C rounds
and all earlier acceptance bullets/rows/coverage matrices are retained verbatim. **No untriaged rounds
remain — the spec is considered CONVERGED at R6.***

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
| R1-F1 | Testable boundedness for the read-then-merge writer (single target file, byte-for-byte sibling/comment/order preservation, stale-hash refusal). | R1 / claude-opus-4-8[1m] | Merged into **FR-NEW-2** as Acceptance (R1) bullets (a)/(b)/(c). | 2026-06-25 |
| R1-F2 | Cross-field / interaction failure clause (attribute-with-dependency-name or deferred, not hard whole-capture reject). | R1 / claude-opus-4-8[1m] | Merged into **FR-8** and **FR-NEW-3** as Acceptance (R1) interaction-failure clauses. | 2026-06-25 |
| R1-F3 | Name the canonical shared view-model both surfaces consume; parity test asserts pure-function equality across a state matrix. | R1 / claude-opus-4-8[1m] | Merged into **FR-3** as the "Canonical state representation" Acceptance (R1) sub-bullet. | 2026-06-25 |
| R1-F4 | Enforce new `field_states` tool under the read-only floor; registry set exactly {survey, assess, field_states}; no write reachable. | R1 / claude-opus-4-8[1m] | Merged into **FR-9** as the enforcement Acceptance (R1) bullet. | 2026-06-25 |
| R1-F5 | Teardown / leak acceptance (port released, no child process, scratch removed, stale scratch GC'd) on end / Ctrl-C / parent crash. | R1 / claude-opus-4-8[1m] | Merged into **FR-NEW-4** as teardown/leak Acceptance (R1) bullets. | 2026-06-25 |
| R1-F6 | Constrain `value_path` to a server-side allow-list (FR-NEW-6 mapping); reject traversal/`../` before `apply_write_plan`. | R1 / claude-opus-4-8[1m] | Merged into **FR-NEW-1** and **FR-NEW-6** as allow-list / traversal-guard Acceptance (R1) bullets. | 2026-06-25 |
| R1-F7 | Web-apply authorization model: foreground same-origin POST with session/CSRF token IS authorization; unauth/cross-origin does not durably write. | R1 / claude-opus-4-8[1m] | Merged into **FR-12** as the web-apply authorization Acceptance (R1) clause (cross-ref FR-NEW-1). | 2026-06-25 |
| R1-F8 | Single derivation point for the derived "ambiguous" label (computed on the FR-3 view-model); define recognized `reason` patterns vs. catch-all. | R1 / claude-opus-4-8[1m] | Merged into **FR-6** and **FR-NEW-5** as the single-derivation-point Acceptance (R1) clause. | 2026-06-25 |
| R2-F1 | Pre-apply capture preview (target file, value_path, old/new value, provenance change, field-scoped diff) before any write. | R2 / gpt-5.5 | Merged into **FR-NEW-1** as Acceptance (R2–R4). | 2026-06-26 |
| R2-F2 | Session-scoped undo/rollback for captured field writes until teardown. | R2 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R2-F3 | Deterministic next-action ranking (blockers > required not_extracted > defaulted > optional; tie-break step order). | R2 / gpt-5.5 | Merged into **FR-11** as Acceptance (R2–R4). | 2026-06-26 |
| R2-F4 | Per-field value/"what this unlocks" help in the FR-1 config. | R2 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R2-F5 | Seeded demo/parity fixture covering all statuses, a blocker, a cross-field dependency, and a write preview. | R2 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R2-F6 | Incremental post-capture refresh of field state, gap list, readiness without restart/reload. | R2 / gpt-5.5 | Merged into **FR-6** as Acceptance (R2–R4). | 2026-06-26 |
| R2-F7 | Kickoff funnel metrics (session/first-capture/next-action/defaulted-reviewed/preview/round-trip/friction/teardown). | R2 / gpt-5.5 | Merged into **FR-15** as Acceptance (R2–R4). | 2026-06-26 |
| R2-F8 | Confirmed-write wording rule: "saved/captured" only after safe-writer durable-write success. | R2 / gpt-5.5 | Merged into **FR-12** as Acceptance (R2–R4). | 2026-06-26 |
| R2-F9 | No-progress-loop guard for guided next-step (offer friction/different field after repeated skips). | R2 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R3-F1 | Full WCAG 2.2 AA accessibility suite for generated forms (labels, focus, keyboard, non-color status, touch/zoom). | R3 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R3-F2 | Config lint for FR-1 (unique value_path, one write mapping, widget/help, allow-list, fixture coverage). | R3 / gpt-5.5 | Merged into **FR-1** as Acceptance (R2–R4). | 2026-06-26 |
| R3-F3 | Kickoff preflight/doctor before serving (inputs, writability, scratch, port, browser fallback). | R3 / gpt-5.5 | Merged into **FR-14** as Acceptance (R2–R4). | 2026-06-26 |
| R3-F4 | Source-inventory view (inspected / produced-records / missing / ignored-out-of-grammar). | R3 / gpt-5.5 | Merged into **FR-5** as Acceptance (R2–R4). | 2026-06-26 |
| R3-F5 | Final build-readiness review step before handoff to `kickoff check`. | R3 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R3-F6 | Debounced refresh / stale-result discard for live extraction/readiness. | R3 / gpt-5.5 | Merged into **FR-6** as Acceptance (R2–R4). | 2026-06-26 |
| R3-F7 | "No hidden broad read" invariant on the source inventory (only configured scan roots). | R3 / gpt-5.5 | Merged into **FR-5** as Acceptance (R2–R4). | 2026-06-26 |
| R3-F8 | Accessibility fixture state (error, defaulted badge, ambiguous label, disabled next action w/ text). | R3 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R4-F1 | Stale-write conflict recovery (preserve proposed value, re-read, new diff, reload/reapply/discard). | R4 / gpt-5.5 | Merged into **FR-NEW-2** as Acceptance (R2–R4). | 2026-06-26 |
| R4-F2 | Field dependency graph in FR-1 config (depends_on/unlocks/blocks_build_when_missing). | R4 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R4-F3 | Machine-readable inspect/dry-run JSON (no serve, no write). | R4 / gpt-5.5 | Merged into **FR-14** as Acceptance (R2–R4). | 2026-06-26 |
| R4-F4 | Stable typed failure reason codes + remediation text for capture/serve failures. | R4 / gpt-5.5 | Merged into **FR-NEW-1** as Acceptance (R2–R4). | 2026-06-26 |
| R4-F5 | Explicit feature modes (read-only inspect / preview-only / write-enabled / demo). | R4 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R4-F6 | Optional handoff packet (Markdown/JSON projection, non-authoritative). | R4 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R4-F7 | Redact local secrets/absolute paths in reason codes, previews, inventory, handoff. | R4 / gpt-5.5 | Merged into **FR-12** as Acceptance (R2–R4). | 2026-06-26 |
| R4-F8 | Inspect JSON compatibility promise (`schema_version` + additive-field tolerance). | R4 / gpt-5.5 | Merged into **FR-14** as Acceptance (R2–R4). | 2026-06-26 |
| R5-F1 | Generated-app freshness fingerprint (FR-1 config + template/theme/SDK version); regenerate/refuse stale apps before serving. | R5 / gpt-5.5 | Merged into **FR-2** as Acceptance (R5–R6). | 2026-06-26 |
| R5-F2 | Batch review queue (review multiple fields/previews together; apply stays per-field safe writes). | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R5-F3 | Performance budgets for extraction/readiness/refresh/first render; "large project / still checking" state when exceeded. | R5 / gpt-5.5 | Merged into **FR-7** as Acceptance (R5–R6). | 2026-06-26 |
| R5-F4 | Visual/text regression coverage (web screenshots + Rich snapshots) across the state matrix. | R5 / gpt-5.5 | Merged into **FR-3** as Acceptance (R5–R6). | 2026-06-26 |
| R5-F5 | Deterministic friction prefill from failure codes / skipped actions / ignored sources, human-confirmed before append. | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R5-F6 | Quick navigation (web command palette / TUI commands) to blockers, defaulted values, inventory, review, preview. | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R5-F7 | Batch graceful degradation (one field's failure leaves others' status independent; no rollback without explicit undo). | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R5-F8 | Generated-artifact cleanup policy (keep latest N / remove stale during preflight; emit cleanup count). | R5 / gpt-5.5 | Merged into **FR-NEW-4** as Acceptance (R5–R6). | 2026-06-26 |
| R6-F1 | Session draft persistence (unapplied values / step / queue position restored across refresh, restart, handoff). | R6 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R6-F2 | Proactive external-edit warning when a target `inputs/*.yaml` hash changes mid-session (non-blocking reload/keep-editing). | R6 / gpt-5.5 | Merged into **FR-NEW-2** as Acceptance (R5–R6). | 2026-06-26 |
| R6-F3 | Single-writer advisory lock (one write-capable session per project root; refusal names lock holder). | R6 / gpt-5.5 | Merged into **FR-NEW-4** as Acceptance (R5–R6). | 2026-06-26 |
| R6-F4 | Field search/filter over steps/fields by name, `value_path`, status, blocker/deferred flags. | R6 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R6-F5 | Headless `startd8 kickoff test-capture` exercising `build_capture_plan` + round-trip without serving/ports. | R6 / gpt-5.5 | Merged into **FR-14** as Acceptance (R5–R6). | 2026-06-26 |
| R6-F6 | Capture POST rate limiting + session/CSRF token expiry with stable `rate_limited`/`session_expired` codes. | R6 / gpt-5.5 | Merged into **FR-NEW-4** as Acceptance (R5–R6). | 2026-06-26 |
| R6-F7 | Round-trip reject escape hatch (copyable field-scoped YAML snippet, no auto-write). | R6 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |
| R6-F8 | Surface draft/lock state in inspect/dry-run JSON (`draft_fields`, `lock_holder`, `lock_age`). | R6 / gpt-5.5 | Accepted — deferred to Phase 2 (§F). | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-25

- **Reviewer**: claude-opus-4-8 (claude-opus-4-8[1m])
- **Date**: 2026-06-25 00:00:00 UTC
- **Scope**: Requirements (F-prefix). Weighted to sponsor focus: FR-NEW-1/2 write path + FR-C3a exception, FR-NEW-3 attribution, FR-NEW-4 serve plumbing, FR-9/OQ-8 read-only boundary, FR-3/OQ-6 parity. Adversarial pass included.

**Executive summary (top requirements gaps):**
- FR-NEW-2 bounds the read exception to "the target kickoff input file only" but gives no *testable* acceptance criterion (no comment-preservation, no concurrency precondition) — the exception is scoped in prose but not verifiable.
- FR-8/FR-NEW-3 assert per-field attribution is "required" but never state what happens when a failure is genuinely cross-field (no single offending `value_path` exists) — an untestable/under-defined acceptance condition.
- FR-3 makes "cross-surface parity is a test requirement" but never names the *canonical state representation* both surfaces consume, so the test has no defined oracle.
- FR-9 claims the read-only floor "structurally refuses" writes but adds no acceptance criterion that the new `field_states` tool is itself inside the floor (it's a new entry point).
- FR-NEW-4 specifies serve plumbing exists but lists no teardown/leak acceptance criteria (orphaned port, zombie process, stale scratch).
- FR-12 is "propose-only over agentic; apply via CLU/web" but no requirement states how a *web* friction-log apply is authorized (the web app runs the safe-writer at human privilege — is that one click an authorized human apply?).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | FR-NEW-2 must add a **testable boundedness criterion**: the read-then-merge writer (a) reads only the single target `inputs/<domain>.yaml`, (b) preserves all sibling keys *and their comments/ordering* byte-for-byte except the captured key's value, (c) refuses if the file's on-disk hash changed since it was read. Today it says "may read the target kickoff input file only" with no preservation or staleness clause. | Sponsor focus #1: comment/provenance loss + concurrent-edit clobber. As written the exception authorizes a read but does not forbid a full-file rewrite or a stale-read clobber, so a conforming implementation could still destroy provenance. | FR-NEW-2 — append acceptance bullets | Golden-file diff (only target value line changes) + a precondition-fails-on-external-mutation test. |
| R1-F2 | Validation | high | FR-NEW-3 / FR-8 must define the **cross-field (interaction) failure case**: when a captured value re-parses alone but fails only in manifest context (relationship to an undeclared entity, enum needing a sibling), specify whether the requirement is (a) attribute-with-dependency-name, or (b) accept-and-defer to build-time. "Attribute to the single offending `value_path`" is unsatisfiable when the failure is relational. | Sponsor focus #2: "could a captured value fail in a way that can't be localized?" Yes — and FR-8's "rejected at capture time, not build time" would then deadlock the author from entering a relationship before its target exists. | FR-8 + FR-NEW-3 — add an interaction-failure clause | Acceptance test: capture a relationship to a missing entity; assert the spec'd behavior (named-dependency message or deferred), not a hard whole-capture reject. |
| R1-F3 | Interfaces | high | FR-3 must name the **canonical shared state representation** (the typed object — fields for step, field value, status badge, source ref, readiness) that both TUI and web consume, so "equivalent output in both surfaces" has a concrete oracle. Today FR-3 says both "share the M1 extraction-state service and M2 readiness data" but does not define the view-model whose equality the parity test asserts. | Sponsor focus #5 / OQ-6: parity is only deterministically testable against one canonical representation; without it, "equivalent" is subjective and the two renderers can derive the "ambiguous" UI label differently. | FR-3 — add "Canonical state representation" sub-bullet | Define the type; parity test asserts both surfaces are pure functions of one serialized instance across a state matrix. |
| R1-F4 | Security | high | FR-9 must add an **acceptance criterion that the new `field_states` tool is itself enforced by the read-only floor** (`handle_concierge_read`), not registered via a path that bypasses it, and that the registry's tool set is *exactly* `{survey, assess, field_states}` (no write action reachable). The text asserts the floor "structurally refuses every other action" but `field_states` is new and unproven against that floor. | Sponsor focus #4: propose-only must be airtight. A new tool added to the registry but dispatched outside `handle_concierge_read` would silently widen the surface. | FR-9 — add enforcement acceptance bullet | Negative test enumerating registry keys + asserting each write action name is refused at the dispatch floor; assert `field_states` routes through the read floor. |
| R1-F5 | Ops | high | FR-NEW-4 must add **teardown/leak acceptance criteria**: on session end, Ctrl-C, and parent crash the served app releases its port and leaves no child process; the scratch dir is removed (and stale scratch from a prior crashed run is GC'd on next launch). Currently FR-NEW-4 names "teardown" only in passing. | Sponsor focus #3: zombie-process / orphaned-port / stale-scratch failure modes. A requirement that says "specify the serve lifecycle … including teardown" without leak criteria cannot be verified as done. | FR-NEW-4 — append teardown acceptance bullets | Integration test: SIGINT mid-session → assert port free + no orphan PID + scratch removed; launch-after-crash reclaims stale scratch. |
| R1-F6 | Security | medium | FR-NEW-1/FR-NEW-2 should constrain the captured `value_path` to a **server-side allow-list** derived from the FR-1 config (FR-NEW-6 mapping), so a value_path supplied by the web/agentic surface cannot redirect the merge-write outside `docs/kickoff/inputs/`. The requirement currently trusts the `value_path` as the write target without an allow-list/traversal guard. | A locally-served writer at human privilege is a confused-deputy surface; an unvalidated `value_path` (e.g. containing `../` or pointing at a non-input file) could write arbitrary project files. | FR-NEW-1/FR-NEW-6 — add allow-list constraint | Test: a `value_path` not present in the FR-1 mapping (or containing traversal) is rejected before `apply_write_plan`. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Risks | medium | FR-12 must specify **who authorizes a web-surface friction/value apply**: the requirement says durable writes happen "at human/CLI privilege (or the local web app's safe-writer)" — clarify that a web button click *is* the human-authorization event (and what prevents an unattended/cross-origin POST from counting as one). The parenthetical quietly grants the web app write authority the agentic loop is denied; that asymmetry needs an explicit authorization model. | FR-9/FR-12/P3 deny the agentic loop writes but FR-12 grants the web app's safe-writer durable writes. Without an explicit "a foreground human POST is the authorization" criterion, the web app becomes the write bypass the read-only floor was designed to prevent. | FR-12 (+ cross-ref FR-NEW-1) — add web-apply authorization clause | Test: capture/friction POST requires same-origin + session token; assert an unauthenticated/cross-origin POST does not durably write. |
| R1-F8 | Data | medium | FR-6/FR-NEW-5: specify that the **derived "ambiguous" UI label** (over free-text `reason`) is computed in *one* place (the M1 canonical view-model, R1-F3) so both surfaces classify identically; and define the closed set of `reason` patterns the UI recognizes vs. the catch-all. FR-6 notes reasons "are not a closed vocabulary," which makes the derived label nondeterministic across surfaces unless centralized. | Sponsor focus #5: drift risk. If each surface pattern-matches `reason` independently, TUI and web can disagree on whether a field is "ambiguous," failing parity in exactly the un-golden'd states. | FR-6 / FR-NEW-5 — add "single derivation point" clause | Property test: random `reason` strings → both surfaces' labels identical (because both call the same classifier). |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; no prior untriaged suggestions exist.

#### Review Round R2 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:43:00 UTC
- **Scope**: Requirements (F-prefix). Second-pass quick-win review for robustness, user value, functional low-hanging fruit, and operational enhancements. Builds on R1 rather than restating its safety findings.

**Executive summary (R2 deltas):**
- R1 covers the core write-safety and dispatch-boundary risks. R2 adds requirements that make the experience more trustworthy and valuable to the author.
- A field-capture write should be previewable before apply and reversible immediately after apply.
- "Guided next-step" needs a deterministic ranking rule so both surfaces recommend the same next action.
- The product should explain what each field unlocks in the generated app, not only how to satisfy the grammar.
- A seeded demo fixture is a low-cost way to improve onboarding and parity testing at the same time.
- Observability should measure the kickoff funnel and write failures, not only raw tool/session spans.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Interfaces | high | Add a requirement for a **pre-apply capture preview**: before any FR-NEW-1 write is applied, both web and TUI must show target file, `value_path`, old value, new value, provenance/default status change, and a field-scoped diff. | FR-NEW-1/2 authorizes a new read-merge-write path, and R1 strengthens safety, but the author still needs a confidence-building preview before allowing a local app to edit YAML. | §3.E FR-NEW-1/2, or new acceptance under FR-8 | Test builds a capture plan and asserts the preview matches the eventual `WritePlan`; no file changes before explicit confirmation. |
| R2-F2 | Risks | medium | Add a session-scoped **undo/rollback acceptance** for captured field writes: after a successful apply, the experience can restore the immediately previous file content/hash for that capture until session teardown. | FR-8 rejects invalid writes and FR-NEW-4 owns scratch lifecycle, but no requirement covers "I accepted the wrong value." A local undo improves robustness without adding a new durable app database. | §3.B FR-8 and §3.E FR-NEW-4 | Apply a capture, undo it, assert the file hash and extraction status return to the pre-capture state. |
| R2-F3 | Interfaces | high | Make FR-11 testable by defining the **next-action ranking**: readiness blockers first, required `not_extracted` fields second, `defaulted` values needing human review third, optional fields last; tie-break by FR-1 step order. | FR-11 says "highest-value unfilled field or blocking gap" but does not define "highest-value." Without a ranking, TUI/web/agent can recommend different next steps. | §3.C FR-11 | Fixture with mixed blockers/missing/defaulted fields returns one expected top recommendation in both surfaces. |
| R2-F4 | Architecture | medium | Extend FR-1 field config to include end-user value help: each field should have both grammar help ("what to type") and value help ("what this unlocks in the generated app"). | The problem statement says authors face a "closed grammar"; exposing grammar is necessary but not sufficient for motivation. This is a quick win that increases completion without generating bucket-4 content. | §3.A FR-1 | Config validation fails if a required field lacks grammar help or value/unlocks help. |
| R2-F5 | Validation | medium | Add a seeded **demo/parity fixture** requirement covering every field status (`extracted/defaulted/not_extracted` + derived ambiguous), a readiness blocker, a cross-field dependency, and one write preview. | FR-3 requires parity and R1 asks for a canonical oracle; one deliberate fixture gives users "what good looks like" and gives tests broad branch coverage. | §3.A FR-3 and §3.B FR-6/FR-7 | `startd8 kickoff start --demo` or equivalent renders the fixture; web and TUI snapshots match the same canonical state. |
| R2-F6 | Ops | medium | Add an incremental refresh requirement: after a field capture apply, the experience re-runs extraction/readiness and updates affected field state, gap list, and readiness meter without requiring restart/reload. | FR-5/6/7 are live surfaces, but the requirements do not explicitly close the post-write read-back loop; stale badges after a successful capture are a high-friction failure. | §3.B FR-5/FR-6/FR-7 and §3.E FR-NEW-1 | Capture one field and assert the next UI state shows the new value and readiness delta in the same session. |
| R2-F7 | Ops | medium | Strengthen FR-15 with kickoff funnel metrics: session started, first field captured, next-action accepted/skipped, defaulted value reviewed, write preview abandoned/applied, round-trip rejected, friction logged, teardown status. | FR-15 lists kickoff events, but not the metrics needed to discover operational quick wins and dropoff causes. | §3.D FR-15 | Trace fixture emits stable event names/attributes; a dashboard query can compute completion/dropoff and write failure rates. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F8 | Security | medium | Add a user-visible **confirmed-write wording rule**: the agentic/chat layer may say "I prepared a preview" or "you can apply this," but may only say "saved/captured" after a safe-writer result confirms a durable write. | FR-9/FR-12 are propose-only for agentic surfaces; misleading wording can still imply autonomy or hide that the human has not applied the change. | FR-9/FR-12 acceptance bullets | Conversation snapshot test asserts no "saved" wording appears before `apply_write_plan` success. |
| R2-F9 | Validation | low | Add a "no-progress loop" guard for the guided next-step: if the same recommendation is skipped or rejected repeatedly, the experience should offer friction logging or a different field. | This is low-cost and improves value: authors often get stuck because the top blocker is not currently answerable. The system should not keep asking the same thing. | FR-11/FR-12 | Fixture simulates two skips of same next action; third recommendation changes or offers friction capture. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: Bounded read/write criteria are foundational before adding preview or undo UX.
- R1-F2: Cross-field/deferred validation behavior is required for useful next-action hints.
- R1-F3: Canonical state representation is prerequisite for deterministic ranking and demo fixtures.
- R1-F4: `field_states` must be proven inside the read-only dispatch floor.
- R1-F5: Serve teardown/leak criteria remain mandatory for a local writer app.
- R1-F6: Server-side `value_path` allow-list is required for any capture preview/apply path.
- R1-F7: Web apply needs an explicit human-authorization model.
- R1-F8: A single derived ambiguity classifier is required for R2's parity/demo fixture.

**Disagreements**:
- None.

#### Review Round R3 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:44:00 UTC
- **Scope**: Requirements (F-prefix). Fresh pass for accessibility, config linting, preflight checks, source transparency, final review ergonomics, and low-cost refresh behavior.

**Executive summary (R3 deltas):**
- R1 has been applied and R2 covers preview/undo/ranking; R3 adds acceptance criteria that improve real user success and operational predictability.
- WCAG-AA theming is not enough for an interactive form workflow; labels, focus, keyboard paths, status text, and mobile zoom/touch targets need explicit requirements.
- FR-1's SDK-internal config should be linted because it is the single source of truth for fields, write mappings, next actions, and parity.
- Starting the local app should include a preflight/doctor phase so users get actionable recovery before uvicorn/scratch/write failures.
- Users need to see what source files were inspected and ignored; otherwise "why didn't it understand my PRD?" remains opaque.
- A final build-readiness review step can turn deterministic extraction/readiness into an end-user handoff without replacing `kickoff check`.
- Live extraction should debounce and discard stale results so the interface feels reliable during rapid edits.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Validation | high | Add explicit accessibility acceptance for the generated web/TUI kickoff forms: programmatic labels for every field, visible focus, keyboard-only operation, non-color-only status/error/defaulted indicators, 44px touch targets on web, 200% zoom without clipping, and mobile viewport zoom not disabled. | FR-2 says reuse `presentation_polish` WCAG-AA theming, but form accessibility depends on labels, focus, errors, and status semantics, not only CSS theme tokens. | §3.A FR-2/FR-3 or new accessibility acceptance under FR-3 | Axe/Lighthouse web scan plus manual smoke: keyboard capture, screen-reader labels, grayscale status, 200% zoom, and Rich output includes textual status labels. |
| R3-F2 | Validation | high | Add a config-lint requirement for FR-1: every required field must have a unique `value_path`, exactly one `inputs/*.yaml` write mapping, widget type, grammar help, value/unlocks help, allow-list membership, and canonical view-model fixture coverage. | FR-1 config is load-bearing for extraction, write-back, parity, and next-action ranking. A typo or missing mapping can silently make a field unwritable or invisible. | §3.A FR-1 and §3.E FR-NEW-6 | Config linter fails on duplicate value paths, missing target file/key, unsupported widget, absent help, and unmapped required fields. |
| R3-F3 | Ops | medium | Add a kickoff preflight/doctor requirement before serving: verify `docs/kickoff/inputs` exists or can be instantiated, target files are writable/confined, stale scratch is recoverable, port binding is possible, and browser launch has TUI/manual-URL fallback. | FR-NEW-4 specifies serving lifecycle, but most serve failures are predictable before starting a local app. Preflight improves user value and avoids partial launches. | §3.D FR-14 and §3.E FR-NEW-4 | Simulate missing inputs, unwritable directory, occupied port, stale scratch, and no browser; preflight reports actionable messages and avoids partial serve. |
| R3-F4 | Interfaces | medium | Add a source-inventory requirement: the experience must show which documents/files were inspected, which produced extraction records, which expected kickoff inputs are missing, and which candidate sources were ignored as out-of-grammar. | The problem statement says authors cannot see the closed grammar. FR-5 pre-populates values, but users also need to know why expected existing content was not used. | §3.B FR-5 and §3.C FR-10 | Fixture with PRD plus incomplete inputs renders identical web/TUI source inventory counts and ignored-source reasons. |
| R3-F5 | Interfaces | medium | Add a final build-readiness review step: summarize remaining blockers, deferred cross-field validations, unreviewed defaulted values, latest applied/prepared writes, and the exact next CLI command before handing off to `kickoff check`. | NR-6 keeps `kickoff check` authoritative, but the experience can reduce anxiety by presenting a deterministic go/no-go handoff from the same data. | §3.B FR-7/FR-8 and §4 NR-6 | Fixture with blockers/defaulted/deferred validation produces a final review that does not claim ready unless `assess`/checker state agrees. |
| R3-F6 | Ops | low | Add debounced refresh semantics: after field edits/previews/applies, extraction/readiness updates are debounced, show a temporary "checking grammar" state, and discard stale extraction results if newer edits arrive. | OQ-5 says extraction is `$0` and synchronous, but interactive UIs can still flicker or show stale status when users type quickly or apply multiple captures. | §3.B FR-5/FR-6/FR-7 | Rapid-edit test triggers multiple refreshes; only latest result updates the canonical state and surfaces. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F7 | Risks | medium | Require a "source inventory has no hidden broad read" invariant: the inventory may report only files/directories intentionally scanned by the existing extraction/survey path, not expand reads beyond the stated kickoff/source inputs to satisfy curiosity. | R3-F4 adds transparency, but it must not become a new broad read path that violates the bounded read posture. | FR-5/FR-10 acceptance | Test inventory generation against a project with unrelated files; inventory excludes unrelated content and records only configured scan roots. |
| R3-F8 | Validation | low | Add an accessibility fixture state with a required field error, `defaulted` badge, ambiguous-derived label, and disabled/unavailable next action with explanatory text. | Accessibility failures often hide in error/disabled/status states rather than happy-path forms. This extends R2's demo fixture into the states users actually struggle with. | FR-3/FR-6/FR-11 acceptance | Web/TUI golden snapshots include visible text for every status and explanation for unavailable action; no status conveyed only by color. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: Pre-apply preview is the right user-confidence layer on top of the bounded writer.
- R2-F2: Undo/rollback improves robustness without creating a new durable persistence layer.
- R2-F3: Deterministic next-action ranking is prerequisite for R3's final build-readiness review.
- R2-F4: Value/unlocks help should be enforced by the FR-1 config linter.
- R2-F5: The seeded demo fixture should include R3's accessibility/status edge cases.
- R2-F6: Incremental refresh should include debounce and stale-result discard.
- R2-F7: Funnel metrics should include preflight failure, final-review outcome, and accessibility smoke status.
- R2-F8: Confirmed-write wording is required so the read-only agentic layer does not imply autonomy.

**Disagreements**:
- None.

#### Review Round R4 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:46:00 UTC
- **Scope**: Requirements (F-prefix). Fresh pass for conflict recovery, field dependencies, CI/dry-run integration, typed failure UX, feature flags, and operational rollout.

**Executive summary (R4 deltas):**
- R1 was applied; R2/R3 add user-confidence and accessibility/preflight improvements. R4 adds recovery and rollout controls around those mechanisms.
- Stale-write refusal should preserve the user's work and offer a rebase/reapply path, not only fail safely.
- Cross-field dependencies should be declared in config so attribution, next-action ranking, and final review agree.
- CI/agents need a machine-readable inspect/dry-run mode that does not launch a local app.
- Stable failure reason codes will make UI messages, tests, telemetry, and support much more robust.
- The experience should have explicit operating modes: read-only inspect, preview-only, write-enabled, and demo.
- A generated handoff packet would make the kickoff session useful even when the user pauses before running the build.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Data | high | Add a stale-write **conflict recovery** requirement: when the target file hash changes between preview/read and apply, preserve the proposed value, re-read the latest file, show an updated diff, and offer reload, reapply-to-latest, or discard. | R1 applied stale-hash refusal, but safe refusal alone can discard user effort. Recovery keeps clobber safety while improving the end-user path through concurrent edits. | §3.E FR-NEW-2 and §3.B FR-8 | External edit between preview and apply refuses write, retains proposed value, and generates a new preview against the updated file. |
| R4-F2 | Architecture | medium | Extend FR-1 config with a field dependency graph (`depends_on`, `unlocks`, `blocks_build_when_missing`) used by attribution, next-action ranking, final review, and "what this unlocks" help. | R1/R2/R3 discuss cross-field failures, ranking, and final review, but no requirement names a single source for dependency semantics. | §3.A FR-1 and §3.B FR-8/FR-7 | A relationship field depending on an entity field emits the same dependency path in validation, next action, and final review. |
| R4-F3 | Ops | medium | Add a machine-readable inspect mode (`startd8 kickoff inspect --json` or `start --dry-run --json`) that emits canonical state, source inventory, readiness, next action, and preflight status without serving web/TUI or writing files. | FR-14 launches the experience, but CI/IDE agents often need the same state without port/process lifecycle. This is a low-cost operational quick win from M1/M2/M3. | §3.D FR-14 and FR-13 | Command emits deterministic JSON for the demo fixture; no port opens, no scratch app is generated, and no writes occur. |
| R4-F4 | Interfaces | medium | Add stable failure reason codes and remediation text for capture/serve failures: stale hash, round-trip field failure, dependency/deferred validation, unsafe value path, CSRF refused, port bind failure, scratch GC failure, and permission denied. | Prior rounds add many safety checks; without stable codes, each surface may invent different copy and telemetry. | §3.E FR-NEW-1/2/3/4 and §3.D FR-15 | Each simulated failure maps to a stable code, user-safe message, and OTel attribute. |
| R4-F5 | Risks | medium | Add explicit feature modes: read-only inspect, preview-only capture, write-enabled local app, and demo. Default to read-only/preview until write-path and serve-path safety tests pass. | This separates immediate value from the riskiest durable-write path and supports staged rollout without blocking the read-only surface. | §3.D FR-14/FR-13 and §3.C FR-9/FR-12 | In preview-only mode, apply endpoints/tool paths cannot call `apply_write_plan`; in write-enabled mode, explicit confirmation and CSRF/session authorization are required. |
| R4-F6 | Interfaces | low | Add an optional **handoff packet** requirement: generate Markdown/JSON summarizing captured values, remaining blockers, reviewed defaults, ignored sources, friction items, and next commands. It is a projection only, not a new source of truth. | Users may need to pause or hand the project to another human/agent. A deterministic handoff artifact increases value without changing the docs-as-store model. | §3.B FR-7/FR-8, §3.C FR-12, §4 NR-3/NR-6 | Generated packet is deterministic from current docs/state, excludes raw secrets, includes source refs and next commands, and is clearly marked non-authoritative. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F7 | Security | medium | Require failure reason codes and handoff packets to **redact local secrets and absolute paths where possible**, while preserving enough relative path/source-ref detail for debugging. | Source inventory, previews, and handoff artifacts improve transparency but can leak project-local details if copied into issues or chats. | FR-10/FR-12/FR-15 acceptance | Fixture containing `.env`-like values and absolute paths produces redacted external artifact with relative safe references. |
| R4-F8 | Ops | low | Add a compatibility promise for inspect/dry-run JSON: include `schema_version` and tolerate additive fields so IDE/MCP agents can consume it safely. | If agents start using the JSON state, unversioned output becomes a brittle hidden API. | FR-13/FR-14 acceptance | JSON schema test validates `schema_version`; old fixture consumers ignore unknown fields. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1 and R2-F2: Preview and undo are prerequisites for stale-conflict recovery.
- R2-F3: Deterministic next-action ranking should use the declared dependency graph.
- R2-F7: Funnel metrics should include R4's typed failure reason codes.
- R2-F8: Confirmed-write wording is easier to enforce with explicit feature modes.
- R3-F2: Config linting should include dependency graph integrity.
- R3-F3: Preflight/doctor pairs naturally with inspect/dry-run JSON.
- R3-F4 and R3-F5: Source inventory and final review are the core inputs for a handoff packet.
- R3-F7: Source inventory and handoff artifacts must not broaden reads or leak unrelated local files.

**Disagreements**:
- None.

#### Review Round R5 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:48:00 UTC
- **Scope**: Requirements (F-prefix). Late-pass quick wins for generated-artifact freshness, batch review ergonomics, performance budgets, visual regression, friction taxonomy, and navigation speed.

**Executive summary (R5 deltas):**
- R2-R4 cover confidence, accessibility, preflight, modes, and dry-run. R5 adds polish and operational safeguards that are cheap once those foundations exist.
- Generated local apps need stale-artifact detection keyed to config/templates/theme/SDK version.
- Per-field safety can coexist with a batch review queue that improves end-user speed.
- "Live" extraction/readiness should have explicit performance budgets and large-project fallbacks.
- Parity should include visual/Rich regression snapshots, not just data equality.
- Friction capture can be prefilled deterministically from failure codes, skipped actions, and ignored-source evidence.
- Keyboard/command navigation to blockers and defaulted values is a small feature with high accessibility and power-user value.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Ops | high | Add generated-app freshness requirements: generated kickoff app metadata must include a fingerprint of FR-1 config, renderer/template/theme versions, and SDK version; stale generated apps must be regenerated or refused before serving. | FR-NEW-4 covers serving lifecycle, but not stale generated artifacts. A stale app could present old fields or handlers after config/template changes. | §3.A FR-2 and §3.E FR-NEW-4 | Change FR-1 config/template; next start detects mismatch and regenerates/refuses with a stable reason code. |
| R5-F2 | Interfaces | medium | Add a batch review queue requirement: users can review multiple missing/defaulted fields and their previews together, but apply still executes as separate per-field/per-file safe writes with individual success/failure status. | Per-field writes are safe but repetitive. Batch review improves completion speed without weakening FR-NEW-1/2 safety. | §3.B FR-8, §3.C FR-11, §3.E FR-NEW-1 | Queue three fields, preview all, apply, and assert each field reports independent result/round-trip attribution. |
| R5-F3 | Ops | medium | Add performance budget requirements for initial extraction/readiness, post-capture refresh, and first render; if exceeded, the UI must show a "large project / still checking" state rather than stale or frozen output. | OQ-5 establishes extraction is `$0`, and R3 adds debounce, but no requirement defines acceptable live feedback latency. | §3.B FR-5/FR-7 and §3.D FR-15 | Performance fixture records timings for small/medium/large input packages and asserts warnings/telemetry above threshold. |
| R5-F4 | Validation | medium | Add visual/text regression coverage: web screenshots and Rich text snapshots for missing/defaulted/error/conflict/final-review/preflight-failure states. | FR-3 parity and R3 accessibility can pass at the state level while the visible UI clips, hides labels, or formats statuses differently. | §3.A FR-3 and §3.B FR-6/FR-7 | Golden snapshots compare web and TUI outputs for the seeded fixture state matrix. |
| R5-F5 | Interfaces | medium | Add deterministic friction prefill: when a next action is skipped, source content is ignored, or a typed failure occurs, the experience pre-populates a friction log preview with candidate friction class, evidence, and implication, requiring human confirmation before durable append. | FR-12 lets users log friction, but the system already has high-quality evidence at the moment of failure. Prefill improves feedback quality without bucket-4 content generation. | §3.C FR-12 and §3.D FR-15 | Simulate ignored PRD section and stale hash failure; friction preview contains candidate class/evidence and no durable write until confirmed. |
| R5-F6 | Interfaces | low | Add quick navigation requirements: web keyboard shortcuts/command palette and TUI commands jump to next blocker, next defaulted value, source inventory, final review, and capture preview with visible focus/selection. | Large kickoff packages need fast navigation, and keyboard navigation is an accessibility win. This builds on next-action ranking and canonical state. | §3.A FR-3 and §3.C FR-11 | Keyboard/TUI command tests navigate to expected field/section without mouse; focus remains visible and screen-reader label is present. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F7 | Risks | medium | Require batch review to degrade gracefully: if one field in a batch fails round-trip, stale-hash, or authorization, other fields must report independent status and no successful write should be rolled back unless the user explicitly requests undo. | Batch UX can accidentally reintroduce all-or-nothing ambiguity that the per-field design avoided. | FR-8/FR-NEW-1 acceptance | Batch with one invalid field and two valid fields reports one failure, two successes, and preserves undo per successful field. |
| R5-F8 | Ops | low | Add generated-artifact cleanup policy for stale app versions: keep only the latest N scratch/generated versions or remove all stale versions during preflight, with clear telemetry. | Fingerprinting creates more scratch variants; without cleanup, stale generated apps can accumulate. | FR-NEW-4 acceptance | Create multiple stale fingerprints; preflight removes or reports them according to policy and emits cleanup count. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1 and R2-F2: Preview and undo are prerequisites for safe batch review.
- R2-F3 and R4-F2: Next-action ranking plus dependency graph make the review queue coherent.
- R2-F5 and R3-F8: Seeded demo/accessibility fixtures should back visual/text regression coverage.
- R2-F7 and R4-F4: Funnel metrics and typed reason codes should include performance and friction-prefill outcomes.
- R3-F1 and R3-F8: Accessibility acceptance should include keyboard/command navigation paths and edge-state fixtures.
- R3-F3 and R4-F3: Preflight and inspect/dry-run are the right places to expose stale-artifact and performance warnings.
- R3-F4/R4-F6: Source inventory and handoff packets are natural inputs for friction prefill.
- R4-F5: Feature modes should gate batch apply separately from preview-only batch review.

**Disagreements**:
- None.

#### Review Round R6 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 02:50:00 UTC
- **Scope**: Requirements (F-prefix). Fresh pass for session draft persistence, proactive external-edit detection, single-writer locking, large-package navigation, CI capture harness, and local-web abuse hardening.

**Executive summary (R6 deltas):**
- R2-R5 cover preview, modes, polish, and batch UX. R6 targets session continuity and multi-process safety gaps visible in daily use.
- Unapplied draft values need scratch persistence so refresh, crash, or TUI↔web switch does not lose author effort.
- External file edits should be detected proactively during a session, not only at apply-time stale-hash refusal.
- A single-writer advisory lock prevents concurrent write-capable sessions from interleaving captures.
- Field search/filter improves large-package usability beyond command-palette jump targets.
- A headless `test-capture` command enables M6 round-trip regression in CI without browser automation.
- Local web capture needs rate limiting and session-token expiry with stable reason codes.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Interfaces | high | Add **session draft persistence**: unapplied field values, current step, and review-queue position are stored in the M7 scratch area and restored across browser refresh, TUI restart, and surface handoff until teardown or explicit discard. | FR-4 promises resumable progress; R2 undo only covers post-apply rollback. Losing typed-but-unapplied values is a common high-friction failure. | §3.B FR-4 and §3.E FR-NEW-4 | Enter values without apply, restart, assert identical draft restoration in web and TUI. |
| R6-F2 | Risks | medium | Add **proactive external-edit warnings**: when a target `inputs/*.yaml` hash changes during an active session, surface a non-blocking warning with reload/keep-editing choices before apply. | R1/R4 refuse stale applies safely but late; proactive detection saves user effort and reduces surprise. | §3.E FR-NEW-2 and §3.B FR-8 | Mid-session external edit triggers warning; user can reload latest file state without clobber. |
| R6-F3 | Ops | medium | Add a **single-writer lock** requirement: at most one write-capable kickoff session per project root; concurrent write attempts receive a clear refusal naming the lock holder. | Per-field atomic writes do not prevent two sessions from interleaving conflicting captures. | §3.E FR-NEW-1/2/4 and §3.D FR-14 | Second write-enabled session refused; lock released on teardown. |
| R6-F4 | Interfaces | low | Add **field search/filter** over steps and fields by name, `value_path`, status, and blocker/deferred flags. | Large kickoff packages need discoverability beyond guided next-step. Low-lift user value. | §3.A FR-1 and §3.C FR-11 | Search/filter fixture returns expected subsets deterministically in web and TUI. |
| R6-F5 | Validation | medium | Add **`startd8 kickoff test-capture`** (or equivalent): headless command exercising `build_capture_plan` and per-field round-trip against a fixture matrix without serving UI or opening ports. | CI needs write-path regression without browser/uvicorn lifecycle. Complements inspect/dry-run read paths. | §3.D FR-14 and §3.B FR-8 | Fixture matrix passes/fails with per-field attribution output; no port opened. |
| R6-F6 | Security | medium | Add **capture POST rate limiting** and **session/CSRF token expiry** with stable `rate_limited` and `session_expired` reason codes and remediation text. | Loopback+CSRF (R1) does not cover stale-tab replay or local script burst POSTs against a human-privilege writer. | §3.E FR-NEW-4 and FR-12 authorization acceptance | Burst POSTs rejected with stable code; expired token cannot apply. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F7 | Interfaces | low | Add a **round-trip reject escape hatch**: on per-field round-trip failure, offer a copyable field-scoped YAML snippet (with provenance comment) for manual paste, with no automatic write. | Some failures are not auto-resolvable in-session; users need a deterministic off-ramp without violating safe-writer policy. | §3.B FR-8 and §3.E FR-NEW-3 | Reject path shows copyable snippet matching preview; extraction after manual paste succeeds. |
| R6-F8 | Ops | low | Require draft persistence and single-writer lock state to appear in inspect/dry-run JSON (`draft_fields`, `lock_holder`, `lock_age`) for agents and support tooling. | Operational visibility into session continuity failures without launching UI. | §3.D FR-13/FR-14 acceptance | Inspect JSON includes draft/lock fields for active session fixture. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F2 and R4-F1: Undo and conflict recovery complement draft persistence and proactive edit warnings.
- R2-F6 and R3-F6: Incremental refresh should restore from drafts after session restart.
- R3-F3: Preflight should verify single-writer lock before write-enabled serve.
- R4-F3 and R4-F4: Inspect JSON and typed codes should include lock, draft, `session_expired`, and `rate_limited`.
- R4-F5: Draft persistence and test-capture respect preview-only vs write-enabled modes.
- R5-F2 and R5-F5: Batch queue and friction prefill benefit from draft state and search.

**Disagreements**:
- None.
