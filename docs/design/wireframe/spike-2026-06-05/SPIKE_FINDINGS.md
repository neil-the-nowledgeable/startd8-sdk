# Spike Findings — Deterministic Manifest Extraction on Real strtd8 Prose

**Date:** 2026-06-05
**Question:** does the authoring-contract grammar survive contact with real kickoff prose, and
do extracted manifests round-trip clean through the SDK parsers (FR-WPI-1/2/4's core claim)?
**Method:** ~300 lines of throwaway stdlib parsing (`spike.py`, this dir) against the REAL
`strtd8/docs/kickoff/REQUIREMENTS_v0.5-draft.md` — pages + app + views + completeness
extractors, FR-WPI-3-shaped report, round-trip via the generators' own parsers, then a full
`startd8 wireframe` run on the extracted set + the real contract.
**Artifacts:** `manifests/` (the extracted four), `extraction-report.json` (22 extracted / 3
defaulted / 11 not_extracted), `spike.py`.

## Verdict: the thesis HOLDS — pilot acceptance hit on first real contact

```
4/4 extracted manifests ROUND-TRIP CLEAN (parse_pages / parse_app_manifest /
                                          parse_views / completeness loader)
Status:  7 planned / 1 not defined / 0 invalid     (was: 3 INVALID hand-authored)
Shape:   Entities: 16 | CRUD routes: 80 | Pages: 3 | Views: 4 | AI passes: 5
Cascade: scaffold: ready | backend: ready | views: ready
```

Every item of the standing strtd8 acceptance (`VALIDATION_AND_MANIFEST_DERIVATION.md` §2)
checked: **16 entities / 80 routes** ✓ · `Target Roles` in nav (17 items, table order) ✓ ·
`Metric.value` rendered `owned`-omitted in the form plan (FR-6) ✓ · readiness ×3 `ready` ✓ ·
the 3 invalid hand-authored manifests reproduced correctly from the doc, including the exact
drift keys (`database`/`env`, `label`/`path`, `archetype`) that made the originals invalid.

**Working as designed (not gaps):** dashboard `Shows: counts of X and Y per job` → aggregates
with schema-resolved FKs (`tailored_matches_count, of: TailoredMatch, fk: jobDescriptionId`);
export-package `Of: Job Workspace` → root resolved via the referenced view; **nav-table route
precedence** (Value Map → `/value-map` from the Nav table, others kind-derived); the three
§2.7 generator-gap settings + completeness nudges flagged `not_extracted`, manifests still
clean (the subset rules behave).

## Findings — feed back into the spec + contract (and the focus-CRP session)

| # | Finding | Recommendation |
|---|---------|----------------|
| F1 | **Adjacent tables merge** under naive `\|`-line scanning — the Pages section legitimately holds TWO tables (Pages + Nav); spike v1 produced 21 phantom pages | P0 `parse_md_table` must segment tables as maximal consecutive-`\|` runs (fixed in spike v2; encode as a P0 test) |
| F2 | **Unicode in names**: `Résumé` → naive kebab yields `/r-sum` | Contract route-derivation rule needs NFKD normalization (`é`→`e` → `/resume`); add to §2.2 + a P1 test |
| F3 | **`Shows:` lines for detail-compose/workspace are prose, not grammar** ("resolved to whichever value-model item each points at") — relation/panel resolution is NOT deterministically extractable as written; dashboards' `counts of …` ARE | v1: extract kind/root/route for those archetypes, flag `shows` `not_extracted` — **views still round-trip and render as shells** (ViewSpec allows empty relations/panels). Contract follow-up: a constrained Relations/Panels line format |
| F4 | **Category vs entity-name in exclude**: "Don't count: connection records, AiCall" — `connection records` is a category | Either enforce literal entity names in the contract, or (better) define the category: join models are **schema-derivable** (compound-`@@id` link tables) — a deterministic expansion rule, no guessing |
| F5 | **Ungrammared view lines**: `Also shows:` / `Empty state:` / `Formats:` have no ViewSpec home; `Gap callout:` maps to `gap.needs_from` but needs field-name resolution from prose | Flag `not_extracted` v1 (done); `Formats:` is a generator-gap (export-package format selection isn't manifest-expressible) — same backlog class as §2.7 |
| F6 | **Nav table is a route authority**: it carries view routes (`/value-map`) and entity-UI routes, not just page routes | Make route precedence explicit in the contract: Nav table > kind-aware derivation; nav targets pointing at generated CRUD/UI routes pass through untouched |

## Cost & scope evidence for the plan

The four extractors + table parser + report = **~300 lines, stdlib + yaml only, zero LLM
calls** — consistent with the plan's P0/P1 sizing. The hard 20% is exactly where the spike
drew the line: detail-compose/workspace relation grammar (F3) and prose-category expansion
(F4) — both have honest `not_extracted` fallbacks, so they don't block P0–P6.

*Spike code is throwaway-quality (single-doc, regex-first); P0/P1 implementation supersedes it.
Kept here as evidence + grammar test-case source.*
