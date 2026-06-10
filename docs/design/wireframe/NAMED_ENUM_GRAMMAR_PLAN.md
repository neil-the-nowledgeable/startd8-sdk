# Named / Shared Enum Grammar — Implementation Plan

**Version:** 1.0 (post-investigation)
**Date:** 2026-06-09
**Requirements:** [`NAMED_ENUM_GRAMMAR_REQUIREMENTS.md`](NAMED_ENUM_GRAMMAR_REQUIREMENTS.md) (v0.1)
**Status:** Planning — feeds the reflective update to requirements v0.2

This plan maps each FR to concrete files/changes in `src/startd8/manifest_extraction/`, and records
what the code investigation revealed that the v0.1 requirements assumed away.

---

## Discoveries (planning ⇄ requirements)

> The v0.1 draft inherited the strtd8 query's framing ("add a named-enum construct; it composes
> cleanly"). Reading the code revealed five corrections.

| v0.1 assumption | Planning revealed | Impact |
|-----------------|-------------------|--------|
| `enum: ApplicationStatus` in the Type cell parses straightforwardly | `entities.py:146` **lowercases the entire type cell** (`ftype = strip_annotations(...).lower()`) before matching. `enum: ApplicationStatus` becomes `enum: applicationstatus` — the enum **name is destroyed**. | FR-PE-9 must parse the reference from the **raw** (un-lowercased) cell. New explicit requirement; without it the name can't be recovered. |
| Inline `choice of:` already works; we add a parallel named path | `choice.group(1)` (the `a\|b\|c` values) is **discarded** — `DocField` has no values field — and `prisma_emitter.py` emits **no enum block at all**. Every `choice of:` field today references a **dangling** type. | FR-PE-10 (value capture + block emission) is a **prerequisite for any enum to round-trip**, not an add-on. It is the load-bearing fix; the named form layers on top. |
| `semantic_diff()` will catch enum drift | `semantic_diff()` iterates only `parsed.models`; it never looks at `parsed.enums`. The parity gate is **blind to enums** — `ApplicationStatus` could diverge silently. | FR-PE-11 promoted from "nice" to **load-bearing** for the reconciliation acceptance (the whole point is the live 9 values must match). |
| Enums land on the graph like entities | `_build_graph()` only routes the `Entities` section to an extractor and merges `entities`/`joins`/`fk_parents`. No `enums` field on `EntityGraph`; no routing for an `## Enums` section; no cross-doc merge. | FR-PE-8 needs: new `EntityGraph.enums` field, a new `extract_enums()`, new section routing, and a `setdefault` merge mirroring entities. |
| The Prisma parser may need enum support | `prisma_parser.py` **already** parses enum blocks: `enums: Dict[str, Tuple[str,...]]` (ordered), `_parse_enum_body`, `is_scalar_or_enum`. | FR-PE-10 round-trip + FR-PE-11 diff are **low-risk** — the parse side exists. Confirmed assumption, not a gap. |
| Inline `choice of: a\|b\|c` values parse cleanly from a table cell (implementation-time discovery) | `grammar.py::md_tables` split cells on **every** `\|`, including the escaped `\\\|` the authoring contract documents for literal pipes — so `choice of: open\|won\|lost` lost all but its first value. Masked until now because values were discarded. | One extra fix: `md_tables` now splits on **unescaped** pipes only and unescapes `\\\|` → `\|`. Benefits all cell parsing; full suite green. |

**Open-question resolutions from planning:**
- **OQ-PE-6 → `enum: <Name>` confirmed**, but it MUST be matched against the raw type cell (the
  lowercasing trap). A bare PascalCase `<Name>` token is rejected — it would collide with the
  case-folding and with future composite-type names.
- **OQ-PE-8 → flag collisions.** Synthesized `<Entity><Field>` names and `## Enums` names share one
  namespace; a collision is `not_extracted(enum-name-collision)`, never a silent merge.
- **OQ-PE-5 → pipe-line confirmed** (reuses the `choice of:` value delimiter — one parse rule for
  both forms).

---

## Step-by-step

### Step 1 — `EntityGraph.enums` + `extract_enums()` (FR-PE-8)
- `entities.py`: add `enums: Dict[str, Tuple[str, ...]] = field(default_factory=dict)` to
  `EntityGraph`. Extend `all_model_names()`? No — enums are not models; keep separate (the emitter
  and `semantic_diff` handle them on their own track).
- Add `extract_enums(doc_label, enum_sections, records)` (or fold into `extract_entities` signature):
  for each `### Enum: <Name>` block, parse the first non-empty body line as pipe-separated values
  (reuse the `choice of:` splitter — `[v.strip() for v in line.split("|") if v.strip()]`). Record
  one `ExtractionRecord(.../enums/<Name>, EXTRACTED, value="N values")`.
