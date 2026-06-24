# <Project> — Content Pages (prose source)                                    [TEMPLATE]

> **TEMPLATE** — copy to `<project>/docs/kickoff/authoring/pages.md`, replace every `<…>`, delete
> the `▷` guidance lines and this banner. This authors the **page index + nav** (`prisma/pages.yaml`);
> the page **bodies** are separate markdown you write at `app/pages/<name>.md`. Validate with
> `startd8 kickoff check docs/kickoff/authoring/pages.md` (writes nothing).

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**What this is:** the **prose-authored source** for `prisma/pages.yaml`, written to the Kickoff
Authoring Contract **§2.2 Pages** grammar. Pages are the app's **getting-started / onboarding
content surface** — the standalone pages a user reads (Home, Getting started, How it works), as
opposed to the entity CRUD screens (`/ui/<entity>`, generated from the contract) and the composite
views (`views.yaml`). Prose outside the `## Pages` / `## Navigation` sections is tolerated and
ignored (contract §1: *the format carries the truth*).

> **Two files, two lifecycles (the Words/Structure split):**
> - **This file → `pages.yaml`** = the page *index* (which pages exist, their titles, nav). Structure.
> - **`app/pages/<name>.md`** = each page's *body* (the actual copy). Words — bucket-2/4 content,
>   read at generate time, rendered to an **untracked** fragment, so editing a body never trips
>   `generate … --check` (SOTTO). **You author both:** name the page here, write its body there.

---

## Pages

▷ One row per standalone content page. ROUTES ARE DERIVED — never write URLs:
▷ `Home` → `/`; any other page → `/<kebab(name)>` (e.g. `How it works` → `/how-it-works`).
▷ The `Content file` is the body's path under `app/` (e.g. `pages/home.md` → `app/pages/home.md`) —
▷ create that markdown file with the real copy. Nav label defaults to the page name; nav order =
▷ table order (override below only if nav ≠ pages).

| Page | Purpose | Content file |
|------|---------|--------------|
| Home | Landing + what the app is, in one screen | pages/home.md |
| Getting started | First-run walkthrough — the steps a new user takes | pages/getting_started.md |
| How it works | The method/approach, explained | pages/how_it_works.md |

## Navigation

▷ OPTIONAL — include only when nav should differ from the Pages list (e.g. to add links to the
▷ generated entity CRUD screens, which live at `/ui/<entity>` and are in no manifest). Nav targets
▷ are **opaque route strings**, emitted verbatim — a target the extractor can't resolve renders with
▷ an advisory "route not in manifest" status, never an error (contract §2.2). Delete this section to
▷ let nav derive from the Pages table.

| Label | Target |
|-------|--------|
| Home | / |
| Getting started | /getting-started |
| <Entity plural, e.g. Members> | /ui/<entity, e.g. member> |

---

## Authoring notes (prose, ignored by extraction)

- **Getting-started content is bucket-4** (real, human-authored copy) — it becomes real only on
  human approval; a placeholder body is the honest starting state, never gated.
- **Empty-state nudges** ("No chores due today — add your first…") are NOT pages — they belong in
  `view_prose.yaml` (`empty:` on a composite view). Form-field help/instructions belong in
  `form_prose.yaml` (the form Words layer). Pages are the standalone narrative content.
- **Flag-don't-guess (contract §3):** a malformed row → `not_extracted(<reason>)` in the
  `kickoff check` report; routes are never invented from anything but the page name.

## Extraction expectation (what §2.2 should produce)

▷ Update to mirror your filled tables — the round-trip acceptance target for `prisma/pages.yaml`.

```yaml
pages:
  - {slug: /,                title: Home,            nav_label: Home,            content: pages/home.md}
  - {slug: /getting-started, title: Getting started, nav_label: Getting started, content: pages/getting_started.md}
  - {slug: /how-it-works,    title: How it works,    nav_label: How it works,    content: pages/how_it_works.md}
nav:                          # only when a Navigation table was authored
  - {label: Home, href: /}
  - {label: Getting started, href: /getting-started}
  - {label: <Members>, href: /ui/<member>}
```

*Authored to Kickoff Authoring Contract §2.2. See `README.md` for the authoring-source convention,
and `views.md` for the composite-views sibling. Pages bodies (`app/pages/*.md`) are the Words layer
(hash-exempt); this index is Structure.*
