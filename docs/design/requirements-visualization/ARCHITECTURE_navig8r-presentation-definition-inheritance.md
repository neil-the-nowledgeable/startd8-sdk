# Navig8r Presentation Definition — Cross-Domain Inheritance Architecture

**Status:** architecture / vision (design-time) · 2026-08-15
**Question this answers:** *Can/should we define a presentation-definition "language" for the navig8r
(requirements) visualizer to separate presentation from content into entirely different structures, with
an inheritance model so a top-level design definition propagates to downstream domains while each keeps its
unique logic atomically — toward a cross-domain visualization layer that maximizes reuse.*

## TL;DR
- **Yes** — as a **declarative View Definition** (the serializable presentation twin of `NODE-SCHEMA`),
  **grown from `RenderProfile`**, with **CSS-cascade / design-token inheritance** (base ⊕ domain ⊕
  instance, deep-merged per leaf → atomic), **not a bespoke parser**.
- The one genuinely "language"-like piece is a **tiny binding-expression grammar** for deriving chrome
  from content (`{doc.title}`, `{node.key}` — FR-17 generalized). Everything else is structured data + cascade.
- **The scaffold-mode taxonomy you already built (control · descriptive · computed · node-driven) IS the
  schema of the presentation definition.** The debugging layer revealed the structure; the definition
  formalizes it.

## 1. The essential separation — two structures, one render
- **CONTENT** = the Node graph (`NODE-SCHEMA`). Domain data. Already the fixed point.
- **PRESENTATION** = the **View Definition**. Domain-agnostic base + thin per-domain deltas. A *different
  structure*, serializable, inheritable.
- They meet only at render: `render(nodes, view_definition) → view`. A pure function; both inputs are contracts.

## 2. The render pipeline (composition)
```
Fᵢ:  Domain → Node-graph                              (source projection — CONTENT)     nodes_from_requirements, …
Lens: (nodes, role, fluency) → lensed view-model      (audience — SHARED)               node_lenses
Res:  (base ⊕ domain ⊕ instance) → View Definition    (presentation CASCADE)            NEW
Gⱼ:   (lensed view-model, View Definition) → output   (RENDERER)                        wireframe/tree/a11y/graph/diff
```
`Gⱼ( Lens(Fᵢ(domain), role, fluency), Res(base, domain, instance) )`. Content (Fᵢ) and presentation (Res)
are entirely separate structures that compose only at Gⱼ.

