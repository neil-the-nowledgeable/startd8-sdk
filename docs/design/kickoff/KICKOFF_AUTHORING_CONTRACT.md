# Kickoff Authoring Contract — the Happy-Path Language

**Version:** 0.4 (v0.3 + the §2.3 `Panel:` line production — detail-compose root-field panels; see Appendix A / VSP-G1)
**Date:** 2026-06-05
**Status:** Draft
**Audience:** Internal + the LLM/human co-work sessions that produce customer kickoff docs.
**Parent:** [`KICKOFF_INPUT_PACKAGE_GUIDE.md`](KICKOFF_INPUT_PACKAGE_GUIDE.md) ·
[`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md)
**Consumer:** the deterministic manifest-extraction phase of plan ingestion (spec:
[`../wireframe/WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md`](../wireframe/WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md))
**Implementation:** P0/P1 of the wiring plan (the grammars' executable form) + the contract-side
tracker [`KICKOFF_AUTHORING_CONTRACT_NEXT_STEPS.md`](KICKOFF_AUTHORING_CONTRACT_NEXT_STEPS.md)

---

## 1. The rule this document encodes

> **The format carries the truth; LLMs only carry you to the format.**

Past failure mode (the reason this exists): LLM generation was used for values a formatted list
already determined — e.g. generating *routes* when routes are a deterministic function of a
pages list. The SDK's value proposition is the opposite split: **LLMs reduce the friction of
translating business needs into well-formatted requirements; deterministic extraction turns
those formats into the application's framework inputs.** LLM + human co-work is spent once per
concept — reaching the format — never on values the format carries.

A kickoff doc that follows this contract is **fully extractable**: every assembly-manifest value
derives from it deterministically, the wireframe renders from those manifests, and the business
user walks the lo-fi prototype before any generation runs.

## 2. The authoring formats (one per manifest)

Each format below is deliberately writable in plain language by a customer with co-work help.
Anything *outside* these formats is still allowed prose — it simply isn't extracted.

### 2.0 Name-derivation rules (shared by §2.1–2.3) *(CRP R1)*

- **Annotation stripping:** a heading's name is its text minus a trailing ` *(…)*` group —
  `### TargetRole *(added 2026-06-05 — …)*` ⇒ entity `TargetRole`. View headings strip the
  `View: ` prefix **first**, then the annotation: `### View: Job Workspace *(P2 preview)*` ⇒
  view name `Job Workspace` (and the derived route excludes the annotation).
- **Kebab derivation:** NFKD-fold to ASCII before kebab-casing (`Résumé` → `resume`).
- **Collisions:** two pages/views deriving the same slug or file-stem ⇒ **both** flagged
  `not_extracted(collision)` — extraction pre-flights what `parse_pages` would loud-fail on;
  an emission that dies in its own round-trip is a bug.
- **Reserved names:** entity/field names colliding with the generators' reserved set (the
  `metadata` class, Python keywords) ⇒ flagged at extraction, citing the backend
  reserved-name guard.
- **Pluralization:** entity references may be plural ("at least 3 ProofPoints", "links to many
  Capabilities") — singularize by matching against declared entity headings after stripping a
  trailing `s`/`ies`; no match ⇒ `not_extracted`.

### 2.1 Entities → `schema.prisma` (draft, Architect-validated)

One `### <EntityName>` heading per entity, with a field table and controlled relationship
sentences:

```markdown
### ProofPoint
A concrete piece of evidence the user provides about their work.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| title | text | yes | |
| story | long text | no | the STAR narrative |
| value | number | no | ONLY HUMANS ENTER THIS |

Relationships: a ProofPoint **belongs to** a Profile; a ProofPoint **links** Capability
**to** Outcome.
```

- **The plain-type → Prisma mapping table (normative — CRP R1):**

  | Plain type | Prisma scalar |
  |---|---|
  | text | String |
  | long text | String |
  | number | **Int** (whole numbers — decided; use `decimal` for anything else) |
  | decimal | Float |
  | money | **Int** (minor units / cents — exact sums; name the field `<thing>Cents`; the cents-vs-float choice is a `data_model.money` convention — KICKOFF_REQUIREMENTS FR-F6) |
  | date | DateTime |
  | date+time | DateTime *(adopted from the templates — was a vocabulary fork)* |
  | yes/no | Boolean |
  | choice of: a\|b\|c | enum (type name = `<Entity><Field>` PascalCase; values UPPER_SNAKE of the choices) |

  **One field per row** — a slash-row (`promptTokens / responseTokens`) is flagged
  `not_extracted(one-field-per-row)`, never split-parsed. Required column vocabulary:
  `yes` / `no` / blank (= no).
- **Relationship grammar (closed set, completed — CRP R1, pilot-blocking):**
  - **has one / has many / belongs to** — FK ownership as named.
  - **links to many** *(adopted — the templates teach it and the reference instance uses it)*:
    M2M join model between subject and object.
  - **links X to Y** (3-entity form): produces join(X, Y) — the *subject* contributes **no**
    FK; join-model name = `XY` in sentence order; compound `@@id` field order follows.
  - **Symmetric restatements dedup**: "A links to many B" + "B links to many A" ⇒ **one** join
    model, named by first-declaration order. (The worked instance's 6 symmetric sentences ⇒
    exactly 3 join models — the §4-acceptance set.)
  - "links X to **nothing** (plain link)" is **non-conforming** ⇒ `not_extracted` — write the
    pairwise sentences instead.
- **DRAFT-mode emitter grammar (FR-PE-5 — the `schema.prisma` *writer*).** These three constructs
  let the doc express everything the live contract uses; they are emitted by the Prisma emitter
  (`prisma_emitter.render_prisma_schema`) and verified by the semantic-parity diff (`semantic_diff`):
  - **Field defaults (FR-PE-5a, OQ-PE-1):** a `default: <value>` clause in the **Notes** cell →
    `@default(<value>)`. A defaulted scalar is emitted **non-optional** (the default supplies the
    value), regardless of the Required column. `| matchScore | number | no | default: 0 |` →
    `matchScore Int @default(0)`.
  - **Loose references (FR-PE-5c, OQ-PE-3) — the verb `references`:** the antonym of `belongs to`.
    `a TailoredMatch **references** a JobDescription` → a `jobDescriptionId` scalar with **no**
    `@relation` and **no** reverse list (the labeled-but-unlinked / polymorphic id the live contract
    uses). Use `belongs to` for an owned FK; use `references` for a loose id. *This is also the
    marker the source-bound AI-pass derivation keys on (OQ-SBE-2).*
  - **Indexes & compound uniqueness (FR-PE-5b, OQ-PE-2):** per-entity **`Indexes:`** and **`Unique:`**
    lines (after the `Relationships:` paragraph, blank-line separated). Semicolon-separated specs,
    each a comma-separated column list: `Indexes: jobDescriptionId; jobDescriptionId, kind` → two
    `@@index`; `Unique: jobDescriptionId, subjectType, subjectId` → one compound `@@unique`.
- Extraction emits a *draft* contract; the Architect validates (the bookend, preserved —
  drafting ≠ the forbidden mid-run mutation). The draft is gated (round-trip + whole-schema parity,
  FR-PE-6) and reaches the project tree only by an explicit human-triggered **promotion** (FR-PE-7).

### 2.2 Pages → `pages.yaml`

A single **Pages table**. Routes are never authored and never LLM-generated — they are derived:

```markdown
| Page | Purpose | Content file |
|------|---------|--------------|
| Home | Landing + orientation | home.md |
| How it works | The method, explained | how_it_works.md |
```

- `slug`/route = kebab-case of the page name (`How it works` → `/how-it-works`); Home → `/`.
- `nav_label` = page name; nav order = table order. An optional **Nav table** (Label | Target)
  overrides when nav ≠ pages.
- **Nav targets are opaque route strings (CRP R2):** emitted verbatim, never validated against
  the page/view route set — CRUD routes like `/ui/proofpoint` exist at runtime but in no
  manifest; an extractor that validates would falsely flag most of a real nav. The wireframe
  renders unknown-route nav entries with an advisory "route not in manifest" status, never
  `absent`.

### 2.3 Views → `views.yaml`

One block per composite view, constrained keys, archetype from the **published vocabulary**
(`dashboard, board, workspace, detail-compose, export-package`):

```markdown
### View: Value Map
- Kind: detail-compose
- Root: Capability
- Shows: Capability→Outcome, Capability→ProofPoint (only user-linked rows)
- Empty state: "not yet linked"
- Route: /value-map        # OPTIONAL — overrides the derived route
```

The co-work session's job here is archetype *selection* (which of the five fits). *(The v0.1
claim "every other line maps 1:1" was false — CRP R1; the actual mappings:)*

