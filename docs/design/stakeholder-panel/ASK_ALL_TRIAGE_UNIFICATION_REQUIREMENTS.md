# Ask-All Triage Unification (Q1 + provenance) — Requirements

**Version:** 0.2 (Post-audit — pre-CRP)
**Date:** 2026-07-09
**Status:** Draft (reflective loop; CRP pending)
**Cluster:** Q1 (triage the single-question ask-all) + V3-lite (per-item role provenance) — the thin
edge of A1 (unify the two panel artifacts). See `ROLE_BASED_INPUT_ENHANCEMENTS.md`.

---

## 0. Planning Insights (grounded audit)

| v0.1 assumption | Audit discovery | Impact |
|-----------------|-----------------|--------|
| "Point `build_triage` at the `.startd8/stakeholder-panel/` store" | The ask-all session is a **flat list of per-persona answers** (`role_id, question, text, grounding, value_path, cost_usd, model, …`) — **no `synthesis.text`, no sections**. `build_triage` requires a `KickoffTranscript` with `synthesis.text`. | **Q1 needs a small adapter** (`triage_ask_all`), not a re-point. FR-1/FR-2. |
| One extractor fits both | `extract_candidates` parses a *sectioned synthesis*; ask-all answers are freeform per-persona prose (one answer per persona). Feeding them to the section parser yields all-UNSTRUCTURED — losing the natural **one-candidate-per-persona-answer** structure + the role. | **Adapter maps 1 answer → 1 candidate**, role-tagged; reuse `classify` (input_kind) + `render_backlog_section`. FR-2/FR-3. |
| Provenance is a later feature | The ask-all data already carries `role_id` per answer — provenance is **free on this path**. `Candidate` has no `role` field today. | **Add optional `role` to `Candidate`** (V3-lite). FR-4. |
| A reader exists | `kickoff_experience/portal_build.py:83` already reads `.startd8/stakeholder-panel/`; no typed loader for a *single* ask-all session. | **Add a tiny loader** (list + load one session). FR-5. |
| Corroboration/dedup in scope | Ask-all is N personas × 1 question; "corroboration" = clustering similar answers — a separate concern (F3). | **Out of scope (NR-2)** — v1 is role-tagged pass-through. |

**Resolved:** the bridge emits **no OTel** today (O1 remains greenfield, out of this increment).

---

## 1. Problem
The cheap ($0.006), Grafana-drivable **single-question ask-all** produces role-based input that is
**stranded** — only the multi-round facilitation *synthesis* flows through triage/typing/backlog. Make
ask-all a first-class, typed, routable input source.

## 2. Requirements
- **FR-1 (adapter entry point).** `triage_ask_all(answers, *, question="") -> TriageReport` in
  `synthesis_bridge` — deterministic, `$0`, no writes. Accepts the parsed ask-all answer list.
- **FR-2 (1 answer → 1 candidate).** Each persona answer becomes one `Candidate`: `raw_text` = the answer
  (bounded/cleaned), `source_section` = the persona display/role, `input_kind` via the existing heuristic
  (`classify._infer_kind`), `lane = NON_DECIDABLE` (answers are input, never auto FIELD_LEVEL). An empty
  answer or a persona that `deferred` (flag) is skipped with a health note (nothing silently dropped).
- **FR-3 (reuse the pipeline).** The resulting `TriageReport` renders via the existing
  `render_backlog_section` / `to_markdown` — one report shape for both producers.
- **FR-4 (`role` provenance — V3-lite).** `Candidate` gains an optional `role: str = ""`; the adapter
  sets it from `role_id`. `to_dict` includes it; the backlog/report surfaces "— role" so a reader sees
  *who* said it. (Additive; facilitation candidates leave it "".)
- **FR-5 (loader).** A tiny `stakeholder-panel` session reader: `list_ask_all_sessions(project)` +
  `load_ask_all_session(project, sid)` returning the parsed answer list (+ the question).
- **FR-6 (CLI — unified, auto-detecting).** `kickoff panel triage <sid>` / `kickoff panel backlog <sid>`
  **auto-detect** the store: a facilitation session (kickoff-panel) → `build_triage`; an ask-all session
  (stakeholder-panel) → `triage_ask_all`. Same output/flags (incl. `--append`). A `--source ask-all|facilitation`
  override resolves ambiguity.
- **FR-7 (health/cost).** The report health surfaces the ask-all question + total spend (`sum(cost_usd)`)
  and any deferred/empty personas.

## 3. Non-Requirements
- **NR-1** no LLM on this path (deterministic `$0`); the opt-in `refine_input_kinds` may still be applied
  by the caller, unchanged.
- **NR-2** no corroboration/clustering/dedup (F3) — v1 is role-tagged pass-through.
- **NR-3** ask-all candidates are never FIELD_LEVEL / never auto-enter VIPP apply (same as UNSTRUCTURED).
- **NR-4** no new store/format; reads the existing `.startd8/stakeholder-panel/` JSON.

## 4. Open Questions (decisions)
- **OQ-1 — granularity:** one candidate per whole answer (recommended; low noise) vs split each answer
  into sentences (finer, noisier)?
- **OQ-2 — CLI shape:** auto-detect under the existing `kickoff panel triage/backlog` (recommended) vs a
  separate `kickoff stakeholders triage` command?
- **OQ-3 — `role` surfacing:** add `role` as a first-class `Candidate` field (recommended, V3-lite) vs
  fold the role into `source_section` only (no schema change)?

## Reference Audit
| Symbol | Where | Exists? |
|--------|-------|---------|
| ask-all store `.startd8/stakeholder-panel/<sid>.json` (answer list) | written by the run endpoint; read by `portal_build.py:83` | ✅ |
| `Candidate` / `classify._infer_kind` / `TriageReport` / `render_backlog_section` | `synthesis_bridge/` | ✅ (add `role`) |
| `build_triage` (needs `synthesis.text`) | `route.py:25` | ✅ (ask-all lacks synthesis → new adapter) |
| `Candidate.role` | `models.py` | ❌ → FR-4 |
| typed single-session ask-all loader | — | ❌ → FR-5 |

*v0.2 — post-audit. Q1 is a small adapter (not a re-point) + free provenance. Deterministic `$0`;
reuses classify + backlog. Ready for CRP after decisions.*
