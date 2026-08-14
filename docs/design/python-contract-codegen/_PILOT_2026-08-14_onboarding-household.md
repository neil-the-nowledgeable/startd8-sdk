# Pilot findings — `onboarding:` + household forms (2026-08-14)

**Pilot:** `household/household-o11y` lived demo · wireframe fixture harness  
**Trigger:** First-run `/welcome` dogfood + create-Chore Internal Server Error  
**Status:** Fixes landed in `htmx_generator` / household regen (same day); this note is the durable record.

**Companions:** `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` · `SDK_FORM_HELP_INPUT_REQUIREMENTS.md` (household copy) ·
`FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` · PC-13 (tips as content)

---

## What worked

| Surface | Result |
|---------|--------|
| `views.yaml` `onboarding:` → `/welcome` tips + empty-state checklist | Orientation readable; tips dismiss via `localStorage` (no modal) |
| Nav includes Welcome from `onboarding:` | Present beside Getting Started (`pages:`) |
| CRUD create with valid enums + `datetime-local` (after coerce fix) | 303 → detail |
| Views / Getting Started / home / admin nav | 200 |
| Blur `/validate` for empty required text | Inline “This field is required.” |

---

## Defects found (and remediation posture)

### P0 — crash / poison

| ID | Finding | Root cause | Fix |
|----|---------|------------|-----|
| P0-1 | Save Chore → 500 | `_coerce` left `datetime-local` strings as `str`; SQLite needs `datetime` | Parse `datetime` in `_coerce` / `_field_error` |
| P0-2 | Create/update never run `_field_error` | Validate-on-blur only; submit coerces+commits | Server-side `_form_errors` on create/update; re-render form with `errors` + `prefill` |
| P0-3 | Bad datetime / empty required FK → 500 | Uncaught `ValueError` / `IntegrityError` | Same as P0-2 |
| P0-4 | Forged lowercase enum can poison DB → list/API/welcome 500 | SQLite stores free text; SQLAlchemy enum fails on **read** | Validate select values against allowed frozenset before commit |
| P0-5 | `/welcome` → 500 (`TypeError` tuple/dict key) | Onboarding used Starlette-old `TemplateResponse(name, {request:…})` | Request-first: `TemplateResponse(request, name, ctx)` (match `web.py` / `pages.py`) |

### P1 — correctness / affordances

| ID | Finding | Fix |
|----|---------|-----|
| P1-1 | Empty required `anchorDate` still created (model/`now()` default) | Required check on create (omit ≠ valid) |
| P1-2 | FK fields are raw text IDs (`assigneeId`, `memberId`, …) | Structural field hint + form_prose help; picker is later enhancement |
| P1-3 | Delete returns HTMX row fragment (200), not redirect | Documented as HTMX-list contract (FORM_SUBMIT); leave |
| P1-4 | Nav: duplicate Home; raw view labels (`chore_fairness`) | **Closed** — brand ≠ Home; view labels humanized; `nav_label` on onboarding |

### P2 — default form UI (pilot ask)

Bare generated forms were hard to use on first run:

| ID | Ask | Fix |
|----|-----|-----|
| P2-1 | More contrast on field borders | `htmx-base` CSS: stronger input/select border + focus ring |
| P2-2 | Per-field instructions | (a) structural hints when no `form_prose` help; (b) wire household `--form-prose` + expand Chore/Member copy; (c) **FR-FH-11** stack instructions *above* the control |
| P2-3 | Sensible defaults where obvious | Create-form defaults: `interval=1`, `turnIndex=0`, `leadDays=3`, `refillLeadDays=7`; required selects prefer first enum when unset |
| P2-4 | Labels read as captions of their fields | Humanized labels (`anchorDate` → `Anchor date`) directly above the control (FR-FH-11) |
| P2-5 | Form chrome polish | Distinctive form surface (clipboard ledger): stronger borders, focus, type, motion on field reveal |

---

## Non-goals (this pilot)

- Retrofit attorney-portal ONB  
- Replace `pages:` `/getting-started`  
- Confirm-walk archetype  
- Full FK picker widgets  

---

## Verify (re-run after regen)

```bash
cd ~/Documents/dev/household/household-o11y
# welcome
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/welcome   # 200
# bad datetime must NOT 500
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/ui/chore \
  -d 'name=X&domain=CHORES&cadence=WEEKLY&interval=1&turnIndex=0&anchorDate=not-a-date'  # 200 form w/ errors
# good create
curl -sS -D - -o /dev/null -X POST http://127.0.0.1:8000/ui/chore \
  -d 'name=Pilot&domain=CHORES&cadence=WEEKLY&interval=1&turnIndex=0&anchorDate=2026-08-14T10:00' \
  | head -5   # 303 Location: /ui/chore/…?created=1
```

---

## Execution log

| When | What |
|------|------|
| 2026-08-14 | Pilot dogfood; P0-1 datetime coerce; welcome TemplateResponse hotfix |
| 2026-08-14 | This note + htmx create/update validation, base form CSS, structural hints/defaults, form_prose wired on regen |
| 2026-08-14 | Restored `onboarding:` codegen (request-first TemplateResponse); household regen with `--form-prose`; smoke green |
| 2026-08-14 | **Merged** [startd8-sdk PR #463](https://github.com/neil-the-nowledgeable/startd8-sdk/pull/463) → `origin/main` (`1379392`) — `onboarding:` archetype + form validation / FR-FH-11 |
| 2026-08-14 | **§2 follow-ups on main** — humanized view labels (`nav_generator.py`); welcome ledger CSS (`onboarding_generator.py`); `nav_label` + `redirect_root_if_empty` (FR-2; closes P1-4) |
| 2026-08-14 | **Consumer-side (household repo, no remote):** `household-o11y` `364d752` — regen with `onboarding:` + form ledger polish from startd8 main |
