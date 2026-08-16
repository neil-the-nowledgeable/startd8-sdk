# ADR — Promote the acceptance oracle, human-approval gate, and change-history into the Node IR

**Status:** Accepted (2026-08-16 — schema owner go) · **Date:** 2026-08-16 · **Deciders:** navigator / Node-schema owner (human)
**Affects:** `startd8-sdk/src/startd8/navigator/models.py` (canonical Node) ·
`dev-os/NODE-SCHEMA.md` §1 (schema doc) · ContextCore Node mirror
**Relates:** the Natural-Language Programming System thesis
(`~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md`) · REQ-08 (Verify-as-oracle,
navigator projection) · REQ-16 (derivation edge + schema self-conformance — enforces this ADR)

## Context

In the NLPS framing, the **Node/contract is the IR** of a compiler whose source language is prose:
`INTENT → FUNCTIONAL DESCRIPTION (FRs) → CONTRACT/Node → {impl, tests, docs}`. The system's
**reliability architecture** rests on two things the thesis names explicitly:

- **`Verify:` is the oracle** — the compiler's type-checker / acceptance criterion.
- The **`NL→contract` step is human-gated** (`Approve?:`, the DATA-MODEL bookend) — the reliability
  pivot that makes the ambiguous step trustworthy before the deterministic `contract→product` step runs.

**Finding (grounded 2026-08-16):** `det_req.py` parses each FR into
`{name, lives, verify, approve_prompts, was, serves, …}`, but `models.Node`'s fields are
`key, does, status, wont, lives, ships_when, confidence, triggers, children, child_keys, category,
orientation, route_state, status_facets, attributes` — **there is no `verify`, no `approve`, no `was`.**
When a requirement projects into a Node, its acceptance oracle, its human-approval gate, and its
change history are **dropped at the Node boundary.**

The IR therefore discards exactly the two fields that encode the NLPS's reliability semantics. The
downstream consequence is already visible: REQ-08's `pipeline_provenance` must **reconstruct** the
verification/approval chain heuristically (longest-prefix ownership) because it isn't carried, and
the oracle exists only as a navigator-side projection rather than a native property every instance
(capability, signal, case-section) could hold.

## Decision

Promote three **optional** fields to first-class on the Node, and have the det-req→Node projection
**carry them through** instead of dropping them:

| Field | Meaning (compiler role) | Source |
|-------|-------------------------|--------|
| `verify` | the **acceptance oracle** — the node's checkable contract (carries REQ-08's classified kind: `command` / `assertion` / `manual`) | det-req `Verify:` |
| `approve` | the **human-gate marker** — crossed / pending (the DATA-MODEL bookend) | det-req `Approve?:` |
| `was` | the **change-history alias** — raw material for the RETROSPECTIVE bookend | det-req `Was:` |

All three are optional with empty defaults. **Render output stays byte-identical** (the new fields
aren't rendered by default); the only intended change is the `node_field_names()` golden and
`NODE-SCHEMA.md` §1 — i.e. a **deliberate Node schema-version bump (0.3.9 → 0.4.0)**, which is the
correct signal for a real IR evolution.

## Consequences

**Positive**
- The reliability semantics become **native, not reconstructed** — REQ-08's oracle and
  `pipeline_provenance` stop being navigator-only heuristics.
- `verify` is **uniform across all six instances** — a capability or signal can carry its own oracle.
- The **human-gate becomes a queryable facet** (`approve:crossed` vs `approve:pending`), so "did this
  cross the DATA-MODEL bookend?" is answerable at the IR, not inferred.
- The **RETROSPECTIVE bookend gets a home** (`was`), closing the feedback edge of the compiler.
- Enables the **schema-as-Node** dogfood: a Node's own `verify` can assert its own `lives`.

**Costs**
- Node schema-version bump: `node_field_names()` golden updates (the deliberate signal), and
  `NODE-SCHEMA.md` §1 must add the fields. *(Note: §1 is **already stale** — it omits
  `category/orientation/route_state/status_facets/child_keys/attributes` that the code has — so §1
  needs a refresh regardless; REQ-16 makes that drift a gated invariant.)*
- The **ContextCore Node mirror** must adopt the fields to stay byte-identical.

**Risks & mitigations**
- *Accretion.* Held to the schema's own bar ("first-classing axes is a **simplification**, not
  accretion" — §1a): promoting these **removes** the heuristic reconstruction path, doesn't add one.
- *Cross-repo drift.* Mitigated by **REQ-16's conformance gate** (doc↔code field parity), which would
  have caught the existing §1 staleness.

## Alternatives considered

- **(A) Keep `verify`/`approve` as navigator-only projections** (REQ-08's conservative choice).
  *Rejected:* forces heuristic reconstruction and leaves the NLPS's reliability fields non-native and
  un-carryable cross-repo.
- **(B) Store them in the existing `attributes` open bag** (byte-identical, no schema bump).
  *Rejected:* `attributes` are untyped strings; an oracle needs structure (kind + clause) and the
  human-gate needs to be a first-class **facet**. Burying reliability semantics in a string bag
  reproduces the reconstruction problem — **first-classing is the point.**

## Coordination

`models.py` is the canonical Node; `dev-os/NODE-SCHEMA.md` §1 and the ContextCore mirror follow. This
is a **cross-repo schema change** and must not land in code until the schema owner approves. This ADR
records the decision; **REQ-16** specs the sibling derivation edge and the conformance gate that
enforces the doc↔code parity this ADR depends on.
