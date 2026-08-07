# Cross-Repo Contract Health — Enhancement Backlog (CEP)

**Subject:** the ContextCore→SDK observability **contract-health surface** — how the SDK consumes the
`onboarding-metadata.json` / `.contextcore.yaml` producer contracts, and how that surface is kept
**correct, covered, and drift-proof** as it grows. (Distinct from SLI-kind *determination*, which the two
sibling backlogs below already mine.)

**Generated:** 2026-07-27 · Cumulative Enhancement Protocol (CEP).

---

## Provenance (FR-9)

**Prior-art manifest** — greps actually run:
- `grep -rl "ENHANCEMENT_BACKLOG" docs/` → two existing backlogs, **reconciled against, not duplicated**:
  - `docs/design/observability-requirement-shaped/OBSERVABILITY_REQSHAPED_ENHANCEMENT_BACKLOG.md` (fr_coverage surfacing, per-kind hint, base-RED-triple drift-seam, OQ-5 grounding pilot, enabling_flag, validate-promql wiring).
  - `docs/design/observability-compare/ENHANCEMENT_BACKLOG.md` (compare-live multi-container, span-metrics subjects, digest-pin, OTel metrics, probe wiring, lane unification).
- `gh issue list --state all --search "observability in:title"` → SLI-kind issues (#231/#233/#308/#319 open; #226/#228–230/#232/#254/#274–286/#307 closed) — **out of this subject** (determination, not contract health).
- **Gap confirmed:** neither existing backlog covers cross-repo *contract-health / drift-protection* — the axis opened this session by the golden round-trip (#352, extended #356). CEP targets that gap.

**CEP run shape:** N=3 independent seeders (18 ideas) → 1 cumulate round (6 moves, all CROSS). Quick pass (saturation reached in one round).

**R-4 kill metric (triage-surviving off-seed items):** **5 crossovers kept** (X1, X2, X3, X4, X6). One move (X5) demoted as a mislabeled same-seeder merge (not counted). 5 > 0 → CEP beat parallel-and-dedupe this run.

**Repo / branch:** `startd8-sdk` @ `cep/contract-health-backlog` (pushable; not `/tmp`/detached-HEAD).

**Honesty note:** seeders read the code + specs (grounded), but verify each item against the tree before building — the surface shifts. **Defect (`fix`) items carry their code-grounding** (CL-29 gate); a spec-graded defect the code already resolved is void.

---

## Ranked backlog (best-of-lineage)

### 🔴 Defect-first

**CH-1 — Make the vocab-parity drift guard actually fire (offline vendored snapshot).** `S` · `fix` · **X6** (CROSS s1-vendored + s2-parity-runs + s1-capture; seeders 1+2). **→ RESOLVED (this branch): `test_vocabulary_parity_offline.py` + `data/contextcore_vocab_snapshot.json` — the 7 parity guards now fire offline in SDK CI; the `importorskip` sibling stays as the live upgrade check + a snapshot-vs-live freshness test forces refresh. (#359 had widened the surface to 7 guards all behind the same dead `importorskip`.)**
The one guard against `REQUEST_KINDS`/`UNGROUNDED_KINDS`/`_TRIPLET_SIGNAL_KINDS`/`CANONICAL_SERVICE_KINDS` (`metric_descriptor.py:282`, a hand-copied literal of ContextCore's `ServiceKind`) drifting from upstream is `test_vocabulary_parity_contextcore.py:18`, which opens with `pytest.importorskip("contextcore.contracts.types")` — **ContextCore is not installed in the SDK venv, so it skips in every SDK CI run** (verified this session: same `ModuleNotFoundError` that skips the #345 carry test). Fix: commit a `contextcore_vocab_snapshot.json` (the enum values), assert the SDK mirror `==` snapshot **offline** (no importorskip), and keep the importorskip test as the live upgrade-path check. **Grounding:** `test_vocabulary_parity_contextcore.py:18`; `metric_descriptor.py:282`. *(Refresh mechanism has a design choice → not auto-applied; see CH-1a dependency on CH-6.)*

### 🚀 Enhanced capabilities

**CH-2 — Regen-and-diff CI lane: the golden captured FROM the real producer, drift-gated.** `M` · `new-capability` · **X1** (CROSS s1-S1 + s3-R5 + s1-S3; seeders 1+3). **Flagship.**
Today's golden (`test_onboarding_metadata_golden_roundtrip.py`, #352/#356) is **hand-authored-to-contract** — a fresh belief that ages the moment it's committed. A cross-repo CI lane (mirroring `observability-compare-live-gate.yml`) that installs both repos, regenerates the golden via ContextCore's `build_onboarding_metadata()` (`onboarding.py:654,1176`), and **fails on capture-vs-committed drift** converts the golden from a periodically-stale snapshot into a live gate. Neither a one-shot capture nor a static both-repos test catches producer drift *after* commit — the fusion does.

**CH-3 — Single-sourced consumed-key manifest → bidirectional coverage guards.** `M` · `wire-existing` · **X2** (CROSS s1-S4 + s2-single-source + s2-provenance; seeders 1+2).
Extract the ~30 hint keys the consumer reads (`artifact_generator_context.py:445–505`, today scattered string literals across two parse sites) into one `_CONSUMED_KEYS` manifest that drives **both** guards: (a) the golden *exercises* every consumed key (catches a consumer-side field the fixture forgot — the `enabling_flag` blind spot precedent), and (b) every producer-emitted key is consumed-or-known-ignored (catches a producer-side field the consumer silently drops). Neither guard alone anchors on a single greppable contract; fused, they can't independently drift.

**CH-4 — `$0` read-only `--validate` preflight (present-vs-defaulted + typo did-you-mean + malformed-value report).** `S` · `wire-existing` · **X4** (CROSS s3-R3 + s3-R4 + s2-datasource; seeders 2+3).
A read-only verb that dry-runs load+extract and reports, per service: which contract fields are present vs silently defaulted, did-you-mean typos of known keys, and present-but-malformed values (`datasources`/`descriptor_overrides`/`business`, isinstance-guarded to `{}` today at `:462–480`). Fusing the three moves the diagnosis **out of a live generation pass's log stream** into one upfront `$0` report — an author validates the contract before spending a run.

**CH-5 — Traceability-classified orphan FRs (typo vs plan-component-not-instrumented), or pin #29 as deliberate non-input.** `L` · `new-capability` · **X3** (CROSS s2-orphan + s2-traceability + s1-S6; seeders 1+2).
An FR whose `service` matches no fleet member (`f.service in (None, "", service.service_id)`, `artifact_generator.py:678` — no else-branch) is silently dropped. Surfacing it says *"FR-7 targets paymentsvc, not in the fleet"* but not *why* (fat-finger vs a plan component never built). Threading `ingestion-traceability.json` (#29, producer `plan_ingestion_workflow.py:2323`) into `load_business_context` classifies the two failure modes — which need opposite fixes. **Larger + speculative (consumes a new artifact); rank last.** Cheaper subset available: surface orphan FRs with a warning (the `S` half) without the traceability arg.

---

## 🃏 Wildcard (single-seeder, zero descendants — the orthogonality lane)

**CH-6 — `schema_version` on the onboarding-metadata contract + consumer version-tolerance.** `S` · `new-capability` · seed **s1:S5** (only seeder 1 raised it; no VARY/CROSS descendants).
The contract carries **no version field** (`onboarding-metadata.json` keys = `project_id`/`_note`/`instrumentation_hints`), and the consumer reads it purely structurally (`.get()` with silent defaults), so a producer schema bump degrades to *"observed by nothing"* rather than a legible mismatch — even though the SDK already stamps `schema_version` on its **own** output (`artifact_generator.py:1704`). Have the producer stamp `schema_version` and the consumer warn (not fail) on an unrecognized major. **The one true version-handshake idea; it underwrites CH-1's snapshot-refresh and CH-2's drift-diff (a version bump is the signal both watch for) — worth surfacing separately so a swarm of test-guards doesn't bury it.**

---

## ✅ Auto-applied this run (Phase 4 — XS/mechanical, verified) → PR

Both are the clean XS constituents of the **demoted** move X5 (a same-seeder R1+R2+R6 merge; the *fusion* was not cross-seeder, but the individual XS fixes stand on their own and were grounded as genuinely open):

- **CH-7 (R2) — Loader parse-error context.** `XS` · `fix`. `load_onboarding_metadata` did bare `json.load(f)`; a malformed artifact raised a `JSONDecodeError` that **doesn't name the file**. Now wrapped → `ValueError` naming path + line/col. **Grounded open:** no try/except at `load_onboarding_metadata`. Verified: `test_onboarding_loader_robustness.py::test_invalid_json_raises_with_path_and_position`.
- **CH-8 (R6) — Non-object hint guard.** `XS` · `fix`. `extract_service_hints` did `hint.get("transport")` (`:426`) with no `isinstance` guard → an opaque `AttributeError` on a non-dict hint value. Now a warned skip. **Grounded open:** no shape guard before the loop body. Verified: `::test_non_dict_hint_is_skipped_not_crashed`.

---

## Honest gaps & demotions (decisions, not tasks)

- **X5 demoted (Goodhart guard).** The "one hoisted shape-invariant guard" move fused R1+R2+R6 — but all three are **seeder 3** ideas, so it is a same-seeder consolidation, not a cross-seeder fusion; not counted in the R-4 kill metric. Its value survives as the auto-applied CH-7/CH-8 (and R1's `raw_hints` top-level guard remains a small open follow-up).
- **#29 traceability remains out-of-scope by default.** CH-5 is the only path that consumes it, and it is `L`/speculative; absent that, the golden (#356) documents #29 as a deliberate non-input — correct until a consumer need is proven.
- **CH-1 refresh is not auto-applied.** A vendored snapshot with a *manual* refresh is "a slower tautology"; its refresh should ride CH-2's regen script / CH-6's version signal — a design choice, so it stays a proposal.

---

## Selection is yours

CH-2/CH-3/CH-5 (M/L) and CH-1/CH-4/CH-6 (S) are **proposals** — pick what to build. Only CH-7/CH-8 (XS) were auto-executed, and even those stop at a PR you merge. Suggested order: **CH-1** (defect, the guard that never fires) → **CH-6** (version handshake underwrites the rest) → **CH-2** (flagship drift gate) → **CH-4** (`$0` author ergonomics) → **CH-3** → **CH-5**.
