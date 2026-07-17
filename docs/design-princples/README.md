# Design Principles Index

The cross-cutting design principles that govern the **startd8-sdk** (and its ContextCore +
Capability Delivery Pipeline ecosystem). Most are named for a Japanese concept and articulated as
*living guidance* — update the source doc as new instances are found, rather than freezing it.

> **Note on the path:** this directory is spelled `design-princples/` (missing an `i`). The
> misspelling is load-bearing — CLAUDE.md, MEMORY, and many docs link to it — so it is preserved
> rather than renamed.

---

## The core family — "don't discard / don't defer / don't disturb"

Most of the positive principles are refusals to waste something. Read as a set, they form a
coherent stance: value already exists in the pipeline; the failure mode is losing it.

| Principle | One-line stance | Scope |
|-----------|-----------------|-------|
| **[Mottainai](./MOTTAINAI_DESIGN_PRINCIPLE.md)** (もったいない) | Don't discard **artifacts** — forward what an earlier stage already computed instead of regenerating it | within a run |
| **[Kaizen](./KAIZEN_DESIGN_PRINCIPLE.md)** (改善) | Don't discard **lessons** — every run's outcome, good or bad, improves the next | across runs |
| **[Warm Up](./WARM_UP_DESIGN_PRINCIPLE.md)** | Don't discard **context** — disciplined hand-off when the primary LLM toolchain changes and returns | across toolchain transitions |
| **[Hayai](./HAYAI_DESIGN_PRINCIPLE.md)** (早い) | Don't defer **enforcement** — bind quality knowledge at the earliest stage it can be resolved | across pipeline stages |
| **[Sotto](./SOTTO_DESIGN_PRINCIPLE.md)** (そっと) | Don't disturb **what exists** — authored content rides the deterministic skeleton via a hash-exempt, presence-gated seam (byte-identical when absent) | deterministic codegen cascade |

---

## Derivation & determinism

| Principle | One-line stance |
|-----------|-----------------|
| **[Hitsuzen](./HITSUZEN_DESIGN_PRINCIPLE.md)** (必然) | When an output is fully determined by inputs already flowing through the pipeline, **derive it deterministically** instead of paying an LLM to generate it |
| **[Genchi Genbutsu](./GENCHI_GENBUTSU_DESIGN_PRINCIPLE.md)** (現地現物) | Before generating or rebuilding, **find and bind to the real authoritative artifact** — never a template, convention, or inferred default. The discoverability precondition beneath Mottainai |
| **[Ichigo Ichie](./ICHIGO_ICHIE_DESIGN_PRINCIPLE.md)** (一期一会) | Treat every run as the **first and only** encounter — optimizations must improve first-run quality, not just repeat-run familiarity |

---

## Contracts, security & visibility

| Principle | One-line stance |
|-----------|-----------------|
| **[Keiyaku](./KEIYAKU_DESIGN_PRINCIPLE.md)** (契約) | Every agent-to-agent message is a **typed, validated contract** — not unstructured prose the receiver has to trust |
| **[Anzen](./ANZEN_DESIGN_PRINCIPLE.md)** (安全) | **Security by construction** — the pipeline structurally cannot emit known vulnerability classes, the same way it can't emit a service without a dashboard |
| **[Mieruka](./MIERUKA_DESIGN_PRINCIPLE.md)** (見える化) | Make **code structure observable** as first-class telemetry — no step should mutate code it cannot first query. The visibility substrate Kaizen depends on |

---

## Reflection & meta

| Principle | One-line stance |
|-----------|-----------------|
| **[Data Model & Retrospective](./DATA_MODEL_AND_RETROSPECTIVE.md)** | The **two human bookends** — as implementation automates, leverage concentrates at designing the contract (front, the pipeline must never author it) and reflecting on the actuals to feed lessons back (back). Bracket every cascade pass with both |
| **[Hansei](./HANSEI_DESIGN_PRINCIPLE.md)** (反省) | After doing a thing, reflect on the **actuals** (code, logs, diffs — not the plan), extract the process it proved, and spread it (*yokoten*). The reflect-after-doing twin of forward planning |
| **[Personal Conway](./PERSONAL_CONWAY_DESIGN_PRINCIPLE.md)** | *(Meta-principle)* At the solo limit, Conway's Law has no team to average out idiosyncrasy — the software becomes a high-fidelity cast of one mind |

---

## Anti-principles — patterns to *recognize and stop*

| Anti-principle | What to stop doing |
|----------------|--------------------|
| **[Accidental Complexity](./ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md)** | When the machinery built to solve a problem becomes the primary source of failures, the solution has out-grown the problem (Brooks, *No Silver Bullet*) |
| **[Zero Value Precision](./ZERO_VALUE_PRECISION_ANTI_PRINCIPLE.md)** | Refining *how exactly* a system produces something **no user is served by** — precision as the costume of rigor, especially when it blocks value users actually need |

---

## Context correctness cluster (ContextCore lineage)

A distinct set authored under the ContextCore / Force Multiplier Labs line of work — longer design
documents about making context degradation *structurally impossible to do silently*, rather than
single-concept principles.

| Document | Focus |
|----------|-------|
| **[Context Correctness by Construction](./CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)** | Theoretical foundation: a contract system makes silent context degradation impossible without emitting a signal |
| **[Context Correctness by Design](./CONTEXT_CORRECTNESS_BY_DESIGN.md)** | Companion: design-time awareness prevents *design collisions* that no runtime gate can undo |
| **[ContextCore Context Contracts](./ContextCore-context-contracts.md)** | Context-propagation bugs as a distinct bug class (system succeeds, no error, silence) |
| **[Context Propagation](./context-propagation.md)** | Design principle draft — upstream decisions (e.g. domain classification) must reach every downstream phase |
| **[Context Propagation — Session Brief](./context-propagation-session-brief.md)** | Session notes grounding the above (Artisan PI-006→PI-013 domain-classification failure) |

---

## How the principles relate

- **Mieruka → Kaizen → Mottainai** — you cannot improve (Kaizen) what you cannot see (Mieruka); you cannot forward (Mottainai) what you cannot discover (Genchi Genbutsu).
- **Mottainai / Kaizen / Warm Up** are the "anti-waste trilogy" (artifacts / lessons / context).
- **Hayai** is enforcement-timing; **Hitsuzen** is generation-vs-derivation; **Keiyaku** and **Anzen** are structural guarantees; **Sotto** governs the authored-content seam over deterministic output.
- **Data Model & Retrospective** is the human frame the others serve: determinism (Hitsuzen) collapses the middle, pushing human leverage to the two bookends — designing the contract (front) and the retrospective (back, which *is* **Hansei** at the increment boundary, feeding **Kaizen**).
- **Personal Conway** frames why one author's principles cohere at all.

> Maintenance: when you add a new principle doc to this directory, add a row here. When CLAUDE.md's
> `docs/design-princples/` references change, keep this index in sync.
