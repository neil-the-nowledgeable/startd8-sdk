# `onboarding:` Archetype — Plan

**Pairs with:** `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` v0.1 · **Date:** 2026-08-14

## Steps

| # | Action | File(s) | FR |
|---|--------|---------|-----|
| S1 | Manifest parse | `onboarding_manifest.py` | FR-1/2 |
| S2 | Generator (router + template + aggregator) | `onboarding_generator.py` | FR-3/4 |
| S3 | Assembler `out.extend(render_onboarding(...))` | `assembler.py` | FR-3 |
| S4 | Drift kinds + renderers | `drift.py` | FR-5 |
| S5 | Unconditional `onboarding_routers` mount | `crud_generator.py` `render_main` | FR-5 |
| S6 | Export from package `__init__` if needed | `__init__.py` | — |
| S7 | Unit tests | `tests/unit/backend_codegen/test_onboarding.py` | FR-1…5 |
| S8 | Wireframe fixture declare | `tests/fixtures/wireframe/prisma/views.yaml` | dogfood harness |
| S9 | Household declare (lived) | `household-o11y/prisma/views.yaml` | dogfood demo |

## Dogfood

1. **Harness:** wireframe Profile/Metric/Note + `onboarding:` → pytest green + optional `--check`.
2. **Lived:** household-o11y — tips + empty states for Member/Chore/Bill; leave `pages:` `/getting-started`.

## Non-goals

See REQ FR-6 / Non-goals.
