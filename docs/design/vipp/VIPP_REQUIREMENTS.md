# VIPP (Very Important Project Person) Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-30
**Status:** Draft
**Owner:** neil-the-nowledgeable

> **One-line.** The VIPP is the **project-side negotiator/applier** counterpart to the SDK-side
> onboarding hosts (Concierge / Welcome Mat / Red Carpet). It is the **OBSERVED(project)-authority
> dual** of the existing **FDE** (`src/startd8/fde/`), which carries **MECHANISM(sdk) authority**.
> Where the FDE is the SDK's insider *posted into the project*, the VIPP is the project's
> representative *facing the SDK*: it receives the hosts' proposals, evaluates them against project
> ground-truth, negotiates, and **applies accepted proposals at project human privilege**.

---

## Locked design decisions (pre-draft)

These were decided with the operator before drafting and frame every requirement below:

1. **Primary job — negotiator/applier.** The VIPP receives the hosts' proposals (manifests,
   schema, value-captures, friction, brief), decides on the project's behalf against project
   ground-truth, and applies at **project human privilege**. It is the active counterpart that
   drives the project side of kickoff — not merely a passive ground-truth oracle.
2. **Authority role — project (OBSERVED) authority; dual of the FDE.** Per
   [Tekizai-Tekisho](../../design-princples/TEKIZAI_TEKISHO_DESIGN_PRINCIPLE.md), the VIPP supplies
   the **OBSERVED (project)** half of a cross-boundary composition (what the project actually has,
   wants, and owns). The hosts supply the **MECHANISM (sdk)** half (what the cascade needs, what is
   `$0`, which kinds/manifests exist). VIPP output is a *composed*, source-labeled disposition —
   never a solo SDK-mechanism verdict.
3. **Transport — file-protocol first (FDE-style).** v1 communication is `vipp-*.{md,json}` files
   using **Keiyaku-contract-shaped, transport-agnostic** typed contracts (frozen dataclasses, JSON
   canonical / markdown derived, `PROTOCOL_VERSION` independent of SDK version). A synchronous A2A
   channel (or the ContextCore insight bus) is a **roadmap dependency**, not a v1 wiring target.
4. **Privilege — applies at PROJECT human privilege only.** The VIPP writes only through the
   existing confined/atomic propose→confirm seam over **closed kinds**. It never makes the *SDK*
   operate; reciprocally the hosts never make the *project* operate. The "CLI is sole writer" rule
   becomes "the VIPP is the project-side applier."
