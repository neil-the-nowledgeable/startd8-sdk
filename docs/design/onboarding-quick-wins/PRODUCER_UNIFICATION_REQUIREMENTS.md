# VIPP Inbox Producer Unification — Requirements

**Version:** 1.0
**Date:** 2026-07-03
**Status:** Spec (follow-up from the integration audit; not yet implemented)
**Tracks:** [`SUGGESTIONS.md`](./SUGGESTIONS.md) "unify the three inbox producers"; builds on
`docs/design/project-init/` and `docs/design/vipp/`.

> **Design mandate for this work: subtract, don't add.** The goal is to *remove* accidental
> complexity that accrued as onboarding capabilities grew in parallel — not to build a "producer
> framework." Every requirement below is justified by a concrete duplication or workaround in the
> current code, with a citation. If a requirement doesn't delete something, it doesn't belong here.

---

## 1. The honest reframing (read this first)

The audit called this "three inbox producers, entry points not unified." Reading the code changes the
frame:

- **The three "producers" are ESSENTIAL, not accidental.** They exist for genuinely different reasons:
  - **agentic** — the Concierge chat serializes an *LLM-built* buffer's leftovers at session end
    (`cli_kickoff.py:683` → `maybe_serialize_buffer`);
  - **deterministic** — `project init --instantiate` serializes a *greenfield-auto-derived* proposal
    (`project/init.py:285`);
  - **authored** — `project init --proposals FILE` serializes an *operator-authored* set.
  Collapsing these into one mega-producer would *destroy* an essential distinction (three different
  sources of proposals) — that would be **adding** accidental complexity, not removing it.

- **The serialization primitive is ALREADY unified.** All producers go through the single
  `vipp_seam.serialize_buffer` (`vipp_seam.py`), which owns the envelope, the confined write, the
  monotonic `inbox-seq`, `0600`, `.gitignore`, and no-clobber-of-undrained. FR-11 already extracted the
  shared `ensure_inbox_scaffold`. **This half is done and correct.**

- **The VALIDATION primitive is NOT unified — and that is the whole defect.** `make_propose_handler`
  conflates two jobs: (1) *validate + construct* a `ProposedAction` per kind, and (2) *return a
  human-readable ack string* for the agentic LLM tool. Programmatic callers only get the string, so
  they reverse-engineer success — which is exactly the accidental complexity `project init` had to add.

**So the unification is small and subtractive: factor the one validation primitive out of the
message-shaped handler, and let every producer share it.** No framework. No new abstraction layer.

---

## 2. Pre-existing accidental complexity (the inventory this work deletes)

| # | Accidental complexity | Location | Why it's accidental |
|---|---|---|---|
| A | Validation success detected by **string-sniffing** the handler ack | `project/init.py:170` (`_rejection_detail`), `:230`, `:279` (`len(buffer) == before`) | The handler's return is a *human message* for an LLM tool, not a result type. A reworded prefix silently admits bad proposals. `_rejection_detail` and the buffer-length-delta only exist to undo the string coupling. |
| B | `make_propose_handler` **conflates** validate/construct with message-formatting + buffer side-effect + telemetry | `proposals.py:150-209` | A pure "args → ProposedAction (or typed error)" function is the essential unit; it's currently entangled with four unrelated concerns, so it can't be reused by a non-agentic caller. |
| C | The buffer→serialize **idiom re-implemented** per caller | `project/init.py:223-234` & `256-285` vs `cli_kickoff.py:673-683` | Each producer re-wires `make_propose_handler` + `ProposalBuffer` + serialize. |
| D | Kickoff-domain tuple **triplicated** | ~~`concierge/core.py:230`, `project/init.py:53`, `red_carpet_advisor.py:73`~~ | **RESOLVED** in `feat/onboarding-complexity-cleanup` — one `concierge.core.KICKOFF_INPUT_DOMAINS`, imported by all three, guarded by an `is`-identity test. Listed here for completeness. |

---

## 3. Essential complexity (what genuinely must exist)

Producing a VIPP inbox is irreducibly:
1. **Validate** a proposal per its kind (the per-kind rules: `validate_friction`, `validate_posture`,
   `build_capture_plan`, source-presence for schema/manifest/brief).
2. **Construct** a typed `ProposedAction` (kind + params + id, plus `base_sha` for capture).
3. **Serialize** the set into the confined, parity-guarded, no-clobber inbox envelope.

Step 3 is already one function (`serialize_buffer`). Steps 1–2 are one function's worth of logic that
is currently trapped inside a message-shaped handler. **That's the entire essential surface: two
functions.**

---

## 4. Requirements

**FR-PU-1 — Extract a pure validate-and-construct primitive.** Add
`kickoff_experience.proposals.build_proposal(args: dict, *, project_root, config=None) -> ProposedAction`,
containing exactly the kind-dispatch + per-kind validation currently in `make_propose_handler`
(`proposals.py:152-199`). It raises a typed error (`ConciergeInputError` / `CaptureError`; unknown kind
→ `ConciergeInputError("unknown_kind", …)`) on invalid input. It has **no** buffer side-effect, **no**
telemetry, and returns **no** string. It is the single source of per-kind validation.

