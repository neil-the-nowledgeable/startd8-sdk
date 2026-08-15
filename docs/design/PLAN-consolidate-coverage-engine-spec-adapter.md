# Consolidate per-language coverage generators into a CoverageEngine + spec + adapter — Plan

**Pairs with:** `REQ-consolidate-coverage-engine-spec-adapter.md` (v0.3.1)
**DIDL:** planned canonical ref `cc:intent:coverage-map:plan:engine-consolidation` (mirrors the REQ's; readable handle = this filename, no integer-led identity).
**Date:** 2026-08-15   **Scope:** behaviour-preserving refactor (characterization-guarded)

> **Execution note:** the consolidation is being drafted in an **isolated git worktree** (background agent),
> so it stays a reviewable proposal until this REQ is settled (spec-before-build preserved). This plan is the
> contract the worktree diff must satisfy.

## Iterations

### IT-0 — Characterization harness FIRST  → FR-5
- Before moving any code, snapshot the behaviour: capture the committed `{go,java,node}-capability-index/*`
  JSON+.md and the three analyzer summaries (coverage % + per-pattern counts). Write a test that regenerates
  via the (to-be) engine and asserts byte-identity. **This is the guard for every later step.**
- **Exit:** harness reproduces today's artifacts + numbers exactly (Go 46.2%/6, Java 38.5%/5, Node 23.1%/3).

### IT-1 — Extract the shared engine  → FR-1
- Move `serialize`/`sha`/`write_or_check`(drift)/`render_index_md`/`Detector`(matches/hyp/coverage_report)
  into `src/startd8/coverage_map/engine.py`. Parameterize the two variation points the render/matcher already
  have: path separator + has-annotations column.
- **Deps:** IT-0. **Exit:** engine imports cleanly; harness still green.

### IT-2 — `LanguageCoverageSpec` dataclass  → FR-2
- Define the typed spec (forms, composites+not_witnessable, crosswalk, floor, resolution_pending, metadata).
  Convert each language's `_*_structure_forms`/`_language_composites`/`_communication_crosswalk`/… into a spec instance.
- **Deps:** IT-1. **Exit:** each spec round-trips to today's JSON; harness green.

### IT-3 — `CoverageAdapter` + `LanguageProfile` reuse  → FR-3
- Read `languages/protocol.py`. If `LanguageProfile.import_pattern_template`/`source_extensions` cleanly
  supply the import-extractor + extensions, bind to them; else a minimal `CoverageAdapter` dataclass
  (extensions, import_fn, separator, has_annotations). **Document the fit/no-fit decision.**
- **Deps:** IT-1. **Exit:** Go/Node use today's import mechanism; Java carries has_annotations; no `*_parser.py` touched.

### IT-4 — Thin the 6 scripts  → FR-4
- Rewrite each `gen_*`/`analyze_*` as: build a `LanguageCoverageSpec` + `CoverageAdapter`, call the engine.
  Delete the duplicated skeleton. Report before/after LOC.
- **Deps:** IT-1, IT-2, IT-3. **Exit:** scripts are spec+adapter shims; combined LOC drops materially; `--check` exit 0 all three.

### IT-5 — Green + parity confirmation  → FR-5, O-2
- Run the 62 existing tests + the IT-0 harness + regenerate-and-`--check` + re-run all three analyzers `--no-write`.
- **Deps:** IT-4. **Exit:** 62 tests pass unchanged; artifacts + 3 coverage numbers byte-identical; report the diff.

## Traceability

| FR | IT | Verify seed |
|----|----|-------------|
| FR-5 | IT-0, IT-5 | characterization: engine output == committed artifacts |
| FR-1 | IT-1 | engine owns skeleton; harness green |
| FR-2 | IT-2 | spec round-trips to today's JSON |
| FR-3 | IT-3 | LanguageProfile fit documented; parsers untouched |
| FR-4 | IT-4 | scripts thinned; LOC drop; --check exit 0 |
| O-2 | IT-5 | 62 tests green; numbers byte-identical |

## Notes

- **Over-abstraction guard (the load-bearing constraint):** if a proposed generalization serves only these 3
  languages and adds indirection without removing duplication, reject it. One module + one dataclass + one
  adapter shape. No DSL, no plugin registry, no config files (NR-4).
- After landing: the `LanguageCoverageSpec` is itself a reusable artifact — note in the pattern doc that
  future derived views (instrumentation-gap, cross-repo domain matrix) consume the spec, not the scripts.
- The Tier-B languages (Ruby/Swift/PHP/Rust/C++/Erlang) will each be *just a new spec + adapter* against this
  engine — the consolidation's real payoff is that the next 6 variants are data, not code.
