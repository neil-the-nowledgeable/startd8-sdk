# ContextCore — a product intro at three altitudes

**Date:** 2026-08-17 · **Purpose:** one high-level intro that meets three readers where they are — a
**new intern** (lowest fluency), an **executive** (business value), and a **software-engineering leader**
we want as a **design partner toward a first paying customer**. Grounded in the ContextCore code + the
2026-08-17 o11y PM findings ([[PM_FINDINGS_contextcore-o11y-value-lineage]]).

> **Why three lenses over one core:** ContextCore's whole thesis is that the *same ground truth* serves
> different people at different altitudes. This intro is that thesis in miniature.

---

## The core (one sentence, for everyone)

**ContextCore keeps a live, honest picture of your work — from the business goal at the top down to the
AI agents doing the tasks at the bottom — derived automatically from ground truth (commits, tests, agent
sessions), so the status can't silently lie.**

*Why now:* in an AI-agent-driven org, work moves faster than any human can hand-update a status board — and
you need to know what the agents are producing, whether it's grounded, and whether it's moving the number.
ContextCore is the observability **and accountability** layer for exactly that.

---

## Lens 1 — Start here (a brand-new teammate)

Every team asks the same three questions all day: **What's done? Are we on track? What's stuck?** Normally
the answers live in people's heads and in status docs that go stale the moment they're written — so people
guess, or the board says "green" when things are actually behind.

ContextCore answers those three questions **automatically and honestly.** It watches the real work as it
happens — code getting committed, tests passing or failing, AI agents finishing tasks — and keeps a live
picture of what's *actually* true. Nobody hand-updates it, so it can't drift or fib.

> Think of the **speedometer in a car**: you don't tell the car it's going 60 — the needle reads it off the
> wheels. ContextCore is a speedometer for a project: it reads "how are we doing" from the *actual work*,
> not from anyone's opinion.

**Why you'll care:** you can look and *know* what's going on — which features are shipping, which are stuck,
what the AI agents have produced — without pinging five people. *(The grown-up word for this is
**observability** — the same idea companies use to watch their software, pointed at the work itself.)*

---

## Lens 2 — For the executive (the business value)

**BLUF: ContextCore gives you one trustworthy line of sight from the number to the work that moves it — and
it's built for the age of AI-agent delivery.**

- **Trust — the status can't be gamed or drift.** Every signal is *derived from ground truth* (commits, CI,
  agent sessions), not typed into a form by someone hoping to look good. Your dashboards become **audit-grade**:
  the map matches the territory.
- **Line of sight from the number to the work.** Declare business objectives (revenue, conversion, margin)
  with **pace targets** and healthy-range **envelopes**; ContextCore tells you in real time whether you're on
  track and warns *early* when you drift out of band.
- **Accountability for AI agents — the new frontier.** As you move work to agents, the questions change:
  *What did they ship? What did it cost per outcome? Did they break anything? Is it moving the number?*
  ContextCore observes the **agents themselves** — productivity, cost-per-issue, regression rate — so your AI
  investment is measurable, not a black box. *(This is live today.)*
- **The honest edge = the opportunity.** The connective tissue that ties agent work *up to* business outcomes
  — **feature observability** — is the piece we're building next. Everything *under* it (agent productivity)
  and *above* it (business goals) already works. That gap is deliberately where a design partner shapes the
  product.

**Bottom line:** *know if you're hitting the number, in real time, from ground truth — and know whether your
agents are earning their keep.*

---

## Lens 3 — For the engineering leader (architecture + an invitation)

You're deciding two things: is this *real*, and is it worth *co-building*. Straight talk.

- **OTel-native, no black box.** Everything is OpenTelemetry — spans (Tempo), metrics (Mimir), logs (Loki),
  Grafana on top. Standard wire protocol, your stack, no lock-in. A "project" is a trace; epics/stories/tasks
  are spans.
- **Deterministic / correct-by-construction.** Status is *derived* from artifacts, never asserted. The model
  is small and honest: `Objective` + `KeyResult` bound to a metric → classified into health → pace/envelope/
  coverage boards. The category taxonomy is validated (an unknown category is a *build error*). This is
  "verification that cannot silently die" applied to project state.
- **Agent-native observability — the wedge.** Most observability watches *services*; ContextCore watches the
  **AI agents doing the work** — sessions, cost, output, regressions, and typed agent-to-agent contracts/
  handoffs. That's the differentiator for an AI-driven org.
- **We know exactly where the frontier is — and we can show it.** We ran ContextCore's own observability model
  through a node visualizer: its objectives render as **6 nodes, 0 edges** — a flat constellation. That's the
  honest gap, grounded in code (file:line): the **value lineage `business ← feature ← agent` isn't modeled** —
  objectives are siblings with no `serves` edge, and **goal↔work binding is implicit** (a PromQL string,
  `"promql:epic:EPIC-001"`, not a declared link). We've already written the first spec to fix it (the objective
  `serves` edge, BUILD-READY).
- **The ask — be our design partner toward first paying customer.** The highest-value unbuilt piece is
  **feature observability**: the *hinge* where agent-produced, deterministically-grounded work becomes business
  value. We want a partner to shape exactly that — how features roll up to outcomes, how agent work binds to
  features, what the boards say.
  - **You get:** influence over the model, an OTel-native system you run yourself, and early accountability for
    your own AI-agent delivery.
  - **We bring:** a working engine (business + agent o11y shipped), a grounded roadmap, a visualizer that
    exposes our own gaps, and a bias for honest, deterministic signal over vanity dashboards.

---

## The map (what's shipped vs the frontier)

| Pillar | Question it answers | Audience | State |
|--------|--------------------|----------|-------|
| **Business o11y** | Are we hitting the number? | Executive | **shipped** |
| **Feature o11y** | Are the right features shipping, on pace? | Product/Delivery | **frontier — the design-partner ask** |
| **AI-agent o11y** | What are the agents producing / costing? | Eng leader | **shipped** |
| **Deterministic grounding** | Can I trust the signal? | Everyone | the substrate (a guarantee, not a screen) |

*The intern sees "what's going on." The exec sees the number. The engineer sees the spans. Same ground
truth, three altitudes — which is exactly what ContextCore is for.*
