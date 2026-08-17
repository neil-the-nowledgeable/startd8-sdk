# Value proposition: verification that cannot silently die

**Date:** 2026-08-16 · **Type:** strategic anchor · **Status:** proposed as the central value prop for the effort
**Grounded in:** `dev-os/FINDING-verify-liveness-lacuna.md` (the NetBSD `O-4` Functional Spine Fracture) ·
the cross-corpus `honest-grounding` principle (`RESEARCH_cross-corpus-grammar-principles-vs-conventions.md`)

## The value prop, in one sentence

> **Your requirements cannot lie about being verified.** A requirement can *never* read "verified" while its
> check attests nothing — because the acceptance oracle is bound to a **live** gate, the gate is **re-checked
> when the implementation changes**, and a gate that silently dies routes to a **human-gated decision**, never
> a silent green.

## The failure it prevents (grounded, not hypothetical)

A real incident: NetBSD `O-4` claimed `session ≡ old_session`, guarded by `make parity`. A *faithful*
refactor (linear interpreter → IPC daemon) made the command block on a socket — the parity comparison became
**structurally impossible**. Yet the requirement still had its verify prose, still pointed at real code, and
**passed every structural check.** It read green while its guarantee was dead. *"A faithful local change
severed a global requirement↔check invariant that no participant was holding."*

This is the **Functional Spine Fracture** — and it is universal. Every codebase accumulates dead gates after
refactors and does not know it. The cruelest part, named in the finding: the instrument that *should* catch
it usually **trips its own class** — a liveness blind-spot in the liveness checker (a durable green that
carries no truth is exactly what the greens are trusted to rule out, right before a milestone).

## Why this is the *central* value prop (and beats the alternatives)

Two candidate value props emerged from this effort:
- The **Craft-Grammar self-similarity** result is *intellectually* compelling — but it is a *property* of the
  system, not a *benefit* to a user.
- **Verification-that-cannot-silently-die** is a **benefit**: concrete, visceral, universal, and painful. It
  answers "why should I care?" with a failure everyone has lived.

The grammar is the **why-it-works** (the system is coherent). This is the **what-you-get**.

## Why *this* machinery is uniquely positioned to deliver it

The fix is not a new engine — it is **wiring together pieces this effort already built**. That one-to-one
mapping is the tell that this is the effort's true purpose:

| The fix needs… | …and the effort already built it |
|---|---|
| a first-class oracle | `verify` as a Node field (REQ-17) |
| a runnable gate handle | `verify.gate` — one additive field (REQ-22 FR-1) |
| a liveness check (resolve / run / provenance-fail) | `verify_oracle` — classify + sandboxed run + error-vs-fail (REQ-08, **built**) |
| catch it *when the impl changes* | the derivation edge (REQ-16) + realization provenance (REQ-19) → re-check on drift |
| "retiring an invariant needs sign-off" | the retrospective bookend — a human-gated `revises` (REQ-20/21) |

Without this effort, closing the lacuna is a from-scratch verify-execution + provenance + feedback system.
With it, it is **one small additive REQ** (REQ-22). The parts were, in retrospect, *converging on this the
whole time.*

## The deep reason it belongs at the center

**Verify-liveness is `honest-grounding` applied to the oracle itself.** The principle this effort *measured*
as cross-corpus universal — *a claim is cruft until grounded, never asserted* — when applied to `verify`,
**demands** that a verify be grounded in a *live* gate, not a *prose seed*. A present-but-dead verify is
*cruft masquerading as proven* — the same shape as the dormant value path, the confidence-aware seam, the
whole spine of the work. So this value prop is not a new capability grafted on; it is **the faithful
application of the effort's own deepest principle to the effort's own reliability instrument.** That is why
it can anchor everything: the IR (verify · derivation · realization · retrospective) was, all along,
converging on making verification *live*.

## Honest scope (so the claim survives scrutiny)

- It prevents this class **once REQ-22 is built** — small *because* of the scaffolding, but not free today.
  (And the effort's *own* invariant 9 currently checks presence, not liveness — REQ-22 FR-7 fixes that too.)
- Catching *arbitrary project gates* (e.g. `make parity`) needs `verify_oracle`'s run-scope widened beyond
  navigator subcommands, with the sandbox + timeout intact.
- **Structural death is a fact → GAP; provenance-failure is a precision-governed candidate.** The claim is
  "a dead gate is *never a silent green*," not "we auto-repair it."
- The check is **advisory** (it routes to a human), never a blocking build gate.

## The claim, restated for the effort

The Natural-Language Programming System's reliability rests on grounding every claim. Its **most valuable,
most concrete promise** is to extend that grounding to the claim a requirement makes about *itself*: that it
is verified. **A requirement built through this system cannot carry a verified badge its check no longer
earns.** That is the durable green made honest — and it is the reason the effort matters.
