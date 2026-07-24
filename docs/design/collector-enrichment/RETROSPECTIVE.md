# Retrospective — collector_enrichment SDK build (Hansei)

**Date:** 2026-07-23
**Pilot:** the FR-1b + FR-2–11 build, commits `fb007fb7` (doc mirror) → `415a33aa` (reflective
reqs v0.3.1) → `fc2613af` (generator + 28 tests) → `a478e8d8` (format). Refs #320.
**Question:** what reusable standard did this prove for **consuming a cross-repo engineering handoff**?

---

## Phase 2 — the actuals I grounded against (not the handoff prose)

- **The real producer:** `ContextCore utils/instrumentation.py:405-523` on branch
  `feat/collector-enrichment-fr1a-export` (unmerged) — what bytes the SDK will actually receive.
- **The real target artifact:** `~/Documents/Jobs/.../Insight-Finder/demo/collector/otelcol-config-extras.yml:31-48`
  — the verbatim hand-written OTTL the generator must reproduce.
- **The observed behavior:** the emitter, run against the Online-Boutique map, produced output that
  passed **semantic parity** against that verbatim block, was byte-identical under shuffled input, and
  skipped cleanly with no business context. Full obs suite (696) + feature tests (28) green.

## Phase 3 — reversed discovery table (handoff belief → grounded actual)

The handoff (`COLLECTOR_ENRICHMENT_SDK_HANDOFF.md`) is a **belief artifact**: ContextCore's model of
the SDK's job. Six of its clauses drifted from the real producer / real reference:

| Handoff said (belief) | Actuals revealed (grounded) | Standard extracted |
|---|---|---|
| hint carries top-level `criticality`/`owner` | producer writes **nested** `hint["business"]` (`instrumentation.py:523`) | read the producer's real key path, not the prose's |
| SDK re-applies a project→service fallback | producer **already resolved** target-over-project (`:516-517`); re-applying breaks byte-identical absence | don't re-derive what the producer forwards (Mottainai) |
| OTTL form `set(business.<attr>)` | real form `set(attributes["business.<attr>"], "<value>")` (`otelcol-config-extras.yml:37`) | bind syntax to the real target artifact, byte-for-byte |
| byte-parity vs the reference block | reference **groups services by value**; one-per-service can't be byte-equal | define equivalence on the resolved *meaning*, not the bytes |
| statement count `|attr| × N` | partial context is valid → **Σ present `(service,attr)` pairs** | count what's present, not the cartesian product |
| declaration-gate it (like `capability_index`) | presence of exported business context **is** the signal | gate on the data that exists, not a redundant declaration |

Every row is a place the *documentation about the interface* was wrong and the *interface itself* was
right. The reflective-requirements loop surfaced them **because Phase 2 touched both real ends** — had I
planned against the handoff prose, all six would have shipped as bugs (nested-key `KeyError`/silent-miss,
a byte-parity gate that can never pass, a "every service = medium" absence regression, garbled OTTL the
collector rejects).

## Phase 4 — the extracted standard

> **Standard: Consuming a cross-repo engineering handoff.**
> A handoff doc is the *producing* team's model of the *consuming* system. It drifts from both real
> ends. Before implementing, Genchi Genbutsu on **both**:
>
> 1. **The real producer** — read the code that emits the contract (even on an unmerged branch:
>    `git fetch <remote> <branch>` / `git grep <sha>:<path>`). Confirm the exact key path, nesting, and
>    what resolution it has **already applied**. Consume forwarded values as-is (Mottainai) — never
>    re-derive a fallback the producer computed.
> 2. **The real target artifact** — if the output must match a hand-written reference, find and read the
>    actual file (the handoff's stated path may be wrong; search for it). Bind emitted **syntax** to it
>    byte-for-byte; define **equivalence** on meaning when two legitimate renderings can't be byte-equal
>    (→ a semantic parity gate, not a diff).
> 3. **Treat every handoff clause as a hypothesis**, not a requirement. Fold the corrections into the
>    spec's §0 with the grounding cite, so the next reader sees belief-vs-actual, not just the fix.
>
> Where a forwarded contract can be absent, absence must degrade to **byte-identical to before** (SOTTO):
> presence-gate the output; don't default-fill.

Ground: this standard is exactly the v0.3.1 §0 table — each clause earned by a shipped correction above.

## Phase 5 — lesson + principle

- **Lesson (SDK / cross-repo):** *"A cross-repo handoff is a belief artifact — bind to the real producer
  code AND the real target artifact before implementing; the prose drifts from both."* Detection: any
  handoff clause naming a key path, a value form, or a parity criterion. Recovery: `git fetch` the
  producer branch + `find` the reference file; re-plan against those. → to Lessons Learned + auto-memory.
- **Principle reaffirmed — Genchi Genbutsu** applies to *interface documentation*, not just running
  systems: the doc about the bytes is not the bytes. **Mottainai** killed the redundant fallback;
  **SOTTO** shaped presence-gating; the **accidental-complexity anti-principle** killed both the
  declaration allowlist and a value-grouping engine.

## Phase 6 — Yokoten

- The three sibling collector-config generators (spanmetrics #307, this, and any future `transform/*`
  emitter) share the shape "generate a Collector processor from the manifest, parity-checked before
  retiring a hand-written block." The **semantic-parity-gate** pattern (parse both → compare resolved
  maps, grouping-insensitive) is the reusable piece — apply it to the next cutover rather than a diff.
- Feeds the forward loop: the extracted standard is now an input to the next `/reflective-requirements`
  that consumes a ContextCore→SDK handoff (the FR-7 spanmetrics-dimension follow-up will).
