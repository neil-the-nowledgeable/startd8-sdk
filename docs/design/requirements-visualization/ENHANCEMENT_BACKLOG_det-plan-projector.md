# Enhancement backlog — the det-plan projector (REQ-29)

**Date:** 2026-08-17 · **Subject:** `src/startd8/plan_codegen/` (shipped `35e75c89`, hardened `33606c12`, standard `c3273dec`)
**Pass:** HTH Phase 4 (value/reach). Bug-review was Phase 1; complexity is out of lane. **CEP: skipped (NR-5 — bounded `$0`-projector surface; single-pass is proportionate).**

**Grounding note (belief → actual corrections):**
- Believed the "unexercised provider skip-path" was a *built-but-unwired defect*. **Actual:** the provider IS wired
  (registry `pyproject.toml:197`, discovered=True) and unit-tested; it is only *un-exercised end-to-end*. → a
  **validation** item (EC-3), **not** a P0 defect. (Cleared the defect gate: the wire is real; the negative is only
  "no prime run has driven it," which is a coverage gap, not a break.)
- Believed `dependsOn` was empty because the projector couldn't derive it. **Actual:** the projector **already fully
  consumes** authored FR deps — `_fr_depends_map`/`_DEPENDS` (`projector.py:83,290,298`) parse them and `_assert_acyclic`
  (`:314`) cycle-rejects them. The gap is purely upstream (det-req has no field to author). → reframes EC-1 from "build
  dependsOn" to "**author the field the built consumer is already waiting for**."

---

## Top findings (do first)

**EC-1 — Add a first-class `Depends:` FR field to det-req (unlock the already-built dependsOn consumer).** — **M**
The projector's dependency machinery is **fully built and idle**: `_fr_depends_map` + `_DEPENDS` (`projector.py:83,298`)
parse `Depends: FR-x, FR-y`, `project_plan` maps them to iteration edges (`:347`), and `_assert_acyclic` (`:314`)
cycle-rejects them via `queue.py`. But **zero real reqs author the field** (grepped: 0 `Depends:` across all 5 pilot
reqs) because det-req's single-line FR grammar has no parsed slot for it (pilot fold-in G-1). *This is the classic
latent path — the consumer is 100% done and just has no producer.* Add a parsed, position-defined `Depends:` field to
det-req-kit's grammar → every projected `dependsOn` becomes real and the build-order DAG stops being 100% human-residue.
→ so a **req author can encode FR ordering once** and every projected plan (and any future det-doc consumer) reads a real
DAG **without hand-drawing it in prose**. (Cross-kit: det-req-kit owns the grammar; the SDK side is already done.)

**EC-2 — Corpus-wide `generate plan --check` CI gate + batch sweep.** — **S**
`generate plan --check` already returns the exit-code contract (0 in-sync / 1 drift — `cli_generate.py`, tested in
`test_cli.py`), and `validate_plan` already computes conformance+liveness findings on every run (`:1065`). Two cheap
wraps: (a) a batch verb/loop that projects all plan-owed REQs in the corpus in one command (today it's one `--requirements`
at a time), and (b) a CI recipe that runs `--check` over the committed `*.projected.md` so a req edit that would change its
plan fails the build. → so a **maintainer catches a stale projected plan the moment a req changes**, instead of it drifting
silently. (Wires two things that already exist; no new engine.)

**EC-3 — Prove the provider's `$0`-skip path end-to-end (validation, not a feature).** — **S**
`DetPlanProjectorProvider.is_in_sync` (`provider.py`) is unit-tested and registry-wired, but **no test drives it through a
real prime-contractor run** with a det-plan `.md` as a target file — the only context where the skip-hook actually consults
it (Phase-2.5 inventory: `unexercised`). One integration test that runs the prime skip-hook over an in-sync projected plan
and asserts `$0.00`-skip closes the loop. → so the team **knows the `$0` claim holds in the real pipeline**, not just in
isolation. (Same latent-risk class as any provider that's wired but never exercised by its true caller.)

---

<details>
<summary><b>Backlog appendix</b> (draw from over later increments)</summary>

### ⚡ Quick wins
- **EC-4 — `--sarif -` / always-emit option.** SARIF is computed on every run but only *written* when `--sarif <path>`
  is passed (`cli_generate.py:1069`); findings otherwise only hit the console. A `--sarif -` (stdout) or a default
  sidecar next to `--out` lets a CI/IDE consume the findings without a second flag. **XS.**
- **EC-5 — Name the `--out` in the `--check`-with-no-`--out` message.** `--check` without `--out` prints `None` in the
  drift message (harmless but confusing). Guard: require `--out` under `--check`, or print a clearer hint. **XS.**

### 🌱 Low-hanging fruit
- **EC-6 — Surface `costClass` finer than one band (needs a per-FR regime).** Every iteration bands `llm-integration`
  today (pilot G-2) because det-req declares no per-FR realization. If EC-1's field work lands, a sibling `Regime:` FR
  hint would let `_regime_of_fr` (`projector.py`) resolve `deterministic-$0`/`human` per FR instead of the coarse default.
  **S** (and gated on a det-req grammar add, like EC-1).
- **EC-7 — Make `--strategy shared-touches` discoverable.** The alternate grouping is built + CLI-exposed
  (`cli_generate.py:1023`, default `per-fr`) but undocumented in help beyond one line; a `generate plan --help` example
  and a note in the SCHEMA §2 fold-back would surface it. **XS.**

### 🚀 Enhanced capabilities (Yokoten — higher effort, justify by the standard)
- **EC-8 — Adopt `STANDARD_det-doc-kit-projector-pattern.md` for the next projector (det-crp / det-handoff).** The
  extracted standard (`c3273dec`) says the 5-part shape is reusable; the *second* adoption is what promotes it from
  "proved-once" to a true standard (the `/reflective-adoption` gate). Building the det-crp projector against this standard
  is the highest-leverage next family step — and stress-tests I-1 (audit det-crp's source grammar for authored fields
  first). **L.**

### Honest gaps (decisions, not bugs)
- **The empty `dependsOn` is correct today, not a bug.** Until EC-1 lands, an empty DAG is the *honest* projection — the
  charter's human-gated ordering residue. Don't "fix" it by inferring edges from shared `Touches`/ordinal (that would
  violate never-inferred, §8). EC-1 is the *only* legitimate way to make it non-empty.
- **One-iteration-per-FR is a deliberate default, not laziness.** Strategic batching is human judgment (pilot G-3);
  `shared-touches` exists for those who want coarser, but the transparent scaffold is the right default.

</details>

*Tight backlog: 3 top findings + 5 appendix items, all grounded to `file:line`. EC-1 is the flagship — it turns a fully-built idle consumer live.*
