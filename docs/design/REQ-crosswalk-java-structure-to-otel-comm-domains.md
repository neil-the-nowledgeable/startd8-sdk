# Crosswalk Java structural surface + annotations to OTel communication domains — Requirements

**Project:** startd8-sdk · Java structure→OTel §5 capability index   **Criticality:** medium
**Version:** 0.2 (Post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-crosswalk-java-structure-to-otel-comm-domains.md`
**Inherits standards:** det-req-kit · DIDL · `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` (the pattern this instantiates) · `REQ-crosswalk-go-structure-to-otel-comm-domains.md` (the advisory-tier sibling)
**Audience:** operator (SDK maintainer running the index/coverage generator)

> **DIDL:** Semantic name — *Crosswalk Java structural surface + annotations to OTel communication
> domains*. Planned canonical ref — `cc:intent:java-comm-index:requirement:crosswalk`. Readable handle —
> `REQ-crosswalk-java-structure-to-otel-comm-domains.md`.

## 0. Planning Insights (Self-Reflective Update)

> Java was picked as the "authoritative-tier generality test" (exercise the call-site φ). Grounding
> `java_parser.py` **falsified that premise** and replaced it with a better one: Java is body-blind like
> Go, but adds the **annotation φ axis** Go lacked. The variant's job is therefore to stress a *new φ
> signal*, not a new tier. This drove a **template-level correction** in the pattern doc (fidelity × depth
> × annotation — see its "Substrate model refinement").

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Java (authoritative) exercises the call-site φ | `java_parser.py:11` — **"Does not parse method bodies (no call graph)"**; and `javalang` isn't installed → regex fallback. Authoritative *fidelity* ≠ call-graph *depth*. | Call-site φ stays **floor** for Java too. The call-site axis is Python-only (depth-gated). → FR-5, template refinement |
| φ is imports + declarations (like Go) | Java has **annotations** (`@Path`, `@GrpcService`, `@KafkaListener`), extracted by `java_parser` (`JavaElement.annotations`, `_parse_annotations`). | φ gains a **third signal**: `annotation_signatures`, declaration-attached (no body walk). This is what Java uniquely tests. → FR-2, FR-4 |
| Any authoritative parser is call-graph capable | Only Python's extractor walks bodies. Java/Go/C# are declaration-depth. | The pattern's "tier" split was one axis doing two jobs → corrected to fidelity × depth. → pattern doc |
| Corpus = reuse Go's | Go corpus is `.go`. Java needs its own. | Corpus = **`OSS/kestra`** (2106 `.java`; `@Path` 140, `@Repository` 42 — real annotation + import signal). → FR-4, O-3 |

**Resolved open questions:**
- **OQ-1 → No parser, no body-walker.** Consume `parse_java_source` (declarations + annotations) + its imports. NR-1/NR-2.
- **OQ-2 → The annotation axis is the point.** φ carries `import_signatures` **and** `annotation_signatures`; a §5 pattern fires on either.

## Overview

A Java analogue of the Go index, adding the **annotation φ axis**. Crosswalks Java's declaration-depth
structural surface — imports + top-level declarations + **annotations** (via
`startd8/languages/java_parser.py`) — to the **same 15 OTel §5 semconv domains** as the Python/Go pilots.
Java is authoritative-*fidelity* but **body-blind** (declaration-depth), so the call-site φ remains a
floor; the new signal it exercises is annotation-based detection (e.g. `@Path` → HTTP even when the import
is generic). Adds **no parser**; reuses the language-agnostic `ElementKind` layer.

## Objectives

- O-1: A Java index whose L4 crosswalk keys are **key-for-key identical** to the Python/Go pilots' 15 §5
  semconv domains (invariant portability — now across three languages).
- O-2: A working **`annotation_signatures`** detection path — the first φ signal beyond imports since
  Python's decorators; a §5 pattern fires on import **or** annotation. **✅ works, but IT-5 measured its
  marginal DOMAIN contribution = 0** — annotations co-occur with their package imports (`@Path` ⇒
  `javax.ws.rs`), so at file×domain granularity annotation ⊆ import. The axis's real value is
  element-level precision + span-role, NOT domain coverage (folded into the pattern doc as a template lesson).
- O-3: A coverage number for `OSS/kestra` — **baseline 38.5% achievable (5/13) over 2106 files** (IT-5);
  detected HTTP/RPC/DB/GENAI/CLI, all via imports; 8 not-evidenced (the ecosystem-grounded set + messaging).
- O-4: Zero new parsing machinery — consume `java_parser.py` (Mottainai).

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Hand-authored Java L1/composite constants drift from `java_parser`'s emitted kinds | `--check` drift guard + parity test (forms ⊆ `PARSER_KIND_SETS["java"]`) | high |
| quality | `javalang` absent → regex fallback emits fewer/looser elements than assumed | Ground the parity test on regex-fallback output (the actual runtime path here), not the javalang ideal | high |
| quality | Annotation signatures overfit to kestra's JAX-RS; miss Spring/Micronaut | Ground signatures across ≥2 annotation families; mark `grounding` | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Author the Java structural-element surface (L1) as a maintained constant.** Emit
  `java-structure-forms.json` enumerating the forms `java_parser` recognizes (class, interface, enum,
  record, method, constructor, field, constant), each `JAVA-STRUCT-###`. Touches: gen-index, `docs/design/java-capability-index/java-structure-forms.json`. Verify: every form's `parser_kind` ∈ `manifest_adapter.PARSER_KIND_SETS["java"]`; a kind emitted by `parse_java_source` on a real fixture with no form fails the parity test. Serves: O-1, O-4
- **FR-2 — Author the L4 crosswalk φ with 15 §5 keys, Java `import_signatures` AND `annotation_signatures`.** Emit
  `communication-crosswalk.json` (`JAVA-OTEL-5.*`) with the **same 15 semconv domains** as the Python file,
  each carrying Java `import_signatures` (`io.grpc`, `javax.sql`, `org.apache.kafka`, …) and, where the
  domain has a declaration-attached marker, `annotation_signatures` (`Path`/`GET`→http, `GrpcService`→rpc,
  `KafkaListener`→messaging), plus `grounding: corpus|ecosystem`. Touches: `docs/design/java-capability-index/communication-crosswalk.json`. Verify: `semconv_domain` set == Python's; each non-floor entry has ≥1 import **or** annotation signature. Serves: O-1, O-2
- **FR-3 — Author the Java composites (L3) keyed on `java_forms`, not `ast_nodes`.** Emit
  `language-composites.json` (`JAVA-LC-*`) for declaration-level idioms (annotated-type, interface-impl via
  `implements`, generic-type, nested-class, annotation-bearing-method), each referencing `java_forms`; a
  `not_witnessable` block records body-level idioms (lambda-in-body, try-with-resources, stream-pipeline).
  Touches: `docs/design/java-capability-index/language-composites.json`. Verify: no `ast_nodes` field; every `java_forms` id is a `JAVA-STRUCT-###`. Serves: O-1
- **FR-4 — Coverage analyzer matches imports AND annotations (no new extraction).** `analyze_java_comm_coverage.py`
  walks `*.java`, calls `parse_java_source` (elements carry `.annotations`) + its import extraction, computes
  `hyp(f)` matching φ's `import_signatures` ∪ `annotation_signatures`, and reports coverage with an
  **import-hits vs annotation-hits breakdown**. Touches: analyze-cov, opt-workdir. Verify: over `OSS/kestra` detects `JAVA-OTEL-5.1-HTTP` via the `@Path` annotation path; reports which patterns were annotation-only. Serves: O-2, O-3, O-4
- **FR-5 — `detectability_floor` names the un-witnessable + resolution-pending patterns.** Floor = call-body
  patterns (`5.2-HTTP-METRICS`) + no-signal patterns (`5.7-CICD`), marked `floor: advisory` (correct-absence),
  **plus** any §5 pattern reachable *only* via a call site — marked **`floor: resolution-pending`** because Java
  is resolution-blind *today* but the SDK roadmaps the unlock (**scip-java**, CKG Phase 4 — `CODE_KNOWLEDGE_GRAPH_DESIGN.md`),
  not a permanent absence. Touches: `docs/design/java-capability-index/communication-crosswalk.json`, analyze-cov. Verify: floor patterns never appear in any `hyp(f)`; report shows achievable-vs-floor split; resolution-pending entries cite the SCIP unlock. Serves: O-2
- **FR-6 — Drift-guard + regenerate (Kagami).** `gen_java_structure_comm_index.py --check` re-generates + sha-compares
  (exit 1 on drift); the `.md` index is regenerated from JSON with a generated-do-not-edit banner. Touches: opt-check, exit-drift, `docs/design/JAVA_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md`. Verify: hand-edit a JSON → `--check` exits 1; the `.md` carries the banner. Serves: O-2

## Non-goals

- **NR-1 — Do not modify `java_parser.py` or add a Java parser.** Consume it as-is (regex-fallback path included).
- **NR-2 — Do not attempt call-site / resolution for Java.** That is the resolution-pending floor (FR-5). The
  canonical unlock is **not** a bespoke body-walker but the SDK's planned **SCIP** path (`scip-java`, CKG
  Phase 4 — `CODE_KNOWLEDGE_GRAPH_DESIGN.md`); when it lands, the call-site φ can be added to *all* languages
  at once. Do not fork that here.
