# REQ — FieldState explicit-state emission for `observability-quality.json` (CCbC Tier B)

**Status:** DRAFT + CONVERGED (CRP rounds R1–R3 folded; see Appendix A/B/C) · **Owner:** startd8-sdk (observability scoring pipeline)
**Consumer rep:** ContextCore report-card loop + Harbor FDE · **Companion (landed, Tier A):** `39c23587` (`rollup_avg_by_type` single-source), `006fd7ef` (merge recompute), `c405cff6` (SLO scoring feed)
**Source principle:** Context-Correctness-by-Construction — Harbor `analysis/component-binding/REQ-01-Systematic-Component-Binding.md` FR-7 ("a state must surface explicitly instead of silently arriving as a 0"; tri-state grounded / bound / unbound-with-reason).
**Phase-0 status:** CLOSED — the `{value, state, reason}` contract below converged with the consumer rep. This REQ formalizes it; it does not re-open it.

> Uncommitted deliverable. Do NOT land without human review. This doc is the spec + the converged CRP; a sibling Phase-1 PLAN section is embedded (§8).

---

## 1. Context / Problem

Over the Harbor observability pilot, one bug class recurred: the SDK's `observability-quality.json` emits a bare `0` **or an absent field**, and a downstream consumer (ContextCore's report-card grader) misreads it as a real value.

Grounded shapes (verified against real Harbor surfaces, not fixtures):

| Surface (real) | `metric_coverage_bridge` on disk | What it actually means | What the grader inferred |
|---|---|---|---|
| `out/export-verify/artifacts/observability-quality.json` | **present, `0.0`** (all 3 orientations `0.0`; `avg_metric_coverage_score = 0.0`) | computed, but no scored artifact carried matching metric content | "no coverage" |
| `out/export-durable/artifacts/observability-quality.json` (affordance-merged path) | **ABSENT** (no `metric_coverage_*` key on any of 3 services; `aggregate` has no `avg_metric_coverage_*`) | the affordance-apply/merge path never ran the coverage computation | "coverage = 0" (via `agg.get(...) or 0`) |

These are **two distinct producer states that render to the same consumer conclusion** ("0"). The `export-durable` absence is the exact class that dropped `avg_dashboard_spec_score` (bus `93e86298`) and stuck the structural grade at B. The consumer reader confirms the flattening is live: `analysis/gen-report-card.py:158` does `agg.get("avg_metric_coverage_score")` and `:299` does `off["composite"] or 0` — a `None` (or absence) becomes `0` one layer down.

**Tier A (landed) closed the *drop* class** structurally (a producer can no longer construct an aggregate missing a per-type key present in `services`). **Tier B (this REQ) closes the *misread* class**: the SDK stops emitting an ambiguous `0`/absent and instead emits an explicit `FieldState` the consumer cannot misread — and pins the consumer obligation not to re-collapse it.

## 2. Goals / Non-goals

### Goals
- G1. Replace ambiguous bare `0`/absent for the migrated fields with an explicit `FieldState` = `{value, state, reason, …}`.
- G2. **One source, two renders**: a canonical plain-value channel (back-compat) AND a structured `field_states` sidecar, both derived from ONE `FieldState` by ONE serializer — the plain value is DERIVED from `FieldState.value`, never set independently (the CCbC guard against the drift that caused the original drop).
- G3. Default-OFF migration flag → byte-identical output until consumers opt in; then flip default on and retire the consumer's "0/absent → fail/not-deployed" inferences.
- G4. First surface migrated: `metric_coverage_{human,system,bridge}` (+ their `dashboarded`/`alerted` aliases). Verified on the REAL Harbor surfaces.
- G5. A documented consumer contract: parity-test the reader; average over MEASURED values, count `null`s separately; NEVER re-derive the aggregate; NEVER flatten `null`→`0`.

### Non-goals
- N1. NOT migrating every field in `observability-quality.json` in this REQ (guard against wrapper-everywhere gold-plating — Appendix B/R2). Only `metric_coverage_*` is in Phase 1; the mechanism is general but applied surface-by-surface.
- N2. NOT owning the consumer's reader implementation — the SDK owns the emitted shape + a parity fixture; the loop/FDE own adopting it.
- N3. NOT retiring the "multiple writers" reality in this REQ beyond the two `observability-quality.json` producers (see §7 + A11). The live-binding registry `unbound` axis (a third producer) is scoped as `unbound`-state-**ready** (the enum reserves it, FR-2) but explicitly **NOT migrated here** — it is the super-report's S4/EC-13 liveness surface, gated on live data that doesn't exist yet and owned by the Phase-0 live-first re-sequence, so it is deferred to §12 phase 3 (LOCKED, A11/OQ-3).
- N4. NOT introducing a runtime `FieldState` object into the scoring hot path where a plain float already suffices internally — `FieldState` is a *serialization-boundary* type, not a pervasive value wrapper (Appendix B/R2).

## 3. The `FieldState` schema (FR-1..FR-4)

- **FR-1 (shape).** `FieldState` serializes to:
  ```json
  {"value": <float|null>, "state": <str>, "reason": <str|null>, "expected": [<str>...]?, "covered": [<str>...]?}
  ```
  `value` is `null` unless `state == "computed"`. `expected`/`covered` are OPTIONAL and emitted only when non-empty (byte-identity discipline mirroring `CoverageReport.to_fr_coverage`).
