# Facilitation & Stakeholder-Panel — Value Roadmap

**Status:** tracking doc (living)
**Created:** 2026-07-10
**Owner:** stakeholder-panel / kickoff_experience
**Context:** value-discovery pass after shipping **F1 (facilitation-over-HTTP)** — the multi-round
facilitation is now HTTP-drivable + has a Grafana `facilitate` mode + a cheap model tier.

> This doc tracks the enhancement backlog surfaced in the F1 value-discovery review.
> **Shipped so far:** the three quick wins (#1–#3), the ⭐ Triage-panel loop-closer, and #4/#5 — see the
> ✅ tables below. **Remaining open follow-ons: #6, #7, #8, #9, #10**, a minor readout item, and
> re-enabling GitHub Actions (see the "Remaining" sections). Each item is anchored to real code so it
> can be picked up without re-discovery.

## Framing — the key finding

The **entire synthesis→action pipeline already exists over HTTP** — `/stakeholders/{triage,
disposition, serialize, negotiate, extract, apply}` routes are all live
(`kickoff_experience/stakeholder_run_server.py`). The Grafana plugin originally surfaced only 3
(`run` / `apply` / `facilitate`) — an operator could *generate* a synthesis and *apply* pre-existing
proposals but couldn't *triage, route, or serialize* one without the CLI.
**That gap held most of the trapped value — it was the ⭐ item, now SHIPPED** (PR #185): the plugin's
`triage` mode drives triage → extract → disposition → serialize from the dashboard.

Effort key: 🟢 quick (<½ day) · 🟡 medium (1–2 days) · 🔴 bigger bet.

---

## ✅ Shipped in the quick-wins follow-up (`feat/facilitation-quick-wins`)

| # | Item | Anchor |
|---|------|--------|
| 1 | **Facilitation cost → OTel gauge at completion** — new `kickoff.facilitation.cost_usd` gauge (labels: project, posture, tier), emitted from the worker's terminal path so the cost panel isn't blind to the biggest single spend until a portal rebuild. | `metrics.py:record_facilitation_cost`, `facilitate_run.py:_worker` |
| 2 | **"Which mode?" in-panel guidance** — mode radio reframed as a decision aid (Run = survey / Facilitate = workshop / Apply = write gate) + clearer option labels. | `grafana-plugins/.../module.ts` |
| 3 | **Plugin CI typecheck/build gate** — GH Action runs lint + `tsc --noEmit` + vitest + webpack build on any plugin change, so the TS (uncovered by pytest) can't rot silently. | `.github/workflows/grafana-plugin.yml` |

## ✅ Shipped — the ⭐ loop-closer + more hardening

| # | Item | Anchor |
|---|------|--------|
| ⭐ | **Grafana Triage panel mode** — routes a finished synthesis into typed candidates + the paid extract → disposition → serialize write path (composes with Apply). CRP caught 3 shipped-route correctness bugs (domain, double-spend, undrained-inbox). | PR #185; `components/TriagePanel.tsx`, `stakeholder_run_server.py` |
| #4 | **Configurable concurrency cap** — `MAX_CONCURRENT_FACILITATIONS` overridable via env `STARTD8_MAX_CONCURRENT_FACILITATIONS`. | `facilitate_run.py:_max_concurrent_facilitations` |
| #5 | **Outside-view cache (Mottainai)** — reuse the R0 reference-class forecast across re-runs (keyed on objective+strategy+model); env opt-out `STARTD8_OUTSIDE_VIEW_NOCACHE`. | `facilitation.py:_ov_cache_*` |

---

## 🟡 Higher-value capabilities (remaining)

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

## 🔧 Operational & reliability hardening (remaining)

### Re-enable GitHub Actions  🟢 (infra decision — owner: repo admin)
Actions is **disabled repo-wide**, so the plugin CI gate (#3, shipped) and the Python CI are dormant.
Re-enabling (Settings → Actions → Allow) activates the `tsc --noEmit` + build gate on every plugin
change automatically — until then the plugin TS is only verified when someone builds it manually.
**Anchor:** repo settings; `.github/workflows/grafana-plugin.yml`.

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

## Suggested sequence (remaining)

> The theme of what's left: #1–#5 + ⭐ made facilitation *drivable and cheap*; #6–#10 make it
> *trustworthy* — believe the output (#6/#8), watch it happen (#7), aren't lied to when it breaks (#9),
> aren't surprised by the bill (#10).

1. **#6 consensus / divergence signal** — highest output-quality-per-effort; **unblocks #8**.
2. **#8 confidence-gated apply** — the guardrail #6 enables at the write boundary.
3. **#7 live per-round progress** — the UX win (data already persisted per round).
4. **#9 stale-run reaper** + **#10 budget alert** — reliability + cost governance once facilitation
   sees real usage.
5. **Re-enable GitHub Actions** — whenever the repo admin is ready (activates the dormant CI gate).

*(The minor readout item is optional / arguable — pick up only if the shareable readout needs the
synthesis narrative.)*