## 3. What the View Definition captures — mapped to the scaffold taxonomy
| Definition section | Scaffold layer | Shared / domain | Examples (today's home) |
|---|---|---|---|
| **theme** (tokens) | cross-cutting | SHARED base + optional domain tweak | colors/fonts/spacing (today: hardcoded CSS `:root`) |
| **vocabulary** | descriptive | DOMAIN | statuses (name/meaning/color/severity), gap_noun, labels |
| **chrome** (derivation rules) | descriptive | SHARED rules, domain values | eyebrow=`{node.key}`, headline=`{doc.title}`, subtitle=`{doc.semantic_name}` (FR-17); why/do/section_lead |
| **glance** | computed | SHARED bindings | status roll-up, plan.shape |
| **control** | control | SHARED | the top-right VIEW MODE options |
| **regions** | (layout) | SHARED skeleton + domain add/remove | ordered regions × layer × binding (today: `data-scaffold`/`data-layer`) |
| **lenses** | cross-cutting | SHARED | audience × fluency (node_lenses) |
| **shell** | (renderer) | SHARED fragments + renderer structure | a11y conventions, XSS helpers, scaffold CSS |

**~90% shared, ~10% domain-override.** That ratio is *why* inheritance is the right model.

## 4. Inheritance — atomic + propagating (the load-bearing mechanic)
- **Cascade:** `resolve(def) = deep_merge(resolve(def.extends), def)` — recursive; **later wins per leaf key**.
- **Atomic:** override at the *finest grain* (one token, one status, one region-binding). Overriding
  `theme.accent` does NOT freeze `theme.ink` — that still inherits base updates. This is precisely "retain
  unique logic while getting updates."
- **Propagating:** change the base → every non-overriding inheritor gets it automatically.
- **Requirement for atomicity:** overridable collections are **keyed maps, not positional lists** (statuses
  keyed by id, regions keyed by name) so a delta merges by key, not whole-list replace. (Today
  `dataclasses.replace(REQUIREMENTS_PROFILE, statuses=…)` is *shallow* — replaces the whole tuple; the
  definition upgrades this to deep, keyed merge.)
- This is **CSS custom-property cascade / design-token `extend`** semantics — a proven model, not an invention.

## 5. Is it a "language"? (can we)
The declarative schema + cascade is a *definition language* in the meaningful sense (a governed, inheritable
contract) **without a bespoke parser**:
- **Schema** = the presentation twin of `NODE-SCHEMA` → **`VIEW-SCHEMA` / NODE-VIEW-DEFINITION**
  (serializable JSON, cross-repo, governable by REQ-06).
- The one true grammar = **binding expressions** for chrome (`{doc.title}`, `{node.key}`, `{count(nodes)}`)
  — a tiny, **sandboxed** resolver over a whitelisted content context (no `eval`). Generalizes FR-17.
- Cascade semantics = deep-merge. Reuse, not invent.

## 6. Should we? (the discipline)
**Essential complexity (real):** N domains × M renderers, cross-repo (legal · benchmark · dev-os live in
*other repos*). A cross-repo boundary can't share Python classes — it needs a **serializable presentation
contract**, symmetric to the `NODE-SCHEMA-JSON` those repos already emit. That argues *for* a declarative
View Definition.
**Accidental-complexity guard (Personal Conway / the requirements-engineering-OS shadow):** do NOT build a
bespoke parser, a plugin system, or a general theming engine up front. **Grow from `RenderProfile`** (already
has `to_dict`), add cascade + tokens + bindings incrementally, and **prove each step with a 2nd real domain**
before generalizing. One-example generalization is the trap.
**Verdict: yes — incrementally, serializable, cascade-based, parser-free, proven by a 2nd domain.**

## 7. Incremental path (each a Spec Delivery Loop REQ)
1. **View Definition schema + cascade resolver** (deep-merge, keyed collections). Prove: requirements +
   one more domain share a base; a base change propagates to both. *Keystone — REQ-10.*
2. **Theme tokens into the definition** — extract the hardcoded CSS `:root`; renderers read tokens from the
   resolved definition → theme updates propagate to every renderer/domain.
3. **Chrome as binding-expressions** — generalize FR-17 (+ the static-text pass's section_lead/title) into
   `{…}` bindings resolved against a content context.
4. **Control-layer schema** — formalize the consolidated top-right options as the definition's `control` section.
5. **Region/layer bindings** — promote `data-scaffold`/`data-layer` into first-class definition entries
   (scaffold mode becomes a *read* of the definition — the mirror closes).
6. **Shared shell fragments** — extract a11y conventions, XSS helpers, scaffold CSS into a base shell module
   renderers import → base updates propagate.
7. **Cross-repo serialization** — emit/consume `VIEW-SCHEMA` JSON; onboard the 2nd repo (legal or benchmark).

## 8. How today's two parallel tasks feed this
- **Static-text derivation** (section_lead / page title; classify why/do as guidance) = the **chrome
  derivation rules** (§3 chrome, §7 step 3) — converting static copy into bindings.
- **Top-right consolidation** = the **control-layer schema** (§3 control, §7 step 4) — the first structuring
  of the definition's `control` section.
They are literally building the first two layers of the View Definition.

## 9. Principle alignment
- **Kagami:** the base is the single source; inheritors *reference* (`extends`), never fork.
- **Mottainai:** reuse the base; don't re-derive per domain.
- **Sotto:** content rides the deterministic presentation skeleton; the definition IS the skeleton.
- **Accidental-Complexity anti-principle:** the parser-free / prove-with-2 discipline is the guard.
