# Demo Data — policy & registry

**One rule:** the SDK's product code carries **no demo domain**, and the repo stores **no rich demo
dataset**. Demos live in their own repos; this directory only *points* to them.

## The hybrid model

| Kind | Where it lives | Why |
|------|----------------|-----|
| **Neutral test fixtures** | in-repo, `tests/fixtures/**` | Small, domain-agnostic, self-contained so CI is hermetic (no dependency on a sibling repo). E.g. `tests/fixtures/kickoff_panel/complete_generic.json`. |
| **Rich, domain-specific demos** | their own repos, referenced by [`DEMO_REGISTRY.yaml`](DEMO_REGISTRY.yaml) | Real personas / kickoff inputs / captured sessions. Not copied in (avoids duplication + drift) and never a runtime/CI dependency. |
| **Product defaults** | *none* | Facilitation/kickoff context is **config-driven** from the project's own requirements/kickoff inputs — no baked demo domain. |

## Rules

1. **No demo domain in `src/`.** Product code must not hardcode a specific business/demo scenario as a
   default. (This is why the "Blue Planet Adventures" retail scenario was removed from
   `stakeholder_panel/facilitation.py` on 2026-07-07.)
2. **In-repo fixtures are neutral and minimal.** Model them on a real neutral project (the benchmark
   portal) or a synthetic generic one — never on a specific external demo dataset.
3. **Rich demos are referenced, not copied.** Add a record to `DEMO_REGISTRY.yaml`; do not vendor the
   dataset into the SDK.
4. **The registry is reference-only.** No product code path or test resolves a registry `lives_in`
   path. It's for humans/agents looking for a rich dataset to run a panel/kickoff against.

## Registry

See [`DEMO_REGISTRY.yaml`](DEMO_REGISTRY.yaml). Current entries:
- `retail-blue-planet` → `../contextcore-demo-retail` (the origin of the retail demo; **preserved**, not deleted)
- `benchmark-portal` → the Summer 2026 reviewer portal (neutral, non-retail)
