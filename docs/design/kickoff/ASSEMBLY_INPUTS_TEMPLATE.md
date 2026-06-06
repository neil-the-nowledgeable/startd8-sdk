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
```

With no `--inputs` at all, `startd8 wireframe` falls back to exactly the conventional paths
above. See `docs/design/wireframe/WIREFRAME_REQUIREMENTS.md` (FR-W6–W8).

---

*Instantiated from `startd8-sdk/docs/design/kickoff/ASSEMBLY_INPUTS_TEMPLATE.md` (v0.1). The
Status column uses the kickoff provisioning states; see `KICKOFF_REQUIREMENTS.md` for the
collection machinery (POLISH flag → RESOLVE collect → VALIDATE gate) and the domain slices for
per-class detail.*
