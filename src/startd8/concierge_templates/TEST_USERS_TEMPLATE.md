# <Project> — Test Users

> **TEMPLATE** — copy into `<project>/docs/`, replace every `<…>`, delete guidance lines
> (the `▷` lines) and this banner. How-to:
> [`HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`](HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md).
> Section headings are EXACT — the build system anchors on them. Pairs with the project's
> REQUIREMENTS: every entity and field named here must exist in its Entities section.

**Project:** <name>   **Version:** <0.1.0>   **Date:** <YYYY-MM-DD>
**Format:** requirements-and-plan-format v0.1 / authoring-contract grammar v0.1
**Pairs with:** `<REQUIREMENTS file>` (Entities + AI assists + Owned fields are the vocabulary)

> **What this document is (and is not).** Test users are **static test data** — bucket 2 of the
> generation scope: the throwaway rows that prove the application works. They exist so every
> generated screen, AI pass, and policy can be exercised end-to-end *before any real user
> exists*. The content does **not** need to be good — it needs to be *shaped right* and
> *complete enough to reach every behavior listed in Coverage*. Nothing here is ever shipped
> content, never graded on quality, and is deleted/reset freely.
>
> **Reading the row tables:** columns are the entity's own fields (REQUIREMENTS vocabulary,
> same plain types). Two bookkeeping columns are fixture-specific: **state** declares the
> provenance the row is seeded with — `confirmed` (user-approved data), `suggested`
> (AI-suggested, awaiting review: seeds `source:"ai", confirmed:false`) — so both halves of
> the suggest→confirm loop are testable. You never type ids or timestamps; rows are referenced
> **by name**, and the derivation resolves names to ids.

## Purpose

<2–3 sentences: what these fixtures must prove for THIS project — typically: every AI pass
runs against a realistic confirmed model; every view/page renders non-empty; the owned-field
policy holds.>

## Test users

▷ One `###` block per test user. 1 is the minimum; add more only when they exercise a
▷ DIFFERENT shape (an empty-state user, a maximal user, an edge-case user) — never for variety.

### User: <short-name>

**Shape:** <one phrase: what this user's data is FOR — e.g. "complete confirmed model,
the happy path" / "fresh signup, all empty states" / "mid-wizard: half suggested, half confirmed">

#### Rows: <EntityName>

▷ One `####` table per entity this user owns rows in, heading exactly `Rows: <EntityName>`.
▷ Columns = the entity's fields from REQUIREMENTS (omit any field to leave it blank/default)
▷ + the `state` column. The `name`-like field (first text field) is the row's reference key.
| <field> | <field> | … | state |
|---------|---------|---|-------|
| <value> | <value> | … | <confirmed|suggested> |

#### Links

▷ Only for link/join relationships ("links X to Y" in REQUIREMENTS). Reference rows by the
▷ name values used above. One line per connection.
- <EntityName> "<row name>" → <OtherEntity> "<row name>"

#### Owned-field proofs

▷ The rows that prove ONLY HUMANS ENTER THIS fields survive the AI passes untouched. One line
▷ per proof: the field, the human-typed value seeded above, and the invariant. The build turns
▷ each line into a test assertion.
- <Entity.field> = "<seeded value>" — AI passes must leave it byte-identical.

## Coverage

▷ The contract this document makes with the build: which behaviors these users prove. One row
▷ per behavior; every AI pass in REQUIREMENTS "AI assists" SHOULD appear (a pass no test user
▷ can reach is a gap — flag it, don't hide it). Views/pages with empty-state behavior get a
▷ row pointing at the user that exercises emptiness.
| Behavior | Exercised by | How it's proven |
|----------|--------------|-----------------|
| AI pass: <pass name> | <user short-name> | runs against this user's <inputs>; output rows land `suggested`; shape-valid |
| View: <view name> | <user short-name> | renders non-empty with this user's rows |
| Empty state: <view/page> | <empty-state user> | renders the declared empty state, no error |
| Owned field: <Entity.field> | <user short-name> | seeded value byte-identical after every pass |

## Lifecycle

▷ Defaults shown; edit only if your project differs.
- Seeds load in **test and development only** — never in a production boot.
- Loading is **idempotent**: re-seeding the same user replaces that user's rows wholesale.
- Fixtures are **reset-able**: a test may delete everything a user owns and re-seed.
- Quality is **out of scope**: no review gate ever judges fixture prose; only shape, reachability
  (Coverage), and owned-field proofs are asserted.

---

▷ Derivation contract (delete this footer in your instance): the seed fixtures derive from
▷ this document — `seeds/<short-name>.yaml`, one per test user — the same
▷ machines-translate-humans-confirm model as the assembly manifests. Verbatim values; `state`
▷ maps to provenance (`confirmed` → `source:"user", confirmed:true`; `suggested` →
▷ `source:"ai", confirmed:false`); names resolve to generated ids; Links become FK/join rows;
▷ Owned-field proofs become test assertions. Hand-editing the derived YAML instead of this
▷ document recreates the drift class the wireframe exists to catch.
