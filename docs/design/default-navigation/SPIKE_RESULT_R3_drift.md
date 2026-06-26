# Spike Result — R3 (always-on nav as a 3-input owned kind)

**Date:** 2026-06-26
**Branch / worktree:** `spike/default-nav-drift` (`../startd8-nav-spike`, off `origin/main` @ `e599904a`)
**Verdict:** ✅ **R3 falsified (de-risked). The approach holds. Proceed to implement.**

## Question
Can the always-on default nav be added as a 3-input (schema + `views.yaml` + `pages.yaml`)
owned/deterministic kind that the **real** drift + skip-hook machinery recognizes as `$0`-owned and
`in_sync`, flips stale when **any** input changes, and doesn't regress existing kinds?

## What was built (minimal, real — not mocked)
- `_headers.py::header_nav_tmpl` — 3-sha header, **reusing** the existing `forms-sha256` (views) and
  `pages-sha256` (pages) header lines → **no new drift regex**.
- `nav_generator.py` — deterministic `nav_registry()` (pages + entities + views) + `render_nav_partial()`.
- `drift.py` — `_NAV_KINDS`, `nav_stale_reason`, `_check_nav_drift`, one dispatch line in `check_drift`.
- `tests/unit/backend_codegen/test_nav_drift_spike.py` — drives the **production** `check_drift` and
  `owned_file_in_sync` over the real `tests/fixtures/wireframe` schema/views/pages.

## Result — `9 passed`, plus `74` existing drift/skip/owned tests still green
| Claim under test | Outcome |
|---|---|
| Registry aggregates pages + entities + views (all-visible default) | ✅ |
| Render is byte-identical across calls (idempotency, FR-10) | ✅ |
| Real `check_drift(..., forms_text, pages_text)` → `in_sync` | ✅ |
| **Real `owned_file_in_sync(..., views_text, pages_text)` → `True`** (the core R3 question) | ✅ |
| Any of schema / views / pages changes → `stale` | ✅ (3 cases) |
| Hand-edit → `tampered` | ✅ |
| Manifests **not** threaded → `False` (safe fall-through, not a false `in_sync`) | ✅ |
| Existing backend_codegen drift/skip/owned suite unaffected | ✅ `74 passed` |

## Findings that correct the plan
1. **The "first 3-sha artifact" claim (old R3) was wrong.** `header_ai_layer` already ships a
   3-input/3-hash header. A 3-sha owned kind is a *proven* pattern, not novel.
2. **The skip-hook already threads both manifests** the nav needs — `owned_file_in_sync` has
   `views_text` and `pages_text` on its signature today. The `forms:`/`editors:` bug class does **not**
   re-appear; the nav kind inherits the correct safe-fall-through behavior.
3. **No new header regex** was required — `forms-sha256` + `pages-sha256` already parse.
4. **R4 is the residual cost, and it is real but bounded.** The new `_nav.html` is purely additive
   (no existing file's bytes change — 74 tests confirm). **But** wiring nav into `base.html` via a
   `{% include "_nav.html" ignore missing %}` line *does* change `base.html` by one line → a **one-time
   re-stamp of every existing app's base template** until regenerated. The plan's "base.html stays
   unchanged" wording (FR-14) is imprecise: base.html gains exactly one deterministic include line,
   once. Acceptable (a normal generator-version regen), but state it honestly.

## Effort signal
The spike is ~M0 + a thin slice of M1 (registry + partial + drift family). The remaining build is
mechanical: assembler emission, the `base.html` include line, and the runtime config loader
(`load_hidden()` / `visible_nav()`). No architectural unknowns remain.

## Disposition
Spike code lives on `spike/default-nav-drift`. It can be promoted as the M0/M1 starting point or
discarded (the learning is captured here). The worktree is removable with
`git worktree remove ../startd8-nav-spike`.
