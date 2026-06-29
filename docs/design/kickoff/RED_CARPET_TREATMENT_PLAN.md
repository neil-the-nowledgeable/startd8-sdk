# Red Carpet Treatment — Implementation Plan

**Version:** 0.2 (Post-CRP R1 — pairs with `RED_CARPET_TREATMENT_REQUIREMENTS.md` v0.3)
**Date:** 2026-06-29
**Status:** Draft

> Planned against **`origin/main`** (not the primary worktree — see §0 build-env discovery). Maps each
> FR to real seams; discoveries that change the requirements are in §6 → fed to requirements §0 (v0.2).

---

## 0. Build-environment discovery (read first)

The planning Explore pass read the **primary worktree** (`feat/welcome-mat-2-download`), which is
**behind `origin/main`** — it has the download pillar but **not** PR #62's chat panel nor the 7
chat-hardening commits. It therefore mis-reported the **proposal model and the web chat as absent**.
Verified against `origin/main`: `kickoff_experience/proposals.py` (`ProposedAction`, `apply_proposal`),
the `propose_action` read-effect tool (`chat.py`), `/concierge/chat` + `_ChatStore` +
`new_agentic_kickoff_chat` (`web.py`/`cli_kickoff.py`) **all exist**. **RCT must be branched from
`origin/main`** — the primary worktree lacks the substrate RCT rides.

**Parallel-work collision risk (CRP R1-S8).** RCT edits **contended** kickoff files (`proposals.py`,
`web.py`, the kickoff telemetry module) that concurrent multi-vendor agents also touch. Land RCT work
via the safe worktree → rebase → FF-push path (as the Welcome Mat 2.0 commits did), and expect
mid-flight rebases; sequence so each landed commit is self-contained.

## 1. Architecture at a glance

RCT is a **conductor** over five existing subsystems, plus **three genuinely-new pieces**:

| RCT concern | Reuses (origin/main) | New |
|-------------|----------------------|-----|
| Agentic interview + propose-confirm | `AgenticSession` + `build_kickoff_registry` + `propose_action`→`ProposedAction`→`apply_proposal`; `/concierge/chat` panel + `_ChatStore` (web), `kickoff chat` (CLI) | a RCT **system prompt** + **stage driver**; extend proposal **kinds** |
| Data-model contract | `generate contract` (prose→prisma, `--promote`); `concierge/derive` (Pydantic→prisma) | **interview → requirements/PRD prose brief** step |
| Manifests + value inputs | `manifest_extraction` extractors + `extract_manifests`; `build_instantiate_plan` + templates; `capture.py` (per-key inputs merge) | **project-tree manifest writer** (the key gap) |
| Readiness → run | `build_assess`/`build_readiness`/`build_concierge_view`; `wireframe`; `generate backend/scaffold/views/frontend` | RCT **stage-state** + stage rail |
| Retrospective | the friction path | a reflection prompt per increment |

## 2. The genuinely-new pieces (where the real work is)

**N1 — Project-tree manifest writer (FR-RCT-6, the biggest gap).** `extract_manifests(docs)` returns
the manifests **in memory**, round-trip-gated; the only on-disk writer targets a *run-dir*
(`plan_ingestion_emitter`), **not** the project's `docs/kickoff/inputs/`. RCT needs an orchestration
that maps each `result.manifests[filename]` → its project destination and writes through the
**existing** `apply_write_plan` confinement seam (mirroring `build_instantiate_plan`). Pure plumbing
over existing extraction — but net-new.

**N2 — Interview → requirements/PRD prose brief (FR-RCT-4).** Neither producer does a *conversational*
interview→schema: `generate contract` consumes a **prose requirements doc**; `derive` reverse-derives
from **live Pydantic models**. So RCT's from-scratch path is: agent interviews → **drafts a requirements
prose brief** (a proposal) → human confirms → `generate contract` (prose→prisma) → `--promote`. (The
`derive` path is a *side door* for users who already have models.)

**N3 — RCT stage-state + stage rail (FR-RCT-2).** No persisted kickoff/RCT session state exists today
(readiness is recomputed from the filesystem each call). RCT's "current stage / next gap / resume"
needs a small `.startd8/` state record — though the **stage map itself is derived from `build_assess`**
(which already reports per-stage cascade readiness AND the 4 value domains), so state is a thin cursor,
not a second source of truth.

