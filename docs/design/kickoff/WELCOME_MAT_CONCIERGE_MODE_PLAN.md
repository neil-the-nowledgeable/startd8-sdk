# Welcome Mat — Concierge Mode — Implementation Plan

**Version:** 1.2 (Post-CRP R2–R5)
**Date:** 2026-06-26
**Status:** Draft
**Requirements:** `WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` (v0.4)

> **Headline.** Concierge mode is **mostly a thin surface** over machinery that already exists — the
> load-bearing OQ-1 ("does the web need a new generic WritePlan engine?") is **false**:
> `concierge/writes.py:203 to_planned_writes` + `safe_write.py:200 apply_write_plan` are the exact
> 3-line pattern the CLI uses (`cli_concierge.py:201-202,250-251`), reusable verbatim. The real work
> is surface plumbing + **four concrete defects/conflicts** v0.1 didn't anticipate (a serve-blocking
> conflict, an inert `--force`, a missing timestamp stamp, and no existing TUI host).

## Milestones

### M-CM0 — Shared Concierge view-model (FR-CM-3/4/10) — *foundation*
- **Add** `kickoff_experience/concierge_view.py::build_concierge_view(project_root) -> dict`: a
  schema-versioned dict combining `build_survey()` (`concierge/core.py:83`),
  `ReadinessView.from_assess(build_assess())` (`readiness.py:100`) — **reused, not re-derived**
  (FR-CM-4), an `instantiate_offer` (`{"needed": not (root/"docs/kickoff/inputs").is_dir(),
  "postures": [...]}`), and a static friction form-spec. One representation both surfaces render
  (mirrors `state.to_dict()` parity oracle).
- **R1-S6 (perf):** `build_survey` walks `root.rglob("*")` (`core.py:77`), so `build_concierge_view`
  is an O(repo) cost on every `GET /concierge` — a latency/soft-DoS cliff on large monorepos. Bound or
  memoize it: add a short TTL / per-request memo, or a bounded walk.
- **R1-S9 (MCP floor):** pin that `build_concierge_view` (with its `instantiate_offer` + friction
  form-spec) is **not** MCP-exposed — only the bare `build_survey` shape is (FR-CM-9). The aggregator
  carries write-affordance metadata and must stay off the read-only MCP floor.
- **R2-S2 (schema-versioned view contract):** make `build_concierge_view` a documented schema-versioned
  payload — `schema_version`, posture/banner copy-or-key, `survey`, `readiness`, `instantiate_offer`,
  `friction_form`, `next_action` — not a free-form dict, so web/TUI render from one stable interface
  (parity oracle). Unit test asserts the exact required keys + `schema_version`.
- **R5-S1 (restart-safe package-state):** replace the boolean `instantiate_offer.needed` with a
  package-state enum (`missing` / `partial` / `complete` / `blocked`) derived from the instantiate
  plan/checklist, so a cold-start partial scaffold (`inputs/` present but other ACTION_NEW artifacts
  absent) is rediscovered after restart, not hidden. Test: partially scaffolded root →
  `package_state=partial` + retry action; retry completes remaining ACTION_NEW without overwrite.
- Depends on: nothing.

### M-CM1 — Generic WritePlan applier (FR-CM-7, resolves OQ-1)
- **Add** `kickoff_experience/concierge_apply.py::apply_concierge_plan(project_root, plan, *,
  force=False)`: `apply_write_plan(root, to_planned_writes(plan), force=force)` wrapped to catch
  `SafeWriteError` + non-`ok` `WriteResult` and return a **typed** result with a new
  `ConciergeWriteCode` vocabulary (parallel to `CaptureCode`, `capture.py:40`) — `OK`, `WRITE_BLOCKED`
  (symlink/confinement; surface the `STARTD8_CONCIERGE_ALLOWED_ROOTS` hint, OQ-3), `WRITE_REFUSED`
  (NR-CM-D).
- **R1-S3 (fourth code):** add a `SKIPPED`/`PARTIAL` `ConciergeWriteCode` and map `WriteResult.skipped`.
  No-clobber instantiate of an existing file lands in `skipped` (`safe_write.py:236`) while `ok=True`
  ignores `skipped` (`ok = not blocked and not errors`, `safe_write.py:65-66`), so the applier must
  return **written/skipped counts** — not bare `OK` — to distinguish "wrote 7 files" from "all 7
  already existed, wrote 0".
- **NR-CM-B / R1-S2 (correct the layer):** **move** friction timestamp stamping *out* of
  `apply_concierge_plan` and into the surface handler. `build_friction_entry` bakes `ts` into
  `append_text` at build time (`writes.py:155-162`), so by the time the applier sees the plan the
  timestamp is frozen inside an opaque string — stamping there would require an unauthorized
  parse/re-serialize. The surface handler passes `timestamp=datetime.now(timezone.utc).isoformat()`
  **into** `build_friction_entry` *before* serialization, exactly as the CLI does
  (`cli_concierge.py:233`); else UI entries are unstamped (the NR-CM-B failure).
- No stale-file guard needed (instantiate = `ACTION_NEW` no-clobber; friction = `ACTION_APPEND`
  O_APPEND concurrency-safe).
- **R2-S5 (typed pre-apply validation):** add a typed validation layer ahead of the builders —
  `invalid_posture` / `missing_required_field` / `input_too_large` with conservative friction-field
  length caps **before** `build_friction_entry` serializes. Bad inputs return typed non-500 results and
  append no jsonl line.
- **R3-S3 (durable friction provenance):** the surface handler stamps `schema_version` + `source`
  (`web`/`tui`) into the friction entry alongside `ts` (passed into `build_friction_entry`, per
  NR-CM-B), preserving the three user fields and adding no local paths — so OQ-5 read-back can migrate.
- **R4-S4 (shared result envelope):** introduce one `ConciergeResult` envelope consumed by web + TUI —
  `code`, `message_key`, `severity`, `retryable`, `written_count`, `skipped_count`, `remaining_count`,
  optional refreshed view — with user-facing copy in a single presenter map, so recovery/retry copy
  cannot drift between surfaces.
- Depends on: nothing.

### M-CM2 — Serve a package-less project (NR-CM-A) — *unblocks FR-CM-6, do before web instantiate*
- **Change** `serve.py:97` to make `inputs_dir` **advisory** (`blocking=False`) so a project missing
  `docs/kickoff/inputs/` can still be served (today `PreflightResult.ok` requires it, `serve.py:76`,
  and `serve_kickoff`/`start_cmd` refuse, `serve.py:214`, `cli_kickoff.py:212`). Without this, the
  instantiate offer is unreachable for exactly the projects it targets.
- **R1-S1 (also neutralize `inputs_writable`):** flipping `serve.py:97` alone is **not enough**. In
  WRITE/DEMO mode preflight adds a second blocking `Check("inputs_writable", inputs_ok and
  os.access(...))` (`serve.py:103-106`); when `inputs/` is absent `inputs_ok` is False, so this check
  fails-blocks the serve. Neutralize it too (advisory, or skip in a concierge-bootstrap serve mode).
  Test: `preflight(no-inputs, mode=WRITE).ok is True` and no blocking check fails.
- The web overview/state must degrade gracefully with no inputs (empty state already does).
- **R2-S3 (package-less first-run routing/CTA):** a package-less serve must not merely stop failing —
  when `instantiate_offer.needed`, the overview surfaces a prominent "Create kickoff package" Concierge
  CTA / banner to `/concierge`, and ordinary capture/apply affordances avoid implying a package exists.
  Test: no-`inputs/` root serves 200, overview shows the CTA, `/concierge` reports `needed=True`.
- **R4-S5 (operator startup/confinement guidance):** startup output for a package-less serve points to
  `/concierge` as the next step; `WRITE_BLOCKED` (symlink/confinement) surfaces the bounded
  `STARTD8_CONCIERGE_ALLOWED_ROOTS` remediation — without emitting raw path lists into telemetry.
- Depends on: nothing. **Blocks M-CM3 instantiate.**

### M-CM3 — Web Concierge surface (FR-CM-1/2/3/4/5/6/11)
In `web.py build_kickoff_app` (shares `_SessionStore`, `mode`, `cfg`, `root`, `stylesheet`):
- **`GET /concierge`** → render `build_concierge_view(root)` (posture banner, survey panel, readiness
  recap, friction form, instantiate offer if `inputs/` absent). Issue CSRF cookie like
  `overview()`/`step()` (`web.py:255-257`). Emit `survey_viewed`.
