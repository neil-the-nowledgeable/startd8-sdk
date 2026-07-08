# Digital Project Workbook — Panel-Processing Pipeline (Increment 3) Requirements

**Version:** 0.3 (Post-planning + lessons hardening — ready for CRP)
**Date:** 2026-07-08
**Status:** Draft
**Parent:** the Digital Project Workbook (`GRAFANA_KICKOFF_PORTAL_*`, `WORKBOOK_STAKEHOLDER_RUN_*`)
**Pilot:** `household-o11y`

---

## 0. Planning Insights (Self-Reflective Update)

> A grounded planning pass over `vipp/apply.py`, `stakeholder_panel/proposals.py`, and the
> `synthesis_bridge`/`vipp` code paths. Six corrections — the biggest resolves the riskiest FR (the
> apply gate over HTTP).

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Reproducing `apply`'s `confirm()` over HTTP is uncertain (OQ-1, "riskiest FR") | `apply_dispositions(root, *, confirm: ConfirmFn, force=False)` calls `confirm(action, disp)->bool` **per-proposal**; the internal `_RATIFY_TOKEN="vipp:human-confirm"` is applied **only when confirm returns True** (`apply.py:163-166`). | FR-R7 reproduces the gate as **preview→ratify**: preview calls `confirm→False` (returns the would-apply list + a challenge, no writes); ratify's endpoint-confirm returns True **only** for `disp.proposal_id`s the human explicitly echoes with a challenge token. **Per-proposal + non-one-click by construction.** OQ-1 resolved. |
| FR-R4 (set disposition) is new work | `ProposalStore.update_disposition(...)` / `update_dispositions(updates)` are **first-class** (`proposals.py:113,123`). | FR-R4 is trivial routing; narrowed. |
| Apply is all-or-nothing | `confirm` is **per-proposal** (keyed by `disp.proposal_id`). | FR-R7 supports **granular** ratification (ratify specific proposals), matching the CLI. |
| Apply status could come from a persisted `ApplyResult` | `apply_dispositions` **returns** `ApplyResult` (not persisted). | The apply *route* returns it; the *display* (FR-D5) infers status from the stores. |
| `force` is fine | `apply_dispositions(force=True)` bypasses stale-seq/no-clobber guards. | **NR-8:** the endpoint MUST NOT expose `force`. |
| Reuse the run endpoint's `run_key` for extract idempotency | `run_key` binds `{question,cap,roster}` — wrong for extract (keyed by the *synthesis*). | OQ-4: extract idempotency keys on `(session_id + synthesis-checksum)`. |

**Resolved open questions:** OQ-1 → preview/ratify per-proposal challenge-echo. OQ-3 → recompute triage
from the transcript at build ($0). OQ-4 → extract idempotency = session_id + synthesis checksum.
**Still open:** OQ-2 (section vs dedicated dashboard), OQ-5 (apply auth posture), OQ-6 (token UX).

### 0.1 Lessons-Learned Hardening
- **Phantom-reference audit** — every routed symbol grounded (see §Reference Audit): `apply_dispositions`,
  `ProposalStore.update_disposition`, `read_inbox`, `VippReport.from_json`, `build_triage`,
  `extract_field_mappings`, `stage_recommendations`, `serialize_accepted_to_vipp`, `run_vipp_negotiate`.
- **Overloaded-term discipline** — "proposal" is **tri-loaded** (`ProposalStore` `Recommendation` →
  host `ProposedAction` → VIPP `EnvelopedProposal`). This spec uses the **precise** names per the
  bridge's own NR-8; the pre-VIPP unit is a **Recommendation** (or **Candidate** pre-staging), never a
  bare "proposal."
- **Single-source vocabulary** — the pipeline vocabulary (`Lane`, `Candidate`, `Recommendation`,
  `disposition`, `VippDisposition`, `Decision`, `Grounding`) is **owned by** `synthesis_bridge/models.py`
  + `vipp/models.py`; this spec **cites** it, never redefines.
