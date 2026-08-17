# Seat requirement authoring on det-req and Definer round-trip — Requirements

**Project:** startd8-sdk (requirements visualization ladder) · **Criticality:** high  
**Version:** 0.4.1 (Post CRP R1 + FR Name/marker repair) · **Date:** 2026-08-14  
**Format:** det-req/0.1  
**Backend:** visual-editor-capability  
**Pairs with:** `PLAN-seat-requirement-authoring-on-det-req-definer.md`  
**Inherits standards:** det-req-kit · NODE-SCHEMA · HOWTO-VISUALIZE-A-REQUIREMENT · VISUAL-REQUIREMENTS-DEFINER-ROADMAP · OPERATOR-PANEL-UX-STANDARD · DELIVERY_EVIDENCE_CONTRACT · DETERMINISTIC_INTENT_DELIVERY_LANGUAGE (DIDL)  
**Audience:** operator  
**Trust boundary:** authored graph/det-req is human-owned; derived overlays (evidenceVerification / health) and any `Touches:`-mined refs are read-only / `provenance: derived` — they must not clear the FR-4 evidence gate or become a second authored store  

> **DIDL identity (document)** — not an integer phase brand:  
> - **Semantic name:** Seat requirement authoring on det-req and Definer round-trip  
> - **Local key (initiative):** `FEAT-req-authoring-seat` (ladder: after SDK Node home)  
> - **Canonical ref (planned):** `cc:intent:startd8-requirements-visualization:feature:feat-req-authoring-seat`  
> - **Readable handle:** `feature/seat-requirement-authoring-on-det-req-and-definer-round-trip`  
> Product capability ≠ code capability-index.

---

## 0. Planning Insights (Self-Reflective Update)

> Drafted after Phase 1/2 ship + ATM research inventory. Planning/research falsified the
> TOP_DOWN one-liner that “Requirements Panel emits det-req.”

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Requirements Panel is the emit seat | Panel REQ/PLAN = persona **prose elicitation** only (no det-req/`Lives:`) | **FR-1:** Definer `detReqWriter` is the emit seat; Panel is optional upstream elicitation |
| Need a new SDK writer for det-req | Live path: `loops/builder/writers/detReqWriter.js` + `roundtrip.sh --no-serve` | Mottainai — extend Definer/roundtrip; do not fork a second writer in startd8 |
| Phase 3 = only HTML polish | Differentiator = easy + powerful + well-architected **authoring loop** (HOWTO §6) | FRs cover UX laws, evidence gate, dual render, corpus — not chrome alone |
| Integer `REQ-03` naming | DIDL four-form identity | Filenames/titles use semantic slug; in-body `FR-*` local keys retained |
| SDK navigator replaces CC a11y | HOWTO still cites CC a11y + corpus; SDK owns Node home | Dual consumers: `startd8 navigator` + CC a11y/cockpit; one grammar/store |
| `/private/tmp/contextcore-delivery-evidence/` is SSOT | Path absent; contract lives in ContextCore docs; dogfood under `/private/tmp/roundtrip-*` | Cite ContextCore `DELIVERY_EVIDENCE_CONTRACT.md` |

**Resolved open questions:**
- **OQ-emit → Definer emit; Panel elicitation.** Both may compose later (elicitation → graph/det-req), but emit authority is Definer write-back.
- **OQ-renderer → no 2nd renderer/grammar/store** (Definer roadmap lock; inherits Phase 1 CRP).

### 0.1 CRP R1 hardening (v0.4)

| ID | Merged into |
|----|-------------|
| R1-F1 | Trust boundary + FR-4 / FR-6 provenance |
| R1-F2 | FR-4 three-way parity (`fr_health`) |
| R1-F3 | Contract projection **Wire form** + FR-1/FR-2 |
| R1-F4 | FR-6 parse-loss floor |
| R1-F5 | FR-7 typed skip + expiry |
| R1-F6 | FR-11 + O-5 cold-start |

---

## 0.3 Delivery split (2026-08-16 — the loop's ownership pass)

