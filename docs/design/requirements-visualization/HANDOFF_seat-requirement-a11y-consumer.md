# Handoff — Seat requirement authoring, the ContextCore a11y-consumer side (FR-7)

**Date:** 2026-08-16 · **From:** startd8-sdk session (built the SDK slice) · **For:** the ContextCore navigator / a11y team
**Spec (SSOT, build-ready):** `startd8-sdk/docs/design/requirements-visualization/REQ-seat-requirement-authoring-on-det-req-definer.md` (v0.4.1)

## Why you're getting this

The seat-req's whole point is **one grammar, one store, dual consumers** (Objective O-3: *glance validation
uses SDK and/or CC navigators against the **same** det-req bytes — no forked schema*). The SDK side is built
+ landed (`startd8-sdk` `d0dd91b9`); the Definer/kit side is delegated to the dev-os team. **FR-7 is yours:
keep ContextCore a11y a first-class consumer of the same det-req bytes.**

## What's yours — FR-7

> **CC a11y remains a first-class consumer.** Operators can validate the same det-req bytes with the
> ContextCore a11y / corpus navigators per HOWTO §6 **without an SDK reimplementation of the cockpit**.

**Verify (the acceptance condition, verbatim from the spec):**
> The documented command path succeeds on the same det-req file used in FR-6 **OR** records a typed skip
> (`install-propagation`) with a **pinned ContextCore version + expiry date** in the round-trip/report
> artifact; the gate **fails after expiry**.

So FR-7 is satisfied one of two honest ways — do EITHER:
1. **Live path** — document (and prove) the ContextCore a11y command that renders/validates a det-req file
   (the same bytes the SDK's `startd8 navigator build --source requirements` consumes), per HOWTO §6; **or**
2. **Typed skip** — if the CC navigator isn't installed/propagated in the round-trip env, emit a
   `install-propagation` skip **with a pinned CC version + an expiry date** into the round-trip report, so
   it's an honest "not-here-yet", not a silent pass — and the gate turns red once the expiry passes. (This is
   the Harbor Honesty-Verdict / absence-vs-error move: a skip must name why + when it stops being acceptable.)

## The shared input (don't fork the schema)

- The det-req bytes are the SAME the SDK consumes — a det-req/0.1 file (Wire form: one FR per line; strong
  Lives `git:<40hex>:<path>`; `Lives:` before `Verify:`; `Name:` on every FR). Do **not** introduce a second
  grammar/store/renderer (Definer roadmap lock + the spec's NR/O-3).
- Cross-check: the CC a11y render and the SDK `navigator build` render should agree on the FR set from the
  same file. The SDK now enforces a **parse-loss floor** (node count == FR-marker count, else non-zero) — a
  free signal that neither consumer is silently dropping FRs.

## Context — the CC Node mirror already tracks the SDK 0.4.0 field set

You merged `contextcore#491` (the Node mirror at 0.4.0: `verify`/`approve`/`was`/`derivation`). A **follow-on**
adds `verify_gate` (startd8 REQ-22 verify-liveness) — a *separate* coordinated handoff, not part of FR-7. FR-7
only needs the a11y consumer to read the same det-req bytes; it doesn't require the new mirror field.

## If you'd rather not build now

FR-7 is explicitly satisfiable by the **typed-skip** path (option 2) — the spec designed it so an un-propagated
CC navigator doesn't block the seat-req, as long as the skip is honest (pinned version + expiry). That's the
lowest-effort correct answer if the a11y command path isn't ready.
