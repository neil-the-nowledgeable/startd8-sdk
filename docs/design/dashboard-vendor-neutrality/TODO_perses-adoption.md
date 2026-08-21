# TODO — Adopt Perses as the vendor-neutral dashboard IR

**Source:** [ADR_adopt-perses-neutral-dashboard-ir.md](ADR_adopt-perses-neutral-dashboard-ir.md) (Status: Accepted — bounded adoption) ·
**Requested by:** Dash0 pilot team · **Created:** 2026-08-20

> Assign each item by filling the **Owner** column. Do the **de-risk gate (T0)** before committing anyone to
> the decoupling work (T2+) — its result can bound or block the whole effort. Repo/GitHub work respects the
> branch-first + return-to-main workflow.

Legend — Status: ☐ todo · ◐ in progress · ☑ done · ⊘ blocked

---

## Phase 0 — De-risk (do first, read-only, no commitment)

| # | Task | Scope / grounding | Depends on | Owner | Status |
|---|------|-------------------|------------|-------|--------|
| T0 | **Perses coverage map** — does Perses' CUE schema cover the construct vocab `dashboard_creator/v2` actually emits? Inventory the model's panel/query/variable/layout kinds; map each against the Perses schema; record gaps. | [`T0_perses-coverage-matrix.md`](T0_perses-coverage-matrix.md); audited against Perses v0.54.0 + bundled plugin versions | — | Codex | ☑ |
| T0.1 | **Decision checkpoint** — if T0 finds a gap, bound/revise the ADR before proceeding; if clean, mark ADR **Accepted**. | **Accepted bounded go** by authorized decider proxy on 2026-08-20. Perses lowering must reject nested tab/section composition, conditions, auto-grid, section variables, dashboard-list, and arbitrary plugin payloads. Flat tabs exist in the pinned schema but are not yet in the neutral T1 vocabulary. | T0 | Decider proxy | ☑ |

## Phase 1 — Neutral model extraction (behavior-preserving)

| # | Task | Scope / grounding | Depends on | Owner | Status |
|---|------|-------------------|------------|-------|--------|
| T1 | **Freeze the neutral construct vocabulary** — panel (viz-kind + query + position), variable, datasource-ref, section. Name the portable subset as the model core, separate from Grafana naming (`viz_config` kind names, `AutoGridLayout`). | `dashboard_creator/neutral.py`; boundary recorded in the T0 matrix | T0.1 | Codex | ☑ |
| T2 | **Reframe `to_v2()` as a Grafana *lowering*** off the neutral core — output must stay **byte-identical**. | `dashboard_creator/v2/lowering.py`; domain-observability producer migrated first; Grafana-only producers deliberately remain on legacy v2 models | T1 | Codex | ☑ |
| T2.1 | **Golden test guarding Grafana byte-identity** — existing fixtures → `to_v2()` unchanged. | Exhaustive seven-file checksum + canonical-serializer guard in `test_neutral_core.py`; migrated producer also compared to legacy output | T1 (guard precedes the rest of T2) | Codex | ☑ |

## Phase 2 — Perses emitter + validation oracle

| # | Task | Scope / grounding | Depends on | Owner | Status |
|---|------|-------------------|------------|-------|--------|
| T3 | **Implement `to_perses()`** as the primary emitter from the neutral model. | `dashboard_creator/perses/emitter.py`; deterministic canonical JSON; partial mappings fail loudly | T1 | Codex | ☑ |
| T4 | **Wire Perses CUE schema as the validation oracle** — validate emitted dashboard at generation time (the "verify that can't silently die" gate for the BI waist). | `dashboard_creator/perses/validate.py`; exact upstream CUE sources and versions pinned in `schema/SCHEMA-PINS.json`; wheel inclusion verified; dedicated CI job installs CUE v0.16.1 and runs real accept/reject tests | T3 | Codex | ☑ |
| T5 | **Golden-test both lowerings** — one shared neutral fixture → {Grafana v2, Perses}, both valid. | `test_perses_emitter.py` + `portable_shared.{grafana,perses}.golden.json`; real CUE accept/reject tests | T2.1, T4 | Codex | ☑ |
| T5.1 | **Wire the first live Perses generation surface.** Keep Grafana as the default; `dashboard create --target perses` consumes `observability.yaml` through the neutral domain producer, validates with CUE, and writes canonical JSON. | `REQ-perses-live-generation.md`; `cli_dashboard.py`; `perses/live_generation.py` | T5 | Codex | ☑ |
| T5.2 | **Commit a live-generated pilot artifact and regeneration gate.** The real CLI output must be byte-stable and CUE-valid in the dedicated CI job. | `pilot/dash0-pilot.observability.yaml`; `pilot/obs-domain-dash0-pilot-v2.perses.json`; `test_perses_live_generation.py` | T5.1 | Codex | ☑ |

## Phase 3 — ContextCore CRD emission (cross-repo)

