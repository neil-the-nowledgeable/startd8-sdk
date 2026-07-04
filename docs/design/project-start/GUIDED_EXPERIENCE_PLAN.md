# Guided Experience — Implementation Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-04
**Tracks:** `GUIDED_EXPERIENCE_REQUIREMENTS.md` v0.2
**Posture:** Detangle + consolidate + promote; deterministic-first; nothing forced; kernel byte-identical when absent.

---

## Guiding constraints (from the planning pass)

1. **No SDK deployment-mode self-awareness exists** — route on explicit preference >
   surface > project-shape; never *detect* agent-presence (D1).
2. **The conductor is deterministic-first** — the $0 advisor + wizard already guide;
   LLM is strictly opt-in (D5). "Guided" costs $0.
3. **The facilitation process is an un-packaged script** — promote before harden;
   route its writes through the safe-write floor (D2/D8).
4. **The win is surface/vocab/write-path reduction, not LOC** (D3/D7).
5. **Cloud is read-only for now** — cloud-write has no trust substrate (D6).

---

## Milestones

### M0 — Routing seam (small, safe)
- Add a `guided` preference reusing the `concierge_agent.py:59-75` precedence ladder
  (`--guided/--no-guided` → project `build-preferences.yaml` → global
  `~/.startd8/config.json` → default-quiet). Route on: explicit > served-surface >
  `build_assess` project-shape. **No agent-presence detection.**
- One ignorable offer line; `--no-guided` ⇒ kernel byte-identical (FR-GE-1/2/3).
- **Satisfies:** FR-GE-1, FR-GE-2, FR-GE-3, FR-GE-4.

### M1 — Single entry point + vocabulary retirement
- Introduce `startd8 kickoff guided` (or no-subcommand ⇒ guided offer) sequencing
  Orient→Guide→Deepen over `orchestrator.py:build_kickoff_plan`.
- Retire `concierge_app`/`panel_app` as top-level groups (`cli.py:1259-1260`); alias
  their verbs under `kickoff` (hidden aliases for one release — parent FR-10).
- **Net:** 3 groups → 1, 23 verbs → ~12.
- **Satisfies:** FR-GE-5, FR-GE-7, OQ-GE-2.

### M2 — Concierge/conductor detangle (the real reduction)
- Merge the concierge-UI quartet (`concierge_agent`/`_apply`/`_view`/`tui_concierge`)
  → one view+apply (the parity view-model `concierge_view.py` becomes THE view).
- Merge `red_carpet_completion` + `wizard` + `orchestrator` (three overlapping
  "what's next" projections over the same advisor output) → one conductor module.
- Collapse `chat.py`'s three constructors (`new_kickoff_chat`/`new_agentic_kickoff_chat`/
  `new_red_carpet_chat`) → one parametrized constructor.
- Verify all writes ride `concierge/safe_write.py` (FR-GE-13).
- **Target:** 24 → ~16 modules. **Satisfies:** FR-GE-6, FR-GE-7, FR-GE-13, OQ-GE-3/6.

### M3 — Promote & harden facilitation (biggest lift)
- **Promote** `run_kickoff_panel.py` orchestration → `stakeholder_panel/facilitation.py`,
  built over the existing `StakeholderPanel`/roster/guards (OQ-GE-8 sizes the
  abstraction). Route transcript persistence through the safe-write floor (fixes D8).
- Then harden: **H1** artifact-grounding fidelity (read the running app / `survey`,
  not just schema); **H2** assumptions-as-gate (halt on ≥N high-impact/low-confidence);
  **H3** cost tracking (panel already tracks `cost_usd` — wire it end-to-end).
- **FR-GE-11** raw-round persistence; **FR-GE-12** anti-smoothing as a *test* (assert
  named raw-round tensions survive the synthesis; `_SYNTH_SYS` already instructs it —
  make it verifiable).
- **Satisfies:** FR-GE-10, FR-GE-11, FR-GE-11a, FR-GE-12, FR-GE-13.

### M4 — Surface parity (CLI / TUI / served)
- One view-model (`concierge_view.py` is already the parity oracle) feeds CLI, TUI,
  and the local served UI. Cross-surface parity test.
- **Satisfies:** FR-GE-9.

### M5 — Cloud scoping (read-only)
- Ship cloud as **read/preview-only** (Orient + Deepen-view); local write uses the
  existing loopback+token model. Human downloads produced inputs, writes locally.
- Cloud-**write** deferred (OQ-GE-7 — net-new auth/tenancy).
- **Satisfies:** FR-GE-8 (standalone + cloud-read), NR (no cloud-write yet).

---

## FR → Milestone traceability

| FR | Milestone |
|----|-----------|
| FR-GE-1/2/3/4 | M0 |
| FR-GE-5, FR-GE-7 | M1 (+ M2 detangle) |
| FR-GE-6, FR-GE-13 | M2 |
| FR-GE-10/11/11a/12 | M3 |
| FR-GE-9 | M4 |
| FR-GE-8 | M5 |
| FR-GE-14 | all (human ratifies; never authors/decides) |

---

*Plan v1.0 — sequenced so routing (M0) and the single entry point (M1) land before
the detangle (M2), the facilitation promotion+hardening (M3) is isolated as the big
lift, and cloud stays read-only (M5) until the OQ-GE-7 auth design exists.*
