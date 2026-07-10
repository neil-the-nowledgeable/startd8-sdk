# Live Per-Round Progress (#7) — Requirements

**Version:** 0.3.1 (Post lessons + design-principle hardening — ready for CRP)
**Date:** 2026-07-10
**Status:** Draft

---

## 0. Planning Insights (Self-Reflective Update)

> Planning against the real transcript + `facilitate_status` mostly **confirmed** the draft (a thin,
> additive, low-risk feature). Key resolutions:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Per-round text needs a new load | `facilitate_status` **already loads `t.rounds`** (for #6 consensus) | FR-1 is a lazy-derive on data in hand — no new I/O. |
| `rounds` might overlap the synthesis | `t.rounds` = persona rounds R1–R4; R5 synthesis is a **separate** `t.synthesis` (already surfaced) | No overlap; existing `synthesis` field untouched. |
| Rounds are complete | A mid-round write has **fewer entries than the roster** — partial rounds are normal | FR-3: render 0..N entries, no error. |
| Payload is fine | full-text × personas × rounds re-sent every 5s ≈ 40KB/poll | **Excerpt-bound** (FR-2) — the real design lever. |

**Resolved open questions:** OQ-1 → **(b) per-persona excerpt summaries** (payload discipline); OQ-3 →
**rounds only** (NR-4); OQ-4 → **flag + small label**; OQ-5 → **latest round expanded**. OQ-2 (excerpt
length N) → default **240 chars**, confirmable by the sponsor (§4).

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified: `facilitate_status`, `KickoffTranscript.rounds`,
  `PanelRound.{round_id,title,kind,entries}`, `PanelEntry.{role_id,display_name,text,grounding}`,
  `facilitation.CHALLENGER_IDS`, `FacilitateStatusResult` all exist. New: an additive `rounds` field +
  `_round_summaries` helper + `RoundSummary`/`RoundEntry` TS types.
- **[Single-source]** — the summary is derived by ONE helper reused nowhere-else-competing; challenger
  detection reuses the `CHALLENGER_IDS` constant (as #6/#8 do), not a re-listed set.

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Mottainai / Hitsuzen]** — derived on read from the already-persisted rounds (no new persistence, no
  generation); the signal is fully determined by the transcript.
- **[Genchi Genbutsu]** — binds to the **real** `t.rounds` entries (+ the real `CHALLENGER_IDS`), not a
  reconstructed proxy; additive field, existing poll fields untouched.
- **[Accidental-Complexity]** — one pure helper, no special-casing; partial/absent rounds fall out of the
  same code path.
- **[Context-Correctness]** — absent/halted/errored transcript → no `rounds` key (not a `None` that the
  UI must special-case); the UI simply renders `status.rounds ?? []`.

---

## 1. Problem Statement

The multi-round facilitation runs for **minutes** (fire-and-poll). The Grafana `FacilitatePanel` shows a
bare spinner + "round N" until the **final synthesis** lands, then everything appears at once. #7 surfaces
each round's content **as it lands** so the operator watches the deliberation unfold (and can bail early
if a round goes off-track). The per-round data is **already persisted** in the transcript — this is a
surfacing feature, not new generation. Additive, $0, read-only.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `KickoffTranscript.rounds[].entries[]` | Per-round, per-persona text persisted (`role_id`, `text`, …) | Not exposed on the poll payload |
| `facilitate_status` poll payload | Returns `rounds_completed` (a count) + final `synthesis` | No per-round content while in progress |
| `FacilitatePanel` StatusView | Spinner + "round N" until terminal | No live per-round view |

## 2. Requirements

- **FR-1 — Per-round summaries on the poll payload.** `facilitate_status` returns a `rounds` list, each
  `{round_id, title, kind, entries: [{role_id, display_name, excerpt, grounding, is_challenger}]}`,
  derived from the already-persisted `t.rounds` (lazy, same pattern as #6 consensus).
- **FR-2 — Bounded excerpt (payload discipline).** Each entry's `excerpt` is the first N chars of its
  text (N a named constant), NOT the full text — the poll repeats ~every 5s, so the payload must stay
  small. The full text is what the final synthesis + the CLI are for.
- **FR-3 — Partial rounds render cleanly.** A mid-round write has fewer entries than the roster; the
  summary shows whatever entries exist (0..N) without error — the point is to watch it fill in.
- **FR-4 — Challenger labelling.** Entries whose `role_id ∈ CHALLENGER_IDS` are marked `is_challenger`
  so the UI can label adversary/skeptic voices (cheap; already known at this layer).
- **FR-5 — Grafana live accordion.** `FacilitatePanel` renders a per-round accordion that grows as rounds
  land (each round a collapsible section; personas + excerpts inside), keeping the existing status header,
  SYNTHETIC & UNRATIFIED banner, and #6 consensus chip.
- **FR-6 — Honest framing.** Excerpts are synthetic persona output; keep the banner; excerpts are partial
  previews, not the deliberation of record.
- **FR-7 — Graceful edge cases.** A halted run (R0 prep, no R1–R5) → empty/absent `rounds` + the existing
  halt surface; unknown/errored/absent transcript → no `rounds` (existing status untouched).

## 3. Non-Requirements

- **NR-1 — No full per-entry text on the poll** (payload discipline; excerpts only — see OQ-1).
- **NR-2 — No new persistence / no new generation** — derived from the persisted transcript on read.
- **NR-3 — No change to the CLI** — `run_kickoff_panel.py` already prints rounds live via `on_round`.
- **NR-4 — No R0 prep surfacing** in this increment (rounds only — the roadmap's framing; see OQ-3).
- **NR-5 — No change to existing poll fields** (additive `rounds` only).

## 4. Open Questions

- **OQ-2 — Excerpt length N (the one sponsor lever left).** `EXCERPT_CHARS` default **240** — enough to
  read a persona's gist, small enough that 5 rounds × ~4 personas stays a few KB per 5s poll. Confirm.

*(OQ-1/3/4/5 resolved in §0: excerpt summaries; rounds only; challenger flag+label; latest expanded.)*

---

*v0.1 — draft.*
*v0.2 — post-planning: confirmed thin/additive; excerpt-bounding is the design lever; 4 OQs resolved.*
*v0.3 — lessons hardening: phantom audit clean; single-source helper + reused CHALLENGER_IDS.*
*v0.3.1 — design-principle hardening: Mottainai/Hitsuzen (derive-from-persisted), Genchi-Genbutsu,
Accidental-Complexity, Context-Correctness. One minor OQ (excerpt length) for the sponsor. Ready for CRP.*
