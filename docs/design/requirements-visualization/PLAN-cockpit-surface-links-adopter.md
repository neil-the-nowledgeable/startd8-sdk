# Cockpit Tiles Link to Navigator via surface_links — Plan

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.2   **Date:** 2026-08-19
**Format:** plan
**Pairs with:** `REQ-cockpit-surface-links-adopter.md`
**Inherits standards:** det-req-kit

> **Readable handle:** `feature/cockpit-surface-links-adopter`
> **Semantic name:** *Wire cockpit readiness tiles to link to the navigator node via the declared surface_links drill binding and resolve_surface_link_href*

---

## Planning Discoveries

| What the requirements assumed | What planning revealed |
|-------------------------------|----------------------|
| The web cockpit needs a new helper to resolve the link | `resolve_surface_link_href(link, key)` already exists, is public, and returns `""` safely when no href. Zero new helper code. |
| The Grafana v2 board needs structural changes to carry links | Text panels accept raw markdown; the field row builder already formats strings. A `[text](href)` insert is pure string formatting. |
| The terminal view needs Rich Hyperlink support | Rich `Text` has no interactive hyperlink in a standard terminal. The annotation is just a styled string append (`[dim]#key[/dim]`). |
| The cockpit renderers don't currently import from `navigator.view_definition` | `portal_spec.py:49-54` already imports `cockpit_attention_colors` from `view_definition` (EC-CS-8). Same import pattern — no new coupling direction. |
| The resolved definition needs to be threaded into the cockpit renderer | The web cockpit already calls `resolve_kickoff_state()` which provides the field keys; the resolved View Definition is importable as `BASE_NAVIG8R_DEFINITION` + `resolve` (or just the surface_links data from the base). |

---

## Approach

The implementation is **3 parallel, independent edits** (one per rendering surface) plus a shared test module. Each edit:
1. Imports `resolve_surface_link_href` and `BASE_NAVIG8R_DEFINITION` (or reads the surface_links dict)
2. In the per-field render loop, calls `resolve_surface_link_href(drill_link, field_key)`
3. If the result is non-empty, formats the link in the surface's idiom (HTML / markdown / Rich)

---

## Iterations

### Iteration 1: Web cockpit drill link (FR-1, FR-5)

**Target:** `src/startd8/kickoff_experience/web.py`

**What exists:** The web overview route renders per-field status badges into HTML. Each field row already has access to `field_key` (the manifest field name, which IS the requirement node key for kickoff inputs).

**Steps:**

1. **Import** `resolve_surface_link_href` and `BASE_NAVIG8R_DEFINITION` from `startd8.navigator.view_definition` (lazy import in the render function to avoid import-time cycle, matching `portal_spec.py:49-54` pattern).

2. **Resolve the drill link dict** once per render: `drill = (BASE_NAVIG8R_DEFINITION.surface_links or {}).get("drill", {})`.

3. **In the per-field row**, call `href = resolve_surface_link_href(drill, field_key)`. If `href`: wrap the field label/badge in `<a href="{href}" class="drill-link">…</a>`. If not: leave unchanged (byte-identical).

4. **Test** (`tests/unit/kickoff/test_cockpit_drill_link.py`):
   - `test_web_overview_field_has_drill_link` — render with surface_links → assert `<a href="#field_key"` in output.
   - `test_web_overview_no_link_when_no_surface_links` — render with empty surface_links → assert no `<a href="#` in output.

**Estimated:** ~10 lines of production code + ~20 lines of test.

### Iteration 2: Grafana v2 board drill link (FR-2)

**Target:** `src/startd8/kickoff_experience/portal_spec_v2.py`

**What exists:** `build_workbook_v2()` builds field rows with attention badges into `V2Panel` text panels. The content is assembled as markdown strings.

**Steps:**

1. **Import** `resolve_surface_link_href` and `BASE_NAVIG8R_DEFINITION` (same lazy pattern).

2. **Resolve drill dict** at the top of the board builder.

3. **In the field-row formatter**, append ` [→ navig8r](#{key})` to the field's markdown line when `resolve_surface_link_href(drill, field_key)` returns non-empty.

