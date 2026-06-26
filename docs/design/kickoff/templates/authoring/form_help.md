# <Project> — Form Help (prose source)                                       [TEMPLATE]

> **TEMPLATE** — copy to `<project>/docs/kickoff/authoring/form_help.md`, replace every `<…>`, delete
> the `▷` guidance lines and this banner, then author one `### Form: <Entity>` block per entity whose
> create/edit form needs guidance. Validate with
> `startd8 kickoff check docs/kickoff/authoring/form_help.md` (writes nothing), iterate until it
> reports the fields as `extracted`, then let the extractor emit `prisma/form_prose.yaml`.

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**What this is:** the **prose-authored source** for `prisma/form_prose.yaml` — the form **Words layer**
(per-field help/placeholder + a per-form intro) rendered into the generated create/edit forms. Help and
intro are **hash-exempt** (they ride untracked fragments, SOTTO): editing this copy never trips
`generate backend --check`. Absent ⇒ today's bare forms (opt-in). Prose outside the `## Form Help`
section is tolerated and ignored (contract §1: *the format carries the truth*).

> **Prerequisite (sequencing):** the Form-Help extractor resolves every `### Form: <Entity>` heading and
> every `Field` cell against your `prisma/schema.prisma`. Author the contract first — a `Form:` or a
> `Field` that names something undeclared is flagged `not_extracted` (sourced, advisory) and dropped,
> never guessed.

> **This is bucket-4 human content.** Help is the commissioning team's words, authored once. Put it on
> the fields a user most needs explained — the human-only owned fields (medical, financial) and the
> convention-laden ones ("0 = Monday", "dollars vs cents"). No AI pass ever originates a help value
> (FR-FH-6).

---

## Form Help

▷ One `### Form: <Entity>` block per entity form you want to guide. The ENTITY comes from the heading
▷ (a trailing `*(…)*` annotation is stripped) and must match a declared model. Inside each block:
▷   • an optional `- Intro:` line (a bullet, like the Views grammar) — one paragraph above the form;
▷   • a `Field | Help | Placeholder` table — one row per field. `Help` is the persistent description
▷     (wired as `aria-describedby`); `Placeholder` is the in-field example hint (optional). Omit either
▷     by leaving the cell blank. A field with neither is simply left out.

### Form: <Medication>

- Intro: <one sentence above the form, in the user's words — what this form is for and what it computes>

| Field               | Help                                                        | Placeholder |
|---------------------|-------------------------------------------------------------|-------------|
| <quantityRemaining> | <Units on hand right now.>                                   | <30>        |
| <dosesPerDay>       | <Doses taken per day — drives the run-out forecast.>         | <2>         |

### Form: <Bill>

| Field         | Help                                                | Placeholder |
|---------------|-----------------------------------------------------|-------------|
| <amountCents> | <Amount in dollars, e.g. 42.00; stored as cents.>   | <42.00>     |
| <weekday>     | <For a weekly cadence: 0 = Monday … 6 = Sunday.>    |             |

---

*Reference — the emitted `prisma/form_prose.yaml` shape (what this prose round-trips to):*

```yaml
forms:
  Medication:
    intro: "…"
    fields:
      quantityRemaining: { help: "Units on hand right now.", placeholder: "30" }
      dosesPerDay:       { help: "Doses taken per day — drives the run-out forecast.", placeholder: "2" }
  Bill:
    fields:
      amountCents: { help: "Amount in dollars, e.g. 42.00; stored as cents.", placeholder: "42.00" }
      weekday:     { help: "For a weekly cadence: 0 = Monday … 6 = Sunday." }
```
