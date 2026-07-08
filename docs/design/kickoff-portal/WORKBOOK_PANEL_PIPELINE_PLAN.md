# Workbook Panel-Processing Pipeline (Increment 3) — Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-08
**Requirements:** `WORKBOOK_PANEL_PIPELINE_REQUIREMENTS.md` (v0.3)

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
