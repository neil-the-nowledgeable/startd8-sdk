# Next Steps — Dash0 Perses Pilot

**Audience:** Dash0 pilot team · **From:** startd8-sdk + ContextCore ·
**Created:** 2026-08-20 · **Source of truth:** [ADR](ADR_adopt-perses-neutral-dashboard-ir.md) ·
[coverage matrix](T0_perses-coverage-matrix.md) · [TODO](TODO_perses-adoption.md)

> ## 🟡 SDK READY — Dash0 team may begin its gate
>
> The startd8-owned gates are green: the live CLI, pinned CUE oracle, and canonical pilot artifact
> are ready. End-to-end Dash0 validation is still outstanding (tracked as **CL-8, maturity L3** in
> `CLOSURE-LEDGER.md`). The Dash0 team should now follow `READY_FOR_DASH0_TEAM.md` to close G3 and run
> the live import; no Dash0 credential or mutation was performed by startd8.

---

## 1. What's ready today

- A **vendor-neutral dashboard model** (`dashboard_creator/neutral.py`) that lowers to **both**
  Grafana v2 and **Perses v0.54.0** from one source (`emit_perses_dashboard(...)`).
- Deterministic, canonical JSON output (`perses_json()`), guarded by golden tests.
- An **offline CUE validation oracle** pinned to Perses v0.54.0 — emission optionally self-validates
  and **fails loud** rather than shipping an unconformant dashboard.
- Emit-both: the retained Grafana lowering stays byte-identical, so nothing regresses for Grafana.

## 2. What you'll actually get (the portable subset)

The neutral model covers the portable subset of *generated* dashboards — not arbitrary hand-authored ones:

| Capability | Supported today |
|---|---|
| Panels | `markdown`, `time_series` (PromQL), `logs` (LogQL) |
| Queries | PromQL (range) + LogQL; `datasource` by name or `$var` |
| Variables | Static allow-list (`StaticListVariable`) |
| Layout | Titled sections → Perses `Grid` layout, explicit x/y/w/h placement, collapse state |
| Presentation | Absolute thresholds; a reviewed unit set (count/short/percent/bytes/seconds/ms/usd/…) |
| Metadata | name, project, tags, duration, description |

## 3. What fails loud (known boundaries — expect a typed error, not a silent drop)

By design these raise `PersesCapabilityError` / model-validation errors rather than emitting
something the CUE oracle can't back:

- Tabs, nested tab→section→grid composition, conditional panel/layout visibility, auto-grid layout.
- Section-scoped variables, dashboard-list / dashboard-navigation panels.
- Arbitrary Grafana-plugin payloads (portable subset only).
- **Instant** (non-range) queries; query units with no reviewed Perses mapping.
- Static variables carrying an explicit `current`/default (Perses v0.54 CUE leaves `defaultValue`
  underconstrained — held back until upstream resolves it; see TODO T9).

If your pilot needs one of these, that's a **finding to report** (§7), not a blocker to work around.

## 4. Readiness gates — ALL must be green before the live import

- [x] **G1 — Live generation caller wired.** `startd8 dashboard create OBSERVABILITY_YAML --target
      perses --project PROJECT` uses the neutral domain-observability producer and writes canonical,
      CUE-validated Perses JSON. Grafana remains the default target.
- [x] **G2 — CUE oracle exercised in CI and locally.** The accompanying change extends the pinned CUE
      v0.16.1 accept/reject job to cover live generation; the same seven oracle tests passed locally
      without skips, including malformed-plugin rejection. The one-line install is in
      `perses/schema/README.md`.
- [ ] **G3 — Authorized Dash0 import path.** A Dash0 project/endpoint + an authorized, credential-safe
      import mechanism is agreed (no secrets in this repo or these docs).
- [x] **G4 — Sample dashboard pre-validated.** `pilot/dash0-pilot.observability.yaml` generated
      `pilot/obs-domain-dash0-pilot-v2.perses.json` through the live CLI; the pinned CUE oracle accepts
      it and CI asserts byte-identical regeneration.

This handoff is live for G3 preparation. The Dash0 team should begin the import only after the
accompanying startd8 change is merged to `main` and G3 is checked.

## 4a. How startd8-sdk unblocks this (owner plan, ordered by critical path)

This is the concrete sequence used to close the startd8-owned gates and hand off G3.

**Step 1 — Close G2 (CUE oracle in CI). ✅ DONE.**
- A `perses-schema` CI job already exists (`.github/workflows/tests.yml:74`) — installs pinned CUE
  v0.16.1 and runs `tests/unit/dashboard_creator/test_perses_emitter.py`.
- **Evidence:** all seven oracle tests passed locally with pinned CUE, including malformed-plugin
  rejection; the CI job exercises both emitter and live-generation tests. The one-line local install
  is documented in the schema README.

