# Synthesis: metabolizing the CRP review corpus into draft-time grammar — four investigations converge on one missing wire

**Date:** 2026-08-17 · **Type:** aggressive-investigation synthesis (ATM Phase-1.5 convergence) · **Status:** ship-ready backlog + one named class
**Grounds in:** `dev-os/CRP-INDEX.md` (7299 accepted rows / 463 docs) · `dev-os/det-req-kit/{SCHEMA.md, extract.py}` · `dev-os/PATTERN-CATALOG.md` (PC-16..18) · `REQ-07` (the 0-vs-2/2 false-positive data) · `REQ-22/23/25` (the already-metabolized liveness layer + fact-rung/judgment-rung split) · `startd8-sdk/query_prime/security` (the security reuse target)
**Predecessor:** `ANALYSIS_crp-index-review-wisdom-into-grammar.md` (identified the thread; this executes it via four parallel investigations)

---

## 0. What was investigated

Four parallel agents mined `CRP-INDEX.md`'s recurring review themes (the ranked backlog of "the same concern re-derived review after review") into **concrete det-req/det-plan grammar rules** — the shift-left move: metabolize a recurring finding into a *format rule* so the draft already satisfies it and reviews stop re-deriving it. Coverage:

| Investigation | Themes | Rows re-derived |
|---|---|---|
| **A — Ambiguity** | #2 specify/define/clarify | 542 |
| **B — Structure** | #3 schema/types/serialization · #6 state/lifecycle/resume | 323 + 218 |
| **C — Robustness** | error #122·231 · security #114·192 · concurrency #77·116 · determinism #77·96 | ~635 |
| **D — Framework + dormancy** | the general metabolizer + the re-seeking dormant path | — |