5. **Security — VIPP is untrusted to the Concierge.** The Concierge treats VIPP-originated content
   as an **external/untrusted agent**: it rides the existing prompt-injection fence, and every
   VIPP-sourced claim stays **source-labeled** so it cannot masquerade as SDK-mechanism authority.

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). A
> codebase sweep against the real Concierge/Red Carpet/FDE/Sapper seams revealed **5 corrections —
> 2 of them load-bearing**, enough to confirm the v0.1 draft carried the usual share of wrong
> assumptions (the loop working as intended). The single most important discovery: **the v0.1 design
> assumed a project-resident VIPP could read host proposals off disk; in fact proposals are
> in-memory-only by design, so the central new requirement is a *proposal-serialization seam* that
> does not exist today.**

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **FR-4:** the VIPP "ingests host proposals" — implying it can read pending `ProposedAction`s from disk under `.startd8/`/`docs/kickoff/`. | **Proposals are IN-MEMORY ONLY.** `ProposalBuffer` is a bounded (`_MAX=32`), session-scoped, in-process list with no `save`/`to_dict`/disk path (`kickoff_experience/proposals.py:4-5, 114-135`); built fresh per chat (`chat.py:330, 357`) and consumed only from the live object (`web.py:954/982`, `cli_kickoff.py:294/434`). Only *applied results* hit disk. **It is in-memory by design (security: bounded, session-scoped).** | **New FR-15 (proposal-serialization seam)** + **FR-16 (two-process file-mediated topology)**, and FR-4 rewritten to depend on them. This is the riskiest piece and a new persistence surface to confine — see OQ-9. |
| **FR-5 / FR-12:** the closed write kinds are `{friction, instantiate, schema, manifest, value-input}` (assumed from Red Carpet FR-RCT-9). | The real closed enum is **`PROPOSAL_KINDS = ("instantiate","friction","capture","schema","manifest","brief")`** — six kinds (`proposals.py:41`). There is **no `value-input` kind** (that is the Red Carpet *stage* literal `value_inputs`, `red_carpet.py:24`); the value-capture kind is **`capture`**, and **`brief`** (writes `docs/kickoff/REQUIREMENTS.md`) was omitted. The apply gate is `if action.kind not in PROPOSAL_KINDS` (`proposals.py:241-242`); each kind needs BOTH enum membership AND an explicit apply branch (`proposals.py:235-240`). | **FR-5/FR-12 corrected** to the real 6-kind enum. VIPP applies via `apply_proposal(project_root, action, *, config)` (`proposals.py:217`), which re-validates live. |
| **FR-7:** the VIPP builds its own "project ground-truth source map" (reads schema/manifests/models directly). | **Sapper already IS the project-ground-truth oracle** — "answers 'what does THIS project's codebase actually contain?'" (`sapper/ground_truth.py:1-23`), with a layered oracle stack (`ProjectKnowledgeOracle`/`ControlledCorpusOracle`/`CachingOracle`/`CompositeOracle`, built by `oracle_for_project(project_root)`, `:282-302`) and a `FrictionReport`→OBSERVED-`LabeledClaim` bridge (`sapper/fde_bridge.py:41-63`). | **FR-7 reframed to CONSUME, not re-implement** (OQ-7 → option b). VIPP's OBSERVED claims come from `oracle_for_project` / `FrictionReport` / `to_observed_claims`. Re-implementing would fork the ground-truth authority and create the cycle the bridge exists to avoid. |
| **FR-5:** "`WritePlan` … the confined/atomic writer." | **`WritePlan` is not a class** — it is a JSON-dict contract emitted by pure builders (`writes.py:82/214`); only `PlannedWrite` and `WriteResult` are dataclasses (`safe_write.py:46-66`). `apply_write_plan(project_root, writes, *, force)` enforces the guards (root-symlink reject, `..`/abs-path reconfine, `O_NOFOLLOW` TOCTOU-closed walk, clobber guard, atomic temp+`O_EXCL`+`os.replace`). | **FR-5 wording fixed.** VIPP rides `apply_proposal` (which routes to `apply_write_plan`/`apply_concierge_plan`/`promote_schema` per kind), not a `WritePlan` object. |
| **OQ-6:** unclear whether the VIPP reads the Concierge over MCP or only via files. | **The `startd8_concierge` MCP tool exposes `survey`/`assess` only** (`READ_ACTIONS`, `core.py:27`), is `readOnlyHint=True` and never writes (`startd8_mcp.py:3151-3191`); `propose_action`/`ProposalBuffer` are **not on the MCP surface at all** (only in the in-process chat, `chat.py:258`). | **OQ-6 resolved.** Over MCP a VIPP gets only surveys/assessments (at most a preview plan dict) — **never proposals**. Proposals must come through the FR-15 file seam. MCP is an optional read enrichment, not the proposal channel. |

**Resolved open questions:**
- **OQ-1 → Separate package `src/startd8/vipp/`** mirroring `fde/`/`sapper/`, with `cli_vipp.py` (Typer
  sub-app) registered via `app.add_typer(vipp_app, name="vipp")` near `cli.py:1248-1253`. Different
  authority role ⇒ different home (FDE's OQ-1 logic).
- **OQ-2 → No authority tension.** Authority is about *which artifacts adjudicate a claim*, not where
  the code lives. The VIPP brain ships as SDK code but draws its authority from *project* artifacts
  (Sapper/oracle reads), labeling its claims OBSERVED(project). Mirrors the FDE (SDK code, but
  authority sourced from SDK mechanism → MECHANISM label).
- **OQ-3 → Human-gated apply in v1** (FR-16). VIPP emits dispositions (ACCEPT/REJECT/COUNTER); an
  explicit human confirm precedes any write (surprise-write control, à la the FDE's deferred
  auto-launch). Autonomous apply over a restricted kind subset is opt-in/roadmap.
- **OQ-5 → Filesystem confinement is the v1 trust boundary.** v1 transport is local files within one
  project tree, so no network identity/bearer-token is needed; the `safe_write` confinement guards
  are the boundary. A2A bearer-token/agent-card auth is deferred with the A2A transport (FR-14).
- **OQ-6 → File seam, not MCP** (see table). MCP `survey`/`assess` is optional read enrichment only.
- **OQ-7 → Consume Sapper** (option b): VIPP uses `oracle_for_project`/`FrictionReport`/
  `to_observed_claims` as its OBSERVED ground-truth input; it does not subsume or fork Sapper.
- **OQ-8 → No disk seam exists → build one** (FR-15). The host serializes its pending
  `ProposedAction`s to a confined project-local inbox; VIPP reads it and writes dispositions back.

**New open questions surfaced by planning:**
- **OQ-9.** The FR-15 seam adds a *persistence surface* to data that is in-memory-by-design today.
  Does serializing the `ProposalBuffer` weaken the host's security posture (bound, session-scope,
  no-disk)? Needs a confinement + retention design (CRP-worthy).
