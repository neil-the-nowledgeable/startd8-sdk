# Welcome Mat — Concierge Mode Requirements

**Version:** 0.4 (Post-CRP R2–R5)
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
  - **Acceptance (R2–R5):** *(R3-F2 — post-apply reconciliation)* after instantiate apply, a
    refreshed Concierge payload no longer offers package creation for the same root and shows the next
    recommended action; after friction apply, the confirmation carries bounded metadata only (no raw
    paths, no submitted free text).
- **FR-CM-2 — Discoverable entry.** Web: a nav link to `/concierge` from the overview. TUI: a **new
  `kickoff concierge` host command** (`questionary`-driven) — *not* a menu item on an existing TUI,
  because `KickoffChat`/`ConciergeChat` have no interactive REPL/menu caller today (`chat.py:161`).
  The mode does not replace the kickoff state/overview.
  - **Acceptance (R2–R5):** *(R3-F5 — non-interactive TUI fail-closed)* when
    `questionary.confirm().ask()` returns `None`, raises, or detects no interactive terminal, the
    operation is refused with a typed `confirm_unavailable` result and **no disk write**; no
    unattended `--yes` shortcut ships in v1.

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
  - **Acceptance (R2–R5):**
    - *(R2-F1 — preview-before-apply, shared with FR-CM-6)* the preview response includes action,
      warnings, write count, and per-write path/status/bytes, and **no** content beyond what is already
      in the plan; the project tree is byte-identical before/after preview (proves no write occurred).
    - *(R2-F5 — typed pre-apply validation, also NR-CM-D)* blank required fields, invalid posture, or
      oversized free text return a typed non-500 code (`missing_required_field` / `invalid_posture` /
      `input_too_large`) with conservative length caps applied **before** jsonl serialization; the
      project tree is unchanged and no jsonl line is appended.
    - *(R3-F1 — replay/idempotency, also FR-CM-6/NR-CM-D)* applying the same confirmed intent twice
      changes disk only once and emits only one success event; the repeat returns a typed replay/no-op
      outcome (one-time apply intent / idempotency key).
    - *(R3-F4 — durable friction schema, also NR-CM-B)* web/TUI-created jsonl entries include
      `schema_version`, `source` (`web`|`tui`), `ts`, and the three user-authored fields, and contain
      no raw project paths.
    - *(R4-F4 — mode/surface availability matrix, also FR-CM-6/FR-CM-10)* a defined matrix governs
      READ/WRITE/DEMO × web/TUI: previews are available where safe, applies **fail closed** outside
      explicit write-capable human-privilege modes, and a refused apply leaves disk unchanged.
    - *(R5-F2 — UI-redress protection, also FR-CM-6)* web responses for `/concierge`, preview, and
      apply confirmation carry a frame-deny policy (`Content-Security-Policy: frame-ancestors 'none'`
      or `X-Frame-Options: DENY`); the confirmation UI cannot be embedded by another origin.
- **FR-CM-6 — Instantiate a kickoff package** *(v0.2: requires NR-CM-A; force clause dropped)*. When
  the served project lacks a kickoff package (no `docs/kickoff/inputs/`), offer to scaffold one:
  preview the `build_instantiate_plan` `WritePlan` (posture `prototype|production`, optional authoring
  trio), and on explicit human confirmation apply it via the safe-writer at the **pinned served root
  only** (OQ-2), **no-clobber** (honest: `ACTION_NEW` is skipped when a file exists *regardless of
  force*, `safe_write.py:231`, so v1 ships **no force UI** — see NR-CM-C). Never runs the cascade.
  **Depends on NR-CM-A** (the Welcome Mat must be serveable for a package-less project, which it is
  not today).
  - **Acceptance (R1) — failure & recovery.** Multi-file instantiate is **non-atomic**:
    `apply_write_plan` continues past a per-file error (`safe_write.py:209-258`), so a mid-scaffold
    failure leaves a **partial** package. Because every file is `ACTION_NEW`, a re-run is
    **idempotent** (already-written files skip), so the documented recovery is "re-run instantiate".
    A partial result must be surfaced (ties to the `partial` code, NR-CM-D). Acceptance: a forced
    mid-plan error leaves prior files intact, reports `partial`, and a re-run completes the remainder.
  - **Acceptance (R2–R5):** *(R5-F1 — restart-safe partial detection, also NR-CM-A)* the offer
    distinguishes `missing` / `partial` / `complete` / `blocked` package states; a root with
    `docs/kickoff/inputs/` present but other expected instantiate artifacts absent yields
    `package_state=partial`, shows a retry/recovery action, and retry completes the missing
    `ACTION_NEW` files without overwriting existing ones.
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
  - **Acceptance (R1):** the new aggregator `build_concierge_view` (which bundles the
    `instantiate_offer` + friction form-spec write-affordance metadata) is **not** the MCP-exposed
    surface; only the bare `build_survey` shape is. Acceptance: the MCP `concierge` survey returns the
    `build_survey` shape, not the `concierge_view` schema.
- **FR-CM-10 — Web/TUI parity.** Survey, friction, and instantiate are available and equivalent in
  both surfaces, consuming shared payloads so parity is testable against one representation.
  - **Acceptance (R1):** parity has two separable meanings. **(a) View parity** — both surfaces render
    the *same* `build_concierge_view` payload (one representation, testable against one oracle).
    **(b) Write-behavior equivalence** — the same `WritePlan` produces an *identical on-disk result*
    across surfaces. The two surfaces intentionally differ in their **authorization gates** (web:
    mode-gate + CSRF + rate-limit; TUI: explicit confirm); this gate asymmetry is documented and is
    *not* a parity violation.
  - **Acceptance (R2–R5):** *(R2-F2 — view-model contract)* the shared `build_concierge_view` payload
    defines a stable contract — `schema_version`, posture/banner text-or-key, `survey`, `readiness`,
    `instantiate_offer`, `friction_form`, and a `next_action`/CTA field; a contract test asserts the
    required keys + schema version, and both surfaces render the **same** `next_action` rather than
    each deciding independently.