Together they cover **~1,700 of the 7,299 accepted suggestions** — the top un-metabolized mass (themes #1 verify + #4 observability were already metabolized into REQ-22/23).

---

## 1. THE CONVERGENCE (the class, named independently by all four)

> **Every metabolized theme lands at exactly one seam — the draft-time firing wire — and that seam is the same dormant value path Investigation D independently diagnosed.**

- **A** ships its ambiguity *fact-rungs* by extending `extract.py`'s `user_outcome_verify_advisory` machinery; parks its *judgment-rungs* behind REQ-07 FR-7.
- **B** lands `serialization_gaps` / `lifecycle_gaps` as `extract.py` lints (new `Emits:` / `Lifecycle:` fields + fact/candidate split).
- **C** lands all four robustness rules as `extract.py` lints, reusing `risk_type_advisory` and `query_prime/security verify_file`.
- **D** proves the re-seeking that motivates the whole effort is caused by the **absence of a draft-time firing wire**: the "Phase 4.5/4.6 keyed lookup" the analysis assumed exists **is not in the CRP path at all** — it's an unbuilt reflective-loop hook (`REQ-01 FR-4`, marked *Partial*), and `PATTERN-CATALOG` PC-16..18 self-report *"not yet wired as a draft-time check."*

**This is the ATM Phase-1.5 recurring class:** the metabolization pipeline (census → catalog → `/metabolize-finding` → `extract.py collect_findings`) is built end-to-end **except the firing seam**, and all four themes queue at it. Metabolizing *any* theme requires wiring that seam once; then each theme is an additive lint. **Fix the wire once → every theme's metabolization fires + the dormancy resolves, together.**

The convergence itself validates the method (the session's recurring signature): we already metabolized themes #1/#4 into REQ-22/23 fact cells — the same `extract.py` advisory seam — so this continues a *proven* path, not a speculative one.

---

## 2. The fact-vs-candidate split, per theme (the REQ-25 discipline, applied uniformly)

Every rule decomposes into a **fact-rung** (structural/presence — ships loud, cannot cry wolf) and a **judgment-rung** (semantic — parked by default behind REQ-07 FR-7, ships only as a dismissible candidate). This is the whole design hinge; it's what keeps an "ambiguity lint" from firing like the weak-verify check that went 2/2 false on a clean brief.

| Theme | New FR field | **Fact-rung** (ships now — GAP-class, exit-unchanged advisory) | **Judgment-rung** (parked — precision-gated candidate) | Left review-only (hypothesis cells) |
|---|---|---|---|---|
| **Ambiguity #2** | — | `placeholder` (bare `TBD`/`TODO`/`???`) · `open-enumeration` (`etc.`/`…`) · `unresolved-binary` (`whether…or…` w/ no verify branch) | `weasel-word` (`appropriate`/`reasonable`/`sufficient`/`gracefully`) · `undefined-term` | patterns A–D/F (schema/failure/threshold "should exist but absent" — no lexical tell) |
| **Schema #3** | `Emits: <artifact> schema=<ref> version=<field>` | emit-shaped FR (`.json`/`manifest`/`model_dump`) with **no `Emits:`** | has `Emits:` but no `version=`; no round-trip in `Verify:` | S-D bare-string→typed · S-E fallback-first-class |
| **Lifecycle #6** | `Lifecycle: states=… resume=… idempotent=…` | persist/resume-shaped FR with **no `Lifecycle:`** | has `Lifecycle:` but no `idempotent=` under retry; `states=` with no invalid-transition `Verify:` | L-D atomicity/lost-update · L-E rollback/GC/TTL |
| **Error #(err)** | `onFailure: fail-closed\|degrade\|typed-marker\|retry` | input-bearing `Touches:` (file/manifest/upstream/subprocess) with no failure behavior named | which behavior is correct (design judgment) | — |
| **Security #(sec)** | (reuses header `trustBoundary`/`dataClassification`) | a `security` risk / PII doc with no *resolvable mitigation vocabulary* (`sanitize`/`allowlist`/`parameterize`/`authz`) — the dangling-reference shape | whether the control holds → **already built:** `verify_file` (REQ-25 FR-1) | — |
| **Concurrency #(conc)** | — | a `python-data-store` write touch with no named write-discipline (`atomic`/`temp+rename`/`O_EXCL`/`build-then-swap`) | TOCTOU-free? merge truly keyed? | — |
| **Determinism #(det)** | — | a `deterministic-$0` FR whose `Verify:` names no determinism criterion (`--check`/`in_sync`/`byte-identical`/`sorted`/`seeded`) | source actually free of `Date.now()`/dict-order → **already built:** `--check` drift gate | — |

**Ambiguity is 87% three verbs** — specify (36%) / define (34%) / clarify (16%) — a tight, real signature; the object of the verb is what factors into the fact/judgment split above.

---

## 3. The ranked, ship-ready backlog (value × low-false-positive × reuse-leverage)

1. **Ambiguity fact-rungs (theme #2) 🥇** — largest deterministically-detectable slice (542 re-derivations), near-1.0 precision (placeholder/open-enum/unresolved-binary are structural facts), reuses the shipped `user_outcome_verify_advisory` machinery. *Ship now; park weasel/undefined-term.*
2. **Concurrency atomic-write lint (theme #(conc))** — *astonishingly stereotyped* accepted rows ("temp+fsync+rename / O_EXCL not TOCTOU"), so **lowest false-positive surface** — the cleanest proof-of-method for a hard `error`/exit-1 fact-rung.
3. **Security mitigation-vocabulary lint (theme #(sec))** — **highest reuse leverage**: REQ-25 FR-1 already metabolized the *code-side* fact-rung via `verify_file`; the missing half is the *draft-time* "a security risk names a resolvable control" lint, a small extension of `risk_type_advisory`.
4. **Schema `Emits:` + `serialization_gaps` (theme #3)** and **Lifecycle `Lifecycle:` + `lifecycle_gaps` (theme #6)** — proposed as **REQ-30 / REQ-31**, continuing the REQ-22/23 series; both fact-lints structurally decidable; det-plan is the stronger home for lifecycle's *process* half (grounded in the shipped `checkpoint.py` + `.startd8/state/` resume).
5. **Error `onFailure:` (theme #(err))** — highest doc count (122) but a fuzzier trigger ("touches an external input?"); needs advisory-tier tuning before it's a hard fact-rung.
6. **Determinism (theme #(det))** — *metabolize last:* already the most-enforced at code time (`--check` drift gate, SOTTO byte-identical); the marginal value of the grammar rule is lowest.

**Deliberately NOT metabolized** (the disciplined stopping point — hypothesis cells per REQ-23 NR-3): bare-string→typed, fallback-first-class, atomicity-correctness, rollback/GC. These need implementation-semantics judgment the det-req can't see structurally; forcing them into lints would cry wolf.

---

## 4. The two wires (Investigation D's fix — do these and the whole thing self-closes)

The pipeline parts all exist (census `render_crp_index.py` → catalog `PATTERN-CATALOG` + `pattern_catalog recall` → metabolizer `/metabolize-finding` → host `extract.py collect_findings`), wired at the *routing* level by `LOOP_CATALOG #7`. The single missing piece is the **draft-time firing wire**, and it has two ends:

1. **Fuel the review surface** (cheapest, highest leverage): have `new-cnvrg-rvw-prmpt` inject a *"Settled corpus themes — do not re-derive"* block from `CRP-INDEX.md`/`PATTERN-CATALOG.md` into every generated review prompt. Zero new engine.
2. **Fuel the draft surface** (the true shift-left): land the §2 fact-rungs as advisory content-lints in `det-req-kit/extract.py::collect_findings`, starting advisory (never break exit code) per REQ-06 FR-8 "never cry wolf." *This is where §3's backlog ships.*
3. **Complete `REQ-01 FR-4`** (mark it wired; run its stop/rollback gate) and **run `pattern_catalog sync`** so PC-16..18 are actually queryable — right now the top-3 themes aren't even in the recall store.

**Proposed `LOOP_CATALOG #8 — Review-Theme Metabolizer Loop:** census (`render_crp_index.py`) → promote top un-metabolized theme to `PATTERN-CATALOG` → `/metabolize-finding` → advisory `extract.py` lint → re-census. Moving number: *re-seek rate for a metabolized theme* (accepted rows/round → toward 0). Placement: **cross-kit family capability** (census is corpus-wide; host is det-req-kit; injection is the CRP generator) — the findings-half twin of the reflective-pairs → det-plan-kit lineage. Only irreducibly per-theme work: authoring each theme's lint predicate once (amortized across all its future re-seeks — 542 ambiguity re-derivations collapse to one predicate).

---

## 5. The one-line conclusion

*The 7,299 accepted review suggestions are the whole system's accumulated wisdom, and the recurring themes are a ranked backlog of the draft-time grammar rules the det-*-kits should enforce. Four investigations metabolized the top ~1,700 into concrete fact/candidate-split lints — and all four converged on the same missing seam: a single draft-time firing wire whose absence is exactly the re-seeking dormancy. Wire it once (two ends: review-prompt injection + `extract.py` content-lints), ship the ambiguity + atomic-write fact-rungs first, and the census stops being a read-only report and becomes a self-closing shift-left loop.*
