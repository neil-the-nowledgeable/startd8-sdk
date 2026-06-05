# Basic Wireframing Capability — Requirements

**Version:** 0.3 (Post-CRP — rounds R1–R6 triaged; see Appendix A/B)
**Date:** 2026-06-05
**Status:** Draft
**Plan:** [`WIREFRAME_PLAN.md`](WIREFRAME_PLAN.md)
**Related:** [`../kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`](../kickoff/ASSEMBLY_INPUTS_TEMPLATE.md)
(input catalog basis), [`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md) (FR-X1
pre-flight, FR-X5 inventory), [`../kickoff/KICKOFF_ASSEMBLY_INPUTS.md`](../kickoff/KICKOFF_ASSEMBLY_INPUTS.md)
(Group F input detail), `docs/design/python-contract-codegen/` (the $0 cascade this previews)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass
> (codebase exploration of the parsers, generators, CLI, and cap-dev-pipe hooks) revealed:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Absent manifest ⇒ "not defined" uniformly | `parse_app_manifest(None)` yields a **full default scaffold**; absent `completeness.yaml` ⇒ presence-rule fallback; absent `human_inputs.yaml` ⇒ server-managed omissions still apply | FR-W4 rewritten: per-manifest absence semantics with a new `defaults` status |
| Status vocabulary = kickoff's 3 states | A present-but-unparseable manifest is a distinct, common state. **Correction (R6-F1):** the YAML manifest parsers loud-fail, but the **Prisma parser is lenient** — never raises, skips unparseable lines (`prisma_parser.py:276`) — so schema invalidity needs a recoverability check, not exception catching | Added `invalid` status + FR-W13 graceful degradation; FR-W4 defines schema recoverability |
| Field-level form detail might be too costly for "basic" (OQ-6) | `htmx_generator._form_fields`/`_writable_fields` already compute exactly this (FR-PG-5) | OQ-6 resolved: forms section is field-level, including owned/server-managed omissions |
| cap-dev-pipe hook mechanism unknown (OQ-4) | Established precedent: env-gated `scripts/run_*.py` shims in `run-prime-contractor.sh` (Service Assistant opt-out, FDE opt-in), `set +e`, never block | OQ-4 resolved: opt-in `STARTD8_WIREFRAME=1` shim, FDE-style |
| A machine-readable inventory format might exist (OQ-3) | FR-X5 instantiation is **markdown only**; no YAML inventory format exists anywhere | OQ-3 resolved: this capability defines `assembly-inputs.yaml`, the first machine-readable companion to the template |
| Generators might need first-class plan objects (OQ-2) | Generators are one-pass emitters (`(path, content)` tuples); only frontend has `SkeletonPlan`. Refactoring all three is invasive | OQ-2 resolved: wireframe derives its plan from the **shared parsers** independently; divergence risk gated by a golden cross-check test (new FR-W14) |
| `views.yaml` parses standalone | `parse_views()` requires `known_entities` from the parsed Prisma schema | Plan derivation is schema-first; views degrade (not crash) when the schema is absent/invalid |
| Container section is a rich surface | `AppManifest` container surface is thin: `dockerfile: bool` + `python_version` | Containers section scoped to what `app.yaml` actually declares |

**Resolved open questions:**
- **OQ-1 → top-level `startd8 wireframe`.** Not `generate` (emits no app code; that group's help says "code generation"), not `assist` (that family is run-triage/bridge).
- **OQ-2 → independent derivation + cross-check test** (FR-W14). No generator refactor in v1.
- **OQ-3 → this capability defines `assembly-inputs.yaml`**; proposed to kickoff as the canonical FR-X5 machine-readable companion (their call to adopt).
- **OQ-4 → opt-in env-gated pipeline shim** (`STARTD8_WIREFRAME=1`), following the FDE precedent at `run-prime-contractor.sh:557`; edit lands in the canonical cap-dev-pipe repo.
- **OQ-5 → minimal v1 placeholder detection** (zero-model schema; `REPLACE_WITH_` sentinels), documented as a subset of kickoff FR-X1 semantics.
- **OQ-6 → field-level forms** — the helpers already exist; promote two private functions to public.

---

## 1. Problem Statement

The $0 deterministic cascade (`startd8 generate scaffold` / `generate backend` /
`generate views`) assembles ~89% of an application from seven hand-authored input manifests.
Today the only ways to see *what the cascade will build* are (a) run it and read the emitted
files, or (b) mentally simulate it from the manifests. There is no **pre-generation summary
view** — a "wireframe" — that shows a user the planned application shape (containers, services,
pages, forms, views, CRUD surfaces) and, critically, **what has been planned for vs. what has
not been defined yet** (e.g., `views.yaml` absent ⇒ no composite views will exist).

This matters at the front human bookend (DATA MODEL design): the wireframe is the cheapest
possible feedback on the contract + manifests *before* any generation, and it doubles as a
shared review artifact for the kickoff conversation.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Pre-generation plan object | Only `frontend_codegen.skeleton:SkeletonPlan` (frontend-only) | No plan representation spanning scaffold + backend + views |
| Planned-vs-undefined visibility | FR-X1 pre-flight report **specified** (kickoff docs, not yet built) — input *status* only | Nothing maps input status → *consequence* ("no views.yaml ⇒ 0 composite views") |
| Summary rendering | `--check` drift output (post-generation); sapper/FDE friction reports (mechanism, not shape) | No human-readable app-shape inventory |
| Input bundling | Manifests passed as individual CLI flags (`--schema --pages --views …`) | No way to load one or more YAML "assembly inputs" files cataloging the manifest set per `ASSEMBLY_INPUTS_TEMPLATE.md` |
| cap-dev-pipe visibility | Cascade is deliberately standalone (zero cap-dev-pipe references — master Non-Goals) | No optional, read-only pipeline hook to surface the planned shape |

## 2. Requirements

### Plan derivation

- **FR-W1 — Wireframe plan model.** The capability MUST derive a structured `WireframePlan`
  from the assembly input manifests **without invoking the generators and without writing any
  application files**. The plan enumerates, at minimum:
  - **Scaffold/Containers** — what `app.yaml` actually declares: app name/package, db path,
    Dockerfile y/n, python version, migrations, logging
  - **Services** — FastAPI app, web (HTMX) router mount, AI service + one item per `AiPass`
    (from `ai_passes.yaml`), export endpoints
  - **Entities & CRUD** — per Prisma model: routes (list/get/create/update/delete), table,
    Pydantic models, with artifact paths from `CANONICAL_LAYOUT`
  - **Pages** — content pages + nav from `pages.yaml` (slug/title/nav, nav-override handling)
  - **Forms** — HTMX create/edit forms per entity at **field level**: writable fields shown,
    owned (`human_inputs.yaml`) and server-managed fields listed as omitted
  - **Composite views** — per `views.yaml` `ViewSpec` (name, kind, route, root entity, panels)
  - **Completeness** — signal set from `completeness.yaml`
- **FR-W2 — Deterministic and $0.** Plan derivation MUST be fully deterministic and MUST NOT
  make LLM calls. Operationalized (R1-F5): same inputs ⇒ **byte-identical canonical JSON** from
  `to_json()` — stable key order, artifact paths emitted **project-relative with forward
  slashes** on every host OS (R5-F4). Audit metadata (`generated_at`, `startd8_version`,
  `emit_context`) lives in a top-level **`_meta`** object that is **excluded** from the
  canonical body, the byte-identical tests, and the `inputs_fingerprint` (R5-F1; FR-W12).
- **FR-W3 — Reuse generator parsers.** The plan MUST be derived via the existing manifest
  parsers (`parse_prisma_schema`, `parse_app_manifest`, `parse_views`, `parse_pages`,
  `parse_ai_passes`, `parse_human_inputs`, completeness loader) — not a parallel parsing path
  that can drift from the generators.
- **FR-W14 — Anti-divergence cross-check.** A unit test MUST assert, on a full fixture, that
  the artifact paths enumerated by the wireframe plan match the paths actually emitted by
  `render_backend()` / `render_views()` / `render_scaffold()` (both directions). This is the
  gate that permits deriving the plan outside the generators (OQ-2) without silent drift.

### Planned vs. not-yet-defined

- **FR-W4 — Definition status per section, with per-manifest absence semantics.** Each plan
  section MUST carry one of five statuses: `planned` (manifest authored), `defaults` (manifest
  absent but the generator produces defaulted output anyway), `placeholder` (sentinel/stub
  content), `not_defined` (manifest absent and nothing will be generated), `invalid` (manifest
  present but fails its parser **or its recoverability check** — see below). Absence maps per
  manifest — it is NOT uniformly `not_defined`:

  | Input absent | Status | Consequence |
  |---|---|---|
  | `schema.prisma` | `not_defined` (everything entity-derived) | no entities, CRUD, forms, or views |
  | `app.yaml` | `defaults` | default scaffold (SQLite, Dockerfile on, py3.11) |
  | `pages.yaml` | `not_defined` | no content pages or site nav |
  | `views.yaml` | `not_defined` | no composite views |
  | `ai_passes.yaml` | `not_defined` | no AI service/passes |
  | `human_inputs.yaml` | `defaults` | only server-managed omissions apply |
  | `completeness.yaml` | `defaults` | presence-rule fallback scoring |

  **Schema invalidity & placeholder scoping (R6-F1).** `parse_prisma_schema` is **lenient** —
  it never raises, skips unparseable lines, and returns an empty schema for blank input
  (`prisma_parser.py:276-283`) — so `invalid` for `schema.prisma` MUST be detected via a
  **recoverability check**: compare raw-text `model`/`enum` block count against parsed count;
  mismatch ⇒ `invalid` with a "lenient parse dropped N blocks" message. The `placeholder`
  zero-model rule applies **only** when the raw text contains no dropped `model` blocks —
  otherwise the schema is `invalid`, not `placeholder`. v1 placeholder detection remains
  minimal: zero-model schema + `REPLACE_WITH_` sentinels in YAML scalar values.

  **Composition rule (R6-F3).** Sections derived from ≥2 manifests (Forms = schema +
  `human_inputs.yaml`; Services = schema + `ai_passes.yaml`; Composite views = schema +
  `views.yaml`) take **worst-wins** precedence `invalid > placeholder > not_defined > defaults
  > planned`, with the consequence line taken from the worst contributor. In particular,
  Services MUST NOT render `planned` items when the schema is `not_defined`/`invalid`.

  **Kickoff status mapping (R1-F1).** The kickoff provisioning states map deterministically:
  `authored` → `planned` (or `invalid` if parsing/recoverability fails), `placeholder` →
  `placeholder`, `absent` → `not_defined` or `defaults` per the absence table above.

- **FR-W5 — Consequence rendering.** For each non-`planned` section the summary MUST state the
  downstream consequence in app-shape terms (table above), not just the input status. This is
  the wireframe's value-add over the FR-X1 pre-flight report.
- **FR-W13 — Graceful degradation.** A manifest that fails its parser **or its recoverability
  check** (the lenient Prisma case — FR-W4) MUST surface as `invalid` without aborting the rest
  of the plan. Views validation requires the parsed schema (`parse_views(known_entities=…)`);
  if the schema is absent/invalid, the views section degrades with a note rather than crashing.
  Hardening (R5-F2, R5-S2): `invalid` error text is capped at **500 characters** in tree + JSON
  with `error_truncated: true` when capped (full text to debug logs only); all manifest reads
  are **UTF-8** — a `UnicodeDecodeError` on a manifest ⇒ section `invalid` ("not valid UTF-8"),
  on an `--inputs` file itself ⇒ exit 2; no silent encoding fallback.

### Inputs

- **FR-W6 — Assembly-inputs YAML.** The capability MUST accept one or more YAML files that
  provide the input values, structured per the catalog in `ASSEMBLY_INPUTS_TEMPLATE.md` — i.e.,
  a machine-readable instantiation of the per-project inventory: for each catalog entry, the
  file path (and optionally an explicit status override). Multiple files merge in order, last
  wins per key.
  - **Override precedence (R2-F1):** when the manifest file exists on disk, the parser-derived
    status (`planned`/`invalid`/`placeholder`) wins; an explicit `status:` override applies
    when the file is absent (inventory declared ahead of authoring). Conflicts between override
    and disk reality surface as warnings, never silently.
  - **Path confinement (R3-F4):** a manifest path whose resolution escapes `project_root` MUST
    be rejected with exit 2 and a clear error **before** any file read.
  - **Merge transparency (R5-S5):** when a later file overwrites a catalog key, the overwrite
    is recorded in `merge_warnings` (`{key, previous_path, new_path, source_file}`) in the JSON
    and echoed to stderr in rendered mode.
- **FR-W7 — Direct flags fallback.** Individual manifest paths MUST also be acceptable as
  direct CLI flags **with the exact spellings of all three generators** (R1-F3, R3-F1, R5-F6):
  `--schema --pages --ai-passes --human-inputs --completeness --pages-authoring` (backend;
  `--pages-authoring` requires `--pages`), `--manifest` for `app.yaml` (scaffold's spelling;
  `--app` MAY alias it), and `--views` (views generator). Flags override YAML-provided values.
  (`--ai-agent-spec` is deliberately not mirrored — Appendix B R4-F4.)
- **FR-W8 — Convention defaults.** With no inputs at all, the capability MUST fall back to the
  **five exact conventional filenames** plus contract and scaffold manifest, each mapped to its
  catalog key (R6-F2): `prisma/schema.prisma`, `app.yaml` (root), `prisma/human_inputs.yaml`,
  `prisma/ai_passes.yaml`, `prisma/pages.yaml`, `prisma/completeness.yaml`,
  `prisma/views.yaml` — resolved against the project root. Stray YAML files (e.g.
  `prisma/notes.yaml`) are never picked up; no glob enumeration.

### Invocation & output

- **FR-W9 — Direct CLI.** Top-level `startd8 wireframe` MUST render the summary view: a Rich
  tree grouped by section (scaffold/containers / services / entities & CRUD / pages / forms /
  views / content inputs / completeness), each item status-colored with a text label (color is
  never the only signal), consequence lines under non-`planned` sections, and a closing footer:
  - **counts line** — N planned / M defaults / K placeholder / J not defined / E invalid;
  - **shape summary line** (R3-F3) — `Entities: N | CRUD routes: R | Pages: P | Views: V |
    AI passes: A`;
  - **cascade readiness line** (R4-F2) — per generator, `scaffold|backend|views:
    ready | blocked(<primary reason>)`, derived purely from section statuses.

  `--json` writes JSON to **stdout** and suppresses Rich rendering unless `--verbose` (R4-F1,
  sapper pattern). An optional `--only-issues` filter renders only non-`planned`
  sections/items while the footer keeps full-plan totals (R2-F4). Per-section item lists
  SHOULD cap at `--max-items` (default 25) with an "… and N more" suffix (R5-S3). **Exit
  semantics:** advisory exit 0 regardless of plan statuses; exit 2 when an `--inputs` file is
  unreadable, not valid UTF-8, fails assembly-inputs schema validation, or a resolved path
  escapes `project_root` (R2-F3, R3-F4). Manifest parser failures remain non-fatal (FR-W13).
- **FR-W10 — JSON output.** `--json` MUST emit the full `WireframePlan` as JSON for machine
  consumption (CI, pipeline, prompts). The JSON MUST carry an integer **`schema_version`**
  (R1-F2); breaking field changes bump it, and a one-line stability policy lives beside the
  serializer. Canonical-body and path rules per FR-W2.
- **FR-W11 — Optional cap-dev-pipe initiation.** The capability MUST be optionally invocable
  from cap-dev-pipe as a **read-only visibility step** (consistent with the Group F boundary:
  the pipeline never *runs* the cascade; it may *see* its inputs/plan). Mechanism: an **opt-in,
  env-gated shim** (`STARTD8_WIREFRAME=1` → `scripts/run_wireframe.py`) following the FDE
  precedent in `run-prime-contractor.sh` — `set +e`, always exits 0, never blocks. Default-off
  because most pipeline projects don't use the cascade. The hook edit lands in the canonical
  cap-dev-pipe repo.
  - **Input discovery (R1-F4):** the shim resolves `project_root` from `PROJECT_ROOT` in
    `pipeline.env`, then applies FR-W8 convention defaults; an optional
    `STARTD8_WIREFRAME_INPUTS` env var names assembly-inputs YAML file(s). Absent manifests
    still produce a valid plan (`not_defined`/`defaults`) — never a crash.
  - **Artifact precedence (R4-F3):** the shim writes only under
    `pipeline-output/<run>/wireframe/`; direct CLI writes `.startd8/wireframe/`; neither
    overwrites the other; `_meta.emit_context` records `cli` | `pipeline`.
  - **Discoverable failure (R5-F5):** on internal failure the shim still exits 0 but writes
    `wireframe-error.json` (`{error_type, message}`) in its output dir, so operators can
    distinguish opted-off vs crashed vs empty-manifests.
- **FR-W12 — Persisted artifact.** Whether invoked directly or from the pipeline, the
  capability SHOULD persist the JSON plan (suggested: `.startd8/wireframe/wireframe-plan.json`)
  so later stages/sessions can diff "planned vs. built". The persisted JSON MUST include
  **`inputs_fingerprint`** — a stable hash over each catalog entry's resolved path + content
  SHA-256 (R3-F2) — and **`input_provenance`** per key: `{path, source: convention|yaml|flag}`
  (R3-S2). Writes are **atomic** (temp file + rename; directory created if missing); an
  unwritable target degrades to a warning with exit 0 (R6-F4). In pipeline context a
  human-readable `wireframe-summary.md` SHOULD be persisted alongside the JSON (R1-S3).

### Visibility extensions

- **FR-W15 — Content-inputs visibility (R2-F2).** The plan MUST include a read-only **Content
  inputs** section listing content files referenced by the manifests — `app/pages/*.md` paths
  from `pages.yaml` `content:` entries and AI prompt paths referenced from `ai_passes.yaml` —
  each status-only (`planned`/`placeholder`/`not_defined`) with consequence lines (e.g.
  "no page body at generate time"). Explicitly **non-generative**: bucket 2/4 visibility only,
  per the template's bucket rule (`placeholder` is the intended starting state, never gated).
- **FR-W16 — Stable public API (R4-F5).** `build_wireframe_plan()` and
  `load_assembly_inputs()` MUST be stable public exports of `startd8.wireframe` for
  programmatic use (kickoff FR-X1/FR-X5 machinery, TUI, tests) — not CLI-only.

## 3. Non-Requirements

- **No visual/graphical wireframes.** No HTML mockups, no images, no boxes-and-arrows rendering
  in v1. "Wireframe" here = structured textual summary of planned app shape.
- **No generation.** Never writes application files; not a dry-run mode of the generators.
- **No drift detection.** `--check` already answers "is what's on disk stale"; the wireframe
  answers "what will be built". Out of scope to compare plan vs. disk in v1 (see FR-W12 for the
  enabling artifact).
- **Tool boundary (R2-F5).** Three pre-run visibility tools coexist and the wireframe subsumes
  neither: **wireframe** = Group F assembly shape from assembly manifests; **sapper** =
  mechanism/friction survey (ForwardManifest-driven, Prime/EMIT landmines); **kickoff FR-X1** =
  five-class input-provisioning pre-flight (content, conventions, build prefs, observability).
- **No gating.** Purely advisory; never fails a build or blocks a pipeline run. No built-in
  gate flag either — CI that wants to gate parses the FR-W10 JSON (`schema_version`'d) and
  decides itself (R5-F3 rejected; see Appendix B).
- **No mechanism/friction analysis.** Sapper/FDE preflight own routing/invention landmines.
- **No OTel emission in v1.** Deferred until after the strtd8 pilot (R3-S5 rejected; see plan
  Appendix B).

## 4. Open Questions

OQ-1 through OQ-6 from v0.1 were all resolved by the planning pass — see §0. Remaining:

- **OQ-7 — Kickoff adoption of `assembly-inputs.yaml`.** This capability defines the first
  machine-readable instantiation of the inventory; whether the kickoff machinery (FR-X1/FR-X5)
  adopts it as canonical is a kickoff-docset decision, tracked there, not blocking here.
- **OQ-8 — Planned-vs-built diff.** FR-W12's persisted plan enables a later `wireframe --diff`
  comparing plan against disk; deliberately deferred (Non-Requirements: no drift detection in
  v1). Revisit after first real use at the strtd8 pilot.

---

*v0.2 — Post-planning self-reflective update. 1 requirement rewritten (FR-W4 absence
semantics), 2 added (FR-W13 graceful degradation, FR-W14 anti-divergence cross-check), FR-W1
forms scoped to field level, FR-W9/FR-W11 made concrete, 6 open questions resolved, 2 new.*

*v0.3 — Post-CRP triage of review rounds R1–R6 (28 F-suggestions applied, 2 rejected — see
Appendix A/B). Headline fix: lenient-Prisma-parser recoverability check (R6-F1). Added
FR-W15 (content inputs), FR-W16 (public API); hardened FR-W2/W4/W6–W13.*

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
| R1-F1 | Kickoff status → wireframe status mapping table | composer-2.5 R1 | Merged into FR-W4 ("Kickoff status mapping") | 2026-06-05 |
| R1-F2 | `schema_version` + stability policy on JSON | composer-2.5 R1 | Merged into FR-W10 | 2026-06-05 |
| R1-F3 | Mirror `generate views --views` flag | composer-2.5 R1 | Merged into FR-W7 (all-three-generators spelling) | 2026-06-05 |
| R1-F4 | FR-W11 shim input-discovery contract | composer-2.5 R1 | Merged into FR-W11 ("Input discovery" bullet) | 2026-06-05 |
| R1-F5 | Byte-identical canonical JSON determinism | composer-2.5 R1 | Merged into FR-W2 (operationalized) | 2026-06-05 |
| R2-F1 | FR-W6 status-override precedence rules | composer-2.5 R2 | Merged into FR-W6 ("Override precedence") | 2026-06-05 |
| R2-F2 | Content-inputs section (read-only) | composer-2.5 R2 | New FR-W15 | 2026-06-05 |
| R2-F3 | Exit 2 on invalid assembly-inputs YAML | composer-2.5 R2 | Merged into FR-W9 exit semantics | 2026-06-05 |
| R2-F4 | `--only-issues` filter | composer-2.5 R2 | Merged into FR-W9 (footer keeps full totals) | 2026-06-05 |
| R2-F5 | Tool-boundary note (wireframe/sapper/FR-X1) | composer-2.5 R2 | Merged into §3 Non-Requirements | 2026-06-05 |
| R3-F1 | `--manifest` parity for `app.yaml` | composer-2.5 R3 | Merged into FR-W7 (`--app` as optional alias) | 2026-06-05 |
| R3-F2 | `inputs_fingerprint` on persisted JSON | composer-2.5 R3 | Merged into FR-W12 (with `_meta` exclusion per R5-F1) | 2026-06-05 |
| R3-F3 | Shape summary line | composer-2.5 R3 | Merged into FR-W9 footer | 2026-06-05 |
| R3-F4 | Path confinement to `project_root` | composer-2.5 R3 | Merged into FR-W6 + FR-W9 exit semantics | 2026-06-05 |
| R3-F5 | Completeness `defaults` lists presence-rule signals | composer-2.5 R3 | FR-W4 `defaults` consequence + plan Step 2 Completeness bullet | 2026-06-05 |
| R4-F1 | `--json` → stdout, Rich only with `--verbose` | composer-2.5 R4 | Merged into FR-W9/FR-W10 | 2026-06-05 |
| R4-F2 | Cascade readiness footer line | composer-2.5 R4 | Merged into FR-W9 footer | 2026-06-05 |
| R4-F3 | Dual persist-path precedence + `emit_context` | composer-2.5 R4 | Merged into FR-W11 ("Artifact precedence") | 2026-06-05 |
| R4-F5 | Stable public API promise | composer-2.5 R4 | New FR-W16 | 2026-06-05 |
| R5-F1 | `_meta` exclusion from determinism + fingerprint | composer-2.5 R5 | Merged into FR-W2 | 2026-06-05 |
| R5-F2 | 500-char cap + `error_truncated` on parser errors | composer-2.5 R5 | Merged into FR-W13 | 2026-06-05 |
| R5-F4 | Project-relative forward-slash JSON paths | composer-2.5 R5 | Merged into FR-W2 | 2026-06-05 |
| R5-F5 | Shim writes `wireframe-error.json`, still exit 0 | composer-2.5 R5 | Merged into FR-W11 ("Discoverable failure") | 2026-06-05 |
| R5-F6 | `--pages-authoring` in FR-W7 | composer-2.5 R5 | Merged into FR-W7 (requires `--pages`) | 2026-06-05 |
| R6-F1 | Lenient Prisma parser ⇒ recoverability check; fix §0 premise; scope placeholder rule | claude-opus-4-8[1m] R6 | FR-W4 "Schema invalidity & placeholder scoping" + FR-W13 rewrite + §0 row corrected | 2026-06-05 |
| R6-F2 | FR-W8 exact five conventional filenames, no glob | claude-opus-4-8[1m] R6 | FR-W8 rewritten | 2026-06-05 |
| R6-F3 | Worst-wins section-status composition rule | claude-opus-4-8[1m] R6 | FR-W4 "Composition rule" (also covers R2-S3/R5-S6 Services cell) | 2026-06-05 |
| R6-F4 | FR-W12 atomic persist + unwritable-target semantics | claude-opus-4-8[1m] R6 | Merged into FR-W12 | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R4-F4 | Mirror `--ai-agent-spec` and list effective agent spec | composer-2.5 R4 | Echoes a generator *rendering* input with no app-shape consequence; wireframe stays manifest-derived. Revisit post-pilot if users ask "which model runs my passes" at kickoff. | 2026-06-05 |
| R5-F3 | Opt-in `--fail-on-issues` exit-1 gate | composer-2.5 R5 | Conflicts with the deliberate "No gating" non-requirement even as opt-in; CI can gate from the `schema_version`'d FR-W10 JSON without the tool growing gate semantics. Revisit post-pilot. | 2026-06-05 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:05:00 UTC
- **Scope**: Dual-document review — requirements clarity, testability, kickoff integration.

**Executive summary:**
- Kickoff Status column and wireframe status enum need an explicit mapping table.
- FR-W7 flag surface is incomplete vs actual generator CLIs (`generate views` is separate).
- FR-W10 JSON needs version + stability contract before pipeline/CI adoption.
- FR-W11 needs input-discovery requirements, not only env-gate mechanics.
- FR-W2 determinism should name canonical serialization, not only "byte-identical plan" in prose.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Add an explicit mapping table from kickoff inventory **Status** (`authored` \| `placeholder` \| `absent` in `ASSEMBLY_INPUTS_TEMPLATE.md`) to wireframe section statuses (`planned` \| `defaults` \| `placeholder` \| `not_defined` \| `invalid`). | Kickoff FR-X1/FR-X5 use three provisioning states; FR-W4 defines five wireframe states with different absence semantics — without mapping, the same row can be interpreted two ways at the human bookend. | New subsection under FR-W4 or §0 Planning Insights | Table-driven unit test: each kickoff status + manifest presence tuple maps to exactly one wireframe status. |
| R1-F2 | Interfaces | medium | Require `schema_version` (and a one-line consumer-stability policy) on `--json` output in FR-W10, matching the pattern used by sapper/nemawashi friction reports. | FR-W10 says "full WireframePlan as JSON" but fixes no contract; pipeline hooks and future `wireframe --diff` (OQ-8) will break silently on field renames. | FR-W10 | CI validates emitted JSON against a checked-in schema; bumping fields without `schema_version` increment fails the test. |
| R1-F3 | Interfaces | medium | Expand FR-W7 to require CLI flags for **`generate views`** inputs (`--views` manifest path), not only `generate backend` flags — views are a separate generator (`cli_generate.py:383`). | FR-W7 says flags mirror `generate backend`; composite views are planned via `parse_views` / `render_views`, so a user who only passes backend flags cannot wireframe views even when `views.yaml` exists. | FR-W7 | CLI test: `--views prisma/views.yaml` populates the Composite views section as `planned`. |
| R1-F4 | Ops | high | Extend FR-W11 with **input discovery**: how the shim locates `project_root`, optional `assembly-inputs.yaml`, and manifest paths when invoked from cap-dev-pipe (env vars, provenance file, or convention defaults per FR-W8). | FR-W11 specifies opt-in gate and output dir but not inputs — the shim cannot meet FR-W6–W8 without a declared discovery contract. | FR-W11, new bullet after env-gate sentence | Shim integration test with `pipeline.env` + missing manifests: still emits JSON listing `not_defined`/`defaults` with recorded input paths, exit 0. |
| R1-F5 | Validation | medium | Make FR-W2 testable: same inputs ⇒ **byte-identical** canonical JSON from `to_json()` (stable key order, normalized paths) in addition to in-memory plan equality. | "Deterministic" is stated but not operationalized; Rich rendering can differ cosmetically while JSON is the machine contract for FR-W10/W12. | FR-W2 + FR-W10 cross-reference | Two consecutive CLI `--json` runs on a fixture diff empty; reordering YAML merge inputs does not change output when paths resolve identically. |

**Endorsements:** none — first round.

**Disagreements:** none — first round.

#### Review Round R2 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:20:00 UTC
- **Scope**: Requirements gaps — content visibility, exit semantics, end-user filtering, tool boundaries.

**Executive summary:**
- FR-W6 status override needs precedence rules vs parser-derived status.
- Content bucket inputs deserve a read-only wireframe section for kickoff value.
- Exit-code contract should cover invalid assembly-inputs YAML, not only unreadable files.
- `--only-issues` (or equivalent) is a low-effort UX win for large manifests.
- Clarify wireframe vs sapper vs FR-X1 in Non-Requirements to prevent scope creep and user confusion.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | medium | Specify FR-W6 **status override precedence**: override applies when the path is missing or when kickoff inventory marks `absent`/`placeholder`; when the manifest file exists, parser-derived `planned`/`invalid`/`placeholder` (sentinel detection) takes precedence unless override is `absent` and file is missing. | FR-W6 promises override but defines no conflict rules; without them implementers cannot sync with kickoff inventory (R1-F1 mapping) without fighting live parser results. | FR-W6, new paragraph after merge rule | Table-driven tests for override+presence combinations; each resolves to one section status. |
| R2-F2 | Architecture | medium | Add FR-W1 bullet (or FR-W15): **Content inputs** section listing referenced `app/pages/*.md` and AI prompt paths from manifests, status-only (`planned`/`placeholder`/`not_defined`), with consequence lines — explicitly **non-generative** (bucket 2/4 visibility). | ASSEMBLY_INPUTS_TEMPLATE catalog includes content rows; wireframe's value proposition is "planned vs undefined" at the human bookend, but content wiring is invisible today. | FR-W1 enumeration list | Wireframe with `pages.yaml` referencing missing markdown: content row `not_defined` with consequence text. |
| R2-F3 | Validation | medium | Expand FR-W9 exit semantics: exit **2** when any `--inputs` file is unreadable **or** fails assembly-inputs YAML schema validation (unknown top-level keys, malformed structure); manifest parser failures remain **non-fatal** (`invalid` section status per FR-W13). | FR-W9 only names unreadable inputs; strict loader in plan Step 1 mirrors `parse_app_manifest` loud-fail — silent continuation on bad inventory YAML would produce nonsense paths. | FR-W9 + FR-W13 cross-reference | Corrupt assembly-inputs YAML ⇒ exit 2; corrupt `pages.yaml` ⇒ plan continues with Pages `invalid`. |
| R2-F4 | Ops | low | Add optional **`--only-issues`** (or `--status not-planned`) to FR-W9: render/JSON-emit only sections/items whose status ≠ `planned`, preserving footer counts. | Full tree on a mature project is noisy; kickoff reviewers care about gaps. Filtering is a one-flag UX win atop existing status model. | FR-W9 | CLI test: fixture with mixed statuses; filtered output omits `planned` sections but counts line matches full plan. |
| R2-F5 | Architecture | low | Extend Non-Requirements with a **tool boundary** note: wireframe = Group F assembly shape; sapper = Prime/EMIT skeleton tunnel survey; FR-X1 = five-class kickoff pre-flight — wireframe does not subsume either. | Non-Requirements says "Not FR-X1" and "No mechanism/friction" but not sapper; users running cap-dev-pipe may conflate the two pre-gen reports. | §3 Non-Requirements, new bullet | Doc review: boundary paragraph cites sapper host inputs (ForwardManifest) vs wireframe inputs (assembly manifests). |

**Endorsements** (prior untriaged suggestions):
- R1-F3: `--views` flag parity is required for composite-view planning.
- R1-F5: Byte-identical JSON determinism should be a named acceptance test.

**Disagreements:** none.

#### Review Round R3 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:35:00 UTC
- **Scope**: Requirements hardening — CLI parity, provenance, security, completeness semantics, UX metrics.

**Executive summary:**
- FR-W7 should mirror **`generate scaffold --manifest`**, not invent `--app`.
- FR-W12 persisted JSON needs an **inputs fingerprint** to enable OQ-8 and audit reproducibility.
- FR-W6 needs path confinement to `project_root` after YAML-relative resolution.
- Completeness `defaults` should expose presence-rule fallback explicitly vs authored signals.
- FR-W9 shape summary complements status counts for end-user scanability.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Interfaces | medium | FR-W7 MUST accept **`--manifest`** for `app.yaml` (same name as `generate scaffold`), treating `--app` only as an optional alias. | FR-W7 says flags mirror generators; scaffold uses `--manifest` (`cli_generate.py:323`) while the plan proposes `--app` — a direct parity violation that will confuse kickoff runbooks. | FR-W7 | CLI help lists `--manifest`; `--manifest ./app.yaml` and scaffold use identical flag spelling. |
| R3-F2 | Data | medium | FR-W12 (and FR-W10 JSON) MUST include an **`inputs_fingerprint`**: stable hash of resolved manifest paths + content SHA256 (or mtime fallback) for each catalog entry. | OQ-8 deferred diff needs to know whether the plan changed because inputs changed; status counts alone are insufficient. Fingerprint is cheap once parsers read files. | FR-W12 + FR-W10 | Two runs with identical manifests ⇒ identical fingerprint; editing `schema.prisma` bumps fingerprint only. |
| R3-F3 | Ops | low | FR-W9 MUST add a **shape summary** line (entity count, CRUD route count, page count, view count, AI pass count) in addition to the status counts footer. | "N planned / M defaults …" answers provisioning; it does not answer "how big is this app?" — the primary kickoff question at the DATA MODEL bookend. | FR-W9, after counts line | Fixture with known model/view/page counts ⇒ summary line matches parser-derived totals. |
| R3-F4 | Security | medium | FR-W6 MUST reject manifest paths whose resolution escapes **`project_root`** (e.g. `../../../etc/passwd` via relative YAML paths) with exit 2 and a clear error — before reading file contents. | Assembly-inputs paths are relative to the YAML file; without confinement, a malicious or mistaken inventory could wireframe/read arbitrary filesystem locations on CI hosts. | FR-W6 + FR-W9 exit semantics | YAML with `schema: ../../../../etc/passwd` ⇒ exit 2; valid in-repo relative path succeeds. |
| R3-F5 | Architecture | low | FR-W1 Completeness bullet MUST state that when `completeness.yaml` is **`defaults`**, the plan lists the **presence-rule fallback** signals (from `derived.py` default path) separately from authored weighted signals when the manifest is `planned`. | FR-W4 maps absent completeness.yaml to `defaults` / "presence-rule fallback scoring" but FR-W1 only says "signal set from completeness.yaml" — implementers may emit an empty section under defaults. | FR-W1 Completeness bullet + FR-W4 table cross-ref | Absent completeness.yaml ⇒ Completeness section `defaults` with enumerated presence-rule entities; authored yaml ⇒ listed weighted signals. |

**Endorsements** (prior untriaged suggestions):
- R1-S2: `--out`/`--project` alias reduces friction across generate + wireframe CLIs.
- R2-F4: `--only-issues` filter is the highest UX ROI item left in FR-W9.
- R1-S1: Pipeline shim stage/discovery remains blocking for FR-W11 delivery.

**Disagreements:** none.

#### Review Round R4 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:50:00 UTC
- **Scope**: End-user actionability, JSON/CLI contract, programmatic API, generator flag parity.

**Executive summary:**
- FR-W10 needs sapper-aligned `--json` stdout semantics.
- Cascade readiness line closes the loop from "planned shape" to "which generate commands to run".
- FR-W11 dual-output paths need explicit precedence, not accidental overwrite.
- `--ai-agent-spec` belongs in wireframe when AI layer is planned.
- Stable public API for `build_wireframe_plan` enables kickoff integration without CLI subprocess.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Interfaces | medium | FR-W10: **`--json` writes to stdout** and suppresses Rich rendering unless a **`--verbose`** flag is set; persisted file (FR-W12) still written unless `--no-write`. | Sapper uses this contract (`cli_sapper.py:45`); FR-W10 is silent on stdout vs stderr vs file, so CI/pipeline consumers will parse contaminated output. | FR-W10 + FR-W9 | `--json` stdout is parseable JSON only; Rich tree absent without `--verbose`. |
| R4-F2 | Ops | high | FR-W9 MUST append a **cascade readiness** line after counts/shape summary: for each of `generate scaffold`, `generate backend`, `generate views`, emit `ready` or `blocked(<primary reason>)` from section statuses. | Problem Statement positions wireframe as pre-generation feedback; without readiness hints users still mentally map sections → CLI commands. Purely derived from existing statuses — high value, low effort. | FR-W9, new sentence after footer counts | Schema `invalid` ⇒ backend `blocked`; views.yaml `not_defined` ⇒ views `blocked(missing views.yaml)`; all planned ⇒ all `ready`. |
| R4-F3 | Ops | medium | FR-W11 MUST state **artifact precedence**: pipeline shim writes only under `pipeline-output/<run>/wireframe/`; direct CLI writes `.startd8/wireframe/`; neither overwrites the other; JSON includes `emit_context` (`cli` \| `pipeline`). | Two persist paths (FR-W12 vs FR-W11) without rules invite "which plan is current?" confusion after a local re-run during a pipeline session. | FR-W11 + FR-W12 | Shim run does not touch `.startd8/`; local CLI does not touch `$OUTPUT_DIR`; JSON field present. |
| R4-F4 | Interfaces | low | FR-W7 MUST mirror **`--ai-agent-spec`** from `generate backend` (`cli_generate.py:156-161`): when `ai_passes.yaml` is `planned`, wireframe lists the effective runtime agent spec (flag value or documented default). | AI layer is in FR-W1 Services; the runtime model is part of planned app shape when passes exist — omitting the flag hides a generator input users already tune. | FR-W7 + FR-W1 Services bullet | `--ai-passes` + `--ai-agent-spec foo:bar` ⇒ plan JSON lists `agent_spec: foo:bar`. |
| R4-F5 | Architecture | low | Add FR-W1 note (or FR-W15): **`build_wireframe_plan()` and `load_assembly_inputs()` are stable public API** exported from `startd8.wireframe` for programmatic use (kickoff FR-X1/FR-X5, TUI, tests) — not CLI-only. | Plan Shape shows public API in `__init__.py` but requirements never promise stability; kickoff adoption (OQ-7) needs importable plan derivation without subprocess overhead. | FR-W1 intro or new API bullet | Import test: `from startd8.wireframe import build_wireframe_plan` works; semver/doc note in `__init__.py`. |

**Endorsements** (prior untriaged suggestions):
- R3-F4: Path confinement on assembly-inputs is mandatory before CI adoption.
- R1-F1: Kickoff Status mapping table still blocks clean FR-X5/wireframe convergence.
- R3-F1: `--manifest` parity prevents the most common copy-paste CLI failure.

**Disagreements:** none.

#### Review Round R5 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 21:15:00 UTC
- **Scope**: Determinism boundaries, encoding, CI opt-in strictness, cross-platform JSON, requirements↔plan flag gaps.

**Executive summary:**
- FR-W2 and R3-F2 fingerprint need an explicit non-deterministic `_meta` carve-out.
- Parser errors and UTF-8 failures need bounded, testable surface messages.
- Optional `--fail-on-issues` enables CI without rewriting the advisory default in FR-W9.
- JSON paths must be normalized for cross-platform determinism.
- FR-W7 is incomplete vs `generate backend` for `--pages-authoring`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Data | medium | FR-W2 MUST clarify: **`_meta`** fields (`generated_at`, `startd8_version`, `emit_context`) are **excluded** from byte-identical canonical JSON and from `inputs_fingerprint` (R3-F2); only the deterministic plan body is hashed. | FR-W2 says "byte-identical plan" without scoping audit metadata — implementers will either skip useful metadata or break determinism tests (R1-F5). | FR-W2, new sentence after "byte-identical plan" | Canonical JSON diff empty across runs; `_meta.generated_at` may change; fingerprint stable. |
| R5-F2 | Validation | medium | FR-W13 MUST cap **`invalid` parser error text** at **500 characters** in tree + JSON, set **`error_truncated: true`** when capped, and preserve full text only in debug logs. | Strict parsers emit multi-line errors; embedding unbounded tracebacks in FR-W10 JSON bloats pipeline artifacts and breaks snapshot tests. | FR-W13 + FR-W10 | Synthetic 2k-char parser error ⇒ JSON message ≤500 + flag set. |
| R5-F3 | Ops | low | FR-W9 MUST add optional **`--fail-on-issues`**: exit **1** when any section status ∉ `{planned, defaults}`; default remains advisory exit **0** (consistent with §3 "No gating"). | Kickoff/CI users want a cheap gate ("any `invalid` or `not_defined`?") without making wireframe blocking by default. Opt-in preserves Non-Requirements. | FR-W9 exit semantics paragraph | `--fail-on-issues` + fixture with one `invalid` section ⇒ exit 1; default invocation ⇒ exit 0. |
| R5-F4 | Data | low | FR-W10 JSON MUST emit artifact paths as **project-relative** strings with **forward slashes** regardless of host OS (FR-W2 cross-platform determinism). | Windows backslashes in persisted plans break byte-identical comparisons and OQ-8 diff on mixed dev/CI hosts. | FR-W10 + FR-W12 | Windows CI job: JSON paths use `/`; same fixture on macOS/Linux matches. |
| R5-F5 | Ops | medium | FR-W11 MUST require the shim to write **`wireframe-error.json`** on internal failure while still exiting **0** — same non-blocking contract, discoverable failure. | FR-W11: "always exits 0, never blocks" — without an error artifact, pipeline operators cannot tell opt-off vs crash vs empty manifests. | FR-W11, new bullet after output dir sentence | Simulated exception in shim ⇒ exit 0 + error JSON under `pipeline-output/.../wireframe/`. |
| R5-F6 | Interfaces | medium | FR-W7 MUST list **`--pages-authoring`** (requires `--pages`, mirrors `cli_generate.py:137-141`) and wireframe MUST enumerate the authoring artifacts that flag adds — per plan Step 2/R2-S4. | FR-W7: "mirroring `generate backend`'s flags" — `--pages-authoring` is a documented backend flag absent from FR-W7 while plan Step 4 already plans it (R2-S4). Dual-doc drift. | FR-W7 flag list + FR-W1 Pages bullet | `--pages --pages-authoring` adds authoring paths; `--pages-authoring` alone ⇒ exit 2 with same message as generate backend. |

**Endorsements** (prior untriaged suggestions):
- R5-S1: `_meta` exclusion is the correct resolution for fingerprint + determinism tension.
- R4-F3: Artifact precedence rules pair with shim error JSON for operational clarity.
- R1-F2: `schema_version` on JSON remains prerequisite before external consumers depend on FR-W10.

**Disagreements:** none.

#### Review Round R6 — claude-opus-4-8[1m] — 2026-06-05

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-06-05 18:20:00 UTC
- **Scope**: Code-verified requirements pass — strict-parser premise vs actual lenient Prisma parser, FR-W8 convention testability, multi-manifest status semantics, FR-W12 persist failure modes. (Feature Requirements)

**Executive summary:**
- §0 Planning Insight "Strict parsers loud-fail on bad manifests" is **factually wrong for `schema.prisma`**: `parse_prisma_schema` is lenient by design (never raises; skips unparseable lines; empty schema for blank input — `languages/prisma_parser.py:276-283`). FR-W4's `invalid` ("fails its strict parser") is therefore **undetectable** for the keystone manifest as specified.
- FR-W8's "`prisma/*.yaml`" names a glob, not the five per-key conventional filenames — untestable and order-sensitive as written.
- FR-W4 maps one absent manifest → one status, but three sections derive from ≥2 manifests; no composition rule when contributors disagree.
- FR-W12 has no failure semantics (unwritable dir, partial write) for a SHOULD-persist artifact that OQ-8 and pipeline consumers will parse.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Risks | high | Rewrite the `invalid` definition in FR-W4 ("manifest present but fails its strict parser") and FR-W13 ("fails its strict parser MUST surface as `invalid`") to account for the **lenient** Prisma parser: `parse_prisma_schema` never raises — it skips unparseable lines and returns an empty schema for blank input (`prisma_parser.py:276-283`). Require schema invalidity to be detected via a **recoverability check** (raw-text `model`/`enum` block count vs parsed count; mismatch ⇒ `invalid`), and correct the §0 row "Strict parsers loud-fail on bad manifests" to "YAML manifest parsers loud-fail; the Prisma parser is lenient". Also scope FR-W4's `placeholder` rule: "zero-model parsed schema ⇒ placeholder" MUST apply only when the raw text contains no dropped `model` blocks — otherwise it is `invalid`, not `placeholder`. | The five-status model's most safety-critical transition (`invalid` on the contract) cannot fire as specified; a corrupted `schema.prisma` would render as `placeholder` or a partial `planned` entity list — exactly the false-confidence failure FR-W13 exists to prevent. All of R1–R5 inherited this wrong premise. | FR-W4 status definitions + FR-W13 first sentence + §0 Planning Insights row 2 | Garbled-model fixture (unbalanced braces, 3 `model` keywords, 1 parsed) ⇒ schema section `invalid` with dropped-block message; empty template schema with zero `model` keywords ⇒ `placeholder`. |
| R6-F2 | Data | medium | FR-W8: replace "`prisma/*.yaml`" with the **five exact conventional filenames** per the `ASSEMBLY_INPUTS_TEMPLATE.md` catalog — `prisma/human_inputs.yaml`, `prisma/ai_passes.yaml`, `prisma/pages.yaml`, `prisma/completeness.yaml`, `prisma/views.yaml` — each mapped to its catalog key. | As written, "the documented path convention (`prisma/schema.prisma`, root `app.yaml`, `prisma/*.yaml`)" is a glob: it does not say which file feeds which catalog key, would match stray YAML (e.g. `prisma/notes.yaml`), and glob enumeration order threatens FR-W2 determinism. The template (rows 19-25) already fixes the exact names — the requirement should cite them. | FR-W8 sentence "documented path convention (…)" | Unit test: empty inputs in a project containing exactly the five conventional files resolves each catalog key to its named path; a stray `prisma/extra.yaml` is ignored. |
| R6-F3 | Data | medium | Add to FR-W4 a **section-status composition rule** for sections derived from multiple manifests (Forms = schema + `human_inputs.yaml`; Services = schema + `ai_passes.yaml`; Composite views = schema + `views.yaml`): worst-wins precedence `invalid > placeholder > not_defined > defaults > planned`, consequence line from the worst contributor. | The FR-W4 table is keyed by single absent manifest; it is silent on, e.g., Forms when schema is `planned` and `human_inputs.yaml` is `invalid`. R2-S3/R5-S6 patched only Services×schema; without a general rule, the same input set can legitimately render two different wireframes — violating FR-W2's "same inputs ⇒ byte-identical plan". | FR-W4, new paragraph after the absence table | Parametrized matrix test over (primary status × secondary status) pairs; each resolves to exactly one documented section status. |
| R6-F4 | Ops | low | FR-W12: specify persist **failure semantics** — write MUST be atomic (temp file + rename; never a partial JSON on disk), the directory is created if missing, and an unwritable target degrades to a warning with exit 0 (advisory contract preserved). | FR-W12 says SHOULD persist but nothing about interrupted writes or read-only roots; OQ-8 diff and pipeline consumers will parse this file, and a truncated JSON poisons them silently. Cheap to specify now, painful to retrofit. | FR-W12, new sentence after the suggested path | Kill-mid-write test: on-disk file is either previous or new complete JSON; read-only `.startd8/` ⇒ rendered output + warning, exit 0. |

**Endorsements** (prior untriaged suggestions):
- R5-F2 (error-text cap): right call, but note its premise "strict parsers emit multi-line errors" holds only for the YAML manifests — pair it with R6-F1 for the schema path.
- R3-F4: path confinement is the only Security-area item across all rounds and should land before pipeline/CI use.
- R1-F4: shim input discovery is still the largest unresolved FR-W11 gap after five rounds.

**Disagreements:** none.