**Per-kind keys (CRP R1/R2):** every block requires `Kind` + `Root` (name from the heading;
route derived below). `board` additionally **requires `Group by:`** (a Root-entity field — the
column discriminator; optional `Order:` = allowed column values). `export-package` requires
`Of:` (the workspace it bundles) + `Formats:`. A block ends at the next heading or the first
non-`- Key:` line.

**Line micro-grammars:**
- `Shows: A→B, A→C (annotation)` → `relations` entries (`name` = the join-model name; `from` =
  the left entity; `fk` = the join model's FK column). Parenthetical annotations are tolerated
  display prose. **Sequencing dependency (CRP R2): the Views extractor runs AFTER the
  entity/relationship pass** — `fk` values derive from the §2.1-derived join models; without
  that pass ⇒ `not_extracted(fk-unavailable)`, never a guessed `<entity>Id` (a wrong guess
  passes the YAML round-trip and fails only at generate time).
- `Also shows:` → additional `relations`/`aggregates`; counts ("counts of X per Y") →
  `aggregates{name, of, fk}`.
- `Panel: <Name> = <field>, <field>, …` *(VSP-G1 — detail-compose only)* → a `panels` entry
  `{name, fields, show_when: any_set}`: a named group of **Root-entity fields**, rendered only when
  ≥1 field is non-empty. **Repeatable** (a view may declare several). Each field token resolves
  case-tolerant against the Root entity's §2.1 fields (a trailing parenthetical is tolerated display
  prose); an unknown field ⇒ `not_extracted` (named, dropped — **never a guessed field**, since the
  views round-trip gate doesn't field-check). A panel with no resolvable field is dropped whole. On
  any non-detail-compose kind ⇒ `not_extracted(off-archetype)`. A free-prose `Shows:` that is neither
  the arrow, counts, nor this Panel form stays `not_extracted(prose)` — flag-don't-guess preserved.
- `Empty state:` → **`not_extracted(generator-gap)`** — `parse_views` has no home for it
  (recorded per entry, never silently dropped).
- `Gap callout:` → `gap`.

**View routes (kind-aware derivation — answers the strtd8 §2 derivation question, 2026-06-05):**
routes derive by default, parameterized by kind: `detail-compose`/`dashboard`/`board` →
`/<kebab(view name)>`; `workspace` → `/<kebab(root)>/{id}`; `export-package` →
`<of-view-route>/export.{fmt}`. An explicit `- Route:` line **overrides** the derivation —
permitted for views (unlike pages, which stay pure-derived) because workspace/export routes are
parameterized and nav targets may predate the view name. The override is authored format data,
never an LLM product.

### 2.3b Form Help → `form_prose.yaml` *(the form WORDS layer — FR-FH-8)*

One block per entity form you want to guide. The **Words layer** for forms (per-field help/placeholder
+ a per-form intro), rendered into the generated create/edit forms and kept **outside the drift hash**
(help/intro ride untracked fragments, SOTTO) — editing copy never trips `generate backend --check`.
Absent ⇒ today's bare forms (opt-in).

```markdown
### Form: Bill
- Intro: Amounts are entered in dollars.

| Field       | Help                                           | Placeholder |
|-------------|------------------------------------------------|-------------|
| amountCents | Amount in dollars, e.g. 42.00; stored as cents | 42.00       |
| weekday     | For a weekly cadence: 0 = Monday … 6 = Sunday  |             |
```

**Grammar.** Heading `### Form: <Entity>` (annotation-stripped, name-derivation §2.0). An optional
`- Intro:` bullet (a key-line, like §2.3's `- Title:`). A `Field | Help | Placeholder` table — one row
per field; `Help` is the persistent description (wired as `aria-describedby`), `Placeholder` the
in-field example hint (either may be blank; a field with neither is omitted).

**Sequencing + dangling-target guard (mirrors §2.3).** The Form-Help extractor runs AFTER the
entity/relationship pass: the `### Form: <Entity>` heading resolves against the §2.1-derived entities
and each `Field` cell against that entity's fields (case-tolerant → the canonical field name). An
unknown entity or field is recorded **`not_extracted`** (sourced, advisory) and dropped — never guessed.
The emitted `prisma/form_prose.yaml` round-trips through `parse_form_prose` at ingestion. (Help is
bucket-4 human content; no AI pass originates a value — FR-FH-6.)

### 2.4 Completeness → `completeness.yaml`

A **"What counts as complete"** list in controlled sentences:

```markdown
A profile is complete when it has:
- at least 3 ProofPoints (weight 2)
- at least 2 Capabilities
- at least 1 ValueProp
(Don't count: join tables, AiCall)
```

`at least <N> <Entity>` → `min_rows`; optional `(weight N)`; the don't-count line → `exclude`.

**Block recognition + mappings (CRP R1/R2):**
- **Intro anchor:** any sentence containing `is complete when it has` (case-insensitive) opens
  the block — trailing parentheticals/colons on that line are tolerated.
- **Exclude category words:** "connection records" / "join tables" map to the §2.1-derived join
  models (so this extractor also runs **after** the relationship pass); anything else must be a
  declared entity name.
- **Nudge suffix** (`— nudge: "…"`, taught by the templates): tolerated, terminated at the
  ` — ` dash, and reported **`not_extracted(generator-gap)` per entry** — the SDK manifest
  cannot represent nudges yet; silently dropping an authored nudge would violate traceability.
  (Each suffixed entry yields TWO report rows: `extracted` for min_rows, `not_extracted` for
  the nudge.)

### 2.5 AI assists → `ai_passes.yaml`

An **AI-assists table** — what the AI does in the app (the passes), not how:

```markdown
| Assist | Reads | Writes | Purpose |
|--------|-------|--------|---------|
| extract | uploaded resume | ProofPoint, Capability | first-pass capture |
| quantify_metrics | ProofPoint | Metric (except value) | suggest measurable framings |
```

Prompt path derives from name (`prompts/<name>.md`); prompt *content* is bucket-3 content,
authored later under the content rules.

### 2.6 Owned fields → `human_inputs.yaml`

One list, one controlled phrase:

```markdown
Only humans enter: Metric.value, Profile.email
```

(Reinforced inline by the `ONLY HUMANS ENTER THIS` field-note in §2.1 tables — both extract to
the same policy.)

### 2.7 Scaffold & runtime → `app.yaml`

*(Grammar contributed by the strtd8 team, REQUIREMENTS 0.5.2 — they found scaffold values had
no home in the format and invented the right one.)* A **Scaffold & runtime table**
(Setting | Value | Plain meaning), settings vocabulary: `package name, display name,
python version, port, database, sqlite mode, migrations, logging, container, env keys`:

```markdown
## Scaffold & runtime
| Setting | Value | Plain meaning |
|---------|-------|---------------|
| package name | startd8 | the Python package/module name |
| port | 8099 | dev and prod |
| env keys | ANTHROPIC_API_KEY (optional) · COST_BUDGET_USD (default 10.00) | `.env.example` is emitted by the scaffold |
```

The section is **optional** — absent, the non-production defaults apply (kickoff value files +
industry dataset, per the PoC posture). When present it is the derivation source for `app.yaml`;
env-key defaults MUST agree with `inputs/build-preferences.yaml` (one value, two surfaces —
extraction flags disagreement).

**Setting → `AppManifest` mapping + per-cell micro-grammars (CRP R1 — without these, the strtd8
`database`/`env` drift class just recurs inside the cells):**

| Setting | Maps to | Cell grammar |
|---|---|---|
| package name | `app.package` | identifier |
| display name | `app.name` | text |
| python version | `app.python_version` | version string |
| database | `persistence.path` | path extracted from a `sqlite:///<path>` URL; parentheticals ignored |
| logging | `logging.file` | first comma-segment = file path; rest is prose |
| migrations | `migrations.enabled` | leading tool/yes ⇒ true |
| container | `container.dockerfile` | leading `yes`/`no` |
| port | `app.port` *(D8)* | leading integer (`8099`, `8099 (dev and prod)`); non-numeric ⇒ flag |
| env keys | `app.env_keys` *(D8)* | `·`-separated, each `KEY (qualifier…)` → `[{name, qualifier?}, …]`; baked into `.env.example` (deduped against templated vars) and available for the build-preferences agreement check |
| sqlite mode | **`not_extracted(generator-gap)`** — app-code concern (WAL/journal-mode touches `db.py`), not scaffold plumbing; backend-codegen backlog, out of scaffold v1 scope | |

### 2.9 Technology conventions → `conventions.yaml` *(value input — FR-VIP)*

The highest-leverage value input: the stack/layout/naming generated and bespoke code must FOLLOW,
so generation never INVENTS it (the run-028 Flask-where-FastAPI class). A `## Technology conventions`
section, with subsections. Emits `domain: conventions`; the round-trip authority is
`kickoff_inputs.parse_conventions` (a `ConventionsManifest`).

```markdown
## Technology conventions

- Language: python
- Field authorship: prisma/human_inputs.yaml
- Provenance default: templated

| Layer | Choice | Plain meaning |
|-------|--------|---------------|
| framework | fastapi | … |
| data layer | sqlmodel | … |

### Module layout
| Role | Path |
|------|------|
| tables | app.tables |
| templates dir | app/templates |

### Naming
| Aspect | Style |
|--------|-------|
| routes | kebab-case |
| metric prefix | household_ |

### Data-model conventions
- Money: cents
- Datetime: utc
- Recurrence: structured
- References: loose-allowed
- Weekday: iso

#### Computed fields
- <free text, one bullet each>

#### Deferred
- <free text, one bullet each>

### Architecture invariants
- <the load-bearing rules, one bullet each — carried verbatim>
```

**Mapping (normative).** Leading key-lines → `language` (**required**), `field_authorship`,
`provenance_default`. The `| Layer | Choice |` table → `stack:` (Layer→key, spaces→`_`:
`data layer`→`data_layer`; open vocabulary, D-VIP-3). `### Module layout` `| Role | Path |` →
`module_paths:` (`templates dir`→`templates_dir`). `### Naming` `| Aspect | Style |` → `naming:`
(aspect synonyms: `routes`→`route_style`, `files`→`files`, `classes`→`classes`, `metric prefix`→
`metric_prefix`). `### Architecture invariants` bullets → `architecture_notes: [str, …]` (verbatim).

**Data-model conventions (FR-F6 / DMC-G1)** — the §2.9 `### Data-model conventions` subsection. Key
lines map to `data_model:` with controlled enums; the two `####` lists are free text:

| Prose | → `data_model` key | Controlled vocabulary |
|---|---|---|
| `- Money: <v>` | `money` | `cents` \| `float` |
| `- Datetime: <v>` | `datetime` | `utc` \| `local` |
| `- Recurrence: <v>` | `recurrence` | `structured` \| `rrule` \| `none` |
| `- References: <v>` | `references` | `fk-only` \| `loose-allowed` |
| `- Weekday: <v>` | `weekday` | `iso` \| `us` (optional) |
| `#### Computed fields` bullets | `computed_fields` | `list[str]` |
| `#### Deferred` bullets | `deferred` | `list[str]` |

An out-of-vocabulary enum or an unknown data-model key → `not_extracted(...)` (flag, never guess —
§3); the subsection is optional (absent ⇒ no `data_model:` emitted). Unknown **top-level** keys are
rejected by `parse_conventions` (typo guard); `stack`/`naming` sub-keys are open vocab. Project-
agnostic (FR-VIP-9) — household's sheet is a fixture, never a built-in.

### 2.10 Business targets → `business-targets.yaml` *(value input — FR-VIP)*

What success looks like in numbers (the goal lines on dashboards). A `## Business targets` section:
key-lines + a `| Metric | Target | Why |` table per group. Round-trip authority
`kickoff_inputs.parse_business_targets`; emits `domain: business-targets`.

| Prose | → YAML | Rule |
|---|---|---|
| `- Provenance default: <v>` | `provenance_default` | scalar |
| `- Monetization: not-applicable` | `monetization: {mode_now, conversion_rate, price_point}` | `not-applicable` **expands** to the full block (the only v1 value; a live funnel needs its own sub-grammar) |
| `### Outcomes` table | `product_funnel` | Metric→snake_case key; `{target, why}` per row |
| `### Usage` table | `traction` | same |
| `### Unit economics` table | `unit_economics` | same |
| `### Per-role goals` `\| Role \| Goal \|` | `per_role_top_goals` | Role→key (verbatim), Goal→string |

`Target` parses as an **int** when it is a bare integer (`0`/`3`/`20`), else a string (`"95%"`,
`"<= $25"`). `Why` is free text. An **unrecognized `###` group** → `not_extracted(unknown-group)`
(flag, never guess). The whole section is optional. Project-agnostic — a personal tool's
household-outcome targets parse exactly like a SaaS funnel (FR-VIP-9).

### 2.11 Build preferences → `build-preferences.yaml` *(value input — FR-VIP)*

How the build factory runs (spend / model routing / profile). A `## Build preferences` section: a
`Provenance default` key-line + one `###` subsection per group, each a block of `- Key: value` lines.
Round-trip authority `kickoff_inputs.parse_build_preferences`; emits `domain: build-preferences`.

| Prose | → YAML | Rule |
|---|---|---|
| `- Provenance default: <v>` | `provenance_default` | scalar |
| `### Budgets` block | `budgets` | key→snake_case (`Per pipeline run`→`per_pipeline_run`); string values |
| `### Model routing` block | `model_routing` | key→snake_case; `Note`→`note` (free text) |
| `### Generation` block | `generation` | key→snake_case |
| `### Unattended` block | `unattended` | `Question answers`→`question_answers`; `Non interactive`→`non_interactive` (**bool**) |

`unattended.non_interactive` coerces `true`/`false` to a bool; a non-bool there is
`not_extracted`, never guessed. **Never** emit a pinned model version — only `*_tier` names (tiers
resolve via `model_catalog`). `language` should equal `conventions.yaml` `language` (one value, two
surfaces — disagreement is a preflight concern, not an extraction error). Unknown top-level keys are
rejected; group sub-keys are open vocab. The section is optional.

## 3. The friction loop (when prose doesn't match)

Non-conforming sections are **flagged, never guessed**: the extraction report lists each
manifest value as `extracted (from §X)` or `not extracted (no conforming section)`. The fix is
always the same — an LLM+human co-work pass that *reformats the customer's prose into the
contract*, then re-extract. The LLM proposes the formatted section; the human confirms it still
says what they meant. Values never enter through the LLM directly.

## 4. Traceability

Every extracted value records its source (`doc § / table row / sentence`) so the wireframe — and
later the delivered app — can answer "where did this come from?" back to the customer's own
words. This is the acceptance-gate currency: the business user walks the wireframe holding the
prose they wrote.

## 4b. Controlled-corpus alignment

The contract's controlled vocabularies and the terms extracted through them are **corpus
material** (`../controlled-corpus/CONTROLLED_CORPUS_REQUIREMENTS.md` — pre-implementation;
alignment is advisory until it ships, FR-H4-style: *collection here, accumulation there*):

- **Vocabularies are corpus-versioned.** The plain-type names, relationship verbs, and the
  five view archetypes are exactly the "controlled vocabulary" the corpus exists to make
  durable; the contract's grammar version stamps a corpus snapshot, so vocabulary growth never
  changes how an old doc extracts.
- **Extracted terms become corpus terms with bindings.** Every entity/page/view name extracted
  here is a term whose binding chain (`"Proof Point"` → `ProofPoint` model → `app.tables`
  construct) is precisely what the corpus tracks; each clean extraction + parser round-trip is
  a **determinism sample** strengthening that binding's confidence/maturity.
- **Surface-form canonicalization runs through corpus synonyms.** Customer prose drifts
  ("proof point" / "Proof Points" / "evidence item") — extraction consults corpus synonyms to
  map to the canonical term, **flagging** low-confidence matches for the co-work pass rather
  than auto-merging (the corpus doc's title-drift question, answered conservatively).
- **Precedence holds.** Contract-conforming human prose sits at the top of the established
  `SOURCE_PRECEDENCE` (human > reference > deterministic > inferred) — the corpus learns *from*
  it, never overrides it.

## 5. Vocabulary ownership (single source — CRP R1)

**This contract owns every controlled vocabulary and grammar** (§2.0 name rules, §2.1 types +
verbs, §2.3 archetypes + keys + route derivation, §2.4 completeness sentences, §2.7 settings).
The templates (`REQUIREMENTS_TEMPLATE.md`, `HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`,
`REQUIREMENTS_AND_PLAN_FORMAT.md`) and the wiring docs **cite §-refs**; any vocab list they
display is a non-normative snapshot and must say so. The three template drifts found at review
are resolved *into* the contract: `links to many` adopted (§2.1), `date+time` adopted (§2.1),
the nudge suffix documented as tolerated-and-flagged (§2.4). Vocabulary drift is this system's
recorded dominant failure mode (five instances before this review; three more found in the
teaching surfaces) — one owner, everyone else quotes.

## 6. Open questions

1. **Grammar versioning** — the controlled vocabularies (types, relationship verbs, archetypes)
   need a version stamp so old docs extract identically after vocabulary growth.
   **Direction (corpus alignment, §4b):** the version stamp is a corpus snapshot reference.
   *(Post-CRP note: this doc is now grammar v0.2 — the CRP adoptions (`links to many`,
   `date+time`) are the first vocabulary-growth event; the worked instance authored against
   v0.1+templates extracts identically under v0.2 by design.)*
2. **Where the formats are taught** — embed worked examples in the kickoff package templates
   (likely), plus a `--lint` mode that checks a doc against the contract before extraction.
3. **strtd8 retrofit** — `USER_JOURNEYS.md`/`REQUIREMENTS.md` predate this contract; retrofit
   the Pages/Views/Entities sections into them, or author a sibling extraction-source doc?

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-G1 | Complete + disambiguate the relationship grammar (links-to-many in; 3-entity join semantics; symmetric dedup; pluralization; plain-link non-conforming) | R1 (opus); endorsed R2 — pilot-blocking | §2.1 relationship-grammar block; pluralization in §2.0 | 2026-06-05 |
| R1-G2 | Publish the plain-type→Prisma mapping; one-field-per-row; Required vocab; adopt `date+time` | R1 (opus) | §2.1 normative mapping table (`number`→Int decided) | 2026-06-05 |
| R1-G3 | Enumerate per-kind view keys + Shows/Also-shows/Empty-state/Gap micro-grammars + block termination | R1 (opus); endorsed R2 | §2.3 per-kind keys + line micro-grammars | 2026-06-05 |
| R1-G4 | Name-derivation rules (annotation stripping, NFKD kebab, collisions pre-flight, reserved names) | R1 (opus); endorsed R2 | New §2.0 (shared by §2.1–2.3) | 2026-06-05 |
| R1-G5 | §2.7 Setting→AppManifest mapping + per-cell micro-grammars | R1 (opus) | §2.7 mapping table (port/sqlite-mode/env-keys = generator-gap; env-keys still parsed for the agreement check) | 2026-06-05 |
| R1-G6 | Single-source vocabulary ownership + resolve the 3 template drifts + exclude category-words + intro matcher | R1 (opus); endorsed R2 | New §5 ownership; §2.4 category-word mapping; drifts adopted into §2.1/§2.4 | 2026-06-05 |
| R2-G1 | `board` requires `Group by:` (+ optional `Order:`) | R2 (sonnet) | §2.3 per-kind keys | 2026-06-05 |
| R2-G2 | `Shows:` fk derivation sequenced AFTER the relationship pass; never guessed | R2 (sonnet) | §2.3 sequencing-dependency clause (`not_extracted(fk-unavailable)`) | 2026-06-05 |
| R2-G3 | View-heading annotation stripping (`View: ` prefix first, then `*(…)*`) | R2 (sonnet) | §2.0 annotation rule covers both heading forms | 2026-06-05 |
| R2-G4 | Completeness intro-sentence anchor pattern | R2 (sonnet) | §2.4 block-recognition bullet (`is complete when it has`, case-insensitive) | 2026-06-05 |
| R2-G5 | Nudge suffix flagged `not_extracted(generator-gap)` PER ENTRY (two report rows), never silently dropped | R2 (sonnet, adversarial) | §2.4 nudge bullet | 2026-06-05 |
| DMC-G1 | Add the `money` plain type (→ Int minor units) and surface the **data-model representation conventions** (money/dates/recurrence/references/computed/deferred) as a declared input + qualifying question set. The `references` loose-ref verb (already in §2.1, FR-PE-5c) and `default:` notes are synced into the teaching templates, which omitted them. | data-model-conventions update (household-o11y kickoff, 2026-06-23) | §2.1 type table (`money`); KICKOFF_REQUIREMENTS FR-F6/FR-H6; `conventions.yaml` `data_model:` block; template/how-to vocab sync | 2026-06-23 |
| VIP-G1 | Add **§2.9 Technology conventions → `conventions.yaml`** — the first prose-authored *value* input. Defines the section/subsection grammar (key-lines + stack/module-layout/naming tables + the FR-F6 `### Data-model conventions` enum block + architecture-invariant bullets), the controlled vocabularies, and flag-don't-guess handling. Implemented as `manifest_extraction.extract_conventions` + the strict round-trip authority `kickoff_inputs.parse_conventions` (`ConventionsManifest`). | FR-VIP slice (household-o11y kickoff, 2026-06-23); `SDK_VALUE_INPUT_AUTHORING_REQUIREMENTS.md` + `HOWTO_DATA_MODEL_CONVENTIONS_GRAMMAR.md` | §2.9 grammar + mapping/enum tables; `kickoff_inputs/conventions.py`; round-trip wired into `extract.py`; GRAMMAR_VERSION already `v0.3` | 2026-06-25 |
| VIP-G2 | Add **§2.10 Business targets → `business-targets.yaml`** — the value-input fan-out (table-per-group grammar: Outcomes/Usage/Unit-economics `\| Metric \| Target \| Why \|` → `product_funnel`/`traction`/`unit_economics`; Per-role goals table; int-vs-string target literal; `not-applicable` monetization expansion; unknown-group flag). `extract_business_targets` + `parse_business_targets` (`BusinessTargetsManifest`). | FR-VIP fan-out (household-o11y, 2026-06-23) | §2.10 grammar + mapping table; `kickoff_inputs/business_targets.py`; round-trip wired into `extract.py` | 2026-06-25 |
| VIP-G3 | Add **§2.11 Build preferences → `build-preferences.yaml`** — the value-input fan-out (key-line groups: Budgets/Model-routing/Generation/Unattended → snake_case scalar maps; `non_interactive` bool coercion; tier-names-never-versions). `extract_build_preferences` + `parse_build_preferences` (`BuildPreferencesManifest`). Closes the `cli_kickoff` "needs a `build_preferences_text` pass" backlog note. | FR-VIP fan-out (household-o11y, 2026-06-23) | §2.11 grammar + mapping table; `kickoff_inputs/build_preferences.py`; round-trip wired into `extract.py` | 2026-06-25 |
| VSP-G1 | Add the **§2.3 `Panel: <Name> = <field>, …` line production** (detail-compose only) → a `panels` entry surfacing Root-entity fields, shown when any is set. Repeatable; case-tolerant field resolution against the §2.1 graph with flag-don't-guess on unknown fields (the views round-trip gate doesn't field-check, so the extractor is the sole guard); off-archetype on non-detail-compose; genuinely-unstructured prose `Shows:` still flagged. Closes lane D9 / spike F3 (the "constrained Relations/Panels line format" follow-up). **No `view_codegen` change** — the `Panel{name,fields,show_when}` schema + detail-compose renderer already existed; only `extract_views` + the contract gained the production. GRAMMAR_VERSION → v0.4. | D9 / spike-finding F3 (reflective-requirements pass, 2026-06-29); `VIEW_SHOWS_PANELS_GRAMMAR_REQUIREMENTS.md` v0.2 + `_PLAN.md` v1.0 | §2.3 Panel micro-grammar; `manifest_extraction/extractors.py` `extract_views`; `models.py` GRAMMAR_VERSION | 2026-06-29 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: Claude Opus 4.8 (claude-opus-4-8-1m)
- **Date**: 2026-06-05 23:23:38 UTC
- **Scope**: First review of this contract (per `crp-focus-wiring-grammars.md` extended scope) — grammar ambiguity hunt: every §2 grammar tested against the strtd8 worked instance (`strtd8/docs/kickoff/REQUIREMENTS_v0.5-draft.md`) and against the generator parsers it must feed (`scaffold_codegen/manifest.py`, `pages_generator.py`, `view_codegen/manifest.py`, `ai_layer.py`, `derived.py`), read-only.

##### Executive summary

- The closed vocabularies are forked at birth: the templates teach `links to many` (relationships) and `date+time` (types) which §2.1 omits — and the reference consumer's conforming doc already uses `links to many` throughout. Extraction built to this contract alone flags the pilot's happy path.
- §2.3's "every other line maps 1:1" is not true: `Shows:`, `Empty state:`, `Of:`, `Formats:` have no defined mapping to `parse_views`' actual sub-schemas (`relations{name,from,fk}` etc.), and the required `fk` values are derivable only via the join models — a derivation the contract never states.
- The "links X to Y" 3-entity sentence is the single most ambiguous production: which pair gets the join model, whether the subject gets an FK, and how symmetric restatements dedup are all unstated.
- The claimed 1:1 plain-type → Prisma scalar mapping table is never published (`number` → Int or Float is a coin-flip).
- Name-derivation rules (kebab collisions, unicode folding, heading annotations, reserved names like `metadata`) are absent; `parse_pages` loud-fails on collisions, so extraction must pre-flight them.
- §2.7 lacks the Setting → `AppManifest` field mapping and per-cell micro-grammars; the worked instance's `env keys`/`database`/`logging` cells are unparseable without them.
- Single-source ownership should be declared here: this contract owns the vocabularies; templates and wiring docs cite.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-G1 | Interfaces | critical | Complete and disambiguate the relationship grammar: (i) decide `links to many` in or out of the closed set (templates teach it; the worked instance uses it; recommended: in, semantics = M2M join model between subject and object); (ii) define the 3-entity sentence "A links B to C" precisely — which join model(s) it produces (recommend: join(B,C); state whether A contributes an FK), its derived name (e.g. `BC` concatenation order) and compound-`@@id` field order; (iii) symmetric restatements ("a Capability links to many ProofPoints" + "a ProofPoint links to many Capabilities") dedup to ONE join model; (iv) entity references may be plural — singularization = match against declared entity headings after stripping a trailing `s`/`ies`, else `not_extracted`; (v) rule "links X to nothing (plain link)" (live in the worked instance's ProofPoint block) conforming or not | Two implementers today would emit different schemas from the same conforming doc — join arity, naming, dedup, and pluralization are all guesses; the worked instance exercises every one of these holes | §2.1, after the relationship-verbs bullet | Fixture per sub-rule from the worked instance's Entities section; assert exactly 3 join models (ProofPoint↔Capability, ProofPoint↔Outcome, Capability↔Outcome) from its relationship sentences |
| R1-G2 | Interfaces | high | Publish the plain-type → Prisma scalar mapping table the "mapped 1:1" claim references: `text`→String, `long text`→String, `number`→Int (or Float — must be decided), `decimal`→Decimal, `date`→DateTime, `yes/no`→Boolean, `choice of: …`→enum (+ enum type naming and value derivation rules); reconcile the template-taught `date+time`; add a one-field-per-row rule (the worked instance's `promptTokens / responseTokens` slash-row must be flagged, not parsed as one field); define the Required-column vocabulary (`yes`/`no`/blank) | "Mapped 1:1 to Prisma scalars" without the table is exactly the ambiguity class this contract exists to kill; `number`'s Int-vs-Float choice silently changes the generated schema | §2.1, replacing the field-types bullet | Golden: each plain type maps to one asserted Prisma scalar; slash-row fixture → `not_extracted(one-field-per-row)` |
| R1-G3 | Interfaces | high | §2.3: enumerate the constrained key set per kind and define the line micro-grammars: `Shows: A→B, A→C (annotation)` → `relations`/`aggregates` entries (state the arrow grammar, parenthetical-annotation tolerance, and that `fk` derives from the corresponding join model); map or flag `Also shows:`, `Of:`, `Formats:`, `Gap callout:` (worked-instance keys), and `Empty state:` (no `parse_views` home → `not_extracted(generator-gap)`); define what terminates a Views block (next heading or first non-`- Key:` line) | `parse_views` accepts only `name/kind/route/root/aggregates/signal/group_by/order/polymorphic/relations/panels/gap` and requires all of name/kind/route/root — "constrained keys" + "every other line maps 1:1" cannot be implemented as written; the worked instance's four view blocks use five surface keys with no defined mapping | §2.3, after the kind-aware route-derivation paragraph | Round-trip the worked instance's four Views blocks through `parse_views` using only contract rules; each surface key has one asserted destination or flag |
| R1-G4 | Data | high | Add name-derivation rules: (i) kebab-derivation collision behavior — two pages/views deriving the same slug or file-stem ⇒ flag BOTH `not_extracted(collision)` (`parse_pages` loud-fails on duplicate slugs and colliding derived names — extraction must pre-flight, never emit a manifest that dies in round-trip); (ii) unicode folding (is kebab("Résumé") `résumé` or `resume`? — recommend NFKD-fold to ASCII); (iii) heading-annotation stripping: `### TargetRole *(added 2026-06-05 — …)*` ⇒ entity name is the heading text minus a trailing ` *(…)*` group; (iv) reserved-name guard: entity/field names colliding with the generators' reserved set (the `metadata` class, Python keywords) ⇒ flag at extraction, citing the backend reserved-name guard | Every rule here is exercised by the worked instance (Résumé nav label, annotated headings) or by a shipped defect class (the `metadata` crash); without them, two extractors diverge and some emissions fail their own FR-WPI-4 round-trip | New §2.0 "Name derivation rules" (shared by §2.1–2.3) | Fixtures: colliding pair → both flagged; `Résumé` → asserted slug; annotated heading → clean entity name; `Metadata` entity → flagged |
| R1-G5 | Interfaces | medium | §2.7: publish the Setting → `AppManifest` mapping (package name→`app.package`, display name→`app.name`, python version→`app.python_version`, database→`persistence.path`, logging→`logging.file`, migrations→`migrations.enabled`, container→`container.dockerfile`; port/sqlite mode/env keys → `not_extracted(generator-gap)`) and per-cell micro-grammars: database (path extracted from a `sqlite:///` URL; parentheticals ignored), logging (first comma-segment = file path), container (leading `yes`/`no`), env keys (entries split on `·`, each `KEY (qualifier…)`, defaults compared against `build-preferences.yaml`) | The worked instance's cells are rich prose (`sqlite:///./app.db (override via DATABASE_URL)`, `logs/app.log, rotating, level INFO`, nested-paren env-keys) — without micro-grammars, the strtd8 `database`/`env` drift class this section exists to fix just recurs inside the cells | §2.7, after the settings-vocabulary sentence | Round-trip the worked instance's full Scaffold & runtime table → asserted `AppManifest` values + asserted generator-gap flags |
| R1-G6 | Architecture | high | Declare single-source vocabulary ownership: this contract owns all controlled vocabularies and grammars (§2.1 types + verbs, §2.3 archetypes + keys + route derivation, §2.4 completeness sentences, §2.7 settings); templates (`REQUIREMENTS_TEMPLATE.md`, `HOW_TO_AUTHOR…`, `REQUIREMENTS_AND_PLAN_FORMAT.md`) and the wiring docs cite §-refs and mark any quoted list as a non-normative snapshot. Resolve the three live template drifts: `links to many` (template:58 — fold into §2.1 per R1-G1), `date+time` (template:57 — adopt or strike), and the completeness nudge suffix (template:101 teaches `— nudge: "…"`, which §2.4 omits and the SDK cannot represent — recommend §2.4 document it as tolerated-and-flagged `not_extracted(generator-gap)` suffix, terminated at the ` — ` dash). Also in §2.4: define the exclude-line's category words ("connection records"/"join tables" map to the derived join models; anything else must be a declared entity name) and the intro-sentence matcher (recommend: any line ending `complete when it has:` introduces the block) | Vocabulary drift is this system's recorded dominant failure mode (five instances on record); the teaching surfaces already contradict the normative one before the first extractor is built, and the worked instance follows the templates, not the contract | New §6 "Vocabulary ownership"; §2.4 amendments inline | Grep-level check in CI or review: template vocab lists match contract §-refs; nudge-suffix fixture → min_rows extracted + suffix flagged; "connection records" exclude-line → join models excluded |

##### Endorsements & Disagreements

None — this is the document's first review round.

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-06

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-06 00:00:00 UTC
- **Scope**: Second review of KICKOFF_AUTHORING_CONTRACT.md; adversarial grammar pass against the strtd8 worked instance; second-order effects of R1-G1–G6; cross-doc single-source drift extensions; board-archetype gap; view-heading annotation extension.

##### Executive summary

- R1-G1's relationship dedup rule is confirmed load-bearing: the worked instance has all three join-model pairs stated symmetrically (6 sentences → 3 join models); without the dedup rule, the entire Completeness section's exclude list also breaks (R2-F5 in the requirements doc).
- §2.3 is missing per-kind required-key documentation for the `board` archetype — the contract lists it in the five but never defines its required `group_by` key.
- View-block heading annotation stripping is unstated for the `### View: Name *(…)*` form (R1-G4 covers entity headings only).
- The `shows:` arrow grammar in §2.3 is the single highest-ambiguity line: `Shows: A→B, A→C (annotation)` must map to `relations{name,from,fk}` which requires join-model knowledge — another sequencing dependency on R1-G1.
- §2.4's completeness intro-sentence is a free-prose sentence that must be matched by the extractor; the contract gives no anchor pattern.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-G1 | Interfaces | high | §2.3: add the `board` archetype's required-key definition alongside the other four — `board` requires `group_by` (an entity field name from the Root entity, used as the column discriminator; maps to `manifest.py`'s `group_by` key); optionally `order` (an ordered allow-list of column values). Without this, an author who picks `Kind: board` and omits `group_by` passes the contract but fails `parse_views` validation loud at FR-WPI-4 round-trip. The contract already defines route derivation per-kind; key requirements should follow the same pattern. | `parse_views` (`view_codegen/manifest.py:22–31`) lists `group_by` and `order` as known keys for board views; the contract §2.3 says "one block per composite view, constrained keys, archetype from the published vocabulary" but documents only the `detail-compose` example — `board` is in `HOW_TO_AUTHOR` §3 as "status columns" but its required key is nowhere in the contract. | §2.3, new sub-block after the worked example, following the pattern of the existing route-derivation paragraph | Fixture: `Kind: board` with and without `group_by` — without → `not_extracted(missing group_by)` per the contract |
| R2-G2 | Interfaces | medium | §2.3 (extension of R1-G3): define the `Shows:` arrow grammar as a **post-relationship-extraction** step — `Shows: A→B` maps to a `relations` entry where `name=AB` (or the join-model name derived from R1-G1), `from=A`, `fk` is the join-model's FK to B. This sequencing dependency is absent from both R1-G3 and the contract; an implementer building the views extractor in isolation (no relationship pass yet) cannot derive the `fk` value. State explicitly that the view extractor requires the entity/relationship extraction results as input. | The `relations{name, from, fk}` sub-schema in `parse_views` requires an FK column name that only exists after the join model is derived; `Shows: Capability→ProofPoint` requires knowing that the CapabilityProofPoint join model has an FK named (e.g.) `capabilityId`/`proofPointId` — derivable, but not from §2.3 alone. | §2.3, after the route-derivation paragraph; add a note: "The `Shows:` extractor runs after the entity/relationship pass — `fk` values derive from the join models R1-G1's rules produce." | Fixture: `Shows: Capability→ProofPoint` with and without prior relationship extraction → with prior pass: `fk` populated correctly; without → `not_extracted(fk-unavailable)` |
| R2-G3 | Data | medium | §2.3 (extension of R1-G4): define view-heading annotation stripping parallel to the entity-heading rule: `### View: Job Workspace *(P2 preview)*` → view name "Job Workspace" (strip the `View: ` prefix, then strip a trailing ` *(…)*` group by the same rule as entities). Without this, the `*(P2 preview)*` annotation from the worked instance produces a view named with the annotation, and the derived route includes the literal asterisks. Note: this is a second parse form from entity headings — the prefix `View: ` is stripped first, then annotation stripping applies to the remainder. | The worked instance's three `*(P2 preview)*` views are the only non-trivial test of this rule; R1-G4 defines entity annotation stripping but §2.3 has no parallel statement; the two heading forms parse differently and the contract must state both. | §2.3, new sentence before the route-derivation paragraph | Fixture: `### View: Job Workspace *(P2 preview)*` → name="Job Workspace", route="/job-workspace" (annotation not in route) |
| R2-G4 | Architecture | low | §2.4: add an explicit intro-sentence anchor pattern — the extractor must recognize the completeness block's opening; recommend: "any sentence that contains the phrase `is complete when it has`" (case-insensitive, after the entity name) introduces the block. This prevents an author's paraphrase ("reaches completion once it has") from silently producing a missing completeness manifest. Cross-doc: `HOW_TO_AUTHOR` §2 step 5 says "In controlled sentences: *at least N Entity*" without specifying the intro sentence. | "A profile is complete when it has" is the only worked example; the contract §2.4 shows the bullet list but not the line before it; an extractor that anchors on `complete when it has:` (colon-terminated) misses the worked instance's form which ends with `*(confirmed items only…)*` on the same line. | §2.4, before the worked example; add: "Intro-sentence pattern: any sentence containing `is complete when it has` (case-insensitive) opens the block." | Fixture: the worked instance's `A profile's value model is complete when it has *(confirmed items only…)*:` → block recognized and bullet list extracted |

##### Stress-test / adversarial pass

**Guessing `fk` values in `Shows:` lines.** An implementer who satisfies the letter of R1-G3 (map `Shows: A→B` to a `relations` entry) without the R1-G1 relationship-extraction pass would guess the `fk` value — probably `<A>Id` or `<B>Id` by convention. For `Capability→ProofPoint`, this produces `fk=capabilityId` or `fk=proofPointId` depending on the guess direction. The `parse_views` round-trip (FR-WPI-4) does NOT validate FK column names against the schema — it accepts any string for `fk`. So a wrong FK guess passes the round-trip and only fails at `generate views` time when the DB column doesn't exist. R2-G2 closes this by requiring the prior relationship pass; R1-G3 must cite R2-G2 (or vice-versa) to be implementable.

**Completeness nudge suffix extraction ceremony.** The worked instance has `- at least 3 ProofPoints — nudge: "Add confirmed proof points…"`. R1-G6 recommends documenting nudge as `not_extracted(generator-gap)`. But an implementer who implements only the `min_rows` extraction and silently ignores the ` — nudge: "…"` suffix (without flagging it) satisfies the letter of R1-G6 while producing an extraction report that doesn't mention the nudge at all. The flag must be explicit: the extractor must emit `not_extracted(generator-gap)` for the nudge portion *per entry*, not just drop it. R1-G6 implies this but doesn't state it as a per-entry reporting requirement.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-G5 | Validation | medium | §2.4: state that the nudge suffix (`— nudge: "…"` per the template) is reported `not_extracted(generator-gap)` **per entry** in the extraction report — not silently dropped — so the report surfaces the backlog item for every completeness rule that has an unsupported suffix. An implementer who silently drops the suffix satisfies "emit the SDK schema" but violates FR-WPI-3's "full traceability" because the report omits a value the author wrote. | The strtd8 worked instance has five completeness entries, all with nudge suffixes; a silent drop means the extraction report shows five `extracted` entries with no mention of five `not_extracted(generator-gap)` nudges — the business user's authored nudge text disappears without a trace. | §2.4, annotation after the intro-sentence recommendation (or inline with R1-G6's nudge resolution) | Fixture: completeness entry with nudge suffix → extraction report has TWO rows for that entry: one `extracted` for min_rows, one `not_extracted(generator-gap)` for the nudge |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-G1: Relationship grammar disambiguation — endorsing; the adversarial pass confirms this is pilot-blocking: all 6 symmetric relationship sentences in the worked instance produce 3 join models only with the dedup rule.
- R1-G3: §2.3 constrained-key enumeration + Shows micro-grammar — endorsing; R2-G2 extends this with the sequencing dependency on the relationship pass.
- R1-G4: Name-derivation rules — endorsing; R2-G3 extends this with the view-heading form.
- R1-G6: Single-source ownership + nudge resolution — endorsing; R2-G5 tightens the per-entry reporting requirement for nudge suffixes.

**Disagreements:** none — all R1-G* suggestions are independently confirmed against the worked instance.