- **Nav link** to `/concierge` from `_render_overview` (`web.py:148`).
- **`POST /concierge/friction`** + **`POST /concierge/instantiate`**: reuse the *exact* apply gate
  from `capture_apply` (`web.py:296-313`) — preview/inspect-mode 403, `sessions.valid` 403,
  `sessions.rate_ok` 429 — then `build_friction_entry`/`build_instantiate_plan` → `apply_concierge_plan`.
  Typed JSON like `_capture_error`. Emit `friction_logged`/`kickoff_instantiated`/
  `concierge_write_refused`.
  - **R1-S8 (DNS-rebinding defense):** the capture gate uses an httponly+SameSite=strict CSRF token
    but does **no** Origin/Host allowlist check, leaving a loopback app exposed to DNS-rebinding (a
    rebind-forged request could append arbitrary friction jsonl lines). Add an `Origin`/`Host ==
    127.0.0.1:port` allowlist check on the two new POSTs; this also hardens the pre-existing capture
    endpoint. Test: a forged `Origin` header is rejected on both new POSTs.
- **Instantiate target = the pinned served root only** (OQ-2) — never a surface-supplied path.
- **Force (NR-CM-C / D3):** ship **honest no-clobber** — no force UI in v1. `build_instantiate_plan`
  emits `ACTION_NEW` for every file and `apply_write_plan` skips `ACTION_NEW` when the file exists
  **regardless of force** (`safe_write.py:231`), so a force toggle would be an inert lie. (Fixing the
  builder to emit `ACTION_OVERWRITE` under force is a separate, later decision.)
- **R1-S4 (Failure & recovery — partial-apply):** multi-file instantiate is **non-atomic**.
  `apply_write_plan` collects per-file blocked/errors and **continues** (`safe_write.py:209-258`), so
  a mid-loop confinement/OS error leaves a half-written package with `ok=False`. Mitigation: because
  every file is `ACTION_NEW` no-clobber, a **retry is idempotent** (already-written files skip), so the
  documented recovery is "re-run instantiate". Surface a `PARTIAL` result (the R1-S3 code). Test:
  inject a per-file error mid-plan → prior files persisted, result is `PARTIAL`, a second call
  completes the remainder.
- **R2-S1 (explicit preview endpoints):** add `POST /concierge/friction/preview` +
  `POST /concierge/instantiate/preview` reusing the pure builders — return writes/warnings/posture/bytes
  and typed builder errors **without mutating disk** — so preview-then-apply is testable, not just UI
  prose. Test: preview leaves disk byte-identical; bad posture/missing field → typed 400; apply stays
  CSRF/session/rate-gated.
- **R3-S1 (one-time apply intent):** store a short-lived apply-intent/idempotency id in the
  preview/session and consume it on apply; a double-click / refresh-resubmit / repeated confirm returns
  a typed no-op/refused outcome — no second friction append, no duplicate install event.
- **R3-S2 (post-apply reconciliation):** after `kickoff_instantiated`, rebuild `build_concierge_view`
  and return the updated `instantiate_offer`/readiness/next-action; after `friction_logged`, return a
  bounded success confirmation (no raw paths, no submitted free text).
- **R4-S3 (user-facing partial recovery):** a `PARTIAL`/skipped result summarizes
  written/skipped/failed/remaining files and offers a safe "retry instantiate" next action reusing the
  same no-clobber semantics; a second run completes remaining writes and clears the recovery state.
- **R5-S2 (frame-busting / UI-redress):** emit `Content-Security-Policy: frame-ancestors 'none'` (or
  `X-Frame-Options: DENY`) on `/concierge`, preview, and apply-confirmation responses so the local UI
  cannot be framed and a foreground click cannot be visually hijacked. Header/browser test asserts the
  frame-deny policy.
- Depends on: M-CM0, M-CM1, M-CM2.

### M-CM4 — TUI Concierge host command (FR-CM-1/2/3/5/6, resolves OQ-4) — *build, not extend*
- **Discovery D2:** `KickoffChat`/`new_kickoff_chat` (`chat.py:161`) and `ConciergeChat` have **no**
  interactive REPL/menu caller anywhere — there is no running "TUI Welcome Mat" to add a menu item to.
- **Add** a Typer command `kickoff concierge` in `cli_kickoff.py` (registered like `start_cmd`
  `cli_kickoff.py:195`) that renders `build_concierge_view` with `rich` (`console` already imported)
  and offers friction/instantiate via `questionary.confirm().ask()` (hard dep, `pyproject.toml:32`;
  house pattern `tui/mixin_enhancement_chain.py:45`) → `apply_concierge_plan` (the **same** applier as
  web — FR-CM-7 one write path).
- **R1-S7 (write-parity matrix):** the shared `build_concierge_view` gives *view* parity, but the web
  write path enforces mode-gate + CSRF + rate-limit (`web.py:296-313`) while the TUI path is a bare
  `questionary.confirm()` with none of those — a single view oracle cannot test write-behavior
  equivalence. Add a parity test matrix: the **same `WritePlan`** → web (gated) and TUI (confirm)
  produce **identical on-disk results**; document the intended gate asymmetry (dep note on M-CM3,
  whose apply gate is the gated side).
- **R3-S5 (non-interactive fail-closed):** when `questionary.confirm().ask()` returns `None`, raises,
  or runs in a non-TTY/unsupported terminal, treat it as `WRITE_REFUSED`/`confirm_unavailable` and do
  **not** apply; no hidden `--yes` shortcut in v1 (human confirmation is explicit). Test: monkeypatch
  confirm → `False`/`None`/raise all leave disk unchanged and return a typed friendly refusal.
- Depends on: M-CM0, M-CM1.

### M-CM5 — Telemetry (FR-CM-11)
- **Add** to `telemetry.py:37-53`: `EV_SURVEY_VIEWED`, `EV_KICKOFF_INSTANTIATED`,
  `EV_CONCIERGE_WRITE_REFUSED`; extend `FUNNEL_EVENTS`. `friction_logged` already exists.
- **R2-S4 (event attribute/privacy contract):** every Concierge event carries a bounded attribute
  allowlist — `source` (web/tui), `mode`, `action`, `code`, `posture`, `with_authoring`,
  `written_count`, `skipped_count` — across success / no-op / partial / refused, and **never** emits
  `friction`/`what_happened`/`implication` text or raw file paths. `record_events()` test asserts the
  exact keys and the absence of free text + paths.

### M-CM6 — Boundaries (FR-CM-8/9) — *verification + one negative regression guard test*
- **FR-CM-8 already holds**: `build_kickoff_registry` exposes only `survey/assess/field_states` read
  tools (`chat.py:97-138`); the loop has no tool to apply a write → "propose-only" is automatic. No
  registry change (optionally note drafting in the system prompt).
- **R1-S5 (negative regression guard):** "propose-only" is enforced by the **absence** of an apply
  tool, which a future addition could silently widen. Ship a regression test that enumerates the tool
  names exposed by `build_concierge_registry` (`concierge/chat.py`) and the MCP `startd8_concierge`
  path and asserts the set ⊆ `{survey, assess, field_states}` — **no** apply/instantiate/friction
  tool. (This milestone is no longer ~0 code: it ships this guard test.)
- **FR-CM-9 already satisfied**: `startd8_concierge` MCP tool is read-only and write actions return a
  preview `WritePlan` (no `apply_write_plan` in the MCP path) — **no new work**.
- **R1-S9 (aggregator not MCP-exposed):** pin that `build_concierge_view` (with `instantiate_offer` +
  friction form-spec) is **not** the MCP surface — only the bare `build_survey` is. Assert the MCP tool
  returns the `build_survey` shape, not the `concierge_view` schema.

### M-CM7 — Validation & release gates (R2–R5)
- **R3-S4 (package-less first-run journey test):** one end-to-end fixture exercises the feature as a
  user would — serve a root with no `docs/kickoff/inputs/`, open overview, enter Concierge, **preview**
  instantiate (no write), **apply** instantiate, refresh state, then **log friction** — asserting
  HTTP 200, preview no-write, apply write-counts, refreshed `instantiate_offer`, friction append,
  expected telemetry attributes, and no MCP write tool. TUI runs the same write-plan/apply sequence
  against the shared payload. (Low-hanging integration guard — all pieces are deterministic + local.)
- **R4-S1 (rollout/CI sequencing gates):** before `POST /concierge/friction` or
  `POST /concierge/instantiate` are considered done / mergeable in a release branch, CI must prove:
  M-CM1 typed outcomes, M-CM2 package-less WRITE preflight, R2 preview no-write, R2 telemetry-privacy,
  and M-CM6 MCP/loop negative guards all pass. The CI job/checklist **fails** if write routes run
  without these. (Release-safety invariant, not another impl detail.)
