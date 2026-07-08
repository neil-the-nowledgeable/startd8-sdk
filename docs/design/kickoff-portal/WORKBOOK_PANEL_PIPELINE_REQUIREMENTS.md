# Digital Project Workbook — Panel-Processing Pipeline (Increment 3) Requirements

**Version:** 0.4 (Post-CRP R1 — apply gate rebuilt; 14 findings accepted)
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

### 0.2 CRP Round-1 Triage (v0.3 → v0.4) — the apply gate did not hold

> Independent CRP (Appendix A) raised F-1…F-8 (requirements) + S-1…S-6 (plan), all code-grounded.
> **All 14 ACCEPTED.** Three BLOCKERs broke the v0.3 apply gate; a **user decision** (2026-07-08) chose
> **"HTTP apply, honestly re-scoped"** — build apply-from-Grafana, fix the blockers, and **drop the
> "human-proof" claim**: apply is **token-gated** (whoever holds the endpoint token can apply) but each
> apply is a **deliberate two-request act bound to exactly the previewed set**.

| # | Sev | Finding | Change applied |
|---|-----|---------|----------------|
| F-1 | BLOCKER | Preview via `apply_dispositions(confirm→False)` is **not read-only** (records `consumed`; an all-REJECT report **shreds the inbox**) | FR-R7 preview **never calls `apply_dispositions`** — it **reconstructs** the would-apply set purely (read inbox+dispositions via `_reconstruct`), zero side effects. AC: preview leaves `vipp-cursor.json` + inbox byte-identical. |
| F-2 | BLOCKER | Challenge-echo is theater — same token authorizes preview+ratify, challenge returned in the body → scriptable unattended | **Claim dropped:** NR-2 re-scoped — apply is **token-gated, not human-proof**. **`strict=True` is MANDATORY** when the apply route is enabled (was OQ-5 "recommended"). |
| F-3 | BLOCKER | Preview↔ratify unbound — a concurrent negotiate re-seqs the inbox; ratify applies an unpreviewed set | FR-R7 challenge **binds `envelope_seq` + a content-hash of the previewed would-apply set**; ratify **refuses** if the live inbox seq ≠ the challenge's (stale → re-preview). |
| F-4 | SHOULD | Challenge lifecycle unspecified (only an in-memory, restart-losing nonce) | FR-R7 challenge = a **stateless HMAC** over `{seq, content-hash, expiry}` with a per-server key (survives restart; no server store; single-use via a small persisted seen-set). OQ-6 resolved. |
| F-5 | SHOULD | Funnel stores are **project-global singletons** (inbox/dispositions carry no session_id); ProposalStore is per-session → mis-attribution | FR-D1/D4/D5: render inbox/dispositions as **project-global "last-serialized" state**, never implying a session join past the staged column. (M-display already does this.) |
| F-6 | SHOULD | FR-R4 API wrong: `update_disposition(domain, value_path, disposition)` (3 positional); serialize filters the literal `"accepted"` (docstring says "approved" — a trap); no-ops if not staged | FR-R4 corrected: 3 positional args, pin `"accepted"`/`"rejected"`, ensure the rec is staged first. FR-R5 pins the `"accepted"` literal. |
| F-7 | SHOULD | FR-C5 confinement is asserted, not grounded; `apply_dispositions` doesn't confine itself | FR-C5 **maps each guard to its enforcing function** (`resolve_confined_root` in `ensure_posting`/`serialize_buffer`; symlink-reject in `run_vipp_negotiate`) and **flags apply's own path for an explicit `resolve_confined_root`**. |
| F-8 | SHOULD | Two paid paths don't share the run endpoint's preflight (`run_key` is run-shaped; negotiate-narrative uses its own `max_cost_usd`) | FR-R3: a **new** extract preflight/estimate keyed on `(session_id + synthesis-checksum)`. FR-R6: negotiate-narrative spends via `max_cost_usd` — the endpoint sets/enforces that ceiling explicitly. |

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
  ($0). (CRP F-8) Reuses the fail-closed budget gate but with a **new extract preflight/estimate** keyed
  on **`(session_id + synthesis-checksum)`** — NOT `run_key` (which binds question/cap/roster). extract
  is the only paid step here.
