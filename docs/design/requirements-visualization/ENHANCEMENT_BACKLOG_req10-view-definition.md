# Enhancement Backlog — REQ-10 View Definition + Cascade

**Subject:** the shipped REQ-10 keystone (`src/startd8/navigator/view_definition.py` + the two derived
profiles). **Generated:** 2026-08-15 via CEP (Cumulative Enhancement Protocol), HTH stage-7 phase 4.
**Tree:** local `main` @ `7f217215` (REQ-10 `aa42795e` + phase-1 harden `7f217215`).

> Selection is **human-owned** — pick from S/M/L below. Only the XS integrity-guard test was
> auto-executed (annotated `→ landed`). Agents read the spec/code; **re-ground each `fix` against the
> tree before building** (a claimed gap may already be closed).

## Provenance / prior-art manifest (Phase 0)

Greps run (2026-08-15):
- `rg -l -i "ENHANCEMENT_BACKLOG|EC-[0-9]|AC-[0-9]" docs/design/requirements-visualization` → found
  `ENHANCEMENT_BACKLOG_navigator-viz.md`, `ENHANCEMENT_BACKLOG_req07-diff.md` (per-REQ backlogs; **no
  REQ-10/view-definition backlog** — this file is the first).
- `rg -n -i "view.definition|REQ-10|cascade|inherit" ENHANCEMENT_BACKLOG_navigator-viz.md` → **no
  overlap** (that backlog covers REQ-02/04/07/09 renderers; nothing on the definition system).
- Concurrent prior art: `docs/design/requirements-visualization/_spike/view_definition_spike.py` (commit
  `12ea9800`) — a **throwaway parallel prototype** by another agent that independently converged on the
  same 3-part design (serializable def + `deep_merge` cascade + `to_render_profile`). Its extra choices
  (severity-sorted status order; **shared statuses lifted into the base**) are **byte-identity-breaking**
  (they reorder the requirements statuses) — folded below as deliberate M-tier future work, not now.

**CEP run shape:** 3 independent seeders (18 ideas) → 1 cumulate round (orchestrator CROSS moves) →
triage. **Triage-surviving off-seed count (R-4 kill metric): 4 crossovers** (EC-1, EC-3, EC-2, EC-8) —
CEP earned its keep (>0). **Byte-identity is a hard gate** on every row; rows that reorder statuses or
lift shared statuses into the base are flagged `byte-breaking`.

## Ranked backlog

| ID | Title | Val×Eff | Type | Byte-safe | Lineage |
|----|-------|---------|------|-----------|---------|
| **EC-3** | **Definition-integrity guard** — registry-parametrized test: resolves + real-definition JSON round-trip + `profile == projection` drift guard (auto-covers a future domain) | **XS** | fix | ✅ | CROSS(A4+B3+A6) — **→ landed this run** |
| **EC-1** | **`navigator view-definition` CLI** — `--list` the inheritance graph (base→domains) **and** `--dump NAME` / `--emit` a resolved definition or the whole registry as JSON via the existing `to_dict`. One command serves operator-introspection **and** the cross-repo export seam (NR-4 / architecture §7 step 7 enabler) | **S** | wire-existing | ✅ | CROSS(A1+A2+C1) |
| **EC-2** | **Fold `NODE_SCHEMA_PROFILE` into a real 3rd definition** (`NODE_SCHEMA_DEFINITION extends base`) — de-dups the `sources_node_schema.py:25-45` literal, widens the cross-domain proof to 3 real domains, auto-covered by EC-3. (Keep the spike's `legal` domain as the documented cross-repo adopter demo) | **S** | wire-existing | ✅ (insertion order matches the literal) | CROSS(A3+C3) |
| **EC-4** | **`definition_diff(domain, base)` helper** — surface exactly what a domain overrides vs the base (wires the existing `_deep_merge` logic); feeds governance + the HOWTO | **S** | wire-existing | ✅ | B4 |
| **EC-6** | **REQ-06 `govern.py` hook for definitions** — govern the presentation definitions (cycle / dangling-extends / unknown-section) alongside the requirement docs, reusing `resolve`'s guards | **M** | wire-existing | ✅ | B5 (VARY of EC-3) |
| **EC-7** | **HOWTO: author a new domain definition** — the base you inherit → your delta (vocab+chrome) → round-trip → resolve → register → lint. Codifies the pattern the 2 examples embed | **M** | docs | ✅ | B6 |
| **EC-8** | **Theme activation = the next REQ (architecture §7 step 2)** — make `theme` tokens actually reach rendered HTML (CSS custom properties) so a base theme change is *visible*, not just in the resolved dict. Seed its spec with a **consumption/dormancy audit** (which of theme/lenses/control/glance/regions renders vs is dormant). **Author via `/reflective-requirements`, not inline** (byte-breaking; NR-3) | **L** | author-spec | ❌ byte-breaking | CROSS(C2+C4+A5+C6) — highest-value next step |
| **EC-9** | **`NODE-VIEW-SCHEMA` cross-repo contract (architecture §7 step 7)** — emit content (NODE-SCHEMA-JSON) + presentation (view definition) together so legal/benchmark/dev-os author their own domain deltas. Author-spec; EC-1's `--emit` is its first brick | **M** | author-spec | n/a | C5 |

### Wildcard (single-seeder, no descendants — seen separately so variations can't bury it)

| ID | Title | Val×Eff | Note |
|----|-------|---------|------|
| **EC-5** | **Loud `from_dict` on missing `"name"`** — currently a bare `KeyError` (`view_definition.py:95`); a clear `ValueError` is ~3 lines | XS / fix | **Phase-1 review DECLINED this** as NR-4 (no external consumer yet). Revisit *with* EC-1 — the export CLI makes `from_dict`/`to_dict` a real consumer, at which point the strict error earns its place. |

## Byte-breaking future ideas (deliberate, need golden updates — not now)

- **Severity-derived status order** (from the spike): order statuses by `(severity, id)` instead of
  authoring order — deterministic, but reorders the requirements statuses → M, needs golden updates.
- **Shared statuses in the base** (from the spike): lift the common `excluded`/`unknown` (and the shared
  green `#3d7a57`) into `BASE_NAVIG8R_DEFINITION.vocabulary.statuses` so the *status* vocabulary also
  cascades by id. Elegant, but reorders → M, needs golden updates. Pairs naturally with EC-2.

## Honesty note

Seeders read the spec + code and cited `file:line`, but **verify before building** — re-ground each
`fix` against the tree (the CL-29 gate). EC-3 was code-grounded (it exercises the phase-1 guards +
adds real round-trip coverage the synthetic test lacked) and landed this run.
