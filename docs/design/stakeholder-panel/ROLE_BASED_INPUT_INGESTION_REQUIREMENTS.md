# Role-Based Project Input — Complete, Honest Ingestion (incl. a Residual Capture Lane)

**Version:** 0.5 (CRP-hardened — 2 rounds, 30 suggestions, all accepted)
**Date:** 2026-07-09
**Status:** Draft (reflective loop + CRP complete; ready to implement)
**Author:** Neil Yashinsky (with Claude)

> ### 0.2 Decisions (v0.4) — the five OQs resolved by the user
> - **OQ-1 → 3rd lane + tag.** `Lane.UNSTRUCTURED` *and* an `input_kind` on every candidate (FR-3/FR-4).
> - **OQ-2 → 10-kind taxonomy.** Added `decision` + `constraint` to the 8 (FR-4).
> - **OQ-3 → build the LLM Tier-2 now.** The opt-in `input_kind` refinement ships this increment (FR-12).
> - **OQ-4 → in-report only** (default kept; no sidecar).
> - **OQ-5 → guarded append.** The backlog renderer also appends into an existing `ENHANCEMENTS_BACKLOG.md`
>   under write-guards — this **lifts NR-4** and adds a write surface (FR-7 + FR-14 write-safety).

> **Strategic frame.** The SDK's ability to generate *useful, role-based input on a project* — via the
> stakeholder panel — is a **differentiator**. For that to hold, panel output must be **fully
> captured, typed, and routed**; it must never be silently dropped just because it did not fit a
> predefined structure. This spec closes the ingestion gaps (A–D) and adds the differentiating piece:
> a **residual/unstructured capture lane** (E) that preserves *and types* everything the structured
> extractor doesn't claim.

---

## 0. Planning Insights (Self-Reflective Update)

