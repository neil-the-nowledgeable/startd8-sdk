# Wireframe — Requirements Navigator

**What this is:** every wireframe-capability requirement, rendered so you can **approve the whole
capability at a glance** *and* **drill to a single clause** — using **one visual grammar at every
level** (the same grammar as [`../kickoff/README.md`](../kickoff/README.md)).

> **Role.** The wireframe is the pattern **done right from the start**: every requirement was
> **concept-keyed from line 1** (`FR-W-*`, `FR-WPI-*`) — never a branded title later back-fitted to
> an `FR-`prefix, never a rename-into-a-new-file. Where the kickoff set had to *recover* legibility,
> the wireframe *was born legible*. It is also the kickoff navigator's **Level-4 handoff**: the
> kickoff leaf bottoms out at a requirement's `LIVES` → a real `file:line`, and this is the
> capability that previews **the generated code shape** that leaf will build — where a requirement's
> `LIVES` meets territory.

---

## The grammar (one node, every altitude)

Everything on this page — the whole capability, a section, a concept, a single clause — is the
**same node**, shown at different zoom:

```
<status>  <KEY>  <one-line DOES> ........ <refs/confidence>   ← collapsed (the landscape)
```
expandable to the full card:
```
DOES · WON'T · LIVES (typed) · [SHIPS-WHEN] · KEY · confidence · APPROVE?
```

- **`<status>`** — the metadata encoding: `✅ built + wired` · `🟡 built, thin` · `📄 spec-only`
- **`<KEY>`** — the stable `FR-`prefix. **This is identity** and never changes.
- **`LIVES`** is **typed** — each ref tagged `{code | test | doc}` at a `file:line`.
- **`confidence`** (0–1) is an honest evidence score, not a wish — see the footnote.[^conf]
- **`SHIPS-WHEN`** appears **only when `LIVES` has no code leaf** — the activation gate that
  distinguishes a *parked decision* from a *dormant defect*.

A **section**'s status is the min of its concepts; advertise the lowest open loop — no rounding up.

---

## Level 1 — The landscape (approve at a glance)

*Fly over the whole capability. Grounded 2026-07-16 via `grep -rnE 'FR-W' src/startd8/{wireframe,manifest_extraction}/` + test dirs; number = code mentions, or `spec` where the code leaf is empty.*

**Plan derivation** — the deterministic `WireframePlan` core · `src/startd8/wireframe/plan.py`
```
✅ FR-W1   Derive a structured WireframePlan from the manifests, no gen ........ 6   · 0.9
✅ FR-W2   Deterministic + $0: byte-identical canonical JSON, no LLM .......... 2   · 0.9
✅ FR-W3   Reuse the generators' own manifest parsers (never a fork path) ..... 1   · 0.9
✅ FR-W14  Anti-divergence cross-check: plan paths == emitted paths .......... 2   · 0.9
```
**Planned vs. not-yet-defined** — the five-status machinery · `plan.py`
```
✅ FR-W4   Definition status per section (planned/defaults/placeholder/… ) .... 6   · 0.9
✅ FR-W5   Consequence rendering — app-shape terms, not just input status .... 1   · 0.9
✅ FR-W13  Graceful degradation: bad manifest → `invalid`, plan continues .... 5   · 0.9
```
**Inputs** — assembly-inputs resolution · `src/startd8/wireframe/inputs.py`
```
✅ FR-W6   Assembly-inputs YAML: catalog paths, merge, path-confinement ..... 5   · 0.9
✅ FR-W7   Direct flags fallback — exact generator spellings .............. 3   · 0.9
✅ FR-W8   Convention defaults — five exact filenames, no glob ............ 3   · 0.9
```
**Invocation & output** — CLI + render + persist · `cli_wireframe.py` · `wireframe/render.py`
```
✅ FR-W9   `startd8 wireframe` Rich tree + counts/shape/readiness footer ... 6   · 0.9
✅ FR-W10  `--json` full WireframePlan, `schema_version`'d ................ 3   · 0.9
✅ FR-W11  Opt-in env-gated cap-dev-pipe shim (STARTD8_WIREFRAME=1) ....... shim · 0.9
✅ FR-W12  Persisted artifact + inputs_fingerprint, atomic write ......... 4   · 0.9
```
**Visibility extensions**
```
✅ FR-W15  Content-inputs section (read-only, non-generative) ............. 1   · 0.9   · plan.py:812
✅ FR-W16  Stable public API: build_wireframe_plan / load_assembly_inputs .. 1   · 0.9   · __init__.py:7
```