- **FR-CM-11 — Observability.** Concierge actions emit funnel events consistent with M8
  (`survey_viewed`, `friction_logged`, `kickoff_instantiated`, `concierge_write_refused` with the
  typed reason code).
  - **Acceptance (R1):** a no-clobber **no-op** instantiate (0 files written, all targets already
    present) is neither an install nor a refusal, so it must emit a **distinct** asserted funnel
    event/code rather than `kickoff_instantiated` — tied to the `skipped` code (NR-CM-D / R1-F2),
    so the M8 funnel does not over-report installs.
  - **Acceptance (R2–R5):** *(R2-F4 — telemetry attribute/privacy contract)* each event carries a
    bounded attribute allowlist (`source`, `mode`, `action`, `code`, `posture`, `with_authoring`,
    `written_count`, `skipped_count`) across success / partial / no-op / refused paths, and **excludes**
    free-text friction fields (`friction`/`what_happened`/`implication`) and raw file paths.

### E. Requirements surfaced by planning (new in v0.2)

- **NR-CM-A — Serve a package-less project.** The Welcome Mat must be **serveable for a project
  lacking `docs/kickoff/inputs/`**, otherwise FR-CM-6's instantiate offer is unreachable (preflight
  marks `inputs_dir` blocking and `serve_kickoff`/`start_cmd` refuse, `serve.py:214`,
  `cli_kickoff.py:212`). Demoting `inputs_dir` alone is **insufficient**: in WRITE/DEMO mode preflight
  adds a *second* blocking check, `inputs_writable` (`serve.py:103-106`), which also fails when
  `inputs/` is absent and re-blocks a write-capable serve. Both checks must be neutralized (demote to
  advisory, or add a concierge-bootstrap serve mode). **This blocks FR-CM-6.**
  - **Acceptance (R1):** `preflight(project_without_inputs, mode=WRITE).ok is True` (no blocking check
    fails).
  - **Acceptance (R2–R5):**
    - *(R2-F3 — package-less first-run discoverability, also FR-CM-2)* a project without
      `docs/kickoff/inputs/` returns HTTP 200 for both the overview and `/concierge`; the overview
      surfaces a "Create kickoff package" Concierge CTA; the Concierge payload has
      `instantiate_offer.needed=True`. A successful-but-empty serve must not look broken.
    - *(R4-F5 — operator first-run/confinement guidance, also NR-CM-D)* package-less serve output names
      the `/concierge` route/CTA, and `write_blocked` output names the `STARTD8_CONCIERGE_ALLOWED_ROOTS`
      remediation — while telemetry omits raw path values.
- **NR-CM-B — Stamp the friction timestamp at the surface handler.** `build_friction_entry`
  serializes the **full** JSON line (including `ts`) into `append_text` at build time
  (`writes.py:155-162`), so `apply_concierge_plan` receives an opaque pre-serialized line and cannot
  "stamp" the timestamp there without an unauthorized re-parse/re-serialize. The **surface handler**
  (web/TUI) must therefore pass `timestamp=datetime.now(timezone.utc).isoformat()` **into**
  `build_friction_entry` *before* the line is serialized — exactly as the CLI does
  (`cli_concierge.py:233`) — else UI-logged entries are unstamped.
  - **Acceptance (R1):** a friction entry created via the web/TUI surface has a non-null ISO-8601 `ts`
    identical in shape to a CLI-created entry.
- **NR-CM-C — Honest force semantics for instantiate.** `--force` is **inert** for instantiate today
  (`ACTION_NEW` is skipped on an existing file regardless of force, `safe_write.py:231`). v1 ships
  **no force UI** (honest no-clobber). A real overwrite path (builder emits `ACTION_OVERWRITE` under
  an explicit confirm) is a separate, later decision.
- **NR-CM-D — Typed concierge-write reason codes.** Define a `ConciergeWriteCode` vocabulary (parallel
  to `CaptureCode`) — `ok` / `write_blocked` (confinement/symlink, with the
  `STARTD8_CONCIERGE_ALLOWED_ROOTS` hint) / `write_refused` / **`skipped` (and/or `partial`)** — so
  `concierge_write_refused` (FR-CM-11) carries a stable code across web, TUI, and telemetry. The
  fourth code covers the case where `WriteResult.skipped` is non-empty but `ok=True`: a no-clobber
  instantiate of an already-existing file lands in `skipped` while leaving `ok=True`
  (`safe_write.py:65-66,236`). The applier returns **written/skipped counts**, not a bare `ok`, so a
  no-op instantiate (0 written) is distinguishable from a real install.
  - **Acceptance (R1):** instantiate over a partially or fully pre-existing package returns a distinct
    code (`skipped`/`partial`) plus written/skipped counts, not bare `ok`.
  - **Acceptance (R2–R5):** *(R4-F3 — user-facing recovery semantics, also FR-CM-5/FR-CM-6)* each code
    declares whether it is **retryable**, a bounded **message key**, and the **next action** shown:
    `partial` returns written/skipped/failed/remaining counts plus a safe no-clobber retry path;
    `write_blocked` surfaces the `STARTD8_CONCIERGE_ALLOWED_ROOTS` hint **without** leaking the path
    into telemetry. A table-driven test enumerates every code across web and TUI.