> Planning this against the real `synthesis_bridge` + `kickoff_view` code (v0.1 → v0.2) surfaced 5
> corrections; two were structural.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| `build_triage` can read `transcript.posture` for B/D | **`KickoffTranscript` (Pydantic, `kickoff_view/models.py`) exposes `objective`/`synthesis`/`status` but NOT `posture`** — the field exists in the session JSON (#174) but is unmapped by the model | **Added FR-8:** declare `posture` on `KickoffTranscript` (maps the JSON key) before any posture-aware routing. A phantom reference if unaddressed. |
| Residual could be "just a `kind` tag" on NON_DECIDABLE | `TriageReport.to_markdown` has a **fixed two-section layout** (FIELD_LEVEL + NON_DECIDABLE) and `counts()` enumerates `Lane`; dropped content has no home | **Lane and kind are ORTHOGONAL** (FR-3/FR-4): a 3rd `Lane.UNSTRUCTURED` gives residual its own section+count; an `input_kind` tag types EVERY candidate. Do both. |
| Fixing extraction might yield field-level candidates | `classify._detect_value_path` marks FIELD_LEVEL only on a verbatim allow-listed `Entity.field` token; UX recs never contain one | Confirmed: A/E restore **completeness**, not field-level yield. The apply pipeline still correctly gets ~0 for prototype (recorded as NR-2, not a gap). |
| Backlog render (C) is a fresh parse of the synthesis | `build_triage` already produces a structured `TriageReport`; a 2nd parse would drift | **C consumes the `TriageReport`** (one extraction, two renderers) — FR-6. DRY. |
| Only prototype synthes drop content | The bold-lead item-format miss (`**T1 — … OPEN**` not matching the numbered/bullet regex) affects the **`Tensions` section in BOTH postures** | A's format-robustness + E's residual pass are **posture-independent**; only D's health note and the section *vocabulary emphasis* are posture-flavored. |

**Resolved open questions (from v0.1):**
- **OQ (persistence path) → the `TriageReport` IS the artifact.** Residual lives in the report (`to_dict`/`to_markdown`), persisted wherever the caller writes the report. A separate sidecar file is optional (kept as OQ-4).
- **OQ (LLM typing) → deterministic default, LLM is an opt-in Tier-2** mirroring the `extract_llm.py` precedent. Residual is ALWAYS captured deterministically; an LLM only *refines* `input_kind`.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK lessons before CRP. Each changed the draft:

- **Phantom-reference audit (Leg 13/16)** — grepped every named symbol. Found `transcript.posture` unmapped
  on `KickoffTranscript` → **FR-8** (declare it). All other symbols (`Lane`, `Candidate`, `TriageReport`,
  `extract_candidates`, `classify`, `health_check`, `build_triage`, `PanelSynthesis.text`) verified present.
  See §Reference Audit.
- **Overloaded-term co-location (Leg 12/16)** — `kind` is heavily overloaded in this SDK (`backend_codegen`
  "kinds", deterministic-provider "kinds", `TriageReport.to_dict()["kind"]` = the report type). → name the new
  candidate field **`input_kind`** (never bare `kind`), and keep it on `Candidate`, not a new co-located concept.
- **Single-source "nothing silently dropped" contract (Leg 16)** — the invariant is stated in
  `kickoff-panel triage --help` and `TriageReport` docstring (existing FR-5). This spec makes it TRUE; it cites
  that contract as the owner, and does not restate it as a new rule free to drift.
- **Under-generation is a false-pass (Leg 16 #—)** — a residual lane could be gamed by emitting empty/near-empty
  fragments. → FR-3 sets a **minimum-content floor** + a completeness invariant test (FR-13) that asserts the
  union of all lanes' verbatim text covers every non-boilerplate synthesis line.
- **CRP steering** — least-reviewed artifact = this doc (brand new) + `synthesis_bridge/extract.py` (never
  CRP'd). Settled / do-not-relitigate: the prototype posture itself (#172–174), the 2 existing lanes' meaning,
  the "$0 deterministic default" stance.

---

## 1. Problem Statement

The stakeholder panel produces role-based project input (a facilitated **synthesis**). The
`synthesis_bridge` triages that synthesis into actionable lanes. Today it **under-reads** any synthesis
whose shape differs from the original scrutiny structure — silently dropping the majority of a
`prototype` synthesis — which both violates the stated "nothing dropped" contract and wastes the very
role-based input that is the differentiator.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `extract.py` section vocab | `{recommendation, open question, risk register, tension}` | prototype headers `Prioritized UX Improvements / Quick Wins / Bigger Bets` unrecognized → **dropped** (A) |
| `extract.py` item format | captures only numbered/bullet lines | bold-lead items (`**T1 — … OPEN**`) → **dropped**, both postures (A) |
| unrecognized/orphan content | not captured at all | any content outside a known section+format is **silently lost** — no residual bucket (E) |
| `build_triage` posture awareness | reads `objective`/`synthesis` only | can't tailor routing/health to `posture` (B/D) — and `posture` isn't even on the model (FR-8) |
| input typing | items carry only `source_section` | no **type-of-input** classification (suggestion/feedback/…) across items (E) |
| backlog handoff | none (done by hand — household §7) | no tool to fold a synthesis into a backlog doc (C) |

---

## 2. Requirements

### A — Structured extraction completeness
- **FR-1 (section vocabulary).** `extract_candidates` recognizes the prototype section headers
  (`Prioritized UX Improvements`, `Quick Wins`, `Bigger Bets`) in addition to the existing four, via the
  same prefix-match mechanism. Header→label additions are the single source; `classify` routes them.
- **FR-2 (item-format robustness).** Within a recognized section, capture **bold-lead** items
  (`**Label — …**`) and definition-style lines, not only `1.`/`-` lines — so `Tensions` (both postures)
  and bold UX items are captured. Preserve the ≥8-char noise floor.

### E — Residual / unstructured capture (the centerpiece)
- **FR-3 (residual lane).** Add `Lane.UNSTRUCTURED`. After the structured pass, a **residual pass**
  emits an `UNSTRUCTURED` candidate for every non-boilerplate synthesis line/paragraph the structured
  pass did **not** already claim (content under unknown headings; recognized-section lines that matched
  no item pattern). Each preserves **verbatim** `raw_text` (Mottainai). A minimum-content floor
  (≥ N chars / not a bare heading or separator) prevents empty-fragment gaming.
- **FR-4 (`input_kind` typing — orthogonal to lane).** Every `Candidate` (all lanes) carries an
  `input_kind: InputKind` — the *type of input received*. **Taxonomy (10, closed enum):**
  `recommendation, suggestion, question, risk, tension, feedback, content, decision, constraint,
  uncategorized`. Deterministic assignment: from `source_section` where known (Recommendations→
  `recommendation`, Open Questions→`question`, Risk Register→`risk`, Tensions→`tension`,
  UX Improvements/Quick Wins/Bigger Bets→`suggestion`); for residual, a keyword heuristic —
  trailing `?`→`question`; `must|never|cannot|only|limit|required`→`constraint`;
  `decided|will|chosen|ratified|agreed`→`decision`; `suggest|recommend|should|could|consider`→
  `suggestion`; else `content`. Unmappable → `uncategorized` (never dropped). The heuristic is the
  deterministic floor; the LLM Tier-2 (FR-12) may only *refine* it.
- **FR-5 (nothing-dropped, now true).** The union of all candidates' verbatim text covers every
  non-boilerplate line of the synthesis. This upgrades the existing FR-5 contract from *claimed* to
  *verified* (see FR-13). Applies to **both** postures.
- **FR-11 (report surfaces residual + kind).** `TriageReport.to_markdown`/`to_dict` gain an
  `## UNSTRUCTURED (preserved — received but not previously accounted for)` section and expose
  `input_kind` per candidate and a per-kind count summary.

### B / D — Posture-aware routing + honest framing
- **FR-8 (map posture onto the transcript).** Declare `posture: str = "scrutiny"` on `KickoffTranscript`
  so the session-JSON key (#174) is available to consumers. *(Blocks B/D.)*
- **FR-9 (posture-aware framing/health).** `build_triage` reads `transcript.posture`. For `prototype`,
  `health_check` adds a non-blocking note: *"prototype/UX synthesis — items are design recommendations,
  not `entity.field` values; route to the requirements backlog, not the VIPP apply pipeline."* Field-level
  detection still runs (harmless; a prototype synthesis MAY name a field) but is not expected to fire.
- **FR-10 (scrutiny unchanged).** For `posture="scrutiny"` (default / absent), routing and the report
  are behavior-compatible except for the additive residual/kind surfaces (guarded by FR-13).

### C — Backlog renderer
- **FR-6 (render a backlog section from the report).** A pure function
  `render_backlog_section(report, *, title, project) -> str` consumes a `TriageReport` and emits a
  markdown backlog section (grouped by `source_section`/`input_kind`; SYNTHETIC & UNRATIFIED banner;
  preserves open tensions + open questions as decisions) — the shape produced by hand for
  household `ENHANCEMENTS_BACKLOG.md §7`.
- **FR-7 (CLI surface + guarded append).** `startd8 kickoff panel backlog <session> [--project] [--json]
  [--out FILE] [--append FILE]` — default prints the section to stdout (`$0`, read-only); `--out` writes a
  new file; `--append` performs a **guarded append** into an existing `ENHANCEMENTS_BACKLOG.md` per FR-14.
- **FR-14 (write-safety for the guarded append).** The append is: **preview-by-default** (prints the
  diff/would-write unless `--append --yes`); **append-only** (never rewrites or reorders existing content —
  inserts a new section before the doc's closing footer, or at EOF); **idempotent** (each session's block
  carries a `<!-- startd8-panel-backlog: <session_id> -->` marker; re-running replaces only that marked
  block, never duplicates); **fail-closed** if the target isn't a writable existing file. Carries the
  SYNTHETIC & UNRATIFIED banner.

### Cross-cutting
- **FR-12 (deterministic $0 default; LLM opt-in Tier-2 — IN SCOPE).** All of A–E run deterministically at
  `$0` and always produce a complete, typed triage. A **flag-gated, bounded** LLM pass
  (`--llm-kind [--model …]`) may only **refine `input_kind`** on `UNSTRUCTURED` (and unconfidently-typed)
  items — it **never** generates/rewrites content (NR-1), **never** changes `lane` or `raw_text`, and is
  bounded (batched, capped, cheap-model default). Output is validated against the closed 10-kind enum; an
  out-of-enum answer is discarded (keeps the deterministic kind). Off by default; degrades to the
  deterministic result on any error (missing key / cost ceiling / parse fail), with a health note.
- **FR-13 (completeness + backward-compat guards).** Tests: (a) coverage invariant (FR-5) on both a
  prototype and a scrutiny synthesis fixture; (b) the real household prototype synthesis now surfaces
  UX Improvements/Quick Wins/Bigger Bets + typed Tensions (regression vs the "7 Open Questions only"
  bug); (c) scrutiny golden unchanged except additive residual/kind; (d) `input_kind` mapping table.

---

## 2.1 CRP Hardening (v0.5) — accepted refinements

> Two independent CRP rounds (R1 focus-weighted, R2 adversarial) produced 15 F- + 15 S-suggestions, all
> code-anchored; the orchestrator ACCEPTED all (Appendix A), resolving three embedded design choices.
> These refine the FRs above and are normative.

**Residual pass & coverage (the centerpiece — E):**
- **H-1 [R2-F1/S1] Residual runs on the raw line stream, NOT behind the section gate.** `extract_residual`
  iterates `text.splitlines()` independently of the structured loop's `if not section: continue`
  (`extract.py:83`), so lines under **unrecognized `##` headings** are captured (tagged
  `source_section="(unsectioned)"` or the literal heading). Without this the headline unknown-heading case
  is a silent no-op. *(FR-3)*
- **H-2 [R1-F4/S5] Define "boilerplate" normatively + normalization-aware coverage.** Boilerplate =
  {blank lines; heading-only lines; markdown table header+separator rows; the SYNTHETIC/UNRATIFIED banner &
  disclaimer lines; fragments `< MIN_ITEM_CHARS` (=8)}. The FR-5 coverage invariant compares on
  **`_clean()`-normalized** text (the structured path stores cleaned `raw_text`, `extract.py:45`), not raw
  substrings. *(FR-3, FR-5, FR-13)*
- **H-3 [R1-F7/S5] Coverage invariant is bidirectional.** Union of all lanes' normalized text **covers**
  every non-boilerplate line (no drop) **AND** structured-claimed ∩ residual-claimed line-index sets = ∅
  (no double-count). *(FR-5)*
- **H-4 [R1-S3] Risk-Register table rows.** Claimed-index tracking marks risk **data** rows as claimed and
  header/separator rows as boilerplate, so residual re-emits no table scaffolding and risks appear once. *(FR-3)*
- **H-5 [R2-F7] Empty / all-boilerplate synthesis.** The report renders a deterministic (possibly `(none)`)
  UNSTRUCTURED section; `--append` writes **no block** (no marker) when there are zero candidates — an empty
  run never churns the target. *(FR-11, FR-14)*

**Typing (FR-2/FR-4):**
- **H-6 [R2-F2/S2] Title derivation for bold-lead items** must not split on the `—`/`.` that the
  `**Label — …**` format uses (`_title_of`, `extract.py:55`): title = the whole bold span (capped), not
  truncated at the delimiter. *(FR-2)*
- **H-7 [R2-F3/S4] `input_kind` heuristic = word-boundary match, first-match-wins.** Use `\b…\b`
  (`only`/`limit`/`will`/`agreed` must not fire inside `commonly`/`unlimited`/`willing`/`disagreed`); pin the
  precedence so "should be required" resolves deterministically (documented order). *(FR-4)*
- **H-8 [R2-S3] `_SECTION_ROUTING` for the new sections.** UX Improvements/Quick Wins/Bigger Bets get an
  explicit NON_DECIDABLE reason/owner ("design recommendation → requirements backlog" / "requirements-build"),
  not the generic "not reducible to a single field value" default. *(FR-1, FR-9)*

**Posture (FR-8/FR-9) & report (FR-11):**
- **H-9 [R2-F4] Resolve FR-9 ↔ NR-2 ↔ code.** Orchestrator chose **(a) soften the note**: *"expected to route
  to the backlog; field-level detection may still fire if the synthesis names an allow-listed field."*
  `classify` is unchanged (FIELD_LEVEL still possible). NR-2 scopes to UNSTRUCTURED/UX-suggestion items, which
  never auto-map. *(FR-9, NR-2)*
- **H-10 [R1-S1] `health_check` gains `posture: str = "scrutiny"` (keyword-only)**; `build_triage` threads
  `getattr(transcript, "posture", "scrutiny")`. *(FR-8, FR-9)*
- **H-11 [R1-F8] FR-8 is additive** — `KickoffTranscript` already has `extra="allow"` (`kickoff_view/models.py:114`),
  so `posture`-less transcripts load unchanged (default `"scrutiny"`); no external exact-shape consumer. *(FR-8)*
- **H-12 [R2-F6/S6] `counts()` stays `Dict[str,int]`** (adds only the `UNSTRUCTURED` key); per-kind counts are a
  **separate** `kind_counts()` / `to_dict["kind_counts"]`. The hardcoded Counts f-string in `to_markdown`
  (`models.py:86`) is updated to render the UNSTRUCTURED count + kind summary **[R1-S2]**. *(FR-11)*

**LLM Tier-2 (FR-12):**
- **H-13 [R1-F3/S4] `{index: input_kind}` contract.** `index` = 0-based position in the **explicitly-passed
  subset** (order-preserved); keys that are missing / out-of-range / duplicated are discarded (→ deterministic
  kind), distinct from the out-of-enum-value discard. *(FR-12)*
- **H-14 [R1-F6/S7] Numeric bounds as acceptance criteria** (config + CLI help): `max_items_per_call`,
  `max_items_per_run`, and a cost ceiling that aborts to the deterministic result + health note. *(FR-12)*
- **H-15 prompt-injection [R2 exec-summary] the residual `raw_text` is fenced** as data in the typing prompt
  (never as instructions); the LLM may only return the `{index: kind}` map. *(FR-12, NR-1)*

**Guarded append write-safety (FR-14):**
- **H-16 [R1-F1/S6] Marker-injection neutralization.** Before writing, assert the rendered block contains no
  `startd8-panel-backlog` marker substring (residual `raw_text` is verbatim/attacker-influenced) — fail-closed
  or escape. *(FR-14)*
- **H-17 [R1-F2] Deterministic insertion point.** Footer rule pinned: insert before the **last** line matching
  `^\*.*\*$`; on zero/multiple/ambiguous matches fall back to **EOF** (never mid-doc). *(FR-14)*
- **H-18 [R1-F5] Malformed/duplicate-marker recovery.** An unclosed or duplicated opener for the sid → **fail
  closed** with a diagnostic (never guess the region). No file lock — concurrent runs are last-writer-wins under
  temp+rename (documented limitation). *(FR-14)*
- **H-19 [R2-F5/S5] Atomic-write mechanics.** Temp file created **in the target's own directory** (same fs →
  `os.replace` atomic, no cross-device fail); a **symlink** target is resolve-and-replace-target or fail-closed
  (never clobber the link); target mode preserved. *(FR-14)*
- **H-20 [R1-S8] `render_backlog_section` byte-stability golden** — grouping order sorted/stable so the marked
  block is identical across runs (idempotency depends on it). *(FR-6)*
- **H-21 [R2-S7] Preview exit-code contract** (`polish check` style): `--append` without `--yes` exits **0** when
  already idempotent (block byte-identical), **2** when it would write — so CI can gate on backlog drift. *(FR-7)*

---

## 3. Non-Requirements

- **NR-1 (no content generation).** Residual capture **preserves and types** existing panel output; it
  never authors content (bucket 4). No summarization/rewriting of the residual text.
- **NR-2 (residual/UX is never FIELD_LEVEL).** UNSTRUCTURED and UX-suggestion items are never auto-mapped
  to `entity.field`; they never enter the VIPP apply pipeline. 0 field-level candidates for a prototype
  synthesis is CORRECT, not a defect. *(Scope clarified per H-9: this applies to UNSTRUCTURED/UX-suggestion
  items — a `Recommendation`-lane item that verbatim names an allow-listed `Entity.field` MAY still classify
  FIELD_LEVEL; the FR-9 note is softened accordingly, `classify` is unchanged.)*
- **NR-3 (no synthesis re-structuring).** This does not build the latent structured-synthesis arrays
  (`kickoff_view` FR-UX-15/16). It parses the prose `synthesis.text` as today.
- ~~**NR-4 (no auto-write into project docs).**~~ **LIFTED in v0.4 (OQ-5).** The renderer MAY append into an
  existing `ENHANCEMENTS_BACKLOG.md`, but ONLY under the FR-14 write-guards (preview-default, append-only,
  idempotent-by-session-marker, fail-closed). It still never *creates* the project's canonical docs from
  scratch and never rewrites existing content.
- **NR-5 (no new posture).** Uses the existing `scrutiny`/`prototype` postures only.

---

## 4. Open Questions — RESOLVED (v0.4)

- **OQ-1 → 3rd lane + `input_kind` tag.** `Lane.UNSTRUCTURED` + `input_kind` on every candidate (FR-3/FR-4).
- **OQ-2 → 10-kind taxonomy** (added `decision` + `constraint`) (FR-4).
- **OQ-3 → build the LLM Tier-2 now** — opt-in, bounded, refine-only (FR-12).
- **OQ-4 → in-report only** (no sidecar).
- **OQ-5 → guarded append** into `ENHANCEMENTS_BACKLOG.md` (FR-7 + FR-14; lifts NR-4).

*(No open questions remain. Residual forks for CRP: the write-safety of the guarded append (FR-14) and the
bounded LLM refinement (FR-12) are the least-settled surfaces.)*

---

## Reference Audit (phantom-reference check)

| Symbol | Where | Exists? |
|--------|-------|---------|
| `Lane` (FIELD_LEVEL, NON_DECIDABLE) | `synthesis_bridge/models.py:19` | ✅ (add UNSTRUCTURED) |
| `Candidate` (title/source_section/raw_text/lane/reason/…) | `models.py:26` | ✅ (add `input_kind`) |
| `TriageReport` (counts/to_dict/to_markdown) | `models.py:50` | ✅ (add residual section) |
| `extract_candidates` / `_SECTION_PREFIXES` / regexes | `extract.py:66/25/32` | ✅ |
| `classify` / `_detect_value_path` / `_SECTION_ROUTING` | `classify.py:49/35/24` | ✅ |
| `health_check` | `classify.py:76` | ✅ |
| `build_triage` (reads session_id/objective/synthesis) | `route.py:25` | ✅ |
| `PanelSynthesis.text` | `kickoff_view/models.py:100` | ✅ |
| `KickoffTranscript.posture` | `kickoff_view/models.py:111` | ❌ **absent → FR-8** |
| `startd8 kickoff panel …` CLI group | `cli_panel.py` | ✅ (add `backlog`) |

---

*v0.5 — Post-planning (5 corrections) + lessons-hardening (5) + 5 user decisions + **CRP (2 rounds, 30
suggestions, all accepted → §2.1 H-1…H-21)**. Centerpiece = the residual/unstructured capture lane (E).
Deterministic `$0` core + opt-in LLM refine; scrutiny backward-compatible. Ready to implement.*

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

> All 15 R1+R2 F-suggestions ACCEPTED (both rounds self-filtered to code-anchored findings). Merged into
> **§2.1 CRP Hardening (v0.5)** as H-1…H-21 (F- and S- items that coincide share one H-id). Three embedded
> design choices resolved by the orchestrator (noted below).

| ID | Merged as | Notes | Date |
|----|-----------|-------|------|
| R1-F1 | H-16 | marker-injection neutralization (fail-closed/escape) | 2026-07-09 |
| R1-F2 | H-17 | deterministic footer/insertion rule (last `^\*.*\*$`, else EOF) | 2026-07-09 |
| R1-F3 | H-13 | `{index:kind}` subset-position contract; discard missing/oob/dup | 2026-07-09 |
| R1-F4 | H-2 | define boilerplate + `_clean()`-normalized coverage | 2026-07-09 |
| R1-F5 | H-18 | malformed/dup-marker → fail-closed; no-lock note | 2026-07-09 |
| R1-F6 | H-14 | numeric LLM caps as acceptance criteria | 2026-07-09 |
| R1-F7 | H-3 | bidirectional coverage (covers AND disjoint) | 2026-07-09 |
| R1-F8 | H-11 | FR-8 additive (`extra="allow"`); no breaking change | 2026-07-09 |
| R2-F1 | H-1 | residual on raw line stream, not behind section gate | 2026-07-09 |
| R2-F2 | H-6 | bold-lead title not split on `—`/`.` | 2026-07-09 |
| R2-F3 | H-7 | word-boundary heuristic + pinned precedence | 2026-07-09 |
| R2-F4 | H-9 | FR-9↔NR-2 resolved via **(a) soften the note** | 2026-07-09 |
| R2-F5 | H-19 | atomic-write: same-dir temp / symlink / mode | 2026-07-09 |
| R2-F6 | H-12 | `counts()` stays all-int; `kind_counts()` sibling | 2026-07-09 |
| R2-F7 | H-5 | empty-synthesis → no backlog block; deterministic report | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | Both rounds were code-anchored and non-redundant; no suggestion warranted rejection. | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-09 18:30:00 UTC
- **Scope**: Focus-file weighted — FR-14 guarded append, FR-12 LLM refine, FR-3/FR-5 residual+coverage invariant, extract.py dual-pass. Anchored against `synthesis_bridge/{extract,classify,models,route}.py` + `kickoff_view/models.py`.

##### Focus-file asks — answered

**Ask 1 — FR-14 guarded append (idempotency / atomicity / append-only / preview / fail-closed / marker injection)**
- **Summary answer:** Partial — the marker/preview/fail-closed shape is sound, but three write-safety holes are underspecified: (a) marker injection via hostile synthesis text, (b) footer-detection ambiguity, (c) concurrent-run / malformed-marker recovery.
- **Rationale:** FR-14 says re-running "replaces only that marked block" keyed on `<!-- startd8-panel-backlog: <session_id> -->`, and the plan M6 implements it as a regex on the sid. But `session_id` and the *rendered section body* both flow from data; a synthesis line containing the literal closing marker `<!-- /startd8-panel-backlog: <sid> -->` (NR-1 preserves residual text **verbatim** — FR-3) would prematurely terminate the replace region or corrupt the append. FR-14 also says "insert before the doc's closing footer, or at EOF" but never defines how the footer is detected (plan M6 says "closing `*italic footer*` if present") — an `ENHANCEMENTS_BACKLOG.md` with two italic lines, or none, has an ambiguous insertion point, violating "append-only / never-rewrite" nondeterministically.
- **Assumptions / conditions:** residual `raw_text` can contain arbitrary markdown/HTML comments; the target file is human-edited between runs.
- **Suggested improvements:** see R1-F1 (marker injection), R1-F2 (footer/insertion determinism), R1-F5 (concurrency + malformed-marker recovery).

**Ask 2 — FR-12 opt-in LLM input_kind refinement (bounding / enum-validation / fail-open / index-alignment)**
- **Summary answer:** Partial — enum-validation and fail-open are specified; the `{index: kind}` index-alignment contract and the batch-boundary cost cap are not testably pinned.
- **Rationale:** FR-12 + plan M7 return `{index: input_kind}` over a batch of UNSTRUCTURED+`content`/`uncategorized` candidates, but the requirement never states what `index` is keyed to (position in the filtered subset vs. the global candidate list) nor what happens to indices the model **omits or invents** (out-of-range / missing keys) — distinct from the out-of-enum *value* case that FR-12 does cover. A dropped or shifted index silently re-types the wrong candidate. "Batched, capped, cheap-model default" gives no numeric cap.
- **Assumptions / conditions:** the model may return a partial/renumbered map.
- **Suggested improvements:** see R1-F3 (index-alignment + missing/extra-key discard), R1-F6 (numeric caps as acceptance criteria).

**Ask 3 — FR-3/FR-5 residual pass + "nothing dropped" coverage invariant**
- **Summary answer:** Partial — "boilerplate" and "non-boilerplate line" are used as load-bearing terms in FR-3/FR-5/FR-13 but never defined, and the double-count guard is asserted only one-directionally.
- **Rationale:** FR-5 asserts "the union of all candidates' verbatim text covers every non-boilerplate line," and FR-13(a) tests it — but "boilerplate" is enumerated only informally in the plan (M2: "blank, `## `-only headings, table separators, the banner/disclaimer lines, <8 chars"). The requirement must own that list or FR-13's test is unfalsifiable. Separately, the structured pass **normalizes** text via `_clean()` (extract.py:45, strips `*_` and collapses whitespace) while the residual invariant compares "verbatim `raw_text`" — a bold-lead item captured structurally as cleaned text will not be a substring of the raw synthesis line, so a naive "union ⊇ raw lines" test both under- and over-matches.
- **Assumptions / conditions:** coverage is checked by line/substring containment.
- **Suggested improvements:** see R1-F4 (define boilerplate + normalization-aware coverage), R1-F7 (double-count both directions).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | FR-14: add an acceptance criterion that the guarded append **neutralizes marker sequences inside the rendered block** — before writing, assert the rendered section contains no `<!-- startd8-panel-backlog:` / `<!-- /startd8-panel-backlog:` substring (fail-closed, or escape it), since FR-3 preserves residual `raw_text` verbatim and a hostile/coincidental synthesis line could inject a closing marker. | Idempotency keys on the marker pair; injected markers let a re-run truncate/duplicate or corrupt an unrelated block. Not currently covered by any FR. | FR-14, after "idempotent" clause | Unit test: synthesis whose residual line literally contains `<!-- /startd8-panel-backlog: X -->`; assert append either escapes it or fails closed, and a second run stays byte-idempotent. |
| R1-F2 | Data | high | FR-14: define the **insertion point deterministically** — specify the exact footer-detection rule (e.g. "last line matching `^\*.*\*$`" vs any italic) and the tie-break when zero or multiple candidates match; state that on ambiguity the append falls back to EOF (never mid-doc). | "insert before the doc's closing footer, or at EOF" is ambiguous for real docs with 0/2 italic footers; ambiguity breaks the append-only/never-rewrite guarantee nondeterministically. | FR-14, "append-only" clause | Golden test: three `ENHANCEMENTS_BACKLOG.md` fixtures (no footer / one footer / two italic lines); assert insertion point is deterministic and surrounding bytes unchanged. |
| R1-F3 | Interfaces | high | FR-12: pin the `{index: input_kind}` contract — state that `index` is the candidate's position in the **explicitly-passed subset** (0-based, order preserved), and that any key that is missing, out-of-range, or duplicated is discarded (falls back to the deterministic kind), not just out-of-enum *values*. | FR-12 covers out-of-enum values but is silent on index misalignment; a shifted/omitted key silently re-types the wrong candidate — the exact off-by-one the focus file flags. | FR-12, after "out-of-enum answer is discarded" | Unit test: stub agent returns a map missing one index, one out-of-range, one duplicate; assert each affected candidate keeps its deterministic kind and no unrelated candidate is mutated. |
| R1-F4 | Validation | high | FR-3/FR-5: **define "boilerplate"** normatively in the requirement (blank lines, heading-only lines already consumed, table header/separator rows, the SYNTHETIC/UNRATIFIED banner + disclaimer lines, and `<`min-char fragments) and make the coverage comparison **normalization-aware** (compare on `_clean()`-normalized text, since extract.py:45 strips emphasis/whitespace before storing `raw_text`). | FR-5/FR-13(a) hinge on "non-boilerplate line" and "verbatim" but the structured pass stores *cleaned* text, so a raw-substring union test is neither sound nor complete. | FR-3 (define term) + FR-5 (comparison basis) | The FR-13(a) coverage test must normalize both sides; add a fixture line with bold/backticks and assert it is counted as covered. |
| R1-F5 | Risks | medium | FR-14: add a **malformed/duplicate-marker recovery** rule — if the target already contains an opening marker for `<sid>` with no matching close (or two openers), the append must fail closed with a diagnostic rather than guess the replace region; and note there is no lock (concurrent runs on the same file are last-writer-wins under temp+rename). | Idempotency by marker assumes well-formed marker pairs; a hand-edited or crash-truncated doc breaks the regex-replace silently. | FR-14, "fail-closed" clause | Unit test: doc with an unclosed opener → assert append refuses + explains; doc with two openers for one sid → same. |
| R1-F6 | Ops | medium | FR-12: convert "bounded (batched, capped, cheap-model default)" into **numeric acceptance criteria** — a max items/call, a max total items refined per run, and a hard cost ceiling that aborts to the deterministic result — so FR-13's LLM test can assert them. | "Bounded" is untestable as prose; the focus file calls out cost-ceiling + caps as a risk surface. | FR-12 | Test asserts refinement is skipped past N items and that a synthetic over-ceiling cost aborts to deterministic + health note. |
| R1-F7 | Data | medium | FR-5: make the double-count guard **bidirectional** — assert not only that the union *covers* every non-boilerplate line (no drops) but also that no source line is claimed by **both** a structured candidate and an UNSTRUCTURED residual candidate (no double-count), which the focus file explicitly asks. | FR-3 says residual emits only lines the structured pass "did not already claim," but the invariant as written (FR-5) only tests coverage, not disjointness; a line matched by both the Risk-Register table path *and* the residual sweep would double-count. | FR-5 / FR-13(a) | Test asserts structured-claimed line-index set and residual-claimed set are disjoint on both fixtures. |
| R1-F8 | Interfaces | low | FR-8: state that `posture` reads from the transcript via graceful-optional access (the model has `extra="allow"`, so the JSON key already loads today) and that declaring the field must **not** change load behavior for transcripts lacking it (default `"scrutiny"`), and confirm no external `KickoffTranscript` consumer asserts an exact field set. | Focus cross-repo note asks to check downstream loaders; `kickoff_view/models.py:114` already allows extras, so FR-8 is additive — but the requirement should say so to prevent a reviewer "breaking change" flag. | FR-8 | grep consumers of `KickoffTranscript(...)`/`.model_dump()` for exact-shape assertions; add a load test with a `posture`-less fixture. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Appendix C was empty at R1.

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-09 19:10:00 UTC
- **Scope**: Adversarial / stress-test pass. Re-grounded in `synthesis_bridge/{extract,classify,models,route}.py` + `kickoff_view/models.py`. R1 was strong on the three focus asks; R2 attacks residual-pass code-level traps (unknown-heading skip, `_title_of` em-dash split, keyword substring matching), the FR-9↔NR-2 latent contradiction, the atomic-write/symlink surface R1's marker work left open, and a `counts()` return-shape backward-compat break. Does NOT re-propose R1-F1..F8; endorsements below.

##### Executive summary (top risks / gaps)

- **Unknown-heading content is invisible to the current loop** (`extract.py:83-84` `if not section: continue`) — FR-3's "content under unknown headings" requires the residual pass to see lines the structured loop skips *before* the body; the dual-pass refactor must not inherit that early-out (R2-F1).
- **`_title_of` splits on em-dash** (`extract.py:55` `re.split(r"[:—.]", ...)`) — the very bold-lead items FR-2 adds (`**T1 — … OPEN**`) get their title truncated at the `—`, and `.` splitting fractures any line with a decimal/abbreviation (R2-F2).
- **FR-4 keyword heuristic is substring, not word-boundary** — `only`/`limit`/`will` as bare substrings mis-fire inside `commonly`/`unlimited`/`willing`; ordering also lets "should be required" resolve to `constraint` before `suggestion`. The requirement must pin matching semantics (R2-F3).
- **FR-9 health note asserts a routing fact `classify` can violate** — it says prototype items "route to the requirements backlog, not the VIPP apply pipeline," but `_detect_value_path` (classify.py:43-46) still promotes any allow-listed `entity.field` to FIELD_LEVEL, making the note false when it fires (R2-F4).
- **FR-14 atomic write omits the symlink/cross-device/temp-placement surface** the focus file explicitly asks — temp+rename over a symlinked `ENHANCEMENTS_BACKLOG.md` silently replaces the link with a file; temp in a foreign dir fails `os.replace` cross-device (R2-F5).
- **Adding `by_kind` inside `counts()` changes its return value-type from all-`int` to mixed** — any consumer summing/asserting int values breaks; M1's "or a sibling `kind_counts()`" must be the requirement, not an option (R2-F6).
- **FR-11/FR-14 SYNTHETIC banner + `input_kind` typing has no defined behavior for the empty-synthesis / zero-candidate case** — does an empty triage still emit an UNSTRUCTURED section and a backlog block (and thus a marker) or not? Undefined idempotency baseline (R2-F7).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | high | FR-3: state explicitly that the residual pass captures non-boilerplate lines that fall under **unrecognized headings** (where `_section_for` returns `""`), which the current structured loop discards at `extract.py:83-84` (`if not section: continue`) before the body ever runs. The residual sweep must operate on the raw line stream independent of the structured loop's `section` gate, tagging such lines `source_section="(unsectioned)"` or the literal unknown heading. | FR-3 lists "content under unknown headings" as a target, but the only code path that reaches item logic is gated behind a known section; a refactor that reuses that gate captures nothing new under unknown headings — silently reproducing the drop this feature fixes. | FR-3, "content under unknown headings" clause | Fixture: a synthesis with a `## Parking Lot` (unknown) heading holding 3 real lines → assert all 3 surface as UNSTRUCTURED candidates. |
| R2-F2 | Data | high | FR-2: require that title derivation for bold-lead items **not split on the em-dash** that FR-2's own `**Label — …**` format uses — `_title_of` (extract.py:52-59) does `re.split(r"[:—.]", text)`, so `**T1 — Foo vs Bar OPEN**` yields title `T1` and `.` splits any decimal/abbrev line. Specify the intended title for bold-lead (e.g. the whole bold span, capped) so FR-1/FR-2 and `_title_of` agree. | R1's coverage matrix noted the `_title_of` interaction as a gap but filed no actionable requirement; without a pinned title rule the captured item's label is truncated at the delimiter the new format depends on. | FR-2 (add a title-derivation clause) | Test: `**T1 — A vs B (OPEN)**` and `budget was $1.5M.` → assert titles are not truncated at `—`/`.`. |
| R2-F3 | Validation | medium | FR-4: pin the residual keyword heuristic's **matching semantics** — word-boundary (`\b…\b`) not bare substring, and state the resolution order is first-match-wins with the listed precedence. As written, `only`/`limit`/`will`/`agreed` match inside `commonly`/`unlimited`/`willing`/`disagreed`, and "we should keep this required" hits `constraint` (via `required`) before `suggestion` (via `should`). | The heuristic is the deterministic floor the LLM only refines; a substring false-positive silently mis-types items and is the kind of "valid-enum but semantically wrong" the focus file warns about, now baked deterministically. | FR-4, keyword-heuristic list | Table test: `commonly`, `unlimited scope`, `willing`, `should be required` → assert each maps to the intended kind (content/… , not constraint/decision). |
| R2-F4 | Risks | medium | FR-9: reconcile the prototype health note with `classify`'s live FIELD_LEVEL path — either (a) soften the note to "expected to route to the backlog; field-level detection may still fire if the synthesis names an allow-listed field," or (b) when `posture=="prototype"`, suppress FIELD_LEVEL promotion (per NR-2's "never enter the VIPP apply pipeline"). Today `_detect_value_path` (classify.py:43-46) runs regardless of posture, so the note can assert a falsehood. | FR-9 says detection "still runs (harmless)" but NR-2 says prototype/residual items "never enter the VIPP apply pipeline"; if an allow-list is present and a field is named, classify.py sets FIELD_LEVEL and the note lies — an internal contradiction between FR-9, NR-2, and the code. | FR-9 (note wording) + NR-2 | Test: prototype transcript + non-empty allow-list + a synthesis line naming an allowed `Entity.field` → assert behavior matches whichever branch is chosen (no lane/note contradiction). |
| R2-F5 | Security | high | FR-14: add atomic-write criteria the focus file asks and R1 left open — the temp file MUST be created **in the target's own directory** (same filesystem, so `os.replace` is atomic and never cross-device-fails); if the target is a **symlink**, either resolve-and-replace-the-target or fail closed (never silently replace the link with a regular file); preserve the target's mode/permissions across the rename. | R1-F1/F2/F5 hardened markers/footer/malformed but not the write mechanics; a symlinked backlog (common in monorepos) or a temp dir on another mount turns "atomic temp+rename" into data loss or an unhandled `OSError`. | FR-14, atomic-write clause | Tests: (a) symlinked target → assert defined behavior (follow-or-fail, not link-clobber); (b) simulate cross-device temp → assert same-dir temp is used; (c) assert target mode preserved. |
| R2-F6 | Interfaces | medium | FR-11: require the per-kind counts to be exposed as a **separate accessor** (`kind_counts()` / a `by_kind` key in `to_dict`), NOT by adding non-int values inside `counts()`. `counts()` (models.py:61-66) returns `Dict[str,int]`; nesting a `by_kind` dict inside it changes its value type and breaks any `all(isinstance(v,int) …)` / `sum(counts().values())` consumer. | The plan's M1 offers "a `by_kind` sub-count (or a sibling `kind_counts()`)" as equivalent, but only the sibling is backward-safe; the requirement should mandate it so the additive-compat claim (FR-13c) holds. | FR-11 (counts surface) | Test: `counts()` still returns all-int and includes `UNSTRUCTURED`; kind breakdown is reachable via the separate accessor / `to_dict["kind_counts"]`. |
| R2-F7 | Validation | low | FR-11/FR-14: define the **zero-candidate / empty-synthesis** behavior — does an empty or all-boilerplate synthesis still render an `## UNSTRUCTURED` section (empty) and, for `--append`, still write a marked (empty) backlog block? This sets the idempotency baseline and prevents an empty run from churning the target file. | The coverage invariant and marker idempotency both assume at least the section/marker shape is deterministic for the empty case; unspecified today (health_check flags empty synthesis but the report/backlog behavior isn't stated). | FR-11 (section) + FR-14 (marker) | Test: empty-synthesis transcript → report/backlog shape is deterministic and a re-run is byte-idempotent (or no block is written at all — whichever is chosen). |

##### Endorsements / Disagreements

**Endorsements** (prior untriaged R1 items this reviewer strongly agrees with):
- R1-F1 (marker-injection neutralization): correct and load-bearing — FR-3's verbatim `raw_text` is attacker-controllable text flowing straight into the marked block; strongly endorse fail-closed-or-escape.
- R1-F3 (`{index: kind}` index-alignment contract): the exact off-by-one the focus file flags; endorse, and R2 assumes it as the base for no further index suggestions.
- R1-F4 (define "boilerplate" + normalization-aware coverage): the `_clean()`-vs-verbatim mismatch is real (extract.py:45-49 stores cleaned text); this is a prerequisite for FR-13(a) being a real test.
- R1-F7 (bidirectional double-count / disjointness): endorse — the focus file explicitly asks it and FR-5 as written only tests coverage.

**Disagreements:** none. R1-F8's `extra="allow"` observation is confirmed accurate (`kickoff_view/models.py:114`) — I extend rather than dispute it.