## 3. Reuse map (origin/main seams — verified)

- **Proposal/confirm:** `ProposedAction(kind, payload, id)` + `ProposalBuffer.pending()/pop()` +
  `apply_proposal(root, action, config)` (dispatches by `kind`; today `friction`/`instantiate`). The
  `propose_action` read-effect tool records proposals; the loop never writes; `/concierge/chat/confirm`
  applies at human privilege (`_concierge_write_gate`: mode+host+CSRF). **RCT extends the `kind`
  vocabulary** with `schema`/`manifest`/`value-input` + their apply paths (→ `generate contract
  --promote`, → N1 writer, → `capture.py` merge). *Medium.*
- **Schema producers:** `startd8 generate contract` (`cli_generate.py`), `concierge/derive`. *Small.*
- **Extractors:** `manifest_extraction/{extract,extractors}.py` — pure prose→dict, round-trip-gated. *None.*
- **Cascade + wireframe:** `startd8 generate backend/scaffold/views/frontend`, `startd8 wireframe` — all
  `$0`/no-LLM. *None.*
- **Readiness:** `build_assess` (cascade sections + 4 value domains), `build_readiness` (score),
  `build_concierge_view` (web/TUI payload + next_action). *None* (RCT consumes, never recomputes).
- **Value-input capture:** `capture.py` single-key merge-splice into `inputs/*.yaml` (allow-list gated)
  — `value-input` proposals must use THIS, not a whole-file write. *None.*
- **Web chat:** `/concierge/chat` + `_ChatStore` + `chat_factory` (web.py) + the chat hardening (cookie,
  budget, mode-gate, etc.). RCT's web surface = a **staged experience reusing the chat engine** + a
  stage rail, not a new chat. *Medium* (stage rail + a richer write-proposal registry, not a new chat).
- **CLI:** add `@kickoff_app.command("red-carpet")` mirroring `chat_cmd`'s agent resolution. *Trivial.*

## 4. Per-stage flow (the conductor)

For each stage in `build_assess`-derived order — **DATA MODEL → pages → views → forms → flows →
imports → app/scaffold → value inputs → placeholder content → readiness/run**:
1. RCT reads the gap (`build_assess`), picks the next unmet stage.
2. The agent interviews + **drafts a proposal** (`propose_action`, the right `kind`).
3. The human **confirms** (web CSRF/loopback/intent, or CLI confirm) → apply path runs (N1 / `generate
   contract --promote` / `capture`).
4. **Re-assess** (`build_assess`), show updated readiness, run the **per-increment reflection**
   (FR-RCT-12).
5. When the surface is complete → `wireframe` checkpoint → offer the `$0` cascade.

## 5. Sequencing *(re-ordered post-CRP R1-S4 — the schema gate precedes the manifest writer)*

0. **The closed apply-side `kind` allow-list + the no-loop-write registry assertion** (R1-S1) — land
   this *first* as the security floor every later kind rides.
1. **N2 schema gate** — interview→prose-brief→`generate contract --promote` + the `schema` kind, with
   the **two-step ratification** (R1-S6) and **schema-drift** detection (R1-S7). The data-model gate
   must exist before the manifest writer so N1 can assert it refuses to run pre-schema (R1-S4).
2. **N1 project-tree manifest writer** + the `manifest`/`value-input` kinds — with **server-derived
   confined dests** (R1-S2), **no-clobber/replace-confirm + atomic** writes (R1-S3), and **per-kind
   apply-time re-validation** (R1-S11). `value-input` rides `capture.py`.
3. **N3 stage-state + the `build_assess`-driven stage driver** (the conductor) — CLI first
   (`kickoff red-carpet`), with **cursor reconcile-on-resume + concurrency safety** (R1-S8).
4. Web **stage-rail over `/concierge/chat`** (R1-S10 — *not* a new route); reflection step; telemetry
   incl. the confirm→apply/denial/exhaustion events (FR-RCT-14); **whole-build spend ceiling +
   checkpoint** (R1-S9); cascade handoff + `wireframe` checkpoint.

## 7. Validation Strategy *(new, CRP R1-S5)*