- **NR-3 — Do not re-derive `ElementKind` (L2).** Cite `manifest_adapter.map_parser_kind`.
- **NR-4 — Do not restate the 15 semconv domain definitions.** Cite the Python crosswalk + OTel semconv.

## Owned fields

Only humans enter: `reason` strings in `detectability_floor`; any φ entry `note` marked advisory.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8; the 15 §5 keys = `docs/design/python-capability-index/communication-crosswalk.json`; Java forms + annotations = `startd8/languages/java_parser.py`.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| gen-index | console-script | structure | `python3 scripts/gen_java_structure_comm_index.py`; emits JSON + .md; owns drift guard |
| analyze-cov | console-script | structure | `python3 scripts/analyze_java_comm_coverage.py`; consumes `parse_java_source` (+ annotations) |
| opt-check | option | structure | `--check` drift guard |
| opt-workdir | option | words | `--workdir` corpus root (default `OSS/kestra`) |
| exit-drift | exit-class | structure | `exit 1` on drift; `exit 0` on match |

> The emitted data artifacts (`java-capability-index/*.json`) + the `.md` are **outputs** of gen-index,
> named as file paths in FR `Touches:` — not CLI vocabulary entries.

---

## Appendix A — Accepted (with where merged)

## Appendix B — Rejected (with rationale)

