# PLAN-01 — SDK Node Home — Implementation Plan

**Pairs with:** `REQ-01-sdk-node-home.md` · **Version:** 0.4 · **Date:** 2026-08-14  
**Status:** Phase 1 **implemented** (F-1…F-5 ✅; F-CC-1 deferred)

## Discoveries (locked into REQ §0)

| Assumption (REQ v0.1) | Planning discovery | Impact on plan |
|---|---|---|
| Invent Node | CC `navigator/models.py` is the lived model | F-1 = **copy port** into `startd8.navigator`; shared package deferred |
| Redesign WireframeItem | Flatten loss at `nodes_to_wireframe_plan` | F-2 = additive optional fields + compose emit |
| Edit GAP_STATUSES for Nodes | App gap vocab ≠ Node vocab | F-2 uses `route_state` / `is_gap`, not GAP_STATUSES overload |
| Greenfield requirements source | extract.py parses Lives; CC source is huge | F-3 = **minimal** FR→Node; **vendor_thin** default |
| Projection stays in CC | Adapter already works in CC render.py | F-2 = move `nodes_to_wireframe_plan` into SDK (FR-10) |
| `subcommand` kinds for libs | Closed CLI vocabulary only | Contract Projection CLI-only; file-path Touches |
| Reuse `startd8 nav` | Existing app top-nav | F-4 group name = `navigator` |
| Port `default_confidence` from CC | **Phantom** — CC has `derive_status` only | F-1: ★ SDK-owned `default_confidence` (FR-4 rubric) |

## Design (post CRP R1)

| FR | File · symbol (to-be-created marked ★) | Change |
|----|----------------------------------------|--------|
| FR-1 | ★ `src/startd8/navigator/__init__.py`, ★ `models.py` | Copy-port Node / NodeEvidence / derive_status from CC; field-compat golden (no `import contextcore`) |
| FR-4 | ★ `models.py` `default_confidence` | ★ SDK-owned helper (0.9/0.6/0.4); **not** a CC port |
| FR-10 | ★ `src/startd8/navigator/project.py` | Port `nodes_to_wireframe_plan`; call `wireframe_view.render_to_file` |
| FR-2, FR-3, FR-8 | `wireframe/plan.py` WireframeItem · `wireframe_view/compose.py` · `profile.py` | Optional grounding fields; `_item_view` **omit-when-empty**; `need_items` excludes `route_state` ∈ `{owned_elsewhere, declared_unimplemented}`; keep `GAP_STATUSES` app-only |
| FR-5 | ★ `sources_capability.py` | Load `startd8.sdk.capabilities.yaml` → Nodes |
| FR-6 | ★ `sources_requirements.py` + ★ thin lives/`fr_health` helper | vendor_thin default; optional `DET_REQ_KIT` subprocess; no sibling import |
| FR-7 | ★ `cli_navigator.py` + `cli.py` add_typer | `navigator build` / `ground` beside existing `nav` |
| FR-9 | ★ `ground.py` + CLI `ground` | `$0` key→count JSON |

**Dependency direction:** startd8 must **not** import ContextCore. CC may later switch to SDK Node (`F-CC-1` deferred).

**Reuse (Mottainai):** one HTML backend; one grammar; det-req docs as the requirements store.

## Iterations

| id | FRs | target | state |
|----|-----|--------|-------|
| F-1 | FR-1, FR-4 | ★ `navigator/models.py` + field-compat golden + `default_confidence` tests | ✅ done |
| F-2 | FR-2, FR-3, FR-8, FR-10 | WireframeItem + omit-when-empty compose + need_items honest-skip + ★ `project.py` + determinism green | ✅ done |
| F-3 | FR-5, FR-6 | ★ sources (capability + minimal requirements); tests without kit on `sys.path` | ✅ done |
| F-4 | FR-7 | ★ `cli_navigator.py` wired in `cli.py`; dual help smoke (`navigator` + `nav`) | ✅ done |
| F-5 | FR-9 | ★ `ground.py` + CLI | ✅ done |
| F-CC-1 | — | CC thin shim / twin retirement — **deferred** (out of Phase 1) | deferred |

Dependencies: F-1 → F-2 → F-3 → F-4; F-5 after F-1 (parallel OK with F-3). F-CC-1 non-blocking. Acyclic.

### F-2 Notes (CRP R1)

- Compose `_item_view` omits optional Node fields when unset/empty.
- Extend `need_items` so items with honest-skip `route_state` are excluded even if status mapping would flag them; do not grow `GAP_STATUSES`.

### F-3 Notes (CRP R1)

- Default coupling: `vendor_thin`. Override: env `DET_REQ_KIT` → optional subprocess. Unit tests must pass with kit absent from `PYTHONPATH`.

## Verify (whole change)

- `pytest tests/unit/wireframe/ tests/unit/navigator/` green (incl. without det-req-kit on path).
- `startd8 navigator build --source capability-index --format json` emits live capability_id keys.
- Fixture det-req with Lives → HTML/JSON carries typed evidence; done-claim without Lives ≠ grounded.
- Smoke: `startd8 navigator --help` lists build/ground; `startd8 nav --help` still app top-nav.
- `test_no_profile_is_byte_identical` + determinism tests unmodified and green; classic compose JSON keyset unchanged.
- No `import contextcore` from startd8.
- Field-compat golden green; F-CC-1 remains deferred.

## Reference audit (phantoms)

