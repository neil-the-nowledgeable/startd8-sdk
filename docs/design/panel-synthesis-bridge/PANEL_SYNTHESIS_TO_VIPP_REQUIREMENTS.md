# Panel Synthesis → VIPP Proposals Bridge — Requirements

**Version:** 0.3 (Post lessons-learned hardening — ready for CRP)
**Date:** 2026-07-07
**Status:** Draft
**Owner:** startd8-sdk
**Related:** `docs/design/vipp/` (VIPP negotiator/applier), `docs/design/stakeholder-panel/` (panel + proposals), `docs/design/kickoff/` (Concierge host, inbox seam)

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass read the actual VIPP / kickoff_experience / stakeholder_panel modules and resolved
> most open questions — several against reality that contradicts the v0.1 draft.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The bridge needs a new staging store for field candidates | `stakeholder_panel/proposals.py:ProposalStore` already stages per-`value_path` records with a **disposition** field (`save`/`load`/`get`/`update_disposition`), at `.startd8/stakeholder-panel/proposals/`. | **FR-6/FR-7 narrowed** — reuse ProposalStore; its disposition field *is* the human-review substrate. No new store. |
| The bridge must build/serialize an envelope itself | Producer path already exists: `build_proposal("capture", {value_path, value})` → `ProposalBuffer.add` → `vipp_seam.serialize_buffer(buffer, root)` writes the confined inbox (seq, checksum, 0600, no-clobber). | **FR-8 narrowed** — compose existing functions; write **zero** new envelope/inbox code. |
| The allow-list is vaguely "host config" | `allowed_value_paths()` is a concrete method on the M3 manifest config (`kickoff_experience/manifest.py:133`). | **FR-4 grounded** to a real function. |
| Field-level items are the primary deliverable | On a brownfield app the manifest allow-list may be **empty**, and the benchmark-portal synthesis's items are dominantly governance/schema/human → **field-level yield may be ~0**. | **Reframed** — the always-firing core is the **classifier + NON-DECIDABLE router**; the FIELD-LEVEL→envelope lane is increment 2, gated on a non-empty allow-list (see FR-3a). |
| Extraction is a single step | Prose→items extraction needs an LLM (paid, non-deterministic); classification / allow-list gate / routing are deterministic `$0`. | **FR-2 split from FR-3/4/5** by cost; FR-13 sharpened. |
| The synthesis is trustworthy input | `facilitation.py` **defaults the business description to the "Blue Planet Adventures" outdoor-gear retail scenario** (`DEFAULT_DESC`, overridable). A run that overrides objective/strategy but not `desc` produces a **domain-contaminated synthesis** — exactly the "outdoor-gear retailer" mismatch the benchmark-portal synthesis flagged (Tension T4). | **New FR-14** — extraction must anchor to the project artifact + allow-list (not trust prose framing) and surface a precondition health-check when the session context looks like the retail default. |

