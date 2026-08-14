# Form field layout — FR-FH-11 (label stack)

**Status:** Implemented 2026-08-14 · **Pairs with:** household `SDK_FORM_HELP_INPUT_REQUIREMENTS.md` FR-FH-11 ·
pilot [`_PILOT_2026-08-14_onboarding-household.md`](./_PILOT_2026-08-14_onboarding-household.md)

## Requirement

Each generated form field shall render as a vertical stack **directly above** its control:

1. **Label** — humanized caption (`anchorDate` → `Anchor date`), `for=` wired to the control  
2. **Instruction** — `form_prose` help fragment *or* structural hint (never below the control)  
3. **Control** — input / select / checkbox / datetime-local  
4. **Error** — inline validation message below the control only  

## Code

- `backend_codegen/htmx_generator.py` — `_form_input_html`, `_human_label`, `_BASE_STYLE` (“clipboard ledger”)  
- Forms carry `class="entity-form"` for the card chrome  

## Verify

```bash
.venv/bin/python -m pytest tests/unit/backend_codegen/test_htmx.py tests/unit/backend_codegen/test_form_prose.py -q
# form HTML: label index < help/hint index < input name=
```