- **FR-2 (four states).** `state ∈ {"computed", "not_computed", "excluded", "unbound"}` — a closed enum. Any other value is a producer bug (FR-19 gate).
  - `computed` — the value was produced. A `0.0` here is a *real* zero ("computed, and it is zero", e.g. `export-verify`).
  - `not_computed` — this producer path did not run the computation (e.g. the affordance-apply/merge path; `export-durable`). `value: null`.
  - `excluded` — the axis/artifact was deliberately not produced (e.g. an `alert_rule` skipped because the RED kind is declared-covered, #286). `value: null`. NOT a coverage gap.
  - `unbound` — deployed-but-unscraped (the live-binding axis; registry `0.0` misread as "not deployed"). `value: null`. **RESERVED, not built now (A11/OQ-3):** this is the super-report **S4/EC-13** liveness surface, gated on live data that does not exist yet AND owned by the Phase-0 live-first re-sequence (liveness is only knowable live). `unbound` is kept a first-class state HERE precisely so the binding surface can adopt FieldState later with NO schema change — but it is **not emitted by the `metric_coverage_*` Phase-1 producer** (which is statically computable and therefore cannot be `unbound`). See §11 point 2 and §12 phase 3.
- **FR-3 (reason-required rule).** `reason` is REQUIRED (non-empty str) whenever `state != "computed"`, and MUST be `null`/omitted when `state == "computed"`. Enforced by the serializer (FR-19), not by convention.
- **FR-4 (value invariant).** `state == "computed" ⇔ value is a float`; `state != "computed" ⇔ value is null`. The serializer refuses to emit a `computed`+`null` or a `not_computed`+float (FR-19). This is the single guard that makes a `null` unambiguously "not measured" and a `0.0` unambiguously "measured zero".

## 4. Two-channel single-source rendering + the CCbC guard (FR-5..FR-9)

- **FR-5 (one source).** For each migrated field, the producer constructs exactly ONE `FieldState` instance. All rendered representations derive from it.
- **FR-6 (channel A — canonical plain value).** The existing plain key (e.g. `services.<svc>.metric_coverage_bridge`) is rendered as `FieldState.value` (a `float` when `computed`, else `null`). This is what the grader and back-compat readers read. It is **DERIVED**, never assigned from a separate code path (the CCbC guard: the drift that dropped `avg_dashboard_spec_score` was two independent constructions of related values).
- **FR-7 (channel B — structured sidecar).** A parallel `field_states` block, keyed `"<service>.<field>"` (and `"aggregate.<field>"` for rollups), carries the full `FieldState`. Rendered from the SAME instance by the SAME serializer as channel A.
- **FR-8 (renders, not sources).** Additional co-located renders are permitted — e.g. a sibling `metric_coverage_bridge_state` key — ONLY as further renders of the same `FieldState`. Add renders freely; never add a second *source* that could drift. (CRP R3 crystallized this as the load-bearing rule.)
- **FR-9 (single serializer).** Exactly one function (e.g. `render_field_state(fs) -> (plain_value, sidecar_dict)`) produces both channels. No call site sets a plain value and a sidecar entry independently. A test asserts every migrated plain key is reproducible from its sidecar `FieldState.value` (FR-17 parity).

## 5. Dual-emit migration flag (FR-10..FR-12)

- **FR-10 (flag).** A default-OFF flag `emit_field_states` (bool) gates channel B (the sidecar) AND the `null`-for-`not_computed`/`excluded` rendering of channel A. Threaded through the two producers' call chain, not read from a global.
- **FR-11 (byte-identical when off).** With `emit_field_states=False`, `observability-quality.json` is **byte-identical** to pre-feature output on the real surfaces (`export-verify`, `export-durable`). No `field_states` block; the plain keys keep their current on-disk behavior INCLUDING current absence (`export-durable` stays absent-when-off — the flag does not add the key when off). Verified by a golden byte-diff gate (FR-18).
- **FR-12 (flag-on semantics + flip).** With `emit_field_states=True`: absent `metric_coverage_*` becomes `null + state:not_computed + reason` (the key now PRESENT), computed values become `float + state:computed`, and the `field_states` sidecar is emitted. **Flip trigger (LOCKED, A9/OQ-1):** the default flips to ON when — and only when — the consumer PASSES the real-surface parity fixture (FR-17) whose expected grade encodes the null-rule (a `null`-flattening reader fails it). That passing fixture IS the adoption signal; no separate hand-shake artifact is required. At flip, `schema_version` bumps (FR-22) and the consumer retires the "0/absent → fail/not-deployed" inferences in the same coordinated window.

## 6. Consumer contract (FR-13..FR-17) — documented obligations on the reader

These are obligations the SDK documents and PARITY-TESTS a fixture for, but the consumer implements. Stated normatively so the loop/FDE can adopt them verbatim.

- **FR-13 (state→tri-state map).** The consumer maps `state` to its report-card tri-state:
  | `FieldState.state` | consumer tri-state |
  |---|---|
  | `computed` | grounded-and-bound |
  | `not_computed` | deployed-but-unbound (surface `reason`) |
  | `excluded` | not-counted (NOT a gap; excluded from denominators) |
  | `unbound` | deployed-but-unbound (no scrape) |
- **FR-14 (grader null-rule; SDK-side denominator).** The grade averages over the MEASURED (`computed`) values ONLY; `not_computed`/`unbound` are counted separately (a "not measured" tally), and `excluded` is dropped from both numerator and denominator. **The grade-ready denominator (with `excluded` already dropped) is computed SDK-side and emitted (LOCKED, A13/OQ-5; see FR-23)** — the consumer READS it, never re-derives it. Consequence the consumer relies on: **progress = the average of measured values rising; regression = a field flipping `number → null`** (a measured value going missing), which the old `→0` collapse masked.
- **FR-15 (no re-derive — filter, don't recompute).** The consumer MUST NOT re-derive or re-roll the aggregate (`avg_*`) OR the grade denominator from per-service values. The SDK is the exclusive generator of both; a re-deriving consumer is the anti-pattern that caused the original drop. **Reconciled with FR-14 (A13/OQ-5):** the consumer MAY **filter/route** by SDK-emitted `state` (e.g. tally `not_computed` separately for the "not measured" count) — filtering by an emitted state is NOT re-derivation — but MAY NOT **recompute** any value, aggregate, or denominator. The consumer reads the SDK's `aggregate` block + emitted denominator as authoritative.
- **FR-16 (no null-flatten — the one-layer-down guard).** The consumer MUST NOT flatten `null`/absent → `0` at ANY layer (grounding: `gen-report-card.py:158/:299` currently does `agg.get(...) or 0` / `off[...] or 0`). A `null` MUST route to the "not measured" tally (FR-14), never into a numeric axis as `0`. The SDK cannot enforce this in the consumer's process; it is a stated obligation + a parity fixture (FR-17) whose expected grade encodes the null-rule so a flattening reader fails the fixture.
- **FR-16b (per-layer no-flatten lint — LOCKED, A10/OQ-2).** FR-16 + the top-level FR-17 fixture are NOT sufficient alone: a reader can pass the fixture at the top and still `or 0` in a nested render (grounded: the two live flatten sites are at DIFFERENT depths — `gen-report-card.py:158` = `agg.get("avg_metric_coverage_score")` and `:299` = `off["composite"] or 0`). The consumer MUST additionally run a static lint/grep guard that fails CI on `or 0` / bare `.get(..., 0)` applied to any state-bearing field at EVERY read layer, not just the top. This is a stated consumer obligation (like FR-13..FR-17); the SDK documents the guard and ships the grounded flatten-site list as its seed corpus.
- **FR-17 (parity test the reader; IS the flip signal).** The SDK ships a real-surface parity fixture (from `export-durable` + `export-verify`, flag-on) plus the expected tri-state/grade the null-rule produces. The consumer's reader MUST reproduce it. The fixture is DERIVED from a real export (FR-20), never hand-injected (a hand-injected value hides the very absence this contract makes explicit). **The consumer passing this fixture is the concrete safe-to-flip-default signal (A9/OQ-1, cross-ref FR-12)** — its expected grade is constructed so a `null`-flattening reader produces the WRONG grade, so a pass is grounded evidence the reader adopted `state`.

## 7. Producer-side invariants + gates (FR-18..FR-21)

- **FR-18 (byte-identity gate, flag-off).** A CI test regenerates the real `export-verify` and `export-durable` inputs with `emit_field_states=False` and asserts byte-identity with the committed golden. This is the migration-safety gate.
- **FR-19 (serializer-enforced schema).** `render_field_state` raises on: unknown `state`; `computed` with `value is None`; non-`computed` with `value is not None`; non-`computed` with empty/absent `reason`. No `FieldState` reaches disk unvalidated. (Guards FR-2/FR-3/FR-4 by construction.)
- **FR-20 (real-surface verification).** Every FR is checkable on `out/export-verify` and `out/export-durable` WITHOUT a synthetic fixture. Specifically: flag-on, `export-durable`'s `metric_coverage_bridge` MUST render `{"value": null, "state": "not_computed", "reason": <non-empty>}` and MUST NOT be `0` or absent; `export-verify`'s MUST render `{"value": 0.0, "state": "computed"}`.
- **FR-21 (both producers share the serializer).** `_write_quality_report` (`artifact_generator.py`) and `merge_quality_services` (`affordance_map_consume.py`) BOTH render `metric_coverage_*` via the single serializer (FR-9) — mirroring how they already share `rollup_avg_by_type`. Neither producer may construct the plain value or sidebar independently. A drift test (mirror of the Tier-A rollup test) asserts both paths emit identical `FieldState` shapes for the same input.
- **FR-22 (schema_version bumps on flip — LOCKED, A12/OQ-4).** `schema_version` is a bare unvalidated `"1.0"` string today (R1-S3; S6's "trusting an unvalidated literal" hazard). The default-flip to `emit_field_states=True` bumps it (`"1.0"→"1.1"`), and the consumer MAY gate on it. `field_states`-PRESENCE is explicitly NOT the version signal (implicit, drift-prone). Flag-OFF stays byte-identical INCLUDING `schema_version` (consistent with FR-11/B4) — the bump lands at the flip, not at the dual-emit landing.
- **FR-23 (SDK emits the grade-ready denominator — LOCKED, A13/OQ-5).** The `aggregate` block emits the grade-ready denominator with `excluded` already dropped, alongside the per-state counts (`computed`/`not_computed`/`unbound`/`excluded`) and per-field `state`s for audit. This is the single authority the consumer reads (FR-14/FR-15); the consumer never recomputes it. Rendered by the same serializer path as the rollups (FR-9/FR-21) so it cannot drift from the per-field `FieldState`s it summarizes.
- **FR-24 (one self-describing-state vocabulary across BOTH scoring artifacts — LOCKED, A14/DECISION-2; cross-repo).** There is ONE authoritative state vocabulary — the four `FieldState.state` names + `reason` (FR-2) — and it is shared across the two scoring artifacts a report-card reader consults, so a "green" self-describes *consistently regardless of which artifact you read*. **SDK half (this REQ, SDK-owned):** the SDK owns and emits `FieldState` on `observability-quality.json` — authoritative. **ContextCore half (ROUTED, NOT SDK-owned):** ContextCore's `coverage-report.json` already carries the S6 self-describing-provenance pattern (`fr_map_source` / `fr_map_matched_subject` / `fr_map_fallback` — super-report §2b.2); it ADOPTS the SAME four state names (`computed`/`not_computed`/`excluded`/`unbound`) so a fallback/absent axis on the coverage report renders the same explicit state a `metric_coverage_*` field does. This adoption is a **cross-repo contract line item routed to the loop/FDE** (their artifact, their process) — it is explicitly NOT an SDK deliverable. The SDK's obligation is only to keep the four state names + the `reason` rule as the published, versioned (FR-22) vocabulary the ContextCore side binds to; the loop owns landing it on `coverage-report.json`. See Appendix A A14 and §13.

## 8. Phase-1 PLAN (mechanical build — `metric_coverage_*` behind the flag)

**Scope:** emit `FieldState` for `metric_coverage_{human,system,bridge}` (+ `dashboarded`/`alerted` aliases + the `aggregate.avg_metric_coverage_*`) behind `emit_field_states`, default OFF, byte-identical off, verified on real surfaces.

**Build steps (behaviour-preserving, incremental):**
1. **`FieldState` + serializer** in `artifact_generator_models.py` (next to `rollup_avg_by_type`, the existing shared home): dataclass per FR-1, `render_field_state()` per FR-9/FR-19. Unit-test the serializer's four refusals (FR-19).
2. **Producer A** (`_write_quality_report`, ~line 2657–2732): where `metric_coverage_*`/`avg_metric_coverage_*` are set, route through the serializer. When the coverage guard (line 2638) is FALSE → emit `not_computed` (flag-on) / stay absent (flag-off). When computed → `computed` with the float.
3. **Producer B** (`merge_quality_services`, ~line 1046): the affordance-merge path that today never computes `metric_coverage_*` → emit `not_computed` FieldState per service (flag-on). This is the `export-durable` fix — the field goes from absent to `null+reason`, never `0`.
4. **Flag threading:** `emit_field_states` param on both producers + the `generate_observability_artifacts` / affordance-apply entry points; default False. No global.
5. **Aggregate sidecar:** `field_states["aggregate.avg_metric_coverage_*"]`.

**Verify-gate (the acceptance test, real surfaces — no synthetic fixture):**
- `export-verify` flag-OFF → byte-identical golden (FR-18).
- `export-durable` flag-OFF → byte-identical golden (still absent).
- `export-verify` flag-ON → `metric_coverage_bridge` = `{"value":0.0,"state":"computed"}`; sidebar present.
- `export-durable` flag-ON → `metric_coverage_bridge` = `{"value":null,"state":"not_computed","reason":"affordance-apply path; coverage not recomputed"}`; **asserted NOT 0 and NOT absent** (FR-20).
- Parity: every migrated plain key reproducible from its sidecar `FieldState.value` (FR-17/FR-9).
- Drift: both producers emit identical FieldState for identical input (FR-21).

**Test list:**
- `test_field_state_serializer_refusals` (FR-19 × 4 cases).
- `test_quality_report_flag_off_byte_identical` (export-verify + export-durable goldens; FR-18/FR-11).
- `test_metric_coverage_not_computed_on_merge_path` (export-durable flag-on → null+reason, not 0/absent; FR-20).
- `test_metric_coverage_computed_zero_distinct_from_not_computed` (export-verify 0.0 computed vs durable null; the core discrimination).
- `test_plain_value_derived_from_field_state` (FR-9 parity; grep no independent plain-value assignment).
- `test_both_producers_share_serializer` (FR-21 drift mirror).
- `test_consumer_parity_fixture` (FR-17 expected tri-state/grade under the null-rule; a flattening reader fails it).

## 9. Risks

- R-1 (consumer flattens one layer down anyway). The SDK can't enforce FR-16 in the consumer's process. Mitigation: FR-17 parity fixture whose expected grade only passes a null-respecting reader. **RESOLVED (A10/OQ-2 → FR-16b):** the fixture alone is insufficient (top vs nested layers); a consumer-side per-layer lint against `or 0`/`.get(...,0)` on state-bearing fields is now required.
- R-2 (schema-version story). `schema_version` is a plain `"1.0"` string literal (grounded). Adding `field_states` under flag-on is additive; but a hard flip changes the shape. **RESOLVED (A12/OQ-4 → FR-22):** the flip bumps `schema_version` (`"1.0"→"1.1"`); presence-as-version rejected.
- R-3 (byte-identity fragility). `export-durable` is the affordance-merged path; its golden must be regenerated from the SAME inputs the CI uses, or the byte gate flaps on input drift, not code drift. Mitigation: pin the input export dir + a `--check` regenerate.
- R-4 (third producer / live-binding). The `unbound` state has no Phase-1 producer; if a reader expects `unbound` before the binding surface migrates, it sees only 3 states. Scoped out (N3). **RESOLVED (A11/OQ-3):** the binding surface is the super-report S4/EC-13 lane, deferred to §12 phase 3 (gated on Phase-0 live data); `unbound` stays schema-reserved so adoption is additive.
- R-5 (over-abstraction). Building a `FieldState` framework across all fields would be accidental complexity. Guarded by N1/N4 — serialization-boundary type, one surface first.

## 10. Open Questions — ALL RESOLVED (see Appendix A A9–A13)

All five OQs are now LOCKED. They are retained here (struck-through as resolved) with a pointer to the
Appendix A entry that records the decision + rationale and the FRs each tightened.

- **OQ-1 (flip trigger).** ~~What is the concrete signal that the consumer's reader has adopted `state` and it is safe to flip `emit_field_states` default ON?~~ **RESOLVED → A9.** The signal is the consumer PASSING the real-surface parity fixture (FR-17) whose EXPECTED GRADE encodes the null-rule (a flattening reader fails it). Sharpened FR-12 + FR-17.
- **OQ-2 (enforcement of no-flatten).** ~~Is the parity fixture sufficient, or does the consumer also expose a per-layer self-check?~~ **RESOLVED → A10.** A top-level parity test is INSUFFICIENT; additionally require a consumer-side lint/grep guard against `or 0` / bare `.get(...,0)` on state-bearing fields at EVERY read layer (grounded: `gen-report-card.py:158` and `:299`). New FR-16b.
- **OQ-3 (`unbound` producer + schema ownership).** ~~Does Tier B own migrating the live-binding registry surface, and who owns the `unbound` render?~~ **RESOLVED → A11: NO — reserve, don't build now.** `unbound`/binding-liveness IS the S4/EC-13 surface, gated on live data that doesn't exist yet and belonging to the Phase-0 live-first re-sequence (liveness is only knowable live). `unbound` stays a first-class FieldState state so the binding surface adopts it later with NO schema change. Tier B ships on the SDK-generated `metric_coverage_*` surface only. Sharpened N3 + FR-2's `unbound` clause. See §11/§12.
- **OQ-4 (schema_version on flip).** ~~Does the flip bump `schema_version`, or is `field_states` presence the version signal?~~ **RESOLVED → A12: bump `schema_version` on the default-flip** (it is a bare unvalidated `"1.0"` today — S6's "trusting an unvalidated literal" hazard) rather than using `field_states`-presence as the version signal. New FR-22.
- **OQ-5 (`excluded` denominator ownership).** ~~SDK-side or consumer-side, and how to reconcile with FR-15 (no re-derive)?~~ **RESOLVED → A13: SDK-side.** The SDK computes the grade-ready denominator (excludes `excluded`, emits counts + per-field states for audit); the consumer READS it and never re-derives. FR-15 tension reconciled explicitly: the consumer may FILTER by SDK-emitted state but may NOT recompute values. Sharpened FR-14 + FR-15; new FR-23.

---

## 11. Grounding / pilot-process alignment

This REQ does not stand alone — it is one lane of the broader o11y-sapper retrospective. Grounded in the
super-report (`O11Y_SAPPER_SUPER_REPORT.md`) and the pilot-process audit (`PILOT_PROCESS_SURVIVORSHIP_AUDIT.md`):

1. **FieldState is the `metric_coverage` instance of the report's recurring self-describing-artifact pattern
   — "make a green unable to lie."** The super-report applies the same move repeatedly: **S6** makes
   `CoverageReport` self-describe its FR-map provenance (`fr_map_source`/`fr_map_matched_subject`/
   `fr_map_fallback`) so a fallback `0.0` can no longer be mistaken for a real 0% (super-report §2b.2);
   **S2** attributes RED-loci components so a blank isn't silently dropped (§2c); **S4** locates the
   liveness `state` a bound verdict must surface (§2d). FieldState is that same pattern for the
   `metric_coverage_*` field: an explicit `{value, state, reason}` so a `0`/absent can't be misread. It
   should **mirror S6's provenance-field style** — a small, additive, self-describing sidecar on the
   emitted artifact (FR-7), opt-in, byte-identical when off — not a new pervasive value type (N4).

2. **This SDK lane is the NAMED orthogonal complement to the live-first re-sequence.** The pilot-process
   audit shows ~6/8 finding-classes are artifacts of running the authoritative live scrape LAST, and its
   fix is a loop-owned spine change (a **Phase-0 Live App-Landscape Catalog**; audit §3). But the
   super-report's §5 / audit §2 table is explicit that the live-first re-sequence does **NOT** fix every
   class: **GD-1 (scorer-set wiring) is "a pure scoring bug, unrelated to live/static" — `✗` in the
   audit's prevented-by-live-catalog column** (audit §2 table; super-report §5: "Only GD-1 (a pure scorer
   bug) and the S1/S3 code sprawl are orthogonal"). **That orthogonal scorer-integrity class is exactly
   this SDK lane.** So there are two distinct levers, and they compose:
   - **Live-first re-sequence** — *loop-owned*, fixes the **inventory** (what the pipeline knows about
     reality); probe-surface first, populate `declared_emitted_series`.
   - **CCbC scoring-integrity + self-describing state (this REQ)** — *SDK-owned*, fixes the **scoring**
     (how a known value is rendered so it can't be misread as a false zero). FieldState + the two-channel
     single-source guard is the concrete deliverable of this lever.

   Framing the two as complements (not substitutes) matters: no amount of live-first inventory closes the
   `agg.get(...) or 0` misread (FR-16), and no amount of FieldState makes a never-scraped surface knowable
   — which is precisely why the `unbound` binding surface is deferred to the live-first lane (A11/§12).

3. **The migration shape matches the report's established, human-gated pattern.** The dual-emit
   default-OFF flag → byte-identical-when-off → opt-in flip (FR-10..FR-12/FR-22) is the SAME shape the
   super-report uses for its own behaviour-changing distillations: **S6's `strict=True` is opt-in,
   default-off, behaviour-preserving until flipped** (super-report §2b.2), and the deeper reconciliations
   are "proposed and gated to a human" because "they change what rows report" (§0, §2.5). FieldState's
   flip likewise changes what the artifact reports, so it is proposed-and-gated, not auto-flipped — the
   flip signal is a grounded fixture pass (FR-12/FR-17), and the human review bookend is retained (§0 banner).

## 12. Phased roadmap

Three phases, explicitly de-coupled so the SDK lane is **not blocked** on the loop's spine change:

- **Phase 1 — NOW (SDK, independent of Phase 0). "PRE-ISTIO ARMOR" — lands BEFORE the Istio pilot start
  (LOCKED, A15/DECISION-1).** Ship Tier B FieldState on the `metric_coverage_*`
  surface (§8): the two producers emit `computed`/`not_computed`/`excluded` behind `emit_field_states`
  (default OFF, byte-identical off), and the consumer drops `or 0` (FR-16/FR-16b). **This surface is
  STATIC-computable and SDK-generated** — the coverage score is derived from scored artifacts on disk,
  not from a live scrape — so **Phase 1 does NOT depend on Phase 0.** Tier B is therefore not blocked on
  the loop's live-first spine change. This is the GD-1-class orthogonal scorer-integrity lever (§11 point 2).

  **Sequencing rationale (why pre-Istio):** Istio is the WORST case for the false-zero Shape this REQ
  cures. The super-report's Generality Audit quantifies it: **0 of ~10 Envoy/C++ data-plane RED families
  are statically extractable** (`istio_requests_total` is Envoy/C++, name composed at runtime across a
  language boundary — `telemetry.go:977`; super-report §4.1/§4.2), and Istio's canonical error dimension
  is `response_code` not `status`, `error_selector → availability` (super-report §4, §3.1). Every one of
  those is a static-read that legitimately returns a `0`/absent. **Without FieldState, an Istio `0`-read
  masquerades as `0%` coverage; with it, that same read self-describes as `not_computed`(reason: "C++ /
  runtime-composed metric name → live-probe required")** — so the pilot *knows to live-probe* (the §4.2
  live-probe + manifest-declare remediation) instead of trusting a false zero. Because Phase 1 is
  static-computable it does NOT wait on Phase 0 — the armor can land ahead of the Istio start. This is the
  data-level expression of the pre-Istio consolidation checklist (super-report §3.1) applied to the
  scoring artifact.

- **Phase 2 — LOOP (spine change; loop-owned).** The pilot-process re-sequence: a **Phase-0 Live
  App-Landscape Catalog** that runs `probe_surface` FIRST across the deployment-config topology and
  populates `declared_emitted_series` (today `0` on all six Harbor components — audit §1) from the live
  scrape. This is the loop's inventory lever, not an SDK deliverable; the SDK depends on its OUTPUT (live
  liveness data) only for Phase 3. Routed to the loop orchestrator as a spine change (audit §6).

- **Phase 3 — THEN (SDK, gated on Phase 0 + EC-13 live data).** Once the live catalog exists, the
  live-binding registry surface adopts FieldState and renders `unbound` for a deployed-but-unscraped
  series (FR-2's reserved state, activated) — closing the "registry `0.0` → not deployed" misread that is
  the super-report's **S4/EC-13** finding ("presence ≠ liveness"; §2d.2). This phase is **gated on Phase 0
  AND on the EC-13 live data** (a `compare-live` run with a deliberately-frozen series — S4/EC-13 §2d.3/§2d.4),
  because `unbound`/liveness is only knowable live. No schema change is needed at this point: the `unbound`
  state was reserved in Phase 1 (A11/FR-2) precisely so this adoption is additive.

  **Non-blocking note (LOCKED):** because Phase 1's `metric_coverage_*` surface is static-computable,
  Phase 1 does NOT wait on Phase 2/Phase 3. The two SDK phases bracket the loop's spine change but only
  Phase 3 consumes its output.

---

## 13. Pilot-Process Integration

This REQ is one lane of a broader pilot process (the CNCF observability-artifact audit —
`repoprobe/docs/PILOT_OPERATING_MODEL.md`, `PILOTS_HOWTO.md`, and the o11y-sapper super-report). §11 grounds
FieldState in the super-report's *artifact* pattern; this section grounds it in the pilot *process* — what
FieldState is FOR in that process, and how the SDK lane composes with the loop-owned levers without leaking
scope across the repo boundary.

### 13.1 The recognition — FieldState is the data-level enforcement of the invariant autonomy depends on

The pilot model runs at **high autonomy**, and that autonomy is not free — it rests on two load-bearing
invariants (`PILOT_OPERATING_MODEL.md` §"Invariants that keep autonomy safe"):

- **Invariant #1 — machine-checkable oracle:** "trust only what re-runs" (binding coverage / `fr_ratio` /
  determinism diff). Autonomy is safe *because* correctness is re-runnable, not asserted.
- **Invariant #2 — survivorship gate:** "no green trusted for a milestone until **reconciled to
  `origin/main`** *and* **re-measured against the *derived/consumed* artifact** (coverage-report / live
  probe), **not the merge marker** — a fix can be on `main` while its consumed surface is stale/inert."

The **recurring failure Shape across the whole process is one thing wearing many masks: a `0`/absent that
means two different things, read as the wrong one.** It is the same Shape at every layer:

- the super-report **S6** fallback `0.0` mistaken for a real 0% (an FR-map fallback, not a score);
- **PILOTS_HOWTO Step 5**'s near-zero metric read — "do **not** read '0 metrics' as 'nothing emitted' —
  read it as 'I haven't taught the reader this subject's registration idiom yet'" (`0 of 202` Thanos,
  `0 → 112` Istio);
- `declared_emitted_series = 0` on all six Harbor components (the live-inventory field empty until the end
  — super-report §5);
- **GD-1**'s dropped rollup — the `merge_quality_services` bug fixed in `006fd7ef` — which **IS invariant
  #2's named "inert derived artifact behind a merged fix"**: a fix on `main` whose consumed surface was
  stale/inert.

**FieldState is the STRUCTURAL cure for that Shape.** It turns invariant #2 from a *manual audit* ("go
re-measure the consumed artifact, don't trust the merge marker") into a **by-construction property of the
artifact itself**: the emitted `{value, state, reason}` self-describes whether a green is real
(`state == computed`, `value` a real float) or a mask (`state == not_computed`, `value: null` + a `reason`).
A `null`-flattening reader is caught by the parity fixture (FR-17) + per-layer lint (FR-16b). So **FieldState
is the data-level enforcement of invariant #2 — the very invariant the pilot model's autonomy depends on.**
The loop no longer has to *remember* to re-measure the consumed surface; the surface says whether it's real.

### 13.2 The three-way convergence — one design, not three

Three efforts, each owned by a different actor, are the same design pattern applied at three layers. They
**compose** (they are not substitutes — §11 point 2):

| # | Lever | Owner | What it is |
|---|---|---|---|
| (a) | Live-first Phase-0 re-sequence | **loop-owned** | *WHEN* reality enters — restructures `PILOTS_HOWTO` Step 2 (Ground) so the live scrape runs FIRST (super-report §5) |
| (b) | **FieldState self-describing state** | **SDK-owned (this REQ)** | the *SCHEMA* carrying does-emit / should-emit / not-yet-measured with `reason` provenance |
| (c) | Self-describing artifacts | **ContextCore (S6)** | already landed on `coverage-report.json` (`fr_map_source`/`fr_map_matched_subject`/`fr_map_fallback`) |

The lever (b) *is the coordinate* the other two need. `FieldState.state` is the position in the live-first
sequence:

- `not_computed` — **pre-live / static-only**: the computation didn't run on this path (the `export-durable`
  merge case; or a statically-unreadable idiom — the Istio C++ read).
- `computed` — **live-measured** (or statically computed where static suffices): a real value, real zero
  included.
- `unbound` — **emitted-but-not-scraped**: the S4/EC-13 registry case (deployed-but-unscraped; presence ≠
  liveness) — reserved now, activated in Phase 3 against live data (FR-2, §12).
- `excluded` — **should-not** be produced (a deliberately-skipped axis; not a gap).

And `FieldState.expected[]` / `covered[]` (FR-1) carry the **two-authority gap** — *what SHOULD emit* ∩
*what DOES* — which the super-report §5 process-audit says **IS** the coverage finding ("this separates the
two questions the process conflates … whose gap **is** the coverage finding").

### 13.3 Integration map — SDK-owned vs routed (staying in the SDK lane)

Split explicitly so the SDK lane does not hand-roll or silently absorb loop-owned work (invariant #9 —
"don't hand-roll the pipeline … **consume** the shipped capability or **route** the gap"):

**SDK-owned (this REQ):**
- FieldState on the scoring artifact `observability-quality.json` (Phase 1, §8) — the `computed` /
  `not_computed` / `excluded` render behind `emit_field_states`.
- FR-3's manifest metric profiles already embody **invariant #9** by construction: *subject data* lives in
  the manifest, the *generic engine* in code — the exact "keep subject data separate from generic engine"
  discipline the operating model requires.

**ROUTED to the loop / FDE (NOT SDK deliverables — cross-repo line items):**
- `PILOTS_HOWTO` **Step 2** — the Phase-0 live catalog produces the *computed* facts FieldState renders
  (the live scrape is the authoritative source of `computed` values; loop-owned, §12 Phase 2).
- **Step 4** — `declared_emitted_series` (today `0` and silently empty) becomes **FieldState-shaped**, so a
  `0` there renders `not_computed`/`unbound` with a reason instead of a silent empty — closing the `=0`
  silent-empty at its source.
- **Step 5** — the near-zero metric read emits `not_computed`(reason: "idiom not taught to the reader")
  instead of a silent passing empty — i.e. the "0 metrics ≠ nothing emitted, it's an untaught idiom"
  discipline, expressed as an explicit state rather than a human-remembered rule.
- **Step 7** — the scorecard's dimension-coverage checklist READS `state` (tick only what actually
  computed; a `not_computed` axis is visibly not-yet-measured, not a silent tick).
- **Relay** — register the Shape **"silent-0/absent → explicit FieldState"** in the
  `PILOT_RELAY_PROCESS.md` Shape & Color catalog, **with FieldState named as the remediation**, so the next
  pilot inherits the *cure* (the explicit-state pattern), not the *class* (another false-zero to rediscover
  one-run-at-a-time).

The routed half is a cross-repo contract (FR-24 / A14): the SDK publishes the four-state vocabulary + the
`reason` rule; the loop/FDE own landing it on their artifacts and process steps.

---

## Appendix A — Accepted (folded into the numbered FRs above)

- **A1 (from R1).** Byte-identity-when-off must include *preserving current absence* on `export-durable`, not just "no sidecar". A naive implementation that adds the key when off would break FR-11. → sharpened FR-11.
- **A2 (from R1).** The `not_computed` vs `computed-0.0` distinction is the WHOLE point and both are real on disk (`export-durable` absent vs `export-verify` 0.0). Added a dedicated discrimination test → FR-20 + test list.
- **A3 (from R2).** Consumer can flatten `null→0` one layer down; the current reader provably does (`gen-report-card.py:158/:299`). Parity fixture alone is necessary but its expected grade must ENCODE the null-rule so a flattener fails → FR-16 sharpened + FR-17 expected-grade clause.
- **A4 (from R2).** `FieldState` must be a serialization-boundary type, not a pervasive value wrapper, or it's a framework (accidental complexity). → N4 + FR-5 scoped to the render boundary.
- **A5 (from R2).** "Exclusive generator" is aspirational: there are ≥2 `observability-quality.json` writers today (the two producers) plus the live-binding surface. FR-15's "no re-derive" is enforceable only because Tier A already single-sourced the rollup; the `unbound`/binding writer is explicitly OUT of scope → N3 + OQ-3.
- **A6 (from R3).** The load-bearing invariant is "add renders, never add sources" — a co-located `<field>_state` sibling is fine IFF it renders the same instance. Promoted to its own FR → FR-8.
- **A7 (from R3).** Both producers must share the serializer exactly as they already share `rollup_avg_by_type`, with a drift mirror-test — otherwise the two-path drift that this REQ exists to kill reappears at the serializer level. → FR-21.
- **A8 (from R3).** Every FR must be checkable on `export-verify`/`export-durable` without a synthetic fixture; the `not_computed` case specifically must assert NOT-0 AND NOT-absent. → FR-20 tightened.

### Locked decisions (OQ-1..OQ-5 resolution — folded into the numbered FRs)

- **A9 (locks OQ-1 — flip-default signal).** The concrete safe-to-flip signal is: the consumer PASSES the real-surface parity fixture (FR-17) whose EXPECTED GRADE encodes the null-rule. Because the fixture's expected grade is constructed so a `null`-flattening reader produces the WRONG grade (A3), passing it IS the evidence the reader adopted `state` and no longer collapses `null→0`. No separate hand-shake artifact is needed — the fixture is the adoption gate. → sharpened FR-12 (flip trigger = fixture-pass) + FR-17. *Rationale:* a bare "consumer says it's ready" is exactly the unverified claim the super-report's survivorship lens distrusts; a passing null-rule fixture is a grounded, reproducible signal.
- **A10 (locks OQ-2 — per-layer no-flatten).** A top-level parity test is INSUFFICIENT: a reader can pass at the top and still `or 0` in a nested panel render (grounded: `gen-report-card.py:158` = `agg.get("avg_metric_coverage_score")` and `:299` = `off["composite"] or 0` are two DIFFERENT read layers). So in ADDITION to FR-17, require a consumer-side lint/grep guard against `or 0` / bare `.get(...,0)` on state-bearing fields at EVERY read layer. → new FR-16b. *Rationale:* the two grounded flatten sites are at different depths; a single top-level fixture cannot cover a nested collapse — the enforcement must be structural (a lint over all read sites), not just behavioral (one fixture).
- **A11 (locks OQ-3 — Tier B does NOT own the binding surface now; reserve on the same schema).** DECISION: **NO — reserve it, don't build it now.** The `unbound`/binding-liveness surface IS the super-report's **S4/EC-13** finding ("presence ≠ liveness"; the bound verdict never consults liveness — `binding_states:245`), which the report says is **gated on live data that does not exist yet** (needs a Harbor `compare-live` run with a deliberately-frozen series — S4/EC-13 §2d.3) AND belongs to the **Phase-0 live-first re-sequence** (survivorship-audit S4 row: "liveness is ONLY knowable live"). `unbound` therefore stays a first-class FieldState `state` (FR-2) so the binding surface can adopt FieldState later **with no schema change**; Tier B Phase 1 ships on the SDK-generated, statically-computable `metric_coverage_*` surface ONLY. → sharpened N3 + FR-2's `unbound` clause; see the new §11 (grounding) point 2 and §12 (roadmap) phase 3. *Rationale:* building the binding surface now would couple this SDK-owned scoring lane to a loop-owned spine change (Phase 0) and to live data that isn't available — exactly the scope-coupling B5 rejected, now grounded in the super-report's own sequencing.
- **A12 (locks OQ-4 — schema_version bumps on flip).** DECISION: **bump `schema_version` on the default-flip** (`"1.0"→"1.1"`), NOT `field_states`-presence as the version signal. `schema_version` is a bare unvalidated `"1.0"` string today (R1-S3), and the super-report's S6 warns against a reader "trusting an unvalidated literal." A monotonic version bump at the flip gives the consumer a single, explicit gate; `field_states`-presence is an implicit, easily-drifted signal. Flag-OFF stays byte-identical INCLUDING `schema_version` (so the bump lands at the flip, not the dual-emit landing — consistent with B4). → new FR-22. *Rationale:* presence-as-version repeats the "self-describing-but-implicit" smell; an explicit version field is the S6 self-describing-artifact move applied to versioning.
- **A13 (locks OQ-5 — SDK-side `excluded`-denominator; FR-15 tension reconciled).** DECISION: **SDK-side.** The SDK computes the grade-ready denominator (already excludes `excluded`), and emits the counts + per-field `state`s for audit; the consumer READS the SDK's denominator and NEVER re-derives it. This reconciles the FR-15 (no re-derive) tension EXPLICITLY: the consumer MAY **filter/route** by SDK-emitted `state` (e.g. tally `not_computed` separately), but MAY NOT **recompute** the aggregate or the denominator from per-service values. → sharpened FR-14 + FR-15; new FR-23. *Rationale:* a consumer recomputing/flattening the denominator is the exact "mismeasured green" the super-report hunts (the `gen-report-card.py or 0` at `:299` is one instance); single-sourcing the denominator SDK-side is S6's self-describing-fix pattern (one authority emits it, no one downstream re-derives).

### Cross-repo / sequencing decisions (DECISION-1, DECISION-2 — folded above)

- **A14 (DECISION 2 — ONE self-describing-state vocabulary across both scoring artifacts; scope split SDK-vs-routed).** DECISION: **one vocabulary, two artifacts.** The four `FieldState.state` names + `reason` are the single authoritative state vocabulary. The **SDK owns and emits** it on `observability-quality.json` (this REQ — authoritative). ContextCore's `coverage-report.json` — which already self-describes provenance via the S6 pattern (`fr_map_source` / `fr_map_matched_subject` / `fr_map_fallback`; super-report §2b.2) — **adopts the SAME four state names** so a green self-describes consistently *whichever artifact a report-card reader consults*. **Scope honesty:** only the SDK half is in this REQ; the ContextCore-adoption half is a **cross-repo contract line item ROUTED to the loop/FDE** (their artifact, their process — not SDK-owned). The SDK's sole obligation is to keep the four names + the `reason` rule as the published, versioned (FR-22) vocabulary the ContextCore side binds to. → new FR-24; see §13. *Rationale:* a reader that meets two artifacts speaking two different "absent/0" dialects re-imports the exact misread this REQ kills; one shared self-describing vocabulary is S6's provenance-field move generalized across the two artifacts, and calling the ContextCore half *routed* (not SDK-owned) keeps the SDK lane honest per invariant #9 (don't hand-roll / route the cross-repo gap).
- **A15 (DECISION 1 — FieldState Phase 1 lands PRE-ISTIO).** DECISION: **Phase 1 lands before the Istio pilot start.** Istio is the worst case for the false-zero Shape (Generality Audit: **0 of ~10 Envoy/C++ data-plane RED families statically extractable**, `response_code` not `status`, `error_selector → availability` — super-report §4.1/§4.2/§3.1). FieldState makes an Istio static `0`-read self-describe as `not_computed`(reason: C++/runtime-composed name → live-probe required) instead of masquerading as `0%` coverage, so the pilot knows to live-probe (the §4.2 remediation). Phase 1 is static-computable, so this does NOT wait on Phase 0. → sharpened §12 Phase 1 ("pre-Istio armor"); see §13. *Rationale:* landing the armor after Istio starts would let Istio inherit the false-zero class the super-report §3.1 checklist exists to clear before the pilot — the data-level analogue of the pre-Istio consolidation checklist.

