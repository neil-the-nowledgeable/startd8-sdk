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
| **REQ-11 Theme-token activation** (`feature/…-theme-ece95538`) | 6 FRs; architecture §7 step 2 ON the REQ-10 keystone — project resolved `theme` into `RenderProfile.theme_tokens` (empty-default guard) → renderer emits an additive `:root` CSS custom-property override → a base/domain theme change becomes *visible*. Reconciles base theme to the real `_template.py` `:root` values (byte-identity for app path + non-overriding domains); capability's `accent` override is the visible-teeth proof. Authored via `/reflective-requirements` (§0 caught the base-theme placeholder mismatch). **BUILD-READY** (stage-0 gate ✓, 6/6 named FRs) — next Spec Delivery Loop delivery | **specced, not built** |

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
