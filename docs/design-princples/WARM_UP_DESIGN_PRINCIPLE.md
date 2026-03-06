# Warm Up Design Principle

Purpose: establish a cross-cutting design principle for the startd8-sdk development workflow — ensuring smooth transitions between LLM toolchains when the primary tool becomes unavailable, and disciplined re-entry when it returns.

This document is intentionally living guidance. Update it as new line-change scenarios are encountered.

---

## The Principle

**Warm Up** — in hockey, a line change is one of the most dangerous moments in a game. The first shift (your primary line) heads to the bench, the second shift jumps over the boards, and if the timing is off, you're caught with too many men on the ice or, worse, nobody covering the defensive zone.

Applied to LLM-assisted development: **when your primary LLM toolchain becomes unavailable and you switch to alternatives, both the transition out and the transition back carry risk. The second shift (backup tools) lacks the first shift's context about the codebase. The first shift (primary tools) returns to a changed landscape. Both transitions require deliberate warm-up protocols to avoid compounding errors.**

---

## Relationship to Mottainai and Kaizen

Warm Up completes the anti-waste trilogy alongside [Mottainai](./MOTTAINAI_DESIGN_PRINCIPLE.md) and [Kaizen](./KAIZEN_DESIGN_PRINCIPLE.md):

| Dimension | Mottainai | Kaizen | Warm Up |
|-----------|-----------|--------|---------|
| **Scope** | Single pipeline run | Across runs over time | Across toolchain transitions |
| **Focus** | Don't discard artifacts | Don't discard lessons | Don't discard context |
| **Waste eliminated** | Redundant LLM regeneration | Repeated failures | Transition-induced regressions |
| **Mechanism** | Artifact forwarding | Observation → Analysis → Action | Pre-flight → Validate → Reconcile |
| **Question** | "Has this already been computed?" | "Have we seen this problem before?" | "What changed while I was away, and what did the backup miss?" |

Together: Mottainai prevents waste within a run, Kaizen prevents waste across runs, and Warm Up prevents waste across toolchain transitions.

---

## Why This Matters

When the primary LLM tool (e.g., Anthropic Claude via Claude Code) goes down, the natural response is to keep working with whatever is available — Codex, Antigravity (Google models, Sonnet, Opus, GPT-OSS medium), or other alternatives. This is correct behavior. **The anti-pattern is not switching tools — it is switching without transition discipline.**

The risks manifest in two directions:

### First → Second Shift (Primary goes down, backup steps in)

1. **Context deficit** — The backup tool has no session memory of prior architectural decisions, codebase conventions, or in-progress work. It starts cold.
2. **Codebase ignorance** — The backup may not understand what already exists, leading to:
   - Reimplementing functionality that already exists elsewhere in the codebase
   - Creating artifacts that violate established patterns (naming, structure, error handling)
   - Building scaffolds or skeletons where production code already lives
3. **Approval pressure** — Impatience to keep making progress leads to approving requirements, plans, or generated code without the scrutiny the primary tool's deeper context would have caught.
4. **Artifact litter** — Diagnostic files, scratch artifacts, and work-in-progress outputs accumulate in the repo root without cleanup.

### Second → First Shift (Primary returns, resumes work)

1. **Stale assumptions** — The primary tool's memory/context reflects the pre-outage state. It doesn't know what the backup built, broke, or changed.
2. **Uninspected commits** — Work committed during the outage may contain subtle issues: duplicated logic, wrong abstractions, broken tests, pattern violations.
3. **Uncommitted drift** — The working tree may contain a mix of good work and artifacts that need triage before the primary tool can resume cleanly.
4. **Compounding errors** — If the first transition introduced issues (e.g., the backup built something that already existed), the primary tool may build on top of those errors, making them harder to unwind later.

---

## The Warm Up Protocol

### Phase 1: Pre-Flight (Before switching to backup)

When the primary tool becomes unavailable, before starting work with the backup:

- [ ] **Commit or stash** all in-progress work on the primary tool — leave no uncommitted drift
- [ ] **Write a transition note** (even a one-liner in a scratch file) capturing:
  - What was in progress
  - What decisions were pending
  - What the next planned steps were
- [ ] **Tag the transition point** — `git tag warm-up/out-$(date +%Y%m%d)` so you can diff against it later

### Phase 2: Second Shift Discipline (Working with backup tools)

While working with backup tools, maintain extra rigor:

- [ ] **Scope narrowly** — Favor small, well-defined tasks over ambitious multi-file changes
- [ ] **Verify before building** — Before implementing anything, ask: "Does this already exist in the codebase?" Backup tools won't volunteer this information
- [ ] **Commit frequently** — Small, atomic commits make it easier to cherry-pick or revert during reconciliation
- [ ] **Flag uncertainty** — If the backup tool makes a design decision you're unsure about, add a `# WARM-UP: review this` comment rather than silently accepting
- [ ] **Avoid repo-root litter** — Keep diagnostic files, patches, and scratch artifacts out of the working tree, or in a dedicated `tmp/` directory
- [ ] **Run tests after each commit** — Backup tools are more likely to introduce regressions they can't detect

### Phase 3: Warm Up (Primary tool returns)

When the primary tool becomes available again, **do not resume where you left off**. Instead:

#### 3a. Reconnaissance

- [ ] **Diff against transition tag** — `git diff warm-up/out-YYYYMMDD..HEAD` to see everything the backup produced
- [ ] **Review commit log** — Read every commit message from the outage period with fresh eyes
- [ ] **Inventory working tree** — `git status` to identify uncommitted changes and untracked artifacts
- [ ] **Run full test suite** — Establish a green/red baseline before making any changes

#### 3b. Triage

Classify every change from the outage period:

| Category | Action | Example |
|----------|--------|---------|
| **Clean** | Keep as-is | Well-scoped feature with passing tests |
| **Needs polish** | Keep but refine | Correct intent, but violates patterns or conventions |
| **Redundant** | Remove | Reimplements existing functionality |
| **Litter** | Delete | Scratch files, diagnostic dumps, skeleton artifacts |
| **Suspect** | Investigate | Approved requirements or plans that may have been under-scrutinized |

#### 3c. Reconciliation

- [ ] **Delete litter** — Remove scratch artifacts, orphan files, diagnostic dumps
- [ ] **Validate requirements** — Re-read any requirements docs approved during the outage; flag anything that duplicates existing capabilities or contradicts established patterns
- [ ] **Validate plans** — Re-read implementation plans; check that referenced files, functions, and modules actually exist at the paths specified
- [ ] **Fix pattern violations** — Bring outage-period code into alignment with codebase conventions
- [ ] **Remove redundancies** — If the backup reimplemented something that exists, choose the canonical version and delete the duplicate
- [ ] **Run tests again** — Confirm reconciliation didn't introduce new failures

#### 3d. Resume

- [ ] **Update context** — Refresh the primary tool's context with the current state (`/context_setter` or equivalent)
- [ ] **Tag the warm-up completion** — `git tag warm-up/in-$(date +%Y%m%d)`
- [ ] **Resume normal workflow** — The first shift is back, fully warmed up

---

## Current Violations (Baseline)

The following are known Warm Up violations from the 2026-03-04 through 2026-03-06 outage period, when work was performed with Codex and Antigravity (Google models, Sonnet, Opus, GPT-OSS medium) while Anthropic was unavailable.

### Violation 1: Skeleton artifact in repo — `src/mypackage/`

A generic `MyClass` skeleton with `NotImplementedError` stubs was created under `src/mypackage/utils.py`. This path has no relationship to the startd8 SDK namespace. Likely a Codex test artifact or default scaffold.

**Category**: Litter
**Action**: Delete

### Violation 2: Diagnostic files in repo root