| # | Task | Scope / grounding | Depends on | Owner | Status |
|---|------|-------------------|------------|-------|--------|
| T6 | **Add Perses Dashboard CRD as a `DerivationRule` output-kind** in ContextCore (CRD→CRD projection). | ContextCore `DerivationRule`; `EXPORT_ENRICHMENT_PLAN.md:40` | T3 | | ☐ |
| T6.1 | **Track T6 in ContextCore's own CLOSURE-LEDGER** (cross-repo work lands there, cite from here — don't duplicate rows). | `ContextCore/CLOSURE-LEDGER.md` | T6 | | ☐ |

## Phase 4 — Dash0 pilot validation

| # | Task | Scope / grounding | Depends on | Owner | Status |
|---|------|-------------------|------------|-------|--------|
| T7 | **Validate a generated Perses dashboard against Dash0** (the requesting pilot's consumer) end-to-end. | SDK handoff is ready in `READY_FOR_DASH0_TEAM.md`; pilot access still requires a Dash0 target, authorized import path, and human operator. No credential values belong here. | T5.2 | Pilot owner | ☐ |
| T8 | **Log this effort as an open loop in the SDK CLOSURE-LEDGER** with honest maturity. | `CLOSURE-LEDGER.md` CL-8 is L3: live generation + offline oracle proven, first external consumer still pending | — | Codex | ☑ |

## Phase 5 — Perses upstream contribution lane (parallel; does not block the bounded pilot)

| # | Task | Scope / grounding | Depends on | Owner | Status |
|---|------|-------------------|------------|-------|--------|
| T9 | **Inventory each portability gap against Perses upstream** — find existing issues/RFCs for nested layout composition, conditional rendering, responsive auto-layout, scoped variables, dashboard navigation, and the underconstrained static-variable `defaultValue` CUE definition; open a minimal generic issue only where none exists. | Read-only inventory below. Existing: scoped variables #2709; dashboard grouping #4067; dashboard links #1642/#4176. No exact issue found for the other gaps. Opening issues remains an explicit GitHub write. Flat tabs themselves are not a schema gap. | T0.1 | Codex | ◐ |
| T9.1 | **Rank contribution candidates by ecosystem value and tractability** — prefer a generally useful capability with a clear schema/runtime contract; record why other gaps wait. | Upstream maintainer direction + the Dash0 pilot's observed need | T9, T7 | | ☐ |
| T9.2 | **Contribute upstream without a private dialect** — implement the selected Perses change with upstream tests/docs. Keep startd8 fail-loud until the capability ships in a pinned Perses release and passes local CUE + Dash0 gates. | Perses contribution guide and maintainer-approved design | T9.1 | | ☐ |

---

## Non-goals (from ADR — do NOT scope in)

- Vendor-neutral **viewing** (that's emit-both, or the Perses UI).
- Arbitrary Grafana-plugin panels in the neutral IR (portable subset only).
- Deprecating Grafana output — it stays as a retained secondary lowering.
- Maintaining a private Perses fork or startd8-only schema dialect; contributions target upstream Perses.

## T9 upstream inventory (read-only, 2026-08-20)

| Gap | Existing upstream record | Assessment / next contribution move |
|---|---|---|
| Panel-group/section-scoped variables | [perses/perses#2709](https://github.com/perses/perses/issues/2709) (open) | Exact conceptual match. Engage on the existing issue; do not open a duplicate. It spans API and UI, so it is not the first tractable contribution. |
| Navigation among related dashboards | [#1642](https://github.com/perses/perses/issues/1642) (closed: dashboard links), [#4176](https://github.com/perses/perses/issues/4176) (open: preserve time range), and [#4067](https://github.com/perses/perses/issues/4067) (open: tabbed dashboard grouping) | The base capability exists and follow-ons are active. Contribute to the existing records if the pilot exposes a concrete navigation need. |
| Nested tab → section/row → grid composition | No exact open issue found; #4067 is related UX but groups whole dashboards | First seek maintainer direction on whether composition belongs in `perses/spec` or should remain dashboard grouping. Avoid proposing a Grafana-shaped nesting model. |
| Conditional panel/layout visibility | No exact open issue found | Needs a generic predicate/context contract plus runtime behavior; propose only after the pilot demonstrates a portable use case. |
| Responsive auto-layout | No exact open issue found | Broad schema, editor, and renderer change. Defer behind narrower correctness gaps. |
| Static-list `defaultValue` CUE validation | No exact issue found in `perses/perses` or `perses/spec`; pinned CUE declares `#DefaultValue: _`, while the Go API accepts only string or string array | **Recommended first upstream contribution:** constrain the CUE union and add matching JSON/YAML/CUE tests. It is narrow, ecosystem-wide, release-verifiable, and would let startd8 safely lower explicit defaults. |

Provisional contribution order: (1) `defaultValue` schema correctness; (2) collaborate on #2709 if the pilot
needs scoped variables; (3) design conditional visibility from a concrete cross-tool use case; (4) defer nested
composition and responsive auto-layout until maintainers confirm the intended abstraction. T9 remains in progress
because creating or commenting on upstream issues is a GitHub write and was not performed by this implementation pass.
