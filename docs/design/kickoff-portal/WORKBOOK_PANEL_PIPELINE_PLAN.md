# Workbook Panel-Processing Pipeline (Increment 3) — Plan

**Version:** 1.1 (Post-CRP R1 — apply gate rebuilt)
**Date:** 2026-07-08
**Requirements:** `WORKBOOK_PANEL_PIPELINE_REQUIREMENTS.md` (v0.4)

> **CRP R1 (Appendix A/C):** all 6 plan findings accepted. The v0.3 M-apply preview was broken (calling
> `apply_dispositions` mutates the cursor / can shred the inbox, S-1). **M-apply below is superseded by
> the requirements v0.4 FR-R7 redesign**: **pure-reconstruct preview** (byte-identical AC), a
> **stateless-HMAC challenge bound to `{envelope_seq, content-hash}`**, ratify **refuses on stale seq**
> (S-3), **`strict` mandatory** (S-2), explicit `resolve_confined_root` on the apply path (F-7), and the
> extract/negotiate budget paths corrected (S-6). The capability is **token-gated, not human-proof.**

## Planning summary

The pipeline logic (synthesis_bridge + vipp) is **fully built on the CLI** and reads/writes four
`.startd8/` stores. This increment is **surfacing + driving**, not new logic — every route threads
through the existing code paths. The apply gate — the one genuinely risky part — is reproducible over
HTTP as a **per-proposal preview→ratify challenge-echo** flow (§0). Sequenced so the riskiest step
(apply) is last and most-guarded.

## M-display — the pipeline funnel (read-only, $0)

**Goal:** surface the whole pipeline state; no writes, no spend.
- New pure builder (like `_stakeholders_section`) reading: transcript (recompute `build_triage`),
  `ProposalStore.load()`, `read_inbox`, `VippReport.from_json`. Render the funnel (FR-D1..D6) + the
  SYNTHETIC/UNRATIFIED + health warnings + `evidence_available` qualifiers.
- **OQ-2:** likely a **sibling dashboard** `cc-portal-kickoff-pipeline-{project}` (the funnel is large),
  with a compact summary + link in the main Workbook.
- **Exit:** the Workbook shows triage→staged→inbox→dispositions→apply-status for a real session.

## M-drive-$0 — safe endpoint routes (triage / disposition / serialize / negotiate)

**Goal:** Grafana-triggered $0 actions, reusing the Phase-2 endpoint's auth + confinement.
- Routes on the existing app: triage (FR-R2), disposition (FR-R4 → `update_disposition`), serialize
  (FR-R5), negotiate (FR-R6, narrative deferred). All inherit `0600` + symlink-reject + stale-seq; the
  disposition/serialize writes go through the CLI stores (no new write path).
- **Exit:** accept a rec → serialize → negotiate, all from the endpoint; stores + display reflect it.

## M-drive-paid — extract→stage (FR-R3)

**Goal:** the one paid pipeline step, behind the run endpoint's guards.
- Reuse fail-closed budget + dry-run estimate; idempotency keyed on **(session_id + synthesis checksum)**
  (OQ-4), not `run_key`. `extract_field_mappings` → `stage_recommendations` (draft/estimate).
- **Exit:** dry-run estimate → confirm → staged recommendations appear (draft), deduped on resubmit.

## M-apply — the gate (FR-R7), most-guarded, LAST

**Goal:** apply to the project source of record, provably human-ratified, never one-click.
- `POST …/apply/preview`: `apply_dispositions(confirm=lambda a,d: False)` → would-apply set + a
  ratification challenge. **No writes.**
- `POST …/apply/ratify`: body = `{proposal_ids:[…], challenge:"…"}`; endpoint confirm returns True only
  for ratified ids **and** a matching challenge → `_RATIFY_TOKEN` applied per-proposal. `force` never
  exposed (NR-8). Recommend `--strict` when this route is enabled (OQ-5).
- Plugin: a **two-screen** apply flow (preview list → type the challenge → ratify) — never a single button.
- **Exit:** on a throwaway project, preview shows the would-apply set; ratify writes only the echoed
  proposals; inbox shredded; a bogus/absent challenge writes nothing.

## M-pilot — household end-to-end + verdict

- Real run → triage → stage → accept → serialize → negotiate → apply-**preview** on household; apply's
  *actual write* only on a throwaway project. Written verdict.

## Traceability

| Req | Milestone |
|-----|-----------|
| FR-D1..D6 display | M-display |
| FR-R1 route surface | M-drive-$0 (+ paid/apply add routes) |
| FR-R2 triage / R4 disposition / R5 serialize / R6 negotiate | M-drive-$0 |
| FR-R3 extract→stage (paid) | M-drive-paid |
| FR-R7 apply | M-apply |
| FR-C1..C6 constraints | all milestones (cross-cutting) |
| FR-P1 pilot | M-pilot |

## Risks

1. **The apply write from a dashboard is the single highest-risk surface in the SDK** — it writes the
   project source of record. Mitigation: preview→ratify challenge-echo, per-proposal, no `force`,
   strict auth, throwaway-project-only real writes in the pilot. This is why apply is last + isolated.
2. **Posture shift** — the portal was read-only; the drive routes make it write-capable. Must inherit
   every CLI guard (FR-C5); no weaker path.
