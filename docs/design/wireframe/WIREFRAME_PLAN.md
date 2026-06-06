# Basic Wireframing Capability — Implementation Plan

**Version:** 1.2
**Date:** 2026-06-05
**Status:** Draft (post-CRP R1–R6 triage; v1.2 consumer-agnostic naming, aligned to
requirements v0.4 §1.0 — the wireframe is SDK-owned; strtd8 is the reference consumer, first
of many)
**Requirements:** [`WIREFRAME_REQUIREMENTS.md`](WIREFRAME_REQUIREMENTS.md)

---

## 1. Shape

New read-only module `src/startd8/wireframe/` + one CLI command + one cap-dev-pipe shim.
No generator refactor. Everything derives from the **same parsers the generators use**.

```
src/startd8/wireframe/
├── __init__.py        # public API: load_assembly_inputs, build_wireframe_plan
├── inputs.py          # AssemblyInputs + assembly-inputs.yaml loader/merger (FR-W6..W8)
├── plan.py            # WireframePlan dataclasses + build_wireframe_plan() (FR-W1..W5)
└── render.py          # Rich tree renderer + JSON serializer (FR-W9, FR-W10)
src/startd8/cli_wireframe.py   # `startd8 wireframe` (registered in cli.py)
scripts/run_wireframe.py       # cap-dev-pipe shim (FR-W11) — never blocks, exits 0
```

## 2. Steps

### Step 1 — `inputs.py`: assembly-inputs YAML (FR-W6, FR-W7, FR-W8)

`AssemblyInputs` frozen dataclass: one optional `Path` per catalog entry of
`ASSEMBLY_INPUTS_TEMPLATE.md` §"Contract / assembly manifests" (schema, app, human_inputs,
ai_passes, pages, completeness, views) + `project_root`.

`load_assembly_inputs(yaml_paths: Sequence[Path], overrides: dict, project_root: Path)`:
1. Start from the **five exact conventional filenames** + contract + scaffold manifest mapped
   per catalog key (FR-W8/R6-F2: `prisma/schema.prisma`, root `app.yaml`,
   `prisma/{human_inputs,ai_passes,pages,completeness,views}.yaml`) resolved against
   `project_root` — paths recorded but existence checked later. No glob enumeration.
2. For each YAML file in order: read as **UTF-8** (`UnicodeDecodeError` ⇒ exit 2, R5-S2),
   `yaml.safe_load`, strict top-level key check (mirror `parse_app_manifest`'s loud-fail style,
   `scaffold_codegen/manifest.py:32`), merge last-wins per key (FR-W6). Schema:
   `inputs: {schema: {path: <p>, status?: <override>}, …}` — per-key `status:` override
   supported (R2-S1): override labels the section when the file is absent; parser outcome wins
   when the file exists. Paths relative to the YAML file's directory. Overwrites of an
   already-set key append to `merge_warnings` (R5-S5).
3. **Confine paths** (R3-F4): any resolved manifest path escaping `project_root` ⇒ exit 2
   before reading.
4. Apply direct CLI flag overrides last (FR-W7).

Worked `assembly-inputs.yaml` example (R1-S5; also lands in the template via Step 7):

```yaml
# docs/ASSEMBLY_INPUTS.yaml — machine-readable instantiation of ASSEMBLY_INPUTS_TEMPLATE.md
inputs:
  schema: {path: prisma/schema.prisma}
  app: {path: app.yaml}
  human_inputs: {path: prisma/human_inputs.yaml}
  ai_passes: {path: prisma/ai_passes.yaml}
  pages: {path: prisma/pages.yaml}
  completeness: {path: prisma/completeness.yaml, status: absent}   # declared ahead of authoring
  views: {path: prisma/views.yaml, status: absent}
```

### Step 2 — `plan.py`: the plan model (FR-W1..W5)

Statuses (per-item and per-section): `planned | defaults | placeholder | not_defined | invalid`.
**Per-manifest absence semantics** (Phase-3 discovery — absence ≠ uniformly "not defined"):

| Input absent | Section status | Consequence line |
|---|---|---|
| `schema.prisma` | everything entity-derived `not_defined` | "no contract → no entities, CRUD, forms, or views" |
| `app.yaml` | scaffold `defaults` | "default scaffold (app/, SQLite ./data/app.db, Dockerfile on, py3.11)" — `parse_app_manifest(None)` yields full defaults |
| `pages.yaml` | content pages `not_defined` | "no content pages or site nav" |
| `views.yaml` | composite views `not_defined` | "no composite views" |
| `ai_passes.yaml` | AI layer `not_defined` | "no AI service/passes" |
| `human_inputs.yaml` | owned-field policy `defaults` | "no owned-field omissions beyond server-managed columns" |
| `completeness.yaml` | completeness `defaults` | "presence-rule fallback scoring" |

`build_wireframe_plan(inputs) -> WireframePlan` sections, each built from the generator's own
parser (FR-W3):

- **Scaffold/Container** — `parse_app_manifest` → name, package, db path, Dockerfile y/n,
  python version, migrations, log file (`scaffold_codegen/manifest.py:19-30`).
- **Services** — FastAPI app + web mount **when schema is `planned` or `placeholder`**; when
  schema is `not_defined`/`invalid`, Services degrades accordingly — never `planned` AI/web
  items (R2-S3/R5-S6). Export endpoints; AI service + one item per `AiPass`
  (`ai_layer.py:parse_ai_passes:108`).
- **Entities & CRUD** — `parse_prisma_schema` (`languages/prisma_parser.py:276`) → per model:
  routes (list/get/create/update/delete), table, Pydantic models; paths from
  `backend_codegen.crud_generator.CANONICAL_LAYOUT`.
- **Pages & nav** — `parse_pages` (`pages_generator.py:67`) → slug/title/nav per `ContentPage`,
  nav_override handling. With `--pages-authoring` (R2-S4): add the authoring artifacts
  (`app/pages_admin.py`, `app/pages_io.py`, authoring templates), gated exactly like
  `cli_generate.py:137-225`.
- **Forms** — per entity, field-level (cheap — Phase-3 discovery): writable fields via
  `htmx_generator._writable_fields`/`_form_fields` (promote to public names, ~2-line change),
  with owned/server-managed omissions from `parse_human_inputs`.
- **Composite views** — `parse_views(text, known_entities=…)` (`view_codegen/manifest.py:100`)
  → per `ViewSpec`: name, kind, route, root, panel count. Requires parsed schema for
  `known_entities`; if schema absent/invalid, mark section `invalid`-degraded, don't crash.
- **Content inputs** (R2-S2, FR-W15) — read-only: `app/pages/*.md` paths referenced from
  `pages.yaml` `content:` + prompt paths referenced from `ai_passes.yaml`, each
  `planned`/`placeholder`/`not_defined` with consequence lines. No generation claims.
