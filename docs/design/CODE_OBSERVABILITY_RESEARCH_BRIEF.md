# Code Observability — Research Brief (Instructions for the Researcher)

> **Version:** 0.1 (2026-06-01)
> **Audience:** A researcher (human or agent) executing the investigation that informs the
> Code Observability / "Mieruka" effort.
> **Companion docs (read first, ~15 min):**
> [CODE_OBSERVABILITY_DESIGN.md](./CODE_OBSERVABILITY_DESIGN.md) ·
> [CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md](./CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md) ·
> [CODE_OBSERVABILITY_RESEARCH_AGENDA.md](./CODE_OBSERVABILITY_RESEARCH_AGENDA.md) ·
> [MIERUKA_DESIGN_PRINCIPLE.md](../design-princples/MIERUKA_DESIGN_PRINCIPLE.md) ·
> `scripts/spikes/code_observability/PHASE0_FINDINGS.md`

---

## 1. What this brief is

This document tells you **what to research, why, and exactly how to report results.** It
assigns the **P0 first-wave topics** (the ones that unblock imminent design decisions). The
full topic list (P1/P2) lives in the Research Agenda; the same output format applies to those.

Do **not** start writing code. This is investigation that feeds requirements and design
decisions. Your output is a written report, not an implementation.

## 2. Context you need (the 60-second version)

We are building **"Code Observability"**: model code *structure* (symbols, calls, dataflow) as
OpenTelemetry signals so the same **PromQL / LogQL / TraceQL** surface we already run for
business observability becomes the query interface for "what code exists, what it does, how to
edit it safely." It is a deliberate, **clean-room alternative to CodeQL** — we want CodeQL's
*value* (query code as data) without its *delivery mechanism* (relational/Datalog DB, build-
coupled extraction, and a license that gates proprietary code).

A Phase 0 spike already validated the pipeline (tree-sitter → a `CodeGraph` IR → OTel → live
Tempo) and found that **TraceQL gives only coarse reachability, not precise taint** — that gap
is the main reason this research exists.

## 3. Operating rules (apply to every topic)

1. **Clean-room IP discipline.** You may study, cite, and compare CodeQL — but do **not**
   transcribe or paraphrase CodeQL query semantics, copy `.ql` library code, or recommend using
   CodeQL binaries/extractors/DB format. When you recommend a tool or technique, **confirm it is
   independent of CodeQL** and note its lineage.
2. **Licensing is a first-class finding.** For every tool/library you recommend, state the
   **license** (MIT / Apache-2.0 / LGPL / GPL / commercial) and the **distribution
   implication** for an SDK we may ship. A capable tool with an incompatible license is a
   *rejected* option — say so explicitly.
3. **Cite primary sources.** Prefer official docs, source repos, specs, and papers over blog
   posts. Every non-obvious claim needs a citation with a URL. Note the **publication/commit
   date** when recency matters (it is June 2026 — flag anything that looks stale or
   fast-moving).
4. **Separate fact from inference.** Mark claims as **[verified]** (you confirmed from a primary
   source), **[reported]** (a secondary source asserts it), or **[inferred]** (your reasoning).
   Do not present inference as fact.
5. **Answer the decision, not just the topic.** Each assignment names a **decision it unblocks**
   (a REQ/OQ). Your report must end each topic with a concrete recommendation for that decision,
   even if hedged — "insufficient evidence, here's what would resolve it" is a valid answer.
6. **Flag what you could not verify.** A short "Gaps / unknowns" line per topic is mandatory.

---

## 4. Assignments (P0 first wave)

Work in roughly this order; RT-A1 and RT-D4 are the most load-bearing.

### Assignment 1 — RT-A1: Name/scope resolution on tree-sitter
- **What:** Determine what accurate **cross-file call resolution** requires on top of
  tree-sitter (which parses but does not resolve). Investigate GitHub **stack-graphs /
  `tree-sitter-stack-graphs`** as the leading candidate, plus alternatives.
- **Why:** Our Phase 0 call graph resolved calls only *within* one file. Without cross-file
  resolution, the `CALLS` graph is approximate and edit-impact (Phase 2) is unreliable.
- **Answer specifically:** Is stack-graphs production-ready for Go/Java/C#/JS-TS? License?
  Effort to adopt vs. building per-language resolvers? Is it CodeQL-independent?
- **Decision it unblocks:** REQ-MIE-220/410; the one-resolver-everywhere vs. best-per-language
  choice.

### Assignment 2 — RT-D4: Python-native resolution & taint stack
- **What:** Determine how far the **Python lane** can go *without* tree-sitter/stack-graphs,
  using native `ast` + stdlib (`symtable`, `importlib`, `dis`) and the pure-Python ecosystem
  (**Jedi**, **astroid**, **Pysa**, **LibCST**). Where is the stdlib-only line?
- **Why:** Python is our most mature language and the **cheapest proving ground** for the full
  resolution→dataflow→taint vision before we generalize.
- **Answer specifically:** Can stdlib `symtable`+`importlib` resolve cross-file Python calls
  well enough, or is Jedi/astroid needed? Is **Pysa** usable as an embeddable taint engine
  (license, API, standalone-from-Pyre feasibility)? Confirm the constraints we believe true:
  native `ast` is not partial-file tolerant and is interpreter-version-bound.
- **Decision it unblocks:** REQ-MIE-210; whether to validate taint (RT-B1) in Python first.