**Resolved open questions:**
- **OQ-1 → LLM for extraction, `$0` for the rest.** Prose→candidate-items is an LLM step (FR-2, paid); classify/gate/route/stage/serialize are deterministic `$0`.
- **OQ-2 → Values usually are NOT in the prose.** The synthesis rarely states a concrete field value, so the bridge stages a **target field + suggested/blank value** and the human supplies/edits the value at review (FR-7). Only where the prose states a value-normalizable specific (`$`, `%`, date — the grounding-guard tokens) is a value pre-filled.
- **OQ-3 → `base_sha` is `build_proposal`'s concern, not the bridge's.** Reusing `build_proposal("capture", …)` means the existing capture construction owns `base_sha` (host-supplied/None for capture); the bridge does not synthesize it.
- **OQ-5 → ProposalStore fits.** Resolved above; it is the FR-6 staging home and FR-7 review substrate.
- **OQ-6 → allow-list = `manifest.allowed_value_paths()`.** For a brownfield app with no kickoff manifest this can be empty → drives the FR-3a gate and the reframe.
- **OQ-7 → NON-DECIDABLE router is the core.** Build the always-firing triage/routing first; the FIELD-LEVEL lane second.

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md`. Three lessons applied:

- **[Phantom-reference audit]** — verified every symbol this spec names exists on disk: `ProposalStore`,
  `serialize_buffer`, `ProposalBuffer`, `build_proposal`, `apply_proposal`, `manifest.allowed_value_paths()`,
  `capture` in `PROPOSAL_KINDS`, `ProposalEnvelope`/`EnvelopedProposal`. See §5 Reference Audit.
- **[Single-source vocabulary ownership (Leg-? #5)]** — the envelope/proposal **schema is owned by
  `vipp/models.py` + `kickoff_experience/proposals.py`**; the allow-list vocabulary by
  `kickoff_experience/manifest.py`. This doc **cites** those owners and treats any schema it shows as a
  *non-normative snapshot*, never a redefinition (prevents contract drift). Added NR-7.
- **[Overloaded-term collision (Leg 6 #13)]** — "**proposal**" is already tri-loaded: panel `ProposalStore`
  record, host `ProposedAction`/`ProposalBuffer`, and VIPP `EnvelopedProposal`. The bridge must **not** add a
  fourth meaning: it names its extracted pre-staging unit a **"candidate"** and reuses the existing types
  downstream. Added NR-8 + a terminology table (§6).

---

## 1. Problem Statement

The stakeholder panel (`startd8 kickoff panel`) runs a facilitated, multi-round session and emits an
LLM-authored **synthesis** — a free-text markdown artifact (`{model, text}`) containing a risk
register, tensions, at-risk assumptions, priority-ordered **recommendations**, and **open questions
for the human**. Today this synthesis has **no programmatic addressing path**: the only surface over
it is the read-only viewer (`startd8 kickoff-panel show/view`). A human reads it and acts by hand.

Separately, **VIPP** (`startd8 vipp init/negotiate/apply`) already exists as the project-side,
deterministic (`$0`, no-LLM) negotiator/applier. It consumes a **structured** `ProposalEnvelope`
(written to the confined inbox `.startd8/vipp/proposals-inbox.json`), adjudicates each proposal
against project ground truth, and emits source-labeled dispositions an applier consumes at project
human privilege. Its one **field-level** proposal kind is `capture` — `params = {value_path:
"entity.field", value: <val>}` — adjudicated by FIELD_AUTHORITY against Sapper ground truth.

**The gap:** nothing converts synthesis *prose* into the structured proposals VIPP consumes. So the
one class of panel recommendation that *is* mechanically decidable — "set field X to Y" — cannot be
routed through the existing `$0` negotiator; it is triaged by hand along with everything else.

This capability bridges that gap: **extract the decidable, field-level items from a panel synthesis,
stage them as structured `capture` proposals in a VIPP envelope, and separate out (never silently
drop) the narrative/governance items that are not field-level.**

### Component gap table

| Component | Current State | Gap |
|-----------|--------------|-----|
| Panel synthesis | Free-text markdown; read-only viewer only | No structured, machine-addressable form |
| VIPP inbox/envelope | Consumes structured `capture`/`brief`/… proposals via `serialize_buffer` | No producer that derives proposals from panel output |
| Field-level recommendations | Buried in prose, mixed with governance items | Not separated, not mapped to `entity.field` value_paths |
| Narrative/governance recommendations | Same prose | No explicit "not decidable by VIPP → route to human/requirements" bucket |
| Provenance of a proposed value | Panel answers are synthetic/unratified | A proposed field value from the panel is an **estimate**, must be labeled as such |

---

## 2. Requirements

### Extraction & classification

- **FR-1 — Read a panel session.** The bridge consumes a saved kickoff-panel session (the transcript
  JSON + its synthesis text) identified by session id (default: latest), from the project's
  `.startd8/kickoff-panel/` store.
- **FR-2 — Extract candidate decidable items.** From the synthesis (and, where structured, the
  round entries), produce a list of **candidate items**, each with: a short title, the source span /
  round + role support it came from, and a proposed disposition target.
- **FR-3 — Classify each candidate into exactly one lane** (deterministic, `$0`):
  - **FIELD-LEVEL** — maps to a concrete `entity.field` **value_path** (a proposed value may be
    supplied by the human at review, OQ-2). Eligible to become a VIPP `capture` proposal.
  - **NON-DECIDABLE** — narrative, governance, schema-change, or open-question items that do not
    reduce to a single field-value. These are routed out, not forced into proposals.
- **FR-3a — Core-first sequencing.** The **classifier + NON-DECIDABLE router (FR-3/FR-5)** is the
  primary, always-firing deliverable and the first increment. The **FIELD-LEVEL → envelope lane
  (FR-6/FR-7/FR-8)** is the second increment and is **gated on a non-empty `allowed_value_paths()`**:
  when the allow-list is empty (e.g. a brownfield app with no kickoff manifest), the bridge produces
  the routing report only and says so, rather than emitting an empty envelope.
- **FR-4 — Allow-list gate.** A FIELD-LEVEL candidate is only promotable if its `value_path` is in
  the host's `allowed_value_paths()`. A field-shaped candidate whose path is *not* allow-listed is
  reclassified NON-DECIDABLE (with reason `value_path_not_allowed`), not dropped.
- **FR-5 — No silent loss.** Every synthesis recommendation/open-question is accounted for in the
  output: either a staged FIELD-LEVEL candidate or a line in the NON-DECIDABLE report with a reason
  and a suggested owner (human decision / requirements backlog / schema change).

### Staging & envelope production

- **FR-6 — Stage via the existing ProposalStore at `estimate` provenance.** FIELD-LEVEL candidates are
  staged (not yet in the VIPP inbox) as drafted recommendations carrying **`estimate`** provenance — a
  panel-proposed value for a field is a *starter estimate*, never an OBSERVED fact — by **reusing
  `stakeholder_panel/proposals.py:ProposalStore`** (`save`) rather than a new store.
- **FR-7 — Human review before the inbox, via the disposition field.** Staged candidates are presented
  for human review/edit (accept / edit value / drop) and their disposition recorded through
  `ProposalStore.update_disposition(...)`. The panel is synthetic and unratified; a human ratifies
  which candidates become negotiable proposals before any envelope is written.
- **FR-8 — Emit a VIPP envelope by composing existing producers.** On confirmation, the bridge turns
  each accepted candidate into a `capture` action via `build_proposal("capture", {value_path, value})`,
  adds them to a `ProposalBuffer`, and calls `vipp_seam.serialize_buffer(buffer, project_root)` — which
  already writes the confined inbox with monotonic `envelope_seq`, content checksum, 0600, gitignore,
  and no-clobber-of-undrained. The bridge writes **no** envelope/inbox bytes directly (NR-7). The
  envelope shape shown in §6 is a non-normative snapshot of `vipp/models.py`.
- **FR-9 — Then hand off to VIPP unchanged.** After the envelope is written, the operator runs the
  existing `startd8 vipp negotiate` and `startd8 vipp apply`. The bridge does **not** re-implement
  adjudication or application — it only produces the envelope VIPP already knows how to consume.

### Provenance, safety, honesty

- **FR-10 — Synthetic/unratified labeling.** Every staged candidate and the NON-DECIDABLE report
  carry the "synthetic, unratified panel input" banner and pin the source session id (and, where
  available, the persona/brief support and grounding level) so a reviewer ratifies against the gap,
  not the persuasive prose.
- **FR-11 — Idempotent, re-runnable.** Re-running the bridge on the same session + unchanged synthesis
  is a recognizable no-op (does not duplicate staged candidates or clobber an undrained inbox).
- **FR-12 — CLI surface.** A user-facing command drives the flow (working name `startd8 kickoff
  panel propose` — see OQ-4), with `--session`, a `--dry-run`/preview mode (`$0`, shows lanes without
  writing), and `--json` for agents.
- **FR-13 — Cost honesty.** Extraction (FR-2) uses an LLM → the command is clearly **paid** and its
  cost is tracked; classification, allow-list gating, routing, staging, and envelope serialization
  (FR-3/4/5/6/8) and the downstream VIPP steps are **`$0`**. `--dry-run` runs only the `$0` stages
  over already-extracted candidates.
- **FR-14 — Context-contamination precondition.** Because `facilitation.py` defaults the business
  description to the "Blue Planet Adventures" retail scenario, a session's synthesis may be framed
  around a domain the project is not. The bridge MUST (a) anchor extraction to the **live project
  artifact + `allowed_value_paths()`**, not the prose's framing, so a retail-framed recommendation
  cannot mint a field-level proposal for a field the project lacks; and (b) surface a **health check**
  that flags — non-blocking — when the source session's context matches the retail default, so the
  reviewer knows the input may be contaminated.

---

## 3. Non-Requirements

- **NR-1 — Not a VIPP replacement.** Does not adjudicate or apply proposals. It only produces the
  envelope; VIPP negotiate/apply are unchanged.
- **NR-2 — Not a synthesis author.** Does not run or re-run the panel, and does not rewrite the
  synthesis. It consumes an existing session.
- **NR-3 — Does not force non-field items into proposals.** Governance decisions (blinding, embargo
  ownership), schema/feature work (new entities, state machines), and open questions are explicitly
  *not* coerced into `capture` proposals. They go to the NON-DECIDABLE report.
- **NR-4 — No new proposal kind.** Uses the existing `capture` kind and existing envelope contract;
  does not extend `PROPOSAL_KINDS` or bump `PROTOCOL_VERSION` (if planning shows a bump is needed,
  that is a discovery to surface, not a goal).
- **NR-5 — No auto-apply.** Never applies to disk without the human-confirm + `vipp apply` path.
- **NR-6 — Not a requirements generator.** For NON-DECIDABLE items it emits a routed backlog list,
  not authored requirements docs.
- **NR-7 — Does not redefine or write the envelope/inbox directly.** The `ProposalEnvelope`/
  `EnvelopedProposal` contract is owned by `vipp/models.py`; the inbox write is owned by
  `vipp_seam.serialize_buffer`. The bridge composes them and treats any schema it displays as a
  non-normative snapshot — it never re-implements serialization or bumps `PROTOCOL_VERSION`.
- **NR-8 — Does not add a fourth meaning of "proposal".** The extracted pre-staging unit is a
  **"candidate"** (§6); downstream it becomes a ProposalStore record, then a host `ProposedAction`,
  then a VIPP `EnvelopedProposal` — all existing types. No new "proposal" class is introduced.

---

## 4. Open Questions

- **OQ-4 — Command home (still open).** `startd8 kickoff panel propose` (panel namespace owns "from a
  panel session") vs `startd8 vipp stage-from-panel` (VIPP namespace owns "produce an envelope"). Lean
  panel-namespace, but the CRP should confirm which surface owns the verb.
- **OQ-9 — LLM extraction contract (new).** What is the input/output JSON contract for the FR-2
  extraction boundary (a Keiyaku A2A contract per the SDK's micro-prime rule)? Candidate fields:
  `{title, source_span, round_support[], role_support[], suggested_lane, value_path?, value?,
  value_specifics[]}`.
- **OQ-10 — Verification of extracted value_paths (new).** Should a candidate's `value_path` be
  verified against Sapper `project_knowledge.field_sets` *at extraction time* (pre-flight), or left
  entirely to VIPP `negotiate` (which already does FIELD_AUTHORITY)? Pre-flight would let the bridge
  reclassify a phantom-field candidate to NON-DECIDABLE before staging, at the cost of duplicating a
  check VIPP owns.

- **OQ-1 — Is extraction deterministic or LLM-based?** The synthesis is free prose. Can decidable
  items be extracted heuristically ($0, deterministic), or is an LLM pass required? If LLM, this is
  the one paid step — does that violate the "panel-adjacent tooling is cheap" expectation?
- **OQ-2 — Where do proposed *values* come from?** A `capture` proposal needs a concrete `value`.
  Does the synthesis ever state one (e.g. "publication budget ceiling $8,000"), or does the human
  always supply it at review time? If the latter, the bridge stages a *target field* with a blank/
  suggested value, not a decided one.
- **OQ-3 — What is `base_sha` for a panel-derived capture proposal?** VIPP treats `base_sha` as a
  host-trusted, propose-time, capture-only binding that is never VIPP-amendable. What binds it here —
  the ground-truth/schema sha at extraction time, or None?
- **OQ-4 — Command home.** `startd8 kickoff panel propose`, `startd8 vipp stage-from-panel`, or a
  new verb? Whose namespace owns "produce a VIPP envelope from a panel session"?
- **OQ-5 — Staging store reuse.** Does the existing `stakeholder_panel/proposals.py` ProposalStore
  fit as the FR-6 staging home, or does a panel-derived-candidate need a distinct record shape?
- **OQ-6 — Allow-list source.** Where does `allowed_value_paths()` come from for a brownfield app
  like the benchmark portal, and are the synthesis's field-shaped items (`Run.name`, `embargoState`,
  …) even in it? If almost nothing is allow-listed, the field-level yield may be ~0 — is the value
  then mostly the NON-DECIDABLE routing report?
- **OQ-7 — How much of a real synthesis is actually field-level?** On the benchmark-portal synthesis,
  the 9 recommendations are dominantly governance/schema/human. If the real-world hit rate is near
  zero, is the FIELD-LEVEL lane worth building now, or is the first increment the classifier +
  NON-DECIDABLE router (which is the part that always fires)?

---

---

## 5. Reference Audit (phantom-reference check)

Every code symbol this spec depends on, verified to exist on disk (2026-07-07):

| Symbol | Location | Role in the bridge |
|--------|----------|--------------------|
| `ProposalStore` (`save`/`load`/`get`/`update_disposition`) | `stakeholder_panel/proposals.py` | FR-6 staging + FR-7 review substrate |
| `PROPOSAL_KINDS` incl. `"capture"` | `kickoff_experience/proposals.py:41` | field-level kind (`params={value_path,value}`) |
| `build_proposal(kind, args, …)` | `kickoff_experience/proposals.py:140` | FR-8 build a `capture` `ProposedAction` |
| `ProposalBuffer.add` | `kickoff_experience/proposals.py:114/122` | FR-8 accumulate before serialize |
| `serialize_buffer(buffer, root, …)` | `kickoff_experience/vipp_seam.py:181` | FR-8 write confined inbox (seq/checksum/0600) |
| `manifest.allowed_value_paths()` | `kickoff_experience/manifest.py:133` | FR-4 allow-list gate / FR-3a sequencing gate |
| `ProposalEnvelope` / `EnvelopedProposal` | `vipp/models.py` | §6 snapshot (owned there, NR-7) |
| `evaluate_envelope` (FIELD_AUTHORITY for `capture`) | `vipp/evaluate.py` | downstream `vipp negotiate` (NR-1) |
| `apply_proposal` | `kickoff_experience/proposals.py:217` | downstream `vipp apply` (NR-1) |
| `DEFAULT_DESC` retail scenario | `stakeholder_panel/facilitation.py:83` | FR-14 contamination source |
| kickoff-panel session store | `.startd8/kickoff-panel/<id>.json` | FR-1 input |

*No phantom references: no symbol named as load-bearing is unverified. New code the bridge adds
(extractor, classifier/router, CLI verb) is greenfield and marked as such — not claimed to exist.*

## 6. Terminology (overloaded-term disambiguation)

| Term | Owner / type | Meaning here |
|------|--------------|--------------|
| **candidate** | *new* (this bridge) | An extracted, pre-staging synthesis item — before any lane/store decision |
| ProposalStore **record** | `stakeholder_panel/proposals.py` | A staged per-`value_path` recommendation with a disposition (FR-6/7) |
| **ProposedAction** / ProposalBuffer | `kickoff_experience/proposals.py` | Host action + in-memory buffer; the `capture` we build (FR-8) |
| **EnvelopedProposal** / ProposalEnvelope | `vipp/models.py` | The serialized inbox unit VIPP negotiates (NR-7) |

Non-normative envelope snapshot (authoritative form: `vipp/models.py`):
```
ProposalEnvelope { project_id, envelope_seq (monotonic), generated_at, content_checksum, proposals[] }
EnvelopedProposal { kind:"capture", params:{value_path:"Entity.field", value:<any>}, id, base_sha }
```

---

*v0.3 — Post lessons-learned hardening. Applied 3 lessons (phantom-reference audit, single-source
vocabulary ownership, overloaded-term collision). vs v0.1: 5 FRs narrowed/grounded (FR-3/4/6/7/8),
2 added (FR-3a, FR-14), 2 NRs added (NR-7/8), 6 OQs resolved, 3 opened (OQ-4/9/10). Ready for CRP.*
