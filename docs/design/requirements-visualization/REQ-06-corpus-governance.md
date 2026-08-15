# Corpus Governance — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — this is the spec-only deliverable; plan follows)*
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-01-sdk-node-home (parent) · REQ-02-n-level-tree-renderer · REQ-03-a11y-renderer-and-corpus-index · REQ-04-lift-lenses-to-shared-transform · REQ-05-graph-topology-renderer
**Audience:** operator (SDK contributors; requirements-corpus authors; the loop family)
**Trust boundary:** local filesystem + authored req docs; no network fetch; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-governs-a-directory-of-6b37edab`
> **Semantic name:** *SDK navigator governs a DIRECTORY of requirement docs — asserting name-block presence, single-line-FR conformance, no dangling cross-refs, index freshness, and per-doc coverage — emitting a pass/fail governance report that plugs into the existing loop family rather than a parallel mechanism.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-06`

---

## 0. Why this exists — the governance counterpart to the corpus INDEX

`VISUALIZATION_VARIANTS_ANALYSIS.md` §7 surfaced REQ-06 as an emergent, cross-cell requirement:
**corpus governance** = `corpus-index (REQ-03) × the provenance/cruft/inspect loops`. The distinction
is deliberate and load-bearing:

| Capability | Question it answers | Verb | Home |
|-----------|--------------------|------|------|
| **REQ-03 corpus index** | "what's in the corpus, and how healthy does each doc look?" | **renders** | `navigator/render_index.py` |
| **REQ-06 corpus governance** | "does the corpus obey the discipline it claims to?" | **governs** (pass/fail) | this REQ |

The corpus index already computes a per-doc *health* glyph for a human to read; it does **not** assert
a corpus-wide *contract* an author (or CI) can fail on. REQ-06 is that contract — the enforcement
backstop for the standing conventions the corpus has accrued: `NAMING_CONVENTION.md` (semantic name,
not integer+type alone), the **single-physical-line FR** rule (`parse_fr_lines` is per-line — a
hard-wrapped FR silently drops `Name:`/`Touches:`/`Verify:`), and the "every REQ has a deterministic
`Name:` block + Objectives + FRs + Verify" discipline REQ-01..05 now model.

**Governance is a discipline over the CORPUS, not a lint of one doc.** A single-doc lint can't see an
index that lags the docs, a cross-ref to a REQ that was renamed away, or an orphaned doc no index
links. Those are corpus-level facts, and they are exactly the failure modes an unwatched requirements
directory drifts into.

