# Kickoff — User/Company Content & Fixture Inputs (Group G)

**Version:** 0.2 (post-CRP — 5 suggestions applied, see Appendix A)
**Date:** 2026-06-05
**Status:** Draft
**Parent:** [`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md) (master; cross-class
machinery FR-X1–X5)
**Related:** `docs/design/CONTENT_PAGES_CAPABILITY_HANDOFF.md` (the shipped pages capability),
CLAUDE.md "Generation Scope & Priority" (the bucket separation — load-bearing for this group)

---

## 1. Scope

The content the user/company provides — and the placeholder content the SDK ships in its place
until they do. Governed end-to-end by the **bucket separation**:

- **Bucket 2** (placeholder copy + static test data): SDK-generated, minimal, deliberately
  throwaway — exists only to prove the application works. **Never invest in making it good.**
- **Bucket 4** (real value content): provided by the **user / commissioning company — NOT the
  SDK.** The SDK builds the application that *holds* content; it does not author the content.

The kickoff job for this class: collect bucket-4 *references*, mark bucket-2 placeholders
honestly, and make the authored-vs-placeholder ratio visible — so "looks done" never conceals
"needs the company's real content."

---

## 2. Input Inventory (detail)

### 2.1 `prisma/pages.yaml` — content pages manifest

- **Drives:** `generate backend --pages` (`assembler.py:84`) — slug, title, `.md` content path,
  nav labels. Strict YAML validation (`pages_generator.parse_pages`); safe authoring surface
  shipped (`pages_authoring.py`: atomic create, comment-preserving, dup-safe, `/ui/pages` UI).

### 2.2 `app/pages/*.md` — content prose

- **Mechanism (the temporal model — preserve it):** the **owned shell** template is drift-tracked
  (schema + pages hashes); the rendered prose lives in an **untracked body fragment**
  (`_<name>.body.html`), regenerated from the `.md` at generate time (`pages_generator.py:275–281`).
  A `.md` edit never flags drift; a `pages.yaml` edit does.
- **Today there is NO placeholder/authored distinction** — no status field, no sentinel, nothing
  in the model distinguishes SDK stub prose from company-authored prose. That is the FR-G1 gap.
- **Authoring model:** design-time author + regenerate — the UI writes generator *inputs*
  (`pages.yaml` entry + `.md`); pages go live on the next `generate backend`.

### 2.3 `seeds/*.seed.json` — declared fixtures (e.g. `extract.seed.json`)

- **Role:** seed/fixture data for AI passes (strtd8's `extract.seed.json` feeds the `extract`
  pass) and view-test seeding. Listed in the strtd8 inventory as a non-YAML input.
- **Default posture:** generated tests use deterministic baked sample values
  (`test_emitter.py:42–52`) — fixture-free, bucket 2 by design. A user-declared fixture file is
  the *optional* enhancement, not the norm.

### 2.4 AI-pass prompt files

- Referenced by path from `ai_passes.yaml` (the owned harness embeds only the path — same
  temporal model as pages prose). Prompt prose is user-editable content; covered by the same
  FR-G1 marking convention.

---

## 3. Requirements (Group G detail)

- **FR-G1 — Placeholder/authored content marking.** Content prose (`app/pages/*.md`, AI-pass
  prompt files) MAY carry lightweight front-matter `status: placeholder | authored`. Defaults by
  origin: SDK-emitted stubs ⇒ `placeholder`; files created via the authoring UI ⇒ `authored`;
  **unknown origin** (pre-existing/adopted files with no front-matter, not SDK-emitted this run,
  not UI-created — the brownfield case) ⇒ **`placeholder`** (conservative; keeps the score
  honest). The marking MUST NOT enter the drift surface — prose stays untracked; the temporal
  model (`.md` edit ≠ drift) is preserved exactly. **Render-strip (normative, resolves former
  OQ-1):** front-matter MUST be stripped before rendered output — never visible in served HTML
  (`status: placeholder` leaking into company-facing pages is both a UX defect and an internals
  leak). If the markdown renderer (`pages_generator.py:275–281`) cannot strip front-matter, the
  implementation MUST use the sidecar form (a status field on the `pages.yaml` entry) instead;
  either way the test suite covers one page with and one without marking.
- **FR-G2 — Content provisioning score.** The run quality report includes the content class in
  the per-class `input_provisioning_score` (FR-X4): authored pages ÷ total pages. **Denominator
  (defined):** the count of `pages.yaml` entries — an entry whose `.md` file does not exist is
  status `absent` and stays in the denominator (so declaring a page before authoring it lowers
  the score honestly; the three candidate counts diverge exactly in brownfield adoption).
  **Prompt prose is a separate sub-score** (`content_prompts`), not part of the pages score —
  decided (resolves former OQ-2): different owner, different downstream effect (bucket-3 output
  quality). An all-placeholder run scores ≈ 0 on content provisioning — honest, not failing
  (bucket 2 is the intended starting state).
- **FR-G3 — Collection ≠ authorship (the bucket-4 boundary).** The pipeline collects bucket-4
  content *references* (pages.yaml entries + `.md` paths) and flags `placeholder` status
  pre-handoff. It MUST NOT generate, improve, or quality-score real company content. Bucket-2
  placeholders are generated minimal and marked — never invested in. **Enforcement (not just
  principle):** any pipeline/SDK write to a file whose status is `authored` MUST be detected and
  blocked (VALIDATE-stage check — the FR-F3 analogue); the unknown-origin ⇒ `placeholder` default
  (FR-G1) means a mislabeled brownfield file fails *safe* only if regeneration of `placeholder`
  files is also conservative — regeneration touches owned shells and SDK-emitted stubs, never
  adopted prose it didn't create.
- **FR-G4 — Declared fixtures.** A project MAY declare user-provided fixture/seed files
  (`seeds/*.seed.json`) in its inventory (FR-X5); when declared, they are provenance-recorded
  (FR-F1 pattern: path + hash + status) and used by AI-pass seeding / view-test seeding. Their
  **absence is never flagged** (unlike Group F inputs) and they are **never** matrix-mandatory
  (FR-X3) — placeholder fixtures are the intended default.

---

## 4. Acceptance (Group G)

- A fresh strtd8 run reports content `input_provisioning_score` ≈ 0 (all placeholders); marking
  one page's front-matter `authored` moves the score; the `.md` edit still does not flag drift.
- The FR-X1 pre-flight report shows per-page status without ever gating on it.
- `seeds/extract.seed.json` appears in the inventory + provenance record when present; removing
  it produces no flag.
- No SDK code path generates or rewrites a file marked `authored` (FR-G3) — regeneration touches
  only owned shells and `placeholder`-status stubs.

---

## 5. Open Questions (Group G)

1. ~~**Front-matter vs sidecar.**~~ **RESOLVED (CRP R2):** render-strip is normative in FR-G1;
   sidecar is the mandated fallback if the renderer can't strip. Remaining implementation check:
   verify `pages_generator.py` renderer behavior with front-matter input.
2. ~~**Prompt-file scoring.**~~ **RESOLVED (CRP R1):** separate `content_prompts` sub-score —
   folded into FR-G2. Remaining: the sub-score's formula.
3. **Authoring-UI default.** UI-created pages default `authored` — but a user can create a stub
   via the UI. Allow the UI to set status explicitly?

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F-cnt-1 | Reconcile FR-G2 "prompts counted separately" vs OQ-2 | R1 (opus); endorsed R2 | Decision finalized in FR-G2 (`content_prompts` sub-score); OQ-2 marked resolved, narrowed to formula | 2026-06-05 |
| R1-F-cnt-2 | Define unknown-origin (brownfield) status default; align master FR-G1 strength | R1 (opus); endorsed R2 | FR-G1: unknown origin ⇒ `placeholder`; master §5 FR-G1 reworded to MAY-with-defaults | 2026-06-05 |
| R2-F-cnt-1 | Make front-matter render-strip normative (or sidecar) | R2 (sonnet) | FR-G1 render-strip requirement + sidecar fallback; OQ-1 marked resolved | 2026-06-05 |
| R2-F-cnt-2 | Define FR-G2's "total pages" denominator | R2 (sonnet) | FR-G2: denominator = `pages.yaml` entries; missing `.md` ⇒ `absent`, stays in denominator | 2026-06-05 |
| R2-F-cnt-3 | FR-G3 enforcement check (block writes to `authored` files) | R2 (sonnet, adversarial) | FR-G3: VALIDATE-stage block + conservative-regeneration rule for adopted prose | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: claude-opus-4-8-1m (Claude Opus 4.8, 1M context)
- **Date**: 2026-06-05 (UTC)
- **Scope**: Group G slice review as part of the kickoff doc-set CRP pass.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F-cnt-1 | Validation | medium | Reconcile FR-G2 with OQ-2: FR-G2 already legislates "(prompts counted separately)" while OQ-2 still asks whether prompts join the content score or get a sub-score. Either soften FR-G2 to leave the decision to OQ-2's resolution, or finalize the sub-score decision in FR-G2 and shrink OQ-2 to its formula | A requirement and its own open question currently disagree on whether the matter is decided — an implementer can't tell if "prompts counted separately" is binding | §3 FR-G2 + §5 OQ-2 | FR-G2's scoring statement and the OQ list contain no overlapping undecided term |
| R1-F-cnt-2 | Data | medium | Define the status of pre-existing/adopted content files with unknowable origin (no front-matter, not SDK-emitted this run, not UI-created): FR-G1's defaults-by-origin covers only the two known origins. Specify the fallback (recommend `placeholder` — conservative, keeps the score honest) and align master §5 FR-G1's unconditional phrasing with the slice's MAY-with-defaults model | FR-G2's denominator needs a status for every page; brownfield adoption (existing `app/pages/*.md` trees) hits the undefined case immediately; master/slice normative strength also diverges (focus ask 1) | §3 FR-G1 (+ note to master §5) | A project adopted with three unmarked legacy `.md` pages reports a defined score with those pages in a documented default state |

**Endorsements / Disagreements:** none — first round for this file.

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-05

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-05 00:00:00 UTC
- **Scope**: Group G slice review, second pass. Focus on FR-G1 front-matter strip risk (OQ-1), brownfield origin default (R1-F-cnt-2 extension), and FR-G3 boundary enforcement.

##### Executive summary

- OQ-1 (front-matter strip at render time) is a correctness risk if unresolved: a rendered page with a YAML front-matter block that is not stripped could expose `status: placeholder` in production UI.
- FR-G3's "MUST NOT generate, improve, or quality-score real company content" has no detection mechanism — same structural gap as FR-F3 in the assembly slice.
- FR-G2's scoring formula (authored ÷ total pages) uses "total pages" as the denominator — undefined when `pages.yaml` lists pages whose `.md` files do not exist yet (absent vs placeholder distinction in the content class).

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-cnt-1 | Risks | high | Resolve OQ-1 by specifying the mechanism: front-matter MUST be stripped by the markdown renderer before serving, not just at generate time. If the current renderer (`pages_generator.py:275–281`) does not strip YAML front-matter, add that as a requirement — or choose the sidecar approach (status field on the `pages.yaml` entry) which never enters the rendered body. State the decision in FR-G1 as a normative constraint, not an open question | A `status: placeholder` front-matter block that survives into rendered HTML is both a UX defect and a data-leak of SDK internals into company-facing output. The temporal model (`.md` → rendered body) makes this invisible until a real user hits the page | §3 FR-G1 + §5 OQ-1 | A page with `status: placeholder` in front-matter renders HTML with no YAML front-matter visible; the SDK test suite covers at least one page with and one without front-matter |
| R2-F-cnt-2 | Data | medium | Define "total pages" in FR-G2's denominator: clarify whether it is (a) the count of `pages.yaml` entries, (b) the count of existing `.md` files referenced by `pages.yaml`, or (c) the count of entries where the `.md` file exists. The three counts diverge in brownfield adoption (entries with no `.md` yet) and in newly-declared pages (entries added to `pages.yaml` before their `.md` is authored) | A denominator mismatch causes FR-G2 scores to differ between implementations; "authored ÷ total pages" is ambiguous exactly where brownfield runs (R1-F-cnt-2's scenario) happen | §3 FR-G2 | An FR-G2 score computed from a fixture with 3 entries, 2 existing `.md` files (1 authored, 1 placeholder), 1 absent `.md` produces the same numeric result across two independent implementations |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-cnt-3 | Security | low | FR-G3 states the pipeline "MUST NOT generate, improve, or quality-score real company content" but has no gate or detection path — a pipeline stage could write to a file marked `authored` and satisfy all other FRs. Add a VALIDATE-stage check (analogous to the FR-F3 suggestion in the assembly slice): any pipeline write to a file whose status is `authored` MUST be flagged and blocked. The non-goal of not generating bucket-4 content needs an enforcement hook, not just a normative statement | Without enforcement, a future "auto-improve placeholder" feature could be added that respects the FR-G3 letter (it only runs on `placeholder` files) but a mis-labeling error (brownfield file with no front-matter, defaulting to unknown) would silently violate bucket-4 safety | §3 FR-G3 | VALIDATE: regenerating a project with one `authored` page does not modify that page's `.md` or any artifact containing its prose |

**Endorsements:**
- R1-F-cnt-1: concur — FR-G2 vs OQ-2 contradiction must be resolved; the "prompts counted separately" text is either binding or it isn't.
- R1-F-cnt-2: concur — the brownfield origin-unknown case is the highest-risk gap for the FR-G2 scoring denominator; `placeholder` as the conservative default is the right recommendation.
