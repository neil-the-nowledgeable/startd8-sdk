# Persona-Drafting Toolkit — Requirements

**Version:** 0.1
**Date:** 2026-07-03
**Status:** Draft → Building
**Owner:** neil-the-nowledgeable
**Backlog:** `ENHANCEMENT_BACKLOG.md` (item #10/#11)
**Consumers:** `requirements_panel/` (built), Manifest Suggester (design-only), Stakeholder Panel (shipped — opt-in).

> **What this is.** A small, dependency-light package `src/startd8/persona_drafting/` that holds the
> primitives the three persona-drafting siblings each re-implement: **heading-injection sanitization**,
> the **atomic JSON session-store** shape (a generalization of `stakeholder_panel.proposals.ProposalStore`),
> and **bounded owner-resolution**. It is a *refactor-and-extract*, not a new capability — the goal is to
> stop triplicating these and to **de-risk the Manifest Suggester build** (its spec reuses all three).

---

## 1. Problem Statement

The Requirements Panel build produced a **second copy** of two primitives that already exist in the
Stakeholder Panel, and the design-only Manifest Suggester will produce a **third**:

| Primitive | Copy 1 (shipped) | Copy 2 (built) | Copy 3 (planned) |
|-----------|------------------|----------------|-------------------|
| Atomic JSON session store (own subdir, `mkstemp`+`os.replace`, `0700`, `sort_keys`+`indent=2`, GC, path-traversal guard) | `stakeholder_panel/proposals.py:ProposalStore` | `requirements_panel/store.py:CandidateStore` | Manifest-Suggester `store.py` |
| Bounded owner-resolution (default role → high-confidence `answers_for` → skip) | `stakeholder_panel/input_domains.py:resolve_owner` (value-domain-bound) | `requirements_panel/domains.py:resolve_requirement_owner` | Manifest-Suggester resolver |
| Heading-injection sanitization (`^#{1,6}`/setext → blockquote-demote) | — | `requirements_panel/sanitize.py` | Manifest-Suggester (R3-S1) |

Each copy drifts independently (the store copies already differ in GC), and each re-litigates the same
edge cases (atomicity, path traversal, bare-month exclusion, near-vs-exact matching).

## 2. Guiding Principles

- **P1 — Extract only what is genuinely shared and stable.** Sanitization, the store shape, and bounded
  owner-resolution are proven and identical in intent. Grounding, synthesis, and readiness stay
  **feature-owned** (they differ per artifact) — do not over-extract.
- **P2 — No behavior change for existing consumers.** The Requirements Panel's 29 tests must stay green;
  the Stakeholder Panel is **not** forced to migrate (its `ProposalStore` may adopt the base later, opt-in).
- **P3 — Dependency-light.** The toolkit imports only stdlib + `stakeholder_panel.models.PersonaBrief`
  (for the resolver's brief type). No agent/LLM/telemetry coupling — it is `$0` infrastructure.
- **P4 — Generic, not value-coupled.** The bounded resolver keys on a **symbol string + a domain
  descriptor** (owning role + aliases), never on the value domains (the exact coupling that made
  `input_domains.resolve_owner` non-reusable, R1-F1/R2-S1).

## 3. Requirements

### A. Sanitization (`persona_drafting/sanitize.py`)

- **FR-PD-1 — Move heading sanitization into the toolkit.** Relocate `neutralize_headings` /
  `has_unsafe_heading` / `ATX_HEADING_RE` / `SETEXT_RE` verbatim (behavior-preserving). `^#{1,6}`+setext
  scan, blockquote-demotion primitive, idempotent (R1-F5/R2-S5). `requirements_panel.sanitize`
  re-exports from here so existing imports keep working (P2).

### B. Atomic session store (`persona_drafting/staging.py`)

- **FR-PD-2 — A generic `JsonSessionStore` base.** Encapsulate the proven `ProposalStore` mechanics:
  own subdir, `mkstemp`+atomic `os.replace`, `0700` dir, `sort_keys`+`indent=2`, `_safe_session_component`
  path-traversal guard, and `session_ids`/`latest_session`/`gc_stale_proposals`-equivalent module helpers.
  It is **generic over the record type** via `to_dict`/`from_dict` callables (or a small typed protocol),
  so both `Recommendation` and `RequirementCandidate` records ride it.
- **FR-PD-3 — `CandidateStore` is re-expressed on the base, GC included.** `requirements_panel.store`
  subclasses/uses `JsonSessionStore`, **gaining the session GC it currently lacks** (backlog #9). Same
  on-disk path (`.startd8/requirements-panel/candidates/`) — no migration.

### C. Bounded owner-resolution (`persona_drafting/owner_resolution.py`)

- **FR-PD-4 — A generic `resolve_bounded_owner`.** Signature
  `resolve_bounded_owner(*, owning_role, aliases, symbol, briefs) -> Optional[str]`: (1) the default
  `owning_role` if present on the roster; (2) else a persona whose `answers_for` **explicitly names** the
  symbol or an alias (high-confidence, normalized like `routing`); (3) else `None` — skip, never a loose
  match. Deterministic roster-order tie-break. `resolve_requirement_owner` is re-expressed on it (P2).

## 4. Non-Requirements

- **NR-PD-1 — Do not force-migrate the Stakeholder Panel.** `ProposalStore` / `input_domains.resolve_owner`
  may adopt the base later; this increment does not touch shipped panel behavior (P2).
- **NR-PD-2 — Do not extract grounding, synthesis, or readiness.** They are artifact-specific (a screen
  grounds against the extractor round-trip; a requirement against brief+schema) — extracting them would
  couple siblings that should stay independent (P1).
- **NR-PD-3 — No new provenance vocabulary here.** The shared provenance enum (backlog #12) is a separate,
  later increment; the toolkit is mechanics only.
- **NR-PD-4 — No CLI, no LLM.** Pure `$0` infrastructure consumed by the siblings.

## 5. Open Questions

- **OQ-PD-1 — RESOLVED** → generic over record type via a `to_dict`/`from_dict` protocol, not generics
  gymnastics (Python has no ergonomic typed generic dataclass store; a protocol + callables is simplest).
- **OQ-PD-2 — OPEN** → migrate `ProposalStore` onto `JsonSessionStore` in a follow-up? (Leaning yes, but
  out of scope here per NR-PD-1 — the panel is shipped and heavily tested.)

## §Validation Strategy

- **Behavior-preserving:** the Requirements Panel's existing 29 tests stay green unchanged (P2).
- **Sanitize parity:** the relocated functions pass the same `^#{1,6}`/setext/idempotency fixtures.
- **Store parity + GC:** round-trip + atomic-write assertions carry over; a new test proves `CandidateStore`
  now GCs to the keep-limit (backlog #9 closed).
- **Resolver parity:** `resolve_bounded_owner` reproduces `resolve_requirement_owner`'s default-role /
  alias / skip cases, and a test asserts it is **not** value-domain-bound (the R1-F1 non-reuse property).

---

*v0.1 — Draft. Extract-and-refactor of three proven primitives to de-risk the Manifest Suggester build
and stop triplication. Grounding/synthesis/readiness deliberately stay feature-owned.*
