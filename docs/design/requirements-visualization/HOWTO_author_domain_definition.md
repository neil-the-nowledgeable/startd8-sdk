# HOWTO: author a new domain View Definition

**For:** an SDK contributor or cross-repo adopter (legal · benchmark · dev-os) adding a **new domain**
to the navig8r presentation system. **Grounds:** REQ-10 (keystone) · REQ-11 (theme) · REQ-12 (chrome
bindings) · REQ-cross-surface-view-definition (`node_state` / `surface_links`) · the shipped
examples in `src/startd8/navigator/view_definition.py`.

A domain's *presentation* — its status vocabulary, masthead chrome, theme, and content-derived chrome
— is a **serializable `ViewDefinition`** that `extends` a shared base via a per-leaf cascade. You author
a **thin delta**; the base supplies the rest; the resolver merges them; a projection turns the result
into the `RenderProfile` the renderers already consume. You do **not** touch a renderer.

## The mental model

```
BASE_NAVIG8R_DEFINITION  (theme · lenses · control · glance · regions
                          · node_state · surface_links — shared defaults)
        ▲ extends
YOUR_DEFINITION          (your delta: vocabulary + chrome [+ optional theme override + chrome bindings])
        │ resolve(def, registry)  →  deep-merge per leaf, keyed collections by id
        ▼
ResolvedDefinition  →  to_render_profile(resolved[, context])  →  RenderProfile  →  renderer (unchanged)
```

## Steps

### 1. Understand what the base gives you (inherit, don't re-declare)
The base owns the domain-neutral defaults: `theme` (the real `:root` tokens `ink`/`paper`/`accent`),
`lenses` (role/fluency), `control` (panel structure), `glance` (status roll-up), `regions` (the
layer skeleton), plus the cross-surface sections `node_state` (canonical health + per-surface
presentation) and `surface_links` (declared drill/rollup pointers). Your domain inherits all of
these — **do not copy them into your delta.** A resolved dump of a thin delta will still show
`surface_links.drill.via == "fullview"`; that is inheritance, not something you authored. Drill and
rollup are **declared-not-wired** until a cockpit adopter reads them — `view-definition --validate`
passing does not mean tiles are linked.

### 2. Author your delta
Add a `ViewDefinition(name="<your-domain>", extends="base", …)` with only what differs:
- **`vocabulary`** — your `gap_noun` + a **keyed** `statuses` map (keyed by status id, never a
  positional list, so overrides stay atomic). Example (`CAPABILITY_DEFINITION`):
  ```python
  vocabulary={"gap_noun": "capability", "statuses": {
      "built": {"label": "Built", "color": "#3d7a57", "meaning": "code leaf present", "severity": 0},
      ...
  }}
  ```
  **Equal-keys opt-in (trap):** `to_render_profile` reads statuses from shared `node_state`
  presentation (navig8r leaves) **only when** your `vocabulary.statuses` key set **exactly equals**
  the canonical navig8r map (`grounded` / `spec` / `awaiting` / `excluded` / `unknown`). A proper
  subset (e.g. only `{spec, awaiting}`) is **not** an opt-in — you keep your own labels and colors.
  Reusing those five ids on purpose **drops** your authored label/color/meaning in favor of the
  shared taxonomy. Keep a local vocabulary if you do not want that.
- **`chrome`** — your masthead/apex strings (`title`, `eyebrow`, `section_lead`, `headline`,
  `summary_meta`, `why`, `do`).
- **`theme`** *(optional)* — override only the tokens you change; the rest inherit
  (e.g. `CAPABILITY_DEFINITION` sets `theme={"accent": "#3a6a94"}` and keeps the base ink/paper).
  A theme override renders as an additive `:root` CSS override (REQ-11).
- **`chrome.bindings`** *(optional)* — derive chrome from a per-doc content context with single-field
  `{field}` placeholders (REQ-12). Fields must be in `BINDING_CONTEXT_FIELDS`
  (`key`/`title`/`semantic_name`/`initiative`). Example (`REQUIREMENTS_DEFINITION`):
  ```python
  "bindings": {"eyebrow": "{key}", "headline": "{title}", "section_lead": "What {key} defines"}
  ```
  A binding applies only when a context is passed **and** every referenced field resolves non-empty;
  otherwise the static chrome value stands.

### 3. Register it
Add your definition to `DEFINITION_REGISTRY` in `view_definition.py`:
```python
DEFINITION_REGISTRY = {..., "<your-domain>": YOUR_DEFINITION}
```

### 4. Derive the RenderProfile in your source module
In your `sources_<domain>.py`, project the resolved definition:
```python
YOUR_PROFILE = to_render_profile(resolve(YOUR_DEFINITION, DEFINITION_REGISTRY))
# per-doc chrome bindings: pass a context (e.g. requirement_identity(path))
prof = to_render_profile(resolve(YOUR_DEFINITION, DEFINITION_REGISTRY), context=idy)
```

### 5. Inspect + validate
```bash
startd8 navigator view-definition --name <your-domain>          # the resolved JSON
startd8 navigator view-definition --name <your-domain> --diff   # only what YOU override vs base
startd8 navigator view-definition --validate                     # govern the whole registry (EC-6 + EC-CS-1)
# --validate also walks resolved surface_links.via (must name a regions.bindings key or `serves`)
# and cockpit attention (ok/review/blocked/backlog). Passing does not mean drill/rollup are live.
```

### 6. It's covered by the guards
Adding a definition to the registry is automatically exercised by the **definition-integrity guard**
(`test_view_definition.py`): every registry entry must resolve, JSON round-trip, and (if it has a
module-level `*_PROFILE`) match its projection. Add your `"<your-domain>": YOUR_PROFILE` row to
`_PROFILE_BY_DOMAIN` there so the drift guard covers your projection too.

## Rules of thumb

- **Thin delta only.** If you're copying a base value verbatim, delete it — inherit instead.
- **Keyed maps, never positional lists**, for anything overridable (statuses).
- **Byte-identity.** A domain with no theme override + no bindings renders exactly as before; the app
  path (no profile) is never themed. Prove it: `test_no_profile_is_byte_identical` must stay green.
- **Don't touch the renderer.** Everything routes through `to_render_profile` → `RenderProfile`.
- **Later steps** (control schema, region bindings, shared shell, cross-repo `VIEW-SCHEMA` export) are
  separate REQs; today a domain customizes vocabulary + chrome + theme + chrome-bindings.

## Reference
`src/startd8/navigator/view_definition.py` — `ViewDefinition`, `resolve`, `to_render_profile`,
`resolve_bindings`, `validate_definitions`, and the three real examples
(`REQUIREMENTS_DEFINITION` · `CAPABILITY_DEFINITION` · `NODE_SCHEMA_DEFINITION`).