- **Prune phantom scope** — the reverse consult-panel CLI exposure stays a Non-Requirement (NR-5).
- **CRP steering** — brand-new doc-set (least-reviewed); settled/do-not-relitigate: route-through-CLI,
  no-one-click-apply, estimate≠authored, ground-truth-adjudicates-never-originates, no-`force`.

### Reference Audit

| Routed symbol | Exists? | Path |
|---------------|---------|------|
| `apply_dispositions(root, *, confirm, force)` + `ConfirmFn` + `_RATIFY_TOKEN`/`assert_ratifiable` | ✅ | `vipp/apply.py:86,89,50`; `fde/ratification.py` |
| `ProposalStore.load` / `update_disposition` / `update_dispositions` | ✅ | `stakeholder_panel/proposals.py:94,113,123` |
| `read_inbox` / `ProposalEnvelope.from_json` / `VippReport.from_json` | ✅ | `vipp/{apply,models}.py` |
| `build_triage` / `TriageReport` (`counts`,`health`,`to_dict`) | ✅ | `synthesis_bridge/{route,models}.py` |
| `extract_field_mappings` (paid) / `stage_recommendations` / `serialize_accepted_to_vipp` | ✅ | `synthesis_bridge/{extract_llm,stage}.py` |
| `run_vipp_negotiate(inbox, panel=…)` | ✅ | `vipp/assistant.py` |
| CLI confirm pattern `_make_confirm` / `vipp_apply` | ✅ | `cli_vipp.py:45,153` |
| Phase-2 run endpoint (auth + fail-closed + idempotency to extend) | ✅ | `kickoff_experience/stakeholder_run_server.py` |
| a persisted `ApplyResult` / a single pipeline-state artifact | ❌ (infer from stores) | — |

---

## 1. Problem Statement

The stakeholder-panel CLI now has a **systematic pipeline** that turns the panel's free-text synthesis
into structured, adjudicated, human-gated field changes:

```
panel (paid) → transcript+synthesis → synthesis_bridge (extract→classify→TriageReport; [paid] extract
→ stage Recommendation(draft, estimate) → [human accepts] → serialize → VIPP inbox) → vipp negotiate
(evaluate vs Sapper → dispositions ACCEPT/REJECT/COUNTER) → vipp apply (HUMAN confirm gate → writes
project source-of-record → inbox shredded)
```

The **Digital Project Workbook** (Grafana) today displays the roster + the latest run's *raw* answers,
and can *run* the panel (Phase 2). It surfaces **none of the systematic processing**. This increment
extends the Workbook to **fully display and drive** that pipeline — **including the VIPP apply write** —
with every human-in-the-loop gate preserved.

### Gap table

| Component | Current State | Gap |
|-----------|---------------|-----|
| Pipeline display | none (raw answers only) | funnel: triage → staged → inbox → dispositions → apply-status |
| Pipeline drive | run-only (Phase 2) | triage · extract→stage (paid) · accept/reject · serialize · negotiate · **apply** |
| Read surfaces | 4 stores exist + readable | not read by the Workbook |
| Apply gate | CLI `vipp apply` + `confirm()` | must be reproduced faithfully over HTTP + a dashboard button |

---

## 2. Requirements

### 2A. Display (read-only, $0 — extends `portal_spec.py`)

- **FR-D1 — Pipeline funnel section.** A new `$0`, pure Workbook section renders the pipeline state
  from the four existing stores (transcript, `ProposalStore`, VIPP inbox, VIPP dispositions) + a
  recomputed triage. Funnel: synthesis items → triaged (NON_DECIDABLE vs FIELD_LEVEL) → staged
  (draft/accepted/rejected) → inbox (pending) → dispositions (ACCEPT/REJECT/COUNTER) → apply-status.
- **FR-D2 — Triage view.** Recompute `TriageReport` from the transcript's synthesis at portal build
  ($0, deterministic) — render `counts()`, the NON_DECIDABLE table (`title`, `reason`, `suggested_owner`,
  `source_section`) and FIELD_LEVEL candidates (`value_path`). Shows "nothing dropped."
- **FR-D3 — Staged recommendations view.** `ProposalStore(root, session).load()` → per-field rows:
  `value_path`, `recommended_value`, `role_id`, `grounding`, **`disposition`** (draft/accepted/rejected/
  invalid), `provenance` (=estimate), `cost_usd`.
