# Requirements + Plan — Agentic oracle value-input coverage

> **Status:** DRAFT (reflective-requirements; open questions to be resolved by a parallel spike on the
> benchmark portal, findings folded back before implementation).
> **Origin:** surfaced by walking the agentic kickoff experience over the Summer2026 benchmark portal
> (`benchmarking/Summer2026/portal/internal`) — 2026-07-10.

## Problem

The agentic kickoff oracle (`AgenticView` → `build_agentic_view`) is the single read-model behind
`kickoff status | check | report | promote | cockpit` and the Grafana Workbook. Its **field/readiness**
derivation reads authoring **markdown** only, so for projects whose kickoff state lives in the
**value-input layout** it reports **false-empty** — "no kickoff inputs, 0 fields, readiness None,
not ready" — for a fully-kicked-off, fully-built app.

This is not a cosmetic bug: for value-input-driven projects (the canonical instantiated-package
layout), *every* agentic surface — status, the activation gate, promotion eligibility, the terminal
cockpit, and the Grafana Workbook — renders "not started."

### Evidence (the portal walkthrough)

Same project, two surfaces, opposite answers:

| Surface | Reads | Result on the portal |
|---|---|---|
| `kickoff assess` (value-input model) | `docs/kickoff/inputs/*.yaml` + `docs/kickoff/confirmed.yaml` | ✅ all 4 domains "present · confirmed"; $0 cascade: 13 entities / 65 routes |
| `kickoff status` / `report status` (the **oracle**) | `build_kickoff_state` ← `load_kickoff_docs` (authoring markdown) | 🔴 `field_count: 0`, `readiness_percent: None`, "no kickoff inputs yet" |
| `kickoff status` (roster sub-surface) | `load_roster` ← `docs/kickoff/inputs/stakeholders.yaml` | ✅ "14 personas" |

The oracle is **internally inconsistent**: its roster surface reads `inputs/` and finds 14 personas,
while its field surface reads authoring markdown and finds nothing — so it simultaneously reports
"14 personas" and "no kickoff inputs."

### Root cause (isolated)

`src/startd8/kickoff_experience/docs.py::load_kickoff_docs` supports exactly two layouts —
`docs/kickoff/authoring/*.md` and `REQUIREMENTS*/PLAN*.md` — and returns `[]` for the
`docs/kickoff/inputs/*.yaml` + `confirmed.yaml` layout. `build_kickoff_state` therefore extracts 0
fields. The oracle folds `build_kickoff_state` as its *only* field/readiness source, so it inherits
the blindness. **There are two kickoff state models — markdown-extraction and value-input-confirmation
— and the oracle folds only the first.**

## Essential vs accidental (the distillation frame)

- **Essential:** the oracle is *the single read-model over a project's kickoff state* — every surface
  derives from it. That single-oracle property is correct and must be preserved.
- **Accidental:** the oracle silently omits an entire state model (value-input/`confirmed.yaml`) that
  a sibling surface (`assess`/`confirm`) already reads. The fix restores completeness to the one
  oracle, not a second parallel read-model.

## Functional Requirements

- **FR-1 — Value-input coverage.** When a project uses the `docs/kickoff/inputs/*.yaml` + `confirmed.yaml`
  layout, the oracle's `field_count` / `readiness_percent` / `next_action` MUST reflect that state
  (parity with what `assess` already reports), not report "no inputs."
- **FR-2 — Provenance → attention.** A value-input's confirmed/awaiting/absent state MUST map onto the
  oracle's attention model: confirmed → `ok`; awaiting-a-decision → `review`/`backlog`; a required
  value absent → `blocked`. (Exact mapping — see OQ-4.)
- **FR-3 — Combine, don't double-count.** When BOTH markdown-extraction fields and value-input fields
  are present, readiness MUST combine them coherently with a defined precedence and no double-count.
