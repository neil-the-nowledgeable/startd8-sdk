# PLAN — Seat requirement authoring on det-req and Definer round-trip

**Pairs with:** `REQ-seat-requirement-authoring-on-det-req-definer.md` · **Version:** 0.4 · **Date:** 2026-08-14  
**Status:** ready to implement (post CRP R1)  
**DIDL semantic name:** Seat requirement authoring on det-req and Definer round-trip  
**Readable handle:** `feature/seat-requirement-authoring-on-det-req-and-definer-round-trip`

## Discoveries (locked into REQ §0)

| Assumption | Planning discovery | Impact on plan |
|---|---|---|
| Panel emits det-req | Panel = elicitation only | F-1a centers Definer writer; F-5 documents Panel sibling |
| New SDK det-req writer | `detReqWriter.js` exists | No startd8 fork; SDK work = consume + recipe |
| Integer REQ-03 brand | DIDL rule | Filenames use semantic slug |
| Replace CC a11y | HOWTO dual path | F-3 SDK HTML; F-4 CC path as verify/doc |
| Two-way evidence parity | SDK `fr_health` is third twin | F-2 includes `det_req.py` |
| Soft cruft verify | tool can be absent and still "pass" | F-3 Verify typed skip (R1-S1) |

## Design

| FR | File · symbol | Change |
|----|---------------|--------|
| FR-1, FR-2 | `dev-os/loops/builder/writers/detReqWriter.js` (+ tests) | Export parity vs **Wire form**; Approve?/Was/Lives; DEFINER-PILOTS gaps |
| FR-3, FR-5 | `dev-os/loops/builder/roundtrip.sh`, fixtures | Harden `--no-serve`; overlay read-only; negative export-unblock test |
| FR-4 | `req-health.mjs` ↔ `extract.py` ↔ `src/startd8/navigator/det_req.py:fr_health` | Three-way class parity; Touches-mined = derived |
| FR-6 | `src/startd8/navigator/*` + `src/startd8/wireframe/{shape_dialect,profile}.py` | Golden consume; parse-loss floor; no new profile module |
| FR-7, FR-8 | HOWTO + folder README | Dual consumer + §6; FR-7 typed skip |
| FR-9 | headers / `.cursor/rules/intent-delivery-naming.mdc` | Already |
| FR-10 | `docs/design/requirements-panel/*` | Emit-seat disclaimer |
| FR-11 | folder README + checked-in golden | Cold-start ≤5 steps |

**Dependency direction:** Definer/dev-os owns emit; startd8 owns Node consume + dialect chrome; det-req-kit owns schema.

**Reuse (Mottainai):** one grammar (NODE-SCHEMA), one store (det-req/0.1), existing roundtrip, existing SDK navigator. Checked-in export golden lives in startd8 so F-3 runs without a live regenerate.

## Iterations

| id | FRs | target | state |
|----|-----|--------|-------|
| F-1a | FR-1, FR-2 | dev-os `detReqWriter` Wire form parity (+ writer commit recorded on golden) | pending |
| F-1b | FR-9 | startd8 DIDL headers already; keep CRP from inventing REQ-NN | pending |
| F-2 | FR-3, FR-4, FR-5 | Headless roundtrip + three-way evidence parity note (`DET_REQ_KIT` set **and** unset) | pending |
| F-3 | FR-6 | Checked-in export golden under `tests/unit/navigator/fixtures/` (or `docs/…/goldens/`); SDK navigate + parse-loss + cruft run-or-skip | pending |
| F-4 | FR-7, FR-8, FR-11 | Operator recipe + CC a11y typed skip + cold-start README | pending |
| F-5 | FR-10 | Panel docs emit-seat disclaimer / cross-link | pending |

Dependencies: F-1a → F-2 → F-3; F-1b parallel; F-4 after F-2; F-5 independent. Acyclic.

## Verify (whole change)

- `roundtrip.sh --no-serve` green on evidence dogfood graph  
- `extract.py --report` exit 0 on exported det-req; done-claim without authored Lives advisories; three-way `fr_health` class match  
- Golden records writer commit/version; regenerating produces a reviewable diff  
- `startd8 navigator build` on checked-in golden: Nodes shape, node count = FR count > 0, Lives painted; `~/Documents/dev/dev-os/scripts/cruft_lint.py` bleed 0 **or** typed skip if absent  
- Documented HOWTO §6 + cold-start README; Panel docs do not claim emit  
- No new integer-led REQ/PLAN filenames  

