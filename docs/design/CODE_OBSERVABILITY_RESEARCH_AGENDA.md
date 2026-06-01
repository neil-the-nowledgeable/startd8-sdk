# Code Observability — Research Agenda

> **Version:** 0.1 (2026-06-01)
> **Status:** Topic backlog for prioritization
> **Principle:** [MIERUKA_DESIGN_PRINCIPLE.md](../design-princples/MIERUKA_DESIGN_PRINCIPLE.md)
> **Related:** [CODE_OBSERVABILITY_DESIGN.md](./CODE_OBSERVABILITY_DESIGN.md) · [CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md](./CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md) · `scripts/spikes/code_observability/PHASE0_FINDINGS.md`

Each topic states the **question**, **why it matters** (linked to a REQ/OQ/risk), what a
**good answer** looks like, and a **priority**. P0 = blocks a near-term design decision;
P1 = needed before the relevant phase; P2 = strategic / opportunistic. Topics are tagged by
theme, not by phase, because several inform multiple phases.

---

## Theme A — Prior Art & Build-vs-Embed (clean-room defensibility + leverage)

### RT-A1 — Name/scope resolution on tree-sitter (P0) ⚠ biggest under-examined gap
**Q:** tree-sitter *parses* but does not *resolve* — given a call `foo()`, which declaration
does it bind to (especially cross-file, across imports, with shadowing)? Phase 0 resolved
calls only within a single file. What does accurate cross-file `CALLS` resolution require?
**Why:** REQ-MIE-220/410 depend on real call edges; without resolution the call graph is
approximate and edit-impact (Phase 2) is unreliable.
**Investigate:** GitHub **stack-graphs** / `tree-sitter-stack-graphs` (MIT — ironically
GitHub's own, post-CodeQL, and *permissively licensed*), scope-resolution approaches, and
whether we adopt it as a component vs. build per-language resolvers.
**Good answer:** a recommendation (adopt stack-graphs / build / hybrid) with a per-language
maturity read and a clean-room confirmation. **Note:** Python resolves natively (see RT-D4) —
this topic is really about the *tree-sitter* languages (Go/Java/C#/JS-TS); the cross-cutting
decision is one-resolver-everywhere (stack-graphs, consistent) vs. best-per-language (deeper).

### RT-A2 — Survey Kythe & Glean (P1)
**Q:** How do Google **Kythe** and Meta **Glean** model code facts, store them, serve queries,
and handle incrementality at scale? What did they learn that we can adopt?
**Why:** Strengthens the clean-room lineage (NFR-5) *and* gives proven design patterns for the
IR (REQ-MIE-100) and incremental extraction (NFR-3).
**Good answer:** a 1-page comparison (schema model, storage, query, incrementality) with
explicit "adopt / avoid / inspired-by" notes.

### RT-A3 — SCIP / LSIF as an interchange format (P1)
**Q:** Should `CodeGraph` emit (or import) **SCIP** (Sourcegraph) / **LSIF**? These are the de
facto code-intelligence interchange formats with existing per-language indexers.
**Why:** Interop with IDEs/Sourcegraph, and possibly free high-quality indexers we can feed
into the graph instead of writing extractors (relates to RT-A1, REQ-MIE-200).
**Good answer:** verdict on emit-SCIP / consume-SCIP / neither, with licensing + effort.

### RT-A4 — Build-vs-embed for taint: Semgrep as a component (P0)
**Q:** Semgrep has an open-source (LGPL) **taint mode** with dataflow. Can we *embed* it for
the precise-taint piece (Phase 2/3 risk) instead of building taint from scratch on our graph?
**Why:** §2 of the Phase 1 reqs names flow-sensitive taint as the concentrated risk; reusing a
mature engine could collapse that risk — *if* licensing and integration fit.
**Good answer:** licensing analysis (LGPL implications for our distribution), capability fit
(languages, sanitizer modeling), and a build-vs-embed-vs-hybrid recommendation.

---

## Theme B — Dataflow & Taint Analysis (the concentrated risk)

### RT-B1 — Static taint algorithms: IFDS/IDE & SSA (P0)
**Q:** What is the right algorithmic foundation for inter-procedural, flow-sensitive taint —
the **IFDS/IDE** framework (Reps–Horwitz–Sagiv), SSA-based dataflow, or something lighter?
**Why:** Determines whether REQ-MIE-330's DATAFLOW contract can later support *precise* taint
or stays coarse forever.
**Good answer:** a recommended algorithm class with complexity/precision tradeoffs and what
graph facts it needs us to emit (feeds the REQ-MIE-330 contract).

### RT-B2 — Source/sink/sanitizer specification model (P1)
**Q:** How should untrusted-source, dangerous-sink, and sanitizer sets be specified and
maintained per language (config? rule files? OWASP-derived catalogs)?
**Why:** REQ-MIE-230 hand-tags sources/sinks today; this won't scale beyond the fixture.
**Good answer:** a spec format + a starter catalog grounded in OWASP source/sink lists,
reconciled with our existing `query_prime/security` patterns (don't duplicate).

### RT-B3 — Precision/recall measurement & ground truth (P1)
**Q:** How do we *prove* our taint is better than today's regex `query_prime/security`? Which
labeled datasets (OWASP Benchmark, NIST **Juliet** Test Suite, real CVEs) and what harness?
**Why:** Without this, "better taint" is an assertion. Directly supports REQ-MIE-230 acceptance
and the honest-risk note in §2.
**Good answer:** a chosen benchmark + a precision/recall/F1 harness design we can run per phase.

### RT-B4 — Coarse-DATAFLOW usefulness threshold (P0, links OQ-1.4)
**Q:** Is Phase 1's coarse argument-flow DATAFLOW *useful on its own*, or does it only become
valuable once the Phase 2 flow-sensitive extractor lands? What's the false-positive rate on
real OSS targets (not just the fixture)?
**Why:** Resolves OQ-1.4 — whether REQ-MIE-230 ships in Phase 1 or waits.
**Good answer:** measured FP/FN on 2–3 OSS Go targets → ship-now vs defer recommendation.

---

## Theme C — OTel Data-Model Fit (is telemetry the right substrate?)

### RT-C1 — Traces vs. a graph store: honest architectural bake-off (P0)
**Q:** Are OTel traces genuinely the right primitive for a code graph, or are we forcing it?
Phase 0 showed TraceQL does coarse reachability but **not** link-chasing. Where's the line
where we'd want a real graph store (or graph DB) alongside/instead of Tempo?
**Why:** Foundational. The whole "reuse business-o11y stack" thesis rests on this fitting well
enough; we should pressure-test it before Phase 2 commits.
**Good answer:** a decision matrix (traces-only / traces+helper / traces+graph-store) with the
criteria that would flip the choice, plus the cardinality ceiling where traces break down.

### RT-C2 — TraceQL roadmap & span-link query support (P1)
**Q:** Does Tempo/TraceQL have any roadmap toward span-*link* traversal or transitive queries?
What exactly are today's limits (confirmed PARTIAL in Phase 0)?
**Why:** If link traversal is coming, the Phase 2 helper (RT-C3) might be thinner or temporary.
**Good answer:** current limits documented + roadmap signal; informs REQ-MIE-320 longevity.

### RT-C3 — Span-link emission mechanics (P0, = OQ-1.1 / OQ#6)
**Q:** Native OTel span Links (two-pass span-id pre-allocation) vs. resolved-target-span-id
*attributes* for DATAFLOW edges — which, and what are the downstream query costs of each?
**Why:** Locks REQ-MIE-320/330 before the contract is published.
**Good answer:** a recommendation with a tiny prototype of both against Tempo.

### RT-C4 — Cardinality controls & Mimir tenancy (P1, = OQ-1.3 / OQ#1, NFR-2)
**Q:** What are the concrete Mimir cardinality limits for per-element/per-module `code_*`
gauges, and should code metrics live in a separate tenant/namespace from business metrics?
**Why:** Phase 0 confirmed ~1:1 span:function scaling; NFR-2 controls must be sized correctly.
**Good answer:** label-budget guidance + tenancy recommendation + retention policy for `code_*`.

### RT-C5 — Emerging OTel semantic conventions for code/source (P2)
**Q:** Are there (draft) OTel semantic conventions for code/source attributes we should align
`span.code.*` / `code_*` names to, rather than inventing our own?
**Why:** Future interop + avoids a later rename. Cheap to check.
**Good answer:** alignment notes or "none exist, here's our namespaced convention."

---

## Theme D — Extraction Depth & Multi-Language

### RT-D1 — tree-sitter ABI versioning & the codebleu pin (P0, = REQ-MIE-500)
**Q:** What's the cleanest durable fix for `tree-sitter-go` 0.25 (ABI 15) vs. `codebleu`'s
`tree-sitter<0.23` pin — optional extra, subprocess isolation, vendored grammar, or replacing
codebleu?
**Why:** BLOCKING Phase 1.
**Good answer:** a chosen strategy validated by a clean `pip install` of the proposed extra.

### RT-D2 — Per-language grammar & resolution maturity (P1)
**Q:** For Go/Java/C#/JS-TS/Python, how mature are the tree-sitter grammars and (with RT-A1)
the resolution stories? Where will Phase 4 hit walls (generics, macros, partials, decorators)?
**Why:** Sets realistic expectations for the "One Model, All Languages" rule (Principle Rule 2).
**Good answer:** a per-language readiness table with known sharp edges.

### RT-D4 — Python-native resolution & taint stack (P0)
**Q:** How far can the **Python lane** go without the tree-sitter/stack-graphs machinery, using
native `ast` + stdlib **`symtable`** (scope), **`importlib`** (cross-file imports), **`dis`**
(bytecode-resolved calls), and the pure-Python ecosystem (**Jedi**/**astroid** for resolution,
**Pysa** for real flow-sensitive taint, **LibCST** for lossless splicing)? Where's the line
between stdlib-only and pulling in a library?
**Why:** Python is the most mature SDK language and the cheapest **proving ground** for the
full resolution→dataflow→taint vision (RT-A1, RT-B1) — validate algorithms here before
generalizing. Reshapes REQ-MIE-210 and the build-vs-embed calculus per-lane.
**Constraints to confirm:** native `ast` is *not* partial-file tolerant (NFR-1 → hybrid with
tree-sitter for inner-loop) and is interpreter-version-bound; `dis`/`inspect` need importable,
side-effect-safe code.
**Good answer:** a Python-lane stack recommendation (stdlib core + which libs, with licenses)
covering resolution + taint + splicing, and the explicit ast-vs-tree-sitter context split.

### RT-D3 — Incremental extraction strategy (P1, NFR-3)
**Q:** What's the right granularity (file vs. element) and invalidation key (content hash vs.
commit) for incremental re-extraction after a splice? How do tree-sitter's incremental-parse
APIs help?
**Why:** NFR-3 + inner-loop latency (NFR-4); stable IDs (REQ-MIE-110) are a prerequisite.
**Good answer:** an incremental design that re-processes only affected files sub-second.

---

## Theme E — Downstream Capabilities (Phase 2/3 foresight)

### RT-E1 — Change-impact / blast-radius analysis (P1, Phase 2)
**Q:** What are proven techniques for "which callers break if I change this signature?"
(call-graph reachability, change-impact analysis, regression-test selection literature).
**Why:** Backs the graph-aware splicing capability (design §2.6-B, Principle Rule 5).
**Good answer:** a method we can compute from `CodeGraph` `CALLS` fan-in, with edge cases
(dynamic dispatch, interfaces, reflection) flagged.

### RT-E2 — Code-graph visualization in Grafana (P2)
**Q:** Can Grafana's **node-graph / service-graph** panels render call graphs and dataflow
usefully, or do we need the contextcore-owl plugin path?
**Why:** Layer-3 "Code Observability dashboard pack" (Phase 4) UX.
**Good answer:** a feasibility note + which panel type fits, built via `/dbrd-cr8r`.

### RT-E3 — Query ergonomics: do PromQL/LogQL/TraceQL answer real dev questions? (P1)
**Q:** Catalog the questions Prime Contractor actually needs answered ("unused exports",
"callers of X", "modules with rising coupling", "tainted handlers") and test which map cleanly
to the three query languages vs. need a thin helper DSL.
**Why:** Validates the core "no new query language" thesis (Principle Rule 4) before we over-rely on it.
**Good answer:** a question→query mapping table with a "needs helper" column.

---

## Theme F — Validation & Integration

### RT-F1 — Benchmark target selection (P1)
**Q:** Which OSS targets (online-boutique is already in use; others?) give us buildable,
realistically-sized, multi-language ground truth for extraction + taint evaluation — with no
licensing gate?
**Why:** Feeds RT-B3/RT-B4 and Phase 1 verification beyond the synthetic fixture.
**Good answer:** a short curated target list with size/language/license notes.

### RT-F2 — Feed path into forward_manifest / micro_prime / Kaizen (P1)
**Q:** Beyond REQ-MIE-410, what's the highest-value way for `CodeGraph` to enrich
`forward_manifest_extractor`, the `micro_prime` decomposer/splicer, and Kaizen trend analysis
without duplicating existing structural logic?
**Why:** Ensures the IR earns its keep across the pipeline, not just as a standalone index.
**Good answer:** an integration map (producer → consumer) with the dedup boundaries called out.

---

## Suggested first wave (P0 cluster)

If we run research before Phase 1 implementation, the P0 set that unblocks the most decisions:
**RT-A1** (name resolution — or our call graph is approximate), **RT-C1** (traces-vs-graph-store
honesty check), **RT-C3** (span-link mechanics → locks REQ-MIE-330), **RT-D1** (the blocking
pin), and the taint pair **RT-A4 + RT-B1** (build-vs-embed + algorithm) since that's where the
real value and the real risk both concentrate. RT-B4/RT-C-cardinality follow closely.
