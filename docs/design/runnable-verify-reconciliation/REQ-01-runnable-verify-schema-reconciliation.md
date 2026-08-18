# Runnable-Verify Reconciliation — one canonical `verify.gate` schema unifying `a1` (generation) and CL-55 (governance) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-18
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-01-runnable-verify-schema-reconciliation.md` · **`docs/design/oracle-generation-loop/VERIFY-GRAMMAR.md` (the `a1` grammar — BUILT)** · **`dev-os/FINDING-verify-liveness-lacuna.md` (CL-55 — the `verify.gate` prescription)** · `REQ-22-verify-liveness-not-presence.md` (verify-liveness + `verify.gate` field — BUILT) · `REQ-23-liveness-layer-fact-first-cells.md` (the liveness layer — BUILT) · `REQ-27-self-dogfood-verify-gate-adoption.md` (self-dogfood adoption — spec)
**Inherits standards:** det-req-kit `SCHEMA.md` (the schema SSOT — dev-os) · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern + FR-7 precision) · REQ-07 (Validation Cockpit — advisory, NR-1) · Harbor Honesty-Verdict (absence-vs-error) · Mottainai (reuse-not-build) · over-abstraction guard (no dispatch framework)
**Audience:** det-req-kit owners (Kagami/Mottainai — schema) / SDK navigator + oracle-loop contributors / validators (cross-repo)
**Trust boundary:** local; the schema addition is a dev-os/det-req-kit change (kit owner's go); the conforming parsers + the `kind`-aware liveness check are SDK-side; gate execution stays opt-in under the existing sandboxes (read-only allow-list / sandbox exec), advisory, never a blocking build gate
**Data classification:** internal

> **Readable handle:** `feature/canonical-runnable-verify-gate-unifies-a1-and-cl55`
> **Semantic name:** *A single canonical runnable-`verify.gate` schema — a typed handle whose `kind` ∈ {command, pytest, probe, named-fitness} — is defined once in det-req-kit SCHEMA.md so both the oracle-loop generation runner (a1's one-shot/probe forms) and the det-req-kit governance liveness check (CL-55's runnable handle) consume the same shape, of which a1's forms are the typed instances, additively and backward-compatibly so the three existing oracles stay valid.*
> **Canonical ref:** `cc:intent:runnable-verify-reconciliation:feature:req-01`

## 0. Planning insights — what grounding the two conventions against each other revealed

The reflective loop grounded both conventions against their real files (`grammar.py`, `verify_oracle.py`,
`govern.py:_gate_liveness`, `det_req.py:parse_gate`, det-req-kit `SCHEMA.md`, `FINDING-verify-liveness-lacuna.md`).
The groundings that revised the spec:

| v0.1 assumption (pre-grounding) | Grounding discovery | Impact on this REQ |
|---|---|---|
| `a1` and `verify.gate` are two names for the same thing | **They are NOT.** `a1` (`grammar.py`) is a *typed 2-form runner grammar* (one-shot argv + data-only probe struct) with its OWN parser; `verify.gate` (CL-55 / REQ-22) is a *generic runnable handle string* — "a command, a test id, or a named fitness function" — parsed by `det_req.parse_gate` into a bare `verify_gate: str`. a1 is a **realized instance-set**; verify.gate is an **under-typed placeholder**. | FR-1 states the delta precisely; the schema (FR-2) makes verify.gate the *typed superset* whose instances are a1's forms. |
| verify.gate's liveness check would accept a1's forms | **It does not.** `govern.py:_gate_liveness` reuses `verify_oracle._classify_clause`, whose `_ALLOWED_VERBS = {"startd8"}`. A `pytest …` or `probe GET /x -> 200` gate classifies as NON-`command` → `dead-structural` → a **false GAP**. The governance liveness checker would red-flag exactly the runnable forms the generation runner executes successfully. | FR-3 (the false-GAP hazard) is the load-bearing reconciliation defect; FR-5 makes the liveness check `kind`-aware over the same shared parser. |
| Only two oracles to reconcile | **There are THREE** verify-classifiers: (a) `navigator/verify_oracle.classify` (startd8-verb allow-list, SDK self-check); (b) `oracle_loop/grammar.parse_verify_clause` (a1 — pytest/probe, generated-app fitness); (c) the det-req-kit `verify-liveness` check (CL-55, governance) which today *borrows* (a). Three parsers, three verb sets, one field. | FR-6 scopes honestly: unify a1⇄verify.gate under one *typed schema + shared parser*; the navigator startd8-verb oracle becomes ONE `kind=command` variant, not deleted. |
| The schema lives in the SDK | **The SDK is a conforming consumer, not the SSOT.** det-req-kit `SCHEMA.md` §5 owns the FR `verify` field (dev-os, Kagami/Mottainai); the SDK's `parse_gate`/`grammar.py` are *conforming parsers*. Putting the canonical schema in the SDK would re-fork what Kagami just de-forked (SCHEMA.md changelog 2026-08-15). | FR-4 places the typed `verify.gate` schema in det-req-kit SCHEMA.md as the single source; the SDK parsers conform. This is a cross-repo PROPOSAL to the kit, honestly flagged (NR-5). |
| verify.gate is already shipped, so this is a no-op | **verify.gate is shipped UNTYPED.** `det_req.py:145` is `verify_gate: str = ""` — a bare string; `_gate_liveness` guesses its runnability via the startd8-only classifier. The typing + the shared multi-`kind` parser is the missing rung. REQ-27's self-study measured `verify.gate` adoption at 0/180 — the untyped field has no instances yet, so typing it now is **cheap** (no migration debt). | FR-7 makes adoption additive on a still-empty field; the a1 corpus (oracle-loop specs) becomes the first typed-gate corpus for free. |

**The core reconciliation thesis (stated up front).** `a1 ≠ verify.gate` today: a1 is a *typed, 2-form, executable
grammar*; verify.gate is a *generic untyped runnable-handle string*. They are **not competing** — they are the
**instance layer and the placeholder layer of the same idea**. The reconciliation is a single canonical
`verify.gate` that is a **typed handle** `{ kind, raw }` with `kind ∈ {command, pytest, probe, named-fitness}`,
of which **a1's one-shot(`pytest`/console-script)/probe forms are exactly the `pytest`/`command`/`probe` instances**
and **the navigator startd8-verb oracle is exactly the `command` instance**. One schema (det-req-kit SCHEMA.md),
one shared parser the SDK's two grammars converge on, one `kind`-aware liveness check. Additive; the existing a1
grammar and the existing `verify_gate: str` both stay valid.

## Overview

Define ONE canonical runnable-`verify.gate` in det-req-kit `SCHEMA.md`: a typed handle
`{ kind: command|pytest|probe|named-fitness, raw: string, [probe: {method,path,body?,expectedStatus}] }`, a strict
superset of today's bare `verify_gate: str` (an absent `kind` ⇒ untyped-legacy, still valid). Make the SDK's two
generation parsers (`oracle_loop/grammar.parse_verify_clause`, `navigator/det_req.parse_gate`) emit the typed
handle — a1's `one-shot`→`pytest`/`command`, a1's `service`→`probe`, the navigator startd8-verb span→`command`.
Make the governance liveness check (`govern.py:_gate_liveness`) `kind`-aware over the SAME typed handle so a
`pytest`/`probe` gate is `live`, not a false `dead-structural` GAP. Keep it additive, backward-compatible, and
advisory. The schema field is a cross-repo proposal to det-req-kit (kit owner's go); the parsers + the
`kind`-aware liveness are SDK-side.

## Objectives

- **O-1:** One schema both sides consume — target: a single typed `verify.gate` in det-req-kit SCHEMA.md that the oracle-loop runner (generation) AND the det-req-kit liveness check (governance) both read; a1's forms are its enumerated instances.
- **O-2:** The false-GAP class is closed — target: a `pytest`/`probe`/console-script gate classifies `live` under the governance liveness check, not `dead-structural`; the startd8-verb `command` still classifies `live`.
- **O-3:** Additive + backward-compatible — target: the existing a1 grammar, the existing `verify_gate: str`, and every current corpus REQ stay valid unchanged; an absent `kind` is untyped-legacy, never a break; no rewrite is forced.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| coordination | The typed `verify.gate` is a det-req-kit (dev-os) SCHEMA.md addition — cross-repo, not SDK-owned | NR-5/FR-4: the schema field is the kit owner's (Kagami/Mottainai) go; the SDK ships only conforming parsers + the kind-aware check; this REQ is honestly a PROPOSAL to the kit for the schema half | high |
| scope | Re-forking what Kagami just de-forked — a second SDK-local gate schema | FR-4/NR-6: the schema SSOT stays det-req-kit SCHEMA.md §5; the SDK does NOT define a rival schema, it emits the kit's shape | high |
| quality | The liveness check keeps false-GAP-ing a1's forms (the grounded defect) if the kind-awareness lands without the shared parser | FR-3/FR-5: the check dispatches on the typed `kind`, not on the startd8-only `_ALLOWED_VERBS`; a1's parser is the resolver for `pytest`/`probe` kinds | high |
| scope | A gate dispatch/execution framework (the over-abstraction the finding + REQ-22 forbid) | NR-2/NR-4: `verify.gate` stays a plain typed value object (a tagged union), not an executor registry; execution reuses the two existing sandboxes | medium |
| integrity | Silently coercing a malformed gate to a valid kind (a false-live) | FR-2/FR-8: an unparseable/kind-mismatched gate is `manual`/untyped-residue → reported, never silently promoted to live (mirrors a1's `manual` + verify_oracle's `manual`) | high |
| security | Broadening execution surface by unifying verb sets | NR-3: unification is of the SCHEMA + classification only; execution security stays per-runner (a1: sandbox exec + data-only probe; navigator: read-only startd8 allow-list) — no runner inherits another's execution authority | high |

## Functional requirements

- **FR-1 — State the a1⇄verify.gate delta precisely.** Record that a1 is a typed 2-form executable grammar (one-shot argv + data-only probe struct) with its own parser while `verify.gate` is a generic untyped runnable-handle string, so they are the instance layer and the placeholder layer of one idea, not rivals nor identical. Name: The REQ states that a1 is a typed instance-set and verify.gate is an untyped handle so they are not identical and not competing. Touches: `docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md`. Lives: doc docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md. Approve?: is the a1 vs verify.gate delta stated as instance-set vs untyped-handle rather than equal or competing?. Verify: `§0 and Appendix A state the delta as a1=typed-instances vs verify.gate=untyped-handle; a reader can quote the one-line delta from the doc without inferring it`. Serves: O-1
- **FR-2 — The canonical typed `verify.gate` shape.** Define one `verify.gate` = a typed handle `{ kind ∈ {command,pytest,probe,named-fitness}, raw: string, probe?: {method,path,body?,expectedStatus} }`, a strict superset of the bare `verify_gate: str` (an absent `kind` ⇒ untyped-legacy, still valid), of which a1's one-shot(`pytest`/console-script)→`pytest`/`command`, a1's `service`→`probe`, and the navigator startd8-verb span→`command` are the enumerated instances. Name: The canonical verify.gate is a typed tagged-union handle whose kinds are exactly a1s forms plus named-fitness. Touches: `dev-os/det-req-kit/SCHEMA.md`, `dev-os/det-req-kit/requirement.schema.json`. Lives: doc docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md. Approve?: is verify.gate a typed tagged union whose kinds are a1s forms plus named-fitness with an untyped-legacy fallthrough?. Verify: `Appendix B specifies the typed handle with kind ∈ {command,pytest,probe,named-fitness}, a probe sub-struct matching a1 ProbeSpec, and an absent-kind untyped-legacy rule; the four kinds cover both a1 forms and both existing oracles`. Serves: O-1
- **FR-3 — Name the false-GAP hazard the shared shape closes.** Record that today `govern.py:_gate_liveness` reuses `verify_oracle._classify_clause` (`_ALLOWED_VERBS={"startd8"}`), so a `pytest`/`probe` gate classifies NON-command → `dead-structural` → a false GAP, meaning the governance liveness check would red-flag exactly the forms the a1 generation runner executes successfully. Name: The REQ names the false-GAP hazard where the startd8-only classifier red-flags a1s pytest and probe gates as dead. Touches: `docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md`, `src/startd8/navigator/govern.py`. Lives: code src/startd8/navigator/govern.py. Approve?: does the REQ name the startd8-only-classifier false-GAP hazard as the load-bearing defect?. Verify: `the REQ cites govern.py:_gate_liveness reusing verify_oracle._classify_clause with _ALLOWED_VERBS={"startd8"} and states a pytest/probe gate falls to dead-structural today`. Serves: O-2
- **FR-4 — Schema SSOT is det-req-kit; SDK parsers conform.** Place the typed `verify.gate` schema in det-req-kit `SCHEMA.md` §5 as the single source of truth (owner Kagami/Mottainai), and make the SDK's `oracle_loop/grammar.py` + `navigator/det_req.parse_gate` conforming PARSERS that emit the kit's shape rather than a rival SDK-local schema. Name: The typed verify.gate schema is single-sourced in det-req-kit SCHEMA.md and the SDK grammars become conforming parsers. Touches: `dev-os/det-req-kit/SCHEMA.md`, `src/startd8/oracle_loop/grammar.py`, `src/startd8/navigator/det_req.py`. Lives: doc docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md. Approve?: is det-req-kit SCHEMA.md the schema SSOT with the SDK grammars as conforming parsers not a rival schema?. Verify: `the REQ assigns schema ownership to det-req-kit SCHEMA.md §5 (Kagami/Mottainai) and designates grammar.py + parse_gate as conforming parsers, with no second SDK-local schema defined`. Serves: O-1
- **FR-5 — `kind`-aware liveness closes the false-GAP.** Specify that `govern.py:_gate_liveness` dispatches on the typed `verify.gate.kind` — using `oracle_loop.grammar` as the resolver for `pytest`/`console-script`/`probe` kinds and `verify_oracle` for the `command` (startd8-verb) kind — so a `pytest`/`probe` gate resolves `live`, an unresolvable one stays `dead-structural`, and the startd8-verb `command` still resolves `live`. Name: The liveness check dispatches on verify.gate.kind reusing a1s parser for pytest and probe so those gates resolve live. Touches: `src/startd8/navigator/govern.py`, `src/startd8/navigator/verify_oracle.py`, `src/startd8/oracle_loop/grammar.py`. Lives: code src/startd8/navigator/govern.py. Approve?: does the liveness check resolve a pytest or probe gate as live by dispatching on kind rather than the startd8-only verb set?. Verify: `probe GET /health -> 200` — the REQ specifies a probe/pytest gate resolves live via oracle_loop.grammar while a malformed one stays dead-structural and the startd8-verb command stays live. Serves: O-2
- **FR-6 — Scope the THREE oracles honestly.** Record that three verify-classifiers exist — `navigator/verify_oracle.classify` (startd8-verb, SDK self-check), `oracle_loop/grammar.parse_verify_clause` (a1, generated-app fitness), and the det-req-kit `verify-liveness` check (governance) — and that this reconciliation unifies a1⇄verify.gate under one typed schema + shared parser where the navigator startd8-verb oracle is the `command` instance, NOT deleting or rewriting any of the three. Name: The REQ enumerates the three oracles and scopes reconciliation to a1-verify.gate under one schema with the navigator oracle as the command instance. Touches: `docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md`. Lives: doc docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md. Approve?: does the REQ scope the three oracles honestly with the navigator oracle as a command instance rather than a deletion?. Verify: `Appendix C tabulates the three oracles (verify_oracle / grammar / verify-liveness) with their verb sets and maps each to a canonical kind, deleting none`. Serves: O-3
- **FR-7 — Adoption is additive on a still-empty field.** Specify that the typed gate is adopted additively — the a1 oracle-loop specs become the first typed-gate corpus for free, the `verify_gate: str` field stays valid with `kind` absent (untyped-legacy), and REQ-27's measured 0/180 adoption means there is no migration debt to unwind. Name: Adoption is additive with a1 specs the first typed corpus and the untyped legacy field still valid so no migration debt exists. Touches: `docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md`, `docs/design/requirements-visualization/REQ-27-self-dogfood-verify-gate-adoption.md`. Lives: doc docs/design/runnable-verify-reconciliation/REQ-01-runnable-verify-schema-reconciliation.md. Approve?: is adoption additive on an empty field with a1 specs the first typed corpus and no forced rewrite?. Verify: `the REQ states verify.gate adoption is 0/180 (REQ-27) so typing is migration-free, a1 specs are the first typed corpus, and an absent kind stays valid`. Serves: O-3
- **FR-8 — Malformed gate is residue, never silently promoted.** Specify that a gate that neither parses under a1's grammar nor matches a startd8-verb command nor a named-fitness reference is classified `manual`/untyped-residue and REPORTED, never coerced to a valid `kind` (mirroring a1's `manual` and verify_oracle's `manual`), so unification never manufactures a false-live. Name: A gate that matches no kind is reported as manual residue and never silently coerced to a live kind. Touches: `src/startd8/oracle_loop/grammar.py`, `src/startd8/navigator/govern.py`. Lives: code src/startd8/oracle_loop/grammar.py. Approve?: is a no-kind-match gate reported as residue rather than coerced to a live kind?. Verify: `a gate matching no kind (bad probe / non-startd8 verb / unknown fitness) is classified manual/untyped-residue and reported, never promoted to live — matching a1 KIND_MANUAL and verify_oracle KIND_MANUAL`. Serves: O-2

## Non-requirements

- **NR-1:** Does NOT block the build — the reconciled liveness check stays advisory (candidate/gap), consistent with REQ-07 NR-1; a dead gate routes to a human decision, it does not halt a pipeline.
- **NR-2:** Does NOT build a gate dispatch/execution framework — `verify.gate` is a plain typed value object (a tagged union); execution reuses the two existing sandboxes (a1's `run_sandboxed`/`run_service_sandboxed`, the navigator read-only allow-list). The over-abstraction guard from the finding + REQ-22 NR-4 holds.
- **NR-3:** Does NOT broaden any runner's execution authority — the unification is of SCHEMA + classification; a1 keeps its sandbox-exec + data-only probe, the navigator keeps its read-only startd8 allow-list; no runner inherits another's verbs at execution time.
- **NR-4:** Does NOT re-author any existing `Verify:` prose — the typed `verify.gate` is a handle beside the prose; the prose acceptance statement stays the human-readable residue (mirrors REQ-22 NR-5 / REQ-27 NR-5).
- **NR-5:** The typed `verify.gate` schema is a det-req-kit (dev-os) SCHEMA.md addition — cross-repo, needs the kit owner's (Kagami/Mottainai) go; this REQ is honestly a PROPOSAL for that half. Only the conforming parsers + the `kind`-aware liveness check are in-scope for startd8.
- **NR-6:** Does NOT define a rival SDK-local gate schema — the SDK emits the kit's shape; re-forking what the 2026-08-15 Kagami de-fork just unified is explicitly out of scope.
- **NR-7:** Does NOT delete or rewrite any of the three oracles — `verify_oracle`, `grammar`, and the `verify-liveness` check all stay; they are re-expressed as consumers of one typed `kind`.

## Contract projection

**Backend:** `python-cli-surface` — the reconciliation surfaces through the SDK's console entrypoints + the
det-req-kit CLI. `Touches:` names bind to these entries.

| kind | entries | note |
|------|---------|------|
| `console-script` | `startd8` (`startd8 navigator …`), `extract` (det-req-kit `extract.py`) | the two consuming binaries — SDK navigator + kit extractor |
| `command` | `navigator build`, `navigator govern`, `navigator verify` | the govern/liveness + oracle surfaces where the `kind`-aware check lands |
| `option` | `--run-oracle`, `--format json` | opt-in execution + machine-readable verdict (existing flags) |
| `exit-class` | `0 ok`, `1 advisory-gap` | the liveness check is advisory — a gap is reported, not a hard non-zero build fail |

Cross-repo note: the schema half (`dev-os/det-req-kit/SCHEMA.md` §5, `requirement.schema.json`) is a
det-req-kit projection entry (`verify` field), NOT a `python-cli-surface` entry — it is the PROPOSAL surface
(FR-2/FR-4), owned by the kit, cited not owned here.

## Appendix A — the a1 ⇄ verify.gate delta (the reconciliation's central table)

| dimension | `a1` (`oracle_loop/grammar.py`) | `verify.gate` (CL-55 / REQ-22, `det_req.parse_gate`) |
|---|---|---|
| what it is | a **typed 2-form executable grammar** | a **generic runnable-handle string** ("a command / test id / named fitness function") |
| representation | `ParsedClause{ kind ∈ one-shot\|service\|assertion\|manual, command_argv, probe: ProbeSpec }` | `verify_gate: str` (bare) |
| runnable forms | `one-shot` (`pytest`/`python`/console-script argv) + `service` (`probe METHOD /path [body] -> STATUS` → data-only `ProbeSpec`) | none typed — a raw string classified downstream |
| its own parser | **yes** — `parse_verify_clause` (distinct from `classify`) | no — `parse_gate` just pulls the substring into a `str` |
| runner | `benchmark_matrix.sandbox.run_sandboxed` (rc0) + `run_service_sandboxed` (fixed loopback httpx) | none — `govern._gate_liveness` *guesses* runnability via `verify_oracle._classify_clause` (startd8-only) |
| verb authority | `_ONESHOT_VERBS = {pytest, python, python3}` + console-script + `_PROBE_METHODS` | `_ALLOWED_VERBS = {startd8}` (borrowed from `verify_oracle`) |
| residue | `assertion` (prose) / `manual` (rejected) | — (untyped) |

**Delta (the one-line answer):** `a1 ≠ verify.gate`. a1 is the **realized, typed instance-set**; verify.gate is
the **generic untyped placeholder**. a1's `one-shot`/`service` forms ARE concrete instances of the runnable
handle CL-55 asked for — but verify.gate was shipped without the typing that would let the governance side
recognize them. **They converge iff verify.gate becomes the typed superset (Appendix B) whose enumerated
instances are exactly a1's forms.**

## Appendix B — the canonical typed `verify.gate` (proposal to det-req-kit SCHEMA.md §5)

```
verify.gate := {
  kind:  "command" | "pytest" | "probe" | "named-fitness"   # REQUIRED when gate present-and-typed;
                                                             # ABSENT ⇒ untyped-legacy (bare str, still valid)
  raw:   string                                              # the authored handle, verbatim (residue-safe)
  probe: { method, path, body?, expectedStatus }?           # present iff kind == "probe" (mirrors a1 ProbeSpec)
}
```

- `kind: command` — a startd8-verb (or other allow-listed console) one-shot. **Instance of:** the navigator
  `verify_oracle` `command` + a1's console-script one-shot. Resolver: `verify_oracle` (read-only allow-list).
- `kind: pytest` — a `pytest …` one-shot (a1's power path). **Instance of:** a1 `one-shot`. Resolver:
  `oracle_loop.grammar` → `run_sandboxed`.
- `kind: probe` — a data-only HTTP probe. **Instance of:** a1 `service`. Resolver: `oracle_loop.grammar._parse_probe`
  → `run_service_sandboxed`. `probe` sub-struct = a1's `ProbeSpec` fields.
- `kind: named-fitness` — a named fitness-function reference (CL-55's third form). No a1 instance yet; reserved,
  resolves via a named-registry lookup (a plain reference, NOT a dispatch framework — NR-2).
- **absent `kind`** — the shipped `verify_gate: str` — untyped-legacy, still valid; `_gate_liveness` falls back
  to today's startd8-only classification for it. Backward-compatible by construction (O-3).

**Rule (FR-8):** a present gate whose `raw` matches no `kind` resolver is `manual`/untyped-residue — reported,
never coerced to a live `kind`.

## Appendix C — the three oracles, mapped to canonical kinds (scope honesty, FR-6)

| oracle | file | verb/form authority | canonical role after reconciliation |
|---|---|---|---|
| navigator verify_oracle | `navigator/verify_oracle.py` | `_ALLOWED_VERBS = {startd8}` | the `command` kind's resolver (SDK self-check); **kept, not deleted** |
| oracle-loop `a1` grammar | `oracle_loop/grammar.py` | `{pytest,python,python3}` + console-script + `{GET,POST,PUT,PATCH,DELETE}` probe | the `pytest`/`command`(console-script)/`probe` kinds' resolver (generated-app fitness); **kept** |
| det-req-kit verify-liveness | `navigator/govern.py:_gate_liveness` + kit `SCHEMA.md` | today borrows `verify_oracle` (startd8-only) → **the false-GAP source** | becomes `kind`-aware: dispatches to the two resolvers above per `verify.gate.kind` (FR-5) |

**Scope statement:** this reconciliation unifies **a1 ⇄ verify.gate** under **one typed schema + one shared,
`kind`-dispatched parser**. It does **not** merge the three oracles into one function — it re-expresses them as
**resolvers keyed by the one canonical `kind`**. The navigator startd8-verb oracle survives as the `command`
resolver; a1 survives as the `pytest`/`probe` resolver; the governance check stops false-GAP-ing by dispatching
on `kind` instead of the startd8-only verb set.

## Appendix D — Convergent-Review cross-model memory

### A — Accepted
*(none yet — R1 pending)*

### B — Rejected (with rationale)
*(none yet — R1 pending)*

### C — Incoming
*(review rounds append here)*
