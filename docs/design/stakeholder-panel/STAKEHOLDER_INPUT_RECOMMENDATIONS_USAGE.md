# Stakeholder Input Recommendations (Teian) — Usage

**Status:** Implemented (M0–M3). Requirements v0.4 / Plan v1.2 in this directory.

Teian is the **proactive** mode of the Stakeholder Panel: the persona agents draft starter values for
the still-blank kickoff **value** inputs, which a team member can **edit** or **approve as acceptable**.
Every draft is an `estimate` (never counted as `authored`) until a human decides.

## Prerequisites

- A validated roster at `docs/kickoff/inputs/stakeholders.yaml` (`startd8 concierge instantiate-kickoff`
  then author the personas). Personas own domains by `role_id`: `product-owner`→business-targets,
  `architect`→conventions, `pm`→build-preferences. A domain with no matching persona is **skipped**.
- The kickoff value YAMLs present under `docs/kickoff/inputs/` with unfilled `<placeholder>` values.

## The flow

```bash
# 1. Draft (paid). Walks unfilled fields, asks each owning persona, stages drafts out-of-band.
startd8 panel recommend [--domain business-targets] [--cap N] [--redraft] [--model <spec>]

# 2. Review ($0). Renders each pending draft with its persona brief + the gap it fills.
startd8 panel review [--session <id>]

# 3a. Approve — promote a draft into the domain YAML (comment-preserving splice + strict gate).
startd8 panel approve --field business-targets:product_funnel.signup_rate
startd8 panel approve --all                     # every pending draft in the session

# 3b. Reject — drop a draft (no write).
startd8 panel reject --field conventions:stack.web
```

Prefer editing the YAML directly for long/complex values; `approve --edit` is for short scalars.

## What is (and isn't) guaranteed

- **`estimate`, never `OBSERVED`/`authored`.** A draft is a starter, not a fact. The SDK never flips a
  domain to `authored`; after approving all of a domain's drafts, `approve` reminds you to set
  `provenance_default: authored` in the YAML yourself (the provisioning score reads only the in-file
  provenance, never the staging file).
- **Comment-preserving writes.** `approve` splices only the target value(s) via
  `kickoff_experience/capture.py`; your comments, key order, and blank lines survive (SOTTO). A value
  that fails the domain's strict parser is rejected (exit 4), marked `invalid`, and the file is left
  untouched.
- **Composite fields.** A `business-targets` metric row (`{target, why}`) is drafted in one query and
  applied as two sequential scalar splices.
- **No wasted spend.** A field already drafted is skipped on re-run unless `--redraft`; a field you
  filled directly in the YAML is treated as stale (hidden from review, refused by approve unless
  `--force`).
- **Bounded.** `--cap` and the panel budget preflight abort/defer *before* spend; a persona
  failure/deferral leaves the field unchanged and never aborts the pass.

## Staging artifact

Drafts live in `.startd8/stakeholder-panel/proposals/proposals-<session>.json` (`0600`, sorted,
`indent=2`) — the per-field audit trail (in-file YAML holds only the domain-level `provenance_default`).
Old sessions are garbage-collected on `recommend`.

## Observability

The pass runs under a parent span `stakeholder.recommend_pass` (aggregating cost + field counts) with a
child `panel.ask` span per draft. The human decision funnel emits `stakeholder.recommendation_reviewed`
/`_approved`/`_rejected` events (domain + role_id only — no drafted values in telemetry).
