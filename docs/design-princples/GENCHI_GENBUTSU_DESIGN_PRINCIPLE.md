# Genchi Genbutsu Design Principle

Purpose: establish the **discoverability precondition** beneath Mottainai — before you can forward, preserve, or reuse an authoritative thing, you must be able to *find and bind to the real one*. This document is intentionally living guidance. Update it as new instances are identified.

---

## The Principle

**Genchi Genbutsu** (現地現物) — "go and see the actual thing." The Toyota practice of grounding a decision in the real artifact at its source, not in a report, a proxy, or an assumption.

Applied to the pipeline: **before generating, binding, or rebuilding, resolve the *actual authoritative artifact* and bind to it — never to a template, a convention, an inferred default, or a fresh rebuild.**

Mottainai answers *"has this already been computed — so don't regenerate it."* Genchi Genbutsu answers the prerequisite: *"can the authoritative version be **found**, and am I binding to it or to a proxy?"* You cannot forward what you cannot discover. Genchi Genbutsu is to Mottainai what Mieruka is to Kaizen — the visibility that makes the higher principle physically possible.

---

## Why This Matters

Every recurring accidental-complexity instance in this ecosystem shares one root:

> **An authoritative thing already exists — the target's real metric names, a prior implementation, the human's authored intent, a foreign project's identity boundary — but is invisible at the point of use (un-bound, un-declared, un-scoped, or un-named), so the system re-derives, clobbers, re-implements, or contaminates it.**

The pattern was first named as **Mottainai** in the prime-contractor prompt assembly (Feb 2026): `PrimeContractorWorkflow._generate_code()` had injection slots for all 7 onboarding fields, but *every field was `None` at runtime*, so the DESIGN prompt silently fell back to asking the LLM to re-derive values ContextCore export had already computed. The slot existed; the authoritative artifact was un-discoverable at the point of use. Genchi Genbutsu names *that* failure — the invisibility, not the waste it causes.

---

## The Four Rules

1. **Bind to reality, not convention.** Resolve the target's *actual* metrics / schema / interface and validate against it — not against a structurally-plausible template. Transport-inferred `http_server_duration` is a proxy; the running system's `calls_total{service_name,...}` is the actual thing. Structural validity that passes while the semantic binding is wrong is a Genchi Genbutsu failure. *(Sibling: Hitsuzen — derive the determinable; Context-Correctness-by-Construction — the binding must reach its consumer intact.)*

2. **Respect the boundary you are writing into.** Never inject your own identity, defaults, or paths into an artifact owned by another project or tenant. Source-identity in a foreign sink is taint — the dual of missing context. Go and see *whose* artifact this is before you write to it.

3. **Authored intent is authoritative.** When a human has declared intent, resolve the real authored artifact and merge authored-wins; never rebuild-from-template-and-restore-a-whitelist. A preserve-whitelist silently drops everything it has not yet enumerated — it is Genchi Genbutsu failing one field at a time.

4. **One canonical, *discoverable* name per concept.** A capability un-findable by name (generic `generate_prometheus_rule`, `manifest.py` ×7) will be re-created, because a fresh-context author cannot discover it to reuse it. Distinct, greppable, single-home names are what make Mottainai's "forward, don't regenerate" physically possible for *code symbols*. Record the canonical owner in the terminology registry so the next author lands on one answer. *(This is the Mottainai "Inventory Problem" applied to code, not pipeline artifacts.)*

---

## The Diagnostic Question

> **"Is there already an authoritative version of this — and would the next engineer (or agent) actually find it?"**

If the honest answer is *"it exists, but nobody would find it,"* that is a Genchi Genbutsu violation — and it will become a Mottainai violation the moment someone re-derives it, a divergence bug the moment two copies drift, and a silent-degradation bug the moment the proxy and the real thing disagree.

---

## Relationship to Other Principles

| Principle | Question it answers |
|-----------|---------------------|
| **Genchi Genbutsu** | *Can the authoritative version be found, and am I binding to it or a proxy?* (precondition) |
| **Mottainai** | *Has this already been produced — so forward it, don't regenerate.* (Genchi Genbutsu makes "it" findable) |
| **Mieruka** | *Is the code structure queryable before I mutate it?* (visibility for editing safety) |
| **Hitsuzen** | *Is the output determined by available inputs — so derive, don't LLM-guess.* |
| **Context-Correctness-by-Construction** | *Does required context reach its consumer, tracked and validated?* |
| **Sotto** | *When authored input is absent, is output byte-identical? The feature speaks only when invoked.* |

---

## Instances (baseline — 2026-07-09)

- **Metric binding.** Generator bound to a transport-inferred convention, not the target's real metric surface; validated structurally. → Rule 1.
- **Cross-project taint.** ContextCore injected `contextcore_*`/`startd8_*` metrics, query_templates, and its own capability-index path into foreign exports. → Rule 2.
- **init-from-plan rebuild.** Rebuilt the manifest from a fresh template and dropped authored intent; a growing preserve-whitelist replaced by one authored-wins merge. → Rule 3.
- **Three observability generators.** One concept implemented 3× (startd8 `artifact_generator`, ContextCore `operator.py`, `cli/_generators.py`); generic naming made the existing one un-discoverable. Canonical designated in ContextCore `docs/adr/003`. → Rule 4.
- **This principle system's own Mottainai fork** (ContextCore's copy stale at 274 lines vs the 479-line canonical here) is itself a Rule-4 violation — two copies, the authoritative one un-discoverable from the other.
