# Session Ledger — Specs & Open Tasks (requirements-visualization + craft)

**Captured:** 2026-08-15 · **Scope:** the requirements-visualization navigator work and the
craft/design-principle promotions from this session. Grouped by *state*, with the still-open items
called out explicitly. Names follow the semantic-naming convention (no integer+content-type alone).

---

## ✅ Implemented (built + landed)

| Artifact | What | State |
|---|---|---|
| **REQ-01 SDK Node Home** | FR-1..FR-15 (added FR-11 structure-only, FR-12 debug panel, FR-13 provenance readout, FR-14 cruft purge, FR-15 scaffold mode); FR-1/4/6/8 gained `Name:`/`Touches:` | built, tests green |
| **REQ-02 N-level tree renderer** | `render_tree.py` ported from ContextCore live pair, XSS-safe, `--renderer tree` | **built, 235 tests** |
| **REQ-03 a11y renderer + corpus index** | `render_a11y.py` + `render_index.py` ported standalone; `build --format a11y` + `navigator index --dir` | **built, +20 tests** (`d416fc38`) |
| **REQ-04 lift lenses to shared transform** | `node_lenses.py` (`apply_node_lenses`/`apply_section_lenses`/`project_nodes`); compose is now a thin wrapper — byte-identity held | **built, 272 tests** (`5cb91c37`) |
| **REQ-05 graph/network-topology renderer** | `graph_projection.py` (ported) + `render_graph.py` standalone SVG; deterministic layout, cycle-safe; `--renderer graph` + `--semantic-only/--full-graph` | **built, 284 tests** (`b39540bd`) — 1st Spec Delivery Loop delivery |
| **REQ-09 shared-lens adoption** | tree + a11y inherit `node_lenses` via opt-in `--role`/`--fluency` (byte-identical default); `apply_node_lenses` wired 2/1 | **built, 302 tests** (`90efe69f`) — 2nd loop delivery; closes HTH dormant D-1 |
| **REQ-06 corpus governance** | `govern.py` + `navigator govern --dir` (5 checks, fail/advisory); consolidates the loop's stage-0 gate (Kagami); LOOP_CATALOG #7 | **built, 320 tests** (`54524784`) — 3rd loop delivery; 1st run flagged the seat-req drift |
| **REQ-07 diff-audience view** | `diff.py` (`diff_nodes → NodeDiff`, order-stable) + `render_diff.py` standalone delta renderer; `navigator diff --before --after` (+`--json`/`--max-detail`/`--role`) | **built, 367 tests** (`ecd96e02`) — 4th loop delivery |
| **REQ-10 View Definition + cascade (keystone)** | `view_definition.py` — serializable `ViewDefinition`/`ResolvedDefinition` (JSON round-trip) + per-leaf keyed-by-id cascade `resolve` + `BASE_NAVIG8R_DEFINITION`; requirements + capability domains re-expressed as `extends: base` + a thin delta, projecting to the existing `RenderProfile` (`to_render_profile`) — renderers unchanged, byte-identical. Keystone FR-5+FR-6: a base theme change propagates atomically to both domains while each keeps its overrides | **built, 400 tests** (`aa42795e`) — 5th Spec Delivery Loop delivery; architecture §7 step 1 |
| **REQ-11 Theme-token activation** (`feature/…-theme-ee3af56c`) | architecture §7 step 2 — the cascade's *visible teeth*. `RenderProfile.theme_tokens` (empty-default guard); `to_render_profile` projects the resolved `theme`; `render_html` emits a non-empty map as an additive `:root` CSS override (server-side splice before `</head>`, template constant untouched). FR-1 reconciled the base theme to the renderer's real `:root` values (byte-identity anchor). Proven end-to-end: capability renders `--accent:#3a6a94` vs requirements `--accent:#1b545f`; app path injects nothing | **built, 413 tests** (`a1a32eee`) — 6th Spec Delivery Loop delivery; byte-identity unedited |
| **REQ-12 Chrome-binding grammar** (`feature/…-chrome-from-22c6a41b`) | architecture §7 step 3 — `resolve_bindings` substitutes `{field}` placeholders; chrome carries a `bindings` map applied at projection ONLY under a per-doc context + only when fields resolve non-empty (else static). REQUIREMENTS_DEFINITION's FR-17/18 masthead rules are now declarative bindings; `requirements_profile_for` is a thin caller (compound page-title stays, NR-2). Existing FR-17/18 tests pass UNEDITED (the byte-identity oracle) | **built, 427 tests** (`d39e038f`) — 7th Spec Delivery Loop delivery |
| **REQ-13 Cross-repo VIEW-SCHEMA import** (`feature/…-externally-authored-d055cadd`) | architecture §7 step 7 (MECHANISM) — `load_definition` (JSON→ViewDefinition) + `resolve_external` (resolve an external def against the shipped base, registry never mutated) + `navigator view-definition --from <file>` (load→resolve→validate→dump). Synthetic 'legal' adopter fixture inherits the base theme + renders its own vocab/chrome. Real 2nd-repo onboarding is out of scope (NR-1 — the outward step this unblocks) | **built, 435 tests** (`fbd18f79`) — 8th Spec Delivery Loop delivery |
| **REQ-08 NL-Programming pipeline + Verify-oracle + provenance** (`feature/…-pipeline-stage-558d6fc7`) | the prose→product compiler made observable. `sources_pipeline.py` — 6 pipeline-stage Nodes via `category`+`attributes` (no `Node` field change), status from `sdk_artifact`-on-disk + a `pipeline` ViewDefinition (statuses keyed by NodeStatus ids). `verify_oracle.py` — promote `Verify:` to an acceptance oracle: classify (single-span extract, closed-set placeholder + multi-command guards) + opt-in `evaluate` (default-inert; `--run-oracle` runs only a read-only-`navigator`-subcommand allow-set, argv-token self-exec guard, `--oracle-timeout`, missing-input→`error`; **pass=rc0, prose assertion = human residue**). `pipeline_provenance()` sibling in `provenance.py` (longest-prefix ownership, not-found + SPEC-stage rows). `navigator verify` cmd + `--source pipeline`. Dogfood: `verify --run-oracle` ran FR-3's own clause → **pass**. Full reflective→CRP(R1, 17 accepted)→triage→loop arc | **built, 276 navigator tests** (`e870232c`) — 9th Spec Delivery Loop delivery; byte-identity + node_field_names goldens UNEDITED |
| **Navigator debugging layer** | debug panel (structOnly / combined / hideScaffold / scaffold), provenance readout, layer legend, PF-1 status chips — all gated on `payload.profile` for byte-identity | built |
| **5 loops + catalog** | pilot / content / origin-audit / cruft / inspect loops + `docs/LOOP_CATALOG.md` | built |
| **Node-schema source (Kagami mirror)** | `sources_node_schema.py` introspects `Node` → Nodes | built |
| **Naming convention** | `naming.py` (`name_forms`), `docs/NAMING_CONVENTION.md`, det-req `Name:` field | built |
| **Universal principle promotion** | Mottainai + Personal Conway → craft canonical; SDK de-forked; `craft/design_principles/README.md` join index (closes Lacuna-1) | committed both repos, on main |
| **Meta-analysis corpus** | Craft Grammar, NL-Programming-System thesis, reflective-audit duality, 4 new reflective skills | authored |

