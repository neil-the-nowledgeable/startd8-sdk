# Red Carpet Treatment — Requirements

**Version:** 0.3 (Post-CRP R1)
**Date:** 2026-06-29
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `RED_CARPET_TREATMENT_PLAN.md` (v0.2)
**Related (reuse, inherit boundaries — do not re-litigate):**
`WELCOME_MAT_2.0_REQUIREMENTS.md` (v0.4), `WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` (v0.4),
`INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md`, `KICKOFF_INPUT_PACKAGE_GUIDE.md`,
`KICKOFF_AUTHORING_CONTRACT.md`, `CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md`; the **four-bucket
separation** + **two-generation-paths** framing in `CLAUDE.md`.

> **What the Red Carpet Treatment is.** The white-glove, **agentic, build-your-app-from-scratch**
> experience. An agent walks a greenfield user from *nothing* to a **complete kickoff input surface**,
> co-authoring every input the deterministic `$0` cascade needs, so `startd8 generate
> backend/scaffold/views/frontend` can run at **full capability**. RCT is an **orchestration layer
> above** Welcome Mat 2.0 + Concierge — it sequences the agent and the human through producing inputs;
> it does not re-implement the pieces beneath it, and it never authors the user's real content.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass confronted the draft with the
> real code and surfaced one **build-environment** correction and several **scope** corrections. The
> headline holds — RCT is genuinely an orchestration layer — but it must **branch from `origin/main`**
> and build exactly **three** new pieces.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The proposal model + web chat are reusable substrate | **True on `origin/main`** — `ProposedAction`/`apply_proposal`/`propose_action`, `/concierge/chat`+`_ChatStore`+`new_agentic_kickoff_chat` all exist. The planning Explore pass read the **primary worktree** (`feat/welcome-mat-2-download`), which is *behind* `origin/main` and lacks them, and wrongly reported them absent. | **RCT must branch from `origin/main`** (the primary worktree lacks the substrate). Recorded as a build-env prerequisite. |
| `concierge/derive` does interview→schema (OQ-5) | `derive` is **Pydantic-models → prisma**; `generate contract` is **prose (requirements doc) → prisma** (`--promote` = the human write). **Neither is conversational.** | **FR-RCT-4 reframed:** agent interviews → drafts a **requirements prose brief** → human confirms → `generate contract --promote`. `derive` is a side door for users with existing models. (OQ-5 resolved.) |
| Extractors + an existing writer materialize manifests into the project | `extract_manifests` is pure/in-memory + round-trip-gated; the **only** on-disk writer targets a *run-dir*. **No command writes prose→`docs/kickoff/inputs/*.yaml` in the project tree.** | **New piece N1** (FR-RCT-6 acceptance): a project-tree manifest writer over the existing `apply_write_plan` seam — RCT's biggest genuinely-new piece. |
| Proposal kinds extend cleanly (OQ-1) | Model exists but kinds are **bespoke per-kind apply** (no registry); today `friction`/`instantiate`. | OQ-1 = **medium** extension (a builder + dispatch branch + apply path per new kind); still the riskiest. `value-input` must ride `capture.py` (per-key merge), not a whole-file write. |
| Readiness might cover only the 4 value inputs (FR-RCT-2 risk) | `build_assess` reports **both** per-stage cascade readiness AND the 4 value domains. | FR-RCT-2 confirmed feasible; **RCT stage-state is a thin cursor** over `build_assess` (piece N3), not a second readiness computation. |
| `derive` writes the schema | `derive` **returns a candidate** (`unratified` header); the CLI is the sole writer. The `.prisma` human-privilege write is `generate contract --promote`. | FR-RCT-4/OQ-2 resolved: `.prisma` writes via `generate contract --promote`, distinct from the `inputs/` capture seam. |

**Resolved open questions:**
- **OQ-1 → the proposal model exists & is reusable** (origin/main); extending it to `schema`/`manifest`/
  `value-input` kinds is a **medium** per-kind addition (builders + dispatch + apply path). Still riskiest.
- **OQ-2 → two write seams:** `.prisma` via `generate contract --promote`; `inputs/*.yaml` via the
  `capture.py` per-key merge; both confined/atomic via the safe-writer.
- **OQ-5 → neither `derive` nor `generate contract` is conversational.** From-scratch path = interview →
  requirements prose brief → `generate contract --promote` (piece **N2**).
- **OQ-6 → stage-state is net-new but thin** — a `.startd8/` cursor over the `build_assess` stage map (N3).
- **OQ-3 → prose-authoring is the default front door** (round-trips via the authoring contract); direct-
  manifest only where an extractor doesn't exist. *(Still partly open per manifest — see §5.)*
- **OQ-4, OQ-7, OQ-8 → STILL OPEN** (web stage-rail shape; cascade-readiness threshold; interview spend).

---

## 1. Problem Statement

The deterministic cascade is the SDK's crown jewel — one `schema.prisma` + a handful of manifests
projects into a working all-Python app for `$0`. But **getting to a complete, correct input surface
from a blank start is the hard part**, and today it's a disconnected, expert-only assembly job:

| Capability | Today | Gap |
|-----------|-------|-----|
| **Data-model contract** (`schema.prisma`) | Hand-authored, or derived from a PRD via `concierge/derive` (a discrete action) | No guided, conversational path that *interviews* a non-expert and co-authors the schema from scratch |
| **Assembly manifests** (app/pages/views/forms/flows/imports) | Authored as prose sources that deterministically extract (`manifest_extraction`, authoring-contract §2.2–2.7) or hand-written YAML | No orchestration that walks a user through authoring *each* manifest in dependency order |
| **Value inputs** (conventions/build-prefs/business-targets/observability) | Instantiated as templates by Concierge `instantiate`; filled by hand or pre-filled (`estimate`/`config-default`) | Welcome Mat surfaces readiness + downloads + a chat that can *propose* friction/instantiate — but nothing drives the user to *fill the whole surface* |
| **Readiness → run** | `build_assess`/`build_readiness` report gaps; `startd8 wireframe` previews; the cascade runs when inputs exist | No experience that closes the loop: gap → co-author → confirm → re-assess → … → run |
| **Agentic assist** | `/concierge/chat` (Welcome Mat 2.0) proposes friction/instantiate via the read-effect `propose_action` → human-confirm model | The proposal model isn't yet a *build-the-whole-app* driver; `derive-contract` is explicitly **out of scope** there (WM2 NR-1) |

There is **no single experience that takes a user from "I have an idea" to "the cascade can build my
app."** The pieces exist (derive, extractors, the cascade, the propose-confirm seam, readiness,
download); nothing **sequences** them with an agent in the lead and the human in control.

**What should exist:** a staged, resumable, **agentic Red Carpet Treatment** — web (Welcome
Mat-hosted) and CLI, one engine — that (a) interviews the user and **co-authors the data-model
contract**, then (b) walks the **dependency-ordered** surface (manifests → value inputs → placeholder
content), the agent **drafting each input as a proposal** the human **confirms at human privilege**,
(c) continuously **re-assesses readiness** and (d) when the surface is complete, hands off to the **`$0`
cascade** — bracketed by the two human bookends (DATA MODEL up front, RETROSPECTIVE after each
increment).

---

## 2. Guiding Principles

- **P1 — Orchestrate, don't re-implement.** RCT is a *conductor*. The schema co-authoring rides
  `concierge/derive`; manifests ride the authoring-contract extractors (`manifest_extraction`); value
  inputs ride `build_instantiate_plan` + the input templates; writes ride the `propose_action` →
  `apply_proposal` proposal/confirm seam; readiness rides `build_assess`/`build_readiness`; the build
  rides the `$0` cascade. RCT adds **sequencing, interview prompts, and stage state** — no new
  extractor, generator, write engine, or readiness computation.
- **P2 — The loop proposes; the human applies (inherited, non-negotiable).** Every RCT write is a
  proposal the agent drafts and a foreground human confirms at human privilege (web same-origin POST +
  CSRF + loopback + one-time-intent; or CLI explicit confirm). The agentic loop **never** writes,
  never runs the cascade autonomously, and is never reachable as a write over MCP.
- **P3 — Honor the two human bookends.** The **DATA MODEL** is the front bookend — the contract
  everything derives from — so RCT *starts* there with deliberate human confirmation, never auto-deriving
  past it. The **RETROSPECTIVE** is the back bookend — after each increment RCT reflects and feeds
  lessons back (to the data model / requirements / the next stage).
- **P4 — Respect the four buckets.** RCT produces buckets **1–3** inputs (the application skeleton's
  contract + manifests = bucket 1's *inputs*; placeholder copy + static test data = bucket 2; the
  integration glue = bucket 3). It **never authors bucket 4** — the user's/company's real content. The
  cascade itself is bucket-1, `$0`, **Python-only** (the deterministic path); RCT targets that path.
- **P5 — Readiness-driven, resumable.** RCT is not a fixed wizard; it's a **gap-closing loop** keyed to
  the live readiness/assess state. It can be left and resumed; it always drives to the next real gap.

---

## 3. Requirements

### A. The experience & orchestration

- **FR-RCT-1 — A named, staged Red Carpet flow.** A single agentic experience that sequences a
  greenfield user through the **complete input surface** to cascade-readiness, present in **both** web
  (Welcome Mat-hosted) and CLI, over **one** shared agentic engine + the propose-confirm seam.
- **FR-RCT-2 — Readiness-driven stage map.** RCT derives its current stage and "next gap" from the
  existing `build_assess`/`build_readiness`/wireframe state (never a second readiness computation), so
  it is **resumable** and always advances the largest real gap. Stages (dependency-ordered): **DATA
  MODEL → manifests (pages/views/forms/flows/imports) → value inputs → placeholder content →
  readiness/run**.
  - **Acceptance (CRP R1-F6 — cursor staleness & concurrency) ✅ DELIVERED (N3):** the `.startd8/` stage cursor (N3) is a
    **hint, not a source of truth** — on resume it is **reconciled against live `build_assess`** (a
    hand-edit between stages must move RCT to the correct live gap). Concurrent RCT sessions on the same
    tree (the repo's multi-worktree/multi-agent reality) must not corrupt the cursor (advisory lock or
    last-writer-wins **with detection**). *Verify:* hand-edit an input mid-flow → resume reconciles;
    two sessions advance → no corrupt cursor.
