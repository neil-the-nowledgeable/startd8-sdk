# Consensus / Divergence Signal — Requirements

**Version:** 0.4 (Sponsor decisions locked — building)
**Date:** 2026-07-10
**Status:** Approved to build (lexical + embeddings seam; CRP skipped — additive/$0/read-only)

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (grounded against the transcript model, facilitation rounds, and facilitate_status)
> resolved all 5 open questions and reframed the metric's honest meaning.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| R1 is the independent first-take | **Confirmed** — R1 = "Individual analysis", no digest of others; R3 cross-pollinates. | FR-3 stands. |
| Challengers need a heuristic | `facilitation.CHALLENGER_IDS` is a stable constant → identify by `role_id ∈ CHALLENGER_IDS`. | FR-4 deterministic (OQ-3 resolved). |
| Compute at synthesis + persist a field | R1 entries are already persisted; a **lazy derive** in a shared pure fn is $0, migration-free, single-source (no drift), works on old transcripts. | OQ-2 → lazy-derive; NR-4 holds (no new schema). |
| Lexical divergence ≈ agreement | **Weak proxy** — agreement in different words → low overlap → falsely "low". | Reframed as **lexical divergence** ("how differently they *phrased* it"), a coarse $0 flag, NOT semantic agreement (FR-1/FR-7). Embeddings = deferred semantic upgrade (NR-1). |

**Resolved open questions:**
- **OQ-1 → lexical, honestly named.** Token-set cosine over R1 answers, $0/deterministic; labeled a
  *lexical-divergence* signal, not semantic agreement. Embeddings deferred (NR-1).
- **OQ-2 → lazy-derive** from the persisted R1 entries in a shared helper; no new persisted field.
- **OQ-3 → exclude challengers** from the headline via `CHALLENGER_IDS` (measure the non-challenger
  personas' agreement).
- **OQ-4 → score (0–1) + label (high/mixed/low/n-a) + n + basis`; thresholds are named constants.
- **OQ-5 → the shared `compute_consensus` helper IS the #8 reuse point** (no separate persistence).

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified every named symbol exists: `PanelRound.round_id`,
  `PanelEntry.role_id/.text`, `facilitation.CHALLENGER_IDS`, `facilitate_status`,
  `run_kickoff_panel._print_synthesis`, `FacilitateStatusResult`. No phantoms (only new: `consensus.py`).
- **[Overloaded-term co-location]** — the metric lives in its **own** `consensus.py`, not stacked into
  facilitation.py or synthesis_bridge. No overload.
- **[Provenance over-claim]** — named "lexical divergence / synthetic", never "stakeholder agreement";
  `basis` field records the method so the claim is auditable.

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Hitsuzen]** — the signal is fully determined by the persisted R1 texts → derived deterministically,
  no LLM/embedding call (the whole point of FR-1).
- **[Mottainai]** — derived on read from the already-persisted R1 entries; no persisted derived field to
  drift or migrate (OQ-2).
- **[Genchi Genbutsu]** — binds to the **real** R1 entries + the **real** `CHALLENGER_IDS` constant (not
  a lookalike heuristic); one canonical helper name reused by poll + CLI + #8.
- **[Accidental-Complexity]** — one pure function, no allowlist/special-case machinery.
- **[Context-Correctness]** — degrades to `n/a` when R1 is absent/≤1 rateable — never a silent None/crash.

---

## 1. Problem Statement

The multi-round facilitation emits a synthesis narrative but **no measure of whether the personas
agreed**. A reader can't tell strong convergence from a papered-over split. This adds a deterministic,
$0 **lexical-divergence consensus signal** over the personas' independent R1 answers, surfaced on the
poll payload + Grafana panel + terminal — turning the synthesis into decision-support (high → act;
low → the takes were very different, dig deeper). Unblocks **#8** (confidence-gated apply).

| Component | Current State | Gap |
|-----------|--------------|-----|
| `PanelRound(round_id="R1").entries[].text` | Independent per-persona R1 answers, persisted | No agreement metric over them |
| `facilitate_status` poll payload | status/synthesis/rounds/cost | No `consensus` field |
| Grafana `FacilitatePanel` / CLI synthesis | Renders synthesis + halt | No consensus indicator |

## 2. Requirements

- **FR-1 — Deterministic $0 lexical-divergence metric.** Token-set cosine across the R1 answers — no
  LLM, no embedding, no new dep, fully deterministic. It measures textual divergence (a coarse proxy),
  **not** semantic agreement.
- **FR-2 — Score + bucketed label.** Continuous score (0–1) **and** a bucketed label **high / mixed /
  low** with thresholds as documented named constants (calibrated for the low-baseline overlap of short
  domain answers, per plan R2).
- **FR-3 — Over R1 only.** The independent "Individual analysis" round, before R3 cross-pollination.
- **FR-4 — Exclude challengers from the headline.** Challengers (`role_id ∈ CHALLENGER_IDS`) are
  *prompted* to diverge; the headline consensus is computed over the non-challenger personas so
  structural framing isn't read as genuine disagreement.
- **FR-5 — Poll payload.** `facilitate_status` returns `consensus: {label, score, n, basis}`.
- **FR-6 — Grafana panel + terminal.** The `FacilitatePanel` status header shows the label (with the
  synthetic caveat); the CLI synthesis output prints a consensus line.
- **FR-7 — Honest framing.** Labeled a **synthetic, lexical** signal over role-played personas; it
  informs, never decides; `basis` records the method.
- **FR-8 — Graceful edge cases.** ≤1 rateable persona → `n/a`; halted/absent-R1 → `n/a` (no error);
  works across posture + tier.

## 3. Non-Requirements

- **NR-1 — No embeddings / LLM scoring** this increment (the deferred *semantic* upgrade path).
- **NR-2 — No clustering / topic modelling** — a single divergence scalar, not a map of camps.
- **NR-3 — No gating/blocking on low consensus** — #6 only *surfaces*; #8 consumes it at the apply gate.
- **NR-4 — No new persisted transcript field** — derived on read from the existing R1 entries.

## 4. Open Questions (post-planning)

- **OQ-6 → RESOLVED: lexical now + a documented embeddings seam** (sponsor decision). Ship the $0
  lexical signal, but structure `compute_consensus(rounds, *, exclude_role_ids, method="lexical")` so an
  embedding-backed method can be added later **without changing the poll payload or UI contract** — the
  return stays `{label, score, n, basis}`, and `basis` names the method (`"lexical-r1"` now,
  `"embedding-r1"` later). See **FR-9**.

- **FR-9 — Method seam (embeddings-ready).** `compute_consensus` takes a `method` selecting the scorer;
  the `{label, score, n, basis}` contract is method-agnostic so a future semantic backend is drop-in.
  The bucketing thresholds are per-method (lexical thresholds don't bind an embedding method).

---

*v0.1 — draft.*
*v0.2 — post-planning: 5 OQs resolved; metric reframed lexical-not-semantic; compute flipped to
lazy-derive (no new schema).*
*v0.3 — lessons hardening: phantom audit clean, own module, no provenance over-claim.*
*v0.3.1 — design-principle hardening: Hitsuzen/Mottainai/Genchi-Genbutsu/Accidental-Complexity/
Context-Correctness applied. One OQ (OQ-6) left for the sponsor. Ready for CRP.*