### F. Validation & Release Gates (R2–R5)

- **FR-CM-12 — Package-less first-run journey acceptance test** *(R3-F3)*. A single automated fixture
  exercises the package-less web journey end-to-end: serve a root with **no** `docs/kickoff/inputs/`,
  expose the Concierge CTA/route, **preview** instantiate without writes, **apply** instantiate,
  refresh Concierge state, then **log friction** — asserting user-visible state **and** telemetry at
  the journey level, not only individual helpers. TUI covers the same instantiate/friction
  write-plan + apply against the shared payload.
- **FR-CM-13 — Release/CI gate for write-capable routes** *(R4-F1)*. Before any implementation
  satisfies the FR-CM-5/FR-CM-6 write paths, CI must prove: preview writes nothing, package-less WRITE
  preflight passes, MCP/agentic tools remain read-only, replay protection is active, and telemetry
  excludes free text + raw paths. A CI checklist/automated group **fails** if write endpoints are
  present without these guardrails. (Release-safety sequencing invariant, not another implementation
  detail.)

### G. Phased / Later-Phase Requirements (post-v1)

> Accepted but deferred — the two heaviest mechanisms are phased out of v1 to keep the first cut thin.
> R3-F1 replay-once protection stays the **v1 essential**; only its full lifecycle is deferred here.

- **[Phase 2 — Should-have] Shared test-data fixture matrix** *(R4-F2; related FR-CM-5/6/8/9/10/11,
  NR-CM-A/B/D)*. A single named fixture pack — package-less root, partially scaffolded root, fully
  existing package, symlink-confined root, invalid posture, blank/oversized friction fields — reused
  across web/TUI/MCP/telemetry/applier tests with golden `WritePlan` summaries, instead of per-test
  bespoke setup.
- **[Phase 2 — Should-have] Full preview/apply intent lifecycle** *(R5-F3; related FR-CM-5/6/11,
  NR-CM-D)*. Beyond v1 replay-once: bind each one-time intent to root/action/mode-source/posture + a
  **digest** of the previewed `WritePlan`; **expire** abandoned intents with the local session
  lifetime; consume atomically; **clean up** expired records without retaining free-text friction in
  session state. The digest doubles as a safe telemetry correlation key.

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

*v0.3 — Post-CRP R1. All 7 R1 F-suggestions accepted and merged into prose: NR-CM-B reworded
(surface-handler timestamp), NR-CM-D extended (`skipped`/`partial` code + counts), NR-CM-A extended
(`inputs_writable` neutralized), FR-CM-10 clarified (view vs write-behavior parity), FR-CM-6
failure/recovery clause added, FR-CM-11 no-op event defined, FR-CM-9 MCP aggregator boundary pinned.
Dispositions recorded in Appendix A; R1 round verbatim in Appendix C.*