## Reference audit

| Symbol | Exists? | Disposition |
|--------|---------|-------------|
| `detReqWriter.js` / `roundtrip.sh` / `req-health.mjs` | yes (dev-os) | extend / dogfood |
| `startd8.navigator` + `wireframe/shape_dialect.py` | yes | consume / dialect |
| `~/Documents/dev/dev-os/scripts/cruft_lint.py` | yes | cite absolute; typed skip if missing |
| Requirements Panel emit CLI | **no** | correctly absent (FR-10) |
| `CRUFT-EXPUNGE-LOOP.md` | **missing** | cite script; restore optional |

## Appendix A — Accepted (with where merged)

| ID | Where merged |
|----|----------------|
| R1-S1…S5 | Verify, Reference audit, Iterations F-1a/b F-2 F-3, Design FR-4/FR-6 rows |

## Appendix B — Rejected (with rationale)

*(none — all R1-S* accepted)*

## Appendix C — Incoming review rounds

*(see Iterative Review Log below)*

*v0.4 — Post CRP R1 triage (all 5 S-suggestions accepted). Ready for implementation.*

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
| R1-S1 | Name cruft tool home + typed skip | CRP R1 | Verify + Reference audit | 2026-08-14 |
| R1-S2 | Split F-1a/F-1b; pin writer version on golden | CRP R1 | Iterations table | 2026-08-14 |
| R1-S3 | Checked-in export golden in startd8 | CRP R1 | F-3 target | 2026-08-14 |
| R1-S4 | FR-6 Design → wireframe dialect/profile | CRP R1 | Design table | 2026-08-14 |
| R1-S5 | Parity note records DET_REQ_KIT on/off | CRP R1 | F-2 target | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-5 — 2026-08-14

- **Reviewer**: claude-opus-5
- **Date**: 2026-08-14 19:45:00 UTC
- **Scope**: Plan-side (S-prefix) review of the Design table, Iterations F-1…F-5, Verify bullets, and Reference audit, grounded in targeted reads of `src/startd8/navigator/{det_req,sources_requirements,cli_navigator}.py` and `scripts/navigator_pilot_loop.py`. **Focus ask 4 answered below; asks 1–3 are answered in the REQ file's R1 block.**

##### Focus-file ask 4

**Ask 4 — Are F-1…F-5 dependencies and ownership (dev-os emit vs startd8 consume) crisp enough to implement without accidental second writers?**