3. **Overloaded "proposal"** — implement with the precise types (`Recommendation` vs `EnvelopedProposal`
   vs `ProposedAction`); a wrong type at the serialize/apply boundary corrupts the gate.
4. **Cross-store assembly** — the funnel joins 4 stores by session_id/value_path/envelope_seq with no
   single artifact; a join bug could mis-attribute a disposition. Test the join explicitly.

---

## Appendix A — Accepted Suggestions (cross-model memory)

*(none yet — accepted findings land here with rationale.)*

## Appendix B — Rejected Suggestions (cross-model memory)

*(none yet — rejected findings land here with rationale so later reviewers don't re-propose.)*

## Appendix C — Incoming Review

#### Review Round R1 (independent CRP, 2026-07-08)

- **[S-1]** **[BLOCKER]** M-apply's preview step — `apply_dispositions(confirm=lambda a,d: False)` → "**No writes**" — is factually wrong. That call still records `REJECT`/no-inbox-entry dispositions as `consumed` in `vipp-cursor.json`, and an **all-REJECT** dispositions set leaves `consumed_all=True` so the preview **shreds the inbox** (apply.py:130-136, 145-147, 200-201). — Why: the plan's preview exit ("preview shows the would-apply set") assumes a read-only op that isn't. — Change: M-apply must build a genuinely read-only preview (reconstruct the would-apply set without calling `apply_dispositions`, or add a read-only mode suppressing `record_processed`/`shred_inbox`); add exit criterion "preview leaves the cursor + inbox byte-identical." — M-apply (see F-1).

- **[S-2]** **[BLOCKER]** M-apply's ratify design has no human-presence control and no preview↔ratify rebind. The Phase-2 bearer token authorizes both requests and the challenge is returned in the preview response, so a script chains preview→ratify unattended; and a concurrent negotiate between the two requests re-seqs the inbox so ratify applies an unpreviewed set (apply.py:107-114 only guards disposition-vs-inbox seq). — Why: "provably human-ratified, never one-click" is not achieved by the described mechanism. — Change: M-apply must (a) make the ratify secret human-only knowledge absent from the preview response and mandate `strict=True`; (b) bind the challenge to `envelope_seq` + a content hash and refuse ratify on live-seq drift; (c) add a test for "concurrent negotiate between preview and ratify → ratify refuses." — M-apply (see F-2, F-3).

- **[S-3]** **[SHOULD]** M-apply lacks a **challenge-lifecycle** deliverable. The "two-screen plugin flow (preview list → type the challenge → ratify)" is UX, not a security control; nothing in the plan specifies where the challenge is issued, stored, validated, its TTL, or single-use. The only server state today is an in-memory, run-scoped `_NonceStore` lost on restart (stakeholder_run_server.py:47-63). — Why: without server-side issuance/validation the gate is non-reproducible. — Change: add a M-apply task "challenge issuance/validation" — a stateless signed token (HMAC over seq+content+expiry) or a persisted single-use store — as an explicit deliverable, not just plugin UI. — M-apply (see F-4).

- **[S-4]** **[SHOULD]** Risk 4 understates the funnel problem: it is a **scope mismatch**, not a "join bug." The VIPP inbox and dispositions are project-global singletons (no session_id; vipp_seam.py:58/78), while `ProposalStore` is per-session (proposals.py:61-64) — they cannot be joined by session_id, so a 2-session project mis-attributes the shared inbox/dispositions to whichever session is displayed. — Why: the M-display exit ("shows triage→…→apply-status for a real session") reads as session-scoped end-to-end, which the stores can't deliver. — Change: M-display must render inbox/dispositions as project-global "last-serialized" state (or key the funnel to the last-serialized session) and the join test must assert no cross-session mis-attribution on a 2-session project. — M-display (see F-5).

- **[S-5]** **[SHOULD]** M-drive-$0's "disposition (FR-R4 → `update_disposition`)" needs the corrected API and an ensure-staged precondition. Real signature: `update_disposition(domain, value_path, disposition)` (3 positional args); serialize picks up only the literal `"accepted"` (stage.py:84), and `update_disposition` no-ops on an unstaged `(domain, value_path)` (proposals.py:135-144). — Why: the milestone exit ("accept a rec → serialize → negotiate") silently produces an empty inbox if the disposition string or arg shape is off. — Change: fix the call in M-drive-$0, pin `"accepted"`/`"rejected"`, require ensure-staged, and add an exit assertion "the accepted rec actually appears in the serialized inbox." — M-drive-$0 (see F-6).

- **[S-6]** **[SHOULD]** M-drive-paid's "reuse fail-closed budget + dry-run estimate" is only half-available. The run endpoint's preflight + dry-run are `run_key`/run-shaped (bind question/cap/roster); extract has no such dry-run, and negotiate-narrative (M-drive-$0's paid opt-in) spends through `run_vipp_negotiate`'s own `max_cost_usd` ceiling, not `BudgetManager` (assistant.py:57, 85-101). — Why: two paid paths don't inherit the run endpoint's preflight as the plan implies. — Change: M-drive-paid must build a new extract preflight/estimate keyed on `(session_id + synthesis-checksum)`; M-drive-$0 must state how negotiate-narrative's `max_cost_usd` is set/enforced from the endpoint. — M-drive-paid / M-drive-$0 (see F-8).