**Mottainai (reuse, don't reinvent).** Five governance loops already exist
(`docs/LOOP_CATALOG.md` #1–5) plus the dev-os rung-4 `cruft_lint.py`; the a11y corpus index already
parses every doc into a `ReqView` and computes health. REQ-06 **formalizes and unifies** the
already-computed signals into one fail-on-drift contract + report — it does **not** build a second
parser, a second health model, or a second loop engine. The whole spec is biased toward wiring
existing plumbing (`ReqView`, `_req_summary`, `parse_fr_lines`, `naming.name_forms`, the loop ledgers)
into a single `navigator govern` seam.

---

## Overview

Add a **read-only corpus-governance pass** to the SDK navigator: given a directory of requirement
docs, run a fixed battery of deterministic checks (name-block presence, single-line-FR conformance,
dangling cross-ref detection, index freshness, per-doc coverage) and emit a machine- and
human-readable **governance report** with a pass/fail verdict per check and an overall exit code
(0=clean / 1=drift / 2=error), suitable for CI and for the loop family to consume. Every check reuses
an existing parser/primitive; the report format mirrors the loop ledgers so the governance pass is a
first-class member of the catalog (`docs/LOOP_CATALOG.md` #6), not a parallel mechanism.

## Objectives

- **O-1:** A single `startd8 navigator govern --dir <corpus>` pass runs the full check battery over a
  directory of requirement docs and emits a governance report (pass/fail per check + overall verdict)
  — target: exit 0 on a clean corpus, exit 1 on any drift, exit 2 on operational error.
- **O-2:** Each check is a **precise, low-false-positive** assertion of an existing convention
  (name-block, single-line-FR, cross-refs, index-freshness, coverage), reusing the existing
  parsers/primitives rather than a new one — target: zero false positives on the current corpus
  (REQ-01..05 all pass) and each failure names the exact doc + line + fix.
- **O-3:** Governance plugs into the **existing loop family** and its ledger convention (LOOP_CATALOG
  #1–5 + `cruft_lint`), not a new mechanism — target: a `docs/LOOP_CATALOG.md` #6 entry, a ledger under
  `_pilot/`, and drift routing to the same downstream skills the sibling loops already use.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | False positives crying wolf — a governance pass that fails on conformant docs trains authors to ignore it (the boy-who-cried-wolf failure) | **Precision gate:** each check must score **zero false positives on the current corpus (REQ-01..05)** as an acceptance condition (FR-8); heuristics that can't hit zero degrade to advisory, never fail the build | high |
| quality | Over-governance as iatrogenic cruft — piling on checks the corpus never violates, so the pass itself becomes noise/maintenance drag (governance as accidental complexity) | Charter is a **closed, minimal** battery (the 5 checks named here); a new check requires a demonstrated real drift + a LOOP_CATALOG rationale (NR-6); the pass reuses existing primitives, adds no new parser | high |
| quality | Re-deriving health/parse logic already in `render_index._req_summary` / `ReqView` → mirror drift | **Kagami:** govern reads through the *same* `ReqView` + `parse_fr_lines` the index/pilot loops use; no second parser or health model (FR-9) | high |
| scope-creep | Governance mutating docs (auto-fix) — turning a read-only audit into an editor | NR-2: govern is **read-only** (report only); a fix is a human action or a downstream skill hand-off, never inline | medium |
| quality | Index-freshness check flapping on cosmetic diffs (timestamps, whitespace) | Freshness is defined structurally (does the index link every current `REQ-*.md`, and does each linked doc still exist) — **not** a byte-diff of the rendered HTML (FR-5) | medium |

## Functional requirements

- **FR-1 — Name-block presence check.** Assert every `REQ-*.md` in the corpus carries the deterministic NAME BLOCK (Readable handle + Semantic name + Canonical ref) and that each FR bullet carries an authored `Name:` field, per `NAMING_CONVENTION.md`; a doc/FR identified by integer+type alone is the anti-pattern this check fails on. Name: Corpus governance asserts every REQ doc and every FR carries a deterministic semantic name block. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/cli_navigator.py`. Lives: convention docs/NAMING_CONVENTION.md · code src/startd8/navigator/naming.py. Approve?: does the check reuse `det_req.parse_name` / `naming.name_forms` rather than a new name parser?. Verify: `navigator govern --dir <corpus>` fails a doc missing the handle/semantic-name/canonical block and any FR with no `Name:`, naming the doc + FR id; REQ-01..05 pass. Serves: O-1, O-2
- **FR-2 — Single-line-FR conformance check.** Assert every FR bullet is ONE physical line, because `det_req.parse_fr_lines` is per-line — a hard-wrapped FR silently drops `Name:`/`Touches:`/`Lives:`/`Verify:`; the check flags any FR whose grammar fields would be lost to a line break. Name: Corpus governance asserts every FR bullet is a single physical line so no grammar field is silently dropped. Touches: `src/startd8/navigator/govern.py`. Lives: code src/startd8/navigator/det_req.py. Approve?: does the check dogfool by comparing per-line-parsed FR count to the authored FR-bullet count (a mismatch = a wrapped/dropped FR)?. Verify: a corpus with a hard-wrapped FR fails with the offending doc + FR id + line; a corpus where every FR is single-line passes; `navigator build --format json` FR count equals the authored FR-header count. Serves: O-1, O-2
- **FR-3 — Dangling cross-ref detection.** Assert every intra-corpus cross-reference resolves: `REQ-0n` inline citations and `Inherits standards` entries by **numeric prefix** (a slug tail may drift, so prose-labelled `Inherits` entries are advisory not fail); `Pairs with` and Lives/Touches **paths** resolve to a repo file — but **exclude a doc's own to-be-built deliverable paths** (a spec may cite files it is the deliverable for); flag orphan docs (a `REQ-*.md` with no index and no sibling references) as a distinct, lower-severity advisory. Name: Corpus governance detects cross-references to renamed or missing REQ docs by numeric prefix and flags orphaned docs without false-failing on a spec's own unbuilt deliverables. Touches: `src/startd8/navigator/govern.py`. Lives: code src/startd8/navigator/render_index.py. Approve?: is a broken `REQ-0n` reference a fail while a prose-label drift or unbuilt-own-deliverable is advisory?. Verify: a `REQ-99` citation makes govern fail naming the dangling ref + its citing doc; a fully cross-linked corpus (REQ-01..09) passes with zero fail-severity. Serves: O-1, O-2
- **FR-4 — Coverage check (objectives + FRs + verify present).** Assert every parseable REQ declares Objectives, ≥1 FR, and a `Verify:` on every FR, and — when a doc uses `Serves:` — that every Objective is served by ≥1 FR; reuse the exact gap logic `render_index._req_summary` already computes (orphan FRs, missing verify, unmitigated high risks, unserved objectives). Name: Corpus governance asserts every REQ has objectives, FRs, and a verify per FR, reusing the corpus-index gap logic. Touches: `src/startd8/navigator/govern.py`. Lives: code src/startd8/navigator/render_index.py. Approve?: does coverage read through the same `ReqView` gap computation the corpus index uses (no second health model)?. Verify: a doc with an FR missing `Verify:` or an Objective no FR serves fails with the specific gap; REQ-01..05 pass; the verdict matches the index's per-doc health for the same corpus. Serves: O-1, O-2
- **FR-5 — Index-freshness check.** Assert the rendered corpus index (REQ-03) is current with the docs on disk: every present `REQ-*.md` appears as an index row and every linked leaf still resolves to an existing doc — defined structurally (link set vs doc set), not as a byte-diff of the HTML, so cosmetic re-renders don't flap. Name: Corpus governance asserts the rendered corpus index links exactly the requirement docs on disk. Touches: `src/startd8/navigator/govern.py`. Lives: code src/startd8/navigator/render_index.py. Approve?: is freshness a structural link-set comparison (not a byte-diff) so it won't flap on cosmetic diffs?. Verify: adding a new `REQ-*.md` without regenerating the index fails freshness naming the unindexed doc; a deleted doc still linked fails naming the stale link; a corpus whose index matches disk passes. Serves: O-1, O-2
- **FR-6 — `navigator govern` CLI + governance report.** Add `startd8 navigator govern --dir <corpus> [--format text|json] [--out <path>]` that runs the full check battery read-only and emits a report (per-check pass/fail, per-finding doc+FR+line+fix, an overall verdict) with exit 0=clean / 1=drift / 2=operational-error, consistent with REQ-02/REQ-03 CLI vocabulary and additive to existing commands. Name: Navigator CLI exposes a read-only corpus-governance command emitting a pass/fail report with a drift exit code. Touches: `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/govern.py`. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: is `govern` additive (no break to build/ground/index) and read-only (never writes into the corpus)?. Verify: `startd8 navigator --help` lists `govern`; a clean corpus exits 0, a corpus with drift exits 1 and prints per-check verdicts, a missing `--dir` exits 2; existing `build`/`ground`/`index` unchanged. Serves: O-1, O-3
- **FR-7 — Loop-family integration (LOOP_CATALOG #7).** Register governance as loop **#7** in `docs/LOOP_CATALOG.md` (#6 is already the Spec Delivery Loop, whose stage-0 gate govern generalizes) with a moving number (`govern_score` = clean checks / total checks) and a ledger under `_pilot/`, routing drift to the same downstream skills the sibling loops already use (cruft → `/audit-then-metabolize`; a recurring finding-class → `/metabolize-finding` to make it structurally impossible), rather than a standalone mechanism. Name: Corpus governance is registered as loop #7 and routes recurring drift to the existing metabolize skills. Touches: `docs/LOOP_CATALOG.md`, `src/startd8/navigator/govern.py`, `docs/design/requirements-visualization/_pilot/`. Lives: doc docs/LOOP_CATALOG.md · code scripts/navigator_cruft_loop.py. Approve?: does #7 cite the existing loops/`cruft_lint` it composes instead of duplicating them?. Verify: `docs/LOOP_CATALOG.md` gains a #7 entry (does/driver/moving-number/run/state/status); govern writes a `_pilot/ledger-govern.{json,md}`; a recurring class prints the `/metabolize-finding` invocation. Serves: O-3
- **FR-8 — Precision gate (zero false positives on the current corpus).** Every check must produce **zero false positives** on the current corpus (REQ-01..05 all pass `govern`) as a shipped acceptance condition; a heuristic that cannot reach zero degrades to an **advisory** finding (reported, never fails the exit code) so the pass never cries wolf. Name: Corpus governance guarantees zero false positives on the current corpus, degrading uncertain checks to advisory. Touches: `tests/unit/navigator/test_govern.py`, `src/startd8/navigator/govern.py`. Lives: test tests/unit/navigator/test_govern.py. Approve?: is the precision gate a hard acceptance test (REQ-01..05 must pass clean) not just documentation?. Verify: `govern --dir docs/design/requirements-visualization` exits 0 on the current corpus; a test asserts REQ-01..05 raise no fail-severity finding; any advisory-only check is excluded from the exit-1 verdict. Serves: O-2
- **FR-9 — Single-parser reuse (Kagami, no mirror drift).** Every check reads through the existing `ReqView` / `det_req.parse_fr_lines` / `naming.name_forms` / `render_index` primitives — govern owns **no** second doc parser, FR parser, or health model; a check needing a new signal extends the shared primitive, it does not fork it. Name: Corpus governance reads through the one shared parser and health model, never a forked copy. Touches: `src/startd8/navigator/govern.py`. Lives: code src/startd8/navigator/render_a11y.py · code src/startd8/navigator/det_req.py. Approve?: does `govern.py` import the shared `ReqView`/`parse_fr_lines`/`name_forms` rather than re-implement parsing?. Verify: `grep -n "def parse_fr\|class ReqView\|def name_forms" src/startd8/navigator/govern.py` returns nothing; govern's per-doc health equals `render_index`'s for the same corpus. Serves: O-2, O-3

## Non-goals

- NR-1: A new corpus-index *renderer* — REQ-06 governs; REQ-03 renders. Govern may reuse the index's parse to check freshness but does not restyle or replace the index view.
- NR-2: **Auto-fix / mutation.** Govern is read-only (report + exit code only); a fix is a human edit or a downstream-skill hand-off (`/audit-then-metabolize`, `/metabolize-finding`), never an inline rewrite.
- NR-3: A second requirements parser, FR parser, or doc-health model — govern reuses `ReqView` / `parse_fr_lines` / `naming` / `render_index` (FR-9). Building a parallel one is the accidental complexity this REQ exists to avoid.
- NR-4: Governing non-requirement corpora (plans, lessons, capability manifests) — scoped to `REQ-*.md` directories; a second corpus type is a follow-on with its own loader.
- NR-5: Semantic/quality judgement of FR *content* (is the requirement good?) — that is the Pilot/Content loops (#1/#2); govern asserts structural conformance only.
- NR-6: Growing the check battery beyond the five named here without a demonstrated real drift + a LOOP_CATALOG rationale (the over-governance guard); a speculative check is iatrogenic cruft.
- NR-7: A new CSS/design system for the report — text + JSON only (offline, no CDN); the human view rides the existing index/a11y shell if an HTML report is ever added.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `docs/NAMING_CONVENTION.md` · `docs/LOOP_CATALOG.md` · `dev-os/NODE-SCHEMA.md` · `VISUALIZATION_VARIANTS_ANALYSIS.md` §7 (REQ-06 emergent)

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-govern | command | structure | new: `startd8 navigator govern --dir … [--format text\|json] [--out …]` |
| format-govern | option | structure | `--format text\|json` (report shape) |
| govern-verdict | exit-class | structure | exit 0=clean / 1=drift / 2=error; per-check pass/fail |

Library seams (Touches file paths): `src/startd8/navigator/govern.py` (new),
`src/startd8/navigator/cli_navigator.py`, `tests/unit/navigator/test_govern.py`,
`docs/LOOP_CATALOG.md`, `docs/design/requirements-visualization/_pilot/ledger-govern.{json,md}`.

Primitives reused (no new parser — FR-9): `navigator/det_req.py` (`parse_fr_lines`, `parse_name`),
`navigator/naming.py` (`name_forms`, `slug`), `navigator/render_a11y.py` (`ReqView`),
`navigator/render_index.py` (`_req_summary` gap logic, `_doc_title`), the LOOP_CATALOG loop family
(#1–5) + dev-os `cruft_lint.py` (rung-4 backstop).

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.1 — formalizes the emergent REQ-06 (corpus governance) from VISUALIZATION_VARIANTS_ANALYSIS.md §7: the governance counterpart to REQ-03's corpus INDEX. Reuse-first (Mottainai/Kagami); read-only; precision-gated against crying wolf; charter-bounded against over-governance. Ready for CRP.*
