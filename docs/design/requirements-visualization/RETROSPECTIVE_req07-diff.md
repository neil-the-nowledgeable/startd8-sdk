# Retrospective — REQ-07 Diff-Audience View Delivery (Hansei)

**Pilot:** the REQ-07 diff-audience delivery (`diff.py` engine, `render_diff.py` standalone renderer,
the `navigator diff` CLI + `_load_state`, commit `ecd96e02`, handle
`feature/sdk-navigator-diffs-two-states-of-the-node-125a3a9c`) + the HTH P1/P2 hardening over it.
**Window:** 2026-08-15. **Method:** `/reflective-retrospective` as HTH-on-REQ-07 Phase 3 (grounded in
code + the reachability probe + empirical malformed-input probes, not the spec's beliefs).

## Phase 2.5 — Dormant inventory (grounded via the reachability probe + greps)

Probe: `python3 scripts/navigator_spec_delivery_loop.py --reachability diff.py render_diff.py`.

| Symbol | Probe verdict | Grep / evidence | Status |
|--------|---------------|-----------------|--------|
| `diff_nodes` | wired 1/0 | CLI `diff` L248 + tests | **wired** |
| `node_diff_to_json` | wired 1/0 | CLI `diff --json` L251 + tests | **wired** |
| `render_navigator_diff_html` | wired 1/0 | CLI `diff` L268 + tests | **wired** |
| `NodeDiff` | wired 2/0 | engine return + renderer param | **wired** |
| `FieldDelta` | wired 1/0 | renderer changed-row rendering + tests | **wired** |
| `StatusTransition` | **DORMANT 0/0** | constructed `diff.py:320`; stored on `NodeDiff.status_transitions`; rendered `render_diff._render_transitions` (iterates the field); JSON-serialized `diff.py:381`; tested `test_diff.py:161`, `test_render_diff.py:124` | **dormant (BENIGN)** — field-typed dataclass; probe's name-based heuristic can't see instance-only / field-iterated use (same class as REQ-06's `GovernReport`) |
| `DanglingRef` | **DORMANT 0/0** | constructed `diff.py:260`; stored on `NodeDiff.new_dangling_refs`; rendered `render_diff._render_dangling`; JSON-serialized `diff.py:385`; tested `test_diff.py:173-215`, `test_render_diff.py:124-145` | **dormant (BENIGN)** — same field-dataclass pattern |

Scanned 7 public symbols; **all real value paths wired**. The 2 DORMANT verdicts are the *known
benign field-dataclass class*: a frozen dataclass that is CONSTRUCTED inside the engine, carried as a
typed `NodeDiff` field, and consumed by field-iteration in the renderer + JSON serializer. The probe
counts bare-name references in `src/`; it cannot see `for t in diff.status_transitions`. **Soft-note
only — no wiring needed.** (This is the second confirmed instance of the field-dataclass probe blind
spot; see Phase 5.)

## Phase 3 — Reflection (belief → actual)

| Kind | What the spec/belief said | What the actuals revealed | So the standard is… |
|------|---------------------------|---------------------------|---------------------|
| **artifact** | `StatusTransition`/`DanglingRef` are wired review signals | probe flags them DORMANT 0/0 | benign — field-typed dataclasses whose use is field-iteration, invisible to a name-ref probe. The **field-dataclass dormant class** is now a *recognized, accepted* probe limitation (REQ-06 `GovernReport` was the first). Don't over-engineer the probe; soft-note it. |
| **process** | `_load_state`'s `except (FileNotFoundError, ValueError, OSError)` covers malformed input because JSON/Unicode decode errors ARE `ValueError` | it covers *decode* failures but NOT *structurally-valid-JSON-but-wrong-shape*: a bare scalar (`42`), a non-object node entry, a non-object `lives`/`children` element make `nodes_from_json` call `.get` on a non-dict → **`AttributeError`/`TypeError` leaks as a raw traceback** past the handler (empirically confirmed: 5 leaking classes) | a loader that hands decoded JSON to a `.get`-assuming projector must **validate structure at the CLI boundary** and normalize to the caught exception type (`ValueError`). "It parses" ≠ "it's shaped right." |
| **process** | "diff the dangling-*ness*, not the raw ref list" (spec FR-4) | the engine does exactly this — `_new_dangling_refs` computes `after_dangling − before_dangling` so an already-dangling ref is not re-flagged; `_ref_to_path` strips `git:<sha>:` / `file:` / `:line` and `.lstrip("./")` neutralizes `..` traversal into a repo-relative check | **precision-diff pattern**: diff the *derived property* (dangling-ness), not the raw collection — the correct grain for a "what newly broke" signal, and it also closes the path-traversal false-read. Proven correct + safe as shipped; no fix needed. |
| **artifact** | determinism / order-insensitivity is a risk | `_normalize` compares collection fields as sorted tuples; buckets are key-sorted; `children` compared by child-key set so a grandchild edit lands on the child's own row — `test_shuffled_input_order_yields_identical_diff` + `test_render_twice_byte_identical` green | **order-insensitive-compare discipline**: normalize-then-compare on collections, compare parents by child *identity* not nested content, sort every bucket → byte-identical diffs → a CI diff-of-diffs is meaningful. Proven; no fix needed. |

## Phase 4 — The standard this delivery PROVED

1. **Greenfield standalone-renderer pattern (refined).** REQ-07 re-proved the REQ-02/03/05 discipline:
   a renderer with its OWN `<!doctype>` shell + inlined CSS/JS (no CDN, no `<script src>`), that NEVER
   imports `wireframe_view` (grep-gated + reverse-import test), reusing shared seams by *import not copy*
   (`_safe_href` from `render_tree`, `project_nodes` from `node_lenses` behind a soft-import guard) —
   Kagami. The app-scaffold path stays byte-identical (`test_no_profile_is_byte_identical` unedited).
2. **Precision-diff (diff the derived property, not the raw collection).** For a "what newly broke"
   signal, compute the property on each side and diff the *properties* (`after_dangling − before_dangling`),
   not the raw lists. Avoids re-flagging a pre-existing condition as new, and — for a filesystem-resolved
   ref — the path-normalization it needs (`_ref_to_path` + `.lstrip("./")`) also neutralizes traversal.
3. **Order-insensitive-compare determinism.** Normalize collection fields to sorted tuples before
   comparing; compare parents by child *key-set* (nested edits land on the child's own row); key-sort
   every bucket and fix field order. Result: cosmetic reordering ≠ "changed", and same-inputs → byte-
   identical output. Proven by the shuffled-input and render-twice tests.
4. **Validate structure at the loader boundary (P2 hardening standard).** A CLI loader that decodes
   JSON and hands it to a `.get`-assuming projector must structurally validate (array-of-objects,
   objects-only `lives`/`children`, recursively) and raise the *caught* exception type — otherwise a
   valid-JSON-wrong-shape payload leaks a raw `AttributeError`/`TypeError` traceback. Proven: added
   `_validate_node_json`; 5 previously-leaking input classes now exit 1 cleanly.

## Phase 5 — Lessons

- **The field-dataclass dormant class is now confirmed recurring (2×).** A frozen dataclass that is
  constructed inside its owning module, carried as a typed field on a container, and consumed by
  field-iteration reads DORMANT 0/0 to a name-ref probe. First seen: REQ-06 `GovernReport`. Now:
  REQ-07 `StatusTransition` + `DanglingRef`. **This is a candidate for `/metabolize-finding`** — the
  probe could special-case "constructed + assigned to a container field + that field is iterated" as
  wired, or the retro template could carry a standing "field-dataclass → benign" row so each HTH pass
  stops re-litigating it. (Not built this pass — logged to the backlog.)
- **"It parses" is not "it's shaped right."** The `ValueError`-subclass reasoning that makes decode
  errors self-catching (`JSONDecodeError`/`UnicodeDecodeError` ⊂ `ValueError`) creates a false sense of
  total coverage — the *structural* failure mode leaks a different exception family entirely. Any
  decode→project boundary needs an explicit shape guard, not just a decode-error catch.
- **Recursive hardening again.** HTH-on-REQ-07 hardened the `_load_state` boundary a greenfield build
  left thin, and re-confirmed the probe blind spot a prior HTH pass (REQ-06) first surfaced — the
  harvest keeps improving its own instruments.

## Phase 6 — Yokoten + feed-forward

- **Yokoten:** the loader-boundary shape-guard (`_validate_node_json`) applies to `build`'s own
  `nodes-json` path (`cli_navigator.py:113`), which has the *same* unguarded
  `nodes_from_json(data.get("nodes", data))` call and would leak the same tracebacks — logged as a
  backlog row (out of REQ-07's owned surface: it's the `build` command, not `diff`).
- **Feed-forward:** the field-dataclass-dormant metabolize candidate + the "validate at every
  decode→project boundary" clause become inputs to the next `/reflective-requirements` touching a
  navigator loader or the reachability probe.
