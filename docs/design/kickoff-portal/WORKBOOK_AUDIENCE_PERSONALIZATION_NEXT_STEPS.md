# Workbook × Audience Personalization — Research & Next Steps

**Date:** 2026-07-08 · **Status:** research complete, not built. This is the **audience-on-the-Workbook**
thread — a focused companion to the broader capability spec in `../dynamic-dashboards/`.

The question: **can the kickoff `audience` (persona) lens personalize the Digital Project Workbook
dashboard the way it already personalizes the CLI/web/TUI?** Yes — and there are **two eras**: a modest
win shippable **now** on the classic schema, and a much better **live-switching** end state after the
Grafana ≥13.1 upgrade.

---

## 1. What the audience feature is (review findings)

Recent kickoff work (`concierge/audience.py`, `PERSONA_EXPERIENCES_{REQUIREMENTS,PLAN}.md` v0.8, M1–M5
shipped). **One experience, two orthogonal knobs — persona as a lens, not three parallel flows.**

- **Levels:** `beginner | intermediate | advanced` (default intermediate). Resolved via a ladder:
  `--audience` → project `build-preferences.yaml#/audience` → global `~/.startd8/config.json` → default.
  Public API: `resolve_audience_preference(project_root)` → `{value, source}`; `disclosure_tier(aud)` →
  `expanded | light | compact`.
- **Knob 1 — DISCLOSURE** (prose density): `load_experience_doc(key, tier=…)` slices `<!-- PLAIN -->` /
  `<!-- TL;DR -->` regions. Beginner = expanded plain-language; intermediate = today's prose (byte-
  identical); advanced = terse.
- **Knob 2 — SURFACE** (which fields are prompted): a walk-start **pre-pass** (`apply_audience_defaults`
  + `AUDIENCE_PROFILES` in `manifest.py`) writes *shielded defaults* for beginners with
  `audience-default:<slug>` provenance in `confirmed.yaml`; those fields drop out of the walk and are
  ratified by a normal `kickoff confirm` (which strips the provenance).
- **Guarantee (persona FR-4):** same explicit decisions → **byte-identical** `inputs/` + `confirmed.yaml`
  across personas. Audience is presentation + which-fields-prompted, never the values.
- **Already consumed by:** CLI (`explain`, `guided`), web (`/audience.*`, `/guided.json`), TUI — via
  `guided_parity_digest`. **The Workbook does NOT consume it yet.**

## 2. What the Workbook renders today (the porting surface)

`portal_spec.build_kickoff_portal_spec` has **zero audience awareness** — one fixed prose density. Two
facts shape the port:
- Per-field **attention** (ok/review/blocked/backlog) is derived from **extraction status** (`KickoffState`),
  **not** the `confirmed.yaml` ledger — so it does **not** currently see `audience-default` provenance.
- **What/Why/Who** comes from `explain_input_domain`, which has **no tier parameter** (fixed content).
- Each domain renders as **one markdown text panel** with a field table inside (matters for §4 OQ-5).

## 3. The three porting slices

| Slice | What | Effort | Value | Snag |
|---|---|---|---|---|
| **A — disclosure** | render the Workbook intro (± domain prose) at the resolved audience's tier | Low | Med–High | intro is a hardcoded string in `portal_spec` → swap to the tiered `load_experience_doc` |
| **B — audience-default badge** | show pre-pass-shielded fields as **"✅ safe default set for you"** instead of a scary 🔴 gap | **Med** | **High** (beginner UX) | needs a **new data join** — read `confirmed.yaml` provenance into the portal spec (today it's extraction-only); adds a 4th presentation state |
| **C — tiered domain prose** | per-domain What/Why/Who at beginner/advanced depth | Higher | Med | `explain_input_domain` needs per-tier content markers — real content work |

**Recommendation:** A + B are the value; **B is the one that matters** — a beginner's board shouldn't
scream "8 gaps" when 3 were auto-shielded *for them*. Defer C.

## 4. The two implementation eras

### Era 1 — NOW (classic schema, no Grafana upgrade)
Bake the board at the **currently-resolved** audience. Regeneration/`--provision` re-renders at the new
tier when the audience changes. Works on today's `schemaVersion 39` generator.
- **A:** resolve audience in the portal build → render intro at `disclosure_tier`.
- **B:** join `confirmed.yaml` provenance → render shielded fields as a distinct "audience-default" state.
- **Downside:** switching audience needs a regenerate + re-provision (not live). One board per project,
  rendered for whoever's audience was resolved at generation time.
- **This is a legitimate incremental win available before the upgrade.**

### Era 2 — POST Grafana ≥13.1 (dynamic schema, the better end state)
An `audience` **runtime variable** + **conditional rendering** → the viewer flips their persona lens
**in-browser, live, no regeneration, no write**. One deterministic board carries all variants + rules;
the JSON is identical regardless of viewer audience (strengthens persona byte-identity). **Dissolves the
read-only tension** — it's a view toggle, not a write (Workbook NR-3 holds).
- **This is the target.** It depends on the first-class v2 emit capability — see
  `../dynamic-dashboards/DYNAMIC_DASHBOARDS_REQUIREMENTS.md` (FR-8/FR-9 = this exact consumer) and its
  **M0 spike + Grafana upgrade** gate.

## 5. Next steps

1. **Decide the era-1 question:** ship the **classic-schema A+B port now** (incremental beginner-UX win,
   available before the upgrade), or **wait for era 2** (live switching) and do it once, cleanly? A+B now
   is not throwaway — the *rendering logic* (tier selection, provenance→badge) is reused in era 2; only
   the *trigger* changes (baked-at-gen → runtime variable).
2. **If era-1 now:** small, self-contained — plumb `resolve_audience_preference` + `disclosure_tier` into
   `portal_build`/`portal_spec` (Slice A) and the `confirmed.yaml` provenance join (Slice B). Its own
   reflective-requirements pass is optional (it's a bounded presentation change); the provenance join
   (crossing extraction↔ledger) is the one part worth a design note.
3. **For era 2:** fold this consumer into the dynamic-dashboards plan (M6) — it's already FR-8/FR-9 there.

## 6. Open decisions

- **OQ-5 (field granularity)** — for the surface knob, render fields as **separate panels/rows** (fine,
  bigger `portal_spec` change, enables per-field conditional hiding in era 2) vs a coarse **"collapse the
  shielded section for beginner"** (row-level, cheap). Recommend coarse for v1.
- **OQ-6 (disclosure depth)** — intro-panel-only (v1) vs `explain_input_domain` gains per-tier prose.
- **Era choice** — the §5.1 decision: incremental now vs wait for live-switching.

## 7. Dependencies / relates-to

- **Audience feature (owned; cite, don't re-spec):** `concierge/audience.py`, `manifest.py`
  `AUDIENCE_PROFILES`, `docs/design/kickoff/PERSONA_EXPERIENCES_{REQUIREMENTS,PLAN}.md`.
- **Workbook (the surface):** `kickoff_experience/portal_spec.py`, `WORKBOOK_PROJECT_START_REQUIREMENTS.md`
  (read-only NR-3), and the shipped generation lifecycle.
- **The generator capability (era 2 dependency):** `../dynamic-dashboards/` (spec/plan/next-steps) — the
  Grafana v2 emit path + its M0 spike + Grafana ≥13.1 upgrade.