*v0.4 — Post-CRP R2–R5 (reviewer gpt-5.5). Policy: accept all, phase the two heaviest mechanisms.
All 18 R2–R5 F-suggestions accepted, nothing rejected. **14 merged** as concise `Acceptance (R2–R5)`
criteria on the named FR/NR (preview-before-apply, view-model contract, telemetry attribute/privacy
contract, typed pre-apply validation, replay-once, durable friction schema, non-interactive TUI
fail-closed, mode×surface matrix, frame-deny, restart-safe partial detection, recovery semantics,
package-less first-run UX/operator guidance); **2 into a new §F Validation & Release Gates** subsection
(FR-CM-12 first-run journey test, FR-CM-13 write-route CI gate); **2 phased to §G** (R4-F2 shared
fixture matrix, R5-F3 full intent lifecycle). Dispositions in Appendix A; R2–R5 rounds verbatim in
Appendix C.*

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

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Reword NR-CM-B — surface handler passes the timestamp into `build_friction_entry` (not stamped by the applier) | R1 / claude-opus-4-8-1m | Merged into NR-CM-B | 2026-06-26 |
| R1-F2 | Add a fourth `skipped`/`partial` code; define `WriteResult.skipped` non-empty + `ok=True`; return written/skipped counts | R1 / claude-opus-4-8-1m | Merged into NR-CM-D | 2026-06-26 |
| R1-F3 | Extend NR-CM-A to also neutralize the `inputs_writable` blocking check | R1 / claude-opus-4-8-1m | Merged into NR-CM-A | 2026-06-26 |
| R1-F4 | Clarify FR-CM-10 parity = view parity + separate write-behavior equivalence; document gate asymmetry | R1 / claude-opus-4-8-1m | Merged into FR-CM-10 | 2026-06-26 |
| R1-F5 | Add FR-CM-6 failure/recovery clause — non-atomic multi-file instantiate, idempotent retry, partial surfaced | R1 / claude-opus-4-8-1m | Merged into FR-CM-6 | 2026-06-26 |
| R1-F6 | Define the funnel event/code for a no-clobber no-op instantiate (0 files written) | R1 / claude-opus-4-8-1m | Merged into FR-CM-11 | 2026-06-26 |
| R1-F7 | Pin that `build_concierge_view` is not MCP-exposed; only bare `build_survey` is | R1 / claude-opus-4-8-1m | Merged into FR-CM-9 | 2026-06-26 |
| R2-F1 | Preview-before-apply acceptance: response shape + no-write invariant | R2 / gpt-5.5 | Merged into FR-CM-5/FR-CM-6 | 2026-06-26 |
| R2-F2 | `build_concierge_view` payload contract (schema_version, survey, readiness, offer, form, next_action) | R2 / gpt-5.5 | Merged into FR-CM-10 | 2026-06-26 |
| R2-F3 | Package-less first-run UX/CTA acceptance | R2 / gpt-5.5 | Merged into NR-CM-A / FR-CM-2 | 2026-06-26 |
| R2-F4 | Telemetry attribute/privacy contract (bounded allowlist, no free text/paths) | R2 / gpt-5.5 | Merged into FR-CM-11 | 2026-06-26 |
| R2-F5 | Typed pre-apply validation codes + friction length caps | R2 / gpt-5.5 | Merged into FR-CM-5/FR-CM-6/NR-CM-D | 2026-06-26 |
| R3-F1 | Replay/idempotency: one-time apply intent, single write/event | R3 / gpt-5.5 | Merged into FR-CM-5/FR-CM-6/NR-CM-D | 2026-06-26 |
| R3-F2 | Post-apply feedback + state reconciliation (refresh offer, bounded confirm) | R3 / gpt-5.5 | Merged into FR-CM-1 | 2026-06-26 |
| R3-F3 | Package-less first-run journey acceptance test | R3 / gpt-5.5 | Merged into §F (FR-CM-12) | 2026-06-26 |
| R3-F4 | Durable friction-entry schema (schema_version, source, ts; no paths) | R3 / gpt-5.5 | Merged into FR-CM-5/NR-CM-B | 2026-06-26 |
| R3-F5 | Non-interactive TUI confirm fail-closed (`confirm_unavailable`) | R3 / gpt-5.5 | Merged into FR-CM-2 | 2026-06-26 |
| R4-F1 | Release/CI gate for write-capable routes | R4 / gpt-5.5 | Merged into §F (FR-CM-13) | 2026-06-26 |
| R4-F2 | Shared test-data fixture matrix | R4 / gpt-5.5 | Accepted — deferred to Phase 2 (§G) | 2026-06-26 |
| R4-F3 | User-facing recovery semantics per typed code (retryable/message/next) | R4 / gpt-5.5 | Merged into NR-CM-D | 2026-06-26 |
| R4-F4 | Mode × surface preview/apply availability matrix | R4 / gpt-5.5 | Merged into FR-CM-5/FR-CM-10 | 2026-06-26 |
| R4-F5 | Operator first-run + confinement guidance | R4 / gpt-5.5 | Merged into NR-CM-A / FR-CM-2 | 2026-06-26 |
| R5-F1 | Restart-safe partial-package detection (missing/partial/complete/blocked) | R5 / gpt-5.5 | Merged into FR-CM-6 / NR-CM-A | 2026-06-26 |
| R5-F2 | UI-redress / frame-deny protection for web confirmation | R5 / gpt-5.5 | Merged into FR-CM-5/FR-CM-6 | 2026-06-26 |
| R5-F3 | Full preview/apply intent lifecycle (digest/expiry/cleanup) | R5 / gpt-5.5 | Accepted — deferred to Phase 2 (§G) | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-26

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-26 16:20:00 UTC
- **Scope**: Requirements quality for Concierge mode — ambiguity / missing acceptance criteria / spec-vs-code mismatches on the load-bearing risk areas (write applier, serve-package-less, instantiate atomicity, parity, MCP floor). Grounded in `concierge/`/`serve.py`/`web.py` source.