- **OQ-10.** `ProposedAction.params` + `base_sha` may carry project content; does the inbox need the
  FDE's `redaction` pass before serialization?

---

## 1. Problem Statement

The SDK ships a full **SDK-side onboarding stack** — the **Concierge** (role/engine: survey, assess,
instantiate-kickoff, log-friction, derive-contract), the **Welcome Mat** (served readiness surface +
downloads + chat), and **Red Carpet** (the orchestration layer that walks a greenfield user from
nothing to a complete kickoff input surface). All three enforce **"assist, not operate"**: the
agentic loop never writes; it emits **proposals** (`ProposedAction`); a **human applies** at human
privilege, and today **the CLI is the sole writer**.

On the **project side**, there is **no resident agent** that represents the project's interests to
these hosts. The consuming project's own agent can call the Concierge's **read-only MCP tool**
(`survey`/`assess` only), but that is a one-directional read channel — there is no project-authority
endpoint that (a) speaks for what the project actually *has/wants/owns*, (b) *receives and
negotiates* the hosts' proposals, and (c) *applies* accepted proposals at the project's own human
privilege. Crucially, the proposals themselves never leave the host's memory (§0), so today nothing
*could* receive them out-of-process.

The **FDE** (`src/startd8/fde/`) already proved out the symmetric machinery for "an agent that
carries one party's authority across the project↔SDK boundary without contaminating the other
party's facts" — but the FDE carries the **SDK's** authority *into* the project. The VIPP is the
**missing dual**: the **project's** authority *facing* the SDK.

### Gap table

| Concern | Current State | Gap the VIPP fills |
|---------|--------------|--------------------|
| SDK-mechanism authority on the project side | FDE (built) | Covered (FDE) — VIPP consumes its claims as the MECHANISM half |
| Project ground-truth (what the project has/wants/owns) | **Sapper** oracle stack + `FrictionReport` (built) | Covered (Sapper) — VIPP *consumes* it as the OBSERVED half (FR-7) |
| Host proposals leaving the host process | **In-memory `ProposalBuffer` only** — no disk seam | VIPP needs the new FR-15 serialization seam to receive them |
| Receiving + negotiating host proposals | Human reads in-session; CLI applies | No project-resident negotiator; no ACCEPT/REJECT/COUNTER disposition |
| Applying accepted proposals | `apply_proposal`/`apply_write_plan`, CLI-only, human privilege | VIPP becomes the project-side applier over the same confined seam |
| Composed, source-labeled cross-boundary view | FDE labels OBSERVED/MECHANISM | VIPP authors the OBSERVED half symmetrically |
| Project↔SDK two-way channel | One-directional (MCP read; FDE/SA write files) | VIPP establishes a durable `vipp-*` request/response protocol, A2A-ready |

---

## 2. Requirements

**FR-1 — Role & authority.** The VIPP is a project-resident agent carrying **OBSERVED(project)**
authority, the structural dual of the FDE's MECHANISM(sdk) authority. Authority is defined by *which
artifacts adjudicate a claim* (project artifacts), not by where the code lives. Its output is a
*composed*, source-labeled disposition; it never issues a solo SDK-mechanism verdict.

