# <Project> — Build Preferences (prose source)                               [TEMPLATE]

> **TEMPLATE** — copy to `<project>/docs/kickoff/authoring/build-preferences.md`, replace every `<…>`,
> delete the `▷` guidance lines and this banner, then fill the groups. Validate with
> `startd8 kickoff check docs/kickoff/authoring/build-preferences.md` (writes nothing), iterate until it
> reports the values as `extracted`, then let the extractor emit `kickoff/inputs/build-preferences.yaml`.

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**What this is:** the **prose-authored source** for `kickoff/inputs/build-preferences.yaml` — how the
build factory itself runs (spend / model routing / generation profile), written to Authoring-Contract
**§2.11**. **Never pin a model version string** — name `*_tier`s only (tiers resolve via
`model_catalog`). `language` must equal `conventions.yaml`'s. Prose outside the `## Build preferences`
section is tolerated and ignored.

---

## Build preferences

- Provenance default: <config-default>

### Budgets
▷ string values (`$5.00`, `$0 (local-only)`); key → snake_case.
- Per pipeline run: <$5.00>
- LLM monthly: <$25>
- Infra monthly: <$0 (local-only)>

### Model routing
▷ tier NAMES only — never a pinned version. `Note` is free text.
- Lead tier: <anthropic-flagship>
- Drafter tier: <anthropic-balanced>
- Complexity routing: <enabled>
- Note: <convention-strict work must not route to a tier that can't receive the conventions sheet>

### Generation
- Profile: <full>
- Language: <python>
- Instrumentation: <auto>

### Unattended
▷ `Non interactive` is a **bool** (`true`/`false`).
- Question answers: <.cap-dev-pipe/design/question-answers.yaml>
- Non interactive: <false>