One named test per new piece, runnable in CI:
- **Allow-list floor (R1-S1):** unknown `kind` → rejected; registry introspection asserts **zero
  apply-capable tools** reachable by the loop.
- **N1 confinement (R1-S2):** `dest=../../x.yaml` / absolute / symlink → rejected; realpath-under-root
  assertion fuzzed over the filename→path map.
- **N1 clobber/atomicity (R1-S3):** pre-edited manifest not overwritten without replace-confirm;
  injected mid-write failure → no file mutated (rollback).
- **N2 two-step ratification (R1-S6):** no `.prisma` after brief-confirm; only `--promote` writes it.
  Lossy brief fragment → reported, not promoted.
- **Schema drift (R1-S7):** promote v2 with an entity removed → orphaned manifest flagged.
- **N3 cursor (R1-S8):** hand-edit between stages → cursor reconciles to live `build_assess`; two
  sessions → no corrupt cursor.
- **Per-kind apply-time re-validation (R1-S11):** propose-time-valid but extractor-invalid draft →
  rejected at apply (not partially applied).
- **Cascade predicate (FR-RCT-10):** subset present → offer; remove a gate → offer withheld, gate named.
- **Build spend ceiling (R1-S9):** build crossing the per-session cap checkpoints + resumes; completed
  stages not re-charged.
- **Parity (FR-RCT-15):** web and CLI exercise the same engine/stage map/seam.

## 6. Planning discoveries (feed to requirements §0)

| Requirements assumed (v0.1) | Planning revealed (origin/main) | Impact |
|-----------------------------|----------------------------------|--------|
| The proposal model + web chat are reusable substrate | True on `origin/main`; the Explore pass on the primary worktree wrongly reported them absent → **RCT must branch from `origin/main`** | Add §0 build-env note; pin the base branch |
| `concierge/derive` does interview→schema (OQ-5) | `derive` is **Pydantic-models→prisma**; `generate contract` is **prose→prisma**. Neither is conversational. | **FR-RCT-4 reframed**: interview → requirements **prose brief** → `generate contract --promote`; `derive` is a side door (OQ-5 resolved) |
| Extractors + an existing writer materialize manifests into the project | Extractors are pure/in-memory; **no command writes prose→`docs/kickoff/inputs/*.yaml`** in the project tree (only a workflow → run-dir) | **New requirement/step N1** — the project-tree manifest writer is RCT's biggest genuinely-new piece |
| Proposal kinds extend cleanly (OQ-1) | Model EXISTS (`ProposedAction`/`apply_proposal`, kinds friction/instantiate) but kinds are **bespoke per-kind apply**, no registry | OQ-1 = **medium** extension (builders + dispatch branch per kind); still the riskiest |
| Readiness may only cover the 4 value inputs (FR-RCT-2 risk) | `build_assess` reports **both** per-stage cascade readiness AND the 4 domains | FR-RCT-2 confirmed feasible; **stage-state is a thin cursor** over `build_assess`, not a second readiness |
| RCT is "mostly orchestration" (P1) | Confirmed — 3 new pieces (N1 writer, N2 interview→brief, N3 stage-state); everything else is reuse | P1 holds; name the 3 new pieces explicitly |
| `value-input` writes ride the instantiate write | They must ride **`capture.py`** (per-key merge into `inputs/*.yaml`, allow-list gated), not a whole-file write | FR-RCT-9 must distinguish per-kind apply paths |

---

*Plan v0.1 — drafted against origin/main. 7 discoveries feed requirements §0 (v0.2). Headline: RCT is
genuinely an orchestration layer, but it must branch from `origin/main` and build three new pieces — the
project-tree manifest writer (N1), the interview→prose-brief→contract step (N2), and the
`build_assess`-driven stage driver/state (N3).*

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

