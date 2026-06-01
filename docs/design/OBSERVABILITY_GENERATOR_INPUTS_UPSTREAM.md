# Bringing observability-generator placeholders forward as cap-dev-pipe inputs

**Date:** 2026-05-31
**Status:** Design note (requirements-adjacent) — extends REQ-OAT-024/025; consumed-side is the SDK,
producer-side is cap-dev-pipe (out of this module's immediate scope).
**Related code:** `src/startd8/observability/artifact_generator.py`; the REQ-OAT-061 actionability
check (`_bridge_human_actionable`, step C2) that surfaces these gaps today.

---

## 1. Problem

The observability artifact generator emits **placeholder operational values** because the real ones
are never gathered anywhere upstream. The generator can derive *what to observe* (metrics, thresholds
from the manifest) but not the *operational handoff targets* (where the runbook lives, which webhook
pages whom, the real dashboard URL). So it stamps placeholders into otherwise-valid artifacts.

C2's bridge **actionability** check (REQ-OAT-061) now flags exactly this: an alert whose
`runbook_url`/`dashboard_url` points at something not produced (or a placeholder) scores its **human
half partial** — a *broken system→human handoff*. That check is correct, but it treats a **root-cause
input gap** as a per-run scoring deduction. The fix is to gather these values **once, early**, as
declared inputs — "declare, don't guess" (REQ-OAT-024) applied to operational handoffs.

**Goal:** capture the placeholder elements as inputs at the earliest cap-dev-pipe stages (the
**POLISH** plan-quality gate and the **RESOLVE-Q** manifest-question stage), so they flow through
`.contextcore.yaml` → `onboarding-metadata.json` → the generator, which then substitutes real values
and the actionability check passes for *real* reasons (not by relaxing the check).

## 2. Placeholder inventory (what the generator emits today)

| Placeholder | Where (`artifact_generator.py`) | Should be | Proposed input field |
|-------------|----------------------------------|-----------|----------------------|
| `runbook_url = https://runbooks.example.com/{service}/{alert}` | alert annotations (~825) | the team's real runbook base URL (+ per-alert path convention) | `observability.runbook_base_url` |
| `webhook_configs[].url = REPLACE_WITH_WEBHOOK_URL` | notification policy (~1676) | the real Alertmanager receiver target (Slack/PagerDuty/webhook) | `observability.notification.receiver` (+ kind) |
| `dashboard_url = /d/obs-{service}` | alert/loki annotations + runbook (744/782/817/1720/1770) | the **actual** dashboard UID — note the generator renders `cc-obs-{service}`, so the annotation link is also internally stale | `observability.dashboard_uid_scheme` (default `cc-obs-{service}`) |
| `<THRESHOLD>` (domain-metric alert stubs left commented) | `_domain_alert_todo_block` (~1159) | per-metric alert thresholds | `observability.domain_thresholds[metric]` |
| `Owner: TODO: set manifest.spec.business.owner` | runbook (~1787) | the owning team/contact | already `spec.business.owner` — surface as a POLISH gate |

> The `dashboard_url` row is doubly valuable: it exposes an **internal inconsistency** (annotation
> says `/d/obs-{service}`, the rendered dashboard UID is `cc-obs-{service}`). Gathering one
> `dashboard_uid_scheme` input and using it on **both** sides removes the skew the C2 check works
> around at service granularity.

## 3. Where to gather — pipeline placement

The cap-dev-pipe is a strictly sequential staged pipeline (see
`UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` §Part 4):

```
Stage 0 CREATE → Stage 1 POLISH → 1.5 ANALYZE-PLAN → 2 INIT-FROM-PLAN → 2.5 RESOLVE-Q
  → 3 VALIDATE → 4 EXPORT(onboarding-metadata.json) → 5 PLAN-INGESTION → 6 PRIME-CONTRACTOR
```

- **Stage 1 POLISH (plan quality gate):** add a *completeness check* that flags missing operational
  handoff inputs (runbook base URL, notification receiver, dashboard scheme, owner) as plan gaps —
  the same "make the gap visible early" stance as the rest of the quality gates. POLISH does not
  invent values; it records that they are required and unset.
- **Stage 2.5 RESOLVE-Q (manifest question resolution):** the natural place to *resolve* them —
  this stage already exists to answer manifest questions. Each unresolved operational input becomes
  a resolvable question; answers land in `.contextcore.yaml`.
- **Stage 4 EXPORT:** the resolved values flow into `onboarding-metadata.json` (alongside the
  REQ-OAT-024 `kind`/`category` facts), the contract the generator already reads.

This mirrors the REQ-OAT-031a/031b producer/consumer split: **producer = cap-dev-pipe** (POLISH gate
+ RESOLVE-Q question + EXPORT), **consumer = SDK generator**.

## 4. Proposed declared shape (consumed-side contract)

Carried in `.contextcore.yaml spec.observability` and surfaced in `onboarding-metadata.json`:

```yaml
spec:
  observability:
    runbook_base_url: "https://runbooks.acme.io"        # → runbook_url = {base}/{service}/{alert}
    dashboard_uid_scheme: "cc-obs-{service}"             # used by BOTH the annotation link and render
    notification:
      receiver: "slack-sre"                              # Alertmanager receiver name
      target: "https://hooks.slack.com/services/…"       # the real webhook/integration URL
    domain_thresholds:                                   # optional per-metric alert thresholds
      startd8_cost_total: "100"
```

## 5. Generator changes (when the inputs land — declare-don't-guess)

- Read `runbook_base_url` / `dashboard_uid_scheme` / `notification.*` / `domain_thresholds` from
  metadata; substitute real values where today it writes placeholders.
- **Fallback stays, but is recorded** (REQ-OAT-024 pattern): when an input is absent, keep the
  placeholder AND record `classification_source: "placeholder"` (or `inferred`) in the generation
  report, so the gap is visible rather than silently shipped. The C2 actionability check then
  legitimately scores partial only when the *input* was never provided — pointing at the upstream
  gap, not at the generator.
- Use `dashboard_uid_scheme` on **both** the annotation `dashboard_url` and the rendered dashboard
  UID, closing the `obs-`/`cc-obs-` skew (lets the C2 handoff check resolve by exact UID later).

## 6. Relationship to existing requirements

- **REQ-OAT-024 (declare, don't guess):** this is the same principle extended from metric
  classification to *operational handoff* facts.
- **REQ-OAT-025 (upstream producer, cross-referenced):** REQ-OAT-025 already says the cap-dev-pipe
  onboarding exporter should emit declared facts; this note adds the operational-input set to that
  exporter contract.
- **REQ-OAT-061 (bridge actionability):** the consumer-side check already exists (C2). This note is
  the *producer-side* that makes the check pass for real.

## 7. Scope / next steps

- **Out of scope here (cap-dev-pipe):** the POLISH completeness check, the RESOLVE-Q questions, and
  the EXPORT field emission — tracked in cap-dev-pipe.
- **In scope for a future SDK increment:** generator consumption of the fields + the
  `placeholder`-source recording (small, additive; mirrors the REQ-OAT-024 `inferred` path).
- **No behavior change today** — this note captures the design so the inputs are gathered at the
  right stage rather than patched at generation time.
