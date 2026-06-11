# Concierge MCP Command(s) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-11
**Status:** Draft
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
| The tool lives in the SDK (gateway.py) | Logic and registration are in **two different repos**: SDK ships the callable library; the FastMCP-builder repo (own CI/CODEOWNERS) holds the `@mcp.tool()` wrapper. | **New FR-C14 (cross-repo split).** Echoes F-10 durability — the wrapper lands in a committed repo, not an untracked tree. |
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
  candidate/estimate provenance state; or write outside the **consuming project** directory.
  The tool *prepares and advises*; the team *decides and runs*. This is a capability boundary,
  not a doc convention.
- **FR-C3 — Read-mostly, explicit-write.** `survey`/`assess`/`validate` are pure read ($0, no
  mutation). `instantiate-kickoff`/`derive-contract`/`log-friction` write files, but only into
  the caller-named consuming-project path, only with a `dry_run` default of *preview* (return
  the diff/plan; require an explicit `apply: true` to write). Never silent writes.
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
  honest `provenance`. Preview-by-default (FR-C3). Never fabricates the `owners`/contacts block
  (tier U — no LLM starter; ships flagged). **Prerequisite (planning):** the templates currently
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
- **FR-C9 — `log-friction`.** Append a structured friction item to the project's Concierge
  friction log, **persisted durably** (written into the consuming project, which the team owns
  and commits — the F-10 lesson). Never leaves the only copy untracked in the SDK tree.

### Output, integration, durability

- **FR-C10 — Compose, don't duplicate.** Where the SDK already ships the capability
  (`startd8 wireframe` for cascade view; `generate backend --check` for drift), the Concierge
  action *calls and summarizes* it, never reimplements. `assess` wraps wireframe;
  `derive-contract`'s output is validated by re-running wireframe.
- **FR-C11 — Structured, schema-versioned results.** Every action returns a stable,
  schema-versioned JSON object (the gateway/`handle_workflow_tool` convention). Human-readable
  rendering is a separate concern (the CLI/Rich layer, FR-C13).
- **FR-C12 — Tool annotations honest about the posture.** The MCP tool/action schema MUST carry
  correct annotations: `readOnlyHint` true for survey/assess/validate; `destructiveHint` false
  for all (Concierge never destroys); writes gated behind `apply`. These annotations are how a
  calling agent *knows* the assist-only envelope without reading prose.
- **FR-C13 — Optional CLI parity.** A `startd8 concierge <action>` CLI MAY back the same
  `build_*`/`handle_concierge_tool` code path (one logic, two front doors — the FR-W16 stable-API
  pattern; `cli_queue.py` is the `typer.Typer` + `app.add_typer` registration template), but the
  MCP tool is the primary deliverable; CLI parity is deferrable.
- **FR-C14 — Cross-repo split (SDK logic / MCP-builder wrapper).** The callable logic and its
  stable public API (`build_concierge_*` / `handle_concierge_tool(action, project_root, …)`)
  live in the SDK (`src/startd8/concierge/`). The thin `@mcp.tool()` registration —
  Pydantic input model, annotations, async handler delegating to the SDK — lives in the separate
  **`mcp/startd8-mcp-builder`** repo (its own CI/CODEOWNERS). Version contract: the wrapper
  imports the SDK as a library and pins/declares the minimum SDK version exposing the API. The
  wrapper MUST stay thin (no business logic) so the CLI (FR-C13) and the MCP tool render from the
  one SDK code path. (This split also satisfies the F-10 durability lesson: the only copies of
  both halves live in committed repos, never an untracked working tree.)

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
- **Not a new MCP server.** Extends the existing gateway tool surface; no new transport/server.

## 4. Open Questions

> OQ-1/2/4/5/6 were **resolved** by the planning pass — see §0. Remaining:

- **OQ-3 — Relationship to `startd8 assist` (Service Assistant) and the deferred `startd8 kit`.**
  Three onboarding-adjacent surfaces (assist = run/post-mortem triage, kit = role docs, concierge
  = onboarding). Mechanism is settled (each its own `typer.Typer` app); the *product* question —
  one family vs three, and whether concierge subsumes or calls `kit` — stays open. Lean: ship
  concierge standalone; revisit consolidation once `kit` activates.
- **OQ-7 — Write authorization across the trust boundary.** A FastMCP `startd8_concierge` call
  writing into a consumer project path crosses a trust boundary. Controls proposed: `apply:true`
  required for any write (FR-C3) + hard path-confinement to the caller-named project root
  (FR-C2). Is that sufficient, or does a write need an additional capability token / explicit
  allowlist of the project root? Flag for CRP (security area).
- **OQ-8 — `survey` PII detection depth (F-2).** How far does the personal/PII-material flag go —
  filename/extension heuristics only, or content sniffing? Content sniffing in a read action has
  its own privacy implications. Lean: path/extension heuristics + a conservative "review these"
  list, never reading flagged file contents.

---

*v0.2 — Post-planning self-reflective update. 6 of 13 requirements corrected (FR-C1 reframed to
FastMCP registration, FR-C7 gained a packaging prerequisite, FR-C8 deferred, FR-C12 retargeted),
1 added (FR-C14 cross-repo split), 1 action merged (`validate`→`assess`), 5 open questions
resolved. The one expensive error caught: the MCP surface is a separate FastMCP repo with
discrete tools, not the gateway bridge the draft was built on.*