- **FR-RCT-3 — Discoverable entry** *(CLI ✅ DELIVERED — agentic interview loop)*. CLI:
  `startd8 kickoff red-carpet` (read-only staged status) and `--agent <spec>` (the conversational
  interview loop — stage-aware chat that proposes each input; the human confirms every write via
  `apply_proposal`). Web: a "Build my app" stage-rail entry on `/concierge/chat` (OQ-4) — **pending**.
  Bootstrap-instantiate-if-absent — pending (the loop currently assumes/scaffolds the package via the
  `instantiate` proposal kind).

### B. Data model — the front human bookend

- **FR-RCT-4 — Interview-and-draft the data-model contract** *(reframed by planning)*. The agent
  conducts a **domain interview** and drafts a **requirements/PRD prose brief** (entities, fields, plain
  types, relationships in the authoring-contract §2.1 grammar) as a **proposal**; the human confirms;
  then `startd8 generate contract` (prose→prisma) produces `schema.prisma` and the human ratifies it
  with **`--promote`** (the sole `.prisma` write). *(Planning: neither `generate contract` nor
  `concierge/derive` is conversational — `derive` reverse-derives from existing Pydantic models, a
  **side door** for users who already have them.)* The agent originates the draft; the human owns the
  ratification. This is piece **N2**.
  - **Acceptance (CRP R1-F4 — two ratification gates):** the **prose-brief confirm** and the
    **`generate contract --promote`** are **distinct** human gates — confirming the brief writes **no**
    `.prisma`; only the separate promote action does. *Verify:* filesystem has no `.prisma` after
    brief-confirm; only promote writes it.
  - **Acceptance (CRP R1-F12 — no lossy promote) ✅ DELIVERED (N2):** the schema quality is bounded by
    `generate contract`'s prose grammar; RCT must **surface unparseable/ambiguous brief fragments back
    to the human** rather than promoting a degraded schema (honors P3). *(N2: the `schema` apply path
    rejects with `schema_gate_failed`/`schema_lossy` and never promotes when the gate fails or a field
    is unrenderable.)* *Verify:* a brief with an unsupported construct → RCT reports the gap, does not
    promote.
- **FR-RCT-5 — Data model gates the rest.** The schema is the **first** stage and a **gate**: manifests
  derive from it, so RCT will not drive manifest stages until a confirmed `schema.prisma` exists. This
  enforces "data model = the front bookend" rather than letting generation invent a contract.
- **FR-RCT-16 — Schema-revision drift (CRP R1-F5) ✅ DELIVERED (N2, parity-based).** A **second**
  promote after a live contract exists must **detect** the change and **block** (typed `schema_drift`)
  unless the human re-confirms with `acknowledge_drift` — never a silent revision. *(N2: the `schema`
  apply path runs `emit_schema_draft(live_text=…)`; any `parity_drift` blocks promotion by default.
  This parity-based block **subsumes** the manifest-orphan case — any contract change is caught — for
  v1; a finer manifest-orphan-specific message is a later refinement.)* *Verify:* promote v1 → promote
  v2 with an entity removed → blocked as `schema_drift`; `acknowledge_drift` proceeds
  (`test_red_carpet_schema.py`).

### C. Manifests & value inputs — derive from the contract

- **FR-RCT-6 — Co-author each input via the authoring contract.** For every manifest
  (`pages`/`views`/`forms`/`flows`/`imports`, `app`/scaffold) and value input
  (`conventions`/`build-preferences`/`business-targets`/`observability`), the agent **drafts the
  authoring-contract prose source** as a proposal; the human confirms; the **existing extractor**
  (`manifest_extraction`) turns prose → manifest. RCT supplies the interview + the draft, not a new
  extractor.
  - **Acceptance (planning N1 — the project-tree manifest writer):** `extract_manifests` returns
    manifests **in memory** (round-trip-gated) and **no command writes them into the project's
    `docs/kickoff/inputs/*.yaml`** today (only a workflow → run-dir). RCT must add an orchestration that
    maps each extracted manifest → its project destination and writes it through the **existing**
    `apply_write_plan` confinement/atomic seam (mirroring `build_instantiate_plan`). This is RCT's
    biggest genuinely-new piece — pure plumbing over existing extraction, no new extractor.
  - **Acceptance (CRP R1-F2 — dest confinement, CRITICAL) ✅ DELIVERED (N1):** the write **destination is derived
    server-side from the manifest filename**, **never** taken from the proposal payload; every resolved
    `realpath` is asserted to live **under `docs/kickoff/inputs/`** (reject `..`, absolute paths,
    symlink escape). *Verify:* a proposal with `dest=../../etc/x.yaml` / absolute / symlink → apply
    rejected; the filename→path map is fuzzed against a realpath-under-root assertion.
  - **Acceptance (CRP R1-F3 — overwrite & atomicity) ✅ DELIVERED (N1):** **no-clobber by default** of an existing
    `inputs/*.yaml` that differs from the last RCT-written content; overwrite only on an explicit human
    **"replace"** confirm; the multi-file write is **all-or-nothing** (staged, atomic — rollback on any
    per-file failure). *Verify:* a pre-edited manifest is not overwritten without replace-confirm; an
    injected mid-write failure leaves **no** file mutated.