- **Completeness** — completeness loader from `derived.py:250` **promoted to a public name**
  (R6-S2 — same rule as the htmx helpers; no cross-module private imports) → signal list.
  Under `defaults`, enumerate the presence-rule fallback signals, distinct from authored
  weighted signals (R3-F5).

**Parser failure handling (FR-W13; corrected by R6-S1):** the YAML manifest parsers are
strict/loud — exceptions caught per-manifest → `invalid` (message capped at 500 chars,
`error_truncated` flag — R5-F2; UTF-8 failures ⇒ `invalid` "not valid UTF-8" — R5-S2). But
`parse_prisma_schema` is **lenient** (never raises; skips unparseable lines;
`prisma_parser.py:276-283`), so the schema gets a **recoverability check**: compare raw-text
`model `/`enum ` block count vs parsed counts; mismatch ⇒ `invalid` with "lenient parse
dropped N blocks". Never abort the whole plan.

**Status composition (R6-S4, FR-W4):** sections fed by ≥2 manifests (Forms, Services,
Composite views) take worst-wins precedence `invalid > placeholder > not_defined > defaults >
planned`; consequence line from the worst contributor.

Placeholder detection v1 (FR-W4, deliberately minimal): zero-model parsed schema ⇒
`placeholder` **only when no model blocks were dropped** (else `invalid` — R6-S1); any
`REPLACE_WITH_` sentinel in a YAML manifest's scalar values ⇒ `placeholder`. Documented as a
subset of kickoff FR-X1 semantics.

`WireframePlan` carries `input_provenance` per catalog key — `{path, resolved_path, source:
convention|yaml|flag}` (R3-S2) — plus `merge_warnings` from Step 1.

### Step 3 — `render.py` (FR-W9, FR-W10, FR-W12)

- Rich `Tree` grouped by section (pattern: `cli_manifest.py:132-156`), status-colored
  (green=planned, cyan=defaults, yellow=placeholder, dim=not defined, red=invalid — color +
  text label, sapper pattern `cli_sapper.py:75-114`). Per-section item lists capped at
  `--max-items` (default 25) with "… and N more"; counts stay full totals (R5-S3).
