# Code Knowledge Graph (CKG) — Ground-Up Redesign

> **Version:** 1.0 (2026-06-01)
> **Status:** Architecture — supersedes the *architecture* of `CODE_OBSERVABILITY_DESIGN.md`
> (the "throw-one-away" prototype). Keeps the **Mieruka** principle (make code structure
> queryable); replaces the substrate.
> **Brooks frame:** *"Plan to throw one away; you will, anyhow."* The Code Observability spike
> (tree-sitter + OTel-traces-as-store) was the prototype. It worked well enough to teach us the
> three things that make this redesign necessary. We keep its lessons, discard its substrate.
> **Forcing context:** [CROSS_FILE_CONTRACT_RESOLUTION.md](./CROSS_FILE_CONTRACT_RESOLUTION.md)
> — the RUN_003→RUN_009 trajectory and the 16 cross-file contract failures this system exists to kill.

---

## 0. Research reconciliation (2026-06-01)

This design was checked against `CODE_OBSERVABILITY_RESEARCH_FINDINGS.md` (first pass) and
`CODE_OBSERVABILITY_RESEARCH_SECOND_PASS.md`. Net: the architecture holds; five points are
locked or corrected, and three Phase-1-critical bets remain **unvalidated** and become spike
gates (see `CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md`).

**Locked / corrected by research:**
- ✅ **SCIP-first validated** — active **Apache-2.0** indexers for Go/Java/TS/C#, compiler-grade
  resolution, strongest on complete/buildable targets = CKG *authoritative* mode. tree-sitter
  stays the *draft* (partial/inner-loop) extractor. The two-mode split is confirmed.
