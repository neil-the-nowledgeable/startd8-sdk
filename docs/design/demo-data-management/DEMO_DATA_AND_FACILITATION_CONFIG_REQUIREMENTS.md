# Demo-Data Management + Config-Driven Facilitation — Requirements

**Version:** 0.2 (Phase 1 + Phase 2 implemented)
**Date:** 2026-07-07
**Status:** WS1 + WS2 landed on `chore/demo-data-cleanup`; WS3 FR-11 (re-run portal panel) is Phase 3
**Owner:** startd8-sdk

> **Implementation status.**
> - **Phase 1 (WS1 + FR-5/9/10/12):** done — neutral fixtures + `docs/demos/` registry; baked
>   Blue Planet defaults removed from `facilitation.py`; doc references pointed at the registry;
>   origin demo registered, not deleted.
> - **Phase 2 (FR-6/7/8):** done — `stakeholder_panel/context_resolver.py` derives desc/objective/
>   strategy from `business-targets.yaml` (goals→objective/strategy) and an auto-discovered
>   requirements-doc overview (→desc), neutral placeholder only as a recorded last resort;
>   `run_kickoff_panel.py` wired (explicit args override). Verified against the real portal inputs.
>   - **OQ-1 resolved:** `desc` ← `business-targets.yaml` `description`/`summary` if authored, else the
>     requirements-doc overview paragraph, else the neutral artifact-deferring placeholder. **No new
>     kickoff domain added** (NR-5 held).
>   - **OQ-5 resolved:** thin parser — heading-anchored (Problem Statement/Overview) first-paragraph
>     extraction, bounded to one line; no structured requirements grammar.
> - **Phase 3 (FR-11):** pending — delete + cleanly re-run the portal's contaminated panel session.
**Origin:** Cleanup of "Blue Planet Adventures" retail-demo contamination that leaked into the SDK
panel/facilitation path while testing the panel against a richer dataset than the benchmark portal.

---

## 1. Problem Statement

The ContextCore **retail demo** ("Blue Planet Adventures") — a legitimate, separate project in
`contextcore-demo-retail/` — leaked into the SDK when it was used as a rich dataset to exercise the
stakeholder panel. The leak has three shapes:

1. **Baked product default.** `stakeholder_panel/facilitation.py` hardcodes `DEFAULT_DESC` /
   `DEFAULT_OBJECTIVE` / `DEFAULT_STRATEGY` = the Blue Planet retail scenario. `FacilitationConfig`
   defaults its `desc`/`objective`/`strategy` to these, and `scripts/run_kickoff_panel.py` is the
   only constructor — so **any run that doesn't explicitly pass a domain silently facilitates against
   the retail demo.** This is the root cause of the benchmark-portal synthesis's "outdoor-gear
   retailer" framing mismatch.
2. **Retail test fixtures.** `tests/fixtures/kickoff_panel/complete_retail.json` (and, to a lesser
   extent, `thin_schema.json`) carry retail-demo content and are referenced 10+ times by
   `tests/unit/kickoff_view/test_kickoff_view.py`.
3. **Doc references.** Several `docs/design/**` files reference Blue Planet as "the demo used" or as a
   historical experiment record.

**Decisions already made (user):**
- **Demo-data home = hybrid** — neutral, self-contained fixtures live in-repo (CI-safe); rich external
  demos are referenced by a **pointer registry**, not duplicated.
- **Facilitation = config-required** — drop the baked demo defaults; **derive** the run context by
  parsing the project's requirements / kickoff inputs.
- **Docs = update** to reflect the agreed demo storage/management scheme.
- **The origin retail demo (`contextcore-demo-retail/` et al.) is NOT deleted** — it is registered as
  a pointer.

### Gap table

| Component | Current State | Target |
|-----------|--------------|--------|
| Facilitation context | Baked Blue Planet default; silent on omission | Required + derived from real inputs; neutral placeholder only, never a demo domain |
| Test fixtures | Retail-demo content, test-referenced | Neutral, self-contained, domain-agnostic fixtures |
| Rich demo datasets | Copied ad hoc / implied by defaults | Referenced via `DEMO_REGISTRY.yaml` pointers |
| Design docs | Blue Planet as running example | Neutral wording + a pointer to the registry; history annotated, not erased |

---

## 2. Requirements

### Workstream 1 — Demo-data management (hybrid)

- **FR-1 — Neutral in-repo fixtures.** Replace `complete_retail.json` with a domain-neutral,
  self-contained fixture (`complete_generic.json`) and neutralize `thin_schema.json`. Update
  `test_kickoff_view.py` to reference the new fixture(s). Tests remain hermetic (no external path).
- **FR-2 — Demo pointer registry.** Add `docs/demos/DEMO_REGISTRY.yaml`: one record per external demo
  — `{id, title, lives_in (repo-relative path), use_for, kickoff_inputs, notes}`. Seed it with
  `retail-blue-planet → ../contextcore-demo-retail` and `benchmark-portal →
  ../benchmarking/Summer2026-portal-rebuild`.
- **FR-3 — Registry is reference-only.** No product code or test imports resolve the registry's
  external paths at runtime/CI. It is documentation + an optional human/agent lookup. (A validator
  that the paths *exist* is a separate, opt-in dev tool — NR-4.)
