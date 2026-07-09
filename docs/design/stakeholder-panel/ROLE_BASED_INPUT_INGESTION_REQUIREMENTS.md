# Role-Based Project Input — Complete, Honest Ingestion (incl. a Residual Capture Lane)

**Version:** 0.4 (User decisions folded — pre-CRP)
**Date:** 2026-07-09
**Status:** Draft (reflective loop complete; CRP pending)
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

## 3. Non-Requirements

- **NR-1 (no content generation).** Residual capture **preserves and types** existing panel output; it
  never authors content (bucket 4). No summarization/rewriting of the residual text.
- **NR-2 (residual/UX is never FIELD_LEVEL).** UNSTRUCTURED and UX-suggestion items are never auto-mapped
  to `entity.field`; they never enter the VIPP apply pipeline. 0 field-level candidates for a prototype
  synthesis is CORRECT, not a defect.
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

*v0.4 — Post-planning (5 corrections, 2 structural) + lessons-hardening (5 lessons) + 5 user decisions
folded (10-kind taxonomy, LLM Tier-2 in scope, guarded backlog append). Centerpiece = the
residual/unstructured capture lane (E). Deterministic `$0` core + opt-in LLM refine; scrutiny
backward-compatible. Ready for CRP.*
