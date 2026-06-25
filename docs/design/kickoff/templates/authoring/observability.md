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

> **Slice status:** **Slice 1 = `#### Thresholds` + `#### Receivers`** extracts now (it feeds
> alerts/notifications). Service-levels, collection, and the runbook (Slices 2–3) are authored below
> for human value but are not extracted yet.
>
> **Secret safety (load-bearing):** a receiver `Target` (and any contact) **must** be
> env-indirected (`${VAR}`) or an obviously-fictional `.test` value. A literal URL/email is
> **flagged, never extracted** — a real secret must never land in a manifest as authored.

---

## Observability

- Provenance default: <config-default | authored>
- Industry dataset: <end_user_application | …>

### Alerting

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

### Service levels   *(Slice 2 — authored for humans, not yet extracted)*

- Availability: <99.5>
- Latency p99: <500ms>

### Runbook   *(Slice 3 — authored for humans, not yet extracted)*

- Overview: <one paragraph: what user-facing failure looks like, what backend failure looks like>

---

## Reference (prose — ignored by extraction)

| Prose | → spec / `observability.yaml` | Rule |
|---|---|---|
| `- Provenance default:` / `- Industry dataset:` | `provenance_default` / `industry_dataset` | scalar key-lines |
| `#### Receivers` table | `receivers[]` | `Target` MUST be `${VAR}` — a literal secret is **flagged** |
| `#### Thresholds` table | `signals[].threshold` | `Op ∈ {> < >= <= ==}`; `Value` numeric; bad op / non-number → flagged |

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
