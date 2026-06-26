# <Project> — Business Targets (prose source)                                [TEMPLATE]

> **TEMPLATE** — copy to `<project>/docs/kickoff/authoring/business-targets.md`, replace every `<…>`,
> delete the `▷` guidance lines and this banner, then fill the tables. Validate with
> `startd8 kickoff check docs/kickoff/authoring/business-targets.md` (writes nothing), iterate until it
> reports the metrics as `extracted`, then let the extractor emit `kickoff/inputs/business-targets.yaml`.

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**What this is:** the **prose-authored source** for `kickoff/inputs/business-targets.yaml` — what
success looks like, in numbers (the goal lines on the overview dashboard), written to Authoring-Contract
**§2.10**. A personal/household tool's "business targets" are **outcome** targets; declare monetization
`not-applicable` honestly rather than leaving it blank. Prose outside the `## Business targets` section
is tolerated and ignored.

---

## Business targets

- Provenance default: <estimate>
▷ optional. `- Monetization: not-applicable` expands to the full monetization block (the only v1 value).
- Monetization: not-applicable

### Outcomes

▷ The goal lines on the overview dashboard — the outcomes the app exists to improve. `Target` is kept
▷ numeric when it's a bare integer (`0`), else a string (`95%`, `<= $25`). `Why` is free text.

| Metric | Target | Why |
|--------|--------|-----|
| <on time rate> | <95%> | <the core outcome — operations should rarely slip> |
| <missed critical events> | <0> | <zero-tolerance outcome> |

### Usage

| Metric | Target | Why |
|--------|--------|-----|
| <weekly active loggers> | <3> | <people who log at least one event/week> |

### Unit economics

| Metric | Target | Why |
|--------|--------|-----|
| <llm cost per month> | <<= $25> | <build-side only> |
| <runtime cost per event> | <$0.00> | <the deterministic-runtime economic claim> |

### Per-role goals

▷ The human-recognizable one-liner behind the numbers. `Role`→key (verbatim), `Goal`→string.

| Role | Goal |
|------|------|
| <the-user> | <I do X in under N seconds and trust the system to warn me.> |
