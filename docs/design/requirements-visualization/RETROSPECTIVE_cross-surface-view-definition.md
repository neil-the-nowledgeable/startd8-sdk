# Retrospective — Cross-Surface View Definition (Hansei)

**Pilot:** REQ-cross-surface-view-definition delivery (`67051859`, PREP lock `1940b8d8`) + HTH
code-review harden (`7ca8a5f2` on this branch: opt-in is **exact key-set equality**, not subset).
**Window:** 2026-08-19. **Method:** `/reflective-retrospective` as HTH stage-7 Phase 3 — grounded in
the post-harden tree (`view_definition.py` + four test modules + greps), not the spec's beliefs.
**review: offered → continued** (loop-authorized; HTH FR-4).

## Phase 2.5 — Dormant inventory (grep, don't assert)

| Touch | Grep / evidence | Status |
|-------|-----------------|--------|
| `_status_specs` / `_navig8r_statuses_from_node_state` | called from `to_render_profile` (`view_definition.py:261,314`) | **wired** |
| `node_state` section on resolve / `to_dict` | `_SECTIONS` L47-48; inherited by every domain; tests `test_node_state_taxonomy.py` | **wired** (data) |
| `presentation.navig8r` → `StatusStyle` | FR-2 tests + `test_hth_*` pins; requirements profile byte-identical | **wired** |
| `presentation.cockpit` | declared `view_definition.py:463-499`; `rg` in `kickoff_experience/` = **0 hits** | **dormant (by NR-7)** |
| `surface_links.drill` / `.rollup` | declared `:506-518`; consumed only by `test_surface_links.py` + resolve inheritance | **dormant (by NR-7)** — declared-not-wired |
| `validate_definitions` vs `surface_links.via` | function `:691-712` checks `extends` + `chrome.bindings` only; no `via` / `attention` walk | **soft-only at harvest** — closed by **EC-CS-1** (`_validate_resolved_cross_surface`) |
| `REQUIREMENTS_DEFINITION.vocabulary.statuses` vs navig8r leaves | two copies (`:530-536` vs `:461-492`); projection **discards vocab values** when keys equal (`:264-266`); no equality pin at harvest start | **unexercised dual-write** (CEP XS pin this run) |
| Done-when / FR-7 byte-identity | `test_no_profile_is_byte_identical` unedited; goldens unedited | **wired** |
| Ledger implement row | said opt-in is a **subset**; code after `7ca8a5f2` is **equality** | **claim-ceiling** — RECORD wrote the PREP sentence; HTH-1 moved the tree |

Scanned 9 touches. Navig8r projection path is wired. Cockpit leaves + both `surface_links` bindings are
**declared-not-consumed** on purpose (NR-7 / ledger H1). Do not invent a projector with no caller this
pass — that would mint a new dormant.

## Phase 3 — Reflection (belief → actual)

| Kind | What I believed about what I built | What the actuals revealed | So the standard is… |
|------|-----------------------------------|---------------------------|---------------------|
| **artifact** | FR-4/FR-5 "drill/rollup declared" means insight can flow between surfaces | `kickoff_experience/` has zero `surface_links`/`node_state` hits; `to_render_profile` never reads `surface_links` or `presentation.cockpit` | **declared ≠ user-visible.** A typed pointer in the cascade is a contract for a later adopter, not a live link. Soft-label the Done-when: definition-complete, surface-incomplete. Inventory row → CEP / ledger H1. |
| **process** | subset-as-opt-in is the generous empty-default (any domain that *mentions* canonical keys should inherit the shared map) | a domain keyed `{spec, awaiting}` would be recoloured with requirements meanings; empty vocab used to invent the five canonical statuses | **opt-in to a shared keyed taxonomy is equality of key sets, not subset.** Subset is accidental overlap, not consent. Proven by HTH-1 + three pins. |
| **artifact** | the requirements `vocabulary.statuses` literal is still the Derive-to-Prove oracle | when keys equal, `_status_specs` **returns `node_state` values** and ignores vocab *content*; editing vocab color while keeping keys is a silent no-op | **dual-write needs a sync pin** (or stop authoring the second copy). The oracle is whichever side projection reads; the other copy is a fossil unless a test equates them. |
| **process** | STAGE-0 gate takes a spec path the way the runbook writes it (relative) | from a `/private/tmp` worktree, a relative path crashes `Path.relative_to` | **absolute spec path at the gate** until the driver is fixed; the crash is a driver bug, not a spec miss. |

## Phase 4 — The standard this delivery PROVED

1. **Shared taxonomy as an ordinary cascade section.** Cross-SURFACE reuse is the same move as
   cross-DOMAIN reuse: add `node_state` + `surface_links` to `_SECTIONS`, author once on
   `BASE_NAVIG8R_DEFINITION`, inherit via existing `resolve` / `_deep_merge`. No second resolver
   (NR-1). Proven: capability's resolved `node_state`/`surface_links` equal requirements'
   (`test_fr6a_capability_inherits_the_same_sections_unchanged`).
2. **Equality-gated projection (empty-default).** A domain projects from the shared map iff
   `set(vocabulary.statuses) == set(navig8r leaves)`. Proper subset, empty vocab, and foreign key
   sets keep their own `vocabulary.statuses` — byte-identical for capability/pipeline/node-schema.
   Malformed non-dict leaves skip, they do not raise (projection fail-open; governance is a later
   `--validate` row).
3. **Declared-not-wired surface links (NR-7).** Drill `via: fullview` names a registered region;
   rollup `via: serves` names an existing graph primitive. Neither binding adds a route, an edge
   kind, or a cockpit import. The adopter (ledger H1) is a **separate spec**; this delivery's
   Done-when stops at the definition.
4. **Canonical ids = consumer keys verbatim.** PREP locked `grounded`/`spec`/`awaiting`/`excluded`/
   `unknown`; `activated` is `kind: "project"` only. Spec prose `speculative` is not an id.

## Phase 5 — Lessons

- **Subset is not consent.** Key-set overlap with a shared map is the default *accident* of a
  small domain, not an opt-in. The HTH-1 High finding is the same class as "empty field substitutes
  empty string" chrome bindings: fail-open must not *recolour*.
- **A second copy that projection does not read is not an oracle.** Derive-to-Prove still needs the
  authored vocab for byte-identity of the *input document*, but the *render* oracle is
  `presentation.navig8r` once keys match. Pin them equal or delete one copy.
- **NR-7 is a claim-ceiling, not a defect.** Dormant `surface_links` would be a bug if the spec had
  promised a live cockpit link. It promised a zero diff on `kickoff_experience/`. The harvest's job
  is to keep that ceiling honest in the ledger and `--validate` (CEP), not to wire the cockpit in
  this composition.

## Phase 6 — Yokoten + feed-forward

- **Yokoten:** the equality-gated opt-in applies to any future shared keyed map that projects over
  domain vocabularies (do not copy the original subset heuristic). `--validate` should grow the same
  way `chrome.bindings` did (REQ-10 EC-6) — `surface_links.via` is the next field in that family.
- **Feed-forward:** ledger H1 (cockpit adopter) + CEP `EC-CS-1` (`validate_definitions` walks
  `via`) are the next `/reflective-requirements` inputs. Do not start H1 inside this HTH.
- **Bus:** no `bus.sh` in this environment (`dev-os/cursor-loops/templates/agent-comms-queue/bus.sh`
  absent). Explicit **no bus peer** — subject is SDK-local definition; the only outward edge is the
  in-repo cockpit adopter (H1), already on the ledger.