- **Summary answer:** No — the *prose* ownership is crisp, but **F-1 is the weak link**: it straddles two repos, and no iteration owns the shared fixture or the cross-repo pin, so F-3's "golden" can drift silently.
- **Rationale:** "F-1 | FR-1, FR-2, FR-9" mixes dev-os writer edits (FR-1/FR-2) with startd8 header work (FR-9), and "Dependencies: F-1 → F-2 → F-3" then hides a two-repo boundary inside a single arrow. "Dependency direction: Definer/dev-os owns emit; startd8 owns Node consume" states who owns the *code* but never who owns the **handoff artifact** (the exported det-req the F-3 golden asserts against), so a writer change can land without invalidating the golden. Accidental second *writers* are well guarded (FR-1 plus the Reference audit row confirming no Panel emit CLI); the real exposure is accidental second **fixtures/goldens**.
- **Assumptions / conditions:** both repos are worked by the same operator but land as separate commits, with no shared CI runner across them.
- **Suggested improvements:** R1-S2 (split F-1a/F-1b and name the pin), R1-S3 (one home for the fixture and the exported golden), R1-S1 (name the cruft tool's home and its skip class so the Verify bullet can actually fail).

##### Executive summary

- **F-1 is a two-repo iteration wearing one id** — split it and name the writer commit/version that F-3's golden pins, or "golden" means "whatever was on disk that day" (R1-S2).
- **The cross-repo handoff artifact has no owner.** The graph fixture lives in dev-os and the exported det-req is regenerated per run; F-3 therefore cannot run in a startd8-only checkout, which quietly contradicts the Reuse/Mottainai "one store" claim at the seam where it matters most (R1-S3).
- **A Verify bullet that cannot fail:** `cruft_lint.py` resolves to `~/Documents/dev/dev-os/scripts/cruft_lint.py` (`scripts/navigator_pilot_loop.py:41`) and, when absent, `_cruft_lint` returns a "(not found ...)" *note* — so "cruft bleed 0" can be reported green by a gate that never executed (R1-S1).
- **The FR-6 file list points at the wrong layer:** dialect/profile chrome is in `src/startd8/wireframe/`, not `startd8/navigator/*`; an implementer following the Design table is one step from adding the parallel profile the "no 2nd renderer" lock forbids (R1-S4).
- **F-2's parity note can be self-parity:** the SDK's kit-preferring parser silently falls back to its vendored twin, so "kit vs Studio agree" may really be "vendored vs Studio" (R1-S5, adversarial).
- **Design table omits the SDK's evidence-class twin** for FR-4 (`src/startd8/navigator/det_req.py`) — filed requirements-side as R1-F2; the plan row should gain the file when that is triaged.
- **Well-covered, no suggestions filed:** the emit-authority lock itself (FR-1 + Reference audit), acyclicity of F-1…F-5, and the DIDL naming iteration (F-1/FR-9) — the latter is already satisfied by this pair's own filenames.
- **Security** was considered and produces no plan suggestion: profile is internal, the change adds no auth surface, and the only trust question (authored vs derived evidence) is filed as R1-F1.

##### Plan Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Ops | high | Name the cruft tool's resolved home and a typed skip class in the Verify bullet; add a Reference audit row for the script path itself | Anchor: Verify bullet "cruft bleed 0 for Entities/CRUD" and Reference audit row "`CRUFT-EXPUNGE-LOOP.md` / **missing** / cite `cruft_lint.py`". The tool is cross-repo at `~/Documents/dev/dev-os/scripts/cruft_lint.py` (`scripts/navigator_pilot_loop.py:41`) and `_cruft_lint` degrades to a text note when it is absent, so a green whole-change Verify does not imply the gate ran. The audit table currently vouches for a doc while omitting the executable it redirects to | **Verify (whole change)** bullet 3, plus a new row in **Reference audit** | Run the whole-change Verify with the dev-os path renamed: assert a typed skip or non-zero exit rather than a note; assert the audit table lists the resolved script path |
| R1-S2 | Architecture | high | Split F-1 into **F-1a** (dev-os `detReqWriter` export parity, FR-1/FR-2) and **F-1b** (startd8 DIDL headers + consume prep, FR-9), and state which writer commit or version the F-3 golden pins | Anchor: iteration row "F-1 | FR-1, FR-2, FR-9" and "Dependencies: F-1 → F-2 → F-3". One id spanning two repos makes the arrow unenforceable and lets F-3's golden pin a stale export with no signal. Answers focus ask 4 | **Iterations** table plus the **Dependency direction** paragraph | Golden artifact records the writer commit/version it was generated from; changing the writer without regenerating the golden fails F-3 |
| R1-S3 | Data | high | Give the cross-repo artifacts one named home: the dogfood graph fixture **and** a checked-in exported det-req golden inside startd8, so F-3 runs without a dev-os checkout | Anchor: Design row "FR-3, FR-5 / `dev-os/loops/builder/roundtrip.sh`, fixtures" and Verify "on that export". No iteration owns the export; regenerated per run it is not a golden, and the "one store (det-req/0.1)" Reuse claim goes untested precisely at the repo seam it is supposed to hold | **Iterations** F-3 target, plus the **Reuse (Mottainai)** line | F-3 green in a startd8-only checkout; regenerating the export produces a reviewable diff rather than a silent change |
| R1-S4 | Interfaces | medium | Correct the FR-6 Design row: the dialect/profile chrome is `src/startd8/wireframe/shape_dialect.py` and `startd8/wireframe/profile.py`, not `startd8/navigator/*` | Anchor: Design row "FR-6 / `startd8/navigator/*` (already shipped)". `sources_requirements.py` imports `RenderProfile` from `startd8.wireframe.profile`, and `shape_dialect.py` exists only under `wireframe/`. An implementer scoped to `navigator/*` either edits the wrong layer or adds a parallel profile — the exact second-renderer drift the plan's Reuse note forbids | **Design** table, FR-6 row | After F-3, grep the diff: no new render/profile module outside `src/startd8/wireframe/`; the touched-files list matches the Design row |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S5 | Risks | medium | Require F-2's evidence-gate parity note to record **which parser produced the rows** (`DET_REQ_KIT` set vs unset) and to run both ways | `parse_fr_lines_prefer_kit` falls back to the vendored parser when the kit yields no FRs — the code comment says "fall back, but loud" yet emits no warning. A recorded "kit and Studio agree" can therefore be vendored-vs-Studio: self-parity dressed as cross-implementation parity, which would let the FR-4 gate pass while the twin it was meant to check never ran | **Iterations** F-2 target, plus the `extract.py --report` **Verify** bullet | Run F-2 twice, with and without `DET_REQ_KIT`; assert the note names the parser used and that both runs yield the same classes |

**Endorsements** — none available: Appendix C had no prior rounds (R1 is the first review of this pair).

**Disagreements** — none available (no untriaged prior items).

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps every REQ section/ID to the plan artifact that carries it. `Gap` rows and `Partial` rows each name the specific missing piece and, where filed, the R1 suggestion that proposes it.

| Requirement (REQ section or ID) | Plan section / iteration | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| O-1 (operator authors Node, valid export) | F-1, F-2; Verify bullets 1–2 | Partial | The "one round-trip green on dogfood graph" target is not any iteration's exit condition, and no step covers the operator's first run (R1-F6) |
| O-2 (headless define ⟷ validate) | F-2; Verify bullet 1 | Covered | — |
| O-3 (same det-req bytes, no forked schema) | F-3, F-4 | Partial | No check asserts "no forked schema"; FR-7's unbounded skip lets this read covered without a CC run (R1-F5) |
| O-4 (UX laws, cruft bleed 0) | F-3, F-4; Verify bullet 3 | Partial | Cruft tool home and skip class unnamed, so the gate can be skipped silently (R1-S1) |
| FR-1 Emit seat is Definer | F-1; Design row 1; Reference audit row 3 | Partial | Positive parity only; no negative gate asserting no other writer emits `Format: det-req/0.1` (ask 1) |
| FR-2 NODE fields on the inspector | F-1; Design row 1 | Partial | "Lossless" has no wire form to be lossless against (R1-F3) |
| FR-3 Headless round-trip gate | F-2; Design row 2; Verify bullet 1 | Covered | — |
| FR-4 Evidence gate before render | F-2; Design row 3; Verify bullet 2 | Partial | Design row lists two implementations; the SDK twin `src/startd8/navigator/det_req.py:fr_health` that drives the render is unlisted (R1-F2) |
| FR-5 Optional dossier / FLCM overlay | F-2; Design row 2 | Partial | No negative test in Verify proving overlay parse failure cannot block export |
| FR-6 SDK navigator consumes same det-req | F-3; Design row 4; Verify bullet 3 | Partial | File list points at the wrong layer (R1-S4); no parse-loss floor on node count (R1-F4) |
| FR-7 CC a11y first-class consumer | F-4; Design row 5 | Partial | Acceptance cannot fail as written (R1-F5) |
| FR-8 HOWTO §6 is the operator recipe | F-4; Design row 5; Verify bullet 4 | Covered | — |
| FR-9 DIDL naming on authored artifacts | F-1; Design row 6; Verify bullet 5 | Covered | — |
| FR-10 Elicitation Panel stays a sibling | F-5; Design row 7; Verify bullet 4; Reference audit row 3 | Covered | — |
| Trust boundary (header): derived overlays must not become authored | (none) | Gap | The SDK consumer mines `Touches:` into `lives` and stamps all nodes `provenance: authored`; no iteration or Verify bullet guards this boundary (R1-F1) |
| Risks table (5 rows) | Design + Reuse notes | Partial | Writer/store drift and Panel-conflation rows are structurally mitigated; "derived overlays become authored truth" has no executable mitigation in Verify (R1-F1) |
| Non-goals (6 items) | Reference audit row 3 | Covered | Panel emit CLI confirmed correctly absent; remaining non-goals need no plan step |
| Owned fields (humans-only inputs) | (none) | Gap | No step verifies machine-filled values never land in human-owned fields; low severity, not filed as a suggestion this round |
| Contract projection (5 entries) | Design table | Partial | No iteration verifies the declared surface names (`--source requirements`, `--report`, `--no-serve`) still match the shipped CLIs |
| Operator onboarding / cold start | (none) | Gap | Proposed as new FR-11 (R1-F6); answers focus ask 2 |
