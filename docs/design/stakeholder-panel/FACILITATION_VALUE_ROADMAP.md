# Facilitation & Stakeholder-Panel — Value Roadmap

**Status:** tracking doc (living)
**Created:** 2026-07-10
**Owner:** stakeholder-panel / kickoff_experience
**Context:** value-discovery pass after shipping **F1 (facilitation-over-HTTP)** — the multi-round
facilitation is now HTTP-drivable + has a Grafana `facilitate` mode + a cheap model tier.

> This doc tracks the enhancement backlog surfaced in the F1 value-discovery review. The three
> mechanical quick wins (**#1–#3**) were spun into a follow-up PR (`feat/facilitation-quick-wins`);
> everything below the line remains for tracking and further consideration. Each item is anchored to
> real code so it can be picked up without re-discovery.

## Framing — the key finding

The **entire synthesis→action pipeline already exists over HTTP** — `/stakeholders/{triage,
disposition, serialize, negotiate, extract, apply}` routes are all live
(`kickoff_experience/stakeholder_run_server.py`). But the **Grafana plugin surfaces only 3 of them**
(`run` / `apply` / `facilitate`). An operator can *generate* a synthesis and *apply* pre-existing
proposals from the dashboard, but cannot *triage, route, or backlog* a synthesis without the CLI.
**That gap holds most of the trapped value** — it is the ⭐ item below.

Effort key: 🟢 quick (<½ day) · 🟡 medium (1–2 days) · 🔴 bigger bet.

---

## ✅ Shipped in the quick-wins follow-up (`feat/facilitation-quick-wins`)

| # | Item | Anchor |
|---|------|--------|
| 1 | **Facilitation cost → OTel gauge at completion** — new `kickoff.facilitation.cost_usd` gauge (labels: project, posture, tier), emitted from the worker's terminal path so the cost panel isn't blind to the biggest single spend until a portal rebuild. | `metrics.py:record_facilitation_cost`, `facilitate_run.py:_worker` |
| 2 | **"Which mode?" in-panel guidance** — mode radio reframed as a decision aid (Run = survey / Facilitate = workshop / Apply = write gate) + clearer option labels. | `grafana-plugins/.../module.ts` |
| 3 | **Plugin CI typecheck/build gate** — GH Action runs lint + `tsc --noEmit` + vitest + webpack build on any plugin change, so the TS (uncovered by pytest) can't rot silently. | `.github/workflows/grafana-plugin.yml` |

---

## ⭐ The loop-closer (highest value)

### Grafana "Triage" panel mode — operate the whole pipeline from the dashboard  🔴 (🟡 for a read-only first slice)

The routes exist; only the UI is missing. A `triage` mode:
- pick a completed `session_id` → `POST /stakeholders/triage` → render typed candidates
  (**field-level / non-decidable / residual**),
- show the rendered backlog section (`render_backlog_section`), guarded "append to
  `ENHANCEMENTS_BACKLOG.md`",
- per-candidate `POST /stakeholders/disposition`.

**First slice (🟡):** read-only — candidates + backlog preview, no writes. Delivers ~80% of the value.
**Why it matters:** makes the panel→bridge→VIPP funnel fully operable from Grafana; realizes the
"useful role-based input is a differentiator" thesis. **Anchors:** routes `_triage` / `_disposition`
in `stakeholder_run_server.py`; `synthesis_bridge.build_triage` / `render_backlog_section`; new
`grafana-plugins/.../components/TriagePanel.tsx` mirroring `ApplyPanel.tsx`.

---

## 🟡 Higher-value capabilities

### #6 — Consensus / divergence signal on the synthesis  🟡
Today the synthesis carries no measure of whether the personas *agreed*. Add a **deterministic $0**
divergence metric (lexical or embedding distance across the R1 persona answers) → "consensus:
high / mixed / low". Turns the output from a narrative into decision-support; cheap.
**Anchor:** `stakeholder_panel/facilitation.py` (R1 answers in the transcript); surface on the poll
payload (`facilitate_status`) + the `FacilitatePanel` header.

### #7 — Live per-round progress instead of a spinner  🟡
The transcript already persists **per round** and `facilitate_status` returns `rounds_completed`, but
the UI shows a spinner until the *final* synthesis. Surface each round's summary as it lands → the user
watches the deliberation unfold over the minutes-long run. Data's already there.
**Anchor:** extend `facilitate_status` to return round summaries; render them in `FacilitatePanel.tsx`.

### #8 — Confidence-gated apply (depends on #6)  🟡
Surface the consensus/divergence score **and** the UNRATIFIED banner in the `apply/preview` screen, so
a low-consensus synthesis is visibly flagged *before* it's written to the project source of record.
Reinforces VIPP's "ground truth adjudicates, never originates" at the write boundary.
**Anchor:** `_apply_preview` route; `ApplyPanel.tsx`.

---

## 🔧 Operational & reliability hardening

### #4 — Configurable concurrency cap  🟢
`MAX_CONCURRENT_FACILITATIONS = 4` is a hardcoded module constant — operators can't tune it per host.
Promote to config/env. **Anchor:** `facilitate_run.py`.

### #5 — Cache the R0 outside-view per project (Mottainai)  🟢–🟡
The outside-view / reference-class pass is now *project-derived*, not question-derived — identical
across re-runs, yet it pays a premium LLM call every time. Cache per project → free re-runs.
**Anchor:** `facilitation.py` outside-view pass.

### #9 — Stale-run reaper / heartbeat staleness  🟡
A hard server restart kills the worker thread but leaves the `IdempotencyStore` reservation
`in_progress` until TTL. The client bounded-poll (H-16) hides it from the user, but the server-side
reservation leaks. Add a staleness check in `facilitate_status` (transcript last-write older than N min
→ report `stalled`). **Anchor:** `facilitate_run.py:facilitate_status`, `stakeholder_run.py:IdempotencyStore`.

### #10 — Per-project facilitation budget + Grafana alert  🟡
With #1's gauge in place, add a cumulative **counter** for facilitation spend + an alert rule when a
project crosses a monthly ceiling. Cost governance for the one expensive path.
**Anchor:** `metrics.py`; a Grafana alert rule / dashboard.

### (minor) Readout includes the facilitation synthesis narrative  🟢
`readout.py` renders Status / Assistant / Proposals / Pipeline but not the synthesis *text*. Arguable —
proposals (downstream) are already there. **Anchor:** `readout.py`.

---

## Suggested sequence

1. **⭐ Triage panel mode** (read-only slice) — the loop-closer; the strategic differentiator.
2. **#6 consensus signal** — highest output-quality-per-effort; unblocks #8.
3. **#5 outside-view cache** + **#4 configurable cap** — cheap operational wins.
4. **#9 stale-run reaper** + **#10 budget alert** — reliability + cost governance once facilitation
   sees real usage.
