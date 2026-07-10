# Agentic Workbook — Value Roadmap (post-ship enhancement backlog)

**Date:** 2026-07-09
**Status:** Backlog / advisory
**Context:** The Agentic Workbook cockpit (M1–M5) shipped to `origin/main` (`04fb891e`). This doc
captures the discovered value/quick-win/architectural backlog so it isn't lost (Mottainai).
**Relates to:** `AGENTIC_WORKBOOK_REQUIREMENTS.md`, `AGENTIC_WORKBOOK_PLAN.md`.

---

## Core value gap

The cockpit today shows **state and history** (field tables, raw transcript, pending queue). It does
**not** yet tell the user **what to do next**, show **progress over time**, or hand them a
**shareable output**. Almost everything below closes one of those three gaps using data we already
persist in the `AgenticView` / session snapshot. **Nearly all of it is $0 deterministic** (bucket 1);
the only cost-bearing idea is an *optional*, gated LLM session summary. None of it generates the
user's real content — it surfaces and routes the user's **own** decisions and state (inside the
SDK's bucket boundary).

> The single most underused fact: the Assistant tab renders a *raw transcript* — the lowest
> value-per-pixel surface — when the snapshot already contains everything needed for a
> "session at a glance."

---

## Tier 1 — Quick wins (≈½ day total, $0, no new stores) — **IN PROGRESS**

| # | Suggestion | User value | Reuses |
|---|---|---|---|
| 1 | **"Your next step" callout** on the Status tab (and empty states) | Tells the user what to *do*, not just what *is* — the biggest UX gap | `ranking.next_action(state, readiness)` (already used by `field_states`) folded into `build_agentic_view` |
| 2 | **Readiness "big number"** panel ("62% ready · 3 blocked · 5 ok") | At-a-glance progress; markdown big-number = embed-consistent | `KickoffState.attention_counts` / `counts` |
| 3 | **"Session at a glance"** deterministic summary heading the transcript ("2 surveys, 1 assess, 3 proposals, 2 blockers, cost ≈$0.003") | Turns the least-valuable panel into the most-scannable | derived from `snapshot.turns` (tool-call names + roles we already store) |
| 4 | **Surface `stop_reason`** ("stopped at budget cap — raise `--max-cost`") | Transparency about *why* the assistant stopped | thread the last `AgenticResult.stop_reason` into the snapshot |
| 5 | **Actionable session-end hint** — print the exact `kickoff portal --dynamic --provision …` command | Adoption: users don't know the cockpit exists or how to refresh it | extend `_persist_kickoff_snapshot` |
| 6 | **UID length preflight + hash-suffix** | Reliability — we *hit* this (>40-char UID silently fails to provision) | `workbook_v2_uid` |

---

## Tier 2 — Functional capabilities (≈1–2 days each, $0)

- **`startd8 kickoff cockpit` — a CLI/TUI parity view. — ✅ SHIPPED.** A Rich terminal render of the
  same `AgenticView` (Status / Assistant / Proposals) delivers the cockpit's value **without a running
  Grafana** — realizing FR-3's "the dashboard *and any CLI/TUI view* derive from the same oracle."
  `kickoff_experience/cockpit_view.py` + `startd8 kickoff cockpit [--plain]`; a parity test asserts the
  terminal and the board agree on the next step + proposal ids. The stop-reason explanation was pulled
  into one canonical `session_snapshot.stop_reason_hint` (used by both surfaces).
- **`startd8 kickoff proposals` — list + numbered apply.** The Proposals tab shows the two-step
  `negotiate && apply`; a CLI helper that lists pending proposals and applies your pick closes the
  confirm loop from "copy-paste a command" to "pick #2." (CLI stays sole writer — NR-2 intact.)
- **Shareable "kickoff readout" export — ✅ SHIPPED.** `kickoff_experience/readout.py` +
  `startd8 kickoff readout [--format md|html] [--out FILE]`: a self-contained Markdown/HTML doc
  rendering the same `AgenticView` (readiness, next step, session summary, pending items + confirm
  commands). XSS-safe HTML (every model/session value `html.escape`'d). The higher-value output — an
  emailable/attachable deliverable.

---

## Tier 3 — Architectural leverage (higher payoff, bigger lift)

- **Promote the session snapshot to the `AgenticSession` layer — ✅ SHIPPED.** The presentation-
  neutral core (model + transcript normalization + generic builder) moved to
  `agents/session_snapshot.py` (stdlib-only, no cycle); `kickoff_experience/session_snapshot.py`
  re-exports it (compat) and adds the kickoff policy (redaction, Loki, on-disk persistence).
  `AgenticSession.to_snapshot(*, redactor=…)` is the reusable primitive — **any agentic surface**
  (consultation, concierge, future Prime) now gets a durable, dashboard-able session for free, with
  redaction dependency-injected. Biggest leverage item; 1313 tests green after the relocation.
- **First-class v2 `logs`/datasource panel constructor** in `dashboard_creator/v2`. Today the Loki
  panel is a hardcoded dict inside `portal_spec_v2`. The v2 module only ships `text`/`table`;
  extracting a tested `logs_panel(...)` **broadens the entire dynamic-dashboards capability** — every
  future v2 dashboard can bind a live datasource.
- **Fix the OTel Meter→Mimir metrics path — ✅ SHIPPED (readiness burndown).** The "`emit()`=0 Mimir
  metrics" gap is closed: `kickoff_experience/metrics.py` emits `kickoff.readiness.percent` /
  `kickoff.session.cost_usd` / `kickoff.proposals.pending` / `kickoff.fields.blocked` as real OTel
  **gauges** (labeled `project`), wired via the idempotent `auto_configure_otel()` (opt-in, auto-probes
  `:4317`, no-op without a collector). Emitted on every cockpit build (`portal_build`) and every
  `kickoff cockpit` run. The Status tab gained a **"Readiness over time"** timeseries panel bound to
  the `mimir` datasource (`kickoff_readiness_percent{project="…"}`), additive + graceful-degrade.
  **Live-verified end-to-end**: Meter → otel-collector (`:4317`) → Mimir (`:9009`) → Grafana `mimir`
  datasource → series present (names are `kickoff_readiness_percent` etc. — dots→underscores, no unit
  suffix). *Infra note:* the running dev stack already has the collector + Mimir + `mimir` datasource;
  the repo's `docker-compose.loki-stack.yml` does not (logs-only) — a fuller compose is future ops work.
  Remaining bonus: a cost-over-time panel (the `kickoff_session_cost_usd` gauge is already emitted).
- **Snapshot `schema_version` upgrade seam** (`_upgrade(dict)` registry). We built the *degrade*
  contract; add an *upgrade* path so old snapshots keep rendering after a bump (Mottainai).

---

## Operational & governance

- **Session-history ledger** (`.startd8/kickoff/sessions.jsonl`, compact — cost/readiness/counts, not
  transcripts) → enables **"you went 40% → 62% this session"** (Kaizen progress delta). Same kickoff
  dir, no store-philosophy violation.
- **Audit/activity feed** from the transcript-logger pattern (proposals made / confirmed / discarded
  as structured Loki events) → a trust/provenance surface + the basis for a **shared founder ↔
  FDE/VIPP collaboration view** on the Proposals queue.
- **Retention/purge** (`kickoff cockpit --purge`) + documented Loki retention — the redacted
  transcript is still a persistent surface; give users a clean-up lever.
- **Grafana alert** ("proposal pending > 24h" / "readiness stalled") once metrics exist — turns the
  passive board into an active nudge.

---

## Higher-value outputs

- **Shareable kickoff readout** (Tier 2) — the primary "communicable deliverable" win.
- **Decision log** — the confirmed proposals (VIPP dispositions + `docs/kickoff/confirmed.yaml`) are a
  decision record; "here's what you've decided so far" is high narrative value.
- **(Optional, cost-bearing, gated) LLM session summary** for the Assistant tab — one cheap pass
  ("resolved X, Y; open: Z"). Arguably bucket-3 integration, not bucket-4 content; **gate it**.

---

## Recommended sequence

1. **Tier-1 bundle (#1–#6)** — one ½-day increment, all $0, immediately visible value. *(started here)*
2. **`startd8 kickoff cockpit` CLI parity view** — delivers value to non-Grafana users; pays off FR-3.
3. **Meter→Mimir fix → readiness burndown** — one bug fix that unlocks the progress story.