> Triage R1 (2026-06-29). All 11 plan suggestions accepted; none rejected. Folded into §5 (re-ordered),
> §7 (new Validation Strategy), §0, §2 N1/N2.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Closed apply-side allow-list + no-loop-write registry | claude-opus-4-8-1m | §5 step 0 + §7 | 2026-06-29 |
| R1-S2 | N1 server-derived confined dest | claude-opus-4-8-1m | §5 step 2 + §7 | 2026-06-29 |
| R1-S3 | N1 no-clobber/replace-confirm + atomic | claude-opus-4-8-1m | §5 step 2 + §7 | 2026-06-29 |
| R1-S4 | Re-order: schema gate before N1 | claude-opus-4-8-1m | §5 re-ordered (step 1 before 2) | 2026-06-29 |
| R1-S5 | Add a Validation Strategy section | claude-opus-4-8-1m | new §7 | 2026-06-29 |
| R1-S6 | Two-step ratification sequenced | claude-opus-4-8-1m | §5 step 1 + §7 | 2026-06-29 |
| R1-S7 | Schema-revision drift task | claude-opus-4-8-1m | §5 step 1 + §7 (+ reqs FR-RCT-16) | 2026-06-29 |
| R1-S8 | Concurrent-session cursor safety + collision callout | claude-opus-4-8-1m | §0 callout + §5 step 3 + §7 | 2026-06-29 |
| R1-S9 | Whole-build spend ceiling + checkpoint | claude-opus-4-8-1m | §5 step 4 + §7 | 2026-06-29 |
| R1-S10 | Commit OQ-4 to stage-rail reuse (no new route) | claude-opus-4-8-1m | §5 step 4 (+ reqs OQ-4 resolved) | 2026-06-29 |
| R1-S11 | Per-kind apply-time re-validation tasks | claude-opus-4-8-1m | §5 step 2 + §7 | 2026-06-29 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All 11 plan suggestions accepted; none re-litigated settled boundaries. | 2026-06-29 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-29

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-29 21:05:00 UTC
- **Scope**: Plan quality for the write-model extension (§3 proposal/confirm), the N1 project-tree manifest writer confinement (§2 N1), the N2 data-model bookend (§2 N2), sequencing risk (§5), and the build-environment / concurrency reality (§0). Settled inherited boundaries assumed, not re-litigated.

**Executive summary (top risks / gaps):**