- Value-line form (OQ-PE-5): pipe-separated single line. Empty/`@map` value → `not_extracted`.

### Step 2 — route `## Enums` + cross-doc merge (FR-PE-8)
- `extract.py::_build_graph`: after the entities routing, `find_section(sections, "Enums")`; collect
  its `### Enum:` sub-blocks the same way entities collects `### Entity:` (level + `heading_path[-2]
  == enums_root.title`). Call `extract_enums`; merge `graph.enums.setdefault(name, values)` (later
  docs never override — mirrors the entity merge).

### Step 3 — named-enum reference + raw-cell parse (FR-PE-9, the lowercasing fix)
- `entities.py`: capture the **raw** type cell alongside the lowercased one
  (`raw_type = strip_annotations(row.get("type", ""))`; keep `ftype = raw_type.lower()` for the
  plain-type/`choice of:` matches). Add `_ENUM_REF_RE = re.compile(r"^enum:\s*(\w+)$", re.I)` and
  match it against `raw_type` so the name's case survives.
- On match: `prisma_type = <Name>`; validate `<Name> in graph.enums` — but `graph.enums` is built in
  the same `_build_graph` pass, so validation must run **after** the enum pass. Either (a) order the
  enum pass before the entity pass in `_build_graph`, or (b) defer enum-reference validation to a
  post-pass over the assembled graph. **Choose (a)**: enums have no dependency on entities, so
  extract enums first; entity extraction can then check membership inline.
- Undeclared reference → `not_extracted(enum-undeclared)` with the field path.

### Step 4 — capture inline `choice of:` values (FR-PE-10 part A)
- `DocField`: add `enum_values: Optional[Tuple[str, ...]] = None`.
- `entities.py` choice branch: keep `prisma_type = f"{name}{fname...}"`, **and** set
  `enum_values = tuple(v.strip() for v in choice.group(1).split("|") if v.strip())` (currently
  discarded). Named-enum-referencing fields leave `enum_values=None` (their values live in
  `graph.enums`).

### Step 5 — emit enum blocks (FR-PE-10 part B)
- `prisma_emitter.py`: before the model blocks, collect enums to emit:
  1. named enums from `graph.enums` (name → values), and
  2. per-field synthesized enums from every `DocField.enum_values is not None` (name = its
     `prisma_type`, values = `enum_values`).
  Detect name collisions between the two sets → `UnrenderableField`/flag (OQ-PE-8). Render each as
  `enum <Name> {\n  v1\n  v2\n}` in stable order (named first, alpha; then per-field by
  entity/field declaration order). Prepend the enum blocks to `blocks` before models.
- `models_rendered` unchanged (enums are not models); add `enums_rendered` to `PrismaSchemaResult`
  if useful for the report.

### Step 6 — enum-aware `semantic_diff` (FR-PE-11)
- `prisma_emitter.py::semantic_diff`: after the model comparison, compare `left.enums` vs
  `right.enums`:
  - `set(left.enums) - set(right.enums)` → `enum {name}: emitted, absent from live`
  - reverse → `... in live, not emitted`
  - shared names with differing value tuples → `enum {name}: values {a} (emitted) vs {b} (live)`
    (compare ordered tuples; report the symmetric difference of values for legibility).

### Step 7 — composition + tests (FR-PE-12, acceptance §6)
- Composition is already satisfied by the emitter's existing `@default` path
  (`f"{f.prisma_type} @default({f.default})"`) once `prisma_type` is the enum name — verify, don't
  build. Confirm a named-enum field with `default: discovered` emits
  `status ApplicationStatus @default(discovered)`.
- Tests under `tests/unit/manifest_extraction/`: declaration, multi-field reference, inline value
  capture, mixed emission round-trip, undeclared `not_extracted`, lowercasing-trap regression
  (`enum: ApplicationStatus` keeps its case), enum-aware parity drift, default composition,
  cross-doc merge, name-collision flag.

---

## Risk / sequencing notes
- **Pass ordering** (Step 3) is the one structural change to `_build_graph`: enums must be extracted
  before entity references are validated. Low risk (no reverse dependency).
- **Round-trip safety**: FR-WPI-4 discipline already round-trips the emitted schema through
  `parse_prisma_schema`; emitted enum blocks are covered for free by Step 5 + the existing gate.
- **Parser confirmed** — no `prisma_parser.py` changes needed.
- Touch points are all within `manifest_extraction/` + its tests; no downstream generator changes
  (`generate backend/views` consume the resulting `schema.prisma` unchanged).