**FR-2 — Keiyaku contract pair.** Define the VIPP request/disposition as **frozen-dataclass typed
contracts** (`VippDisposition` over a host `ProposalEnvelope`) with `to_dict`/`from_json`/
`to_prompt_section`, where **JSON is canonical** and markdown is a *derived, lossy* view (no
`from_markdown` round-trip), mirroring `fde/models.py`.

**FR-3 — Hybrid form.** The VIPP's *brain* (negotiation/ground-truth logic) is a first-class,
versioned/testable SDK component with a `startd8 vipp` CLI surface; its *posting* (project-local
context bundle + the `vipp-*.{md,json}` protocol + the FR-15 inbox/outbox) lives under
`.startd8/vipp/`. The brain mirrors the FDE skeleton: `ensure_posting` → fingerprint idempotency
short-circuit → deterministic-first core (LLM opt-in, confined to narrative, re-gated by
`assert_all_labeled`) → write + record + optional notify (`fde/assistant.py:49-142`).

**FR-4 — Negotiation protocol.** The VIPP ingests a host **ProposalEnvelope** (the FR-15 serialized
form of pending `ProposedAction`s), evaluates each against project ground-truth (FR-7), and emits a
per-proposal disposition: **ACCEPT / REJECT(reason) / COUNTER(amended params)**, source-labeled.

**FR-5 — Applier at project human privilege.** ACCEPTed proposals are applied through the existing
`apply_proposal(project_root, action, *, config)` floor (`proposals.py:217`), which re-validates
live against the closed enum **`("instantiate","friction","capture","schema","manifest","brief")`**
(`proposals.py:41`) and routes per kind to `apply_concierge_plan` / `apply_write_plan` /
`promote_schema`. All `safe_write` guards apply (root-symlink reject, `..`/abs reconfine,
`O_NOFOLLOW` walk, clobber guard, atomic replace). The VIPP becomes the project-side applier; the
human-confirm seam (FR-16) is preserved.

