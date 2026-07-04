# Consultation Quick Wins — Batch 1 Requirements

**Version:** 0.2 (Grounded — proportionate lightweight pass)
**Date:** 2026-07-04
**Status:** Draft → implement
**Scope:** the four S-effort quick wins from `ENHANCEMENTS.md` (#1, #2, TUI re-open, roster presets).

> These are small, low-risk, additive changes over the shipped consultation core. This is a
> **proportionate** requirements pass (grounded against the code, no full CRP — reserved for the
> larger native-continuity / serve work). Each FR is verified against real symbols (§Grounding).

---

## 0. Grounding (verified before writing)

| Assumption | Verified |
|------------|----------|
| Tokens→USD exists | `costs/pricing.PricingService.calculate_total_cost(model, in, out)` + `resolve_pricing` fallback for unknown models. Roster keys are `provider:model` → strip prefix before lookup. |
| Cost is persisted per turn already | No — only `input_tokens`/`output_tokens`/`time_ms` on the assistant `Turn`. Add `cost_usd`. |
| CLI reply has a race | Confirmed — only `--serve` has a lock; `facade.follow_up`/`retry_failed` mutate `session.json` with none. |
| TUI can re-open a session | No — `consultation_menu` only starts new; `store.list_sessions()` + `build_roster` + the existing `_consultation_followup_loop` are the pieces to compose. |
| Presets exist | No — `--models` is typed each run; `DEFAULT_COUNCIL` is the only saved roster. |

---

## 1. Requirements

### QW-1 — Dollar cost display
- **QW-1a.** Each assistant `Turn` gains an optional `cost_usd: float`. The engine computes it after a
  successful call from the turn's tokens + the model id via `PricingService.calculate_total_cost`
  (provider prefix stripped); unknown-model pricing degrades to the fallback, never crashes.
- **QW-1b.** The comparison surfaces show cost: `comparison_text`/`comparison_table` add a `$` per
  model; the web view badges show `$0.0123`; a session total is shown. Turns without `cost_usd`
  (older sessions) compute it at display time from tokens (best-effort), or show `—`.
- **QW-1c.** New `consult cost <id>` command prints per-model and total USD for a session.

### QW-2 — CLI concurrency guard
- **QW-2a.** A cross-process **advisory file lock** serializes mutating operations on a session
  (`follow_up`, `retry_failed`). A `fcntl.flock`-based lock (auto-released on process death — no stale
  marker) on `<session-dir>/.write.lock`.
- **QW-2b.** Concurrent CLI mutations on the same session are serialized (second waits or fails clearly),
  never interleaving a lost update on `session.json`. Non-mutating ops (`show`/`web`/`list`) are unaffected.
- **QW-2c.** `start` (new session, unique id) needs no lock (no contention).

### QW-3 — Session re-open in the TUI (FR-MMC-12)
- **QW-3a.** The consultation TUI offers, at entry, **New consultation** or **Open a saved one**.
- **QW-3b.** Open lists `store.list_sessions()` (most-recent first), loads the chosen session, rebuilds
  the roster from `session.roster` via `build_roster` (vision-gated per whether the session had images),
  shows the comparison, and enters the existing follow-up loop (all/one/retry).
- **QW-3c.** Models in the saved roster that are now unavailable (missing keys) are reported, not fatal.

### QW-4 — Roster presets (OQ-9)
- **QW-4a.** A preset store persists named rosters as JSON under the storage dir
  (`.startd8/consult-presets.json`): `save(name, [model_ids])`, `load(name)`, `list()`, `delete(name)`.
- **QW-4b.** `consult run --preset <name>` uses a saved roster; `--save-preset <name>` (with `--models`)
  saves the roster used. `consult roster list|show <name>|delete <name>` manages presets.
- **QW-4c.** `--preset` and `--models` are mutually exclusive on `run`; the default council is unchanged
  when neither is given.

---

## 2. Non-Requirements
- **NR-1.** No automated judging/ranking (still human-eval, consultation NR-2).
- **NR-2.** No schema migration for old sessions — `cost_usd` is additive/optional; absent = compute-at-display or `—`.
- **NR-3.** The CLI lock does not coordinate with a running `--serve` server beyond the existing serve
  lock; the target is the two-concurrent-CLI-replies race (serve already serializes its own writes).
- **NR-4.** Presets are local, unencrypted, single-user (like the rest of `.startd8`).

## 3. Open Questions
- **OQ-1.** Show cost in the *static* web view too (adds `cost_usd` to the embedded payload — yes, it's
  already persist-safe) vs serve-only. → Resolve: static too (it's just a number).
- **OQ-2.** Lock behavior on contention: block-with-timeout vs fail-fast. → Resolve: block briefly then
  fail clearly (avoid indefinite hang).

---

## 4. Grounding Reference (symbols touched)

| Symbol | Location | Change |
|--------|----------|--------|
| `Turn` | `consultation/models.py` | +`cost_usd: Optional[float]` |
| `ConsultationEngine._run_one` | `consultation/engine.py` | compute cost after ok turn |
| `comparison_text`/`comparison_table`/`render_html` | `consultation/view.py` | show $ |
| `ConsultationStore` | `consultation/store.py` | +`session_write_lock()` context mgr |
| `ConsultationService.follow_up`/`retry_failed` | `consultation/facade.py` | wrap in lock |
| `ConsultationMixin.consultation_menu` | `tui/mixin_consultation.py` | new/open branch |
| `consult_app` | `cli_consult.py` | +`cost`, +`roster` sub-cmds, +`--preset`/`--save-preset` |
| *(new)* `consultation/presets.py` | — | preset store |

---

*v0.2 — Grounded lightweight requirements for 4 S-effort additive quick wins. Proportionate to risk;
full reflective-loop/CRP reserved for the M-effort native-continuity work.*