- Depends on: M-CM1, M-CM2, M-CM3, M-CM4, M-CM5, M-CM6.

### Phase 2 (post-v1) — accepted, deferred
> The two heaviest mechanisms are accepted but phased out of v1. R3-S1 replay-once stays the v1
> essential; only its full lifecycle is deferred.
- **[Phase 2] R4-S2 — shared Concierge fixture pack.** One named fixture pack (package-less root,
  partially scaffolded root, fully existing package, symlink-confined root, invalid friction/posture
  payloads) with golden `WritePlan` summaries, reused across M-CM1–M-CM6 tests instead of per-test
  setup.
- **[Phase 2] R5-S3 — preview/apply intent lifecycle.** Bind each one-time intent to
  `project_root`/action/mode-source/posture + a **digest** of the previewed `WritePlan`; expire
  abandoned intents on the session TTL; consume atomically; scrub expired records from `_SessionStore`
  without retaining free-text friction. The digest doubles as a safe telemetry correlation key.

## Dependency order
```
M-CM0 (view-model) ─┬─> M-CM3 (web) ──┐
M-CM1 (applier) ────┤                 ├─> M-CM5 (telemetry) ; M-CM6 (verify)
M-CM2 (serve-pkgless)┘  M-CM4 (TUI) ──┘
```
Build M-CM0/M-CM1/M-CM2 first. M-CM2 specifically unblocks the FR-CM-6 instantiate offer.

## Open questions still open
- **OQ-5 (friction read-back)** — defer; append-only for v1. A bounded reader belongs in the
  `kickoff_experience` layer (human privilege), never in `concierge/`, never over MCP.
- **OQ-6 (force)** — resolved to honest no-clobber for v1 (D3); revisit if overwrite is wanted.

All other OQs resolved — see Requirements §0.

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
| R1-S1 | M-CM2 must also neutralize the `inputs_writable` check, not only `inputs_dir` | R1 / claude-opus-4-8-1m | Merged into M-CM2 | 2026-06-26 |
| R1-S2 | Move friction timestamp to the surface handler (pass into `build_friction_entry` before serialization) | R1 / claude-opus-4-8-1m | Merged into M-CM1 (NR-CM-B bullet) | 2026-06-26 |
| R1-S3 | Add a 4th `ConciergeWriteCode` (SKIPPED/PARTIAL) mapping `WriteResult.skipped`; return written/skipped counts | R1 / claude-opus-4-8-1m | Merged into M-CM1 | 2026-06-26 |
| R1-S4 | State partial-apply + idempotent-retry semantics for multi-file instantiate (Failure & recovery) | R1 / claude-opus-4-8-1m | Merged into M-CM3 | 2026-06-26 |
| R1-S5 | Ship a negative regression guard test enumerating loop + MCP tool names ⊆ {survey, assess, field_states} | R1 / claude-opus-4-8-1m | Merged into M-CM6 | 2026-06-26 |
| R1-S6 | Bound/memoize `build_survey` in `build_concierge_view` (TTL/per-request memo or bounded walk) | R1 / claude-opus-4-8-1m | Merged into M-CM0 | 2026-06-26 |
| R1-S7 | Add a write-parity test matrix — same `WritePlan` → web (gated) and TUI (confirm) identical on disk | R1 / claude-opus-4-8-1m | Merged into M-CM4 (+ M-CM3 dep note) | 2026-06-26 |
| R1-S8 | Add an Origin/Host allowlist check on the new POST friction/instantiate endpoints (DNS-rebinding) | R1 / claude-opus-4-8-1m | Merged into M-CM3 | 2026-06-26 |
| R1-S9 | Pin that `build_concierge_view` is not MCP-exposed (only bare `build_survey`) | R1 / claude-opus-4-8-1m | Merged into M-CM6 / M-CM0 | 2026-06-26 |
| R2-S1 | Explicit preview endpoints / two-step preview contract before apply | R2 / gpt-5.5 | Merged into M-CM3 | 2026-06-26 |
| R2-S2 | Schema-versioned `build_concierge_view` contract (not loose dict) | R2 / gpt-5.5 | Merged into M-CM0 | 2026-06-26 |
| R2-S3 | Package-less first-run routing/CTA, not just serve | R2 / gpt-5.5 | Merged into M-CM2 / M-CM3 | 2026-06-26 |
| R2-S4 | Telemetry event attribute/privacy contract | R2 / gpt-5.5 | Merged into M-CM5 | 2026-06-26 |
| R2-S5 | Typed pre-apply validation layer + friction length caps | R2 / gpt-5.5 | Merged into M-CM1 | 2026-06-26 |
| R3-S1 | One-time apply-intent / idempotency token for writes | R3 / gpt-5.5 | Merged into M-CM3 (+ M-CM4 confirm) | 2026-06-26 |
| R3-S2 | Post-apply reconciliation (refresh view / bounded confirm) | R3 / gpt-5.5 | Merged into M-CM3 | 2026-06-26 |
| R3-S3 | Minimal persisted friction provenance (schema_version, source) | R3 / gpt-5.5 | Merged into M-CM1 | 2026-06-26 |
| R3-S4 | Full package-less first-run journey test | R3 / gpt-5.5 | Merged into M-CM7 | 2026-06-26 |
| R3-S5 | Safe non-interactive `kickoff concierge` confirm behavior | R3 / gpt-5.5 | Merged into M-CM4 | 2026-06-26 |
| R4-S1 | Rollout/CI sequencing gates before write routes | R4 / gpt-5.5 | Merged into M-CM7 | 2026-06-26 |
| R4-S2 | Shared Concierge fixture pack | R4 / gpt-5.5 | Accepted — deferred to Phase 2 | 2026-06-26 |
| R4-S3 | User-facing partial-recovery UX for instantiate | R4 / gpt-5.5 | Merged into M-CM3 | 2026-06-26 |
| R4-S4 | Shared `ConciergeResult` envelope + presenter map | R4 / gpt-5.5 | Merged into M-CM1 | 2026-06-26 |
| R4-S5 | Startup/help guidance for package-less + symlink roots | R4 / gpt-5.5 | Merged into M-CM2 | 2026-06-26 |
| R5-S1 | Restart-safe package-state enum (missing/partial/complete/blocked) | R5 / gpt-5.5 | Merged into M-CM0 | 2026-06-26 |
| R5-S2 | Frame-busting / UI-redress headers on web confirmation | R5 / gpt-5.5 | Merged into M-CM3 | 2026-06-26 |
| R5-S3 | Preview/apply intent lifecycle (digest/expiry/cleanup) | R5 / gpt-5.5 | Accepted — deferred to Phase 2 | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-26

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-26 16:20:00 UTC
- **Scope**: Adversarial pass on the focus areas — generic write applier (M-CM1), serve-package-less (M-CM2), instantiate boundary/atomicity (M-CM3), web/TUI parity (M-CM4), agentic/MCP floor (M-CM6). Grounded in the actual `concierge/`/`serve.py`/`web.py` source.