> The planning pass mapped each FR to its OWNING repo. This spec spans three: only a small SDK slice is
> navigator-internal; the bulk is the dev-os Visual Requirements Definer + the ContextCore a11y consumer,
> **delegated to their dev teams via handoff docs** (per the operator's instruction).

| FR | Owner | Status |
|----|-------|--------|
| **FR-4 (SDK part) — the health twin** | **startd8-sdk** | ✅ **BUILT** — `sources_requirements.py` now computes the FR-4 evidence-gate health class from **authored `Lives:` only**; a mined `Touches:` ref (`provenance: derived`) no longer clears the done-claim gate (R1-F1 fixed — the SDK twin now agrees with `req-health.mjs`/`extract.py`). |
| **FR-6 — SDK navigator + parse-loss floor** | **startd8-sdk** | ✅ **BUILT** — `navigator build --source requirements` now exits non-zero with a named **parse-loss** when the projected node count ≠ the source's FR-marker count (R1-F4 — symmetry with FR-3's fail-loud gate). |
| FR-1, FR-2 (Definer emit + inspector), FR-3, FR-5 (roundtrip), FR-4 (`req-health.mjs`/`extract.py` twins), FR-8 (HOWTO §6), FR-11 (cold-start) | **dev-os** | 🔵 **DELEGATED** → `dev-os/HANDOFF_seat-requirement-authoring-definer-side.md` |
| FR-7 (CC a11y consumer) | **ContextCore** | 🔵 **DELEGATED** → `ContextCore/HANDOFF_seat-requirement-a11y-consumer.md` |
| FR-9 (DIDL naming), FR-10 (Panel sibling) | doc-only | ✅ satisfied by this doc's DIDL header + the Panel cross-link |

## Overview