- **FR-R4 — Disposition a staged recommendation ($0, human gate).** (CRP F-6) Route →
  **`ProposalStore.update_disposition(domain, value_path, "accepted")`** (three positional args) — pin
  the exact literals **`"accepted"`/`"rejected"`** (`serialize_accepted_to_vipp` filters `== "accepted"`;
  the docstring's "approved" is a trap). The route MUST ensure the rec is **staged first** (else
  `update_disposition` no-ops). The **human accept-before-serialize gate** — sets state, doesn't decide.
- **FR-R5 — Serialize accepted → inbox ($0).** Route → `serialize_accepted_to_vipp(accepted_only=True)`
  → VIPP inbox. Non-allow-listed paths are **rejected, not dropped** (already the CLI's behavior).
- **FR-R6 — Negotiate ($0; narrative paid).** Route → `run_vipp_negotiate` → dispositions. (CRP F-8)
  `--narrative`/panel spend runs through `run_vipp_negotiate`'s own **`max_cost_usd`** ceiling — the
  endpoint sets + enforces that ceiling explicitly (it does NOT flow through the run endpoint's preflight).
- **FR-R7 — Apply (THE gate) — pure preview → signed-challenge ratify (CRP F-1/F-2/F-3/F-4, "token-gated,
  honestly re-scoped").** Writes the **project source of record**. Two separate requests:
  1. **Preview** (`POST …/apply/preview`) — **MUST NOT call `apply_dispositions`** (it mutates the cursor
     for REJECTs and can shred the inbox — F-1). Instead **reconstruct** the would-apply set *purely* from
     the inbox + dispositions (mirror `_reconstruct`), **zero side effects** (AC: `vipp-cursor.json` +
     inbox **byte-identical** after preview). Returns the would-apply set + a **stateless HMAC challenge**
     over `{envelope_seq, content-hash-of-would-apply-set, expiry}` signed with a per-server key (F-3/F-4)
     — survives restart, single-use via a small persisted seen-set.
  2. **Ratify** (`POST …/apply/ratify`) — body = `{proposal_ids:[…], challenge}`. The endpoint verifies
     the HMAC, **refuses if the live inbox `envelope_seq` ≠ the challenge's** (a concurrent negotiate →
     stale → re-preview, F-3), then calls `apply_dispositions(confirm=…)` where confirm returns True
     **only** for `disp.proposal_id ∈ proposal_ids`. `_RATIFY_TOKEN` is applied per-proposal for exactly
     the previewed, still-current set. `force` is **not** exposed (NR-8).
  - **Honest posture (F-2):** this is **token-gated, not human-proof** — a holder of the endpoint token
    can drive preview→ratify. The guarantees are: (a) apply is a **deliberate two-request act bound to
    exactly the previewed set** (seq + content-hash), (b) it can't apply something the human didn't
    preview, (c) **`strict=True` (Origin allow-list + replay nonce) is MANDATORY** whenever the apply
    route is enabled. The "cannot auto-fill / human-proof" claim of v0.3 is **withdrawn**.

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
- **FR-C5 — Posture change: confinement grounded to enforcing functions (CRP F-7).** The read-only
  portal now writes; each guard maps to a specific enforcer, and any not enforced on the **apply** path
  is added: `0600` + path-confinement via `resolve_confined_root` (in `ensure_posting` / `serialize_
  buffer`); **symlink-reject** of the inbox read (in `run_vipp_negotiate`); **stale-seq refusal** +
  **no-clobber-of-undrained-inbox** (in `apply_dispositions`). ⚠ `apply_dispositions` does **not** call
  `resolve_confined_root` itself → the apply route MUST wrap it with an explicit confinement check. No
  new, weaker write path.
- **FR-C6 — Anti-anchoring.** Show the original OMIT question next to any synthetic panel advisory.

### 2D. Pilot + verdict

- **FR-P1 — Pilot on household** end-to-end (a real run → triage → stage → serialize → negotiate →
  apply-preview), with a written verdict. Apply's *actual write* is exercised only against a throwaway
  project (never household's real inputs unless explicitly chosen).

---

## 3. Non-Requirements

- **NR-1 — Don't reimplement pipeline logic.** Route through `synthesis_bridge`/`vipp`/`ProposalStore`.
- **NR-2 — No one-click apply, honestly re-scoped (CRP F-2).** Apply is always **pure preview → signed-
  challenge ratify**, a deliberate two-request act bound to the previewed set. It is **token-gated, not
  human-proof**: a holder of the endpoint token can drive it. The v0.3 "cannot auto-fill / human-proof"
  claim is **withdrawn**; `strict=True` is mandatory when apply is enabled. What holds: no apply of an
  unpreviewed/stale set, no `force`, no bypass of the accept-before-serialize gate.
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

- **OQ-1 — Apply's confirm/ratification over HTTP. → RE-RESOLVED (CRP F-1/2/3/4):** the v0.3 answer was
  broken (preview not read-only; challenge theater; preview↔ratify unbound). New: **pure reconstruct-only
  preview** + a **stateless HMAC challenge bound to `{envelope_seq, content-hash}`** + mandatory strict;
  **token-gated, not human-proof.** See FR-R7.
- **OQ-2 — Section vs dedicated dashboard. → OPEN.** The funnel is large; lean toward a **sibling
  dashboard** `cc-portal-kickoff-pipeline-{project}` linked from the main Workbook, keeping the portal
  section a compact summary. Decide in M-display.
- **OQ-3 — Recompute triage vs persist. → RESOLVED:** recompute from the transcript at build ($0). The
  driven triage route may additionally persist, but display never depends on it.
- **OQ-4 — Extract idempotency key. → RESOLVED:** `(session_id + synthesis-checksum)`, not `run_key`
  (which binds question/cap/roster). The paid extract dedupes on the synthesis it processed.
- **OQ-5 — Apply auth posture. → RESOLVED (CRP F-2):** `strict=True` (Origin allow-list + replay nonce)
  is **MANDATORY** when the apply route is enabled (was "recommended"). It is still **token-gated**.
- **OQ-6 — Ratification challenge. → RESOLVED (CRP F-4):** a **stateless HMAC** over `{envelope_seq,
  content-hash, expiry}` with a per-server key, single-use — NOT the in-memory nonce (lost on restart).
  It binds the previewed set; it does **not** prove human presence (F-2).

---

*v0.4 — Post-CRP R1. All 14 findings accepted. **The v0.3 apply gate was broken** (preview not read-only
F-1; challenge theater F-2; preview↔ratify unbound F-3). User chose "HTTP apply, honestly re-scoped":
FR-R7 rebuilt as **pure-reconstruct preview + stateless-HMAC-challenge ratify bound to `{seq, content-
hash}` + mandatory strict**, **token-gated (not human-proof)** — NR-2 claim withdrawn. FR-R4 API fixed
(F-6), FR-C5 confinement grounded (F-7), FR-D funnel = project-global not session (F-5), FR-R3/R6 budget
paths corrected (F-8). Ready to implement (M-display shipped; M-drive/M-apply next).*

---

## Appendix A — Accepted Suggestions (cross-model memory)

> CRP R1 — all 8 requirements findings ACCEPTED; changes in §0.2 + FR-R3/R4/R6/R7 + FR-C5 + FR-D5 + NR-2.
- **[F-1]** ACCEPTED → FR-R7 pure-reconstruct preview (no `apply_dispositions`); byte-identical AC.
- **[F-2]** ACCEPTED → NR-2/FR-R7 re-scoped to token-gated (not human-proof); strict mandatory (OQ-5).
- **[F-3]** ACCEPTED → FR-R7 challenge binds `envelope_seq` + content-hash; stale → refuse.
- **[F-4]** ACCEPTED → FR-R7 stateless HMAC challenge (OQ-6).
- **[F-5]** ACCEPTED → FR-D1/D4/D5 render inbox/dispositions as project-global last-serialized state.
- **[F-6]** ACCEPTED → FR-R4/R5 API + `"accepted"` literal fixed.
- **[F-7]** ACCEPTED → FR-C5 guards mapped to enforcers; apply-path confinement flagged.
- **[F-8]** ACCEPTED → FR-R3 new extract preflight (session+synthesis); FR-R6 `max_cost_usd` ceiling.

## Appendix B — Rejected Suggestions (cross-model memory)

_None — all 14 CRP findings (F-1…F-8, S-1…S-6) were code-grounded and accepted._

## Appendix B — Rejected Suggestions (cross-model memory)

*(none yet — rejected findings land here with rationale so later reviewers don't re-propose.)*

## Appendix C — Incoming Review

#### Review Round R1 (independent CRP, 2026-07-08)

- **[F-1]** **[BLOCKER]** Preview is **not read-only** — the claim "nothing is written" is false. `apply_dispositions(confirm=lambda a,d: False)` (apply.py:121-201) still calls `context.record_processed(..., "consumed")` for every `REJECT` disposition (apply.py:130-136) and every `no_inbox_entry` (apply.py:145-147) — real writes to `vipp-cursor.json`. Worse: `consumed_all` starts `True` and is only set `False` by an actionable ACCEPT/COUNTER; a dispositions report that is **all REJECT** (or all no-inbox-entry) leaves `consumed_all=True`, so **preview shreds the inbox** (apply.py:200-201). — Why: FR-R7's preview safety guarantee is the load-bearing half of the gate; it can mutate the cursor and, in an edge case, destroy the inbox. — Change: FR-R7 must compute the would-apply set **without** calling `apply_dispositions` (read inbox+dispositions and reconstruct via `_reconstruct`), OR add an explicit read-only mode that suppresses `record_processed`/`shred_inbox`; add an acceptance criterion "preview leaves `vipp-cursor.json` and the inbox byte-identical." — FR-R7 / NR-2.

- **[F-2]** **[BLOCKER]** The challenge-echo does **not** prove human presence and does **not** prevent one-click/auto-apply. The Phase-2 bearer token (stakeholder_run_server.py:86-103) authorizes **both** preview and ratify, and FR-R7's preview **returns the challenge in its HTTP response body**. Any token-holding client (or the datasource proxy itself) can chain `preview → read challenge → ratify(challenge)` with zero human involvement. The "never one-click / panel cannot auto-fill the challenge" claim (FR-R7, NR-2) holds only against a naïve button that ignores the preview response — not against any script. — Why: this is the single highest-risk write in the SDK; the stated human gate is security theater at the protocol level. — Change: the ratify secret must require **human-only knowledge not present in the preview response** (e.g. a value the server shows only out-of-band / as a non-machine-readable render, or requires the human to reconstruct), OR the gate must accept that token-holders can apply and re-scope the "human act" claim; and make `strict=True` (Origin allow-list + replay nonce) **mandatory** when the apply route is enabled (currently only "recommended" in OQ-5). — FR-R7 / NR-2 / OQ-5 / OQ-6.

- **[F-3]** **[BLOCKER]** Preview↔ratify integrity across two requests is unbound. `apply_dispositions` refuses only on **disposition-vs-inbox** seq mismatch (apply.py:107-114) — it does **not** know what the human previewed. Between preview and ratify a concurrent `run_vipp_negotiate`/serialize can produce a **new, internally-consistent** (inbox+dispositions) at a fresh `envelope_seq`; ratify then applies a would-apply set the human never saw, while every echoed `proposal_id` still "matches." — Why: the human ratifies content, but the write targets whatever is live at ratify time. — Change: FR-R7's challenge MUST bind `envelope_seq` **and** a content hash of the previewed would-apply set; ratify MUST refuse if the live inbox seq ≠ the challenge's seq (stale-preview → re-preview). — FR-R7.

- **[F-4]** **[SHOULD]** Challenge lifecycle is unspecified (issuance authority, server-side storage, TTL, single-use, seq-binding) — OQ-6 hand-waves it. The only existing server-side state is `_NonceStore` (stakeholder_run_server.py:47-63): **in-memory**, run-endpoint-scoped, 900 s TTL, lost on restart — and the endpoint is explicitly "on-demand/short-lived," so a restart between preview and ratify silently drops the challenge. — Why: without a defined store the gate is non-reproducible and either fails-open or fails-unusable. — Change: specify a **stateless signed challenge** (HMAC over `{seq, content-hash, expiry}` with a per-server key) or a persisted single-use store with TTL; state it in FR-R7 and resolve OQ-6. — FR-R7 / OQ-6.

- **[F-5]** **[SHOULD]** The cross-store funnel join is a **scope mismatch**, not just a "join bug." The VIPP inbox and dispositions are **project-global singletons** (`.startd8/vipp/proposals-inbox.json`, one `dispositions.json`; vipp_seam.py:58/78, context.py:39-49) — they carry **no session_id**. `ProposalStore` is **per-session** (proposals.py:61-64). FR-D1's funnel "synthesis items → staged → inbox → dispositions" therefore **cannot** be joined by `session_id` past the staged column; a two-session project shows session A's staged recs beside whatever session **last serialized** into the shared inbox → mis-attribution. — Why: the display can present one session's dispositions as another's, silently. — Change: FR-D1/D4/D5 must state that inbox/dispositions are project-global "last-serialized" state (not session-scoped) and render them as such (or key the whole funnel to the last-serialized session), never implying a session join. — FR-D1 / FR-D4 / FR-D5.

- **[F-6]** **[SHOULD]** FR-R4 mis-states the real API and the accept vocabulary. The signature is `update_disposition(domain, value_path, disposition)` — **three positional args, not** `update_disposition((domain, value_path), …)` (proposals.py:113). Downstream, `serialize_accepted_to_vipp` filters on the **exact literal** `rec.disposition == "accepted"` (stage.py:84) — so FR-R4 must write exactly `"accepted"` (proposals.py's own docstring says "approved", a trap). Also `update_disposition` returns `False`/no-ops if the `(domain, value_path)` isn't already staged (proposals.py:135-144), and the CLI serialize path never persists via `update_disposition` (it uses `--accept-all` in-memory or hand-edit; cli_panel.py:451) — so "matching the CLI" (§0) is imprecise. — Why: a wrong arg shape or a `"approved"`-vs-`"accepted"` drift makes accept→serialize silently drop everything. — Change: fix FR-R4's call shape, pin the literal `"accepted"`/`"rejected"`, and require the route to ensure the rec is staged before dispositioning. — FR-R4 / FR-R5.

- **[F-7]** **[SHOULD]** FR-C5's "inherit the CLI's confinement" is asserted, not grounded — and `apply_dispositions` **itself** does not confine. Symlink-reject/`0600`/no-clobber live in different modules: `resolve_confined_root` is in `ensure_posting` (context.py:79) and serialize (`serialize_buffer`, vipp_seam.py:96), symlink-reject of the inbox read is in `run_vipp_negotiate` (assistant.py:72-74) — but `apply_dispositions` reads the inbox/dispositions and calls `apply_proposal`/`shred_inbox` with no visible `resolve_confined_root`. — Why: FR-C5 is the whole write-posture safety claim; "inheritance" that isn't traced to a specific enforcing function can have gaps. — Change: FR-C5 must map **each** guaranteed guard (0600, symlink-reject, stale-seq, no-clobber, path-confinement) to the exact function that enforces it on the **apply** path, and flag any guard not enforced there for explicit addition. — FR-C5.

- **[F-8]** **[SHOULD]** "Reuse the run endpoint's fail-closed budget + idempotency" (FR-R3/FR-R6) only partly holds. The run endpoint's budget preflight + `run_key` idempotency are **run-shaped** (bind `{question, cap, roster}`; stakeholder_run_server.py:158-186) — §0 already caught `run_key` is wrong for extract. Separately, `run_vipp_negotiate`'s narrative/panel spend uses its **own** `max_cost_usd` ceiling + internal fingerprint idempotency (assistant.py:57, 85-101), **not** `BudgetManager.ensure_blocking_budget`. — Why: two of the three spend paths do not share the run endpoint's preflight, so "the same budget preflight" (FR-R3, FR-R6) overclaims and could leave a paid path unguarded. — Change: FR-R3 must specify a **new** extract preflight/estimate keyed on `(session_id + synthesis-checksum)`; FR-R6 must acknowledge negotiate-narrative spends via `max_cost_usd` and state how that ceiling is set/enforced from the endpoint. — FR-R3 / FR-R6 / OQ-4.