**FR-6 — Source-labeling.** Every load-bearing claim the VIPP emits or consumes is labeled
**OBSERVED(project)** (VIPP's own / from Sapper), **MECHANISM(sdk)** (consumed from a host), or
**PREDICTION**, reusing `fde.models.ClaimLabel`/`LabeledClaim`. The deterministic composer fills the
slots; an LLM narrator may only reference already-emitted claim ids (it cannot mint claims), gated
by `assert_all_labeled`.

**FR-7 — Project ground-truth via Sapper (consume, don't re-implement).** The VIPP's OBSERVED
evidence is sourced from Sapper: `oracle_for_project(project_root)` for field/module authority and a
`FrictionReport` converted via `sapper.fde_bridge.to_observed_claims` into OBSERVED `LabeledClaim`s.
VIPP does **not** build a parallel ground-truth subsystem. These are deterministic reads
(deterministic-first; LLM confined to narrative).

**FR-8 — Bridge + dependency discipline.** A `vipp/host_bridge.py` translates a host ProposalEnvelope
into VIPP vocabulary and VIPP dispositions back into `ProposedAction`/apply calls. The dependency is
**one-directional** — VIPP depends on `fde`/`sapper`/`kickoff_experience` contracts; **never the
reverse** — with **graceful degradation** via availability flags (mirror `sapper/fde_bridge.py`'s
`FDE_AVAILABLE`). Cross-tool artifact annotation copies the FDE's atomic-patch-by-dict-shape pattern
(`assistant_bridge.py:54-97`), never importing peer types.

**FR-9 — Untrusted-to-Concierge security.** The Concierge treats VIPP-originated content as an
external/untrusted agent: it rides the existing **prompt-injection fence**, and VIPP-sourced claims
stay source-labeled so they cannot masquerade as SDK-mechanism authority. The VIPP cannot cause the
SDK to operate.

**FR-10 — Privilege boundary.** The VIPP applies only at **project human privilege**, only over the
closed kind enum, through `apply_proposal`'s re-validation floor (`proposals.py:241`); it never
records an SDK gate sign-off or runs the SDK cascade. Host proposals cannot mutate the project except
through this confined apply path.

**FR-11 — CLI surface.** A `cli_vipp.py` Typer sub-app `startd8 vipp` (mirroring `cli_fde.py`/
`cli_concierge.py`), registered via `app.add_typer(vipp_app, name="vipp")`, **preview-by-default**
with `--apply` to write and posture-encoding exit codes.

**FR-12 — Bucket discipline.** The VIPP helps produce buckets 1–3 (skeleton/manifests via
`instantiate`/`schema`/`manifest`/`brief`, placeholder copy + static test data, integration glue)
and **never authors bucket 4** (the project's real content). The `capture` kind sets only allowed
value-paths, never authored prose. It *represents* the project's authority over content without
inventing it.

**FR-13 — Protocol versioning.** `PROTOCOL_VERSION` is bumped on contract-shape changes, independent
of the SDK version (FDE R1-F3 parity).

**FR-14 — Roadmap transport.** The contract is designed as the serialized form of a future A2A /
ContextCore-insight-bus channel; v1 ships file transport only. Correlation reuses **`project.id`**
(per `integrations/join_contract.py`) as the shared identity key. A2A identity/auth is deferred here.

**FR-15 — Proposal-serialization seam (NEW, host-side).** Because the host `ProposalBuffer` is
in-memory-only by design, add a host-side seam that serializes pending `ProposedAction`s to a
confined project-local **inbox** (`.startd8/vipp/proposals-inbox.json`, Keiyaku-shaped, JSON
canonical), preserving the buffer's invariants (bounded; `base_sha` captured at propose time for
stale detection, `proposals.py:61-94`). The VIPP writes its dispositions to
`.startd8/vipp/dispositions.json`. The inbox/outbox are confined and clobber-guarded like every other
`.startd8/` write, and the serialization is **opt-in** (the default in-memory posture is unchanged
when no VIPP is present). See OQ-9/OQ-10 for the confinement/redaction design.

**FR-16 — Two-process, file-mediated topology + human-gated apply.** The VIPP runs out-of-process
from the host, mediated by the FR-15 inbox/outbox (consistent with "untrusted to the Concierge" and
file-protocol-first). v1 keeps an **explicit human confirm before any apply** (surprise-write
control); the VIPP produces dispositions and *recommends* applies, but a human gates the actual
write. Autonomous apply over a restricted kind subset is opt-in/roadmap.

---

## 3. Non-Requirements

- **NR-1.** Does not build A2A transport or a live multi-turn message bus (roadmap; v1 = files).
- **NR-2.** Does not author bucket-4 (the project's real user-facing content).
- **NR-3.** Does not make the SDK operate — no SDK gate sign-off, no SDK-side cascade run.
- **NR-4.** Does not remove the human — applies at human privilege; the propose→confirm seam is
  preserved (v1 keeps an explicit human confirm before any write, FR-16).
- **NR-5.** Does not modify the FDE or Sapper internals — the VIPP is a separate package; the
  dependency is one-way.
- **NR-6.** Does not re-implement the Concierge/Red Carpet/Sapper pieces — it consumes them.
- **NR-7.** Does not change the host's default in-memory proposal posture when no VIPP is present —
  the FR-15 serialization is opt-in (NR addition from OQ-9).

---

## 4. Open Questions (residual)

- **OQ-4.** Negotiation depth — v1 emits a single ACCEPT/REJECT/COUNTER disposition pass;
  multi-round live counter-negotiation is roadmap. Confirm v1 stops at one pass.
- **OQ-9.** FR-15 confinement/retention — serializing the in-memory buffer adds a persistence
  surface; design the confinement (reuse `safe_write` guards), retention/TTL, and whether the inbox
  is per-session or durable. CRP-worthy.
- **OQ-10.** FR-15 redaction — do `ProposedAction.params`/`base_sha` need the FDE `redaction` pass
  before hitting the inbox?
- **OQ-11.** In-process fast path — should the host optionally hand the live `ProposalBuffer` to an
  in-process VIPP (skipping FR-15 serialization) for the single-agent case, or is out-of-process the
  only supported topology in v1?

---

*v0.2 — Post-planning self-reflective update. 4 requirements corrected (FR-4/5/7/12), 2 added
(FR-15/16), 1 non-requirement added (NR-7), 7 open questions resolved (OQ-1/2/3/5/6/7/8), 3 new
surfaced (OQ-9/10/11). The central correction: host proposals are in-memory-only by design, so a
serialization seam — not a disk read — is the load-bearing new work.*
