# VIPP (Very Important Project Person) Requirements

**Version:** 0.3 (CRP R1 triaged — 3-lens convergent review + lessons-learned)
**Date:** 2026-06-30
**Status:** Draft
**Owner:** neil-the-nowledgeable

> **v0.3 triage summary.** A 3-lens convergent review (architecture/interfaces/data · risks/
> validation/ops · security), each code-anchored against the real `proposals.py`/`sapper`/
> `safe_write`/`fde` bytes, plus a Lessons-Learned mining pass, produced ~42 suggestions.
> **Disposition: ACCEPT all material suggestions; 0 rejected on merit; 1 partial-defer** (numeric
> confidence-tier, FR-6) — the reviews were anchored, non-overlapping, and three lenses *independently
> converged* on two load-bearing defects (redaction-vs-apply; `base_sha` provenance). See Appendix A
> for per-ID where-merged, Appendix B for the defer, Appendix C for the raw rounds. The convergent
> reframe: **the inbox is an untrusted injection surface INTO the project; `apply_proposal` is a
> kind/confinement floor, not a content boundary; the human-confirm is the sole content gate.**

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
`from_markdown` round-trip), mirroring `fde/models.py`. _[v0.3: R2-S5 —]_ **every** node in the graph
(`EnvelopedProposal`, `VippDisposition`, nested `LabeledClaim`) carries `to_dict`/`from_dict`; the
`decision` enum serializes via the `.value`/`from_value` idiom `ClaimLabel` uses; the round-trip test
covers the full nested `VippReport`. _[v0.3: R2-F7 —]_ identity fields are **`project_id` +
`protocol_version`**; `sdk_version` is retained as **provenance-only** ("the SDK build that ran the
VIPP brain"), never as authority (the report is a project-authority artifact). The envelope carries a
monotonic **`envelope_seq`** + content checksum (FR-18). A2A N:M mapping preserves host-native fields
in a metadata sidecar for round-trip fidelity (Lesson A2A-#4); the lossy markdown view is documented.

**FR-3 — Hybrid form.** The VIPP's *brain* (negotiation/ground-truth logic) is a first-class,
versioned/testable SDK component with a `startd8 vipp` CLI surface; its *posting* (project-local
context bundle + the `vipp-*.{md,json}` protocol + the FR-15 inbox/outbox) lives under
`.startd8/vipp/`. The brain mirrors the FDE skeleton: `ensure_posting` → fingerprint idempotency
short-circuit → deterministic-first core (LLM opt-in, confined to narrative, re-gated by
`assert_all_labeled`) → write + record + optional notify (`fde/assistant.py:49-142`).

**FR-4 — Negotiation protocol.** The VIPP ingests a host **ProposalEnvelope** (the FR-15 serialized
form of pending `ProposedAction`s), evaluates each against project ground-truth (FR-7), and emits a
per-proposal disposition: **ACCEPT / REJECT(reason) / COUNTER(amended params)**, source-labeled,
modeled as an explicit transition table (REJECT terminal; COUNTER re-opens **once** in v1 — Lesson
A2A-#1). _[v0.3 additions:]_
- **OMIT/no-evidence default (R2-F4):** when ground truth is OMIT/absent (the common case — the oracle
  OMITs for most Python projects by design, `ground_truth.py:21-22`), the default is **ACCEPT with an
  OBSERVED(qualifier="no ground truth") claim** so the lack of adjudication is source-labeled and
  visible — never a silent rubber-stamp, never a block. This also defines `SAPPER_AVAILABLE=False`.
- **Per-kind COUNTER contract (R2-F3):** a COUNTER may amend **only** specified params, may **not**
  change `kind`, and is re-validated by the same per-kind floor at apply. A COUNTER touching a
  `capture` target must **re-derive `base_sha` at disposition time** (or drop it and accept the live
  re-read) — never reuse the host's propose-time sha for a different file.
- **Malformed input → REJECT, never crash (Lesson L13-#103):** a non-conformant/non-applicable host
  proposal yields a `REJECT(reason)` disposition (an actionable flag), not a VIPP exception.

**FR-5 — Applier at project human privilege (provenance-pinned).** ACCEPTed proposals are applied
through the existing `apply_proposal(project_root, action, *, config)` floor (`proposals.py:217`),
which re-validates live against the closed enum
**`("instantiate","friction","capture","schema","manifest","brief")`** (`proposals.py:41`) and routes
per kind to `apply_concierge_plan` / `apply_write_plan` / `promote_schema`. All `safe_write` guards
apply (root-symlink reject, `..`/abs reconfine, `O_NOFOLLOW` walk, clobber guard, atomic replace).
_[v0.3 — R3-F2/S1, R2-S4: the CRITICAL provenance rule.]_ For an ACCEPT, the reconstructed action's
`kind`/`params`/`base_sha` are taken from the **trusted host inbox entry matched by `proposal_id`**
(the propose-time record) — **not** from the VIPP-authored disposition; only a COUNTER's explicitly
amended params override, and **`base_sha` is never VIPP-amendable** (else a hostile VIPP sets
`base_sha` = current on-disk sha and the capture stale-guard, `capture.py:371`, goes vacuous). The
applier therefore reads inbox + dispositions **jointly**, joining by `proposal_id`. The VIPP becomes
the project-side applier; the human-confirm seam (FR-16) is preserved. Partial-apply + cursor: FR-18.

**FR-6 — Source-labeling.** Every load-bearing claim the VIPP emits or consumes is labeled
**OBSERVED(project)** (VIPP's own / from Sapper), **MECHANISM(sdk)** (consumed from a host), or
**PREDICTION**, reusing `fde.models.ClaimLabel`/`LabeledClaim`. The deterministic composer fills the
slots; an LLM narrator may only reference already-emitted claim ids (it cannot mint claims), gated
by `assert_all_labeled`. _[v0.3 — R3-F3, the load-bearing security caveat:]_ **source-labeling is NOT
a security control without provenance binding.** `assert_all_labeled` only lints rendered markdown for
a recognized tag; it neither authenticates a writer nor stops MECHANISM being attached to
attacker-authored inbox claims (the inbox is a plain JSON file any local process can write). Therefore
VIPP **must not auto-promote inbox claims to MECHANISM(sdk)** absent a host-written provenance stamp
(host signature/checksum, or a host-only-created path — OQ-12); an inbox of unverified provenance is
treated as OBSERVED/untrusted. Labels (and an optional per-source confidence tier — deferred, App. B)
must survive every serialization boundary intact (Lesson L13-#22).

**FR-7 — Project ground-truth via Sapper (consume + a thin owned adapter).** _[v0.3: R2-F1/S1/S2 —
"consume" understated the real work; the two Sapper interfaces are distinct.]_ The VIPP draws OBSERVED
evidence from **two separately-specified Sapper inputs**: (1) the **queryable oracle**
`oracle_for_project(project_root) -> GroundTruthQuery` whose only method is `answer(GroundTruthQuestion)
-> GroundTruthAnswer` (VALIDATED/REFUTED/OMIT) — VIPP owns a thin new `answer→LabeledClaim(OBSERVED)`
adapter (this does not exist in the tree); and (2) optionally an already-on-disk
`sapper-friction-report.json` fed through `sapper.fde_bridge.to_observed_claims`. To adjudicate a
`schema`/`manifest` proposal, VIPP must first run prose→entity extraction (`build_entity_graph`/
`extract_manifests`) since the entity lives in free-text `params`, not a discrete field. VIPP does
**not** build a parallel ground-truth subsystem. Deterministic reads (LLM confined to narrative).
Per Lesson L10-#41 (incomplete-vs-incorrect): a *missing* oracle degrades the **narrative** only; it
must **never fabricate an OBSERVED claim** — absent ground truth, VIPP abstains (see FR-4 OMIT default).

**FR-8 — Bridge + dependency discipline.** A `vipp/host_bridge.py` translates a host ProposalEnvelope
into VIPP vocabulary and VIPP dispositions back into `ProposedAction`/apply calls. The dependency is
**one-directional** — VIPP depends on `fde`/`sapper`/`kickoff_experience` contracts; **never the
reverse** — with **graceful degradation** via availability flags (mirror `sapper/fde_bridge.py`'s
`FDE_AVAILABLE`). _[v0.3 — R2-F5: scope the import rule.]_ The **contract models** (M0) avoid importing
peer types (clean serialization boundary, atomic-patch-by-dict-shape, `assistant_bridge.py:54-97`);
but the **applier** (`vipp/apply.py`) legitimately **imports `ProposedAction`** because
`apply_proposal` requires a real frozen-dataclass instance (`proposals.py:217`) and vipp→
kickoff_experience is the sanctioned direction (lazy-import inside the method if any cycle threatens —
Lesson L11-#71). _[v0.3 — R2-F6:]_ a **shape-pinning contract test** asserts
`{f.name for f in fields(ProposedAction)} == {"kind","params","id","base_sha"}` so a host-side field
addition fails loudly and forces an envelope/`PROTOCOL_VERSION` bump (the host shape carries **no**
version of its own — it is the drift-prone one). _[v0.3 — R2-S6:]_ host-side opt-in detection (FR-15)
is by `(project_root/".startd8/vipp").exists()` or an env/config flag — **never** `import startd8.vipp`
(that would create the forbidden reverse edge); a dependency-direction test asserts `startd8.vipp ∉
sys.modules` after importing `kickoff_experience.proposals`.

**FR-9 — Untrusted, in BOTH directions.** _[v0.3: R3-F4/S5 — "Concierge fences VIPP content" is
**vacuous in v1**: no VIPP-authored content reaches a Concierge LLM (the apply path calls no agent;
the chat ingests the human's message). Re-scoped.]_ (a) **Roadmap:** the Concierge fences VIPP content
only once a live A2A/chat channel feeds it into an LLM. (b) **Reachable v1 control (the one that
matters):** the host is **symmetrically untrusted to the VIPP** — VIPP's own M2 narrator ingests host
`brief`/`manifest`/`friction` prose from the inbox and **must** pass it through
`security.normalize_untrusted_text` (`security.py:667`) + the `<context>` fence before narration
(threat model: Lesson L13-#72 Specification Poisoning). The VIPP cannot cause the SDK to operate.

**FR-10 — Privilege boundary (floor bounds kind+confinement, NOT content).** _[v0.3: R3-F1 —
`apply_proposal`'s floor (`proposals.py:241`) gates `kind ∈ PROPOSAL_KINDS` and re-runs *structural*
validators; it never validates **content**. For `brief`/`manifest`/`schema`, `params["source"]` is
arbitrary prose written verbatim to disk.]_ The VIPP applies only at **project human privilege**, only
over the closed kind enum, through that floor; it never records an SDK gate sign-off or runs the SDK
cascade. The floor is the **kind/path-confinement** boundary; the **FR-16 human-confirm is the sole
content authority** — therefore OQ-3 autonomous-apply stays out of scope until a content-policy gate
exists (it would remove the only content backstop). The closed-kind floor and `safe_write` confinement
are sound (verified: no kind-escape, no path-escape); the exposure is *content/provenance/persistence*.

**FR-11 — CLI surface + exit-code contract.** A `cli_vipp.py` Typer sub-app `startd8 vipp` (mirroring
`cli_fde.py`/`cli_concierge.py`), registered via `app.add_typer(vipp_app, name="vipp")`,
**preview-by-default** with `--apply` to write. _[v0.3: R1-F6 — enumerate, don't bury in the plan.]_
Exit codes: **0** advisory/in-sync · **1** drift (dispositions differ from a prior run) · **2**
bad-input · **3** write blocked (confinement/clobber/stale-seq refusal). Covered by a test.

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

**FR-15 — Proposal-serialization seam (host-side, design-handoff-file pattern).** Because the host
`ProposalBuffer` is in-memory-only by design, add a host-side seam that serializes pending
`ProposedAction`s to a confined project-local **inbox** (`.startd8/vipp/proposals-inbox.json`,
Keiyaku-shaped, JSON canonical), adopting the **separate-handoff-file pattern wholesale** (Lesson
L11-#34): `schema_version` + **reject-future** semantics + a **consumed lifecycle** (persists until
drained, distinct from a checkpoint). The VIPP writes dispositions to `.startd8/vipp/dispositions.json`.
The seam is **opt-in** — default in-memory posture is **byte-identical-when-absent** (NR-7, the SOTTO
invariant, Lessons L16-#41/#44), proven by a full output-dict-equality test. _[v0.3 resolutions:]_
- **Key whitelist, not whole-dump (OQ-10 / Lesson L11-#41):** serialize an explicit `frozenset`
  whitelist of fields (`kind`, the per-kind `params` subset, `id`, `base_sha`), never the whole object.
- **Redaction is display/defense-in-depth ONLY (R1-F4 · R2-F2 · R3-F6 — 3-lens convergence; OQ-10
  resolved):** `params` flow to the applier **unredacted** because for `brief`/`manifest`/`schema`
  the `params["source"]` **is** the prose written verbatim to disk and round-trip-gated — redacting it
  would persist corrupted bytes. `fde/redaction.py` only strips secret-shaped tokens, so it's kept as a
  pasted-secret catch on at-rest/log/narrative surfaces, **not** as content sanitization. Structural
  keys (`base_sha`, `value_path`, `kind`, `contract_path`) are excluded from any redaction pass.
- **Confinement + retention (R3-F5/F7 · OQ-9 resolved):** inbox/outbox are **session-scoped**, mode
  **`0600`**, **shredded on disposition/apply completion**, a **rejected proposal is purged not
  retained**, and `.startd8/vipp/` ships a **`.gitignore`** (Lesson L12-#21: you cannot un-leak an
  inbox after it reaches git history; `.startd8/` is sometimes committed). Writes confine by resolving
  the **parent dir** realpath, not the leaf (Lesson L11-#85); **reads** of the inbox/outbox are
  **symlink-rejecting** (`O_NOFOLLOW`/realpath-within-root), symmetric to the write guards. An explicit
  empty/"nothing-pending" state exists so a stale prior-run file is never silently re-negotiated
  (Lesson L13-#73).

**FR-16 — Two-process topology + human-gated apply (confirm renders content).** The VIPP runs
out-of-process from the host, mediated by the FR-15 inbox/outbox. v1 keeps an **explicit human confirm
before any apply** — and, because the human-confirm is the **sole content gate** (FR-10), _[v0.3 —
R3-S2:]_ the confirm **renders the concrete content the human is approving** — `ProposedAction.summary()`
(`proposals.py:70`) and, for `capture`, `CapturePlan.preview()` (`capture.py:254`) — i.e. the actual
post-COUNTER brief/schema/manifest/field bytes, not an opaque "ACCEPT". Confirm severity is structured
(a `schema`/`manifest` COUNTER is *blocking-confirm*; a `friction` log may be *advisory* — Lesson
A2A-#5). Autonomous apply over a restricted kind subset is opt-in/roadmap (gated by FR-10's missing
content-policy gate).

**FR-17 — Observability (NEW).** _[v0.3 — R1-F7.]_ VIPP emits one structured negotiation event per
disposition (`kind` + `decision` + label only — **no free-text**, matching the host privacy posture at
`proposals.py:208`), logs via `get_logger` (OTel/Loki bridge), and writes a durable, source-labeled
`dispositions.{json,md}` audit record human-legible in a git diff (Lesson L10-#15). An operator can
reconstruct "what did the VIPP decide and why" from disk + telemetry alone.

**FR-18 — Negotiation lifecycle, sequence & idempotency (NEW).** _[v0.3 — R1-F1/F2/F3 · R1-S2 ·
R3-S4; consolidates the concurrency/replay safety model the v0.2 draft under-specified.]_
- **Envelope sequence, NOT `base_sha`, is the inbox-staleness oracle (R1-F1):** `base_sha` is
  **capture-kind-only** and binds *one file* (`proposals.py:68`, `capture.py:250`) — it gives **zero**
  detection that the inbox itself was re-serialized. The envelope carries a monotonic **`envelope_seq`**
  + content checksum; the VIPP **pins** the seq it read into every disposition.
- **Stale-disposition refusal (R1-F2):** the applier refuses to apply a disposition whose pinned
  `envelope_seq` is behind the on-disk inbox ("re-negotiate"). A re-serialize cannot silently clobber
  an **undrained** inbox (mirror the buffer's `BufferFull` reject-don't-evict, `proposals.py:123`).
- **Consume-on-terminal-success (R1-F3):** after a `_TERMINAL_SUCCESS` apply (`proposals.py:50`) the
  inbox proposal + disposition are marked **consumed**; retriable codes (`_RETRIABLE_CODES`,
  `proposals.py:48`) are retained for resume. This blocks the double-write hazard — note `friction`/
  `instantiate` apply is **not idempotent** (append/re-run), so blind replay duplicates entries.
- **Apply cursor + partial-failure contract (R1-S2):** `apply_dispositions` keeps a cursor keyed by
  `proposal_id` + `envelope_seq`; on "3 of 5 succeed then one fails" it consumes the 3 terminal,
  retains the retriable, and reports `wrote N/M` per-proposal (mirror `_apply_manifest` PARTIAL,
  `proposals.py:425`); a re-run resumes only the unfinished.

---

## Build status (M0–M2 shipped + verified, 2026-06-30)

`src/startd8/vipp/` on `feat/vipp-project-counterpart` (not merged): **M0** contracts (`ef22fcef`),
**M1** ground-truth consumption (`9bf67829`), **M2** deterministic negotiation brain (`de7ca07a`),
**code-review fixes** 2 HIGH + 6 lower (`432f94cb`). 34 unit tests green; ruff/black clean.

**Verify-before-M3 gate (passed):**
- **Reality check (resolves CRP A-F4 empirically):** the *real* `oracle_for_project` **discriminates**
  on a Prisma project — `Profile.email`/`Order.total` → VALIDATED → ACCEPT, the `headlne` typo →
  REFUTED ("'headlne' not in Profile fields ['email','headline','id']") → REJECT. The field-authority
  (`capture`) negotiation is **not vacuous**. `schema`/`manifest` entity adjudication is
  **corpus-dependent** and OMIT-defaults *honestly* (labeled) without a controlled corpus — correct.
- **Code review:** see `432f94cb` — the load-bearing fix was H1 (a host-controlled newline could crash
  the FR-21 label gate; now collapsed at every VIPP-authored-string boundary via `models.oneline`).
- **OQ-11 resolved:** out-of-process-only (above).

**Remaining:** M3 (host-side serialization seam — HIGH/CRP-gated), M4 (provenance-pinned applier —
HIGH/CRP-gated + two-process live integration test), M5 (CLI), M6 (security/obs/docs).

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
  the FR-15 serialization is opt-in, **byte-identical-when-absent** (SOTTO), proven by a dict-equality
  test (Lessons L16-#41/#44).
- **NR-8.** Does not autonomously apply in v1 — the human-confirm is the sole content gate (FR-10/16);
  autonomous apply is roadmap-gated on a content-policy gate that does not yet exist.

---

## 4. Open Questions (residual)

- **OQ-4 → RESOLVED (CRP R1).** v1 is a single ACCEPT/REJECT/COUNTER pass; COUNTER re-opens once
  (Lesson A2A-#1); no live multi-round counter-negotiation in v1 (roadmap).
- **OQ-9 → RESOLVED (CRP R1).** Confinement/retention is now FR-15: session-scoped, `0600`,
  shred-on-completion, purge-rejected, `.gitignore`, parent-dir-confined writes + symlink-rejecting
  reads, `schema_version`+reject-future+consumed lifecycle. *Residual:* a precise TTL for an orphaned
  inbox has **no prior art** in the lessons corpus (the one genuinely novel decision — keep a
  `--stale-after` default and refuse rather than auto-apply a cross-session inbox).
- **OQ-10 → RESOLVED (CRP R1, 3-lens convergence).** Redaction is **display/defense-in-depth only**;
  `params` flow to apply **unredacted** (they are the bytes written + round-trip-gated). The real
  control is the FR-15 key-whitelist + confinement/0600/gitignore, not `fde/redaction.py`.
- **OQ-11 → RESOLVED (verify-before-M3, 2026-06-30): out-of-process-only in v1.** An in-process
  fast path (host hands the live `ProposalBuffer` to VIPP in the same address space, skipping FR-15
  serialization) would **collapse the trust boundary** the whole design rests on — "VIPP untrusted to
  the Concierge" (FR-9), the `safe_write` confinement, source-labeling, and the inbox-as-untrusted-
  injection-surface all live *at the file seam*. The only benefit is skipping a trivial serialization
  of a bounded (≤32) buffer. Not worth collapsing the boundary; **one topology = one code path to
  secure and test.** A future in-process optimization needs an explicit ADR + a real perf trigger.
- **OQ-12 (NEW — CRP R1).** Inbox **writer-provenance**: what host-written stamp (signature/checksum,
  or a host-only-creatable path) lets the VIPP safely promote an inbox claim to MECHANISM(sdk) (FR-6)?
  v1 trust boundary = filesystem confinement (no promotion); a provenance stamp is the FR-9/A2A roadmap.

---

*v0.3 — CRP R1 triaged (3-lens convergent review + lessons-learned). FRs corrected: FR-2/4/5/6/7/8/9/
10/11/15/16; FRs added: FR-17 (observability), FR-18 (lifecycle/sequence/idempotency). OQ-4/9/10
resolved; OQ-12 added. The convergent reframe: the inbox is an untrusted injection surface INTO the
project; `apply_proposal` is a kind/confinement floor, not a content boundary; the human-confirm is
the sole content gate. Two defects three lenses independently converged on: redaction-vs-apply, and
`base_sha`-provenance.*

---

## Appendix A — Accepted CRP suggestions (incorporated)

CRP R1 ran 3 independent lenses — **A**=architecture/interfaces/data, **B**=risks/validation/ops,
**C**=security — each code-anchored, plus a Lessons-Learned (LL) mining pass. ⊕ marks multi-lens
convergence (highest confidence). Requirements-doc IDs are F-N per lens.

| ID(s) | Suggestion (short) | Where merged |
|-------|--------------------|--------------|
| ⊕ B-F4 · A-F2 · C-F6 | **Redaction-vs-apply:** redacting `params` corrupts the prose written to disk; redaction is display/defense-in-depth only, `params` apply unredacted. | FR-15, OQ-10 resolved |
| ⊕ B-F1 · A-F3 · C-F2/S1 | **`base_sha` provenance:** capture-only file guard, not inbox-staleness; ACCEPT reconstructs from trusted inbox by `proposal_id`; `base_sha` not VIPP-amendable. | FR-5, FR-18 |
| C-F1 | `apply_proposal` floor = kind/confinement, **not content**; human-confirm is sole content gate; OQ-3 autonomous-apply out of scope. | FR-10, NR-8 |
| C-F4 · C-S5 | FR-9 "Concierge fences VIPP content" vacuous in v1; reachable control = VIPP's narrator fences inbox prose. | FR-9 |
| C-F3 | Source-labeling not a security control without provenance binding; no auto-promote inbox→MECHANISM. | FR-6, OQ-12 |
| C-F5/F7 · C-S3 | Persistence-of-ephemeral: session-scope, `0600`, shred, purge-rejected, gitignore; read-side symlink reject. | FR-15, OQ-9 resolved |
| A-F1 · A-S1/S2 | Sapper consumption: oracle (`answer`)≠`FrictionReport`; need `answer→LabeledClaim` adapter + prose→entity extraction. | FR-7, plan M1/M2 |
| A-F4 | OMIT/no-evidence default disposition = ACCEPT + labeled "no ground truth" (else negotiation vacuous). | FR-4 |
| B-F2 · C-S4 | Envelope `seq` + checksum; refuse stale disposition; don't clobber undrained inbox. | FR-18 |
| B-F3 | Consume-on-terminal-success; `friction`/`instantiate` apply not idempotent → replay hazard. | FR-18 |
| B-S1 · A-S3 | Idempotency fingerprint defeated by `generated_at` → exclude via `checksum_json_excluding`. | plan M2 |
| B-S2 | M4 apply cursor + partial-failure contract (retain retriable, consume terminal, report N/M). | FR-18, plan M4 |
| B-S4 | Two-process race is untested → gated live integration test (serialize N, read, serialize N+1, refuse stale). | plan M3/M4 |
| A-F5 · A-S? | Scope "never import peer types" to contract models; applier legitimately imports `ProposedAction`. | FR-8 |
| A-F6 | Shape-pinning contract test for `ProposedAction` drift (host shape carries no version). | FR-8 |
| A-S6 | Host opt-in detection by filesystem/flag, never `import startd8.vipp` (reverse-edge). | FR-8 |
| A-F7 | `sdk_version` provenance-only; identity = `project_id`+`protocol_version`. | FR-2 |
| A-S5 | Per-contract `to_dict`/`from_dict` on every graph node; `decision` enum serialization. | FR-2 |
| C-S2 | Human-confirm renders concrete content (`summary()`/`preview()`), not opaque ACCEPT. | FR-16 |
| B-F6 | Exit-code table belongs in the requirement. | FR-11 |
| B-F7 | Observability FR (event-per-disposition, `get_logger`, durable audit). | FR-17 (new) |
| A-F? · B-? | COUNTER per-kind contract (amend only, no kind-change, re-derive capture `base_sha`). | FR-4 |
| LL (multiple) | Handoff-file pattern #34, key-whitelist #41, SOTTO #41/#44, exclude-own-writeback #8, spec-poisoning #72, incomplete-vs-incorrect #41, confidence-propagation #22. | FR-15/18/7/9/6 |

## Appendix B — Rejected / deferred CRP suggestions (with rationale)

| ID | Suggestion | Disposition |
|----|------------|-------------|
| C-F3 (partial) / LL-#22 | Add a **numeric per-source confidence tier** alongside the 3 categorical labels. | **DEFER to roadmap.** v1 keeps the 3 categorical OBSERVED/MECHANISM/PREDICTION labels (which already survive serialization). A numeric confidence sub-tier is over-engineering for a single-pass v1 negotiator; revisit if multi-round (OQ-4) lands. Not rejected on merit — scope. |

_No suggestion was rejected as wrong. The reviews were anchored and code-verified; near-total accept is the correct outcome (matches this repo's CRP-quality bar)._

## Appendix C — Incoming (raw review rounds)

**Round 1 (CRP, 3 lenses, 2026-06-30).** Lens A (architecture/interfaces/data): F-1..F-7, S-1..S-6.
Lens B (risks/validation/ops): F-1..F-7, S-1..S-8. Lens C (security): F-1..F-7, S-1..S-7. Full raw
text retained in the session transcript; the load-bearing items are triaged into Appendix A above with
their lens-prefixed IDs. Highest-impact (all ACCEPT): redaction-vs-apply (⊕ B-F4/A-F2/C-F6), base_sha
provenance (⊕ B-F1/A-F3/C-F2), Sapper-interface correction (A-F1/S1/S2), OMIT-default (A-F4), FR-9
re-scope (C-F4), envelope-seq/lifecycle (B-F1/F2/F3, C-F5).
