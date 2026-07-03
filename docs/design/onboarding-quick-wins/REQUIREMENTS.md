# Onboarding Quick-Wins (Top 3) — Requirements

**Version:** 1.0
**Date:** 2026-07-03
**Status:** Implementing (`feat/onboarding-quick-wins`)
**Tracks:** [`SUGGESTIONS.md`](./SUGGESTIONS.md) · builds on `docs/design/project-init/` (PR #85) and
`docs/design/vipp/`.

> Three independently-valuable, low-risk improvements to the onboarding surface, each verified against
> the code. Two carry a **scope correction** discovered while writing these requirements (marked ⚠) —
> the reason requirements come before code.

---

## FR-QW-1 — `vipp negotiate` treats a missing inbox as a clean exit 0 when opted in (OQ-8)

**Problem.** `project init` establishes the VIPP posting and leaves the project **inbox-*ready*** with
no `proposals-inbox.json` (the normal, healthy state). But `cli_vipp.py:110` exits **2** ("no
proposals-inbox.json") on a missing inbox — so the exact next step init prints (`startd8 vipp
negotiate`) **errors on a freshly-init'd project**.

**Requirement.** `vipp negotiate` distinguishes two missing-inbox cases:
- **Opted in** (a `.startd8/vipp/` posting exists, per `vipp_seam.vipp_opted_in`) but **no inbox** →
  **exit 0** with an informative message ("inbox-ready; no proposals to negotiate yet — a producer
  must serialize proposals first, e.g. `startd8 project init --proposals`, or the host").
- **Not opted in** (no posting) → **exit 2** as today, guiding the user to `startd8 project init`
  (or `vipp init`) first. This preserves the genuine mis-use signal.

**Non-goal.** No change to the negotiate logic itself, or to any other exit-2 path (unreadable /
malformed / future-protocol inbox stay exit 2).

**Acceptance.**
- Opted-in project, no inbox → `negotiate` exits 0, message mentions "inbox-ready".
- Bare dir (no posting), no inbox → `negotiate` exits 2, message points at `project init`.
- The existing `test_negotiate_without_inbox_exits_2` is updated to the opted-in exit-0 behavior; a
  new test covers the not-opted-in exit-2 case.

---

## FR-QW-2 — Capability-index derived artifact sync (agent card)

**Problem.** `startd8.project.init` is a capability in `startd8.sdk.capabilities.yaml` (v1.14.0) but is
**absent from `docs/capability-index/agent-card.json`**, so an A2A/agent consumer reading the card
cannot discover it.

⚠ **Scope correction.** The original suggestion said "regenerate the derived artifacts" including
`mcp-tools.json`. But `mcp-tools.json` lists only capabilities exposed as **MCP tools**, and
`project.init` is **CLI-only** (no MCP tool — consistent with the Concierge design where only the
read-only survey/assess are exposed as tools). Therefore `project.init` belongs in **`agent-card.json`
only**, and must **not** be added to `mcp-tools.json`.

**Requirement.** Add a `project.init` **skill** entry to `agent-card.json` matching the existing skill
shape (`id`, `name`, `description`, `tags`, `inputModes`, `outputModes`). Leave `mcp-tools.json`
unchanged.

**Non-goal.** No new MCP tool. No auto-generator (these artifacts are hand-maintained; no generator
script exists).

**Acceptance.**
- `agent-card.json` contains a skill with `id: startd8.project.init`.
- `mcp-tools.json` is byte-unchanged.
- Both files remain valid JSON; skill count reflects the addition.

---

## FR-QW-3 — Harden `vipp.context.ensure_posting` confinement (VIPP only)

**Problem.** `vipp.context.ensure_posting` / `fde.context.ensure_posting` have no confinement guard —
they `mkdir` + atomic-write through a symlinked project root before any check. `project init` guards
up front, but other VIPP callers (`vipp init`, `vipp negotiate` via `assistant`) still have the hole.

**Requirement.** `vipp.context.ensure_posting` validates the project root via
`concierge.safe_write.resolve_confined_root` **before** creating `.startd8/vipp/` or writing the
context bundle. A symlinked / escaping / non-directory root raises `SafeWriteError` (surfaced by CLIs
as the existing "blocked" exit 3).

⚠ **Scope correction — VIPP only, FDE explicitly excluded.** Verified: VIPP's write path
(`vipp_seam`) **already** rejects symlinked roots (4 `resolve_confined_root` call sites) and VIPP tests
already `realpath` their tmp dirs — so this change is *consistent* and low-blast-radius. **FDE has no
confined-write system anywhere** and its tests use raw (symlinked) tmp paths; guarding
`fde.context.ensure_posting` would be inconsistent with FDE's design **and** break its tests. Adding
confinement to FDE is a separate, larger design and is **out of scope** here.

**Design notes.**
- Import direction is safe: `concierge.safe_write` imports neither `vipp` nor `fde` (no cycle).
- `resolve_confined_root` requires the root to **exist** and returns its realpath; `ensure_posting`
  already assumes an existing project root, so this only *adds* rejection of symlinked/escaping roots.
- Use the returned real path for the subsequent writes (normalize + confine in one step).

**Acceptance.**
- `vipp.context.ensure_posting` on a symlinked root raises `SafeWriteError`; no `.startd8/` is created
  in the symlink target.
- `vipp.context.ensure_posting` on a normal (non-symlinked) root is unchanged (idempotent restamp).
- Full `vipp` + `kickoff_experience` + `project` suites pass; **`fde` suite untouched and green**.

---

## Cross-cutting

- **Branch-first**, `feat/onboarding-quick-wins` off `origin/main`.
- Deterministic / `$0` — no LLM, no network.
- Each FR ships with tests; no regressions across the affected suites.