- **FR-RCT-7 — Placeholder content only (bucket boundary).** RCT generates **placeholder/bucket-2**
  content prose and static test data sufficient to prove the app works, and then **explicitly hands
  off** real (bucket-4) content to the user/company. RCT never authors real value content.
  - **Acceptance (CRP R1-F10 — measurable boundary):** placeholder content is **structurally valid but
    semantically inert** (templated/lorem values carrying a `placeholder: true`-equivalent marker), and
    RCT emits an explicit **hand-off notice enumerating the fields the user must replace** with real
    (bucket-4) content. *Verify:* generated placeholders carry the inert marker; the hand-off notice
    lists the user-owned fields.

### D. The write model — propose, then human-apply

- **FR-RCT-8 — Every write is propose-then-human-apply.** RCT reuses the `propose_action` (read-effect)
  → `apply_proposal` (human-privilege) proposal/confirm model: the agent drafts a proposal for each
  input; the human applies it (web same-origin+CSRF+loopback+one-time-intent, or CLI confirm). The loop
  never applies; MCP never writes.
- **FR-RCT-9 — Proposal kinds span the surface (per-kind apply paths).** Extend the existing
  `ProposedAction`/`apply_proposal` model (today `friction`/`instantiate`) with the RCT kinds, each
  routed to its **correct existing write seam** (planning: the kinds are bespoke per-kind apply, not a
  registry — so each is a builder + dispatch branch + apply path):
  - `schema` → `generate contract --promote` (the `.prisma` write),
  - `manifest` → the **N1 project-tree manifest writer** (FR-RCT-6),
  - `value-input` → **`capture.py`** (per-key merge-splice into `inputs/*.yaml`, allow-list gated) —
    **not** a whole-file write.
  Each proposal **re-validates on apply** (extractor/grammar/round-trip conformance), never trusting the
  loop's draft blindly; the human applies at human privilege.
  - **Acceptance (CRP R1-F1 — the closed-allow-list floor, CRITICAL) ✅ DELIVERED 2026-06-29:** `apply_proposal` MUST **reject
    any `kind` not in the closed enumerated set** {`friction`,`instantiate`,`schema`,`manifest`,
    `value-input`}, and the agent-facing tool registry MUST expose **only read/propose tools — no
    apply/write tool is registered for the loop**. *Verify:* dispatching an unknown `kind` is rejected;
    a registry introspection test asserts zero apply-capable tools (the inherited "loop never writes"
    floor, under the richer vocabulary).
  - **Acceptance (CRP R1-F11 — per-kind re-validation at human privilege):** re-validation runs **after
    human confirm, not in the loop**, and is **≥ generation-time strictness** per kind — `schema` →
    contract grammar + `--promote` parse; `manifest` → extractor round-trip + dest-confinement (FR-RCT-6);
    `value-input` → `capture.py` allow-list + per-key merge. A draft that fails re-validation is
    **rejected, not partially applied**. *Verify:* a draft that passes propose-time but violates the
    extractor contract is rejected at apply.

### E. Readiness → cascade handoff

- **FR-RCT-10 — Live readiness + run handoff.** RCT surfaces the live readiness/wireframe throughout
  and, when the surface is complete, **offers to run the `$0` cascade** (`generate
  backend`/`scaffold`/`views`/`frontend`). RCT **orchestrates the inputs**; the cascade is the separate
  deterministic `$0` step. RCT never claims to *generate content* (bucket-4) and never makes the build a
  loop-autonomous action.
  - **Acceptance (CRP R1-F7 — testable offer predicate, resolves OQ-7) ✅ DELIVERED (N3):** the cascade offer is gated by
    a **named, checkable readiness predicate** — `cascade_offerable = schema_confirmed AND
    app_manifest_present AND ≥1 page AND ≥1 view` (the minimal viable subset) — and when the offer is
    **withheld**, RCT names **which** gates are unmet. *Verify:* subset present → offer appears; remove
    one gate → offer withheld naming the specific unmet gate.
- **FR-RCT-11 — Wireframe checkpoint.** Before offering the cascade, RCT shows the `startd8 wireframe`
  `$0` pre-generation summary ("here's the app we'll build") as the human go/no-go checkpoint.

### F. Retrospective — the back human bookend

- **FR-RCT-12 — Per-increment reflection.** After each confirmed stage/increment, RCT runs a short
  **reflection** — what was decided, what's still ambiguous, what should feed back to the data model or
  earlier inputs — and offers to log friction (reusing the existing friction path). This operationalizes
  the RETROSPECTIVE bookend; it is advisory, never a gate.