**Executive summary**
- M-CM2 is **incomplete**: flipping `inputs_dir` to advisory does not unblock a WRITE-mode serve — the separate `inputs_writable` check (`serve.py:103-106`) is still blocking and fails when `inputs/` is absent, so instantiate stays unreachable.
- M-CM1's friction timestamp stamping is at the **wrong layer**: `build_friction_entry` already serializes the full JSON line (incl. `ts`) into `append_text` (`writes.py:155-162`), so `apply_concierge_plan` cannot "stamp" without re-parsing the line.
- The `ConciergeWriteCode` vocabulary (OK/WRITE_BLOCKED/WRITE_REFUSED) has **no code for `skipped`** — no-clobber instantiate of an existing file lands in `WriteResult.skipped`, which leaves `ok=True`; the user gets a flat OK while zero/some files were written.
- Multi-file instantiate is **non-atomic** (`apply_write_plan` continues past per-file blocked/errors) — a mid-loop block leaves a half-scaffolded package; the plan never states partial-apply/retry semantics.
- "Propose-only" (M-CM6) is enforced by the **absence** of an apply tool and is asserted with ~0 code and **no regression guard** — a future tool added to `build_concierge_registry`/MCP would silently widen the floor.
- `build_concierge_view` runs `build_survey` (`core.py:77 root.rglob("*")`) per `GET /concierge` with no caching — an O(repo) latency cliff on large monorepos.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Risks | high | M-CM2 must also neutralize the `inputs_writable` check, not only `inputs_dir`. In WRITE/DEMO mode `preflight` adds `Check("inputs_writable", inputs_ok and os.access(...))` with default `blocking=True` (`serve.py:103-106`); when `inputs/` is absent `inputs_ok` is False so this check fails-blocks the serve. Flipping `serve.py:97` alone leaves the package-less serve refused. | The instantiate offer (FR-CM-6) targets exactly package-less projects served in a write-capable mode; M-CM2 as written does not actually unblock it. | M-CM2 bullet "Change `serve.py:97` to make `inputs_dir` **advisory**" | Add a test: `preflight(root_without_inputs, mode=WRITE).ok is True`; assert no blocking check fails. |
| R1-S2 | Data | high | Move friction timestamp stamping out of `apply_concierge_plan` into the surface handler, mirroring the CLI: pass `timestamp=datetime.now(timezone.utc).isoformat()` **into** `build_friction_entry` (as `cli_concierge.py:233` does) **before** the JSON line is serialized. `build_friction_entry` bakes `ts` into `append_text` at build time (`writes.py:155-162`); by the time the applier sees the plan the timestamp is frozen inside an opaque string. | M-CM1 says "The applier stamps ... for the friction branch" — but the applier would have to JSON-parse and re-serialize `append_text` to do so, which the plan does not describe. Wrong layer = unstamped UI entries (the exact NR-CM-B failure). | M-CM1 bullet "**NR-CM-B:** stamp the friction timestamp here" | Unit test: a friction entry logged via the web/TUI path has a non-null ISO `ts` byte-for-byte equal to a CLI-logged entry's shape. |
| R1-S3 | Interfaces | high | Add a fourth `ConciergeWriteCode` (e.g. `SKIPPED`/`NOOP`/`PARTIAL`) and map `WriteResult.skipped`. No-clobber instantiate of a file that exists lands in `skipped` (`safe_write.py:236`), and `WriteResult.ok` ignores `skipped` (`ok = not blocked and not errors`, `safe_write.py:65-66`), so `apply_concierge_plan` returns OK while writing nothing. | OK/WRITE_BLOCKED/WRITE_REFUSED cannot distinguish "wrote 7 files" from "all 7 already existed, wrote 0". The surface then emits `kickoff_instantiated` for a no-op. | M-CM1 bullet defining the `ConciergeWriteCode` vocabulary | Test: instantiate over a project where some/all target files pre-exist → result carries a distinct code and a written/skipped count, not bare OK. |
| R1-S4 | Risks | medium | State partial-apply + retry semantics for multi-file instantiate. `apply_write_plan` collects per-file blocked/errors and **continues** (`safe_write.py:209-258`), so a mid-loop confinement/OS error leaves a half-written package and `ok=False`. Note the mitigation explicitly: ACTION_NEW no-clobber makes a **retry idempotent** (already-written files skip), so the documented recovery is "re-run instantiate". | Focus #1 asks for atomicity gaps; the jsonl append is atomic (O_APPEND single write) but the instantiate projection is not, and the plan is silent on the half-scaffolded state. | M-CM3 bullet on instantiate / new "Failure & recovery" note | Test: inject a per-file error mid-plan; assert prior files persisted, result is `PARTIAL`, and a second call completes the remainder. |
| R1-S5 | Security | medium | M-CM6 should ship a **negative regression guard**, not just a prose assertion. Add a test that enumerates the tool names exposed by `build_concierge_registry` (`concierge/chat.py`) and the MCP `startd8_concierge` path and asserts the set ⊆ {survey, assess, field_states} with **no** apply/instantiate/friction tool. "Propose-only is automatic" holds only as long as nobody adds a tool. | The read-only floor is currently protected by absence; a silent future regression (someone wires an apply tool into the loop or MCP) would pass all tests. Focus #5 asks to verify the floor cannot widen. | M-CM6 "FR-CM-8 already holds" / "FR-CM-9 already satisfied" | CI test enumerating allowed loop + MCP tool names; fails if any write-capable tool appears. |
| R1-S6 | Ops | low | Bound or memoize `build_survey` in `build_concierge_view`. It walks `root.rglob("*")` (`core.py:77`) on every `GET /concierge`; on a large monorepo this is an O(repo) per-request cost with no cache, and it runs even when the user only wants the readiness recap. | M-CM0 makes `build_concierge_view` the hot path for both surfaces; an uncached full-tree walk is a latency/soft-DoS cliff. | M-CM0 bullet defining `build_concierge_view` | Benchmark `GET /concierge` on a synthetic 50k-file tree; add a TTL/per-request memo or a bounded walk. |
| R1-S7 | Validation | medium | Define what FR-CM-10 "parity" means for **writes**, not just the view payload, and pin it in M-CM3/M-CM4. The shared `build_concierge_view` gives *view* parity, but the web write path enforces mode-gate + CSRF + rate-limit (`web.py:296-313`) while the TUI path is a bare `questionary.confirm()` with none of those. A single payload oracle does not test write-behavior equivalence. | The plan claims "parity is testable against one representation," but the most consequential difference (write authorization) is invisible to that oracle. | M-CM4 / dependency note on M-CM3 | Add a parity test matrix: same `WritePlan` → web (gated) and TUI (confirm) produce identical on-disk results; document intended gate asymmetry. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Security | low | The new `POST /concierge/instantiate` + `/concierge/friction` endpoints inherit the capture gate, which relies on a httponly+SameSite=strict CSRF token (`web.py:255-257,304-309`) but does **no Origin/Host allowlist check**. A loopback web app is exposed to DNS-rebinding; for instantiate the blast radius is low (no-clobber, pinned root) but friction lets a rebind-forged request append arbitrary jsonl lines. | Adding write endpoints is the moment to add an `Origin`/`Host == 127.0.0.1:port` check; it also hardens the pre-existing capture endpoint. | M-CM3 apply-gate bullet | Test a forged `Origin` header is rejected on the two new POSTs. |
| R1-S9 | Architecture | low | Pin that `build_concierge_view` (with its `instantiate_offer` + friction form-spec) is **not** the MCP-exposed surface — only the bare `build_survey` is (FR-CM-9). The aggregator is a tempting read-only thing to expose, and while it carries no apply, surfacing an `instantiate_offer`/form over MCP muddies the "MCP is survey-only" line. | Focus #5 — keep the MCP read floor narrow and explicit so a future MCP addition doesn't grab the aggregator. | M-CM6 FR-CM-9 note / M-CM0 | Assert the MCP tool returns `build_survey` shape, not the `concierge_view` schema. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Appendix C was empty at R1.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement ID → plan milestone(s) → coverage. Gaps flagged here correspond to the R1-S/R1-F suggestions above.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-CM-1 (named surface) | M-CM3, M-CM4 | Full | — |
| FR-CM-2 (discoverable entry) | M-CM3 (nav link), M-CM4 (`kickoff concierge`) | Full | — |
| FR-CM-3 (survey panel) | M-CM0, M-CM3, M-CM4 | Full | — |
| FR-CM-4 (assess consolidation) | M-CM0 (`ReadinessView` reuse) | Full | — |
| FR-CM-5 (log friction) | M-CM1, M-CM3, M-CM4 | Partial | Timestamp stamped at wrong layer (R1-S2/R1-F1); jsonl write-behavior parity across surfaces untested (R1-S7/R1-F4). |
| FR-CM-6 (instantiate) | M-CM2, M-CM3 | Partial | Serve-unblock incomplete — `inputs_writable` still blocks (R1-S1/R1-F3); partial multi-file apply + retry semantics unstated (R1-S4/R1-F5). |
| FR-CM-7 (one write path) | M-CM1 | Partial | `ConciergeWriteCode` lacks a `skipped`/`partial` code; no-clobber no-op reports OK (R1-S3/R1-F2). |
| FR-CM-8 (agentic boundary) | M-CM6 | Partial | Enforced by absence; no regression guard test (R1-S5). |
| FR-CM-9 (MCP read-only) | M-CM6 | Partial | Aggregator vs bare-survey MCP boundary not pinned (R1-S9/R1-F7). |
| FR-CM-10 (web/TUI parity) | M-CM0, M-CM3, M-CM4 | Partial | View parity covered; write-behavior parity undefined (R1-S7/R1-F4). |
| FR-CM-11 (observability) | M-CM3, M-CM5 | Partial | No event defined for a no-clobber no-op instantiate (R1-F6). |
| NR-CM-A (serve package-less) | M-CM2 | Partial | Only `inputs_dir` demoted; `inputs_writable` gap (R1-S1/R1-F3). |
| NR-CM-B (stamp timestamp) | M-CM1 | Partial | Layer mismatch with `build_friction_entry` serialization (R1-S2/R1-F1). |
| NR-CM-C (honest force) | M-CM3 | Full | — |
| NR-CM-D (typed reason codes) | M-CM1 | Partial | Missing `skipped`/`partial` code (R1-S3/R1-F2). |

