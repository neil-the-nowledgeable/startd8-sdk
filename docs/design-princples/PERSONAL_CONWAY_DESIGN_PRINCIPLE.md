# Personal Conway — The Cast of the Mind

**Status:** Living guidance (meta-principle).
**Lineage:** Conway's Law (Melvin Conway, 1967) as amplified by Fred Brooks
(*The Mythical Man-Month* — conceptual integrity; *No Silver Bullet*).

---

## The Principle

> A system's structure is a cast of the organization that built it.
> **When the organization is one person, the cast has no team to average out
> its idiosyncrasy — so the software becomes a high-fidelity impression of a
> single cognitive culture.**

Conway's Law says the software mirrors the *communication structure* of its
makers. At the solo limit there is no communication structure to mirror — only a
mind. The system therefore mirrors the **cognitive culture of that mind**: its
strengths *and* its characteristic failure modes, stamped in without dilution.

The practical payload is not "this is a flaw." It is: **your cast-signature is
predictable, therefore catchable by construction.** Map the signature; build the
scaffolding that closes the loops it habitually leaves open.

## Why This Matters

Every other principle in this registry is a *counterweight* to a specific cast
failure. Mottainai counters loops-opened-then-abandoned (dormant value paths).
Genchi Genbutsu counters assert-from-memory. Accidental-Complexity counters
build-a-framework-for-the-framework. Single-source counters parallel-threads-drift.
They keep recurring because the cast keeps producing the same shapes. Naming the
cast explains *why the counterweights exist* and lets you deploy them before the
failure, not after.

## The cast-signature (this maker's — observed, strength ↔ shadow)

Authored candidly. The origin of this signature is an **AuDHD** cognitive style —
named here as the honest *source*, not as a subject or a deficit. The strengths
below are inseparable from the shadows; you do not get one without risking the
other.

| Strength (the gift) | Shadow (the predictable failure) |
|---|---|
| **Systematizing** — builds coherent, principled systems | **Over-formalization** — a framework for the frameworks (a *requirements-engineering OS*); accidental complexity |
| **Pattern-recognition** — sees the archetype behind the instances | **Premature generalization** — abstracting from one example ("framework-for-one") |
| **Holistic / expansive ambition** — genuine range, whole-system vision | **Sprawl that outruns its own inventory** — the map is always a floor, never the territory |
| **Hyperfocus depth** — 800-line protocols, exhaustive specs | **Loops opened faster than closed** — dormant value paths, drift, unfinished wiring |
| **Parallel threads** — many live fronts at once | **Duplication of single-sources** — worktree/branch multiplication; two of the "one" index |

## The Diagnostic Question

> **"Is this structure a requirement of the problem — or an impression of how I
> think?"**

And the sharper follow-up, naming the known failures:

> **"Which of my four cast-failures is this an instance of — dormant path, drift,
> sprawl, or over-abstraction?"**

If you can name it, the counterweight principle is already written.

## The Four Practices

1. **Name the signature.** Own the tendency. It is a cast to *map*, not a fault
   to shame. Un-named, it operates invisibly; named, it becomes a checklist.
2. **Externalize executive function.** Build the scaffolding that closes loops
   the mind opens faster than it closes them — indexes, single-source registries,
   Mottainai/dormant-path audits, the dismissal-audit, provenance trackers. These
   are prosthetic working-memory, and they are *the right adaptation*, not a crutch.
3. **Prefer closing a loop to opening one.** The single discipline that most
   counters the signature. Before starting the next system, wire the last one in.
4. **Detection over prevention.** You will not stop the tendency — it is the same
   faculty that produces the range. Get *better at catching it*. (Demonstrably,
   you have: the corpus index, the sweep-was-a-floor correction, the
   dormant-path finding — the detection loop is tightening.)

## Relationship to Other Principles

This is the **meta-principle**: it explains the *why* beneath the others.
- **Mottainai / dormant-value-paths** → the "loops opened, not closed" shadow.
- **Genchi Genbutsu** → the "map is a floor" shadow (ground before you assert scope).
- **Accidental-Complexity anti-principle** → the "over-formalization" shadow.
- **Single-source-of-truth** → the "duplicated-single-source" shadow.

The RE-OS, the CORPUS-INDEX, and the dismissal-audit are not just tools — they are
**instruments of externalized executive function**, purpose-built for this cast.

## Instances (grounded — this corpus, 2026-07)

- **`src/startd8/corpus/provider.py`** — the Controlled-Corpus deterministic
  provider: built, tested, and *explicitly not wired into the live drafter*
  ("FR-7 is phased"). A dormant value path — the signature, in its own oracle.
- **`implementation_engine/budget.py::enforce_prompt_budget`** — an 86-line
  budget enforcer, exported and tested, **never called by the drafter** it was
  built for. Dormant path.
- **Two `PIPELINE_REQUIREMENTS_INDEX.md`** (210 vs 263 reqs) — a "single" source,
  drifted into two.
- **Worktree multiplication** — the corpus looked 3–4× its true size because one
  repo appears as eight.
- **The dev-only corpus sweep was a floor** — ~1,000 genuine RE docs lived
  outside it; the map under-counted the territory.
- **The RE-OS itself** — a requirements-engineering operating system: the
  systematizing gift at full expression, carrying (in its own R1) the exact
  over-abstraction risk this principle names. Strength and shadow, same artifact.

---

*The goal is not a different mind. It is a mind that has built itself the right
scaffolding — so the cast keeps its range, and the loops still close.*
