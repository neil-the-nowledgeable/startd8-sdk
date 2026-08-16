# Chrome-Binding Grammar — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.2 (post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · architecture `ARCHITECTURE_navig8r-presentation-definition-inheritance.md` (§7 step 3 — chrome as binding-expressions)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-10-view-definition-cascade (parent keystone) · REQ-11-theme-token-activation (sibling) · SOTTO_DESIGN_PRINCIPLE (byte-identical-when-absent)
**Audience:** operator / SDK contributors / cross-repo adopters (legal · benchmark · dev-os)
**Trust boundary:** local filesystem + authored definitions; no LLM; no network
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-derives-domain-chrome-from-f0e5970e`
> **Semantic name:** *SDK navigator derives domain chrome from content via a tiny binding-expression grammar so a definition's chrome fields carry {key}/{title}/{semantic_name} placeholders resolved against a per-doc context at projection time, generalizing the FR-17/18 masthead derivation while unbound chrome and the app path stay byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-12`

## 0. Why this exists — the one genuinely "language"-like piece

The architecture (§7 step 3) names chrome derivation as the sole grammar-like piece of the presentation
system: chrome fields **derived from content** via `{doc.title}` / `{node.key}` placeholders rather than
hardcoded. Today that derivation exists but is **imperative and requirements-specific** —
`requirements_profile_for` (FR-17/18) reads `requirement_identity()` and rebuilds the masthead with
Python (`eyebrow = key`, `section_lead = f"What {key} defines"`, …). This REQ **lifts those rules into
the definition** as declarative `{field}` bindings resolved by a tiny shared grammar at projection time,
so any domain (not just requirements) can derive chrome from its content context, and the derivation is
data — inspectable via `view-definition`, cascade-inheritable — not code. Scoped to the chrome-binding
mechanism only; unbound chrome stays byte-identical.

## 0. Planning Insights (self-reflective update)

> Planning against the real `requirements_profile_for` (sources_requirements.py) revealed the derivation
> is **two shapes**, not one — a correction that scopes the grammar honestly:

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Every chrome derivation is a single `{field}` template | Four fields are single-source (`eyebrow={key}`, `headline={title}`, `section_lead="What {key} defines"`, `summary_meta=["{semantic_name}"]`) — but the page **`title`** is a **compound with 3-way degradation** (`{key} — {title}`; key-only→`key`; title-only→`title`; neither→static) that a single-placeholder grammar cannot express | **NR-2**: the grammar covers single-field bindings this step; the compound page-title's degradation **stays in `requirements_profile_for`** (a richer expression grammar with conditionals is a later refinement) — keeps byte-identity exact without over-building |
| Bindings can just replace the chrome strings | The base `REQUIREMENTS_PROFILE` (no per-doc context) and non-requirements domains render with **static** chrome; a literal `{key}` there would leak the placeholder | **FR-3**: bindings apply ONLY when a context is passed AND all referenced fields resolve non-empty; else the static chrome value stands (graceful fallback = today's behaviour) |
| Every field derives | `why`/`do` (reading guidance) and `gap_noun` (vocabulary) are intentionally NOT derived | bindings are opt-in per field; unbound fields ride through unchanged |

**Resolved open questions:** OQ-1 (grammar power?) → single-field `{field}` substitution only, no
functions/conditionals (NR-2). OQ-2 (context source?) → the existing `requirement_identity()` output
(`key`/`title`/`semantic_name`/`initiative`); no new extraction (NR-3). OQ-3 (byte-identity of the
per-doc requirements render?) → preserved by reproducing the single-field rules exactly + leaving the
compound title in place.

## Overview

Add a tiny binding-expression resolver — `resolve_bindings(template, context)` — that substitutes
`{field}` placeholders from a context dict (single-field substitution only). Let a `ViewDefinition`'s
`chrome` carry an optional `bindings: {chrome_field: template}` map. Extend `to_render_profile(resolved,
context=None)` so that, when a context is supplied, each bound chrome field is set to the resolved
template **iff** every referenced field is non-empty, otherwise the static chrome value stands. Move the
requirements domain's FR-17/18 single-field derivations (`eyebrow`/`headline`/`section_lead`/
`summary_meta`) into `REQUIREMENTS_DEFINITION.chrome.bindings`, and reduce `requirements_profile_for` to
a thin caller that passes `requirement_identity(path)` as the context (retaining only the compound
page-title logic, NR-2). Unbound chrome, non-requirements domains, and the app-scaffold path stay
byte-identical.