4. **Test** (add to existing v2 test or a new `test_cockpit_drill_link.py` case):
   - Built dashboard JSON for a field row → grep markdown pattern.
   - No surface_links → no markdown link.

**Estimated:** ~8 lines production + ~15 lines test.

### Iteration 3: Terminal cockpit annotation (FR-3)

**Target:** `src/startd8/kickoff_experience/cockpit_view.py`

**What exists:** `_status_panel(view)` builds a Rich `Text()` body with attention counts. It does NOT currently render per-field rows — it only shows aggregate counts (`{ok} ok · {review} review · …`).

**Discovery:** The terminal view shows aggregate counts, NOT per-field rows. Adding a per-field `#key` annotation requires either:
- (a) Add a per-field table to the terminal output (scope expansion), or
- (b) Defer FR-3 to when the terminal view gains per-field rendering.

**Decision:** FR-3's scope should be narrowed — the terminal annotation applies IF/WHEN per-field rows exist. Since the terminal currently shows only aggregates, **FR-3 is deferred to a follow-on** (it requires per-field rendering the terminal doesn't yet have). This is documented as a planning insight → flows back to Phase 3.

### Cross-cutting: FR-4 zero-diff guard

**Steps:**
1. After all changes, verify: `git diff --stat src/startd8/navigator/ src/startd8/wireframe_view/` = 0.
2. Run existing test suite: `pytest tests/unit/navigator/ tests/unit/wireframe/ -x --tb=short`.
3. Confirm `test_no_profile_is_byte_identical` passes unedited.

---

## File change manifest

| File | Change | FR |
|------|--------|-----|
| `src/startd8/kickoff_experience/web.py` | Add drill-link formatting in overview field rows | FR-1 |
| `src/startd8/kickoff_experience/portal_spec_v2.py` | Add markdown link in v2 board field rows | FR-2 |
| `src/startd8/kickoff_experience/cockpit_view.py` | ~~Add dim annotation~~ **DEFERRED** (no per-field rows exist) | FR-3 (deferred) |
| `tests/unit/kickoff/test_cockpit_drill_link.py` | New: drill-link tests for web + v2 + empty-default | FR-1, FR-2, FR-5 |
| `src/startd8/navigator/*` | **NO CHANGE** | FR-4 |
| `src/startd8/wireframe_view/*` | **NO CHANGE** | FR-4 |

---

## Open questions for implementation

- **OQ-I-1:** Does `web.py`'s overview route have direct access to field keys, or does it iterate domain→manifest→fields? Need to confirm the loop structure to find the right insertion point.
- **OQ-I-2:** Does the Grafana v2 text panel support relative `#key` links, or does it need an absolute URL? (Likely relative is fine since the board and navig8r share a domain in dev.)
- **OQ-I-3:** Should the `<a href>` link target `_blank` (new tab to navig8r) or stay in the same page? The navig8r lives at a different path (`/navigator`); the cockpit is at `/`. A relative `#key` won't work cross-page — it needs `/navigator#key` or a configurable base path. **This is the key implementation question for FR-1.**

---

## Cost estimate

- **Production code:** ~20 lines (2 files)
- **Test code:** ~40 lines (1 new file)
- **LLM cost:** $0 (deterministic rendering, no LLM)
- **Effort:** XS–S (2 trivial format insertions + tests)

---

## Gate

Done-when all of:
1. Web overview renders `<a href="…#key">` per field (or `/navigator#key` — resolve OQ-I-3)
2. Grafana v2 board carries `[→ navig8r](#{key})` markdown per field row
3. `git diff --stat src/startd8/navigator/ src/startd8/wireframe_view/` = 0
4. New tests pass; existing navigator/wireframe tests pass unedited
5. `test_no_profile_is_byte_identical` passes unedited

---

*v0.2 — Post-planning update. FR-3 (terminal) deferred (no per-field rows in terminal view). OQ-I-3 (relative vs absolute URL) identified as the key implementation decision. Effort: XS–S.*
