# Author the `business.*` Weaver Semconv Registry Group — Requirements

**Project:** ContextCore (registry) + startd8-sdk (design home)   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-19
**Format:** det-req/0.1
**Backend:** otel-weaver-semconv
**Method:** `/reflective-instantiation` — the built registry groups predict the shape of the empty `business` cell (§A)
**Pairs with:** **`REQ-business-flow-and-flow-criticality.md`** (the carrier — its FR-1/FR-5/FR-9 reference this schema) · `DESIGN_business-dimension-roadmap.md` (the dimension adjudication) · `REFERENCE_weaver-loom-map-fidelity.md` (the Weaver mechanism) · `../contextcore-intro/REFERENCE_business-instrumentation-in-the-otel-model.md` (the `business.*` semconv namespace)
**Inherits standards:** OTel Weaver registry schema · the sibling groups' structure (`registry/{task,project,sprint,agent,lesson}.yaml`) · registry-mirrors-canonical-Python-enum discipline (`contextcore weaver check`) · the naming-collision + minimalism guardrails of `DESIGN_business-dimension-roadmap.md`
**Audience:** ContextCore contributors · platform/SRE
**Trust boundary:** the registry is DESCRIPTIVE metadata — authoring it changes no emission and no telemetry bytes
**Data classification:** internal; low-cardinality, non-PII dimensions only

> **Readable handle:** `feature/business-semconv-registry-group-1c8f1d6d`
> **Semantic name:** *ContextCore authors the `business.*` Weaver semantic-convention registry group, formalizing the already-emitted static attributes (criticality, value, owner, cost_center) plus the co-shipped dynamic pair (flow and flow.criticality), mirroring the canonical `Criticality`/`BusinessValue`/`OwnerRelation` enums in contracts/types.py, registering the closed enums in the weaver enum map so `contextcore weaver check` validates them in CI, and leaving `business.flow`'s app-declared values to live-check fidelity rather than weaver-enum validation, so the business dimension has one governed, versioned, CI-enforced vocabulary that the carrier and the fidelity gate both reference.*
> **Canonical ref:** `cc:intent:business-context:feature:business-semconv-registry`

## 0. Why this exists

The `business.*` namespace is **emitted today but ungoverned**. `detector.py` already stamps
`business.criticality`, `business.value`, `business.owner`, `business.cost_center` onto every signal (lines
205–208, 383–385), yet there is **no `registry/business.yaml`** — the manifest reserves it as a commented
Phase-2 line. So the registry *lags emission*: the four shipped attributes have no declared type, no
allowed-values, no `weaver check` coverage. This REQ closes that gap and lays the schema foundation the
dynamic axis (`REQ-business-flow-and-flow-criticality.md`) and the fidelity gate (its FR-9 / `weaver registry
live-check`) both depend on. It is **Decision 2** of `REFERENCE_weaver-loom-map-fidelity.md §4`: land the
reserved group.

## A. Reflective-instantiation (the method that sets the scope)

**Product space:** *ContextCore Weaver registry group = BOUNDED-CONTEXT × {attribute_group, prefix,
canonical-enum-mirror, `weaver check`-validated}.* **Invariant:** each group is a prefix-namespaced
`attribute_group` whose closed enums mirror a canonical Python enum in `contracts/types.py` and are validated
by `contextcore weaver check` (`_ATTRIBUTE_ENUM_MAP` in `cli/weaver.py`).

| Cell | Prefix | Enum mirror(s) | Built? |
|------|--------|----------------|--------|
| task | `task` | TaskType/TaskStatus/Priority/… | ✅ |
| project · sprint · agent | resp. | (agent.type→AgentType) | ✅ |
| lesson | `lesson` | LessonCategory/Source/Maturity/… | ✅ (experimental) |
| **business** | **`business`** | **Criticality · BusinessValue · OwnerRelation** | ⬜ (reserved) |

**Adjudication of the `business` cell's attributes (Phase 3):**