## Appendix B — Rejected (with rationale)

- **B1 (R1 proposal: migrate all fields to FieldState at once).** REJECTED — wrapper-everywhere is the accidental-complexity trap the source principle warns against; and a big-bang schema change maximizes byte-identity risk. Surface-by-surface, `metric_coverage_*` first. (→ N1.)
- **B2 (R2 proposal: make FieldState the internal value type throughout the scoring hot path).** REJECTED — the scoring loop computes floats; wrapping every intermediate is gold-plating and hurts readability with no correctness gain. FieldState lives at the serialization boundary only. (→ N4.)
- **B3 (R2 proposal: SDK enforces the consumer's no-flatten rule).** REJECTED as infeasible — the SDK cannot reach into the consumer's process. Replaced with the strongest available: a parity fixture whose expected grade fails a flattening reader (FR-17). Recorded as residual risk R-1 + OQ-2.
- **B4 (R3 proposal: bump schema_version now, pre-flip).** REJECTED for Phase 1 — flag-off is byte-identical INCLUDING schema_version; bumping it while off would itself break byte-identity. Version bump (if any) belongs at the flip, not the dual-emit landing. (→ OQ-4.)
- **B5 (R3 proposal: migrate the live-binding `unbound` surface in the same REQ for completeness).** REJECTED as scope creep — it is a different producer (possibly consumer-owned today) and would couple two migrations. `unbound` is schema-reserved (FR-2) but not produced here. (→ N3 + OQ-3.)

## Appendix C — Incoming (raw review rounds)

### Review Round R1 — lenses: back-compat/migration correctness; the false-zero vs absence distinction
- R1-S1: Does `emit_field_states=False` REALLY stay byte-identical? The risk isn't the sidecar (clearly gated) — it's whether the plain-value render path, once routed through the serializer, changes the current on-disk behavior. On `export-durable` the key is currently ABSENT; a serializer that always emits `null` would ADD a key even when off. Byte-identity must mean "absent stays absent when off".
- R1-S2: The two real surfaces disagree: `export-verify` has `metric_coverage_bridge: 0.0` (present, computed), `export-durable` has it ABSENT. The REQ must not conflate these — the contract's value is precisely telling them apart. Need a test that both cases coexist and stay distinct.
- R1-S3: `schema_version` is a bare `"1.0"` string — no Literal/enum. Any version story must acknowledge it's a free string today; a reader gating on it is trusting an unvalidated literal.
- R1-S4: The flag must thread through BOTH producers (`_write_quality_report` AND `merge_quality_services`), or `export-durable` (merge path) and `export-verify` (direct path) migrate at different times — a split-brain schema.

### Review Round R2 — lenses: consumer-contract soundness; exclusive-generator claim vs reality; over-abstraction
- R2-S1: The parity-test + no-re-derive obligation is NOT sufficient on its own: the current consumer (`gen-report-card.py`) provably flattens `None→0` at :158 (`agg.get(...)`) and :299 (`... or 0`). A consumer can adopt `state` at the top and still collapse a nested `null` to `0` in a panel. The obligation must be "no flatten at ANY layer", and the fixture's expected grade must be constructed so a flattener produces the WRONG grade (else it passes vacuously).
- R2-S2: "SDK is the exclusive generator" is only true post-Tier-A for the ROLLUP. There are two `observability-quality.json` writers (the two producers) and a third live-binding surface (the `unbound` axis). Claiming exclusivity oversells; the honest claim is "single-sourced rollup + single serializer for migrated fields; the binding writer is out of scope". Retiring the consumer re-derive is enforceable, but only for the fields the SDK actually single-sources.
- R2-S3: Over-abstraction guard: is `FieldState` + sidecar the minimum? Yes for the boundary, NO if it becomes the internal value type or is applied to all fields at once. Pin it as a serialization-boundary dataclass, one surface first. Otherwise it's a framework for a single use — itself accidental complexity.
- R2-S4: Real-surface verifiability: is every FR checkable on `out/export-*` without injecting a value? The `not_computed` case is only honestly testable on `export-durable` (a surface where the value is genuinely missing). A synthetic fixture that injects `not_computed` would hide the very absence — so the acceptance test MUST run on the real durable export.

### Review Round R3 — lenses: the drift risk the whole thing exists to kill; renders-vs-sources; real-surface acceptance
- R3-S1: Can two code paths STILL produce the plain value and the structured value independently? If channel A (plain) and channel B (sidecar) are written by two statements, drift reappears one level down from where Tier A fixed it. The invariant must be explicit: ONE serializer emits both; the plain value is DERIVED from `FieldState.value`. A grep/AST test should assert no call site assigns a migrated plain key except via the serializer.
- R3-S2: The "add renders freely, never add sources" rule (from the Phase-0 contract) is the actual load-bearing principle and deserves its own FR — a sibling `<field>_state` key is safe ONLY as another render of the same instance. Promote it.
- R3-S3: The two producers must share the serializer the way they already share `rollup_avg_by_type` — with a mirror/drift test — or the serializer itself becomes the new drift seam.
- R3-S4: Acceptance must assert the negative on the real durable surface: `not_computed` renders NOT-0 AND NOT-absent (flag-on). "Not absent" is as important as "not zero" — the original `export-durable` bug was absence, not a literal zero.
- R3-S5 (convergence check): remaining unresolved items are all consumer-side or cross-repo (no-flatten enforcement depth, `unbound` producer ownership, schema_version-on-flip, `excluded` denominator ownership) → routed to OQ-2..OQ-5, not blocking the SDK Phase-1 build. CRP converged.
