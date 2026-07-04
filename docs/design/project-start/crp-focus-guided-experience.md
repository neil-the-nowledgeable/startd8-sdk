# CRP Focus — Guided Experience

## Least-reviewed target
`GUIDED_EXPERIENCE_REQUIREMENTS.md` (v0.3) + `GUIDED_EXPERIENCE_PLAN.md` (v1.0) —
brand-new, no prior external review. They went through the reflective loop
(draft→plan→reflect→lessons) but never an independent architectural review. This is
the least-reviewed artifact in the whole project-start set.

## SETTLED — do NOT relitigate (out of scope for suggestions)
1. The v0.17 essential model: guided/agentic experience **available but not
   required — complement not substitute**; kernel byte-identical without it; "meet
   the user where they are." (Owner: `PROJECT_START_REQUIREMENTS.md` §0.4.)
2. Routing = explicit-preference > surface > project-shape; **agent-presence is
   never detected** (no SDK deployment-mode self-awareness exists — planning D1).
3. The conductor is **deterministic-first** ($0 advisor + wizard); LLM strictly
   opt-in. "Guided" costs zero LLM.
4. Anti-sprawl success metric = **one entry point / one vocabulary / one write
   path** (NOT fewer LOC). It is a detangle, and facilitation promotion adds a module.
5. Cloud is **read/preview-only** for v-next; cloud-write deferred (OQ-GE-7).
6. Parent decisions: kernel = `startd8 kickoff` (survey/instantiate/assess + derive
   on-ramp); `project init` scoped-out to the VIPP capability; the anti-principle lens.

## Where we most need review (weight these)
1. **Consolidation soundness (FR-GE-5/6/7).** Does the detangle genuinely reduce
   sprawl, or risk re-accreting it? Are the merge targets (concierge-UI quartet, the
   three "what's next" projections, the three chat constructors) real, and does M1/M2
   sequencing hold? Any surface/vocabulary collision the "one entry point" claim misses?
2. **FR-GE-11a — facilitation promotion (the biggest lift).** Is promoting the
   un-packaged script into `stakeholder_panel/facilitation.py` fully specified? The
   safe-write-floor routing (FR-GE-13), the abstraction over `StakeholderPanel`
   (OQ-GE-8), the H1/H2/H3 hardening — any gap or ordering hazard?
3. **Routing / offer-not-force (FR-GE-3/4).** Edge cases: served-surface implies
   no-agent but a served surface could be driven by an agent too; the precedence
   ladder; the "one ignorable line, never a gate" guarantee; non-interactive/CI.
4. **Safe-write + safety (FR-GE-13/14).** All writes (inputs AND transcripts) ride
   the confined floor; the human-ratification / never-authors-or-decides invariant.
5. **Cloud read-only (FR-GE-8) + OQ-GE-7.** Is "download-and-write-locally" a
   coherent cloud story? What exactly blocks cloud-write, and is the deferral clean?
6. **Requirements↔plan gaps / over-reach**, and any contradiction with the parent
   reqs v0.17 (esp. FR-6/NR-2 as revised, and the retirement→consolidation reframe).