**Executive summary**
- NR-CM-B mislocates the timestamp: it says "the applier must stamp" but the CLI it cites stamps *before* `build_friction_entry`, which freezes `ts` into the serialized `append_text`.
- NR-CM-D's reason-code vocabulary omits the `skipped`/no-op outcome that no-clobber instantiate actually produces.
- NR-CM-A only addresses `inputs_dir`; the `inputs_writable` blocking check (present in WRITE mode) is not mentioned and re-blocks the package-less serve.
- FR-CM-10's "parity" is underspecified — it conflates shared *view payload* with *write-behavior* equivalence.
- FR-CM-6 ("no-clobber") and FR-CM-11 ("typed reason code") have no acceptance criteria for the partial / zero-write instantiate case.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Reword NR-CM-B. It states "The web/TUI applier (`apply_concierge_plan`) must stamp `datetime.now(timezone.utc).isoformat()`, mirroring the CLI (`cli_concierge.py:233`)" — but the CLI does **not** stamp in the applier; it passes `timestamp=` into `build_friction_entry` (`cli_concierge.py:233`) *before* the line is serialized into `append_text` (`writes.py:155-162`). Specify the surface handler injects the timestamp into the builder, OR explicitly require the applier to re-parse/re-serialize `append_text`. | As written the requirement is unimplementable at the named layer — the applier receives an opaque pre-serialized line; "stamping" there is a no-op or a JSON round-trip the spec doesn't authorize. | NR-CM-B | Acceptance: a friction entry created via web/TUI has a non-null ISO-8601 `ts` identical in shape to a CLI entry. |
| R1-F2 | Interfaces | high | Extend NR-CM-D's `ConciergeWriteCode` vocabulary ("`ok` / `write_blocked` / `write_refused`") with a `skipped`/`noop`/`partial` code, and define the result when `WriteResult.skipped` is non-empty but `ok=True`. No-clobber instantiate of an existing file produces a `skipped` entry that leaves `ok=True` (`safe_write.py:65-66,236`). | Without a fourth code the surface cannot tell "instantiated N files" from "all files already existed, wrote nothing" — both map to `ok`, and FR-CM-11 would emit `kickoff_instantiated` for a no-op. | NR-CM-D | Acceptance: instantiate over a partially/fully pre-existing package returns a distinct code + written/skipped counts. |
| R1-F3 | Risks | high | NR-CM-A must cover the `inputs_writable` check, not only `inputs_dir`. It says "Demote `inputs_dir` to advisory, or add a concierge-bootstrap serve mode" but `preflight` adds a second blocking check `inputs_writable` in WRITE/DEMO mode (`serve.py:103-106`) that fails when `inputs/` is absent. | The stated demotion does not actually make a write-capable serve of a package-less project pass preflight, so FR-CM-6 stays blocked — the very thing NR-CM-A exists to fix. | NR-CM-A | Acceptance: `preflight(project_without_inputs, mode=WRITE).ok is True`. |
| R1-F4 | Validation | medium | FR-CM-10 says survey/friction/instantiate are "equivalent in both surfaces, consuming shared payloads so parity is testable against one representation." Clarify that this is *view* parity; define separately what *write* equivalence means, since web enforces mode-gate + CSRF + rate-limit while TUI is a bare confirm. | "Equivalent" is untestable as written — a shared view payload says nothing about whether the two surfaces produce identical on-disk results or apply the same authorization. | FR-CM-10 | Acceptance: a parity test asserts identical on-disk results for the same `WritePlan` across surfaces; documents the intended gate asymmetry. |
| R1-F5 | Risks | medium | FR-CM-6 calls instantiate "no-clobber" but does not state partial-apply / retry semantics for the multi-file scaffold. `apply_write_plan` continues past a per-file error (`safe_write.py:209-258`), so a failure mid-scaffold leaves a partial package. State that a retry is idempotent (ACTION_NEW skips written files) and that a partial result is surfaced. | A reader/implementer cannot tell what state the project is in after a failed instantiate, nor what the user should do. | FR-CM-6 (add a failure/recovery clause) | Acceptance: a forced mid-plan error leaves prior files intact, reports `partial`, and a re-run completes the remainder. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Ops | medium | FR-CM-11 requires `kickoff_instantiated` and `concierge_write_refused` (typed code) but defines no event for a no-clobber **no-op** instantiate (all files already present): it is neither an install (nothing written) nor a refusal (`ok=True`). Specify which funnel event fires (and with what code) when written-count is 0. | Ties to R1-F2 — telemetry would over-report installs or silently drop the no-op, corrupting the M8 funnel. | FR-CM-11 | Acceptance: instantiate that writes 0 files emits a distinct, asserted event/code. |
| R1-F7 | Security | low | FR-CM-9 says "a read-only `concierge survey` may be exposed over MCP" — pin that the new aggregator `build_concierge_view` (which bundles the `instantiate_offer` + friction form-spec) is **not** what MCP exposes; only the bare `build_survey` is. | Prevents a future MCP addition from grabbing the convenient aggregator and surfacing write-affordance metadata over the read-only floor. | FR-CM-9 | Acceptance: MCP `concierge` survey returns `build_survey` shape, not the `concierge_view` schema. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Appendix C was empty at R1.

#### Review Round R2 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 16:35:00 UTC
- **Scope**: Requirements-quality pass after accepted R1 changes, focused on preview semantics, view-model contract, first-run user value, telemetry attributes, and typed input validation.

**Executive summary**
- FR-CM-5/6 require preview-then-apply, but the requirements do not define what a valid preview response must contain or how to prove it wrote nothing.
- FR-CM-10 depends on a shared payload but does not name the required fields or schema-versioning contract for the Concierge view-model.
- NR-CM-A makes package-less serving possible, but the requirements do not say what the first-run web experience should do once serving succeeds.
- FR-CM-11 names funnel events but omits the stable attributes and privacy exclusions needed for useful operational dashboards.
- The requirements define apply-result codes but do not define typed behavior for invalid user inputs before a `WritePlan` reaches `apply_write_plan`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | high | Add explicit acceptance criteria for preview-before-apply in FR-CM-5 and FR-CM-6. The text says friction "shows a preview" and instantiate "preview the `build_instantiate_plan` `WritePlan`", but it does not define the response shape or the no-write invariant. Require preview output to include action, warnings, write count, per-write path/status/bytes, and no content beyond what is already in the plan; require disk to remain byte-identical after preview. | This makes the most important user-trust moment testable: the human sees exactly what will be written before confirming. It also prevents an implementation that jumps directly from form submission to apply while still claiming preview support in UI copy. | FR-CM-5 and FR-CM-6 | Tests call friction and instantiate preview paths, assert the response shape, and compare the project tree before/after to prove no write occurred. |
| R2-F2 | Interfaces | medium | Define the required `build_concierge_view` payload contract in FR-CM-10: `schema_version`, posture/banner text or key, `survey`, `readiness`, `instantiate_offer`, `friction_form`, and a `next_action`/CTA field. The current sentence "consuming shared payloads so parity is testable against one representation" does not say what representation must contain. | A stable view schema is the cheapest way to protect web/TUI parity and improve end-user value: both surfaces can render the same recommended next step instead of separately deciding what matters most. | FR-CM-10 | Contract test asserts required keys and schema version; web and TUI tests compare their rendered decisions against the same `next_action` from the shared payload. |
| R2-F3 | Ops | medium | Extend NR-CM-A with package-less first-run UX acceptance. After demoting blocking preflight checks, a project without `docs/kickoff/inputs/` should not merely serve; it should show an obvious Concierge path to instantiate the kickoff package, ideally a "Create kickoff package" CTA on the overview plus the `/concierge` offer. | The current requirement fixes reachability at the server layer but not discoverability at the user layer. A successful empty serve that looks broken still fails the Concierge-mode value proposition. | NR-CM-A and FR-CM-2 | Acceptance: serving a project with no `docs/kickoff/inputs/` returns HTTP 200 for overview and `/concierge`; the overview includes a Concierge instantiate CTA; the Concierge payload has `instantiate_offer.needed=True`. |
| R2-F4 | Ops | medium | Add a telemetry attribute/privacy contract to FR-CM-11. In addition to event names, require bounded attributes such as `source`, `mode`, `action`, `code`, `posture`, `with_authoring`, `written_count`, and `skipped_count`; explicitly forbid free-text friction fields and raw file paths in event attributes. | Event names alone are not enough to run an operational funnel or debug write outcomes. Attribute allowlisting also prevents accidental leakage of local paths or user-entered friction text into OTel/log sinks. | FR-CM-11 | `record_events()` tests assert exact attribute keys for success, partial/no-op, and refused paths; tests also assert friction text and per-file paths are absent. |
| R2-F5 | Risks | medium | Define typed pre-apply validation failures for Concierge forms. FR-CM-5 requires three fields and FR-CM-6 has a posture enum, but neither specifies behavior for blank fields, invalid posture, or oversized free text. Add stable codes such as `missing_required_field`, `invalid_posture`, and `input_too_large`, plus conservative length caps for friction fields before jsonl serialization. | R1 covered `apply_write_plan` outcomes, but many bad user inputs fail before apply. A typed validation contract avoids opaque 500s, protects the append-only log from bloat, and gives both web and TUI the same user-facing copy. | FR-CM-5, FR-CM-6, and NR-CM-D | Tests submit blank friction fields, invalid posture, and overlong text; each returns a typed non-500 error and leaves the project tree unchanged. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 requirements suggestions have already been triaged into Appendix A.