1. §3 "RCT extends the `kind` vocabulary" names the new kinds but the plan never commits to a **closed apply-side allow-list** or a test that the agent registry exposes no apply tool — the security floor the design depends on.
2. §2 N1 says it "writes through `apply_write_plan`" but the plan has **no task for server-derived destinations or path-confinement validation** — the highest-severity missing work item.
3. §2 N1 / §4 step 3 omit **overwrite/clobber and multi-file atomicity** tasks for the manifest write.
4. §5 sequencing puts **N1 before N2**, but FR-RCT-5 makes the schema a gate that *precedes* manifests; building/testing the manifest writer before any schema gate exists risks validating N1 in an unrealistic order and masking the gate dependency.
5. §2 N2 / §4 collapse the **prose-brief confirm and `--promote`** into one flow step; the two-step ratification is not sequenced.
6. §0 + §3 flag the multi-worktree reality but no plan step addresses **concurrent RCT sessions / cursor (N3) staleness**.
7. The plan has **no validation strategy section** — each new piece (N1/N2/N3) lacks named tests; the focus file's security questions need explicit test tasks.
8. §0 build-env note pins `origin/main` but does not call out the **parallel-work collision risk** on contended kickoff files (proposals.py, web.py) that the repo's concurrent-agent reality creates.
9. No task covers **schema-revision drift** (a v2 `--promote` after manifests derive from v1).
10. No task covers a **whole-build spend ceiling / resumable checkpoint** (OQ-8) — §4's per-stage loop is many paid turns.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | Add a §5 task (and §3 note) to implement and test a **closed apply-side `kind` allow-list** in `apply_proposal`, plus an introspection test asserting `build_kickoff_registry` exposes only read/propose tools — no apply tool reachable by the loop. | §3 extends the kind vocabulary but never states the dispatcher rejects unknown kinds or that the loop has no write path; this is the inherited "loop never writes" invariant under a richer vocabulary (focus §A) and must be an explicit, tested task. | §5 sequencing (new step under item 1); §3 Proposal/confirm bullet | Unit: unknown `kind` → reject; registry introspection asserts zero apply-capable tools. |
| R1-S2 | Security | critical | In §2 N1, add an explicit task: the writer **derives each destination server-side from the manifest filename** and asserts the resolved realpath is under `docs/kickoff/inputs/` (reject `..`, absolute, symlink-escape) before any write. | §2 N1 says "writes through `apply_write_plan` confinement seam" but does not make dest-derivation/confinement a named work item; the proposal payload must not choose the path (focus §A/§B). Riding the seam is necessary but the dest rule is the actual control. | §2 N1, after the `apply_write_plan` sentence | Test: `dest=../../x.yaml`/absolute/symlink → rejected; realpath-under-root assertion fuzzed over the filename map. |
| R1-S3 | Data | high | Add §2 N1 tasks for **overwrite semantics (default no-clobber of differing hand-edited files; overwrite only on explicit replace-confirm)** and **multi-file atomic (staged) write** with rollback on partial failure. | §4 step 3 re-enters stages; the plan has no clobber/atomicity handling, so a re-run can destroy hand edits or leave a half-written input surface (focus §B). | §2 N1; §4 step 3 | Test: pre-edited manifest not overwritten without replace-confirm; injected mid-write failure → no file mutated. |
| R1-S4 | Architecture | high | Re-order §5 sequencing so the **schema gate (N2 + `schema` kind) lands before or with N1**, or add a §5 note that N1 is built behind a stub schema gate and its tests assert it refuses to run before a confirmed `schema.prisma`. | FR-RCT-5 makes the data model a gate preceding manifests; §5 currently builds N1 (item 1) before N2 (item 2), which can validate the manifest writer in an order the requirement forbids and hide the gate dependency. | §5 Sequencing | Verify the manifest stage is unreachable in a test harness until a confirmed schema exists. |
| R1-S5 | Validation | high | Add a **§7 Validation Strategy** section to the plan enumerating per-piece tests: N1 (confinement, clobber, atomicity), N2 (two-step ratification, lossy-brief surfacing), N3 (cursor staleness/concurrency), plus the registry allow-list assertion and the per-kind re-validation tests. | The plan maps FRs to seams but has no validation section; the focus file's security questions (§A–C) need explicit test tasks or they will not be built. | New §7 after §6 | Section exists with one named test per bullet; tests runnable in CI. |
| R1-S6 | Risks | high | In §2 N2 / §4, sequence the **two distinct human ratifications**: (1) confirm prose brief, (2) separate `generate contract --promote`. State that brief-confirm does not write `.prisma`. | §2 N2 and §4 step 2/3 read as one confirm; the focus file (§C) asks for two-step ratification of the DATA MODEL bookend. | §2 N2; §4 step 3 | Filesystem assertion: no `.prisma` after brief-confirm; only promote writes it. |
| R1-S7 | Risks | medium | Add a §2 N2 task for **schema revision drift**: a second `--promote` after manifests derive from v1 must detect dependent manifests and block/warn/re-assess, not silently invalidate them. | The bookend can be revised; the plan has no drift handling, so stale manifests can pass readiness while being broken (focus §C). | §2 N2 (or §4 re-assess step) | Test: promote v2 with an entity removed → orphaned manifest flagged. |
| R1-S8 | Ops | high | Add §5/§2-N3 tasks for **concurrent-session cursor safety** (validate cursor vs live `build_assess` on resume; advisory lock or last-writer-wins-with-detection) and a §0 callout flagging **parallel-work collision risk** on contended files (`proposals.py`, `web.py`). | §0 pins `origin/main` and notes concurrent multi-vendor agents but no step addresses two RCT sessions or contended-file edits (focus §D + build-env note). | §0 (collision note); §2 N3 / §5 | Test: two sessions advance the same tree → cursor not corrupted; hand-edit between stages → cursor reconciles to live assess. |
| R1-S9 | Ops | medium | Add a §5 task for a **whole-build spend ceiling + resumable checkpoint** distinct from the inherited per-session cap; resume must not re-spend completed stages. | §4 is a many-turn paid loop; the per-session envelope (FR-WM2-9a) cannot bound cross-session build spend (focus §E, OQ-8). | §5 (new item 4 sub-task); cross-ref FR-RCT-13 | Simulate a build crossing the per-session cap → checkpoints, resumes, cumulative spend bounded, completed stages not re-charged. |
| R1-S10 | Interfaces | medium | For OQ-4, the plan should **commit to the lower-risk reuse** (stage-rail extension of `/concierge/chat` + `_ChatStore`, per §3 Web chat "*Medium*") rather than a new `/red-carpet` route, and note that a new route duplicates the chat hardening (cookie/budget/mode-gate). | §3 already argues the web surface is "a staged experience reusing the chat engine, not a new chat"; a separate `/red-carpet` route forks the hardened chat surface and re-litigates inherited security controls (focus §D). | §3 Web chat bullet; §5 item 4 | Verify the web surface reuses the existing chat gate (`_concierge_write_gate`) with no duplicated CSRF/mode logic. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S11 | Validation | medium | §3 / §2 N1 should add per-kind **apply-time re-validation tasks** that run at human privilege after confirm and are at least as strict as propose-time: `schema`→grammar+promote-parse, `manifest`→extractor round-trip+dest-confinement, `value-input`→capture allow-list. A draft failing re-validation is rejected, not partially applied. | The plan asserts the loop's draft "is never trusted blindly" (FR-RCT-9) but defines no re-validation work; an adversarial draft passing propose-time could smuggle a bad value at apply (focus §A). | §3 Proposal/confirm; §2 N1 | Per-kind negative test: propose-time-valid but extractor-invalid draft → rejected at apply. |

