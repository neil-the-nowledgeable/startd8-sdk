# Startd8 MCP Improvements — Central Task List (Worktree-First)

**Purpose**: A detailed, parallelizable implementation plan to improve the Startd8 MCP server.

**Design goal**: multiple agents can work concurrently using **separate git worktrees** with minimal merge conflicts.

**Scope**: Improvements to `startd8_mcp.py` (skills/tools/resources/tasks/prompt tools), correctness, safety, maintainability, observability, and developer experience.

---

## How to use this plan with worktrees

### Worktree conventions

- **One feature group per worktree/branch**.
- **Do not edit another group’s files** unless a task explicitly says so.
- **All cross-cutting changes go through FG01 (core architecture)**.

**Suggested branch names**:

- `fg01-core-arch`
- `fg02-response-contracts`
- `fg03-skills-resources`
- `fg04-skill-execution-providers`
- `fg05-task-runner`
- `fg06-observability-devex`

### Suggested git worktree commands (once git repo exists)

```bash
# Example: create a worktree for FG03
git checkout -b fg03-skills-resources
git worktree add ../startd8-mcp-fg03 fg03-skills-resources

# Repeat per feature group
```

### Merge/coordination order (to reduce conflicts)

1) **FG01** (module split + public interfaces) merges first
2) **FG02** (response contracts + error model) merges second
3) **FG03/FG04/FG05/FG06** can proceed in parallel once FG01/FG02 contracts are stable

---

## Global contracts (shared across feature groups)

These contracts are referenced by multiple worktrees. Do not change them outside FG02.

- **Canonical response envelope**: a single JSON schema used by all tools, with a Markdown “view” when needed.
- **Error codes**: `invalid_params`, `failed_precondition`, `internal`, `not_found`, `rate_limited`, `unauthorized`.
- **Tool signatures**: prefer `async def tool(params: <PydanticModel>) -> str` returning JSON text (Markdown only when explicitly requested).

---

## Feature groups

Each feature group has its own design document with detailed designs and example code.

- **FG01**: Core architecture refactor (split monolith into modules)
  - Doc: `improvement_plan/feature_groups/FG01_core_architecture.md`
- **FG02**: Response contracts + error model (JSON-first everywhere)
  - Doc: `improvement_plan/feature_groups/FG02_response_contracts.md`
- **FG03**: Skills + resources (discovery, caching, deterministic behavior)
  - Doc: `improvement_plan/feature_groups/FG03_skills_and_resources.md`
- **FG04**: Skill execution + providers (SDK alignment, Anthropic fallback, track_response)
  - Doc: `improvement_plan/feature_groups/FG04_skill_execution_and_providers.md`
- **FG05**: Task runner hardening (security, allowlists, ALLOW_AUTO_DEPS, diffs)
  - Doc: `improvement_plan/feature_groups/FG05_task_runner_hardening.md`
- **FG06**: Observability + DevEx (logging, diagnostics, CI, packaging)
  - Doc: `improvement_plan/feature_groups/FG06_observability_and_devex.md`

---

## Central task queue (worktree-parallel)

### Group: FG01 — Core architecture

- [ ] **IMP-001**: Convert `startd8_mcp.py` into a module-shim + move implementation into `startd8_mcp_server/` (no behavior change)
  - **Depends on**: none
  - **Owner/worktree**: FG01
- [ ] **IMP-002**: Add a thin module entrypoint `python -m startd8_mcp_server` and keep `startd8_mcp.py` as compatibility shim
  - **Depends on**: IMP-001
  - **Owner/worktree**: FG01
- [ ] **IMP-003**: Centralize environment/config parsing into `startd8_mcp_server/config.py`
  - **Depends on**: IMP-001
  - **Owner/worktree**: FG01

### Group: FG02 — Response contracts

- [ ] **IMP-010**: Define canonical response envelope + typed builder helpers
  - **Depends on**: IMP-001
  - **Owner/worktree**: FG02
- [ ] **IMP-011**: Standardize tool outputs to use the canonical response envelope (including errors)
  - **Depends on**: IMP-010
  - **Owner/worktree**: FG02
- [ ] **IMP-012**: Add/adjust tests that assert the response contract for representative tools (`startd8_use_skill`, `tasks.run`, one read-only tool)
  - **Depends on**: IMP-011
  - **Owner/worktree**: FG02

### Group: FG03 — Skills/resources

- [ ] **IMP-020**: Add skill discovery caching (TTL + invalidation by directory mtime)
  - **Depends on**: IMP-001
  - **Owner/worktree**: FG03
- [ ] **IMP-021**: Improve “skill not found” UX: best-match suggestion list + deterministic ordering
  - **Depends on**: IMP-020
  - **Owner/worktree**: FG03
- [ ] **IMP-022**: Add tests for cache behavior and deterministic skill ordering
  - **Depends on**: IMP-020
  - **Owner/worktree**: FG03

### Group: FG04 — Skill execution/providers

- [ ] **IMP-030**: Introduce provider abstraction (Anthropic + optional Startd8 SDK provider)
  - **Depends on**: IMP-001, IMP-010
  - **Owner/worktree**: FG04
- [ ] **IMP-031**: Fix/contain logging monkeypatching: remove global patches, keep targeted sanitization
  - **Depends on**: IMP-030
  - **Owner/worktree**: FG04
- [ ] **IMP-032**: Implement `track_response` when SDK is present; no-op with explicit metadata when absent
  - **Depends on**: IMP-030
  - **Owner/worktree**: FG04
- [ ] **IMP-033**: Add “startup self-check” tool (or startup banner) that reports resolved SDK agent class and effective command/env
  - **Depends on**: IMP-030
  - **Owner/worktree**: FG04
- [ ] **IMP-034**: Implement `startd8_compare_agents` (remove placeholder) using the provider abstraction
  - **Depends on**: IMP-030, IMP-010
  - **Owner/worktree**: FG04

### Group: FG05 — Task runner hardening

- [ ] **IMP-040**: Enforce `ALLOW_AUTO_DEPS` (currently defined but not enforced)
  - **Depends on**: IMP-001, IMP-010
  - **Owner/worktree**: FG05
- [ ] **IMP-041**: Tighten file-write policy: safe defaults for extensions + explicit override knobs
  - **Depends on**: IMP-040
  - **Owner/worktree**: FG05
- [ ] **IMP-042**: Add `tasks.validate` (parse + dependency checks + cycle detection) without running agents
  - **Depends on**: IMP-040
  - **Owner/worktree**: FG05
- [ ] **IMP-043**: Expand tests for task security (path traversal, blocked extensions, root escape)
  - **Depends on**: IMP-041
  - **Owner/worktree**: FG05

### Group: FG06 — Observability/DevEx

- [ ] **IMP-050**: Add request correlation IDs and structured debug logging toggled by env
  - **Depends on**: IMP-001
  - **Owner/worktree**: FG06
- [ ] **IMP-051**: Add CI (pytest) and baseline linting (ruff) for GitHub
  - **Depends on**: git repo exists
  - **Owner/worktree**: FG06
- [ ] **IMP-052**: Update docs to remove absolute-path assumptions; provide `run_mcp.sh` as canonical launcher for Cursor config
  - **Depends on**: IMP-002, IMP-030
  - **Owner/worktree**: FG06

---

## Definition of done (global)

- All changed tools return responses matching FG02’s response contract.
- `pytest` passes.
- Cursor config can start the server reliably (no PYTHONPATH drift).
- No secrets committed; `.env` remains local-only.
