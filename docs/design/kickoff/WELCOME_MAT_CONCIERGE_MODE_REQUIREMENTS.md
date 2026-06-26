# Welcome Mat — Concierge Mode Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-26
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `WELCOME_MAT_CONCIERGE_MODE_PLAN.md` (v1.0)
**Related:** `INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (v0.5, "Welcome Mat"),
`CONCIERGE_MCP_REQUIREMENTS.md` (v0.4), `CONCIERGE_FRICTION_LOG_NAVIG8.md`

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass read the real `concierge/`
> and `kickoff_experience/` code and found the feature is **thinner than feared in one place and
> blocked in another**: the load-bearing write-plumbing worry was already solved, but FR-CM-6 is
> *unreachable* as written, and four concrete defects/specs were missing.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **OQ-1:** the web may need a new generic `WritePlan` apply engine ("how much new plumbing?") | `concierge/writes.py:203 to_planned_writes` already converts a plan → `PlannedWrite`s; the CLI apply is a 3-liner (`cli_concierge.py:201-202,250-251`) the web/TUI reuse verbatim. M6's `apply_capture` is `CapturePlan`-specific (splice/stale-guard) but the generic plan is *simpler*. | **Narrowed FR-CM-7 / OQ-1 resolved.** ~40-line typed wrapper, not new write plumbing. |
| **FR-CM-6:** offer to instantiate a kickoff package for a project that *lacks* one, from inside the served app | `preflight` marks `inputs_dir` **blocking** (`serve.py:97,64,76`); `serve_kickoff`/`start_cmd` **refuse to serve** a project missing `docs/kickoff/inputs/` (`serve.py:214`, `cli_kickoff.py:212`). The instantiate offer is **unreachable for exactly the projects it targets**. | **Added NR-CM-A.** Demote `inputs_dir` to advisory (serve package-less). FR-CM-6 infeasible until then. |
| **FR-CM-6 / OQ-6:** instantiate is no-clobber with `--force` as a separate confirm to overwrite | `build_instantiate_plan` emits `ACTION_NEW` for every file (`writes.py:101`); `apply_write_plan` **skips `ACTION_NEW` when the file exists regardless of `force`** (`safe_write.py:231`). `--force` is **inert** for instantiate (the CLI's force help is misleading). | **Added NR-CM-C; force clause dropped.** Ship honest no-clobber (no force UI) in v1. |
| **FR-CM-1/2 (TUI half):** add a "menu item / command" to the existing TUI Welcome Mat | `KickoffChat`/`new_kickoff_chat` (`chat.py:161`) and `ConciergeChat` have **no interactive REPL/menu caller** anywhere — the running "TUI Welcome Mat" does not exist yet. | **Reframed: build a TUI concierge host command** (`kickoff concierge` Typer cmd + `questionary.confirm`), not extend one. |
| **FR-CM-5:** friction "appends via `apply_write_plan`" | `build_friction_entry` leaves `ts=None`; only the CLI stamps the timestamp (`writes.py:147`, `cli_concierge.py:233`). | **Added NR-CM-B.** The web/TUI applier must stamp the time, else UI entries are unstamped. |
| **OQ-3:** symlinked-root refusal must be typed, not a 500 | `resolve_confined_root` raises `SafeWriteError` on a symlinked/`..` root unless `STARTD8_CONCIERGE_ALLOWED_ROOTS` set (`safe_write.py:89`). The dev worktree `/tmp/kickoff-impl`→`/private/tmp` is symlinked, so every write blocks here. `apply_capture` already models the typed wrap (`capture.py:387`). | **OQ-3 resolved.** `apply_concierge_plan` catches → typed `WRITE_BLOCKED` + the `ALLOWED_ROOTS` hint. Added NR-CM-D (typed reason codes). |
| **FR-CM-9:** a read-only `concierge survey` *may* be exposed over MCP | Already exposed: `startd8_concierge` MCP tool is `readOnlyHint=True`; write actions return a preview `WritePlan` (no `apply_write_plan` in the MCP path) (`startd8_mcp.py:3041`). | **FR-CM-9 resolved — no work.** |
| **FR-CM-4:** assess "not a second divergent readiness computation" | One source already: `readiness.build_readiness` wraps `concierge.build_assess` (`readiness.py:148`); web + inspect both consume it. | **Resolved — reuse `ReadinessView`;** the only risk is the new view-model re-deriving it (it must not). |

**Resolved open questions:**
- **OQ-1 → reuse `to_planned_writes` + `apply_write_plan`** (thin wrapper). No new web write engine.
- **OQ-2 → instantiate into the pinned served root only** (scaffold-if-absent); never a surface-supplied path (breaks the security pin).
- **OQ-3 → typed `WRITE_BLOCKED`** via the applier catching `SafeWriteError`; surface the `ALLOWED_ROOTS` escape.
- **OQ-4 → `questionary.confirm().ask()`** on a **new** TUI/CLI host command (none exists to extend).
- **OQ-7 → optional drift panel** via `compute_drift`, web human-privilege only, never MCP.
- **OQ-5 → STILL OPEN** (defer): append-only friction for v1; a bounded read-back belongs in `kickoff_experience`, never `concierge/`, never MCP.
- **OQ-6 → STILL OPEN** (resolved to honest no-clobber for v1; revisit if overwrite is wanted).

---

## 1. Problem Statement

The **Welcome Mat** (interactive kickoff experience) exposes the Concierge only in disconnected
read-only slices, with one mandated piece unbuilt and a surface asymmetry:

| Concierge action | Today in the Welcome Mat | Gap |
|------------------|--------------------------|-----|
| **`assess`** (readiness) | Surfaced as the web readiness meter (FR-7) and a TUI tool | OK, but not presented *as* "the Concierge" — it reads as anonymous readiness |
| **`survey`** (brownfield triage) | Reachable only as a tool in the **TUI** conversational driver (`build_kickoff_registry`) | **Not in the web app at all** — no panel renders `build_survey` (requirement-doc/extraction-format flags, model files, fixtures, PII risk) |
| **`log-friction`** | Specified (FR-12) but **not built** — only a `friction_logged` telemetry event name exists | No friction surface in either web or TUI; the F-1..F-10 friction class can't be captured in-flow |
| **`instantiate-kickoff`** | CLI-only precursor (OQ-7: "CLI is sole writer") | Can't scaffold a kickoff package for a project that lacks one from inside the Welcome Mat |
| **`derive-contract`** | Out of scope (NR-5) | (intentionally out) |

There is **no deliberate, user-visible "Concierge mode."** A user who lands on a brownfield project
can't see the triage, can't instantiate a kickoff package if one is missing, and can't log friction
when the grammar rejects their content — the exact onboarding moments the Concierge exists to serve.

Meanwhile the **safety boundaries are already settled and must be preserved:**
- The Concierge MCP tool is **preview-only** (never writes); MCP write actions return a `WritePlan`.
- The **CLI is a writer at human privilege**, applying plans via the safe-writer (`apply_write_plan`,
  confinement: rejects symlinked/`..` roots, atomic, no-clobber).
- The Welcome Mat already established a **local-web writer at human privilege** (M6 capture: CSRF +
  rate-limit + same-origin → `apply_write_plan`). Concierge writes can ride that same seam.
- The **agentic loop is read-only** (`handle_concierge_read` floor): `survey`/`assess` are the only
  agentic-callable actions; `instantiate`/`log-friction` are propose-only.

**What should exist:** a named **Concierge mode** in the Welcome Mat — present in **both** web and TUI
— that (a) renders `survey` triage, (b) consolidates `assess` readiness, (c) lets a human **log
friction in-flow**, and (d) offers to **instantiate a kickoff package** for a project missing one —
all by reusing the existing Concierge builders + the safe-writer, with writes only at human privilege
(web same-origin / CLI / explicit TUI confirm), never over MCP and never autonomously by the loop.

---

## 2. Guiding Principles (inherited)

- **P1 — Reuse, don't re-implement.** Concierge mode is a *surface* over `handle_concierge_tool` /
  `build_survey` / `build_instantiate_plan` / `build_friction_entry` + `apply_write_plan`. No new
  triage/scaffold/friction logic.
- **P2 — Assist, not operate.** Concierge mode never runs the cascade or records a gate (FR-C2). It
  surveys, advises, scaffolds, and logs friction.
- **P3 — Writes only at human privilege; never MCP, never the loop.** Every Concierge write is
  preview-then-apply through the safe-writer, authorized by a foreground human (web same-origin POST
  with session/CSRF, the CLI, or an explicit TUI confirm). The agentic loop may *propose* but never
  applies (the read-only floor is unchanged).
- **P4 — Full fidelity in both surfaces.** Per OQ-6 (resolved in v0.5), survey/friction/instantiate
  appear in **both** web and TUI; parity is a property of one shared payload.

---

## 3. Requirements

### A. The mode itself

- **FR-CM-1 — A named Concierge surface.** Add a user-visible **Concierge** section to the Welcome
  Mat in both web and TUI, presenting onboarding-assist actions behind one entry with a posture
  banner ("assist, not operate — I survey, advise, scaffold, and log friction; I never run the
  build or record gates"). *(v0.2: the TUI surface is a **new host command** — see FR-CM-2 — since
  no interactive TUI Welcome Mat exists to extend.)*
- **FR-CM-2 — Discoverable entry.** Web: a nav link to `/concierge` from the overview. TUI: a **new
  `kickoff concierge` host command** (`questionary`-driven) — *not* a menu item on an existing TUI,
  because `KickoffChat`/`ConciergeChat` have no interactive REPL/menu caller today (`chat.py:161`).
  The mode does not replace the kickoff state/overview.

### B. Read actions (no new write surface)

- **FR-CM-3 — Survey panel (closes the web gap).** Render `build_survey` output in **both** surfaces:
  requirement/PRD docs with their `extraction_format` flag (the F-4 "needs reformat" signal), Pydantic
  model files, fixture candidates, and PII risk flags — with the existing notes. Read-only, `$0`.
- **FR-CM-4 — Assess consolidation.** The existing readiness surface (FR-7) is reachable *from* the
  Concierge mode (the same `build_assess`/`ReadinessView` data), presented as a Concierge action — not
  a second, divergent readiness computation.

### C. Write actions (human-privilege, preview-then-apply)

- **FR-CM-5 — Log friction in-flow (closes FR-12).** A friction form captures the three required
  fields (`friction`, `what_happened`, `implication`), builds a `WritePlan` via `build_friction_entry`,
  shows a preview, and on explicit human confirmation appends to `concierge-friction.jsonl` via
  `apply_write_plan`. **The applier must stamp the timestamp** (NR-CM-B) — the builder leaves
  `ts=None`. Web: same-origin + CSRF (the M6 authorization model). TUI: explicit confirm. The
  conversational loop may *offer/prefill* but never applies.
- **FR-CM-6 — Instantiate a kickoff package** *(v0.2: requires NR-CM-A; force clause dropped)*. When
  the served project lacks a kickoff package (no `docs/kickoff/inputs/`), offer to scaffold one:
  preview the `build_instantiate_plan` `WritePlan` (posture `prototype|production`, optional authoring
  trio), and on explicit human confirmation apply it via the safe-writer at the **pinned served root
  only** (OQ-2), **no-clobber** (honest: `ACTION_NEW` is skipped when a file exists *regardless of
  force*, `safe_write.py:231`, so v1 ships **no force UI** — see NR-CM-C). Never runs the cascade.
  **Depends on NR-CM-A** (the Welcome Mat must be serveable for a package-less project, which it is
  not today).
- **FR-CM-7 — One write path** *(v0.2: thin reuse, OQ-1 resolved)*. Concierge writes reuse the
  existing seam — `to_planned_writes` (`writes.py:203`) → `apply_write_plan` (`safe_write.py:200`),
  the **same** 3-line pattern the CLI uses (`cli_concierge.py:201`) — behind one typed applier
  `apply_concierge_plan` (NR-CM-D). No new write engine. M6's `apply_capture` is *not* reused (its
  splice/stale-guard is `CapturePlan`-specific; the generic concierge plan needs no stale guard —
  instantiate is `ACTION_NEW`, friction is `ACTION_APPEND`).

### D. Boundaries & cross-cutting

- **FR-CM-8 — Agentic boundary unchanged.** `survey`/`assess` remain the only agentic-callable
  Concierge actions (the read-only floor is not widened). `instantiate-kickoff`/`log-friction` are
  **propose-only** in the conversational driver — the loop drafts; the human applies via FR-CM-5/6.
- **FR-CM-9 — MCP stays read-only.** A read-only `concierge survey` may be exposed over MCP (like
  `kickoff_state_tool`), but no Concierge **write** is ever reachable over MCP (preview-only, FR-C3).
- **FR-CM-10 — Web/TUI parity.** Survey, friction, and instantiate are available and equivalent in
  both surfaces, consuming shared payloads so parity is testable against one representation.
- **FR-CM-11 — Observability.** Concierge actions emit funnel events consistent with M8
  (`survey_viewed`, `friction_logged`, `kickoff_instantiated`, `concierge_write_refused` with the
  typed reason code).

### E. Requirements surfaced by planning (new in v0.2)

- **NR-CM-A — Serve a package-less project.** The Welcome Mat must be **serveable for a project
  lacking `docs/kickoff/inputs/`**, otherwise FR-CM-6's instantiate offer is unreachable (preflight
  marks `inputs_dir` blocking and `serve_kickoff`/`start_cmd` refuse, `serve.py:214`,
  `cli_kickoff.py:212`). Demote `inputs_dir` to advisory, or add a concierge-bootstrap serve mode.
  **This blocks FR-CM-6.**
- **NR-CM-B — Stamp the friction timestamp.** `build_friction_entry` leaves `ts=None` (`writes.py:147`,
  caller-stamped). The web/TUI applier (`apply_concierge_plan`) must stamp
  `datetime.now(timezone.utc).isoformat()`, mirroring the CLI (`cli_concierge.py:233`), else
  UI-logged entries are unstamped.
- **NR-CM-C — Honest force semantics for instantiate.** `--force` is **inert** for instantiate today
  (`ACTION_NEW` is skipped on an existing file regardless of force, `safe_write.py:231`). v1 ships
  **no force UI** (honest no-clobber). A real overwrite path (builder emits `ACTION_OVERWRITE` under
  an explicit confirm) is a separate, later decision.
- **NR-CM-D — Typed concierge-write reason codes.** Define a `ConciergeWriteCode` vocabulary (parallel
  to `CaptureCode`) — `ok` / `write_blocked` (confinement/symlink, with the
  `STARTD8_CONCIERGE_ALLOWED_ROOTS` hint) / `write_refused` — so `concierge_write_refused`
  (FR-CM-11) carries a stable code across web, TUI, and telemetry.

---

## 4. Non-Requirements

- **NR-1 — `derive-contract` not exposed.** PRD→Prisma derivation stays its own track (NR-5 inherited).
- **NR-2 — No MCP writes.** Concierge mode never writes over MCP; the MCP surface is preview/read-only.
- **NR-3 — No re-implementation.** Concierge mode does not re-derive triage/scaffold/friction logic;
  it reuses the `concierge/` builders + `apply_write_plan`.
- **NR-4 — Not an operator.** Concierge mode never runs the cascade, records a gate, or applies
  deployment — assist only (P2).
- **NR-5 — No autonomous writes.** The agentic loop never applies a Concierge write (propose-only).

---

## 5. Open Questions

*5 of 7 resolved by the planning pass — see §0 for rationale + citations. Retained for the record.*

- **OQ-1 — RESOLVED → reuse `to_planned_writes` + `apply_write_plan`** (thin ~40-line typed wrapper);
  no new web write engine. M6's `apply_capture` is not reused (its splice/stale-guard is
  `CapturePlan`-specific).
- **OQ-2 — RESOLVED → instantiate into the pinned served root only** (scaffold-if-absent). An
  arbitrary target param breaks the security pin (`web.py:231`, `concierge/chat.py:18`).
- **OQ-3 — RESOLVED → typed `WRITE_BLOCKED`** via `apply_concierge_plan` catching `SafeWriteError`,
  surfacing the `STARTD8_CONCIERGE_ALLOWED_ROOTS` hint (mirrors `capture.py:387`). Materially affects
  the `/tmp`→`/private/tmp` dev env.
- **OQ-4 — RESOLVED → `questionary.confirm().ask()`** (hard dep) on a **new** `kickoff concierge` host
  command — there is no interactive TUI to extend (`chat.py:161`).
- **OQ-5 — STILL OPEN (defer).** Append-only friction for v1; a bounded `concierge-friction.jsonl`
  read-back belongs in the `kickoff_experience` layer (human privilege), never `concierge/`, never MCP.
- **OQ-6 — STILL OPEN (resolved to honest no-clobber for v1).** Posture (`prototype|production`) is a
  clean enum; **force is inert** for instantiate (NR-CM-C) so v1 ships no force UI. Revisit if
  overwrite is wanted.
- **OQ-7 — RESOLVED (optional).** `compute_drift` reads files; an instantiate drift panel at web
  human-privilege does not cross the FR-C3a/MCP bound **as long as it is never wired to MCP**.

---

*v0.2 — Post-planning self-reflective update. 1 requirement narrowed (FR-CM-7/OQ-1), 1 reframed
(FR-CM-1/2 TUI half), 1 gated on a new blocker (FR-CM-6 ← NR-CM-A), 4 added (NR-CM-A..D), 5 of 7 open
questions resolved. Headline: Concierge mode is a thin surface over `to_planned_writes` +
`apply_write_plan`, but FR-CM-6 was unreachable as written (serve-blocking conflict) and `--force` is
inert. Ready for optional CRP review before implementation.*