#### Review Round R2 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 16:35:00 UTC
- **Scope**: Gap-hunting after accepted R1 safety fixes, focused on end-user value, low-effort implementation wins, operational clarity, and testable contracts across web/TUI/MCP.

**Executive summary**
- The plan says friction/instantiate are preview-then-apply, but M-CM3 only defines apply POSTs; adding explicit preview routes reuses existing builders and makes the user confirmation step testable.
- `build_concierge_view` is the new shared contract, but the plan only calls it a dict; a small typed/schema-versioned view contract would prevent web/TUI drift and make parity tests sharper.
- Package-less serve should not merely stop failing; the first-run UX should route users toward the Concierge instantiate offer instead of dropping them into an empty or confusing ordinary kickoff overview.
- Concierge telemetry needs stable attributes, not only event names, so dashboards can distinguish source, mode, no-op, partial, refused, and successful writes without leaking paths or free text.
- Form and builder errors need the same typed, friendly surface as write errors; invalid posture, missing fields, and overlong friction text should never become opaque 500s or unbounded jsonl growth.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | Add explicit Concierge preview endpoints or an equivalent two-step preview contract before apply. M-CM3 currently lists only `POST /concierge/friction` and `POST /concierge/instantiate`, then immediately builds a plan and applies it after the apply gate; it does not define the preview response shape required by FR-CM-5/6. Reuse the pure builders for `POST /concierge/friction/preview` and `POST /concierge/instantiate/preview`, returning writes, warnings, posture, bytes, and typed builder errors without mutating disk. | This is low effort because `build_friction_entry` and `build_instantiate_plan` already produce the preview `WritePlan`; it closes a user-facing trust gap and makes "preview-then-apply" testable rather than implied by UI prose. | M-CM3 bullet defining the two POST handlers | Tests: preview calls return `ok=True` + plan summary and leave disk unchanged; bad posture/missing friction field returns typed 400; apply remains CSRF/session/rate-gated. |
| R2-S2 | Architecture | medium | Replace the loose "`build_concierge_view(project_root) -> dict`" milestone with a small schema-versioned view contract, e.g. `ConciergeView` or a documented dict schema containing `schema_version`, `survey`, `readiness`, `instantiate_offer`, `friction_form`, and `next_action`. Include the posture banner copy or banner key in the payload so web and TUI cannot drift on the "assist, not operate" promise. | FR-CM-10 relies on one shared payload, but a free-form dict makes parity depend on convention. A typed or explicitly documented schema is a small change that turns the view-model into a real interface and gives tests stable keys to assert. | M-CM0 "Shared Concierge view-model" | Unit test: `build_concierge_view(...).to_dict()` or dict output contains exactly the expected required keys and `schema_version`; web and TUI render from this object without reassembling survey/readiness separately. |
| R2-S3 | Ops | medium | Add first-run routing/CTA behavior for package-less projects, not just package-less serve. When `instantiate_offer.needed` is true, the web overview should surface a prominent Concierge CTA or redirect/banner to `/concierge`, and ordinary capture/apply affordances should avoid implying the kickoff package already exists. | M-CM2 makes the app serveable without `docs/kickoff/inputs/`, but the value is only realized if the user can immediately find the scaffold action. Otherwise the app may render an empty/low-readiness overview that looks broken before the user reaches Concierge mode. | M-CM2 degrade-gracefully note and M-CM3 `GET /concierge` / overview nav bullet | Web test: a project without `docs/kickoff/inputs/` serves successfully, overview includes a "Create kickoff package" Concierge CTA, and `/concierge` shows `instantiate_offer.needed=True`. |
| R2-S4 | Ops | medium | Define the attribute contract for the new telemetry events, not only the event names. For `survey_viewed`, `kickoff_instantiated`, no-op/skipped, partial, and `concierge_write_refused`, include bounded attributes such as `source` (web or TUI), `mode`, `action`, `code`, `posture`, `with_authoring`, `written_count`, and `skipped_count`; explicitly exclude free-text friction content and raw file paths. | M-CM5 extends `FUNNEL_EVENTS`, but dashboards and tests cannot distinguish successful install vs partial vs no-op vs refusal without stable attributes. Attribute allowlisting also avoids accidentally emitting user-authored friction text or local paths into telemetry. | M-CM5 Telemetry | Test with `record_events()`: each Concierge event carries the expected bounded attributes and does not include `friction`, `what_happened`, `implication`, or per-file path values. |
| R2-S5 | Risks | medium | Add a typed validation/error layer for Concierge form inputs before plan apply. Map `ConciergeWriteError` and bad enum/input cases to stable web/TUI result codes such as `invalid_posture`, `missing_required_field`, and `input_too_large`; set conservative field length caps for the three friction text fields before serializing to jsonl. | R1 covered write-result codes after `apply_write_plan`, but builder/form errors happen before that layer. Without a typed pre-apply error surface, invalid user input can become a generic failure, and unbounded friction text can bloat the append-only log. | M-CM1 typed result wrapper and M-CM3/M-CM4 form handling | Tests: invalid posture and blank friction fields produce typed non-500 responses; overlong friction text is refused before `build_friction_entry`; no jsonl line is appended on validation failure. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 plan suggestions have already been triaged into Appendix A.

---

## Requirements Coverage Matrix — R2

Analysis only (not triage). This R2 matrix assumes accepted R1 changes remain in force and highlights remaining value/operational gaps.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-CM-1 (named surface) | M-CM0, M-CM3, M-CM4 | Partial | Named surface is covered, but the shared posture/banner contract is not pinned in the view-model (R2-S2/R2-F2). |
| FR-CM-2 (discoverable entry) | M-CM3, M-CM4 | Partial | Web nav exists, but package-less first-run CTA/routing is not specified (R2-S3/R2-F3). |
| FR-CM-3 (survey panel) | M-CM0, M-CM3, M-CM4 | Full | R1 performance bounding still applies; no new R2 gap beyond the view schema contract. |
| FR-CM-4 (assess consolidation) | M-CM0 | Full | Reuse of `ReadinessView` is covered. |
| FR-CM-5 (log friction) | M-CM1, M-CM3, M-CM4 | Partial | Preview route/contract and typed pre-apply validation are underspecified (R2-S1/R2-S5/R2-F1/R2-F5). |
| FR-CM-6 (instantiate) | M-CM2, M-CM3 | Partial | Preview route/contract and package-less first-run UX are underspecified (R2-S1/R2-S3/R2-F1/R2-F3). |
| FR-CM-7 (one write path) | M-CM1 | Partial | Write path is shared, but builder/form errors before apply need typed mapping (R2-S5/R2-F5). |
| FR-CM-8 (agentic boundary) | M-CM6 | Full | R1 regression guard covers the write-floor risk. |
| FR-CM-9 (MCP read-only) | M-CM6 | Full | R1 aggregator boundary covers the MCP exposure risk. |
| FR-CM-10 (web/TUI parity) | M-CM0, M-CM3, M-CM4 | Partial | Parity depends on a loose dict; view schema and banner/next-action keys should be contractually stable (R2-S2/R2-F2). |
| FR-CM-11 (observability) | M-CM3, M-CM5 | Partial | Event names are planned, but stable bounded attributes and privacy exclusions are missing (R2-S4/R2-F4). |
| NR-CM-A (serve package-less) | M-CM2, M-CM3 | Partial | Preflight unblock is covered by R1; first-run routing/CTA remains unspecified (R2-S3/R2-F3). |
| NR-CM-B (stamp timestamp) | M-CM1/M-CM3/M-CM4 | Full | R1 moved stamping to the surface handler. |
| NR-CM-C (honest force) | M-CM3 | Full | v1 no-force UI is covered. |
| NR-CM-D (typed reason codes) | M-CM1, M-CM5 | Partial | Apply-result codes are covered by R1; pre-apply validation codes and telemetry attributes remain underspecified (R2-S4/R2-S5/R2-F4/R2-F5). |

#### Review Round R3 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 16:50:00 UTC
- **Scope**: Late-round gap-hunting after accepted R1 and incoming R2, focused on replay safety, post-apply user feedback, persisted provenance, full-journey validation, and TUI failure modes.

