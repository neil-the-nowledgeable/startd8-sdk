# Source-Bound Extraction — Spike Charter

**Version:** 1.0
**Date:** 2026-06-07
**Status:** ✅ COMPLETE — converges. See `SOURCE_BOUND_EXTRACTION_SPIKE_FINDINGS.md` (2026-06-08).
**Time box:** 1 focused day (~4–6 hrs). Stop at the box whether or not it converges; the writeup is the deliverable.
**Owner:** SDK
**Probe target:** strtd8's live FR-3 `extract` pass + its real fixtures
**North-star (deferred, do NOT build):** `GENERATED_IMPORT_PATH_REQUIREMENTS.md` — the full
generated-import / import-template generalization. This spike validates the **mechanical core only**
(FR-IMP-2/4/5); the `imports.yaml` grammar, `from_json` owned-kind, and import surface (FR-IMP-1/3/6)
wait for a **second consumer** per the rule-of-three.

---

## 0. Why a spike, not a build

The full import-path requirements doc is a **one-consumer generalization**. Its consumer (strtd8
content-import) ships FR-13 + FR-15 **today** on the existing `generate backend` cascade ($0), and
even offers an owned-glue fallback for FR-14 — so almost nothing in that doc is *blocking*. Building
a 7th manifest + authoring-contract §2.8 + a new owned-kind for one import declaration is the
speculative abstraction the second-consumer rule exists to prevent.

**But one thing in it is not speculative — it's a latent correctness bug in a shipped generator.**
Re-running any text-mode AI pass on a `name`-less entity **appends duplicates**, because `_persist`
dedups by `name` only (`ai_layer.py:392–395`) and the harness has no source to scope by
(`ai_layer.py:452`). That bites any app that re-extracts, consumer-requested or not. This spike
isolates **whether the fix is small and clean** before anyone commits the grammar around it.

---

## 1. The spike question (the one thing we're learning)

> **Can FR-14-class "idempotent-by-source, provenance-stamped" extraction be delivered by a small,
> isolated change to `_persist` + `_render_pass_text` alone — a declarable identity key, a
> source-bound signature, and a deterministic stamp — *without* touching `render_export`, the
> manifest extractors, or `render_edge_schemas`, and with unbound passes generating byte-identical
> code? Proven against strtd8's real `extract` pass and `extract-paste.private.json`.**