#### Review Round R3 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 16:50:00 UTC
- **Scope**: Late-round requirements pass after accepted R1 and incoming R2, focused on replay/idempotency, post-apply feedback, persisted provenance, full first-run journey validation, and non-interactive TUI behavior.

**Executive summary**
- FR-CM-5/6 require explicit human confirmation, but the requirements do not define replay or double-submit behavior after a preview has been confirmed once.
- The requirements specify what writes do, but not what the user sees immediately after a successful or no-op write.
- Telemetry attributes are not a substitute for durable friction-entry provenance; the jsonl artifact should be minimally self-describing.
- Existing acceptance criteria are strong at the component level but do not yet require one package-less first-run journey through serve, preview, apply, refresh, and friction logging.
- The TUI command needs defined behavior when confirmation cannot be obtained, otherwise "human privilege" has an ambiguous edge case.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Security | medium | Add replay/idempotency acceptance criteria to FR-CM-5 and FR-CM-6. After a preview is confirmed and applied once, repeating the same browser submission, apply token, or TUI confirmation must not append a second friction line or emit a second install event. Require a one-time apply intent, idempotency key, or equivalent consumed confirmation record with a stable typed result for repeats. | FR-CM-5 says "on explicit human confirmation appends" and FR-CM-6 says "on explicit human confirmation apply it", but neither defines whether one confirmation can be replayed. CSRF and explicit confirm do not by themselves prevent accidental double-clicks or browser resubmits. | FR-CM-5, FR-CM-6, and NR-CM-D | Acceptance: applying the same confirmed intent twice changes disk only once and emits only one success event; the repeated request returns a typed replay/no-op/refused outcome. |
| R3-F2 | Ops | medium | Define post-apply user feedback and state reconciliation for both surfaces. After instantiate, the Concierge view should refresh or return an updated payload where `instantiate_offer.needed` reflects the new package state and the user sees the next recommended action. After friction logging, the user should receive a bounded success confirmation that does not echo raw local paths or submitted free text. | The current requirements prove that writes happen, but not that users can tell what changed. This is especially important for package-less onboarding, where a stale "create package" offer after a successful apply would make the feature feel broken. | FR-CM-1, FR-CM-5, FR-CM-6, and FR-CM-10 | Acceptance: after instantiate apply, a refreshed Concierge payload no longer offers package creation for the same root; after friction apply, the confirmation contains bounded metadata only. |
| R3-F3 | Validation | high | Add a required package-less first-run journey acceptance test. The journey should start from a root without `docs/kickoff/inputs/`, serve successfully, expose the Concierge CTA/route, preview instantiate without writes, apply instantiate, refresh the Concierge state, then log friction. It should assert the user-visible state and telemetry at the journey level, not only individual helpers. | NR-CM-A, FR-CM-2, FR-CM-5, FR-CM-6, FR-CM-10, and FR-CM-11 are tightly coupled. Component tests can all pass while the first-run path still fails through a missing route, stale state, or mismatched event. | Add to section 3 or a new validation subsection after FR-CM-11 | Acceptance: a single automated fixture exercises the package-less web journey end-to-end; TUI covers the same instantiate/friction write-plan and apply results against the shared payload. |
| R3-F4 | Data | low | Extend FR-CM-5 or NR-CM-B with a minimal durable friction-entry schema: include `schema_version`, `source` (`web` or `tui`), and timestamp, while preserving the three required user-authored fields and forbidding raw filesystem paths. | R2-F4 covers event attributes, but the append-only `concierge-friction.jsonl` is the durable artifact that OQ-5 may later read back. Without version/source provenance, future bounded read-back and migrations have to infer too much from free text or external telemetry. | FR-CM-5 and NR-CM-B | Acceptance: web/TUI-created jsonl entries include `schema_version`, `source`, `ts`, `friction`, `what_happened`, and `implication`; entries do not contain raw project paths. |
| R3-F5 | Risks | medium | Specify non-interactive or interrupted TUI confirmation behavior. For `kickoff concierge`, if `questionary.confirm().ask()` returns `None`, raises, or detects no interactive terminal, the operation must be refused with a stable typed result and no disk write. Explicitly keep unattended `--yes` behavior out of v1 unless a later requirement reopens the human-confirmation model. | FR-CM-2 defines a new `questionary`-driven command and P3 requires foreground human confirmation, but neither says what happens when no foreground confirmation is possible. This edge case should fail closed. | FR-CM-2, FR-CM-5, FR-CM-6, and NR-CM-D | Acceptance: mocked non-TTY, `None`, and interrupted confirm paths leave disk unchanged and return a typed refusal or `confirm_unavailable` code. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: Preview response shape and no-write invariants are prerequisite contracts for R3-F1 replay protection.
- R2-F2: The required shared payload schema is the right basis for R3-F2 post-apply reconciliation.
- R2-F3: Package-less first-run CTA should be accepted and then verified in the R3-F3 end-to-end journey.
- R2-F4: Event attributes and privacy exclusions are necessary for R3-F3 journey assertions and operational dashboards.
- R2-F5: Typed pre-apply validation pairs cleanly with R3-F5 typed confirmation-unavailable behavior.