- **FR-D4 — VIPP inbox + dispositions view.** `read_inbox` → pending `capture` proposals; `VippReport`
  → per-proposal **decision** (ACCEPT/REJECT/COUNTER), `reason`, `evidence_available`, `envelope_seq`,
  `cost_usd`, `llm_used`, and the `panel_advisories` section.
- **FR-D5 — Apply status (inferred).** No `ApplyResult` is persisted; infer: inbox present ⇒ N pending;
  inbox absent + dispositions present ⇒ consumed/applied. Surface the state honestly (no false "done").
- **FR-D6 — Health/contamination warnings.** Surface `TriageReport.health` (FR-14 under-grounding /
  retail-default-context flags) so a reviewer knows the input may be contaminated.

### 2B. Drive (CLI-backed endpoint routes — extend `stakeholder_run_server.py`)

> Every action routes **THROUGH the CLI code paths** (`synthesis_bridge`, `vipp`, `ProposalStore`) —
> the endpoint never re-implements pipeline logic. All routes reuse the Phase-2 endpoint's auth
> (bearer token, posture split) + the fail-closed/idempotency machinery where they spend.

- **FR-R1 — Endpoint route surface.** Add pipeline routes to the existing run endpoint (same app, same
  auth): triage, extract-stage, disposition (accept/reject), serialize, negotiate, apply. Each returns
  a structured status the Workbook can render.
- **FR-R2 — Triage ($0).** Route → `build_triage(transcript)` → `TriageReport.to_dict()`. Read-only.
- **FR-R3 — Extract→stage (PAID).** Route → `extract_field_mappings` (paid) → `stage_recommendations`
  ($0). Reuses the **fail-closed budget + dry-run estimate + run_key idempotency** the run endpoint
  already provides (extract is the only paid step here).
- **FR-R4 — Disposition a staged recommendation ($0, human gate).** Route → `ProposalStore.
  update_disposition((domain, value_path), "accepted"|"rejected")` (first-class, per §0). The **human
  accept-before-serialize gate** — the route sets state, it doesn't decide.
