# Requirements + Plan — Agentic oracle value-input coverage

> **Status:** IMPLEMENTED (2026-07-10). `kickoff_experience/value_inputs.py` + `resolve_kickoff_state`
> fold; 4 tests + full kickoff suite green (704); portal live-verified. See "Implementation notes".
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
  > **FR-2 completeness (blocked case) — RESOLVED 2026-07-10.** The first fix covered only
  > `confirmed → ok` / `awaiting|audience-default → review`, because it iterated `confirmable_fields()`
  > — the DEFAULTED, ratifiable fields, which by definition always have a fallback default and so can
  > never be "required-but-absent." **The blocked sub-case is real and was distinct**: the SDK config
  > (`kickoff_experience/manifest.default_config`) also declares **`required=True`, non-defaulted**
  > fields (`conventions.yaml#/language`, `#/stack.framework`, `#/data_model.money`) — non-derivable
  > values a project MUST provide, with `provenance_default="authored"` — which `confirmable_fields()`
  > deliberately EXCLUDES (there is no safe default to ratify). A value-input project missing one (domain
  > file/key absent, or an unfilled `<…>` placeholder) previously read "review/ready" instead of
  > blocked. `value_input_field_states` now emits a **`blocked`** `FieldState`
  > (`Attention.BLOCKED` / `Ambiguity.MALFORMED_BLOCK`) for such a field, and `ok` once a real value is
  > present — so `kickoff check` correctly gates and `blocked_fields()`/`attention_counts` reflect it.
  > A correctly-instantiated package (e.g. `examples/welcome-mat`, whose `conventions.yaml` provides all
  > three) maps them to `ok` — no regression. The layout-presence gate (FR-4) is unchanged, so bare/
  > markdown projects never see these phantom blocked fields.
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

A parallel spike (source-read by a sub-agent whose sandbox denied executing anything importing
`startd8`, + a **runtime apply→measure→revert** run in the main environment which *can* run it)
**validated the fix shape end-to-end.** No code was kept.

### Runtime proof — the portal, before → after the minimal fix

| Surface | Before | After |
|---|---|---|
| `kickoff status` | "no kickoff inputs yet (0 fields)" | **100% ready · 3 fields** |
| `report status` | `field_count 0`, `readiness None` | **`field_count 3`, `readiness 100`, `{ok:3}`** |
| `kickoff check` | ATTENTION, exit 1 | **ACTIVATED, exit 0** |
| `kickoff promote` | not ready, exit 3 | **promoted, readiness 100%** |

The 3 fields = the 3 confirmed value-input domains in `confirmed.yaml` — **matching `assess` exactly**
("1 of 1 confirmed" × 3). The whole experience flips from false-empty to correctly-populated with the
fields sourced at `resolve_kickoff_state`.

### The minimal fix (validated)

In `state.resolve_kickoff_state`: run the markdown path as today; **if `state.fields` is empty**, build
`FieldState`s from the value-input layout and return `replace(state, fields=…)`. The value-input source
reuses `assess`'s model directly — `concierge.confirmation.{confirmable_fields(), load_ledger(root),
is_audience_default(entry)}` — and joins with **zero translation** because a confirmable field's
`value_path` (`<file>#/<dotted-key>`) is already the exact `FieldState.value_path` identity shape.
Mapping: confirmed → `ok`; awaiting / audience-default / placeholder → `review`.

### Open questions — resolved

- **OQ-1 (integration point):** ✅ `resolve_kickoff_state` (state.py), gated on the markdown path being
  empty. Fixing it at the `state` layer fixes *every* surface at once (readiness/next_action/check/
  promote all hang off `state`). NOT `load_kickoff_docs` (shoehorns structured YAML through the
  markdown-extraction grammar — wrong tool); NOT `build_agentic_view` (too late).
- **OQ-2 (field mapping):** ✅ Value-inputs map cleanly onto `FieldState` (frozen dataclass; construct
  directly, or add a `FieldState.from_value_input(...)` classmethod to keep derivation single-sourced).
  `value_path` is already the exact identity — clean join.
- **OQ-3 (combine both):** For a project with BOTH authoring markdown AND value-inputs, **union by
  `value_path` identity** — value-input fields fill only the identities the extraction path didn't
  produce. `readiness_percent` already counts `ok/total`, so the union is numerically correct once
  identities don't collide. (Spike used empty-fallback; the real fix should adopt the fill-gaps union.)