| Symbol in plan | Exists today? | Disposition |
|----------------|---------------|-------------|
| `WireframeItem` / `compose` / `GAP_STATUSES` / `RenderProfile` | yes | extend |
| `cli.py` `nav` typer | yes | do not collide |
| `startd8.sdk.capabilities.yaml` v1.27.0 | yes (68 caps, `wont` on all) | default source |
| `startd8.navigator.*` | **no** | ★ create in F-1..F-5 |
| CC `Node` / `nodes_to_wireframe_plan` | yes (CC repo) | provenance for port; not a runtime dep |
| CC `default_confidence` | **no** | do not claim port — SDK-owned (R1-S1) |

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.4 — Post CRP R1 triage (all 6 S + focus locks merged). Ready for implementation.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Remove phantom `default_confidence` CC port | CRP R1 | Design table + F-1; SDK-owned helper | 2026-08-14 |
| R1-S2 | Explicit need_items honest-skip filter in F-2 | CRP R1 | F-2 Notes | 2026-08-14 |
| R1-S3 | F-3 default vendor_thin | CRP R1 | F-3 Notes + Design FR-6 | 2026-08-14 |
| R1-S4 | Compose omit-when-empty | CRP R1 | F-2 Notes + Design | 2026-08-14 |
| R1-S5 | Field-compat golden + F-CC-1 deferred row | CRP R1 | Iterations table | 2026-08-14 |
| R1-S6 | Dual nav/navigator help smoke | CRP R1 | Verify + F-4 | 2026-08-14 |
| Focus 1–4 | Port-now; vendor_thin; additive fields; CC stub | CRP R1 | Discoveries + F-CC-1 | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) |  |  | All R1 S-suggestions accepted | 2026-08-14 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2 — 2026-08-14 UTC

- **Reviewer**: composer-2
- **Date**: 2026-08-14 16:10:00 UTC
- **Scope**: Dual-doc CRP R1 — focus asks (port/shared, extract coupling, WireframeItem shape, CC follow-on) + plan architecture/interfaces/validation gaps; grounded against CC `navigator/models.py`+`render.py`, startd8 `wireframe/plan.py`, `wireframe_view/compose.py`, `wireframe/profile.py`, `cli.py`, det-req-kit `extract.py`
- **Orchestrator note:** Round retained for memory; dispositions in Appendix A (2026-08-14). See REQ Appendix C for full F-table + focus answers.

##### Focus-file asks (summary)

1. Port-now; shared package deferred.
2. vendor_thin default; optional DET_REQ_KIT subprocess.
3. Additive WireframeItem fields; omit-when-empty compose.
4. CC import acceptable deferred; name F-CC-1 only.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Remove or reword Design-table claim that F-1 ports `default_confidence` from CC; mark ★ SDK-owned helper implementing FR-4 rubric instead. | CC `navigator/models.py` exports `Node` / `NodeEvidence` / `StatusFacet` / `derive_status` only — no `default_confidence`. | Design table row FR-1/FR-4; F-1 target notes | Grep CC models for symbol absence; unit test FR-4 rubric in SDK `navigator/models.py` |
| R1-S2 | Interfaces | high | In F-2 Notes, specify the honest-skip compose change: extend `need_items` so items with `route_state` in `{owned_elsewhere, declared_unimplemented}` are excluded; keep `GAP_STATUSES` app-only. | Live `compose.py` filters solely via `it.status in GAP_STATUSES`. | Iterations F-2 Notes | Unit: honest-skip absent from need_items; app plan unchanged |
| R1-S3 | Risks | high | Resolve F-3 extract coupling to vendor_thin; optional DET_REQ_KIT subprocess. | Sibling import breaks PyPI/CI. | Iterations F-3 | pytest without kit on path |
| R1-S4 | Data | medium | Document F-2 compose emit rule: optional fields only when set. | Always-present keys break FR-8. | F-2 Notes | Classic compose keyset unchanged |
| R1-S5 | Validation | medium | Add F-1 field-compat golden + deferred F-CC-1. | Twin drift fence + named follow-on. | Iterations table | Golden + F-CC-1 deferred |
| R1-S6 | Ops | low | Dual help smoke for `navigator` + `nav`. | Locks NR-6. | Verify; F-4 | Both helps correct |

## Requirements Coverage Matrix — R1

Analysis only (not triage). Coverage values: Covered / Partial / Gap. *(Post-triage: Partials addressed in v0.4 Design/Iterations.)*

| Requirement | Plan section / task | Coverage | Notes / gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Node model | Design FR-1; F-1 | Covered (post R1) | Field-compat golden named |
| FR-2 Typed grounding in compose | Design FR-2; F-2 | Covered (post R1) | omit-when-empty explicit |
| FR-3 Derived status + honest-skip | Design FR-2/FR-3; F-2 | Covered (post R1) | need_items filter in F-2 Notes |
| FR-4 Default confidence | Design FR-4; F-1 | Covered (post R1) | SDK-owned; phantom removed |
| FR-5 Capability-index source | Design FR-5; F-3 | Covered | |
| FR-6 Minimal det-req source | Design FR-6; F-3 | Covered (post R1) | vendor_thin locked |
| FR-7 Navigator CLI `build` | Design FR-7; F-4 | Covered | + dual help smoke |
| FR-8 App-path byte identity | Design FR-2/FR-8; F-2 | Covered (post R1) | compose + HTML |
| FR-9 Grounding pass | Design FR-9; F-5 | Covered | |
| FR-10 Projection in SDK | Design FR-10; F-2 | Covered | |
| NR-1..NR-8 | Discoveries; F-CC-1 | Covered | |
| O-1..O-3 | Verify | Covered (post R1) | |