**Step 2 — Close G1 (live generation caller). ✅ DONE.**
- **Evidence:** `startd8 dashboard create … --target perses` now routes the domain-observability
  producer through `emit_perses_dashboard(validate=True)` and writes canonical `perses_json()`;
  `--check` validates without writing. Grafana remains the default target. The contract and fail-loud
  behavior are captured in `REQ-perses-live-generation.md`.

**Step 3 — Close G4 (pre-validated sample). ✅ DONE.**
- **Evidence:** the checked-in source regenerates the checked-in Perses JSON byte-for-byte through
  the live CLI, and the pinned CUE oracle accepts it.

**Step 4 — Close G3 (authorized Dash0 import path). READY FOR DASH0 TEAM.**
- This is the one gate startd8-sdk **cannot** self-serve: it needs a Dash0 project/endpoint,
  credentials (never in-repo), and confirmation of **which Perses version Dash0 accepts** vs our
  pinned **v0.54.0**.
- **Completed (startd8-sdk):** `DASH0_PERSES_COMPATIBILITY.md` records the emitted shape/version and
  Dash0's documented import contracts, including the remaining runtime-version uncertainty.
- **Action (pilot team / human):** provision the Dash0 target + authorized, credential-safe import
  path. **This is the ask on you.**
- **Then G3 → ✅.**

**Step 5 — Go-live + promote.** With G1–G4 green, flip the banner, run §5 with the pilot, and promote
**CL-8 L3 → L4/L5** on a successful Dash0 import.

**Parallel, off the critical path:** ContextCore Perses-CRD emission (TODO **T6**) and upstream-Perses
gap contributions (TODO **T9**) proceed independently — neither blocks this pilot.

### Gate ownership at a glance

| Gate | Blocker | Owner | On critical path? |
|---|---|---|---|
| G2 CUE-in-CI | **green in CI + locally, including reject test** | startd8-sdk | ✅ done |
| **G1 live caller** | **`--target perses` live and tested** | **startd8-sdk** | **✅ done** |
| G4 sample validated | canonical pilot artifact generated + pinned | startd8-sdk | ✅ done |
| G3 Dash0 import path | Dash0 endpoint + creds + Perses-version match | **pilot team / human** | yes — **the ask on you** |

## 5. When ready — step-by-step for the pilot

1. **Generate.** Run the handed-off generation command (from G1) to produce a Perses Dashboard JSON.
2. **Validate locally first.** Confirm it passed the CUE oracle at emit time (emission self-validates
   when `validate=True`). A `PersesValidationError` means stop and file it — do **not** hand an
   unvalidated dashboard to Dash0.
3. **Import into Dash0** via the agreed path (G3). Record: Perses/API version accepted, any transform
   Dash0 applied, and whether it round-tripped.
4. **Verify in Dash0's UI/runtime:** panels render, queries resolve against the datasource, variables
   populate, layout/sections match intent, thresholds/units display correctly.
5. **Capture evidence:** the generated JSON, Dash0's accept/reject response, and screenshots/console.

## 6. Success criteria for the pilot

- A startd8-generated Perses dashboard **imports into Dash0 with no manual edits** and renders faithfully.
- Any divergence is attributable to a **named boundary** (§3) or a **specific Dash0/Perses-version gap**,
  not to silent lowering drift.
- Result promotes **CL-8 from L3 → L4/L5** (proven at first real consumer).

## 7. What to report back (closes the loop)

Send findings to startd8-sdk in these buckets so they route correctly:

- **Boundary hit** (§3 capability you need) → feeds TODO **T9 upstream-Perses** lane.
- **Version/interop gap** (Dash0 expects a Perses shape/version we don't emit) → bounds the ADR.
- **Validation escape** (Dash0 rejected something our CUE oracle accepted) → **highest priority**; it
  means the oracle and Dash0's Perses view disagree — pin the exact versions.
- **UX/faithfulness** (renders but wrong) → lowering fidelity bug.

## 8. References

- Entry API: `src/startd8/dashboard_creator/perses/emitter.py` → `emit_perses_dashboard`, `perses_json`
- Validation: `src/startd8/dashboard_creator/perses/validate.py` (CUE v0.16.1; Perses v0.54.0 oracle)
- Neutral model: `src/startd8/dashboard_creator/neutral.py`
- Boundary rationale: `T0_perses-coverage-matrix.md` · Decision: `ADR_adopt-perses-neutral-dashboard-ir.md`
- Status/maturity: `CLOSURE-LEDGER.md` **CL-8**
- Live-generation contract: `REQ-perses-live-generation.md`
- Dash0 compatibility: `DASH0_PERSES_COMPATIBILITY.md`
- Pilot-team action sheet: `READY_FOR_DASH0_TEAM.md`