Make **requirement authoring** the startd8/dev-os differentiator: an operator seats NODE-SCHEMA
fields (DOES / WON'T / LIVES / SHIPS-WHEN / Approve?) in the **Visual Requirements Definer**,
exports **det-req/0.1** with evidence locators, validates via **one-command round-trip**, and
renders in navigators that already speak Nodes — without a second grammar, store, or HTML backend.

This is the **up** ladder after SDK Node home (substrate) and evidence/Approve? leaves. Ease =
Panel Laws + HOWTO §6 recipe; power = Lives/evidence/FLCM overlays; architecture = DIDL +
det-req-kit + Definer It-1…It-6 compose locks.

## Objectives

- O-1: An operator authors a requirement Node in Definer and gets a valid det-req/0.1 export with `Lives:` / `Approve?:` / `Was:` when set — target: one round-trip green on dogfood graph  
- O-2: Headless CI proves define ⟷ validate without a local HTTP server — target: `roundtrip.sh --no-serve` exit 0 on fixture + fail-loud on empty navigator JSON  
- O-3: Glance validation uses SDK and/or CC navigators against the **same** det-req bytes — target: no forked schema  
- O-4: Authoring UX obeys OPERATOR-PANEL-UX + SV-1…10 on the Definer/validation surfaces that Phase 3 ships or gates — target: cruft_lint bleed = 0 on emitted preview HTML (tool must have *run*, or typed skip)  
- O-5: Cold-start ease — a fresh operator produces a valid det-req from the dogfood seed in ≤5 documented steps with zero undocumented prerequisites  

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Second writer / second store drifts from det-req-kit | Single emit: Definer `detReqWriter`; schema cite only | high |
| quality | Conflating elicitation Panel with emit seat | FR-1 + NR-Panel-emit; Panel remains prose sibling | high |
| cost | Rebuilding CC a11y cockpit inside SDK | NR — reuse CC a11y; SDK HTML is Node/wireframe profile path | medium |
| availability | Roundtrip depends on editable ContextCore install lag | HOWTO propagation note; pin `--no-serve` artifacts under `/tmp` | medium |
| safety | Derived evidence overlays become authored truth | Read-only overlay; detReqWriter ignores verification fields | high |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Emit seat is Definer.** Name: The Visual Requirements Definer write-back is the sole det-req emit authority not the persona panel. Requirement authoring that produces det-req/0.1 is owned by the Visual Requirements Definer write-back (`detReqWriter`), not by the persona Requirements Panel. Touches: `loops/builder/writers/detReqWriter.js`, `VISUAL-REQUIREMENTS-DEFINER-ROADMAP.md`. Lives: code `/Users/neilyashinsky/Documents/dev/dev-os/loops/builder/writers/detReqWriter.js`. Approve?: is Definer the only emit authority?. Verify: exported markdown validates as det-req/0.1 via `det-req-kit/extract.py --report` exit 0 on the evidence dogfood graph export **and** matches the Contract projection Wire form. Serves: O-1

- **FR-2 — NODE fields on the inspector.** Name: The Definer inspector authors the NODE-SCHEMA fields per node without a Studio-only schema. The Definer inspector authors DOES / Verify / WON'T / optional Lives / Approve? / Was aliases per node without inventing a Studio-only schema. Touches: Definer inspector, NODE-SCHEMA. Verify: round-trip graph → det-req → re-project preserves those fields lossless for the dogfood fixture against the Wire form (It-6 compose bar). Serves: O-1

- **FR-3 — Headless round-trip gate.** Name: The headless round-trip exports validates via navigator JSON and fails loud on empty output. `roundtrip.sh --no-serve` exports, validates via navigator JSON, and fails loud on empty/malformed navigator output. Touches: `loops/builder/roundtrip.sh`, exit classes. Lives: code `/Users/neilyashinsky/Documents/dev/dev-os/loops/builder/roundtrip.sh`. Verify: `roundtrip.sh --no-serve` on `fixtures/evidence-dogfood.graph.json` exits 0; broken navigator stub exits non-zero with a named reason. Serves: O-2

- **FR-4 — Evidence gate before render.** Name: Three health twins agree on a done-claim's evidence class before render and mined refs never clear the gate. Done-claim Verifies without strong authored `Lives:` (or honest-skip) are visible as UNKNOWN / advisory before HTML render. **Three** twins must agree on class ∈ {`n/a`,`skipped`,`unknown`,`on_track`}: Studio `req-health.mjs`, kit `extract.py --report`, and SDK `startd8.navigator.det_req.fr_health`. `Touches:`-mined path refs (if any) are `provenance: derived` and **must not** clear this gate. Touches: `req-health.mjs`, `det-req-kit/extract.py`, `src/startd8/navigator/det_req.py`, EVIDENCE-1. Verify: fixture with done-claim and no authored Lives shows `unknown` in all three; strong `git:` clears it; fixture with only Touches-mined refs stays `unknown` for the gate. Serves: O-1, O-4

- **FR-5 — Optional dossier / FLCM overlay.** Name: The round-trip attaches dossier and forward-manifest as derived read-only overlays independent of the export. Round-trip may attach `--dossier` / `--forward-manifest` as **derived read-only** overlays; export remains independent of overlay parse failure. Touches: `roundtrip.sh`, DELIVERY_EVIDENCE_CONTRACT. Verify: overlay failure cannot block det-req export; Health routes drift to attention without writing overlay fields into authored det-req. Serves: O-2

- **FR-6 — SDK navigator consumes the same det-req.** Name: The SDK navigator renders the exported det-req with Node shape and a parse-loss floor on the round-trip. `startd8 navigator build --source requirements` renders the exported det-req with Node-domain shape (no app-cascade bleed) and paints Lives / Approve? / Was. Touches: `src/startd8/navigator/`, `src/startd8/wireframe/shape_dialect.py`, `startd8.wireframe.profile`. Lives: code `src/startd8/navigator/cli_navigator.py`. Verify: export from FR-3 → build HTML shows Nodes/Sections; **node count equals FR count in the export and is non-zero** (else non-zero exit / named parse-loss); at least one authored Lives line when present; `~/Documents/dev/dev-os/scripts/cruft_lint.py` Entities/CRUD bleed = 0 **or** typed skip if tool absent. Serves: O-3, O-4

- **FR-7 — CC a11y remains a first-class consumer.** Name: ContextCore a11y validates the same det-req bytes or records a typed expiring skip. Operators can validate the same bytes with ContextCore a11y/corpus navigators per HOWTO §6 without an SDK reimplementation of the cockpit. Touches: HOWTO-VISUALIZE-A-REQUIREMENT, ContextCore `navigator`. Verify: documented command path succeeds on the same det-req file used in FR-6 **or** records a typed skip (`install-propagation`) with pinned ContextCore version + expiry date in the round-trip/report artifact; gate fails after expiry. Serves: O-3

- **FR-8 — HOWTO §6 is the operator recipe.** Name: The operator recipe is the cited HOWTO section six authoring loop not a parallel checklist. Phase-3 acceptance is the documented loop: normalize det-req → evidence gate → optional Definer round-trip → render → cruft → Panel Laws/SV score — cited, not restated. Touches: `HOWTO-VISUALIZE-A-REQUIREMENT.md` §6. Verify: README/operator note for this feature links HOWTO §6 steps 1–7 without inventing a parallel checklist. Serves: O-4

- **FR-9 — DIDL naming on authored artifacts.** Name: New authored ladder docs use DIDL four-form identity with no integer-led filenames. New REQ/PLAN/initiative docs for this ladder use DIDL four-form identity (semantic name / canonical ref / readable handle); no new integer-led `REQ-NN` / `PLAN-NN` filenames. Touches: `.cursor/rules/intent-delivery-naming.mdc`, DIDL overview. Verify: this pair’s filenames contain no `REQ-0`/`PLAN-0` ordinal brand; header carries semantic name + planned canonical ref. Serves: O-1

- **FR-10 — Elicitation Panel stays a sibling.** Name: The persona requirements panel drafts prose candidates without claiming det-req emit authority. The persona Requirements Panel may draft prose candidates; it must not silently claim det-req emit authority. Touches: `docs/design/requirements-panel/`. Verify: Panel docs (or a one-line cross-link) state emit seat = Definer; no Panel CLI writes det-req/0.1 in this iteration. Serves: O-1

- **FR-11 — Cold-start operator path.** Name: A fresh operator reaches a valid det-req from the dogfood seed in five documented steps. Ship the dogfood graph (or a checked-in export golden) as the seed plus one copy-paste command in this folder’s README, with a measurable ease target. Touches: `docs/design/requirements-visualization/` README, dogfood fixture/golden. Verify: fresh-checkout dry run following only this folder’s README + HOWTO §6 reaches a valid det-req in ≤5 documented steps; every prerequisite is listed in those docs. Serves: O-5

## Non-goals

- Replacing ContextCore a11y cockpit inside startd8  
- Auto-generating hand fsn navigator READMEs  
- Interactive/3D fsn navigator  
- Merging Requirements Panel elicitation into Definer in this iteration (composition is a later feature)  
- Shared npm/Python package for Node across repos (Phase 1 deferred F-CC-1 stands)  
- Making Feature O11y / WorkItem `satisfies` join mandatory for export  

## Owned fields

Only humans enter: Definer node DOES / Verify / WON'T / Lives refs / Approve? prompts / Was aliases · initiative semantic names · dossier paths when used  

## Contract projection

- **Backend:** visual-editor-capability  
- **Vocabulary home (cite):** `dev-os/visual-editor/VISUAL-REQUIREMENTS-DEFINER-ROADMAP.md` · `det-req-kit/SCHEMA.md` · DIDL overview  

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| detReqWriter | writer | graph → det-req/0.1 | Emit authority |
| roundtrip.sh | command | `--no-serve` | Headless gate |
| req-health.mjs | gate | Lives advisory twin | Studio evidence gate |
| startd8 navigator build | console-script | `--source requirements` | SDK consumer |
| extract.py --report | command | exit + lives_advisory | Kit evidence gate |
| fr_health | gate | `n/a`/`skipped`/`unknown`/`on_track` | SDK twin (R1-F2) |
| Wire form | serialization | one FR per markdown line; `Approve?:` / `Was:` separators `·` `\|` `;`; strong Lives `git:<40hex>:<path>`; `Lives:` before `Verify:` | Shared golden for writer ↔ SDK parse (R1-F3) |
| cruft_lint.py | command | `~/Documents/dev/dev-os/scripts/cruft_lint.py` | Must run or typed skip (R1-S1) |

## Appendix A — Accepted (with where merged)

| ID | Where merged |
|----|----------------|
| R1-F1…F6 | Trust boundary, FR-1/2/4/6/7, FR-11, O-5, Wire form / fr_health projection rows |

## Appendix B — Rejected (with rationale)

*(none — all R1-F* accepted)*

## Appendix C — Incoming review rounds

*(see Iterative Review Log below)*

*v0.4 — Post CRP R1 triage (all 6 F-suggestions accepted). Ready for implementation.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Touches-mined ≠ authored Lives; provenance derived | CRP R1 | Trust boundary + FR-4/FR-6 | 2026-08-14 |
| R1-F2 | Name SDK `fr_health` as third twin | CRP R1 | FR-4 + Contract projection | 2026-08-14 |
| R1-F3 | Byte-level Wire form | CRP R1 | Contract projection + FR-1/FR-2 Verify | 2026-08-14 |
| R1-F4 | FR-6 parse-loss floor | CRP R1 | FR-6 Verify node count | 2026-08-14 |
| R1-F5 | FR-7 typed skip + expiry | CRP R1 | FR-7 Verify | 2026-08-14 |
| R1-F6 | Cold-start FR-11 + O-5 | CRP R1 | New FR + objective | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-5 — 2026-08-14

- **Reviewer**: claude-opus-5
- **Date**: 2026-08-14 19:45:00 UTC
- **Scope**: Requirements-side (F-prefix) review of the emit-seat / round-trip / dual-consumer FRs, grounded in targeted reads of the cited SDK consumer (`src/startd8/navigator/det_req.py`, `sources_requirements.py`, `cli_navigator.py`) and `scripts/navigator_pilot_loop.py`. Focus asks 1–3 answered below; **ask 4 (plan iterations) is answered in the PLAN file's R1 block.**

##### Focus-file asks

**Ask 1 — Emit seat: is Definer-as-sole-authority (FR-1) plus Panel-as-elicitation (FR-10) right, or must Phase 3 ship a Panel→det-req bridge?**

- **Summary answer:** Yes — keep Definer `detReqWriter` as sole emit authority; do **not** put a Panel→det-req bridge in Phase 3 scope.
- **Rationale:** FR-1 plus the high-priority Risks row "Second writer / second store drifts from det-req-kit" already carry this. A bridge would add a second writer *before* the first writer's output is pinned to what the consumer actually parses — and that pin does not exist yet: the SDK's `parse_fr_lines` is documented "Minimal FR bullet parser (single-line det-req FR shape)" and its Approve?/Was regexes accept only specific separators (see R1-F3). Adding a second emit path on top of an unspecified wire form is how the FR-1 risk materializes.
- **Assumptions / conditions:** Panel prose is human-carried into Definer for one iteration (copy/paste friction accepted); FR-10's cross-link actually lands (plan F-5).
- **Suggested improvements:** (a) give FR-1 a *negative* acceptance test — a repo grep gate asserting no non-Definer writer emits `Format: det-req/0.1`; (b) record the deferred bridge as a **named later feature** (DIDL semantic name) in Non-goals so each CRP round does not re-litigate it.

**Ask 2 — Ease vs power: do FR-3…FR-8 make the loop easy enough while still powerful, or is an operator onboarding FR missing?**

- **Summary answer:** Partial — power is well covered (Lives/evidence/FLCM), but **ease is asserted, not measured**; an operator onboarding FR is missing (see R1-F6).
- **Rationale:** FR-8 delegates ease to "HOWTO §6 steps 1–7" and O-4 measures only cruft bleed. Every current Verify presumes an operator who *already* has a graph, the `fixtures/evidence-dogfood.graph.json` fixture, and dev-os on disk — the first-run path (which FR-3's fixture could seed for free) is owned by no FR, so "easy" has no regression test and cannot be falsified.
- **Assumptions / conditions:** "operator" = someone with dev-os checked out but no prior Definer session.
- **Suggested improvements:** add FR-11 per R1-F6 with a measurable cold-start target; ship the dogfood graph as the operator's seed artifact plus one copy-paste command in this folder's README (Mottainai — the fixture already exists for FR-3).

**Ask 3 — Dual consumers: is FR-6 (SDK) + FR-7 (CC a11y) the right split, or should one be deferred?**

- **Summary answer:** Keep both, but demote FR-7 from co-equal gate to **doc + bounded skip** — do not defer it entirely.
- **Rationale:** FR-7's Verify ends "(or records install-propagation skip with pin note)", which makes it pass unconditionally; an unfalsifiable criterion is *worse* for architecture simplicity than an explicit deferral, because O-3 then reads "covered" whether or not a CC consumer ever ran. FR-6 is the criterion with executable teeth. Keeping CC as a *cited* consumer costs nothing and preserves O-3's "same det-req bytes"; making it a gate imports the cross-repo install lag already flagged in Risks ("Roundtrip depends on editable ContextCore install lag").
- **Assumptions / conditions:** no ContextCore-side code change is in scope this iteration.
- **Suggested improvements:** apply R1-F5 (typed skip class + pinned version + expiry, surfaced in the round-trip report) rather than deleting FR-7.

##### Executive summary

- **Biggest gap is not in the docs' prose but at the seam they assume is settled:** the SDK consumer synthesizes evidence from `Touches:` and can paint a done-claim FR **grounded green** with no authored `Lives:` — the exact case FR-4 exists to flag (R1-F1). This also crosses the header's own trust boundary.
- **The FR-4 parity is two-way but the taxonomy has three implementations.** `src/startd8/navigator/det_req.py:fr_health` is a third twin of the `unknown / skipped / on_track / n/a` classes and is the one that paints the HTML — yet it is unnamed in FR-4 (R1-F2).
- **"Lossless" (FR-2) and "export parity" (FR-1) are untestable without a wire form.** The consumer's regexes are strict about separators, label order, and line count; a graph-authored long DOES will wrap and silently vanish (R1-F3, R1-F4).
- **The FR-6 bullet has no parse-loss floor.** "at least one Lives line" passes when 9 of 10 FRs were dropped; FR-3 got a fail-loud gate and FR-6 did not — an asymmetry across the same round-trip (R1-F4).
- **The FR-7 bullet as written cannot fail** (R1-F5); this inflates O-3 coverage.
- **No FR owns the operator's first run** (R1-F6) — the answer to focus ask 2.
- **The FR-6 anchor `shape_dialect.py` is wrong-layer:** it resolves to `src/startd8/wireframe/shape_dialect.py`, and `sources_requirements.py` imports `RenderProfile` from `startd8.wireframe.profile` — plan-side correction filed as R1-S4.
- **Areas considered but not filed here:** *Security* — declared profile is **internal**, no auth/PII surface introduced; the only trust question is authored-vs-derived, filed as R1-F1 under Data. *Ops* — filed plan-side (R1-S1, R1-S3) since tool homes and fixtures are plan artifacts.
- Suggestion count is 11 across both docs (soft cap 10); the +1 is spent answering focus asks 2 and 3, which require requirement-shaped deltas rather than prose answers.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | State explicitly whether `Touches:`-mined refs count as `Lives:` for status/health, and require mined refs to carry `provenance: derived` (not `authored`) | `sources_requirements.py:_lives_from_touches` promotes existence-checked `Touches:` paths into `lives`, so a done-claim FR with **no** authored Lives can reach `grounded` green, while `req-health.mjs` / `extract.py` would classify it `unknown` — a silent disagreement on the very class FR-4 requires agreement on. It also crosses the header's own line: "derived overlays ... must not become a second authored store", and every node is stamped `"provenance": "authored"` regardless of origin | FR-6 bullet, plus one clarifying clause on the header's **Trust boundary** line | Fixture: done-claim FR, no `Lives:`, one existing `Touches:` path. Assert SDK class equals kit class, or that mined refs render as derived and do **not** clear the FR-4 gate |
| R1-F2 | Validation | high | FR-4 names two gate implementations; name the **third** (`src/startd8/navigator/det_req.py:fr_health`) and fix the canonical class set as `n/a` or `skipped` or `unknown` or `on_track` | Anchor: "Studio `req-health.mjs` and kit `extract.py --report` agree on the gap class". The SDK vendors a third implementation of that taxonomy and it is the twin that drives the rendered status — a two-way parity check leaves the deciding implementation unverified, which is how a "no second grammar" lock erodes in practice | FR-4 bullet (extend Touches list and Verify) | One table-driven fixture set run through all three implementations; assert identical class per fixture, with the SDK twin asserted in unit CI |
| R1-F3 | Interfaces | high | Add a byte-level wire form to FR-1/FR-2: one FR per line, `·` as the Approve?/Was separator, `git:<40hex>:<path>` for strong Lives, and `Lives:` before `Verify:` | "preserves those fields lossless" cannot be tested without naming the serialization. The consumer is strict: `parse_approve_prompts` stops at the first `. ` and splits only on `·`, `\|`, `;`; `parse_was_aliases` splits on `·`, `,`, `;`; `extract_lives` reads only Lives appearing **before** `Verify:`. A writer that emits any other shape passes its own tests and loses fields downstream | FR-1 and FR-2 bullets, or a new "Wire form" row under **Contract projection** | Golden byte fixture shared by both repos; round-trip equality test graph → det-req → graph, plus one writer unit test per field |
| R1-F4 | Validation | high | Give FR-6 a parse-loss floor: assert node count equals FR count in the export **and** is non-zero, exiting non-zero otherwise | FR-6's "shows Nodes/Sections counts and at least one Lives line" passes even when most FRs were dropped. `parse_fr_lines` is documented as single-line-only and `nodes_from_requirements` returns `[]` silently, so a wrapped or multi-line Definer export renders an empty page. FR-3 already demands fail-loud on empty navigator JSON; FR-6 should not be the softer half of the same loop | FR-6 Verify clause | Fixture with a deliberately wrapped FR bullet: assert non-zero exit or a named parse-loss reason; assert emitted node count equals FR count in the source |
| R1-F5 | Risks | high | Bound FR-7's skip: typed skip class, pinned ContextCore version, expiry date, and the skip must appear in the round-trip report | Anchor: "(or records install-propagation skip with pin note)" — as written FR-7 has no failing state, so O-3 reads covered whether or not a CC consumer ever ran. An always-passing criterion is worse than an explicit deferral because the coverage matrix conceals it | FR-7 Verify clause | Assert the report carries either a CC success line or a typed skip with version and expiry; the gate fails once the expiry passes |
| R1-F6 | Architecture | medium | Add **FR-11 — cold-start operator path**: ship the dogfood graph as a seed plus one copy-paste command, with a measurable ease target (first valid det-req within N documented steps, zero undocumented prerequisites) | Answers focus ask 2. Ease is currently delegated to FR-8's HOWTO cite, and every Verify presumes an operator who already has graph, fixture, and dev-os on disk. Without an FR owning the first run, "easy" — the stated differentiator — has no regression test | New FR after FR-8; add a matching target to **Objectives** (new O-5, or extend O-1) | Fresh-checkout dry run following only this folder's README plus HOWTO §6: count steps and record every prerequisite absent from the docs; the count is the gate |

**Endorsements** — none available: Appendix C had no prior rounds (R1 is the first review of this pair).

**Disagreements** — none available (no untriaged prior items).
