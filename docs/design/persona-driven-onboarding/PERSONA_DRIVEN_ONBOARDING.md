# Persona-Driven Onboarding — the human-facing half of observability generation

**Status:** design draft (2026-08-07) · **Author:** o11y-sapper session · **Depends on:** the o11y
generation surface (SCORE-1..4), `kickoff_experience/portal_spec_v2.py`, `stakeholder_panel/`,
`concierge/audience.py`, `integrations/contextcore.py`.

## 1. The thesis (why this exists)

We have spent the pilot perfecting the **substance** — o11y coverage/fidelity (bridge SCORE-1,
system SCORE-3, human SCORE-4, L1c/RED correctness). But *the substance is not the value a human
receives.* Most teams never get the most out of observability tooling because the **onboarding
surface** — the persona-tiered, value-framed view that makes the substance legible — is the last
thing built, if ever. This doc makes that surface a first-class, generated artifact, driven by the
same manifests the o11y is.

**The proof it works already exists** (`~/Documents/ContextCore/Demo/demo-runs/2026-05-14-fallback/`):
the online-boutique build produced a **role-tiered portal** — `cc-portal-online-boutique-{executive,
manager,engineer}` — with two features that are the whole point:

- **Derived business observability (dollar-escalation per audience).** *The same manifest* produced
  **$475K/yr (Engineer) · $258K (Manager) · $1.3M aggregate (Executive)** — same facts, framed for
  each audience. Observability *derived from the value/persona model*, not bolted on.
- **Honest self-reported gaps.** The Executive tab showed **Composite 67% but SLO 0%** — "the system
  tells the Executive, in their own dashboard, that the team skipped SLOs." **This is exactly the
  number our SCORE-3 work moves.** The coverage lift *is* the business signal.

## 2. The mechanism (extracted from the reference demos)

Both the Insight-Finder (astronomy shop) and ContextCore retail demos run on a **`PersonaManifest`**
(`kind: PersonaManifest`, `personas/roles.yaml`) — roles with a `character`, `department`, a
`contextcore_persona` archetype, `service_tier_exposure`, and `capabilities` — and *that manifest
drives* the generated SLOs / alert rules / dashboards. The N roles collapse to a small archetype set,
which tiers into **three audiences**:

| Audience tier | `contextcore_persona` archetypes | Consumes | Value framing |
|---|---|---|---|
| **Business** | `engineering_leader`, `compliance_officer` | criticality map, **value-weighted** health, coverage-as-KPI | aggregate $ pain, "is it good + improving?" |
| **Functional** | `project_manager` (PM / owner) | per-service health, remediation queue, "what to fix next" | scoped $ pain, progress |
| **Technical** | `developer`, `operator` (SRE) | RED SLOs/alerts, per-artifact coverage, traces, dead-SLI findings | precise $ pain, the raw artifacts |

**Two orthogonal axes** (both already partly in the SDK): the **role** axis above (executive/manager/
engineer — the demo portal) × the **disclosure** axis (`beginner/intermediate/advanced` —
`concierge/audience.py`, `portal_spec_v2._AUDIENCES`). A persona = (role tier, disclosure level).

## 3. What this app already has (connect, don't reinvent)

- **Authoring:** `stakeholders.yaml` kickoff input + `stakeholder_panel/` (roster, persona, panel) —
  ~90% of a `PersonaManifest`; missing only `contextcore_persona` + `service_tier_exposure`.
- **Generator:** `kickoff_experience/portal_spec_v2.py:build_workbook_v2` ($0 deterministic dynamic
  workbook) — currently carries the **disclosure** axis; needs the **role** axis + the value framing.
- **Disclosure axis:** `concierge/audience.py` (beginner/intermediate/advanced).
- **ContextCore:** `integrations/contextcore.py` — personas ARE `contextcore_persona` archetypes;
  the span/task model is already persona-aware.
- **The data:** `observability-quality.json` (our SCORE-1..4 coverage/fidelity) — the exact feed the
  Business tab's "artifact quality" gauge + honest-gaps signal read.

## 4. The gap (demonstrated ≠ in the SDK)

1. **Role axis** (executive/manager/engineer) — proven in the demo portal, not in `build_workbook_v2`
   (which has only the disclosure axis).
2. **Derived business observability** — the per-audience **$ pain framing** (`per_role_top_goals` in
   `business-targets.yaml` is the seed) — demonstrated, not an SDK primitive.
3. **Honest-gaps → business** — surfacing `observability-quality.json` coverage/SLO% *in the Business
   tab* as a signal a sponsor can act on. (The data is ours; the surfacing is missing.)

## 5. Plan

1. **Extend `stakeholders.yaml` → a `PersonaManifest`** kickoff input (add `contextcore_persona`,
   `service_tier_exposure`, `capabilities`) — reuse the stakeholder_panel roster; draft in
   `personas/roles.yaml` (this dir). Two altitudes:
   - **(a) observed subject** (Harbor / boutique) — roles of the app being watched.
   - **(b) toolchain operation** (startd8-sdk + ContextCore pilot) — roles of the people *running the
     pilot* (sponsor / FDE / sapper). **This is the adoption lever**; see the draft manifest.
2. **Add the role axis + value framing to `build_workbook_v2`** (or the CC portal): emit a
   Business / Functional / Technical tab per persona tier, reading `observability-quality.json` for
   the coverage/fidelity KPIs + honest-gaps, and `per_role_top_goals` for the $ framing.
3. **Wire through kickoff** so each persona gets *their* artifact (portal tab + guided experience),
   personalized by (role tier × disclosure level).
4. **Reference build first:** regenerate the boutique's `cc-portal-*-{executive,manager,engineer}` on
   current SDK, then generate the **Harbor** persona portal showing the coverage we lifted (SCORE-3/4)
   — closing the loop: our substance work becomes the number the Executive sees improve.

## 6. The narrative frame (onboarding, not just dashboards)

`~/Documents/ContextCore/Demo/tale-of-2companies/` — "a tale of 2 teams": two retail eComm firms, same
microservices, same OOM incident; one has Context (kickoff→launch→big-day in 3 days), one doesn't. The
persona portal is where that story is *shown per role* — the Executive sees $ risk, the SRE sees the
dead SLI. Onboarding = the persona meeting their own view on day one.