## Appendix C — Incoming review rounds

---

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified extant: `parse_java_source` + `JavaElement.annotations` +
  `_parse_annotations` (java_parser.py), `PARSER_KIND_SETS["java"]`, `map_parser_kind`. The `javalang`
  dependency is **absent at runtime** (grounded: import fails) → the regex-fallback path is the real one;
  FR-1/risks reflect that, not the javalang ideal.
- **[Single-source vocabulary ownership]** — the 15 §5 domains + the Go sibling's crosswalk shape are the
  owners; this REQ cites them, re-authoring only Java signatures (imports + annotations).
- **[Prune phantom scope]** — the call-site φ (the original reason for picking Java) was pruned to NR-2 +
  the FR-5 depth-floor once grounding showed Java is body-blind.
- **[CRP steering]** — least-reviewed surface = the `annotation_signatures` field (new; no sibling has it).

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Genchi Genbutsu]** — the whole §0 is this principle firing: bound to the *real* `java_parser` (body-blind,
  regex-fallback) + the *real* corpus (kestra annotations), not the "authoritative Java" assumption. Prevented
  building a call-site φ that would never fire. **Grounded against the SDK's own multilang SSOT** rather than
  re-derived: the tier model + `per-parse tiering` = `MULTILANG_MANIFEST_VALIDATION_REQUIREMENTS.md` FR-5
  (javalang-absent → advisory-in-practice is *their* named case); the call-site unlock = SCIP/CKG
  (`CODE_KNOWLEDGE_GRAPH_DESIGN.md` §4). Mottainai: cite these, don't invent parallel vocabulary.
- **[Mottainai]** — consume `java_parser` + annotations + `ElementKind`; no parser, no body-walker, no L2 (NR-1/2/3).
- **[Kagami]** — JSON + `.md` are derived; `--check` is the runnable regen; `.md` banner (FR-6).
- **[Accidental-Complexity (anti)]** — resisted adding a body-walker to "make Java authoritative"; the
  annotation axis is the minimum new mechanism that fits the substrate and tests something Go couldn't.

*v0.3.1 — Post lessons + principle hardening. 4 planning discoveries (1 premise-falsifying → template correction,
1 new φ axis, 2 grounding). The annotation axis is the new template stress. Ready for CRP-lite.*