## Objectives

- **O-1:** Chrome derives from content as data — target: a definition's chrome carries `{field}` bindings resolved against a per-doc context at projection time (not hardcoded Python).
- **O-2:** Byte-identity preserved — target: `REQUIREMENTS_PROFILE` (no context), capability/node-schema, and the app path are byte-identical; `requirements_profile_for(REQ-01)` reproduces today's masthead exactly.
- **O-3:** The derivation is inspectable + inheritable — target: bindings live in the definition (visible via `view-definition`, cascade-mergeable), generalizing FR-17/18 beyond the requirements domain.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A binding leaks a literal `{key}` into the static base profile or a non-requirements domain | FR-3: bindings apply only with a context and only when fields resolve non-empty; else static value stands | high |
| quality | The per-doc requirements render drifts from today (the FR-17/18 output) | FR-4/FR-5: reproduce the single-field rules exactly; keep the compound page-title in `requirements_profile_for` (NR-2); byte-identity test | high |
| complexity | Building a full expression language (functions, conditionals, arithmetic) | NR-2: single-field `{field}` substitution only; the compound title is the sole documented exception | medium |
| scope | Creep into control/region/shell/serialization derivation | NR-1: chrome bindings only — those are later architecture steps | medium |

## Functional requirements

- **FR-1 — Binding-expression resolver.** A `resolve_bindings(template: str, context: Mapping[str, str]) -> str` substitutes `{field}` placeholders in a template with the context's values (single-field substitution only — no functions, conditionals, or arithmetic); an unknown/empty field substitutes the empty string. Name: Navigator adds a tiny binding resolver that substitutes single-field placeholders in a chrome template from a context. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does resolve_bindings substitute {field} placeholders and nothing more (no expression language)?. Verify: `resolve_bindings("What {key} defines", {"key": "REQ-01"})` returns `"What REQ-01 defines"`; `resolve_bindings("{missing}", {})` returns `""`; a template with no placeholder is returned unchanged. Serves: O-1
- **FR-2 — Chrome carries an optional bindings map.** A `ViewDefinition`'s `chrome` may include a `bindings: {chrome_field: template}` map (keyed by the RenderProfile chrome field it derives); an absent/empty `bindings` means no derivation — the byte-identity guard. Name: A ViewDefinition chrome section carries an optional bindings map keyed by the chrome field each template derives. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: is bindings optional and absent by default?. Verify: a definition whose `chrome` has no `bindings` key projects identically with or without a context; a `bindings` map round-trips through `to_dict`/`from_dict`. Serves: O-2
- **FR-3 — Context-gated binding application at projection.** `to_render_profile(resolved, context=None)` gains an optional context; when a context is supplied, each field named in `chrome.bindings` is set to `resolve_bindings(template, context)` **iff** every field the template references resolves non-empty, otherwise the static chrome value stands; `context=None` leaves chrome untouched (byte-identical). Name: Navigator applies chrome bindings at projection only under a context and only when referenced fields resolve non-empty. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: do bindings apply only with a context and fall back to static when a field is empty?. Verify: with `context=None`, `to_render_profile` output equals today's (unbound); with a context supplying `key`, the `eyebrow` binding `"{key}"` yields the key; with a context whose `key` is empty, `eyebrow` stays the static value. Serves: O-2
- **FR-4 — Requirements domain derivations become bindings.** `REQUIREMENTS_DEFINITION.chrome.bindings` carries the FR-17/18 single-field rules (`eyebrow="{key}"`, `headline="{title}"`, `section_lead="What {key} defines"`, `summary_meta=["{semantic_name}"]`), and `requirements_profile_for` reduces to projecting with `requirement_identity(path)` as context — retaining ONLY the compound page-title logic (NR-2). Name: The requirements domain expresses its FR-17/18 masthead derivations as chrome bindings and requirements_profile_for becomes a thin context-passing caller. Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_sources_and_cli.py`. Lives: code src/startd8/navigator/sources_requirements.py. Approve?: are the requirements masthead rules now declarative bindings rather than hardcoded Python?. Verify: `REQUIREMENTS_DEFINITION.chrome["bindings"]["eyebrow"] == "{key}"` and `["section_lead"] == "What {key} defines"`; `requirements_profile_for(REQ-01)` returns eyebrow `"REQ-01"`, headline the H1 title, and `section_lead "What REQ-01 defines"` — identical to today. Serves: O-1
- **FR-5 — Byte-identity across the unbound surfaces.** The base `REQUIREMENTS_PROFILE` (no context), the capability + node-schema domains (no bindings), and the app-scaffold path stay byte-identical; the per-doc `requirements_profile_for` output is unchanged from today. Name: Chrome bindings leave the static base profile, non-requirements domains, and the app path byte-identical. Touches: `tests/unit/navigator/test_view_definition.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_view_definition.py. Approve?: are all unbound surfaces byte-identical after bindings land?. Verify: `REQUIREMENTS_PROFILE.eyebrow == "This spec"` (static, no context); `to_render_profile(resolve(CAPABILITY_DEFINITION))` is unchanged; `test_no_profile_is_byte_identical` passes unedited; `requirements_profile_for(REQ-01)` equals its pre-REQ-12 output. Serves: O-2
- **FR-6 — Bindings are inspectable + inherited.** The `bindings` map is part of the resolved definition (dumped by `view-definition`, cascade-merged by id), so a domain inherits the base's binding rules and can override one — generalizing FR-17/18 beyond requirements. Name: Chrome bindings resolve through the cascade and are inspectable via the view-definition dump. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: do bindings ride the cascade and appear in the resolved dump?. Verify: `resolve(REQUIREMENTS_DEFINITION).chrome["bindings"]["eyebrow"] == "{key}"`; a child overriding one binding keeps the base's other bindings (keyed merge by field). Serves: O-3