---

## 📝 Planned, NOT explicitly deferred (open specs — no code yet)

| Spec | What | Why open |
|---|---|---|
| **REQ-08 NL-programming pipeline provenance** | 8 FRs; `Stage`-as-Node (extend, don't fork), `Verify:`-as-oracle, extends `provenance.py` | **specced, not built** |
| **REQ-14 Control-schema formalization** (`feature/…-control-panel-cc54b3a8`) | 5 FRs; architecture §7 step 4 — formalize `control` as a keyed group schema (panel + groups {label/hint/order}) reconciled to the renderer's real headers; cascade-able + validated (`validate_definitions`) + inspectable (`view-definition --dump`/`--diff`). §0 reflective insight: the panel is JS-generated with bespoke per-toggle handlers, so renderer consumption is DEFERRED (NR-1) — this step is DATA only (mirrors REQ-10 formalizing theme before REQ-11 activated it), so byte-identical everywhere. Authored via `/reflective-requirements`. **BUILD-READY** (stage-0 ✓, 5/5 named FRs) — prepared for build | **specced, not built** |

> **REQ-14 numbering resolution (2026-08-15):** `REQ-14` = **control-schema formalization** (this row; `REQ-14-control-schema-formalization.md`, landed `fe0c006b`). A concurrent branch `spec/req-14-control-region-unification` (`REQ-14-control-region-unification.md`, commit `8cf38087`) also claimed REQ-14 for a broader *control + region* unification (steps 4+5) — that work should **renumber to REQ-15** to avoid the clash. `REQ-14` is taken.

---

## 🔧 Open follow-ups (mentioned, not started)

- **Reflective-family maturity ladder** (rungs 1–5) — audit family has one; reflective septet doesn't yet.
- **Remaining universal-but-SDK-homed principles** — README pointer table resolves citations, but
  promoting any (if deemed universal) is a clean one-at-a-time follow-on.
- **ContextCore Mottainai pointer** — could re-point to craft (trivial, not done).
- **Lacuna-audit findings** to act on: KM-refactor mid-flight, cross-layer backrefs, dormant sync
  tiers, vertebra symmetry (read-only, not fixed).

---

## ⏸️ Explicitly deferred (NOT open — for completeness)

- REQ-01 lens-lift is captured as **REQ-04** (so REQ-04 is the live path, not deferred).
- Uncommitted craft session docs (`THE_CRAFT_GRAMMAR`, `THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM`,
  `LACUNA_AUDIT_findings`) + modified `KAGAMI` — **left for the user** to place/version, deliberately
  not committed.

---

## Recommended next pickups (priority order)

1. **REQ-03** (a11y renderer) — recovers lost work.
2. **REQ-04** (lift lenses) — unblocks tree/a11y renderers from inheriting the lenses.

Both are specced and ready to build.