- Footer, three lines: **counts** ("N planned / M defaults / K placeholder / J not defined /
  E invalid"), **shape summary** ("Entities: N | CRUD routes: R | Pages: P | Views: V | AI
  passes: A" — R3-S4), **cascade readiness** ("scaffold: ready | backend: blocked(invalid
  schema) | views: blocked(missing views.yaml)" — derived from section statuses only, R4-S2).
- Consequence lines (FR-W5) rendered under each non-`planned` section.
- `to_json(plan)` — `schema_version` (R1-F2), stable key order, project-relative forward-slash
  paths (R5-F4), `input_provenance` + `merge_warnings` + `inputs_fingerprint` (R3-S2/R3-F2);
  audit fields (`generated_at`, `startd8_version`, `emit_context`) in a top-level `_meta`
  excluded from canonical-body hashing and byte-identical tests (R5-S1).
- Persist to `<project_root>/.startd8/wireframe/wireframe-plan.json` unless `--no-write` —
  **atomic** (`tempfile` in target dir + `os.replace`, `mkdir -p`; unwritable target ⇒ warning
  + exit 0, R6-S5). Markdown summary (`wireframe-summary.md`) reuses the tree's text render
  (R1-S3, persisted in pipeline context).

### Step 4 — `cli_wireframe.py` (FR-W9)

Top-level `startd8 wireframe` (OQ-1 resolved: not under `generate` — it generates no app code;
not under `assist` — that family is run-triage). Options: `--inputs <yaml>` (repeatable),
`--project <root>` (read-root; deliberately NOT aliased to the generators' `--out` write-target
— R1-S2 rejected), per-manifest flags with the generators' exact spellings (R3-S1, R2-S4):
`--schema --pages --ai-passes --human-inputs --completeness --pages-authoring` (backend),
`--manifest` for `app.yaml` (scaffold spelling; `--app` alias), `--views` (views), plus
`--json` (stdout-only machine output; Rich tree suppressed unless `--verbose` — R4-S1),
`--only-issues`, `--max-items`, `--no-write`. Register in `cli.py` beside
`app.add_typer(generate_app, …)` (cli.py:770). Exit 0 always (advisory, non-gating); exit 2 on
unreadable/non-UTF-8/schema-invalid `--inputs` file or a path escaping `project_root`.

### Step 5 — cap-dev-pipe shim (FR-W11)

`scripts/run_wireframe.py` following the Service-Assistant/FDE shim precedent
(`run-prime-contractor.sh:541-548` — env-gated, `set +e`, never blocks). Pipeline edit (in the
**canonical cap-dev-pipe repo**, mirrors via symlink): opt-in block gated on
`STARTD8_WIREFRAME=1` (FDE-style opt-in, not SA-style opt-out — most pipeline projects don't
use the cascade), writing `wireframe-plan.json` + `wireframe-summary.md` into
`$OUTPUT_DIR/wireframe/`.

- **Placement & discovery (R1-S1):** the block runs **early** in `run-prime-contractor.sh`
  (before workflow launch — it is pre-generation visibility, not post-mortem triage like SA).
  `project_root` from `PROJECT_ROOT` in `pipeline.env`; assembly-inputs YAML(s) from optional
  `STARTD8_WIREFRAME_INPUTS`; otherwise FR-W8 convention defaults. Absent manifests ⇒ valid
  `not_defined`/`defaults` plan, exit 0.
- **Artifact precedence (R4-S4):** shim writes only `$OUTPUT_DIR/wireframe/`; direct CLI
  writes `.startd8/wireframe/`; no clobbering; `_meta.emit_context: cli|pipeline`.
- **Crash visibility (R5-S4):** uncaught exception ⇒ still exit 0, but write
  `wireframe-error.json` (`{error_type, message}`) beside intended artifacts; log via
  `get_logger`.

### Step 6 — Tests

`tests/unit/wireframe/`:
- inputs: merge order, last-wins + `merge_warnings`, flag override, convention defaults
  (per-key filename mapping; stray `prisma/extra.yaml` ignored), strict unknown keys, status
  override precedence, path-escape rejection, UTF-8 failures
- plan: fixture manifests (mini schema shaped like the reference consumer's contract) →
  snapshot JSON; per-manifest absence
  semantics table above as parametrized cases; invalid-manifest degradation; **schema
  recoverability** (garbled model block ⇒ `invalid` with dropped-block count — R6-S1);
  **composition matrix** (schema status × secondary status ⇒ documented section status — R6-S4)
- determinism: two runs ⇒ byte-identical canonical JSON; `_meta` may differ; fingerprint
  stable (R1-F5/R5-S1)
- **golden cross-check (FR-W14):** on the **named fixture** `tests/fixtures/wireframe/`
  (reference-consumer-shaped schema + full manifest set — R3-S3), every artifact path in the plan appears
  in actual `render_backend()`/`render_views()`/`render_scaffold()` output and vice versa.
  The fixture MUST enable **every conditional generator surface** (R6-S3): `ai_passes.yaml` +
  `human_inputs.yaml` (AI layer incl. `app/server.py`), `authoring=True`, `completeness_text`
  — beware the kwarg trap: `render_backend(manifest_text=…)` is **ai_passes.yaml**, while
  scaffold's `--manifest` is `app.yaml`. Non-owned content prose (`app/pages/*.md`) is
  excluded from the owned-artifact equality set (R1-S4).
- CLI: `--json` smoke via Typer runner (stdout is JSON-only; no Rich bytes)

### Step 7 — Docs

Update `ASSEMBLY_INPUTS_TEMPLATE.md` footer + `KICKOFF_ASSEMBLY_INPUTS.md` related-links with a
pointer to the wireframe as the machine-readable consumer of the inventory, **including the
worked `assembly-inputs.yaml` example** from Step 1 (R1-S5); CLAUDE.md one-liner under
Commands. Add a **"When to use wireframe vs sapper vs kickoff FR-X1"** comparison table
(inputs scope, output shape, gating, cost — R2-S5). Register the command in
`docs/capability-index/` via the `/capability-index` workflow and add a reference-consumer
pilot one-liner (strtd8, the first of the expected many SDK consumers) for first real use /
OQ-8 feedback (R4-S5).

## 3. Risks

- **Plan/generator divergence** (accepted for v1, OQ-2): mitigated by FR-W14 cross-check test
  with all conditional surfaces enabled (R6-S3).
- **Lenient Prisma parser** (R6-S1): `invalid` schemas are undetectable by exception-catching;
  the recoverability check (raw block count vs parsed count) is the only tripwire — keep it in
  sync if the parser gains strictness later.
- **Private helper imports**: promote `_form_fields`/`_writable_fields` **and the completeness
  loader** (R6-S2) to public names rather than importing privates cross-module; retain private
  aliases delegating to the public names so existing backend_codegen internals/tests are
  untouched (R4-S3).
- **Boundary creep**: pipeline hook is read-only visibility, opt-in, never blocks — consistent
  with Group F "make inputs visible, nothing more".

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
| R1-S1 | Shim placement + input discovery | composer-2.5 R1 | Step 5 "Placement & discovery" (early in run-prime-contractor.sh; PROJECT_ROOT + STARTD8_WIREFRAME_INPUTS) | 2026-06-05 |
| R1-S3 | Markdown summary alongside JSON | composer-2.5 R1 | Step 3 persist + Step 5 (`wireframe-summary.md`) | 2026-06-05 |
| R1-S4 | Cross-check excludes non-owned pages prose | composer-2.5 R1 | Step 6 golden cross-check bullet | 2026-06-05 |
| R1-S5 | Worked `assembly-inputs.yaml` example | composer-2.5 R1 | Step 1 example block + Step 7 template update | 2026-06-05 |
| R2-S1 | Status override implementation + precedence | composer-2.5 R2 | Step 1 item 2 (file-present ⇒ parser wins) | 2026-06-05 |
| R2-S2 | Content-inputs plan section | composer-2.5 R2 | Step 2 new "Content inputs" bullet (pairs FR-W15) | 2026-06-05 |
| R2-S3 | Services degrade when schema absent/invalid | composer-2.5 R2 | Step 2 Services bullet rewritten (merged with R5-S6) | 2026-06-05 |
| R2-S4 | `--pages-authoring` artifacts in plan | composer-2.5 R2 | Step 2 Pages bullet + Step 4 flag | 2026-06-05 |
| R2-S5 | Wireframe vs sapper vs FR-X1 comparison table | composer-2.5 R2 | Step 7 docs | 2026-06-05 |
| R3-S1 | `--manifest` primary flag for app.yaml | composer-2.5 R3 | Step 4 flag list | 2026-06-05 |
| R3-S2 | `input_provenance` in plan/JSON | composer-2.5 R3 | Step 2 closing para + Step 3 `to_json` | 2026-06-05 |
| R3-S3 | Named golden fixture path | composer-2.5 R3 | Step 6 (`tests/fixtures/wireframe/`) | 2026-06-05 |
| R3-S4 | Shape summary line | composer-2.5 R3 | Step 3 footer | 2026-06-05 |
| R4-S1 | `--json` → stdout, Rich behind `--verbose` | composer-2.5 R4 | Step 4 flags | 2026-06-05 |
| R4-S2 | Cascade readiness footer | composer-2.5 R4 | Step 3 footer | 2026-06-05 |
| R4-S3 | Retain private aliases on promotion | composer-2.5 R4 | §3 Risks bullet | 2026-06-05 |
| R4-S4 | Artifact precedence + `emit_context` | composer-2.5 R4 | Step 5 bullet | 2026-06-05 |
| R4-S5 | Capability-index registration + pilot one-liner | composer-2.5 R4 | Step 7 (via `/capability-index` workflow) | 2026-06-05 |
| R5-S1 | `_meta` exclusion from canonical JSON | composer-2.5 R5 | Step 3 `to_json` bullet | 2026-06-05 |
| R5-S2 | UTF-8 read semantics | composer-2.5 R5 | Step 1 item 2 + Step 2 failure-handling para | 2026-06-05 |
| R5-S3 | `--max-items` cap (default 25) | composer-2.5 R5 | Step 3 tree bullet + Step 4 flag | 2026-06-05 |
| R5-S4 | Shim `wireframe-error.json` on crash | composer-2.5 R5 | Step 5 "Crash visibility" | 2026-06-05 |
| R5-S5 | `merge_warnings` on key overwrite | composer-2.5 R5 | Step 1 item 2 + Step 3 JSON | 2026-06-05 |
| R5-S6 | Services bullet wording fix | composer-2.5 R5 | Merged with R2-S3 in Step 2 Services bullet | 2026-06-05 |
| R6-S1 | Schema recoverability check (lenient parser) | claude-opus-4-8[1m] R6 | Step 2 failure-handling para + placeholder scoping + §3 Risks; pairs R6-F1 | 2026-06-05 |
| R6-S2 | Promote completeness loader to public | claude-opus-4-8[1m] R6 | Step 2 Completeness bullet + §3 Risks | 2026-06-05 |
| R6-S3 | Fixture must enable all conditional surfaces + kwarg-trap note | claude-opus-4-8[1m] R6 | Step 6 golden cross-check bullet | 2026-06-05 |
| R6-S4 | Worst-wins status composition rule | claude-opus-4-8[1m] R6 | Step 2 "Status composition"; pairs R6-F3 | 2026-06-05 |
| R6-S5 | Atomic persist write | claude-opus-4-8[1m] R6 | Step 3 persist bullet; pairs R6-F4 | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S2 | `--out` alias for `--project` | composer-2.5 R1 | `--out` names a **write target** in every generator; the wireframe's `--project` is a **read root** for a tool that never writes app files. Aliasing conflates read/write semantics and invites "wireframe wrote nothing to --out" confusion — worse than the muscle-memory papercut it fixes. | 2026-06-05 |
| R3-S5 | OTel metrics from CLI/shim | composer-2.5 R3 | Deferred post-pilot per R6 disagreement: a $0 local advisory command gains little from metric emission, and OTel init on every `startd8 wireframe` invocation is real surface to add before first user feedback (OQ-8 pilot). Revisit if the pipeline hook sees real adoption. | 2026-06-05 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:05:00 UTC
- **Scope**: Dual-document review — robustness, end-user value, quick wins, operational enhancements.

**Executive summary:**
- Pipeline shim lacks placement and input-discovery spec — highest delivery risk for FR-W11.
- CLI flag parity gap: `generate views` flags not mirrored; `--project` vs `--out` naming will confuse users.
- Kickoff inventory Status vocabulary (`authored|placeholder|absent`) is not mapped to wireframe statuses — integration friction with FR-X1/FR-X5.
- JSON output needs schema versioning before CI/pipeline consumers depend on it.
- Low-effort wins: persisted markdown summary, assembly-inputs.yaml example in the template, determinism snapshot test.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Ops | high | Specify **when** the cap-dev-pipe shim runs (pipeline stage + ordering relative to plan-ingestion / prime contractor) and **how** it resolves `project_root` + assembly-input paths from `pipeline.env` / run provenance. | Step 5 only copies the FDE env-gate pattern; cap-dev-pipe projects often lack Group F manifests. Without discovery rules the shim will silently wireframe an empty convention-default tree or the wrong root. | §2 Step 5 — cap-dev-pipe shim | Integration test on a `.cap-dev-pipe/pipeline-output/<run>/` fixture: shim writes to `$OUTPUT_DIR/wireframe/` using paths from `pipeline.env`, exits 0 even when manifests are absent. |
| R1-S2 | Ops | medium | Align CLI root flag with existing generators: accept `--out` as an alias of `--project` (or standardize on `--out` everywhere) so `startd8 wireframe` matches `generate backend` / `generate scaffold` muscle memory. | Step 4 introduces `--project <root>` while `cli_generate.py` uses `--out` for the same concept — an avoidable UX papercut on every kickoff session. | §2 Step 4 — `cli_wireframe.py` | Typer test: `wireframe --out .` and `wireframe --project .` produce identical plans. |
| R1-S3 | Interfaces | medium | Persist a human-readable **markdown** summary alongside JSON in pipeline-output (`wireframe/wireframe-summary.md`), reusing the Rich tree renderer text path. | FR-W11 targets pipeline visibility; JSON alone is poor for the kickoff conversation the Problem Statement cites. Markdown is ~10 lines of reuse atop Step 3. | §2 Step 5 + Step 3 (`render.py`) | Pipeline shim run leaves both `wireframe-plan.json` and `wireframe-summary.md` under `$OUTPUT_DIR/wireframe/`. |
| R1-S4 | Validation | medium | Extend Step 6 golden cross-check (FR-W14) to assert **non-owned paths** the plan must not claim: e.g. `app/pages/*.md` prose (generated from `pages.yaml` but outside drift hash per `cli_generate.py` pages help). | FR-W14 as written checks generator artifact paths both ways; pages/content prose is a common silent divergence surface not emitted as owned files. | §2 Step 6 — Tests | Fixture with `--pages`: plan lists content pages but cross-check excludes `app/pages/*.md` from owned-artifact equality set. |
| R1-S5 | Data | low | Add a worked **`assembly-inputs.yaml` example** block to Step 1 (and Step 7 doc update) matching `ASSEMBLY_INPUTS_TEMPLATE.md` catalog keys — not only the inline `inputs: {schema: …}` mention. | FR-W6 is the first machine-readable inventory (OQ-3); authors currently only have a markdown table template with no copy-paste YAML shape. | §2 Step 1 + Step 7 | Doc test or snapshot: example YAML loads via `load_assembly_inputs()` and resolves paths relative to the YAML directory. |

**Endorsements:** none — first round.

**Disagreements:** none — first round.

---

## Requirements Coverage Matrix — R1

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-W1 — Wireframe plan model | Step 2 (`plan.py`) | Full | — |
| FR-W2 — Deterministic and $0 | Step 2; Step 6 (partial) | Partial | No byte-identical JSON determinism test named (see R1-F5) |
| FR-W3 — Reuse generator parsers | Step 2 | Full | — |
| FR-W4 — Definition status per section | Step 2 absence table | Partial | Kickoff Status → wireframe status mapping absent (see R1-F1) |
| FR-W5 — Consequence rendering | Step 3 (`render.py`) | Full | — |
| FR-W6 — Assembly-inputs YAML | Step 1 | Partial | No worked example in template/docs (see R1-S5) |
| FR-W7 — Direct flags fallback | Step 1, Step 4 | Partial | `generate views --views` not mirrored (see R1-F3); `--project` vs `--out` (see R1-S2) |
| FR-W8 — Convention defaults | Step 1 | Full | — |
| FR-W9 — Direct CLI | Step 3, Step 4 | Full | — |
| FR-W10 — JSON output | Step 3 (`to_json`) | Partial | No `schema_version` contract (see R1-F2) |
| FR-W11 — cap-dev-pipe shim | Step 5 | Partial | Stage ordering + input discovery unspecified (see R1-S1, R1-F4) |
| FR-W12 — Persisted artifact | Step 3 (`--no-write`) | Full | — |
| FR-W13 — Graceful degradation | Step 2 parser catch | Full | — |
| FR-W14 — Anti-divergence cross-check | Step 6 golden test | Partial | Non-owned content paths (e.g. pages prose) not scoped (see R1-S4) |

#### Review Round R2 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:20:00 UTC
- **Scope**: Gap-hunting — second-order effects, kickoff/content visibility, CLI parity gaps R1 missed.

**Executive summary:**
- FR-W6 **status override** is required in requirements but absent from Step 1 — implement or defer explicitly.
- **`--pages-authoring`** and AI prompt paths are invisible in the planned shape despite being kickoff-relevant surfaces.
- Services section behavior when schema is absent/invalid is internally inconsistent between plan Step 2 and FR-W4.
- End-user quick win: `--only-issues` filter to surface non-`planned` sections without reading the full tree.
- Docs gap: wireframe vs sapper vs FR-X1 pre-flight need a one-page boundary so users pick the right tool.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | medium | Implement FR-W6 **status override** in Step 1 (`assembly-inputs.yaml` per-key `status:` alongside `path:`) and document precedence: override labels the section for kickoff inventory sync; parser outcome still wins for `invalid` when file is present-but-unparseable. | FR-W6 requires "optionally an explicit status override"; Step 1 only merges paths. Without this, the first machine-readable inventory cannot express kickoff `authored`/`absent` before files exist on disk. | §2 Step 1 — `inputs.py` | YAML with `pages: {path: prisma/pages.yaml, status: absent}` yields Pages section `not_defined` even if a stale file exists; unparseable present file still surfaces `invalid`. |
| R2-S2 | Architecture | medium | Extend Step 2 plan sections with **Content inputs** (read-only): list `app/pages/*.md` slugs referenced from `pages.yaml` and prompt paths referenced from `ai_passes.yaml`, each tagged `placeholder`/`not_defined` per ASSEMBLY_INPUTS_TEMPLATE bucket rules — no generation claims. | Problem Statement cites kickoff review; Group F table includes content prose and prompt paths but FR-W1 enumerates only generators' owned outputs. Users cannot see "what content is wired vs missing" from the wireframe today. | §2 Step 2 — new **Content inputs** subsection in `plan.py` | Fixture with `pages.yaml` + missing `app/pages/foo.md`: wireframe lists slug `foo` as `not_defined` with consequence "no page body at generate time". |
| R2-S3 | Risks | medium | Reconcile Step 2 **Services** bullet ("FastAPI app + web mount (always, given schema)") with FR-W4 (`schema.prisma` absent ⇒ entity-derived sections `not_defined`): when schema is absent/invalid, Services MUST degrade to `not_defined` or `invalid` with an explicit consequence — not an unconditional FastAPI item. | Current plan text implies services always appear; FR-W4 table says no schema ⇒ no entities/CRUD/forms/views but is silent on Services, creating implementer ambiguity and false "planned" signal. | §2 Step 2 — Services bullet + absence table row | Parametrized test: no schema ⇒ Services section status `not_defined` (or `invalid` with parser error), not `planned`. |
| R2-S4 | Interfaces | low | Mirror `generate backend --pages-authoring` in Step 4 CLI flags; when set (requires `--pages`), add plan items for `app/pages_admin.py`, `app/pages_io.py`, and authoring templates — gated the same way as `cli_generate.py:137-225`. | Authoring UI is a real app-shape surface (~4 owned files) triggered by a backend flag; omitting it makes the wireframe under-report what `--pages-authoring` will add. | §2 Step 4 + Step 2 Pages/Services | CLI test: `--pages --pages-authoring` adds authoring artifacts to plan; flag without `--pages` errors like generate backend. |
| R2-S5 | Ops | low | Step 7 docs: add a **"When to use wireframe vs sapper vs kickoff FR-X1"** comparison table (inputs scope, output shape, gating, cost). | Three pre-run visibility tools now exist; Problem Statement positions wireframe at the DATA MODEL bookend but does not disambiguate sapper (Prime/EMIT) or FR-X1 (five-class kickoff). Reduces wrong-tool usage. | §2 Step 7 — Docs | Doc review: table covers scope boundary from Non-Requirements ("Not FR-X1", "No mechanism/friction") plus sapper's EMIT/skeleton focus. |

**Endorsements** (prior untriaged suggestions):
- R1-S1: Pipeline shim needs stage + discovery — still the top FR-W11 delivery risk.
- R1-S3: Markdown summary in pipeline-output is high value for kickoff reviewers at low implementation cost.
- R1-F1: Kickoff Status → wireframe status mapping unblocks FR-X5/wireframe convergence.

**Disagreements:** none.

---

## Requirements Coverage Matrix — R2

| Requirement Section | Plan Step(s) | Coverage | Gaps (new/changed since R1) |
| ---- | ---- | ---- | ---- |
| FR-W6 — Assembly-inputs YAML | Step 1 | Partial | Status override in FR-W6 not in Step 1 (R2-S1, R2-F1) |
| FR-W1 — Wireframe plan model | Step 2 | Partial | Content inputs + pages-authoring surfaces not enumerated (R2-S2, R2-S4, R2-F2) |
| FR-W4 — Definition status | Step 2 absence table | Partial | Services when schema absent unspecified (R2-S3) |
| FR-W9 — Direct CLI | Step 4 | Partial | No `--only-issues` filter; exit 2 scope narrow (R2-F3, R2-F4) |
| Non-Requirements boundaries | Step 7 (partial) | Partial | sapper boundary not documented (R2-S5, R2-F5) |

#### Review Round R3 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:35:00 UTC
- **Scope**: Late-phase gap-hunting — CLI parity细节, provenance, security, shape metrics, golden fixtures.

**Executive summary:**
- Scaffold CLI uses `--manifest` for `app.yaml`; plan Step 4 says `--app` — flag mismatch will break copy-paste from generate commands.
- Persisted JSON lacks **input provenance/fingerprint** — blocks OQ-8 diff and pipeline debugging.
- Path escape via `assembly-inputs.yaml` relative paths is unaddressed.
- Shape summary counts (entities/routes/views) are high-value, low-effort UX atop existing parsers.
- Completeness `defaults` should distinguish presence-rule fallback vs authored signal list.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Interfaces | medium | Step 4 CLI: accept **`--manifest`** as the primary flag for `app.yaml` (matching `generate scaffold --manifest`), with `--app` as alias if desired — not `--app` alone. | Step 4 lists "`--schema --app --pages`"; `cli_generate.py:323` uses `--manifest` for the same file. Users will copy scaffold invocations and get "unknown option" errors. | §2 Step 4 — `cli_wireframe.py` | Typer test: `wireframe --manifest app.yaml` resolves app manifest; matches scaffold flag name in help text. |
| R3-S2 | Data | medium | Add **`input_provenance`** to `WireframePlan` / `to_json()`: for each catalog key, record `{path, resolved_path, source: convention\|yaml\|flag, yaml_index?}`. | FR-W12 enables later diff (OQ-8) and pipeline debugging; without provenance a persisted plan cannot explain *why* a section was `defaults` vs `planned`. Reuses data already computed in Step 1 merge. | §2 Step 2 + Step 3 (`plan.py`, `to_json`) | JSON output includes provenance; changing only CLI flag override updates `source: flag` on next run. |
| R3-S3 | Validation | low | Step 6: pin the **FR-W14 golden fixture** to an explicit strtd8-shaped mini corpus under `tests/fixtures/wireframe/` (schema + full manifest set) and reference it in the plan — not an anonymous "full fixture". | Anti-divergence test is the OQ-2 gate; without a named canonical fixture, drift in test data won't match the RUN-028/strtd8 evidence the requirements cite. | §2 Step 6 — Tests | Fixture path documented; CI fails if fixture removed; cross-check covers backend+scaffold+views paths. |
| R3-S4 | Ops | low | Step 3 renderer: add a **shape summary** line after status counts — e.g. `Entities: N \| CRUD routes: R \| Pages: P \| Views: V \| AI passes: A` — derived from parsed plan items. | FR-W9 footer counts statuses; kickoff reviewers also need at-a-glance *magnitude* ("3 entities vs 30") without expanding the tree. ~15 lines atop existing parsed models. | §2 Step 3 — `render.py` | Snapshot test: fixture with 2 entities, 1 view ⇒ summary line matches expected integers. |
| R3-S5 | Ops | low | Emit OTel metrics from CLI/shim: `wireframe.duration_ms`, `wireframe.sections{status}` counters — mirror sapper/nemawashi observability pattern. | Pipeline opt-in hook (FR-W11) benefits from Grafana visibility ("did wireframe run?", "how many `invalid` sections?") at near-zero cost once Step 4 exists. | §2 Step 4 + Step 5 | Local stack run shows metrics; pipeline shim increments `wireframe.sections` with status labels. |

**Endorsements** (prior untriaged suggestions):
- R1-F2: `schema_version` on JSON is prerequisite before pipeline consumers depend on FR-W10.
- R2-F3: Exit 2 for bad assembly-inputs YAML prevents silent garbage plans.
- R2-S3: Services must not show `planned` when schema is absent — closes a false-confidence hole.

**Disagreements:** none.

---

## Requirements Coverage Matrix — R3

| Requirement Section | Plan Step(s) | Coverage | Gaps (new since R2) |
| ---- | ---- | ---- | ---- |
| FR-W7 — Direct flags fallback | Step 4 | Partial | `--manifest` scaffold parity missing (R3-S1, R3-F1) |
| FR-W10 / FR-W12 — JSON + persist | Step 3 | Partial | No input provenance/fingerprint (R3-S2, R3-F2) |
| FR-W1 — Completeness section | Step 2 | Partial | Presence-rule fallback vs authored signals not distinguished (R3-F5) |
| FR-W9 — Direct CLI | Step 3 | Partial | No shape-summary line (R3-S4, R3-F3) |
| FR-W6 — Assembly-inputs YAML | Step 1 | Partial | Path escape hardening absent (R3-F4) |
| FR-W14 — Cross-check | Step 6 | Partial | No named golden fixture path (R3-S3) |

#### Review Round R4 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 20:50:00 UTC
- **Scope**: Convergence-phase — UX polish, API surface, cascade guidance, artifact lifecycle.

**Executive summary:**
- `--json` should follow sapper: machine output to stdout, Rich tree optional — not specified today.
- **Cascade readiness** footer turns the wireframe into actionable "what to run next" guidance — highest end-user ROI left.
- Promoting `_form_fields` needs backward-compatible aliases to avoid breaking backend_codegen internals.
- Pipeline vs direct CLI **dual persist paths** need explicit rules to prevent confusing overwrites.
- Public `build_wireframe_plan` API enables kickoff/TUI reuse without shelling out.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Interfaces | medium | Step 4: when **`--json`**, emit JSON to **stdout** and skip Rich tree unless **`--verbose`** (sapper pattern, `cli_sapper.py:45-64`). | Plan lists `--json` but not interaction with Rich output; piping JSON while Rich prints breaks CI scripts. Sapper already solved this. | §2 Step 4 — `cli_wireframe.py` | Typer test: `--json` ⇒ stdout is valid JSON, no Rich tree bytes; `--json --verbose` ⇒ both. |
| R4-S2 | Ops | medium | Step 3 footer: add **cascade readiness** hints — `scaffold: ready \| blocked(reason)` / `backend: …` / `views: …` — derived from section statuses (e.g. views blocked when schema `invalid`). | Wireframe answers "what will be built"; kickoff users immediately ask "what do I run next?" Three one-line checks reuse existing status model — no new parsers. | §2 Step 3 — `render.py` | Fixture with `invalid` schema ⇒ backend/views show `blocked(invalid schema)`; all `planned` ⇒ all `ready`. |
| R4-S3 | Risks | low | When promoting `_form_fields`/`_writable_fields` to public names, **retain private aliases** in `htmx_generator.py` for existing importers; document in Step 2 Risks. | Plan Step 2 + Risks say "promote" but backend_codegen may have internal/test references to privates; breaking rename is avoidable for a 2-line promotion. | §2 Step 2 Forms bullet + §3 Risks | Grep-backed test or note: `_form_fields` alias delegates to public name; existing backend tests unchanged. |
| R4-S4 | Ops | medium | Step 5: define **artifact precedence** when both direct CLI and pipeline shim run in one session — pipeline writes `$OUTPUT_DIR/wireframe/`; direct CLI writes `.startd8/wireframe/`; JSON SHOULD cross-reference the other path if both exist (no silent clobber). | FR-W11 and FR-W12 name two output locations but not coexistence; a cap-dev-pipe run followed by local `startd8 wireframe` can confuse which plan is authoritative. | §2 Step 5 + Step 3 persist | Shim writes pipeline dir only; direct CLI writes `.startd8/`; JSON includes `emit_context: cli\|pipeline`. |
| R4-S5 | Ops | low | Step 7: register wireframe in **`docs/capability-index/`** (CLI command + read-only plan artifact) and add a **strtd8 pilot** one-liner (`make wireframe` or documented invoke) for first real use (OQ-8). | Capability index tracks SDK surface; wireframe is a new top-level command absent from discovery docs. Pilot doc hook accelerates OQ-8 feedback. | §2 Step 7 — Docs | Capability manifest lists `startd8 wireframe`; strtd8 docs reference the command. |

**Endorsements** (prior untriaged suggestions):
- R3-S2 + R3-F2: Input provenance + fingerprint together unlock OQ-8 and pipeline audit.
- R1-S3: Markdown summary remains the best kickoff-facing pipeline artifact.
- R2-F4: `--only-issues` filter pairs well with cascade readiness footer (R4-S2).

**Disagreements:** none.

---

## Requirements Coverage Matrix — R4

| Requirement Section | Plan Step(s) | Coverage | Gaps (new since R3) |
| ---- | ---- | ---- | ---- |
| FR-W9 — Direct CLI | Step 3–4 | Partial | No cascade readiness footer (R4-S2, R4-F2); `--json`/Rich interaction (R4-S1, R4-F1) |
| FR-W10 — JSON output | Step 4 | Partial | stdout vs file-only unspecified (R4-F1) |
| FR-W11 — Pipeline shim | Step 5 | Partial | Dual persist precedence undefined (R4-S4, R4-F3) |
| FR-W1 — Plan model | Step 2 | Partial | No programmatic API stability note (R4-F5) |
| FR-W7 — Flags | Step 4 | Partial | `--ai-agent-spec` not mirrored (R4-F4) |

#### Review Round R5 — composer-2.5 — 2026-06-05

- **Reviewer**: composer-2.5
- **Date**: 2026-06-05 21:15:00 UTC
- **Scope**: Second-order effects — determinism vs audit metadata, encoding, scale UX, shim failure visibility, plan↔req flag parity.

**Executive summary:**
- Audit metadata (`generated_at`, SDK version) must not break FR-W2 byte-identical JSON or R3 fingerprints.
- Manifest reads need explicit UTF-8 failure modes — silent mojibake breaks parser error clarity.
- Large schemas need truncated Rich/JSON lists or kickoff review becomes unreadable.
- FR-W11 "never blocks" must still leave a discoverable error artifact when the shim crashes.
- FR-W7 omits `--pages-authoring` though plan Step 4 and `generate backend` both expose it.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Data | medium | Step 3 `to_json()`: put **`generated_at`** and **`startd8_version`** in a top-level **`_meta`** object excluded from the FR-W2 canonical serialization used for byte-identical tests and `inputs_fingerprint` (R3-F2). | R3-F2 adds fingerprinting; R1-F5 demands byte-identical JSON — adding timestamps/version without an exclusion rule guarantees nightly CI flakes and false diff positives. | §2 Step 3 — `render.py` / `to_json()` | Two runs same inputs: canonical body identical; `_meta.generated_at` may differ; fingerprint unchanged. |
| R5-S2 | Validation | medium | Step 1 + Step 2: read all manifest files as **UTF-8** (`encoding="utf-8"`); on `UnicodeDecodeError`, assembly-inputs file ⇒ exit 2; individual manifest ⇒ section `invalid` with `"not valid UTF-8"` (FR-W13), no silent latin-1 fallback. | Step 1/2 call parsers on raw text but never state encoding; binary or legacy-encoded YAML on CI hosts yields misleading `invalid` parser errors or wrong placeholders. | §2 Step 1 + Step 2 parser read path | Fixture with ISO-8859-1 bytes ⇒ expected exit/status; valid UTF-8 fixture unchanged. |
| R5-S3 | Ops | low | Step 3 renderer + JSON: cap per-section item lists at **`--max-items`** (default **25**) with suffix `… and N more` when entity/form/view counts exceed the cap; footer counts remain full totals. | strtd8-scale schemas can enumerate 50+ entities; an uncapped tree defeats the "cheapest feedback" goal at the DATA MODEL bookend. ~20 lines; full detail still in JSON when uncapped or via `--max-items 0`. | §2 Step 3 — `render.py` + Step 4 CLI | Fixture with 30 models: tree shows 25 + "… and 5 more"; counts line still reports 30. |
| R5-S4 | Ops | medium | Step 5 shim: on uncaught exception, still **exit 0** (FR-W11) but write **`wireframe-error.json`** (`{error_type, message, traceback?}`) beside intended artifacts; log via `get_logger`. | "Never blocks" + `set +e` can hide a broken wireframe install; pipeline reviewers see no `$OUTPUT_DIR/wireframe/` output and cannot distinguish skip vs crash. FDE/triage shims write sidecar error JSON. | §2 Step 5 — `scripts/run_wireframe.py` | Mocked `build_wireframe_plan` raise ⇒ exit 0 + error JSON present; success path has no error file. |
| R5-S5 | Data | low | Step 1 merge: when a later `--inputs` YAML **overwrites** a catalog key, append to plan/JSON **`merge_warnings`** (and stderr when not `--json`) — `{key, previous_path, new_path, source_file}`. | FR-W6 "last wins" is silent; kickoff debugging of "why did wireframe pick this schema path?" is a common multi-file inventory failure mode. | §2 Step 1 — `inputs.py` | Two YAMLs overriding `schema` ⇒ one warning entry naming both files; single file ⇒ empty warnings. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S6 | Architecture | low | Step 2 **Services** bullet: change "(always, given schema)" to **"when schema is `planned` or `placeholder`; when schema is `not_defined`/`invalid`, Services section is `not_defined` or `invalid`-degraded — do not emit `planned` AI/web items."** Aligns with R2-S3. | Step 2 line 62 implies web mount is always planned whenever any schema file exists; an invalid Prisma file would contradict FR-W13 and R2-S3 false-confidence fix. | §2 Step 2 — Services bullet | Invalid schema fixture ⇒ Services ≠ `planned`; absent schema ⇒ `not_defined`. |

**Endorsements** (prior untriaged suggestions):
- R4-F2 + R4-S2: Cascade readiness footer is the highest remaining end-user value item.
- R2-S4 + R2-F2: Pages-authoring and content inputs complete the app-shape picture.
- R3-S3: Named golden fixture should land before FR-W14 is treated as done.

**Disagreements:** none.

---

## Requirements Coverage Matrix — R5

| Requirement Section | Plan Step(s) | Coverage | Gaps (new since R4) |
| ---- | ---- | ---- | ---- |
| FR-W2 — Deterministic | Step 3 | Partial | No `_meta` exclusion for audit fields (R5-S1, R5-F1) |
| FR-W6 — Assembly-inputs | Step 1 | Partial | Silent last-wins overwrites (R5-S5, R5-F5) |
| FR-W7 — Direct flags | Step 4 | Partial | `--pages-authoring` in plan R2-S4 but absent from FR-W7 (R5-F6) |
| FR-W9 — Direct CLI | Step 3–4 | Partial | No large-schema list cap (R5-S3); no `--fail-on-issues` (R5-F3) |
| FR-W11 — Pipeline shim | Step 5 | Partial | Crash leaves no artifact (R5-S4, R5-F4) |
| FR-W13 — Degradation | Step 2 | Partial | UTF-8 + error truncation unspecified (R5-S2, R5-F2) |
| FR-W1 — Services | Step 2 | Partial | "Always given schema" vs invalid schema (R5-S6) |

#### Review Round R6 — claude-opus-4-8[1m] — 2026-06-05

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-06-05 18:20:00 UTC
- **Scope**: Code-verified pass against actual parser/generator sources — parser-strictness premise, private-import consistency, FR-W14 conditional-surface coverage, multi-manifest status composition, persist atomicity.

**Executive summary:**
- The load-bearing premise "all parsers are strict/loud" is **false for the keystone manifest**: `parse_prisma_schema` is lenient by design (docstring: "unparseable lines are skipped rather than raising... Returns an empty schema for empty/blank input", `languages/prisma_parser.py:276-283`) — Step 2's exception-catch path can never mark `schema.prisma` `invalid`, and corruption masquerades as `placeholder` or a shrunken-but-`planned` entity list. R1–R5 all built on the strict-parser assumption.
- Step 2 imports private `_load_completeness_manifest` (`derived.py:250`) while the plan's own §3 Risks bullet bans cross-module private imports — only the two htmx helpers are slated for promotion.
- FR-W14's "full fixture" silently covers only the unconditional artifact subset unless it enables every conditional `render_backend()` kwarg (AI layer gated on `manifest_text`, authoring on `authoring=True`, weighted completeness on `completeness_text` — `assembler.py:32-43`); plus a kwarg naming trap: `render_backend(manifest_text=…)` is **ai_passes.yaml**, not `app.yaml`.
- Three sections derive from ≥2 manifests (Forms, Services, Views) but no status composition rule exists when contributors disagree.
- Persisted JSON needs atomic write or interrupted runs poison OQ-8 diff and pipeline consumers.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | Risks | high | Step 2 sentence "Parser exceptions (all parsers are strict/loud) are caught per-manifest" is wrong for `schema.prisma`: `parse_prisma_schema` never raises — it skips unparseable lines and returns an empty schema for blank input (`prisma_parser.py:276-283`). Add an explicit **schema recoverability check**: compare raw-text `model `/`enum ` block count against parsed model/enum count; on mismatch (or zero parsed models with non-empty, non-`model`-bearing text) mark the schema item `invalid` with a "lenient parse dropped N blocks" message. | Without this, a corrupted contract silently yields a partial `planned` entity list or a false `placeholder` — defeating FR-W13's purpose at the single most important input; the views `known_entities` degradation also never fires on an invalid (vs absent) schema. | §2 Step 2 — parser-exception paragraph + Entities & CRUD bullet | Fixture with a garbled model block (unbalanced braces): wireframe marks schema `invalid` listing dropped-block count; valid schema fixture unchanged. |
| R6-S2 | Architecture | medium | Promote (or publicly wrap) `_load_completeness_manifest` (`derived.py:250`) alongside `_form_fields`/`_writable_fields` — Step 2's Completeness bullet imports it cross-module as a private. | §3 Risks states "promote … to public rather than importing privates cross-module" but only names the two htmx helpers; the completeness-loader import violates the plan's own stated rule and is equally a ~2-line promotion. | §2 Step 2 Completeness bullet + §3 Risks second bullet | Grep: no `_load_completeness_manifest` import outside `backend_codegen/`; public name re-exported and used by `wireframe/plan.py`. |
| R6-S3 | Validation | medium | Step 6 FR-W14 cross-check: require the golden fixture to **enable every conditional generator surface** — `ai_passes.yaml` (+ `human_inputs.yaml`) so the AI layer (service wrapper, edge schemas, harnesses, AI router, `app/server.py`) is emitted, `authoring=True` for authoring artifacts, and `completeness_text` for weighted completeness (`assembler.py:32-52` gates all of these on optional kwargs). Also note the kwarg naming trap in the test: `render_backend`'s `manifest_text` means **ai_passes.yaml** while scaffold's `--manifest` means `app.yaml`. | A "full fixture" that omits any optional kwarg silently shrinks the cross-checked path set to the unconditional subset — the anti-divergence gate would pass while AI-layer/authoring paths drift. Complements R3-S3 (named fixture), which fixes *where* the fixture lives, not *what it must cover*. | §2 Step 6 — golden cross-check bullet | Cross-check asserts presence of `app/server.py` + AI router + authoring paths in both plan and `render_backend()` output; removing `ai_passes.yaml` from the fixture fails the test. |
| R6-S4 | Data | medium | Step 2: add a **status composition rule** for sections fed by multiple manifests — Forms (schema + human_inputs), Services (schema + ai_passes), Composite views (schema + views). Propose worst-wins precedence `invalid > placeholder > not_defined > defaults > planned`, with the consequence line taken from the worst contributor. | The absence table maps one manifest → one status, and statuses are "per-item and per-section", but nothing defines Forms when schema is `planned` and `human_inputs.yaml` is `invalid`. R2-S3/R5-S6 fixed only the Services×schema cell; this rule generalizes the remaining combinations implementers will otherwise decide ad hoc. | §2 Step 2 — after the absence-semantics table | Parametrized matrix test: each (schema status × secondary-manifest status) pair resolves to the documented section status. |
| R6-S5 | Ops | low | Step 3 persist: write `wireframe-plan.json` atomically (`tempfile` in target dir + `os.replace`) and `mkdir -p` `.startd8/wireframe/`; on unwritable target, warn and continue (exit 0). | A Ctrl-C or crash mid-write leaves truncated JSON that later OQ-8 diff and pipeline consumers parse-fail on; an advisory tool must not crash on a read-only project root. | §2 Step 3 — persist bullet | Kill-during-write simulation leaves either old or new complete file, never partial; read-only dir ⇒ rendered output + warning, exit 0. |

**Endorsements** (prior untriaged suggestions):
- R5-S6 + R2-S3: Services degradation is correct — and interacts with R6-S1: it only works once invalid schemas are *detectable* under the lenient parser.
- R3-F4: Path confinement on assembly-inputs is required before any CI/pipeline host runs the loader.
- R1-S1: Shim input discovery remains the top FR-W11 delivery risk; nothing in R2–R5 resolved it.

**Disagreements** (untriaged prior items, for triage weighing):
- R3-S5 (OTel metrics from CLI/shim): defer to post-pilot — a $0 local advisory command gains little from metric emission, and OTel init/wiring on every `startd8 wireframe` invocation is real surface to add before first user feedback (OQ-8 pilot).

---

## Requirements Coverage Matrix — R6

| Requirement Section | Plan Step(s) | Coverage | Gaps (new since R5) |
| ---- | ---- | ---- | ---- |
| FR-W4 / FR-W13 — statuses + degradation | Step 2 | Partial | `invalid` undetectable for `schema.prisma` (lenient parser — R6-S1, R6-F1); multi-manifest section composition rule missing (R6-S4, R6-F3) |
| FR-W3 — Reuse generator parsers | Step 2 | Partial | Private `_load_completeness_manifest` import contradicts §3 Risks promotion rule (R6-S2) |
| FR-W8 — Convention defaults | Step 1 | Partial | `prisma/*.yaml` is a glob, not a per-key filename mapping (R6-F2) |
| FR-W14 — Anti-divergence cross-check | Step 6 | Partial | Conditional generator surfaces (AI layer, authoring, weighted completeness) not required in fixture (R6-S3) |
| FR-W12 — Persisted artifact | Step 3 | Partial | No atomicity / unwritable-target semantics (R6-S5, R6-F4) |
