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
| #6 | **Consensus / divergence signal** — deterministic $0 lexical-divergence over the independent R1 answers (challengers excluded) → high/mixed/low on the poll payload + Grafana chip + CLI. Honestly framed (lexical, not semantic); embeddings-ready `method` seam. **Unblocks #8.** | `stakeholder_panel/consensus.py`; `facilitate_run.facilitate_status`; `FacilitatePanel.tsx` |
| #8 | **Confidence-gated apply (FLAG)** — surfaces the #6 consensus on the apply **preview** (chip; n/a-visible) so a low-consensus set is flagged before commit. CRP caught 2 security bugs: a path-traversal read via an inbox-controlled `source_session_id`, and an M2 fingerprint cache-bust. Provenance threaded serialize→envelope→preview (top-level, outside every hash). | `_apply_preview` + `_apply_consensus`; `vipp_seam`/`vipp.models`/`vipp.apply`; `ApplyPanel.tsx` |
| #7 | **Live per-round progress** — `facilitate_status` returns bounded per-round summaries (excerpt-capped, challengers flagged) derived on read from the persisted rounds; the FacilitatePanel renders a live accordion that grows as rounds land (latest expanded) instead of a bare spinner. Additive, $0. | `facilitate_run._round_summaries`; `FacilitatePanel.tsx` |
| #9 | **Stale-run staleness report (observer)** — `facilitate_status` reports `stalled` when a non-terminal run's transcript hasn't advanced in `STARTD8_FACILITATION_STALE_SECS` (default 600s); the panel warns + points to Check-again. Observer-only (no reservation reap → no double-spend). | `facilitate_run.facilitate_status`/`_stale_after_secs`; `kickoff_view.mtime`; `FacilitatePanel.tsx` |
| #10 | **Cumulative facilitation-cost counter + documented alert** — `kickoff.facilitation.cost_usd_total` counter (labels project/posture/tier) emitted at the existing cost-emission point; PromQL alert documented (`increase(...[30d]) > CEILING`). Provisioning = operator/grafana-skill; distinct from the fail-closed budget. | `metrics.py:record_facilitation_cost` |

---

## 🎉 Roadmap complete — all higher-value + operational items shipped

Every item #1–#10 + ⭐ is shipped. The only remaining **non-code** follow-ons:

- **Re-enable GitHub Actions**  🟢 (infra decision — repo admin). Actions is disabled repo-wide, so the
  plugin CI gate (#3) + Python CI are dormant; re-enabling activates `tsc --noEmit` + build on every
  plugin change. **Anchor:** repo settings; `.github/workflows/grafana-plugin.yml`.
- **(optional/minor) Readout includes the facilitation synthesis narrative**  🟢 — `readout.py` renders
  Status/Assistant/Proposals/Pipeline but not the synthesis text (arguable; proposals are already there).
- **(operator) Provision the #10 cost alert** in Grafana from the documented PromQL (grafana skill).

---

## Suggested sequence (remaining)

> The arc, now complete: #1–#5 + ⭐ made facilitation *drivable and cheap*; #6–#10 made it
> *trustworthy* — believe the output (#6/#8), watch it happen (#7), aren't lied to when it breaks (#9),
> aren't surprised by the bill (#10). **All shipped.**

The only open follow-ons are non-code (see the section above): re-enable GitHub Actions (repo admin),
provision the #10 alert in Grafana (operator), and the optional readout-synthesis item.