**Ingestion wiring** — wireframe *downstream of plan ingestion* · `src/startd8/manifest_extraction/`
```
✅ FR-WPI-1   Deterministic manifest-extraction phase → run artifacts ...... code+test · 0.9
✅ FR-WPI-2   Extraction flags non-conformance, never guesses (F1–F6) ...... code+test · 0.9
✅ FR-WPI-3   Extraction report with full value-level traceability ......... code+test · 0.9
✅ FR-WPI-4   Schema-valid by construction (round-trips the parsers) ....... code+test · 0.9
✅ FR-WPI-5   Promotion ratchet: extracted → validated → working .......... code · 0.9
✅ FR-WPI-6   `startd8 wireframe --from-run` run-consumption mode .......... code · 0.9
✅ FR-WPI-7   End-to-end fingerprint linkage (prose→manifest→wireframe) .... code · 0.9
✅ FR-WPI-9   Per-phase delivery inventory (the walkthrough artifact) ...... code · 0.9
🟡 FR-WPI-10  Acceptance gate — HITM-wired, advisory (operator-coordinated) . thin · 0.6
✅ FR-WPI-11  Controlled-corpus alignment (advisory until corpus ships) .... code · 0.9
📄 FR-WPI-8   Greenfield contract *drafting* half (DIFF half built) ........ spec · 0.6
```

**Verdict:** the whole `FR-W1..W16` set is built, wired, and unit-tested — this is the
*counter-example done right*: concept-keyed identity, zero rebrands, zero dormant leaves. The one
genuine open loop is **FR-WPI-8's greenfield-drafting half** (the DIFF half ships today; the
`schema.prisma`-from-prose writer is deferred to P7) and **FR-WPI-10** carries thin code (the shim
ordering) because the gate is deliberately a *human act*, not an exit code.

---

## Level 2 — A concept, previewed

Click into any row and it expands to the full card. The grammar carries **both** a fully-built
concept and a deferred one — `SHIPS-WHEN` appears only for the latter, and `confidence` + typed
`LIVES` appear on both:

```
┌─ FR-W1 · "Wireframe plan model" ─────────────────────────── ✅ built + wired ─┐
│  DOES    Derive a structured `WireframePlan` from the assembly manifests —      │
│          scaffold/containers, services, entities & CRUD, pages, forms (field-   │
│          level), composite views, completeness — WITHOUT invoking the           │
│          generators and WITHOUT writing any application files.                  │
│  WON'T   No LLM call (FR-W2 $0 floor). No generation — never a dry-run of the   │
│          generators. No parallel parser that can drift from the cascade         │
│          (FR-W3 reuses the real parsers; FR-W14 gates it).                      │
│  LIVES   code  src/startd8/wireframe/plan.py:116  (build_wireframe_plan)         │
│          code  src/startd8/wireframe/plan.py:1091 (section assembly)             │
│          test  tests/unit/wireframe/test_plan.py                                │
│          test  tests/unit/wireframe/test_cross_check.py  (FR-W14 anti-drift)     │
│  KEY     FR-W1-*      WAS  — (concept-keyed from line 1; never rebranded)         │
│  confidence  0.90  — code leaf resolves + cross-check test guards it              │
│  APPROVE?  [ does DOES match intent? ] · [ is the $0/no-write floor right? ]     │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ FR-WPI-8 · "Contract drafting (greenfield half)" ── 📄 spec-only · DEFERRED (P7) ─┐
│  DOES    Kickoff-time contract drafting: the extraction phase emits a           │
│          `schema.prisma` *draft* into the run dir (Architect-validated before    │
│          promotion), extending the generated→validated→reused ratchet to the     │
│          contract itself. Rescopes FR-F3's prohibition to the project tree +     │
│          mid-run mutation only.                                                  │
│  WON'T   Never writes the *promoted* contract path from a pipeline stage; the    │
│          VALIDATE hash check stands. Not a mutation — a draft into the run dir.   │
│  LIVES   code  manifest_extraction/prisma_emitter.py  (DIFF half only —          │
│          `render_prisma_schema` / `emit_schema_draft`, `entities.diff_against_   │
│          live`) — the greenfield-from-prose writer has no code leaf yet.          │
│  SHIPS-WHEN  a real greenfield consumer appears (the strtd8 pilot needs only     │
│  (P7)        DIFF mode — its contract already exists, per OQ-4). Deliberately     │
│              deferred to P7; "no Prisma writer exists anywhere" was the planning  │
│              discovery that scoped the cut — a v2, not neglect.                   │
│  KEY     FR-WPI-8-*      WAS  — (concept-keyed; amends FR-F3 by reference)        │
│  confidence  0.60  — DIFF half is code+doc evidence; greenfield half is spec only │
│  APPROVE?  [ is DIFF-only the right v1 cut? ] · [ is P7 the right SHIPS-WHEN? ]    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Node fields exercised

This doc-set is **data point #3** validating the [`../../../../dev-os/NODE-SCHEMA.md`] superset
(after the kickoff navigator and its precedent). Fields that appeared here:

| Field | Exercised? | Evidence in this doc |
|---|---|---|
| `status` glyph | ✅ | all three values used (`✅` FR-W1, `🟡` FR-WPI-10, `📄` FR-WPI-8) |
| `does` | ✅ | every row + both cards |
| `wont` | ✅ | both Level-2 cards carry an explicit WON'T floor |
| `lives` (**typed**) | ✅ | `{code, test, doc}` tags at `file:line` — FR-W1 shows code+test, FR-WPI-8 shows a partial (DIFF-only) code leaf |
| `ships_when` | ✅ | FR-WPI-8 (empty code leaf ⇒ gate present, keyed to P7) |
| `confidence` | ✅ | 0.9 built-with-code+test · 0.6 degraded/spec-only — the honest heuristic below |
| `key` / `was` | ✅ | every KEY is concept-keyed with an empty `WAS` — the *no-rebrand* payload this doc proves |

**The data-point-3 payload:** the schema's superset survives a doc-set where **`WAS` is
uniformly empty** — proving the grammar renders a *born-legible* capability as cleanly as it renders
a *recovered* one (kickoff), and that `confidence` + typed `lives` degrade gracefully on a
partially-built concept (FR-WPI-8) without inventing a false leaf.

[^conf]: **Confidence heuristic (honest, not aspirational):** `0.9` = a resolving code leaf **and**
a test found; `0.6` = doc/plan evidence or a *partial* code leaf only (built-but-thin, or one half
of a two-half concept deferred); `0.4` = pure spec, no code anywhere. Every FR-W* here scored 0.9
(code + `tests/unit/wireframe/*`). FR-WPI-8 and FR-WPI-10 scored 0.6 — the first because only its
DIFF half is coded (greenfield draft deferred to P7), the second because the gate is intentionally a
human act with only shim-ordering code behind it. No FR in this set scored 0.4 — the capability has
no pure-vapor requirement.

---

## For new wireframe docs

1. Declare the **`FR-`prefix first**, before the title — as this whole set did. Prefix = identity.
2. Write **DOES / WON'T / LIVES** before the full spec. If the code leaf will be empty, add
   **SHIPS-WHEN** *and* score `confidence` ≤ 0.6 — a deferred requirement without a gate reads as a
   defect.
3. Tag every `LIVES` ref `{code | test | doc}` at a `file:line`. A concept with a `doc`-only
   `LIVES` is spec-only no matter how confident the prose sounds.
4. A rebrand = version bump + alias note in the body. **Never a new file** — this set never needed
   one, which is exactly why it's the pattern to copy.
