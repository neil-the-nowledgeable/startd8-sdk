# Demo App — Requirements (authoring-contract-conformant fixture)

Golden fixture for the manifest-extraction tests: every §2.x grammar surface, including the
deliberate non-conformances the report must flag.

## Scaffold & runtime

| Setting | Value | Plain meaning |
|---------|-------|---------------|
| package name | demoapp | the Python package |
| display name | Demo App | what users see |
| python version | 3.12 | |
| port | 8099 | NO MANIFEST HOME — must flag generator-gap |
| database | sqlite:///./data/demo.db (override via DATABASE_URL) | |
| migrations | alembic | |
| container | yes — emit Dockerfile | |
| env keys | ANTHROPIC_API_KEY (optional) | NO MANIFEST HOME — must flag |

## Entities

### Profile
Who the user is.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
| bio | long text | no | |
| yearsExp | number | no | |
| rating | decimal | no | |
| joined | date | no | |
| active | yes/no | no | |
| tier | choice of: free\|pro | no | |

Relationships: a Profile **has many** Widgets.

### Widget
A thing the user makes.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| title | text | yes | |
| score | number | no | ONLY HUMANS ENTER THIS |
| in / out | text | no | slash-row — must flag one-field-per-row |
| blob | mystery type | no | unknown type — must flag |

Relationships: a Widget **belongs to** a Profile; a Widget **links to many** Tags.

### Tag
A label.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| label | text | yes | |

Relationships: a Tag **links to many** Widgets; a Tag **links** Widget **to** nothing (plain link).

## Pages

| Page | Purpose | Content file |
|------|---------|--------------|
| Home | Landing | home.md |
| Résumé | Unicode route test | resume.md |
| About | About us | about.md *(not written yet)* |

Navigation *(order = display order)*:

| Label | Target |
|-------|--------|
| Home | / |
| Widgets | /ui/widget |
| Résumé | /resume |

## Views

### View: Widget Wall
- Kind: detail-compose
- Root: Widget
- Shows: Widget→Tag (only confirmed)
- Empty state: "nothing yet"

### View: Profile Dashboard
- Kind: dashboard
- Root: Profile
- Shows: counts of widgets per profile

### View: Profile Workspace *(preview)*
- Kind: workspace
- Root: Profile
- Shows: everything about one profile in prose form

### View: Profile Export
- Kind: export-package
- Of: Profile Workspace
- Formats: json, md

### View: Widget Board
- Kind: board
- Root: Widget
- Group by: tier
- Order: free, pro

## Completeness

A profile is complete when it has:

- at least 2 Widgets (weight 2) — nudge: "Make more widgets."
- at least 1 Tag
(Don't count: connection records, Profile)

Completeness is guidance, never a gate.

## AI assists

| Assist | Reads | Writes | Purpose |
|--------|-------|--------|---------|
| suggest_tags | Widget | Tag | propose labels |
| draft_widget | pasted text | Widget (except score) | first draft |

Only humans enter: Widget.score, Profile.rating.