- **FR-R5 — Serialize accepted → inbox ($0).** Route → `serialize_accepted_to_vipp(accepted_only=True)`
  → VIPP inbox. Non-allow-listed paths are **rejected, not dropped** (already the CLI's behavior).
- **FR-R6 — Negotiate ($0; narrative paid).** Route → `run_vipp_negotiate` → dispositions. Narrative is
  an opt-in paid flag gated by the same budget preflight.
- **FR-R7 — Apply (THE gate) — preview → ratify, per-proposal, challenge-echo.** Route →
  `apply_dispositions(project_root, confirm=…)`, writing the **project source of record**. Reproduces
  the CLI's per-proposal `confirm(action, disp)->bool` gate as **two separate requests**:
  1. **Preview** (`POST …/apply/preview`) — calls `apply_dispositions(confirm=lambda a, d: False)` so
     **nothing is written**; returns the exact would-apply set (kind/params from the **trusted inbox**,
     not the disposition) + a per-run **ratification challenge** (a nonce/summary the human must echo).
  2. **Ratify** (`POST …/apply/ratify`) — body carries the **explicit `proposal_ids` to apply** + the
     **challenge token the human re-supplies**. The endpoint's confirm callback returns True **only** for
     `disp.proposal_id ∈ ratified_ids` **and only if** the challenge matches — so `_RATIFY_TOKEN` is
     applied per-proposal exactly for what the human ratified. **Never one-click / auto-apply**; the
     panel/dashboard cannot auto-fill the challenge. `force` is **not** exposed (NR-8). Stale-seq refusal
     + no-clobber-of-undrained-inbox are inherited from `apply_dispositions`.

### 2C. Load-bearing constraints (cross-cutting — carry into EVERY surface)

- **FR-C1 — SYNTHETIC & UNRATIFIED** banner on everything panel-derived (triage, recommendations,
  advisories) — not just the raw-answers section.
- **FR-C2 — `estimate` ≠ `authored`.** A staged recommendation is a *draft starter*; the Workbook must
  never present it as a confirmed field value, and must offer **no path that auto-flips estimate→authored**
  (that flip is a human, in-file act the SDK never performs).
- **FR-C3 — Ground truth adjudicates, never originates.** VIPP dispositions are project-authority but
  `sdk_version` is **provenance-only, never authority**; surface `evidence_available=false` as *degraded*.
- **FR-C4 — Confirmation gates are load-bearing.** (a) disposition→accepted before serialize; (b) an
  explicit ratification confirm before apply. Any Workbook button routes through these, never bypasses.
- **FR-C5 — Posture change: inherit the CLI's confinement.** The read-only-by-default portal now writes;
  it MUST inherit the CLI's guards: `0600` stores, **symlink rejection**, **stale-seq refusal**,
  **no-clobber of an undrained inbox**, path confinement. No new, weaker write path.
- **FR-C6 — Anti-anchoring.** Show the original OMIT question next to any synthetic panel advisory.

### 2D. Pilot + verdict

- **FR-P1 — Pilot on household** end-to-end (a real run → triage → stage → serialize → negotiate →
  apply-preview), with a written verdict. Apply's *actual write* is exercised only against a throwaway
  project (never household's real inputs unless explicitly chosen).

---

## 3. Non-Requirements

- **NR-1 — Don't reimplement pipeline logic.** Route through `synthesis_bridge`/`vipp`/`ProposalStore`.
- **NR-2 — No one-click apply.** Apply is always preview → explicit ratification confirm.
- **NR-3 — No auto-ratify / no estimate→authored auto-flip.** The SDK never confirms on the human's behalf.
- **NR-4 — No new persistence formats.** Read existing stores; recompute triage from the transcript.
- **NR-5 — Reverse consult-panel pass** (`panel_advisories`) is *displayed* if present but **not newly
  CLI-exposed** in this increment (it's only on `run_vipp_negotiate(panel=…)`) unless planning shows it's cheap.
- **NR-6 — No bypass of the human accept/confirm gates**, ever, from any surface.
- **NR-7 — Local pilot only.** No cloud Grafana / multi-tenant.
- **NR-8 — Never expose `apply`'s `force`.** The endpoint MUST NOT pass `force=True` — that bypasses the
  stale-seq + no-clobber guards. Apply always goes through the full preflight.

---

## 4. Open Questions

- **OQ-1 — Apply's confirm/ratification over HTTP. → RESOLVED (§0):** preview (`confirm→False`) →
  ratify (per-proposal `confirm→True` gated by an echoed challenge). Non-one-click by construction.
- **OQ-2 — Section vs dedicated dashboard. → OPEN.** The funnel is large; lean toward a **sibling
  dashboard** `cc-portal-kickoff-pipeline-{project}` linked from the main Workbook, keeping the portal
  section a compact summary. Decide in M-display.
- **OQ-3 — Recompute triage vs persist. → RESOLVED:** recompute from the transcript at build ($0). The
  driven triage route may additionally persist, but display never depends on it.
- **OQ-4 — Extract idempotency key. → RESOLVED:** `(session_id + synthesis-checksum)`, not `run_key`
  (which binds question/cap/roster). The paid extract dedupes on the synthesis it processed.
- **OQ-5 — Apply auth posture. → OPEN (lean).** Same server → same bearer-token + local-posture split;
  but apply is the highest-value target, so require the ratification challenge **in addition** to the
  token (defense in depth), and recommend `--strict` when the apply route is enabled.
- **OQ-6 — Ratification token UX. → OPEN.** The human echoes a challenge the preview issued (a short
  phrase/nonce), typed into the ratify action — provably a human act, not panel/dashboard-autofillable.

---

*v0.3 — Post-planning + lessons hardening. OQ-1 (the apply gate over HTTP) resolved to a per-proposal
preview→ratify challenge-echo flow; FR-R4 narrowed to `update_disposition`; FR-R7 made granular +
non-one-click; NR-8 (no `force`) added; overloaded "proposal" vocabulary disciplined; reference audit
grounded. Ready for CRP.*
