# Zero Value Precision (Anti-Principle)

Purpose: name a specific, insidious failure mode of agent-assisted development — pouring effort into the *precision* of something that serves no user, while that very effort blocks the capabilities users actually need. This is an **anti-principle**: a pattern to recognize and stop, not one to apply.

This document is living guidance. Update it as new instances are observed.

---

## The Anti-Principle

**Zero Value Precision** — refining how *exactly* a system can produce something, when **no user is served by that exactness**.

Precision is not a virtue in itself. It is a virtue *in service of a beneficiary*. Effort spent making a capability more precise — more accurate, more complete, more faithfully generated — is only worth what that precision is worth to someone who will use it. When the answer to "who is served by this precision?" is *no one*, the work is not rigor. It is waste wearing the costume of rigor.

The anti-principle has a sharper, more dangerous form: **zero value precision that also blocks positive value.** When the precision work sits *upstream* of the capabilities a user needs — when "let's get the generation exactly right" displaces "let's let the user do the thing at all" — the cost is not merely the wasted effort. It is the user-facing value that never ships because attention was spent perfecting a means instead of delivering an end.

---

## The Observed Problem

On 2026-06-03, an agent and human were building a local-first value-articulation app (a candidate's Profile + ProofPoints enriched into a value model, exported as Markdown/JSON).

The agent spent a long, focused arc of work on the **AI enrichment layer**: retargeting tests for the generated passes, fixing a datetime-coercion bug in the generated `_persist`, regenerating the layer, then chasing a "linking gap" — the value-map join tables were empty, so the AI-suggested entities had no edges. The agent began designing a linker to *reconstruct* those relationships, and was about to make a **second LLM call** to recover structure a first call had already discarded.

Each step was locally defensible. Tests should pass; bugs should be fixed; a gap is a gap. The precision being sought was real precision — "can we make the generator produce the value model, with correct links, exactly right."

Then the human stopped it: *"I didn't even have a sense we were working on this. It's low-value validation at best, and it's blocking the very user capabilities. The precision we were seeking together served no one."*

A single check exposed it. The **deterministic, $0-LLM capabilities that the user's core journey actually depends on did not exist or were not reachable:**

| Capability the user needs | Reality found |
|---|---|
| Export the value model (the payoff) | Formatter functions existed; **no collector, no route** — a user could not export at all |
| See the value map | **No view existed** — only raw per-entity lists |
| See completeness / guidance | Function existed but was **wired to nothing** |

The app could *generate* a value model with ever-increasing precision and a user still could not get anything out of it. The agent had been polishing the engine of a car that could not be driven — and the human, agreeing step by step under decision-fatigue, had not noticed where the effort was going until it had consumed a great deal of it.

The fix, once seen, was small and deterministic: a ~15-line collector and two download routes. Hours of generation-precision work would not have moved the user one inch closer to the thing those routes delivered in minutes.

---

## Why It Is Insidious

Zero value precision is hard to catch *from the inside* for three compounding reasons:

1. **It wears the costume of rigor.** Fixing a bug, making a test pass, closing a gap, improving accuracy — these are unambiguously "good engineering." The local signal is always positive. Nothing in the act of refining precision tells you the precision has no beneficiary.

2. **It is invisible to the person it is supposedly for.** The human in this session did not realize the work was happening on that path — it never surfaced as "we are now spending our budget on generation precision instead of user capabilities." Drift toward precision does not announce itself; it accretes one reasonable step at a time.

3. **Agreement under fatigue is not a check.** A human saying "yes, proceed" to each step is not validating that the *arc* serves a user. After enough yes/no exchanges, agreement becomes the path of least resistance. **The human's "yes" is signal about the next step, not about the direction.** An agent that treats accumulated agreement as a mandate will drive confidently in the wrong direction.

The result: the most expensive waste is not the obviously-bad idea (those get caught). It is the *locally-excellent* work, agreed to in good faith, pointed at a beneficiary who does not exist.

---

## The Tell

The diagnostic question is not "is this precise?" or "is this correct?" — those will read green. The question is:

> **Who is served by this precision, and is it standing between the user and a capability they could already be using?**

Two answers indicate zero value precision:

- **No one is served.** The exactness improves a property no user perceives or depends on.
- **The user serves themselves.** The thing being precisely generated is something the user authors at runtime anyway (see below) — so the generation is racing the user to do their own job.

If either holds — *and especially* if the work sits upstream of an unshipped user capability — stop. The precision is zero value.

### The most common source: racing the user to author their own structure

The linking gap in the observed session was an instance of a recurring trap: **building machinery to reconstruct structure that the user authors themselves, click by click, at runtime.**

The dependency graph of a value model (which capability ties to which outcome to which proof) is not a thing the system must compute. It is *determined by the user* through the natural sequence of their entry — from a proof point, they add the capability it shows; from that capability, the outcome it drives. The edges are **worn into being by the user's own traversal**, like a desire path across grass. A "missing edge" seen in a flat/batch view is not missing — it is grass that has not been walked yet.

Spending precision — least of all LLM precision — to *infer* that structure is paving a walkway through grass no one crosses, while the real path forms elsewhere. The correct design move is to place the entry points *along the route the user already walks*, so the structure is created by the step itself, deterministically, by the human, for free.

> Heuristic: **if the user authors it by using the product, generating it ahead of them is zero value precision.**

---

## Operating Rules

For agents and humans, before and during precision work:

1. **Name the beneficiary first.** Before refining anything, state who is served by the increased precision and what capability it unblocks for them. If you cannot name one, you are likely in zero value precision.
2. **Walk the user's journey end-to-end before deepening any leg of it.** A leg being imperfect is not a reason to perfect it if a *later* leg does not exist at all. Reachability beats refinement. Ship the thinnest end-to-end path first.
3. **Treat "the generation isn't precise enough yet" as a yellow flag, not a goal.** Ask whether the user needs that precision now, or whether a deterministic, lower-precision, *reachable* version delivers the value today.
4. **Make the arc visible to the human, not just the next step.** Periodically surface *where the budget is going* ("we are now N steps into generation precision; the export/value-map/completeness capabilities are still unreachable"). Do not rely on step-by-step agreement to imply directional consent.
5. **Defer generation-precision to the SDK/tooling only after the capability is proven.** Perfecting *how* something is generated, before a user has used *what* it generates, is the anti-principle at one remove.

---

## Anti-Patterns

| Anti-Pattern | Why it is Zero Value Precision | Resolution |
|---|---|---|
| **"Close the gap because it's a gap"** | A gap in a flat view may be value the user authors at runtime, or precision no one needs | Ask who is served by closing it before closing it |
| **Perfecting generation before the capability is reachable** | The user cannot use what they cannot reach, however precisely it is generated | Wire the capability end-to-end first; refine generation later |
| **A second pass to recover discarded context** | Re-deriving (especially via LLM) what an earlier step already knew is precision spent to undo your own loss | Preserve the context in the first pass, or don't discard it |
| **Treating accumulated "yes" as directional consent** | Agreement under fatigue is about steps, not the arc | Surface the arc; ask "is this still the right thing to be doing?" |
| **Racing the user to author their own structure** | The user wears the desire path by using the product; inferring it ahead is paving empty grass | Put entry points on the user's route; let the step create the structure |
| **Build-gating on precision metrics with no beneficiary** | A green "accuracy improved" with no user who depends on that accuracy is a vanity gate | Gate on a user-reachable capability, not an internal precision number |

---

## Relationship to Other Principles

| Principle | Focus | Interaction with Zero Value Precision |
|---|---|---|
| **Accidental Complexity (anti)** | Complexity that solves no real problem | Sibling. Accidental complexity is *structure* with no beneficiary; zero value precision is *refinement effort* with no beneficiary. Both are locally-justified waste |
| **Mottainai** | Don't waste artifacts/computed work | Mottainai prevents discarding value already produced. Zero Value Precision prevents *producing* value no one will consume — the inverse waste |
| **Mujō** | Knowledge dies with the session | Mujō explains *why* the human couldn't see the drift (the agent's context is ephemeral; the arc isn't durably visible). Surfacing the arc (Operating Rule 4) is a Mujō mitigation |
| **Hitsuzen** (inevitability) | Build what the design makes necessary | The counter-test: zero value precision builds what the design makes *possible* but no user makes *necessary* |
| **Kaizen** | Continuous improvement | Kaizen improves what matters. Zero Value Precision is Kaizen pointed at a metric with no beneficiary — improvement that improves nothing for anyone |

**Positive counterpart:** *reachability before refinement.* The thinnest end-to-end path a user can actually walk is worth more than any leg of it perfected in isolation.

---

## Success Criteria

| Criterion | Test |
|---|---|
| Every precision/refinement task names a served beneficiary and an unblocked capability | Before the work starts, the beneficiary is stated; if none, the task is reclassified or dropped |
| No capability is refined while an upstream capability in the same journey is unreachable | Walk the journey; assert each leg is reachable before any leg is deepened |
| The human can see where effort is going at the arc level, not just per step | The agent periodically reports budget-by-direction, not only the next action |
| Structure the user authors at runtime is not generated ahead of them | No machinery exists to infer relationships the UI lets the user create click-by-click |
| Generation-precision work in tooling/SDK follows a proven, used capability | The capability shipped and was exercised before its generator was perfected |

---

## The Essential Insight

Precision feels like the safest thing to optimize — it is measurable, it is unambiguous, it always reads as progress. That is exactly what makes its emptiness invisible. **The question is never "is this precise enough?" It is "who is served by this precision, and is it the thing standing between the user and something they could already be doing?"**

A reachable capability a user can use today is worth more than a flawlessly generated one they cannot reach. When precision has no beneficiary — or when the beneficiary is the user doing, at runtime, the very thing you are racing to generate — stop. That precision is worth zero, and the value it displaced is the real cost.

---

*Version 1.0.0 | 2026-06-03 | Named "Zero Value Precision" by the human in the session that demonstrated it — a long arc of correct, agreed-to, beneficiary-less generation work, halted one check before it shipped nothing a user could use.*