A clean YES → promote to a **narrow** requirements doc (FR-IMP-2/4/5 only) and let consumer #2 pull
the grammar into existence. A NO (it bleeds into the edge-schema generator / manifest extraction /
router, or the dedup SQL doesn't generalize) → we learned the real shape at spike cost, and the
consumer takes the owned-glue fallback while we redesign.

---

## 2. Concrete starting point (the repro)

1. The shipped behavior to break: in a scratch generated app with a `name`-less entity (or
   ProofPoint), run a text-mode pass twice on the same input → observe **duplicate rows**. That is
   the bug; the spike's acceptance test is its negation.
2. Probe fixtures (strtd8, already real-scale): `tests/fixtures/extract-paste.private.json`
   (27 paste cases + one multi-accomplishment résumé) and `tests/fixtures/import-roundtrip.private.json`.
   Test user **Neil** is the import-volume lens.
3. The live pass: strtd8's FR-3 `extract` (`ai_passes.yaml`), text mode, writes ProofPoint.

---

## 3. Scope fence

**In scope (the mechanical core):**
- **H1 — declarable identity key** in `_persist` (`ai_layer.py:384–404`): `id` | `<field>` |
  `[<f1>,<f2>]` | `source:<field>` | `none`, defaulting to today's name-dedup.
- **H2 — source-bound signature** in `_render_pass_text` (`ai_layer.py:429–472`): emit
  `def <pass>(text, session, source_id=…)` behind a declared marker; unbound branch unchanged.
- **H3 — deterministic provenance stamp** in `_persist`: stamp a declared field from the binding
  context; combined with the **existing** `human_inputs.yaml` edge-omission (no generator change),
  the field is non-null and never AI-authored.

**Out of scope (defer to the north-star, do NOT touch in the spike):**
- `imports.yaml` manifest + authoring-contract §2.8 grammar + a `manifest_extraction` extractor.
- `from_json` round-trip import owned-kind (`render_export` stays untouched).
- import surface / UI (FR-IMP-6).
- Production-merging. **The branch is throwaway by default** — its job is the answer, not the code.

**Declaration is intentionally minimal/throwaway.** The spike does NOT design how a project declares
the binding. Use the cheapest stand-in — a hardcoded source binding in the scratch pass, or a single
ad-hoc `source_binding:` key hand-added to `ai_passes.yaml`. How it's *authored* is the north-star's
job; the spike only proves the *mechanism* behind it.

---

## 4. Hypotheses → probes → what would falsify each

| # | Hypothesis | Probe | Falsified if |
|---|-----------|-------|--------------|
| **H1** | A declarable identity key fits in `_persist` (~15–25 LOC) and generalizes across `id` / field / composite / source-scope / none. | Add the key param; exercise each variant on the scratch entity. | Composite or source-scope dedup needs per-entity query logic that won't generalize, or back-compat name-default regresses an existing pass. |
| **H2** | `_render_pass_text` emits the `source_id=…` variant behind a flag; the **unbound** branch is **byte-identical** to today. | Diff generated `app/ai/<pass>.py` for an unbound pass before/after. | Any byte drift for unbound passes (regression risk to every shipped app), or the renderer can't cleanly fork the two shapes. |
| **H3** | `_persist` stamps the declared provenance field; existing edge-omission keeps it AI-invisible. | Run the bound pass; assert field non-null == source id; assert field absent from the edge model (existing `test_edge_privacy`). | Stamping requires a change to `render_edge_schemas` or the manifest extractors → it's bigger than a spike. |
| **H-INT** | The bound signature threads cleanly through the **AI router** (`render_ai_routes`, ~`ai_layer.py:552`), which today passes `body.{request_field}`. | Trace how `source_id` reaches the route handler. | The route generator needs structural changes to thread `source_id` (e.g. a new request field) → flag as a real integration cost, may widen scope. |

> **H-INT is the most likely surprise.** The text-mode route handler is generated too; a third
> parameter has to come from *somewhere* in the request. If that forces router-generator work, the
> "isolated to `_persist` + `_render_pass_text`" thesis is wrong — which is exactly what the spike
> exists to find out before committing.

---

## 5. Success criteria (the acceptance the spike must hit)

The spike **converges** (clean YES) iff **all** hold:

- [ ] **Idempotency line passes** on strtd8's real pass: running `extract` on a stored source twice
      leaves the count of that source's **unconfirmed** rows **stable**, and **never modifies a
      confirmed** row. (The negation of the §2 repro.)
- [ ] **Provenance holds:** every written row's declared field `== source_id`, `source="ai"`,
      `confirmed=false`; the field is **absent** from the edge model.
- [ ] **Isolation holds:** changes live in `_persist` + `_render_pass_text` only. No diff to
      `render_export`, `render_edge_schemas`, or `manifest_extraction/*`.
- [ ] **No regression:** unbound passes generate byte-identical code; the existing AI-layer test
      suite (edge-privacy, pass-provenance, keyless-boot, cost-logging) stays green.
- [ ] **H-INT resolved:** the source-bound route either threads `source_id` with no router-generator
      change, or the required change is **measured and written down** (LOC + which generator).

Any unchecked box at the time box = **does NOT converge** → §6 abort path.

---

## 6. Decision this spike feeds

| Outcome | Next step |
|---------|-----------|
| **Converges** (all of §5) | Promote to a **narrow** requirements doc — FR-IMP-2/4/5 only, isolation as a constraint. Implement as a real (small) change. Leave FR-IMP-1/3/6 in the north-star, untriggered. |
| **Converges except H-INT** (router work needed) | Promote, but fold the measured router-generator cost into the narrow doc as an explicit FR. |
| **Does NOT converge** (bleeds into edge-schema / extraction, or dedup won't generalize) | Do **not** build. Consumer takes the **owned-glue fallback** (strtd8 FR-14's stated plan B); the redesign waits for a second consumer to justify the larger shape. Record the failing shape in the findings. |

---

## 7. Deliverable

A **findings writeup** (`SOURCE_BOUND_EXTRACTION_SPIKE_FINDINGS.md`) that answers §1 in one
paragraph, checks off §5, resolves H-INT, and selects a §6 row — plus the throwaway branch/patch as
evidence. **The code may be discarded; the answer is the artifact.** No production merge from the
spike itself.

---

*Spike charter v1.0 — scoped to the mechanical core (FR-IMP-2/4/5) of the deferred import-path
generalization. Validates a latent shipped-generator correctness bug's fix in isolation before any
grammar is committed. Time-boxed to one day; the writeup, not the code, is the deliverable.*