**Executive summary**
- The write endpoints are human-confirmed, but the plan does not yet prevent browser resubmits, double-clicks, or repeated TUI confirms from duplicating append-only friction or over-reporting instantiate outcomes.
- After an apply, the user needs a reconciled Concierge state: stale `instantiate_offer.needed=True` or an unchanged readiness recap would make successful writes look ineffective.
- The friction jsonl itself needs minimal provenance fields so future read-back and debugging are possible without parsing telemetry or leaking local paths.
- Existing tests are mostly unit/contract-shaped; a single package-less first-run journey would catch interactions between preflight, preview, apply, state refresh, and telemetry.
- The new `kickoff concierge` command should define safe behavior when it runs in a non-interactive terminal or when `questionary.confirm().ask()` returns `None`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Security | medium | Add a one-time apply-intent or idempotency token for Concierge writes. M-CM3 defines `POST /concierge/friction` and `POST /concierge/instantiate` behind the capture apply gate, and M-CM4 uses `questionary.confirm().ask()`, but neither milestone says what happens when a user double-clicks, refresh-resubmits, or repeats the same confirm. Store a short-lived intent id in the preview/session and consume it on apply; repeated use should return a typed no-op/refused outcome without a second append or duplicate install event. | This is distinct from CSRF and validation: CSRF proves the request came from the page, not that it is the same human-confirmed write only once. Friction is append-only, so replay creates permanent duplicates; instantiate is no-clobber but still risks confusing skipped/no-op telemetry. | M-CM3 apply-gate bullet and M-CM4 TUI confirm bullet | Tests: submit the same preview/apply token twice; first write succeeds, second returns a stable typed outcome, disk and event counts remain unchanged after the second call. |
| R3-S2 | Ops | medium | Add post-apply reconciliation to the web and TUI surfaces. After `kickoff_instantiated`, rebuild `build_concierge_view(root)` and return/render the updated `instantiate_offer`, readiness recap, and next action; after `friction_logged`, return a bounded confirmation that the line was appended without exposing raw local paths or free text. | M-CM0 makes the shared view the source of truth, but M-CM3 currently stops at emitting events. Without an explicit refresh, the page can keep showing "create kickoff package" after creation or leave users unsure whether friction was saved. | M-CM3 `POST /concierge/friction` and `POST /concierge/instantiate`; M-CM4 command result handling | End-to-end test: package-less root shows `instantiate_offer.needed=True`; after apply, response or next render shows `needed=False` and an updated next action; friction apply returns success metadata while omitting raw path and submitted text. |
| R3-S3 | Data | low | Add minimal persisted provenance to friction jsonl entries: `schema_version`, `source` (`web` or `tui`), and a stable `mode` or posture context when available. Keep the user-authored fields unchanged and do not add local paths. | R2 covers telemetry attributes, but the append-only artifact is also the durable source that OQ-5 may later read back. If entries only contain the three free-text fields plus `ts`, future bounded read-back cannot distinguish web vs TUI reports or migrate old/new records cleanly. | M-CM1 NR-CM-B friction timestamp note and M-CM3/M-CM4 friction handling | Unit test: web and TUI friction entries include the same schema version and source field, preserve existing required fields, and contain no raw filesystem paths. |
| R3-S4 | Validation | high | Add one full package-less first-run journey test that exercises the feature as a user would: serve root with no `docs/kickoff/inputs/`, open overview, enter Concierge, preview instantiate, apply instantiate, refresh state, then log friction. Run the core journey for web and at least the same write-plan/apply sequence for TUI. | R1 and R2 add valuable focused tests, but the highest-risk failures are interactions between M-CM2, M-CM0, M-CM3, M-CM4, M-CM5, and M-CM6. A journey test is a low-hanging integration guard because all pieces are deterministic and local. | Dependency order section or a new validation note after M-CM6 | Test fixture: temporary package-less root; asserts HTTP 200, preview no-write, apply write counts, refreshed `instantiate_offer`, friction append, expected telemetry attributes, and no MCP write tool exposure. |
| R3-S5 | Risks | medium | Define safe non-interactive behavior for `kickoff concierge`. M-CM4 assumes `questionary.confirm().ask()` returns a clear human decision, but in a non-TTY, interrupted prompt, or unsupported terminal it can return `None` or fail. Treat that as `WRITE_REFUSED` or a dedicated `confirm_unavailable` result and do not apply; do not add a hidden `--yes` shortcut in v1 because the requirement is explicit foreground human confirmation. | The TUI command is a new write host. Its safest default must be specified before implementation, otherwise an edge terminal state can become either an opaque traceback or an accidental unattended writer. | M-CM4 TUI Concierge host command | Tests: monkeypatch confirm to return `False`, `None`, and raise; all paths leave disk unchanged and return a typed, user-friendly refusal. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1: Explicit preview endpoints are the right foundation for the R3-S1 idempotency token and make preview-before-apply observable.
- R2-S2: A stable view contract is necessary for post-apply reconciliation and avoids stale, surface-specific next-action logic.
- R2-S3: Package-less first-run CTA is the user-facing half of the serve unblock and should be paired with the R3 journey test.
- R2-S4: Telemetry attributes are needed to distinguish success, no-op, partial, replay refusal, and validation refusal without leaking text.
- R2-S5: Typed pre-apply validation is the correct boundary for bad form inputs before the safe-writer ever sees a plan.

**Disagreements**: none.

---

## Requirements Coverage Matrix — R3

Analysis only (not triage). This R3 matrix assumes accepted R1 changes and incoming R2 suggestions remain in scope; it highlights second-order gaps that remain after preview/schema/telemetry/form-validation coverage.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-CM-1 (named surface) | M-CM0, M-CM3, M-CM4 | Partial | Named surface remains covered, but post-apply state should refresh so the Concierge surface reflects completed actions (R3-S2/R3-F2). |
| FR-CM-2 (discoverable entry) | M-CM3, M-CM4 | Partial | R2 covers first-run CTA; R3 adds full journey validation to prove discoverability flows into a completed action (R3-S4/R3-F3). |
| FR-CM-3 (survey panel) | M-CM0, M-CM3, M-CM4 | Full | Existing R1/R2 coverage is sufficient for this round. |
| FR-CM-4 (assess consolidation) | M-CM0 | Partial | Reuse is covered, but post-apply reconciliation should refresh readiness instead of leaving stale assess data on screen (R3-S2/R3-F2). |
| FR-CM-5 (log friction) | M-CM1, M-CM3, M-CM4 | Partial | Needs replay/idempotency protection, persisted provenance, post-apply confirmation, and non-interactive TUI refusal semantics (R3-S1/R3-S2/R3-S3/R3-S5). |
| FR-CM-6 (instantiate) | M-CM2, M-CM3 | Partial | Needs replay/idempotency protection, post-apply state refresh, full first-run journey coverage, and non-interactive TUI refusal semantics (R3-S1/R3-S2/R3-S4/R3-S5). |
| FR-CM-7 (one write path) | M-CM1 | Partial | Shared apply is covered, but repeated confirmed writes should be consumed once across surfaces (R3-S1/R3-F1). |
| FR-CM-8 (agentic boundary) | M-CM6 | Full | R1 regression guard covers this; no new R3 gap. |
| FR-CM-9 (MCP read-only) | M-CM6 | Full | R1 aggregator boundary covers this; R3 journey test should include the existing guard but does not add a new requirement gap. |
| FR-CM-10 (web/TUI parity) | M-CM0, M-CM3, M-CM4 | Partial | R2 covers schema parity; R3 adds parity for post-apply reconciliation, replay handling, and non-interactive TUI refusal semantics (R3-S1/R3-S2/R3-S5). |
| FR-CM-11 (observability) | M-CM3, M-CM5 | Partial | R2 covers attributes; R3 adds replay/no-op event count correctness and journey-level telemetry verification (R3-S1/R3-S4). |
| NR-CM-A (serve package-less) | M-CM2, M-CM3 | Partial | R1/R2 cover unblock and CTA; R3 adds end-to-end proof that package-less serve leads to successful instantiate and refreshed state (R3-S4/R3-F3). |
| NR-CM-B (stamp timestamp) | M-CM1/M-CM3/M-CM4 | Partial | Timestamp layer is covered by R1; persisted friction provenance should include schema/source alongside `ts` (R3-S3/R3-F4). |
| NR-CM-C (honest force) | M-CM3 | Full | v1 no-force UI remains covered. |
| NR-CM-D (typed reason codes) | M-CM1, M-CM5 | Partial | R1/R2 cover apply and validation codes; R3 adds replay/idempotency and confirm-unavailable outcomes (R3-S1/R3-S5/R3-F1/R3-F5). |