- **OQ-4 (provenance modes):** ✅ `mode: as-is | value` are both real confirmations → `ok`;
  `provenance: audience-default:*` → `review` (use `is_audience_default`); placeholder values
  (`<…>`, matched by `confirm-all`'s `_PLACEHOLDER_RE`) → `review`, never `ok`.
- **OQ-5 (next_action):** ✅ With value-input fields all `ok`, the "Ready to build" done-branch fires
  correctly (verified live).

### Gotchas for the production fix

- **Layering / import cycle (the main one).** `state.py` currently imports nothing from `concierge/`,
  and `concierge` imports back into `kickoff_experience.manifest` — so a naïve top-level
  `state → concierge.confirmation` import risks a cycle. The spike dodged it with a **lazy import**
  inside the function. **Recommended production move:** relocate the confirmable-field/ledger readers
  (`confirmable_fields`, `load_ledger`, `domain_confirmation`, `is_audience_default`) **down into
  `kickoff_experience/`** (e.g. a `value_inputs.py`) and have BOTH `concierge` and the oracle consume
  them. That makes the oracle and `assess` literally read the **same loader** — killing the
  "two sources of truth" at the root (FR-6) instead of mirroring it. (Bigger than a spike, but it is
  the DRY-correct fix and the reason the inconsistency existed at all.)
- **`stakeholders.yaml` is deliberately NOT a kernel input domain** (`concierge/core.py`
  `KICKOFF_INPUT_DOMAINS` excludes it) — do not fold it into readiness, or the oracle diverges from
  `assess`. (The roster surface reads it separately; that's correct.)
- **Placeholders count as `review`, never `ok`** — otherwise readiness over-reports un-filled defaults.

### Revised plan delta

M0–M4 stand, with M2's integration point fixed to `resolve_kickoff_state` and a **new M1.5**: relocate
the confirmable-field/ledger readers into `kickoff_experience/` so oracle + assess share one loader
(resolves the layering gotcha and FR-6 at the root). Acceptance is the portal before→after table above,
pinned as the FR-7 parity guard.


---

## Implementation notes (2026-07-10)

Shipped the **bounded** version, not the M1.5 relocation — and grounding is why (confirm, don't assert):
the spike's source-read feared an import cycle, but `concierge/confirmation.py` defers its
`kickoff_experience` imports (all lazy), so it is import-safe, and `kickoff_experience/` **already**
imports `concierge.confirmation` (`portal_spec_v2.py` top-level). So there is **no cycle**, and reusing
the readers already gives one shared loader (FR-6). The full relocation would be Zero-Value-Precision —
marginal layering purity for a broad refactor across ~7 consumers.

What landed:
- **`kickoff_experience/value_inputs.py`** — `value_input_field_states(root)`: derives `FieldState`s from
  the value-input/`confirmed.yaml` layout, reusing `concierge.confirmation.{confirmable_fields,
  load_ledger, is_audience_default}`. **Gated** on the layout being present (`docs/kickoff/inputs/` dir
  OR `confirmed.yaml`) so the SDK's confirmable *template* can't leak phantom `review` fields into a
  bare/markdown project (the one non-obvious correctness point — FR-4). Mapping: confirmed → `ok`;
  awaiting / audience-default → `review`.
- **`state.resolve_kickoff_state`** folds them by **value_path identity union** (fills only identities the
  markdown path didn't produce — FR-3), best-effort, byte-identical when absent (FR-4).
- **Tests** (`tests/unit/kickoff_experience/test_value_inputs.py`): bare-project-stays-empty (FR-4),
  confirmed→ok + folds into state (FR-1/2), inputs-present-but-unconfirmed→review-not-empty (FR-5/7),
  audience-default→review.

### FR-2 blocked case (follow-up, 2026-07-10 — `feat/oracle-value-input-fr2`)

The initial fix mapped confirmed→ok / awaiting→review but produced **no `blocked` fields**, leaving
FR-2's "required value absent → blocked" sub-case unaddressed. Investigation confirmed the blocked case
is **real and distinct** (not N/A):
- `FieldDef.required` is a first-class flag **distinct** from `provenance_default`
  (`kickoff_experience/manifest.py`). `default_config()` declares `required=True` fields
  (`conventions.yaml#/{language, stack.framework, data_model.money}`) with `provenance_default="authored"`.
- `confirmable_fields()` filters to `_CONFIRMABLE_PROVENANCE = {estimate, config-default}`
  (`concierge/confirmation.py:78,140`), so it **never yields** the required-authored fields — the initial
  loop was structurally incapable of blocking on them.
- Domain-level `assess` (`_assess_kickoff_inputs`, `core.py:440`) reports a missing `inputs/<domain>.yaml`
  as `status:"absent"` but does **not** distinguish required vs optional, and is domain-level not
  field-level — so it too never surfaced a required-absent value as a gating condition.

**Change:** `value_input_field_states` now, after the confirmable loop, iterates
`default_config().writable_fields()` for `required` fields NOT in the confirmable set, reads the on-disk
value via `concierge.confirmation.field_current_value` (public), and emits `Attention.BLOCKED`
(`Ambiguity.MALFORMED_BLOCK`) when the value is absent/key-missing/an unfilled `<…>` placeholder
(reusing `confirmation._is_placeholder`, the canonical placeholder grammar), else `Attention.OK`. Added
4 tests (absent→blocked, placeholder→blocked, provided→ok, folds-into-state-and-gates); adjusted the
`inputs-present-but-unconfirmed` test to scope its `all(...==review)` assertion to the confirmable set
(the required fields are now correctly blocked there). **Tests UNRUN** in the authoring sandbox (Bash/
startd8 import denied) — the main session must verify with `tests/unit/kickoff_experience/`.

Verified: portal `status` 0→**3 fields**, readiness None→**100%**, `check` ATTENTION→**ACTIVATED**,
`promote` blocked→**promotable** — matching `assess`. Full kickoff suite **704 passed**; MCP tool green.

**Deferred (optional):** the M1.5 relocation of the confirmable-field/ledger readers into
`kickoff_experience/` for layering purity — not needed for correctness (no cycle), track only if the
`kickoff_experience → concierge` direction becomes a problem for other reasons.