- ✅ **stack-graphs rejected** as a resolver (archived 2025-09; 4 languages, no Go/C#; Rust-only).
  Use SCIP + per-language native resolvers. (CKG was already SCIP-first; this removes a fallback.)
- ✅ **Substrate = persisted CodeGraph helper, embedded (SQLite), not a server graph DB.** Matches
  L4. Flip to an external graph DB only past ~500MB graphs + willingness to operate one.
- ✅ **DATAFLOW encoding decided:** CodeGraph `DATAFLOW` edges are canonical; emit
  `span.code.dataflow_target_ids` as Tempo-visible attributes; native OTel Links are optional
  enrichment only (TraceQL can't transit links).
- ✅ **Taint (Phase 3):** Pysa subprocess (MIT) for Python; build IFDS-lite over CodeGraph for Go;
  **reject Semgrep CE** for cross-file taint (intraprocedural-only; interfile is Pro/commercial);
  **avoid Heros** (LGPL-2.1). Note: CKG's Phase-1 contract checks are *resolution equality*
  checks (CONFORMS_TO / field-set), **not taint** — cheap, and independent of this.

**Unvalidated → Phase-1 spike gates (research did not cover these):**
- ⚠️ **Prisma DMMF** programmatic access (`@prisma/internals` `getDMMF`) — the bet that kills 5/16
  canonical-schema failures. Untested.
- ⚠️ **scip-typescript** operational cost + fact coverage on a RUN_009-scale Next.js+TS project
  (does it need `npm install`? seconds vs minutes? does it surface route/`.d.ts` facts we need?).
- ⚠️ **Cross-DSL `CONFORMS_TO` inference** (binding a Zod schema to its Prisma model) — prior art
  exists (zod-prisma generators) but the inference rule is unverified.

---

## 1. What the throwaway taught us (and why it forces a redesign)

The prototype was not wasted — it converted three assumptions into hard constraints:

| Prototype assumption | What we learned (evidence) | Forcing function for the redesign |
|---|---|---|
| tree-sitter is enough to understand code | tree-sitter **parses but does not resolve** — it can't tell you which declaration `foo()` binds to across files. The Phase 0 call graph was intra-file only. | **Resolution is the actual product**, and the tools that resolve perfectly already exist: each language's own compiler. Use them. |
| OTel traces can be the source of truth | TraceQL does coarse `>>` reachability but **cannot chase links / express taint**; cardinality scales ~1:1 with functions. | **The graph is the source of truth in a real store; observability is a *projection*,** not the substrate. |
| Python `ast` is the gold standard backend | `ast` is **not partial-file tolerant** (raises `SyntaxError`) and is interpreter-version-bound. | **Two extraction modes** (authoritative vs. draft) and **best-tool-per-language**, not one-parser-fits-all. |
| Verification (Approach B) can be a later phase | The cross-file verifier has been **named in four consecutive postmortems and never shipped**; the result is the **score-vs-reality inversion** (4 PASS verdicts on broken builds). | **Verification is a Phase-1, non-deferrable, central service** — not an add-on. Deferring it *is* the documented failure mode. |

And from `CROSS_FILE_CONTRACT_RESOLUTION.md`, the deepest lesson:

> The root problem is the **locality of generation** — a per-file probabilistic generator makes
> 9 categories of local decisions, each a coin-flip for cross-file coherence. Giving it the
> knowledge is **necessary but not sufficient** (§3: the drafter *read* `schema.prisma` and
> *still* wrote `inputTokens` against a `promptTokens` model). The system must (a) provide
> authoritative facts AND (b) **verify** every cross-file contract after generation, in a
> world that spans **multiple languages and DSLs** (TS, Prisma, JSON config, `.d.ts`).

---

## 2. Design goals

- **G1 — Authoritative, never guessed.** Every fact is traceable to the language's own
  toolchain (compiler/type-checker/DSL emitter). No regex approximations in the authoritative path.
- **G2 — Resolution is first-class.** Binding references → definitions across files *and across
  languages/DSLs* (TS code → Prisma field) is the core capability, not a side effect.
- **G3 — Verification is central and non-deferrable.** The Contract Verifier ships in Phase 1.
  It is the answer to the chronic deferral and the score-vs-reality inversion.
- **G4 — Best-possible cross-language + cross-DSL.** Each language/DSL is handled by its
  highest-fidelity tool; gaps are filled by small **custom native parsers we build ourselves**
  and call from Python.
- **G5 — Two modes.** *Authoritative* (whole-project, compiler-backed, highest fidelity) and
  *draft* (partial-file-tolerant, fast, for the inner generation loop).
- **G6 — Truth in a queryable store; observability is a view.** The graph lives in a real,
  transactional, incremental store. OTel/Grafana is an optional projection for humans.
- **G7 — Incremental.** Per-file invalidation keyed on content hash; re-extract only what changed.

---

## 3. Architecture overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L6  PROJECTION (optional view — realizes Mieruka for humans)               │
│     OTel metrics + Grafana "code observability" dashboards. NOT truth.     │
└───────────────▲────────────────────────────────────────────────────────────┘
                │ derived
┌───────────────┴────────────────────────────────────────────────────────────┐
│ L5  SERVICES (the two first-class consumers)                                 │
│   ① Knowledge Provider (pre-gen)  → authoritative context to spec_builder    │
│   ② Contract Verifier  (post-gen) → cross-file contract checks AS QUERIES    │
│      (Approach A + Approach B, unified over one resolved model)              │
└───────────────▲──────────────────────────────────────────────────────────────┘
                │ query
┌───────────────┴────────────────────────────────────────────────────────────┐
│ L4  STORAGE — Code Knowledge Graph (source of truth)                         │
│     SQLite-backed fact store (transactional, incremental, zero-dep, queryable)│
└───────────────▲──────────────────────────────────────────────────────────────┘
                │ normalized facts
┌───────────────┴────────────────────────────────────────────────────────────┐
│ L3  RESOLUTION — bind references→defs across files & languages/DSLs          │
│     Trust the compiler where it resolves (go/types, TS checker, Roslyn);     │
│     our resolver only bridges cross-DSL edges (TS↔Prisma↔config).            │
└───────────────▲──────────────────────────────────────────────────────────────┘
                │ raw facts (one schema)
┌───────────────┴────────────────────────────────────────────────────────────┐
│ L2  FACT SCHEMA — language-agnostic nodes/edges (Keiyaku-typed contract)     │
│     Two modes: authoritative (compiler-backed) | draft (partial-tolerant)    │
└───────────────▲──────────────────────────────────────────────────────────────┘
                │ JSON over stdout/IPC
┌───────────────┴────────────────────────────────────────────────────────────┐
│ L1  FEDERATED EXTRACTORS (probes) — best tool per language/DSL               │
│   SCIP indexers where they exist · custom native probes for gaps · DSL emitters│
└──────────────────────────────────────────────────────────────────────────────┘
```

The shape is deliberately **Kythe/Glean-style fact federation** (independent, cross-checked
prior art — *not* CodeQL): language-specific indexers emit facts into a common schema; a
serving layer answers queries. We adopt the pattern; we own the schema and the store.

---

## 4. L1 — Federated extractors (the cross-language heart)

**Principle: never reimplement a type system.** Each language's compiler already resolves
imports, types, and symbols perfectly. We harvest its output rather than approximating it.

### 4.1 SCIP-first
**SCIP** (Sourcegraph Code Intelligence Protocol) is a cross-language *resolved-symbol* fact
format with mature indexers that **already drive the native compilers**:

| Language/DSL | Authoritative extractor | Mechanism | Resolution quality |
|---|---|---|---|
| TypeScript/JS | **scip-typescript** | runs the TS Compiler API (`ts.TypeChecker`) | full: imports, `.d.ts`, types |
| Go | **scip-go** | uses `go/packages` + `go/types` | full type resolution |
| Python | **scip-python** *(or our `ast`+`symtable` probe)* | type inference + stdlib | high |
| Java | **scip-java** | javac/Gradle integration | full |
| C# | **scip-dotnet** | Roslyn semantic model | full |
| Rust/others | scip-* as available | native | full |

SCIP indexers are exactly *"native parsers called from a common layer"* — already built, MIT/
Apache-licensed, compiler-backed. We **consume SCIP** and normalize it into the CKG. This buys
best-possible cross-language resolution with near-zero custom parser code.

### 4.2 Custom native probes — only where SCIP can't reach (the user's ask)
Where no SCIP indexer exists, where we need facts SCIP doesn't carry, or for **DSLs**, we build
small native probes and call them from Python over a JSON-on-stdout contract:

| Source | Probe | Why custom |
|---|---|---|
| **Prisma schema** | **`prisma` DMMF** via `@prisma/internals` (Node) | Prisma *emits* its own resolved model graph (DMMF JSON) — models/fields/types/constraints/relations. Kills 5 of 16 RUN_009 failures (canonical-schema) deterministically. No parsing to write. |
| `package.json` / `tsconfig.json` | trivial Python JSON readers | dependency-availability + project-config categories |
| Go (if we want facts beyond SCIP, or no toolchain) | tiny **Go probe** using `go/parser`+`go/types` → JSON | full control; productizes the spike fixture into a real native extractor |
| C# (lightweight) | small **Roslyn** dotnet tool → JSON | semantic model when scip-dotnet is too heavy |
| Inner-loop / partial code | **tree-sitter** (draft mode) | the one place tree-sitter belongs: fast, error-tolerant, no build |

**IPC contract.** Probes are processes that read file paths and write **normalized fact JSON**
to stdout (the L2 schema). Default: one-shot subprocess. For incremental speed (G7), a probe may
run as a **long-lived daemon** answering re-extraction requests. The JSON fact schema is the
**Keiyaku-typed A2A contract** between every probe and the graph — versioned, validated.

---

## 5. L2 — The fact schema (one model, all sources)

A language-agnostic graph. Nodes and edges are intentionally small and universal so a Prisma
field and a TS interface property are the *same kind of thing* to the verifier.

**Nodes:** `Module` (file), `Symbol` (function/class/method/var), `Type`, `Field`, `Param`,
`Route` (HTTP endpoint), `Dependency` (external package), `ConfigEntry`, `ModelEntity` (DSL
model, e.g. a Prisma model). Each carries `id` (stable, path+fqname+kind — *not* line numbers),
`source` (which probe + tool version), `mode` (authoritative|draft), `span`, `signature`.

**Edges:** `DEFINES`, `IMPORTS`, `CALLS`, `REFERENCES`, `INHERITS`, `DATAFLOW`, and the
cross-DSL one that matters most here: **`CONFORMS_TO`** (a code symbol claims to mirror a DSL
model — e.g., a Zod schema ⇄ a Prisma model; a TS request type ⇄ a route's contract).

**Two modes (G5).** Every fact is tagged `authoritative` (compiler/DMMF-backed) or `draft`
(tree-sitter, partial-tolerant). The Knowledge Provider prefers authoritative; the inner loop
tolerates draft. Verdicts are only emitted from authoritative facts (so we never re-create the
score-vs-reality inversion on guessed data).

---

## 6. L3 — Resolution

- **Trust the compiler.** SCIP/DMMF facts arrive already resolved; we ingest bindings as-is.
- **We resolve only the seams** the individual compilers can't see: **cross-DSL** and
  **cross-language** edges — the `CONFORMS_TO` relationships. Example: bind a TS `z.object({...})`
  named `ProofPointSchema` to the Prisma `ProofPoint` `ModelEntity` and diff their `Field` sets.
  *This is the exact check that would have caught RUN_009 failures #9, #13.*
- This is the principled home for the cross-file contract logic that `forward_manifest` and
  `cross_file_imports.py` approximate today.

---

## 7. L4 — Storage (truth) vs L6 — Projection (view)

- **L4 store = SQLite fact tables** (nodes, edges, with indices). Rationale: transactional,
  incremental, zero external dependency, trivially queryable from Python, embeddable in
  `.startd8/state/`. (Glean uses a custom content-addressed store at Meta scale; SQLite is the
  honest right-sized choice for our scale — revisit only if we outgrow it.) **This is the source
  of truth.**
- **L6 projection = OTel/Grafana**, derived from the store: `code_*` metrics, contract-compliance
  gauges, findings logs, call-graph node-graph panels. This is where the **Mieruka** principle is
  satisfied for human operators — but it is a *read model*, never queried by the pipeline for
  correctness. This demotion is the central correction from the throwaway.

---

## 8. L5 — The two services (this is what fixes RUN_009)

### 8.1 Knowledge Provider (pre-generation) = Approach A, done right
A deterministic query API over the CKG that feeds `spec_builder` authoritative answers, bounded
to the feature's `target_files` + their import-graph closure (finite token cost): what files
exist and export what, dependency manifest, tsconfig aliases, Prisma model field/type tables,
existing route shapes, external SDK type surface (from `.d.ts` via SCIP).

### 8.2 Contract Verifier (post-generation) = Approach B, finally central
Every generated file is checked against the CKG **before the feature is marked successful**.
Each of the seven RUN_009 categories is a **query over the resolved graph**, not a bespoke regex:

| RUN_009 category | CKG query | Backed by |
|---|---|---|
| module-path (6) | every `IMPORTS` edge resolves to a `DEFINES` target | SCIP / draft resolution |
| dependency-availability (1×2) | every external `IMPORTS` has a `Dependency` node | package.json probe |
| external-library-API (2) | every `REFERENCES` to an external `Symbol`/`Type` resolves | SCIP `.d.ts` facts |
| canonical-schema (5) | every `db.<model>.x({...})` field ∈ the `ModelEntity` field set, types agree; compound keys ∈ constraints | Prisma DMMF |
| api-request/response-shape (2) | `Route` request/response `Type` ⇄ consumer expectation via `CONFORMS_TO` | SCIP + resolution |
| type-signature (2) | param/return types resolve; no unused-by-contract params | SCIP |
| project-config (2) | tsconfig path alias targets exist; framework-mode facts present | config probes |
| Zod↔Prisma symmetry | `CONFORMS_TO` field-set + type-class agreement | DMMF + SCIP |

A failed query → feature marked failed, pipeline stage attributed (`drafter / cross-file
contract / <query_name>`), Kaizen suggestion emitted. **This is the load-bearing item that
ships first** (§11), so verdicts stop being decorative.

---

## 9. What we keep from the throwaway

- The **Mieruka principle** (code must be queryable before it's mutated) — now on a sound substrate.
- The **CodeGraph IR concept** — generalized into the language-agnostic L2 fact schema.
- **Keiyaku-typed contracts** — now the probe↔graph JSON fact schema.
- The **`forward_manifest` integration point** — the Knowledge Provider is its authoritative backend.
- The **Phase 0 evidence** (TraceQL limits, cardinality) — it's *why* L6 is a projection, not the store.
- **tree-sitter** — kept, but scoped to *draft mode* (inner-loop, partial files) only.

## 10. Clean-room & build-vs-embed

- **Embed, don't reinvent:** SCIP indexers (compiler-backed, permissive), Prisma DMMF, native
  compiler APIs. We write parsers only for genuine gaps.
- **Independent lineage:** Kythe/Glean fact-federation + SCIP + each language's own compiler.
  None is CodeQL; we touch no CodeQL binaries/QL/DB-format/semantics. Per-tool licenses recorded
  per the research brief's discipline.

## 11. Phased rollout — aimed at the bleeding, verification-first

The old plan was Python/Go-first. **That was the prototype's bias, not the problem's shape.**
The bleeding is the **TypeScript + Prisma** stack of RUN_009. Lead there.

- **Phase 1 (kills the inversion):** scip-typescript + Prisma DMMF + package.json/tsconfig probes
  → CKG (SQLite) → **Contract Verifier** wired as a hard gate into the prime pipeline. Knowledge
  Provider feeds spec_builder. *Verification ships in Phase 1 — non-negotiable.* Target: the exact
  16 RUN_009 failures become detected (and most preventable) instead of false-PASS.
- **Phase 2:** Knowledge-Provider-driven **contract-first** data-layer sequencing (Prisma→Zod→
  API→UI) to *prevent* the canonical-schema drift Approach A alone can't (the §3
  necessary-not-sufficient finding).
- **Phase 3:** Go + Python authoritative probes (productize the spike's native Go extractor);
  draft-mode tree-sitter for inner-loop on all languages.
- **Phase 4:** Java/C# via scip-java/scip-dotnet; the L6 Grafana projection.

**Anti-deferral guardrail:** the Contract Verifier cannot slip past Phase 1. It has slipped four
times; this design treats that as the primary risk, not a nicety.

## 12. Risks & open questions

- **OQ-1 — SCIP indexer operational cost.** scip-typescript needs a resolvable TS project (deps
  installed). Acceptable for the authoritative whole-project index; confirm it's not on the inner
  loop (draft mode covers that). How heavy on RUN_009-scale projects?
- **OQ-2 — Cross-DSL `CONFORMS_TO` inference.** How do we *know* a given Zod schema is meant to
  mirror a given Prisma model — naming convention, explicit annotation, or heuristic + confirm?
- **OQ-3 — Daemon vs one-shot probes** for incremental latency (G7); which languages justify a daemon.
- **OQ-4 — SQLite ceiling.** At what repo size do we need a real graph store? Define the trip-wire.
- **OQ-5 — Prevent vs detect split.** Phase 1 detects; how much of canonical-schema can Phase 2
  contract-first actually *prevent* given the §3 finding that knowledge-in-context wasn't enough?
- **OQ-6 — Authoritative mode needs buildable-ish code.** Where does that leave mid-batch
  verification of a partially-generated batch — verify per-completed-feature against the
  authoritative target index + draft facts for in-flight siblings?

## 13. Mapping to CROSS_FILE_CONTRACT_RESOLUTION Approaches A–F

| That doc's approach | This design |
|---|---|
| A — Pre-flight project-knowledge artifact | **L5 Knowledge Provider** over the CKG |
| B — Verify-after-generate (load-bearing, deferred 4×) | **L5 Contract Verifier**, Phase-1, central |
| C — Contract-first generation | **Phase 2**, fed by the Knowledge Provider |
| D — Single-pass batch synthesis | orthogonal workflow choice; CKG verifies its output |
| E — Iterative refinement w/ cross-file feedback | the Verifier is E's detector + loop-exit condition |
| F — Schema-driven scaffold | DMMF facts make this natural later; deferred per that doc |

This design is the structural treatment §10 ("the Brooks frame revisited") of that doc calls
for: it treats cross-file coherence as a **first-class, authoritative, verified concern**,
instead of extending per-file inheritance to the n+1th category.