#### Review Round R4 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 17:05:00 UTC
- **Scope**: Late-round operational review after accepted R1 and incoming R2/R3, focused on rollout sequencing, reusable test data, recovery UX, result-envelope maintainability, and first-run operator ergonomics.

**Executive summary**
- The plan has strong component-level fixes, but it does not yet say which CI gates must be green before write-capable routes can ship.
- The same package-less and partial-root fixtures can validate preflight, preview, apply, telemetry, and MCP boundaries if the plan names them once.
- Partial instantiate recovery is technically retryable, but the user-facing recovery path is still underspecified.
- Typed result codes are emerging across R1-R3; a shared result envelope and presenter would prevent web/TUI copy and retry semantics from drifting.
- Package-less serve and symlink-root blocks need operator-facing guidance at startup, not only typed JSON after a failed write.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Ops | high | Add explicit rollout and CI sequencing gates before M-CM3 write-capable routes are considered done. In the "Dependency order" section, require M-CM1 typed outcomes, M-CM2 package-less WRITE preflight, R2 preview no-write tests, R2 telemetry privacy checks, and M-CM6 MCP/loop negative guards to pass before enabling `POST /concierge/friction` or `POST /concierge/instantiate` in a release branch. | The milestones list dependencies, but not release gates. A feature can be implemented in dependency order and still merge write endpoints before the guard tests or telemetry privacy assertions exist. | `## Dependency order` and M-CM3 acceptance notes | CI job or checklist fails if write-route tests run without preview no-write, package-less preflight, no-MCP-write, and telemetry privacy assertions. |
| R4-S2 | Validation | medium | Define one shared Concierge fixture pack instead of one-off tests: a package-less root, a partially scaffolded root, a fully existing package, a symlinked/confined root, and invalid friction/posture payloads. Reuse it across M-CM1, M-CM2, M-CM3, M-CM4, M-CM5, and M-CM6 tests, with golden `WritePlan` summaries for instantiate and friction preview. | R2/R3 add many focused tests. Without shared fixtures, the test suite will duplicate setup and subtly diverge, especially around package-less roots and partial retry cases. This is low effort because all scenarios are local deterministic filesystem states. | New validation note after M-CM6 or under `## Dependency order` | Test helper exposes the fixture pack; web, TUI, applier, preflight, telemetry, and MCP-boundary tests import it and assert against the same golden plan summaries. |
| R4-S3 | Risks | medium | Add user-facing partial-recovery UX for instantiate, not just the technical retry rule. When an instantiate result is `partial` or has skipped/written counts, the web/TUI response should summarize written, skipped, failed, and remaining files, then offer a safe "retry instantiate" next action that reuses the same no-clobber semantics. | R1 established that retry is idempotent and R3 covers post-apply reconciliation, but neither tells the user how to recover from a half-scaffolded package. Without visible remaining work, users may assume the project is corrupted or manually edit around it. | M-CM3 "Failure & recovery" note and M-CM4 command result handling | Inject a mid-plan failure; assert the response includes counts, failed filenames or bounded labels, and a retry CTA; a second run completes remaining writes and clears the recovery state. |
| R4-S4 | Interfaces | medium | Introduce a shared Concierge result envelope consumed by both web and TUI, e.g. `code`, `message_key`, `severity`, `retryable`, `written_count`, `skipped_count`, `remaining_count`, and optional refreshed view payload. Keep user-facing copy in one presenter map instead of formatting errors independently in route handlers and the Typer command. | R1-R3 add typed apply, validation, replay, and confirm-unavailable outcomes. If each surface maps those codes separately, parity and recovery copy will drift even if the disk writes remain equivalent. | M-CM1 typed result wrapper plus M-CM3/M-CM4 response handling | Unit test enumerates every `ConciergeWriteCode` and validation/replay code and asserts both web JSON and TUI rendering use the shared message key and retryability metadata. |
| R4-S5 | Ops | low | Add startup/help guidance for the two most common first-run operator states: package-less serve and symlink-confined roots. When M-CM2 allows serving without `docs/kickoff/inputs/`, startup output should point to `/concierge` as the next step; when writes are blocked by confinement, the surfaced hint should include the bounded `STARTD8_CONCIERGE_ALLOWED_ROOTS` remediation without exposing raw path lists in telemetry. | The plan handles the technical states, but operators will first encounter them in terminal output and local-web guidance. Clear next steps reduce "served but empty" confusion and make the symlink workaround discoverable in the `/tmp` to `/private/tmp` dev environment. | M-CM2 serve-package-less note and M-CM1 `WRITE_BLOCKED` handling | CLI/web smoke test captures startup or error output for package-less and symlink roots; output names `/concierge` or the env-var hint, while telemetry remains path-free. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1: Explicit preview endpoints are the cleanest place to attach R4 rollout gates and golden no-write fixtures.
- R2-S4: Stable telemetry attributes should be accepted before operational dashboards or CI assertions depend on these events.
- R3-S1: One-time apply intent is necessary for append-only friction and should be part of the write-route release gate.
- R3-S4: The first-run journey test is the right end-to-end guard; R4-S2 makes its fixtures reusable across lower-level tests.
- R3-S5: Non-interactive TUI fail-closed behavior is essential to preserve the human-confirmation model.

**Disagreements**: none.

---

## Requirements Coverage Matrix — R4

Analysis only (not triage). This R4 matrix assumes accepted R1 changes and incoming R2/R3 suggestions remain in scope; it highlights rollout, maintenance, and operational ergonomics gaps that remain after preview/schema/telemetry/form-validation/replay coverage.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-CM-1 (named surface) | M-CM0, M-CM3, M-CM4 | Partial | Named surface is covered, but recovery and success messaging should come from one result presenter so web/TUI do not drift (R4-S4/R4-F3). |
| FR-CM-2 (discoverable entry) | M-CM3, M-CM4 | Partial | R2 covers first-run CTA; startup/help guidance for package-less serve and symlink-confined roots remains underspecified (R4-S5/R4-F5). |
| FR-CM-3 (survey panel) | M-CM0, M-CM3, M-CM4 | Full | Existing R1/R2 coverage is sufficient for this round. |
| FR-CM-4 (assess consolidation) | M-CM0 | Full | Existing R1/R3 coverage is sufficient for this round. |
| FR-CM-5 (log friction) | M-CM1, M-CM3, M-CM4 | Partial | Needs rollout gates, shared fixtures, shared result-envelope copy, and mode availability semantics for preview/apply behavior (R4-S1/R4-S2/R4-S4/R4-F1/R4-F2/R4-F4). |
| FR-CM-6 (instantiate) | M-CM2, M-CM3 | Partial | Needs rollout gates, reusable partial-root fixtures, and user-facing partial-recovery UX beyond the technical retry rule (R4-S1/R4-S2/R4-S3/R4-F1/R4-F2/R4-F3). |
| FR-CM-7 (one write path) | M-CM1 | Partial | Shared apply path is covered, but result-to-message mapping and retryability metadata should also be shared across surfaces (R4-S4/R4-F3). |
| FR-CM-8 (agentic boundary) | M-CM6 | Partial | R1 covers the regression guard; rollout sequencing should require it before write-capable routes are released (R4-S1/R4-F1). |
| FR-CM-9 (MCP read-only) | M-CM6 | Partial | R1 covers the aggregator boundary; shared fixtures should keep MCP no-write assertions aligned with web/TUI write fixtures (R4-S2/R4-F2). |
| FR-CM-10 (web/TUI parity) | M-CM0, M-CM3, M-CM4 | Partial | R2/R3 cover view and write behavior; shared result-envelope rendering and mode availability matrix remain gaps (R4-S4/R4-F4). |
| FR-CM-11 (observability) | M-CM3, M-CM5 | Partial | R2/R3 cover attributes and event-count correctness; release gates should require privacy assertions before shipping write endpoints (R4-S1/R4-F1). |
| NR-CM-A (serve package-less) | M-CM2, M-CM3 | Partial | Package-less preflight and CTA are covered by R1/R2; startup/operator guidance remains underspecified (R4-S5/R4-F5). |
| NR-CM-B (stamp timestamp) | M-CM1/M-CM3/M-CM4 | Partial | Timestamp and provenance are covered by R1/R3; shared fixture assertions should keep web/TUI jsonl shape identical (R4-S2/R4-F2). |
| NR-CM-C (honest force) | M-CM3 | Full | v1 no-force UI remains covered. |
| NR-CM-D (typed reason codes) | M-CM1, M-CM5 | Partial | Typed codes are covered across R1-R3, but shared user-facing message keys, retryability metadata, and mode-specific refusal semantics remain underspecified (R4-S4/R4-F3/R4-F4). |

