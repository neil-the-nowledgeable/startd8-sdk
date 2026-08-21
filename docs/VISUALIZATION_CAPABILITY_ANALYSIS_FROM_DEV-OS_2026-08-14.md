# Visualization-capability analysis — what it means for startd8-sdk

**From:** dev-os (visualization-capability catalog + REQ-10 benchmark-node-tree work), 2026-08-14.
**To:** the startd8-sdk agent team.
**Kind:** consumer analysis brief. **Companion:** `NAVIG8_A11Y_RENDERER_TRACK_FROM_DEV-OS_2026-08-14.md`
(the renderer-migration ask). This note covers the *other* two SDK-relevant findings from the same session.
**One line:** two SDK assets are load-bearing across repos and should be treated as canonical shared
surfaces — (1) the **navigator** is the designated cross-repo node-viz renderer, and (2)
`kickoff_experience.manifest.PROVENANCE_DEFAULTS` is a canonical dual-axis vocabulary that consumers import.

---

## Background

dev-os catalogued the visualization capabilities across four independently-built systems (startd8-sdk
requirements viz, startd8-work legal navigator, the Summer-2026 benchmark portal, and dev-os) to maximize
reuse toward a new target (the benchmark as a node tree). The headline: **all four already converged on one
contract — NODE-SCHEMA-JSON** (`key / does / status / status_facets / wont / lives / children`). Two of the
findings are about **startd8-sdk-owned assets**, so they're written up here.

## Finding 1 — the navigator is a cross-repo shared renderer, not just a requirements tool

The four systems are **node-sources**; the renderer they (should) share is the **startd8-sdk navigator**
(`src/startd8/navigator/`), now the **forward home** for the navigator (decision 2026-08-14; ContextCore's
is the prior home). What makes the SDK navigator the designated renderer:

| Asset (startd8-sdk) | Why it's the reuse target |
|---|---|
| `navigator/models.py` `Node` | field-compatible with NODE-SCHEMA v0.3.9+; already carries `children`/`child_keys` |
| `wireframe_view` **audience × fluency lenses** | end_user/architect × beginner/intermediate/advanced, pre-embedded + client-side toggle — the standout reusable asset; no other system has it. This is the crown jewel other renderers should *not* re-implement |
| `navigator/project.py`, `cli_navigator.py` | the projection + CLI seam downstream sources plug into |

**What this means for the SDK team:** the navigator's blast radius is wider than "render a requirement."
startd8-work's legal navigator, the benchmark portal (`node_projection.py`), and dev-os projectors all emit
NODE-SCHEMA and want to render through *this* renderer. Treat `Node` + the lenses as a **stable public
contract**, not an internal detail. (The concrete gap blocking that today — the SDK navigator only has the
2-level wireframe projection, not the N-level tree renderer — is the subject of the companion a11y-renderer
note.)

## Finding 2 — `PROVENANCE_DEFAULTS` is a canonical cross-repo vocabulary (keep it stable)

startd8-work's legal navigator pioneered a **dual-axis** node encoding — `CONFIDENCE ⊥ PROVENANCE` — that
dev-os wants to reuse for the benchmark (auto-score = confidence; adjudication state = provenance). Tracing
the provenance vocabulary to its source landed **inside the SDK**:

- **Canonical home (grounded):** `startd8-sdk/src/startd8/kickoff_experience/manifest.py:38-40` —
  `PROVENANCE_DEFAULTS: frozenset[str] = frozenset({"authored", "estimate", "config-default", "templated"})`
  (validated internally at manifest.py:183).
- **Cross-repo consumer:** `startd8-work/src/startd8_work/legal/navigator_export.py:61` imports it —
  `from startd8.kickoff_experience.manifest import PROVENANCE_DEFAULTS` — and at line 63 keeps a
  **hard-coded fallback frozenset** for when the import fails.

Two implications for the SDK team:

1. **This is a public vocabulary, not a kickoff-internal constant.** It already crosses a repo boundary and
   is about to cross a second (dev-os REQ-10 FR-4 will import it directly rather than mirror the legal
   file). Changing the member set (`authored`/`estimate`/`config-default`/`templated`) is a **breaking
   change for external consumers** — treat it with public-API stability.
2. **The import-with-fallback is a smell worth resolving.** A consumer needing a `try/except` +
   duplicated frozenset means the symbol isn't cleanly/reliably importable (buried in
   `kickoff_experience.manifest`, which pulls a heavier module graph). Consider exposing
   `PROVENANCE_DEFAULTS` (and the confidence vocabulary, if there's a paired one) from a **lightweight,
   dependency-thin module** consumers can import without the fallback — that removes the fork risk (every
   fallback frozenset is a Kagami-style mirror that silently drifts if the canonical set changes).

## What dev-os will do (so you can hold us to cite-don't-fork)

- Render the benchmark node tree through **the SDK navigator** (once the tree renderer lands — a11y note),
  never a 4th renderer.
- Import `PROVENANCE_DEFAULTS` from the SDK for REQ-10 FR-4's dual-axis, not mirror the legal file. If the
  import path stays fragile, we'll cite it and flag the fork risk rather than copy the frozenset.

## Small asks for the SDK team

1. Treat `navigator.models.Node` + the audience/fluency lenses as a **stable cross-repo contract**.
2. Treat `kickoff_experience.manifest.PROVENANCE_DEFAULTS` as **public/stable**; consider a thin export so
   consumers drop their fallback copies.
3. (Separately) the a11y-renderer track — see the companion note.

## References (grounded homes — cite, don't copy)

- `startd8-sdk/src/startd8/navigator/` (models.py, project.py, wireframe_view, cli_navigator.py).
- `startd8-sdk/src/startd8/kickoff_experience/manifest.py:38` (`PROVENANCE_DEFAULTS`).
- `startd8-work/src/startd8_work/legal/navigator_export.py:61-63` (consumer + fallback).
- dev-os: `VISUALIZATION-CAPABILITY-CATALOG.md`, `REQ-10-Navigate-Benchmark-As-Node-Tree.md` (FR-4/NR-3),
  `PRINCIPLE-INDEX.md` (Kagami — the fork-risk principle behind the fallback-frozenset smell).

*Grounded 2026-08-14 by direct read (file:line above). No SDK code changed by this note.*