- **FR-4 — No regression for markdown projects (SOTTO).** For a project with authoring markdown and no
  value-input layout, oracle output MUST be byte-identical to today (the existing 686-test suite green).
- **FR-5 — Internal consistency.** The oracle's field/roster/pipeline sub-surfaces MUST agree on
  "does this project have kickoff inputs" — no more "14 personas + no inputs."
- **FR-6 — Reuse the existing model.** The value-input state MUST reuse the loader/model `assess`/
  `confirm` already use (`confirmed.yaml` + the input-domain registry), not a reinvented parser.
- **FR-7 — Parity guard.** A project that `assess` reports as populated MUST NOT show
  "no inputs / readiness None" in the oracle. (This is the acceptance test — pin it against the portal.)

## Non-Requirements

- NOT changing `assess`/`confirm` or the input-domain/`confirmed.yaml` model.
- NOT changing the markdown-extraction grammar (`build_kickoff_state` for authoring docs stays as-is).
- NOT requiring a `.startd8` runtime store. (The dormant momentum/retrospective on a store-less
  project is expected and separate — a `check --record` seeds it; but note that is NOT the cause here:
  `field_count` is 0 because the *inputs* aren't read at all, independent of the ledger.)

## Open Questions (the spike resolves these — findings fold back here)

- **OQ-1 — Integration point.** Extend `load_kickoff_docs` to emit value-input docs? Add a parallel
  value-input field source folded in `build_agentic_view`/`_load_state`? Or merge both in
  `resolve_kickoff_state`? (Spike recommends the cleanest.)
- **OQ-2 — Field mapping.** Do value-inputs map cleanly onto `FieldState` (value_path, attention,
  value, manifest), or is a distinct-but-adjacent shape needed?
- **OQ-3 — Readiness semantics.** How does `readiness_percent` (ok/total) combine markdown fields and
  value-input fields when both exist?
- **OQ-4 — Provenance modes.** `confirmed.yaml` records `mode: as-is` vs `value` per field — does the
  mode affect attention (e.g., `as-is` on a defaulted value → `review` vs `ok`)?
- **OQ-5 — next_action.** With value-input fields present, does the "Ready to build" done-branch still
  fire correctly, and does a leverage/next-step recommendation make sense over value-input classes?

## Plan (milestones)

- **M0 — Ground on the assess model.** Locate the exact loader(s)/registry `assess` uses for
  `inputs/*.yaml` + `confirmed.yaml`; document the "present/confirmed/awaiting/absent" derivation.
- **M1 — Value-input field source.** A `$0` deterministic function that derives field-level state from
  the value-input layout (reusing M0's model), mapping provenance → attention (FR-2/FR-6).
- **M2 — Fold into the one oracle.** Wire M1 into the oracle's field/readiness derivation at the
  integration point chosen in OQ-1, combining with markdown fields per FR-3, byte-identical when absent
  per FR-4.
- **M3 — Parity guard + live-verify.** A test asserting assess-populated ⇒ oracle-populated (FR-7);
  live-verify on the portal: `status`/`check`/`promote` reflect the confirmed value-inputs.
- **M4 — Regression + consistency guards.** Existing kickoff suite green (FR-4); a consistency test for
  FR-5 (roster present ⇒ field surface not "no inputs").

## Verification

- **Acceptance (the portal):** after the fix, `kickoff status` on `portal/internal` shows non-None
  readiness + N>0 fields reflecting the 4 confirmed value-input domains; `kickoff check` is not
  "no inputs captured"; `kickoff promote` eligibility reflects real state.
- **No regression:** `tests/unit/kickoff_experience/` green (markdown path unchanged).
- **Parity + consistency guards** (FR-7, FR-5) pinned as tests.

---

## Spike findings (folded in — 2026-07-10)

*(Pending — the parallel spike on the portal proves the fix shape, resolves OQ-1..5, and surfaces
gotchas; its results replace this section before implementation.)*