### Assignment 3 — RT-C1: Traces vs. a graph store (architectural bake-off)
- **What:** Pressure-test whether OTel **traces** are genuinely the right primitive for a code
  graph, or whether a real **graph store** belongs alongside/instead of Tempo.
- **Why:** The entire "reuse the business-o11y stack" thesis rests on this fitting well enough.
  Phase 0 showed traces do coarse reachability but not link-chasing.
- **Answer specifically:** At what code size/cardinality do traces break down? What query
  classes are impossible on traces that a graph store handles trivially? Provide a decision
  matrix: **traces-only / traces+helper / traces+graph-store**, with the criteria that flip it.
- **Decision it unblocks:** the substrate commitment before Phase 2.

### Assignment 4 — RT-C3: Span-link emission mechanics (= OQ-1.1)
- **What:** Compare **native OTel span Links** (via two-pass span-id pre-allocation) vs.
  **resolved-target-span-id attributes** for representing DATAFLOW edges.
- **Why:** Phase 0 found span Links require the target SpanContext to exist at creation, so a
  top-down call tree can't natively link to unborn children. We must pick before publishing the
  DATAFLOW contract.
- **Answer specifically:** Downstream query cost of each in Tempo; which the Phase 2 graph
  helper consumes more cleanly; any OTel SDK constraints.
- **Decision it unblocks:** REQ-MIE-320 / REQ-MIE-330.

### Assignment 5 — RT-D1: tree-sitter ABI vs. the codebleu pin (BLOCKING)
- **What:** Find the cleanest durable fix for `tree-sitter-go` 0.25 (grammar ABI 15) needing
  core ≥0.25 while `codebleu` pins `tree-sitter<0.23`.
- **Why:** This blocks Phase 1 installation.
- **Answer specifically:** Evaluate optional-extra isolation, subprocess isolation, vendoring
  the compiled grammar against the pinned core, and replacing/relaxing codebleu. Recommend one,
  with the `pip install` shape it implies.
- **Decision it unblocks:** REQ-MIE-500.

### Assignment 6 — RT-A4 + RT-B1: Taint — build vs. embed, and the algorithm
- **What:** (RT-A4) Can we **embed** an open-source taint engine — **Semgrep** taint mode
  (LGPL), or **Pysa** for Python — instead of building taint ourselves? (RT-B1) If we build,
  what algorithmic foundation (**IFDS/IDE**, SSA-based dataflow, lighter) fits?
- **Why:** Flow-sensitive taint is the **concentrated risk** of the whole effort; this is where
  the real value over today's regex `query_prime/security` lives, and exactly what TraceQL does
  *not* give for free.
- **Answer specifically:** Semgrep taint-mode capabilities (languages, sanitizer modeling) and
  the **LGPL distribution implications** for our SDK; Pysa standalone feasibility; if building,
  which algorithm and what graph facts it requires us to emit (this feeds REQ-MIE-330).
- **Decision it unblocks:** the Phase 2/3 taint strategy (build / embed / hybrid).

> P1/P2 topics (RT-A2, RT-A3, RT-B2/B3/B4, RT-C2/C4/C5, RT-D2/D3, RT-E*, RT-F*) are in the
> Research Agenda. Use the **same output format** below when you get to them.

---

## 5. How to format your results

Deliver **one markdown file** named `CODE_OBSERVABILITY_RESEARCH_FINDINGS.md` in
`docs/design/`. Structure it exactly as follows.

### 5.1 Top of file
```
# Code Observability — Research Findings
> Version / Date / Researcher
> Scope: which assignments are covered (e.g. P0 first wave: RT-A1, RT-D4, RT-C1, RT-C3, RT-D1, RT-A4+RT-B1)
```

### 5.2 Executive summary (≤1 page, first)
A table with one row per assignment:

| Topic | One-line recommendation | Decision unblocked | Confidence (H/M/L) | Blocking issue? |
|-------|-------------------------|--------------------|--------------------|-----------------|

Follow the table with 3–5 sentences on the **single most consequential finding** for the
effort overall.

### 5.3 Per-topic section (repeat for each assignment)
Use this exact template:

```
## RT-XX — <title>

**Recommendation (BLUF):** <one or two sentences — the decision, stated plainly>

**Key findings:**
- <finding> [verified|reported|inferred] — <source URL>
- ...

**Decision impact:** <which REQ/OQ this resolves, and how it changes the doc — e.g.
"REQ-MIE-330: encode DATAFLOW as attributes, not Links">

**Licensing & clean-room check:** <license of any recommended tool + distribution implication;
explicit confirmation it is CodeQL-independent>

**Confidence:** <High|Medium|Low> — <why>

**Gaps / unknowns:** <what you could not verify and what would resolve it>

**Sources:**
1. <Title> — <URL> (<date if relevant>) — primary|secondary
2. ...
```

### 5.4 Cross-cutting section (end of file)
- **Recommended P0 decisions, consolidated** — a short list the design team can act on.
- **New questions surfaced** — anything your research exposed that isn't yet a topic (propose
  an RT-ID so we can add it to the agenda).
- **Suggested changes to existing docs** — name the file + REQ/OQ and the proposed edit.

---

## 6. Definition of done

- All six P0 assignments answered, each ending in a concrete recommendation.
- Every recommended tool has a stated license + distribution implication.
- Every non-obvious claim is tagged [verified|reported|inferred] and cited.
- The executive-summary table is complete and the consolidated P0 decisions are listed.
- Findings written to `docs/design/CODE_OBSERVABILITY_RESEARCH_FINDINGS.md`.
