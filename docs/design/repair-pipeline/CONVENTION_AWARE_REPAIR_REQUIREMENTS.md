# Convention-Aware Repair — Requirements

**Version:** 0.7 (FR-CAR-12 — cure must reach micro-prime + test-gen paths; RUN-038 #5/#4-convention)
**Date:** 2026-06-04
**Status:** Partially implemented — Phase A + Phase B (B.1/B.2/B.3) landed on `main`; **Phase C (FR-CAR-5)
is now PARTIAL** — sub-step **8b** (static convention authority via `convention_guidance`) landed
(`24893fcc`); sub-step **8a** (schema-derived field-set/enum authority) **remains** and is tracked to
completion as **FR-MPF-1** in `../micro-prime/MICRO_PRIME_FIDELITY_REQUIREMENTS.md`. The sibling
classifier change (route convention-strict work off micro-prime — §4 Non-Requirement, FR-CAR-9 "D3") is
owned there too (FR-MPF-2/3/4). Pairs with `CONVENTION_AWARE_REPAIR_PLAN.md` · CRP R1 triaged (Appendix A)
**Aligns with:** `REPAIR_RETRY_ITERATIVE_REQUIREMENTS.md` (the "complete true residual, don't mask" framing),
`POST_GENERATION_REPAIR_PIPELINE_REQUIREMENTS.md`, `MANIFEST_DRIVEN_NAME_REPAIR_*`
**Motivating evidence:** `strtd8/docs/P2_RUN_028_POSTMORTEM.md` (micro-prime emitted Flask-not-FastAPI,
`session.query`, table-from-`app.models`; the build gate caught only the F811 symptom).
**Confirming evidence (RUN-032, 2026-06-03T2358):** the *identical* class recurred and the now-landed
machinery behaved exactly as specified — see §0.5.

---

## 0.5 Implementation status & RUN-032 baseline (NEW in v0.4)

**What has landed on `main`** (since v0.3 was written):

| FR | Phase | Status | Code |
|----|-------|--------|------|
| FR-CAR-0/1/2/3 | Phase A — authority + detection (advisory) | ✅ landed | `repair/convention.py` (`PythonConventionAuthority`, `detect_conventions`), `ConventionDiagnostic` in `repair/models.py` |
| FR-CAR-7 | Phase B.1 — verdict hard-gate | ✅ landed | `forward_manifest_validator.py` convention hard-gate |
| FR-CAR-4 | Phase B.2 — safe fixers + governed-scope guard (**lever 2 "cure"**) | ✅ landed | `repair/steps/python_convention_fix.py` + `repair/routing.py` (`python_convention_error` → `python_convention_fix`) |
| FR-CAR-6 | Phase B.3 — escalate-don't-silence | ✅ landed | `RepairOutcome.unrepaired_diagnostics` + `EscalationHandoff` residual |
| **FR-CAR-5** | **Phase C — adherence reaches micro-prime (lever 1 "prevention")** | 🟡 **partial** | **8b convention authority landed** (`24893fcc`: `convention_guidance` from `repair.convention` threaded via `MicroPrimeContext`/`process_file_with_context`). **8a field-set/enum authority remains** — `micro_prime/` still has **zero** `project_knowledge`/`upstream_interface`/`field_set` refs; the lead-path `gen_context["upstream_interfaces"]` is dropped in `from_prime`. Tracked as **FR-MPF-1**. |

**RUN-032 (`.cap-dev-pipe/.../run-032-20260603T2358`) — score 0.51 PARTIAL, 4/7.** This run *predates*
Phase B.2/B.3, so it is a clean **"before" baseline** for the cure-side work and a **direct demand** for
the prevention-side (FR-CAR-5):

- **The class recurred unchanged.** Every failure is convention/idiom invention on the **micro-prime
  (simple) tier**: `from app.models import JobDescription` (should be `app.tables`); `from sqlalchemy.orm
  import Session` / `session.query(...)` / `import sqlmodel` (should be SQLModel `session.exec(select(...))`).
  Detected as `convention_violations` with `convention_kind` + `expected` + `safe_fixable` — **empirical
  proof FR-CAR-1/3 (Phase A) work in the wild.**
- **The verdict gate fired (FR-CAR-7):** `PI-005` → `FAIL:disk_quality`; the wrong-idiom file cascaded to a
  boot failure that failed **two** features sharing `app/jobs.py` (`PI-001`/`PI-002` → `FAIL:boot`,
  `app.server:app` won't import). Cross-feature boot-cascade is new evidence that **one** un-prevented
  micro-prime file zeroes multiple features — sharpening the FR-CAR-5 priority.
- **The safe-fixer did NOT apply** (`job_export.py` repair header = `import_completion, duplicate_removal,
  extended_lint_fix` — no `python_convention_fix`), because the run predates Phase B.2. Once Phase B.2/B.3
  are exercised on a fresh run, the open question is whether the micro-prime `_run_post_generation_repair`
  path even *invokes* convention detection (CRP R1-S3) — to verify on the next run.
- **The F811 fix held** (`duplicate_definitions: 0`) — the RUN-028 symptom did not recur.

**Net for this update:** requirements already cover both levers with **no conflict** (lever 1 = FR-CAR-5 /
Phase C; lever 2 = FR-CAR-4 / Phase B.2, now landed; both consume FR-CAR-0; OQ-5 + §4 Non-Requirement make
the composition explicit). **FR-CAR-0 has landed (Phase A), so FR-CAR-5's blocking precondition is now
satisfied and Phase C is unblocked.**

---

## 0. Planning Insights (Self-Reflective Update: v0.1 → v0.2)

> The planning pass (3 parallel code explorations) tested v0.1's assumptions against the actual
> `project_knowledge`, repair, escalation, and verdict code. It revealed **6 corrections** — a
> >30% revision, which means v0.1 was premature in exactly the way the loop is meant to catch.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| `project_knowledge` is the source of truth for framework/ORM/module-source house style (FR-CAR-2) | `ProjectKnowledge` (`contractors/project_knowledge/models.py:76`) encodes module-source (`UpstreamInterface`), `Negative` (invented→correct), field-sets, enums, omissions — **but the producer reads only `.ts/.tsx/.js` + `schema.prisma` and `@/`-aliases (TS/Prisma-ONLY), and encodes NO framework/ORM idiom at all.** For a Python project it yields nothing useful. | **NEW FR-CAR-0 (foundational) + FR-CAR-2 reframed:** the Python convention source-of-truth **does not exist yet** and must be built. The deterministic generators (`backend_codegen` renderers) are the de-facto authority; the rule set must be **derived from them** (and the producer extended to Python). |
| Adding a `convention` Diagnostic category is greenfield (FR-CAR-1) | The **`convention` category ALREADY EXISTS** in `repair/routing.py:150` — for C# (`csharp_convention_error` → `csharp_convention_fix`). Convention-repair is an **established pattern**; there's no `ConventionDiagnostic` dataclass yet (C# routes on the category string + a language step). | **FR-CAR-1 narrowed:** *extend* the existing convention category to Python (a `python_convention_fix` step + a `ConventionDiagnostic` subclass), not invent it. De-risks significantly. |
| Detection is greenfield (FR-CAR-3) | `content_contract` detectors already exist: `WrongImportPathDiagnostic` (invented module specifier) + `MisnamedFieldDiagnostic` (invented Prisma field, via `scan_prisma_usage`) (`repair/models.py:128,146`). Module-source/import detection **partly exists**. | **FR-CAR-3 narrowed:** reuse/extend `content_contract` for `module_source`; build only the `framework` / `orm_idiom` / `template_idiom` detectors. |
| Repair can escalate unrepaired diagnostics (FR-CAR-6) | `RepairOutcome` (`repair/models.py:278`) has **no residual field**; `EscalationHandoff` (`micro_prime/models.py:139`) carries prose `failure_message` + repair-step details, **no structured diagnostic payload**; `_run_post_generation_repair` returns a **count** and drops the rest. | **FR-CAR-6 made concrete:** two model changes required — add `unrepaired_diagnostics` to `RepairOutcome`, add a residual payload to `EscalationHandoff` (or a sibling channel) — plus rewiring the post-gen repair to act on them. |
| Convention residue fails the verdict by feeding `semantic_issues` (FR-CAR-7) | `compute_disk_quality_score` (`forward_manifest_validator.py:553`) weights `semantic_penalty` at only **0.2**, and hard-zero applies **only** when `ast_valid=False`. A lint-clean, AST-valid wrong-framework file would still score **~0.8** even with convention errors in `semantic_issues`. | **FR-CAR-7 reframed:** failing a lint-clean wrong file needs a **dedicated convention term / hard-gate** in the score formula — appending to `semantic_issues` is insufficient. |
| Injecting adherence into micro-prime is a prompt tweak (FR-CAR-5) | Clean seam exists (`MicroPrimeContext` → `process_file_with_context` → `process_file`, `micro_prime/context.py:11`, `engine.py:2557`) but **nothing project-knowledge-shaped is threaded**, and `gen_context` doesn't carry `project_knowledge` into `from_prime`. It is also **blocked on FR-CAR-0** (no Python conventions exist to inject). | **FR-CAR-5 sequenced after FR-CAR-0:** add a `MicroPrimeContext` field + thread from `gen_context` (where prime_contractor holds `self._project_knowledge`). Only meaningful once Python conventions exist. |

**Resolved open questions**
- **OQ-1 (source of truth) → none exists for Python; build it (FR-CAR-0).** `project_knowledge` is TS/Prisma-only and framework/ORM-blind. The generators are the de-facto authority → derive the convention rule set from them and extend the producer to Python.
- **OQ-2 (safe-fix vs escalate) → reuse the C# convention-fix precedent.** Deterministic, AST-local, revert-on-break. `module_source`/import rewrites are safe (reuse `content_contract` fixers); wholesale `framework`/`orm` rewrites escalate.
- **OQ-3 (in-run vs post-run) → both, one rule set.** In-run via an extended `EscalationHandoff` (micro-prime element path); post-run via the iterative residual + `RepairOutcome.unrepaired_diagnostics`. Both consume the FR-CAR-0 source.
- **OQ-4 (relationship to existing categories) → extend, don't double-count.** `module_source` reuses `content_contract`; `convention` = framework/ORM/template idiom (new). Must register as a **distinct** category in the verdict, not conflate with `semantic_issues` (FR-CAR-7).
- **OQ-5 (cross-tier) → detect on all tiers; inject preferentially on micro-prime** (weakest adherence, largest validated lift).
- **OQ-6 (symptom-fix linkage) → file-scoped.** `RepairOutcome` is file-granular; flag a residual `convention` diagnostic in the same file as a mechanical fix.
- **OQ-7 (bootstrap corpus) → yes.** RUN-028's rejected `jobs.py` lives under the run's `…/generated/app/jobs.py`; use it as the seed fixture for FR-CAR-3 detectors and FR-CAR-2 parity tests.

### Cross-project evidence (online-boutique-demo) — the pattern is already polyglot

A second exploration (`online-boutique-demo`, the SDK's Go/Java/C#/Node/Python microservices benchmark)
shows **convention-aware repair is NOT Python-greenfield — it already exists per-language**, born from those
runs:
- **C#:** `csharp_convention_fix` / `csharp_namespace_fix` / `csharp_nullable_fix` / `csharp_access_modifier`,
  with a dedicated `("convention", "csharp_convention_error", …)` route (`routing.py:150`).
- **Go:** `go_dot_import_cleanup` / `go_contamination_strip` / `go_unchecked_error`; RUN-120 surfaced
  **package-declaration consistency** as a convention failure (REQ-KZ-GO-606).
- **Java:** `java_missing_override` / `java_raw_type_fix` / `java_import_sort` / `java_duplicate_method`.

**Two consequences for this spec:**
1. **FR-CAR-1 is de-risked further** — `csharp_convention_fix` is a *complete working template* for a
   `python_convention_fix` step; the Python gap is that `backend_codegen` (the newest generator) has **no**
   convention step, only AST/semantic checks.
2. **The existing per-language steps are hand-coded → exactly the drift risk FR-CAR-0/2 exist to kill.**
   `csharp_convention_fix` hardcodes C# rules with no parity tie to a C# generator. So FR-CAR-0's
   **authority + parity** discipline should **retro-cover the existing C#/Go/Java steps too** (FR-CAR-8 is
   not Python-only). Corpus expands: RUN-028 (Python) **+** RUN-120 (Go) **+** the C# convention runs.

### Cross-project evidence (controlled-corpus) — the convention-false-PASS class is already labeled

The Controlled Corpus (`docs/design/controlled-corpus/`, mined from the 37-run online-boutique trove,
5 languages, Claude+Gemini) supplies three things this spec needs:
1. **A two-axis determinism model: structural stability × semantic compliance (req-score)** — *exactly* the
   distinction at the heart of this spec. A convention violation is a failure on the **semantic axis** while
   the **structural axis is clean** (builds/lints fine).
2. **It already labels the class** as `false_pass_risk` (stable build **but** req-score <0.7 → "must stay
   LLM + SCR"). The headline example is **`shoppingassistantservice.py` — the *Flask* RAG, stability 1.0 /
   req 0.5**: a real, cross-run-stable, **wrong-framework** false-PASS. That is independent corroboration of
   the RUN-028 class **and a ready-made fixture** (OQ-7 widens: RUN-028 jobs.py + the corpus `false_pass_risk`
   set, not just one file).
3. **The symptom-fix risk, located precisely (not a corpus defect).** The inventory's *"run-028 class …
   now fixed via the F811 repair 886dccbd"* is **correct in its context** — it is in the *corpus-widening*
   caveat and means the build-FAIL **blocker to accumulating green runs** clears, so the corpus can widen.
   The corpus's **req-score axis already handles the convention defect right** (the Flask RAG stays
   `false_pass_risk` at req 0.5, independent of the F811 fix — the corpus is **not** fooled). The symptom-fix
   trap this spec targets lives **one layer over**, at the **disk-quality verdict** (`compute_disk_quality_score`:
   `ast_valid` + a 0.2-capped semantic penalty), where a now-lint-clean Flask file would wrongly score ~0.8.
   So the corpus is the **proof the two-axis gate works**; FR-CAR-6/7's job is to bring the *verdict* up to
   that standard, not to correct the corpus.

**Implications for the spec:**
- **FR-CAR-7 must align with the two-axis model the corpus already uses** — "structurally clean" must not
  imply PASS at the verdict layer; the convention (semantic-axis) term is the missing factor *there*.
- **FR-CAR-0 consumes/feeds the corpus, but is still net-new for framework/ORM.** `corpus/view.as_project_knowledge()`
  is currently a **boundary shim** (CKG authorities empty); the corpus is the determinism **classifier** +
  fixture source, not yet the framework/ORM authority. The corpus tells you *which* target files are
  `deterministic_candidate` vs `false_pass_risk`; the convention **rules** (FastAPI-not-Flask) are still
  generator-derived (FR-CAR-0). The two compose: corpus = where to look; authority = what's correct.

---

## 1. Problem Statement

We have steadily **expanded the surface we can deterministically generate** — the all-Python backend
(`backend_codegen/`: Pydantic + SQLModel + FastAPI + HTMX), content pages (`pages_generator.py`), and
the CKG knowledge-provider's adherence injection (`contractors/project_knowledge/adherence.py`:
field-set authority + module-path negatives, validated to lift cheap-tier adherence ~0.05–0.40 → ~1.0).
**The repair pipeline has not kept pace.** Repair is purely *mechanical* (syntax / AST / imports / lint /
indentation / duplicates); it does not know the house style those generators encode. RUN-028 made the
gap concrete: micro-prime produced architecturally-wrong-but-valid-Python code that passed **every**
repair gate, and only a top-level F811 tripped the external build gate.

### Gap table — deterministic-generation capability vs. repair coverage

| House-style capability (we generate it) | Encoded in | Present in repair? | Gap |
|---|---|---|---|
| FastAPI routing (`APIRouter`/`Depends`/`HTMLResponse`) | `crud_generator`, `htmx_generator` | ❌ | Flask code is valid Python → passes syntax/AST/lint; never flagged |
| SQLModel access (`session.exec(select(...))`, `session.get`) | `crud_generator` | ❌ | `session.query(X).get(id)` not detected/fixed |
| Table source = `app.tables`; Pydantic `*Schema` = `app.models` | `crud`/`ai_layer` | ⚠️ partial | post-028 `duplicate_removal` drops a dup *import* (886dccbd) but there is **no positive** "import the table from `app.tables`" |
| Jinja2Templates / `TemplateResponse` (the `value_map.py` pattern) | `htmx_generator`, `pages_generator` | ❌ | `render_template(...)` / Flask response tuples not flagged |
| Module-path **authority + negatives**, field-set authority | `project_knowledge/adherence.py` | ⚠️ lead/drafter only | `micro_prime/` has **zero** `project_knowledge` refs → the cheapest tier never receives it |
| **Escalate on unrepairable** | — | ❌ | `prime_adapter._run_post_generation_repair` returns a *count* and continues; diagnostics it can't fix are **dropped**, not escalated |

### Three failure modes (RUN-028)
1. **Convention-blind.** Wrong framework / ORM / module-source is valid Python → every mechanical gate passes.
2. **Adherence bypass.** The validated injection reaches only the lead/drafter path; micro-prime generates
   (and self-repairs) with no house-style knowledge.
3. **Silence-not-escalate, and the symptom-fix trap.** Repair drops what it can't fix; worse, the new
   cross-kind F811 fix (886dccbd) can make a wrong-framework file **lint-clean**, converting a loud FAIL
   into a quiet wrong-but-passing output.

---

## 2. Goal

Make repair **convention-aware**, deriving the house style from the **same source the generators encode**
(no hand-maintained parallel catalog that drifts — the CRP validator-parity lesson), so it can: detect the
convention class, **deterministically fix what is unambiguously safe**, and **route the rest to the true
residual + escalation — never silence it**. Bring each *expanding* deterministic-generation capability into
repair **in lock-step**, so the two never diverge again.

---

## 3. Functional Requirements

### FR-CAR-0 — Python convention source-of-truth (FOUNDATIONAL; NEW in v0.2)
There is **no existing artifact** that encodes the Python house style (framework, ORM idiom,
module-source authority) in a consumable form — `project_knowledge` is TS/Prisma-only and framework/ORM-blind.
Build it: a deterministic **`PythonConventionAuthority`** derived from the **generators themselves** (the
`backend_codegen` renderers are the de-facto truth — e.g. `CANONICAL_LAYOUT` knows tables live in
`app.tables`, the renderers emit FastAPI/SQLModel/`Jinja2Templates`), plus **generator-derived negatives**
(the Python analogue of the seeded TS `Negative`s: Flask→FastAPI, `session.query`→`session.exec(select())`,
table-from-`app.models`→`app.tables`). Extend the `project_knowledge` producer to read `.py` so the same
artifact serves all consumers. **Everything below consumes FR-CAR-0; it is the prerequisite.**
**v0.3 (CRP R1-F1/S1) — split provenance per rule-kind:** `module_source` is **derived from
`CANONICAL_LAYOUT`** (the one genuinely declarative source — clean to consume). `framework`/`orm_idiom`/
`template_idiom` rules come from a **small generator-adjacent declarative manifest** co-located with
`backend_codegen`, **asserted-equal-to-renderer-output by the FR-CAR-2 parity test** — NOT parsed out of the
f-string renderers (parsing Python templates is itself a drift surface). The plan's former fallback (manifest)
is now the **primary** mechanism for idiom rules.

### FR-CAR-1 — `convention` diagnostic category
**v0.2 (narrowed): the `convention` category already exists** (`repair/routing.py:150`, used by C#). Add a
`ConventionDiagnostic` subclass to the taxonomy (`repair/models.py`, alongside `semantic` /
`contract_violation` / `content_contract`) with sub-kinds `framework`, `orm_idiom`, `module_source`,
`template_idiom`, `response_idiom`, carrying the offending span + canonical expectation + `safe_fixable: bool`;
and add **Python routes** to the routing table (the C# convention route is the working precedent to mirror).

### FR-CAR-2 — Single source of convention truth (parity-enforced)
Convention rules MUST derive from the **FR-CAR-0 `PythonConventionAuthority`** (itself derived from the
generators), **not** a hand-maintained parallel list. A **parity test** is required: a file produced by a
generator, then corrupted to violate a convention, MUST be detected by the repair detector. (Mirrors the
content-pages CRP R1-F4/S4 "validator ≡ generator" guard.)
**v0.2 note:** the existing seeded TS `Negative`s (`@/lib/prisma`→`@/lib/db`) are the working *pattern* to
follow, but they are TS-specific — the Python negatives are a new, generator-derived set (FR-CAR-0), not a
reuse of the TS ones.

### FR-CAR-3 — Detect the RUN-028 convention class
The detector MUST flag, at minimum: wrong **framework** (Flask import / `@app.route` / `render_template`
in a FastAPI project), wrong **ORM idiom** (`session.query(...)`, `.query(...).get(...)`), wrong
**module-source** (a SQLModel table imported from `app.models` whose canonical home is `app.tables`),
wrong **response/template idiom** (Flask response tuple; no `TemplateResponse`). Seeded from RUN-028 and
**extensible per run** (the same accretion model as the triage anti-flavor catalog / Gap A–AB).
**v0.2 (narrowed): `module_source` detection partly exists** — `WrongImportPathDiagnostic` +
`MisnamedFieldDiagnostic` (`content_contract`, `repair/models.py:128,146`) already flag invented module
specifiers + Prisma field names; reuse/extend them. Net-new detectors are `framework`, `orm_idiom`,
`template_idiom`. Use the rejected `…/generated/app/jobs.py` from RUN-028 as the seed fixture (OQ-7).

### FR-CAR-4 — Deterministic fixes only where unambiguous; escalate the rest
Where a violation has an **unambiguous, contract-grounded** rewrite, repair it **non-destructively**
(revert on break, per existing step discipline): e.g. `session.query(X).get(id)` → `session.get(X, id)`;
import of a known table from the wrong module → its canonical module (when the symbol's home is known from
the contract); alias normalizations. **Wholesale-wrong implementations** (a Flask app, a hand-rolled CRUD
layer) MUST NOT be auto-rewritten — they **escalate** (FR-CAR-6). The safe-fix vs escalate boundary is a
first-class rule (OQ-2), not an ad-hoc per-step choice.
**v0.3 (CRP R1-F6/S6) — a 5th guard, authority-governed scope:** revert-on-break catches *breakage*, not
*wrongness* (a correct `session.query` in a dual-pattern file like `app/ai/extract.py` compiles after a
rewrite). A safe-fix fires **only when the file is within the authority's governed scope** (generator-owned
artifact kinds per `CANONICAL_LAYOUT`); hand-written integration files (`app/ai/*`) are **detect-and-advise,
never auto-fixed**. Acceptance: the safe-fixer makes **zero** rewrites on `extract.py`.
**v0.3 (CRP R1-F10):** a module-source rewrite MUST first verify the symbol is **not** also legitimately
exported by the original module (revert-on-break won't catch a repointed but still-compiling shadowed import).

### FR-CAR-5 — Adherence reaches the cheapest tier (micro-prime)
The CKG knowledge-provider's **field-set authority + module-path negatives** MUST be available to (a)
**micro-prime's generation prompt** (`micro_prime/engine.py` `_build_*_prompt`) and (b) the convention
detector/fixer. Net: micro-prime both *generates* and *self-repairs* toward the house style. Closes the
"`micro_prime/` has zero `project_knowledge` refs" gap. (Necessary-but-not-sufficient — adherence.py's own
"injection ≠ adherence" guardrail still applies; pairs with FR-CAR-3 detection.)
**v0.2 (sequenced after FR-CAR-0):** the seam is concrete — add a field to `MicroPrimeContext`
(`micro_prime/context.py:11`), thread it from `gen_context` in `from_prime` (prime_contractor already holds
`self._project_knowledge`), and pass it through `process_file_with_context` → `process_file` → the prompt
builders. Today **nothing project-knowledge-shaped crosses that boundary.**
**v0.4 (unblocked):** FR-CAR-0 landed (Phase A, `PythonConventionAuthority` in `repair/convention.py`), so
the blocking precondition is satisfied — Phase C may proceed. Two distinct authorities must reach micro-prime
and they have different readiness: (a) the **schema-derived field-set + enum authority** (already validated
on the lead/drafter path, Python-useful today, *independent of FR-CAR-0*); and (b) the **generator-derived
Python convention authority** (module-source `app.tables` + ORM/framework idiom) from FR-CAR-0. Both render
into the micro-prime generation prompt via the same `MicroPrimeContext` field.
**v0.5 (status correction):** sub-step **8b landed** (`24893fcc`) — `convention_guidance`
(`render_convention_guidance()` from `repair.convention`, the FR-CAR-0 `PythonConventionAuthority`) is now
threaded through `MicroPrimeContext` → `process_file_with_context` (`engine.py:2566-2578`). Sub-step **8a
(schema-derived field-set + enum authority) did NOT land** — it requires forwarding the lead-path
`gen_context["upstream_interfaces"]` (produced by `_collect_upstream_interfaces`,
`prime_contractor.py:4443-4584`), which `from_prime` (`context.py:54-91`) still drops. 8a is specified to
completion — with corrected status, the exact seam, and **measurable** acceptance (field-set block present
in the micro-prime prompt **and** the RUN-011 field-invention class not recurring on SIMPLE) — as
**FR-MPF-1** in `../micro-prime/MICRO_PRIME_FIDELITY_REQUIREMENTS.md`. This avoids re-deriving the seam here
while keeping the CAR record truthful.

### FR-CAR-6 — Escalate, don't silence (the A3 + symptom-fix guard)
Every diagnostic MUST be classified `repaired` / `safe-unfixable-mechanical` / `convention-or-semantic-unfixable`.
Unfixable `convention`/`semantic` diagnostics MUST be **emitted as escalation** — `EscalationHandoff`
(Keiyaku K-6) in-run, the iterative **residual + verdict** post-run — and **never dropped** (today
`_run_post_generation_repair` returns a count and continues). A pass that fixed a **co-located** mechanical
error (e.g. F811) MUST still surface any residual `convention` violation: **fixing a symptom MUST NOT flip
a FAIL to PASS.**
**v0.2 (made concrete): two model changes are required** — (a) add `unrepaired_diagnostics: List[Diagnostic]`
to `RepairOutcome` (`repair/models.py:278`; today the orchestrator drops them), and (b) add a structured
residual payload to `EscalationHandoff` (`micro_prime/models.py:139`; today only a prose `failure_message`).
Then rewire `prime_adapter._run_post_generation_repair` (returns a bare count today) to escalate on the
residual instead of dropping it.
**v0.3 (CRP R1-F2/S2) — unify the residual, don't fork it:** `RepairOutcome.unrepaired_diagnostics`
**IS** the file-granular instance of `REPAIR_RETRY_ITERATIVE`'s "complete true residual" — same
`List[Diagnostic]` type, same honesty invariant — and the iterative driver consumes it rather than re-scanning.
State whether `EscalationHandoff.residual` carries `Diagnostic` objects directly or a documented projection
(don't create a second silent type).
**v0.3 (CRP R1-F3/S5) — these are FROZEN dataclasses:** `EscalationHandoff` and `MicroPrimeContext` are
`@dataclass(frozen=True)` with multiple `from_*` constructors + `to_dict`/`to_prompt_section` consumers, so
new fields are a **breaking contract change** — require defaults + a call-site migration sub-task (same for
`RepairContext.convention_authority`, R1-S10).
**v0.3 (CRP R1-F9/S3) — detection must run WHERE the residual is dropped:** `_run_post_generation_repair`
today runs only `check_syntax`+`check_lint` — it emits **no** `ConventionDiagnostic`s, so without adding a
**convention-detection checkpoint into this path**, `unrepaired_diagnostics` is always convention-empty in the
exact micro-prime path RUN-028 exercises. Detection in `validate_disk_compliance` alone is insufficient.

### FR-CAR-7 — Convention residue is a hard verdict signal
The disk-quality / verdict layer (and the Semantic Compliance Reviewer) MUST treat an **unrepaired
`convention` violation as failing**, even when the file is **lint-clean and AST-valid** (the
wrong-framework-but-clean case). This is the gate-level symptom-fix guard backing FR-CAR-6.
**v0.2 (reframed — feasibility):** appending to `DiskComplianceResult.semantic_issues` is **insufficient** —
`compute_disk_quality_score` (`forward_manifest_validator.py:553`) caps `semantic_penalty` at 0.2 and
hard-zeros only on `ast_valid=False`, so a lint-clean wrong file still scores ~0.8. A **dedicated convention
term** (or a hard-gate: any `error`-severity convention violation → score 0.0, like the `ast_valid` gate) is
required in the formula. Register `convention` as a **distinct** category, not conflated with semantic issues.
This makes the verdict honor the Controlled Corpus's **two-axis** model (structural stability × semantic
compliance): a `false_pass_risk` file — structurally stable but semantically wrong (the Flask RAG, req 0.5) —
MUST score as failing, not ~0.8.
**v0.3 (CRP R1-F8/S4) — use a HARD-GATE, not a weighted 5th term.** The formula sums to 1.0
(contract 0.4 + import 0.2 + stub 0.2 + semantic 0.2); inserting a weighted convention factor re-normalizes
and **destabilizes every existing threshold + the corpus's calibration**. An error-severity convention
violation → score **0.0** (additive, exactly like the existing `ast_valid` gate) leaves convention-clean
scores unchanged.
**v0.3 (CRP R1-F4/S4) — de-dup + state the corpus relationship.** A diagnostic counted as `convention` is
**excluded from `semantic_issues`** for scoring (no double penalty when the same span is both). State the
intended relation to the corpus req-score: the verdict's convention gate is a **cheap deterministic proxy**;
the corpus req-score remains the authoritative semantic-compliance number (they must not silently disagree).

### FR-CAR-8 — Coverage parity with the generators (the lock-step requirement)
As the deterministic generators **expand** (content-pages today; future view / composite generators), the
convention rule set MUST expand **in the same change**: a new owned-artifact kind ships with (a) its
convention rules (FR-CAR-2 source) and (b) a generated-then-corrupted **parity test** (FR-CAR-2). A
generator capability without matching repair coverage is the defect this requirement exists to prevent.
**v0.2 (polyglot scope):** this is **not Python-only.** The existing hand-coded C#/Go/Java convention steps
(`csharp_convention_fix`, `go_dot_import_cleanup`, `java_missing_override`, …) have **no parity tie** to their
generators — they are the drift risk in the present tense.
**v0.3 (CRP R1-F5/S8) — REFRAMED from "rewrite" to "additive coverage, deferred."** The original "bring them
under authority+parity" is a *rewrite of working code with no generator to derive from* — `csharp_convention_fix.py`
(246 lines of hardcoded regex) reads no authority, and rules like namespace-PascalCase have **no C# generator**
to parity-test against (there is no C# equivalent of `backend_codegen`). So: **(a)** authority-derivation
applies **only where a generator exists** (Python today); **(b)** where none exists (C#/Go/Java), require a
**declarative rule manifest + golden-corpus regression test** (assert no behavior change), not a rewrite; **(c)**
the whole polyglot retrofit is **deferred until after the Python proof** (Phases A–C). The lock-step meta-test
must not mis-fire on hand-coded steps that have no generator.

### FR-CAR-9 — Telemetry + Kaizen feedback
Each convention detection / fix / escalation MUST be logged + OTel-metric'd (`category`, `rule`, `tier`,
`outcome=fixed|escalated`) and routed to **Kaizen**, so recurring **per-tier** convention violations (a)
inform the complexity classifier (postmortem A1 / deterministic-first review **D3** — "SIMPLE + strict
house-style → not micro-prime") and (b) become prompt hints. Convention-fix metrics are pipeline-innate
(system-oriented), matching the existing micro-prime repair metrics.

### FR-CAR-10 — Deterministic, reuse-not-rebuild
The detector and safe-fixers are **deterministic, no-LLM**. Reuse the existing
`Diagnostic`/`RepairContext`/`RepairOutcome`/step-routing (`repair/routing.py`)/`EscalationHandoff`
machinery and the iterative loop's residual concept; add only the `convention` category, the
source-of-truth adapter, the safe fixers, and the **escalate-not-drop** wiring. Same tree → same result.

### FR-CAR-11 — Advisory→gating ramp has a numeric precondition (NEW in v0.3, CRP R1-F7/S7)
The advisory→gating flip (Phase A advisory → Phase B FAIL) MUST be governed by a **measured false-positive
threshold**, not a judgment call: an error-severity convention violation may gate the verdict (FR-CAR-7) /
trigger escalation (FR-CAR-6) **only after** the detector demonstrates **FP < X%** over a known-good
in-architecture corpus (N files).

**v0.6 — precondition stated and MET (measurement 2026-06-04):**
- **X = 5%** (the FP ceiling); **N = 19** (the deployed `strtd8/app/` owned FastAPI/SQLModel files —
  hand-maintained, in-house-style → any error-severity convention hit is a false positive), plus the
  lock-step parity corpus (every `render_backend` owned kind), which is FP-free by construction
  (`test_lockstep_all_generated_python_is_convention_clean`).
- **Measured FP = 0%** (0 of 19 governed files flagged). The detector's only hit on a *correct* file was
  `app/ai/extract.py` (one `orm_idiom`) — the **FR-CAR-4-carved bespoke dual-pattern file**, out of the
  gate's governed scope, so not a gating FP. True positives fired correctly on RUN-032's known-wrong
  `job_export.py` (3 hits: `module_source` + 2 `orm_idiom`).
  > *Corpus note:* the Controlled Corpus `false_pass_risk`/`deterministic_candidate` sets are
  > online-boutique (gRPC/Flask/polyglot) — a **different architecture** than the FastAPI/SQLModel
  > house-style this detector encodes, so running it there would measure architecture mismatch, not
  > detector FP. The measurement therefore uses the in-architecture deployed app (the correct known-good
  > set), which is also why the gate ships behind an off-switch for non-canonical projects (generalization
  > gap, tracked separately).
- **0% < 5% → precondition satisfied.** Implemented as the `STARTD8_CONVENTION_GATING` env flag
  (`forward_manifest_validator._convention_gating_enabled`, default **on**); the §4 ramp is the flag —
  set it to `0` to revert to advisory (detect + record, no hard-zero) on architectures where FP is unmeasured.

---

### FR-CAR-12 — The cure must reach micro-prime-generated and test-generated files (NEW in v0.7, RUN-038 #5 + #4-convention)

RUN-038 exposed two coverage holes where prevention (FR-CAR-5) and cure (FR-CAR-4) are *present
but never reach the files that actually fail* — the worst-of-both the postmortem (§2.5) named.

**FR-CAR-12a — Convention cure/escalation reaches the micro-prime repair pipeline.** The routers
`PI-001/002/003` were generated on the micro-prime path (`simple` tier), hard-gated on disk
(`module_source` `from app.models import …`, `safe_fixable=true`), yet `semantic_repairs_applied=0`
— the FR-CAR-4 `python_convention_fix` never ran. Root cause (home-verified): `micro_prime/repair.py`
`_ALL_STEPS` contains `fence_strip`/`import_completion`/… but **no convention step**. This contradicts
**OQ-3** ("convention-repair lives in *both* the micro-prime in-run path and the post-run path"). The
convention safe-fixer **or** the FR-CAR-6 escalate-the-residual path MUST be reachable on the
micro-prime repair pipeline, so a `safe_fixable=true` violation on a micro-prime-generated file is
**either auto-fixed or escalated — never hard-gated *and* silently left unfixed**.

**FR-CAR-12b — Governed scope includes generator-owned app files.** The integration-path
`python_convention_fix._is_governed` restricts the fixer to `backend_codegen` `CANONICAL_LAYOUT`
spine files, **excluding generated app routers** (`app/jobs.py`, `app/job_export.py`) — which the
deterministic generators also own. A `safe_fixable` violation that is hard-gated but
*out-of-governed-scope* is a **requirement gap**, not just a missing fix: the governed scope MUST
cover generator-owned app files, not only the `CANONICAL_LAYOUT` spine.

**FR-CAR-12c — Convention authority reaches the test-generation path.** `convention_guidance`
(FR-CAR-5b/8b) is threaded into the main micro-prime path but **not** into the test-generation path
(`LLMTestGenerator` receives only `semantic_conventions`), so test files carry the same
`module_source`/`orm_idiom` class (RUN-038 §2.2). The field-set/entity-name half of the test gap is
closed by **FR-MPF-7** (`2095457f`); this is the **convention half** — `convention_guidance` MUST
reach the test-generation prompt with the same coverage as the main generation path.

**Acceptance.** (a) A micro-prime-generated file with a `safe_fixable=true module_source` violation
is auto-fixed or escalated — never `semantic_repairs_applied=0` alongside a hard-gate. (b) A generated
test file imports tables from the correct module under the convention authority.

> **RUN-038 diagnostic now standing:** the Forward Deployed Engineer surfaces this exact state on
> every run — a `MECHANISM (sdk, conflict)` claim flags any `safe_fixable=true` violation with
> `semantic_repairs_applied=0` (`fde/sources.py:read_convention_status`). FR-CAR-12 is the fix; the
> FDE claim is the regression tripwire.

---

## 4. Non-Requirements

- **Not** a general semantic code-understanding engine. Convention rules are a **bounded, contract-derived**
  catalog, not arbitrary intent inference.
- **Not** auto-rewriting wholesale-wrong implementations (Flask app → FastAPI app). That is **escalation**
  territory (FR-CAR-6), not deterministic repair.
- **Not** the complexity-classifier change itself (A1 / D3). This doc ensures repair + escalation **cover the
  consequence**; routing convention-strict views away from micro-prime is a sibling change.
- **Not** re-implementing the adherence injection. Reuse `project_knowledge`; FR-CAR-5 only **wires it to new
  consumers** (micro-prime + repair).
- **Not** gating-by-default initially. Advisory → gating ramp (the Semantic Compliance Reviewer posture),
  via an env flag, once false-positive rates are measured.
- **Not** in scope: non-Python convention catalogs beyond what each generator already encodes (extend per
  LanguageProfile as those generators mature).

---

## 5. Open Questions

> **v0.2: all seven were resolved by the planning pass — see §0 "Resolved open questions."** Retained
> below as the record of what was asked (per the reflective-loop discipline: modify, don't delete).

- **OQ-1 — Source of truth.** Which artifact authoritatively encodes framework/ORM/module-source house
  style — `project_knowledge` (CKG), the `LanguageProfile`, or a new shared convention manifest? How much is
  per-project (module-source) vs per-language (framework/ORM)? (FR-CAR-2 hinges on this.)
- **OQ-2 — Safe-fix vs escalate boundary.** Formalize "deterministically rewritable": AST-local + single-symbol
  + contract-grounded? What's the test that keeps a fixer from a destructive rewrite (FR-CAR-4)?
- **OQ-3 — In-run vs post-run homes.** Does convention-repair live in micro-prime's element pipeline
  (`EscalationHandoff` K-6), the post-run iterative loop (residual), the Semantic Compliance Reviewer, or
  all three — and how do they share one rule set without divergence?
- **OQ-4 — Relationship to existing categories.** Extend the existing `semantic` / `contract_violation`
  Diagnostic categories and the in-run `MicroPrimeConfig.semantic_verification_*` (default-on), or add
  `convention` as distinct? Avoid overlap/double-counting with `disk_compliance.semantic_issues`.
- **OQ-5 — Cross-tier scope.** Run convention-repair for **all** tiers, or gate to cheap/micro-prime where
  adherence is weakest (cost)? The CKG data shows the largest lift on the cheapest tier.
- **OQ-6 — Symptom-fix linkage.** How does FR-CAR-6 concretely link a mechanical fix (F811) to a co-located
  convention residue — same file? same element? same import cluster? — to flag "you fixed a symptom" without
  false positives?
- **OQ-7 — Bootstrap corpus.** Is RUN-028's rejected `jobs.py` (and prior run residues) available as the
  seed corpus for the FR-CAR-2 parity tests and FR-CAR-3 detector fixtures?

---

*v0.2 — Post-planning self-reflective update. 1 requirement **added** (FR-CAR-0, foundational: the Python
convention source-of-truth doesn't exist yet); 4 **narrowed** to reuse existing machinery (FR-CAR-1 convention
category already exists for C#; FR-CAR-3 `module_source` partly exists as `content_contract`; FR-CAR-2/5 keyed
to FR-CAR-0); 2 **reframed for feasibility** (FR-CAR-6 needs 2 model fields; FR-CAR-7 needs a dedicated verdict
term, not `semantic_issues`); 7 open questions resolved. Net: the work is mostly **extending established
patterns**, gated on building the Python convention authority first.*

*v0.3 — CRP R1 applied (all 10 F-suggestions accepted; dispositions in Appendix A). Net design changes:
FR-CAR-0 splits provenance (declarative `CANONICAL_LAYOUT` vs a generator-adjacent manifest, not renderer
parsing); FR-CAR-4 adds an authority-scope guard (no auto-fix of hand-written files) + a symbol-shadow check;
FR-CAR-6 unifies the residual with the iterative loop's, flags the frozen-dataclass migration, and requires
convention detection in the post-gen path; FR-CAR-7 chooses a hard-gate over a re-weighting term + de-dups
vs `semantic_issues`; FR-CAR-8 reframed from rewrite→additive/deferred; new FR-CAR-11 (numeric gating gate).*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Split authority provenance: `CANONICAL_LAYOUT` declarative for module-source; manifest for framework/ORM/template, not renderer-parsed | CRP R1 | **Applied** to FR-CAR-0 (v0.3 note). | 2026-06-03 |
| R1-F2 | Unify `RepairOutcome.unrepaired_diagnostics` with the iterative loop's "true residual"; define `EscalationHandoff.residual` type | CRP R1 | **Applied** to FR-CAR-6 (v0.3). | 2026-06-03 |
| R1-F3 | `EscalationHandoff`/`MicroPrimeContext` are frozen — field adds are breaking; need defaults + migration | CRP R1 | **Applied** to FR-CAR-6 (v0.3; also covers `RepairContext.convention_authority`, R1-S10). | 2026-06-03 |
| R1-F4 | De-dup convention vs `semantic_issues`; state relation to corpus req-score | CRP R1 | **Applied** to FR-CAR-7 (v0.3). | 2026-06-03 |
| R1-F5 | Reframe FR-CAR-8 from rewrite → additive/golden-corpus, deferred behind Python proof | CRP R1 | **Applied** to FR-CAR-8 (v0.3) — corrected an overreach. | 2026-06-03 |
| R1-F6 | Add 5th safe-fix guard: authority-governed scope; hand-written files detect-and-advise | CRP R1 | **Applied** to FR-CAR-4 (v0.3); `extract.py` zero-rewrite acceptance. | 2026-06-03 |
| R1-F7 | Numeric advisory→gating FP threshold | CRP R1 | **Applied** as **new FR-CAR-11**. | 2026-06-03 |
| R1-F8 | Hard-gate over a weighted 5th term (preserve the 1.0-sum formula) | CRP R1 | **Applied** to FR-CAR-7 (v0.3). | 2026-06-03 |
| R1-F9 | Wire convention detection into `_run_post_generation_repair`, not just `validate_disk_compliance` | CRP R1 | **Applied** to FR-CAR-6 (v0.3). | 2026-06-03 |
| R1-F10 | Module-source rewrite: verify symbol not also exported by the original module | CRP R1 | **Applied** to FR-CAR-4 (v0.3). | 2026-06-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all 10 R1-F suggestions accepted) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-04 04:05:00 UTC
- **Scope**: Pre-implementation architectural review of v0.2 requirements; weighted to the 6 focus-file asks (FR-CAR-0 authority abstraction, FR-CAR-6 residual composition, FR-CAR-7 verdict double-count, FR-CAR-8 polyglot retrofit, FR-CAR-4 safe-fix boundary, advisory→gating ramp). All findings grounded in code (cited file:line).

##### Focus-file asks (answered first, per template)

**Ask 1 — Is "derive the convention authority from the generators" the right abstraction (vs. extending `project_knowledge`'s producer, vs. a generator-adjacent manifest)?**
- **Summary answer:** Partial — the *intent* (single generator-rooted truth, no hand catalog) is right, but "derive *from* the renderers" is mechanically unclean and should be narrowed to "derive from the generators' declarative inputs, fall back to a generator-adjacent manifest."
- **Rationale:** The renderers encode idioms as Python f-string templates (`backend_codegen` `*_generator.py`), not a declarative form, so a literal "read the renderer to learn FastAPI-not-Flask" requires parsing Python string templates — brittle and itself a drift surface. The one genuinely declarative source the plan already cites is `CANONICAL_LAYOUT` (module-source: tables=`app.tables`), which *is* clean to consume; the framework/ORM idiom is not. The producer (`project_knowledge/producer.py:26` `_TSJS` only, built on `parse_prisma_schema`) is structurally Prisma/TS-shaped and would need a parallel Python path regardless — so "extend the producer" and "new authority" are not really alternatives; both are net-new Python code.
- **Assumptions / conditions:** `CANONICAL_LAYOUT` remains the declarative module-source truth; framework/ORM/template idioms are enumerable (small closed set), not inferred.
- **Suggested improvements:** In FR-CAR-0, split the authority's provenance per rule-kind: module-source = derived from `CANONICAL_LAYOUT` (declarative, parity-testable); framework/ORM/template = a **small generator-adjacent declarative manifest** co-located with `backend_codegen` and asserted-equal-to-renderer-output by the FR-CAR-2 parity test (rather than parsed *out of* the renderer). The plan's own fallback (Risks bullet 1) should be promoted to the primary mechanism for the idiom rules.

**Ask 2 — Does FR-CAR-6's residual compose with the existing iterative "complete true residual" + K-6, or duplicate it?**
- **Summary answer:** Composes in *principle* (same "honest residual, never silence" axiom) but **introduces a second residual data structure** at a different granularity, which is a divergence risk unless explicitly unified.
- **Rationale:** `REPAIR_RETRY_ITERATIVE_REQUIREMENTS.md` FR-7/FR-8 define the residual as a **regen worklist** of deterministic-unrepairable `{file,line,code,message}` tuples surfaced across un-masking passes (NFR-3 "honest residual"). FR-CAR-6 adds `RepairOutcome.unrepaired_diagnostics: List[Diagnostic]` (per-file) and a payload on the frozen `EscalationHandoff` (per-element, in-run) — a *different* shape, consumer (escalation/verdict, not regen), and lifecycle. There is one *concept* (true residual) but the spec is about to materialize it as **two types**.
- **Assumptions / conditions:** Both residuals must reach the same Kaizen/regen sink eventually (FR-CAR-9).
- **Suggested improvements:** Add an explicit FR sentence: `RepairOutcome.unrepaired_diagnostics` **is** the file-granular instance of the iterative loop's "complete true residual" — same list type, same honesty invariant — and the iterative driver consumes it instead of re-scanning. State whether `EscalationHandoff.residual` carries `Diagnostic` objects directly (one type) or a projection (two types, must round-trip). See R1-F2.

**Ask 3 — Does FR-CAR-7's verdict term double-count against `semantic_issues` / the corpus req-score?**
- **Summary answer:** Yes, two double-count hazards exist and neither is currently fenced in the requirement.
- **Rationale:** (a) `compute_disk_quality_score` (`forward_manifest_validator.py:553`) already feeds `semantic_issues` into `semantic_penalty` (0.2 weight); FR-CAR-7 says "register convention as distinct, not conflated" but if a convention violation is *also* emitted as a semantic issue (likely, given `SemanticDiagnostic` exists), it is penalized twice. (b) The corpus already produces an independent req-score; FR-CAR-7 creates a *second* semantic-compliance number in `compute_disk_quality_score` that can disagree with it (§0 even flags this: "are there now two semantic-compliance numbers that can disagree?").
- **Assumptions / conditions:** Convention detection and semantic detection can fire on the same span.
- **Suggested improvements:** FR-CAR-7 should mandate a **de-dup rule** (a diagnostic counted as `convention` is excluded from `semantic_issues` for scoring) and state the **intended relationship to the corpus req-score** (is the verdict's convention gate meant to *predict* req<0.7, or is req-score authoritative and the verdict a cheap proxy?). See R1-F4.

**Ask 4 — Is the FR-CAR-8 polyglot retrofit of working C#/Go/Java steps worth the regression risk?**
- **Summary answer:** Not on day one — defer behind the Python proof; make FR-CAR-8 *additive parity coverage*, not a *rewrite* of the existing steps.
- **Rationale:** `csharp_convention_fix.py` is 246 lines of hardcoded regex (namespace PascalCase, file-scoped namespace, `<Nullable>`) that takes `RepairContext` but **never reads any authority from it** — and several of its rules (PascalCase casing) don't obviously derive from any generator. Forcing it under FR-CAR-0's authority+parity discipline is a rewrite of working code whose rules may have **no generator to be parity-tested against** (there is no C# generator emitting these conventions the way `backend_codegen` does). The drift risk FR-CAR-8 cites is real, but the cure (rewrite) risks regressing runs these steps were *born from* (RUN-120 Go, the C# convention runs).
- **Assumptions / conditions:** The Python authority pattern proves out first (Phases A–C).
- **Suggested improvements:** Reframe FR-CAR-8 so the polyglot retrofit adds a **parity test that asserts the existing hand-coded rules match a per-language generator** *only where such a generator exists*; where no generator exists (C#/Go/Java today), require a **declarative rule manifest + golden-corpus regression test** instead of authority-derivation, and mark the retrofit explicitly *deferred until after the Python proof*. See R1-F5.

**Ask 5 — Is FR-CAR-4's "authority-scoped, AST-local, single-symbol, revert-on-break" tight enough for dual-pattern code (`session.query` and `select` both legal)?**
- **Summary answer:** Necessary but not sufficient — those four guards prevent *destructive* rewrites but not *false* ones; dual-pattern files need a per-file authority opt-out.
- **Rationale:** `app/ai/extract.py` (plan Risks bullet 2) legitimately uses both `session.query` and `select`; "AST-local single-symbol revert-on-break" will still happily rewrite a *correct* `session.query` because the rewrite *compiles* (revert-on-break only catches breakage, not wrongness). The missing guard is **authority scope**: is this file in a region the authority governs?
- **Assumptions / conditions:** The authority can express file/region scope (allowlist or per-module convention applicability).
- **Suggested improvements:** Add to FR-CAR-4 a fifth guard: a safe-fix fires only when the file is within the **authority's governed scope** (e.g. generator-owned artifact kinds per `CANONICAL_LAYOUT`); hand-written integration files like `app/ai/*` are out-of-scope → detect-and-advise, never auto-fix. State the acceptance test on `extract.py` explicitly (no rewrite). See R1-F6.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | FR-CAR-0: split authority provenance per rule-kind — module-source derived from `CANONICAL_LAYOUT` (declarative); framework/ORM/template from a small generator-adjacent declarative manifest asserted equal to renderer output, NOT parsed out of the f-string renderers. | The renderers encode idioms as Python string templates (`backend_codegen/*_generator.py`); literally "deriving from the renderers" parses Python templates — itself a drift surface. The plan already lists this as a fallback (Risks 1); promote it. | FR-CAR-0 body ("derived from the generators themselves") | Parity test: corrupt a generated file per rule-kind; both provenance paths flag it. |
| R1-F2 | Interfaces | high | FR-CAR-6: state explicitly that `RepairOutcome.unrepaired_diagnostics` IS the file-granular instance of `REPAIR_RETRY_ITERATIVE`'s "complete true residual" (same `List[Diagnostic]`, same honesty invariant), and define whether `EscalationHandoff.residual` carries `Diagnostic` objects or a projection. | Verbatim: "add `unrepaired_diagnostics: List[Diagnostic]` to `RepairOutcome` … add a structured residual payload to `EscalationHandoff`". Today there are two residual concepts in two docs at two granularities; without unification they drift. | FR-CAR-6, after the "two model changes" sentence | Test: iterative loop consumes `RepairOutcome.unrepaired_diagnostics` directly (no re-scan); round-trip `EscalationHandoff.residual` ↔ `Diagnostic`. |
| R1-F3 | Interfaces | medium | FR-CAR-6: note that `EscalationHandoff` is `@dataclass(frozen=True)` (`micro_prime/models.py:139`) and `MicroPrimeContext` is `frozen=True` (`context.py:11`) — adding fields touches every `from_*` constructor and is a breaking contract change; specify default values + migration of existing call-sites. | Verbatim: "add a structured residual payload to `EscalationHandoff`". A frozen dataclass field addition without a default breaks all constructors and `to_dict`/`to_prompt_section`; the requirement is silent on this. | FR-CAR-6 v0.2 note | grep for `EscalationHandoff(` / `MicroPrimeContext(` call-sites; all compile with the new field defaulted. |
| R1-F4 | Validation | high | FR-CAR-7: add a de-dup rule (a diagnostic scored as `convention` is excluded from `semantic_issues` scoring) AND state the intended relationship between the new verdict convention-gate and the corpus req-score. | `compute_disk_quality_score:553` already penalizes `semantic_issues` at 0.2; "register distinct, not conflated" doesn't prevent double-penalty if the same span is both. §0 itself asks "two semantic-compliance numbers that can disagree?" — unanswered. | FR-CAR-7, after "Register `convention` as a distinct category" | Test: a file with one convention error scores identically whether or not the same error is also in `semantic_issues` (no double penalty). |
| R1-F5 | Architecture | high | FR-CAR-8: reframe from "bring existing C#/Go/Java steps under authority+parity" (a rewrite) to "add parity/regression coverage; derive-from-generator only where a generator exists; declarative-manifest + golden-corpus elsewhere" and mark the retrofit deferred-until-after-Python-proof. | `csharp_convention_fix.py` (246 lines) is hardcoded regex that reads no authority; rules like namespace-PascalCase have no generator to parity-test against. Forcing authority-derivation risks regressing the very runs these steps were born from. | FR-CAR-8 v0.2 polyglot-scope paragraph | A new parity test passes for Python; C#/Go/Java get a golden-corpus regression test, no behavioral change. |
| R1-F6 | Risks | high | FR-CAR-4: add a 5th safe-fix guard — fire only when the file is within the authority's governed scope (generator-owned artifact kinds); hand-written files (e.g. `app/ai/extract.py`) are detect-and-advise only, never auto-fixed. | "AST-local, single-symbol, revert-on-break" catches *breakage* not *wrongness*; a correct `session.query` in a dual-pattern file compiles after rewrite → false rewrite. | FR-CAR-4, the safe-fix-vs-escalate rule | Acceptance: run safe-fixer on `extract.py` → zero rewrites; on a generator-owned file with `session.query(X).get(id)` → fixed. |
| R1-F7 | Validation | medium | FR-CAR-6/7: define the advisory→gating env flag's *measurement gate* numerically — what false-positive rate over what corpus size flips advisory to FAIL? | Non-Requirements says "Advisory → gating ramp … once false-positive rates are measured" but no threshold is stated; without it the ramp is untestable and the flip is a judgment call. | §4 Non-Requirements (gating-by-default bullet) or a new FR-CAR-11 | Define: e.g. FP < X% on the `false_pass_risk` corpus of N files before any error-severity gate. |
| R1-F8 | Data | medium | FR-CAR-7: specify that adding a convention term to the score formula must NOT silently re-weight the existing four factors (contract 0.4 / import 0.2 / stub 0.2 / semantic 0.2 = 1.0); choose hard-gate (preserves existing scores) over a 5th weighted term (rescales all historical scores). | The formula sums to 1.0; inserting a weighted convention factor forces re-normalization, destabilizing every existing threshold and the corpus's calibrated req-score comparisons. A hard-gate (error-convention → 0.0, like `ast_valid`) is additive and non-destabilizing. | FR-CAR-7, the "dedicated convention term (or a hard-gate)" choice | Regression: existing disk-quality scores on the corpus are unchanged for convention-clean files. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Risks | medium | FR-CAR-3/6: the post-gen path that drops the residual (`prime_adapter._run_post_generation_repair`) only runs **syntax + lint** checkpoints (`check_syntax`/`check_lint`) — it never *generates* `ConventionDiagnostic`s today. FR-CAR-6's "escalate the residual" presupposes a convention-detection stage is wired into *this* checkpoint, not just `validate_disk_compliance`. State where detection runs in the post-gen path. | Without a convention checkpoint here, `unrepaired_diagnostics` will never contain convention items in the micro-prime path the whole spec is motivated by (RUN-028). | FR-CAR-3 or FR-CAR-6, post-run home | Test: a Flask file through `_run_post_generation_repair` yields a `ConventionDiagnostic` in the residual. |
| R1-F10 | Security | low | FR-CAR-4: "import of a known table from the wrong module → its canonical module" can change runtime import semantics if two modules export the same symbol; require the fixer to verify the symbol is NOT also legitimately importable from the original module before rewriting. | A blanket module-source rewrite could repoint a deliberately-shadowed import; revert-on-break won't catch it (both compile). | FR-CAR-4, module-source fixer | Test: a symbol exported from both `app.models` and `app.tables` is not rewritten. |

