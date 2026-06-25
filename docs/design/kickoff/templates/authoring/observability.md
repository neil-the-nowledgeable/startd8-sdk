# <Project> — Observability (prose source)                                    [TEMPLATE]

> **TEMPLATE** — copy to `<project>/docs/kickoff/authoring/observability.md`, replace every `<…>`,
> delete the `▷` guidance lines and this banner. Validate with
> `startd8 kickoff check docs/kickoff/authoring/observability.md` (writes nothing) — **Slice 1**
> (Thresholds + Receivers) extracts today.

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**What this is:** the **prose-authored source** for `kickoff/inputs/observability.yaml`, written to
the Kickoff Authoring Contract **§2.12** grammar. It is human-readable *and* deterministically
extractable into an `ObservabilitySpec` — the same model the alert renderer consumes — so the seam
closes end-to-end: **prose → spec → active alert rule**. Prose outside the `## Observability`
section is tolerated and ignored.

> **Slice status:** all of `## Observability` extracts now — **Slice 1** (Thresholds + Receivers →
> alert/notification rules) and **Slices 2–3** (Service-levels, Collection, Channels, Runbook → the
> spec `context` for dashboards/SLOs/notifications).
>
> **Secret safety (load-bearing):** a receiver `Target` (and any contact) **must** be
> env-indirected (`${VAR}`) or an obviously-fictional `.test` value. A literal URL/email is
> **flagged, never extracted** — a real secret must never land in a manifest as authored.

---

## Observability

- Provenance default: <config-default | authored>
- Industry dataset: <end_user_application | …>

### Alerting

#### Channels

▷ Alert channels — one per bullet (free-text, not `Key: value`).

- #<alerts-channel>

#### Receivers

▷ Where alerts go. `Target` MUST be `${VAR}` env-indirection (secret safety). `Severities` is a
▷ comma-separated list.

| Name | Type | Target | Severities |
|------|------|--------|------------|
| <default> | <webhook> | ${<RECEIVER_URL>} | critical, warning |

#### Thresholds

▷ The alert spec — one row per signal. `Op` ∈ `>` `<` `>=` `<=` `==`; `Value` is a number; `For` is
▷ a Prometheus duration (e.g. `5m`, `0m`). Each row becomes an ACTIVE alert rule
▷ (`<Metric> <Op> <Value>`). Mix the app's own health (convention shapes) with your domain signals.

| Metric | Op | Value | Unit | Severity | For |
|--------|----|-------|------|----------|-----|
| <app_error_rate> | > | 0.02 | ratio | critical | 5m |
| <your_domain_signal> | > | 0 | count | warning | 0m |

### Service levels

- Availability: <99.5>
- Latency p99: <500ms>

#### Per service   *(optional — stricter SLOs where user trust is on the line)*

| Service | Availability | Latency p99 |
|---------|--------------|-------------|
| <entry-app> | <99.9> | <300ms> |

### Collection

- Metrics interval: <30s>
- Log level: <info>

### Runbook

- Overview: <one line: what user-facing failure looks like, what backend failure looks like>
- Escalation: <oncall -> team lead -> vendor>

#### Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| <availability> | <known failure mode> | <the guard> | <high> |

#### Procedures

- <triage step 1 — start from the dashboard>
- <a failure-mode-specific step>

---

## Reference (prose — ignored by extraction)

| Prose | → spec / `observability.yaml` | Rule |
|---|---|---|
| `- Provenance default:` / `- Industry dataset:` | `provenance_default` / `industry_dataset` | scalar key-lines |
| `### Service levels` + `#### Per service` | `context.service_levels` (+ `per_service`) | key-lines (label → snake_case) + table |
| `### Collection` | `context.collection` | key-lines |
| `#### Channels` bullets | `context.alerting.channels[]` | free-text bullets |
| `#### Receivers` table | `receivers[]` | `Target` MUST be `${VAR}` — a literal secret is **flagged** |
| `#### Thresholds` table | `signals[].threshold` | `Op ∈ {> < >= <= ==}`; `Value` numeric; bad op / non-number → flagged |
| `### Runbook` + `#### Risks` + `#### Procedures` | `context.runbook` (`overview/escalation/risks[]/procedures[]`) | key-lines + table + bullets |

A receiver target that is a **literal** secret → `not_extracted(secret-literal)`. An out-of-vocab
`Op` or a non-numeric `Value` → flagged in the `kickoff check` report (never guessed, contract §3).

## Extraction expectation (Slice 1 — what §2.12 should produce)

```yaml
provenance_default: <config-default>
industry_dataset: <end_user_application>
alerting:
  receivers:
    - {name: <default>, type: <webhook>, target: "${<RECEIVER_URL>}", severities: [critical, warning]}
  metric_thresholds:
    <app_error_rate>:     {op: ">", value: 0.02, unit: ratio, severity: critical, for: 5m}
    <your_domain_signal>: {op: ">", value: 0,    unit: count, severity: warning,  for: 0m}
```

*Authored to Kickoff Authoring Contract §2.12 (Slice 1). See `README.md` for the authoring-source
convention, and `views.md`/`pages.md` for the assembly-manifest siblings.*