Multiple work artifacts left in the repo root during the outage:
- `LARGEST_PY_FILES.md` — refactor target list (useful but misplaced)
- `pytest_failures.txt` — test output dump
- `full_recent_diff.patch` / `recent_commits.patch` — diff artifacts

**Category**: Litter
**Action**: Delete or relocate to `docs/reviews/` if content is worth preserving

### Violation 3: Uncommitted drift across 19 files (+918 lines)

A large batch of uncommitted changes spanning requirements docs, source files, and tests accumulated without being committed atomically. This makes it harder to attribute changes to specific decisions and harder to revert selectively.

**Category**: Needs triage
**Action**: Review each change group, commit in logical units

### Violation 4: Unverified requirements and plans

Requirements documents (`MICRO_PRIME_REQUIREMENTS.md`, `PRIME_CONTRACTOR_REQUIREMENTS.md`, `PRIME_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md`) and implementation plans (`MODERATE_DECOMPOSER_IMPLEMENTATION_PLAN.md`) were modified during the outage. These need re-review to ensure they don't:
- Duplicate capabilities that already exist
- Reference files or modules at incorrect paths
- Introduce design decisions that conflict with established patterns

**Category**: Suspect
**Action**: Re-review with primary tool's full codebase context

---

## Anti-Patterns

### The Impatient Handoff

**Pattern**: Primary tool goes down → immediately start approving large-scope changes with backup tools → don't review what was built → primary returns and inherits the mess.

**Fix**: Scope narrowly during backup. Review everything during warm-up.

### The Silent Resume

**Pattern**: Primary tool comes back → pick up where you left off without reviewing what happened during the outage → build on top of potentially flawed foundations.

**Fix**: Always run Phase 3 (Warm Up) before resuming. Never skip reconnaissance.

### The Clean Enough Fallacy

**Pattern**: "The tests pass, so the outage work must be fine." Tests validate behavior, not design quality. Backup tools may have introduced correct-but-wrong implementations (reimplementing existing utilities, violating naming conventions, creating unnecessary abstractions).

**Fix**: Triage includes pattern review, not just test status.

### The Permanent Second Shift

**Pattern**: Primary tool returns but you keep using the backup for some tasks because "it's already set up." This creates divergent context — two tools with partial knowledge of the codebase, neither fully informed.

**Fix**: Consolidate back to the primary tool. Use warm-up reconciliation as the single source of truth.

---

## Metrics

Track these across toolchain transitions to measure warm-up effectiveness:

| Metric | Target | Description |
|--------|--------|-------------|
| **Litter count** | 0 | Untracked artifacts left in working tree after backup shift |
| **Redundancy count** | 0 | Features reimplemented that already existed |
| **Uncommitted line delta** | < 200 | Lines changed but not committed at transition point |
| **Test regression count** | 0 | Tests broken during backup shift that weren't caught |
| **Warm-up duration** | < 1 hour | Time from primary-returns to clean-resume |
| **Requirement re-review rate** | 100% | Percentage of outage-approved requirements re-reviewed |

---

## Checklist Summary

```
PRE-FLIGHT (before switching to backup)
[ ] Commit/stash all work
[ ] Write transition note
[ ] Tag transition point

SECOND SHIFT (working with backup)
[ ] Scope narrowly
[ ] Verify before building
[ ] Commit frequently
[ ] Flag uncertainty with WARM-UP comments
[ ] No repo-root litter
[ ] Run tests after each commit

WARM UP (primary returns)
[ ] Diff against transition tag
[ ] Review commit log
[ ] Inventory working tree
[ ] Run full test suite
[ ] Triage all changes (clean/polish/redundant/litter/suspect)
[ ] Delete litter
[ ] Validate requirements and plans
[ ] Fix pattern violations
[ ] Remove redundancies
[ ] Run tests again
[ ] Update primary tool context
[ ] Tag warm-up completion
[ ] Resume normal workflow
```
