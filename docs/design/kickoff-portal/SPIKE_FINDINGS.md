# Grafana Kickoff Portal — Iteration-1 Spike Findings (Option 3)

**Date:** 2026-07-07
**Artifact:** `spike/build_kickoff_portal.py` → provisioned dashboard `cc-portal-kickoff-household-o11y`
**Evidence:** `spike/kickoff-portal-snapshot.png` (rendered snapshot)
**Question:** Is Grafana a good enough UI/UX for the kickoff experience? (read-only slice)

---

## What was built (in ~1 iteration, $0 LLM)

A real kickoff dashboard, generated through the **same `DashboardCreatorWorkflow` jsonnet path** the
online-boutique portal uses (no hand-authored JSON), **provisioned live** to Grafana `:3000`.
Two revisions:
- **v1 (provenance heuristic):** derived confirmation from each domain's `provenance_default` — a rough
  file-level signal (`spike/kickoff-portal-snapshot.png`).
- **v2 (canonical, option-1 read slice — current):** derives from the **canonical `KickoffState`**
  (`kickoff_experience/state.py`, the `$0` extraction HTMX/TUI use — FR-3, single source of truth).
  Real per-field **attention** (ok/review/blocked/backlog) over **87 fields / 7 manifests**
  (78 ok · 4 review · 4 blocked · 1 backlog). What/Why/Who **cited** from
  `concierge/core.explain_input_domain` (single-source vocab). 14 panels.
  Evidence: `spike/kickoff-portal-canonical.png`. **Option 1** = bake state into panels + re-provide on
  write (no endpoint, no TSDB, no new exposure); reachability for the future option-2 write loop is
  **confirmed** (Grafana pod → `host.docker.internal`).

## Promoted to a shipped command (2026-07-07)

The spike is now a real capability: **`startd8 kickoff portal`** (read-only by default; `--provision URL`
pushes to Grafana). Module `src/startd8/kickoff_experience/portal_spec.py`
(`build_kickoff_portal_spec(state, project)` — pure, derives from canonical `KickoffState`), CLI command
in `cli_concierge.py`, tests `tests/unit/test_kickoff_portal_spec.py` (9, green). Still **option-1**
(bake + re-provision; no live pipeline). Verified generate-only + provision against household.

### Concept & naming — the Digital Project Workbook

The portal is framed as the **Digital Project Workbook**: a **dynamic, query-based** evolution of
Brooks' workbook (*"Why Did the Tower of Babel Fail?"*, The Mythical Man-Month), which was **static**
(paper/microfiche). It is the single shared structure holding every foundational project decision, so
the team sees the whole — here generated live from the canonical project state. The **stakeholder panel
is a key part** of the Workbook. To make room and remove a `p<tab>` collision, the stakeholder command
was **renamed `kickoff panel` → `kickoff stakeholders`** (canonical), with `kickoff panel` (and
top-level `panel`) kept as **hidden one-release deprecated aliases**. The dashboard title is now
`"<project> — Digital Project Workbook"`.

## Evidence-based assessment

| Surface | Verdict | Evidence |
|---------|---------|----------|
| **Markdown/content panels** (What/Why/Who, per-domain field state, provenance badges) | ✅ **Strong** | Renders cleanly + readably — intro + legend table, collapsible per-domain rows, nested real values (targets 95 %/100 %, stack fastapi/sqlmodel/htmx, budgets), ✅/🟡 confirmation badges. This is a legitimately good *read/status* surface. |
| **Numeric gauge + stat chips** | ⚠️ **Renders live, but data is fake** | Snapshot shows "No data" (snapshots don't run queries); confirmed `vector(0.25)` **does** evaluate in Mimir → the live gauge shows 25 %. BUT those are **baked literals**, not live kickoff metrics. Real, moving numbers need the M1 emit seam. |
| **Confirmation burndown (time-series)** | ⛔ **Not demonstrable** | No time-series without the emit seam (M1) + history. Deferred as planned. |
| **Write/interactive** | ⛔ **Not in this slice** | Needs the chat-panel fork (M4). |

**Provisional verdict: COMPLEMENTARY (leaning strong-complementary).** Grafana is a genuinely good
**read / status / self-monitoring** surface for kickoff — the content panels are better than expected.
It is **not** a form-filling surface, and its *live-data* value is entirely gated on the M1 emit seam,
which the parallel CRP found is more than "reuse GUIDANCE" (see below). HTMX/CLI stays primary for
capture; Grafana owns the at-a-glance read + history + self-monitoring pane.

## The "No data" caveat, stated honestly

The snapshot's "No data" on the gauge/chips is a **snapshot limitation**, not the live behavior
(`vector()` evaluates live). But it accidentally exposes the real truth: **static `vector()` literals
are not a data pipeline.** A kickoff portal that actually *tracks* confirmation over time needs real
metrics in Mimir — which is exactly the M1 work the CRP scrutinized.

## Parallel CRP — 3 blockers that reshape M1/M2 (persisted in Appendix C of both docs)

The independent CRP (F-1…F-7 in REQUIREMENTS Appendix C, S-1…S-5 in PLAN Appendix C) verified claims
against real code and found the **live-data path does not actually connect** as v0.3 assumed:

1. **[BLOCKER F-1] `CommsKind.GUIDANCE` is a query dead-end.** `OTLPTransport.query()` *explicitly
   raises* for GUIDANCE (otlp_transport.py:121-129). Records emitted as GUIDANCE can never be read
   back via OTLP/Tempo → the FR-2 "reuse GUIDANCE" decision is functionally broken, not just an overload.
2. **[BLOCKER F-2] The emit seam produces no Mimir metrics.** `build_transport().emit()` writes a
   payload-less envelope span (Tempo) + a local JSON file — **zero metrics**. But FR-5's completeness/
   burndown panels are Mimir/PromQL. Per REQ-PRO-001, ContextCore (not startd8) owns the metric-ified
   gauges — that metric-ifier is out of scope and absent from M0. **Panels can render empty on a green M0.**
3. **[BLOCKER F-3] The idempotent-`record_id` claim is false + self-contradictory.** `_derive_record_id`
   keys on `timestamp_ns` (default now()) → re-emit is *not* idempotent; and identity-overwrite would
   collapse the very history the burndown needs.

Plus SHOULDs: capture.py rejects not-yet-present keys (breaks "capture-a-value"); confirm≠capture are
different paths; the "proven path" only proves *provisioning* (static text + `vector(N)` — exactly what
this spike confirmed); unsigned-plugin loading contradicts "M0 needs no work" + shared-stack blast
radius; Infinity has no standing read-only endpoint; the fork is likely two plugins; FR-9's rubric
lacks falsifiable thresholds.

## Implication for the roadmap

- The **read/presentation bet is validated** — cheaply, and with a real artifact on screen.
- The **live-data bet (M1→M2) is not** — the emit→metric→panel chain is genuinely broken as specced.
  Before building M1, resolve F-1/F-2/F-3: either emit **real OTLP metrics** to Mimir (not GUIDANCE
  comms records), or read current-state via **Infinity over the CLI `state.json`** (no TSDB at all for
  the live view) and reserve the TSDB strictly for append-only history.
- Next: triage the CRP suggestions (Appendix C → A/B), then decide M1's data path deliberately.
