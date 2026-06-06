# Role Kit CLI (`startd8 kit <role>`) — Requirements

**Version:** 0.1 (Draft — pre-planning)
**Date:** 2026-06-05
**Status:** **DEFERRED — not scheduled.** Per the 2026-06-05 operator decision (Q8, recorded in
`../HITM_ROLE_MODEL_REQUIREMENTS.md` OQ-5): role kits are **docs-first now**; this CLI is the
natural v2 once kits stabilize. This doc exists so the v2 phase starts from agreed requirements
instead of a blank page.
**Parent:** [`../HITM_ROLE_MODEL_REQUIREMENTS.md`](../HITM_ROLE_MODEL_REQUIREMENTS.md) — FR-J9
(kit completeness criteria), FR-J1 (role registry), §3 role map (11 roles)
**Precedent:** [`../wireframe/WIREFRAME_REQUIREMENTS.md`](../wireframe/WIREFRAME_REQUIREMENTS.md)
— `startd8 wireframe` (built 2026-06-05): the $0 / read-only / advisory CLI pattern this command
mirrors (FR-W2 determinism, FR-W9 exit semantics, FR-W10 JSON, FR-W11 pipeline hook, FR-W14
anti-divergence, FR-W16 stable API).

> **Reflective-loop status.** Phase 1 (draft) + a light grounding pass against the wireframe
> spec and CLI conventions were done at authoring time. **The full planning pass (Phases 2–4)
> is deliberately deferred to the implementing project** — see §5 for the checklist that pass
> must execute before any code. Expect the usual share of v0.1 assumptions to be wrong; that is
> the loop working, later.

---

## 1. Problem Statement

The docs-first kits (v1, in place) give each delivery role its templates, checklists, and
validation-artifact pointers as markdown. Expected friction as usage grows — the demand signals
that would justify this v2:

| Friction | Docs-first reality | What the CLI adds |
|----------|--------------------|--------------------|
| Discoverability | "Which docs belong to *my* role for *this* project?" requires knowing the doc set | `startd8 kit architect` answers it in one command |
| Per-project resolution | Kit components are generic templates; the project-specific instances (this project's polish report, FDE preflight, inventory) live elsewhere | Kit resolves template → this-project instance where one exists |
| Completeness checking | FR-J9's "kit is complete iff (a) draft template, (b) review checklist, (c) named validation artifact" is verified by hand | Machine-checked, per role, feeding the FR-X1 kit-completeness field |
| CI consumption | None | `--json` (schema-versioned), wireframe-style |

**Not a build trigger by itself:** this ships only when the §5 activation criteria are met.

---

## 2. Requirements

### Command surface

- **FR-KIT-1 — Command + role IDs.** `startd8 kit <role>` renders one role's kit;
  `startd8 kit` (no argument) or `startd8 kit --all` renders the cross-role list view (role ×
  completeness table). Role IDs are the 11 delivery roles of the HITM §3 map in kebab-case:
  `customer-po`, `ba`, `pm`, `architect`, `backend-dev`, `frontend-dev`, `dba`, `ops`,
  `test-engineer`, `qa`, `security`. *(Assumption to verify in the planning pass: whether the
  FR-J1 role registry exists as a readable artifact by then, or the 11 IDs are a CLI-internal
  constant seeded from HITM §3 — see OQ-1.)*
- **FR-KIT-2 — $0, read-only, advisory (wireframe semantics).** No LLM calls, no network, no
  filesystem writes (except an optional `--out` for the JSON view). **Advisory exit 0**
  regardless of kit completeness; exit 2 only for an unreadable explicitly-passed input (the
  FR-W9 rule). Never a gate — CI that wants to gate parses the JSON.

### Kit content & resolution

- **FR-KIT-3 — Kit view = FR-J9 completeness criteria.** For the selected role, render: (a) the
  role's **draft template(s)**, (b) its **review checklist**, (c) the **named validation
  artifact** for the role's HITM §3 gate — each as a path + one-line description + status. The
  view also names the role's gate ("what you approve, in which artifact form") verbatim from
  the role map.
- **FR-KIT-4 — Docs remain canonical (anti-fork).** The CLI is a *view over* the docs-first kit
  sources — it MUST NOT embed divergent copies of template/checklist content. A unit test MUST
  assert the CLI's component list for each role matches the docs-side kit definitions
  (the FR-W14 anti-divergence pattern applied to kits).
- **FR-KIT-5 — Per-project resolution with component status.** Run inside a project, each kit
  component resolves to the **project-specific instance** when present (e.g. BA →
  `polish-report.json`, Ops → `fde-preflight.md` + the credential-presence checklist, PM → the
  FR-X5 inventory + plan, Architect → the ingestion-generated convention manifest, QA → the
  postmortem/batch summaries); otherwise to the SDK template. Each component carries a status:
  `project-instance | template-only | absent`. Outside a project, templates render with a note.
- **FR-KIT-6 — Completeness assessment.** Emit the FR-J9 per-role kit-completeness verdict
  (complete iff a/b/c all resolve) — the machine source for the FR-X1 pre-flight report's
  kit-completeness field. Statuses are honest (`template-only` is not `absent`, and neither is
  failure — advisory posture).

### Output & integration

- **FR-KIT-7 — Rich summary + `--json`.** Default: Rich table per the wireframe rendering
  conventions. `--json` emits the full kit view (schema-versioned, stable-key) to stdout and
  suppresses Rich unless `--verbose` (FR-W10 conventions).
- **FR-KIT-8 — Optional cap-dev-pipe read-only hook.** Optionally invocable from cap-dev-pipe
  as a visibility step (FR-W11 pattern) so the pre-flight report can include kit completeness
  without the SDK pipeline gaining a new gate. Opt-in, never blocking.
- **FR-KIT-9 — Stable public API.** `build_kit_view(role, project_root) -> KitView` (and the
  JSON serializer) are stable public surface (FR-W16 pattern), so the pipeline hook, tests, and
  any future portal render from one code path.

---

## 3. Non-Requirements

- **No workflow tooling** — no assignment, notification, or SLA machinery (HITM §5 stands).
- **No approval recording** — gates and records stay operator-coordinated (2026-06-05 Q2);
  the kit *names* the validation artifact, it never records sign-off.
- **No content generation** — the kit points at generators and templates; it never runs
  generation or drafts content itself ($0 posture).
- **No gating** — no `--fail-on-incomplete`; advisory exit semantics are load-bearing (FR-KIT-2).
- **Not a portal** — single-command terminal views only; any HTML/portal rendering belongs to
  the observability portal track, not this CLI.

---

## 4. Open Questions (seeds for the deferred planning pass)

1. **OQ-1 — Role-ID source.** Hardcoded 11-role constant seeded from HITM §3, or a readable
   FR-J1 registry artifact (if one exists by then)? Constant is simpler; registry is one source
   of truth. *(Lean: constant in v1 of the CLI, registry when FR-J1 materializes.)*
2. **OQ-2 — SDK template home.** Where do the SDK-side kit templates live for the CLI to read:
   `docs/design/kickoff/` (where they are today), `src/startd8/help_content/` (the existing
   packaged-help system — overlap to investigate), or a new `kits/` package data dir? Packaging
   matters: `docs/` isn't shipped in wheels.
3. **OQ-3 — Relationship to `startd8 assist`.** The Service Assistant already surfaces triage
   and (per Q5) the inventory drift check. Does `kit` link to assist outputs, or does assist
   grow a `kit` subcommand? One CLI family vs two.
4. **OQ-4 — Customer/PO kit shape.** The §3.0 role is pure tier U — its "kit" is mostly the
   things *presented to* them (UAT drafts, starter values to approve). Does a terminal CLI
   serve that persona at all, or does the customer-po kit just render the request list
   (defaults doc §3) for the operator to relay?

---

## 5. Activation Criteria + Deferred Planning-Pass Checklist

**Build this only when** (any combination signaling real demand):
- the docs-first kits have been used across ≥ 1 full increment and the discoverability friction
  in §1 is *observed*, not predicted; and
- `startd8 wireframe` is committed/stable (the pattern this mirrors); and
- the role docs/templates have stabilized enough that FR-KIT-4's anti-fork test has something
  fixed to assert against.

**The implementing project MUST run reflective-loop Phases 2–4 before coding**, verifying at
minimum:
- [ ] `cli_wireframe.py` registration pattern + Rich/JSON conventions still as grounded here
- [ ] `help_content/` overlap (OQ-2) — read it before inventing a template home
- [ ] FR-J1 registry existence (OQ-1) and the current role list (HITM §3 may have evolved)
- [ ] The actual docs-first kit component inventory per role (what FR-KIT-5 resolves to)
- [ ] `startd8 assist` surface (OQ-3) for CLI-family consolidation
- [ ] Then: update this doc to v0.2 with the §0 Planning Insights table, resolve OQs, and offer
      CRP per the loop.

---

*Draft 0.1 — deferred-phase requirements; light grounding only (wireframe spec + CLI
conventions). The full planning pass and any implementation belong to the later phase/project
that activates this per §5.*
