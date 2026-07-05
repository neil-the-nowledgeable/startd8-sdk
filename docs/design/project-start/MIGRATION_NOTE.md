# Project-Start Distillation — Migration Note & Removal Criteria

> **Parent milestone M5** (`PROJECT_START_PLAN.md`) — satisfies **FR-9, FR-10,
> FR-11, FR-12, NR-5**. This note is the consumer-facing runbook for the
> kernel/guided distillation *and* the codified, CRP-corrected criteria for a
> **future, separate** deletion PR. **Nothing is deleted in this change (NR-5).**
> Everything is retained behind hidden aliases (one-release window) or consolidated
> into the guided experience.

## TL;DR — is anything broken for me today?

**No.** Every prior surface still resolves. The kernel was *renamed* (`concierge` →
`kickoff`), the compensatory metaphor tooling was *demoted* (`kickoff` →
`kickoff-legacy`), and Welcome Mat / Red Carpet / the Stakeholder Panel were
*consolidated* into one optional `kickoff guided` experience — all behind hidden
aliases that keep old CLI names, MCP `action` enum values, and the always-on
`project init` VIPP posting working for **one release**. Migrate at your leisure
before the alias window closes.

---

## What changed (surface-by-surface)

| Old surface | New surface | Alias today? | Migrate to |
|-------------|-------------|--------------|------------|
| `startd8 concierge <verb>` (CLI group) | `startd8 kickoff <verb>` | **Yes**, hidden group + stderr deprecation notice | `startd8 kickoff …` |
| `startd8 concierge instantiate-kickoff` | `startd8 kickoff instantiate` | **Yes** (subcommand kept on the hidden `concierge` group) | `startd8 kickoff instantiate` |
| `startd8 concierge derive-contract` | `startd8 kickoff derive` | **Yes** (subcommand kept on the hidden `concierge` group) | `startd8 kickoff derive` |
| MCP `ConciergeInput.action = "instantiate-kickoff"` | `action = "instantiate"` | **Yes**, dispatches + `DeprecationWarning` (`_ACTION_ALIASES`, `concierge/core.py`) | `action="instantiate"` |
| MCP `action = "derive-contract"` | `action = "derive"` | **Yes**, aliased in `_ACTION_ALIASES` (CLI-only per FR-C8; not on the MCP enum) | `action="derive"` (CLI) |
| `startd8 kickoff <metaphor>` (old metaphor group: `check`/`red-carpet`/`start`/`plan`/…) | `startd8 kickoff-legacy <metaphor>` | **Yes**, group renamed + stderr deprecation notice | `startd8 kickoff-legacy …` (transitional) or the consolidated `startd8 kickoff guided` |
| `startd8 panel <verb>` (top-level group) | `startd8 kickoff panel <verb>` | **Yes**, hidden `panel` alias group | `startd8 kickoff panel …` |
| Welcome Mat serve/web + Red Carpet conductor + Stakeholder Panel (separate metaphors) | one **optional** `startd8 kickoff guided` experience (Orient → Guide → Deepen) | n/a — code retained & consolidated, not deleted | `startd8 kickoff guided` |
| Teian point-value drafter (`panel recommend`) | **dropped** (the ghost; NR-7) — its $0 coverage *signal* is retained as the discovery trigger | n/a | (no replacement — point-value drafting was the accidental complexity) |
| `project init` (always posts VIPP) | VIPP is now **opt-in** (`--with-vipp`) | **Yes** — old invocation keeps posting VIPP **by default** until the alias window closes | add `--with-vipp` |

---

## Consumer-by-consumer impact

### navig8 — **kernel-only; zero impact (FR-11)**

navig8 (the legal-intake instantiation that defined the Concierge feature) uses
**only the two write verbs** the kernel exposes: `instantiate` (scaffold the input
package) and `derive` (derive the contract). Both of the old names it may have
scripted — `concierge instantiate-kickoff` / `concierge derive-contract` (CLI) and
the `instantiate-kickoff` MCP `action` value — **still resolve** through the hidden
CLI aliases and the `_ACTION_ALIASES` MCP map. navig8 therefore has **zero required
change today**; it should adopt `kickoff instantiate` / `kickoff derive` (and MCP
`action="instantiate"`) before the alias window closes. navig8 never consumed
Welcome Mat serve, the ranked Red Carpet playbook, or the Stakeholder Panel, so the
consolidation is invisible to it.

- **Known capability loss (FR-5a, skipped):** the *only* place that computed the
  **$0 schema-shape diagnostics** — missing-FK, no-PK, island tables, empty enum —
  was Red Carpet's `_schema_advisories` (`kickoff_experience/red_carpet_advisor.py:181-250`).
  M1 **did not port** it into the kernel `assess` (the optional ~90-LOC port under
  FR-5a was skipped). So a consumer that relied on Red Carpet surfacing schema-shape
  problems **no longer gets that signal from the kernel**. There is **no evidence
  navig8 depended on it** (it drives instantiate/derive, not schema linting), so the
  net navig8 impact remains zero — but the capability loss is recorded here per
  FR-5a's "accept the loss and name it explicitly in the migration note." Red Carpet
  code is retained (NR-5), so the diagnostic can be re-surfaced or ported later if a
  consumer need appears.

