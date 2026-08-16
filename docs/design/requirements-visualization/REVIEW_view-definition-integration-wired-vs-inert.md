# Review: navig8r ↔ View Definition integration — wired vs inert

> **Currency update (2026-08-16) — the mechanism now exists; the path is DORMANT, not absent.**
> Re-grounded against `main` after **REQ-14 was BUILT** (`a84bf12c`, additive runtime override) and
> **REQ-08 was BUILT** (`sources_pipeline.py` / `verify_oracle.py` / `pipeline_provenance`). The
> wired-vs-inert finding below is superseded in ONE respect:
> - **`control`/`regions` are no longer *absent* from the pipeline — they are *dormant*.** REQ-14 added
>   `RenderProfile.control`/`.regions` + `applyDefinitionOverride()` (re-labels the panel/regions from the
>   profile at runtime). But it is an ADDITIVE override: the base render keeps the hardcoded labels, and
>   the override only fires when a domain *supplies a `control`/`regions` delta*. The shipped domains
>   (requirements/capability) supply none → `applyDefinitionOverride` is a **no-op** → the 2-domain
>   scaffold-label diff is **still byte-identical** (re-verified 2026-08-16). Honest status:
>   **wired-but-unfueled (dormant value path)**, not *not-wired*. The mirror is *closeable* (mechanism in
>   place) but not yet *closed* (no domain fuels it). Closing it = give a domain a `control`/`regions`
>   delta and prove it re-labels — the atomic-override half of REQ-14's own FR-3/FR-5.
> - **REQ-08 built** means the ADR/REQ-16/REQ-17 premise ("REQ-08 reconstructs `verify` via longest-prefix
>   ownership") is now grounded in *shipped code*, not a spec — the field-promotion case is stronger.


**Date:** 2026-08-15 · **Type:** live-integration review (read-only; nothing built)
**Scope:** how much of the "new presentation logic" (REQ-10 View Definition + cascade) the navigator
actually renders *through* today, vs what is still hardcoded in the template.
**Method:** render the SAME navigator through **two domains** and diff the output — what flows from the
View Definition changes by domain; what's template-hardcoded stays byte-identical.

## TL;DR

The presentation logic is **half-integrated, cleanly**: `vocabulary`, `chrome`, and `theme` genuinely
flow `resolve() → to_render_profile() → RenderProfile → render`. But **`control` (debug panel),
`regions` (scaffold anatomy), `lenses`, and `glance` are inert** — declared in the definition, never
projected, and rendered identically regardless of which domain's definition is fed in. The scaffold
mode — the very surface whose job is to *reveal the template's anatomy* — is provably **not** sourced
from the definition. That open mirror is exactly what **REQ-14** specs.

## How it was checked (reproducible)

```bash
# requirements domain
PYTHONPATH=src python3 -m startd8.cli navigator build --source requirements \
  --requirements docs/design/requirements-visualization/REQ-10-view-definition-cascade.md \
  --format html --out /tmp/req.html
# capability-index domain
PYTHONPATH=src python3 -m startd8.cli navigator build --source capability-index \
  --format html --out /tmp/cap.html
```

The navigator HTML is **client-side JS-driven** — it embeds a JSON `payload` and builds the DOM in the
browser. So a naïve `grep` of the static HTML reads the **renderer JS template** (identical across
domains), not the data. The real per-domain values live in the embedded `payload.profile` (and the
REQ-11 theme override is a second `:root{}` spliced before `</head>`, distinct from the template's base
`:root`). Read those, not the first match.

## Findings

### ✅ WIRED — flows from the View Definition (differs by domain)

| Section | `req.html` (requirements) | `cap.html` (capability) | Delivered by |
|---------|---------------------------|-------------------------|--------------|
| `theme` → `--accent` | `#1b545f` | `#3a6a94` | REQ-11 |
| `chrome` eyebrow | `"REQ-10"` | `"Capability index"` | REQ-10 / REQ-12 |
| `vocabulary` statuses | Grounded · Awaiting · Excluded · Spec | Delivered · Spec | REQ-10 |

Confirmed via the spliced `:root` override and `payload.profile.eyebrow` — **not** the base `:root` /
JS template (that first-match trap gave a false "theme identical" reading on the first pass).

### ❌ INERT — hardcoded in the template (byte-identical across domains)

| Section | Evidence | Status |
|---------|----------|--------|
| `control` (debug panel: VIEW / OVERLAYS / TEMPLATE ANATOMY toggles) | no `RenderProfile.control` field; `to_render_profile` docstring: *"`lenses`/`control`/`glance`/`regions` are still NOT projected"* | not projected, not consumed |
| `regions` (scaffold anatomy) | **9 `data-scaffold=` labels byte-identical** in `req.html` vs `cap.html` (`diff` empty) | template-hardcoded |
| `lenses` (audience × fluency) | applied *outside* the cascade in `node_lenses.py` | not definition-driven |
| `glance` (status-counts band) | declared in `BASE_NAVIG8R_DEFINITION`, unprojected | inert |

The decisive tell: the debug/scaffold blocks are **identical no matter which domain's definition drives
the render** — so they cannot be coming from the definition. The domain-diff (control/scaffold identical
across two domains) is, in effect, a ready-made byte-identity assertion for REQ-14's guard FRs.

## Grounding (source of truth)

- `src/startd8/navigator/view_definition.py` — `to_render_profile` projects `vocabulary` + `chrome`
  (+ `theme`); its docstring states `lenses`/`control`/`glance`/`regions` are **NOT** projected.
- `src/startd8/navigator/sources_requirements.py:70` — `REQUIREMENTS_PROFILE =
  to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))` (the nav renders through it).
- `src/startd8/wireframe/profile.py` — `RenderProfile` has `theme_tokens` + chrome/vocab fields; **no**
  `control` / `regions` fields yet.
- `src/startd8/wireframe_view/_template.py` — the debug panel + `data-scaffold` anatomy are still literal
  HTML (~28 `data-scaffold` / `#debug` / `body.scaffold` refs).

## Conclusion → next step

`vocabulary` + `chrome` + `theme` are the 3 of the definition's substantive sections that are wired;
`control` + `regions` + `lenses` + `glance` are the 4 still inert. **REQ-14
(`control-region-unification`)** closes the two you keep circling — projects `control` + `regions`,
has the template read them, byte-identical default, atomic override. `lenses` + `glance` remain
unspecced (candidate REQ-15/16). Nothing was built in this review.

*Companion: `REQ-14-control-region-unification.md` (specced, DIDL-named, unbuilt) ·
`ARCHITECTURE_navig8r-presentation-definition-inheritance.md` §7 (steps 4/5 = the inert sections).*
