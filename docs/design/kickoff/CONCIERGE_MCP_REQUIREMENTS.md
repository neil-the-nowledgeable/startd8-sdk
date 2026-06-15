# Concierge MCP Command(s) — Requirements

**Version:** 0.4 (Post-CRP — write-path security hardening folded in; R1 triaged, all accepted)
**Date:** 2026-06-12
**Status:** Draft — read-only core shipped; write-path spec hardened, cleared to implement
**Parent role spec:** [`CONCIERGE_FRICTION_LOG_NAVIG8.md`](CONCIERGE_FRICTION_LOG_NAVIG8.md)
(the observed-activity source), [`HITM_ROLE_MODEL_REQUIREMENTS.md`](../HITM_ROLE_MODEL_REQUIREMENTS.md)
(role map; candidate role 3.11)
**Sibling precedents:** [`ROLE_KIT_CLI_REQUIREMENTS.md`](ROLE_KIT_CLI_REQUIREMENTS.md)
(deferred `startd8 kit <role>` advisory CLI — $0/read-only/advisory pattern),
`docs/design/wireframe/WIREFRAME_REQUIREMENTS.md` (the $0/read-only/advisory CLI this mirrors)
**MCP surface basis:** `src/startd8/mcp/gateway.py` — the single-tool-with-actions bridge
(`startd8_workflow` → `get_workflow_tool_schema()` / `handle_workflow_tool()`)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2, after a thorough planning pass against the
> actual MCP surface, the wireframe machinery, the manifest-extraction code, and the CLI/packaging
> conventions. The pass corrected ~6 of 13 requirements (>30% — the v0.1 was premature against an
> unfamiliar surface, exactly the case this loop is for). The largest correction would otherwise
> have surfaced mid-implementation, when it is 10× more expensive.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| MCP surface = the gateway single-tool-with-actions **bridge** (`get_workflow_tool_schema`/`handle_workflow_tool`) | The **real client-facing server is a SEPARATE repo** — `mcp/startd8-mcp-builder/startd8_mcp.py` (`FastMCP("startd8_mcp")`) — with **discrete `@mcp.tool()` functions** (list_skills, use_skill, help, status, tasks_*), each = Pydantic input + `@mcp.tool(annotations=…)` + async handler importing `startd8.*`. The gateway bridge is library-internal and **not** what the server uses. | **FR-C1 reframed:** `startd8_concierge` is **one `@mcp.tool()`** in the FastMCP server whose Pydantic input carries an `action` field. "Single tool, action-dispatched" survives as a *within-tool* design; registration is `@mcp.tool()`, not the gateway bridge. |
| The tool lives in the SDK (gateway.py) | Logic and registration are in **two packages of the same repo**: `src/startd8/` ships the callable library; the self-contained subproject `mcp/startd8-mcp-builder/` (own `pyproject`=`startd8-mcp`, CLAUDE.md, CI/CODEOWNERS — **tracked in the SDK repo, not a separate repo**) holds the `@mcp.tool()` wrapper alongside its existing 17 `startd8_*` tools. | **New FR-C14 (cross-package split).** Simpler than a cross-repo split; both halves are committed in one repo (also satisfies F-10 durability). |
| `derive-contract` is "a deterministic AST transform, not generation" (implied lightweight) | Pydantic→Prisma introspection is **net-new AST work**; only the *emit* half is reusable (`manifest_extraction/entities.py` `EntityGraph` → `prisma_emitter.render_prisma_schema()`). The introspection front-half does not exist. | **FR-C8 is the heaviest action by far → DEFERRED out of v1** to its own follow-on (resolves OQ-1 granularity). When built, it reuses `prisma_emitter` for the back half only. |
| `assess` wraps a wireframe that "exists" (hoped) | **CONFIRMED:** `build_wireframe_plan()` → `WireframePlan` carries the exact provisioning states; `cli_wireframe.py` is the rendering precedent. | **FR-C6/FR-C10 strengthened** — `assess` is cheap (wrap + summarize); wireframe is the model for the whole JSON/CLI shape. `validate` folds into `assess` (no separate action). |
| `instantiate-kickoff` just copies templates | Templates in `docs/design/kickoff/templates/` are **NOT packaged** (docs tree isn't shipped). Must become package data — `src/startd8/help_content/` is the shipped-data precedent. | **FR-C7 gains a prerequisite:** package the templates (`src/startd8/concierge_templates/`) before the action can read them at a consumer site. |
| annotations "MUST carry readOnlyHint…" at the gateway level | Annotations are a **FastMCP-server** convention (`@mcp.tool(annotations={readOnlyHint, destructiveHint, idempotentHint, openWorldHint})`), absent from `mcp/types.py`. | **FR-C12 retargeted** to the wrapper layer; SDK gateway types unaffected. |

**Resolved open questions:**
- **OQ-1 → Resolved.** v1 = `survey` · `assess` (absorbs `validate`) · `instantiate-kickoff` · `log-friction`. `derive-contract` **deferred** to its own action/follow-on (it is net-new AST work).
- **OQ-2 → Resolved.** Logic in a new `src/startd8/concierge/` package (stable API); registration as a `@mcp.tool()` in the FastMCP-builder repo. Not the gateway, not the SkillRegistry.
- **OQ-4 → Resolved (and deferred).** Pydantic-only front-half is net-new; reuse `prisma_emitter` back-half. Lands with the deferred `derive-contract`.
- **OQ-5 → Resolved.** Package templates as `concierge_templates/` package-data (`help_content/` precedent); read via `importlib.resources`.
- **OQ-6 → Resolved.** `assess` wraps `build_wireframe_plan()`; never recomputes provisioning state.
- **OQ-7 → Open (sharpened).** A FastMCP tool writing into a consumer project path still crosses a trust boundary; `apply:true` + path-confinement (FR-C2) are the controls. Kept for CRP.
- **OQ-3 → Partially resolved.** Mechanism known (own `typer.Typer` app, `cli_queue.py` pattern); the assist/kit/concierge family relationship stays a design choice.

---

## 1. Problem Statement

The **Concierge** is the project-side SDK-onboarding role, defined empirically from the navig8
instantiation (friction log, 10 items). Today every Concierge activity is performed by a human
+ Claude reading docs and running ad-hoc shell/greps; nothing is exposed as a callable surface
an *external AI agent* (the consuming project's own assistant, or a remote orchestrator) can
invoke through the SDK's MCP gateway.

The operating posture is fixed (operator decision 2026-06-07): the Concierge **assists** — it
surveys, derives starters, validates, and advises; it does **not** operate or orchestrate
(it never runs the cascade, never records a gate sign-off, never mutates the consuming repo
without the team driving). MCP commands must encode that posture in their *capabilities*, not
just their docs.

### Gap table

| Concierge activity (observed) | Today | Gap |
|-------------------------------|-------|-----|
| Brownfield asset survey / triage | ad-hoc `find`/`grep`/`Explore` agent | No structured, repeatable survey an agent can call |
| Kickoff package instantiation | hand-copy templates, hand-fill | Not callable; provenance discipline applied by memory |
| Contract derivation from existing models | hand-written by Claude (F-5) | No models→prisma surface; risk of contract↔models drift |
| Inputs/contract validation | `startd8 wireframe` (exists, $0/advisory) | Wireframe covers the cascade view, not the *onboarding-readiness* view |
| Friction capture back to SDK | hand-edited markdown, **lost when uncommitted (F-10)** | No durable, structured capture path |
| Readiness assessment / "what's next" | Claude reads state, narrates | No machine-readable onboarding-state report |

### Why MCP (not just a CLI)

The Role Kit CLI sibling is a *terminal* command for the human operator. The Concierge surface
is for the **consuming project's agent** to self-serve onboarding through the gateway the SDK
already ships — the same way `startd8_workflow` lets an external agent discover/run workflows.
A CLI (`startd8 concierge …`) MAY back the same logic (FR-C9), but the MCP tool is the primary
deliverable here.

---

## 2. Requirements

### Command surface & shape

- **FR-C1 — Single tool, action-dispatched, registered as a FastMCP `@mcp.tool()`.** Expose
  **one** MCP tool, `startd8_concierge`, registered in the FastMCP server
  (`mcp/startd8-mcp-builder/startd8_mcp.py`) the same way `startd8_use_skill` /
  `startd8_status` are: a Pydantic input model carrying an `action` field (enum) +
  `@mcp.tool(annotations=…)` + an async handler that calls the SDK library. (The action-dispatch
  *within* the tool echoes the gateway's `startd8_workflow` shape, but registration is the
  FastMCP discrete-tool pattern, **not** the gateway bridge — see §0.) **v1 actions:**
  `survey` · `assess` · `instantiate-kickoff` · `log-friction`. (`validate` folded into
  `assess`; `derive-contract` deferred — FR-C8.)
- **FR-C2 — Assist-only capability envelope (load-bearing).** No action may: run a generation
  cascade or pipeline pass; record a validation/gate sign-off; promote any artifact out of a
  candidate/estimate provenance state; or write outside the **consuming project directory**.
  The tool *prepares and advises*; the team *decides and runs*. This is a capability boundary,
  not a doc convention. **"Consuming project directory" is defined operationally (R1-F7)** as the
  realpath-confined root of FR-C3.1: `realpath(project_root)` and everything lexically beneath it
  after each target is itself resolved; comparisons are case-fold-aware on case-insensitive
  filesystems and `./`/`..`-normalized so equivalent spellings reach the same decision.
- **FR-C3 — MCP never writes; the CLI writes (OQ-7 resolution, 2026-06-11).** Over MCP, **all
  actions are read/preview-only**: `survey`/`assess` are pure reads; `instantiate-kickoff`/
  `log-friction` **return a planned-write descriptor (target paths + per-file status) but do not
  touch disk**. The only writer is the CLI (FR-C13), which runs at the human's own filesystem
  privilege — so **no new write trust boundary** is crossed by an LLM-invoked MCP call. Rationale:
  `apply:true` is a *safety* control (no silent writes), not an *authorization* control (an LLM
  can set it); read/preview-only MCP sidesteps the write-authorization question for v1.

  The CLI writer's confinement guarantees are an **enumerated, individually-testable invariant set
  (R1-F3)** — each maps 1:1 to a security test (plan Step 5):
  - **FR-C3.1 — Root integrity (R1-F1/R1-S3).** Reject a `project_root` whose lexical path differs
    from its realpath (a symlinked root), OR confine against an explicit
    `STARTD8_CONCIERGE_ALLOWED_ROOTS` allowlist. A symlinked root otherwise makes every write
    "inside" the resolved base while bytes land in the symlink target.
  - **FR-C3.2 — No traversal / no symlink escape.** Every target resolves inside the confined
    root; reject `..` traversal and symlink escape; **validate every parent component** created
    by `mkdir`, not just the leaf (R1-S2).
  - **FR-C3.3 — Write-time re-validation, not plan-time only (R1-S1).** Enforce confinement at the
    moment of write via dir-fd-relative open (`O_NOFOLLOW`/`O_EXCL`, write/replace through the
    validated parent's fd), closing the resolve→replace TOCTOU window — the validated inode is the
    written inode.
  - **FR-C3.4 — No clobber.** `new` refuses if the target exists; overwrite requires `--force`;
    `append` only appends, never truncates.
  - **FR-C3.5 — Atomic, including append (R1-S8).** `new`/`overwrite` write temp+`os.replace`;
    `append` uses `O_APPEND` single-`write()` (or temp+replace) — crash-safe and safe under
    concurrent CLI invocations.
  - **FR-C3.6 — WritePlan is untrusted data, not a capability (R1-S4).** The safe-writer
    re-confines and re-classifies every `path`/`action` independently of who built the plan; a
    hand-crafted or agent-round-tripped plan carrying an out-of-confinement path is hard-stopped.

  If MCP writes are ever added, they gate behind the `STARTD8_CONCIERGE_ALLOWED_ROOTS` allowlist +
  these invariants, **not** merely `apply:true`.
- **FR-C3a — MCP read/disclosure bound (R1-F2/R1-S5 — the live OQ-7 leak).** Preview descriptors
  returned over MCP may report path + per-file status (`new`/`exists`/`would-overwrite`/`blocked`)
  but **MUST NOT return existing consumer-file *content* or content diffs**. Builders may `stat`
  to classify status; they must not read-and-return existing bytes over MCP. Without this, an
  untrusted LLM exfiltrates consumer file contents through previews *with no write ever occurring*
  — the disclosure channel the write-only framing left open.
- **FR-C4 — `$0` by default; LLM only where the activity is irreducibly generative.** `survey`,
  `assess`, `validate`, `instantiate-kickoff` (template copy + provenance fill), and
  `derive-contract` (models→prisma is a *deterministic* AST transform, not generation) are all
  $0. Any action that would need an LLM (e.g. a future "draft requirements from PRD") MUST be a
  distinct action that declares its cost and is off by default.

### Per-action behavior

- **FR-C5 — `survey`.** Given a project root, return a structured brownfield triage: detected
  product boundary candidates, existing requirement/PRD docs (+ whether they match the
  extraction format), existing models/entities, test-fixture candidates, path couplings that a
  carve would break (the F-3 grep), and any PII/personal-material risk flags (F-2). Read-only.
- **FR-C6 — `assess`.** Return a machine-readable **onboarding-readiness report**: per kickoff
  input domain (business-targets / observability / conventions / build-preferences) and per
  assembly input (schema / app.yaml / manifests), the provisioning state
  (`authored|estimate|config-default|placeholder|absent`) and what's blocking the next step.
  This is the "what's next" report the team's `NEXT_STEPS.md` is the prose form of. Composes
  with `startd8 wireframe` rather than duplicating it (FR-C10).
- **FR-C7 — `instantiate-kickoff`.** Project the kickoff templates into the consuming project
  with provenance pre-filled per posture (production vs prototype/solo), every value carrying
  honest `provenance`. **Over MCP: returns the planned files + provenance, never writes** (FR-C3);
  the CLI applies them. Never fabricates the `owners`/contacts block (tier U — no LLM starter;
  ships flagged). **"Flagged" is concrete (R1-F8):** the `owners` block ships with provenance
  `placeholder` and `.test`-domain markers; under `--posture production` an `--apply` that would
  write a still-`placeholder` owners block **warns** (advisory posture — never blocks). Default
  posture is `prototype` (R1 PQ-6 — zero required human input, the navig8 path). **Prerequisite
  (planning):** the templates currently
  live under `docs/design/kickoff/templates/`, which is **not shipped in the wheel**; this action
  depends on first packaging them as package-data (`src/startd8/concierge_templates/`, following
  the `help_content/` precedent) and reading via `importlib.resources`. The packaging task is a
  named dependency of this FR, not an afterthought.
- **FR-C8 — `derive-contract` (DEFERRED — own follow-on, not v1).** Deterministically derive a
  `schema.prisma` candidate from the project's existing Pydantic models, carrying the navig8
  derivation rules as transform logic: semantic-id→`nodeKey`+`@@unique`, `Dict`/`List`→`Json`,
  cross-list trace→join model, hyphenated enum value normalization, builtin-name renames,
  computed fields stay computed. Emits the contract **plus a derivation report** naming every
  deviation and exclusion (so the Architect can ratify — the gate stays theirs, FR-C2).
  Preview-by-default. **Deferred because** planning showed the Pydantic→IR introspection
  front-half is net-new AST work (only the emit half reuses
  `manifest_extraction/prisma_emitter.render_prisma_schema()`); it is heavier than the other
  four actions combined and earns its own reflective pass. v1 ships without it; navig8's contract
  was derived by hand and stands.
- **FR-C9 — `log-friction`.** Produce a structured friction item for the project's Concierge
  friction log. **Over MCP: returns the entry + target path** (FR-C3); the CLI appends it. The
  log lives **in the consuming project, which the team owns and commits** (the F-10 lesson) —
  never the only copy untracked in the SDK tree. **Format acceptance criteria (R1-F4/R1-S7 —
  resolves PQ-1):** a single durable append-only file, `concierge-friction.jsonl` (JSON Lines) —
  one durable home (F-10), append-only by construction (no whole-file rewrite, no parse-to-
  increment: id = ULID-per-line or line count), machine-appendable, and race/crash-safe per
  FR-C3.5. Markdown is a **rendered view** (by `assess`/a viewer), never a second persisted
  source of truth.

### Output, integration, durability

- **FR-C10 — Compose, don't duplicate.** Where the SDK already ships the capability
  (`startd8 wireframe` for cascade view; `generate backend --check` for drift), the Concierge
  action *calls and summarizes* it, never reimplements. `assess` wraps wireframe;
  `derive-contract`'s output is validated by re-running wireframe.
- **FR-C11 — Structured, schema-versioned results.** Every action returns a stable,
  schema-versioned JSON object (the gateway/`handle_workflow_tool` convention). Human-readable
  rendering is a separate concern (the CLI/Rich layer, FR-C13).
- **FR-C12 — Tool annotations honest about the posture, and verified (R1-F5).** The MCP
  tool/action schema MUST carry correct annotations: `readOnlyHint: true` (the MCP surface never
  writes — FR-C3); `destructiveHint: false` (Concierge never destroys). These annotations are how
  a calling agent *knows* the assist-only envelope without reading prose — so an annotation that
  lies is worse than none. A **conformance test** MUST verify runtime behavior matches the hint:
  invoke every action over the MCP tool against a filesystem watcher and assert **zero writes**
  (proves `readOnlyHint`) and no deletions (proves `destructiveHint`).
- **FR-C13 — CLI parity. [DONE — read-only actions]** `startd8 concierge survey|assess` backs
  the same `handle_concierge_tool` code path as the MCP tool (one logic, two front doors —
  FR-W16). Rich by default, `--json` for the schema-versioned payload, advisory exit 0 / exit 2
  on unreadable input (FR-W9). Implemented in `src/startd8/cli_concierge.py`, registered in
  `cli.py` beside `assist`. Write actions will land here as the CLI is the sole writer (OQ-7).
- **FR-C14 — Cross-package split (SDK logic / MCP-builder wrapper), one repo.** The callable
  logic and its stable public API (`build_concierge_*` / `handle_concierge_tool(action,
  project_root, …)`) live in the SDK package (`src/startd8/concierge/`). The thin `@mcp.tool()`
  registration — Pydantic input model, annotations, async handler delegating to the SDK — is
  added to the existing FastMCP server in the **`mcp/startd8-mcp-builder/`** subproject
  (`startd8_mcp.py`), beside the 17 `startd8_*` tools already there. Both packages live in the
  startd8-sdk repo (the subproject has its own `pyproject`/CI but is **not** a separate git repo).
  The wrapper imports the SDK as a library and declares the minimum SDK version exposing the API,
  and MUST stay thin (no business logic) so the CLI (FR-C13) and the MCP tool render from the one
  SDK code path. **Registration target (resolved):** add the `@mcp.tool()` to the root monolith
  **`startd8_mcp.py`** — it is the documented "Primary Server," the module all 14 test files
  import, the CLAUDE.md launch target (`python3 startd8_mcp.py`), and the public entrypoint the
  `startd8_mcp_server/` package itself defers to "for backward compatibility." Caveat for the
  implementer: the 20 existing tools are **duplicated** in `startd8_mcp_server/server.py` (a
  parked monolith→package refactor with the identical tool surface); a tool added to the monolith
  must be mirrored there too, or the refactor's go-forward status confirmed first — pre-existing
  drift, flagged not inherited.
- **FR-C15 — Idempotency & drift for `instantiate-kickoff` (R1-F6/R1-S6).** Per-file skip-existing
  is the right default but must not silently certify a half-instantiated package as done. The
  action emits a **package-level verdict** (`complete` / `partial` / `drifted`) and supports a
  `--check` mode reporting per-file state (`matches-template` / `diverged` / `absent`) with a
  **non-zero exit on drift**, mirroring `generate backend --check` (composes with FR-C10). Never
  merges YAML values; `--force` is required to overwrite a diverged file.

---

## 3. Non-Requirements

- **No orchestration.** Never runs the cascade, a pipeline pass, or a workflow. (That's
  `startd8_workflow`'s job; Concierge may *point at* it but not invoke it.)
- **No gate recording / approvals.** Never records attorney/architect/PO sign-off; gates stay
  with their owning role (FR-C2). No SLA/assignment/notification machinery (HITM §5 stands).
- **No real-content generation.** Bucket-4 content is the company's; the Concierge prepares
  buckets 1–2 inputs only.
- **No multi-project orchestration.** One consuming project per call. No fleet/portfolio view.
- **Not a replacement for the human+Claude Concierge.** v1 exposes the *mechanizable* subset of
  the observed activities; judgment-heavy assists (PRD→requirements translation) stay manual or
  become explicitly-LLM actions later.
- **Not a new MCP server.** Adds one `@mcp.tool()` to the existing FastMCP server
  (`mcp/startd8-mcp-builder/startd8_mcp.py`, tool #18); no new transport/server.

## 4. Open Questions

> OQ-1/2/4/5/6 resolved by the planning pass (§0). OQ-3/OQ-7 resolved by design decision
> 2026-06-11 (below). OQ-8 remains a small implementation-pass call.

- **OQ-3 — RESOLVED (2026-06-11): three sibling commands, `concierge` composes with `kit`.**
  `assist` / `kit` / `concierge` are three phases of one project lifecycle — **triage** /
  **deliver** / **onboard** — not competitors, and not one umbrella noun (that would force churn
  on shipped `assist` and conflate the phases). Each is its own `typer.Typer` app. Where they
  touch: `concierge assess` and `kit` both report readiness, at different grains (project-inputs
  vs role-kit completeness) — so `assess` **calls** `kit` for the kit-completeness line rather
  than reimplementing it (FR-C10). Since `kit` is deferred, that is a forward-compatible seam,
  not a v1 dependency. Folding `kit` *into* `concierge` is rejected (a category error — `kit` is
  delivery-time and role-scoped; `concierge` is onboarding). `concierge` reuses `assist`'s
  conventions (idempotent, exit-0-always, `--no-emit`/`--no-write`) but stays a separate command.
- **OQ-7 — RESOLVED (2026-06-11), then HARDENED by CRP R1 (2026-06-12).** MCP is read/preview-only;
  the CLI is the only writer (FR-C3). The CRP pass found the write-only framing left a **read-side
  disclosure leak** (a preview returning existing-file content exfiltrates without a write) and a
  TOCTOU/symlinked-root confinement gap — now closed by FR-C3.1–C3.6 + FR-C3a. The write trust
  boundary was the easy half; the CRP earned its keep on the read half. Allowlist remains the
  design if MCP writes are ever added.
- **OQ-8 — `survey` PII detection depth (F-2).** Open (small). How far does the
  personal/PII-material flag go — filename/extension heuristics only, or content sniffing?
  Content sniffing in a read action has its own privacy implications. Lean: path/extension
  heuristics + a conservative "review these" list, **never reading flagged file contents**.

---

*v0.2 — Post-planning self-reflective update. 6 of 13 requirements corrected (FR-C1 reframed to
FastMCP registration, FR-C7 gained a packaging prerequisite, FR-C8 deferred, FR-C12 retargeted),
1 added (FR-C14 cross-package split), 1 action merged (`validate`→`assess`), 5 open questions
resolved. The one expensive error caught: the MCP surface is a separate FastMCP subproject with
discrete tools, not the gateway bridge the draft was built on.*

*v0.3 — OQ-3 and OQ-7 resolved as design decisions (not unknowns), so CRP is not warranted yet:
MCP is read/preview-only in v1 (CLI is the sole writer — removes the write trust boundary), and
`concierge` ships as a sibling of `assist`/`kit`, composing with `kit`. Next move is a thin spike
of the read-only core (`survey`+`assess`) — which, being read-only, needs neither OQ-7 nor the
template-packaging prerequisite — on branch `feat/concierge-mcp`. CRP is reserved for the
write-action increment, where the security lens earns its keep.*

*v0.4 — Post-CRP (write-path increment). CRP R1 (claude-opus-4-8-1m) triaged: all 8 F-suggestions
accepted and folded in. New: FR-C3.1–C3.6 (enumerated confinement invariants — root integrity,
no-escape, write-time TOCTOU close, no-clobber, atomic-incl-append, WritePlan-untrusted),
**FR-C3a** (MCP read/disclosure bound — the live leak the write-only framing missed), FR-C15
(idempotency/drift). Tightened: FR-C2 (defines "consuming project directory"), FR-C7 (owners flag
+ posture warn), FR-C9 (`.jsonl` durability), FR-C12 (conformance test). The CRP earned its keep on
the read-side disclosure leak that the internal reflective loop had declared resolved.*

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

> R1 triage (2026-06-12): all 8 F-suggestions ACCEPTED — each was a real gap on a security-sensitive
> doc with known open questions; none were noise. Folded into the FR prose as below.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Reject symlinked `project_root`; re-check confinement at write time | R1 | → FR-C3.1 + FR-C3.3 | 2026-06-12 |
| R1-F2 | Bound MCP read/disclosure: preview never returns existing-file content | R1 | → **FR-C3a** (the live OQ-7 leak) | 2026-06-12 |
| R1-F3 | Restate FR-C3 confinement as enumerated, individually-testable invariants | R1 | → FR-C3.1–C3.6 | 2026-06-12 |
| R1-F4 | FR-C9 friction-log format + append-safety acceptance criteria | R1 | → FR-C9 (single append-only `.jsonl`, crash/race-safe) | 2026-06-12 |
| R1-F5 | FR-C12 conformance test that runtime matches `readOnlyHint` | R1 | → FR-C12 (fs-watcher zero-write assertion) | 2026-06-12 |
| R1-F6 | Idempotency/drift: package verdict + `--check` | R1 | → **FR-C15** | 2026-06-12 |
| R1-F7 | Define "consuming project directory" operationally | R1 | → FR-C2 (realpath-confined root per FR-C3.1) | 2026-06-12 |
| R1-F8 | Concrete `owners` flag + posture interaction | R1 | → FR-C7 (`placeholder`+`.test`; production warns, never blocks) | 2026-06-12 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-11

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-11 00:00:00 UTC
- **Scope**: Requirements-side review weighted on the write-path security surface (FR-C2/C3/C12), idempotency/durability acceptance criteria, and the OQ-7 read-side disclosure boundary. Adversarial pass included.

##### Executive summary (≤10 bullets)

- FR-C3 frames `apply:true` correctly as a *safety* not *authorization* control, but its confinement clause is prose, not testable acceptance criteria — the security invariants need to be enumerated and falsifiable.
- FR-C3's confinement says "realpath within the named project root" but does not address a `project_root` that is *itself* a symlink (plan PQ-3) — the strongest single gap on the security surface.
- The OQ-7 boundary is stated as write-only; the **read/disclosure** side (preview returning existing-file content/exists-status over MCP) is never bounded by any FR.
- FR-C2 ("write outside the consuming project directory" forbidden) defines the boundary but gives no verification method and no definition of "consuming project directory" under symlink/relative-path conditions.
- No FR sets idempotency / partial-existing acceptance criteria (plan PQ-2); "skip existing unless --force" lives only in the plan, with no requirement that a half-instantiated package be detectable.
- FR-C9 mandates the friction log be durable and committed but does not specify its format or append-safety — leaving PQ-1 (markdown vs JSON vs JSONL) entirely to the plan.
- FR-C12 enumerates annotation values but does not require a test that the *running* tool's behavior matches its declared `readOnlyHint`/`destructiveHint` (annotation honesty is asserted, not verified).
- FR-C7's "never fabricates the `owners` block (tier U); ships flagged" has no acceptance criterion for what "flagged" means or how `--apply` treats it (plan PQ-4 is open).

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | FR-C3 says the CLI enforces "realpath within the named project root; reject `..`/symlink escape" — add an explicit sub-requirement that a `project_root` which is itself a symlink (or whose realpath differs from its lexical path) is rejected or allowlisted, and that confinement is re-checked at write time, not only at plan time. | The current wording confines against the *resolved* root, so a symlinked root passes confinement while writing into the symlink target (plan PQ-3). Plan-time-only check leaves a TOCTOU gap. | FR-C3 (new bullet on root integrity + write-time re-check) | Acceptance test: `ln -s /etc root && instantiate-kickoff root --apply` must refuse; assert no bytes written under realpath of `/etc`. |
| R1-F2 | Security | high | Add a requirement bounding the MCP **read/disclosure** surface: preview payloads (WritePlan) may report path + status but MUST NOT return existing consumer-file *content* or content diffs over MCP. | OQ-7/FR-C3 close the write boundary but say nothing about disclosure; a preview that renders by reading existing files lets an untrusted LLM exfiltrate file contents without any write. This is the live OQ-7 leak. | New FR (or FR-C3 sub-clause) on preview disclosure limits | Acceptance: target exists with secret content; assert the MCP preview JSON contains none of those bytes. |
| R1-F3 | Validation | high | FR-C3's confinement guarantees are prose; restate them as an enumerated, individually-testable invariant set (no traversal, no symlink escape, root-integrity, no-clobber, atomic, append-only, write-time re-validation) so each has a named test. | "Reject `..`/symlink escape; no clobber without --force" bundles ≥5 distinct guarantees into one sentence — untestable as written; an implementer cannot tell which cases are acceptance-blocking. | FR-C3 (break into FR-C3.1…C3.n) | Each enumerated invariant maps 1:1 to a security test in the plan's Step 5 set. |
| R1-F4 | Data | medium | FR-C9 requires the friction log be durable/committed but does not specify format or append-safety. Add acceptance criteria: single durable file, append-only, machine-appendable without parsing human-formatted rows, crash-safe append. | PQ-1 is unresolved at the requirements level; without a format criterion the implementer may choose the brittle markdown-table-append the focus file warns against (id-parse, race on concurrent append). | FR-C9 (durability acceptance criteria) | Acceptance: concurrent `log-friction --apply` ×2 yields two whole, distinct entries; a crash mid-append never tears a line. |
| R1-F5 | Validation | medium | FR-C12 asserts annotation values but not that runtime behavior matches them. Add a requirement that a conformance test verifies the tool performs no disk write when `readOnlyHint:true` and never deletes (asserting `destructiveHint:false`). | Annotations are how a calling agent learns the assist-only envelope (FR-C12's own rationale); an annotation that lies is worse than none. Honesty must be verified, not declared. | FR-C12 (add conformance-test requirement) | Acceptance: invoke every action over the MCP tool against an fs-watcher; assert zero writes for read-only-hinted actions. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Risks | medium | Add an idempotency/partial-existing requirement: `instantiate-kickoff` must report a package-level verdict (`complete`/`partial`/`drifted`) and detect a half-instantiated or template-diverged package, not silently report success on a per-file basis. | Plan PQ-2 + navig8's existing partial files: a project with some kickoff files present reads as "done" though stale/diverged. No FR currently requires aggregate detection. | New FR-C15 (idempotency & drift) | Acceptance: instantiate, hand-edit one file, re-run; assert `drifted` reported and non-zero CLI exit. |
| R1-F7 | Security | medium | FR-C2 forbids writing "outside the consuming project directory" but never defines that directory under relative-path/symlink/case-insensitive-FS conditions; add a precise definition tied to the confinement mechanism in FR-C3. | "Outside the consuming project directory" is the load-bearing boundary phrase yet is undefined operationally; on a case-insensitive FS `Root/x` vs `root/x` and `..`-normalization edge cases are ambiguous. | FR-C2 (define "consuming project directory" = realpath-confined root per FR-C3) | Acceptance: case-only and `./`-prefixed path variants resolve to the same confined decision. |
| R1-F8 | Security | low | FR-C7's "ships flagged" for the `owners`/tier-U block needs a concrete criterion: define the flag value (e.g. provenance `placeholder` + `.test` marker) and whether `--apply` warns or blocks under `production` posture (plan PQ-4 is open). | "Ships flagged" is untestable as written; without a defined flag a consuming project could promote fabricated owners unnoticed — exactly the provenance-honesty FR-C7 protects. | FR-C7 (define owners flag + posture interaction); resolve PQ-4 | Acceptance: assert instantiated `owners` block carries the defined flag and that `--apply --posture production` emits the documented warn/block. |


