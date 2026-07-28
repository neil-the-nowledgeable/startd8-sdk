# Makoto Design Principle

Purpose: establish a cross-cutting invariant for every verdict-emitting surface in the pipeline —
a `PASS`/`FAIL`, `deterministic`/`nondeterministic`, `covered`/`gap` claim must be **read from the
evidence it names**, never asserted from a proxy. This is Genchi Genbutsu enforced *in the code that
reports*, not just in the human who investigates.

This document is intentionally living guidance. Update it as new examples arise.

---

## The Principle

**Makoto** (誠) — "sincerity, truthfulness, integrity." A verdict is a claim about a state. Makoto
requires the claim to be **true to the evidence** for that state — and, when the evidence is absent,
to say *"I don't know"* rather than assert a pass or a fail.

> **No verdict may assert a state without reading the evidence for that state.**
> Absent evidence, the verdict is **inconclusive** — it must never assert the pass *or* the fail.
> And a guard that suppresses a *false* verdict is not a fix that establishes the *true* one.

The second clause is load-bearing: "stopped failing" (a neutral/inconclusive verdict) is not
"verified working" (a positive verdict backed by evidence). Track them separately.

## Why This Matters

Every verdict drifts optimistic until forced to read evidence. A verdict that reports **green when
broken** (or red when fine) is worse than no verdict: it *actively spends* a diagnostic cycle and
erodes trust in the whole surface — once a `PASS` has lied, every `PASS` is suspect. The failure is
never in the *work*; it is in the *report of the work*. Makoto closes the gap between what the code
does and what the code *says it does*.

## The Test

A surface violates Makoto when you can point to a **verdict field with no backing evidence field** —
or a non-neutral verdict whose evidence field is empty. The canonical smells:

- `verdict=nondeterministic; surviving_diffs=0` — asserting a failure with zero diff evidence.
- `result: PASS` while `coverage=0.0` — a verdict that never read the ratio it implies.
- `covered 7/7` while the live system binds `0` — a static claim never checked against reality.

**To comply:** the classifier must consume the artifact/diff/live-series before it emits; if that
input is empty or the harness errored, emit `inconclusive` + capture the raw evidence, never the
assertion. The positive verdict requires positive evidence.

## Relationship to Other Principles

- **[Genchi Genbutsu](./GENCHI_GENBUTSU_DESIGN_PRINCIPLE.md)** (go and see the real artifact) — the human/agent
  discipline. **Makoto is Genchi Genbutsu compiled into the verdict-emitting code**: the *machine* must go and
  see before it reports.
- **[Mieruka](./MIERUKA_DESIGN_PRINCIPLE.md)** (make the true state visible) — Mieruka surfaces the verdict;
  Makoto requires the surfaced verdict to be **evidence-true**, not a hollow green.
- **[Keiyaku](./KEIYAKU_DESIGN_PRINCIPLE.md)** (verifiable contract terms) — a verdict is a claim in the
  contract; Makoto is the clause that it be **independently verifiable against its evidence**.

## Examples (each grounded; the class proved itself ≥4× across two subjects)

| Verdict that lied | Evidence it failed to read | Fix |
|---|---|---|
| `result: PASS` on a `fr_ratio=0.0` run (`passed()` = "ran + deterministic", not "covered") | the coverage ratio | **#204** — verdict rides a loud `⚠ COVERAGE` caveat |
| `nondeterministic; surviving_diffs=0` on byte-identical output | the diff lines (empty ⇒ not nondeterminism) | **#224/D1a** — empty-diff non-pass ⇒ `inconclusive`, never `nondeterministic` |
| `inconclusive` read as "determinism fine" | the harness never ran the scored path | **#224/D1c** — make the harness run + positively emit `deterministic` (guard ≠ fix) |
| static `coverage 7/7 PASS` | the live system bound `0` of the SLIs | **compare-live oracle** — replay generated PromQL against the real system (`EC-GEN-LIVE-BIND-ZERO`) |

Cross-pilot: the Harbor pilot independently filed the determinism case as "Finding D1" — the second
subject hitting the same class is what promoted this from a lesson to a principle.

## Maintenance

Add new violations to the Examples table as they arise; a violation is always a *reporting* defect, not
a work defect. Added to the design-principles index (`README.md`). Detection is cheap — grep verdict-emitting
code for a non-neutral verdict returned on an empty/absent evidence input.
