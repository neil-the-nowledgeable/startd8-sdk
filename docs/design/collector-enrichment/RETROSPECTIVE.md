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

---

# Retrospective — the follow-ups batch (QW-2/QW-3/EC-1/EC-2, PR #324)

**Pilot:** the four enhancement-backlog items, commits on `feat/collector-enrichment-followups`.
**Question:** what reusable standard did EC-1 prove for **adding a per-instance override to a shared
generator**?

## Phase 2 — the actuals

- The diff threaded an optional `service` into `_severity_for` and 9 per-service call sites; the runbook
  gained a per-service owner branch; the generator gained a spanmetrics-dimension fragment + `fr_coverage`.
- **The observed result:** the full observability suite stayed **732 passed** — byte-identical — with **no
  feature flag**. The grep `grep -rl '"business"' tests/…/instrumentation_hints` returned only my *own*
  collector_enrichment tests: no alert/SLO/runbook fixture carries per-service business.

## Phase 3 — reversed discovery table (belief → actual)

| The spec (NR-1) believed | The actuals revealed | Standard extracted |
|---|---|---|
| EC-1 "must be additive/**flag-guarded** — rewiring risks byte-output regressions." | **No flag needed.** The new field's **empty-default** (`criticality=""`, `owner=None`) + the consumer's fallback-to-project **is** the guard: empty ⇒ project value ⇒ identical bytes. | When an added per-instance override defaults to empty AND the consumer falls back to the prior value, existing output is byte-identical *for free* — a flag is accidental complexity. |
| The risk is "rewiring." | The risk is only real **if an existing fixture populates the new field.** It doesn't (grep-verified). | The load-bearing safety step is the **grep proving no existing input carries the new field**, not a flag. |

## Phase 4 — the extracted standard

> **Standard: the empty-default is the guard, not a flag.**
> To add a per-instance override to a shared generator without regressing existing output:
> 1. Give the new field an **empty/absent default** (`""` / `None`).
> 2. Have the consumer **prefer the per-instance value only when truthy, else fall back** to the
>    existing (project/global) value — and keep the *fallback path's* derivation/trace **byte-identical**
>    to before (e.g. `_severity_for`'s project-path `source` string is unchanged).
> 3. **Grep the fixtures/inputs to prove none populate the new field.** This is the actual safety proof;
>    the full suite is the confirmation.
> 4. Only reach for a feature flag when an existing input *does* carry the field and the new behavior
>    would change shipped output — i.e. when steps 1–3 can't hold. Absent that, a flag is a mechanism
>    guarding a regression a structural invariant already prevents.

Ground: `_severity_for` (`artifact_generator_generators.py:193`) + the 9 threaded call sites; the
byte-identical 732-fixture result; the fixture grep.

## Phase 5 — lesson + principle

- **Lesson (SDK):** *"empty-default is the byte-identity guard, not a flag"* — with the grep-the-fixtures
  proof step. → auto-memory + Lessons Learned.
- **Accidental-Complexity anti-principle** (reaffirmed): the spec's instinct to add a *flag* was a
  mechanism to guard a regression a **structural invariant** (empty-default → fallback → identical)
  already prevents. Prefer the invariant; delete the mechanism.
- **SOTTO**: byte-identical-when-absent, achieved by empty-gating rather than a flag — the same shape as
  the generator's presence-gate.

## Phase 6 — Yokoten

- The same "empty-default is the guard" move applies to the *other* dormant FR-1b consumers and to any
  future per-service override of a shared generator (thresholds, datasource UIDs, dashboard placement).
  When the next one lands, skip the flag; grep the fixtures instead.
- Feeds the forward loop: this standard is now an input to the next `/reflective-requirements` that
  proposes a per-instance override — it should default to "empty-default guard, verify by grep" and only
  escalate to a flag if a fixture already carries the field.

---

# Retrospective — the enhancement-backlog-driven arc (#322–326)

**Pilot:** five PRs driven by `/enhancement-backlog` (parity CLI → live proof → follow-ups → drift/append
→ legibility/scoring → `--reference-cmd`), over the collector_enrichment subsystem.
**Question:** how should an enhancement backlog be *consumed*? What did the arc prove about the backlog
itself as an input?

## Phase 2 — the actuals

The backlog is *supposed* to be grounded (its own discipline: `Confirmed:` vs `Hypothesis:`). Yet at
**build** time, grounding the enabling claim against the real code — and the real external system —
corrected the backlog's framing on three of the items actually built.

## Phase 3 — reversed discovery table (backlog said → actuals revealed)

| The backlog said | Grounding at build time revealed | So the standard is… |
|---|---|---|
| QW-3 provenance is likely **redundant** with existing drift detection | `check_drift` (`artifact_generator.py:1633-1664`) is **key + derivation** based, **not** content-based → provenance is *not* redundant; a business change was silently undetected (→ QW-5, a real fix) | re-ground the "redundant with X" dismissal against X's actual code — a dismissal is a hypothesis too |
| EC-3 = `--live-config <url>` pulling a running collector's effective config | stock `otelcol-contrib` exposes **no** config-over-HTTP endpoint (zPages ≠ raw config) → built `--reference-cmd` instead | ground the **external data source**, not just the internal enabling claim |
| the parity gate is the deliverable (function + test) | correct — but reachable **only from tests**; the operator surface was missing (→ QW-1 CLI) | "shipped as speced" can still be unreachable; check the *surface*, not just the function |

The load-bearing surprise is the middle row. The backlog grounded the half it could see — its **own
repo** ("the parity parser is transport-agnostic", true) — and *guessed* the half it couldn't — the
**third-party** surface ("otelcol exposes config over HTTP", false). The internal "already exists" was
right while the external "and you can fetch X from Y" was wrong.

## Phase 4 — the extracted standard

> **Standard: an enhancement-backlog item is a hypothesis; re-ground it at build time — the internal
> enabling claim AND the external data source.**
> A backlog is authored against a snapshot and grounded against the code it can see. Before building an
> item:
> 1. **Re-verify the internal enabling claim** — the code moves; the `file:line` the item cites may have
>    changed. Confirm the plumbing still exists and does what the item assumes.
> 2. **Ground the external data source separately** — if the item depends on a third-party surface (an
>    endpoint, a binary flag, a config API), verify *that* exists. The internal claim can be true while the
>    external assumption is false (EC-3: transport-agnostic parser ✓, otelcol config endpoint ✗).
> 3. **Treat "redundant with X" / "already covered" as a hypothesis too** — open X's code before dismissing
>    (QW-3→QW-5: the "redundant" provenance was the fix).
> 4. Expect ~1-in-3 built items to need a framing correction. That is the grounding working, not the
>    backlog failing.

## Phase 5 — lesson + principle

- **Lesson:** *"an enhancement-backlog item is a belief; re-ground both its internal claim and its external
  data source at build time"* — the third member of the belief-artifact triad with
  [[feedback_cross_repo_handoff_grounding]] (handoffs) and the requirements spec (reflective-requirements).
  → auto-memory.
- **Genchi Genbutsu, extended:** the principle already says "bind to the real artifact." The arc sharpens
  it — *which* real artifact: for a backlog item, that's **two** artifacts (your code + the third-party
  system it touches), and the backlog only grounded the first.

## Phase 6 — Yokoten

- Every future `/enhancement-backlog` consumption: before building an item, re-run its `Confirmed:` claim
  and, if it names an external surface, verify that surface exists — don't inherit the backlog's grounding.
- The belief-artifact triad (handoff · spec · backlog) now has one rule: **the map is not the territory,
  in both directions, at every stage — re-ground at the moment of building, not just at authoring.**