- **FR-4 — Demo policy doc.** `docs/demos/README.md` states the policy: neutral fixtures live in-repo;
  rich, domain-specific demos live in their own repos and are referenced by the registry; product
  code carries **no** demo domain.

### Workstream 2 — Config-driven facilitation

- **FR-5 — Remove baked demo defaults.** Delete `DEFAULT_DESC`/`DEFAULT_OBJECTIVE`/`DEFAULT_STRATEGY`
  (the Blue Planet strings) from `facilitation.py`. No demo domain remains in product code.
- **FR-6 — Context is required, not demo-defaulted.** `FacilitationConfig` no longer supplies a
  domain-specific default for `desc`/`objective`/`strategy`. A run without resolvable context fails
  with a clear error (or falls to the FR-9 neutral placeholder) — it never silently adopts a demo.
- **FR-7 — Derive context from real inputs.** Provide a parser that resolves `desc`/`objective`/
  `strategy` from the project's actual kickoff inputs and/or a requirements doc:
  - `objective`/`strategy` ← the `business-targets.yaml` domain (goals/targets) where present;
  - `desc` ← a project brief source (see OQ-1);
  - the parser returns a typed result the `FacilitationConfig` consumes; missing pieces are reported,
    not invented.
- **FR-8 — Wire the run path.** `scripts/run_kickoff_panel.py` (and any CLI surface that facilitates)
  sources context via FR-7, not baked defaults; explicit `--desc/--objective/--strategy` args still
  override.
- **FR-9 — Neutral placeholder fallback only.** If context cannot be derived and none is passed, the
  only permitted fallback is a **domain-neutral** placeholder that defers to the artifact
  (`_gather_artifact` already loads the live project), e.g. desc = "the project described by the
  artifact below" — never a demo scenario.

### Workstream 3 — Cleanup & docs

- **FR-10 — Neutralize SDK design-doc references.** Rewrite incidental "the demo is Blue Planet"
  wording to be domain-neutral and point to `DEMO_REGISTRY.yaml`; **annotate** (don't erase) genuine
  historical experiment records (e.g. `PROJECT_START_REQUIREMENTS.md` §experiments).
- **FR-11 — Handle the contaminated portal session.** The benchmark-portal runtime panel session
  (`portal/internal/.startd8/kickoff-panel/kp-20260704T160024-6bdc06.json` + `.view.html`, + the two
  `stakeholder-panel/` sessions) was produced against the contaminated default. After FR-5–FR-9 land,
  delete it and re-run the panel cleanly — OR archive it as evidence with a provenance note. (User
  choice at execution time; not auto-deleted.)
- **FR-12 — Register, don't delete, the origin.** The retail demo is preserved and referenced via
  FR-2. The generated `convergent-review-prompt-…-20260704T1219.md` at the SDK repo root (untracked,
  regenerable) may be deleted.

---

## 3. Non-Requirements

- **NR-1 — Do not delete the origin demo.** `contextcore-demo-retail/`, `ContextCore-wt/**/demo-artifacts/`,
  and `contextcore-dot-me/` content are out of scope for deletion; they are pointed to, not removed.
- **NR-2 — Do not duplicate the rich demo into the SDK.** In-repo fixtures are *neutral and minimal*,
  not a copy of the retail dataset.
- **NR-3 — Do not break tests.** Fixture replacement is paired with the `test_kickoff_view.py` update
  in the same change; the suite stays green.
- **NR-4 — No hard runtime dependency on the registry.** Resolving external demo paths is not required
  for any product code path or CI run.
- **NR-5 — Not a new kickoff-input schema (unless OQ-1 forces it).** Prefer deriving from existing
  domains + the requirements doc; adding a `project-brief` domain is a fallback, not a goal.

---

## 4. Open Questions

- **OQ-1 — Canonical source of `desc`.** `business-targets.yaml` carries goals/targets (→ objective/
  strategy) but **no prose project description**. Where does `desc` come from — the requirements doc's
  header/overview (parse it), a new optional `project-brief` kickoff field/domain, or the
  `_gather_artifact` summary itself? (Prefer: requirements-doc overview, falling back to the artifact
  summary; avoid a new domain per NR-5.)
- **OQ-2 — Neutral fixture domain.** Should `complete_generic.json` model the **benchmark portal**
  (real, already in-hand, non-retail) or a fully synthetic generic project? (Lean: benchmark portal —
  it's the app in front of us and keeps the fixture honest.)
- **OQ-3 — Missing-context behavior (FR-6 vs FR-9).** Hard error, or silent neutral placeholder? A
  hard error surfaces misconfiguration loudly; the placeholder keeps ad-hoc runs working. (Lean:
  error in the script/CLI when context is expected; placeholder only when explicitly opted into.)
- **OQ-4 — Registry schema reuse.** Does an existing SDK manifest/registry convention fit
  `DEMO_REGISTRY.yaml`, or is a fresh small schema cleaner?
- **OQ-5 — Requirements-format parser scope (FR-7).** How much structure can we assume in "the
  requirements format"? A robust heading/section parser vs a thin "read the overview paragraph" — the
  latter is far cheaper and probably sufficient for `desc`.

---

*Draft 0.1 — grounded against `facilitation.py`, `input_domains.py`, `test_kickoff_view.py`,
`scripts/run_kickoff_panel.py`, and the portal kickoff inputs. Next: planning pass to resolve OQ-1/5
(the parser feasibility) before implementation.*
