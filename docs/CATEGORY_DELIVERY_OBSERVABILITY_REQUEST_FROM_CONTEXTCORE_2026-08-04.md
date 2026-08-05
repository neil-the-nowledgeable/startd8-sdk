> ## ✅ RESOLVED — 2026-08-05
>
> Delivered by **startd8-sdk PR #381** (`DELIVERY = "delivery_observability"` in
> `src/startd8/observability/taxonomy_enums.py`, now on `main`). The §5 acceptance passes —
> `"delivery_observability" in {c.value for c in Category}` → `True` — so ContextCore's Feature/Delivery
> Observability **Phase 2** facet flip is unblocked. The optional §3 grouping (`metrics_awaiting_category_home`)
> was taken. This request doc is retained as the incoming-request + resolution record.

---

# SDK Capability Request — add `delivery_observability` to the `Category` taxonomy

**From:** ContextCore (downstream consumer of `startd8.observability.taxonomy_enums.Category`)
**To:** startd8-sdk / SDK team (taxonomy owner)
**Date:** 2026-08-04
**Priority:** low — **Phase-2 enabler, not a Phase-1 blocker** (see §4)
**Size estimate:** **XS** (~2 lines, no ripple — see §3)

---

## 1. The ask

Add one member to the observability `Category` enum:

```python
# src/startd8/observability/taxonomy_enums.py
class Category(str, Enum):
    SERVICE          = "service_observability"
    BUSINESS         = "business_observability"
    PIPELINE_INNATE  = "pipeline_innate"
    PROJECT          = "project_observability"
    AI_AGENT         = "ai_agent_observability"
    DELIVERY         = "delivery_observability"   # <-- requested (member name your call)
```

…and bump the class docstring from *"The 5-category observability taxonomy"* to *"6-category"*.

That is the whole required change. **ContextCore is not asking the SDK team to build anything else** —
no generators, no descriptors, no dispatch. We only need `delivery_observability` to be a *valid member*
of the vocabulary the SDK owns.

## 2. Why ContextCore needs it

ContextCore treats `startd8...Category` as the single source of truth for the Node-taxonomy **Category
facet** carried by an `Objective` (`ContextCore/src/contextcore/models/manifest.py`). The facet validator
is correct-by-construction when startd8 is importable:

```python
def _known_categories():        # contextcore/models/manifest.py
    from startd8.observability.taxonomy_enums import Category
    return {c.value for c in Category}      # membership is enforced here
```

ContextCore's **Feature / Delivery Observability** feature declares delivery goals as ordinary `Objective`s
carrying a category facet (exactly as its Business Observability feature already uses
`business_observability`). **Phase 2** of that feature covers *feature/product delivery* — milestone/epic
pace, a product-request queue, a unified rollup — which is broader than the existing
`ai_agent_observability` value and wants its own umbrella concept-key: `delivery_observability`.

Without the member, `Objective(category="delivery_observability")` raises in any environment where startd8
is installed (correct-by-construction rejecting an unknown facet). We do **not** want to work around this
with a fail-open literal — that would only "pass" in CI (where startd8 is absent) and break on every
developer machine that has the SDK. Owning the vocabulary is the SDK's job; hence this request rather than
a downstream hack.

## 3. Size / ripple analysis (grounded in the SDK tree, 2026-08-04)

**XS — the enum stands alone; a new value needs no per-category wiring.** Verified:

| Checked | Finding |
|---------|---------|
| `observability/manifest.py` | **No** per-`Category` descriptor table (`grep 'Category\.'` → none). A new value needs no descriptor entry. |
| `observability/artifact_generator.py` / `_generators.py` | **No** exhaustive switch on Category values that a new member would break. The only value-specific site is `artifact_generator.py:2365` — a grouping `r.get("category") in (Category.PROJECT.value, Category.AI_AGENT.value)`. |
| exhaustiveness tests | No test iterates `for c in Category` asserting `len == 5`; the "5-category" claim lives only in the docstring. |
| `str`-valued enum | Descriptor fields typed `str` accept the new member and serialize transparently — no type changes. |

**One optional decision (SDK team's call, not required by ContextCore):** should `delivery_observability`
join the project-scoped grouping at `artifact_generator.py:2365` alongside `PROJECT`/`AI_AGENT`? That is a
one-line choice that affects *startd8's own artifact generation* for this category, and only matters if the
SDK later generates artifacts for delivery-category objectives. ContextCore's facet validation does not
depend on it.

**Rough effort:** ~2 lines of change + 1 doc/CHANGELOG line + (optionally) 1 line at :2365 + a one-line
enum-membership test. Well under an hour including review.

## 4. Phase-1 is NOT blocked — what ContextCore is doing meanwhile

ContextCore's Feature Observability **Phase 1** (the agent-productivity hero: agent work-sessions, agent
output, agent goals, the `delivery agents` board) is **entirely agent-scoped**, so it rides the **existing**
`ai_agent_observability` value — correct-by-construction today, zero SDK dependency. We are proceeding on
that now.

This request only unblocks **Phase 2** (feature/product delivery beyond agents). There is no schedule
pressure; land it whenever it fits the SDK team's queue. When it lands, ContextCore will switch the Phase-2
objectives' facet to `delivery_observability` and note the version in its plan.

## 5. Acceptance (how ContextCore will verify once it lands)

```python
from startd8.observability.taxonomy_enums import Category
assert "delivery_observability" in {c.value for c in Category}

# and, in ContextCore where startd8 is importable:
from contextcore.models.manifest import Objective
Objective(id="OBJ-DELIVERY", description="…", category="delivery_observability")   # no longer raises
```

## 6. Contact / provenance

Raised by the ContextCore Feature Observability build. Design context (ContextCore repo):
`docs/design/requirements/REQ_FEATURE_OBSERVABILITY.md`,
`docs/plans/FEATURE_OBSERVABILITY_PLAN.md` (Phase 2, G10–G13),
`docs/plans/FEATURE_O11Y_SESSION_HANDOFF_G1.md`.
Follows the existing consumer-feedback convention (`docs/NAVIG8_FEEDBACK_FROM_CONSUMER_2026-07-10.md`).