#### Review Round R5 — gpt-5.5 — 2026-06-26

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-26 17:20:00 UTC
- **Scope**: Late-stage convergence pass after accepted R1 and incoming R2/R3/R4, focused on cold-start recovery after partial writes, UI-redress hardening for human-confirmed writes, and preview/apply intent lifecycle maintenance.

**Executive summary**
- The remaining highest-value gap is restart-safe recovery: `instantiate_offer.needed` is currently a boolean keyed only to `inputs/`, so a partially scaffolded package can disappear from the Concierge path after a server restart.
- The local web write flow has CSRF, Origin/Host, rate limits, and human confirmation, but still needs an explicit anti-clickjacking/UI-redress guard so "human privilege" means an intentional click on the local page.
- R3's one-time apply intent should be scoped, digested, expiring, and garbage-collected; otherwise abandoned previews become a session-store maintenance hazard and stale applies are harder to reason about.
- R2-R4 have strong untriaged items. This round endorses the ones that should be accepted before or alongside R5 rather than restating them.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Risks | high | Replace the boolean `instantiate_offer.needed` in M-CM0 with a restart-safe package-state contract such as `missing`, `partial`, `complete`, and `blocked`, derived from the same instantiate plan/checklist used by recovery tests. M-CM0 currently defines `instantiate_offer` as `{"needed": not (root/"docs/kickoff/inputs").is_dir(), ...}`; that misses a cold-start partial package where `inputs/` exists but other generated files are absent after an interrupted or previous failed instantiate. | R4-S3 covers result-time partial recovery, but after a process restart the UI must rediscover incomplete scaffold state without relying on an in-memory partial result. This is a low-effort extension because R4-S2 already proposes a partially scaffolded fixture and R1/R4 already require written/skipped/remaining counts. | M-CM0 `instantiate_offer` bullet and M-CM3 "Failure & recovery" note | Test a partially scaffolded root with `docs/kickoff/inputs/` present but other planned files missing; `build_concierge_view` reports `package_state=partial`, exposes a retry/recovery next action, and the retry completes remaining ACTION_NEW files without overwriting existing ones. |
| R5-S2 | Security | medium | Add explicit frame-busting / UI-redress protection for the Concierge web pages and write confirmations. M-CM3 hardens POSTs via the capture gate plus R1-S8 Origin/Host checks, but the local web app should also emit `Content-Security-Policy: frame-ancestors 'none'` or `X-Frame-Options: DENY` on `/concierge` and write-confirmation responses so a malicious page cannot frame the local UI and trick a foreground user into confirming a write. | The design's safety claim depends on explicit human confirmation. CSRF and Origin/Host checks do not fully address clickjacking, where the request originates from the real local page but the user's click is visually manipulated. | M-CM3 `GET /concierge` and POST confirmation/response handling | Browser/header test asserts `/concierge`, preview, and apply responses include a frame-deny policy; manual or automated clickjacking harness cannot frame the Concierge confirmation UI. |
| R5-S3 | Ops | medium | Specify lifecycle rules for the R3 one-time apply intent: bind each intent to `project_root`, action, mode/source, posture, and a digest of the previewed `WritePlan`; expire abandoned intents with the existing session TTL; consume atomically on apply; and scrub expired intent records from `_SessionStore` without retaining free-text friction content. | R3-S1 establishes replay protection, but without scope/digest/expiry rules an abandoned preview can become stale session state, and an apply can be harder to prove is the exact plan the user previewed. Binding to a digest also gives R2/R3 telemetry a safe correlation key without local paths or free text. | M-CM3 apply-gate/session handling and M-CM4 TUI confirm handling | Tests: stale intent returns a typed expiry result and writes nothing; intent for another root/action/posture is refused; mutated preview digest is refused; session cleanup removes abandoned intents while preserving no friction free text in memory or telemetry. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1: Explicit preview endpoints are the prerequisite for R5-S3's digest-bound apply intent and should be accepted first.
- R2-S2: A typed shared view contract is needed before `package_state=partial` can be rendered consistently across web and TUI.
- R2-S4: Stable telemetry attributes provide the safe place to carry a digest/correlation key without leaking paths or friction text.
- R3-S1: One-time apply intent remains the right replay primitive; R5-S3 only tightens its lifecycle and scope.
- R3-S2: Post-apply reconciliation pairs directly with R5-S1 so the surface reflects partial, complete, and retryable states.
- R3-S4: The package-less first-run journey should include the R5 partial cold-start and frame-deny assertions.
- R4-S2: The shared fixture pack is the best home for the partially scaffolded root and clickjacking/header tests.
- R4-S3: User-facing partial recovery is still necessary; R5-S1 makes that recovery rediscoverable after restart.
- R4-S4: A shared result envelope should carry the typed expiry, stale-intent, and partial-package recovery messages.

**Disagreements**: none.

---

## Requirements Coverage Matrix — R5

Analysis only (not triage). This R5 matrix assumes accepted R1 changes and incoming R2/R3/R4 suggestions remain in scope; it highlights the remaining cold-start, UI-redress, and intent-lifecycle gaps surfaced by this round.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-CM-1 (named surface) | M-CM0, M-CM3, M-CM4 | Partial | Named surface is covered, but the shared Concierge state should expose `missing`/`partial`/`complete` package state so recovery survives refresh and restart (R5-S1/R5-F1). |
| FR-CM-2 (discoverable entry) | M-CM3, M-CM4 | Partial | R2/R4 cover first-run CTA and guidance; partial-package rediscovery should also route users back to Concierge recovery when the server starts on an incomplete package (R5-S1/R5-F1). |
| FR-CM-3 (survey panel) | M-CM0, M-CM3, M-CM4 | Full | Existing R1/R2 coverage remains sufficient for this round. |
| FR-CM-4 (assess consolidation) | M-CM0 | Full | Existing R1/R3 coverage remains sufficient for this round. |
| FR-CM-5 (log friction) | M-CM1, M-CM3, M-CM4 | Partial | Needs UI-redress protection for human-confirmed web writes and scoped/expiring preview-apply intents for replay-safe friction append (R5-S2/R5-S3/R5-F2/R5-F3). |
| FR-CM-6 (instantiate) | M-CM0, M-CM2, M-CM3 | Partial | Needs restart-safe partial-package detection, clickjacking protection around web confirmation, and digest-bound preview/apply intents (R5-S1/R5-S2/R5-S3/R5-F1/R5-F2/R5-F3). |
| FR-CM-7 (one write path) | M-CM1 | Partial | Shared apply is covered; stale or mismatched preview/apply intents should be refused before reaching the shared writer (R5-S3/R5-F3). |
| FR-CM-8 (agentic boundary) | M-CM6 | Full | R1/R4 guard and release-gate coverage remain sufficient for this round. |
| FR-CM-9 (MCP read-only) | M-CM6 | Full | R1 aggregator boundary remains sufficient for this round. |
| FR-CM-10 (web/TUI parity) | M-CM0, M-CM3, M-CM4 | Partial | View/result parity should include package-state recovery and stale-intent messages; web-only frame-deny is an intentional local-browser hardening, not a TUI parity requirement (R5-S1/R5-S3/R5-F1/R5-F3). |
| FR-CM-11 (observability) | M-CM3, M-CM5 | Partial | R2/R3 cover attributes and event counts; R5 adds safe correlation via preview-plan digest and typed stale/expired intent outcomes (R5-S3/R5-F3). |
| NR-CM-A (serve package-less) | M-CM2, M-CM3 | Partial | Package-less serve is covered by R1/R2/R4; partially scaffolded package detection after restart remains underspecified (R5-S1/R5-F1). |
| NR-CM-B (stamp timestamp) | M-CM1/M-CM3/M-CM4 | Partial | Timestamp/provenance are covered by R1/R3; intent cleanup should not retain free-text friction content in session state (R5-S3/R5-F3). |
| NR-CM-C (honest force) | M-CM3 | Full | v1 no-force UI remains covered. |
| NR-CM-D (typed reason codes) | M-CM1, M-CM5 | Partial | Typed write/validation/result codes are covered across R1-R4; add stale-intent, expired-intent, and partial-package recovery states if R5 is accepted (R5-S1/R5-S3/R5-F1/R5-F3). |
