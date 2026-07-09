# Agentic Workbook — Kickoff Dashboard × Agentic Capabilities Requirements

**Version:** 0.5 (User decisions on OQ-2/OQ-3 + FR-6b Loki depth)
**Date:** 2026-07-09
**Status:** IMPLEMENTED (FR-1–FR-10 + FR-6b; FR-11 live-chat deferred) — live-verified on Grafana 13.1.0
**Owner doc for:** surfacing the kickoff agentic layer in the Grafana Workbook
**Relates to (does not restate):** `GRAFANA_KICKOFF_PORTAL_REQUIREMENTS.md` (portal), `WORKBOOK_AUDIENCE_PERSONALIZATION_REQUIREMENTS.md` (audience lens), `../dynamic-dashboards/DYNAMIC_DASHBOARDS_REQUIREMENTS.md` (v2 foundation), `../kickoff/AGENTIC_CONCIERGE_MODE_REQUIREMENTS.md` + `../agentic-loop/AGENTIC_LOOP_REQUIREMENTS.md` (the agent), `../kickoff/INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (web/TUI surfaces)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between the v0.1 mental draft and this v0.2 after a planning pass over the three
> subsystems (agentic kickoff capabilities, the Workbook builders, the ContextCore chat panel).
> The planning pass **materially reshaped** the requirements — five corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| We need new persistence for a "pending proposals" surface — the `ProposalBuffer` is in-memory and discarded on session end (`proposals.py:114`, `_MAX=32`). | A **durable serialized proposal store already exists**: `vipp_seam.py` writes `.startd8/vipp/proposals-inbox.json` (`ProposalEnvelope`, shape-pinned to `ProposedAction`), and **`portal_build.py:117` already reads it** to render pipeline dispositions. | **FR-2 reuses the existing inbox** — no new proposal store (Mottainai / NR-3). The gap is only *wiring the chat's `propose_action` into that inbox*, not inventing persistence. |
| A read-only "mirror" of the agent needs the ContextCore chat panel (a custom plugin) embedded. | The read-only mirror is **pure display** — transcript (markdown) + proposal table. Native v2 `text`/`table` panels cover it with **zero plugin dependency and no live endpoint**. | **FR-5–FR-8 use native v2 panels.** The CC panel shell is needed **only for live chat** → moved to the deferred, gated FR-11. |
| `build_workbook_v2` is greenfield / must be written. | It **already exists** (`portal_spec_v2.py:135`): a `RowsLayout` board, audience-conditional, with per-domain shielded-field subsections and a `-v2` UID (`workbook_v2_uid`). `build_sectioned_v2` + `Section` + Tabs constructs are shipped (M0–M5). | **FR-5 extends** `build_workbook_v2` into a `TabsLayout` cockpit; it does not rebuild. The existing rows become the **Status** tab. |
| The `AgenticSession` transcript is already persisted somewhere. | `AgenticSession` (`agents/agentic.py:368`) has **no `save`/`to_dict`/serialize** — transcript + cost live only in memory for the session. | **FR-1 is the genuine new capability**: persist a session snapshot (transcript + cost + proposals ref) to a durable, dashboard-consumable artifact. This is the "agentic capabilities themselves need an update" the request anticipated. |
| Embedding a chat panel is mainly a UI task. | A chat panel **requires a live backend endpoint**; the kickoff-portal plan **deliberately deferred** that (OQ-8 / M4: "bake + re-provision, no endpoint, no `0.0.0.0` LAN exposure"). The CC panel is also a *thin stateless proxy* — no tools, no propose/confirm gate — so as-is it would surface a **weaker, different agent** than startd8's. | The **live-endpoint/exposure decision is the true gate**, not the panel choice. Live chat (FR-11) is an explicit later milestone; reuse of the CC panel is **shell-only, backend-rewired** (NR-5 rejects as-is reuse). |

**Resolved open questions (from v0.1):**
- **OQ-A → Resolved.** "New store for proposals?" → No; reuse `.startd8/vipp/proposals-inbox.json` (already produced + consumed).
- **OQ-B → Resolved.** "Custom plugin for the mirror?" → No; native v2 panels. Custom plugin only for live chat (deferred).
- **OQ-C → Resolved.** "Cross the live-endpoint line now?" → No (user decision: read-only mirror first).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK/knowledge-management lessons before CRP. Each changed or confirmed the draft:

- **[Reuse-first audit — KM Leg 3 #34]** — "before 'add capability X', grep for the fragmented thing that already exists." The audit found the proposal store (`vipp_seam.py` inbox), the v2 builder (`build_workbook_v2`), and the Section/Tabs constructs all **already exist** → 4 of 5 v0.1 assumptions became *reuse*, not *build* (see §0 table). This is the single biggest change to the draft; it reframed "build an agentic dashboard" as "wire existing machinery into one read-model + wrap it in tabs."
- **[Verify-against-source / phantom-reference audit — KM Leg 7 #48]** — every code symbol this doc names was grepped for existence: `portal_spec.py`, `portal_spec_v2.py:build_workbook_v2`, `state.py`, `proposals.py:ProposalBuffer`, `chat.py:cost_line`, `vipp_seam.py`, `dashboard_creator/v2/sectioned.py:{build_sectioned_v2,Section}`, `provision_v2`, `workbook_v2_uid`. One phantom corrected: the v2 Workbook builder lives at `kickoff_experience/portal_spec_v2.py`, **not** `dashboard_creator/v2/portal_spec_v2.py`. One claim left as an explicit **OQ-4** rather than asserted: whether `make_propose_handler` already writes the inbox (not yet verified against source).
- **[Single-source vocabulary ownership — Design_Docs #5]** — this doc is declared the **owner** of the agentic-cockpit surface only; the header's *Relates to* list **cites** the portal/audience/dynamic-dashboards/agentic-loop docs by name and does **not** restate their vocabularies (audience variable semantics, byte-identity AC, propose→confirm posture) — it references them. No controlled vocabulary is duplicated here.
- **[Prune phantom scope]** — checked FR-11 (live chat): it is architecturally a *different provenance/exposure tier* (needs a live endpoint the portal deliberately deferred), so it is **fenced as a deferred, gated track** (Group C + NR-1/NR-5), not folded into the v1 milestone set.

**CRP steering (carried to the focus file, not the body):** both docs are **brand-new (zero prior review)** → the CRP target is the pair itself. Settled / do-not-relitigate: read-only-mirror-first (user decision), reuse-shell-rewire-backend for FR-11 (user decision), no-new-store (NR-3), classic-untouched (NR-4).

---

## 1. Problem Statement

The kickoff Workbook and the kickoff **agentic** stack were built in parallel but never joined:

| Component | Current State | Gap |
|-----------|--------------|-----|
| **Workbook** (`portal_spec.py`, `portal_spec_v2.py`) | Static, read-only, `$0`-generated board: markdown field tables + baked gauge/stat. Audience-personalized v2 variant exists (`build_workbook_v2`). | Shows only **extraction state**. The agent's *activity* (chat, proposals, cost) has no visual home. |
| **Agentic concierge** (`chat.py`, `agents/agentic.py`) | Real LLM loop with `survey`/`assess` tools; **propose → human-confirm → apply**; cost-transparent. | Session state is **ephemeral** (in-memory transcript; `ProposalBuffer` discarded). Nothing survives to render. |
| **Proposal architecture** (`proposals.py`, `vipp_seam.py`) | Typed `ProposedAction`s serialized to the VIPP inbox; VIPP adjudicates. | The **propose→confirm loop has no UI** — a human confirms blind from the CLI with no at-a-glance queue. |

**What should exist:** the Workbook becomes an **agentic cockpit** — a v2 dynamic board with **Status / Assistant / Proposals** tabs — that *mirrors* (read-only, `$0`, no live backend) the outputs of the agentic kickoff sessions, giving the propose→confirm architecture its missing visual home. To do that, the agentic layer gains a **durable, dashboard-consumable session snapshot** (the capability update). Live in-dashboard chat is designed but **deferred** behind the endpoint/exposure decision.

---

## 2. Requirements

### Group A — Agentic capability updates (make session state renderable)

- **FR-1 — Durable session snapshot.** After an agentic kickoff session (`kickoff chat`), persist a deterministic snapshot artifact (proposed: `.startd8/kickoff/agentic-session.json`) containing: a **`schema_version`** integer (R1-F2); ordered turns (role, text, tool-call name only — no free-text tool args beyond kind); per-session cost (model id, input/output tokens, cost); and a reference to pending proposals. Absent a session, the artifact is absent (presence-gated).
  - **Redaction (testable; R1-F1).** Before write, apply the **same redactor the VIPP inbox uses** — `fde.redaction.redact` (cf. `vipp_seam.py:_warn_if_secret`) — over every persisted string. **AC:** a secret-shaped token planted in a turn's text does **not** appear in the persisted `agentic-session.json` bytes.
  - **Overwrite/durability contract (R1-F5).** Last-session-only retention (OQ-1): a new session overwrites via **temp-then-rename** (an interrupted overwrite leaves the prior valid snapshot readable); concurrent `kickoff chat` sessions against one project root are **last-writer-wins** (stated, acceptable).
- **FR-2 — Reuse the VIPP inbox as the proposal store.** Pending proposals surfaced by the dashboard come from the **existing** `.startd8/vipp/proposals-inbox.json` (`ProposalEnvelope`). **This is already produced** (OQ-4 resolved against source): `kickoff chat` serializes its buffer at session end via `maybe_serialize_buffer(chat.buffer, …)` (`cli_kickoff.py:677` → `vipp_seam.serialize_buffer:181`), and `portal_build.py:117` already reads the inbox. FR-2 is therefore **reuse + read, not new wiring**; the `propose_action` handler stays buffer-only *by design* (`proposals.py:make_propose_handler` only `buffer.add()`s — the CLI owns the session-end persist, keeping the loop write-free). No second proposal store is introduced.
- **FR-3 — Single snapshot read-model.** One deterministic builder folds `KickoffState` (readiness/fields) + the FR-1 session snapshot + the FR-2 inbox into one view-model consumed by the dashboard, so the dashboard and any CLI/TUI view derive from the same oracle (parity, mirroring `state.py`'s single-derivation discipline). **Version contract (R1-F2):** on an **unknown `schema_version`**, the read-model degrades to a typed "unsupported snapshot" empty-marker (per FR-10) — it never raises or mis-parses.
- **FR-4 — Cost & posture transparency carried through.** The snapshot and every rendered surface carry the "assist, not operate" posture and per-session cost line (mirroring `chat.py`'s `cost_line()`), plus a `generated_at` timestamp and an explicit "snapshot — not a live agent" disclosure.

### Group B — The agentic cockpit dashboard (v2 reframe, read-only)

- **FR-5 — Tabbed cockpit.** Extend `build_workbook_v2` into a `TabsLayout` board with three sections built via `build_sectioned_v2`/`Section`: **Status** (the current audience-personalized rows, unchanged), **Assistant** (FR-6), **Proposals** (FR-7). Reuses shipped v2 constructs (M0–M5); keeps the `-v2` UID (`workbook_v2_uid`).
- **FR-6 — Assistant tab (read-only transcript).** Renders the FR-1 snapshot's transcript as markdown `text` panels, newest session, with the FR-4 cost line, `generated_at`, and the "snapshot, no live call" disclosure. **Transcript depth (OQ-2 resolved — full transcript, two-tier):** the baked `text` panel renders a **capped head/tail** of turns (readability + Grafana text-panel size) with a "… N earlier turns — see the Full Transcript panel below" note; the **complete, un-truncated transcript is served on demand via the FR-6b Loki logs panel**. The full transcript is *also* retained verbatim in the FR-1 snapshot file. No detail is lost: the cap is a rendering choice, not a persistence one.
- **FR-6b — Full-transcript depth via Loki (LogQL logs panel).** On snapshot write (FR-1/M1), emit every transcript turn as a **redacted, structured JSON log line** through `startd8.logging_config.get_logger("startd8.kickoff.transcript")` (which reaches Loki through the established file→Promtail→Loki bridge; `logging_otel.py`). The Assistant tab includes a Grafana **`logs` panel** bound to the pre-provisioned **`loki` datasource** with a LogQL selector scoped to this project + newest session (e.g. `{job="startd8", logger="startd8.kickoff.transcript"} | json | project="<p>" | session_id="<sid>"`), giving the user full transcript depth on demand.
  - **Redaction parity (R1-F1).** Turns are passed through the **same `fde.redaction.redact`** used for the snapshot *before* logging — Loki is a persistent PII surface too. **AC:** a planted secret does not appear in the emitted log line.
  - **Additive + graceful degradation.** The logs panel is additive: if Loki is unreachable or holds no matching lines, the panel is empty — the baked capped-tail panel (FR-6) still renders the transcript offline. The cockpit never *depends* on a live query to be honest.
  - **Does NOT cross the FR-11 gate (posture note).** Loki is an **already-provisioned Grafana datasource**, not a new startd8 backend endpoint. Referencing it is distinct from FR-11's deferred live *agentic* endpoint (which runs the model + tools). FR-6b introduces no startd8 server, no `0.0.0.0` exposure, and no live model call — it reads log lines the CLI already wrote. NR-1 (no live backend) is preserved.
- **FR-7 — Proposals tab (queue + confirm affordance).** Renders pending proposals (from FR-2) as a `table`: kind, target/`value_path`, one-line summary, proposal `id`. Each row shows the **exact CLI command** to act on it (e.g. `startd8 kickoff confirm …` or `startd8 vipp apply …`). **The command must be copy-safe and id-bound (R1-F4):** any `value_path`/target is shell-escaped, and the rendered command is derived from the row's proposal `id` such that a copy-paste resolves to exactly that proposal. **AC:** render the command for proposal `P`, parse it back, assert the target `id == P.id` (fixture includes a `value_path` with spaces/quotes). **No write action in the dashboard** (NR-2).
- **FR-8 — Audience-conditional cockpit.** The three tabs respect the shipped `audience` CustomVariable via conditional rendering: **Beginner sees a *simplified* Proposals tab (OQ-3 resolved — show simplified, not hidden): the confirm command is the teaching moment**, so it is shown with reduced columns/detail rather than removed; Advanced/Intermediate see full detail. The Assistant tab is likewise simplified (capped tail only, FR-6b logs panel hidden) for Beginner.
  - **Embed, not reference (R1-F3 resolution).** The cockpit **bakes (embeds) the snapshot content** into the text/table panels at generation time — consistent with the read-only "bake + re-provision, no live endpoint" posture (NR-1). It does **not** reference the snapshot file via a live datasource.
  - **Byte-identity — scoped to a fixed snapshot (R1-F3).** Because the embedded snapshot varies per session, the byte-identity guarantee is asserted **over a frozen snapshot fixture**: for one project + one fixed snapshot, the three audiences produce JSON identical **except the `audience` variable's `current` default** (per Workbook NR-3 / dynamic-dashboards FR-9). It is **not** a claim that two different sessions emit identical bytes.
- **FR-9 — Additive & idempotent.** Classic Workbook (`portal_spec.py`) is byte-untouched; the cockpit is emitted only on the v2 (`--dynamic`) path. Re-provision is idempotent (title/UID collision-guarded per shipped `provision_v2`).
- **FR-10 — Honest empty states.** No session yet → Assistant/Proposals render a "run `startd8 kickoff chat` to begin" hint, **not** an error or a blank panel. No pending proposals → "no proposals awaiting confirmation." **Present-but-malformed/unreadable snapshot (R1-F6):** the tabs render an honest "snapshot unavailable" state — never a traceback or a blank panel. **AC:** feeding the read-model a truncated/invalid `agentic-session.json` yields the unavailable-state, not an exception.

### Group C — Live in-dashboard chat (DEFERRED, gated)

- **FR-11 — Live agentic chat panel (deferred).** Reuse the **ContextCore chat panel's React shell** (`contextcore-chat-panel`: markdown render, panel options, unsigned-plugin deploy pattern) **rewired** from its stateless `/invoke → Claude` proxy to a **startd8 loopback agentic endpoint** that runs the real `AgenticSession` (`survey`/`assess`/`propose_action`) with the cost line and a proposal-confirm affordance. **Gated on the live-endpoint/exposure decision** (kickoff-portal M4). Requirements captured here; **implementation deferred** — no work in the v1 milestone set. Hardening baseline: loopback-only bind + token/CSP/Origin/replay caps (reuse the `consult --serve` pattern).

---

## 3. Non-Requirements

- **NR-1 — No live backend in v1.** The cockpit is a read-only mirror; the portal's "bake + re-provision, no endpoint, no LAN exposure" posture is preserved. (Live backend is FR-11, deferred.)
- **NR-2 — No autonomous or dashboard-initiated writes.** The loop never writes; the dashboard never applies. The **CLI remains the sole writer**; the Proposals tab only *shows* the confirm command.
- **NR-3 — No new persistence store.** Only the existing VIPP inbox (proposals) + the single FR-1 session snapshot file. No kickoff database.
- **NR-4 — Classic Workbook byte-untouched.** Additive on the v2 path only.
- **NR-5 — The CC panel is NOT reused as-is.** A thin stateless proxy bypasses startd8's tool/propose/confirm safety architecture and would surface a weaker agent. Shell-only reuse, backend rewired (FR-11).
- **NR-6 — No streaming** in v1 (matches agentic-loop Increment 1).
- **NR-7 — Not a general chat surface.** The agent stays kickoff-scoped (survey/assess/propose over `KickoffState`); this is not a free-form assistant.

---

## 4. Open Questions

- **OQ-1 — Snapshot location & retention.** `.startd8/kickoff/agentic-session.json` (last session only) vs a `sessions/` dir (last-N, history). Default lean: last session only for v1 (burndown history is the metrics path, not the transcript).
- **OQ-2 — Transcript rendering depth. → RESOLVED (user decision 2026-07-09).** Full transcript, **two-tier**: a baked capped tail in the `text` panel (FR-6) + the complete transcript served on demand via a **Loki LogQL `logs` panel** (FR-6b). The snapshot file also retains the full transcript. No detail is lost.
- **OQ-3 — Audience treatment of Proposals. → RESOLVED (user decision 2026-07-09).** **Show simplified for Beginner** (the confirm command is the teaching moment), not hidden. See FR-8.
- **OQ-4 — `propose_action` → inbox wiring. → RESOLVED (source-verified 2026-07-09).** The handler is buffer-only *by design*; `kickoff chat` already persists the buffer to the inbox at session end (`maybe_serialize_buffer`, `cli_kickoff.py:677`). No new persist step needed — FR-2 is reuse. **New sub-question surfaced:** the same session-end seam does **not** persist the *transcript* (FR-1's genuine gap) — M1 should add the snapshot write alongside the existing `maybe_serialize_buffer` handoff.
- **OQ-5 — Live-chat endpoint hardening (FR-11, deferred).** Loopback-only + token/CSP/Origin/replay caps via the `consult --serve` pattern — confirm reuse when FR-11 is scheduled.

---

*v0.2 — Post-planning self-reflective update. 5 assumptions corrected (4 reused existing machinery; 1 identified the real new capability), 3 open questions resolved, live-chat scope isolated behind the endpoint gate.*

*v0.3 — Post lessons-learned hardening. Applied 4 lessons: reuse-first audit (KM Leg 3 #34), verify-against-source/phantom-reference (KM Leg 7 #48, 1 phantom corrected + 1 unverified claim demoted to OQ-4), single-source ownership (Design_Docs #5), prune-phantom-scope (FR-11 fenced). OQ-4 then resolved against source (FR-2 downgraded build→reuse; R1 dissolved; a 2nd phantom `write_inbox`→`serialize_buffer` corrected).*

*v0.4 — Post-CRP R1 triage. All 6 F-suggestions ACCEPTED + applied: FR-1 gained testable redaction (`fde.redaction.redact` + planted-secret AC) + `schema_version` + temp-then-rename overwrite contract; FR-3 gained the unknown-version degrade contract; FR-7 gained copy-safe/id-bound command + round-trip AC; FR-8 resolved the byte-identity-vs-per-session tension (embed + frozen-fixture); FR-10 gained the malformed-snapshot honest state. See Appendix A.*

*v0.5 — User decisions before implementation. OQ-2 resolved: full transcript, two-tier (baked capped tail + on-demand Loki LogQL depth) → new **FR-6b** (redacted transcript emission to Loki + `logs` panel; additive, graceful-degrade, does NOT cross the FR-11 endpoint gate since `loki` is a pre-provisioned datasource). OQ-3 resolved: Beginner sees a **simplified** Proposals tab (not hidden) → FR-8 updated. Source-verification pass confirmed all named symbols exist (3 minor deltas: `redact()` returns `(text, manifest)`; `build_workbook_v2` uses `RowsLayout` directly so M3 wraps it into a Status `Section`; `--dynamic` lives in `cli_concierge.py` while the chat seam is `cli_kickoff.py:677`).*

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
| R1-F1 | Make FR-1 redaction testable (named rule set + AC) | R1 (claude-opus-4-8[1m]) | Merged into **FR-1**: named `fde.redaction.redact` (same redactor the VIPP inbox uses) + planted-secret AC. | 2026-07-09 |
| R1-F2 | Add `schema_version` + FR-3 unknown-version degrade contract | R1 | Merged into **FR-1** (field) + **FR-3** (degrade-to-typed-marker contract). | 2026-07-09 |
| R1-F3 | Resolve FR-8 byte-identity vs per-session content | R1 | Merged into **FR-8**: embed (bake) not reference; byte-identity scoped to a **frozen snapshot fixture**. | 2026-07-09 |
| R1-F4 | FR-7 command copy-safe + id-bound | R1 | Merged into **FR-7**: shell-escape + id-derived + render→parse round-trip AC. | 2026-07-09 |
| R1-F5 | FR-1 overwrite/durability contract | R1 | Merged into **FR-1**: temp-then-rename + last-writer-wins (ties OQ-1). | 2026-07-09 |
| R1-F6 | FR-10 malformed-snapshot honest state | R1 | Merged into **FR-10**: "snapshot unavailable" state + truncated-file AC. | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | R1 | All 6 R1 F-suggestions accepted. | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-09

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-09 21:30:00 UTC
- **Scope**: Requirements review (F-prefix) — dual-document, weighted toward FR-1 snapshot schema/redaction/retention, FR-8 byte-identity under varying snapshot content, and FR-7/FR-10 confirm-surface honesty.

**Executive summary (top ambiguities / gaps):**
- FR-1 says redaction "rules from the agentic loop apply" but names no rule set and gives no acceptance criterion — the one genuinely new persisted artifact has no testable redaction bar.
- FR-1's snapshot has no declared **schema version**, so FR-3's read-model has no contract to validate against as the agentic loop evolves.
- FR-8's byte-identity claim collides with FR-1/FR-6's **per-session-varying** transcript/cost content; the requirement never states whether audience byte-identity is asserted over a fixed snapshot or the live one.
- FR-7 requires the "exact CLI command" but does not require it be copy-safe (escaping) or verifiably bound to the right proposal `id` — a mis-rendered command undermines the whole confirm-surface honesty.
- OQ-1 (retention) leaves overwrite/concurrency semantics of the single snapshot file undefined; FR-1 calls the artifact "durable" without an overwrite contract.
- FR-10 defines empty states for "no session / no proposals" but not for a **present-but-malformed/unreadable** snapshot — the honest-state matrix is incomplete.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | Make FR-1 redaction testable: replace "Redaction rules from the agentic loop apply (secret/PII redaction before write)" with a named rule set (or explicit cross-ref to the owning agentic-loop requirement ID) and an acceptance criterion — e.g. "no value matching the loop's secret/PII patterns appears in the persisted bytes." | As written, "rules … apply" is unverifiable; the snapshot is the feature's primary new on-disk PII surface (persisted transcript text). A reviewer cannot tell what "redacted enough" means. | FR-1, final sentence | AC: plant a known secret in a turn; assert absent from `agentic-session.json` bytes |
| R1-F2 | Interfaces | high | Add a `schema_version` field to the FR-1 snapshot artifact and state FR-3's contract on it (read-model must degrade to a typed empty/"unsupported" marker on an unknown version, per FR-10, not raise). | FR-3 is the single derivation oracle but FR-1 declares no versioned contract; snapshot-format drift is near-certain as the agentic loop iterates and would silently corrupt every rendered surface. | FR-1 (add field to the "containing:" list) + FR-3 (state the version contract) | AC: a snapshot with a bumped `schema_version` yields a typed unsupported-marker, not a traceback |
| R1-F3 | Data | high | Resolve the FR-8 ↔ FR-1/FR-6 tension explicitly: state whether the byte-identity guarantee ("identical bytes except the `audience` variable's `current` default") is asserted over a **fixed snapshot fixture** or the live snapshot, since transcript/cost vary per session. If the snapshot is embedded in the emitted JSON, byte-identity across audiences is only assertable against a frozen snapshot. | FR-8's guarantee and FR-1/FR-6's per-session content are in direct tension; without pinning, the "identical bytes except audience current" AC is structurally unprovable. | FR-8, after the byte-identity sentence | AC: byte-diff harness across 3 audiences over a frozen snapshot fixture; diff == audience `current` only |
| R1-F4 | Interfaces | medium | Strengthen FR-7: require the rendered confirm command to be copy-safe (shell-escape any `value_path`/target) and verifiably bound to the row's proposal `id`, so a copied command targets exactly that proposal. | FR-7's honesty (and the NR-2 "show the command, don't act" contract) depends on the command being copy-exact; a mis-escaped `value_path` or wrong `id` produces a command that looks actionable but targets the wrong/no proposal — worse than an empty state. | FR-7, after "the exact CLI command to act on it" | AC: render command for proposal P, parse back, assert target id == P.id; include a `value_path` containing spaces/quotes |
| R1-F5 | Data | medium | Give FR-1 an explicit overwrite/durability contract tied to OQ-1: for last-session-only retention, specify temp-then-rename overwrite and last-writer-wins for concurrent `kickoff chat` sessions, so "durable" is not contradicted by an interrupted overwrite. | FR-1 calls the artifact "durable" and "presence-gated" but never states what happens on the second session or an interrupted write; a truncated overwrite would feed FR-3 a corrupt file. | FR-1 (durability clause) or OQ-1 (promote the lean to a stated contract) | AC: interrupted overwrite leaves the prior valid snapshot readable |
| R1-F6 | Risks | medium | Extend FR-10's honest-empty-state matrix to cover a **present-but-unreadable/malformed** snapshot (not just "no session"): the Assistant/Proposals tabs must render an honest "snapshot unavailable" state, never a traceback or a blank panel. | FR-10 enumerates "no session yet" and "no pending proposals" but omits the malformed/corrupt-file case, which is exactly the state R1-F2/R1-F5 make possible; the honesty guarantee has a hole. | FR-10, add a third bullet | AC: feed the read-model a truncated/invalid `agentic-session.json`; assert an honest unavailable-state, not an exception |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; no prior untriaged suggestions exist.