### household-o11y & benchmark portal — **zero break today; migrate before window close**

Both reach VIPP through `project init`'s always-on posting (§0.3). Two changes could
have double-broken them — the `project init` **scope-out** (VIPP un-bundled, M3/FR-1a)
and the **opt-in flip** (VIPP no longer posts by default, FR-14) — landing in the same
release. The **consumer-safe alias window (M3)** prevents this: the *old* `project init`
invocation **keeps posting VIPP by default** until the alias window closes, and emits a
deprecation notice.

- **Migration path:** adopt **`project init --with-vipp`** (explicit opt-in) before
  the alias window closes. After that, the default `project init` is the un-bundled
  kernel-setup path and will **not** post VIPP.

### Scripted / MCP callers (any) — **zero break today**

Anything keying on the MCP `ConciergeInput.action` **string** keeps working: the old
`"instantiate-kickoff"` enum value still dispatches (mapped to `instantiate` with a
`DeprecationWarning` by `_ACTION_ALIASES`, `concierge/core.py`). Update to the
canonical `"instantiate"` value before the window closes. (`derive`/`derive-contract`
is CLI-only over MCP by design — FR-C8 keeps the MCP action set a tight read/preview
floor — so `derive-contract` is aliased only on the CLI/`_ACTION_ALIASES` side.)

---

## Removal criteria (FR-12, CRP-corrected)

The retained/consolidated code becomes **eligible for a later, separate deletion PR**
only when **all** of the following are **jointly** true:

1. **Kernel + guided shipped as the documented surface.** `startd8 kickoff`
   (`survey`/`assess`/`instantiate`/`derive`) and `startd8 kickoff guided` are the
   documented, shipped onboarding surface (FR-9 gate).
2. **Consumer(s) migrated.** Every documented consumer (navig8; household-o11y;
   benchmark portal) has moved to the new verbs / to `project init --with-vipp`, so
   no documented consumer resolves to a retiring path.
3. **No live caller resolves to the retiring code** — verified by **grep across the
   three real registries** (R1-F1 correction):
   - **CLI subcommand set** — no non-deprecated command still routes to the retiring
     modules (`red_carpet*`, the demoted metaphor group, the Teian drafter).
   - **MCP `ConciergeInput.action` enum** — no `action` value (incl. the deprecated
     `instantiate-kickoff`) is still required; the alias window has closed.
   - **Documented consumers** — the §0.3 apps above.

> **CRP fix (R1-F1):** the criterion is **NOT** "no external caller in the
> `startd8.contractors.deterministic_providers` entry-point group." The retiring
> surfaces are **CLI/MCP commands**, not deterministic-provider plugins, so that gate
> **passes vacuously** while a live CLI/MCP caller still exists. The gate is the
> three registries above.

### Detection trigger (FR-12 / R2-F1) — so satisfaction is *noticed*, not passive

A passive checklist is a "delete when you feel like it" policy. The satisfaction of
the criteria is actively surfaced by a **test-backed detection trigger**:

- **`tests/unit/concierge/test_removal_criteria_trigger.py`** enumerates the current
  deprecated-alias surfaces (the CLI alias groups + subcommands, the MCP
  `_ACTION_ALIASES` map, the `ConciergeAction` deprecated enum value, and the
  `--with-vipp`/default-posting seam) and **asserts they still resolve** (NR-5: nothing
  deleted yet). It emits a **removal checklist** (the caller inventory a future
  deletion PR must clear). When the alias window closes and the aliases are removed,
  these assertions **flip to failing** — a loud, dated, CI-visible signal that (a) the
  window is being closed and (b) the removal-criteria grep now has a concrete target
  list. It is the forcing function that a checklist alone lacks.

- **Activation mechanism:** the future deletion PR's checklist is exactly the list this
  test prints. A reviewer runs the trigger, confirms every enumerated surface is either
  (i) still needed → deletion blocked, or (ii) has zero live callers across the three
  registries → deletion authorized for that surface. No code is deleted until the
  trigger's enumerated surfaces each clear the three-registry grep.

---

## What is explicitly **not** in this change (NR-5)

- No module is deleted. Welcome Mat, Red Carpet (incl. `_schema_advisories`), the
  Stakeholder Panel, and the demoted metaphor group are **retained** — consolidated or
  aliased, not removed.
- Only the **Teian point-value drafter** is dropped (the ghost, NR-7) — and only its
  *drafting*; its $0 coverage *signal* survives as the discovery trigger.
- The deletion itself is a **later, separate PR**, gated on the criteria above and
  triggered by the detection test.