### G. Boundaries & cross-cutting

- **FR-RCT-13 — Cost posture.** The agentic interview is the **one paid surface** (LLM); extraction, the
  cascade, readiness, and wireframe are `$0`. RCT inherits the chat hardening from Welcome Mat 2.0
  (per-session budget caps, turn cap, message cap, graceful degradation, mode gate) — a `preview`/
  `inspect` serve disables the paid interview.
  - **Acceptance (CRP R1-F8 — whole-build ceiling, resolves OQ-8):** a from-scratch build spans many
    paid turns across sessions, so the per-session envelope (FR-WM2-9a) is **insufficient**. RCT adds a
    **cross-session whole-build spend ceiling** + a **resumable checkpoint**: on exhaustion it **pauses
    and resumes (never silently stops)**, and **resume does not re-spend completed stages**. *Verify:* a
    build crossing the per-session cap checkpoints and resumes; cumulative spend is bounded; completed
    stages are not re-charged.
- **FR-RCT-14 — Observability.** RCT emits stage-funnel events (`red_carpet_started`, `stage_entered`,
  `input_proposed`, `input_confirmed`, `stage_completed`, `cascade_offered`) with bounded attributes
  (stage/kind/code, **no** interview text, no raw paths) — registered in the kickoff telemetry module.
  - **Acceptance (CRP R1-F9 — the confirm→apply boundary is visible):** extend the event set with
    `input_applied`, `apply_rejected` (bounded reason `code`), `cascade_run`, and `budget_exhausted` —
    the security- and cost-relevant moments the current list omits. Each emits with the bounded
    attribute allowlist (no interview text, no raw paths). *(Plan gap: FR-RCT-14 had no plan task — added
    in the plan §7.)*
- **FR-RCT-15 — Parity by shared construction.** Web and CLI run the **same** RCT engine, stage map, and
  propose-confirm seam; surface differences are limited to the authorization gate (web CSRF/loopback vs
  CLI confirm), as in Welcome Mat 2.0.

---

## 4. Non-Requirements

- **NR-1 — No real (bucket-4) content authoring.** RCT produces placeholder content + static test data
  only; the user's/company's real value content is theirs.
- **NR-2 — No re-implementation.** RCT does not re-implement `concierge/derive`, the
  `manifest_extraction` extractors, the `$0` cascade, the proposal/confirm write engine, readiness, or
  the template instantiate — it sequences them.
- **NR-3 — No autonomous / loop writes; no MCP writes.** The agentic loop never applies a write or runs
  the cascade; MCP stays preview/read-only.
- **NR-4 — Not polyglot.** RCT targets the **deterministic, Python-only** generation path. The
  LLM-driven polyglot path (Prime/MicroPrime microservice fleets) is out of scope.
- **NR-5 — Not a benchmark / not Prime.** RCT is an onboarding/build experience, not the Prime/Artisan
  construction pipeline or the model benchmark.

---

## 5. Open Questions

*All 8 resolved (5 by planning, 3 by CRP R1) — see §0 + the Acceptance criteria. Retained for the record.*

- **OQ-1 — RESOLVED → the proposal model exists & is reusable** (`origin/main`); extending to
  `schema`/`manifest`/`value-input` kinds is a **medium** per-kind addition (builder + dispatch + apply
  path). Still the riskiest piece.
- **OQ-2 — RESOLVED → two confined write seams:** `.prisma` via `generate contract --promote`;
  `inputs/*.yaml` via the `capture.py` per-key merge. Both atomic/confined through the safe-writer.
- **OQ-5 — RESOLVED → neither producer is conversational.** From-scratch path = interview →
  requirements prose brief → `generate contract --promote` (piece N2); `derive` (Pydantic→prisma) is a
  side door.
- **OQ-6 — RESOLVED → stage-state is net-new but thin** — a `.startd8/` cursor over the `build_assess`
  stage map (piece N3), not a second readiness computation.
- **OQ-3 — PARTLY RESOLVED → prose-authoring is the default** front door (round-trips via the authoring
  contract); direct-manifest only where no extractor exists. Per-manifest specifics still open.
- **OQ-4 — RESOLVED (CRP R1-S10) → stage-rail extension of `/concierge/chat`** (+ `_ChatStore`), **not**
  a new `/red-carpet` web route — a separate route would fork/duplicate the hardened chat surface
  (cookie/budget/mode-gate). The web surface reuses the existing chat gate with no duplicated CSRF/mode
  logic. (CLI keeps `kickoff red-carpet`.)
- **OQ-7 — RESOLVED (CRP R1-F7) → a named predicate** `cascade_offerable = schema_confirmed AND
  app_manifest_present AND ≥1 page AND ≥1 view` (FR-RCT-10), with unmet gates surfaced.
- **OQ-8 — RESOLVED (CRP R1-F8) → a cross-session whole-build spend ceiling + resumable checkpoint**
  (FR-RCT-13), distinct from the inherited per-session cap.

---

