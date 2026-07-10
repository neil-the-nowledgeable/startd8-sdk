# Live Per-Round Progress (#7) — Implementation Plan

**Version:** 1.0 (Post-draft planning pass)
**Date:** 2026-07-10
**Requirements:** `LIVE_ROUND_PROGRESS_REQUIREMENTS.md` v0.1

---

## Planning discoveries

Grounded against `kickoff_view/models.py` (transcript), `facilitate_run.facilitate_status`,
`FacilitatePanel.tsx`, `run_kickoff_panel.py`.

| Draft assumption | Planning revealed | Impact |
|------------------|-------------------|--------|
| Per-round text is loadable at poll time | **Confirmed** — `facilitate_status` already loads `t.rounds` (for #6 consensus); `PanelRound{round_id,title,kind,entries}` + `PanelEntry{role_id,display_name,text,grounding,flags}`. | FR-1 is a thin add on data already in hand (Mottainai). |
| `rounds` = the whole run incl. synthesis | `t.rounds` = the **persona rounds (R1–R4)**; the R5 synthesis is a **separate** `t.synthesis` (already surfaced). | No overlap — `rounds` naturally covers the deliberation; the synthesis field is untouched. |
| Payload could bloat | 5 rounds × ~4 personas × full-text (~2KB) re-sent every 5s ≈ 40KB/poll. | **Excerpt-bound** each entry (FR-2) — the driver for summaries over full text. |
| Rounds are always complete | A **mid-round write has fewer entries than the roster** (transcript docstring) — partial rounds are normal. | FR-3: render 0..N entries without error. |
| Challengers need detection | `facilitation.CHALLENGER_IDS` (reused from #6/#8) — `role_id ∈ CHALLENGER_IDS`. | FR-4 deterministic, no new logic. |

## Approach

### Step 1 — a small pure helper (single source, testable)
- In `facilitate_run.py` (or a tiny local fn): `_round_summaries(rounds) -> list[dict]`:
  - for each `PanelRound`: `{round_id, title, kind, entries: [...]}`;
  - each entry: `{role_id, display_name, excerpt: text[:EXCERPT_CHARS] (+ "…" if truncated),
    grounding, is_challenger: role_id in CHALLENGER_IDS}`;
  - tolerant of dict OR object rounds (mirror `consensus._r1_texts`), empty/partial safe.
  - `EXCERPT_CHARS` a named constant (≈ 240, pending OQ-2).
- **Tests:** shape; excerpt truncation (+ ellipsis); partial round (0/1/N entries); challenger flag;
  empty rounds → `[]`.

### Step 2 — poll payload  [FR-1/3/7]
- `facilitate_status`: add `"rounds": _round_summaries(getattr(t, "rounds", []) or [])` to the returned
  dict (additive; unknown/error/halt paths keep their existing minimal returns → no `rounds` key there).
- **Test:** a completed scripted run's status carries `rounds` with R1 summaries + `is_challenger` flags;
  the existing fields are unchanged (superset).

### Step 3 — plugin types  [FR-5]
- `types.ts::FacilitateStatusResult` += `rounds?: RoundSummary[]`; add `RoundSummary`/`RoundEntry` types.

### Step 4 — `FacilitatePanel.tsx` live accordion  [FR-5/6]
- In the StatusView, render `status.rounds` as a `Collapse` accordion (reuse the `Collapse` pattern from
  `TriagePanel`), each round a section (title + entry count), personas + excerpts inside; challenger
  entries get a small "(adversary/skeptic)" label; latest round expanded (OQ-5). Grows as polls land.
  Keep the status header, SYNTHETIC & UNRATIFIED banner, and #6 consensus chip. **Real verify:**
  `npm ci && typecheck && lint && test && build`.

### Step 5 — docs
- README (Facilitate mode: live round accordion) + roadmap (#7 shipped).

## Requirement → step trace
FR-1→S1/S2 · FR-2→S1 · FR-3→S1/S2 · FR-4→S1 · FR-5→S3/S4 · FR-6→S4 · FR-7→S2.

## Risks
- **R1 — payload size.** Mitigated: excerpt-bound (FR-2) + it's a handful of short strings.
- **R2 — TS unverified.** Not a risk — plugin builds in-repo (real verify).
- **R3 — partial-round flicker** (entries appearing one poll at a time). Acceptable/desired — that IS the
  "watch it unfold" value; the UI just re-renders what's present.

*v1.0 — planning pass. #7 is a thin, additive lazy-derive over data `facilitate_status` already loads;
the one real design lever is excerpt-bounding to keep the 5s poll cheap.*