| Attribute | Verdict | Reason |
|---|---|---|
| `business.criticality` (static) | **natural-next — MUST** | already emitted by `detector.py`; registry lagging emission is a coverage gap. Mirrors `Criticality`. |
| `business.value`, `business.owner`, `business.cost_center` (static) | **natural-next — MUST** | same: shipped + emitted, unregistered. `value`→`BusinessValue`; `owner`/`owner_relation`→`OwnerRelation`. |
| `business.flow` (dynamic) | **natural-next (co-ship)** | the anchor of the dynamic column. **Open string, NOT a weaver enum** (values are app-declared in the route→flow map, not in `types.py`) → fidelity via `live-check`, not `weaver check`. |
| `business.flow.criticality` (dynamic) | **natural-next (co-ship)** | mirrors `Criticality`; **distinct name** from static `business.criticality` (the roadmap §4.2 collision fix, made concrete in the registry). |
| `business.compliance_scope` (obligation) | **earned-in — defer** | strongest next dim (roadmap), but earns its registration on its use case; reserve in comments. |
| `business.channel`, `business.tenant_tier`, `business.transaction_type` | **earned-in — defer** | roadmap "natural-next, soon-after"; author per named need. |
| `business.tier` | **correct-absence** | folds into criticality (roadmap verdict change); do not register a colliding dim. |

**The revealing-absence (the load-bearing seam):** `business.flow` exposes that a Weaver group has **one**
validation mechanism (closed-enum ⋈ `types.py`), but the business dimension needs **two** — closed enums
validated by `weaver check`, and the open app-declared `flow` validated by `live-check` against the route→flow
map. Naming this two-validator split is the instantiation's main structural finding (FR-5).

## Design decisions

- **Mirror, don't invent.** Enum members are copied from `contracts/types.py` (`Criticality`, `BusinessValue`,
  `OwnerRelation`); `contextcore weaver check` fails on any registry↔enum drift. No new enum is coined here.
- **Formalize the shipped four first.** The static attributes are already on the wire; registering them is
  pure catch-up and unblocks the reverse check ("emitted attributes exist in the registry").
- **Two validators, by design.** Closed enums → `weaver check` (CI, vs `types.py`). Open `business.flow` →
  `weaver registry live-check` (vs the app route→flow map). Never enum-validate `flow` against `types.py`.
- **Distinct names.** static `business.criticality` (resource) ≠ dynamic `business.flow.criticality` (baggage).
- **Descriptive only.** Authoring the registry changes no emission; telemetry is byte-identical.
- **Experimental + minimal.** `stability: experimental`; only the MUST + co-ship cells in v1; the rest reserved.

## Overview

Create `ContextCore/semconv/registry/business.yaml` as a `registry.business` `attribute_group` (prefix
`business`); formalize the four shipped static attributes and the two co-shipped dynamic attributes; register
the closed enums in `_ATTRIBUTE_ENUM_MAP`; wire `contextcore weaver check` in CI; leave `business.flow`'s
values to `live-check`; register the group in `registry_manifest.yaml`.

## Objectives

- **O-1:** The business dimension has one governed, versioned, CI-enforced vocabulary — target: `registry.business` exists, is manifest-registered, and `contextcore weaver check` validates its enums against `types.py`.
- **O-2:** The registry matches emission — target: every `business.*` attribute `detector.py` emits is declared in the group (no emitted-but-unregistered attribute).
- **O-3:** Additive and honest — target: no emission/telemetry change; `stability: experimental`; deferred dims reserved, not authored.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Registry enum drifts from the canonical `types.py` enum | FR-4: register in `_ATTRIBUTE_ENUM_MAP`; `weaver check` fails on drift in CI | high |
| quality | Dynamic flow criticality collides with static resource criticality | FR-3: distinct name `business.flow.criticality` | high |
| scope | Over-authoring deferred dims (compliance/channel/tenant) by symmetry | FR-6/NR-2: v1 = MUST + co-ship only; rest reserved-in-comments | medium |
| reliability | Mis-validating open `business.flow` values against a fixed enum | FR-5: `flow` is open string; fidelity via `live-check`, never `weaver check` | medium |

## Functional requirements

