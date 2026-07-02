# CRP Focus — Red Carpet Wizard-Driver + Asset-Chaining

## Where we need review most (least-reviewed target)

Both docs (`RED_CARPET_WIZARD_DRIVER_REQUIREMENTS.md` v0.3, `..._PLAN.md` v0.1) are **brand new** and have
had only the internal reflective + lessons passes. Weight the review on:

1. **The FR-WD-5 security decision** — is "propose the `derive-contract` command, never import project
   code in the wizard" airtight, or is there a residual path where the driver would import/execute
   untrusted project code (e.g. the completion model or inventory touching the models)?
2. **The deterministic driver loop (FR-WD-1/4)** — is a `$0` leading loop (present→propose→confirm→advance)
   genuinely buildable over the existing `on_proposal`/`apply_proposal`/`render_state` seams without the
   `ask_sync` LLM turn, and is the auto-advance/no-progress guard (OQ-6) sound against thrash?
3. **The completion model (FR-WD-2, OQ-3)** — is the union `{cascade gates} ∪ {writable fields}` a
   coherent denominator, and does counting `defaulted` distinctly avoid a misleading "100%"?
4. **The asset-chaining proposals (FR-WD-6/7)** — do the reused `brief`/`capture` kinds actually accept the
   pre-populated `source`/values the driver would propose, and does no-clobber behave under re-drive?

## Settled — do NOT relitigate (inherited floors)

- **Propose-confirm floor + closed `PROPOSAL_KINDS` allow-list** (RCT / advisor CRP R1-F1): the loop never
  writes; MCP read-only. No new proposal kind is added.
- **RCT P5 — gap-loop, NOT a fixed wizard.** "Wizard" here = proactive driver over the live gap model; do
  not propose a rigid linear next/back wizard.
- **FR-WD-5 no-import security stance** — the wizard proposes the derive command; it does not import
  project modules. (Challenge *residual* import paths, not the stance itself.)
- **Extend-don't-duplicate** — RCT/advisor/interactive specs own their vocabulary; this doc cites them.

## Dual-doc coverage ask

Confirm every FR-WD-* maps to a plan step, and that the plan's §7 validation (esp. the no-untrusted-import
security test) actually proves the FR-WD-5 stance.
