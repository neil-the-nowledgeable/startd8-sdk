# Consensus / Divergence Signal — Implementation Plan

**Version:** 1.0 (Post-draft planning pass)
**Date:** 2026-07-10
**Requirements:** `CONSENSUS_SIGNAL_REQUIREMENTS.md` v0.1

---

## Planning discoveries (feeds the reflection)

Grounded against `kickoff_view/models.py` (transcript), `stakeholder_panel/facilitation.py` (rounds +
challenger ids), `kickoff_experience/facilitate_run.py::facilitate_status`, `scripts/run_kickoff_panel.py`.

| Draft assumption | Planning revealed | Impact |
|------------------|-------------------|--------|
| R1 answers are the independent first-take | **Confirmed** — R1 = "Individual analysis (means-ends)", per-persona from `ctx` with NO digest of others; R3 is the cross-pollination round (`_digest`). | FR-3 stands: compute over R1. |
| Challengers need a heuristic | **Confirmed constant** — `facilitation.CHALLENGER_IDS = {adversary-exploit, adversary-discredit, skeptical-new-user}`; identify by `entry.role_id in CHALLENGER_IDS`. Stable, works on old transcripts. | FR-4 has a clean deterministic answer (OQ-3). |
| Compute at synthesis + persist a new field | The R1 entries are **already persisted** on the transcript; a **lazy derive** in a shared pure fn is $0, migration-free, single-source (can't drift), and works on old transcripts. Recompute-per-poll cost is negligible (lexical over a few short strings). | **OQ-2 → lazy-derive, no new persisted schema** (NR-4 holds). |
| Lexical divergence ≈ agreement | **Weak proxy (the key limitation):** two personas can strongly AGREE using different vocabulary → low lexical overlap → falsely "low consensus." | Re-frame: this is a **lexical-divergence** signal ("how differently they *phrased* their takes"), a coarse $0 flag — **not** semantic agreement. Honest naming (FR-7); conservative buckets; embeddings = the deferred semantic upgrade (NR-1). |
| — | `facilitate_status` loads the full transcript (`t.rounds`) — the natural call site; CLI renders via `_print_synthesis`; plugin reads `FacilitateStatusResult`. | Surfaces (FR-5/6) are all thin reads of the one helper. |

## Approach

### Step 1 — the shared pure helper (the single source)
- New `src/startd8/stakeholder_panel/consensus.py`:
  - `ConsensusResult` (dataclass): `label` ("high"|"mixed"|"low"|"n/a"), `score: Optional[float]` (0–1),
    `n: int` (rateable personas), `basis: str` ("lexical-r1"), `to_dict()`.
  - `compute_consensus(rounds, *, exclude_role_ids) -> ConsensusResult`:
    - find the `round_id == "R1"` round; collect `entries[].text` for `role_id NOT in exclude_role_ids`;
    - normalize (lowercase, tokenize words, drop stopwords/very-common tokens);
    - `< 2` rateable → `n/a`;
    - mean **pairwise token-set cosine** similarity → `score`; bucket high/mixed/low by documented thresholds.
  - Pure, deterministic, no deps, no I/O.
- **Tests:** identical answers → high (score≈1); disjoint vocab → low; 1 persona → n/a; challenger excluded;
  ordering-independent; empty/whitespace-safe.

### Step 2 — poll payload (FR-5)
- `facilitate_status`: `consensus = compute_consensus(t.rounds, exclude_role_ids=CHALLENGER_IDS)`; add
  `"consensus": consensus.to_dict()` to the returned dict. Absent-R1/halted → `n/a` (no error).
- **Test:** a completed scripted-run status carries `consensus` with a label + n.

### Step 3 — Grafana panel (FR-6)
- `types.ts::FacilitateStatusResult` += `consensus?: {label, score, n, basis}`.
- `FacilitatePanel.tsx` status header: a small consensus chip ("consensus: high · n=4") with the
  synthetic caveat in a tooltip/label. **Real verify:** `npm ci && typecheck && lint && test && build`.

### Step 4 — CLI/terminal (FR-6)
- `run_kickoff_panel.py::_print_synthesis` (or its caller): print a "Consensus (synthetic, lexical): …"
  line from the same helper.

### Step 5 — docs
- Short note in the roadmap (#6 shipped) + a line in the panel README consensus behavior.

## Requirement → step trace
FR-1/2/3/4/8→S1 · FR-5→S2 · FR-6→S3+S4 · FR-7→S1(naming)+S3/S4(caveat) · (#8 hand-off, OQ-5)→S1 helper is the reuse point.

## Risks
- **R1 — lexical ≠ semantic** (the big one): mitigated by honest naming ("lexical divergence", "synthetic")
  + conservative buckets + embeddings as the documented deferred upgrade. Surface for CRP.
- **R2 — threshold calibration**: lexical overlap on short domain answers skews low; thresholds must be
  set against that, not against an intuition of 0.5=medium. Document + make them named constants.
- **R3 — TS unverified** — no longer a risk: the plugin is fully buildable in-repo now (real verify, S3).

*v1.0 — planning pass. Confirmed R1-independence + challenger constant; flipped OQ-2 to lazy-derive
(no new schema); surfaced the lexical≠semantic limitation as the headline reframe (honest naming).*