**Disagreements**: none.

#### Review Round R4 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 17:05:00 UTC
- **Scope**: Requirements-quality pass after accepted R1 and incoming R2/R3, focused on rollout gates, reusable test data, recovery UX, mode semantics, and operator-facing first-run guidance.

**Executive summary**
- The requirements define what Concierge mode must do, but not which safety and privacy checks must be present before write endpoints are releasable.
- The acceptance criteria would be stronger if they named a reusable fixture matrix instead of relying on per-requirement bespoke setup.
- Typed outcomes are specified, but user-facing recovery copy and retryability semantics are not yet requirements.
- Web and TUI authorization differ by design; requirements should explicitly define preview/apply availability by mode and surface.
- Package-less and symlink-confined roots need discoverable operator guidance, not only server-side or typed-error behavior.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Ops | high | Add a release/CI gate requirement for write-capable Concierge routes. Before any implementation satisfies FR-CM-5 "on explicit human confirmation appends" or FR-CM-6 "on explicit human confirmation apply it", CI must prove preview writes nothing, package-less WRITE preflight passes, MCP/agentic tools remain read-only, replay protection is active, and telemetry excludes free text and raw paths. | The current requirements contain strong individual acceptance criteria, but no sequencing invariant that prevents write routes from shipping before their guardrails. This is a release safety requirement, not another implementation detail. | Add a new "Release and CI gates" subsection after FR-CM-11 or under section 3.D | CI checklist or automated test group fails if write endpoints are present without no-write preview, package-less preflight, no-MCP-write, replay, and telemetry privacy assertions. |
| R4-F2 | Validation | medium | Define a shared test-data matrix for acceptance criteria: package-less root, partially scaffolded root, fully existing package, symlink-confined root, invalid posture, blank friction fields, and oversized friction fields. Tie these fixtures to FR-CM-5/6/8/9/10/11 and NR-CM-A/B/D rather than letting each requirement invent its own setup. | R1-R3 add many tests that cover adjacent filesystem states. A named fixture matrix reduces maintenance cost and ensures web, TUI, MCP, telemetry, and applier tests exercise the same edge cases. | Add to a new validation subsection after FR-CM-11 | Test helpers expose the matrix; every acceptance test that claims package-less, partial, no-op, symlink-blocked, or invalid-input behavior uses the shared fixtures and golden plan summaries. |
| R4-F3 | Risks | medium | Add user-facing recovery semantics for typed outcomes. NR-CM-D defines codes such as `write_blocked`, `write_refused`, `skipped`, and `partial`, but the requirements should also state whether each code is retryable, what bounded message is shown, and what next action the user gets. For `partial`, require written/skipped/failed/remaining counts and a safe retry path; for `write_blocked`, require the `STARTD8_CONCIERGE_ALLOWED_ROOTS` hint without telemetry path leakage. | Codes are not enough for end-user value. A technically correct `partial` or `write_blocked` response can still strand a user unless the requirement defines recovery copy and next actions. | NR-CM-D plus FR-CM-5/FR-CM-6 acceptance clauses | Table-driven test enumerates every code and asserts retryability, message key, bounded metadata, and next action for web and TUI outputs. |
| R4-F4 | Interfaces | medium | Add a mode and surface availability matrix for Concierge preview/apply behavior. FR-CM-5 says "Web: same-origin + CSRF" and "TUI: explicit confirm", while FR-CM-10 documents gate asymmetry, but the requirements do not say what READ, WRITE, DEMO, inspect/preview, web, and TUI combinations should allow. Require previews to be available where safe and applies to fail closed outside explicit write-capable human-privilege modes. | This prevents future ambiguity where one surface allows an apply in a mode the other refuses, or where preview is accidentally blocked because apply is blocked. It also gives operations and tests a single expected matrix. | FR-CM-5, FR-CM-6, and FR-CM-10 | Matrix test iterates mode and surface combinations: preview availability, apply availability, refusal code, and disk unchanged on refused apply. |
| R4-F5 | Ops | low | Add operator-facing guidance acceptance for first-run and confinement cases. NR-CM-A says the Welcome Mat must be serveable without `docs/kickoff/inputs/`, and OQ-3/NR-CM-D mention the allowed-roots hint, but the requirements should state that startup or local-web guidance points package-less users to `/concierge` and explains symlink/confinement remediation safely. | Package-less serve and symlink blocking are likely first-run experiences. If guidance only appears after a failed write, users may never discover the instantiate path or may not understand why a local `/tmp` worktree is blocked. | NR-CM-A, FR-CM-2, and NR-CM-D | Smoke test captures package-less serve output and `write_blocked` UI output; package-less output names the Concierge route or CTA, blocked output names the env-var remediation, and telemetry omits raw path values. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: Preview response shape and no-write invariants are prerequisite release gates for safe write endpoints.
- R2-F4: Telemetry attribute allowlisting is necessary before operational dashboards or privacy assertions can be trusted.
- R3-F1: Replay/idempotency acceptance should be part of the write-route release gate because friction is append-only.
- R3-F3: The package-less first-run journey should be accepted, with R4-F2 supplying shared fixtures for cheaper maintenance.
- R3-F5: Non-interactive TUI refusal is a necessary mode-matrix case and should fail closed.

