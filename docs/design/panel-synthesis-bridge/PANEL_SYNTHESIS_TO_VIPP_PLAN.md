# Panel Synthesis → VIPP Proposals Bridge — Implementation Plan

**Version:** 1.0 (paired with REQUIREMENTS v0.3)
**Date:** 2026-07-07
**Status:** Draft — pre-implementation

> Compose existing producers; write no new envelope/inbox/adjudication code (NR-1/NR-7). New code is
> only: the extractor (LLM), the classifier/router (`$0`), the staging glue, and one CLI verb.

---

## Module layout (proposed)

New subpackage `src/startd8/stakeholder_panel/synthesis_bridge/` (lives with the panel — it consumes
panel output; the "candidate" concept is panel-owned, §6 NR-8):

| File | Responsibility | Maps to |
|------|----------------|---------|
| `models.py` | `Candidate` dataclass + the FR-2 extraction JSON contract (OQ-9) | FR-2, NR-8 |
| `extract.py` | LLM pass: session synthesis → `list[Candidate]` (paid) | FR-1, FR-2, FR-13 |
| `classify.py` | `$0` lane assignment + allow-list gate + retail-default health check | FR-3, FR-3a, FR-4, FR-5, FR-14 |
| `route.py` | NON-DECIDABLE report renderer (md + json), reason + suggested owner | FR-5, NR-6 |
| `stage.py` | glue: accepted candidates → `ProposalStore.save` → `build_proposal` → `serialize_buffer` | FR-6, FR-7, FR-8 |
| `cli` verb | `startd8 kickoff panel propose` (OQ-4) — `--session/--dry-run/--json` | FR-12 |

## Step sequence (increment-ordered, per FR-3a)

**Increment 1 — the always-firing core (`$0` except extraction):**
1. `models.py` — define `Candidate` + extraction I/O contract (Keiyaku A2A per SDK micro-prime rule). Tests first.
2. `extract.py` — LLM boundary reading `.startd8/kickoff-panel/<id>.json` (transcript + synthesis). Cost-tracked; mockable agent for tests.
3. `classify.py` — deterministic lane assignment; FR-14 health check comparing session `desc`/objective to `facilitation.DEFAULT_DESC`.
4. `route.py` + CLI `--dry-run` — emit the NON-DECIDABLE report and a lane summary. **Shippable alone** (delivers the triage even when the allow-list is empty).

**Increment 2 — the field-level lane (gated on non-empty `allowed_value_paths()`):**
5. `classify.py` allow-list gate (FR-4) — reclassify non-allow-listed field-shaped items to NON-DECIDABLE with `value_path_not_allowed`.
6. `stage.py` — `ProposalStore.save` at `estimate` provenance (FR-6); `update_disposition` on human accept/edit/drop (FR-7).
7. `stage.py` serialize — `build_proposal("capture", …)` → `ProposalBuffer` → `serialize_buffer` (FR-8). Then hand to the *existing* `startd8 vipp negotiate` / `apply` (NR-1, no new code).

## Reuse map (what already exists — do NOT rebuild)

- Inbox write, seq, checksum, 0600, no-clobber → `vipp_seam.serialize_buffer`.
- Capture construction + allow-list re-check at apply → `kickoff_experience/proposals.py`.
- Field adjudication (FIELD_AUTHORITY) → `vipp/evaluate.py:evaluate_envelope`.
- Provenance-pinned application → `vipp/apply.py`.
- Per-`value_path` staging + disposition → `stakeholder_panel/proposals.py:ProposalStore`.

## Risks / watch-items

- **R1 — Near-zero field-level yield.** On brownfield + governance-heavy synthesis, increment 2 may
  rarely fire. Mitigated by FR-3a (increment 1 ships value regardless) — but validate the hit rate on
  the benchmark-portal session before investing in increment 2.
- **R2 — Extraction hallucination.** The LLM may invent a `value_path`. Mitigated by FR-4 allow-list
  gate + VIPP's own FIELD_AUTHORITY at negotiate. OQ-10 decides whether to also pre-flight.
- **R3 — Contaminated synthesis input (FR-14).** A retail-default session yields retail-framed
  candidates. Health check surfaces it; extraction anchored to artifact + allow-list contains it.
- **R4 — Idempotency (FR-11).** Re-run must not duplicate ProposalStore records or clobber an
  undrained inbox — `serialize_buffer` already refuses the latter; the former needs a session+content
  fingerprint on `ProposalStore.save`.

## Validation

- Unit: classifier lane assignment (field-level / non-decidable / not-allow-listed), FR-14 health
  check, idempotent re-run.
- Golden: run against the real benchmark-portal session `kp-20260704T160024-6bdc06` → assert the 9
  governance/schema/human recommendations land in NON-DECIDABLE with reasons (empirical yield check).
- Integration: `stage.py` → `serialize_buffer` → `vipp negotiate` produces valid dispositions over a
  synthetic allow-listed field; end-to-end `$0` for the non-extraction path.

---

*v1.0 — paired with REQUIREMENTS v0.3.*