**FR-PU-2 — `make_propose_handler` becomes a thin wrapper — its external contract is unchanged.**
Re-implement the handler as: `build_proposal` → on typed error return the same `"error: …"` string →
`buffer.add` (→ `BufferFull` string) → `emit` telemetry → return the same `"recorded …"` ack. The
agentic caller (`chat.py:335,362`) sees **byte-identical** behavior. A test asserts the ack/error
strings are unchanged for representative inputs.

**FR-PU-3 — `project init` consumes the primitive directly; delete the string workaround.**
`_buffer_from_entries` and the `produce_inbox` instantiate path call `build_proposal` inside a typed
`try/except`, mapping a rejection to `ProposalsFileError` (authored) or a `rejected` status
(instantiate). **Remove** `_rejection_detail` (`init.py:170`) and both `len(buffer)`-delta checks
(`init.py:230`, `:279`). Behavior is identical (same exit codes, same "nothing written on a bad
entry"); the *mechanism* stops depending on message wording.

**FR-PU-4 — No new inbox producer, no new abstraction.** This work adds exactly **one** function
(`build_proposal`) and deletes code. It introduces no "Producer" class/registry/base, no new CLI, and
does not change `serialize_buffer`'s signature or the `ProposalBuffer` contract.

**FR-PU-5 — Preserve every existing invariant.** Envelope parity, `_PROPOSAL_FIELDS` whitelist,
no-clobber-of-undrained, `0600`/gitignore, monotonic `inbox-seq`, and the `EV_PROPOSAL_MADE` telemetry
(kind-only) are unchanged. `build_proposal`'s per-kind logic is the *same* logic moved, not rewritten
— a diff should show pure extraction.

---

## 5. Anti-goals (what this work must NOT do)

- **No "producer framework."** No `Producer` protocol, registry, or plugin surface. Three call sites
  sharing two functions is the target end-state.
- **Do not collapse the three entry points.** Agentic / deterministic / authored are essential
  distinctions.
- **Do not add a `serialize_proposals(entries)` convenience with a single caller.** If (and only if) a
  second raw-entries producer lands (see §7), introduce it then — speculative generality is itself
  accidental complexity.
- **Do not change `serialize_buffer` / `ProposalBuffer`.** They already model steps 2–3 correctly.
- **Do not add confinement/handoff to modules that don't need it just for symmetry** (see §6).

---

## 6. Deliberately NOT unified (and why) — the discipline, made explicit

- **Red Carpet's missing VIPP handoff is left as-is.** Red Carpet applies proposals *directly at human
  privilege* and intentionally does not serialize an inbox (`red_carpet.py` docstring; no
  `maybe_serialize_buffer` in its REPL exit). Adding a handoff "for symmetry with Concierge chat" is a
  **feature/product decision**, not complexity removal — and it would contradict Red Carpet's stated
  design. Tracked as an **open question** (§7), not a requirement.
- **The Manifest Suggester's direct `_apply_manifest` is left as-is.** `startd8 screens approve`
  applying `manifest` proposals straight to disk is a valid, sanctioned path. Routing it through the
  inbox is an *opportunity* `build_proposal` makes trivial (§7), not a mandate.
- **`stakeholder_panel.input_domains` (3 domains) stays separate** from `KICKOFF_INPUT_DOMAINS`
  (4 domains). They are coincidentally-overlapping but semantically distinct (stakeholder-authored
  inputs exclude `observability`). Unifying them would be *accidental coupling* — the inverse mistake.
  A guard test enforces the distinction.

---

## 7. Follow-ons this ENABLES (optional, separately decided)

Once `build_proposal` exists, these become one-liners — but each is its own decision, not part of this
spec:
- **Manifest Suggester → inbox:** `screens approve --to-inbox` could `build_proposal({kind:"manifest",
  source:…})` and serialize, so screen approvals flow through `negotiate` instead of direct apply.
- **Red Carpet handoff (if wanted):** a session-end `maybe_serialize_buffer` mirroring Concierge chat —
  only if the product wants Red Carpet's unconfirmed proposals to survive to VIPP.
- **Cascade readiness in the init report:** an *explicit* `build_assess` call in `run_project_init`
  (never inside `detect_shape` — see the corrected note in `SUGGESTIONS.md`).

---

## 8. Scope, risk, acceptance

- **Risk: low.** Pure extraction + call-site swap; `make_propose_handler`'s external contract is held
  invariant (FR-PU-2 test), so the agentic path is untouched. Net **negative** line count expected.
- **Branch-first**, deterministic/`$0`, no LLM.
- **Acceptance:** `build_proposal` exists and is the only per-kind validator; `make_propose_handler`
  and `project init` both call it; `_rejection_detail` + both buffer-delta checks are gone; the
  agentic ack/error strings are unchanged (test); all `project`/`vipp`/`kickoff`/`concierge` suites
  green; diff is extraction + deletion, no new abstraction.