## Non-requirements

- **NR-1:** Chrome bindings ONLY. This REQ does not add control schema (architecture §7 step 4), region/layer bindings (step 5), shared shell fragments (step 6), or cross-repo `VIEW-SCHEMA` serialization (step 7) — each a separate later REQ.
- **NR-2:** Single-field `{field}` substitution only — NO functions (`{count(nodes)}`), conditionals, or arithmetic. The compound page-title derivation (`{key} — {title}` with 3-way degradation) is NOT expressed in the grammar this step; it stays in `requirements_profile_for`. A richer expression grammar (multi-field templates with degradation, `count(...)`) is a later refinement.
- **NR-3:** No new content-context sources — the binding context is the existing `requirement_identity()` output (`key`/`title`/`semantic_name`/`initiative`). No new extraction or fields.
- **NR-4:** Unbound chrome, non-requirements domains, and the app-scaffold path are byte-identical — the empty-default `bindings` map + context-gated application are the guard (SOTTO); the static chrome values are never deleted (they remain the fallback layer).

## Appendix A — Accepted (with where merged)
*(none yet — CRP incoming)*

## Appendix B — Rejected (with rationale)
*(none yet — CRP incoming)*

## Appendix C — Incoming review rounds
*(none yet)*

*v0.2 — Post-planning self-reflective update. Grammar scoped to single-field bindings; compound page-title kept in requirements_profile_for (NR-2); 3 open questions resolved.*
