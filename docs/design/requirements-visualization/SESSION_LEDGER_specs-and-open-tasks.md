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
| **REQ-05 graph/network topology renderer** | 7 single-line FRs; ports CC `graph_projection.py` (Mottainai), new standalone HTML shell; inherits REQ-04 lenses | **specced, not built** |
| **REQ-06 corpus governance** | 9 FRs; reuses `cruft_lint` + loop family (not a parallel mechanism); `navigator govern --dir`; LOOP_CATALOG #6 | **specced, not built** |
| **REQ-07 diff-audience view** | 10 FRs; `diff_nodes`/`NodeDiff` greenfield delta engine + standalone renderer; `navigator diff --before --after` | **specced, not built** |
| **REQ-08 NL-programming pipeline provenance** | 8 FRs; `Stage`-as-Node (extend, don't fork), `Verify:`-as-oracle, extends `provenance.py` | **specced, not built** |

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
