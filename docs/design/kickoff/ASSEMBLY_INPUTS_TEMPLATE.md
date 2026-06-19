# <Project> — Kickoff Input Inventory (Assembly Inputs)

> **TEMPLATE** — project-agnostic, startd8-SDK-specific. Instantiate per project (FR-X5 of
> [`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md)); reference instance:
> `strtd8/docs/v2/ASSEMBLY_INPUTS.md`. Copy into the project (suggested home:
> `docs/ASSEMBLY_INPUTS.md`), replace `<…>` placeholders, delete rows that don't apply, add
> project-specific rows. Keep the **Status** column current — it feeds the kickoff pre-flight
> report (FR-X1): `authored` | `placeholder` | `absent`.

**Date:** <YYYY-MM-DD>. The hand-authored inputs the `$0` deterministic generators
(`startd8 generate scaffold` / `generate backend` / `generate views`) consume to assemble the
app, plus the related pipeline-orchestration and content inputs. This is the "what feeds the
cascade" reference for <project>.

## Contract / assembly manifests

| File | Drives | Role | Phase | Status |
|---|---|---|---|---|
| `prisma/schema.prisma` * | `generate backend` / `generate views` | **the contract** — keystone data model (<N> entities), single source of truth | <1> | <authored> |
| `app.yaml` (root) | `generate scaffold` | project scaffold — name, db path, WAL, migrations, logging, container, env | <1> | <authored> |
| `prisma/human_inputs.yaml` | `generate backend` | owned-field policy (fields the AI edge omits; e.g. `<Entity.field>`) | <1> | <authored> |
| `prisma/ai_passes.yaml` | `generate backend` (AI layer) | the AI passes — <list pass names> | <3> | <authored> |
| `prisma/pages.yaml` | `generate backend` | content pages + nav | <2> | <authored> |
| `prisma/completeness.yaml` | `generate backend` | completeness signal set + score formula (absent ⇒ presence rule) | <2> | <absent> |
| `prisma/views.yaml` | `generate views` | composite views — <list views/archetypes> | <2> | <absent> |
| `prisma/view_prose.yaml` | `generate views --view-prose` | **view copy (words layer)** — per-view title/intro/empty/success/error/controls; **hash-exempt**, rendered to untracked fragments (outside the drift hash — editing copy never flags drift, per [`SOTTO`](../../design-princples/SOTTO_DESIGN_PRINCIPLE.md)) | <2> | <absent> |
| `prisma/imports.yaml` | `generate backend` | bulk-import owned-kind (`app/importer.py`) + optional paste/upload surface (FR-IMP-3; absent ⇒ no import artifacts) | <2> | <absent> |
| `prisma/api.yaml` | `generate backend --api` | OpenAPI 3.0 **surface overlay** merged into `app/openapi_contract.py` (Role 2; absent ⇒ schema-only contract, SOTTO) | <2> | <absent> |
| `prisma/contexts.yaml` | `generate backend --contexts` | **inter-context outbound producers** — emits `clients/{id}_client.py`, OTel helper, cross-context smoke tests (Role 3; absent ⇒ no context clients, SOTTO) | <2> | <absent> |

`*` = the contract itself (Prisma IDL, not YAML) — the front human design bookend
(`DATA_MODEL_AND_RETROSPECTIVE`): design it before the first cascade run; feed RETROSPECTIVE
findings back into it each increment.

## Content inputs (buckets 2/4)

| File | Role | Status |
|---|---|---|
| `app/pages/*.md` | content prose (untracked; `.md` edits never flag drift) | <placeholder> |
| `<prompts/*.md>` | AI-pass prompt prose (referenced by path from `ai_passes.yaml`) | <placeholder> |

> Bucket rule: `placeholder` is the **intended starting state** here — never gated, honestly
> scored. Real content (bucket 4) is provided by the user/company, never authored by the SDK.

## Related-process inputs (cap-dev-pipe orchestration — not contract assembly)

| File | Role | Status |
|---|---|---|
| `.cap-dev-pipe/pipeline.env` | pipeline env (provider, SDK root, project root, profile, instrumentation) — not YAML | <authored> |
| `.cap-dev-pipe/design/question-answers.yaml` | pre-seeded RESOLVE answers (the unattended channel) | <authored> |
| `.cap-dev-pipe/explain-content.yaml` | explain-mode display copy (presentation-only — no build impact) | <absent> |
| Provider credential presence (`<PROVIDER>_API_KEY` for selected providers) | env vars — presence-only, never the value (FR-I6) | <authored> |
| `<semantic_conventions.yaml>` | per-run convention declaration — framework, ORM, module paths, naming (Group H; home pending) | <absent> |

## Non-YAML inputs

| File | Role | Status |
|---|---|---|
| `prisma/schema.prisma` | the contract (Prisma IDL) | <authored> |
| `seeds/<name>.seed.json` | seed/fixture for the `<pass>` pass / view-test seeding (optional — absence never flagged) | <absent> |

## Path convention

Contract-derived manifests live under `prisma/` (siblings of `pages.yaml`); the project scaffold
manifest `app.yaml` lives at the repo root. <Adjust + note any project deviations here; phase-plan
command lines and runbooks should reference these exact paths.>

## Machine-readable instantiation (wireframe)

`startd8 wireframe` consumes this inventory as YAML (`--inputs`, repeatable, last-wins merge) and
renders the planned-vs-not-yet-defined assembly summary. Worked example (paths relative to the
YAML file's directory; a per-key `status:` override applies only while the file is absent):

```yaml
# docs/ASSEMBLY_INPUTS.yaml — machine-readable companion to this inventory
inputs:
  schema: {path: prisma/schema.prisma}
  app: {path: app.yaml}
  human_inputs: {path: prisma/human_inputs.yaml}
  ai_passes: {path: prisma/ai_passes.yaml}
  pages: {path: prisma/pages.yaml}
  completeness: {path: prisma/completeness.yaml, status: absent}   # declared ahead of authoring
  views: {path: prisma/views.yaml, status: absent}
  view_prose: {path: prisma/view_prose.yaml, status: absent}       # words layer — hash-exempt, optional
  imports: {path: prisma/imports.yaml, status: absent}               # FR-IMP-3 bulk-import — optional
  api: {path: prisma/api.yaml, status: absent}                       # Role 2 OpenAPI overlay — optional
  contexts: {path: prisma/contexts.yaml, status: absent}             # Role 3 outbound producers — optional
```

With no `--inputs` at all, `startd8 wireframe` falls back to exactly the conventional paths
above (eleven catalog keys: schema, app, human_inputs, ai_passes, pages, completeness, views,
view_prose, imports, api, contexts). See `docs/design/wireframe/WIREFRAME_REQUIREMENTS.md` (FR-W6–W8).

### Role 3 — `contexts.yaml` (optional)

Declares **outbound producer contexts** the app consumes across a process boundary. When present,
`startd8 generate backend --contexts prisma/contexts.yaml` emits:

- `clients/{producer_id}_client.py` — typed httpx consumer per outbound entry
- `clients/_context_otel.py` — OTel CLIENT span wrapper (OQ-5)
- `tests/test_cross_context_smoke.py` — loopback (local) + remote smoke templates (FR-6)

**Remote producer smoke:** set `base_url` in the manifest or override at runtime with
`STARTD8_CONTEXT_<PRODUCER_ID>_BASE_URL` (e.g. `STARTD8_CONTEXT_CATALOG_BASE_URL`).
The deploy harness runs live list+create smoke on the `context_smoke` ladder stage when
`prisma/contexts.yaml` is present.

---

*Instantiated from `startd8-sdk/docs/design/kickoff/ASSEMBLY_INPUTS_TEMPLATE.md` (v0.2). The
Status column uses the kickoff provisioning states; see `KICKOFF_REQUIREMENTS.md` for the
collection machinery (POLISH flag → RESOLVE collect → VALIDATE gate) and the domain slices for
per-class detail.*