*v0.2 — Post-planning self-reflective update. P1 ("orchestrate, don't re-implement") **confirmed** —
RCT builds exactly **three** new pieces (N1 project-tree manifest writer, N2 interview→prose-brief→
`generate contract`, N3 `build_assess`-driven stage-state/driver); everything else rides existing
seams. Corrections: FR-RCT-4 reframed (no conversational schema producer exists → interview→prose-brief
path); FR-RCT-6 gained the N1 writer (the real gap); FR-RCT-9 split into per-kind apply paths
(schema→`generate contract --promote`, manifest→N1, value-input→`capture.py`). 1 build-env prerequisite
surfaced (**RCT must branch from `origin/main`**, which the planning Explore pass — reading the stale
primary worktree — initially missed). 5 of 8 open questions resolved. Ready for CRP review before
implementation.*

*v0.3 — Post-CRP R1 (reviewer claude-opus-4-8-1m; 12 F + 11 S suggestions, write-model-weighted).
Policy: **accept all; none rejected.** All 12 requirements suggestions merged as consolidated
`Acceptance (CRP R1)` criteria — the two **critical** security items (R1-F1 closed apply-side kind
allow-list + no loop-write registry; R1-F2 server-derived/confined manifest dest) plus N1 overwrite &
atomicity (F3), two-step schema ratification (F4) + no-lossy-promote (F12), the new **FR-RCT-16**
schema-revision drift (F5), cursor staleness/concurrency (F6), the testable cascade predicate (F7,
resolves OQ-7), the whole-build spend ceiling (F8, resolves OQ-8), confirm→apply telemetry (F9),
measurable bucket-2 boundary (F10), and per-kind apply-time re-validation (F11). The 3 remaining open
questions (OQ-4 web shape, OQ-7, OQ-8) are **resolved** (OQ-4 → stage-rail reuse via R1-S10). The 11
plan suggestions are folded into the plan (v0.2): sequencing re-ordered so the schema gate precedes N1
(S4), a new §7 Validation Strategy (S5), and per-piece confinement/atomicity/allow-list/drift tasks.
Dispositions in Appendix A; R1 rounds verbatim in Appendix C. Ready for implementation (N-pieces
sequenced; branch from `origin/main`).*

---

## Appendix A — Accepted (with where merged)

> Triage R1 (orchestrator, 2026-06-29). **All 12 requirements suggestions accepted; none rejected.**
> Merged as consolidated `Acceptance (CRP R1)` criteria on the named FRs.

| ID | Suggestion | Merged into |
|----|------------|-------------|
| R1-F1 | Closed apply-side `kind` allow-list + registry exposes only read/propose (the loop-never-writes floor) | FR-RCT-9 acceptance |
| R1-F2 | Manifest dest server-derived + confined under `docs/kickoff/inputs/` (reject `..`/abs/symlink) | FR-RCT-6 acceptance |
| R1-F3 | N1 overwrite semantics (no-clobber default, replace-confirm) + multi-file atomicity | FR-RCT-6 acceptance |
| R1-F4 | Two distinct ratification gates (brief-confirm ≠ `--promote`) | FR-RCT-4 acceptance |
| R1-F5 | Schema-revision drift after manifests derive | **new FR-RCT-16** |
| R1-F6 | Cursor staleness reconcile vs live `build_assess` + concurrency safety | FR-RCT-2 acceptance |
| R1-F7 | Testable cascade-offer predicate (resolves OQ-7) | FR-RCT-10 acceptance / OQ-7 |
| R1-F8 | Cross-session whole-build spend ceiling + resumable checkpoint (resolves OQ-8) | FR-RCT-13 acceptance / OQ-8 |
| R1-F9 | `input_applied`/`apply_rejected`/`cascade_run`/`budget_exhausted` telemetry | FR-RCT-14 acceptance |
| R1-F10 | Measurable bucket-2 boundary (inert marker + hand-off notice) | FR-RCT-7 acceptance |
| R1-F11 | Per-kind apply-time re-validation at human privilege, ≥ propose-time strictness | FR-RCT-9 acceptance |
| R1-F12 | No lossy promote — surface unparseable brief fragments | FR-RCT-4 acceptance |

*Plan-side dispositions (R1-S1…S11) are recorded in `RED_CARPET_TREATMENT_PLAN.md` Appendix A.*

## Appendix B — Rejected (with rationale)

<!-- F-<n> / S-<n> — <suggestion> → REJECTED; <why>. -->
*None.* All R1 suggestions were grounded in real code, strengthened the inherited boundaries (never
re-litigated them), and were mutually consistent — accepted in full.

## Appendix C — Incoming review rounds