---

## Requirements Coverage Matrix — R1

*Analysis only (reviewer observations to inform triage); not triage. Maps each requirement to the plan section/task that addresses it.*

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-RCT-1 (named staged flow, web+CLI, one engine) | §1 arch table; §3 Web chat + CLI; §4 conductor | Full | — |
| FR-RCT-2 (readiness-driven stage map, resumable) | §2 N3; §4 step 1; §3 Readiness | Partial | Cursor staleness/concurrency on resume not addressed (R1-S8); stage map derivation from `build_assess` named but not tested. |
| FR-RCT-3 (discoverable entry; bootstrap via instantiate) | §3 CLI; §5 item 3 | Partial | Web entry/CTA and the from-scratch `instantiate`-if-absent bootstrap have no explicit task. |
| FR-RCT-4 (interview→prose brief→`generate contract --promote`, N2) | §2 N2; §4 step 2 | Partial | Two-step ratification not sequenced (R1-S6); lossy prose→prisma surfacing not planned (R1 stress). |
| FR-RCT-5 (data model gates the rest) | §2 N2 (gate implied); §4 step 1 order | Partial | Gate not enforced in sequencing — N1 precedes N2 in §5 (R1-S4); no test that manifest stages refuse before a confirmed schema. |
| FR-RCT-6 (co-author inputs; N1 project-tree writer) | §2 N1; §3 Extractors; §4 step 3 | Partial | Dest-confinement (R1-S2), clobber + atomicity (R1-S3) not planned as tasks. |
| FR-RCT-7 (placeholder/bucket-2 only) | §1 arch table; §4 stage list | Partial | No task defines a measurable placeholder boundary or the bucket-4 hand-off notice. |
| FR-RCT-8 (propose-then-human-apply) | §3 Proposal/confirm; §4 steps 2–3 | Full | — |
| FR-RCT-9 (proposal kinds, per-kind apply paths) | §2 N1; §3 Proposal/confirm; §5 items 1–2 | Partial | Closed apply-side allow-list + no-loop-write registry assertion (R1-S1) and per-kind apply-time re-validation (R1-S11) not planned. |
| FR-RCT-10 (live readiness + run handoff) | §3 Readiness; §4 step 5 | Partial | Cascade-offer threshold (OQ-7) left as a fork; no concrete predicate/task. |
| FR-RCT-11 (wireframe checkpoint) | §4 step 5; §3 Cascade+wireframe | Full | — |
| FR-RCT-12 (per-increment reflection) | §1 Retrospective row; §4 step 4 | Full | — |
| FR-RCT-13 (cost posture, inherited caps) | §3 Web chat (chat hardening) | Partial | Whole-build/cross-session spend ceiling + resumable checkpoint (OQ-8) not planned (R1-S9). |
| FR-RCT-14 (observability stage-funnel events) | (none) | Missing | No plan task implements/registers the funnel events; apply-outcome/denial events also absent (R1-F9). |
| FR-RCT-15 (parity by shared construction) | §3 Web chat; §4 (one engine); §5 item 4 | Partial | Parity asserted but no test that web and CLI exercise the same engine/stage map/seam. |