**Disagreements**: none.

#### Review Round R5 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 17:20:00 UTC
- **Scope**: Late-stage requirements pass after accepted R1 and incoming R2/R3/R4, focused on restart-safe partial-package recovery, UI-redress protection for human-confirmed web writes, and scoped preview/apply intent lifecycle.

**Executive summary**
- FR-CM-6 and NR-CM-A still define the instantiate offer mostly around absence of `docs/kickoff/inputs/`; they should also cover cold-start recovery when a package is partially scaffolded but `inputs/` already exists.
- P3 and FR-CM-5/6 depend on foreground human confirmation, but the requirements do not yet require clickjacking/UI-redress protection for the local web confirmation surface.
- R3's replay protection needs acceptance criteria for intent scope, digest binding, expiry, and cleanup so stale previews cannot become a maintenance or security ambiguity.
- Prior R2-R4 items are mostly complementary; this round endorses the contracts that R5 depends on instead of duplicating them.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Risks | high | Extend FR-CM-6 and NR-CM-A beyond the sentence "When the served project lacks a kickoff package (no `docs/kickoff/inputs/`)" to define restart-safe partial-package detection. Require the Concierge payload to distinguish `missing`, `partial`, `complete`, and blocked states, where `partial` means at least one expected instantiate artifact is absent even if `docs/kickoff/inputs/` exists. | R1/R4 cover partial results and retry while the process still knows what happened, but the requirements do not say how a later server start rediscovers an incomplete package. A boolean keyed only to `inputs/` can hide partial scaffolds and strand the user without a recovery action. | FR-CM-6 and NR-CM-A | Acceptance: a root with `docs/kickoff/inputs/` present but other expected instantiate artifacts missing yields `package_state=partial`, shows a retry/recovery action, and retry completes missing ACTION_NEW files without overwriting existing files. |
| R5-F2 | Security | medium | Add UI-redress protection to the human-confirmation requirement for web writes. P3 says writes require "a foreground human" and FR-CM-5/6 require explicit confirmation, but the web surface should also forbid framing of `/concierge`, preview, and apply confirmation responses with `Content-Security-Policy: frame-ancestors 'none'` or `X-Frame-Options: DENY`. | R1's Origin/Host checks protect request provenance, but clickjacking is a different path: the user can be tricked into clicking the real local page inside a hostile frame. The requirement should make intentional, visible confirmation part of the web write contract. | P3, FR-CM-5, and FR-CM-6 | Acceptance: web responses involved in Concierge write confirmation include a frame-deny policy, and a browser test or header assertion proves the confirmation UI cannot be embedded by another origin. |
| R5-F3 | Ops | medium | Add acceptance criteria for preview/apply intent lifecycle. Building on R3-F1, require each one-time intent to be bound to root, action, mode/source, posture, and a digest of the previewed `WritePlan`; expire abandoned intents with the local session lifetime; consume each intent atomically; and avoid storing free-text friction fields in long-lived session state. | R3-F1 prevents replay, but without scope, digest, and cleanup requirements a stale or cross-context intent can outlive the preview assumptions. The digest also gives observability a safe correlation key without leaking local paths or user-authored friction text. | FR-CM-5, FR-CM-6, FR-CM-11, and NR-CM-D | Acceptance: stale, expired, wrong-root, wrong-action, or digest-mismatched intents return typed non-write outcomes; cleanup removes abandoned intents; telemetry may include the bounded digest/correlation key but not paths or friction text. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: Preview response shape and no-write invariants are prerequisites for R5-F3's digest-bound apply intent.
- R2-F2: The shared payload schema should carry the package-state enum required by R5-F1.
- R2-F4: Telemetry attribute allowlisting is necessary before carrying any digest/correlation key.
- R3-F1: Replay/idempotency remains the correct foundation; R5-F3 only scopes and bounds its lifecycle.
- R3-F2: Post-apply reconciliation is still needed so partial, complete, and retryable states are visible to users.
- R3-F3: The package-less first-run journey should include a cold-start partial-package scenario if R5-F1 is accepted.
- R4-F2: The shared fixture matrix is the right place to maintain the package-less, partial, symlink, and invalid-input states.
- R4-F3: User-facing recovery semantics should include the new `partial package on startup`, `expired intent`, and `stale intent` outcomes.
- R4-F4: The mode/surface availability matrix should include preview/apply intent expiry and web-only frame-deny expectations.

**Disagreements**: none.