<!-- #### Review Round R{n} — <model-id> — <UTC date> -->

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-29

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-29 21:05:00 UTC
- **Scope**: Requirements quality for the RCT write-model extension (FR-RCT-9 per-kind apply paths), the N1 project-tree manifest writer confinement (FR-RCT-6), the N2 data-model bookend (FR-RCT-4/5), and the open forks OQ-4/7/8. Settled boundaries (loop-never-writes, MCP read-only, bucket separation, reuse-don't-reimplement) are assumed, not re-litigated.

**Executive summary (top risks / gaps):**

1. **FR-RCT-9 is the security crux and is under-specified on the apply-side allow-list.** It enumerates three new kinds but does not state that the *apply* dispatcher must reject any `kind` not on a closed allow-list, nor that the agent-facing registry exposes only read/propose tools — the invariant the focus file (§A) calls the floor.
2. **No requirement enforces `dest` confinement for the `manifest` kind.** FR-RCT-6's N1 writer "writes through `apply_write_plan`" but no FR states the destination is server-derived (not proposal-supplied) or path-traversal/zip-slip validated — the single highest-severity gap.
3. **Overwrite/clobber semantics of N1 are unspecified** (focus §B): does N1 overwrite a hand-edited `inputs/*.yaml`? No-clobber vs overwrite-on-confirm, and multi-file atomicity, have no acceptance criterion.
4. **FR-RCT-4 conflates two human ratifications into one** (focus §C): the prose-brief confirm and the `--promote` schema write are distinct gates; the requirement reads as if one confirm covers both.
5. **Schema revision after manifests derive from v1 has no requirement** (drift/regeneration) — a v2 `--promote` can silently strip manifests of their basis.
6. **FR-RCT-2 resumability lacks a staleness/concurrency acceptance criterion** — the `.startd8/` cursor (N3) vs hand-edits-between-stages and the documented multi-worktree/concurrent-session reality.
7. **OQ-7 (cascade-readiness threshold) is untestable as written** — "full surface vs minimal viable subset" needs a concrete, checkable gate.
8. **OQ-8 (whole-build spend) — no requirement for a build-level spend ceiling or resumable checkpoint**; FR-RCT-13 inherits only the *per-session* envelope, which a multi-session from-scratch build escapes.
9. **FR-RCT-14 telemetry omits `input_applied` / failure / budget-exhaustion events** — the confirm→apply boundary and its denials are invisible.
10. **FR-RCT-7 "sufficient to prove the app works" is unmeasurable** — no acceptance criterion separates bucket-2 placeholder from a slide toward bucket-4.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | critical | In FR-RCT-9, add an explicit acceptance criterion: the `apply_proposal` dispatcher MUST reject any `kind` not in a closed, enumerated allow-list (`friction`,`instantiate`,`schema`,`manifest`,`value-input`), and the agent-facing tool registry MUST expose only read/propose tools — no apply/write tool is registered for the loop. | Adding kinds widens the loop's vocabulary; without a closed allow-list + a registry assertion, a future kind or a mis-registered tool can become a loop-reachable write, breaching the inherited "loop never writes" floor (focus §A). | FR-RCT-9, new bullet after the per-kind list | Unit test: dispatch an unknown `kind` → rejected; introspection test asserts the registry exposes zero apply-capable tools. |
| R1-F2 | Security | critical | In FR-RCT-6 Acceptance (N1), require that the manifest write **destination is derived server-side from the manifest filename**, never taken from the proposal payload, and that every resolved path is asserted to live under `docs/kickoff/inputs/` (reject `..`, absolute paths, symlinks). | Today no FR forbids a `manifest` proposal whose `dest` escapes the inputs dir (zip-slip). This is the single biggest new attack surface the focus file (§A/§B) flags; "rides apply_write_plan" is necessary but the dest-derivation rule must be a stated requirement, not assumed. | FR-RCT-6, Acceptance sub-bullet | Test: proposal with `dest=../../etc/x.yaml` or absolute path → apply rejected; fuzz filename map against a realpath-under-root assertion. |
| R1-F3 | Data | high | FR-RCT-6 N1 must state **overwrite semantics**: default **no-clobber** of an existing `inputs/*.yaml` that differs from the last RCT-written content; overwrite only on an explicit human "replace" confirm; and the multi-file write must be **all-or-nothing** (staged, atomic). | A from-scratch loop will re-enter stages; silently clobbering a hand-edited manifest destroys user work, and a partial multi-file write leaves the input surface inconsistent (focus §B). | FR-RCT-6, new Acceptance sub-bullet | Test: pre-place a hand-edited manifest, run N1 → no overwrite without replace-confirm; inject a mid-write failure → no file changed (atomic rollback). |
| R1-F4 | Validation | high | Split FR-RCT-4 into **two explicit ratification gates**: (1) human confirms the prose brief (proposal apply), and (2) human runs `generate contract --promote` as a **separate** confirm to write `.prisma`. State that brief-confirm does NOT imply promote. | As written, FR-RCT-4 reads as a single confirm; the focus file (§C) asks whether `--promote` needs its own gate distinct from the prose-brief confirm. Two-step ratification keeps the DATA MODEL bookend deliberate. | FR-RCT-4, reword the confirm/ratify clause | Acceptance: confirming the brief leaves no `.prisma` on disk; only a distinct promote action writes it; assert via filesystem state between the two steps. |
| R1-F5 | Data | high | Add a requirement (FR-RCT-5 or new) for **schema revision after downstream manifests exist**: a second `--promote` must detect that manifests derive from the prior schema and either block, warn, or trigger re-assessment/regeneration — never silently invalidate them. | The bookend can be revised; without a drift rule, v2 schema + stale manifests pass readiness while being semantically broken (focus §C). | New FR after FR-RCT-5, or FR-RCT-5 extension | Test: promote schema v1 → derive a manifest → promote v2 with an entity removed → RCT flags the now-orphaned manifest. |
| R1-F6 | Risks | high | FR-RCT-2/OQ-6: add an acceptance criterion for **cursor staleness & concurrency** — the `.startd8/` stage cursor must be validated against live `build_assess` on resume (filesystem is source of truth; cursor is a hint), and concurrent RCT sessions on the same project tree must not corrupt it (advisory lock or last-writer-wins with detection). | The repo runs concurrent multi-worktree/multi-vendor agents (focus §D, build-env note); a stale or co-written cursor can drive the user to the wrong stage or skip a real gap. | FR-RCT-2, new sub-bullet; cross-ref OQ-6 | Test: hand-edit an input between stages, resume → cursor reconciles to live assess; two sessions advance → no corrupt cursor. |
| R1-F7 | Validation | medium | Make OQ-7 testable: replace "full surface vs minimal viable subset" with a **named, checkable readiness predicate** (e.g. `cascade_offerable = schema_confirmed AND app_manifest_present AND ≥1 page AND ≥1 view`), and require RCT to surface *which* gates are unmet when the offer is withheld. | An open prose fork is not implementable; the cascade-offer gate is a behavioral decision that needs a concrete predicate to test (focus §D). | OQ-7, and a new acceptance line under FR-RCT-10/11 | Test: with subset present → offer appears; remove one gate → offer withheld with the specific unmet gate named. |
| R1-F8 | Ops | high | FR-RCT-13 + OQ-8: add a **whole-build (cross-session) spend ceiling and resumable checkpoint** requirement, distinct from the inherited per-session cap (FR-WM2-9a). State the build-level budget, what happens on exhaustion (pause + resume, never silent stop), and that resume does not re-spend completed stages. | A from-scratch build is many turns across sessions; the per-session envelope cannot bound total spend (focus §E). Without a build ceiling, a long build can blow budget incrementally. | FR-RCT-13 extension; resolve OQ-8 | Test: simulate a build that crosses the per-session cap → it checkpoints and resumes; assert cumulative spend is bounded and completed stages are not re-charged. |
| R1-F9 | Ops | medium | Extend FR-RCT-14 telemetry with `input_applied`, `apply_rejected` (with bounded reason code), `cascade_run`, and `budget_exhausted` events. | The confirm→apply boundary and its denials/exhaustion are the security- and cost-relevant moments; the current event list stops at `cascade_offered` and omits the apply outcome. | FR-RCT-14, extend the event enumeration | Verify each event emits with bounded attributes (no interview text, no raw paths) in an integration trace. |
| R1-F10 | Validation | medium | Give FR-RCT-7 a measurable bucket-2 boundary: placeholder content must be **structurally valid but semantically inert** (e.g. lorem/templated values, flagged `placeholder: true` or equivalent) and RCT must emit an explicit hand-off notice listing which fields the user must replace with real (bucket-4) content. | "Sufficient to prove the app works" is unmeasurable and risks RCT drifting into authoring real content (NR-1). A marker + hand-off list makes the boundary testable. | FR-RCT-7, add acceptance criterion | Test: generated placeholders carry the inert marker; hand-off notice enumerates the user-owned fields. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F11 | Security | high | FR-RCT-9 "re-validates on apply" must specify **what re-validation runs per kind** and that re-validation executes at **human privilege after confirm**, not in the loop: `schema` → contract grammar + `--promote` parse; `manifest` → extractor round-trip + dest-confinement; `value-input` → `capture.py` allow-list + per-key merge. A draft that fails re-validation is rejected, not partially applied. | "Re-validates on apply" is asserted but unspecified; an adversarial draft could pass propose-time checks and smuggle a bad value into apply if re-validation is weaker than generation-time, or if it runs in the loop. | FR-RCT-9, expand the re-validation clause into a per-kind table | Per-kind negative test: a draft that round-trips at propose-time but violates the extractor contract → rejected at apply. |
| R1-F12 | Risks | medium | Add an explicit dependency-risk note that FR-RCT-4's reliance on `generate contract` (prose→prisma) means **the quality of the schema is bounded by the extractor's prose grammar coverage**; require RCT to surface unparseable/ambiguous brief fragments back to the human rather than promoting a lossy schema. | The reframed N2 path inherits `generate contract`'s parser limits; a silently lossy prose→prisma step would violate the "data model = deliberate bookend" principle (P3). | New sub-bullet under FR-RCT-4 | Test: a brief with an unsupported relationship construct → RCT reports the gap, does not promote a degraded schema. |

<!-- (Duplicate script-initialized review-log scaffold removed during R1 triage — the canonical
Appendix A/B/C are above; R1 is recorded under Appendix C.) -->