- **FR-1 — The `registry.business` group exists and is manifest-registered.** A `semconv/registry/business.yaml` file defines a `registry.business` `attribute_group` with `prefix: business` and `stability: experimental`, and the reserved `# - registry/business.yaml` line in `registry_manifest.yaml` is activated. Name: The business attribute_group exists and is registered in the Weaver manifest. Touches: `ContextCore/semconv/registry/business.yaml`, `ContextCore/semconv/registry_manifest.yaml`. Lives: config ContextCore/semconv/registry/business.yaml. Approve?: does a registered `registry.business` group exist following the sibling-group schema?. Verify: `contextcore weaver check` parses `business.yaml` and the manifest references it; an unregistered group file is not validated. Serves: O-1
- **FR-2 — Formalize the shipped static attributes so the registry matches emission.** The four attributes `detector.py` already emits — `business.criticality`, `business.value`, `business.owner`, `business.cost_center` — are declared in the group with types and briefs, closing the emitted-but-unregistered gap. Name: The already-emitted static business attributes are declared in the registry. Touches: `ContextCore/semconv/registry/business.yaml`, `ContextCore/src/contextcore/detector.py`. Lives: config ContextCore/semconv/registry/business.yaml. Approve?: does the registry declare every `business.*` attribute detector.py emits?. Verify: each of the four detector-emitted `business.*` attributes resolves to a registry member; an emitted attribute absent from the group is flagged by the registry's reverse-coverage check. Serves: O-2
- **FR-3 — Co-ship the dynamic pair with a non-colliding criticality name.** `business.flow` (open string) and `business.flow.criticality` (enum) are declared together, with `business.flow.criticality` named distinctly from the static resource-level `business.criticality` so a span can carry both. Name: The dynamic flow and flow-criticality attributes are declared with a distinct criticality name. Touches: `ContextCore/semconv/registry/business.yaml`. Lives: config ContextCore/semconv/registry/business.yaml. Approve?: are `business.flow` and a non-colliding `business.flow.criticality` both declared?. Verify: the group contains `business.flow` and `business.flow.criticality` as separate attributes, and `business.flow.criticality` differs in name from `business.criticality`. Serves: O-1
- **FR-4 — Closed enums mirror `types.py` and are `weaver check`-validated.** `business.flow.criticality` and `business.value` mirror the canonical `Criticality` and `BusinessValue` enums (and `business.owner_relation` mirrors `OwnerRelation` if authored); each is registered in `_ATTRIBUTE_ENUM_MAP` so `contextcore weaver check` fails on registry↔enum drift. Name: The closed business enums mirror the canonical Python enums and are validated in CI. Touches: `ContextCore/semconv/registry/business.yaml`, `ContextCore/src/contextcore/cli/weaver.py`, `ContextCore/src/contextcore/contracts/types.py`. Lives: code ContextCore/cli/weaver.py::_ATTRIBUTE_ENUM_MAP. Approve?: are the closed business enums mapped to their canonical Python enums and CI-checked?. Verify: adding a member to `business.yaml` absent from the `Criticality` enum makes `contextcore weaver check` fail; an in-sync group passes. Serves: O-1
- **FR-5 — `business.flow` is open and live-check-validated, not weaver-enum-validated.** `business.flow` is declared `type: string` (no `members:`), its values are the app-declared route→flow labels, and its fidelity is enforced by `weaver registry live-check` against the route→flow map (the carrier REQ's FR-9), never by `weaver check` against `types.py`. Name: The open business flow attribute is validated by live-check not by the weaver enum check. Touches: `ContextCore/semconv/registry/business.yaml`, `ContextCore/src/contextcore/cli/weaver.py`. Lives: config ContextCore/semconv/registry/business.yaml. Approve?: is `business.flow` an open string whose fidelity is a live-check concern, not a weaver-enum concern?. Verify: `business.flow` has no `members:` and is absent from `_ATTRIBUTE_ENUM_MAP`; an arbitrary app flow value does not fail `weaver check`; a live route unmapped in the flow map is a `live-check` divergence (per the carrier FR-9). Serves: O-1
- **FR-6 — Experimental, additive, deferred-dims reserved.** The group is `stability: experimental`, authoring it changes no emission (telemetry byte-identical), and the deferred dimensions (`business.compliance_scope`, `channel`, `tenant_tier`, `transaction_type`) are reserved as commented placeholders, not authored. Name: The group is experimental and additive with deferred dimensions reserved not authored. Touches: `ContextCore/semconv/registry/business.yaml`. Lives: config ContextCore/semconv/registry/business.yaml. Approve?: is the group experimental, emission-neutral, and free of prematurely-authored deferred dims?. Verify: emitting the same annotations before and after the group is authored yields byte-identical telemetry; the deferred dims appear only as comments. Serves: O-3

## Non-requirements

- **NR-1:** Does NOT author the dynamic CARRIER (seed/propagate/materialize/OTTL) — that is `REQ-business-flow-and-flow-criticality.md`. This REQ is the schema/vocabulary artifact only.
- **NR-2:** Does NOT populate the earned-in dims (`compliance_scope`, `channel`, `tenant_tier`, `transaction_type`) — reserved in comments; authored on their own use case per the roadmap.
- **NR-3:** Does NOT change `detector.py` emission or any telemetry — the registry is descriptive metadata; telemetry stays byte-identical.
- **NR-4:** Does NOT coin enum values — closed enums mirror `contracts/types.py`; open `business.flow` values live in the app route→flow map, never in `types.py`.
- **NR-5:** Does NOT build the generic multi-table join/registry engine (roadmap C3) — one group now; generalize only at ≥2 declared tables.
