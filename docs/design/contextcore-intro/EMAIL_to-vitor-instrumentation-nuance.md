# Email draft — to Vitor Mouzinho, on the "is it instrumentation?" nuance

Basis for a follow-up email to Vitor Mouzinho (author of *"Auto-Instrumenting Go Applications Without Modifying
Source Code"*), who challenged whether the approach qualifies as instrumentation. Concede the fair part, then use
his own eBPF work as common ground for the real nuance. Adapt freely — use some or all.

---

## Primary draft

**Subject:** The "is it instrumentation?" question — you were right to push (and where it gets interesting)

Hi Vitor,

Really enjoyed talking today — and thanks for pushing me on whether what I was describing actually *counts* as
instrumentation. You were right to, and it sent me back to sharpen the definition, which I clearly hadn't done
cleanly enough in the moment.

Let me concede the fair part first. A lot of what I was describing isn't instrumentation in the classical sense.
I was mostly talking about generating the observability *artifacts* you observe **with** — dashboards, alerts, SLO
configs, collector pipelines — derived automatically from business context. That's generating the observability
*setup*, not producing signal from the running system. Calling it "instrumentation" was loose. Point taken.

Where it gets interesting is that "instrumentation" itself is being redrawn — and your article is a great example
of it. The taxonomy I landed on:

1. **Generate signal** — app code, auto-instrumentation, **eBPF**. *This* is instrumentation. Your Go/eBPF piece
   lives here — and it's already the boundary moving from "write code" to "attach at the infra layer without
   touching source."
2. **Enrich at the source** — resource detectors, span processors that decorate signals in-process.
   Instrumentation-*adjacent*, but decoration, not generation.
3. **Process in the pipeline** — collector-side transforms and routing (OTTL, `k8sattributes`). Not instrumentation.
4. **Generate the o11y artifacts** — the dashboards/alerts/SLOs/config you observe *with*. A different axis
   entirely — and mostly what I was gesturing at on the call.

So you were right: (3) and (4) aren't instrumentation. But what I was clumsily reaching for is that all four are
collapsing into one *declarative* observability discipline — and eBPF (your work) is at the leading edge of (1). I
was trying to extend that same trajectory: not just "instrument without touching source," but make the
instrumentation *business-aware* (carry criticality, the business flow, the value) and *declarative* end-to-end.

And here's the part that's genuinely your wheelhouse, where I'd love your read: eBPF is excellent at *generating*
signal, but the frontier is distributed *context propagation* at the kernel layer — carrying baggage across
service hops without SDKs. That's exactly where "instrumentation" would start carrying business meaning across the
whole call graph, and it's the piece I couldn't quite articulate on the call. What are you seeing there — is
cross-service context/baggage propagation via eBPF getting practical yet, or is it still SDK territory?

Would genuinely value continuing this.

Best,
[your name]

---

## Tighter variant (~180 words)

**Subject:** You were right to push me on "instrumentation"

Hi Vitor — thanks for the challenge today; it made me sharpen a definition I'd been sloppy about.

Fair concession first: a lot of what I described isn't instrumentation. I was mostly talking about auto-generating
the observability *artifacts* — dashboards, alerts, SLOs, collector config — from business context. That's
generating the setup, not producing signal. You were right to call it.

The nuance I was reaching for: instrumentation itself is being redrawn, and your eBPF work is at the front of it.
There's a clean ladder — (1) generate signal (code / auto-instr / **eBPF** = real instrumentation), (2) enrich at
the source, (3) process in the collector, (4) generate the o11y artifacts. (3) and (4) aren't instrumentation —
but all four are collapsing into one *declarative* discipline. I was extending your "instrument without touching
source" trajectory: make the instrumentation *business-aware* and declarative end-to-end.

The frontier I'd love your take on — distributed **context/baggage propagation via eBPF** across service hops.
That's where instrumentation starts carrying business meaning across the whole call graph. Practical yet?

Best, [your name]

---

## Optional modular passage — the concrete example + the "instrument the dimension" reframe (strongest add)

*Drop this in when you want to make the argument land with a shipped example rather than a definition.*

> Here's a concrete one, so it's not just semantics. We generate a collector-side OTTL processor
> (`transform/business`) from a single manifest of business context — it stamps each service's
> **business_criticality** (and owner) onto telemetry it *didn't* originally carry. Our coverage RCA then reads
> that dimension: instead of "is service X observed?", it answers **"are our _critical_ services observed — and
> rank the blind spots by business value."** That question was literally unanswerable before the enrichment, and
> answerable after.
>
> So I'll concede your strict point *and* sharpen mine: this isn't source-side *signal generation* — a collector
> processor can't observe the running system, you're right. But it **instruments a new _dimension_**: it projects
> declared business meaning onto the existing signal so a class of questions becomes answerable. The RCA is the
> proof. The honest caveat: the dimension's information is *declared* (a manifest), not *discovered* from the
> system — so it instruments the business dimension, riding on the classically-instrumented base signal (which is
> your eBPF layer). Two axes of the same word, not a redefinition of it.
>
> (Amusingly, the module that derives all this is literally named `instrumentation.py` — it does double duty:
> derives what each service *should* emit from OTel semconv *and* generates that business-enrichment processor.
> The coverage RCA sits right at the intersection — "is this service instrumented enough to be observable, and
> does it matter?")

## Optional modular passages (drop in if useful)

- **If you want to name the approach:** *"The shorthand I've been using is 'declarative business-context
  observability' — declare a service's business meaning once (as an annotation/CRD), and every signal it emits
  inherits it, with the important requests carrying their business flow with them."*
- **A softer concession line:** *"On reflection you nailed the imprecision — I was collapsing four different things
  ('instrument', 'enrich', 'route', 'configure') under one word, and the one I actually meant was mostly the last."*
- **A common-ground compliment (genuine):** *"Your piece is honestly the cleanest example I've seen of the
  boundary moving — 'instrumentation' stops being something a developer writes and becomes something the platform
  attaches."*

## Tone notes
- **Lead with the concession** — conceding the fair point first is what earns the right to raise the nuance, and
  it reads as confidence, not backpedaling.
- **Make his work the hero**, not yours — his eBPF article *is* the boundary-shift; you're extending its axis.
- **End with a real question in his domain** (eBPF context propagation) — turns a definitional debate into a peer
  exchange he'll want to answer.
- **Keep the product soft** — no pitch; if it comes up, it's a footnote to the idea.
